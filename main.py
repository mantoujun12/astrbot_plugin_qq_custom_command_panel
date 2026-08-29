"""QQ 自定义指令面板插件

用户在 AstrBot WebUI 中通过 schema 的 `selected_commands` 字段手动配置要展示的指令条目,
本插件将用户在 schema 里写好的 {name, desc} 列表原样写入 QQ 官方机器人指令面板。
"""

from __future__ import annotations

from pathlib import Path

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Plain
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
    ProgressCallback,
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
    "v0.4.0",
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

    @staticmethod
    def _make_progress_pusher(event: AstrMessageEvent) -> ProgressCallback:
        """构造一个进度推送回调, 用 event.send 即时推送消息

        与 yield 不同, event.send 会在调用当下立即把消息发到会话,
        不必等 handler 结束才一次性返回所有 yield 结果。
        供 PanelSyncer.sync_all / purge_all 的 on_progress 参数使用。

        回调内异常由 PanelSyncer._emit_progress 兜底捕获 (仅 warning),
        这里不再重复 try/except, 避免双层吞错导致排查困难。
        """

        async def _push(msg: str) -> None:
            await event.send(MessageChain([Plain(msg)]))

        return _push

    # ------------------------------------------------------------------
    # 调试指令
    # ------------------------------------------------------------------

    @filter.command("qq_panel_resync")
    async def resync(self, event: AstrMessageEvent):
        """手动触发面板同步

        长任务指令: 通过 event.send 在每个平台完成时推送进度,
        最后 yield 汇总结果。sync_all 内部对回调异常兜底, 不会影响主流程。
        """
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return
        push = self._make_progress_pusher(event)
        try:
            result = await syncer.sync_all(on_progress=push)
        except Exception as exc:
            yield event.plain_result(t("cmd.sync_failed", exc=exc))
            return
        # sync_all 走清理路径 / 无场景 / 无平台时返回 {}, 此时退回通用成功文案
        if not result:
            yield event.plain_result(t("cmd.resync_success"))
            return
        # result 含成功 + 失败平台 (失败以 {"error": ...} 标记);
        # 摘要必须区分两者, 否则失败平台会被静默排除, 用户误以为全部成功
        total_platforms = len(result)
        succeeded = sum(1 for v in result.values() if "error" not in v)
        failed = total_platforms - succeeded
        total_scenes = sum(len(scopes) for scopes in result.values() if "error" not in scopes)
        if failed > 0:
            yield event.plain_result(
                t(
                    "cmd.resync_partial",
                    succeeded=succeeded,
                    failed=failed,
                    total=total_platforms,
                    scenes=total_scenes,
                )
            )
        else:
            yield event.plain_result(
                t("cmd.resync_summary", platforms=succeeded, scenes=total_scenes)
            )

    @filter.command("qq_panel_fetch")
    async def fetch_panels(self, event: AstrMessageEvent):
        """拉取所有 QQ 平台上已注册的指令面板"""
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return
        clients = syncer.build_clients()
        if not clients:
            yield event.plain_result(t("cmd.no_platform_detected"))
            return

        lines: list[str] = []
        total = 0
        for idx, (pf_id, client) in enumerate(clients.items()):
            platform = getattr(client, "platform_label", "qq")
            # 多平台输出之间用分隔线分段, 提升视觉层次
            if idx > 0:
                lines.append("─" * 36)
            try:
                panels, failed_scopes = await syncer.list_all_panels(client)
            except Exception as exc:
                lines.append(
                    t(
                        "cmd.fetch_platform_failed",
                        pf_id=pf_id,
                        platform=platform,
                        exc=exc,
                    )
                )
                continue

            if failed_scopes:
                lines.append(
                    t(
                        "cmd.fetch_incomplete_warning",
                        pf_id=pf_id,
                        platform=platform,
                        scopes=sorted(failed_scopes),
                    )
                )
            lines.append(
                t(
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
        lines.insert(1, "")
        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_show")
    async def show_panel(self, event: AstrMessageEvent):
        """查看单个面板的完整详情（含 scope / target_type / remark 等）"""
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return

        # 从事件纯文本中提取 panel_id 参数
        raw_text = getattr(event, "message_str", None)
        if not isinstance(raw_text, str):
            try:
                raw_text = str(event.message)
            except Exception:
                raw_text = ""
        tokens = raw_text.strip().split(maxsplit=1)
        panel_id = tokens[1].strip() if len(tokens) > 1 else ""
        if not panel_id:
            yield event.plain_result(t("cmd.show_panel_usage"))
            return

        clients = syncer.build_clients()
        if not clients:
            yield event.plain_result(t("cmd.no_platform_detected"))
            return

        lines: list[str] = []
        found: bool = False
        for pf_id, client in clients.items():
            platform = getattr(client, "platform_label", "qq")
            try:
                detail = await client.get_panel(panel_id)
            except Exception as exc:
                # panel_id 不属于这个 appid 会报 "not found" 之类的错误,
                # 属于正常情况, 不需要 warning 级别; 仅记录到 lines 供调试
                lines.append(
                    t(
                        "cmd.show_platform_error",
                        pf_id=pf_id,
                        platform=platform,
                        exc=exc,
                    )
                )
                continue
            # 查到就说明这个 panel_id 属于该 appid, 找到即停
            found = True
            lines.insert(
                0,
                t(
                    "cmd.show_header",
                    pf_id=pf_id,
                    platform=platform,
                    panel_id=panel_id,
                ),
            )
            scope = detail.get("scope", t("label.unavailable"))
            target_type = detail.get("target_type", t("label.unavailable"))
            lines.append(t("cmd.show_field_line", key="scope", value=scope))
            lines.append(t("cmd.show_field_line", key="target_type", value=target_type))
            owned = PanelSyncer.is_owned_panel(detail)
            lines.append(
                t(
                    "cmd.show_owned",
                    owned=t("label.plugin_owned") if owned else t("label.other"),
                )
            )
            panel_content = detail.get("panel")
            if isinstance(panel_content, dict):
                remark = panel_content.get("remark") or t("label.unavailable")
                lines.append(t("cmd.show_field_line", key="remark", value=remark))
                items = panel_content.get("items") or []
            else:
                items = detail.get("items") or []
            items_count = len(items) if isinstance(items, list) else "?"
            lines.append(t("cmd.show_items_header", count=items_count))
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    lines.append(
                        t(
                            "cmd.show_item_line",
                            name=it.get("name", "?"),
                            desc=it.get("desc", ""),
                        )
                    )
            break

        if not found:
            # 没找到时把每个平台的错误原因附在后面, 便于排错 (常见是 404 not_found)
            output = [t("cmd.show_not_found", panel_id=panel_id)]
            if lines:
                output.append("")
                output.extend(lines)
            yield event.plain_result("\n".join(output))
            return

        yield event.plain_result("\n".join(lines))

    @filter.command("qq_panel_purge")
    async def purge_panels(self, event: AstrMessageEvent):
        """删除所有 QQ 平台上全部指令面板

        因为同一 appid 不会有其他插件共用 /v2/panels, 所以不按 remark 过滤,
        直接清空该 appid 下所有面板, 然后清空本地状态。

        长任务指令: 通过 event.send 在每个平台完成时推送进度,
        最后 yield 汇总结果。
        """
        syncer = self._ready_syncer()
        if not syncer:
            yield event.plain_result(t("cmd.plugin_not_initialized"))
            return

        push = self._make_progress_pusher(event)
        try:
            result = await syncer.purge_all(on_progress=push)
        except Exception as exc:
            yield event.plain_result(t("cmd.purge_failed", exc=exc))
            return

        lines = [t("cmd.purge_done")]
        if not result:
            lines.append(t("cmd.no_platform_detected"))
        else:
            # 区分成功 / 部分失败平台 (purge_all 对部分场景查询失败的平台用
            # {"error": ...} 标记)。合计行只累加成功平台, 若存在部分失败平台,
            # 合计必须显式标注"仅成功平台", 否则用户会误以为是全平台总计。
            total_deleted = 0
            total_remaining = 0
            succeeded = 0
            partial = 0
            for pf_id, info in result.items():
                err = info.get("error")
                if err:
                    partial += 1
                    lines.append(t("cmd.purge_platform_failed", pf_id=pf_id, err=err))
                    continue
                succeeded += 1
                deleted = int(info["deleted"])
                remaining = int(info["remaining"])
                total_deleted += deleted
                total_remaining += remaining
                lines.append(
                    t(
                        "cmd.purge_platform_report",
                        pf_id=pf_id,
                        deleted=deleted,
                        remaining=remaining,
                    )
                )
            if len(result) > 1:
                if partial > 0:
                    lines.append(
                        t(
                            "cmd.purge_partial_total",
                            deleted=total_deleted,
                            remaining=total_remaining,
                            succeeded=succeeded,
                            partial=partial,
                        )
                    )
                else:
                    lines.append(
                        t("cmd.purge_total", deleted=total_deleted, remaining=total_remaining)
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
        lines = [t("cmd.list_header", count=len(cmds))]
        for c in cmds:
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
        self._apply_language()
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
