"""core.config 的单元测试（纯函数，不做任何 IO）"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.config import (
    COMMAND_TEMPLATE_KEY,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SCENES,
    DEFAULT_SECONDARY_COLOR,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    QQ_PLATFORM_TEMPLATE_KEY,
    SCENES,
    export_config,
    get_configured_platforms,
    get_enabled_scenes,
    get_platform_entries,
    get_platforms_from_schema,
    get_selected_commands,
    get_theme_colors,
    mask_secret,
    normalize_config_payload,
    normalize_panel_items,
)
from core.i18n import SUPPORTED_LANGUAGES

REPO_ROOT = Path(__file__).resolve().parent.parent

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
# get_theme_colors
# ---------------------------------------------------------------------------


def test_get_theme_colors_normalizes_valid_values() -> None:
    assert get_theme_colors({"primary_color": "#AABBCC", "secondary_color": "#123456"}) == {
        "primary_color": "#aabbcc",
        "secondary_color": "#123456",
    }


def test_get_theme_colors_falls_back_for_missing_or_invalid_values() -> None:
    assert get_theme_colors({}) == {
        "primary_color": DEFAULT_PRIMARY_COLOR,
        "secondary_color": DEFAULT_SECONDARY_COLOR,
    }
    assert get_theme_colors({"primary_color": "red", "secondary_color": "#12345"}) == {
        "primary_color": DEFAULT_PRIMARY_COLOR,
        "secondary_color": DEFAULT_SECONDARY_COLOR,
    }


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
# normalize_panel_items: 写面板前补齐 QQ 要求的 type
# ---------------------------------------------------------------------------


def test_normalize_panel_items_fills_type_and_truncates() -> None:
    items = normalize_panel_items(
        [
            {"name": "help", "desc": "帮助"},
            {"name": "n" * 30, "desc": "d" * 50},
        ]
    )
    assert items == [
        {"name": "help", "type": "command", "desc": "帮助"},
        {
            "name": "n" * PANEL_ITEM_NAME_MAX,
            "type": "command",
            "desc": "d" * PANEL_ITEM_DESC_MAX,
        },
    ]


def test_normalize_panel_items_skips_invalid_entries() -> None:
    assert normalize_panel_items(
        [
            "junk",
            {"desc": "no name"},
            {"name": "  "},
            {"name": "ok", "desc": 42},
        ]
    ) == [{"name": "ok", "type": "command", "desc": ""}]


def test_normalize_panel_items_non_list_returns_empty() -> None:
    assert normalize_panel_items(None) == []
    assert normalize_panel_items({"name": "help"}) == []


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
    # 平台身份始终取 appid，platform 归一成 qq_official
    assert entries == [
        {
            "pf_id": "222",
            "name": "",
            "appid": "222",
            "secret": "s2",
            "platform": "qq_official",
        }
    ]


def test_get_platform_entries_uses_appid_as_identity() -> None:
    entries = get_platform_entries(
        {
            "qq_platforms": [
                {"name": "bot", "appid": "A", "secret": "s1"},
                {"name": "bot", "appid": "B", "secret": "s2"},
            ]
        }
    )

    assert [(entry["pf_id"], entry["name"]) for entry in entries] == [
        ("A", "bot"),
        ("B", "bot"),
    ]


def test_get_platforms_from_schema_basic() -> None:
    config = {
        "qq_platforms": [
            {"name": "小号", "appid": "111", "secret": "s1", "platform": "qq_official"},
        ]
    }
    assert get_platforms_from_schema(config) == {
        "111": {"appid": "111", "secret": "s1", "platform": "qq_official"},
    }


def test_get_platforms_from_schema_keeps_same_name_with_different_appids() -> None:
    config = {
        "qq_platforms": [
            {"name": "dup", "appid": "1", "secret": "s1"},
            {"name": "dup", "appid": "2", "secret": "s2"},
        ]
    }
    platforms = get_platforms_from_schema(config)
    # 备注名可以重复，平台身份以 appid 为准
    assert platforms == {
        "1": {"appid": "1", "secret": "s1", "platform": "qq_official"},
        "2": {"appid": "2", "secret": "s2", "platform": "qq_official"},
    }


def test_get_platforms_from_schema_dedups_by_appid() -> None:
    config = {
        "qq_platforms": [
            {"name": "first", "appid": "same", "secret": "s1"},
            {"name": "second", "appid": "same", "secret": "s2"},
        ]
    }
    platforms = get_platforms_from_schema(config)
    assert len(platforms) == 1
    assert platforms["same"]["secret"] == "s1"


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
    assert list(platforms) == ["s_app"]
    assert platforms["s_app"]["appid"] == "s_app"


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
    assert exported["primary_color"] == DEFAULT_PRIMARY_COLOR
    assert exported["secondary_color"] == DEFAULT_SECONDARY_COLOR
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


def test_export_and_normalize_preserves_platforms_with_duplicate_names() -> None:
    """GET /config 的结果原样保存回去时，不能丢掉同名平台及其 secret。"""
    config = {
        "qq_platforms": [
            {"name": "bot", "appid": "A", "secret": "s1"},
            {"name": "bot", "appid": "B", "secret": "s2"},
        ]
    }
    exported = export_config(config)
    submitted = [
        {
            "name": platform["name"],
            "appid": platform["appid"],
            "secret": "",
            "platform": platform["platform"],
        }
        for platform in exported["qq_platforms"]
    ]

    values, errors = normalize_config_payload(config, {"qq_platforms": submitted})

    assert errors == []
    assert [(platform["name"], platform["appid"]) for platform in values["qq_platforms"]] == [
        ("bot", "A"),
        ("bot", "B"),
    ]
    assert [platform["secret"] for platform in values["qq_platforms"]] == ["s1", "s2"]


# ---------------------------------------------------------------------------
# normalize_config_payload
# ---------------------------------------------------------------------------


def make_existing() -> dict[str, Any]:
    return {
        "language": "zh-CN",
        "primary_color": "#112233",
        "secondary_color": "#445566",
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
            "primary_color": "#AABBCC",
            "secondary_color": "#123456",
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
    assert values["primary_color"] == "#aabbcc"
    assert values["secondary_color"] == "#123456"
    assert values["scenes"] == ["group"]
    assert values["qq_platforms"] == [
        {
            "__template_key": QQ_PLATFORM_TEMPLATE_KEY,
            "name": "pf2",
            "appid": "9999999999",
            "secret": "new-secret",
            "platform": "qq_official_webhook",
        }
    ]
    assert values["selected_commands"] == [
        {"__template_key": COMMAND_TEMPLATE_KEY, "name": "ping", "desc": "Pong"}
    ]


@pytest.mark.parametrize("language", ["ru-RU", "ja-JP"])
def test_normalize_config_payload_accepts_new_languages(language: str) -> None:
    values, errors = normalize_config_payload(make_existing(), {"language": language})

    assert errors == []
    assert values["language"] == language


@pytest.mark.parametrize("language", ["ru-RU", "ja-JP"])
def test_export_config_preserves_new_languages(language: str) -> None:
    assert export_config({"language": language})["language"] == language


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
            "__template_key": QQ_PLATFORM_TEMPLATE_KEY,
            "name": "renamed",
            "appid": "1023456789",
            "secret": "old-secret",
            "platform": "qq_official",
        }
    ]
    # 未提交的字段沿用旧配置
    assert values["language"] == "zh-CN"
    assert values["primary_color"] == "#112233"
    assert values["secondary_color"] == "#445566"
    assert values["scenes"] == ["c2c", "group"]
    assert values["selected_commands"] == [
        {"__template_key": COMMAND_TEMPLATE_KEY, "name": "help", "desc": "说明"}
    ]


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


def test_normalize_config_payload_writes_template_key() -> None:
    """写回的 template_list 条目必须带 __template_key，否则宿主配置页报找不到模板

    这里断言完整的条目列表：只检查保留下来的条目是不够的，若规范化器把带伪造
    模板键的条目整条丢掉，断言同样会通过，等于放走了真正的 bug。
    """
    values, errors = normalize_config_payload(
        make_existing(),
        {
            "qq_platforms": [
                # 提交项自带非法 key
                {
                    "__template_key": "bogus",
                    "name": "pf2",
                    "appid": "9999999999",
                    "secret": "s",
                    "platform": "qq_official",
                },
                # 提交项完全不带 key
                {"name": "pf3", "appid": "8888888888", "secret": "s", "platform": "qq_official"},
            ],
            "selected_commands": [{"name": "ping", "desc": "Pong"}],
        },
    )

    assert errors == []
    # 两条都必须保留，且数据原样、模板键被纠正
    assert values["qq_platforms"] == [
        {
            "__template_key": QQ_PLATFORM_TEMPLATE_KEY,
            "name": "pf2",
            "appid": "9999999999",
            "secret": "s",
            "platform": "qq_official",
        },
        {
            "__template_key": QQ_PLATFORM_TEMPLATE_KEY,
            "name": "pf3",
            "appid": "8888888888",
            "secret": "s",
            "platform": "qq_official",
        },
    ]
    assert values["selected_commands"] == [
        {"__template_key": COMMAND_TEMPLATE_KEY, "name": "ping", "desc": "Pong"}
    ]


def test_normalize_config_payload_backfills_template_key_for_untouched_fields() -> None:
    """旧版本写坏的配置（缺 __template_key）在局部提交时会被补齐"""
    broken = make_existing()
    broken["qq_platforms"] = [{"name": "pf1", "appid": "1023456789", "secret": "s"}]
    broken["selected_commands"] = [{"name": "help", "desc": "说明"}]

    values, errors = normalize_config_payload(broken, {"language": "en-US"})

    assert errors == []
    assert values["qq_platforms"] == [
        {
            "__template_key": QQ_PLATFORM_TEMPLATE_KEY,
            "name": "pf1",
            "appid": "1023456789",
            "secret": "s",
        }
    ]
    assert values["selected_commands"] == [
        {"__template_key": COMMAND_TEMPLATE_KEY, "name": "help", "desc": "说明"}
    ]


def test_normalize_config_payload_keeps_the_sections_a_page_does_not_own() -> None:
    """视图按页分工提交，缺省的部分必须原样保留。

    「设置」页只发 language / scenes，「兼容性」页只发平台与指令；任一方漏掉的字段
    都要沿用已保存的值，否则两个页面会互相覆盖对方刚保存的改动。
    """
    values, errors = normalize_config_payload(
        make_existing(), {"language": "en-US", "scenes": ["c2c"]}
    )

    assert errors == []
    assert values["language"] == "en-US"
    assert values["scenes"] == ["c2c"]
    assert [p["appid"] for p in values["qq_platforms"]] == ["1023456789"]
    assert [c["name"] for c in values["selected_commands"]] == ["help"]

    values, errors = normalize_config_payload(
        make_existing(),
        {
            "qq_platforms": [
                {"name": "pf1", "appid": "1023456789", "platform": "qq_official", "secret": ""}
            ],
            "selected_commands": [],
        },
    )

    assert errors == []
    assert values["language"] == "zh-CN"
    assert values["scenes"] == ["c2c", "group"]
    # 显式传空列表是「清空」，不能被当成缺省而沿用旧值
    assert values["selected_commands"] == []


def test_normalize_config_payload_rejects_invalid_language() -> None:
    _values, errors = normalize_config_payload(make_existing(), {"language": "fr-FR"})
    assert len(errors) == 1
    assert "language" in errors[0]


def test_normalize_config_payload_rejects_invalid_theme_colors() -> None:
    _values, errors = normalize_config_payload(
        make_existing(),
        {"primary_color": "rgb(1, 2, 3)", "secondary_color": "#12345"},
    )

    joined = " | ".join(errors)
    assert "primary_color" in joined
    assert "secondary_color" in joined
    assert "#RRGGBB" in joined


def test_normalize_config_payload_resets_invalid_stored_theme_colors() -> None:
    existing = {**make_existing(), "primary_color": "red", "secondary_color": "#12345"}

    values, errors = normalize_config_payload(existing, {"scenes": ["c2c"]})

    # 非法旧值不阻塞别的页面保存，未提交时回退默认配色
    assert errors == []
    assert values["primary_color"] == DEFAULT_PRIMARY_COLOR
    assert values["secondary_color"] == DEFAULT_SECONDARY_COLOR


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
    assert DEFAULT_PRIMARY_COLOR == "#3c96ca"
    assert DEFAULT_SECONDARY_COLOR == "#2f86bd"


def test_template_keys_match_conf_schema() -> None:
    """写回用的模板 key 必须和 _conf_schema.json 的 templates 对上"""
    schema = json.loads((REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    assert QQ_PLATFORM_TEMPLATE_KEY in schema["qq_platforms"]["templates"]
    assert COMMAND_TEMPLATE_KEY in schema["selected_commands"]["templates"]


def test_language_schema_matches_supported_languages() -> None:
    schema = json.loads((REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    assert tuple(schema["language"]["options"]) == SUPPORTED_LANGUAGES


def test_non_list_schema_sections_are_ignored() -> None:
    assert get_platform_entries({"qq_platforms": "bad"}) == []
    exported = export_config({"qq_platforms": "bad", "selected_commands": "bad"})
    assert exported["selected_commands"] == []


def test_normalize_config_payload_handles_non_list_sections() -> None:
    values, errors = normalize_config_payload(
        make_existing(),
        {
            "scenes": None,
            "qq_platforms": "bad",
            "selected_commands": "bad",
        },
    )

    assert values["scenes"] == DEFAULT_SCENES
    assert any("qq_platforms" in error for error in errors)
    assert any("selected_commands" in error for error in errors)


def test_normalize_config_payload_handles_non_list_existing_sections() -> None:
    values, errors = normalize_config_payload(
        {"qq_platforms": "bad", "selected_commands": "bad"},
        {"scenes": "bad"},
    )

    assert values["qq_platforms"] == []
    assert values["selected_commands"] == []
    assert any("scenes" in error for error in errors)
