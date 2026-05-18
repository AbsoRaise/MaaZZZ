from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import re


APP_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = APP_ROOT / "data"
CHARACTER_BUILDS_PATH = DATA_DIR / "character_builds.json"
CURRENT_DISKS_PATH = DATA_DIR / "disks.json"
SCAN_HISTORY_DIR = DATA_DIR / "scan_history"
DISK_TYPES_PATH = DATA_DIR / "disk_types.json"
MAIN_STATS_PATH = DATA_DIR / "main_stats.json"
SUB_STATS_PATH = DATA_DIR / "sub_stats.json"


DEFAULT_CHARACTER_BUILDS = {
    "艾莲·乔": {
        "weights": {
            "暴击率": 1.0,
            "暴击伤害": 1.0,
            "攻击力%": 0.8,
            "穿透值": 0.45,
        },
        "preferred_main_stats": {
            "4": ["暴击率", "暴击伤害"],
            "5": ["冰属性伤害", "攻击力%"],
            "6": ["攻击力%"],
        },
        "preferred_sets": {
            "target_set_4": "极地重金属",
            "target_set_2": "啄木鸟电音",
        },
    }
}


_SCAN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-fA-F]{4,12}$")
_MAIN_STAT_SLOTS = {1, 2, 3, 4, 5, 6}
_PREFERRED_MAIN_STAT_SLOTS = {4, 5, 6}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_scan_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"


def safe_scan_id(scan_id: object) -> bool:
    if not isinstance(scan_id, str):
        return False
    return bool(_SCAN_ID_PATTERN.fullmatch(scan_id))


def normalize_slot_main_stats(raw: dict[object, object] | None) -> dict[int, str]:
    if not raw:
        return {}

    normalized: dict[int, str] = {}
    for slot, value in raw.items():
        if not isinstance(value, str) or not value:
            continue
        try:
            slot_number = int(slot)
        except (TypeError, ValueError):
            continue
        if slot_number in _MAIN_STAT_SLOTS:
            normalized[slot_number] = value
    return normalized


def normalize_preferred_main_stats(raw: dict[object, object] | None) -> dict[str, list[str]]:
    if not raw:
        return {}

    normalized: dict[str, list[str]] = {}
    for slot, value in raw.items():
        try:
            slot_number = int(slot)
        except (TypeError, ValueError):
            continue
        if slot_number not in _PREFERRED_MAIN_STAT_SLOTS:
            continue

        values = value if isinstance(value, list) else [value]
        main_stats = [item for item in values if isinstance(item, str) and item]
        if main_stats:
            normalized[str(slot_number)] = main_stats
    return normalized


def summarize_disks(disks: list[dict[str, object]] | tuple[dict[str, object], ...]) -> dict[str, dict[str, int]]:
    slot_counts: Counter[str] = Counter()
    set_counts: Counter[str] = Counter()

    for disk in disks:
        slot = disk.get("slot")
        set_name = disk.get("set_name")
        if slot is not None:
            slot_counts[str(slot)] += 1
        if set_name:
            set_counts[str(set_name)] += 1

    return {
        "slot_counts": dict(slot_counts),
        "set_counts": dict(set_counts),
    }
