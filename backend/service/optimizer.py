from __future__ import annotations

from collections import Counter
from time import perf_counter
from typing import Any

from backend.model.schemas import normalize_slot_main_stats


MATCH_TYPE_PRIORITY = {
    "exact_4_2": 0,
    "target_4_any_2": 1,
    "any_4_2": 2,
    "two_two_two": 3,
    "best_score_only": 4,
}

SLOT_FULL_SCORE = 55.0
MAIN_STAT_EQUIVALENT_SUB_STATS = 3.0
MAX_SUB_STAT_UPGRADES = 5
RARITY_SCORE_MULTIPLIER = {
    "S": 1.0,
    "A": 0.67,
    "B": 0.33,
}


class DiskOptimizer:
    def __init__(self, character_builds: dict[str, Any]) -> None:
        self.character_builds = character_builds

    def score_disk(
        self,
        disk: dict[str, Any],
        weights: dict[str, float],
        preferred_main_stats: dict[int, list[str]] | None = None,
    ) -> float:
        if not isinstance(disk, dict):
            return 0.0
        slot = int(disk.get("slot") or 0)
        main_stats = preferred_main_stats or {}
        max_weight = self._slot_max_weight(slot, weights, main_stats)
        if max_weight <= 0:
            return 0.0

        sub_weight = sum(
            self._sub_stat_count(stat) * self._weight_for_stat(stat, weights)
            for stat in self._sub_stats(disk)
        )
        main_weight = 0.0
        if slot in {4, 5, 6}:
            main_stat_name = self._stat_name(disk.get("main_stat"))
            useful_main_stats = main_stats.get(slot, [])
            main_stat_is_useful = not useful_main_stats or main_stat_name in useful_main_stats
            main_weight = (
                MAIN_STAT_EQUIVALENT_SUB_STATS
                * self._weight_for_stat(disk.get("main_stat"), weights)
                * self._main_stat_level_multiplier(disk)
                if main_stat_is_useful
                else 0.0
            )

        raw_score = (sub_weight + main_weight) * (SLOT_FULL_SCORE / max_weight)
        return round(min(SLOT_FULL_SCORE, raw_score) * self._rarity_multiplier(disk), 4)

    def find_best_combination(
        self,
        character_name: str,
        config: dict[str, Any] | None,
        all_disks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        build = self.character_builds.get(character_name, {})
        merged_config = self._merge_config(build, config or {})
        weights = self._normalize_weights(merged_config.get("weights"))
        preferred_main_stats = self._preferred_main_stats(merged_config.get("preferred_main_stats"))
        target_set_4 = self._string_or_empty(merged_config.get("target_set_4"))
        target_set_2 = self._string_or_empty(merged_config.get("target_set_2"))

        warnings: list[str] = []
        logs: list[str] = []
        started_at = perf_counter()
        candidates_by_slot = self._candidates_by_slot(all_disks, merged_config, warnings)
        candidate_counts = {slot: len(candidates_by_slot.get(slot, [])) for slot in range(1, 7)}
        brute_force_count = self._combination_count(candidates_by_slot)
        logs.append(f"候选数量: {candidate_counts}")
        logs.append(f"原始组合数量估算: {brute_force_count}")
        best = self._best_combo(
            candidates_by_slot,
            weights,
            preferred_main_stats,
            target_set_4,
            target_set_2,
            logs,
        )
        if best is None:
            raise ValueError("no valid disk combination found")

        combo, total_score, set_counts, match_type, score_breakdown = best
        is_fallback = match_type != "exact_4_2"
        if is_fallback:
            warnings.append(
                f"target set combination not found; using fallback match type {match_type}"
            )

        return {
            "character_name": character_name,
            "combo": [dict(disk) if isinstance(disk, dict) else None for disk in combo],
            "total_score": round(total_score, 4),
            "set_counts": dict(set_counts),
            "match_type": match_type,
            "is_fallback": is_fallback,
            "warnings": warnings,
            "score_breakdown": score_breakdown,
            "optimize_logs": logs + [f"总耗时: {perf_counter() - started_at:.3f}s"],
        }

    def _merge_config(self, build: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        preferred_sets = build.get("preferred_sets") if isinstance(build, dict) else {}
        preferred_sets = preferred_sets if isinstance(preferred_sets, dict) else {}
        merged = {
            "weights": build.get("weights", {}) if isinstance(build, dict) else {},
            "target_set_4": self._string_or_empty(preferred_sets.get("target_set_4")),
            "target_set_2": self._string_or_empty(preferred_sets.get("target_set_2")),
            "preferred_main_stats": build.get("preferred_main_stats", {})
            if isinstance(build, dict)
            else {},
        }

        if "weights" in config:
            merged["weights"] = config.get("weights") or {}

        config_sets = config.get("preferred_sets")
        if isinstance(config_sets, dict):
            if "target_set_4" in config_sets:
                merged["target_set_4"] = self._string_or_empty(config_sets.get("target_set_4"))
            if "target_set_2" in config_sets:
                merged["target_set_2"] = self._string_or_empty(config_sets.get("target_set_2"))

        if "target_set_4" in config:
            merged["target_set_4"] = self._string_or_empty(config.get("target_set_4"))
        if "target_set_2" in config:
            merged["target_set_2"] = self._string_or_empty(config.get("target_set_2"))
        if "preferred_main_stats" in config:
            merged["preferred_main_stats"] = config.get("preferred_main_stats") or {}

        return merged

    def _candidates_by_slot(
        self,
        all_disks: list[dict[str, Any]],
        config: dict[str, Any],
        warnings: list[str],
    ) -> dict[int, list[dict[str, Any] | None]]:
        valid_disks = [
            disk
            for disk in all_disks
            if isinstance(disk, dict) and isinstance(disk.get("slot"), int) and 1 <= disk["slot"] <= 6
        ]
        preferred_main_stats = self._preferred_main_stats(config.get("preferred_main_stats"))
        candidates_by_slot: dict[int, list[dict[str, Any] | None]] = {}

        for slot in range(1, 7):
            slot_candidates = [disk for disk in valid_disks if disk.get("slot") == slot]
            if not slot_candidates:
                candidates_by_slot[slot] = [None]
                warnings.append(f"slot {slot} has no candidates; leaving empty")
                continue

            wanted_stats = preferred_main_stats.get(slot, [])
            if wanted_stats:
                filtered = [
                    disk
                    for disk in slot_candidates
                    if self._stat_name(disk.get("main_stat")) in wanted_stats
                ]
                if filtered:
                    slot_candidates = filtered
                else:
                    warnings.append(
                        f"slot {slot} has no candidates for preferred main stats; using all candidates"
                    )
            candidates_by_slot[slot] = slot_candidates

        return candidates_by_slot

    def _best_combo(
        self,
        candidates_by_slot: dict[int, list[dict[str, Any] | None]],
        weights: dict[str, float],
        preferred_main_stats: dict[int, list[str]],
        target_set_4: str,
        target_set_2: str,
        logs: list[str] | None = None,
    ) -> tuple[list[dict[str, Any] | None], float, Counter[str], str, list[dict[str, Any]]] | None:
        best_key: tuple[int, float] | None = None
        best_value = None
        prepared_by_slot = self._best_candidates_by_slot_and_set(candidates_by_slot, weights, preferred_main_stats)
        if logs is not None:
            logs.append(
                "压缩后候选数量: "
                + str({slot: len(prepared_by_slot.get(slot, [])) for slot in range(1, 7)})
            )

        states: dict[tuple[tuple[str, int], ...], tuple[float, list[dict[str, Any] | None], list[float]]] = {
            tuple(): (0.0, [], [])
        }
        state_counts: list[str] = []
        for slot in range(1, 7):
            next_states: dict[tuple[tuple[str, int], ...], tuple[float, list[dict[str, Any] | None], list[float]]] = {}
            for state, (score_sum, combo, scores) in states.items():
                for candidate in prepared_by_slot.get(slot, [self._prepared_empty_candidate()]):
                    next_state = self._advance_set_state(state, candidate["set_name"])
                    next_score = round(score_sum + candidate["score"], 4)
                    previous = next_states.get(next_state)
                    if previous is None or next_score > previous[0]:
                        next_states[next_state] = (
                            next_score,
                            combo + [candidate["disk"]],
                            scores + [candidate["score"]],
                        )
            states = next_states
            state_counts.append(f"{slot}号位后状态数={len(states)}")

        if logs is not None:
            logs.extend(state_counts)
            logs.append(f"动态规划最终状态数: {len(states)}")

        for state, (total_score, combo, scores) in states.items():
            set_counts = Counter(dict(state))
            match_type = self._match_type(set_counts, target_set_4, target_set_2)
            key = (MATCH_TYPE_PRIORITY[match_type], -total_score)
            if best_key is None or key < best_key:
                best_key = key
                score_breakdown = [
                    {"disk": dict(disk) if isinstance(disk, dict) else None, "score": round(score, 4)}
                    for disk, score in zip(combo, scores)
                ]
                best_value = (combo, total_score, set_counts, match_type, score_breakdown)

        return best_value

    def _combination_count(self, candidates_by_slot: dict[int, list[dict[str, Any] | None]]) -> int:
        count = 1
        for slot in range(1, 7):
            count *= max(1, len(candidates_by_slot.get(slot, [])))
        return count

    def _best_candidates_by_slot_and_set(
        self,
        candidates_by_slot: dict[int, list[dict[str, Any] | None]],
        weights: dict[str, float],
        preferred_main_stats: dict[int, list[str]],
    ) -> dict[int, list[dict[str, Any]]]:
        prepared: dict[int, list[dict[str, Any]]] = {}
        for slot in range(1, 7):
            best_by_set: dict[str | None, dict[str, Any]] = {}
            for disk in candidates_by_slot.get(slot, [None]):
                if not isinstance(disk, dict):
                    candidate = self._prepared_empty_candidate()
                else:
                    set_name = disk.get("set_name") if isinstance(disk.get("set_name"), str) else None
                    candidate = {
                        "set_name": set_name,
                        "disk": disk,
                        "score": self.score_disk(disk, weights, preferred_main_stats),
                    }
                key = candidate["set_name"]
                previous = best_by_set.get(key)
                if previous is None or candidate["score"] > previous["score"]:
                    best_by_set[key] = candidate
            prepared[slot] = sorted(best_by_set.values(), key=lambda item: item["score"], reverse=True)
        return prepared

    def _prepared_empty_candidate(self) -> dict[str, Any]:
        return {"set_name": None, "disk": None, "score": 0.0}

    def _advance_set_state(self, state: tuple[tuple[str, int], ...], set_name: str | None) -> tuple[tuple[str, int], ...]:
        if not set_name:
            return state
        counts = dict(state)
        counts[set_name] = min(6, counts.get(set_name, 0) + 1)
        return tuple(sorted(counts.items()))

    def _match_type(self, set_counts: Counter[str], target_set_4: str, target_set_2: str) -> str:
        has_distinct_targets = bool(target_set_4 and target_set_2 and target_set_4 != target_set_2)
        if has_distinct_targets and set_counts[target_set_4] >= 4 and set_counts[target_set_2] >= 2:
            return "exact_4_2"
        if target_set_4 and set_counts[target_set_4] >= 4 and self._has_any_pair_except(set_counts, target_set_4):
            return "target_4_any_2"
        if self._has_four_two(set_counts):
            return "any_4_2"
        if sum(1 for count in set_counts.values() if count >= 2) >= 3:
            return "two_two_two"
        return "best_score_only"

    def _has_four_two(self, set_counts: Counter[str]) -> bool:
        for set_name, count in set_counts.items():
            if count >= 4 and self._has_any_pair_except(set_counts, set_name):
                return True
        return False

    def _has_any_pair_except(self, set_counts: Counter[str], excluded_set: str) -> bool:
        return any(set_name != excluded_set and count >= 2 for set_name, count in set_counts.items())

    def _preferred_main_stats(self, raw: Any) -> dict[int, list[str]]:
        normalized_single = normalize_slot_main_stats(raw if isinstance(raw, dict) else None)
        normalized: dict[int, list[str]] = {
            slot: [value] for slot, value in normalized_single.items()
        }
        if not isinstance(raw, dict):
            return normalized

        for slot, value in raw.items():
            try:
                slot_number = int(slot)
            except (TypeError, ValueError):
                continue
            if slot_number not in range(1, 7) or slot_number in normalized:
                continue
            values = value if isinstance(value, list) else [value]
            stats = [item for item in values if isinstance(item, str) and item]
            if stats:
                normalized[slot_number] = stats
        return normalized

    def _normalize_weights(self, raw: Any) -> dict[str, float]:
        if not isinstance(raw, dict):
            return {}
        weights: dict[str, float] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                continue
            try:
                weights[key] = float(value)
            except (TypeError, ValueError):
                weights[key] = 0.0
        return weights

    def _slot_max_weight(
        self,
        slot: int,
        weights: dict[str, float],
        preferred_main_stats: dict[int, list[str]],
    ) -> float:
        positive_weights = sorted((weight for weight in weights.values() if weight > 0), reverse=True)
        sub_weights = positive_weights[:4]
        if not sub_weights:
            return 0.0

        if slot not in {4, 5, 6}:
            return self._max_sub_stat_weight(positive_weights)

        preferred_stats = [
            stat
            for stat in preferred_main_stats.get(slot, [])
            if weights.get(stat, 0.0) > 0
        ]
        if not preferred_stats:
            return self._max_sub_stat_weight(positive_weights)
        return max(
            self._max_sub_stat_weight(
                [weight for stat, weight in weights.items() if weight > 0 and stat != main_stat]
            )
            + MAIN_STAT_EQUIVALENT_SUB_STATS * weights[main_stat]
            for main_stat in preferred_stats
        )

    def _max_sub_stat_weight(self, weights: list[float]) -> float:
        sub_weights = sorted((weight for weight in weights if weight > 0), reverse=True)[:4]
        if not sub_weights:
            return 0.0
        return sum(sub_weights) + MAX_SUB_STAT_UPGRADES * sub_weights[0]

    def _sub_stat_count(self, stat: Any) -> int:
        if not isinstance(stat, dict):
            return 0
        try:
            upgrade = int(stat.get("upgrade", stat.get("upgrade_count", 0)) or 0)
        except (TypeError, ValueError):
            upgrade = 0
        return max(1, 1 + upgrade)

    def _main_stat_level_multiplier(self, disk: dict[str, Any]) -> float:
        try:
            level = int(disk.get("level", 0) or 0)
        except (TypeError, ValueError):
            level = 0
        return max(0.25, min(1.0, 0.25 + max(0, level) * 0.05))

    def _rarity_multiplier(self, disk: dict[str, Any]) -> float:
        rarity = str(disk.get("rarity") or "S").upper()
        return RARITY_SCORE_MULTIPLIER.get(rarity, 1.0)

    def _sub_stats(self, disk: dict[str, Any]) -> list[Any]:
        sub_stats = disk.get("sub_stats", []) if isinstance(disk, dict) else []
        return sub_stats if isinstance(sub_stats, list) else []

    def _stat_name(self, stat: Any) -> str:
        if isinstance(stat, dict):
            name = stat.get("name") or stat.get("stat_name")
            return name if isinstance(name, str) else ""
        return ""

    def _stat_value(self, stat: Any) -> float:
        if not isinstance(stat, dict):
            return 0.0
        try:
            return float(stat.get("value", 0))
        except (TypeError, ValueError):
            return 0.0

    def _weight_for_stat(self, stat: Any, weights: dict[str, float]) -> float:
        return weights.get(self._stat_name(stat), 0.0)

    def _string_or_empty(self, value: Any) -> str:
        return value if isinstance(value, str) else ""
