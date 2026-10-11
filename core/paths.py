"""插件持久化目录解析

AstrBot 约定: 插件运行期产生的数据应存放于 `<AstrBot data>/plugin_data/<plugin_name>/`,
即 `data/plugin_data/<plugin_name>/`, 而不是工作目录下的 `data/`。
前者会随 AstrBot 一起迁移/备份/审计, 后者散落在仓库根目录, 容易丢失或被误提交。

解析结果必须落在 AstrBot 配置的数据根 (data root) 之内: 数据根不一定是进程
工作目录 (桌面打包版在 ~/.astrbot, 可被 ASTRBOT_ROOT 覆盖), 因此兜底优先用
AstrBot 官方路径工具解析; 相对路径只在宿主连路径工具都不存在时作为最后手段
(源码部署下数据根恰为 CWD/data)。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from importlib import import_module
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .i18n import LOG_TAG, t

PLUGIN_NAME = "astrbot_plugin_qq_custom_command_panel"


def _import_optional(module_name: str) -> Any:
    """可选导入: 模块不存在只代表当前 AstrBot 版本未提供该接口, 返回 None"""
    try:
        return import_module(module_name)
    except Exception:
        return None


def _find_star_tools() -> Any:
    """定位 StarTools 类, 兼容不同 AstrBot 版本的导出位置"""
    for module_name in ("astrbot.api.star", "astrbot.core.star.star_tools"):
        mod = _import_optional(module_name)
        cls = getattr(mod, "StarTools", None) if mod is not None else None
        if cls is not None:
            return cls
    return None


def _find_path_helper(func_name: str) -> Any:
    """定位 astrbot.core.utils.astrbot_path 下的路径辅助函数"""
    mod = _import_optional("astrbot.core.utils.astrbot_path")
    return getattr(mod, func_name, None) if mod is not None else None


def _iter_data_dir_sources(
    context: Any,
    plugin_name: str,
) -> Iterator[tuple[str, Callable[[], Path]]]:
    """按优先级产出 `(来源名, 返回插件数据目录的可调用对象)`。

    1. `StarTools.get_data_dir(plugin_name)` — 官方 API, 返回 `<data>/plugin_data/<name>`
    2. `context.get_data_dir(plugin_name)` — 兼容把该 API 挂在 context 上的版本
    3. `context.data_dir` — 旧版/宿主暴露的数据根 (无参可调用则调用, 属性则取值),
       按 AstrBot 约定拼出 `<data_root>/plugin_data/<name>`
    4. `get_astrbot_plugin_data_path()` — 官方路径工具, 无参, 返回 `<data>/plugin_data`
    5. `get_astrbot_data_path()` — 官方路径工具, 无参, 返回 `<data>`,
       保证兜底仍落在 AstrBot 配置的数据根内

    导入/取属性失败只代表当前 AstrBot 版本未提供该接口, 静默跳过即可。
    """
    star_tools = _find_star_tools()
    if star_tools is not None:
        yield (
            "StarTools.get_data_dir",
            lambda st=star_tools: Path(st.get_data_dir(plugin_name)),
        )

    context_getter = getattr(context, "get_data_dir", None)
    if callable(context_getter):
        yield (
            "context.get_data_dir",
            lambda g=context_getter: Path(g(plugin_name)),
        )

    data_dir_attr = getattr(context, "data_dir", None)
    if callable(data_dir_attr):
        yield (
            "context.data_dir()",
            lambda a=data_dir_attr: Path(a()) / "plugin_data" / plugin_name,
        )
    elif data_dir_attr:
        yield (
            "context.data_dir",
            lambda a=data_dir_attr: Path(a) / "plugin_data" / plugin_name,
        )

    plugin_data_path = _find_path_helper("get_astrbot_plugin_data_path")
    if callable(plugin_data_path):
        # 注意: 该函数无参数 (v4.9.2 - master 均如此), 插件名在返回值后拼接
        yield (
            "get_astrbot_plugin_data_path",
            lambda h=plugin_data_path: Path(h()) / plugin_name,
        )

    data_path = _find_path_helper("get_astrbot_data_path")
    if callable(data_path):
        yield (
            "get_astrbot_data_path",
            lambda h=data_path: Path(h()) / "plugin_data" / plugin_name,
        )


def resolve_plugin_data_dir(
    context: Any = None,
    plugin_name: str = PLUGIN_NAME,
) -> Path:
    """解析插件数据目录, 返回 `<AstrBot data>/plugin_data/<plugin_name>/`。

    按优先级尝试: StarTools / context.get_data_dir → context.data_dir →
    官方路径工具; 全部不可用时回退到相对 AstrBot 运行根的
    `data/plugin_data/<plugin_name>` (仍遵守同一约定, 不再写回裸 `data/`)。

    这里只负责解析路径, 不强制创建目录 — 具体存储层 (如 `PanelStateStore`)
    会在写入前 `mkdir(parents=True, exist_ok=True)`。
    """
    for source, getter in _iter_data_dir_sources(context, plugin_name):
        try:
            path = getter()
        except Exception as exc:
            logger.debug(f"{LOG_TAG} " + t("log.data_dir_resolve_failed", source=source, exc=exc))
            continue
        if path is not None:
            return Path(path)
    # 最后兜底: 相对进程工作目录 (源码部署下与 AstrBot 数据根一致)
    return Path("data") / "plugin_data" / plugin_name


__all__ = ["PLUGIN_NAME", "resolve_plugin_data_dir"]
