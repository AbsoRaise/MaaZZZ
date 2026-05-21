import shutil
import json
from pathlib import Path
from uuid import uuid4

import pytest

from backend.service.maa_scanner import (
    MaaScanner,
    ScanCancelled,
    _is_confirmed_empty_cell,
    _reached_bottom_after_bottom_click,
    _scan_strategy,
    _should_accept_detail_after_click,
    _should_stop_at_empty_or_unmatched_cell,
    grid_cells_from_template_matches,
    iter_grid_scan_targets,
    parse_detail_ocr_results,
)


@pytest.fixture
def temp_dir():
    path = Path(__file__).parent / ".tmp_maa_scanner" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_run_scan_emits_progress_and_writes_debug(temp_dir):
    events = []
    scanner = MaaScanner(resource_root=temp_dir / "resources", debug_dir=temp_dir / "debug")

    disks, logs = scanner.run_scan(events.append)

    assert events[0]["progress"] == 5
    assert events[-1]["progress"] == 100
    assert len(disks) == 2
    assert logs[-1] == "Maa 占位扫描完成"
    assert (temp_dir / "debug" / "latest_result.json").exists()


def test_run_scan_can_be_cancelled_before_work_starts(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources", debug_dir=temp_dir / "debug")

    with pytest.raises(ScanCancelled, match="扫描已中止"):
        scanner.run_scan(cancel_requested=lambda: True)


def test_run_scan_uses_maaframework_runtime_when_enabled(temp_dir):
    events = []
    runtime = FakeMaaRuntime()
    scanner = MaaScanner(
        resource_root=temp_dir / "resources",
        debug_dir=temp_dir / "debug",
        maa_runtime=runtime,
    )
    profile = scanner.profile | {"maa": {"enabled": True, "controller": "dbg", "entry": "ScanDisks"}}
    scanner.profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    disks, logs = scanner.run_scan(events.append)

    assert disks == []
    assert runtime.calls == [
        ("connect", scanner.profile),
        ("run_task", "ScanDisks", scanner.profile),
    ]
    assert events[-1]["message"] == "MaaFramework 任务执行完成"
    assert logs[-1] == "MaaFramework 任务执行完成"


def test_run_scan_does_not_fall_back_when_maa_connection_fails(temp_dir):
    events = []
    runtime = FailingConnectRuntime()
    scanner = MaaScanner(
        resource_root=temp_dir / "resources",
        debug_dir=temp_dir / "debug",
        maa_runtime=runtime,
    )
    profile = scanner.profile | {"maa": {"enabled": True, "controller": "win32"}}
    scanner.profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="未找到匹配的绝区零窗口"):
        scanner.run_scan(events.append)

    assert runtime.calls == [("connect", scanner.profile)]
    debug_result = json.loads((temp_dir / "debug" / "latest_result.json").read_text(encoding="utf-8"))
    assert "未找到匹配的绝区零窗口" in debug_result["error"]
    assert "disks" not in debug_result


def test_run_scan_falls_back_when_maaframework_disabled(temp_dir):
    runtime = FakeMaaRuntime()
    scanner = MaaScanner(resource_root=temp_dir / "resources", maa_runtime=runtime)
    profile = scanner.profile | {"maa": {"enabled": False}}
    scanner.profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    disks, logs = scanner.run_scan()

    assert len(disks) == 2
    assert runtime.calls == []
    assert logs[-1] == "Maa 占位扫描完成"


def test_scan_strategy_defaults_to_legacy_template(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources")

    assert _scan_strategy(scanner.profile) == "legacy_template"


def test_scan_strategy_can_select_row_major_template(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources")
    profile = scanner.profile | {"maa": scanner.profile["maa"] | {"scan_strategy": "row_major_template"}}

    assert _scan_strategy(profile) == "row_major_template"


def test_locate_disk_returns_visible_grid_click_coordinates(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources")

    result = scanner.locate_disk({"inventory_pos": {"row": 2, "column": 3}})

    assert result["supported"] is False
    assert result["target"] == {"row": 2, "column": 3, "visual_row": 2, "x": 438, "y": 451}


def test_scan_from_screenshot_copies_file_to_debug_dir(temp_dir):
    image = temp_dir / "inventory.png"
    image.write_bytes(b"fake png")
    scanner = MaaScanner(resource_root=temp_dir / "resources", debug_dir=temp_dir / "debug")

    result = scanner.scan_from_screenshot(image)

    assert Path(result["debug_screenshot"]).read_bytes() == b"fake png"


def test_scan_from_screenshot_rejects_missing_file(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources")

    with pytest.raises(FileNotFoundError):
        scanner.scan_from_screenshot(temp_dir / "missing.png")


def test_parse_detail_ocr_results_extracts_disk_detail():
    disk = parse_detail_ocr_results(
        [
            {"text": "沧浪行歌[1]", "box": [944, 181, 102, 21], "score": 0.97},
            {"text": "主属性", "box": [952, 303, 41, 18], "score": 0.98},
            {"text": "生命值", "box": [951, 327, 46, 22], "score": 0.99},
            {"text": "2200", "box": [1169, 327, 43, 22], "score": 0.99},
            {"text": "副属性", "box": [952, 355, 41, 19], "score": 0.99},
            {"text": "防御力+1", "box": [951, 380, 67, 21], "score": 0.99},
            {"text": "30", "box": [1187, 380, 26, 22], "score": 0.99},
            {"text": "暴击伤害", "box": [953, 416, 57, 18], "score": 0.99},
            {"text": "+2", "box": [1006, 417, 24, 15], "score": 0.99},
            {"text": "14.4%", "box": [1163, 414, 50, 22], "score": 0.99},
            {"text": "攻击力+1", "box": [951, 449, 67, 20], "score": 0.99},
            {"text": "6%", "box": [1183, 448, 30, 23], "score": 0.96},
            {"text": "暴击率", "box": [951, 482, 46, 22], "score": 0.99},
            {"text": "2.4%", "box": [1170, 482, 42, 23], "score": 0.99},
            {"text": "查看效果", "box": [955, 516, 47, 11], "score": 0.5},
            {"text": "等级15/15", "box": [979, 269, 84, 21], "score": 0.99},
        ],
        {"page": 1, "row": 1, "column": 1, "index": 1},
    )

    assert disk is not None
    assert disk["slot"] == 1
    assert disk["set_name"] == "沧浪行歌"
    assert disk["level"] == 15
    assert disk["main_stat"] == {"name": "生命值", "value": "2200"}
    assert disk["sub_stats"] == [
        {"name": "防御力", "value": "30", "upgrade": 1},
        {"name": "暴击伤害", "value": "14.4%", "upgrade": 2},
        {"name": "攻击力", "value": "6%", "upgrade": 1},
        {"name": "暴击率", "value": "2.4%"},
    ]


def test_parse_detail_ocr_results_ignores_non_stat_detail_text():
    disk = parse_detail_ocr_results(
        [
            {"text": "极地重金属[4]", "box": [944, 181, 102, 21], "score": 0.97},
            {"text": "主属性", "box": [952, 303, 41, 18], "score": 0.98},
            {"text": "暴击率", "box": [951, 327, 46, 22], "score": 0.99},
            {"text": "24%", "box": [1169, 327, 43, 22], "score": 0.99},
            {"text": "副属性", "box": [952, 355, 41, 19], "score": 0.99},
            {"text": "暴击伤害", "box": [951, 380, 67, 21], "score": 0.99},
            {"text": "9.6%", "box": [1187, 380, 42, 22], "score": 0.99},
            {"text": "套装效果", "box": [951, 415, 67, 21], "score": 0.99},
            {"text": "二件套：冰属性伤害提升", "box": [951, 445, 190, 21], "score": 0.96},
            {"text": "查看效果", "box": [955, 516, 47, 11], "score": 0.5},
            {"text": "等级15/15", "box": [979, 269, 84, 21], "score": 0.99},
        ],
        {"page": 1, "row": 1, "column": 1, "index": 1},
    )

    assert disk is not None
    assert disk["main_stat"] == {"name": "暴击率", "value": "24%"}
    assert disk["sub_stats"] == [{"name": "暴击伤害", "value": "9.6%"}]


def test_iter_grid_scan_targets_accounts_for_bottom_row_auto_scroll():
    targets = iter_grid_scan_targets(
        rows=4,
        columns=3,
        scan_rows=5,
        first=[100, 200],
        gap=[10, 20],
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )

    assert [(item["row"], item["column"], item["visual_row"], item["x"], item["y"]) for item in targets] == [
        (1, 1, 1, 100, 200),
        (1, 2, 1, 110, 200),
        (1, 3, 1, 120, 200),
        (2, 1, 2, 100, 220),
        (2, 2, 2, 110, 220),
        (2, 3, 2, 120, 220),
        (3, 1, 3, 100, 240),
        (3, 2, 3, 110, 240),
        (3, 3, 3, 120, 240),
        (4, 1, 4, 100, 260),
        (4, 2, 3, 110, 240),
        (4, 3, 3, 120, 240),
        (5, 1, 4, 100, 260),
        (5, 2, 3, 110, 240),
        (5, 3, 3, 120, 240),
    ]
    assert targets[9]["causes_auto_scroll"] is True
    assert targets[10]["causes_auto_scroll"] is False


def test_grid_cells_from_template_matches_sorts_rows_columns_and_dedupes():
    matches = [
        {"box": [300, 200, 95, 21], "score": 0.91},
        {"box": [100, 200, 95, 21], "score": 0.92},
        {"box": [302, 202, 103, 32], "score": 0.88},
        {"box": [100, 370, 95, 21], "score": 0.9},
        {"box": [300, 370, 95, 21], "score": 0.89},
    ]

    cells = grid_cells_from_template_matches(
        matches,
        rows=2,
        columns=2,
        click_offset=[18, 70],
        dedupe_tolerance=[55, 55],
        row_tolerance=70,
        first=[118, 270],
        gap=[200, 170],
    )

    assert [(cell["row"], cell["column"], cell["x"], cell["y"]) for cell in cells] == [
        (1, 1, 118, 270),
        (1, 2, 318, 270),
        (2, 1, 118, 440),
        (2, 2, 318, 440),
    ]


def test_grid_cells_from_template_matches_does_not_compress_missing_columns():
    matches = [
        {"box": [100, 200, 95, 21], "score": 0.92},
        {"box": [500, 200, 95, 21], "score": 0.91},
    ]

    cells = grid_cells_from_template_matches(
        matches,
        rows=1,
        columns=3,
        click_offset=[18, 70],
        dedupe_tolerance=[55, 55],
        row_tolerance=70,
        first=[118, 270],
        gap=[200, 170],
    )

    assert [(cell["row"], cell["column"], cell["x"], cell["y"], cell["source"]) for cell in cells] == [
        (1, 1, 118, 270, "template-grid"),
        (1, 2, 318, 270, "template-inferred"),
        (1, 3, 518, 270, "template-grid"),
    ]


def test_grid_cells_from_template_matches_uses_roi_local_coordinates():
    cells = grid_cells_from_template_matches(
        [{"box": [170, 200, 95, 21], "score": 0.92}],
        rows=1,
        columns=2,
        click_offset=[18, 70],
        dedupe_tolerance=[55, 55],
        row_tolerance=70,
        first=[118, 110],
        gap=[200, 170],
        roi=[70, 160, 1280, 790],
    )

    assert cells[0]["local_x"] == 118
    assert cells[0]["local_y"] == 110
    assert cells[0]["x"] == 188
    assert cells[0]["y"] == 270
    assert cells[1]["local_x"] == 318
    assert cells[1]["x"] == 388


def test_grid_cells_from_template_matches_accepts_roi_local_match_boxes():
    cells = grid_cells_from_template_matches(
        [{"box": [48, 40, 95, 21], "score": 0.92}],
        rows=1,
        columns=1,
        click_offset=[18, 26],
        dedupe_tolerance=[55, 55],
        row_tolerance=70,
        first=[66, 66],
        gap=[136, 175],
        roi=[100, 210, 1220, 680],
        box_coordinate_space="auto",
    )

    assert cells[0]["local_x"] == 66
    assert cells[0]["local_y"] == 66
    assert cells[0]["x"] == 166
    assert cells[0]["y"] == 276


def test_empty_detection_should_use_only_direct_template_hits():
    cells = grid_cells_from_template_matches(
        [{"box": [500, 200, 95, 21], "score": 0.91}],
        rows=1,
        columns=3,
        click_offset=[18, 70],
        dedupe_tolerance=[55, 55],
        row_tolerance=70,
        first=[118, 270],
        gap=[200, 170],
    )

    direct_empty_cells = [cell for cell in cells if cell.get("source") == "template-grid"]

    assert [(cell["row"], cell["column"]) for cell in direct_empty_cells] == [(1, 3)]


def test_empty_cell_loses_when_disk_template_matches_same_position():
    empty_cells = [{"row": 1, "column": 3, "source": "template-grid"}]
    disk_cells = [{"row": 1, "column": 3, "source": "template-grid"}]

    assert not _is_confirmed_empty_cell(empty_cells, disk_cells, 1, 3)
    assert _is_confirmed_empty_cell(empty_cells, [], 1, 3)


def test_empty_cell_wins_over_inferred_disk_cell():
    empty_cells = [{"row": 1, "column": 3, "source": "template-grid"}]
    disk_cells = [{"row": 1, "column": 3, "source": "template-inferred"}]

    assert _is_confirmed_empty_cell(empty_cells, disk_cells, 1, 3)


def test_scan_does_not_stop_on_inferred_zero_score_cell_without_empty_template():
    disk_cells = [{"row": 1, "column": 3, "source": "template-inferred", "score": 0.0}]

    assert not _should_stop_at_empty_or_unmatched_cell([], disk_cells, 1, 3)


def test_scan_does_not_stop_on_any_non_grid_zero_score_cell_without_empty_template():
    disk_cells = [{"row": 1, "column": 3, "source": "template", "score": 0.0}]

    assert not _should_stop_at_empty_or_unmatched_cell([], disk_cells, 1, 3)


def test_scan_continues_on_real_template_grid_cell_without_empty_template():
    disk_cells = [{"row": 1, "column": 3, "source": "template-grid", "score": 0.8}]

    assert not _should_stop_at_empty_or_unmatched_cell([], disk_cells, 1, 3)


def test_bottom_click_reaches_end_when_screen_does_not_scroll():
    assert _reached_bottom_after_bottom_click(
        scroll_delta=2.0,
        scroll_change_threshold=2.3,
        selected_row=0,
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )


def test_bottom_click_reaches_end_when_selected_stays_on_bottom_row():
    assert _reached_bottom_after_bottom_click(
        scroll_delta=20.0,
        scroll_change_threshold=2.3,
        selected_row=4,
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )


def test_bottom_click_continues_when_screen_scrolls_and_selection_moves_up():
    assert not _reached_bottom_after_bottom_click(
        scroll_delta=20.0,
        scroll_change_threshold=2.3,
        selected_row=3,
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )


def test_bottom_click_continues_when_stable_selection_moves_up_even_if_delta_is_small():
    assert not _reached_bottom_after_bottom_click(
        scroll_delta=2.0,
        scroll_change_threshold=2.3,
        selected_row=3,
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )


def test_bottom_click_reaches_end_when_abnormal_selection_and_delta_is_small():
    assert _reached_bottom_after_bottom_click(
        scroll_delta=2.0,
        scroll_change_threshold=2.3,
        selected_row=2,
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )


def test_bottom_click_continues_when_abnormal_selection_but_delta_is_above_threshold():
    assert not _reached_bottom_after_bottom_click(
        scroll_delta=2.617,
        scroll_change_threshold=2.3,
        selected_row=2,
        auto_scroll_trigger_row=4,
        stable_selected_row=3,
    )


def test_accepts_unchanged_detail_when_disk_template_matches():
    assert _should_accept_detail_after_click(
        detail_delta=0.2,
        detail_change_threshold=3.0,
        matched_cell={"source": "template-grid"},
    )


def test_rejects_unchanged_detail_without_direct_disk_template():
    assert not _should_accept_detail_after_click(
        detail_delta=0.2,
        detail_change_threshold=3.0,
        matched_cell={"source": "template-inferred"},
    )
    assert not _should_accept_detail_after_click(
        detail_delta=0.2,
        detail_change_threshold=3.0,
        matched_cell=None,
    )


def test_accepts_changed_detail_without_direct_disk_template():
    assert _should_accept_detail_after_click(
        detail_delta=8.0,
        detail_change_threshold=3.0,
        matched_cell={"source": "template-inferred"},
    )


class FakeMaaRuntime:
    def __init__(self):
        self.calls = []

    def connect(self, profile):
        self.calls.append(("connect", profile))
        return {"connected": True, "mode": "maa", "message": "connected"}

    def run_task(self, entry, profile):
        self.calls.append(("run_task", entry, profile))
        return {"completed": True}


class FailingConnectRuntime:
    def __init__(self):
        self.calls = []

    def connect(self, profile):
        self.calls.append(("connect", profile))
        raise RuntimeError("未找到匹配的绝区零窗口；请先启动游戏，或在 scan_profile.json 的 maa.hwnd 中填写窗口句柄")

    def run_task(self, entry, profile):
        self.calls.append(("run_task", entry, profile))
        return {"completed": True}
