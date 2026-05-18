from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.service.character_config_manager import CharacterConfigManager
from backend.service.cultivation_advisor import CultivationAdvisor
from backend.service.disk_store import DiskStore
from backend.service.disk_metadata import DiskMetadataStore
from backend.service.maa_scanner import MaaScanner
from backend.service.optimizer import DiskOptimizer

try:
    import webview
except ImportError:  # pragma: no cover - 本地编译环境可以没有 pywebview
    webview = None


def ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def fail(error: Any) -> dict[str, Any]:
    return {"success": False, "data": None, "error": str(error)}


class DesktopApi:
    def __init__(self) -> None:
        self.character_config_manager = CharacterConfigManager()
        self.disk_store = DiskStore()
        self.disk_metadata_store = DiskMetadataStore()
        self.maa_scanner = MaaScanner()
        self._window: Any = None
        self._scan_lock = threading.Lock()
        self._scan_running = False

    def bind_window(self, window: Any) -> dict[str, Any]:
        try:
            self._window = window
            return ok(True)
        except Exception as exc:
            return fail(exc)

    def get_character_builds(self) -> dict[str, Any]:
        try:
            return ok(self.character_config_manager.get_all())
        except Exception as exc:
            return fail(exc)

    def get_disk_metadata(self) -> dict[str, Any]:
        try:
            return ok(self.disk_metadata_store.get_all())
        except Exception as exc:
            return fail(exc)

    def save_character_build(self, character_name: str, config: dict[str, Any]) -> dict[str, Any]:
        try:
            return ok(self.character_config_manager.save_character_build(character_name, config))
        except Exception as exc:
            return fail(exc)

    def get_current_disks(self) -> dict[str, Any]:
        try:
            return ok(self.disk_store.get_current_disks())
        except Exception as exc:
            return fail(exc)

    def get_scan_history(self) -> dict[str, Any]:
        try:
            return ok(self.disk_store.list_scan_history())
        except Exception as exc:
            return fail(exc)

    def get_scan_result(self, scan_id: str) -> dict[str, Any]:
        try:
            return ok(self.disk_store.get_scan_result(scan_id))
        except Exception as exc:
            return fail(exc)

    def delete_scan_result(self, scan_id: str) -> dict[str, Any]:
        try:
            return ok(self.disk_store.delete_scan_result(scan_id))
        except Exception as exc:
            return fail(exc)

    def use_scan_result(self, scan_id: str) -> dict[str, Any]:
        try:
            return ok(self.disk_store.use_scan_result(scan_id))
        except Exception as exc:
            return fail(exc)

    def get_optimize_combo(
        self,
        character_name: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            optimizer = DiskOptimizer(self.character_config_manager.get_all())
            result = optimizer.find_best_combination(
                character_name,
                config,
                self.disk_store.get_current_disks(),
            )
            return ok(result)
        except Exception as exc:
            return fail(exc)

    def get_promising_disks(
        self,
        character_name: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            advisor = CultivationAdvisor(self.character_config_manager.get_all())
            result = advisor.find_promising_disks(
                character_name,
                options,
                self.disk_store.get_current_disks(),
            )
            return ok(result)
        except Exception as exc:
            return fail(exc)

    def get_maa_scan_profile(self) -> dict[str, Any]:
        try:
            return ok(self.maa_scanner.load_profile())
        except Exception as exc:
            return fail(exc)

    def locate_disk(self, disk_or_pos: dict[str, Any]) -> dict[str, Any]:
        try:
            return ok(self.maa_scanner.locate_disk(disk_or_pos))
        except Exception as exc:
            return fail(exc)

    def scan_from_screenshot(self, image_path: str) -> dict[str, Any]:
        try:
            return ok(self.maa_scanner.scan_from_screenshot(image_path))
        except Exception as exc:
            return fail(exc)

    def start_maa_scan(self) -> dict[str, Any]:
        try:
            with self._scan_lock:
                if self._scan_running:
                    return fail("MAA 扫描已在运行")
                self._scan_running = True

            thread = threading.Thread(target=self._run_maa_scan, daemon=True)
            thread.start()
            return ok({"started": True})
        except Exception as exc:
            with self._scan_lock:
                self._scan_running = False
            return fail(exc)

    def _run_maa_scan(self) -> None:
        try:
            disks, logs = self.maa_scanner.run_scan(
                on_progress=lambda payload: self._push_event("maa-progress", payload)
            )
            record = self.disk_store.save_scan_result(disks, source="maa", logs=logs)
            self._push_event("maa-complete", record)
        except Exception as exc:
            self._push_event("maa-error", {"error": str(exc)})
        finally:
            with self._scan_lock:
                self._scan_running = False

    def _push_event(self, event_name: str, payload: Any) -> None:
        if self._window is None:
            return

        event_json = json.dumps(event_name, ensure_ascii=False)
        payload_json = json.dumps(payload, ensure_ascii=False)
        script = (
            "window.dispatchEvent(new CustomEvent("
            f"{event_json}, {{ detail: {payload_json} }}));"
        )
        try:
            self._window.evaluate_js(script)
        except Exception:
            # 前端窗口可能已关闭，后台任务不因此失败。
            pass


def main() -> None:
    if webview is None:
        raise RuntimeError("未安装 pywebview，无法启动桌面窗口；请先安装 pywebview。")

    index_html = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "index.html"
    if not index_html.exists():
        raise FileNotFoundError(f"前端入口不存在：{index_html}")

    api = DesktopApi()
    window = webview.create_window(
        "绝区零驱动盘助手",
        index_html.as_uri(),
        js_api=api,
        width=1280,
        height=720,
    )
    api.bind_window(window)
    webview.start()


if __name__ == "__main__":
    main()

