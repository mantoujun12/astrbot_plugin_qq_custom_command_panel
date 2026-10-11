"""core.config 的单元测试 (纯函数, 无 IO)"""

from __future__ import annotations

from typing import Any

from core.config import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    get_configured_platforms,
    get_enabled_scenes,
    get_platforms_from_context,
    get_platforms_from_schema,
    get_selected_commands,
)

# ---------------------------------------------------------------------------
# get_enabled_scenes
# ---------------------------------------------------------------------------


def test_get_enabled_scenes_default_when_missing() -> None:
    assert get_enabled_scenes({}) == DEFAULT_SCENES


def test_get_enabled_scenes_filters_invalid() -> None:
    config: dict[str, Any] = {"scenes": ["c2c", "hacker", 123, None, "group"]}
    assert get_enabled_scenes(config) == ["c2c", "group"]


def test_get_enabled_scenes_non_list_falls_back() -> None:
    assert get_enabled_scenes({"scenes": "c2c"}) == DEFAULT_SCENES
    assert get_enabled_scenes({"scenes": {"c2c": True}}) == DEFAULT_SCENES


# ---------------------------------------------------------------------------
# get_selected_commands
# ---------------------------------------------------------------------------


def test_get_selected_commands_truncates() -> None:
    config = {
        "selected_commands": [
            {"name": "n" * 30, "desc": "d" * 50},
        ]
    }
    items = get_selected_commands(config)
    assert len(items) == 1
    assert items[0]["name"] == "n" * PANEL_ITEM_NAME_MAX
    assert items[0]["desc"] == "d" * PANEL_ITEM_DESC_MAX
    assert items[0]["type"] == "command"


def test_get_selected_commands_skips_invalid_entries() -> None:
    config = {
        "selected_commands": [
            "not a dict",
            42,
            {"desc": "no name"},
            {"name": "", "desc": "empty name"},
            {"name": "ok", "desc": 123},  # desc 非字符串 → 置空
            {"name": "fine", "desc": "good"},
        ]
    }
    items = get_selected_commands(config)
    assert items == [
        {"name": "ok", "type": "command", "desc": ""},
        {"name": "fine", "type": "command", "desc": "good"},
    ]


def test_get_selected_commands_caps_at_max_items() -> None:
    config = {
        "selected_commands": [{"name": f"cmd{i}", "desc": "d"} for i in range(PANEL_MAX_ITEMS + 5)]
    }
    items = get_selected_commands(config)
    assert len(items) == PANEL_MAX_ITEMS


def test_get_selected_commands_non_list_returns_empty() -> None:
    assert get_selected_commands({"selected_commands": "oops"}) == []
    assert get_selected_commands({}) == []


# ---------------------------------------------------------------------------
# 平台解析: schema / context / fallback
# ---------------------------------------------------------------------------


def test_get_platforms_from_schema_basic() -> None:
    config = {
        "qq_platforms": [
            {"name": "小号", "appid": "111", "secret": "s1", "platform": "qq_official"},
        ]
    }
    platforms = get_platforms_from_schema(config)
    assert platforms == {
        "小号": {"appid": "111", "secret": "s1", "platform": "qq_official"},
    }


def test_get_platforms_from_schema_alias_and_defaults() -> None:
    config = {
        "qq_platforms": [
            # 无 name/platform → pf_id 取 appid, platform 归一化为 qq_official
            {"appid": "222", "secret": "s2", "platform": "qq"},
        ]
    }
    platforms = get_platforms_from_schema(config)
    assert platforms == {
        "222": {"appid": "222", "secret": "s2", "platform": "qq_official"},
    }


def test_get_platforms_from_schema_dedups_by_pf_id() -> None:
    config = {
        "qq_platforms": [
            {"name": "dup", "appid": "1", "secret": "s1"},
            {"name": "dup", "appid": "2", "secret": "s2"},
        ]
    }
    platforms = get_platforms_from_schema(config)
    # 同一 pf_id 只保留第一条
    assert len(platforms) == 1
    assert platforms["dup"]["appid"] == "1"


def test_get_platforms_from_schema_skips_incomplete() -> None:
    config = {
        "qq_platforms": [
            {"name": "no_secret", "appid": "1"},
            {"name": "no_appid", "secret": "s"},
            "not a dict",
            {"name": "unsupported", "appid": "1", "secret": "s", "platform": "aiocqhttp"},
        ]
    }
    assert get_platforms_from_schema(config) == {}


def test_get_platforms_from_context_platform_settings() -> None:
    context = SimpleNamespacePlatform(
        platform_settings=[
            {"enable": True, "type": "qq_official", "id": "ctx1", "appid": "a", "secret": "b"},
            {"enable": False, "type": "qq_official", "id": "ctx2", "appid": "c", "secret": "d"},
        ]
    )
    platforms = get_platforms_from_context(context)
    # enable=False 的平台被跳过
    assert platforms == {
        "ctx1": {"appid": "a", "secret": "b", "platform": "qq_official"},
    }


def test_get_platforms_from_context_via_config_dict() -> None:
    context = SimpleNamespacePlatform(
        astrbot_config={
            "platform_settings": [
                {"enable": True, "type": "qq_official_webhook", "appid": "w1", "secret": "ws"},
            ]
        }
    )
    platforms = get_platforms_from_context(context)
    assert platforms == {
        "w1": {"appid": "w1", "secret": "ws", "platform": "qq_official_webhook"},
    }


def test_get_platforms_from_context_empty_object() -> None:
    assert get_platforms_from_context(SimpleNamespacePlatform()) == {}
    assert get_platforms_from_context(None) == {}


def test_get_configured_platforms_prefers_schema() -> None:
    config = {
        "qq_platforms": [
            {"name": "schema_pf", "appid": "s_app", "secret": "s_sec"},
        ]
    }
    context = SimpleNamespacePlatform(
        platform_settings=[
            {
                "enable": True,
                "type": "qq_official",
                "id": "ctx_pf",
                "appid": "c_app",
                "secret": "c_sec",
            },
        ]
    )
    platforms, source = get_configured_platforms(config, context)
    assert source == "schema"
    assert list(platforms) == ["schema_pf"]


def test_get_configured_platforms_falls_back_to_context() -> None:
    context = SimpleNamespacePlatform(
        platform_settings=[
            {
                "enable": True,
                "type": "qq_official",
                "id": "ctx_pf",
                "appid": "c_app",
                "secret": "c_sec",
            },
        ]
    )
    platforms, source = get_configured_platforms({}, context)
    assert source == "context"
    assert list(platforms) == ["ctx_pf"]


def test_get_configured_platforms_none() -> None:
    platforms, source = get_configured_platforms({}, None)
    assert platforms == {}
    assert source == "none"


class SimpleNamespacePlatform:
    """模拟 AstrBot Context: 按 getattr 探测的属性容器"""

    def __init__(self, **attrs: Any) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


# 严谨起见确认常量值 (截断逻辑依赖它们)
def test_panel_limits_values() -> None:
    assert PANEL_ITEM_NAME_MAX == 14
    assert PANEL_ITEM_DESC_MAX == 30
    assert PANEL_MAX_ITEMS == 20
    assert DEFAULT_SCENES == ["c2c", "group"]
