"""插件持久化目录解析

AstrBot 约定: 插件运行期产生的数据应存放于 `<AstrBot data>/plugin_data/<plugin_name>/`,
即 `data/plugin_data/<plugin_name>/`, 而不是工作目录下的 `data/`。
前者会随 AstrBot 一起迁移/备份/审计, 后者散落在仓库根目录, 容易丢失或被误提交。

解析结果必须落在 AstrBot 配置的数据根 (data root) 之内: 数据根不一定是进程
工作目录 (桌面打包版在 ~/.astrbot, 可被 ASTRBOT_ROOT 覆盖), 因此优先用
AstrBot 官方路径工具解析。即使官方 API 完全不可导入, 最后兜底也会按 AstrBot
的数据根规则定位 (`ASTRBOT_ROOT` > 桌面版 `~/.astrbot` > 工作目录), 而不是
无条件使用进程工作目录。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from importlib import import_module
from pathlib import Path
from typing import Any

from astrbot.api import logger

from .i18n import LOG_TAG, t

PLUGIN_NAME = "astrbot_plugin_qq_custom_command_panel"
# 插件版本, 与 metadata.yaml 的 version 保持一致; 供 @register 与视图状态接口共用
PLUGIN_VERSION = "v0.4.4"


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


def _fallback_data_root() -> Path:
    """官方路径 API 完全不可用时, 按 AstrBot 的规则复刻本机数据根。

    与 `astrbot.core.utils.astrbot_path.get_astrbot_root()` 一致:
    `ASTRBOT_ROOT` > 桌面打包版 (`~/.astrbot`) > 进程工作目录。
    仅在 `get_astrbot_data_path()` 也无法导入时才会用到, 作为最后手段,
    目的是即使退化到该分支也不会把状态写到 AstrBot 数据根之外。
    """
    env_root = os.environ.get("ASTRBOT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    if os.environ.get("ASTRBOT_DESKTOP_CLIENT") == "1":
        return (Path.home() / ".astrbot").resolve()
    return Path.cwd().resolve()


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
    官方路径工具; 全部不可用时按 AstrBot 的数据根规则
    (`ASTRBOT_ROOT` > 桌面版 `~/.astrbot` > 工作目录) 定位到
    `<data_root>/plugin_data/<plugin_name>`, 不会写到数据根之外。

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

    # 最后兜底: 官方路径 API 全部不可用 (正常 AstrBot 下不会发生),
    # 按 AstrBot 的数据根规则定位, 避免写到数据根之外
    fallback = _fallback_data_root() / "data" / "plugin_data" / plugin_name
    logger.warning(f"{LOG_TAG} " + t("log.data_dir_fallback_used", path=fallback))
    return fallback


__all__ = ["PLUGIN_NAME", "PLUGIN_VERSION", "resolve_plugin_data_dir"]
