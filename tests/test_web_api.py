"""core.web_api 的单元测试

覆盖视图状态接口 (GET /<plugin>/status) 的组装逻辑:
- build_status 的字段契约 (对应 types/dashboard.ts 的 StatusResponse)
- appid 脱敏 / 条目计数等纯函数
- register_status_api 的路由注册与降级 (老版本 AstrBot 无 register_web_api)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.config import PANEL_MAX_ITEMS
from core.panel_syncer import PanelSyncer
from core.paths import PLUGIN_NAME, PLUGIN_VERSION
from core.web_api import (
    STATUS_ROUTE_SUFFIX,
    build_status,
    mask_appid,
    panel_items_count,
    register_status_api,
)
from tests.fakes import FakeQQClient

REMARK_PREFIX = PanelSyncer.REMARK_PREFIX


def owned_panel(
    scope: str,
    panel_id: str,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构造一个带本插件 remark 前缀的面板 record"""
    return {
        "panel_id": panel_id,
        "scope": scope,
        "panel": {"items": items or [], "remark": f"{REMARK_PREFIX} qq_official/pf1"},
    }


def make_syncer(config: dict[str, Any] | None = None) -> PanelSyncer:
    """构造 PanelSyncer, context 用 SimpleNamespace 代替 (无平台配置时回退 context)"""
    return PanelSyncer(
        SimpleNamespace(),  # type: ignore[arg-type]
        http=None,
        data_dir=Path(tempfile.mkdtemp(prefix="qq-panel-webapi-")),
        config=config or {},
    )


def stub_clients(syncer: PanelSyncer, clients: dict[str, FakeQQClient]) -> PanelSyncer:
    """把 build_clients 替换为固定返回值, 避免真实构造 QQClient"""
    syncer.build_clients = lambda: clients  # type: ignore[method-assign]
    return syncer


def schema_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "scenes": ["c2c", "group"],
        "qq_platforms": [{"name": "pf1", "appid": "1023456789", "secret": "s"}],
        "selected_commands": [{"name": "help", "desc": "帮助"}],
    }
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# 纯函数: mask_appid / panel_items_count
# ---------------------------------------------------------------------------


def test_mask_appid_keeps_head_and_tail() -> None:
    assert mask_appid("1023456789") == "102*****89"


def test_mask_appid_short_is_fully_masked() -> None:
    assert mask_appid("abc") == "***"


def test_mask_appid_empty() -> None:
    assert mask_appid(None) == ""
    assert mask_appid("") == ""


def test_panel_items_count_nested() -> None:
    assert panel_items_count({"panel": {"items": [1, 2, 3]}}) == 3


def test_panel_items_count_flat() -> None:
    assert panel_items_count({"items": [1, 2]}) == 2


def test_panel_items_count_missing() -> None:
    assert panel_items_count({}) == 0
    assert panel_items_count({"panel": {"items": "oops"}}) == 0


# ---------------------------------------------------------------------------
# build_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_status_reports_scene_states() -> None:
    config = schema_config(scenes=["c2c", "group", "channel"])
    syncer = make_syncer(config)
    client = FakeQQClient(
        existing={"c2c": [owned_panel("c2c", "p1", [{"name": "help"}])]},
        failing_scopes={"channel"},
    )
    stub_clients(syncer, {"pf1": client})

    payload = await build_status(syncer, config)

    assert payload["plugin"]["name"] == PLUGIN_NAME
    assert payload["plugin"]["version"] == PLUGIN_VERSION
    assert payload["scenes"] == ["c2c", "group", "channel"]
    assert payload["items"] == {"count": 1, "max": PANEL_MAX_ITEMS}
    assert payload["panels"] == {"total": 1, "max": PANEL_MAX_ITEMS}

    platform = payload["platforms"][0]
    assert platform["pf_id"] == "pf1"
    assert platform["appid"] == "102*****89"
    assert platform["source"] == "schema"
    assert platform["platform"] == "qq_official"
    assert "error" not in platform

    states = {scene["scope"]: scene["state"] for scene in platform["scenes"]}
    assert states == {"c2c": "synced", "group": "missing", "channel": "failed"}

    c2c = next(scene for scene in platform["scenes"] if scene["scope"] == "c2c")
    assert c2c["panel_id"] == "p1"
    assert c2c["items_count"] == 1


@pytest.mark.asyncio
async def test_build_status_ignores_foreign_panels() -> None:
    """他方面板不算本插件已同步"""
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    foreign = {"panel_id": "x", "scope": "c2c", "panel": {"items": [], "remark": "other"}}
    stub_clients(syncer, {"pf1": FakeQQClient(existing={"c2c": [foreign]})})

    payload = await build_status(syncer, config)

    assert payload["platforms"][0]["scenes"][0]["state"] == "missing"
    assert payload["panels"]["total"] == 1  # 线上面板总数包含他方面板


@pytest.mark.asyncio
async def test_build_status_without_platforms() -> None:
    config = {"scenes": ["c2c"]}
    syncer = make_syncer(config)

    payload = await build_status(syncer, config)

    assert payload["platforms"] == []
    assert payload["panels"]["total"] == 0
    assert payload["items"]["count"] == 0


@pytest.mark.asyncio
async def test_build_status_summarizes_multiple_platforms() -> None:
    config = schema_config(
        scenes=["c2c"],
        qq_platforms=[
            {"name": "pf1", "appid": "1112223334", "secret": "s1"},
            {"name": "pf2", "appid": "5556667778", "secret": "s2"},
        ],
    )
    syncer = make_syncer(config)
    stub_clients(
        syncer,
        {
            "pf1": FakeQQClient(existing={"c2c": [owned_panel("c2c", "p1")]}),
            "pf2": FakeQQClient(existing={"c2c": [owned_panel("c2c", "p2")]}),
        },
    )

    payload = await build_status(syncer, config)

    assert {p["pf_id"] for p in payload["platforms"]} == {"pf1", "pf2"}
    assert payload["panels"]["total"] == 2


# ---------------------------------------------------------------------------
# register_status_api
# ---------------------------------------------------------------------------


class FakeContext:
    """记录 register_web_api 调用的假 context"""

    def __init__(self) -> None:
        self.routes: list[tuple[str, Any, list[str], str]] = []

    def register_web_api(self, route: str, handler: Any, methods: list[str], desc: str) -> None:
        self.routes.append((route, handler, methods, desc))


@pytest.mark.asyncio
async def test_register_status_api_registers_and_serves() -> None:
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    stub_clients(syncer, {"pf1": FakeQQClient(existing={})})
    context = FakeContext()

    assert register_status_api(context, lambda: syncer, lambda: config) is True

    route, handler, methods, _desc = context.routes[0]
    assert route == f"/{PLUGIN_NAME}/{STATUS_ROUTE_SUFFIX}"
    assert methods == ["GET"]

    response = await handler()
    assert response["__json__"] is True
    assert response["data"]["platforms"][0]["pf_id"] == "pf1"


@pytest.mark.asyncio
async def test_status_handler_reports_not_ready() -> None:
    context = FakeContext()
    register_status_api(context, lambda: None, lambda: {})

    _route, handler, _methods, _desc = context.routes[0]
    response = await handler()

    assert response["__error__"] is True
    assert response["status_code"] == 503


def test_register_status_api_skips_without_host_method() -> None:
    """老版本 AstrBot 的 context 没有 register_web_api 时应降级, 不抛异常"""
    assert register_status_api(SimpleNamespace(), lambda: None, lambda: {}) is False
