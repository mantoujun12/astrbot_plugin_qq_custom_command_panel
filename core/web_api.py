"""插件可视化视图 (Dashboard) 的后端 Web API。

只实现视图当前需要的只读接口:

    GET /<plugin_name>/status    状态概览

视图端 (web/dashboard) 通过 `bridge.apiGet("status")` 调用, endpoint 不含插件名
前缀, 由 Dashboard 转发到本路由 (见 AGENTS.md 第 8 条)。返回结构与
`web/dashboard/src/types/dashboard.ts` 的 StatusResponse 一一对应。

数据全部取自 core 的公开能力, 视图层不重复业务逻辑:
    PanelSyncer.build_clients / list_all_panels / owned_panels_by_scope
    config.get_configured_platforms / get_enabled_scenes / get_selected_commands
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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

# 视图状态接口的路由后缀; 完整路由为 /<PLUGIN_NAME>/status
STATUS_ROUTE_SUFFIX = "status"


def mask_appid(appid: Any) -> str:
    """appid 脱敏: 保留前 3 位与后 2 位, 中间用 * 代替

    appid 会展示在视图卡片上, 脱敏避免截图时泄露完整机器人标识。
    过短的 appid 无法保留首尾, 整体打码。
    """
    text = str(appid or "")
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 5)}{text[-2:]}"


def panel_items_count(panel: dict[str, Any]) -> int:
    """统计一个面板 record 的指令条目数, 结构异常时返回 0

    QQ 返回的面板把 items 嵌在 panel 对象里; 兼容旧接口/测试数据里的扁平结构。
    """
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
) -> tuple[dict[str, Any], int]:
    """构造单个平台的状态, 返回 (payload, 该平台线上面板总数)"""
    payload: dict[str, Any] = {
        "pf_id": pf_id,
        "appid": mask_appid(info.get("appid")),
        "source": source,
        "platform": info.get("platform") or getattr(client, "platform_label", "qq"),
        "scenes": [],
    }

    try:
        panels, failed_scopes = await syncer.list_all_panels(client)
    except Exception as exc:
        # list_all_panels 内部已逐场景兜底, 这里只防意外;
        # 单个平台失败不能让整个状态接口 500, 用 error 字段反馈给视图。
        logger.error(
            f"{LOG_TAG} " + t("log.status_platform_failed", pf_id=pf_id, exc=exc),
            exc_info=True,
        )
        payload["scenes"] = [{"scope": scope, "state": "failed"} for scope in scenes]
        payload["error"] = str(exc)
        return payload, 0

    owned = syncer.owned_panels_by_scope(panels)
    for scope in scenes:
        if scope in failed_scopes:
            payload["scenes"].append({"scope": scope, "state": "failed"})
            continue

        panel = owned.get(scope)
        if panel is None:
            payload["scenes"].append({"scope": scope, "state": "missing"})
            continue

        payload["scenes"].append(
            {
                "scope": scope,
                "state": "synced",
                "panel_id": str(panel.get("panel_id", "")),
                "items_count": panel_items_count(panel),
            }
        )
    return payload, len(panels)


async def build_status(
    syncer: PanelSyncer,
    config: dict[str, Any],
    version: str = PLUGIN_VERSION,
) -> dict[str, Any]:
    """组装状态概览响应体 (对应 types/dashboard.ts 的 StatusResponse)

    该接口默认查询线上, 每个平台会对所有场景各调一次 QQ API, 属于慢请求,
    视图只在进入页面/手动刷新时调用。
    """
    platforms, source = get_configured_platforms(config, syncer.context)
    scenes = get_enabled_scenes(config)
    items = get_selected_commands(config)
    clients = syncer.build_clients()

    # 各平台互不依赖, 并发查询缩短整体耗时; list_all_panels 自身不抛异常,
    # 单个平台失败只影响它自己的 payload。
    results = await asyncio.gather(
        *(
            _platform_status(syncer, pf_id, client, platforms.get(pf_id, {}), source, scenes)
            for pf_id, client in clients.items()
        )
    )

    return {
        "plugin": {"name": PLUGIN_NAME, "version": version},
        "platforms": [payload for payload, _ in results],
        "scenes": scenes,
        "items": {"count": len(items), "max": PANEL_MAX_ITEMS},
        # total 为所有平台线上面板数之和; max 为 QQ 单机器人上限
        "panels": {"total": sum(count for _, count in results), "max": PANEL_MAX_ITEMS},
    }


def register_status_api(
    context: Context,
    get_syncer: Callable[[], PanelSyncer | None],
    get_config: Callable[[], dict[str, Any]],
    version: str = PLUGIN_VERSION,
) -> bool:
    """注册视图用的只读 Web API 路由, 成功返回 True

    参数为 provider 而非具体实例: syncer 要到 initialize() 才创建, config 也会
    在运行期刷新, 用回调在每次请求时取最新值。

    老版本 AstrBot 可能没有 astrbot.api.web 或 context.register_web_api,
    此时只记录 warning 并跳过注册, 不影响插件核心的面板同步功能。
    """
    try:
        from astrbot.api.web import error_response, json_response
    except Exception as exc:  # pragma: no cover - 依赖宿主版本, 无法在离线测试覆盖
        logger.warning(f"{LOG_TAG} " + t("log.web_api_unavailable", exc=exc))
        return False

    if not callable(getattr(context, "register_web_api", None)):
        logger.warning(
            f"{LOG_TAG} " + t("log.web_api_unavailable", exc="context.register_web_api missing")
        )
        return False

    async def page_status():  # noqa: ANN202 - 返回值由 astrbot.api.web 决定
        syncer = get_syncer()
        if syncer is None:
            return error_response(t("web.not_ready"), status_code=503)
        return json_response(await build_status(syncer, get_config(), version))

    context.register_web_api(
        f"/{PLUGIN_NAME}/{STATUS_ROUTE_SUFFIX}",
        page_status,
        ["GET"],
        "Plugin dashboard status overview",
    )
    return True


__all__ = [
    "STATUS_ROUTE_SUFFIX",
    "build_status",
    "mask_appid",
    "panel_items_count",
    "register_status_api",
]
