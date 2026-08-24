"""收集 AstrBot 中已注册的指令

该模块仅用于 `/qq_panel_list` 调试指令展示 AstrBot 端已注册指令,
不参与 QQ 面板内容的写入。面板内容完全由用户在 schema 里手动配置。

保留该模块是为了让用户能方便地查看 AstrBot 已注册的指令名和描述,
方便填到 schema 的 selected_commands 中。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.core.star.star_handler import star_handlers_registry

from .config import PANEL_ITEM_DESC_MAX
from .i18n import LOG_TAG, t

# 导入指令过滤器类型, 用来在 event_filters 里识别真正的指令
try:
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.filter.command_group import CommandGroupFilter
except Exception:  # pragma: no cover - 旧版本可能没有
    CommandFilter = None  # type: ignore[assignment,misc]
    CommandGroupFilter = None  # type: ignore[assignment,misc]


def _extract_cmd_name(handler: Any) -> str | None:
    """从 handler 的 event_filters 里提取指令名

    AstrBot 的指令名不在 handler 上直接拿,
    而是在 handler.event_filters[*] 里 (CommandFilter / CommandGroupFilter)。
    """
    filters = getattr(handler, "event_filters", None) or []
    for f in filters:
        if CommandFilter is not None and isinstance(f, CommandFilter):
            name = getattr(f, "command_name", None)
            if name:
                return name
        if CommandGroupFilter is not None and isinstance(f, CommandGroupFilter):
            name = getattr(f, "group_name", None)
            if name:
                return name
    for attr in ("cmd_name", "command_name", "name", "cmd"):
        val = getattr(handler, attr, None)
        if val:
            return val
    return None


def _extract_desc(handler: Any) -> str:
    """从 handler 对象上提取描述"""
    desc = getattr(handler, "desc", None) or getattr(handler, "description", None)
    if desc:
        return desc
    func = getattr(handler, "handler", None) or getattr(handler, "func", None)
    doc = getattr(func, "__doc__", None) if func else None
    if doc:
        first_line = doc.strip().split("\n", 1)[0].strip()
        if first_line:
            return first_line
    return t("fallback.command_desc_default")


def collect_commands() -> list[dict[str, str]]:
    """收集 AstrBot 中已注册的所有指令 (去重)

    仅用于 `/qq_panel_list` 调试指令, 不会写入 QQ 面板。
    返回: [{"name": "/foo", "desc": "..."}, ...]
    """
    seen: dict[str, str] = {}
    try:
        handlers_iter = list(star_handlers_registry)
    except Exception as exc:
        logger.warning(f"{LOG_TAG} {t('log.read_handlers_registry_failed', exc=exc)}")
        return [{"name": k, "desc": v} for k, v in seen.items()]

    for handler in handlers_iter:
        cmd_name = _extract_cmd_name(handler)
        if not cmd_name:
            continue
        full_name = cmd_name if cmd_name.startswith("/") else f"/{cmd_name}"
        if full_name in seen:
            continue
        try:
            desc = _extract_desc(handler)
        except Exception as exc:
            logger.debug(f"{LOG_TAG} {t('log.extract_cmd_desc_failed', cmd=full_name, exc=exc)}")
            desc = t("fallback.command_desc_default")
        seen[full_name] = desc[:PANEL_ITEM_DESC_MAX]

    logger.info(f"{LOG_TAG} {t('log.collect_commands_summary', count=len(seen))}")
    return [{"name": k, "desc": v} for k, v in seen.items()]


__all__ = ["collect_commands"]
