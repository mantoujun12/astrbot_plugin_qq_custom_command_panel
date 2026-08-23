"""QQ 自定义指令面板插件。

用户在 AstrBot WebUI 中通过 schema 的 `selected_commands` 字段手动配置要展示的指令条目,
本插件将用户在 schema 里写好的 {name, desc} 列表原样写入 QQ 官方机器人指令面板。
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
    get_configured_platforms,
    get_platforms_from_context,
    get_platforms_from_schema,
)


@register(
    "astrbot_plugin_qq_custom_command_panel",
    "mantoujun12",
    "在 QQ 官方机器人指令面板里展示用户在 AstrBot WebUI 中自定义配置的指令条目",
    "0.2.0",
    "https://github.com/mantoujun12/astrbot_plugin_qq_custom_command_panel",
)
class QQCommandPanelPlugin(Star):
    """QQ 自定义指令面板插件入口。"""

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
        """手动触发面板同步。"""
        if not self._syncer:
            yield event.plain_result("插件尚未初始化完成，请稍后再试")
            return
        self._syncer.set_config(dict(self.config))
        try:
            await self._syncer.sync_all()
            yield event.plain_result("✅ QQ 指令面板同步完成")
        except Exception as exc:
            yield event.plain_result(f"❌ 同步失败: {exc}")

    @filter.command("qq_panel_fetch")
    async def fetch_panels(self, event: AstrMessageEvent):
        """拉取所有 QQ 平台上已注册的指令面板 (调试用)。"""
        if not self._syncer:
            yield event.plain_result("插件尚未初始化完成，请稍后再试")
            return
        self._syncer.set_config(dict(self.config))
        clients = self._syncer._build_clients()
        if not clients:
            yield event.plain_result(
                "未识别到任何 QQ 平台 (请检查 schema qq_platforms 或 context 平台配置)"
            )
            return

        lines: list[str] = []
        total = 0
        for pf_id, client in clients.items():
            platform = getattr(client, "platform_label", "qq")
            try:
                panels = await self._syncer._list_all_panels(client)
            except Exception as exc:
                lines.append(f"\n[{pf_id}] ({platform}) 拉取失败: {exc}")
                continue

            lines.append(f"\n[{pf_id}] ({platform}) 共 {len(panels)} 个面板:")
            if not panels:
                lines.append("  <无>")
                continue
            for p in panels:
                panel_id = p.get("panel_id", "?")
                scope = p.get("scope", "?")
                panel_content = p.get("panel")
                if not isinstance(panel_content, dict):
                    panel_content = p
                owned = PanelSyncer.is_owned_panel(p)
                tag = "🟢 本插件" if owned else "⚪ 其他"
                items = panel_content.get("items", []) or []
                if isinstance(items, list):
                    total += len(items)
                    items_count = len(items)
                else:
                    items_count = "?"
                lines.append(f"  - panel_id={panel_id} scope={scope} {tag} items={items_count}")
                if isinstance(items, list):
                    for it in items[:5]:
                        if not isinstance(it, dict):
                            continue
                        lines.append(f"      • {it.get('name', '?')}: {it.get('desc', '')}")
                    if len(items) > 5:
                        lines.append(f"      • ... 共 {len(items)} 条")
        lines.insert(0, f"全平台汇总: 共 {len(clients)} 个平台, {total} 条指令条目")
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_purge")
    async def purge_panels(self, event: AstrMessageEvent):
        """删除所有 QQ 平台上**全部**指令面板 (调试用)。

        因为同一 appid 不会有其他插件共用 /v2/panels, 所以不按 remark 过滤,
        直接清空该 appid 下所有面板, 然后清空本地状态。
        """
        if not self._syncer:
            yield event.plain_result("插件尚未初始化完成，请稍后再试")
            return
        self._syncer.set_config(dict(self.config))

        try:
            result = await self._syncer.purge_all()
        except Exception as exc:
            yield event.plain_result(f"❌ purge 失败: {exc}")
            return

        lines = ["🧹 清理完成"]
        if not result:
            lines.append("未识别到任何 QQ 平台 (请检查 schema qq_platforms 或 context 平台配置)")
        for pf_id, info in result.items():
            err = info.get("error")
            if err:
                lines.append(f"- [{pf_id}] 失败: {err}")
            else:
                lines.append(
                    f"- [{pf_id}] 删除 {info.get('deleted', '?')} 个, "
                    f"剩余 {info.get('remaining', '?')} 个"
                )
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_list")
    async def list_cmds(self, event: AstrMessageEvent):
        """列出当前 AstrBot 已注册的指令 (调试用)。

        该指令仅用于辅助用户填 schema 的 selected_commands,
        不会把列出的指令写入 QQ 面板。面板内容由用户在 schema 中自定义。
        """
        cmds = collect_commands()
        if not cmds:
            yield event.plain_result("未找到任何指令")
            return
        lines = [f"已注册指令 (最多展示 {PANEL_MAX_ITEMS} 个):"]
        for c in cmds[:PANEL_MAX_ITEMS]:
            lines.append(f"- {c['name']}: {c['desc']}")
        lines.append("")
        lines.append("提示: 该列表仅作参考, 面板内容由 schema 的 selected_commands 配置决定。")
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_platforms")
    async def debug_platforms(self, event: AstrMessageEvent):
        """调试: 打印插件识别到的 QQ 平台配置。

        同时展示 schema (qq_platforms) 和 context 两种来源,
        用来排查 appid / secret 的识别问题。
        """
        from_schema = get_platforms_from_schema(dict(self.config))
        from_context = get_platforms_from_context(self.context)
        active, source = get_configured_platforms(dict(self.config), self.context)

        def _fmt(platforms: dict) -> list[str]:
            if not platforms:
                return ["  <无>"]
            out = []
            for pf_id, info in platforms.items():
                appid = info.get("appid", "")
                masked = appid[:4] + "***" + appid[-4:] if len(appid) > 8 else "***"
                out.append(
                    f"  - pf_id={pf_id}, platform={info.get('platform')}, "
                    f"appid={masked}, secret={'<set>' if info.get('secret') else '<empty>'}"
                )
            return out

        lines = [
            f"生效来源: {source}",
            f"生效平台数: {len(active)}",
            "",
            f"[schema] qq_platforms ({len(from_schema)}):",
            *_fmt(from_schema),
            "",
            f"[context] platform_settings ({len(from_context)}):",
            *_fmt(from_context),
        ]
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_reload_check")
    async def debug_reload_check(self, event: AstrMessageEvent):
        """调试: 打印当前加载的代码路径和文件修改时间。

        用来确认 AstrBot 是不是真的用了新版本的代码。
        """
        import inspect
        import os
        import time

        try:
            file_path = inspect.getfile(type(self))
        except Exception as exc:
            file_path = f"<无法获取: {exc}>"

        try:
            mtime = os.path.getmtime(file_path)
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        except Exception as exc:
            mtime_str = f"<无法获取: {exc}>"

        yield event.plain_result(
            f"当前类: {type(self).__module__}.{type(self).__name__}\n"
            f"文件路径: {file_path}\n"
            f"文件修改时间: {mtime_str}"
        )


__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "QQCommandPanelPlugin",
]
