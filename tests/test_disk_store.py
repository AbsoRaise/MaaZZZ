import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from backend.service import disk_store
from backend.service.disk_store import DiskStore


@pytest.fixture
def temp_dir():
    path = Path(__file__).parent / ".tmp_disk_store" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def store(temp_dir, monkeypatch):
    current_path = temp_dir / "disks.json"
    history_dir = temp_dir / "scan_history"
    monkeypatch.setattr(disk_store, "CURRENT_DISKS_PATH", current_path)
    monkeypatch.setattr(disk_store, "SCAN_HISTORY_DIR", history_dir)
    return DiskStore()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_init_creates_empty_current_disks_when_missing(temp_dir, monkeypatch):
    current_path = temp_dir / "disks.json"
    monkeypatch.setattr(disk_store, "CURRENT_DISKS_PATH", current_path)
    monkeypatch.setattr(disk_store, "SCAN_HISTORY_DIR", temp_dir / "scan_history")

    manager = DiskStore()

    assert manager.get_current_disks() == []
    assert read_json(current_path) == []


def test_save_scan_result_updates_current_disks_and_writes_history(store, temp_dir):
    disks = [
        {"id": "existing-id", "slot": 1, "set_name": "Polar", "inventory_pos": 12},
        {"slot": 2, "set_name": "Swing", "inventory_pos": 13},
    ]
    saved = store.save_scan_result(disks, source="scanner", logs=["ok"], scan_id="20260518-121314-abcd")

    current = read_json(temp_dir / "disks.json")
    history = read_json(temp_dir / "scan_history" / "20260518-121314-abcd.json")

    assert saved["scan_id"] == "20260518-121314-abcd"
    assert saved["source"] == "scanner"
    assert saved["logs"] == ["ok"]
    assert current == saved["disks"]
    assert history == saved
    assert saved["summary"] == {
        "slot_counts": {"1": 1, "2": 1},
        "set_counts": {"Polar": 1, "Swing": 1},
    }


def test_save_scan_result_rejects_duplicate_scan_id_without_overwriting_history(store, temp_dir):
    first = store.save_scan_result([{"slot": 1}], source="first", logs=["old"], scan_id="20260518-121323-9999")
    history_path = temp_dir / "scan_history" / "20260518-121323-9999.json"

    with pytest.raises(FileExistsError):
        store.save_scan_result([{"slot": 2}], source="second", logs=["new"], scan_id="20260518-121323-9999")

    assert read_json(history_path) == first


def test_save_scan_result_rolls_back_current_when_history_write_fails(store, temp_dir, monkeypatch):
    old_current = store.save_current_disks([{"id": "old", "slot": 1}])
    original_atomic_write = store._atomic_write

    def fail_history_write(path, data):
        if path.name.endswith(".json") and path.parent == store.scan_history_dir:
            raise OSError("history write failed")
        original_atomic_write(path, data)

    monkeypatch.setattr(store, "_atomic_write", fail_history_write)

    with pytest.raises(OSError, match="history write failed"):
        store.save_scan_result([{"slot": 2}], source="unit", logs=[], scan_id="20260518-121324-aaaa")

    assert store.get_current_disks() == old_current
    assert read_json(temp_dir / "disks.json") == old_current
    assert not (temp_dir / "scan_history" / "20260518-121324-aaaa.json").exists()


def test_save_scan_result_does_not_create_history_when_current_write_fails(store, temp_dir, monkeypatch):
    original_atomic_write = store._atomic_write

    def fail_current_write(path, data):
        if path == store.current_disks_path:
            raise OSError("current write failed")
        original_atomic_write(path, data)

    monkeypatch.setattr(store, "_atomic_write", fail_current_write)

    with pytest.raises(OSError, match="current write failed"):
        store.save_scan_result([{"slot": 2}], source="unit", logs=[], scan_id="20260518-121325-bbbb")

    assert not (temp_dir / "scan_history" / "20260518-121325-bbbb.json").exists()


def test_saved_disks_keep_or_add_id_scan_meta_and_inventory_pos(store):
    saved = store.save_scan_result(
        [
            {"id": "kept", "slot": 4, "inventory_pos": 7},
            {"slot": 5, "inventory_pos": 8},
        ],
        source="unit",
        logs=[],
        scan_id="20260518-121315-a1b2",
    )

    first, second = saved["disks"]
    assert first["id"] == "kept"
    assert second["id"]
    assert second["id"] != "kept"
    assert first["inventory_pos"] == 7
    assert second["inventory_pos"] == 8
    assert first["scan_meta"]["scan_id"] == "20260518-121315-a1b2"
    assert second["scan_meta"]["scan_id"] == "20260518-121315-a1b2"
    assert first["scan_meta"]["scanned_at"] == saved["scanned_at"]
    assert second["scan_meta"]["scanned_at"] == saved["scanned_at"]


def test_list_scan_history_returns_summaries_without_disks_in_reverse_time(store):
    store.save_scan_result([{"slot": 1}], source="older", logs=[], scan_id="20260518-121315-1111")
    store.save_scan_result([{"slot": 2}, {"slot": 2}], source="newer", logs=[], scan_id="20260518-121316-2222")

    history = store.list_scan_history()

    assert [item["scan_id"] for item in history] == ["20260518-121316-2222", "20260518-121315-1111"]
    assert all("disks" not in item for item in history)
    assert history[0]["summary"]["slot_counts"] == {"2": 2}
    assert history[0]["disk_count"] == 2


def test_get_scan_result_returns_full_record(store):
    saved = store.save_scan_result([{"slot": 3, "set_name": "Wood"}], source="unit", logs=["log"], scan_id="20260518-121317-3333")

    result = store.get_scan_result("20260518-121317-3333")

    assert result == saved
    result["disks"][0]["slot"] = 99
    assert store.get_scan_result("20260518-121317-3333")["disks"][0]["slot"] == 3


def test_use_scan_result_sets_history_disks_as_current_pool(store):
    store.save_scan_result([{"slot": 1}], source="old", logs=[], scan_id="20260518-121318-4444")
    saved = store.save_scan_result([{"slot": 6, "inventory_pos": 2}], source="chosen", logs=[], scan_id="20260518-121319-5555")
    store.save_current_disks([{"slot": 99}])

    current = store.use_scan_result("20260518-121319-5555")

    assert current == saved["disks"]
    assert store.get_current_disks() == saved["disks"]


def test_delete_scan_result_removes_one_history_item_and_missing_returns_false(store):
    store.save_scan_result([{"slot": 1}], source="unit", logs=[], scan_id="20260518-121320-6666")
    store.save_scan_result([{"slot": 2}], source="unit", logs=[], scan_id="20260518-121321-7777")

    assert store.delete_scan_result("20260518-121320-6666") is True
    assert store.delete_scan_result("20260518-121320-6666") is False
    assert [item["scan_id"] for item in store.list_scan_history()] == ["20260518-121321-7777"]


@pytest.mark.parametrize("method_name", ["get_scan_result", "delete_scan_result", "use_scan_result"])
def test_invalid_scan_id_raises_value_error(store, method_name):
    with pytest.raises(ValueError, match="invalid scan_id"):
        getattr(store, method_name)("../bad")


def test_save_scan_result_rejects_invalid_scan_id(store):
    with pytest.raises(ValueError, match="invalid scan_id"):
        store.save_scan_result([], source="unit", logs=[], scan_id="../bad")


def test_corrupt_current_disks_json_raises_clear_value_error(temp_dir, monkeypatch):
    current_path = temp_dir / "disks.json"
    current_path.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(disk_store, "CURRENT_DISKS_PATH", current_path)
    monkeypatch.setattr(disk_store, "SCAN_HISTORY_DIR", temp_dir / "scan_history")

    with pytest.raises(ValueError, match="Failed to read current disks JSON"):
        DiskStore()


def test_corrupt_history_json_raises_clear_value_error(store, temp_dir):
    history_path = temp_dir / "scan_history" / "20260518-121322-8888.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to read scan history JSON"):
        store.list_scan_history()

    with pytest.raises(ValueError, match="Failed to read scan history JSON"):
        store.get_scan_result("20260518-121322-8888")
