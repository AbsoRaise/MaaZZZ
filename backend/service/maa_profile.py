from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from backend.model.schemas import APP_ROOT, now_iso


RESOURCE_ROOT = APP_ROOT / "assets" / "resource"
DEFAULT_PROFILE_PATH = RESOURCE_ROOT / "config" / "scan_profile.json"
DEFAULT_DEBUG_DIR = RESOURCE_ROOT / "debug"


DEFAULT_SCAN_PROFILE: dict[str, Any] = {
    "version": 1,
    "name": "zzz_disk_scan_default",
    "resolution": [1920, 1080],
    "inventory_grid": {
        "rows": 4,
        "columns": 5,
        "first_cell_center": [320, 260],
        "cell_gap": [170, 160],
    },
    "actions": {
        "click_delay_ms": 300,
        "page_delay_ms": 600,
        "detail_open_delay_ms": 120,
        "auto_scroll_delay_ms": 180,
        "auto_scroll_settle_delay_ms": 200,
        "selected_retry_delay_ms": 80,
        "scroll_change_threshold": 2.3,
        "detail_change_threshold": 3.0,
        "max_consecutive_unknown_cells": 12,
    },
    "ocr_regions": {
        "slot": None,
        "set_name": None,
        "level": None,
        "main_stat": None,
        "sub_stats": [],
    },
    "debug": {
        "save_latest_result": True,
        "save_logs": True,
    },
    "maa": {
        "enabled": False,
        "controller": "win32",
        "entry": "ScanDisks",
        "dbg_path": None,
        "hwnd": None,
        "window_regex": ".*绝区零.*|.*Zenless.*|.*ZZZ.*",
        "class_regex": "UnityWndClass",
        "screencap": "PrintWindow",
        "mouse": "PostMessageWithCursorPos",
        "keyboard": "PostMessage",
        "pipeline_override": {},
        "visible_grid": {
            "rows": 4,
            "columns": 9,
            "first_cell_center": [166, 276],
            "cell_gap": [136, 175],
            "scan_rows": 4,
            "max_scan_rows": 400,
            "auto_scroll_trigger_row": 4,
            "stable_selected_row": 3,
            "template_match": {
                "enabled": True,
                "templates": ["disk_cell.png", "disk_cell_selected.png"],
                "selected_templates": ["disk_cell_selected.png"],
                "empty_templates": ["disk_cell_empty.png", "empty_cell.png"],
                "empty_templates_threshold": [0.9, 0.9],
                "roi": [100, 210, 1220, 680],
                "first_cell_center": [66, 66],
                "box_coordinate_space": "auto",
                "threshold": [0.78, 0.78],
                "order_by": "Vertical",
                "click_offset": [32, -21],
                "row_tolerance": 70,
                "dedupe_tolerance": [55, 55],
            },
        },
        "detail_ocr_roi": [1380, 258, 470, 540],
        "scan_page": 1,
    },
}


DEFAULT_SCAN_PIPELINE: dict[str, Any] = {
    "ScanDisks": {
        "recognition": "DirectHit",
        "action": "Custom",
        "custom_action": "ScanDiskInventory",
        "custom_action_param": {
            "profile": "config/scan_profile.json",
            "output": "output/latest_scan.json",
        },
        "next": [],
    }
}


def ensure_scan_resource_tree(resource_root: Path | None = None) -> Path:
    root = Path(resource_root or RESOURCE_ROOT)
    for child in ("config", "image", "pipeline", "debug", "output"):
        (root / child).mkdir(parents=True, exist_ok=True)
    profile_path = root / "config" / "scan_profile.json"
    if not profile_path.exists():
        write_json(profile_path, DEFAULT_SCAN_PROFILE)
    pipeline_path = root / "pipeline" / "scan_disks.json"
    if not pipeline_path.exists():
        write_json(pipeline_path, DEFAULT_SCAN_PIPELINE)
    return root


def load_scan_profile(profile_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(profile_path or DEFAULT_PROFILE_PATH)
    if not path.exists():
        ensure_scan_resource_tree(path.parents[1])
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            raw = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"扫描配置 JSON 损坏：{path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("扫描配置根节点必须是对象")
    return normalize_scan_profile(raw)


def normalize_scan_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = copy.deepcopy(DEFAULT_SCAN_PROFILE)
    profile.update({key: value for key, value in raw.items() if key not in {"inventory_grid", "actions", "ocr_regions", "debug", "maa"}})
    profile["inventory_grid"].update(_dict_or_empty(raw.get("inventory_grid")))
    profile["actions"].update(_dict_or_empty(raw.get("actions")))
    profile["ocr_regions"].update(_dict_or_empty(raw.get("ocr_regions")))
    profile["debug"].update(_dict_or_empty(raw.get("debug")))
    profile["maa"].update(_dict_or_empty(raw.get("maa")))
    validate_scan_profile(profile)
    return profile


def validate_scan_profile(profile: dict[str, Any]) -> None:
    grid = _dict_or_empty(profile.get("inventory_grid"))
    rows = int(grid.get("rows") or 0)
    columns = int(grid.get("columns") or 0)
    first = grid.get("first_cell_center")
    gap = grid.get("cell_gap")
    if rows <= 0 or columns <= 0:
        raise ValueError("inventory_grid.rows 和 columns 必须大于 0")
    if not _is_pair(first) or not _is_pair(gap):
        raise ValueError("first_cell_center 和 cell_gap 必须是两个数字")


def cell_center(profile: dict[str, Any], row: int, column: int) -> tuple[int, int]:
    grid = profile["inventory_grid"]
    rows = int(grid["rows"])
    columns = int(grid["columns"])
    if not 1 <= row <= rows:
        raise ValueError(f"row 超出范围：{row}")
    if not 1 <= column <= columns:
        raise ValueError(f"column 超出范围：{column}")
    first_x, first_y = grid["first_cell_center"]
    gap_x, gap_y = grid["cell_gap"]
    return int(first_x + (column - 1) * gap_x), int(first_y + (row - 1) * gap_y)


def position_from_index(profile: dict[str, Any], page: int, index: int) -> dict[str, int]:
    grid = profile["inventory_grid"]
    columns = int(grid["columns"])
    capacity = int(grid["rows"]) * columns
    if page <= 0:
        raise ValueError("page 必须大于 0")
    if not 1 <= index <= capacity:
        raise ValueError(f"index 超出当前页容量：{index}")
    row = (index - 1) // columns + 1
    column = (index - 1) % columns + 1
    x, y = cell_center(profile, row, column)
    return {"page": page, "row": row, "column": column, "index": index, "x": x, "y": y}


def validate_disk(disk: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(disk, dict):
        raise ValueError("驱动盘必须是对象")
    slot = int(disk.get("slot") or 0)
    if not 1 <= slot <= 6:
        raise ValueError(f"驱动盘 slot 必须在 1-6：{slot}")
    level = int(disk.get("level") or 0)
    if not 0 <= level <= 15:
        raise ValueError(f"驱动盘 level 必须在 0-15：{level}")
    main_stat = disk.get("main_stat")
    if not isinstance(main_stat, dict) or not isinstance(main_stat.get("name"), str):
        raise ValueError("驱动盘 main_stat.name 缺失")
    sub_stats = disk.get("sub_stats")
    if sub_stats is None:
        disk["sub_stats"] = []
    elif not isinstance(sub_stats, list):
        raise ValueError("驱动盘 sub_stats 必须是列表")
    disk["inventory_pos"] = normalize_inventory_pos(disk.get("inventory_pos"))
    return disk


def normalize_inventory_pos(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError("inventory_pos 必须是对象")
    page = int(raw.get("page") or 0)
    row = int(raw.get("row") or 0)
    column = int(raw.get("column") or raw.get("col") or 0)
    index = int(raw.get("index") or 0)
    if page <= 0 or row <= 0 or column <= 0:
        raise ValueError("inventory_pos 需要 page/row/column")
    if index <= 0:
        index = (row - 1) * 100 + column
    return {"page": page, "row": row, "column": column, "index": index}


def write_debug_artifacts(debug_dir: Path | str, result: dict[str, Any], logs: list[str]) -> None:
    root = Path(debug_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "latest_result.json", {"created_at": now_iso(), **result})
    (root / "latest_logs.txt").write_text("\n".join(logs), encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_pair(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) for item in value)
