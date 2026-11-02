"""core.robot_config 的离线单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.config import PANEL_ITEM_DESC_MAX, PANEL_ITEM_NAME_MAX, PANEL_MAX_ITEMS
from core.i18n import Translator
from core.robot_config import (
    ROBOT_CONFIG_FILENAME,
    RobotConfigError,
    build_runtime_robots,
    empty_robot_config,
    export_robot_config,
    get_runtime_robots,
    legacy_to_robot_drafts,
    load_robot_config,
    save_robot_config,
    validate_robot_config,
)


def make_scenes(
    *,
    enabled_scenes: tuple[str, ...] = ("c2c",),
    items: list[dict[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    panel_items = items if items is not None else [{"name": "help", "desc": "查看帮助"}]
    scenes: dict[str, dict[str, Any]] = {}
    for scene in ("c2c", "group", "channel", "dm"):
        enabled = scene in enabled_scenes
        scenes[scene] = {
            "enabled": enabled,
            "items": [dict(item) for item in panel_items] if enabled else [],
        }
    return scenes


def make_robot(
    *,
    appid: str = "1023456789",
    name: str = "测试机器人",
    secret: str = "plain-secret-value",
    platform: str = "qq_official",
    robot_id: str = "robot-id-1",
    scenes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": robot_id,
        "name": name,
        "appid": appid,
        "secret": secret,
        "platform": platform,
        "scenes": scenes if scenes is not None else make_scenes(),
    }


def make_legacy_config(
    *,
    appid: str = "legacy-appid",
    name: str = "旧机器人",
    scenes: list[str] | None = None,
    commands: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "scenes": ["c2c", "group"] if scenes is None else scenes,
        "qq_platforms": [
            {"name": name, "appid": appid, "secret": "legacy-secret", "platform": "qq_official"}
        ],
        "selected_commands": ([{"name": "help", "desc": "帮助"}] if commands is None else commands),
    }


def assert_invalid(payload: Any, *fragments: str) -> None:
    normalized, errors = validate_robot_config(empty_robot_config(), payload)
    assert normalized == empty_robot_config(), errors
    assert any(all(fragment in error for fragment in fragments) for error in errors), errors


# 加载 / 保存


def test_empty_robot_config_shape() -> None:
    assert empty_robot_config() == {"version": 1, "robots": []}


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_robot_config(tmp_path) == {"version": 1, "robots": []}


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    payload = {"version": 1, "robots": [make_robot()]}

    target = save_robot_config(tmp_path, payload)

    assert target == tmp_path / ROBOT_CONFIG_FILENAME
    assert load_robot_config(tmp_path) == payload


def test_save_creates_missing_directories(tmp_path: Path) -> None:
    data_dir = tmp_path / "nested" / "plugin_data"

    save_robot_config(data_dir, empty_robot_config())

    assert (data_dir / ROBOT_CONFIG_FILENAME).is_file()


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    save_robot_config(tmp_path, {"version": 1, "robots": []})

    leftovers = [path.name for path in tmp_path.iterdir() if path.name.endswith(".tmp")]
    assert leftovers == []


@pytest.mark.parametrize(
    "raw",
    [
        b"{not-json",
        b"[]",
        b"\xff\xfe",
        b'{"version": 0}',
        b'{"version": 1, "robots": {}}',
        json.dumps({"version": 1, "robots": [make_robot()]})[:-1].encode(),
    ],
    ids=["corrupt", "non-object", "invalid-utf8", "bad-version", "bad-robots", "truncated"],
)
def test_load_rejects_invalid_file_without_touching_it(tmp_path: Path, raw: bytes) -> None:
    """损坏或结构非法的文件绝不能变成空配置，否则后续保存会覆盖用户数据。"""
    path = tmp_path / ROBOT_CONFIG_FILENAME
    path.write_bytes(raw)
    before = path.read_bytes()

    with pytest.raises(RobotConfigError):
        load_robot_config(tmp_path)

    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "robots",
    [
        ["bad"],
        [make_robot(appid=123)],  # type: ignore[arg-type]
        [make_robot(scenes="bad")],  # type: ignore[arg-type]
        [make_robot(scenes={**make_scenes(), "c2c": {"enabled": True, "items": "bad"}})],
        [make_robot(scenes={**make_scenes(), "group": "bad"})],
        [make_robot(scenes={**make_scenes(), "other": {"enabled": False, "items": []}})],
    ],
)
def test_load_rejects_invalid_nested_robot_config(
    tmp_path: Path,
    robots: list[Any],
) -> None:
    path = tmp_path / ROBOT_CONFIG_FILENAME
    path.write_text(json.dumps({"version": 1, "robots": robots}), encoding="utf-8")

    with pytest.raises(RobotConfigError):
        load_robot_config(tmp_path)

    assert path.is_file()


def test_load_rejects_duplicate_appid(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "robots": [
            make_robot(appid="same-appid", robot_id="r1"),
            make_robot(appid="same-appid", robot_id="r2"),
        ],
    }
    (tmp_path / ROBOT_CONFIG_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(RobotConfigError, match="same-appid.*重复"):
        load_robot_config(tmp_path)


def test_load_normalizes_secret_and_preserves_existing_version(tmp_path: Path) -> None:
    payload = {"version": 7, "robots": [make_robot(secret="  plain-secret-value  ")]}
    (tmp_path / ROBOT_CONFIG_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_robot_config(tmp_path)

    assert loaded["version"] == 7
    assert loaded["robots"][0]["secret"] == "plain-secret-value"


def test_load_wraps_directory_check_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """检查配置是否存在时也可能因权限不足抛 OSError，同样要包装成 RobotConfigError。"""

    def fail(_path: Path) -> bool:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "exists", fail)

    with pytest.raises(RobotConfigError) as excinfo:
        load_robot_config(tmp_path)

    assert isinstance(excinfo.value.__cause__, OSError)


# 校验


def test_validate_accepts_valid_payload() -> None:
    payload = {"version": 1, "robots": [make_robot()]}

    normalized, errors = validate_robot_config(empty_robot_config(), payload)

    assert errors == []
    assert normalized["version"] == 1
    assert normalized["robots"][0]["appid"] == "1023456789"
    assert normalized["robots"][0]["secret"] == "plain-secret-value"


def test_validate_generates_id_when_missing() -> None:
    robot = make_robot(robot_id="")
    robot.pop("id")

    normalized, errors = validate_robot_config(empty_robot_config(), {"robots": [robot]})

    assert errors == []
    robot_id = normalized["robots"][0]["id"]
    assert isinstance(robot_id, str)
    assert len(robot_id) == 36


def test_validate_rejects_duplicate_appid() -> None:
    assert_invalid(
        {
            "robots": [
                make_robot(appid="same-appid", robot_id="r1"),
                make_robot(appid="same-appid", robot_id="r2"),
            ]
        },
        "重复",
    )


def test_validate_rejects_non_string_appid() -> None:
    assert_invalid({"robots": [make_robot(appid=123)]}, "appid")


def test_validate_rejects_duplicate_robot_id() -> None:
    assert_invalid(
        {
            "robots": [
                make_robot(appid="app-1", robot_id="same-id"),
                make_robot(appid="app-2", robot_id="same-id"),
            ]
        },
        ".id",
        "重复",
    )


def test_validate_rejects_invalid_platform() -> None:
    assert_invalid({"robots": [make_robot(platform="aiocqhttp")]}, "platform")


def test_validate_rejects_invalid_robot_name() -> None:
    assert_invalid({"robots": [make_robot(name="名" * 15)]}, "name", "14")
    assert_invalid({"robots": [make_robot(name="   ")]}, "name")


def test_validate_rejects_enabled_scene_without_items() -> None:
    scenes = make_scenes()
    scenes["c2c"] = {"enabled": True, "items": []}
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "启用", "至少")


def test_validate_allows_disabled_scene_without_items() -> None:
    scenes = make_scenes(enabled_scenes=())
    scenes["c2c"] = {"enabled": False, "items": []}

    normalized, errors = validate_robot_config(
        empty_robot_config(), {"robots": [make_robot(scenes=scenes)]}
    )

    assert errors == []
    assert normalized["robots"][0]["scenes"]["c2c"]["enabled"] is False


def test_validate_rejects_too_many_items_per_scene() -> None:
    items = [{"name": f"cmd{i}", "desc": ""} for i in range(PANEL_MAX_ITEMS + 1)]
    assert_invalid({"robots": [make_robot(scenes=make_scenes(items=items))]}, str(PANEL_MAX_ITEMS))


def test_validate_rejects_oversized_item_fields() -> None:
    name_too_long = [{"name": "n" * (PANEL_ITEM_NAME_MAX + 1), "desc": "ok"}]
    desc_too_long = [{"name": "ok", "desc": "d" * (PANEL_ITEM_DESC_MAX + 1)}]
    assert_invalid(
        {"robots": [make_robot(scenes=make_scenes(items=name_too_long))]},
        str(PANEL_ITEM_NAME_MAX),
    )
    assert_invalid(
        {"robots": [make_robot(scenes=make_scenes(items=desc_too_long))]},
        str(PANEL_ITEM_DESC_MAX),
    )


def test_validate_rejects_empty_item_name() -> None:
    items = [{"name": "  ", "desc": "ok"}]
    assert_invalid({"robots": [make_robot(scenes=make_scenes(items=items))]}, "name", "不能为空")


def test_validate_rejects_non_list_items() -> None:
    scenes = make_scenes()
    scenes["c2c"] = {"enabled": False, "items": "bad"}
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "items", "列表")


def test_validate_rejects_unknown_scene() -> None:
    scenes = {**make_scenes(), "other": {"enabled": False, "items": []}}
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "scenes.other", "不支持")


def test_validate_does_not_silently_truncate() -> None:
    items = [{"name": "n" * (PANEL_ITEM_NAME_MAX + 1), "desc": "d" * (PANEL_ITEM_DESC_MAX + 1)}]
    assert_invalid({"robots": [make_robot(scenes=make_scenes(items=items))]}, "name")


# secret：导出掩码与沿用原值


def test_export_masks_secret_and_marks_set() -> None:
    robot = export_robot_config({"version": 1, "robots": [make_robot()]})["robots"][0]
    assert "secret" not in robot
    assert robot["secret_masked"] == "pla*************ue"
    assert robot["secret_set"] is True

    empty = export_robot_config({"version": 1, "robots": [make_robot(secret="")]})
    assert empty["robots"][0]["secret_masked"] == ""
    assert empty["robots"][0]["secret_set"] is False


def test_validate_keeps_existing_secret_on_empty_submission() -> None:
    existing = {"version": 1, "robots": [make_robot()]}
    submitted = make_robot(secret="")

    normalized, errors = validate_robot_config(existing, {"robots": [submitted]})

    assert errors == []
    assert normalized["robots"][0]["secret"] == "plain-secret-value"


def test_validate_rejects_missing_or_non_string_secret() -> None:
    assert_invalid({"robots": [make_robot(secret="")]}, "secret")
    assert_invalid({"robots": [make_robot(secret=123)]}, "secret", "字符串")


# 新旧合并 / legacy 转换


def test_build_runtime_v2_wins_on_same_appid() -> None:
    legacy = make_legacy_config(appid="shared-appid")
    legacy["scenes"] = ["group"]
    legacy["selected_commands"] = [{"name": "legacy", "desc": "旧"}]
    robot_config = {"robots": [make_robot(appid="shared-appid")]}

    runtime = build_runtime_robots(legacy, robot_config)

    assert len(runtime) == 1
    robot = runtime[0]
    assert robot["source"] == "v2"
    assert robot["scenes"]["c2c"] == [{"name": "help", "desc": "查看帮助"}]
    assert robot["scenes"]["group"] == []


def test_build_runtime_v2_wins_when_legacy_appid_has_whitespace() -> None:
    legacy = make_legacy_config(appid="  shared-appid  ")
    robot_config = {"robots": [make_robot(appid="shared-appid")]}

    runtime = build_runtime_robots(legacy, robot_config)

    assert len(runtime) == 1
    assert runtime[0]["source"] == "v2"
    assert runtime[0]["appid"] == "shared-appid"


def test_build_runtime_keeps_unmatched_legacy_robot() -> None:
    legacy = make_legacy_config(appid="legacy-only")
    robot_config = {"robots": [make_robot(appid="v2-only")]}

    runtime = build_runtime_robots(legacy, robot_config)

    assert {robot["appid"] for robot in runtime} == {"v2-only", "legacy-only"}
    legacy_robot = next(robot for robot in runtime if robot["source"] == "legacy")
    assert legacy_robot["scenes"]["c2c"] == [{"name": "help", "desc": "帮助"}]
    assert legacy_robot["scenes"]["group"] == [{"name": "help", "desc": "帮助"}]
    assert legacy_robot["scenes"]["channel"] == []


def test_build_runtime_keeps_legacy_robots_sharing_a_name() -> None:
    legacy = make_legacy_config(appid="legacy-a", name="bot")
    legacy["qq_platforms"].append(
        {"name": "bot", "appid": "legacy-b", "secret": "secret-b", "platform": "qq_official"}
    )

    runtime = build_runtime_robots(legacy, {"robots": []})

    assert [(robot["id"], robot["appid"], robot["name"]) for robot in runtime] == [
        ("legacy-a", "legacy-a", "bot"),
        ("legacy-b", "legacy-b", "bot"),
    ]


def test_build_runtime_rejects_duplicate_robot_ids() -> None:
    robot_config = {
        "robots": [
            make_robot(appid="app-1", robot_id="same-id"),
            make_robot(appid="app-2", robot_id="same-id"),
        ]
    }

    with pytest.raises(RobotConfigError, match="id 重复"):
        build_runtime_robots({}, robot_config)


def test_build_runtime_rejects_duplicate_appids() -> None:
    robot_config = {
        "robots": [
            make_robot(appid="same-appid", robot_id="r1"),
            make_robot(appid="same-appid", robot_id="r2"),
        ]
    }

    with pytest.raises(RobotConfigError, match="AppID 重复"):
        build_runtime_robots({}, robot_config)


def test_get_runtime_robots_only_keeps_enabled_scenes() -> None:
    robot = make_robot(scenes=make_scenes(enabled_scenes=("group",)))

    runtime = get_runtime_robots({"robots": [robot]})

    assert runtime[0]["source"] == "v2"
    assert runtime[0]["scenes"]["group"] == [{"name": "help", "desc": "查看帮助"}]
    assert runtime[0]["scenes"]["c2c"] == []


def test_legacy_to_robot_drafts_replicates_commands_and_secret() -> None:
    legacy = make_legacy_config(scenes=["c2c", "channel"])

    drafts = legacy_to_robot_drafts(legacy)

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["appid"] == "legacy-appid"
    assert draft["secret"] == "legacy-secret"
    assert draft["platform"] == "qq_official"
    assert draft["scenes"]["c2c"]["enabled"] is True
    assert draft["scenes"]["group"]["enabled"] is False
    assert draft["scenes"]["channel"]["items"] == [{"name": "help", "desc": "帮助"}]
    assert draft["scenes"]["dm"]["items"] == []


@pytest.mark.parametrize("name", ["", "   "])
def test_legacy_to_robot_drafts_falls_back_to_masked_appid(name: str) -> None:
    drafts = legacy_to_robot_drafts(make_legacy_config(appid="1023456789", name=name))

    assert drafts[0]["name"] == "102*****89"


def test_legacy_to_robot_drafts_falls_back_when_name_is_omitted() -> None:
    legacy = {
        "qq_platforms": [{"appid": "1023456789", "secret": "legacy-secret"}],
    }

    drafts = legacy_to_robot_drafts(legacy)

    assert drafts[0]["name"] == "102*****89"


def test_legacy_to_robot_drafts_truncates_overlong_name() -> None:
    drafts = legacy_to_robot_drafts(make_legacy_config(name=f" {'名' * 15} "))

    assert drafts[0]["name"] == "名" * PANEL_ITEM_NAME_MAX
    assert len(drafts[0]["name"]) == PANEL_ITEM_NAME_MAX


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (f"{'a' * (PANEL_ITEM_NAME_MAX - 1)}😀后缀", "a" * (PANEL_ITEM_NAME_MAX - 1)),
        ("😀" * (PANEL_ITEM_NAME_MAX // 2), "😀" * (PANEL_ITEM_NAME_MAX // 2)),
    ],
)
def test_legacy_to_robot_drafts_truncates_by_utf16_units(name: str, expected: str) -> None:
    drafts = legacy_to_robot_drafts(make_legacy_config(name=name))

    assert drafts[0]["name"] == expected
    assert len(drafts[0]["name"].encode("utf-16-le")) // 2 <= PANEL_ITEM_NAME_MAX


@pytest.mark.parametrize("name", ["", f"{'名' * PANEL_ITEM_NAME_MAX}超长"])
def test_legacy_drafts_with_optional_names_can_be_validated_into_v2(name: str) -> None:
    drafts = legacy_to_robot_drafts(make_legacy_config(name=name))

    _normalized, errors = validate_robot_config(empty_robot_config(), {"robots": drafts})

    assert errors == []


def test_legacy_drafts_can_be_validated_into_v2() -> None:
    drafts = legacy_to_robot_drafts(make_legacy_config())

    normalized, errors = validate_robot_config(empty_robot_config(), {"robots": drafts})

    assert errors == []
    assert normalized["robots"][0]["secret"] == "legacy-secret"


def test_validate_rejects_non_dict_payload() -> None:
    assert_invalid(["not-a-dict"], "payload")


def test_validate_rejects_missing_scene_key() -> None:
    scenes = make_scenes()
    scenes.pop("dm")
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "dm")


def test_validate_rejects_non_bool_enabled() -> None:
    scenes = make_scenes(enabled_scenes=())
    scenes["c2c"] = {"enabled": "yes", "items": []}
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "enabled", "布尔")


def test_validate_rejects_blank_secret_for_new_robot() -> None:
    assert_invalid({"robots": [make_robot(secret="   ")]}, "secret")


def test_export_does_not_leak_plaintext_secret() -> None:
    exported = export_robot_config({"version": 1, "robots": [make_robot()]})

    assert "plain-secret-value" not in json.dumps(exported, ensure_ascii=False)


def test_validation_errors_follow_selected_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.i18n as i18n_module

    monkeypatch.setattr(i18n_module, "_instance", Translator(Path("core/i18n"), "ru-RU"))

    _normalized, errors = validate_robot_config(
        empty_robot_config(),
        {"robots": [make_robot(appid="")]},
    )

    assert errors == ["robots[0].appid: значение не может быть пустым"]


def test_save_failure_raises_robot_config_error(tmp_path: Path) -> None:
    (tmp_path / ROBOT_CONFIG_FILENAME).mkdir()

    with pytest.raises(RobotConfigError):
        save_robot_config(tmp_path, empty_robot_config())


def test_save_wraps_directory_creation_failure(tmp_path: Path) -> None:
    """数据目录本身无法创建时也要包装成 RobotConfigError，不能漏出原始 OSError。"""
    data_dir = tmp_path / "data"
    data_dir.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RobotConfigError) as excinfo:
        save_robot_config(data_dir, empty_robot_config())

    assert isinstance(excinfo.value.__cause__, OSError)


def test_save_wraps_serialization_failure(tmp_path: Path) -> None:
    """载荷无法 JSON 序列化时同样返回 RobotConfigError，而不是 TypeError。"""

    with pytest.raises(RobotConfigError) as excinfo:
        save_robot_config(tmp_path, {"version": 1, "robots": [object()]})

    assert isinstance(excinfo.value.__cause__, TypeError)


def test_save_wraps_encoding_failure(tmp_path: Path) -> None:
    """孤立代理字符无法按 UTF-8 写入，保存失败也要包装成 RobotConfigError。"""

    with pytest.raises(RobotConfigError) as excinfo:
        save_robot_config(
            tmp_path,
            {"version": 1, "robots": [{"name": "\ud800"}]},
        )

    assert isinstance(excinfo.value.__cause__, UnicodeEncodeError)


def test_validate_rejects_non_list_robots() -> None:
    _normalized, errors = validate_robot_config(empty_robot_config(), {"robots": "bad"})

    assert errors == ["robots：必须是列表"]


def test_validate_rejects_missing_robots() -> None:
    normalized, errors = validate_robot_config(empty_robot_config(), {})

    assert normalized == empty_robot_config()
    assert errors == ["robots：必须显式传入列表"]


def test_validate_accepts_explicit_empty_robots() -> None:
    normalized, errors = validate_robot_config(empty_robot_config(), {"robots": []})

    assert errors == []
    assert normalized["robots"] == []


def test_validate_rejects_non_dict_robot_entry() -> None:
    _normalized, errors = validate_robot_config(empty_robot_config(), {"robots": ["bad"]})

    assert errors == ["robots[0]：必须是对象"]


def test_validate_rejects_non_dict_scenes_and_scene() -> None:
    assert_invalid({"robots": [make_robot(scenes="bad")]}, "scenes")
    scenes = make_scenes()
    scenes["c2c"] = "bad"  # type: ignore[assignment]
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "scenes.c2c")


def test_validate_rejects_non_dict_item_and_non_string_desc() -> None:
    scenes = make_scenes()
    scenes["c2c"]["items"] = ["bad", {"name": "help", "desc": 123}]
    payload = {"robots": [make_robot(scenes=scenes)]}
    assert_invalid(payload, "items[0]")
    assert_invalid(payload, "items[1].desc")


def test_validate_rejects_desc_too_long() -> None:
    scenes = make_scenes(items=[{"name": "help", "desc": "x" * (PANEL_ITEM_DESC_MAX + 1)}])
    assert_invalid({"robots": [make_robot(scenes=scenes)]}, "desc")


def test_validate_accepts_none_desc() -> None:
    scenes = make_scenes()
    scenes["c2c"]["items"] = [{"name": "help", "desc": None}]

    normalized, errors = validate_robot_config(
        empty_robot_config(),
        {"robots": [make_robot(scenes=scenes)]},
    )

    assert errors == []
    assert normalized["robots"][0]["scenes"]["c2c"]["items"][0]["desc"] == ""


def test_validate_ignores_invalid_entries_when_reusing_secret() -> None:
    existing = {
        "robots": [
            "bad",
            {"appid": "a", "secret": ""},
            {"appid": "a", "secret": "kept-secret"},
        ]
    }

    normalized, errors = validate_robot_config(
        existing,
        {"robots": [make_robot(appid="a", secret="")]},
    )

    assert errors == []
    assert normalized["robots"][0]["secret"] == "kept-secret"


def test_export_handles_invalid_shapes() -> None:
    assert export_robot_config({"robots": "bad"}) == empty_robot_config()

    exported = export_robot_config(
        {
            "version": 0,
            "robots": [
                "bad",
                {"appid": ""},
                {"appid": "a", "scenes": "bad"},
            ],
        }
    )

    assert exported["version"] == 1
    assert len(exported["robots"]) == 1
    assert exported["robots"][0]["appid"] == "a"
    assert exported["robots"][0]["scenes"] == {}


def test_get_runtime_robots_handles_invalid_shapes() -> None:
    assert get_runtime_robots({"robots": "bad"}) == []

    runtime = get_runtime_robots(
        {
            "robots": [
                "bad",
                {"appid": ""},
                {
                    "appid": "a",
                    "scenes": {
                        "c2c": {"enabled": True, "items": "bad"},
                        "group": {
                            "enabled": True,
                            "items": [{"name": ""}, {"name": "ok", "desc": "d"}],
                        },
                    },
                },
            ]
        }
    )

    assert len(runtime) == 1
    assert runtime[0]["scenes"]["c2c"] == []
    assert runtime[0]["scenes"]["group"] == [{"name": "ok", "desc": "d"}]

    no_scenes = get_runtime_robots({"robots": [{"appid": "a", "scenes": "bad"}]})
    assert no_scenes[0]["scenes"] == {scene: [] for scene in ("c2c", "group", "channel", "dm")}
