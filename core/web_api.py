"""插件可视化视图 (Dashboard) 的后端 Web API。

只提供视图当前需要的只读接口 `GET /<plugin_name>/status`，返回结构与
`web/dashboard/src/types/dashboard.ts` 的 StatusResponse 对应。数据取自 core 的
公开能力，视图层不重复业务逻辑。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context

from .config import (
    PANEL_MAX_ITEMS,
    get_configured_platforms,
    get_enabled_scenes,
    get_selected_commands,
)
from .i18n import LOG_TAG, t
from .panel_syncer import PanelSyncer
from .paths import PLUGIN_NAME, PLUGIN_VERSION

# 视图状态接口的路由后缀；完整路由为 /<PLUGIN_NAME>/status
STATUS_ROUTE_SUFFIX = "status"

# 状态结果缓存时长（秒）：面板查询慢且消耗 QQ 配额，重复/并发请求复用同一结果
STATUS_CACHE_TTL = 5.0


def mask_appid(appid: Any) -> str:
    """appid 脱敏：保留前 3 位与后 2 位，中间打码；过短则整体打码"""
    text = str(appid or "")
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 5)}{text[-2:]}"


def panel_items_count(panel: dict[str, Any]) -> int:
    """统计面板 record 的指令条目数，结构异常时返回 0（兼容 items 嵌套或扁平）"""
    content = panel.get("panel")
    items = content.get("items") if isinstance(content, dict) else panel.get("items")
    return len(items) if isinstance(items, list) else 0


async def _platform_status(
    syncer: PanelSyncer,
    pf_id: str,
    client: Any,
    info: dict[str, str],
    source: str,
    scenes: list[str],
) -> tuple[dict[str, Any], int, bool]:
    """构造单个平台的状态，返回（payload，线上已知面板数，计数是否完整）

    计数不完整（有场景查询失败）时，调用方不应把它当作精确的在线总数。
    场景状态：synced=线上恰有一条本插件面板，duplicate=同场景存在多条，
    missing=该场景无本插件面板，failed=查询该场景失败。
    """
    raw_appid = info.get("appid")
    # 未配备注名时 pf_id 会回退成 appid，同样需要脱敏
    display_pf_id = mask_appid(raw_appid) if raw_appid and str(raw_appid) == pf_id else pf_id

    payload: dict[str, Any] = {
        "pf_id": display_pf_id,
        "appid": mask_appid(raw_appid),
        "source": source,
        "platform": info.get("platform") or getattr(client, "platform_label", "qq"),
        "scenes": [],
    }

    try:
        panels, failed_scopes = await syncer.list_all_panels(client)
    except Exception as exc:
        # list_all_panels 已逐场景兜底，这里只防意外；单平台失败不能让整个接口 500
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
) -> dict[str, Any]:
    """组装状态概览响应体（对应 types/dashboard.ts 的 StatusResponse）

    该接口默认查询线上，每个平台对所有场景各调一次 QQ API，属慢请求，
    视图只在进入页面/手动刷新时调用。
    """
    platforms, source = get_configured_platforms(config, syncer.context)
    scenes = get_enabled_scenes(config)
    items = get_selected_commands(config)
    # 用当前配置构建客户端，与上面的平台元数据同源，避免 syncer 内部配置过期
    clients = syncer.build_clients(config)

    # 各平台互不依赖，并发查询缩短耗时；单平台失败只影响它自己的 payload
    results = await asyncio.gather(
        *(
            _platform_status(syncer, pf_id, client, platforms.get(pf_id, {}), source, scenes)
            for pf_id, client in clients.items()
        )
    )

    panels: dict[str, Any] = {
        "total": sum(count for _, count, _ in results),
        # 有场景查询失败时 total 只是下限，明确标记给视图，不能当成精确值
        "partial": any(not complete for _, _, complete in results),
    }
    platform_count = len(clients)
    if platform_count:
        # 聚合面板数的有效上限 = 单机器人上限 × 机器人数；没有平台时省略 max
        panels["max"] = PANEL_MAX_ITEMS * platform_count

    return {
        "plugin": {"name": PLUGIN_NAME, "version": version},
        "platforms": [payload for payload, _, _ in results],
        "scenes": scenes,
        "items": {"count": len(items), "max": PANEL_MAX_ITEMS},
        "panels": panels,
    }


class StatusCache:
    """状态结果的单飞 (single-flight) 加短期缓存

    并发请求复用正在计算或刚算完的结果，TTL 内命中缓存，不重复打 QQ API；
    force=True（视图手动刷新）时跳过缓存。
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
            # 等锁期间可能已有别的请求算好并写入缓存，这里再判一次
            cached = self._peek(force)
            if cached is not None:
                return cached
            value = await compute()
            self._value = value
            self._expires_at = time.monotonic() + self._ttl
            return value

    def _peek(self, force: bool) -> dict[str, Any] | None:
        """命中未过期的缓存则返回结果，否则返回 None"""
        if force or not self._is_fresh():
            return None
        return self._value

    def _is_fresh(self) -> bool:
        return self._value is not None and time.monotonic() < self._expires_at


def register_status_api(
    context: Context,
    get_syncer: Callable[[], PanelSyncer | None],
    get_config: Callable[[], dict[str, Any]],
    version: str = PLUGIN_VERSION,
    *,
    cache_ttl: float = STATUS_CACHE_TTL,
) -> bool:
    """注册视图用的只读 Web API 路由，成功返回 True

    syncer 到 initialize() 才创建，config 也会在运行期刷新，因此用 provider
    回调在每次请求时取最新值。老版本 AstrBot 缺少 astrbot.api.web 或
    register_web_api 时只记 warning 并跳过，不影响面板同步。
    """
    try:
        from astrbot.api.web import error_response, json_response, request
    except Exception as exc:  # pragma: no cover - 依赖宿主版本，无法在离线测试覆盖
        logger.warning(f"{LOG_TAG} " + t("log.web_api_unavailable", exc=exc))
        return False

    if not callable(getattr(context, "register_web_api", None)):
        logger.warning(
            f"{LOG_TAG} " + t("log.web_api_unavailable", exc="context.register_web_api missing")
        )
        return False

    cache = StatusCache(cache_ttl)

    async def page_status():  # noqa: ANN202 - 返回值由 astrbot.api.web 决定
        syncer = get_syncer()
        if syncer is None:
            return error_response(t("web.not_ready"), status_code=503)
        # 视图手动刷新带 refresh=1 时跳过缓存
        raw_refresh = request.query.get("refresh", "")
        force = str(raw_refresh).strip().lower() in ("1", "true", "yes")
        payload = await cache.get(
            lambda: build_status(syncer, get_config(), version),
            force=force,
        )
        return json_response(payload)

    context.register_web_api(
        f"/{PLUGIN_NAME}/{STATUS_ROUTE_SUFFIX}",
        page_status,
        ["GET"],
        "Plugin dashboard status overview",
    )
    return True


__all__ = [
    "STATUS_CACHE_TTL",
    "STATUS_ROUTE_SUFFIX",
    "StatusCache",
    "build_status",
    "mask_appid",
    "panel_items_count",
    "register_status_api",
]
