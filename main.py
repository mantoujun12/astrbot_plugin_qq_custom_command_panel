"""QQ 自定义指令面板插件

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
from .core.i18n import LOG_TAG, get_instance, t


@register(
    "astrbot_plugin_qq_custom_command_panel",
    "mantoujun12",
    "用户在 AstrBot WebUI 自定义 QQ 官方机器人指令面板内容",
    "v0.2.2",
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
            handlers_count = len(list(star_handlers_registry))
        except Exception as exc:
            handlers_count = t(
                "label.unavailable_with_reason",
                reason=str(exc),
            )
        logger.info(f"{LOG_TAG} " + t("log.initialize_handlers_count", count=handlers_count))
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

    # ------------------------------------------------------------------
    # 便捷 helper：避免每个指令里重复写 early-out
    # ------------------------------------------------------------------

    def _ready_syncer(self) -> PanelSyncer | None:
        """刷新配置并返回 syncer，未就绪返回 None"""
        if not self._syncer:
            return None
        self._syncer.set_config(dict(self.config))
        return self._syncer

    def _apply_language(self) -> None:
        """把当前配置里的 language 显式应用到全局翻译器

        `t()` 读取的是 core.i18n 的模块级单例, 这里主动同步一次配置语言,
        保证即使 syncer 尚未初始化, 只读指令也能在运行时修改 language
        后立即用新语言回复, 而不是沿用上一次的全局翻译器语言。
        """
        try:
            language = dict(self.config).get("language")
        except Exception:
            language = None
        get_instance().set_language(language)

    # ------------------------------------------------------------------
    # 调试指令
    # ------------------------------------------------------------------

    @filter.command("qq_panel_resync")
    async def resync(self, event: AstrMessageEvent):
        """手动触发面板同步"""
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return
        try:
            await syncer.sync_all()
            yield event.plain_result(t("cmd.resync_success"))
        except Exception as exc:
            yield event.plain_result(t("cmd.sync_failed", exc=exc))

    @filter.command("qq_panel_fetch")
    async def fetch_panels(self, event: AstrMessageEvent):
        """拉取所有 QQ 平台上已注册的指令面板"""
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return
        clients = syncer._build_clients()
        if not clients:
            yield event.plain_result(t("cmd.no_platform_detected"))
            return

        lines: list[str] = []
        total = 0
        for pf_id, client in clients.items():
            platform = getattr(client, "platform_label", "qq")
            try:
                panels, failed_scopes = await syncer._list_all_panels(client)
            except Exception as exc:
                lines.append(
                    "\n"
                    + t(
                        "cmd.fetch_platform_failed",
                        pf_id=pf_id,
                        platform=platform,
                        exc=exc,
                    )
                )
                continue

            if failed_scopes:
                lines.append(
                    "\n"
                    + t(
                        "cmd.fetch_incomplete_warning",
                        pf_id=pf_id,
                        platform=platform,
                        scopes=sorted(failed_scopes),
                    )
                )
            lines.append(
                "\n"
                + t(
                    "cmd.fetch_platform_summary",
                    pf_id=pf_id,
                    platform=platform,
                    count=len(panels),
                )
            )
            if not panels:
                lines.append(f"  {t('label.unavailable')}")
                continue
            for p in panels:
                panel_id = p.get("panel_id", "?")
                scope = p.get("scope", "?")
                panel_content = p.get("panel")
                if not isinstance(panel_content, dict):
                    panel_content = p
                owned = PanelSyncer.is_owned_panel(p)
                tag = f"🟢 {t('label.plugin_owned')}" if owned else f"⚪ {t('label.other')}"
                items = panel_content.get("items", []) or []
                if isinstance(items, list):
                    total += len(items)
                    items_count: str | int = len(items)
                else:
                    items_count = "?"
                lines.append(f"  - panel_id={panel_id} scope={scope} {tag} items={items_count}")
                if isinstance(items, list):
                    for it in items[:5]:
                        if not isinstance(it, dict):
                            continue
                        lines.append(f"      • {it.get('name', '?')}: {it.get('desc', '')}")
                    if len(items) > 5:
                        lines.append(t("cmd.fetch_truncated_items", count=len(items)))
        lines.insert(
            0,
            t("cmd.fetch_total_summary", platforms=len(clients), items=total),
        )
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_purge")
    async def purge_panels(self, event: AstrMessageEvent):
        """删除所有 QQ 平台上全部指令面板

        因为同一 appid 不会有其他插件共用 /v2/panels, 所以不按 remark 过滤,
        直接清空该 appid 下所有面板, 然后清空本地状态。
        """
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return

        try:
            result = await syncer.purge_all()
        except Exception as exc:
            yield event.plain_result(t("cmd.purge_failed", exc=exc))
            return

        lines = [t("cmd.purge_done")]
        if not result:
            lines.append(t("cmd.no_platform_detected"))
        for pf_id, info in result.items():
            err = info.get("error")
            if err:
                lines.append(t("cmd.purge_platform_failed", pf_id=pf_id, err=err))
            else:
                lines.append(
                    t(
                        "cmd.purge_platform_report",
                        pf_id=pf_id,
                        deleted=info.get("deleted", "?"),
                        remaining=info.get("remaining", "?"),
                    )
                )
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_list")
    async def list_cmds(self, event: AstrMessageEvent):
        """列出当前 AstrBot 已注册的指令

        该指令仅用于辅助用户填 schema 的 selected_commands,
        不会把列出的指令写入 QQ 面板。面板内容由用户在 schema 中自定义。
        """
        self._apply_language()
        cmds = collect_commands()
        if not cmds:
            yield event.plain_result(t("cmd.list_no_commands"))
            return
        lines = [t("cmd.list_header", limit=PANEL_MAX_ITEMS)]
        for c in cmds[:PANEL_MAX_ITEMS]:
            lines.append(f"- {c['name']}: {c['desc']}")
        lines.append("")
        lines.append(t("cmd.list_hint"))
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_platforms")
    async def debug_platforms(self, event: AstrMessageEvent):
        """打印插件识别到的 QQ 平台配置

        同时展示 schema (qq_platforms) 和 context 两种来源,
        用来排查 appid / secret 的识别问题。
        """
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return
        from_schema = get_platforms_from_schema(dict(self.config))
        from_context = get_platforms_from_context(self.context)
        active, source = get_configured_platforms(dict(self.config), self.context)

        def _fmt(platforms: dict) -> list[str]:
            if not platforms:
                return [f"  {t('label.unavailable')}"]
            out = []
            for pf_id, info in platforms.items():
                appid = info.get("appid", "")
                masked = appid[:4] + "***" + appid[-4:] if len(appid) > 8 else "***"
                secret_label = (
                    t("label.secret_set") if info.get("secret") else t("label.secret_empty")
                )
                out.append(
                    t(
                        "cmd.platforms_entry_line",
                        pf_id=pf_id,
                        platform=info.get("platform"),
                        appid=masked,
                        secret=secret_label,
                    )
                )
            return out

        lines = [
            t("cmd.platforms_active_source", source=source),
            t("cmd.platforms_active_count", count=len(active)),
            "",
            t("cmd.platforms_schema_header", count=len(from_schema)),
            *_fmt(from_schema),
            "",
            t("cmd.platforms_context_header", count=len(from_context)),
            *_fmt(from_context),
        ]
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_reload_check")
    async def debug_reload_check(self, event: AstrMessageEvent):
        """打印当前加载的代码路径和文件修改时间

        用来确认 AstrBot 是不是真的用了新版本的代码。
        """
        import inspect
        import os
        import time

        try:
            file_path = inspect.getfile(type(self))
        except Exception as exc:
            file_path = t("label.unavailable_with_reason", reason=str(exc))

        try:
            mtime = os.path.getmtime(file_path)
            mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        except Exception as exc:
            mtime_str = t("label.unavailable_with_reason", reason=str(exc))

        lines = [
            t(
                "cmd.reload_current_class_line",
                module=type(self).__module__,
                cls=type(self).__name__,
            ),
            t("cmd.reload_file_path_line", path=file_path),
            t("cmd.reload_mtime_line", mtime=mtime_str),
        ]
        yield event.plain_result("\n".join(lines))


__all__ = [
    "DEFAULT_SCENES",
    "PANEL_ITEM_DESC_MAX",
    "PANEL_ITEM_NAME_MAX",
    "PANEL_MAX_ITEMS",
    "SCENES",
    "QQCommandPanelPlugin",
]
