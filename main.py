"""QQ 自定义指令面板插件

用户在 AstrBot WebUI 中通过 schema 的 `selected_commands` 字段手动配置要展示的指令条目，
本插件将用户在 schema 里写好的 {name, desc} 列表原样写入 QQ 官方机器人指令面板。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    LogBuffer,
    PanelSyncer,
    WebApiBundle,
    register_web_apis,
    resolve_plugin_data_dir,
)
from .core.i18n import DEFAULT_LANGUAGE, LOG_TAG, initialize, t


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
        # 尽早安装日志缓冲，dashboard 打开时才能看到插件启动阶段的记录。
        self._log_buffer = LogBuffer()
        self._log_buffer.install(logger)
        # 尽早按配置初始化翻译器，让数据目录解析等启动日志也使用目标语言。
        initialize(
            Path(__file__).resolve().parent / "core" / "i18n",
            self.config.get("language", DEFAULT_LANGUAGE),
        )
        # 持久化目录：AstrBot 的 data/plugin_data/<plugin_name>/，
        # 由 core.paths.resolve_plugin_data_dir 兼容不同 AstrBot 版本的获取方式
        self.data_dir = resolve_plugin_data_dir(context, PLUGIN_NAME)
        self._http: aiohttp.ClientSession | None = None
        self._syncer: PanelSyncer | None = None
        self._web_api: WebApiBundle | None = None
        # 注册视图 (Dashboard) 的 Web API：状态、配置、同步与实时日志；
        # syncer 到 initialize() 才创建，因此 handler 在每次请求时再取最新的 syncer / config
        self._web_api = register_web_apis(
            self.context,
            lambda: self._syncer,
            lambda: dict(self.config),
            save_config=self._save_config,
            robot_config_dir=self.data_dir,
            log_buffer=self._log_buffer,
        )

    async def _save_config(self, values: dict[str, Any]) -> None:
        """把 dashboard 提交的配置写回 AstrBotConfig 并立即生效

        AstrBot 的插件配置是 AstrBotConfig（dict 子类）并负责落盘，
        这里先确认宿主提供了持久化接口，再更新内存并写回，
        避免出现"只改内存、没落盘"的假成功。
        """
        save_async = getattr(self.config, "save_config_async", None)
        save_sync = getattr(self.config, "save_config", None)
        if not callable(save_async) and not callable(save_sync):
            raise RuntimeError(t("web.config_unavailable"))

        self.config.update(values)
        if callable(save_async):
            await save_async()
        else:
            save_sync()

        if self._syncer is not None:
            self._syncer.set_config(dict(self.config))

    async def initialize(self) -> None:
        """插件初始化：启动时同步一次面板"""
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
        # 同步任务跑在后台，卸载时先取消，避免请求打到已关闭的 HTTP 会话
        if self._web_api is not None:
            await self._web_api.runner.cancel()
            self._web_api = None
        if self._http and not self._http.closed:
            await self._http.close()
            self._http = None
        self._syncer = None
        self._log_buffer.close()


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
