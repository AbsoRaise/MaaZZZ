import shutil
import json
from pathlib import Path
from uuid import uuid4

import pytest

from backend.service.maa_scanner import MaaScanner


@pytest.fixture
def temp_dir():
    path = Path(__file__).parent / ".tmp_maa_scanner" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_run_scan_emits_progress_and_writes_debug(temp_dir):
    events = []
    scanner = MaaScanner(resource_root=temp_dir / "resources", debug_dir=temp_dir / "debug")

    disks, logs = scanner.run_scan(events.append)

    assert events[0]["progress"] == 5
    assert events[-1]["progress"] == 100
    assert len(disks) == 2
    assert logs[-1] == "Maa 占位扫描完成"
    assert (temp_dir / "debug" / "latest_result.json").exists()


def test_run_scan_uses_maaframework_runtime_when_enabled(temp_dir):
    events = []
    runtime = FakeMaaRuntime()
    scanner = MaaScanner(
        resource_root=temp_dir / "resources",
        debug_dir=temp_dir / "debug",
        maa_runtime=runtime,
    )
    profile = scanner.profile | {"maa": {"enabled": True, "controller": "dbg", "entry": "ScanDisks"}}
    scanner.profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    disks, logs = scanner.run_scan(events.append)

    assert disks == []
    assert runtime.calls == [
        ("connect", scanner.profile),
        ("run_task", "ScanDisks", scanner.profile),
    ]
    assert events[-1]["message"] == "MaaFramework 任务执行完成"
    assert logs[-1] == "MaaFramework 任务执行完成"


def test_run_scan_falls_back_when_maaframework_disabled(temp_dir):
    runtime = FakeMaaRuntime()
    scanner = MaaScanner(resource_root=temp_dir / "resources", maa_runtime=runtime)
    profile = scanner.profile | {"maa": {"enabled": False}}
    scanner.profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    disks, logs = scanner.run_scan()

    assert len(disks) == 2
    assert runtime.calls == []
    assert logs[-1] == "Maa 占位扫描完成"


def test_locate_disk_returns_page_and_click_coordinates(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources")

    result = scanner.locate_disk({"inventory_pos": {"page": 2, "row": 2, "column": 3}})

    assert result["supported"] is False
    assert result["target"] == {"page": 2, "row": 2, "column": 3, "x": 660, "y": 420}


def test_scan_from_screenshot_copies_file_to_debug_dir(temp_dir):
    image = temp_dir / "inventory.png"
    image.write_bytes(b"fake png")
    scanner = MaaScanner(resource_root=temp_dir / "resources", debug_dir=temp_dir / "debug")

    result = scanner.scan_from_screenshot(image)

    assert Path(result["debug_screenshot"]).read_bytes() == b"fake png"


def test_scan_from_screenshot_rejects_missing_file(temp_dir):
    scanner = MaaScanner(resource_root=temp_dir / "resources")

    with pytest.raises(FileNotFoundError):
        scanner.scan_from_screenshot(temp_dir / "missing.png")


class FakeMaaRuntime:
    def __init__(self):
        self.calls = []

    def connect(self, profile):
        self.calls.append(("connect", profile))
        return {"connected": True, "mode": "maa", "message": "connected"}

    def run_task(self, entry, profile):
        self.calls.append(("run_task", entry, profile))
        return {"completed": True}
