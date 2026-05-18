import pytest

from backend.service.optimizer import DiskOptimizer


def disk(disk_id, slot, set_name, main_stat_name, main_value, sub_stats=None):
    return {
        "id": disk_id,
        "slot": slot,
        "set_name": set_name,
        "main_stat": {"name": main_stat_name, "value": main_value},
        "sub_stats": sub_stats or [],
    }


def optimizer(build=None):
    builds = {
        "Anby": build
        or {
            "weights": {"atk": 1.0, "crit": 2.0, "hp": 0.1},
            "preferred_sets": {"target_set_4": "Thunder", "target_set_2": "Wood"},
            "preferred_main_stats": {"4": ["crit"], "5": ["atk"], "6": ["atk"]},
        }
    }
    return DiskOptimizer(builds)


def base_disks():
    return [
        disk("t1", 1, "Thunder", "hp", 1, [{"name": "atk", "value": 1}]),
        disk("t2", 2, "Thunder", "hp", 1),
        disk("t3", 3, "Thunder", "hp", 1),
        disk("t4", 4, "Thunder", "crit", 2),
        disk("w5", 5, "Wood", "atk", 3),
        disk("w6", 6, "Wood", "atk", 4),
        disk("free5", 5, "Inferno", "atk", 20),
        disk("free6", 6, "Inferno", "atk", 20),
    ]


def test_exact_target_four_plus_two_returns_exact_not_fallback():
    result = optimizer().find_best_combination(
        "Anby",
        {"target_set_4": "Thunder", "target_set_2": "Wood"},
        base_disks(),
    )

    assert result["character_name"] == "Anby"
    assert result["match_type"] == "exact_4_2"
    assert result["is_fallback"] is False
    assert result["set_counts"] == {"Thunder": 4, "Wood": 2}
    assert [item["disk"]["id"] for item in result["score_breakdown"]] == [
        item["id"] for item in result["combo"]
    ]


def test_missing_target_sets_falls_back_with_warning():
    result = optimizer().find_best_combination(
        "Anby",
        {"target_set_4": "Missing", "target_set_2": "Also Missing"},
        base_disks(),
    )

    assert result["is_fallback"] is True
    assert result["match_type"] in {
        "target_4_any_2",
        "any_4_2",
        "two_two_two",
        "best_score_only",
    }
    assert result["warnings"]


def test_main_stat_filter_falls_back_per_slot_when_no_matching_main_stat():
    result = optimizer().find_best_combination(
        "Anby",
        {
            "target_set_4": "Thunder",
            "target_set_2": "Wood",
            "preferred_main_stats": {"4": "crit", "5": "missing-main", "6": "atk"},
        },
        base_disks(),
    )

    by_slot = {item["slot"]: item for item in result["combo"]}
    assert by_slot[4]["main_stat"]["name"] == "crit"
    assert by_slot[5]["main_stat"]["name"] == "atk"
    assert any("slot 5" in warning for warning in result["warnings"])


def test_empty_slot_candidates_raise_value_error():
    disks = [item for item in base_disks() if item["slot"] != 3]

    with pytest.raises(ValueError, match="slot 3"):
        optimizer().find_best_combination("Anby", {}, disks)


def test_default_config_uses_character_preferred_sets_and_main_stats():
    result = optimizer().find_best_combination("Anby", {}, base_disks())

    assert result["match_type"] == "exact_4_2"
    assert result["set_counts"] == {"Thunder": 4, "Wood": 2}
    assert next(item for item in result["combo"] if item["slot"] == 4)["main_stat"]["name"] == "crit"


def test_score_disk_weights_main_stat_double_and_adds_sub_stats():
    score = optimizer().score_disk(
        disk(
            "score-me",
            4,
            "Thunder",
            "crit",
            3,
            [{"name": "atk", "value": 5}, {"name": "hp", "value": 10}],
        ),
        {"crit": 2.0, "atk": 1.5, "hp": 0.25},
    )

    assert score == 22.0


def test_match_type_priority_beats_higher_score_best_score_only():
    disks = base_disks() + [
        disk("high1", 1, "Inferno", "atk", 100),
        disk("high2", 2, "Inferno", "atk", 100),
        disk("high3", 3, "Inferno", "atk", 100),
        disk("high4", 4, "Inferno", "crit", 100),
    ]

    result = optimizer().find_best_combination(
        "Anby",
        {"target_set_4": "Thunder", "target_set_2": "Wood"},
        disks,
    )

    assert result["match_type"] == "exact_4_2"
    assert result["set_counts"] == {"Thunder": 4, "Wood": 2}
    assert sum(1 for item in result["combo"] if item["set_name"] == "Inferno") == 0
