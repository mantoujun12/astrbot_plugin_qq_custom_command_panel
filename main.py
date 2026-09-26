"""QQ 自定义指令面板插件

用户在 AstrBot WebUI 中通过 schema 的 `selected_commands` 字段手动配置要展示的指令条目,
本插件将用户在 schema 里写好的 {name, desc} 列表原样写入 QQ 官方机器人指令面板。
"""

from __future__ import annotations

from pathlib import Path

import aiohttp
from astrbot.api import logger
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig

from .core import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    SCENES,
    PanelSyncer,
)
from .core.i18n import LOG_TAG, t


@register(
    "astrbot_plugin_qq_custom_command_panel",
    "mantoujun12",
    "用户在 AstrBot WebUI 自定义 QQ 官方机器人指令面板内容",
    "v0.4.1",
    "https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel",
)
class QQCommandPanelPlugin(Star):
    """QQ 自定义指令面板插件入口"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 持久化目录：AstrBot 提供的 data_dir
        # 各 AstrBot 版本可能字段名不同，做兼容处理
        self.data_dir = self._resolve_data_dir(context)
        self._http: aiohttp.ClientSession | None = None
        self._syncer: PanelSyncer | None = None

    @staticmethod
    def _resolve_data_dir(context: Context) -> Path:
        """兼容不同 AstrBot 版本获取 data_dir 的方式"""
        for attr in ("get_data_dir", "data_dir"):
            getter = getattr(context, attr, None)
            if callable(getter):
                try:
                    return Path(getter())
                except Exception as exc:
                    logger.debug(f"{LOG_TAG} {t('log.attr_call_failed', attr=attr, exc=exc)}")
            elif getter:
                return Path(getter)
        return Path("data")

    async def initialize(self) -> None:
        """插件初始化: 启动时同步一次面板"""
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self._syncer = PanelSyncer(
            self.context,
            self._http,
            data_dir=self.data_dir,
            config=dict(self.config),
        )
        try:
            await self._syncer.sync_all()
        except Exception as exc:
            logger.error(
                f"{LOG_TAG} {t('log.startup_sync_failed', exc=exc)}",
                exc_info=True,
            )

    async def terminate(self) -> None:
        """插件销毁：关闭 HTTP 会话"""
        if self._http and not self._http.closed:
            await self._http.close()
            self._http = None
        self._syncer = None


__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "QQCommandPanelPlugin",
]
