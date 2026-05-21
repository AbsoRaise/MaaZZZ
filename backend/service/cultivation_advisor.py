from __future__ import annotations

from typing import Any

from backend.service.optimizer import DiskOptimizer


class CultivationAdvisor:
    def __init__(self, character_builds: dict[str, Any]) -> None:
        self.character_builds = character_builds
        self.optimizer = DiskOptimizer(character_builds)

    def find_promising_disks(
        self,
        character_name: str,
        options: dict[str, Any] | None,
        all_disks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if character_name not in self.character_builds:
            raise KeyError(character_name)

        build = self.character_builds[character_name]
        weights = self.optimizer._normalize_weights(build.get("weights"))
        preferred_main_stats = self.optimizer._preferred_main_stats(
            build.get("preferred_main_stats")
        )
        recommended_sets = self._recommended_sets(build, options)
        min_effective_sub_stats = self._option(options, "min_effective_sub_stats", 1)
        high_weight_threshold = self._option(options, "high_weight_threshold", 0.8)

        recommendations: list[dict[str, Any]] = []
        for disk in all_disks:
            if not isinstance(disk, dict):
                continue
            if recommended_sets and self._set_name(disk) not in recommended_sets:
                continue

            sub_stats = self.optimizer._sub_stats(disk)
            sub_weights = [
                self.optimizer._weight_for_stat(stat, weights) for stat in sub_stats
            ]
            effective_count = sum(1 for weight in sub_weights if weight > 0)
            if effective_count < min_effective_sub_stats:
                continue

            high_value_count = sum(
                1 for weight in sub_weights if weight >= high_weight_threshold
            )
            effective_roll_count = sum(
                self.optimizer._sub_stat_count(stat)
                for stat, weight in zip(sub_stats, sub_weights)
                if weight > 0
            )
            high_value_roll_count = sum(
                self.optimizer._sub_stat_count(stat)
                for stat, weight in zip(sub_stats, sub_weights)
                if weight >= high_weight_threshold
            )
            weighted_roll_score = sum(
                self.optimizer._sub_stat_count(stat) * weight
                for stat, weight in zip(sub_stats, sub_weights)
                if weight > 0
            )
            max_stat_weight = self._max_stat_weight(weights)
            current_score = self.optimizer.score_disk(disk, weights, preferred_main_stats)
            main_stat_matched, main_stat_factor, main_stat_bonus, main_reason = (
                self._main_stat_adjustment(disk, preferred_main_stats)
            )
            remaining_upgrade_count = self._remaining_upgrade_count(disk)
            max_visible_roll_count = self._max_visible_sub_stat_roll_count(disk)
            potential_score = self._potential_score(
                weighted_roll_score,
                max_stat_weight,
                main_stat_factor,
                remaining_upgrade_count,
                max_visible_roll_count,
            )
            reasons = self._reasons(
                disk,
                effective_count,
                high_value_count,
                main_reason,
                main_stat_bonus,
                remaining_upgrade_count,
                max_visible_roll_count,
            )
            recommendations.append(
                {
                    "disk": disk,
                    "potential_score": potential_score,
                    "current_score": current_score,
                    "rank": self._rank(potential_score),
                    "effective_sub_stat_count": effective_count,
                    "high_value_sub_stat_count": high_value_count,
                    "effective_sub_stat_roll_count": effective_roll_count,
                    "high_value_sub_stat_roll_count": high_value_roll_count,
                    "weighted_sub_stat_roll_score": round(weighted_roll_score, 4),
                    "max_stat_weight": max_stat_weight,
                    "remaining_upgrade_count": remaining_upgrade_count,
                    "max_visible_sub_stat_roll_count": max_visible_roll_count,
                    "main_stat_matched": main_stat_matched,
                    "reasons": reasons,
                }
            )

        return sorted(
            recommendations,
            key=lambda item: (
                self._slot(item.get("disk")),
                -float(item["potential_score"]),
                -float(item["current_score"]),
            ),
        )

    def _main_stat_adjustment(
        self,
        disk: dict[str, Any],
        preferred_main_stats: dict[int, list[str]],
    ) -> tuple[bool | None, float, float, str | None]:
        slot = disk.get("slot")
        if slot not in {4, 5, 6}:
            return None, 1.0, 0.0, None

        stat_name = self.optimizer._stat_name(disk.get("main_stat"))
        wanted = preferred_main_stats.get(slot, [])
        if wanted and stat_name in wanted:
            return True, 1.0, 0.0, f"{slot} 号位主属性匹配：{stat_name}"
        if wanted:
            return False, 0.5, 0.0, f"{slot} 号位主属性未命中推荐：{stat_name}"
        return None, 1.0, 0.0, None

    def _reasons(
        self,
        disk: dict[str, Any],
        effective_count: int,
        high_value_count: int,
        main_reason: str | None,
        main_stat_bonus: float,
        remaining_upgrade_count: int,
        max_visible_roll_count: int,
    ) -> list[str]:
        reasons = [
            "未满级驱动盘" if remaining_upgrade_count > 0 else "已满级驱动盘",
            f"包含 {effective_count:g} 条角色有效副词条",
            f"包含 {high_value_count:g} 条高价值副词条",
            f"剩余 {remaining_upgrade_count:g} 次副词条升级机会",
            f"当前等级最多已出现 {max_visible_roll_count:g} 次副词条",
        ]
        if main_reason:
            reasons.append(main_reason)
        if main_stat_bonus:
            reasons.append(f"主属性匹配加分：+{main_stat_bonus:g}")

        location = self._warehouse_location(disk)
        if location:
            reasons.append(f"仓库位置：{location}")
        return reasons

    def _warehouse_location(self, disk: dict[str, Any]) -> str:
        for key in ("warehouse_location", "location", "position", "source"):
            value = disk.get(key)
            if isinstance(value, str) and value[:1] in {"P", "R", "C"}:
                return value
        return ""

    def _recommended_sets(
        self,
        build: dict[str, Any],
        options: dict[str, Any] | None,
    ) -> set[str]:
        config_sets = None
        if isinstance(options, dict):
            config = options.get("config")
            if isinstance(config, dict) and isinstance(config.get("preferred_sets"), dict):
                config_sets = config.get("preferred_sets")
        preferred_sets = config_sets if isinstance(config_sets, dict) else build.get("preferred_sets")
        if not isinstance(preferred_sets, dict):
            return set()

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
        return target_sets

    def _set_name(self, disk: dict[str, Any]) -> str:
        value = disk.get("set_name") or disk.get("set")
        return value if isinstance(value, str) else ""

    def _level(self, disk: dict[str, Any]) -> int:
        try:
            return int(disk.get("level", 0))
        except (TypeError, ValueError):
            return 0

    def _slot(self, disk: Any) -> int:
        if not isinstance(disk, dict):
            return 99
        try:
            slot = int(disk.get("slot", 99))
        except (TypeError, ValueError):
            return 99
        return slot if 1 <= slot <= 6 else 99

    def _remaining_upgrade_count(self, disk: dict[str, Any]) -> int:
        level = self._level(disk)
        if level >= 15:
            return 0
        if level >= 12:
            return 1
        if level >= 9:
            return 2
        if level >= 6:
            return 3
        if level >= 3:
            return 4
        return 5

    def _max_visible_sub_stat_roll_count(self, disk: dict[str, Any]) -> int:
        return 9 - self._remaining_upgrade_count(disk)

    def _potential_score(
        self,
        weighted_roll_score: float,
        max_stat_weight: float,
        main_stat_factor: float,
        remaining_upgrade_count: int,
        max_visible_roll_count: int,
    ) -> float:
        if remaining_upgrade_count <= 0 or max_visible_roll_count <= 0 or max_stat_weight <= 0:
            return 0.0
        visible_quality = weighted_roll_score * 6.0 / max_stat_weight
        quality_per_visible_roll = visible_quality / max_visible_roll_count
        future_value = quality_per_visible_roll * remaining_upgrade_count
        return round(min(55.0, future_value) * main_stat_factor, 4)

    def _max_stat_weight(self, weights: dict[str, float]) -> float:
        return max((weight for weight in weights.values() if weight > 0), default=0.0)

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

    def _rank(self, potential_score: float) -> str:
        if potential_score >= 25:
            return "high"
        if potential_score >= 12:
            return "medium"
        return "low"
