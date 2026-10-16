"""将用户在 schema 中自定义的指令条目写入 QQ 官方机器人指令面板"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import logger
from astrbot.api.star import Context

from .config import (
    PANEL_MAX_ITEMS,
    SCENES,
    get_enabled_scenes,
    normalize_panel_items,
)
from .i18n import DEFAULT_LANGUAGE, LOG_TAG, Translator, initialize, t
from .qq_client import QQClient
from .robot_config import ROBOT_CONFIG_FILENAME, build_runtime_robots, load_robot_config
from .state import PanelStateStore

# 面板操作的并发上限。QQ 官方 API 有限流 (HTTP 429)，
# 单个 appid 同时发太多请求会被短暂封禁，这里留一个保守的默认值。
DEFAULT_PANEL_OP_CONCURRENCY = 5

# 进度回调：接收一条格式化好的进度消息字符串，由调用方决定如何展示
# （例如 main.py 里用 event.send() 推送给用户）。
# syncer 会在每个平台完成时调用；回调内异常不影响主流程，仅 warning。
ProgressCallback = Callable[[str], Awaitable[None]]

# 结构化事件回调：供 dashboard 渲染进度条 / 平台状态列表
# 与 ProgressCallback 并行存在：文本进日志，结构化事件进可视化
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class PanelSyncError(RuntimeError):
    """某个机器人有场景写入失败

    携带已成功写入的 ``{scope: panel_id}``，调用方据此标记平台失败的同时
    仍能持久化已完成部分。整轮同步因场景查询失败而中止时抛普通 RuntimeError。
    """

    def __init__(self, message: str, saved: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.saved: dict[str, str] = dict(saved or {})


class PanelSyncer:
    """负责把用户在 schema 里手动配置的指令条目写入 QQ 官方机器人面板"""

    # 写入 QQ 面板 remark 字段的固定前缀，用于在 sync 中识别本插件自建的面板（做 update）。
    # purge 路径不再依赖该前缀（直接删所有面板，假设同一 appid 不会与其他插件共用）。
    REMARK_PREFIX = "[astrbot_plugin_qq_custom_command_panel]"

    def __init__(
        self,
        context: Context,
        http: aiohttp.ClientSession,
        data_dir: Any,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.context = context
        self._http = http
        self._data_dir = Path(data_dir)
        self._state = PanelStateStore(data_dir)
        # 引用一份当前插件配置；plugin 实例可在运行期通过 set_config 刷新
        self._config: dict[str, Any] = config or {}

        # 初始化 i18n 单例（运行时翻译数据放在 core/i18n/，
        # 不要和 .astrbot-plugin/i18n/（WebUI 专用，嵌套结构）混淆）。
        locales_dir = Path(__file__).resolve().parent / "i18n"
        language = (self._config or {}).get("language", DEFAULT_LANGUAGE)
        self.translator: Translator = initialize(locales_dir, language)

    @staticmethod
    def is_owned_panel(panel: dict[str, Any]) -> bool:
        """判定一个面板是否由本插件创建（依据 remark 前缀）

        公开方法，供 sync / clear / purge 内部共用，避免“本插件面板”
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
        log_prefix: str = "log_prefix.clean_panel",
    ) -> bool:
        """删除一个面板，失败仅记录 warning 不抛出

        多处清理流程 (sync_for_platform / clear_for_platform / purge_all) 共用，
        统一通过本方法删除，避免重复 try/except/log 模板。

        `log_prefix` 接收翻译 key（形如 "log_prefix.xxx"），调用 t() 实际取值。
        """
        try:
            await client.delete_panel(str(panel_id))
            logger.info(
                f"{LOG_TAG} "
                + t(
                    "log.panel_action_scope",
                    action=t(log_prefix),
                    scope=scope,
                    panel_id=panel_id,
                )
            )
            return True
        except Exception as exc:
            logger.warning(
                f"{LOG_TAG} " + t("log.panel_action_failed", action=t(log_prefix), exc=exc)
            )
            return False

    @staticmethod
    async def _run_concurrent(
        coros: list[Coroutine[Any, Any, Any]],
        *,
        limit: int = DEFAULT_PANEL_OP_CONCURRENCY,
    ) -> list[Any]:
        """并发执行一组协程，带限流信号量，返回与输入同序的结果列表

        用于删除面板、场景同步、清理等独立操作的批量加速。
        返回值保留原始结果（含 Exception），由调用方决定是否处理异常。
        """
        if not coros:
            return []

        sem = asyncio.Semaphore(limit)

        async def _wrap(coro: Coroutine[Any, Any, Any]) -> Any:
            async with sem:
                return await coro

        return list(await asyncio.gather(*[_wrap(c) for c in coros], return_exceptions=True))

    @staticmethod
    async def _emit_progress(
        on_progress: ProgressCallback | None,
        message: str,
    ) -> None:
        """安全触发进度回调，异常仅记录 warning 不影响主流程

        回调失败常见原因：平台适配器不支持 event.send / 网络问题 / 用户会话已关闭。
        这些都不应让正在进行的 sync/purge 中止，因此吞掉异常仅记录。
        """
        if on_progress is None:
            return
        try:
            await on_progress(message)
        except Exception as exc:
            logger.warning(f"{LOG_TAG} progress callback failed: {exc}")

    @staticmethod
    async def _emit_event(
        on_event: EventCallback | None,
        event: dict[str, Any],
    ) -> None:
        """安全触发结构化事件回调，异常仅记录 warning 不影响主流程"""
        if on_event is None:
            return
        try:
            await on_event(event)
        except Exception as exc:
            logger.warning(f"{LOG_TAG} event callback failed: {exc}")

    def build_runtime_robots(
        self,
        config: dict[str, Any] | None = None,
        *,
        robot_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """合并新版机器人和兼容配置，返回统一的运行时机器人列表

        新版按 appid 优先接管，未被接管的旧机器人沿用全局 ``scenes`` 与
        ``selected_commands``；新版 JSON 读取失败抛 :class:`RobotConfigError`，
        由调用方决定如何展示错误，不做静默回退。
        """
        source_config = self._config if config is None else config
        v2_config = robot_config
        if v2_config is None:
            v2_config = load_robot_config(self._data_dir)
        return build_runtime_robots(source_config, v2_config)

    def build_clients(
        self,
        config: dict[str, Any] | None = None,
        *,
        robot_config: dict[str, Any] | None = None,
    ) -> dict[str, QQClient]:
        """根据新版机器人 + 兼容配置构建所有 QQ 客户端

        公开方法，供 sync / clear / purge 流程共用。`config` 用于按调用方提供的
        配置构建，不传时用 syncer 当前持有的配置；视图状态接口会传入当前插件配置，
        保证客户端与响应里的平台元数据同源。
        """
        clients: dict[str, QQClient] = {}
        for robot in self.build_runtime_robots(config, robot_config=robot_config):
            pf_id = str(robot.get("id") or robot.get("appid") or "")
            appid = str(robot.get("appid") or "")
            secret = str(robot.get("secret") or "")
            if not pf_id or not appid or not secret:
                continue
            client = QQClient(
                appid=appid,
                secret=secret,
                http=self._http,
                platform_label=str(robot.get("platform") or "qq"),
            )
            clients[pf_id] = client
        return clients

    async def list_all_panels(
        self,
        client: QQClient,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """按所有支持场景逐个调用 list_panels 并合并结果

        QQ API 要求 GET /v2/panels 必须传 scope，所以需要循环请求一次。
        任一场景失败不抛出，但会记录到 failed_scopes 集合并 warning，
        调用方据此判断返回的 panels 是否完整 — 否则缺失场景会被
        sync_for_platform 误判为“无现有面板”而创建重复面板。

        返回：(panels, failed_scopes)
            panels         - 跨场景合并后的面板列表（可能不完整）
            failed_scopes  - 查询失败的场景集合；为空表示清单完整
        """
        all_panels: list[dict[str, Any]] = []
        failed_scopes: set[str] = set()
        for scope in SCENES:
            try:
                panels = await client.list_panels(scope)
                all_panels.extend(panels)
            except Exception as exc:
                logger.warning(
                    f"{LOG_TAG} {t('log.list_scope_panels_failed', scope=scope, exc=exc)}"
                )
                failed_scopes.add(scope)
        return all_panels, failed_scopes

    def owned_panels_by_scope(
        self,
        all_panels: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """把本插件 owned 的面板按 scope 分组，每个 scope 保留全部记录（维持原顺序）

        公开方法：sync_for_platform 用每个 scope 的第一条做 update 判断，视图状态
        接口据此识别「同一场景存在多条本插件面板」的重复情况。保留全部而非只留一条，
        否则重复面板会被静默吞掉，调用方也无从发现配置异常。
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for p in all_panels:
            if not self.is_owned_panel(p):
                continue
            scope = p.get("scope")
            if scope:
                grouped.setdefault(scope, []).append(p)
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
        """同步单个 scope 的面板：优先 update 已有，否则 create 新建

        返回 (saved_panel_id_or_None, new_total_panels)。
        - saved_panel_id 为 None 表示该 scope 未写入（上限达到 / 失败）
        - new_total_panels 反映本次新建后的总面板数（用于上限判断）
        """
        if existing_panel is not None:
            panel_id = existing_panel.get("panel_id")
            if panel_id:
                await client.update_panel(panel_id, items, remark)
                logger.info(f"{LOG_TAG} " + t("log.update_panel", scope=scope, panel_id=panel_id))
                return str(panel_id), total_panels

        # QQ 限制：一个机器人最多创建 PANEL_MAX_ITEMS 个面板。
        # 达到上限时仍允许更新已有面板，仅阻止新建。
        if total_panels >= PANEL_MAX_ITEMS:
            logger.error(
                f"{LOG_TAG} "
                + t(
                    "log.panel_limit_reached",
                    scope=scope,
                    pf_id=pf_id,
                    total=total_panels,
                    limit=PANEL_MAX_ITEMS,
                )
            )
            return None, total_panels

        panel_id = await client.create_panel(
            scope=scope,
            items=items,
            target_type="all",
            remark=remark,
        )
        logger.info(f"{LOG_TAG} " + t("log.create_panel", scope=scope, panel_id=panel_id))
        return panel_id, total_panels + 1

    async def sync_for_platform(
        self,
        pf_id: str,
        client: QQClient,
        scenes: dict[str, list[dict[str, str]]] | list[str],
        items: list[dict[str, str]] | None = None,
    ) -> dict[str, str]:
        """把一个机器人各场景的指令条目写入对应 QQ 面板

        新版调用传 ``{scope: items}``，各场景条目独立；旧调用仍可传 ``scenes`` 列表
        加一份共享 ``items``。只同步条目非空的场景，未出现的场景则清理本插件在该场景的旧面板。
        条目统一补齐 QQ API 要求的 type 字段后写出。
        返回 {scope: panel_id}；有场景写入失败时抛 :class:`PanelSyncError`
        （异常上的 ``saved`` 保留已成功的场景），不再静默当成成功。
        """
        if isinstance(scenes, list):
            shared = items or []
            scenes = {scope: shared for scope in scenes if scope in SCENES}
        # 配置里只存 name / desc，写出前补齐 type，避免 QQ 返回 30015 面板元素类型不合法
        scenes = {
            scope: normalize_panel_items(raw_items)
            for scope, raw_items in scenes.items()
            if scope in SCENES
        }
        platform = getattr(client, "platform_label", "qq")
        remark = f"{self.REMARK_PREFIX} {platform}/{pf_id}"

        active_scenes = [scope for scope in SCENES if scenes.get(scope)]
        all_existing, failed_scopes = await self.list_all_panels(client)
        # 任一场景查询失败时清单不完整，直接中止协调 — 否则缺失场景会被
        # 误判为“无现有面板”而创建重复面板，或跳过旧面板的清理。
        if failed_scopes:
            raise RuntimeError(
                t(
                    "panel.incomplete_list_retry",
                    scopes=sorted(failed_scopes),
                )
            )

        existing_by_scope = self.owned_panels_by_scope(all_existing)
        total_panels = len(all_existing)
        saved: dict[str, str] = {}
        failures: dict[str, str] = {}

        # ---------- 场景同步：分 update 并发 + create 串行 ----------
        # 已有面板的 scope 走 update 路径：不会修改 total_panels，相互独立可并发
        # 无面板的 scope 走 create 路径：会递增 total_panels，需要串行保证上限判断准确
        update_scopes: list[str] = []
        create_scopes: list[str] = []
        for scope in active_scenes:
            if existing_by_scope.get(scope):
                update_scopes.append(scope)
            else:
                create_scopes.append(scope)

        # (1) update 路径并发：每个 scope 独立 try/except，失败不影响其他
        async def _sync_update_scope(scope: str) -> tuple[str, str | None, str | None]:
            """返回 (scope, saved_id_or_None, error_or_None)，异常时打 error 日志"""
            try:
                # 同一 scope 有多条 owned 面板时只更新第一条，多余的由视图标记为 duplicate
                saved_id, _ = await self._sync_scope_panel(
                    client,
                    pf_id,
                    scope,
                    scenes[scope],
                    remark,
                    existing_by_scope[scope][0],
                    total_panels,
                )
                return scope, saved_id, None
            except Exception as exc:
                logger.error(
                    f"{LOG_TAG} " + t("log.sync_scope_failed", scope=scope, pf_id=pf_id, exc=exc)
                )
                return scope, None, str(exc)

        update_coros: list[Coroutine[Any, Any, tuple[str, str | None, str | None]]] = [
            _sync_update_scope(s) for s in update_scopes
        ]
        for outcome in await self._run_concurrent(update_coros):
            # _sync_update_scope 已经吞掉 Exception；这里只可能是取消之类的 BaseException
            if isinstance(outcome, BaseException):
                raise outcome
            scope, saved_id, error = outcome
            if error is not None:
                failures[scope] = error
            elif saved_id is not None:
                saved[scope] = saved_id

        # (2) create 路径串行：严格维护 total_panels，避免超限创建
        for scope in create_scopes:
            try:
                saved_id, total_panels = await self._sync_scope_panel(
                    client,
                    pf_id,
                    scope,
                    scenes[scope],
                    remark,
                    None,
                    total_panels,
                )
                if saved_id is not None:
                    saved[scope] = saved_id
            except Exception as exc:
                logger.error(
                    f"{LOG_TAG} " + t("log.sync_scope_failed", scope=scope, pf_id=pf_id, exc=exc)
                )
                failures[scope] = str(exc)

        # ---------- 清理未启用场景的旧面板（并发，含重复面板）----------
        disabled_delete_coros: list[Coroutine[Any, Any, bool]] = []
        for scope, owned in existing_by_scope.items():
            if scope in active_scenes:
                continue
            for old in owned:
                old_id = old.get("panel_id")
                if not old_id:
                    continue
                disabled_delete_coros.append(
                    self._safe_delete_panel(
                        client,
                        old_id,
                        scope,
                        log_prefix="log_prefix.remove_disabled_scene_panel",
                    )
                )
        await self._run_concurrent(disabled_delete_coros)

        if failures:
            raise PanelSyncError(
                t(
                    "panel.scope_sync_failed",
                    detail="；".join(f"{scope}: {message}" for scope, message in failures.items()),
                ),
                saved=saved,
            )

        return saved

    async def purge_all(
        self,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, dict[str, str]]:
        """删除所有平台上**全部**指令面板，并清空本地状态

        因为同一 appid 不会有其他插件共用 `/v2/panels`，所以直接删除全部面板，
        而不仅限于 remark 带前缀的本插件面板。返回每个平台删除后的剩余面板数。

        参数：
            on_progress: 可选进度回调，在开始/每个平台完成时触发。

        返回：{pf_id: {"remaining": N, "deleted": D}}
        """
        clients = self.build_clients()
        if not clients:
            await self._emit_progress(on_progress, t("progress.purge_no_platform"))
            self._state.save({})
            return {}

        total = len(clients)
        await self._emit_progress(
            on_progress,
            t("progress.purge_start", platforms=total),
        )

        result: dict[str, dict[str, str]] = {}
        for idx, (pf_id, client) in enumerate(clients.items(), start=1):
            # purge 路径容忍部分场景失败：即使查询不完整，已拿到的面板
            # 仍然可以删，失败场景的面板留着等下次重试即可。
            all_panels, _failed = await self.list_all_panels(client)

            # 并发删除所有面板：先构造协程列表，再一次性跑
            delete_coros: list[Coroutine[Any, Any, bool]] = []
            for p in all_panels:
                panel_id = p.get("panel_id")
                scope = p.get("scope", "?")
                if not panel_id:
                    continue
                delete_coros.append(
                    self._safe_delete_panel(
                        client,
                        panel_id,
                        scope,
                        log_prefix="log_prefix.purge_delete_panel",
                    )
                )
            results = await self._run_concurrent(delete_coros)
            deleted = sum(1 for r in results if r is True)

            # 删除后复查剩余（复查阶段同样容忍部分场景失败）
            remaining_panels, post_failed = await self.list_all_panels(client)
            if _failed or post_failed:
                failed_scopes = _failed | post_failed
                result[pf_id] = {
                    "error": t(
                        "panel.incomplete_list_purged_partial",
                        scopes=sorted(failed_scopes),
                    )
                }
                await self._emit_progress(
                    on_progress,
                    t(
                        "progress.platform_purge_partial",
                        pf_id=pf_id,
                        index=idx,
                        total=total,
                        deleted=deleted,
                    ),
                )
            else:
                result[pf_id] = {
                    "deleted": str(deleted),
                    "remaining": str(len(remaining_panels)),
                }
                await self._emit_progress(
                    on_progress,
                    t(
                        "progress.platform_purged",
                        pf_id=pf_id,
                        index=idx,
                        total=total,
                        deleted=deleted,
                        remaining=len(remaining_panels),
                    ),
                )

        # 清空本地持久化的 panel_id 映射
        self._state.save({})
        return result

    async def sync_all(
        self,
        on_progress: ProgressCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> dict[str, dict[str, str]]:
        """总入口：把每个机器人各场景的指令条目写入对应 QQ 面板

        新版按 appid 优先接管，未被接管的兼容机器人沿用全局 ``scenes`` 与
        ``selected_commands``；新版配置损坏时直接中止，不允许静默回退覆盖面板。

        参数：
            on_progress: 可选进度回调，在每个关键节点触发，回调内异常不影响主流程。
            on_event: 可选结构化事件回调，供 dashboard 渲染进度。

        返回 {pf_id: {scope: panel_id} | {"error": str}}
        """
        # 兼容旧行为：完全没有启用任何场景时直接返回 no_scene，不触碰线上。
        if (
            not get_enabled_scenes(self._config)
            and not Path(self._data_dir / ROBOT_CONFIG_FILENAME).exists()
        ):
            logger.info(f"{LOG_TAG} {t('log.no_scene_enabled')}")
            await self._emit_progress(on_progress, t("progress.sync_no_scene"))
            await self._emit_event(
                on_event,
                {
                    "type": "finish",
                    "ok": True,
                    "reason": "no_scene",
                    "platforms": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "scenes": 0,
                    "items": 0,
                    "result": {},
                },
            )
            return {}

        try:
            robot_config = load_robot_config(self._data_dir)
            robots = self.build_runtime_robots(robot_config=robot_config)
        except Exception as exc:
            logger.error(f"{LOG_TAG} robot config load failed: {exc}", exc_info=True)
            await self._emit_event(
                on_event,
                {
                    "type": "finish",
                    "ok": False,
                    "reason": "config_error",
                    "platforms": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "scenes": 0,
                    "items": 0,
                    "error": str(exc),
                    "result": {},
                },
            )
            raise

        if not robots:
            logger.warning(f"{LOG_TAG} {t('log.no_platform_config')}")
            await self._emit_progress(on_progress, t("progress.sync_no_platform"))
            await self._emit_event(
                on_event,
                {
                    "type": "finish",
                    "ok": True,
                    "reason": "no_platform",
                    "platforms": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "scenes": 0,
                    "items": 0,
                    "result": {},
                },
            )
            return {}

        robot_scenes: dict[str, dict[str, list[dict[str, str]]]] = {}
        for robot in robots:
            pf_id = str(robot.get("id") or robot.get("appid") or "")
            if not pf_id:
                continue
            raw_scenes = robot.get("scenes")
            scenes = (
                {scope: normalize_panel_items(raw_scenes.get(scope, [])) for scope in SCENES}
                if isinstance(raw_scenes, dict)
                else {scope: [] for scope in SCENES}
            )
            robot_scenes[pf_id] = scenes

        # 走公开的 build_clients 构造，保持与状态接口同源并便于测试注入替身。
        expected = self.build_clients(robot_config=robot_config)

        if not expected:
            logger.warning(f"{LOG_TAG} {t('log.no_platform_config')}")
            await self._emit_progress(on_progress, t("progress.sync_no_platform"))
            await self._emit_event(
                on_event,
                {
                    "type": "finish",
                    "ok": True,
                    "reason": "no_platform",
                    "platforms": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "scenes": 0,
                    "items": 0,
                    "result": {},
                },
            )
            return {}

        total = len(expected)
        total_items = sum(
            len(items) for scenes in robot_scenes.values() for items in scenes.values()
        )
        active_scene_count = len(
            {scope for scenes in robot_scenes.values() for scope, items in scenes.items() if items}
        )

        # 兼容旧 dashboard：整轮没有任何条目时用 clear 模式表示清理。
        event_mode = "sync" if total_items else "clear"
        await self._emit_event(
            on_event,
            {
                "type": "start",
                "mode": event_mode,
                "platforms": total,
                "scenes": active_scene_count,
                "items": total_items,
            },
        )
        await self._emit_progress(
            on_progress,
            t(
                "progress.sync_start",
                platforms=total,
                scenes=active_scene_count,
                items=total_items,
            ),
        )

        result: dict[str, dict[str, str]] = {}
        # 部分场景失败时同步仍写过的面板，配合 result 的 error 一起记录
        partial_saved: dict[str, dict[str, str]] = {}
        for idx, (pf_id, client) in enumerate(expected.items(), start=1):
            try:
                scene_map = robot_scenes.get(pf_id, {scope: [] for scope in SCENES})
                saved = await self.sync_for_platform(pf_id, client, scene_map)
                if saved:
                    result[pf_id] = saved
                await self._emit_progress(
                    on_progress,
                    t(
                        "progress.platform_synced",
                        pf_id=pf_id,
                        index=idx,
                        total=total,
                        saved=len(saved),
                    ),
                )
                await self._emit_event(
                    on_event,
                    {
                        "type": "platform",
                        "pf_id": pf_id,
                        "index": idx,
                        "total": total,
                        "status": "ok",
                        "saved": len(saved),
                        "error": None,
                    },
                )
            except Exception as exc:
                logger.error(
                    f"{LOG_TAG} " + t("log.sync_platform_failed", pf_id=pf_id, exc=exc),
                    exc_info=True,
                )
                result[pf_id] = {"error": str(exc)}
                partial = exc.saved if isinstance(exc, PanelSyncError) else {}
                if partial:
                    partial_saved[pf_id] = partial
                await self._emit_progress(
                    on_progress,
                    t(
                        "progress.platform_sync_failed",
                        pf_id=pf_id,
                        index=idx,
                        total=total,
                        exc=exc,
                    ),
                )
                await self._emit_event(
                    on_event,
                    {
                        "type": "platform",
                        "pf_id": pf_id,
                        "index": idx,
                        "total": total,
                        "status": "error",
                        "saved": len(partial),
                        "error": str(exc),
                    },
                )

        state_snapshot = {
            pf_id: scopes for pf_id, scopes in result.items() if "error" not in scopes
        }
        state_snapshot.update(partial_saved)
        self._state.save(state_snapshot)
        succeeded = sum(1 for scopes in result.values() if "error" not in scopes)
        await self._emit_event(
            on_event,
            {
                "type": "finish",
                "ok": succeeded == len(result),
                "reason": event_mode,
                "platforms": len(result),
                "succeeded": succeeded,
                "failed": len(result) - succeeded,
                "scenes": active_scene_count,
                "items": total_items,
                "result": result,
            },
        )
        return result

    async def clear_for_platform(
        self,
        pf_id: str,
        client: QQClient,
    ) -> None:
        """删除该平台下本插件之前创建的所有面板（用于指令清空时的清理）"""
        # clear 路径容忍部分场景失败：删少了一些面板不影响最终一致性，
        # 下次 sync 还会按 remark 重新识别并清理。
        all_existing, _failed = await self.list_all_panels(client)
        delete_coros: list[Coroutine[Any, Any, bool]] = []
        for p in all_existing:
            if not self.is_owned_panel(p):
                continue
            panel_id = p.get("panel_id")
            scope = p.get("scope", "?")
            if not panel_id:
                continue
            delete_coros.append(self._safe_delete_panel(client, panel_id, scope))
        await self._run_concurrent(delete_coros)

    def set_config(self, config: dict[str, Any]) -> None:
        """运行期刷新配置引用，并同步刷新语言设置"""
        self._config = dict(config or {})
        language = self._config.get("language", DEFAULT_LANGUAGE)
        self.translator.set_language(language)


__all__ = ["EventCallback", "PanelSyncError", "PanelSyncer", "ProgressCallback"]
