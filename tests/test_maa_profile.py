import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from backend.service.maa_profile import (
    DEFAULT_SCAN_PROFILE,
    RESOURCE_ROOT,
    cell_center,
    ensure_scan_resource_tree,
    load_scan_profile,
    position_from_index,
    validate_disk,
    write_debug_artifacts,
)


@pytest.fixture
def temp_dir():
    path = Path(__file__).parent / ".tmp_maa_profile" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_ensure_scan_resource_tree_creates_profile_and_dirs(temp_dir):
    root = ensure_scan_resource_tree(temp_dir / "zzz_disk_scan")

    assert (root / "config" / "scan_profile.json").exists()
    assert (root / "pipeline" / "scan_disks.json").exists()
    assert (root / "image").is_dir()
    assert (root / "debug").is_dir()


def test_default_resource_root_uses_maaframework_asset_bundle():
    assert RESOURCE_ROOT.parts[-2:] == ("assets", "resource")


def test_scan_pipeline_exposes_maaframework_entry(temp_dir):
    root = ensure_scan_resource_tree(temp_dir / "resource")

    pipeline = json.loads((root / "pipeline" / "scan_disks.json").read_text(encoding="utf-8"))

    assert "ScanDisks" in pipeline
    assert pipeline["ScanDisks"]["action"] == "Custom"
    assert pipeline["ScanDisks"]["custom_action"] == "ScanDiskInventory"


def test_cell_center_and_position_from_index_use_grid_profile():
    profile = DEFAULT_SCAN_PROFILE

    assert cell_center(profile, 2, 3) == (660, 420)
    assert position_from_index(profile, page=2, index=8) == {
        "page": 2,
        "row": 2,
        "column": 3,
        "index": 8,
        "x": 660,
        "y": 420,
    }


def test_load_scan_profile_rejects_invalid_grid(temp_dir):
    profile_path = temp_dir / "scan_profile.json"
    profile_path.write_text(json.dumps({"inventory_grid": {"rows": 0}}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_scan_profile(profile_path)


def test_validate_disk_normalizes_inventory_pos_col_alias():
    disk = validate_disk(
        {
            "slot": 5,
            "set_name": "极地重金属",
            "level": 1,
            "inventory_pos": {"page": 1, "row": 2, "col": 3, "index": 8},
            "main_stat": {"name": "冰属性伤害", "value": 7.2},
            "sub_stats": [],
        }
    )

    assert disk["inventory_pos"] == {"page": 1, "row": 2, "column": 3, "index": 8}


def test_validate_disk_rejects_invalid_slot():
    with pytest.raises(ValueError):
        validate_disk(
            {
                "slot": 9,
                "level": 1,
                "inventory_pos": {"page": 1, "row": 1, "column": 1},
                "main_stat": {"name": "攻击力", "value": 10},
                "sub_stats": [],
            }
        )


def test_write_debug_artifacts(temp_dir):
    write_debug_artifacts(temp_dir, {"disk_count": 2}, ["a", "b"])

    result = json.loads((temp_dir / "latest_result.json").read_text(encoding="utf-8"))
    assert result["disk_count"] == 2
    assert (temp_dir / "latest_logs.txt").read_text(encoding="utf-8") == "a\nb"
