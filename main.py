"""QQ 自定义指令面板插件。

将 AstrBot 已注册的指令同步到 QQ 官方机器人指令面板，
用户在 QQ 输入 / 即可唤起面板快速调用 AstrBot 指令。
"""

from __future__ import annotations

from pathlib import Path

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig

from .core import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_MAX_ITEMS,
    PANEL_ITEM_NAME_MAX,
    SCENES,
    PanelSyncer,
    collect_commands,
)


@register(
    "astrbot_plugin_qq_custom_command_panel",
    "mantoujun12",
    "将 AstrBot 已注册的指令同步到 QQ 官方机器人指令面板",
    "1.0.0",
    "https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel",
)
class QQCommandPanelPlugin(Star):
    """QQ 自定义指令面板插件入口。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # AstrBotConfig 继承自 Dict，这里只引用一份方便后续操作
        self.config = config
        # 持久化目录：AstrBot 提供的 data_dir
        # 各 AstrBot 版本可能字段名不同，做兼容处理
        self.data_dir = self._resolve_data_dir(context)
        self._http: aiohttp.ClientSession | None = None
        self._syncer: PanelSyncer | None = None

    @staticmethod
    def _resolve_data_dir(context: Context) -> Path:
        """兼容不同 AstrBot 版本获取 data_dir 的方式。"""
        for attr in ("get_data_dir", "data_dir"):
            getter = getattr(context, attr, None)
            if callable(getter):
                try:
                    return Path(getter())
                except Exception:
                    pass
            elif getter:
                return Path(getter)
        # 最后兜底
        return Path("data")

    async def initialize(self) -> None:
        """插件初始化：启动时同步一次面板。"""
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
            logger.error(f"[qq-command-panel] 启动同步失败: {exc}", exc_info=True)

    async def terminate(self) -> None:
        """插件销毁：关闭 HTTP 会话。"""
        if self._http and not self._http.closed:
            await self._http.close()
            self._http = None
        self._syncer = None

    # ------------------------------------------------------------------
    # 调试指令
    # ------------------------------------------------------------------

    @filter.command("qq_panel_resync")
    async def resync(self, event: AstrMessageEvent):
        """手动触发指令面板同步。"""
        if not self._syncer:
            yield event.plain_result("插件尚未初始化完成，请稍后再试")
            return
        self._syncer.set_config(dict(self.config))
        try:
            await self._syncer.sync_all()
            yield event.plain_result("✅ QQ 指令面板同步完成")
        except Exception as exc:
            yield event.plain_result(f"❌ 同步失败: {exc}")

    @filter.command("qq_panel_list")
    async def list_cmds(self, event: AstrMessageEvent):
        """列出当前 AstrBot 已注册的指令 (调试用)"""
        cmds = collect_commands()
        if not cmds:
            yield event.plain_result("未找到任何指令")
            return
        lines = [f"已注册指令 (最多展示 {PANEL_ITEM_MAX_ITEMS} 个):"]
        for c in cmds[:PANEL_ITEM_MAX_ITEMS]:
            lines.append(f"- {c['name']}: {c['desc']}")
        yield event.plain_result("\n".join(lines))


# 供 _conf_schema.json 中通过 template_list 使用
__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_MAX_ITEMS",
    "PANEL_ITEM_NAME_MAX",
    "SCENES",
    "QQCommandPanelPlugin",
]
