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


def get_enabled_scenes(config: dict[str, Any]) -> list[str]:
    """获取用户在配置中开启的场景列表。

    自动过滤掉非法值。
    """
    scenes = config.get("scenes", DEFAULT_SCENES)
    if not isinstance(scenes, list):
        return list(DEFAULT_SCENES)
    return [s for s in scenes if isinstance(s, str) and s in SCENES]


def get_selected_commands(config: dict[str, Any]) -> list[str]:
    """获取用户在配置中勾选要同步的指令名列表。"""
    cmds = config.get("selected_commands", [])
    if not isinstance(cmds, list):
        return []
    return [c for c in cmds if isinstance(c, str) and c]


def get_platforms_from_context(context: Any) -> dict[str, dict[str, str]]:
    """从 AstrBot 平台配置中读取 qq_official / qq_official_webhook 的 appid/secret

    返回 {platform_id: {"appid": ..., "secret": ..., "platform": ...}}
    """
    result: dict[str, dict[str, str]] = {}
    platform_settings = getattr(context, "platform_settings", None)
    if platform_settings is None:
        return result

    for pf_meta in platform_settings:
        platform = pf_meta.get("platform", "")
        if platform not in ("qq_official", "qq_official_webhook"):
            continue
        if not pf_meta.get("enable", True):
            continue
        pf_id = pf_meta.get("id") or pf_meta.get("name") or platform
        appid = pf_meta.get("appid") or pf_meta.get("app_id")
        secret = pf_meta.get("secret") or pf_meta.get("client_secret")
        if appid and secret:
            result[str(pf_id)] = {
                "appid": str(appid),
                "secret": str(secret),
                "platform": platform,
            }
    return result


__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "get_enabled_scenes",
    "get_platforms_from_context",
    "get_selected_commands",
]
