from __future__ import annotations

from typing import Any

from backend.service.cultivation_advisor import CultivationAdvisor
from backend.service.optimizer import DiskOptimizer


class DiscardAdvisor:
    def __init__(self, character_builds: dict[str, Any]) -> None:
        self.character_builds = character_builds
        self.optimizer = DiskOptimizer(character_builds)

    def analyze_disks(
        self,
        disks: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rank_limit = int(self._option(options, "top_rank_limit", 10))
        potential_threshold = self._option(options, "potential_score_threshold", 12.0)
        min_effective_sub_stats = int(self._option(options, "min_effective_sub_stats", 2))
        high_weight_threshold = self._option(options, "high_weight_threshold", 0.8)

        valid_disks = [disk for disk in disks if isinstance(disk, dict)]
        items = [self._empty_item(index, disk) for index, disk in enumerate(valid_disks)]

        for character_name, build in self.character_builds.items():
            if not isinstance(build, dict):
                continue
            matching_indexes = [
                index
                for index, disk in enumerate(valid_disks)
                if self._set_matches_build(disk, build)
            ]
            if not matching_indexes:
                continue

            weights = self.optimizer._normalize_weights(build.get("weights"))
            preferred_main_stats = self.optimizer._preferred_main_stats(
                build.get("preferred_main_stats")
            )
            scored = sorted(
                (
                    (
                        index,
                        self.optimizer.score_disk(
                            valid_disks[index], weights, preferred_main_stats
                        ),
                    )
                    for index in matching_indexes
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            ranks = {index: rank for rank, (index, _score) in enumerate(scored, start=1)}
            scores = dict(scored)

            for index in matching_indexes:
                disk = valid_disks[index]
                score = scores.get(index, 0.0)
                potential = self._potential_for_disk(
                    disk,
                    weights,
                    preferred_main_stats,
                    high_weight_threshold,
                )
                item = items[index]
                rank = ranks[index]
                item["matching_characters"].append(character_name)
                item["character_results"].append(
                    {
                        "character_name": character_name,
                        "score": score,
                        "rank": rank,
                        "potential_score": potential["potential_score"],
                        "effective_sub_stat_count": potential["effective_sub_stat_count"],
                    }
                )
                if item["best_rank"] is None or rank < item["best_rank"]:
                    item["best_rank"] = rank
                    item["best_rank_character"] = character_name
                if potential["potential_score"] > item["best_potential_score"]:
                    item["best_potential_score"] = potential["potential_score"]
                    item["best_potential_character"] = character_name
                if potential["effective_sub_stat_count"] > item["best_effective_sub_stat_count"]:
                    item["best_effective_sub_stat_count"] = potential[
                        "effective_sub_stat_count"
                    ]

        for item in items:
            has_matching_set = bool(item["matching_characters"])
            not_top_rank = item["best_rank"] is None or item["best_rank"] > rank_limit
            low_potential = item["best_potential_score"] < potential_threshold
            too_few_hits = item["best_effective_sub_stat_count"] < min_effective_sub_stats
            item["discard_candidate"] = (
                has_matching_set and not_top_rank and (low_potential or too_few_hits)
            )
            item["reasons"] = self._reasons(
                item,
                rank_limit,
                potential_threshold,
                min_effective_sub_stats,
                low_potential,
                too_few_hits,
            )

        return {
            "items": items,
            "options": {
                "top_rank_limit": rank_limit,
                "potential_score_threshold": potential_threshold,
                "min_effective_sub_stats": min_effective_sub_stats,
                "high_weight_threshold": high_weight_threshold,
            },
        }

    def _empty_item(self, index: int, disk: dict[str, Any]) -> dict[str, Any]:
        return {
            "disk_index": index,
            "disk_id": disk.get("id") or disk.get("disk_id") or "",
            "discard_candidate": False,
            "matching_characters": [],
            "character_results": [],
            "best_rank": None,
            "best_rank_character": "",
            "best_potential_score": 0.0,
            "best_potential_character": "",
            "best_effective_sub_stat_count": 0,
            "reasons": [],
        }

    def _set_matches_build(self, disk: dict[str, Any], build: dict[str, Any]) -> bool:
        set_name = disk.get("set_name") or disk.get("set")
        if not isinstance(set_name, str) or not set_name:
            return False
        preferred_sets = build.get("preferred_sets")
        if not isinstance(preferred_sets, dict):
            return False
        target_sets = {
            value
            for value in (
                preferred_sets.get("target_set_4"),
                preferred_sets.get("target_set_2"),
            )
            if isinstance(value, str) and value
        }
        alternatives = preferred_sets.get("alternatives")
        if isinstance(alternatives, list):
            for value in alternatives:
                if isinstance(value, str) and value:
                    target_sets.add(value)
                elif isinstance(value, dict):
                    for key in ("target_set_4", "target_set_2", "set_name", "set"):
                        alt_set = value.get(key)
                        if isinstance(alt_set, str) and alt_set:
                            target_sets.add(alt_set)
        return set_name in target_sets

    def _potential_for_disk(
        self,
        disk: dict[str, Any],
        weights: dict[str, float],
        preferred_main_stats: dict[int, list[str]],
        high_weight_threshold: float,
    ) -> dict[str, Any]:
        sub_weights = [
            self.optimizer._weight_for_stat(stat, weights)
            for stat in self.optimizer._sub_stats(disk)
        ]
        effective_count = sum(1 for weight in sub_weights if weight > 0)
        high_value_count = sum(1 for weight in sub_weights if weight >= high_weight_threshold)
        current_score = self.optimizer.score_disk(disk, weights, preferred_main_stats)
        _matched, main_factor, _bonus, _reason = CultivationAdvisor(
            self.character_builds
        )._main_stat_adjustment(disk, preferred_main_stats)
        potential_score = round(
            min(55.0, current_score + effective_count * 2.0 + high_value_count * 4.0)
            * main_factor,
            4,
        )
        return {
            "potential_score": potential_score,
            "effective_sub_stat_count": effective_count,
            "high_value_sub_stat_count": high_value_count,
        }

    def _reasons(
        self,
        item: dict[str, Any],
        rank_limit: int,
        potential_threshold: float,
        min_effective_sub_stats: int,
        low_potential: bool,
        too_few_hits: bool,
    ) -> list[str]:
        if not item["matching_characters"]:
            return ["未命中任何角色的目标套装，暂不按可弃置规则判断。"]
        reasons = [
            f"命中套装角色：{'、'.join(item['matching_characters'])}",
            f"最佳排名：第 {item['best_rank']} 名（阈值：前 {rank_limit}）",
            f"最高培养价值：{item['best_potential_score']}",
            f"最多有效副词条：{item['best_effective_sub_stat_count']}",
        ]
        if low_potential:
            reasons.append(f"培养价值低于阈值 {potential_threshold:g}")
        if too_few_hits:
            reasons.append(f"有效副词条少于 {min_effective_sub_stats} 条")
        if item["discard_candidate"]:
            reasons.append("满足可弃置条件。")
        return reasons

    def _option(
        self,
        options: dict[str, Any] | None,
        key: str,
        default: float,
    ) -> float:
        if not isinstance(options, dict):
            return default
        try:
            return float(options.get(key, default))
        except (TypeError, ValueError):
            return default
