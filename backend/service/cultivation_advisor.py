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
        min_effective_sub_stats = self._option(options, "min_effective_sub_stats", 1)
        high_weight_threshold = self._option(options, "high_weight_threshold", 0.8)

        recommendations: list[dict[str, Any]] = []
        for disk in all_disks:
            if not isinstance(disk, dict) or self._level(disk) >= 15:
                continue

            sub_weights = [
                self.optimizer._weight_for_stat(stat, weights)
                for stat in self.optimizer._sub_stats(disk)
            ]
            effective_count = sum(1 for weight in sub_weights if weight > 0)
            if effective_count < min_effective_sub_stats:
                continue

            high_value_count = sum(
                1 for weight in sub_weights if weight >= high_weight_threshold
            )
            current_score = self.optimizer.score_disk(disk, weights, preferred_main_stats)
            main_stat_matched, main_stat_factor, main_stat_bonus, main_reason = (
                self._main_stat_adjustment(disk, preferred_main_stats)
            )
            potential_score = round(
                min(55.0, current_score + effective_count * 2.0 + high_value_count * 4.0)
                * main_stat_factor,
                4,
            )
            reasons = self._reasons(
                disk,
                effective_count,
                high_value_count,
                main_reason,
                main_stat_bonus,
            )
            recommendations.append(
                {
                    "disk": disk,
                    "potential_score": potential_score,
                    "current_score": current_score,
                    "rank": self._rank(potential_score),
                    "effective_sub_stat_count": effective_count,
                    "high_value_sub_stat_count": high_value_count,
                    "main_stat_matched": main_stat_matched,
                    "reasons": reasons,
                }
            )

        return sorted(
            recommendations,
            key=lambda item: (item["potential_score"], item["current_score"]),
            reverse=True,
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
    ) -> list[str]:
        reasons = [
            "未满级驱动盘",
            f"包含 {effective_count:g} 条角色有效副词条",
            f"包含 {high_value_count:g} 条高价值副词条",
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

    def _level(self, disk: dict[str, Any]) -> int:
        try:
            return int(disk.get("level", 0))
        except (TypeError, ValueError):
            return 0

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
