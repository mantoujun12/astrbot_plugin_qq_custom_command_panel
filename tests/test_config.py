"""core.config 的单元测试（纯函数，不做任何 IO）"""

from __future__ import annotations

from typing import Any

from core.config import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    SCENES,
    export_config,
    get_configured_platforms,
    get_enabled_scenes,
    get_platform_entries,
    get_platforms_from_schema,
    get_selected_commands,
    mask_secret,
    normalize_config_payload,
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
            {"name": "ok", "desc": 123},  # desc 非字符串 → 该条变空描述
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
# 平台配置读取：只有 schema qq_platforms 一个来源
# ---------------------------------------------------------------------------


def test_get_platform_entries_keeps_name_and_defaults() -> None:
    config = {
        "qq_platforms": [
            {"appid": "222", "secret": "s2", "platform": "qq"},
        ]
    }
    entries = get_platform_entries(config)
    # 没填 name/platform 时 pf_id 取 appid，platform 归一成 qq_official
    assert entries == [
        {
            "pf_id": "222",
            "name": "",
            "appid": "222",
            "secret": "s2",
            "platform": "qq_official",
        }
    ]


def test_get_platforms_from_schema_basic() -> None:
    config = {
        "qq_platforms": [
            {"name": "小号", "appid": "111", "secret": "s1", "platform": "qq_official"},
        ]
    }
    assert get_platforms_from_schema(config) == {
        "小号": {"appid": "111", "secret": "s1", "platform": "qq_official"},
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


def test_get_configured_platforms_reads_schema_only() -> None:
    config = {
        "qq_platforms": [
            {"name": "schema_pf", "appid": "s_app", "secret": "s_sec"},
        ]
    }
    platforms = get_configured_platforms(config)
    assert list(platforms) == ["schema_pf"]
    assert platforms["schema_pf"]["appid"] == "s_app"


def test_get_configured_platforms_empty_without_qq_platforms() -> None:
    # 插件读不到平台适配器的机器人信息，没有 qq_platforms 就是没有平台
    assert get_configured_platforms({}) == {}
    assert get_configured_platforms({"qq_platforms": []}) == {}


# ---------------------------------------------------------------------------
# mask_secret / export_config
# ---------------------------------------------------------------------------


def test_mask_secret_keeps_head_and_tail() -> None:
    assert mask_secret("abcdefghij") == "abc*****ij"


def test_mask_secret_short_and_empty() -> None:
    assert mask_secret("abc") == "***"
    assert mask_secret(None) == ""
    assert mask_secret("") == ""


def test_export_config_never_leaks_secret() -> None:
    config = {
        "language": "en-US",
        "scenes": ["c2c"],
        "qq_platforms": [
            {"name": "pf1", "appid": "1023456789", "secret": "super-secret-value"},
        ],
        "selected_commands": [{"name": "help", "desc": "说明"}],
    }
    exported = export_config(config)

    assert exported["language"] == "en-US"
    assert exported["scenes"] == ["c2c"]
    assert exported["available_scenes"] == list(SCENES)
    assert exported["limits"] == {
        "name_max": PANEL_ITEM_NAME_MAX,
        "desc_max": PANEL_ITEM_DESC_MAX,
        "items_max": PANEL_MAX_ITEMS,
    }
    platform = exported["qq_platforms"][0]
    assert platform["name"] == "pf1"
    assert platform["appid"] == "1023456789"
    assert platform["secret_set"] is True
    masked = platform["secret_masked"]
    assert len(masked) == len("super-secret-value")
    assert masked.startswith("sup") and masked.endswith("ue")
    assert set(masked[3:-2]) == {"*"}
    # 明文 secret 不得出现在导出结果里
    assert "super-secret-value" not in str(exported)
    assert exported["selected_commands"] == [{"name": "help", "desc": "说明"}]


def test_export_config_normalizes_language_and_skips_invalid_commands() -> None:
    exported = export_config(
        {
            "language": "xx-XX",
            "selected_commands": [{"name": "ok"}, {"desc": "no name"}, "junk"],
        }
    )
    assert exported["language"] == "zh-CN"
    assert exported["selected_commands"] == [{"name": "ok", "desc": ""}]
    assert exported["qq_platforms"] == []


# ---------------------------------------------------------------------------
# normalize_config_payload
# ---------------------------------------------------------------------------


def make_existing() -> dict[str, Any]:
    return {
        "language": "zh-CN",
        "scenes": ["c2c", "group"],
        "qq_platforms": [
            {
                "name": "pf1",
                "appid": "1023456789",
                "secret": "old-secret",
                "platform": "qq_official",
            },
        ],
        "selected_commands": [{"name": "help", "desc": "说明"}],
    }


def test_normalize_config_payload_accepts_full_payload() -> None:
    values, errors = normalize_config_payload(
        make_existing(),
        {
            "language": "en-US",
            "scenes": ["group", "unknown"],
            "qq_platforms": [
                {
                    "name": "pf2",
                    "appid": "9999999999",
                    "secret": "new-secret",
                    "platform": "qq_official_webhook",
                }
            ],
            "selected_commands": [{"name": "ping", "desc": "Pong"}],
        },
    )

    assert errors == []
    assert values["language"] == "en-US"
    assert values["scenes"] == ["group"]
    assert values["qq_platforms"] == [
        {
            "name": "pf2",
            "appid": "9999999999",
            "secret": "new-secret",
            "platform": "qq_official_webhook",
        }
    ]
    assert values["selected_commands"] == [{"name": "ping", "desc": "Pong"}]


def test_normalize_config_payload_keeps_existing_secret_when_blank() -> None:
    """页面只回掩码，secret 留空表示沿用原配置"""
    values, errors = normalize_config_payload(
        make_existing(),
        {
            "qq_platforms": [
                {"name": "renamed", "appid": "1023456789", "secret": "", "platform": "qq_official"},
            ]
        },
    )

    assert errors == []
    assert values["qq_platforms"] == [
        {
            "name": "renamed",
            "appid": "1023456789",
            "secret": "old-secret",
            "platform": "qq_official",
        }
    ]
    # 未提交的字段沿用旧配置
    assert values["language"] == "zh-CN"
    assert values["scenes"] == ["c2c", "group"]
    assert values["selected_commands"] == [{"name": "help", "desc": "说明"}]


def test_normalize_config_payload_requires_secret_for_new_platform() -> None:
    values, errors = normalize_config_payload(
        make_existing(),
        {
            "qq_platforms": [
                {"name": "fresh", "appid": "1234567890", "secret": "", "platform": "qq_official"},
            ]
        },
    )

    assert values["qq_platforms"] == []
    assert len(errors) == 1
    assert "clientSecret" in errors[0]


def test_normalize_config_payload_rejects_invalid_language() -> None:
    _values, errors = normalize_config_payload(make_existing(), {"language": "fr-FR"})
    assert len(errors) == 1
    assert "language" in errors[0]


def test_normalize_config_payload_rejects_bad_platform_entries() -> None:
    _values, errors = normalize_config_payload(
        make_existing(),
        {
            "qq_platforms": [
                "not a dict",
                {"secret": "s"},
                {"appid": "1", "secret": "s", "platform": "aiocqhttp"},
                {"appid": "1", "secret": "s"},
                {"appid": "1", "secret": "s2"},
            ]
        },
    )
    joined = " | ".join(errors)
    assert "条目必须是对象" in joined
    assert "appid 不能为空" in joined
    assert "不支持的平台类型" in joined
    assert "重复" in joined


def test_normalize_config_payload_rejects_oversized_commands() -> None:
    _values, errors = normalize_config_payload(
        make_existing(),
        {
            "selected_commands": [
                {"name": "n" * (PANEL_ITEM_NAME_MAX + 1), "desc": "ok"},
                {"name": "ok", "desc": "d" * (PANEL_ITEM_DESC_MAX + 1)},
                {"desc": "no name"},
                "not a dict",
            ]
        },
    )
    joined = " | ".join(errors)
    assert "name 最多" in joined
    assert "desc 最多" in joined
    assert "name 不能为空" in joined
    assert "条目必须是对象" in joined


def test_normalize_config_payload_rejects_too_many_commands() -> None:
    _values, errors = normalize_config_payload(
        make_existing(),
        {
            "selected_commands": [
                {"name": f"cmd{i}", "desc": ""} for i in range(PANEL_MAX_ITEMS + 1)
            ]
        },
    )
    assert len(errors) == 1
    assert str(PANEL_MAX_ITEMS) in errors[0]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


def test_panel_limits_values() -> None:
    assert PANEL_ITEM_NAME_MAX == 14
    assert PANEL_ITEM_DESC_MAX == 30
    assert PANEL_MAX_ITEMS == 20
    assert DEFAULT_SCENES == ["c2c", "group"]
    assert SCENES == ("c2c", "group", "channel", "dm")
