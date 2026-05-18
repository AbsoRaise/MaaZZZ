from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.model.schemas import (
    CHARACTER_BUILDS_PATH,
    DEFAULT_CHARACTER_BUILDS,
    normalize_preferred_main_stats,
)


ELLEN_NAME = "艾莲·乔"


class CharacterConfigManager:
    """Manage persisted character build scoring configuration."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.config_path = Path(config_path or CHARACTER_BUILDS_PATH)
        self._lock = threading.RLock()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load_or_init()

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def get_character_build(self, character_name: str) -> dict[str, Any]:
        name = self._normalize_character_name(character_name)
        with self._lock:
            if name not in self._data:
                raise KeyError(name)
            return copy.deepcopy(self._data[name])

    def save_character_build(self, character_name: str, config: dict[str, Any]) -> dict[str, Any]:
        name = self._normalize_character_name(character_name)
        normalized = self._normalize_character_config(config)
        with self._lock:
            candidate = copy.deepcopy(self._data)
            candidate[name] = normalized
            self._atomic_write(candidate)
            self._data = candidate
            return copy.deepcopy(normalized)

    def update_weights(self, character_name: str, new_weights: dict[str, Any]) -> dict[str, Any]:
        name = self._normalize_character_name(character_name)
        with self._lock:
            if name not in self._data:
                raise KeyError(name)
            candidate = copy.deepcopy(self._data)
            updated = copy.deepcopy(candidate[name])
            updated["weights"] = self._normalize_weights(new_weights)
            candidate[name] = updated
            self._atomic_write(candidate)
            self._data = candidate
            return copy.deepcopy(updated)

    def _load_or_init(self) -> dict[str, Any]:
        if not self.config_path.exists():
            data = self._default_builds()
            self._atomic_write(data)
            return data

        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                raise ValueError("character build config root must be an object")
            return self._normalize_all_builds(raw)
        except (json.JSONDecodeError, OSError, ValueError):
            if self.config_path.exists():
                backup_path = self._backup_path()
                self.config_path.replace(backup_path)
            data = self._default_builds()
            self._atomic_write(data)
            return data

    def _default_builds(self) -> dict[str, Any]:
        data = self._normalize_all_builds(copy.deepcopy(DEFAULT_CHARACTER_BUILDS))
        if ELLEN_NAME not in data:
            source = next(iter(data.values()), {})
            data[ELLEN_NAME] = copy.deepcopy(source)
        return data

    def _normalize_all_builds(self, builds: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for name, config in builds.items():
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(config, dict):
                config = {}
            normalized[name.strip()] = self._normalize_character_config(config)
        return normalized

    def _normalize_character_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(config, dict):
            raise ValueError("character build config must be an object")
        return {
            "weights": self._normalize_weights(config.get("weights", {})),
            "preferred_main_stats": normalize_preferred_main_stats(config.get("preferred_main_stats")),
            "preferred_sets": self._normalize_preferred_sets(config.get("preferred_sets")),
        }

    def _normalize_weights(self, weights: dict[str, Any]) -> dict[str, float]:
        if not isinstance(weights, dict):
            return {}

        normalized: dict[str, float] = {}
        for key, value in weights.items():
            if not isinstance(key, str) or not key.strip():
                continue
            try:
                normalized[key.strip()] = float(value)
            except (TypeError, ValueError):
                normalized[key.strip()] = 0.0
        return normalized

    def _normalize_preferred_sets(self, preferred_sets: Any) -> dict[str, Any]:
        if not isinstance(preferred_sets, dict):
            preferred_sets = {}

        return {
            "target_set_4": self._string_or_empty(preferred_sets.get("target_set_4")),
            "target_set_2": self._string_or_empty(preferred_sets.get("target_set_2")),
            "alternatives": self._normalize_alternatives(preferred_sets.get("alternatives")),
        }

    def _normalize_alternatives(self, alternatives: Any) -> list[dict[str, str]]:
        if not isinstance(alternatives, list):
            return []

        normalized: list[dict[str, str]] = []
        for item in alternatives:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "target_set_4": self._string_or_empty(item.get("target_set_4")),
                    "target_set_2": self._string_or_empty(item.get("target_set_2")),
                    "note": self._string_or_empty(item.get("note")),
                }
            )
        return normalized

    def _atomic_write(self, data: dict[str, Any]) -> None:
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                dir=self.config_path.parent,
                encoding="utf-8",
                mode="w",
                prefix=f"{self.config_path.name}.",
                suffix=".tmp",
            ) as file:
                temp_path = file.name
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temp_path, self.config_path)
            temp_path = None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)


    def _backup_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return self.config_path.with_name(f"{self.config_path.name}.bak-{stamp}")

    def _normalize_character_name(self, character_name: str) -> str:
        if not isinstance(character_name, str) or not character_name.strip():
            raise ValueError("character name must not be empty")
        return character_name.strip()

    def _string_or_empty(self, value: Any) -> str:
        return value if isinstance(value, str) else ""
