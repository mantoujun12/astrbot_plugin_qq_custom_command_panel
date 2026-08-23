"""收集 AstrBot 中已注册的指令"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.core.star.star_handler import star_handlers_registry

from .config import PANEL_ITEM_DESC_MAX, PANEL_ITEM_NAME_MAX, PANEL_MAX_ITEMS


def _extract_cmd_name(handler: Any) -> str | None:
    """从 handler 对象上提取指令名。"""
    # 优先取装饰器上的 cmd_name
    cmd_name = getattr(handler, "cmd_name", None)
    if cmd_name:
        return cmd_name

    # 退化到几个常见字段
    for attr in ("command_name", "name", "cmd"):
        val = getattr(handler, attr, None)
        if val:
            return val
    return None


def _extract_desc(handler: Any) -> str:
    """从 handler 对象上提取描述。"""
    desc = getattr(handler, "desc", None) or getattr(handler, "description", None)
    if desc:
        return desc
    # 从函数 docstring 取首行
    func = getattr(handler, "handler", None) or getattr(handler, "func", None)
    doc = getattr(func, "__doc__", None) if func else None
    if doc:
        first_line = doc.strip().split("\n", 1)[0].strip()
        if first_line:
            return first_line
    return "AstrBot 指令"


def collect_commands() -> list[dict[str, str]]:
    """收集 AstrBot 中已注册的所有指令 (去重)

    返回: [{"name": "/foo", "desc": "..."}, ...]
    """
    seen: dict[str, str] = {}
    try:
        # star_handlers_registry 支持迭代但不支持下标, 转成 list
        handlers_iter = list(star_handlers_registry)
    except Exception as exc:
        logger.warning(f"[qq-command-panel] 读取 star_handlers_registry 失败: {exc}")
        return [{"name": k, "desc": v} for k, v in seen.items()]

    for handler in handlers_iter:
        # 只取指令类型 handler
        if getattr(handler, "event_type", None) is None:
            continue

        cmd_name = _extract_cmd_name(handler)
        if not cmd_name:
            continue

        full_name = cmd_name if cmd_name.startswith("/") else f"/{cmd_name}"
        if full_name in seen:
            continue

        try:
            desc = _extract_desc(handler)
        except Exception as exc:
            logger.debug(f"[qq-command-panel] 提取指令描述失败 {full_name}: {exc}")
            desc = "AstrBot 指令"
        seen[full_name] = desc[:PANEL_ITEM_DESC_MAX]

    return [{"name": k, "desc": v} for k, v in seen.items()]

    return [{"name": k, "desc": v} for k, v in seen.items()]


def filter_commands(
    all_cmds: list[dict[str, str]],
    selected: list[str],
) -> list[dict[str, str]]:
    """根据用户配置过滤出要同步到面板的指令 (最多 PANEL_MAX_ITEMS 个)

    selected 为空表示不过滤，按所有指令的顺序取前 N 个
    """
    if selected:
        wanted = set(selected)
        wanted_no_slash = {s.lstrip("/") for s in wanted}
        filtered = [
            c for c in all_cmds if c["name"] in wanted or c["name"].lstrip("/") in wanted_no_slash
        ]
    else:
        filtered = list(all_cmds)

    # 截断字段以满足 API 限制
    result = []
    for c in filtered[:PANEL_MAX_ITEMS]:
        result.append(
            {
                "name": c["name"][:PANEL_ITEM_NAME_MAX],
                "desc": c["desc"][:PANEL_ITEM_DESC_MAX],
            }
        )
    return result


__all__ = ["collect_commands", "filter_commands"]
