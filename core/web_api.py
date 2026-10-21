"""插件可视化视图 (Dashboard) 的后端 Web API。

注册的视图接口（视图内用相对路径调用，bridge 会补上插件名前缀）：

- ``GET  /<plugin_name>/status``      状态概览，对应 types/dashboard.ts 的 StatusResponse
- ``GET  /<plugin_name>/config``      读取插件配置（secret 只回掩码）
- ``POST /<plugin_name>/config``      校验并写回插件配置，保存后立即生效
- ``GET  /<plugin_name>/robots``      读取新版机器人配置（secret 只回掩码）
- ``POST /<plugin_name>/robots``      校验并写回新版机器人配置
- ``POST /<plugin_name>/robots/import-legacy`` 从兼容配置导入机器人
- ``POST /<plugin_name>/sync``        触发一次面板同步（后台任务，单飞）
- ``GET  /<plugin_name>/sync/events`` SSE 推送同步进度（结构化事件 + 本地化文本）
- ``GET  /<plugin_name>/logs/events`` SSE 推送插件实时日志（最近 1000 条可回放）

业务逻辑都留在 core 的配置 / 同步模块里，视图层只做组装与协议转换。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context

from .config import (
    PANEL_ITEM_DESC_MAX,
    PANEL_ITEM_NAME_MAX,
    PANEL_MAX_ITEMS,
    SCENES,
    export_config,
    get_configured_platforms,
    get_enabled_scenes,
    get_selected_commands,
    normalize_config_payload,
)
from .i18n import LOG_TAG, t
from .log_stream import LogBuffer, LogSubscriberLimitError
from .panel_syncer import PanelSyncer
from .paths import PLUGIN_NAME, PLUGIN_VERSION
from .robot_config import (
    RobotConfigError,
    build_runtime_robots,
    export_robot_config,
    legacy_to_robot_drafts,
    load_robot_config,
    save_robot_config,
    validate_robot_config,
)
from .sync_runner import SyncRunner

# 视图接口路由后缀，完整路径为 /<PLUGIN_NAME>/<suffix>
STATUS_ROUTE_SUFFIX = "status"
CONFIG_ROUTE_SUFFIX = "config"
ROBOTS_ROUTE_SUFFIX = "robots"
ROBOTS_IMPORT_ROUTE_SUFFIX = "robots/import-legacy"
SYNC_ROUTE_SUFFIX = "sync"
SYNC_EVENTS_ROUTE_SUFFIX = "sync/events"
LOG_EVENTS_ROUTE_SUFFIX = "logs/events"

# 状态结果缓存时间（秒）：连续查询不重复打 QQ API，刷新/保存配置时绕过或失效
STATUS_CACHE_TTL = 5.0


def _web() -> Any:
    """延迟导入 astrbot.api.web

    较早的 AstrBot 版本没有该模块，导入失败时由调用方降级（register 里会先探测）。
    """
    from astrbot.api import web

    return web


def mask_appid(appid: Any) -> str:
    """appid 脱敏：保留前 3 位与后 2 位，中间打码；过短整体打码"""
    text = str(appid or "")
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 5)}{text[-2:]}"


def _robot_response(config: dict[str, Any]) -> dict[str, Any]:
    """给新版机器人配置补齐前端契约里的场景与限制元数据。"""
    payload = export_robot_config(config)
    payload["available_scenes"] = list(SCENES)
    payload["limits"] = {
        "name_max": PANEL_ITEM_NAME_MAX,
        "desc_max": PANEL_ITEM_DESC_MAX,
        "items_max": PANEL_MAX_ITEMS,
    }
    return payload


def _robot_appid_set(config: dict[str, Any]) -> set[str]:
    robots = config.get("robots")
    if not isinstance(robots, list):
        return set()
    appids: set[str] = set()
    for robot in robots:
        if not isinstance(robot, dict):
            continue
        appid = str(robot.get("appid") or "").strip()
        if appid:
            appids.add(appid)
    return appids


def panel_items_count(panel: dict[str, Any]) -> int:
    """统计面板 record 的指令条目数，结构异常时返回 0（items 嵌套或扁平）"""
    content = panel.get("panel")
    items = content.get("items") if isinstance(content, dict) else panel.get("items")
    return len(items) if isinstance(items, list) else 0


async def _platform_status(
    syncer: PanelSyncer,
    pf_id: str,
    client: Any,
    info: dict[str, str],
    scenes: list[str],
) -> tuple[dict[str, Any], int, bool]:
    """构造单个平台的状态，返回（payload，已知面板数，列表是否完整）

    任一场景列表查询失败都会计入 failed_scopes，此时该平台视为不完整，
    用返回的布尔值让调用方判断总数是否只是下限。
    Scene 状态：synced=该场景恰好一个插件面板，duplicate=同场景存在多个，
    missing=该场景无插件面板，failed=查询该场景失败。
    """
    raw_appid = info.get("appid")
    # 未配备注时 pf_id 会退化成 appid，展示时同样需要脱敏
    display_pf_id = mask_appid(raw_appid) if raw_appid and str(raw_appid) == pf_id else pf_id

    payload: dict[str, Any] = {
        "pf_id": display_pf_id,
        "appid": mask_appid(raw_appid),
        "platform": info.get("platform") or getattr(client, "platform_label", "qq"),
        "scenes": [],
    }

    try:
        panels, failed_scopes = await syncer.list_all_panels(client)
    except Exception as exc:
        # list_all_panels 吞场景级异常，这里只兜底；单平台失败不拖垮整个接口
        logger.error(
            f"{LOG_TAG} " + t("log.status_platform_failed", pf_id=pf_id, exc=exc),
            exc_info=True,
        )
        payload["scenes"] = [{"scope": scope, "state": "failed"} for scope in scenes]
        payload["error"] = str(exc)
        return payload, 0, False

    owned = syncer.owned_panels_by_scope(panels)
    for scope in scenes:
        if scope in failed_scopes:
            payload["scenes"].append({"scope": scope, "state": "failed"})
            continue

        owned_list = owned.get(scope, [])
        if not owned_list:
            payload["scenes"].append({"scope": scope, "state": "missing"})
            continue

        first = owned_list[0]
        payload["scenes"].append(
            {
                "scope": scope,
                "state": "duplicate" if len(owned_list) > 1 else "synced",
                "panel_id": str(first.get("panel_id", "")),
                "items_count": panel_items_count(first),
            }
        )
    return payload, len(panels), not failed_scopes


async def build_status(
    syncer: PanelSyncer,
    config: dict[str, Any],
    version: str = PLUGIN_VERSION,
    robot_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装状态概览响应体（对应 types/dashboard.ts 的 StatusResponse）

    该接口默认查询线上，每个平台按场景各查一次 QQ API，所以视图只在进入页面时取。
    平台凭证只来自插件配置：插件读不到 AstrBot 平台适配器的机器人信息。

    新版配置为空时沿用旧版全局统计；否则按“机器人 → 场景”统计，被新版接管的老机器人不再重复出现。
    """
    v2_robots = _v2_robots(robot_config)
    if not v2_robots:
        return await _build_legacy_status(syncer, config, version)

    runtime = build_runtime_robots(config, robot_config or {})
    runtime_by_id = {str(robot.get("id") or robot.get("appid") or ""): robot for robot in runtime}
    # 用同一份新版配置构造客户端，保证平台元信息与运行时机器人同源
    clients = syncer.build_clients(config, robot_config=robot_config or {})

    async def one(pf_id: str, client: Any) -> tuple[dict[str, Any], int, bool]:
        robot = runtime_by_id.get(pf_id, {})
        scenes = [
            scope
            for scope in SCENES
            if isinstance(robot.get("scenes"), dict) and robot["scenes"].get(scope)
        ]
        payload, count, complete = await _platform_status(
            syncer,
            pf_id,
            client,
            {
                "appid": str(robot.get("appid") or ""),
                "platform": str(robot.get("platform") or ""),
            },
            scenes,
        )
        payload["name"] = str(robot.get("name") or "")
        payload["source"] = str(robot.get("source") or "v2")
        return payload, count, complete

    results = await asyncio.gather(*(one(pf_id, client) for pf_id, client in clients.items()))

    active_scenes = [
        scope
        for scope in SCENES
        if any(
            isinstance(robot.get("scenes"), dict) and robot["scenes"].get(scope)
            for robot in runtime
        )
    ]
    total_items = sum(
        len(items)
        for robot in runtime
        if isinstance(robot.get("scenes"), dict)
        for items in robot["scenes"].values()
        if isinstance(items, list)
    )
    panels: dict[str, Any] = {
        "total": sum(count for _, count, _ in results),
        "partial": any(not complete for _, _, complete in results),
    }
    platform_count = len(clients)
    if platform_count:
        panels["max"] = PANEL_MAX_ITEMS * platform_count

    return {
        "plugin": {"name": PLUGIN_NAME, "version": version},
        "platforms": [payload for payload, _, _ in results],
        "scenes": active_scenes,
        "items": {"count": total_items, "max": PANEL_MAX_ITEMS},
        "panels": panels,
    }


def _v2_robots(robot_config: dict[str, Any] | None) -> list[Any]:
    if not isinstance(robot_config, dict):
        return []
    robots = robot_config.get("robots")
    return robots if isinstance(robots, list) else []


async def _build_legacy_status(
    syncer: PanelSyncer,
    config: dict[str, Any],
    version: str,
) -> dict[str, Any]:
    """旧版全局配置的状态统计，保持既有行为不变。"""
    platforms = get_configured_platforms(config)
    scenes = get_enabled_scenes(config)
    items = get_selected_commands(config)
    clients = syncer.build_clients(config)

    results = await asyncio.gather(
        *(
            _platform_status(syncer, pf_id, client, platforms.get(pf_id, {}), scenes)
            for pf_id, client in clients.items()
        )
    )

    panels: dict[str, Any] = {
        "total": sum(count for _, count, _ in results),
        "partial": any(not complete for _, _, complete in results),
    }
    platform_count = len(clients)
    if platform_count:
        panels["max"] = PANEL_MAX_ITEMS * platform_count

    return {
        "plugin": {"name": PLUGIN_NAME, "version": version},
        "platforms": [payload for payload, _, _ in results],
        "scenes": scenes,
        "items": {"count": len(items), "max": PANEL_MAX_ITEMS},
        "panels": panels,
    }


class StatusCache:
    """状态结果的单飞 (single-flight) 内存缓存

    并发请求只计算一次，TTL 内复用，避免重复打 QQ API；
    force=True（视图手动刷新）时绕过缓存，invalidate() 在配置写回后主动失效。
    """

    def __init__(self, ttl: float = STATUS_CACHE_TTL) -> None:
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._expires_at = 0.0
        self._value: dict[str, Any] | None = None

    async def get(
        self,
        compute: Callable[[], Awaitable[dict[str, Any]]],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        cached = self._peek(force)
        if cached is not None:
            return cached

        async with self._lock:
            # 等锁期间可能已有别的请求算完，double check 后直接复用
            cached = self._peek(force)
            if cached is not None:
                return cached
            value = await compute()
            self._value = value
            self._expires_at = time.monotonic() + self._ttl
            return value

    def invalidate(self) -> None:
        """主动失效缓存（配置变更后调用）"""
        self._value = None
        self._expires_at = 0.0

    def _peek(self, force: bool) -> dict[str, Any] | None:
        """命中未过期缓存则返回结果，否则返回 None"""
        if force or not self._is_fresh():
            return None
        return self._value

    def _is_fresh(self) -> bool:
        return self._value is not None and time.monotonic() < self._expires_at


class WebApiBundle:
    """插件视图 Web API 的 handler 集合，以及它们共享的缓存 / 任务状态

    syncer 在 initialize() 才创建，config 也会被保存流程刷新，所以这里用 provider
    回调在每次请求时取最新值；宿主缺少 astrbot.api.web 或 register_web_api 时
    register() 只记 warning 返回 False，不影响插件本体同步。
    """

    def __init__(
        self,
        get_syncer: Callable[[], PanelSyncer | None],
        get_config: Callable[[], dict[str, Any]],
        *,
        save_config: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        robot_config_dir: Path | None = None,
        get_legacy_config: Callable[[], dict[str, Any]] | None = None,
        log_buffer: LogBuffer | None = None,
        version: str = PLUGIN_VERSION,
        cache_ttl: float = STATUS_CACHE_TTL,
    ) -> None:
        self._get_syncer = get_syncer
        self._get_config = get_config
        self._save_config = save_config
        self._robot_config_dir = Path(robot_config_dir) if robot_config_dir is not None else None
        self._get_legacy_config = get_legacy_config
        self._log_buffer = log_buffer
        self._version = version
        self.cache = StatusCache(cache_ttl)
        self.runner = SyncRunner()

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, context: Context) -> bool:
        """注册全部视图接口，成功返回 True"""
        try:
            from astrbot.api import web  # noqa: F401
        except Exception as exc:  # pragma: no cover - 依赖宿主版本，测试覆盖降级分支
            logger.warning(f"{LOG_TAG} " + t("log.web_api_unavailable", exc=exc))
            return False

        if not callable(getattr(context, "register_web_api", None)):
            logger.warning(
                f"{LOG_TAG} " + t("log.web_api_unavailable", exc="context.register_web_api missing")
            )
            return False

        prefix = f"/{PLUGIN_NAME}"
        context.register_web_api(
            f"{prefix}/{STATUS_ROUTE_SUFFIX}",
            self.page_status,
            ["GET"],
            "Plugin dashboard status overview",
        )
        context.register_web_api(
            f"{prefix}/{CONFIG_ROUTE_SUFFIX}",
            self.page_config_get,
            ["GET"],
            "Plugin dashboard config read",
        )
        context.register_web_api(
            f"{prefix}/{CONFIG_ROUTE_SUFFIX}",
            self.page_config_save,
            ["POST"],
            "Plugin dashboard config save",
        )
        context.register_web_api(
            f"{prefix}/{ROBOTS_ROUTE_SUFFIX}",
            self.page_robots_get,
            ["GET"],
            "Plugin robot config read",
        )
        context.register_web_api(
            f"{prefix}/{ROBOTS_ROUTE_SUFFIX}",
            self.page_robots_save,
            ["POST"],
            "Plugin robot config save",
        )
        context.register_web_api(
            f"{prefix}/{ROBOTS_IMPORT_ROUTE_SUFFIX}",
            self.page_robots_import_legacy,
            ["POST"],
            "Plugin robot config legacy import",
        )
        context.register_web_api(
            f"{prefix}/{SYNC_ROUTE_SUFFIX}",
            self.page_sync_start,
            ["POST"],
            "Plugin dashboard panel sync",
        )
        context.register_web_api(
            f"{prefix}/{SYNC_EVENTS_ROUTE_SUFFIX}",
            self.page_sync_events,
            ["GET"],
            "Plugin dashboard panel sync progress (SSE)",
        )
        context.register_web_api(
            f"{prefix}/{LOG_EVENTS_ROUTE_SUFFIX}",
            self.page_log_events,
            ["GET"],
            "Plugin dashboard live logs (SSE)",
        )
        return True

    def _safe_robot_config(self) -> dict[str, Any] | None:
        if self._robot_config_dir is None:
            return None
        return load_robot_config(self._robot_config_dir)

    # ------------------------------------------------------------------
    # 状态概览
    # ------------------------------------------------------------------

    async def page_status(self) -> Any:
        web = _web()
        syncer = self._get_syncer()
        if syncer is None:
            return web.error_response(t("web.not_ready"), status_code=503)
        # 视图手动刷新传 refresh=1 时绕过缓存
        raw_refresh = web.request.query.get("refresh", "")
        force = str(raw_refresh).strip().lower() in ("1", "true", "yes")
        try:
            payload = await self.cache.get(
                lambda: build_status(
                    syncer,
                    self._get_config(),
                    self._version,
                    robot_config=self._safe_robot_config(),
                ),
                force=force,
            )
        except RobotConfigError as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.robot_config_read_failed", exc=exc),
                exc_info=True,
            )
            return web.error_response(str(exc), status_code=500)
        return web.json_response(payload)

    # ------------------------------------------------------------------
    # 配置读写
    # ------------------------------------------------------------------

    async def page_config_get(self) -> Any:
        web = _web()
        return web.json_response(export_config(self._get_config()))

    async def page_config_save(self) -> Any:
        web = _web()
        if self._save_config is None:
            return web.error_response(t("web.config_unavailable"), status_code=503)

        payload = await web.request.json(default={})
        if not isinstance(payload, dict):
            return web.error_response(t("web.config_invalid_body"), status_code=400)

        values, errors = normalize_config_payload(self._get_config(), payload)
        if errors:
            return web.error_response("；".join(errors), status_code=400)

        try:
            await self._save_config(values)
        except Exception as exc:
            logger.error(f"{LOG_TAG} " + t("log.config_save_failed", exc=exc), exc_info=True)
            return web.error_response(t("web.config_save_failed", exc=exc), status_code=500)

        # 配置变了，状态缓存里的平台/场景信息随即过期
        self.cache.invalidate()
        return web.json_response(export_config(self._get_config()))

    # ------------------------------------------------------------------
    # 新版机器人配置
    # ------------------------------------------------------------------

    def _robots_unavailable(self) -> Any:
        web = _web()
        return web.error_response(t("web.robots_unavailable"), status_code=503)

    def _load_robots(self) -> dict[str, Any]:
        if self._robot_config_dir is None:
            raise RobotConfigError(t("web.robots_unavailable"))
        return load_robot_config(self._robot_config_dir)

    def _get_legacy(self) -> dict[str, Any]:
        if self._get_legacy_config is not None:
            return self._get_legacy_config()
        return self._get_config()

    async def page_robots_get(self) -> Any:
        """读取新版机器人配置；文件损坏时返回可读的 500 错误。"""
        web = _web()
        if self._robot_config_dir is None:
            return self._robots_unavailable()
        try:
            config = self._load_robots()
        except RobotConfigError as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.robot_config_read_failed", exc=exc),
                exc_info=True,
            )
            return web.error_response(str(exc), status_code=500)
        return web.json_response(_robot_response(config))

    async def page_robots_save(self) -> Any:
        """校验并原子写回新版机器人配置，secret 留空表示沿用旧值。"""
        web = _web()
        if self._robot_config_dir is None:
            return self._robots_unavailable()

        payload = await web.request.json(default={})
        if not isinstance(payload, dict):
            return web.error_response(t("web.config_invalid_body"), status_code=400)

        try:
            existing = self._load_robots()
        except RobotConfigError as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.robot_config_read_failed", exc=exc),
                exc_info=True,
            )
            return web.error_response(str(exc), status_code=500)

        expected_version = payload.get("version")
        current_version = existing.get("version", 1)
        if type(expected_version) is not int or expected_version < 1:
            return web.error_response(t("web.robot_version_invalid"), status_code=400)
        if expected_version != current_version:
            return web.error_response(t("web.robot_config_conflict"), status_code=409)

        config, errors = validate_robot_config(existing, payload)
        if errors:
            return web.error_response(t("common.error_separator").join(errors), status_code=400)

        config["version"] = current_version + 1
        try:
            save_robot_config(self._robot_config_dir, config)
        except RobotConfigError as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.robot_config_save_failed", exc=exc),
                exc_info=True,
            )
            return web.error_response(str(exc), status_code=500)

        self.cache.invalidate()
        return web.json_response(_robot_response(config))

    async def page_robots_import_legacy(self) -> Any:
        """把兼容配置里的机器人导入新版配置，重复 appid 拒绝导入。"""
        web = _web()
        if self._robot_config_dir is None:
            return self._robots_unavailable()

        payload = await web.request.json(default={})
        if not isinstance(payload, dict):
            return web.error_response(t("web.config_invalid_body"), status_code=400)

        raw_appids: Any
        if "appids" in payload:
            raw_appids = payload.get("appids")
        else:
            raw_appids = [payload.get("appid")]
        if not isinstance(raw_appids, list) or not raw_appids:
            return web.error_response(t("web.robot_appids_invalid"), status_code=400)

        appids = []
        for index, raw_appid in enumerate(raw_appids):
            appid = str(raw_appid or "").strip()
            if not appid:
                return web.error_response(
                    t("web.robot_appid_empty", index=index),
                    status_code=400,
                )
            appids.append(appid)
        if len(set(appids)) != len(appids):
            return web.error_response(t("web.robot_appids_duplicate"), status_code=400)

        try:
            existing = self._load_robots()
        except RobotConfigError as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.robot_config_read_failed", exc=exc),
                exc_info=True,
            )
            return web.error_response(str(exc), status_code=500)

        expected_version = payload.get("version")
        current_version = existing.get("version", 1)
        if type(expected_version) is not int or expected_version < 1:
            return web.error_response(t("web.robot_version_invalid"), status_code=400)
        if expected_version != current_version:
            return web.error_response(t("web.robot_config_conflict"), status_code=409)

        existing_appids = _robot_appid_set(existing)
        duplicates = [appid for appid in appids if appid in existing_appids]
        if duplicates:
            return web.error_response(
                t(
                    "web.robot_appids_existing",
                    appids=t("common.list_separator").join(duplicates),
                ),
                status_code=400,
            )

        drafts = legacy_to_robot_drafts(self._get_legacy())
        by_appid = {
            str(draft.get("appid") or "").strip(): draft
            for draft in drafts
            if isinstance(draft, dict) and str(draft.get("appid") or "").strip()
        }
        missing = [appid for appid in appids if appid not in by_appid]
        if missing:
            return web.error_response(
                t(
                    "web.robot_appids_missing",
                    appids=t("common.list_separator").join(missing),
                ),
                status_code=400,
            )

        robots = existing.get("robots")
        merged = dict(existing)
        merged["version"] = 1
        merged["robots"] = [
            *(robots if isinstance(robots, list) else []),
            *(by_appid[appid] for appid in appids),
        ]

        config, errors = validate_robot_config({}, merged)
        if errors:
            return web.error_response(t("common.error_separator").join(errors), status_code=400)

        config["version"] = current_version + 1
        try:
            save_robot_config(self._robot_config_dir, config)
        except RobotConfigError as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.robot_config_import_failed", exc=exc),
                exc_info=True,
            )
            return web.error_response(str(exc), status_code=500)

        self.cache.invalidate()
        return web.json_response(_robot_response(config))

    # ------------------------------------------------------------------
    # 同步入口 + 进度流
    # ------------------------------------------------------------------

    async def page_sync_start(self) -> Any:
        """触发一次同步；已有任务在跑时返回 busy，不排队"""
        web = _web()
        syncer = self._get_syncer()
        if syncer is None:
            return web.error_response(t("web.not_ready"), status_code=503)
        started = self.runner.start(self._make_run(syncer))
        return web.json_response({"started": started, "busy": not started})

    async def page_sync_events(self) -> Any:
        """SSE 推送同步进度；since 用于断线重连后回放已错过的事件"""
        web = _web()
        syncer = self._get_syncer()
        if syncer is None:
            return web.error_response(t("web.not_ready"), status_code=503)

        raw_since = web.request.query.get("since", "")
        try:
            since = max(0, int(raw_since))
        except (TypeError, ValueError):
            since = 0

        runner = self.runner

        async def events():  # noqa: ANN202 - astrbot.api.web 的流式响应体
            async for event in runner.stream(since):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return web.stream_response(events())

    async def page_log_events(self) -> Any:
        """SSE 推送插件日志；since 用于断线重连和页面重新打开后的回放。"""
        web = _web()
        log_buffer = self._log_buffer
        if log_buffer is None:
            return web.error_response(t("web.not_ready"), status_code=503)

        raw_since = web.request.query.get("since", "")
        try:
            since = max(0, int(raw_since))
        except (TypeError, ValueError):
            since = 0
        client_stream_id = web.request.query.get("streamId", "")
        stream_id = log_buffer.stream_id
        reset = (bool(client_stream_id) and client_stream_id != stream_id) or (
            since > log_buffer.last_seq
        )
        if reset:
            since = 0

        async def events():  # noqa: ANN202 - astrbot.api.web 的流式响应体
            yield f"data: {json.dumps({'type': 'stream', 'id': stream_id, 'reset': reset})}\n\n"
            try:
                async for entry in log_buffer.follow(since):
                    if entry is None:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(entry.as_event(), ensure_ascii=False)}\n\n"
            except LogSubscriberLimitError:
                event = {"type": "error", "code": "subscriber_limit"}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return web.stream_response(events())

    def _make_run(
        self,
        syncer: PanelSyncer,
    ) -> Callable[[Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[Any]]:
        """构造同步任务执行体：先刷新配置，再同时推送文本与结构化事件"""

        async def run(emit: Callable[[dict[str, Any]], Awaitable[None]]) -> Any:
            syncer.set_config(self._get_config())

            async def push_text(message: str) -> None:
                await emit({"type": "message", "text": message})

            return await syncer.sync_all(on_progress=push_text, on_event=emit)

        return run


def register_web_apis(
    context: Context,
    get_syncer: Callable[[], PanelSyncer | None],
    get_config: Callable[[], dict[str, Any]],
    *,
    save_config: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    robot_config_dir: Path | None = None,
    get_legacy_config: Callable[[], dict[str, Any]] | None = None,
    log_buffer: LogBuffer | None = None,
    version: str = PLUGIN_VERSION,
    cache_ttl: float = STATUS_CACHE_TTL,
) -> WebApiBundle | None:
    """注册插件视图 Web API，成功返回 bundle，宿主不支持时返回 None"""
    bundle = WebApiBundle(
        get_syncer,
        get_config,
        save_config=save_config,
        robot_config_dir=robot_config_dir,
        get_legacy_config=get_legacy_config,
        log_buffer=log_buffer,
        version=version,
        cache_ttl=cache_ttl,
    )
    if not bundle.register(context):
        return None
    return bundle


__all__ = [
    "CONFIG_ROUTE_SUFFIX",
    "LOG_EVENTS_ROUTE_SUFFIX",
    "ROBOTS_IMPORT_ROUTE_SUFFIX",
    "ROBOTS_ROUTE_SUFFIX",
    "STATUS_CACHE_TTL",
    "STATUS_ROUTE_SUFFIX",
    "SYNC_EVENTS_ROUTE_SUFFIX",
    "SYNC_ROUTE_SUFFIX",
    "StatusCache",
    "WebApiBundle",
    "build_status",
    "mask_appid",
    "panel_items_count",
    "register_web_apis",
]
