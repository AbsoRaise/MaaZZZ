# ZZZ Disk Desktop Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python/PyWebView backend core, persistent scan history, disk optimization, cultivation recommendations, and replaceable ZZZ-style Vue views for the driver disk desktop app.

**Architecture:** Use focused Python services for character build config, disk storage, optimization, cultivation advice, and Maa scan orchestration. PyWebView exposes a thin `DesktopApi` that returns consistent JSON envelopes to Vue, while frontend views use reusable CSS/CSS variables and asset-path constants so later game screenshots/icons can replace placeholders without layout rewrites.

**Tech Stack:** Python 3.10+, PyWebView, MaaFramework Python binding placeholder, pytest, Vue 3 Composition API, Tailwind CSS.

---

## File Structure

- Create: `backend/model/schemas.py`
  - Default data, JSON-safe validation helpers, timestamp/id helpers, scoring utility types.
- Create: `backend/service/character_config_manager.py`
  - Reads/writes `data/character_builds.json`, initializes default Ellen sample, updates full character config.
- Create: `backend/service/disk_store.py`
  - Reads/writes `data/disks.json`, manages `data/scan_history/*.json`, supports single-history deletion and "use as current".
- Create: `backend/service/optimizer.py`
  - Finds best six-disk combination with exact and fallback set-match priorities.
- Create: `backend/service/cultivation_advisor.py`
  - Ranks all `level < 15` disks by character-relevant sub-stats and 4/5/6 main-stat fit.
- Create: `backend/service/maa_scanner.py`
  - Placeholder async scan worker interface and progress callbacks; later receives real MaaFramework task calls.
- Create: `backend/main.py`
  - PyWebView entrypoint, `DesktopApi`, unified responses, threaded scan progress push.
- Create: `tests/test_character_config_manager.py`
- Create: `tests/test_disk_store.py`
- Create: `tests/test_optimizer.py`
- Create: `tests/test_cultivation_advisor.py`
- Modify or create: `frontend/src/views/ScanView.vue`
  - ZZZ-style scan/history UI, current disk pool summary, history actions, replaceable asset slots.
- Modify or create: `frontend/src/views/MatchView.vue`
  - ZZZ-style character build editor, optimizer controls/results, cultivation recommendations.

Asset replacement rule:

- Use constants such as `DISK_PLACEHOLDER_ASSET`, `SET_ICON_ASSETS`, and CSS custom properties/classes in Vue.
- First implementation may use CSS radial gradients for disk records and simple text/icon placeholders.
- Later real images should only require changing imported asset paths or the asset map, not component layout.

---

## Task 1: Project Skeleton And Test Harness

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/model/__init__.py`
- Create: `backend/service/__init__.py`
- Create: `tests/__init__.py`
- Create: `pytest.ini`

- [ ] **Step 1: Create package marker files**

Create empty package markers:

```text
backend/__init__.py
backend/model/__init__.py
backend/service/__init__.py
tests/__init__.py
```

- [ ] **Step 2: Add pytest config**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -q
```

- [ ] **Step 3: Run baseline tests**

Run:

```powershell
pytest
```

Expected:

```text
no tests ran
```

- [ ] **Step 4: Commit**

```powershell
git add backend tests pytest.ini
git commit -m "chore: initialize backend test harness"
```

---

## Task 2: Shared Schemas And Defaults

**Files:**
- Create: `backend/model/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_schemas.py`:

```python
from backend.model.schemas import (
    DEFAULT_CHARACTER_BUILDS,
    build_scan_id,
    normalize_slot_main_stats,
    safe_scan_id,
    summarize_disks,
)


def test_default_character_build_contains_sets_and_main_stats():
    ellen = DEFAULT_CHARACTER_BUILDS["艾莲·乔"]
    assert "weights" in ellen
    assert ellen["preferred_sets"]["target_set_4"] == "极地重金属"
    assert "5" in ellen["preferred_main_stats"]


def test_normalize_slot_main_stats_turns_keys_into_ints():
    assert normalize_slot_main_stats({"4": "暴击率", 5: "冰属性伤害"}) == {
        4: "暴击率",
        5: "冰属性伤害",
    }


def test_safe_scan_id_rejects_path_traversal():
    assert safe_scan_id("20260518-143012-a8f3")
    assert not safe_scan_id("../bad")
    assert not safe_scan_id("bad/path")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_schemas.py -q
```

Expected: import failure because `backend.model.schemas` does not exist.

- [ ] **Step 3: Implement shared schema helpers**

Create `backend/model/schemas.py`:

```python
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import re


APP_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = APP_ROOT / "data"
CHARACTER_BUILDS_PATH = DATA_DIR / "character_builds.json"
CURRENT_DISKS_PATH = DATA_DIR / "disks.json"
SCAN_HISTORY_DIR = DATA_DIR / "scan_history"


DEFAULT_CHARACTER_BUILDS: dict[str, dict[str, Any]] = {
    "艾莲·乔": {
        "weights": {
            "暴击率": 1.0,
            "暴击伤害": 1.0,
            "冰属性伤害": 1.0,
            "攻击力百分比": 0.6,
            "攻击力": 0.4,
            "生命值": 0.0,
            "防御力": 0.0,
        },
        "preferred_main_stats": {
            "4": ["暴击率", "暴击伤害"],
            "5": ["冰属性伤害", "攻击力百分比"],
            "6": ["攻击力百分比"],
        },
        "preferred_sets": {
            "target_set_4": "极地重金属",
            "target_set_2": "啄木鸟电音",
            "alternatives": [
                {
                    "target_set_4": "啄木鸟电音",
                    "target_set_2": "极地重金属",
                    "note": "暴击率不足时可用",
                }
            ],
        },
    }
}


SCAN_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{4,12}$")


def now_iso() -> str:
    """返回带时区的 ISO 时间，便于历史扫描审计。"""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_scan_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid4().hex[:4]}"


def safe_scan_id(scan_id: str) -> bool:
    return isinstance(scan_id, str) and bool(SCAN_ID_RE.fullmatch(scan_id))


def normalize_slot_main_stats(raw: dict[Any, Any] | None) -> dict[int, str]:
    if not raw:
        return {}
    normalized: dict[int, str] = {}
    for key, value in raw.items():
        try:
            slot = int(key)
        except (TypeError, ValueError):
            continue
        if 1 <= slot <= 6 and isinstance(value, str) and value.strip():
            normalized[slot] = value.strip()
    return normalized


def normalize_preferred_main_stats(raw: dict[Any, Any] | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        try:
            slot = int(key)
        except (TypeError, ValueError):
            continue
        if slot not in (4, 5, 6):
            continue
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = [item for item in value if isinstance(item, str) and item.strip()]
        else:
            values = []
        result[str(slot)] = values
    return result


def summarize_disks(disks: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    slot_counts = Counter(str(disk.get("slot")) for disk in disks if disk.get("slot") in range(1, 7))
    set_counts = Counter(
        str(disk.get("set_name"))
        for disk in disks
        if isinstance(disk.get("set_name"), str) and disk.get("set_name")
    )
    return {
        "slot_counts": dict(sorted(slot_counts.items())),
        "set_counts": dict(sorted(set_counts.items())),
    }
```

- [ ] **Step 4: Run tests**

Run:

```powershell
pytest tests/test_schemas.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/model/schemas.py tests/test_schemas.py
git commit -m "feat: add shared backend schemas"
```

---

## Task 3: Character Build Config Manager

**Files:**
- Create: `backend/service/character_config_manager.py`
- Test: `tests/test_character_config_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_character_config_manager.py`:

```python
import json

from backend.service.character_config_manager import CharacterConfigManager


def test_manager_creates_default_file(tmp_path):
    path = tmp_path / "character_builds.json"
    manager = CharacterConfigManager(path)
    data = manager.get_all()
    assert "艾莲·乔" in data
    assert path.exists()


def test_save_character_build_persists_config(tmp_path):
    path = tmp_path / "character_builds.json"
    manager = CharacterConfigManager(path)
    config = {
        "weights": {"暴击率": 1.0},
        "preferred_main_stats": {"4": ["暴击率"]},
        "preferred_sets": {"target_set_4": "啄木鸟电音", "target_set_2": "激素朋克", "alternatives": []},
    }
    manager.save_character_build("测试角色", config)
    reloaded = CharacterConfigManager(path).get_character_build("测试角色")
    assert reloaded["preferred_sets"]["target_set_2"] == "激素朋克"


def test_corrupt_json_is_backed_up(tmp_path):
    path = tmp_path / "character_builds.json"
    path.write_text("{bad json", encoding="utf-8")
    manager = CharacterConfigManager(path)
    assert "艾莲·乔" in manager.get_all()
    backups = list(tmp_path.glob("character_builds.json.bak-*"))
    assert len(backups) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_character_config_manager.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement manager**

Create `backend/service/character_config_manager.py`:

```python
from __future__ import annotations

import copy
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.model.schemas import CHARACTER_BUILDS_PATH, DEFAULT_CHARACTER_BUILDS, normalize_preferred_main_stats


class CharacterConfigManager:
    """管理角色评分权重、推荐主属性和推荐套装配置。"""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = Path(config_path or CHARACTER_BUILDS_PATH)
        self._lock = threading.RLock()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load_or_init()

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def get_character_build(self, character_name: str) -> dict[str, Any]:
        with self._lock:
            if character_name not in self._data:
                raise KeyError(f"角色不存在：{character_name}")
            return copy.deepcopy(self._data[character_name])

    def save_character_build(self, character_name: str, config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(character_name, str) or not character_name.strip():
            raise ValueError("角色名称不能为空")
        normalized = self._normalize_character_config(config)
        with self._lock:
            self._data[character_name.strip()] = normalized
            self._atomic_write(self._data)
            return copy.deepcopy(normalized)

    def update_weights(self, character_name: str, new_weights: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            config = self.get_character_build(character_name)
            config["weights"] = self._normalize_weights(new_weights)
            return self.save_character_build(character_name, config)

    def _load_or_init(self) -> dict[str, Any]:
        if not self.config_path.exists():
            data = copy.deepcopy(DEFAULT_CHARACTER_BUILDS)
            self._atomic_write(data)
            return data
        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                raise ValueError("角色配置根节点必须是对象")
            return raw
        except Exception:
            backup = self.config_path.with_name(
                f"{self.config_path.name}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            self.config_path.replace(backup)
            data = copy.deepcopy(DEFAULT_CHARACTER_BUILDS)
            self._atomic_write(data)
            return data

    def _normalize_character_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(config, dict):
            raise ValueError("角色配置必须是对象")
        preferred_sets = config.get("preferred_sets") or {}
        if not isinstance(preferred_sets, dict):
            preferred_sets = {}
        return {
            "weights": self._normalize_weights(config.get("weights") or {}),
            "preferred_main_stats": normalize_preferred_main_stats(config.get("preferred_main_stats")),
            "preferred_sets": {
                "target_set_4": str(preferred_sets.get("target_set_4") or ""),
                "target_set_2": str(preferred_sets.get("target_set_2") or ""),
                "alternatives": preferred_sets.get("alternatives") if isinstance(preferred_sets.get("alternatives"), list) else [],
            },
        }

    def _normalize_weights(self, weights: dict[str, Any]) -> dict[str, float]:
        if not isinstance(weights, dict):
            raise ValueError("权重必须是对象")
        result: dict[str, float] = {}
        for name, value in weights.items():
            if not isinstance(name, str) or not name.strip():
                continue
            try:
                result[name.strip()] = float(value)
            except (TypeError, ValueError):
                result[name.strip()] = 0.0
        return result

    def _atomic_write(self, data: dict[str, Any]) -> None:
        temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
        temp_path.replace(self.config_path)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
pytest tests/test_character_config_manager.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/service/character_config_manager.py tests/test_character_config_manager.py
git commit -m "feat: manage character build configs"
```

---

## Task 4: Disk Store And Scan History

**Files:**
- Create: `backend/service/disk_store.py`
- Test: `tests/test_disk_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_disk_store.py`:

```python
import pytest

from backend.service.disk_store import DiskStore


def sample_disks():
    return [
        {
            "id": "disk_1",
            "slot": 5,
            "set_name": "极地重金属",
            "level": 1,
            "inventory_pos": {"page": 2, "row": 3, "column": 5, "index": 17},
            "main_stat": {"name": "冰属性伤害", "value": 7.2},
            "sub_stats": [{"name": "暴击率", "value": 2.4}],
        }
    ]


def test_save_scan_updates_current_and_history(tmp_path):
    store = DiskStore(tmp_path / "disks.json", tmp_path / "scan_history")
    record = store.save_scan_result(sample_disks(), source="test", logs=["ok"])
    assert store.get_current_disks()[0]["id"] == "disk_1"
    assert record["disk_count"] == 1
    assert len(store.list_scan_history()) == 1


def test_use_scan_result_restores_current(tmp_path):
    store = DiskStore(tmp_path / "disks.json", tmp_path / "scan_history")
    first = store.save_scan_result(sample_disks(), source="test")
    store.save_current_disks([])
    store.use_scan_result(first["scan_id"])
    assert len(store.get_current_disks()) == 1


def test_delete_scan_result_removes_one_history(tmp_path):
    store = DiskStore(tmp_path / "disks.json", tmp_path / "scan_history")
    record = store.save_scan_result(sample_disks(), source="test")
    assert store.delete_scan_result(record["scan_id"]) is True
    assert store.list_scan_history() == []


def test_invalid_scan_id_is_rejected(tmp_path):
    store = DiskStore(tmp_path / "disks.json", tmp_path / "scan_history")
    with pytest.raises(ValueError):
        store.get_scan_result("../bad")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_disk_store.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement disk store**

Create `backend/service/disk_store.py`:

```python
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from backend.model.schemas import (
    CURRENT_DISKS_PATH,
    SCAN_HISTORY_DIR,
    build_scan_id,
    now_iso,
    safe_scan_id,
    summarize_disks,
)


class DiskStore:
    """管理当前驱动盘池和每次扫描的历史快照。"""

    def __init__(self, current_path: Path | None = None, history_dir: Path | None = None) -> None:
        self.current_path = Path(current_path or CURRENT_DISKS_PATH)
        self.history_dir = Path(history_dir or SCAN_HISTORY_DIR)
        self._lock = threading.RLock()
        self.current_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        if not self.current_path.exists():
            self._atomic_write(self.current_path, [])

    def get_current_disks(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._read_json(self.current_path, []))

    def save_current_disks(self, disks: list[dict[str, Any]]) -> None:
        if not isinstance(disks, list):
            raise ValueError("驱动盘数据必须是列表")
        with self._lock:
            self._atomic_write(self.current_path, disks)

    def save_scan_result(
        self,
        disks: list[dict[str, Any]],
        source: str = "maa",
        logs: list[str] | None = None,
        scan_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(disks, list):
            raise ValueError("扫描结果必须是列表")
        scan_id = scan_id or build_scan_id()
        if not safe_scan_id(scan_id):
            raise ValueError("非法扫描 ID")
        created_at = now_iso()
        enriched = []
        for index, disk in enumerate(disks, start=1):
            item = copy.deepcopy(disk)
            item.setdefault("id", f"disk_{scan_id}_{index:04d}")
            item["scan_meta"] = {"scan_id": scan_id, "scanned_at": created_at}
            enriched.append(item)
        record = {
            "scan_id": scan_id,
            "created_at": created_at,
            "source": source,
            "disk_count": len(enriched),
            "summary": summarize_disks(enriched),
            "disks": enriched,
            "logs": logs or [],
        }
        with self._lock:
            self._atomic_write(self.current_path, enriched)
            self._atomic_write(self._history_path(scan_id), record)
        return copy.deepcopy(record)

    def list_scan_history(self) -> list[dict[str, Any]]:
        with self._lock:
            records = []
            for path in self.history_dir.glob("*.json"):
                record = self._read_json(path, {})
                if not isinstance(record, dict):
                    continue
                records.append(
                    {
                        "scan_id": record.get("scan_id"),
                        "created_at": record.get("created_at"),
                        "source": record.get("source"),
                        "disk_count": record.get("disk_count", 0),
                        "summary": record.get("summary", {}),
                    }
                )
            return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def get_scan_result(self, scan_id: str) -> dict[str, Any]:
        path = self._history_path(scan_id)
        if not path.exists():
            raise FileNotFoundError(f"扫描记录不存在：{scan_id}")
        record = self._read_json(path, {})
        if not isinstance(record, dict):
            raise ValueError("扫描记录格式错误")
        return copy.deepcopy(record)

    def delete_scan_result(self, scan_id: str) -> bool:
        path = self._history_path(scan_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            return True

    def use_scan_result(self, scan_id: str) -> list[dict[str, Any]]:
        record = self.get_scan_result(scan_id)
        disks = record.get("disks", [])
        if not isinstance(disks, list):
            raise ValueError("扫描记录中没有有效驱动盘列表")
        self.save_current_disks(disks)
        return copy.deepcopy(disks)

    def _history_path(self, scan_id: str) -> Path:
        if not safe_scan_id(scan_id):
            raise ValueError("非法扫描 ID")
        return self.history_dir / f"{scan_id}.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return copy.deepcopy(default)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 文件损坏：{path}") from exc

    def _atomic_write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
        temp_path.replace(path)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
pytest tests/test_disk_store.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/service/disk_store.py tests/test_disk_store.py
git commit -m "feat: persist disks and scan history"
```

---

## Task 5: Combination Optimizer

**Files:**
- Create: `backend/service/optimizer.py`
- Test: `tests/test_optimizer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_optimizer.py`:

```python
from backend.service.optimizer import DiskOptimizer


def disk(disk_id, slot, set_name, main_name="攻击力", level=15, crit=2.4):
    return {
        "id": disk_id,
        "slot": slot,
        "set_name": set_name,
        "level": level,
        "inventory_pos": {"page": 1, "row": 1, "column": slot, "index": slot},
        "main_stat": {"name": main_name, "value": 10.0},
        "sub_stats": [{"name": "暴击率", "value": crit}],
    }


def build_config():
    return {
        "weights": {"攻击力": 0.5, "暴击率": 1.0, "冰属性伤害": 1.0},
        "preferred_main_stats": {"4": ["暴击率"], "5": ["冰属性伤害"], "6": ["攻击力"]},
        "preferred_sets": {"target_set_4": "极地重金属", "target_set_2": "啄木鸟电音"},
    }


def test_optimizer_finds_exact_4_2():
    disks = [
        disk("a1", 1, "极地重金属"),
        disk("a2", 2, "极地重金属"),
        disk("a3", 3, "极地重金属"),
        disk("a4", 4, "极地重金属", "暴击率"),
        disk("b5", 5, "啄木鸟电音", "冰属性伤害"),
        disk("b6", 6, "啄木鸟电音"),
    ]
    result = DiskOptimizer(build_config()).find_best_combination(
        "艾莲·乔",
        {"target_set_4": "极地重金属", "target_set_2": "啄木鸟电音"},
        disks,
    )
    assert result["match_type"] == "exact_4_2"
    assert not result["is_fallback"]
    assert len(result["combo"]) == 6


def test_optimizer_returns_best_score_fallback_when_sets_missing():
    disks = [disk(f"x{slot}", slot, "自由蓝调", crit=slot) for slot in range(1, 7)]
    result = DiskOptimizer(build_config()).find_best_combination(
        "艾莲·乔",
        {"target_set_4": "极地重金属", "target_set_2": "啄木鸟电音"},
        disks,
    )
    assert result["is_fallback"]
    assert result["match_type"] == "best_score_only"
    assert result["warnings"]


def test_optimizer_main_stat_filter_can_fallback_per_slot():
    disks = [disk(f"x{slot}", slot, "自由蓝调") for slot in range(1, 7)]
    result = DiskOptimizer(build_config()).find_best_combination(
        "艾莲·乔",
        {"slot_main_stats": {"4": "暴击率"}},
        disks,
    )
    assert any("4 号位" in warning for warning in result["warnings"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_optimizer.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement optimizer**

Create `backend/service/optimizer.py`:

```python
from __future__ import annotations

from itertools import product
from typing import Any

from backend.model.schemas import normalize_slot_main_stats


MATCH_RANKS = {
    "exact_4_2": 5,
    "target_4_any_2": 4,
    "any_4_2": 3,
    "two_two_two": 2,
    "best_score_only": 1,
}


class DiskOptimizer:
    """根据角色配置、目标套装和主属性要求寻找最高分六件组合。"""

    def __init__(self, character_builds: dict[str, Any]) -> None:
        self.character_builds = character_builds

    def find_best_combination(
        self,
        character_name: str,
        config: dict[str, Any] | None,
        all_disks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        build = self._get_build(character_name)
        config = config or {}
        weights = build.get("weights", {})
        preferred_sets = build.get("preferred_sets", {})
        target_set_4 = config.get("target_set_4") or preferred_sets.get("target_set_4") or ""
        target_set_2 = config.get("target_set_2") or preferred_sets.get("target_set_2") or ""
        slot_main_stats = normalize_slot_main_stats(
            config.get("slot_main_stats")
            or {slot: values[0] for slot, values in build.get("preferred_main_stats", {}).items() if values}
        )

        grouped, warnings = self._group_candidates(all_disks, slot_main_stats)
        missing = [slot for slot in range(1, 7) if not grouped.get(slot)]
        if missing:
            raise ValueError(f"以下槽位没有可用驱动盘：{missing}")

        best: dict[str, Any] | None = None
        for combo_tuple in product(*(grouped[slot] for slot in range(1, 7))):
            combo = list(combo_tuple)
            total_score = sum(self.score_disk(disk, weights) for disk in combo)
            set_counts = self._set_counts(combo)
            match_type = self._match_type(set_counts, target_set_4, target_set_2)
            candidate = {
                "character_name": character_name,
                "combo": combo,
                "total_score": round(total_score, 4),
                "set_counts": set_counts,
                "match_type": match_type,
                "is_fallback": match_type != "exact_4_2",
                "warnings": list(warnings),
                "score_breakdown": [
                    {
                        "disk_id": disk.get("id"),
                        "slot": disk.get("slot"),
                        "score": round(self.score_disk(disk, weights), 4),
                    }
                    for disk in combo
                ],
            }
            if self._is_better(candidate, best):
                best = candidate

        if best is None:
            raise ValueError("没有找到可用组合")
        if best["is_fallback"]:
            best["warnings"].append("未找到完全满足目标套装的组合，已返回降级最优方案")
        return best

    def score_disk(self, disk: dict[str, Any], weights: dict[str, Any]) -> float:
        main_stat = disk.get("main_stat") or {}
        score = float(main_stat.get("value") or 0) * float(weights.get(main_stat.get("name"), 0) or 0) * 2.0
        for sub_stat in disk.get("sub_stats") or []:
            score += float(sub_stat.get("value") or 0) * float(weights.get(sub_stat.get("name"), 0) or 0)
        return score

    def _get_build(self, character_name: str) -> dict[str, Any]:
        if character_name not in self.character_builds:
            raise KeyError(f"角色不存在：{character_name}")
        return self.character_builds[character_name]

    def _group_candidates(
        self,
        all_disks: list[dict[str, Any]],
        slot_main_stats: dict[int, str],
    ) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
        raw: dict[int, list[dict[str, Any]]] = {slot: [] for slot in range(1, 7)}
        for disk in all_disks:
            slot = disk.get("slot")
            if slot in raw:
                raw[slot].append(disk)
        warnings: list[str] = []
        grouped: dict[int, list[dict[str, Any]]] = {}
        for slot in range(1, 7):
            requested = slot_main_stats.get(slot)
            if requested:
                filtered = [d for d in raw[slot] if (d.get("main_stat") or {}).get("name") == requested]
                if filtered:
                    grouped[slot] = filtered
                else:
                    grouped[slot] = raw[slot]
                    warnings.append(f"{slot} 号位没有主属性 {requested} 的驱动盘，已回退为该槽位全部候选")
            else:
                grouped[slot] = raw[slot]
        return grouped, warnings

    def _set_counts(self, combo: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for disk in combo:
            set_name = str(disk.get("set_name") or "")
            counts[set_name] = counts.get(set_name, 0) + 1
        return counts

    def _match_type(self, set_counts: dict[str, int], target_set_4: str, target_set_2: str) -> str:
        has_target_4 = bool(target_set_4) and set_counts.get(target_set_4, 0) >= 4
        has_target_2 = bool(target_set_2) and set_counts.get(target_set_2, 0) >= 2
        has_any_4 = any(count >= 4 for count in set_counts.values())
        pair_count = sum(1 for count in set_counts.values() if count >= 2)
        if has_target_4 and has_target_2:
            return "exact_4_2"
        if has_target_4 and pair_count >= 2:
            return "target_4_any_2"
        if has_any_4 and pair_count >= 2:
            return "any_4_2"
        if pair_count >= 3:
            return "two_two_two"
        return "best_score_only"

    def _is_better(self, candidate: dict[str, Any], best: dict[str, Any] | None) -> bool:
        if best is None:
            return True
        candidate_rank = MATCH_RANKS[candidate["match_type"]]
        best_rank = MATCH_RANKS[best["match_type"]]
        return (candidate_rank, candidate["total_score"]) > (best_rank, best["total_score"])
```

- [ ] **Step 4: Run tests**

Run:

```powershell
pytest tests/test_optimizer.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/service/optimizer.py tests/test_optimizer.py
git commit -m "feat: optimize disk combinations"
```

---

## Task 6: Cultivation Advisor

**Files:**
- Create: `backend/service/cultivation_advisor.py`
- Test: `tests/test_cultivation_advisor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cultivation_advisor.py`:

```python
from backend.service.cultivation_advisor import CultivationAdvisor


BUILDS = {
    "艾莲·乔": {
        "weights": {"暴击率": 1.0, "暴击伤害": 1.0, "冰属性伤害": 1.0, "攻击力": 0.3},
        "preferred_main_stats": {"4": ["暴击率"], "5": ["冰属性伤害"], "6": ["攻击力"]},
        "preferred_sets": {},
    }
}


def disk(level, slot, main_name, subs):
    return {
        "id": f"d{slot}",
        "slot": slot,
        "set_name": "极地重金属",
        "level": level,
        "inventory_pos": {"page": 2, "row": 3, "column": slot, "index": slot},
        "main_stat": {"name": main_name, "value": 10},
        "sub_stats": [{"name": name, "value": value} for name, value in subs],
    }


def test_recommends_unfinished_disk_with_effective_substats_and_matched_main():
    advisor = CultivationAdvisor(BUILDS)
    result = advisor.find_promising_disks(
        "艾莲·乔",
        {"min_effective_sub_stats": 2},
        [disk(1, 5, "冰属性伤害", [("暴击率", 2.4), ("暴击伤害", 4.8)])],
    )
    assert result[0]["rank"] == "high"
    assert result[0]["main_stat_matched"] is True
    assert "仓库位置：P2 / R3 / C5" in result[0]["reasons"]


def test_ignores_max_level_disks():
    advisor = CultivationAdvisor(BUILDS)
    result = advisor.find_promising_disks(
        "艾莲·乔",
        {},
        [disk(15, 5, "冰属性伤害", [("暴击率", 2.4), ("暴击伤害", 4.8)])],
    )
    assert result == []


def test_keeps_good_substat_disk_with_unmatched_456_main_as_lower_priority():
    advisor = CultivationAdvisor(BUILDS)
    result = advisor.find_promising_disks(
        "艾莲·乔",
        {"min_effective_sub_stats": 2},
        [disk(3, 5, "生命值", [("暴击率", 2.4), ("暴击伤害", 4.8)])],
    )
    assert result[0]["main_stat_matched"] is False
    assert result[0]["rank"] in {"medium", "low"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_cultivation_advisor.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement cultivation advisor**

Create `backend/service/cultivation_advisor.py`:

```python
from __future__ import annotations

from typing import Any

from backend.service.optimizer import DiskOptimizer


class CultivationAdvisor:
    """筛选未满级且对角色有培养价值的胚子盘。"""

    def __init__(self, character_builds: dict[str, Any]) -> None:
        self.character_builds = character_builds

    def find_promising_disks(
        self,
        character_name: str,
        options: dict[str, Any] | None,
        all_disks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if character_name not in self.character_builds:
            raise KeyError(f"角色不存在：{character_name}")
        options = options or {}
        build = self.character_builds[character_name]
        weights = build.get("weights", {})
        preferred_main_stats = build.get("preferred_main_stats", {})
        min_effective = int(options.get("min_effective_sub_stats", 1))
        high_threshold = float(options.get("high_weight_threshold", 0.8))
        optimizer = DiskOptimizer(self.character_builds)

        recommendations: list[dict[str, Any]] = []
        for disk in all_disks:
            level = int(disk.get("level") or 0)
            if level >= 15:
                continue
            sub_stats = disk.get("sub_stats") or []
            effective = [s for s in sub_stats if float(weights.get(s.get("name"), 0) or 0) > 0]
            high_value = [s for s in effective if float(weights.get(s.get("name"), 0) or 0) >= high_threshold]
            if len(effective) < min_effective:
                continue

            slot = int(disk.get("slot") or 0)
            main_name = (disk.get("main_stat") or {}).get("name")
            preferred = preferred_main_stats.get(str(slot), [])
            main_matched = True
            main_bonus = 0.0
            if slot in (4, 5, 6):
                main_matched = main_name in preferred if preferred else False
                main_bonus = 12.0 if main_matched else -6.0

            weight_sum = sum(float(weights.get(s.get("name"), 0) or 0) for s in effective)
            low_level_bonus = max(0, 15 - level) * 0.4
            potential_score = weight_sum * 10 + len(high_value) * 5 + len(effective) * 2 + main_bonus + low_level_bonus
            rank = "high" if potential_score >= 28 else "medium" if potential_score >= 18 else "low"

            pos = disk.get("inventory_pos") or {}
            reasons = [
                "未满级驱动盘",
                f"包含 {len(effective)} 条角色有效副词条",
            ]
            if slot in (4, 5, 6):
                if main_matched:
                    reasons.append(f"{slot} 号位主属性匹配：{main_name}")
                else:
                    reasons.append(f"{slot} 号位主属性未命中推荐：{main_name}")
            if pos:
                reasons.append(f"仓库位置：P{pos.get('page')} / R{pos.get('row')} / C{pos.get('column')}")

            recommendations.append(
                {
                    "disk": disk,
                    "potential_score": round(potential_score, 4),
                    "current_score": round(optimizer.score_disk(disk, weights), 4),
                    "rank": rank,
                    "effective_sub_stat_count": len(effective),
                    "high_value_sub_stat_count": len(high_value),
                    "main_stat_matched": main_matched,
                    "reasons": reasons,
                }
            )

        return sorted(recommendations, key=lambda item: item["potential_score"], reverse=True)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
pytest tests/test_cultivation_advisor.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/service/cultivation_advisor.py tests/test_cultivation_advisor.py
git commit -m "feat: recommend cultivation candidates"
```

---

## Task 7: Maa Scanner Placeholder

**Files:**
- Create: `backend/service/maa_scanner.py`

- [ ] **Step 1: Create scanner interface**

Create `backend/service/maa_scanner.py`:

```python
from __future__ import annotations

import time
from typing import Any, Callable


ProgressCallback = Callable[[dict[str, Any]], None]


class MaaScanner:
    """MaaFramework 扫描适配层。

    第一版保留可运行的模拟扫描，后续把 `run_scan` 内部替换为真实 Maa 任务调用。
    """

    def run_scan(self, on_progress: ProgressCallback | None = None) -> tuple[list[dict[str, Any]], list[str]]:
        logs: list[str] = []
        for progress, message in [(10, "初始化 Maa 扫描任务"), (45, "读取仓库页面"), (80, "识别驱动盘词条")]:
            logs.append(message)
            if on_progress:
                on_progress({"progress": progress, "message": message})
            time.sleep(0.2)
        disks = [
            {
                "slot": 5,
                "set_name": "极地重金属",
                "level": 1,
                "inventory_pos": {"page": 1, "row": 1, "column": 1, "index": 1},
                "main_stat": {"name": "冰属性伤害", "value": 7.2},
                "sub_stats": [{"name": "暴击率", "value": 2.4}, {"name": "暴击伤害", "value": 4.8}],
            }
        ]
        logs.append("扫描完成")
        if on_progress:
            on_progress({"progress": 100, "message": "扫描完成"})
        return disks, logs
```

- [ ] **Step 2: Commit**

```powershell
git add backend/service/maa_scanner.py
git commit -m "feat: add maa scanner placeholder"
```

---

## Task 8: PyWebView Main API

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Implement DesktopApi and entrypoint**

Create `backend/main.py`:

```python
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

import webview

from backend.model.schemas import APP_ROOT
from backend.service.character_config_manager import CharacterConfigManager
from backend.service.cultivation_advisor import CultivationAdvisor
from backend.service.disk_store import DiskStore
from backend.service.maa_scanner import MaaScanner
from backend.service.optimizer import DiskOptimizer


def ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def fail(error: Exception | str) -> dict[str, Any]:
    return {"success": False, "data": None, "error": str(error)}


class DesktopApi:
    def __init__(self) -> None:
        self.character_manager = CharacterConfigManager()
        self.disk_store = DiskStore()
        self.scanner = MaaScanner()
        self.window: webview.Window | None = None
        self._scan_lock = threading.Lock()
        self._scan_running = False

    def bind_window(self, window: webview.Window) -> None:
        self.window = window

    def get_character_builds(self) -> dict[str, Any]:
        return self._call(lambda: self.character_manager.get_all())

    def save_character_build(self, character_name: str, config: dict[str, Any]) -> dict[str, Any]:
        return self._call(lambda: self.character_manager.save_character_build(character_name, config))

    def get_current_disks(self) -> dict[str, Any]:
        return self._call(lambda: self.disk_store.get_current_disks())

    def get_scan_history(self) -> dict[str, Any]:
        return self._call(lambda: self.disk_store.list_scan_history())

    def get_scan_result(self, scan_id: str) -> dict[str, Any]:
        return self._call(lambda: self.disk_store.get_scan_result(scan_id))

    def delete_scan_result(self, scan_id: str) -> dict[str, Any]:
        return self._call(lambda: self.disk_store.delete_scan_result(scan_id))

    def use_scan_result(self, scan_id: str) -> dict[str, Any]:
        return self._call(lambda: self.disk_store.use_scan_result(scan_id))

    def get_optimize_combo(self, character_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            optimizer = DiskOptimizer(self.character_manager.get_all())
            return optimizer.find_best_combination(character_name, config or {}, self.disk_store.get_current_disks())

        return self._call(run)

    def get_promising_disks(self, character_name: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        def run() -> list[dict[str, Any]]:
            advisor = CultivationAdvisor(self.character_manager.get_all())
            return advisor.find_promising_disks(character_name, options or {}, self.disk_store.get_current_disks())

        return self._call(run)

    def start_maa_scan(self) -> dict[str, Any]:
        with self._scan_lock:
            if self._scan_running:
                return fail("扫描任务正在运行")
            self._scan_running = True
        thread = threading.Thread(target=self._scan_worker, daemon=True)
        thread.start()
        return ok({"started": True})

    def _scan_worker(self) -> None:
        try:
            disks, logs = self.scanner.run_scan(self._push_progress)
            record = self.disk_store.save_scan_result(disks, source="maa", logs=logs)
            self._push_event("maa-complete", record)
        except Exception as exc:
            self._push_event("maa-error", {"message": str(exc)})
        finally:
            with self._scan_lock:
                self._scan_running = False

    def _push_progress(self, payload: dict[str, Any]) -> None:
        self._push_event("maa-progress", payload)

    def _push_event(self, event_name: str, payload: dict[str, Any]) -> None:
        if not self.window:
            return
        script = (
            "window.dispatchEvent(new CustomEvent("
            f"{json.dumps(event_name)}, "
            f"{{ detail: {json.dumps(payload, ensure_ascii=False)} }}"
            "));"
        )
        self.window.evaluate_js(script)

    def _call(self, func: Callable[[], Any]) -> dict[str, Any]:
        try:
            return ok(func())
        except Exception as exc:
            return fail(exc)


def main() -> None:
    index_path = APP_ROOT / "frontend" / "dist" / "index.html"
    if not index_path.exists():
        raise FileNotFoundError(f"前端入口不存在，请先运行 npm run build：{index_path}")
    api = DesktopApi()
    window = webview.create_window(
        "绝区零驱动盘扫描配装工具",
        url=index_path.as_uri(),
        js_api=api,
        width=1280,
        height=720,
    )
    api.bind_window(window)
    webview.start(debug=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run backend import check**

Run:

```powershell
python -m py_compile backend/main.py backend/service/*.py backend/model/*.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Commit**

```powershell
git add backend/main.py
git commit -m "feat: expose desktop api"
```

---

## Task 9: ScanView Vue UI

**Files:**
- Modify or create: `frontend/src/views/ScanView.vue`

- [ ] **Step 1: Implement ScanView**

Create or replace `frontend/src/views/ScanView.vue` with a Vue 3 Composition API page that:

- Calls `window.pywebview.api.start_maa_scan()`.
- Listens for `maa-progress`, `maa-complete`, and `maa-error`.
- Calls `get_current_disks()`, `get_scan_history()`, `get_scan_result(scan_id)`, `delete_scan_result(scan_id)`, and `use_scan_result(scan_id)`.
- Uses local constants:

```js
const DISK_PLACEHOLDER_ASSET = ''
const SET_ICON_ASSETS = {}
```

Implementation requirements:

- Keep disk record visuals in one local `DiskCard` area/template block.
- Use CSS radial gradients when `DISK_PLACEHOLDER_ASSET` is empty.
- Show `inventory_pos` as `P页 / R行 / C列`.
- Use Tailwind classes for black/yellow high-contrast ZZZ style.
- Use `transition-all duration-100 ease-out`.
- Use no hardcoded game-image dependency.

- [ ] **Step 2: Verify build**

Run:

```powershell
npm run build
```

Expected: Vue build completes and writes `frontend/dist`.

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/views/ScanView.vue frontend/dist
git commit -m "feat: add zzz scan history view"
```

---

## Task 10: MatchView Vue UI

**Files:**
- Modify or create: `frontend/src/views/MatchView.vue`

- [ ] **Step 1: Implement MatchView**

Create or replace `frontend/src/views/MatchView.vue` with a Vue 3 Composition API page that:

- Loads `get_character_builds()` and `get_current_disks()`.
- Allows selecting a character.
- Allows editing:
  - `weights`
  - `preferred_main_stats`
  - `preferred_sets`
- Calls `save_character_build(characterName, config)`.
- Calls `get_optimize_combo(characterName, config)`.
- Calls `get_promising_disks(characterName, options)`.
- Displays optimizer `match_type`, `is_fallback`, `warnings`, `total_score`, `set_counts`, and `combo`.
- Displays cultivation recommendations with `rank`, `potential_score`, `current_score`, reasons, and warehouse position.
- Uses local constants:

```js
const DISK_PLACEHOLDER_ASSET = ''
const STAT_ICON_ASSETS = {}
const SET_ICON_ASSETS = {}
```

Implementation requirements:

- Reuse the same black-record disk card visual language as `ScanView.vue`.
- Keep image/icon usage behind asset maps for later replacement with real game screenshots/icons.
- Use `font-black` for titles and scores.
- Use `font-mono` for numeric values.
- Use black/yellow hover inversion on primary buttons.

- [ ] **Step 2: Verify build**

Run:

```powershell
npm run build
```

Expected: Vue build completes and writes `frontend/dist`.

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/views/MatchView.vue frontend/dist
git commit -m "feat: add zzz match and cultivation view"
```

---

## Task 11: End-To-End Verification

**Files:**
- No new files unless fixing issues found by verification.

- [ ] **Step 1: Run all backend tests**

Run:

```powershell
pytest
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Run Python compile check**

Run:

```powershell
python -m py_compile backend/main.py backend/service/*.py backend/model/*.py
```

Expected: no syntax errors.

- [ ] **Step 4: Start desktop app manually**

Run:

```powershell
python -m backend.main
```

Expected:

- A 1280x720 PyWebView window opens.
- Scan page can start simulated scan and receive progress events.
- A scan history entry appears after completion.
- Match page can run optimizer and cultivation recommendation against current disks.

- [ ] **Step 5: Commit verification fixes**

If verification required fixes:

```powershell
git add backend frontend tests data
git commit -m "fix: resolve desktop verification issues"
```

If no fixes were needed, skip this commit.

---

## Self-Review Notes

- Spec coverage:
  - Character config persistence: Task 3.
  - Current disk pool and scan history: Task 4.
  - Single scan deletion: Task 4.
  - Exact and fallback optimization: Task 5.
  - Cultivation recommendation for all unfinished disks: Task 6.
  - 4/5/6 main-stat matching in cultivation recommendation: Task 6.
  - Warehouse position preservation: Tasks 4, 6, 9, 10.
  - Maa async placeholder and progress events: Tasks 7, 8.
  - PyWebView desktop API: Task 8.
  - ZZZ-style Vue views: Tasks 9 and 10.
  - Replaceable visual assets: Tasks 9 and 10.
- Placeholder scan:
  - The Maa scanner intentionally contains a runnable placeholder interface because real Maa resources are not provided yet. It is isolated in `maa_scanner.py` so replacement is localized.
- Type consistency:
  - Character config fields are consistently `weights`, `preferred_main_stats`, and `preferred_sets`.
  - Disk position is consistently `inventory_pos.page/row/column/index`.
  - API result envelope is consistently `success/data/error`.
