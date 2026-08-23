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
from astrbot.core.star.star_handler import star_handlers_registry

from .core import (
    DEFAULT_SCENES,
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    SCENES,
    PanelSyncer,
    collect_commands,
)


@register(
    "astrbot_plugin_qq_custom_command_panel",
    "mantoujun12",
    "将 AstrBot 已注册的指令同步到 QQ 官方机器人指令面板",
    "0.1.1",
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
                except Exception as exc:
                    logger.debug(f"[qq-command-panel] {attr}() 调用失败: {exc}")
            elif getter:
                return Path(getter)
        # 最后兜底
        return Path("data")

    async def initialize(self) -> None:
        """插件初始化: 启动时同步一次面板。"""
        self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self._syncer = PanelSyncer(
            self.context,
            self._http,
            data_dir=self.data_dir,
            config=dict(self.config),
        )
        # 调试日志: 启动时注册表里有多少 handler
        # 如果是 0, 说明初始化时机太早, 需要延迟同步
        try:
            handlers_count = len(list(star_handlers_registry))
        except Exception as exc:
            handlers_count = f"<无法读取: {exc}>"
        logger.info(f"[qq-command-panel] initialize: star_handlers_registry 长度={handlers_count}")
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
        lines = [f"已注册指令 (最多展示 {PANEL_MAX_ITEMS} 个):"]
        for c in cmds[:PANEL_MAX_ITEMS]:
            lines.append(f"- {c['name']}: {c['desc']}")
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_debug")
    async def debug_handlers(self, event: AstrMessageEvent):
        """调试: 打印 star_handlers_registry 里每个 handler 的关键属性

        用来排查为什么 collect_commands() 没拿到指令。
        """
        # star_handlers_registry 是 StarHandlerRegistry 对象,
        # 只支持迭代, 不支持下标; 先转成 list 避免索引报错
        try:
            handlers = list(star_handlers_registry)
        except Exception as exc:
            yield event.plain_result(f"无法读取 star_handlers_registry: {exc}")
            return

        lines = [
            f"star_handlers_registry 总数: {len(handlers)}",
            f"registry 类型: {type(star_handlers_registry).__name__}",
        ]
        for idx, h in enumerate(handlers[:10]):
            event_type = getattr(h, "event_type", None)
            cmd_name = getattr(h, "cmd_name", None)
            command_name = getattr(h, "command_name", None)
            desc = getattr(h, "desc", None)
            description = getattr(h, "description", None)
            type_name = type(h).__name__
            # 拿到 handler 的真实函数对象, 取 docstring
            func = getattr(h, "handler", None) or getattr(h, "func", None)
            doc = getattr(func, "__doc__", None) if func else None
            doc_first = doc.strip().split("\n", 1)[0].strip() if doc else None

            lines.append(
                f"\n#{idx} type={type_name}\n"
                f"  event_type={event_type!r}\n"
                f"  cmd_name={cmd_name!r}\n"
                f"  command_name={command_name!r}\n"
                f"  desc={desc!r}\n"
                f"  description={description!r}\n"
                f"  doc_first={doc_first!r}"
            )

        # 顺便打印一下 context.platform_settings 的结构, 方便排查平台配置读取
        platform_settings = getattr(self.context, "platform_settings", None)
        if isinstance(platform_settings, list):
            lines.append(f"\nplatform_settings 数: {len(platform_settings)}")
            for i, pf in enumerate(platform_settings):
                if i >= 5:
                    lines.append("  ...")
                    break
                # 只展示字段名 + 类型, 不打印 secret
                if isinstance(pf, dict):
                    keys = sorted(k for k in pf.keys() if "secret" not in k.lower())
                    pf_platform = pf.get("platform")
                    lines.append(f"  #{i} keys={keys}, platform={pf_platform!r}")
                else:
                    lines.append(f"  #{i} <non-dict: {type(pf).__name__}>")
        else:
            lines.append(f"\nplatform_settings 不是 list, 类型={type(platform_settings).__name__}")

        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_platforms")
    async def debug_platforms(self, event: AstrMessageEvent):
        """调试: 打印插件识别到的 QQ 平台配置

        用来排查 get_platforms_from_context 是否正确读取到 appid / secret。
        """
        from .core.config import get_platforms_from_context

        platforms = get_platforms_from_context(self.context)
        if not platforms:
            yield event.plain_result("未识别到任何 QQ 平台配置")
            return
        lines = [f"识别到 {len(platforms)} 个 QQ 平台配置:"]
        for pf_id, info in platforms.items():
            # 不打印 secret 明文
            appid = info.get("appid", "")
            masked = appid[:4] + "***" + appid[-4:] if len(appid) > 8 else "***"
            lines.append(
                f"- pf_id={pf_id}, platform={info.get('platform')}, "
                f"appid={masked}, secret={'<set>' if info.get('secret') else '<empty>'}"
            )
        yield event.plain_result("\n".join(lines))


# 供 _conf_schema.json 中通过 template_list 使用
__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "QQCommandPanelPlugin",
]
