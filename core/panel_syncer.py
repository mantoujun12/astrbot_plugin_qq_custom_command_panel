"""将用户在 schema 中自定义的指令条目写入 QQ 官方机器人指令面板。"""

from __future__ import annotations

from typing import Any

import aiohttp
from astrbot.api import logger
from astrbot.api.star import Context

from .config import (
    PANEL_MAX_ITEMS,
    SCENES,
    get_configured_platforms,
    get_enabled_scenes,
    get_selected_commands,
)
from .qq_client import QQClient
from .state import PanelStateStore


class PanelSyncer:
    """负责把用户在 schema 里手动配置的指令条目写入 QQ 官方机器人面板。"""

    # 写入 QQ 面板 remark 字段的固定前缀, 用于在 sync 中识别本插件自建的面板 (做 update)。
    # purge 路径不再依赖该前缀 (直接删所有面板, 假设同一 appid 不会与其他插件共用)。
    REMARK_PREFIX = "[astrbot_plugin_qq_custom_command_panel]"

    def __init__(
        self,
        context: Context,
        http: aiohttp.ClientSession,
        data_dir: Any,
        config: dict[str, Any] | None = None,
    ):
        self.context = context
        self._http = http
        self._state = PanelStateStore(data_dir)
        # 引用一份当前插件配置；plugin 实例可在运行期通过 set_config 刷新
        self._config: dict[str, Any] = config or {}

    @staticmethod
    def is_owned_panel(panel: dict[str, Any]) -> bool:
        """判定一个面板是否由本插件创建 (依据 remark 前缀)。

        公开方法, 供 main.py 调试指令与 sync 内部共用, 避免"本插件面板"
        判定逻辑在多处各自实现导致策略漂移。
        """
        panel_content = panel.get("panel")
        if isinstance(panel_content, dict):
            remark = panel_content.get("remark") or ""
        else:
            # 兼容旧接口或测试数据里的扁平结构
            remark = panel.get("remark") or ""
        return isinstance(remark, str) and remark.startswith(PanelSyncer.REMARK_PREFIX)

    @staticmethod
    async def _safe_delete_panel(
        client: QQClient,
        panel_id: Any,
        scope: str,
        *,
        log_prefix: str = "清理面板",
    ) -> bool:
        """删除一个面板, 失败仅记录 warning 不抛出。

        多处清理流程 (sync_for_platform / clear_for_platform / purge_all) 共用,
        统一通过本方法删除, 避免重复 try/except/log 模板。
        """
        try:
            await client.delete_panel(str(panel_id))
            logger.info(
                f"[qq-command-panel] {log_prefix} scope={scope} panel_id={panel_id}"
            )
            return True
        except Exception as exc:
            logger.warning(f"[qq-command-panel] {log_prefix}失败: {exc}")
            return False

    def _build_clients(self) -> dict[str, QQClient]:
        """根据配置 (schema 优先, 否则 context) 构建所有 QQ 客户端。"""
        clients: dict[str, QQClient] = {}
        platforms, _source = get_configured_platforms(self._config, self.context)
        for pf_id, info in platforms.items():
            client = QQClient(
                appid=info["appid"],
                secret=info["secret"],
                http=self._http,
                platform_label=info.get("platform", "qq"),
            )
            clients[pf_id] = client
        return clients

    async def _list_all_panels(self, client: QQClient) -> list[dict[str, Any]]:
        """按所有支持场景逐个调用 list_panels 并合并结果。

        QQ API 要求 GET /v2/panels 必须传 scope, 所以需要循环请求一次。
        任一场景失败不影响其他场景, 最后汇总。
        """
        all_panels: list[dict[str, Any]] = []
        for scope in SCENES:
            try:
                panels = await client.list_panels(scope)
                all_panels.extend(panels)
            except Exception as exc:
                logger.warning(f"[qq-command-panel] 查询 {scope} 面板列表失败: {exc}")
        return all_panels

    def _owned_panels_by_scope(
        self,
        all_panels: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """把本插件 owned 的面板按 scope 分组, 供 sync_for_platform 比对使用。"""
        grouped: dict[str, dict[str, Any]] = {}
        for p in all_panels:
            if not self.is_owned_panel(p):
                continue
            scope = p.get("scope")
            if scope:
                grouped[scope] = p
        return grouped

    async def _sync_scope_panel(
        self,
        client: QQClient,
        pf_id: str,
        scope: str,
        items: list[dict[str, str]],
        remark: str,
        existing_panel: dict[str, Any] | None,
        total_panels: int,
    ) -> tuple[str | None, int]:
        """同步单个 scope 的面板: 优先 update 已有, 否则 create 新建。

        返回 (saved_panel_id_or_None, new_total_panels)。
        - saved_panel_id 为 None 表示该 scope 未写入 (上限达到 / 失败)
        - new_total_panels 反映本次新建后的总面板数 (用于上限判断)
        """
        if existing_panel is not None:
            panel_id = existing_panel.get("panel_id")
            if panel_id:
                await client.update_panel(panel_id, items, remark)
                logger.info(
                    f"[qq-command-panel] 更新面板 scope={scope} panel_id={panel_id}"
                )
                return str(panel_id), total_panels

        # QQ 限制: 一个机器人最多创建 PANEL_MAX_ITEMS 个面板.
        # 达到上限时仍允许更新已有面板, 仅阻止新建.
        if total_panels >= PANEL_MAX_ITEMS:
            logger.error(
                f"[qq-command-panel] 同步面板失败 scope={scope} [{pf_id}]: "
                f"已有 {total_panels} 个面板, 已达 QQ 上限 {PANEL_MAX_ITEMS}. "
                "请先执行 /qq_panel_purge 清理"
            )
            return None, total_panels

        panel_id = await client.create_panel(
            scope=scope,
            items=items,
            target_type="all",
            remark=remark,
        )
        logger.info(f"[qq-command-panel] 创建面板 scope={scope} panel_id={panel_id}")
        return panel_id, total_panels + 1

    async def sync_for_platform(
        self,
        pf_id: str,
        client: QQClient,
        scenes: list[str],
        items: list[dict[str, str]],
    ) -> dict[str, str]:
        """把用户在 schema 配置的 items 写入一个平台下所有场景的面板。

        返回 {scope: panel_id}。items 为空时清理该平台所有本插件面板。
        """
        platform = getattr(client, "platform_label", "qq")
        remark = f"{self.REMARK_PREFIX} {platform}/{pf_id}"

        try:
            all_existing = await self._list_all_panels(client)
        except Exception as exc:
            raise RuntimeError(f"查询面板列表失败: {exc}") from exc

        existing_by_scope = self._owned_panels_by_scope(all_existing)

        # items 为空: 清掉本插件在所有场景上的旧面板, 不创建新面板
        if not items:
            for scope, old in existing_by_scope.items():
                old_id = old.get("panel_id")
                if not old_id:
                    continue
                await self._safe_delete_panel(client, old_id, scope)
            return {}

        total_panels = len(all_existing)
        saved: dict[str, str] = {}
        for scope in scenes:
            try:
                saved_id, total_panels = await self._sync_scope_panel(
                    client,
                    pf_id,
                    scope,
                    items,
                    remark,
                    existing_by_scope.get(scope),
                    total_panels,
                )
                if saved_id is not None:
                    saved[scope] = saved_id
            except Exception as exc:
                logger.error(f"[qq-command-panel] 同步面板失败 scope={scope} [{pf_id}]: {exc}")

        # 仅清理本插件创建的、不再启用场景下的旧面板
        for scope, old in existing_by_scope.items():
            if scope in scenes:
                continue
            old_id = old.get("panel_id")
            if not old_id:
                continue
            await self._safe_delete_panel(
                client, old_id, scope, log_prefix="删除已停用场景面板"
            )

        return saved

    async def purge_all(self) -> dict[str, dict[str, str]]:
        """删除所有平台上**全部**指令面板, 并清空本地状态。

        因为同一 appid 不会有其他插件共用 `/v2/panels`, 所以直接删除全部面板,
        而不仅限于 remark 带前缀的本插件面板。返回每个平台删除后的剩余面板数。

        返回: {pf_id: {"remaining": N, "deleted": D}}
        """
        clients = self._build_clients()
        result: dict[str, dict[str, str]] = {}
        for pf_id, client in clients.items():
            try:
                all_panels = await self._list_all_panels(client)
            except Exception as exc:
                logger.error(
                    f"[qq-command-panel] purge 准备阶段查询 {pf_id} 面板失败: {exc}",
                    exc_info=True,
                )
                result[pf_id] = {"deleted": "?", "remaining": "?", "error": str(exc)}
                continue

            deleted = 0
            for p in all_panels:
                panel_id = p.get("panel_id")
                scope = p.get("scope", "?")
                if not panel_id:
                    continue
                ok = await self._safe_delete_panel(
                    client, panel_id, scope, log_prefix="purge 删除面板"
                )
                if ok:
                    deleted += 1

            # 删除后复查剩余
            remaining_count: Any = "?"
            try:
                remaining = await self._list_all_panels(client)
                remaining_count = len(remaining)
            except Exception as exc:
                logger.warning(f"[qq-command-panel] purge 后复查 {pf_id} 面板数失败: {exc}")

            result[pf_id] = {"deleted": str(deleted), "remaining": str(remaining_count)}

        # 清空本地持久化的 panel_id 映射
        self._state.save({})
        return result

    async def sync_all(self) -> dict[str, dict[str, str]]:
        """总入口: 把用户在 schema 中自定义的指令条目写入所有启用的 QQ 平台。

        返回 {pf_id: {scope: panel_id}}
        """
        scenes = get_enabled_scenes(self._config)
        if not scenes:
            logger.info("[qq-command-panel] 未启用任何场景，跳过同步")
            return {}

        # 直接读取用户在 schema 中自定义的指令条目, 不再扫描 AstrBot 已注册指令
        items = get_selected_commands(self._config)

        clients = self._build_clients()
        if not clients:
            logger.warning(
                "[qq-command-panel] 未找到任何 QQ 平台配置, "
                "请确认: 1) 已在 schema 的 qq_platforms 填写 appid+secret, "
                "或 2) AstrBot 后台已启用 qq_official / qq_official_webhook 平台适配器"
            )
            return {}

        if not items:
            logger.info("[qq-command-panel] selected_commands 为空, 清理所有本插件面板")
            for pf_id, client in clients.items():
                try:
                    await self.clear_for_platform(pf_id, client)
                except Exception as exc:
                    logger.error(
                        f"[qq-command-panel] 清理平台 {pf_id} 面板失败: {exc}",
                        exc_info=True,
                    )
            self._state.save({})
            return {}

        logger.info(f"[qq-command-panel] 准备写入 {len(items)} 个自定义指令条目到场景 {scenes}")

        result: dict[str, dict[str, str]] = {}
        for pf_id, client in clients.items():
            try:
                result[pf_id] = await self.sync_for_platform(pf_id, client, scenes, items)
            except Exception as exc:
                logger.error(f"[qq-command-panel] 同步平台 {pf_id} 失败: {exc}", exc_info=True)

        self._state.save(result)
        return result

    async def clear_for_platform(
        self,
        pf_id: str,
        client: QQClient,
    ) -> None:
        """删除该平台下本插件之前创建的所有面板 (用于指令清空时的清理)。"""
        all_existing = await self._list_all_panels(client)
        for p in all_existing:
            if not self.is_owned_panel(p):
                continue
            panel_id = p.get("panel_id")
            scope = p.get("scope", "?")
            if not panel_id:
                continue
            await self._safe_delete_panel(client, panel_id, scope)

    def set_config(self, config: dict[str, Any]) -> None:
        """运行期刷新配置引用。"""
        self._config = dict(config or {})


__all__ = ["PanelSyncer"]
