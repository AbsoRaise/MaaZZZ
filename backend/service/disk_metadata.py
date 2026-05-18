from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.model.schemas import DISK_TYPES_PATH, MAIN_STATS_PATH, SUB_STATS_PATH


DEFAULT_DISK_TYPES = [
    "极地重金属",
    "啄木鸟电音",
    "震星迪斯科",
    "激素朋克",
    "獠牙重金属",
    "河豚电音",
    "自由蓝调",
    "混沌重金属",
    "炎狱重金属",
    "雷暴重金属",
    "灵魂摇滚",
    "摇摆爵士",
]

DEFAULT_MAIN_STATS = [
    "生命值",
    "攻击力",
    "防御力",
    "暴击率",
    "暴击伤害",
    "异常精通",
    "穿透率",
    "能量自动回复",
    "冲击力",
    "物理伤害",
    "火属性伤害",
    "冰属性伤害",
    "电属性伤害",
    "以太伤害",
    "异常掌控",
]

DEFAULT_SUB_STATS = [
    "生命值",
    "攻击力",
    "防御力",
    "暴击率",
    "暴击伤害",
    "异常精通",
    "穿透值",
]


class DiskMetadataStore:
    def __init__(
        self,
        disk_types_path: Path | str | None = None,
        main_stats_path: Path | str | None = None,
        sub_stats_path: Path | str | None = None,
    ) -> None:
        self.disk_types_path = Path(disk_types_path or DISK_TYPES_PATH)
        self.main_stats_path = Path(main_stats_path or MAIN_STATS_PATH)
        self.sub_stats_path = Path(sub_stats_path or SUB_STATS_PATH)

    def get_all(self) -> dict[str, list[str]]:
        return {
            "disk_types": self._load_list(self.disk_types_path, DEFAULT_DISK_TYPES),
            "main_stats": self._load_list(self.main_stats_path, DEFAULT_MAIN_STATS),
            "sub_stats": self._load_list(self.sub_stats_path, DEFAULT_SUB_STATS),
            "rarities": ["S", "A", "B"],
            "slots": ["1", "2", "3", "4", "5", "6"],
        }

    def _load_list(self, path: Path, default: list[str]) -> list[str]:
        if not path.exists():
            self._write_list(path, default)
            return list(default)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"枚举 JSON 损坏：{path}") from exc
        if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
            raise ValueError(f"枚举文件必须是字符串数组：{path}")
        return raw

    def _write_list(self, path: Path, values: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
