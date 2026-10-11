"""插件持久化目录解析

AstrBot 约定: 插件运行期产生的数据应存放于 `<AstrBot data>/plugin_data/<plugin_name>/`,
即 `data/plugin_data/<plugin_name>/`, 而不是工作目录下的 `data/`。
前者会随 AstrBot 一起迁移/备份/审计, 后者散落在仓库根目录, 容易丢失或被误提交。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .i18n import LOG_TAG, t

PLUGIN_NAME = "astrbot_plugin_qq_custom_command_panel"


def _iter_data_dir_getters(
    context: Any,
    plugin_name: str,
) -> Iterator[tuple[str, Callable[[], Path]]]:
    """按优先级产出 `(来源名, 取目录的可调用对象)`。

    1. `StarTools.get_data_dir(plugin_name)` — 官方 API, 返回 `<data>/plugin_data/<name>`
    2. `context.get_data_dir(plugin_name)` — 兼容把该 API 挂在 context 上的版本
    3. `get_astrbot_plugin_data_path()` — AstrBot 路径工具, 返回 `<data>/plugin_data`

    导入/取属性失败只代表当前 AstrBot 版本未提供该接口, 静默跳过即可。
    """
    star_tools: Any = None
    try:
        from astrbot.api.star import StarTools

        star_tools = StarTools
    except Exception:
        star_tools = None
    if star_tools is not None:
        yield (
            "StarTools.get_data_dir",
            lambda: Path(star_tools.get_data_dir(plugin_name)),
        )

    context_getter = getattr(context, "get_data_dir", None)
    if callable(context_getter):
        yield (
            "context.get_data_dir",
            lambda: Path(context_getter(plugin_name)),
        )

    plugin_data_path: Any = None
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        plugin_data_path = get_astrbot_plugin_data_path
    except Exception:
        plugin_data_path = None
    if plugin_data_path is not None:
        yield (
            "get_astrbot_plugin_data_path",
            lambda: Path(plugin_data_path()) / plugin_name,
        )


def resolve_plugin_data_dir(
    context: Any = None,
    plugin_name: str = PLUGIN_NAME,
) -> Path:
    """解析插件数据目录, 返回 `<AstrBot data>/plugin_data/<plugin_name>/`。

    依次尝试官方 API / context / 路径工具, 全部不可用时回退到相对 AstrBot
    运行根的 `data/plugin_data/<plugin_name>` (仍遵守同一约定, 不再写回仓库根 `data/`)。

    这里只负责解析路径, 不强制创建目录 — 具体存储层 (如 `PanelStateStore`)
    会在写入前 `mkdir(parents=True, exist_ok=True)`。
    """
    for source, getter in _iter_data_dir_getters(context, plugin_name):
        try:
            path = getter()
        except Exception as exc:
            logger.debug(f"{LOG_TAG} " + t("log.data_dir_resolve_failed", source=source, exc=exc))
            continue
        if path is not None:
            return Path(path)
    return Path("data") / "plugin_data" / plugin_name


__all__ = ["PLUGIN_NAME", "resolve_plugin_data_dir"]
