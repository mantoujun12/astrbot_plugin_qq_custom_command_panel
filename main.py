"""QQ 自定义指令面板插件

用户在 AstrBot WebUI 中通过 schema 的 `selected_commands` 字段手动配置要展示的指令条目,
本插件将用户在 schema 里写好的 {name, desc} 列表原样写入 QQ 官方机器人指令面板。
"""

from __future__ import annotations

import aiohttp
from astrbot.api import logger
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig

from .core import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    SCENES,
    PanelSyncer,
    register_status_api,
    resolve_plugin_data_dir,
)
from .core.i18n import LOG_TAG, t


@register(
    PLUGIN_NAME,
    "mantoujun12",
    "用户在 AstrBot WebUI 自定义 QQ 官方机器人指令面板内容",
    PLUGIN_VERSION,
    "https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel",
)
class QQCommandPanelPlugin(Star):
    """QQ 自定义指令面板插件入口"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 持久化目录: AstrBot 的 data/plugin_data/<plugin_name>/,
        # 由 core.paths.resolve_plugin_data_dir 兼容不同 AstrBot 版本的获取方式
        self.data_dir = resolve_plugin_data_dir(context, PLUGIN_NAME)
        self._http: aiohttp.ClientSession | None = None
        self._syncer: PanelSyncer | None = None
        # 注册视图 (Dashboard) 的只读状态接口; syncer 到 initialize() 才创建,
        # 因此 handler 在每次请求时再取最新的 syncer / config
        register_status_api(
            self.context,
            lambda: self._syncer,
            lambda: dict(self.config),
        )

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
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "SCENES",
    "QQCommandPanelPlugin",
]
