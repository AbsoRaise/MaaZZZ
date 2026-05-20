from backend.service.discard_advisor import DiscardAdvisor


def disk(disk_id, slot, set_name, main_stat_name, sub_stats=None, level=15):
    return {
        "id": disk_id,
        "slot": slot,
        "set_name": set_name,
        "level": level,
        "rarity": "S",
        "main_stat": {"name": main_stat_name, "value": 0},
        "sub_stats": sub_stats or [],
    }


def advisor():
    return DiscardAdvisor(
        {
            "Anby": {
                "weights": {"crit": 1.0, "atk": 0.8},
                "preferred_sets": {"target_set_4": "Thunder", "target_set_2": "Wood"},
                "preferred_main_stats": {"4": ["crit"]},
            },
            "Miyabi": {
                "weights": {"ice": 1.0},
                "preferred_sets": {"target_set_4": "Polar", "target_set_2": "Wood"},
            },
        }
    )


def test_marks_matching_set_disk_discardable_when_not_top_rank_and_low_value():
    disks = [
        disk(f"better-{index}", 1, "Thunder", "hp", [{"name": "crit", "upgrade": 4}])
        for index in range(10)
    ] + [
        disk("trash", 1, "Thunder", "hp", [{"name": "def"}]),
        disk("off-set", 1, "Inferno", "hp", [{"name": "def"}]),
    ]

    result = advisor().analyze_disks(
        disks,
        {
            "top_rank_limit": 10,
            "potential_score_threshold": 12,
            "min_effective_sub_stats": 2,
        },
    )
    by_id = {item["disk_id"]: item for item in result["items"]}

    assert by_id["trash"]["discard_candidate"] is True
    assert "Anby" in by_id["trash"]["matching_characters"]
    assert by_id["trash"]["best_rank"] == 11
    assert by_id["off-set"]["discard_candidate"] is False
    assert by_id["off-set"]["matching_characters"] == []


def test_keeps_disk_that_is_top_ten_for_any_matching_character():
    disks = [
        disk("keeper", 1, "Thunder", "hp", [{"name": "crit", "upgrade": 4}]),
        disk("weak", 1, "Thunder", "hp", [{"name": "def"}]),
    ]

    result = advisor().analyze_disks(disks, {"top_rank_limit": 10})
    by_id = {item["disk_id"]: item for item in result["items"]}

    assert by_id["keeper"]["discard_candidate"] is False
    assert by_id["keeper"]["best_rank"] == 1


def test_low_hit_count_can_mark_even_when_potential_threshold_is_not_low():
    disks = [
        disk(f"better-{index}", 1, "Thunder", "hp", [{"name": "crit", "upgrade": 4}])
        for index in range(10)
    ] + [
        disk("one-hit", 1, "Thunder", "hp", [{"name": "crit", "upgrade": 0}]),
    ]

    result = advisor().analyze_disks(
        disks,
        {
            "top_rank_limit": 10,
            "potential_score_threshold": 0,
            "min_effective_sub_stats": 2,
        },
    )
    by_id = {item["disk_id"]: item for item in result["items"]}

    assert by_id["one-hit"]["discard_candidate"] is True
    assert by_id["one-hit"]["best_effective_sub_stat_count"] == 1
