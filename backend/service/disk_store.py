from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.model.schemas import (
    CURRENT_DISKS_PATH,
    SCAN_HISTORY_DIR,
    build_scan_id,
    now_iso,
    safe_scan_id,
    summarize_disks,
)


class DiskStore:
    """Persist the current disk pool and scan history snapshots."""

    def __init__(self) -> None:
        self.current_disks_path = Path(CURRENT_DISKS_PATH)
        self.scan_history_dir = Path(SCAN_HISTORY_DIR)
        self._lock = threading.RLock()

        self.current_disks_path.parent.mkdir(parents=True, exist_ok=True)
        self.scan_history_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            if not self.current_disks_path.exists():
                self._atomic_write(self.current_disks_path, [])
                self._current_disks: list[dict[str, Any]] = []
            else:
                self._current_disks = self._read_current_disks()

    def get_current_disks(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._current_disks)

    def save_current_disks(self, disks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock:
            saved = copy.deepcopy(disks)
            self._atomic_write(self.current_disks_path, saved)
            self._current_disks = saved
            return copy.deepcopy(saved)

    def save_scan_result(
        self,
        disks: list[dict[str, Any]],
        source: str,
        logs: list[Any],
        scan_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            scan_id = scan_id or build_scan_id()
            history_path = self._history_path(scan_id)
            if history_path.exists():
                raise FileExistsError(f"scan history already exists: {scan_id}")

            scanned_at = now_iso()
            normalized_disks = self._prepare_scan_disks(disks, scan_id, scanned_at)
            record = {
                "scan_id": scan_id,
                "scanned_at": scanned_at,
                "source": source,
                "logs": copy.deepcopy(logs),
                "disk_count": len(normalized_disks),
                "summary": summarize_disks(normalized_disks),
                "disks": normalized_disks,
            }

            old_current = self._read_current_disks()
            self._atomic_write(self.current_disks_path, normalized_disks)
            try:
                self._atomic_write(history_path, record)
            except Exception:
                try:
                    self._atomic_write(self.current_disks_path, old_current)
                    self._current_disks = copy.deepcopy(old_current)
                except Exception:
                    pass
                raise
            self._current_disks = copy.deepcopy(normalized_disks)
            return copy.deepcopy(record)

    def list_scan_history(self) -> list[dict[str, Any]]:
        with self._lock:
            summaries = []
            for path in self.scan_history_dir.glob("*.json"):
                record = self._read_history_file(path)
                summaries.append(self._summarize_history_record(record))
            summaries.sort(key=lambda item: (item.get("scanned_at", ""), item.get("scan_id", "")), reverse=True)
            return copy.deepcopy(summaries)

    def get_scan_result(self, scan_id: str) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._read_history_file(self._history_path(scan_id)))

    def delete_scan_result(self, scan_id: str) -> bool:
        with self._lock:
            path = self._history_path(scan_id)
            if not path.exists():
                return False
            path.unlink()
            return True

    def use_scan_result(self, scan_id: str) -> list[dict[str, Any]]:
        with self._lock:
            record = self._read_history_file(self._history_path(scan_id))
            disks = copy.deepcopy(record.get("disks", []))
            self._atomic_write(self.current_disks_path, disks)
            self._current_disks = copy.deepcopy(disks)
            return copy.deepcopy(disks)

    def _history_path(self, scan_id: str) -> Path:
        if not safe_scan_id(scan_id):
            raise ValueError(f"invalid scan_id: {scan_id!r}")
        return self.scan_history_dir / f"{scan_id}.json"

    def _prepare_scan_disks(self, disks: list[dict[str, Any]], scan_id: str, scanned_at: str) -> list[dict[str, Any]]:
        prepared = []
        for disk in copy.deepcopy(disks):
            if not isinstance(disk, dict):
                raise ValueError("disk entries must be objects")
            disk.setdefault("id", uuid4().hex)
            scan_meta = disk.get("scan_meta")
            if not isinstance(scan_meta, dict):
                scan_meta = {}
            scan_meta["scan_id"] = scan_id
            scan_meta["scanned_at"] = scanned_at
            disk["scan_meta"] = scan_meta
            prepared.append(disk)
        return prepared

    def _read_current_disks(self) -> list[dict[str, Any]]:
        try:
            data = self._read_json(self.current_disks_path)
        except ValueError as exc:
            raise ValueError(f"Failed to read current disks JSON: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError("Failed to read current disks JSON: root must be a list")
        return data

    def _read_history_file(self, path: Path) -> dict[str, Any]:
        try:
            data = self._read_json(path)
        except ValueError as exc:
            raise ValueError(f"Failed to read scan history JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Failed to read scan history JSON: root must be an object")
        return data

    def _read_json(self, path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError as exc:
            raise ValueError(str(exc)) from exc
        except OSError as exc:
            raise ValueError(str(exc)) from exc

    def _summarize_history_record(self, record: dict[str, Any]) -> dict[str, Any]:
        disks = record.get("disks", [])
        summary = record.get("summary")
        if not isinstance(summary, dict) and isinstance(disks, list):
            summary = summarize_disks(disks)
        return {
            "scan_id": record.get("scan_id"),
            "scanned_at": record.get("scanned_at"),
            "source": record.get("source"),
            "logs": copy.deepcopy(record.get("logs", [])),
            "disk_count": record.get("disk_count", len(disks) if isinstance(disks, list) else 0),
            "summary": copy.deepcopy(summary or {}),
        }

    def _atomic_write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                dir=path.parent,
                encoding="utf-8",
                mode="w",
                prefix=f"{path.name}.{uuid4().hex}.",
                suffix=".tmp",
            ) as file:
                temp_path = file.name
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temp_path, path)
            temp_path = None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
