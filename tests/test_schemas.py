from backend.model.schemas import (
    CURRENT_DISKS_PATH,
    DEFAULT_CHARACTER_BUILDS,
    build_scan_id,
    normalize_preferred_main_stats,
    normalize_slot_main_stats,
    safe_scan_id,
    summarize_disks,
)


def test_default_character_build_contains_sets_and_main_stats():
    ellen = DEFAULT_CHARACTER_BUILDS["艾莲·乔"]
    assert "weights" in ellen
    assert ellen["preferred_sets"]["target_set_4"] == "极地重金属"
    assert "5" in ellen["preferred_main_stats"]


def test_current_disks_path_uses_disks_filename():
    assert CURRENT_DISKS_PATH.name == "disks.json"


def test_normalize_slot_main_stats_turns_keys_into_ints():
    assert normalize_slot_main_stats({"4": "暴击率", 5: "冰属性伤害"}) == {
        4: "暴击率",
        5: "冰属性伤害",
    }


def test_normalize_slot_main_stats_skips_invalid_entries():
    assert normalize_slot_main_stats(
        {None: "x", "bad": "y", "7": "z", "4": "暴击率", "5": ""}
    ) == {4: "暴击率"}


def test_normalize_preferred_main_stats_returns_json_friendly_lists():
    assert normalize_preferred_main_stats(
        {"4": "暴击率", 5: ["冰属性伤害", "", 123], "2": ["攻击力"]}
    ) == {"4": ["暴击率"], "5": ["冰属性伤害"]}


def test_safe_scan_id_rejects_path_traversal():
    assert safe_scan_id("20260518-143012-a8f3")
    assert not safe_scan_id("../bad")
    assert not safe_scan_id("bad/path")


def test_safe_scan_id_rejects_reserved_or_non_shape_values():
    assert not safe_scan_id("CON")
    assert not safe_scan_id("20260518-143012-a8f3.")
    assert not safe_scan_id("20260518-143012-a8f3a8f3a8f3a")
    assert not safe_scan_id("not-a-scan-id")


def test_summarize_disks_counts_slots_and_sets():
    disks = [
        {"slot": 1, "set_name": "极地重金属"},
        {"slot": 1, "set_name": "极地重金属"},
        {"slot": 5, "set_name": "啄木鸟电音"},
    ]
    summary = summarize_disks(disks)
    assert summary["slot_counts"]["1"] == 2
    assert summary["set_counts"]["极地重金属"] == 2


def test_build_scan_id_has_timestamp_shape():
    scan_id = build_scan_id()
    assert len(scan_id) >= 20
    assert safe_scan_id(scan_id)
