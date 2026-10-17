"""插件配置读取、导出与写回校验。

本模块只做纯数据变换，不接触 Web API 与运行时对象，方便离线单测：
- 读取：把 ``_conf_schema.json`` 里的用户配置整理成 PanelSyncer 可直接使用的结构
- 导出：把当前配置转成 dashboard 可渲染的安全结构（secret 只回掩码）
- 归一：校验 dashboard 提交的完整配置，非法输入返回错误而不是静默截断

平台凭证只能来自本插件的 ``qq_platforms``：AstrBot 没有把平台适配器的机器人信息
暴露给插件，所以这里不再保留"从 context 回退读取"的路径。
"""

from __future__ import annotations

import re
from typing import Any

from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, t

# 指令面板 API 限制
PANEL_ITEM_NAME_MAX = 14
PANEL_ITEM_DESC_MAX = 30
PANEL_MAX_ITEMS = 20

# QQ 面板单个条目的类型。POST/PUT /v2/panels 的 panel.items 每项都必须带 type，
# 缺失时 QQ 会整份拒绝并返回 30015「面板元素类型不合法」。
PANEL_ITEM_TYPE = "command"

# 支持的指令面板场景
SCENES: tuple[str, ...] = ("c2c", "group", "channel", "dm")

# 默认场景
DEFAULT_SCENES: list[str] = ["c2c", "group"]

# 插件视图主题默认色，与 web/dashboard/src/theme/index.ts 的浅色调色板保持一致
DEFAULT_PRIMARY_COLOR = "#3c96ca"
DEFAULT_SECONDARY_COLOR = "#2f86bd"
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# 支持的 QQ 平台适配器类型
PLATFORM_TYPES: tuple[str, ...] = ("qq_official", "qq_official_webhook")

# `_conf_schema.json` 里 template_list 的模板 key。
# AstrBot WebUI 靠条目的 __template_key 匹配模板，缺失或非法会让该条目在插件配置页
# 报“找不到对应模板，请删除后重新添加。”，所以写回配置时必须带上。
QQ_PLATFORM_TEMPLATE_KEY = "qq_platform"
COMMAND_TEMPLATE_KEY = "command"

# QQ 平台类型别名：兼容不同 AstrBot 版本/写法之间的差异
_PLATFORM_ALIASES: dict[str, str] = {
    "qq_official": "qq_official",
    "qq_official_webhook": "qq_official_webhook",
    "qqofficial": "qq_official",
    "qq_bot": "qq_official",
    "qq": "qq_official",
}


def get_enabled_scenes(config: dict[str, Any]) -> list[str]:
    """获取用户配置中开启的场景列表

    自动过滤非法值
    """
    scenes = config.get("scenes", DEFAULT_SCENES)
    if not isinstance(scenes, list):
        return list(DEFAULT_SCENES)
    return [s for s in scenes if isinstance(s, str) and s in SCENES]


def get_theme_colors(config: dict[str, Any]) -> dict[str, str]:
    """读取插件视图主题色，缺失或非法值回退到默认配色。"""
    primary = config.get("primary_color")
    secondary = config.get("secondary_color")
    primary_text = primary.strip() if isinstance(primary, str) else ""
    secondary_text = secondary.strip() if isinstance(secondary, str) else ""
    return {
        "primary_color": (
            primary_text.lower() if _HEX_COLOR_RE.fullmatch(primary_text) else DEFAULT_PRIMARY_COLOR
        ),
        "secondary_color": (
            secondary_text.lower()
            if _HEX_COLOR_RE.fullmatch(secondary_text)
            else DEFAULT_SECONDARY_COLOR
        ),
    }


def build_panel_item(name: str, desc: str = "") -> dict[str, str]:
    """构造一条可直接提交给 QQ 面板 API 的条目

    name / desc 超长时截断，避免 QQ 以 30015 拒绝整份面板。
    """
    return {
        "name": name[:PANEL_ITEM_NAME_MAX],
        "type": PANEL_ITEM_TYPE,
        "desc": desc[:PANEL_ITEM_DESC_MAX],
    }


def normalize_panel_items(items: Any) -> list[dict[str, str]]:
    """把配置里的条目整理成 QQ API 需要的结构

    插件内部（schema 与 ``robot_config.json``）只存 name / desc，写入面板前统一
    经这里补齐 type；跳过非字典条目与空 name。
    """
    if not isinstance(items, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        desc = item.get("desc")
        normalized.append(build_panel_item(name, desc if isinstance(desc, str) else ""))
    return normalized


def get_selected_commands(config: dict[str, Any]) -> list[dict[str, str]]:
    """获取用户在 schema 里手动配置的指令面板条目

    schema 的 selected_commands 是 template_list，每条 {name, desc}。
    用户在这里自定义要出现在 QQ 面板里的指令，插件把它们原样写入。

    返回：
        list[{"name": str, "type": "command", "desc": str}]，最多 PANEL_MAX_ITEMS 条
        name 截断到 PANEL_ITEM_NAME_MAX，desc 截断到 PANEL_ITEM_DESC_MAX；
        非法条目会被跳过
    """
    raw = config.get("selected_commands", [])
    if not isinstance(raw, list):
        return []

    cleaned: list[dict[str, str]] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        if not isinstance(name, str) or not name:
            continue
        desc = c.get("desc") or ""
        if not isinstance(desc, str):
            desc = ""
        cleaned.append(build_panel_item(name, desc))
        if len(cleaned) >= PANEL_MAX_ITEMS:
            break
    return cleaned


def mask_secret(value: Any) -> str:
    """secret 展示掩码：保留前 3 位与后 2 位，过短则整体打码"""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 5)}{text[-2:]}"


def _parse_platform_entry(entry: Any) -> dict[str, str] | None:
    """解析一条 schema 的 qq_platforms 条目

    支持格式：
    - 标准格式：{"name": "备注", "appid": "...", "secret": "...", "platform": "qq_official"}
    - 简化格式：{"appid": "...", "secret": "...", "platform": "..."}
    非法条目返回 None
    """
    if not isinstance(entry, dict):
        return None

    platform = entry.get("platform") or entry.get("type") or "qq_official"
    platform = _PLATFORM_ALIASES.get(str(platform), str(platform))
    if platform not in PLATFORM_TYPES:
        return None

    appid = (
        entry.get("appid") or entry.get("app_id") or entry.get("client_id") or entry.get("bot_id")
    )
    secret = (
        entry.get("secret")
        or entry.get("client_secret")
        or entry.get("clientSecret")
        or entry.get("app_secret")
        or entry.get("token")
    )
    if not appid or not secret:
        return None

    # pf_id 优先取备注名，其次 appid，最后平台类型
    pf_id = entry.get("id") or entry.get("name") or entry.get("platform_id") or str(appid)
    name = entry.get("name")
    return {
        "pf_id": str(pf_id),
        "name": name if isinstance(name, str) else "",
        "appid": str(appid),
        "secret": str(secret),
        "platform": platform,
    }


def get_platform_entries(config: dict[str, Any]) -> list[dict[str, str]]:
    """读取 schema 的 qq_platforms 条目（含备注名）

    非法条目跳过，同一 pf_id 只保留第一条，避免重复同步
    """
    raw = config.get("qq_platforms", [])
    if not isinstance(raw, list):
        return []

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        parsed = _parse_platform_entry(item)
        if not parsed or parsed["pf_id"] in seen:
            continue
        seen.add(parsed["pf_id"])
        entries.append(parsed)
    return entries


def get_platforms_from_schema(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """从 schema 配置 (qq_platforms) 读取用户手填的 QQ 平台凭证"""
    return {
        entry["pf_id"]: {
            "appid": entry["appid"],
            "secret": entry["secret"],
            "platform": entry["platform"],
        }
        for entry in get_platform_entries(config)
    }


def get_configured_platforms(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """返回当前配置下可用的平台凭证，未配置时返回空 dict

    只有 ``qq_platforms`` 一个来源：AstrBot 没有向插件暴露平台适配器的机器人
    信息，插件无法从 AstrBot 平台配置里回退读取 appid / clientSecret。
    """
    return get_platforms_from_schema(config)


def _dump_platforms(config: dict[str, Any]) -> list[dict[str, Any]]:
    """把已有 qq_platforms 原样导出（局部提交时用于沿用旧值）"""
    raw = config.get("qq_platforms", [])
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _dump_commands(config: dict[str, Any]) -> list[dict[str, str]]:
    """把已有 selected_commands 原样导出（局部提交时用于沿用旧值）"""
    raw = config.get("selected_commands", [])
    if not isinstance(raw, list):
        return []
    commands: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        desc = item.get("desc")
        commands.append({"name": name, "desc": desc if isinstance(desc, str) else ""})
    return commands


def _with_template_key(entry: dict[str, Any], template_key: str) -> dict[str, Any]:
    """返回带 `__template_key` 的副本，供写回 template_list 字段使用

    本插件每个 template_list 只声明一个模板，这里统一写成固定的模板 key：
    既补上缺失的情况，也覆盖掉提交项里非法的 key，避免 AstrBot 插件配置页
    因匹配不到模板而报“找不到对应模板，请删除后重新添加。”。
    """
    merged = dict(entry)
    merged["__template_key"] = template_key
    return merged


def export_config(config: dict[str, Any]) -> dict[str, Any]:
    """把当前配置导出成 dashboard 可渲染的结构

    secret 只回掩码与"是否已配置"标记，不回明文，页面与前端日志里都不会出现明文密钥。
    """
    language = config.get("language")
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    return {
        "language": language,
        **get_theme_colors(config),
        "scenes": get_enabled_scenes(config),
        "available_scenes": list(SCENES),
        "qq_platforms": [
            {
                "name": entry["name"],
                "appid": entry["appid"],
                "platform": entry["platform"],
                "secret_masked": mask_secret(entry["secret"]),
                "secret_set": bool(entry["secret"]),
            }
            for entry in get_platform_entries(config)
        ],
        "selected_commands": _dump_commands(config),
        "limits": {
            "name_max": PANEL_ITEM_NAME_MAX,
            "desc_max": PANEL_ITEM_DESC_MAX,
            "items_max": PANEL_MAX_ITEMS,
        },
    }


def normalize_config_payload(
    existing: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """校验并合并 dashboard 提交的配置

    - 缺省字段沿用 existing，局部提交也安全
    - 返回 (归一后的配置, 错误列表)；错误列表非空时调用方不应落库
    - 超长 name / desc 与超量指令条目一律报错，不做静默截断
    """
    errors: list[str] = []
    values: dict[str, Any] = {}

    language = payload.get("language", existing.get("language"))
    if language is None:
        language = DEFAULT_LANGUAGE
    if language not in SUPPORTED_LANGUAGES:
        errors.append(
            t(
                "config.error.language",
                value=language,
                supported=t("common.list_separator").join(SUPPORTED_LANGUAGES),
            )
        )
    else:
        values["language"] = language

    for field, default in (
        ("primary_color", DEFAULT_PRIMARY_COLOR),
        ("secondary_color", DEFAULT_SECONDARY_COLOR),
    ):
        submitted = field in payload
        raw_color = payload[field] if submitted else existing.get(field)
        if raw_color is None:
            raw_color = default
        if isinstance(raw_color, str):
            raw_color = raw_color.strip()
        if not isinstance(raw_color, str) or not _HEX_COLOR_RE.fullmatch(raw_color):
            if submitted:
                errors.append(t("config.error.theme_color", field=field, value=raw_color))
            else:
                values[field] = default
        else:
            values[field] = raw_color.lower()

    raw_scenes = payload.get("scenes", existing.get("scenes"))
    if raw_scenes is None:
        values["scenes"] = list(DEFAULT_SCENES)
    elif not isinstance(raw_scenes, list):
        errors.append(t("config.error.scenes_type"))
    else:
        values["scenes"] = [s for s in raw_scenes if isinstance(s, str) and s in SCENES]

    # 页面只回掩码，所以 secret 留空表示沿用原配置（按 appid 匹配）
    secret_by_appid = {entry["appid"]: entry["secret"] for entry in get_platform_entries(existing)}

    raw_platforms = payload.get("qq_platforms")
    if raw_platforms is None:
        values["qq_platforms"] = [
            _with_template_key(item, QQ_PLATFORM_TEMPLATE_KEY) for item in _dump_platforms(existing)
        ]
    elif not isinstance(raw_platforms, list):
        errors.append(t("config.error.platforms_type"))
    else:
        platforms: list[dict[str, str]] = []
        seen_appids: set[str] = set()
        for index, item in enumerate(raw_platforms):
            if not isinstance(item, dict):
                errors.append(t("config.error.platform_entry", index=index))
                continue
            appid = str(item.get("appid") or "").strip()
            if not appid:
                errors.append(t("config.error.platform_appid", index=index))
                continue
            if appid in seen_appids:
                errors.append(t("config.error.platform_duplicate", index=index, appid=appid))
                continue
            platform = str(item.get("platform") or "qq_official")
            platform = _PLATFORM_ALIASES.get(platform, platform)
            if platform not in PLATFORM_TYPES:
                errors.append(t("config.error.platform_type", index=index, platform=platform))
                continue
            secret = str(item.get("secret") or "").strip()
            if not secret:
                secret = secret_by_appid.get(appid, "")
                if not secret:
                    errors.append(t("config.error.platform_secret", index=index))
                    continue
            seen_appids.add(appid)
            name = str(item.get("name") or "").strip()
            platforms.append(
                _with_template_key(
                    {"name": name, "appid": appid, "secret": secret, "platform": platform},
                    QQ_PLATFORM_TEMPLATE_KEY,
                )
            )
        values["qq_platforms"] = platforms

    raw_commands = payload.get("selected_commands")
    if raw_commands is None:
        values["selected_commands"] = [
            _with_template_key(item, COMMAND_TEMPLATE_KEY) for item in _dump_commands(existing)
        ]
    elif not isinstance(raw_commands, list):
        errors.append(t("config.error.commands_type"))
    elif len(raw_commands) > PANEL_MAX_ITEMS:
        errors.append(t("config.error.commands_limit", limit=PANEL_MAX_ITEMS))
    else:
        commands: list[dict[str, str]] = []
        for index, item in enumerate(raw_commands):
            if not isinstance(item, dict):
                errors.append(t("config.error.command_entry", index=index))
                continue
            raw_name = item.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                errors.append(t("config.error.command_name", index=index))
                continue
            if len(name) > PANEL_ITEM_NAME_MAX:
                errors.append(
                    t("config.error.command_name_length", index=index, limit=PANEL_ITEM_NAME_MAX)
                )
                continue
            raw_desc = item.get("desc")
            desc = raw_desc.strip() if isinstance(raw_desc, str) else ""
            if len(desc) > PANEL_ITEM_DESC_MAX:
                errors.append(
                    t("config.error.command_desc_length", index=index, limit=PANEL_ITEM_DESC_MAX)
                )
                continue
            commands.append(_with_template_key({"name": name, "desc": desc}, COMMAND_TEMPLATE_KEY))
        values["selected_commands"] = commands

    return values, errors


__all__ = [
    "COMMAND_TEMPLATE_KEY",
    "DEFAULT_PRIMARY_COLOR",
    "DEFAULT_SCENES",
    "DEFAULT_SECONDARY_COLOR",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_ITEM_TYPE",
    "PANEL_MAX_ITEMS",
    "PLATFORM_TYPES",
    "QQ_PLATFORM_TEMPLATE_KEY",
    "SCENES",
    "build_panel_item",
    "export_config",
    "get_configured_platforms",
    "get_enabled_scenes",
    "get_platform_entries",
    "get_platforms_from_schema",
    "get_selected_commands",
    "get_theme_colors",
    "mask_secret",
    "normalize_config_payload",
    "normalize_panel_items",
]
