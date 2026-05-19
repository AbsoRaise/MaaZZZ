import pytest

from backend.service.cultivation_advisor import CultivationAdvisor
from backend.service.optimizer import DiskOptimizer


def disk(
    disk_id,
    slot,
    main_stat_name,
    main_value,
    sub_stats=None,
    level=0,
    location="P",
):
    return {
        "id": disk_id,
        "slot": slot,
        "set_name": "Thunder",
        "level": level,
        "warehouse_location": location,
        "main_stat": {"name": main_stat_name, "value": main_value},
        "sub_stats": sub_stats or [],
    }


def advisor():
    return CultivationAdvisor(
        {
            "Anby": {
                "weights": {"atk": 1.0, "crit": 2.0, "pen": 0.7, "hp": 0.0},
                "preferred_main_stats": {
                    "4": ["crit"],
                    "5": ["atk"],
                    "6": ["atk"],
                },
            }
        }
    )


def ids(results):
    return [result["disk"]["id"] for result in results]


def test_recommends_underleveled_disks_that_reach_effective_sub_stat_threshold():
    results = advisor().find_promising_disks(
        "Anby",
        {"min_effective_sub_stats": 2},
        [
            disk(
                "promising",
                4,
                "crit",
                2,
                [{"name": "atk", "value": 3}, {"name": "crit", "value": 1}],
                level=14,
            ),
            disk(
                "too-few",
                4,
                "crit",
                2,
                [{"name": "atk", "value": 3}, {"name": "hp", "value": 10}],
                level=14,
            ),
        ],
    )

    assert ids(results) == ["promising"]
    assert results[0]["effective_sub_stat_count"] == 2
    assert "未满级驱动盘" in results[0]["reasons"]
    assert "包含 2 条角色有效副词条" in results[0]["reasons"]
    assert results[0]["rank"] in {"high", "medium", "low"}


def test_ignores_disks_at_max_cultivation_level():
    results = advisor().find_promising_disks(
        "Anby",
        {},
        [
            disk("under", 4, "crit", 1, [{"name": "atk", "value": 1}], level=14),
            disk("maxed", 4, "crit", 99, [{"name": "atk", "value": 99}], level=15),
        ],
    )

    assert ids(results) == ["under"]


def test_slots_four_five_six_mark_main_stat_matches_and_explain_bonus():
    results = advisor().find_promising_disks(
        "Anby",
        {},
        [
            disk("slot4", 4, "crit", 1, [{"name": "atk", "value": 1}]),
            disk("slot5", 5, "atk", 1, [{"name": "crit", "value": 1}]),
            disk("slot6", 6, "atk", 1, [{"name": "pen", "value": 1}]),
        ],
    )

    assert set(ids(results)) == {"slot4", "slot5", "slot6"}
    for result in results:
        assert result["main_stat_matched"] is True
        slot = result["disk"]["slot"]
        main_stat_name = result["disk"]["main_stat"]["name"]
        assert f"{slot} 号位主属性匹配：{main_stat_name}" in result["reasons"]
        assert not any("主属性匹配加分" in reason for reason in result["reasons"])


def test_good_sub_stats_with_unmatched_main_stat_are_kept_at_lower_priority_with_reason():
    results = advisor().find_promising_disks(
        "Anby",
        {},
        [
            disk(
                "matched",
                4,
                "crit",
                1,
                [{"name": "atk", "value": 1}, {"name": "crit", "value": 1}],
            ),
            disk(
                "unmatched",
                4,
                "def",
                1,
                [{"name": "atk", "value": 10}, {"name": "crit", "value": 4}],
            ),
        ],
    )

    assert ids(results) == ["matched", "unmatched"]
    unmatched = results[1]
    assert unmatched["main_stat_matched"] is False
    assert unmatched["effective_sub_stat_count"] == 2
    assert "4 号位主属性未命中推荐：def" in unmatched["reasons"]


def test_slots_one_two_three_are_not_penalized_for_main_stats_outside_preferences():
    results = advisor().find_promising_disks(
        "Anby",
        {},
        [
            disk("slot1", 1, "hp", 0, [{"name": "atk", "value": 1}], location="R"),
            disk("slot2", 2, "def", 0, [{"name": "crit", "value": 1}], location="C"),
            disk("slot3", 3, "atk", 0, [{"name": "pen", "value": 1}], location="P"),
        ],
    )

    assert set(ids(results)) == {"slot1", "slot2", "slot3"}
    assert all(result["main_stat_matched"] is None for result in results)
    assert not any(
        "主属性未命中推荐" in reason
        for result in results
        for reason in result["reasons"]
    )


def test_options_for_effective_sub_stats_and_high_weight_threshold_take_effect():
    results = advisor().find_promising_disks(
        "Anby",
        {"min_effective_sub_stats": 2, "high_weight_threshold": 1.5},
        [
            disk(
                "two-effective-one-high",
                4,
                "crit",
                1,
                [{"name": "atk", "value": 1}, {"name": "crit", "value": 1}],
            ),
            disk(
                "one-effective",
                4,
                "crit",
                1,
                [{"name": "crit", "value": 1}, {"name": "hp", "value": 1}],
            ),
        ],
    )

    assert ids(results) == ["two-effective-one-high"]
    assert results[0]["effective_sub_stat_count"] == 2
    assert results[0]["high_value_sub_stat_count"] == 1
    assert "包含 1 条高价值副词条" in results[0]["reasons"]


def test_results_are_sorted_by_potential_score_descending():
    results = advisor().find_promising_disks(
        "Anby",
        {},
        [
            disk("low", 4, "crit", 1, [{"name": "atk", "value": 1}]),
            disk("high", 5, "atk", 1, [{"name": "crit", "value": 5}]),
            disk("mid", 6, "atk", 1, [{"name": "crit", "value": 2}]),
        ],
    )

    scores = [result["potential_score"] for result in results]
    assert scores == sorted(scores, reverse=True)
    assert ids(results) == ["high", "mid", "low"]


def test_results_include_warehouse_location_reasons_for_p_r_c():
    results = advisor().find_promising_disks(
        "Anby",
        {},
        [
            disk("p", 4, "crit", 1, [{"name": "atk", "value": 1}], location="P2"),
            disk("r", 4, "crit", 1, [{"name": "atk", "value": 1}], location="R3"),
            disk("c", 4, "crit", 1, [{"name": "atk", "value": 1}], location="C5"),
        ],
    )

    reasons_by_id = {result["disk"]["id"]: result["reasons"] for result in results}
    assert "仓库位置：P2" in reasons_by_id["p"]
    assert "仓库位置：R3" in reasons_by_id["r"]
    assert "仓库位置：C5" in reasons_by_id["c"]


def test_reasons_use_clear_chinese_phrases_not_english_regressions():
    custom_advisor = CultivationAdvisor(
        {
            "Miyabi": {
                "weights": {"暴击率": 1.0, "攻击力": 0.9},
                "preferred_main_stats": {"5": ["冰属性伤害"]},
            }
        }
    )

    results = custom_advisor.find_promising_disks(
        "Miyabi",
        {"min_effective_sub_stats": 2, "high_weight_threshold": 0.8},
        [
            disk(
                "cn",
                5,
                "冰属性伤害",
                1,
                [{"name": "暴击率", "value": 1}, {"name": "攻击力", "value": 1}],
                level=12,
                location="P2",
            )
        ],
    )

    reasons = results[0]["reasons"]
    assert "未满级驱动盘" in reasons
    assert "包含 2 条角色有效副词条" in reasons
    assert "包含 2 条高价值副词条" in reasons
    assert "5 号位主属性匹配：冰属性伤害" in reasons
    assert "仓库位置：P2" in reasons
    assert not any(
        english in reason
        for reason in reasons
        for english in ("main stat", "effective sub stats", "warehouse location")
    )


def test_current_score_uses_disk_optimizer_score_disk_formula():
    candidate = disk(
        "score",
        4,
        "crit",
        3,
        [{"name": "atk", "value": 5}, {"name": "pen", "value": 10}],
    )

    result = advisor().find_promising_disks("Anby", {}, [candidate])[0]
    expected = DiskOptimizer(advisor().character_builds).score_disk(
        candidate,
        advisor().character_builds["Anby"]["weights"],
        {4: ["crit"], 5: ["atk"], 6: ["atk"]},
    )

    assert result["current_score"] == expected


def test_missing_character_raises_key_error():
    with pytest.raises(KeyError):
        advisor().find_promising_disks("Missing", {}, [])
