import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from backend.service.character_config_manager import CharacterConfigManager


ELLEN_NAME = "艾莲·乔"


@pytest.fixture
def temp_dir():
    path = Path(__file__).parent / ".tmp_character_config_manager" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_manager_creates_default_file_with_ellen_when_missing(temp_dir):
    path = temp_dir / "character_builds.json"

    manager = CharacterConfigManager(path)
    data = manager.get_all()

    assert ELLEN_NAME in data
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert ELLEN_NAME in saved


def test_save_character_build_persists_complete_config(temp_dir):
    path = temp_dir / "character_builds.json"
    manager = CharacterConfigManager(path)
    config = {
        "weights": {"暴击率": "1.2", "暴击伤害": 2},
        "preferred_main_stats": {"4": "暴击率", 5: ["冰属性伤害", ""], "6": ["攻击力"]},
        "preferred_sets": {
            "target_set_4": "极地重金属",
            "target_set_2": "啄木鸟电音",
            "alternatives": [{"target_set_4": "啄木鸟电音", "target_set_2": "极地重金属", "note": ""}],
        },
    }

    manager.save_character_build("测试角色", config)
    reloaded = CharacterConfigManager(path).get_character_build("测试角色")

    assert reloaded == {
        "weights": {"暴击率": 1.2, "暴击伤害": 2.0},
        "preferred_main_stats": {
            "4": ["暴击率"],
            "5": ["冰属性伤害"],
            "6": ["攻击力"],
        },
        "preferred_sets": {
            "target_set_4": "极地重金属",
            "target_set_2": "啄木鸟电音",
            "alternatives": [{"target_set_4": "啄木鸟电音", "target_set_2": "极地重金属", "note": ""}],
        },
    }


def test_save_character_build_normalizes_unserializable_alternatives(temp_dir):
    path = temp_dir / "character_builds.json"
    manager = CharacterConfigManager(path)

    saved = manager.save_character_build(
        "alternatives test",
        {
            "weights": {},
            "preferred_main_stats": {},
            "preferred_sets": {
                "target_set_4": "set-4",
                "target_set_2": "set-2",
                "alternatives": [
                    {
                        "target_set_4": "alt-4",
                        "target_set_2": "alt-2",
                        "note": {"unsafe"},
                        "extra": object(),
                    },
                    object(),
                    {"target_set_4": object(), "target_set_2": "safe"},
                ],
            },
        },
    )
    reloaded = CharacterConfigManager(path).get_character_build("alternatives test")

    assert saved["preferred_sets"]["alternatives"] == [
        {"target_set_4": "alt-4", "target_set_2": "alt-2", "note": ""},
        {"target_set_4": "", "target_set_2": "safe", "note": ""},
    ]
    assert reloaded == saved


def test_save_character_build_does_not_mutate_memory_when_write_fails(temp_dir):
    path = temp_dir / "character_builds.json"
    manager = CharacterConfigManager(path)
    before = manager.get_all()

    def fail_write(data):
        raise OSError("disk full")

    manager._atomic_write = fail_write

    with pytest.raises(OSError):
        manager.save_character_build(
            "should not persist",
            {
                "weights": {"x": 1},
                "preferred_main_stats": {},
                "preferred_sets": {},
            },
        )

    assert manager.get_all() == before
    assert CharacterConfigManager(path).get_all() == before


def test_two_managers_can_save_to_same_path_without_temp_collision(temp_dir):
    path = temp_dir / "character_builds.json"
    first = CharacterConfigManager(path)
    second = CharacterConfigManager(path)

    first.save_character_build(
        "first role",
        {"weights": {"a": 1}, "preferred_main_stats": {}, "preferred_sets": {}},
    )
    second.save_character_build(
        "second role",
        {"weights": {"b": 2}, "preferred_main_stats": {}, "preferred_sets": {}},
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "second role" in raw
    assert CharacterConfigManager(path).get_character_build("second role")["weights"] == {"b": 2.0}


def test_corrupt_json_is_backed_up_and_default_is_rebuilt(temp_dir):
    path = temp_dir / "character_builds.json"
    path.write_text("{bad json", encoding="utf-8")

    manager = CharacterConfigManager(path)

    assert ELLEN_NAME in manager.get_all()
    backups = list(temp_dir.glob("character_builds.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{bad json"
    rebuilt = json.loads(path.read_text(encoding="utf-8"))
    assert ELLEN_NAME in rebuilt


def test_update_weights_only_changes_weights_and_persists(temp_dir):
    path = temp_dir / "character_builds.json"
    manager = CharacterConfigManager(path)
    manager.save_character_build(
        "测试角色",
        {
            "weights": {"暴击率": 1},
            "preferred_main_stats": {"4": ["暴击率"]},
            "preferred_sets": {"target_set_4": "极地重金属", "target_set_2": "啄木鸟电音"},
        },
    )

    updated = manager.update_weights(
        "测试角色",
        {"暴击率": "2.5", "坏值": object(), "": 1, None: 3},
    )
    reloaded = CharacterConfigManager(path).get_character_build("测试角色")

    assert updated["weights"] == {"暴击率": 2.5, "坏值": 0.0}
    assert reloaded["weights"] == {"暴击率": 2.5, "坏值": 0.0}
    assert reloaded["preferred_main_stats"] == {"4": ["暴击率"]}
    assert reloaded["preferred_sets"] == {
        "target_set_4": "极地重金属",
        "target_set_2": "啄木鸟电音",
        "alternatives": [],
    }


@pytest.mark.parametrize("character_name", ["", "   ", None])
def test_empty_character_name_raises_value_error(temp_dir, character_name):
    manager = CharacterConfigManager(temp_dir / "character_builds.json")

    with pytest.raises(ValueError):
        manager.save_character_build(character_name, {})


def test_returned_data_is_deep_copied(temp_dir):
    manager = CharacterConfigManager(temp_dir / "character_builds.json")
    data = manager.get_all()
    data[ELLEN_NAME]["weights"]["暴击率"] = 999

    fresh = manager.get_all()

    assert fresh[ELLEN_NAME]["weights"].get("暴击率") != 999
