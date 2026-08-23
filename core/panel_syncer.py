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

    # 写入 QQ 面板 remark 字段的固定前缀, 用于识别本插件创建的面板,
    # 避免误改 / 误删用户或其他插件的面板
    REMARK_PREFIX = "[astrbot_plugin_qq_custom_command_panel]"

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
        # 记录每个 pf_id 下属于本插件的面板 id, 供下次比对
        self._owned: dict[str, dict[str, str]] = {}

    @staticmethod
    def _is_owned_panel(panel: dict[str, Any]) -> bool:
        """判定一个面板是否由本插件创建 (依据 remark 前缀)"""
        remark = panel.get("remark") or ""
        return isinstance(remark, str) and remark.startswith(PanelSyncer.REMARK_PREFIX)

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
        """同步一个平台下所有场景的面板，返回 {scope: panel_id}"""
        platform = getattr(client, "_platform_label", "qq")
        remark = f"{self.REMARK_PREFIX} {platform}/{pf_id}"

        # 查询面板列表失败时直接中止, 不要把现状当成空, 否则会重复创建面板
        try:
            all_existing = await client.list_panels()
        except Exception as exc:
            raise RuntimeError(f"查询面板列表失败: {exc}") from exc

        # 只把 remark 带本插件前缀的面板认作 "我创建的",
        # 这样既不会误改别人的面板, 也避免误删
        existing_by_scope: dict[str, dict[str, Any]] = {}
        for p in all_existing:
            if not self._is_owned_panel(p):
                continue
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
                logger.info(f"[qq-command-panel] 创建面板 scope={scope} panel_id={panel_id}")
                saved[scope] = panel_id
            except Exception as exc:
                logger.error(f"[qq-command-panel] 同步面板失败 scope={scope} [{pf_id}]: {exc}")

        # 仅清理本插件创建的、不再启用场景下的旧面板
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

    async def clear_for_platform(
        self,
        pf_id: str,
        client: QQClient,
    ) -> None:
        """删除该平台下本插件之前创建的所有面板 (用于指令清空时的清理)"""
        try:
            all_existing = await client.list_panels()
        except Exception as exc:
            logger.warning(f"[qq-command-panel] 查询面板列表失败 [{pf_id}]: {exc}")
            return

        for p in all_existing:
            if not self._is_owned_panel(p):
                continue
            panel_id = p.get("panel_id")
            scope = p.get("scope", "?")
            if not panel_id:
                continue
            try:
                await client.delete_panel(str(panel_id))
                logger.info(f"[qq-command-panel] 清理面板 scope={scope} panel_id={panel_id}")
            except Exception as exc:
                logger.warning(f"[qq-command-panel] 删除面板失败: {exc}")

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

        clients = self._build_clients()
        if not clients:
            logger.warning(
                "[qq-command-panel] 未找到任何启用的 qq_official / qq_official_webhook 平台配置，"
                "请确认已在 AstrBot 后台配置 QQ 官方机器人并启用。"
            )
            return {}

        # 加载历史 panel_id 映射 (用于日志和后续比对, 实际同步仍以服务端为准)
        self._owned = self._state.load()

        # 即使本次没有可同步的指令, 也要走一遍逻辑:
        # 1) 已启用的场景不要创建空面板 (避免 QQ 端出现空面板)
        # 2) 之前创建过的面板要清掉, 避免残留过期指令
        if not items:
            logger.info("[qq-command-panel] 没有可同步的指令, 清理之前创建的面板")
            for pf_id, client in clients.items():
                try:
                    await self.clear_for_platform(pf_id, client)
                except Exception as exc:
                    logger.error(
                        f"[qq-command-panel] 清理平台 {pf_id} 面板失败: {exc}",
                        exc_info=True,
                    )
            # 同步后清空持久化的 panel_id 映射
            self._state.save({})
            return {}

        logger.info(f"[qq-command-panel] 准备同步 {len(items)} 个指令到场景 {scenes}")

        result: dict[str, dict[str, str]] = {}
        for pf_id, client in clients.items():
            try:
                result[pf_id] = await self.sync_for_platform(pf_id, client, scenes, items)
            except Exception as exc:
                logger.error(f"[qq-command-panel] 同步平台 {pf_id} 失败: {exc}", exc_info=True)

        # 持久化本次结果到 data 目录
        self._state.save(result)
        self._owned = result
        return result

    def set_config(self, config: dict[str, Any]) -> None:
        """运行期刷新配置引用。"""
        self._config = dict(config or {})


__all__ = ["PanelSyncer"]
