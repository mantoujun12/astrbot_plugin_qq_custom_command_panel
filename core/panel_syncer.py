"""同步 AstrBot 指令到 QQ 官方机器人指令面板"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import logger
from astrbot.api.star import Context

from .command_collector import collect_commands, filter_commands
from .config import (
    get_enabled_scenes,
    get_platforms_from_context,
    get_selected_commands,
)
from .qq_client import QQClient
from .state import PanelStateStore


class PanelSyncer:
    """负责把指令同步到 QQ 官方机器人面板"""

    def __init__(
        self,
        context: Context,
        http: aiohttp.ClientSession,
        data_dir: Path | str,
        config: dict[str, Any] | None = None,
    ):
        self.context = context
        self._http = http
        self._state = PanelStateStore(data_dir)
        # 引用一份当前插件配置；plugin 实例可在运行期通过 set_config 刷新
        self._config: dict[str, Any] = config or {}

    def _build_clients(self) -> dict[str, QQClient]:
        """根据 AstrBot 平台配置构建所有 QQ 客户端。"""
        clients: dict[str, QQClient] = {}
        for pf_id, info in get_platforms_from_context(self.context).items():
            client = QQClient(
                appid=info["appid"],
                secret=info["secret"],
                http=self._http,
            )
            # 给 client 打一个 platform 标签，方便生成 remark
            client._platform_label = info.get("platform", "qq")  # type: ignore[attr-defined]
            clients[pf_id] = client
        return clients

    async def sync_for_platform(
        self,
        pf_id: str,
        client: QQClient,
        scenes: list[str],
        items: list[dict[str, str]],
    ) -> dict[str, str]:
        """同步一个平台下所有场景的面板，返回 {scope: panel_id}。"""
        platform = getattr(client, "_platform_label", "qq")
        remark = f"{platform}/{pf_id} 由 astrbot_plugin_qq_custom_command_panel 同步"

        try:
            existing = await client.list_panels()
        except Exception as exc:
            logger.warning(f"[qq-command-panel] 查询面板列表失败 [{pf_id}]: {exc}")
            existing = []

        existing_by_scope: dict[str, dict[str, Any]] = {}
        for p in existing:
            scope = p.get("scope")
            if scope:
                existing_by_scope[scope] = p

        saved: dict[str, str] = {}
        for scope in scenes:
            try:
                if scope in existing_by_scope:
                    old = existing_by_scope[scope]
                    panel_id = old.get("panel_id")
                    if panel_id:
                        await client.update_panel(panel_id, items, remark)
                        logger.info(
                            f"[qq-command-panel] 更新面板 scope={scope} panel_id={panel_id}"
                        )
                        saved[scope] = str(panel_id)
                        continue
                panel_id = await client.create_panel(
                    scope=scope,
                    items=items,
                    target_type="all",
                    remark=remark,
                )
                logger.info(
                    f"[qq-command-panel] 创建面板 scope={scope} panel_id={panel_id}"
                )
                saved[scope] = panel_id
            except Exception as exc:
                logger.error(
                    f"[qq-command-panel] 同步面板失败 scope={scope} [{pf_id}]: {exc}"
                )

        # 清理已停用场景的旧面板
        for scope, old in existing_by_scope.items():
            if scope in scenes:
                continue
            old_id = old.get("panel_id")
            if not old_id:
                continue
            try:
                await client.delete_panel(str(old_id))
                logger.info(
                    f"[qq-command-panel] 删除已停用场景面板 scope={scope} panel_id={old_id}"
                )
            except Exception as exc:
                logger.warning(f"[qq-command-panel] 删除旧面板失败: {exc}")

        return saved

    async def sync_all(self) -> dict[str, dict[str, str]]:
        """总入口：同步所有启用的 QQ 平台

        返回 {pf_id: {scope: panel_id}}
        """
        scenes = get_enabled_scenes(self._config)
        if not scenes:
            logger.info("[qq-command-panel] 未启用任何场景，跳过同步")
            return {}

        all_cmds = collect_commands()
        items = filter_commands(all_cmds, get_selected_commands(self._config))
        if not items:
            logger.info("[qq-command-panel] 没有可同步的指令")
            return {}

        logger.info(f"[qq-command-panel] 准备同步 {len(items)} 个指令到场景 {scenes}")

        clients = self._build_clients()
        if not clients:
            logger.warning(
                "[qq-command-panel] 未找到任何启用的 qq_official / qq_official_webhook 平台配置，"
                "请确认已在 AstrBot 后台配置 QQ 官方机器人并启用。"
            )
            return {}

        # 读取已持久化的 panel_id 映射 (仅用作后续比对 / 调试参考,
        # 当前同步策略以 QQ 服务端查询结果为准)
        self._state.load()

        result: dict[str, dict[str, str]] = {}
        for pf_id, client in clients.items():
            try:
                result[pf_id] = await self.sync_for_platform(pf_id, client, scenes, items)
            except Exception as exc:
                logger.error(
                    f"[qq-command-panel] 同步平台 {pf_id} 失败: {exc}", exc_info=True
                )

        # 持久化本次结果到 data 目录
        self._state.save(result)
        return result

    def set_config(self, config: dict[str, Any]) -> None:
        """运行期刷新配置引用。"""
        self._config = dict(config or {})


__all__ = ["PanelSyncer"]
