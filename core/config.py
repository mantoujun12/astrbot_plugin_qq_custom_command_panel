"""插件配置读取与校验"""

from __future__ import annotations

from typing import Any

# 指令面板 API 限制
PANEL_ITEM_NAME_MAX = 14
PANEL_ITEM_DESC_MAX = 30
PANEL_MAX_ITEMS = 20

# 支持的指令面板场景
SCENES: tuple[str, ...] = ("c2c", "group", "channel", "dm")

# 默认场景
DEFAULT_SCENES: list[str] = ["c2c", "group"]


# QQ 平台类型别名, 用于在不同 AstrBot 版本/适配器命名之间做归一化
_PLATFORM_ALIASES: dict[str, str] = {
    "qq_official": "qq_official",
    "qq_official_webhook": "qq_official_webhook",
    "qqofficial": "qq_official",
    "qq_bot": "qq_official",
    "qq": "qq_official",
}


def get_enabled_scenes(config: dict[str, Any]) -> list[str]:
    """获取用户在配置中开启的场景列表

    自动过滤掉非法值
    """
    scenes = config.get("scenes", DEFAULT_SCENES)
    if not isinstance(scenes, list):
        return list(DEFAULT_SCENES)
    return [s for s in scenes if isinstance(s, str) and s in SCENES]


def get_selected_commands(config: dict[str, Any]) -> list[dict[str, str]]:
    """读取用户在 schema 里手动配置的指令面板条目

    schema 中 selected_commands 是 template_list, 每条 {name, desc},
    用户在这里自定义要出现在 QQ 面板上的指令名和描述, 插件原样写入

    返回:
        list[{"name": str, "type": "command", "desc": str}],
        最多 PANEL_MAX_ITEMS 条
        name 截断到 PANEL_ITEM_NAME_MAX, desc 截断到 PANEL_ITEM_DESC_MAX。
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
        cleaned.append(
            {
                "name": name[:PANEL_ITEM_NAME_MAX],
                "type": "command",
                "desc": desc[:PANEL_ITEM_DESC_MAX],
            }
        )
        if len(cleaned) >= PANEL_MAX_ITEMS:
            break
    return cleaned


def _parse_platform_entry(pf_meta: Any) -> dict[str, str] | None:
    """从一个 schema 条目或 context 条目中解析 appid/secret/platform。

    兼容:
    - schema 新格式: {"name": "备注", "appid": "...", "secret": "...", "platform": "qq_official"}
    - schema 旧 dict 格式: {"appid": "...", "secret": "...", "platform": "..."}
    - context 格式: 同上, 但 enable 字段为 False 时跳过
    """
    if not isinstance(pf_meta, dict):
        return None

    platform = pf_meta.get("platform") or pf_meta.get("type") or "qq_official"
    platform = _PLATFORM_ALIASES.get(platform, platform)
    if platform not in ("qq_official", "qq_official_webhook"):
        return None

    # schema 来源时, enable 字段默认 True (用户显式填了就是 True);
    # context 来源时遵循原始 enable 字段。
    if pf_meta.get("enable") is False:
        return None

    appid = (
        pf_meta.get("appid")
        or pf_meta.get("app_id")
        or pf_meta.get("client_id")
        or pf_meta.get("bot_id")
    )
    secret = (
        pf_meta.get("secret")
        or pf_meta.get("client_secret")
        or pf_meta.get("app_secret")
        or pf_meta.get("token")
    )
    if not appid or not secret:
        return None

    # pf_id 优先用 name (备注), 否则用 appid, 否则用 platform
    pf_id = pf_meta.get("id") or pf_meta.get("name") or pf_meta.get("platform_id") or str(appid)
    return {
        "pf_id": str(pf_id),
        "appid": str(appid),
        "secret": str(secret),
        "platform": platform,
    }


def _build_platform_map(raw_entries: Any) -> dict[str, dict[str, str]]:
    """把原始 platform 条目列表解析并去重为 {pf_id: {appid, secret, platform}}。

    schema 和 context 两个来源的解析后半段一致, 统一在此处合并。
    同一 pf_id 只保留第一条, 避免重复同步。
    """
    if not isinstance(raw_entries, list) or not raw_entries:
        return {}

    result: dict[str, dict[str, str]] = {}
    for entry in raw_entries:
        parsed = _parse_platform_entry(entry)
        if not parsed:
            continue
        if parsed["pf_id"] in result:
            continue
        result[parsed["pf_id"]] = {
            "appid": parsed["appid"],
            "secret": parsed["secret"],
            "platform": parsed["platform"],
        }
    return result


def get_platforms_from_schema(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """从 schema 配置 (qq_platforms) 读取用户手动填写的 QQ 平台凭证。

    schema 格式:: template_list, 每条 {name?, appid, secret, platform?}
    """
    return _build_platform_map(config.get("qq_platforms", []))


def get_platforms_from_context(context: Any) -> dict[str, dict[str, str]]:
    """从 AstrBot 平台配置中读取 qq_official / qq_official_webhook 的 appid/secret。

    不同 AstrBot 版本/部署方式下, 配置可能挂在不同字段上,
    按优先级尝试多个候选路径。
    """
    platform_settings: Any = None
    for attr in ("platform_settings", "_platform_settings", "platforms"):
        val = getattr(context, attr, None)
        if isinstance(val, list) and val:
            platform_settings = val
            break
    if platform_settings is None:
        for attr in ("astrbot_config", "config"):
            conf = getattr(context, attr, None)
            if isinstance(conf, dict):
                ps = conf.get("platform_settings")
                if isinstance(ps, list) and ps:
                    platform_settings = ps
                    break
    return _build_platform_map(platform_settings)


def get_configured_platforms(
    config: dict[str, Any],
    context: Any,
) -> tuple[dict[str, dict[str, str]], str]:
    """优先读 schema (qq_platforms), 为空才 fallback 到 context 平台配置。

    返回 ({pf_id: {"appid", "secret", "platform"}}, 来源)
    来源取值: "schema" / "context" / "none"
    """
    from_schema = get_platforms_from_schema(config)
    if from_schema:
        return from_schema, "schema"
    from_context = get_platforms_from_context(context)
    if from_context:
        return from_context, "context"
    return {}, "none"


__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "get_configured_platforms",
    "get_enabled_scenes",
    "get_platforms_from_context",
    "get_platforms_from_schema",
    "get_selected_commands",
]
