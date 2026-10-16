"""core.web_api 的单元测试

覆盖状态接口的组装逻辑、配置读写（含 secret 掩码与校验）、同步入口的忙闲分支，
以及 WebApiBundle 的路由注册与降级行为。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.config import PANEL_MAX_ITEMS, SCENES
from core.panel_syncer import PanelSyncer
from core.paths import PLUGIN_NAME, PLUGIN_VERSION
from core.robot_config import RobotConfigError, load_robot_config
from core.web_api import (
    CONFIG_ROUTE_SUFFIX,
    ROBOTS_IMPORT_ROUTE_SUFFIX,
    ROBOTS_ROUTE_SUFFIX,
    STATUS_ROUTE_SUFFIX,
    SYNC_EVENTS_ROUTE_SUFFIX,
    SYNC_ROUTE_SUFFIX,
    StatusCache,
    WebApiBundle,
    build_status,
    mask_appid,
    panel_items_count,
    register_web_apis,
)
from tests.fakes import FakeQQClient

REMARK_PREFIX = PanelSyncer.REMARK_PREFIX


@pytest.fixture(autouse=True)
def _reset_web_request() -> Any:
    """每个用例都从干净的 query / body 开始"""
    from astrbot.api.web import request

    request.query.set_values({})
    request.payload = {}
    yield
    request.query.set_values({})
    request.payload = {}


def owned_panel(
    scope: str,
    panel_id: str,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构造一条带本插件 remark 前缀的面板 record"""
    return {
        "panel_id": panel_id,
        "scope": scope,
        "panel": {"items": items or [], "remark": f"{REMARK_PREFIX} qq_official/pf1"},
    }


def make_syncer(config: dict[str, Any] | None = None) -> PanelSyncer:
    """构造 PanelSyncer，context 用 SimpleNamespace 占位（平台信息只来自 config）"""
    return PanelSyncer(
        SimpleNamespace(),  # type: ignore[arg-type]
        http=None,
        data_dir=Path(tempfile.mkdtemp(prefix="qq-panel-webapi-")),
        config=config or {},
    )


def stub_clients(syncer: PanelSyncer, clients: dict[str, FakeQQClient]) -> PanelSyncer:
    """把 build_clients 替换为固定返回值，避免真实创建 QQClient"""
    syncer.build_clients = lambda config=None, **kwargs: clients  # type: ignore[method-assign]
    return syncer


def schema_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "scenes": ["c2c", "group"],
        "qq_platforms": [{"name": "pf1", "appid": "1023456789", "secret": "s"}],
        "selected_commands": [{"name": "help", "desc": "说明"}],
    }
    config.update(overrides)
    return config


async def _async_status_payload() -> dict[str, Any]:
    return {}


# ---------------------------------------------------------------------------
# 纯函数：mask_appid / panel_items_count
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
    # channel 查询失败 => 总量只是下限，partial 为 True；max = 单平台 20 × 1 台
    assert payload["panels"] == {"total": 1, "max": PANEL_MAX_ITEMS, "partial": True}

    platform = payload["platforms"][0]
    assert platform["pf_id"] == "pf1"
    assert platform["appid"] == "102*****89"
    assert platform["platform"] == "qq_official"
    # 插件只能读自己的配置，状态里不再有平台来源字段
    assert "source" not in platform
    assert "error" not in platform

    states = {scene["scope"]: scene["state"] for scene in platform["scenes"]}
    assert states == {"c2c": "synced", "group": "missing", "channel": "failed"}

    c2c = next(scene for scene in platform["scenes"] if scene["scope"] == "c2c")
    assert c2c["panel_id"] == "p1"
    assert c2c["items_count"] == 1


@pytest.mark.asyncio
async def test_build_status_marks_incomplete_total_on_platform_failure() -> None:
    """平台整体异常时总量为下限，partial 用于位置提示"""
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)

    class BoomClient(FakeQQClient):
        async def list_panels(self, scope: str) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

    stub_clients(syncer, {"pf1": BoomClient()})

    payload = await build_status(syncer, config)

    assert payload["panels"]["partial"] is True
    assert payload["panels"]["total"] == 0


@pytest.mark.asyncio
async def test_build_status_flags_duplicate_owned_panels() -> None:
    """同一 scope 下有多条本插件面板时标为 duplicate，否则是 synced"""
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    client = FakeQQClient(existing={"c2c": [owned_panel("c2c", "p1"), owned_panel("c2c", "p2")]})
    stub_clients(syncer, {"pf1": client})

    payload = await build_status(syncer, config)

    scene = payload["platforms"][0]["scenes"][0]
    assert scene["state"] == "duplicate"
    assert scene["panel_id"] == "p1"  # 取第一个，避免暴露多余的副本
    assert payload["panels"] == {"total": 2, "max": PANEL_MAX_ITEMS, "partial": False}


@pytest.mark.asyncio
async def test_build_status_ignores_foreign_panels() -> None:
    """别人的面板不计入本插件同步"""
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    foreign = {"panel_id": "x", "scope": "c2c", "panel": {"items": [], "remark": "other"}}
    stub_clients(syncer, {"pf1": FakeQQClient(existing={"c2c": [foreign]})})

    payload = await build_status(syncer, config)

    assert payload["platforms"][0]["scenes"][0]["state"] == "missing"
    assert payload["panels"]["total"] == 1  # 别人家的面板仍算线上总量
    assert payload["panels"]["partial"] is False


@pytest.mark.asyncio
async def test_build_status_without_platforms() -> None:
    config = {"scenes": ["c2c"]}
    syncer = make_syncer(config)

    payload = await build_status(syncer, config)

    assert payload["platforms"] == []
    assert payload["items"]["count"] == 0
    # 没有平台时不应有综合上限，避免 "0/0" 被当成"已达上限"
    assert payload["panels"] == {"total": 0, "partial": False}


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
    # 综合上限 = 平台数 20 × 2 台
    assert payload["panels"] == {"total": 2, "max": PANEL_MAX_ITEMS * 2, "partial": False}


@pytest.mark.asyncio
async def test_build_status_masks_pf_id_when_it_falls_back_to_appid() -> None:
    """未配备注时 pf_id 会退化成 appid，展示值同样脱敏"""
    config = schema_config(
        scenes=["c2c"],
        qq_platforms=[{"appid": "1112223334", "secret": "s"}],
    )
    syncer = make_syncer(config)
    stub_clients(syncer, {"1112223334": FakeQQClient(existing={})})

    payload = await build_status(syncer, config)

    platform = payload["platforms"][0]
    assert platform["pf_id"] == "111*****34"
    assert platform["appid"] == "111*****34"


@pytest.mark.asyncio
async def test_build_status_uses_current_config_for_clients() -> None:
    """客户端必须按当前传入的 config 构造，避免 syncer 内部配置过期"""
    stale = schema_config(
        scenes=["c2c"],
        qq_platforms=[{"name": "old", "appid": "0000000000", "secret": "s"}],
    )
    current = schema_config(
        scenes=["c2c"],
        qq_platforms=[{"name": "new", "appid": "9999999999", "secret": "s"}],
    )
    syncer = make_syncer(stale)
    fake = FakeQQClient(existing={})
    captured: dict[str, Any] = {}

    def build_clients(config: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        captured["config"] = config
        return {"new": fake}

    syncer.build_clients = build_clients  # type: ignore[method-assign]

    payload = await build_status(syncer, current)

    assert captured["config"] is current
    assert payload["platforms"][0]["pf_id"] == "new"


# ---------------------------------------------------------------------------
# StatusCache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_cache_reuses_result_within_ttl() -> None:
    cache = StatusCache(ttl=60)
    calls = 0

    async def compute() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"n": calls}

    first = await cache.get(compute)
    second = await cache.get(compute)

    assert first == second == {"n": 1}
    assert calls == 1


@pytest.mark.asyncio
async def test_status_cache_force_recomputes() -> None:
    cache = StatusCache(ttl=60)
    calls = 0

    async def compute() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"n": calls}

    await cache.get(compute)
    forced = await cache.get(compute, force=True)

    assert forced == {"n": 2}
    assert calls == 2


@pytest.mark.asyncio
async def test_status_cache_invalidate_drops_value() -> None:
    cache = StatusCache(ttl=60)
    calls = 0

    async def compute() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"n": calls}

    await cache.get(compute)
    cache.invalidate()
    again = await cache.get(compute)

    assert again == {"n": 2}
    assert calls == 2


@pytest.mark.asyncio
async def test_status_cache_coalesces_concurrent_calls() -> None:
    """并发请求只计算一次 (single-flight)，避免重复打 QQ API"""
    cache = StatusCache(ttl=60)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def compute() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"n": calls}

    first = asyncio.create_task(cache.get(compute))
    await started.wait()
    second = asyncio.create_task(cache.get(compute))
    await asyncio.sleep(0)  # 让第二个请求进入等待状态
    release.set()

    r1, r2 = await asyncio.gather(first, second)

    assert r1 == r2 == {"n": 1}
    assert calls == 1


# ---------------------------------------------------------------------------
# WebApiBundle：状态 / 配置
# ---------------------------------------------------------------------------


class FakeContext:
    """记录 register_web_api 调用的假 context"""

    def __init__(self) -> None:
        self.routes: list[tuple[str, Any, list[str], str]] = []

    def register_web_api(self, route: str, handler: Any, methods: list[str], desc: str) -> None:
        self.routes.append((route, handler, methods, desc))


def make_bundle(
    config: dict[str, Any],
    syncer: PanelSyncer,
    save_config: Any = None,
) -> WebApiBundle:
    return WebApiBundle(lambda: syncer, lambda: config, save_config=save_config)


@pytest.mark.asyncio
async def test_page_status_returns_payload_and_uses_cache() -> None:
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)

    class CountingClient(FakeQQClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.list_calls = 0

        async def list_panels(self, scope: str) -> list[dict[str, Any]]:
            self.list_calls += 1
            return await super().list_panels(scope)

    client = CountingClient(existing={})
    stub_clients(syncer, {"pf1": client})
    bundle = make_bundle(config, syncer)

    first = await bundle.page_status()
    second = await bundle.page_status()

    assert first["__json__"] is True
    assert first["data"]["platforms"][0]["pf_id"] == "pf1"
    assert first["data"] == second["data"]
    # 每个状态查询按 SCENES 各查一次，第二次走缓存
    assert client.list_calls == len(SCENES)


@pytest.mark.asyncio
async def test_page_status_reports_not_ready() -> None:
    bundle = WebApiBundle(lambda: None, lambda: {})

    response = await bundle.page_status()

    assert response["__error__"] is True
    assert response["status_code"] == 503


@pytest.mark.asyncio
async def test_page_status_reports_corrupt_robot_config(tmp_path: Path) -> None:
    (tmp_path / "robot_config.json").write_text("{broken", encoding="utf-8")
    syncer = make_syncer({})
    bundle = WebApiBundle(
        lambda: syncer,
        lambda: {},
        robot_config_dir=tmp_path,
    )

    response = await bundle.page_status()

    assert response["__error__"] is True
    assert response["status_code"] == 500
    assert "JSON" in response["message"]


@pytest.mark.asyncio
async def test_page_status_refresh_param_bypasses_cache() -> None:
    from astrbot.api.web import request

    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)

    class CountingClient(FakeQQClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.list_calls = 0

        async def list_panels(self, scope: str) -> list[dict[str, Any]]:
            self.list_calls += 1
            return await super().list_panels(scope)

    client = CountingClient(existing={})
    stub_clients(syncer, {"pf1": client})
    bundle = make_bundle(config, syncer)

    await bundle.page_status()
    cached_calls = client.list_calls
    await bundle.page_status()  # 走缓存，不增加查询次数
    assert client.list_calls == cached_calls

    request.query.set_values({"refresh": "1"})
    await bundle.page_status()

    # refresh=1 绕过缓存，按场景重新查询
    assert client.list_calls == cached_calls + len(SCENES)


@pytest.mark.asyncio
async def test_page_config_get_masks_secret() -> None:
    config = schema_config(
        qq_platforms=[{"name": "pf1", "appid": "1023456789", "secret": "plain-secret-value"}],
    )
    bundle = make_bundle(config, make_syncer(config))

    response = await bundle.page_config_get()

    assert response["__json__"] is True
    platform = response["data"]["qq_platforms"][0]
    assert platform["appid"] == "1023456789"
    assert platform["secret_set"] is True
    assert "plain-secret-value" not in str(response["data"])
    assert platform["secret_masked"].startswith("pla")


@pytest.mark.asyncio
async def test_page_config_save_merges_secret_and_invalidates_cache() -> None:
    from astrbot.api.web import request

    config = schema_config(
        qq_platforms=[{"name": "pf1", "appid": "1023456789", "secret": "old-secret"}],
    )
    syncer = make_syncer(config)
    stub_clients(syncer, {"pf1": FakeQQClient(existing={})})

    saved: dict[str, Any] = {}

    async def save_config(values: dict[str, Any]) -> None:
        saved.update(values)
        config.clear()
        config.update(values)

    bundle = make_bundle(config, syncer, save_config)

    # 先算一次状态，缓存里才有东西可失效
    await bundle.page_status()
    assert bundle.cache._is_fresh() is True

    request.payload = {
        "scenes": ["group"],
        "qq_platforms": [
            {"name": "renamed", "appid": "1023456789", "secret": "", "platform": "qq_official"},
        ],
        "selected_commands": [{"name": "ping", "desc": "Pong"}],
    }

    response = await bundle.page_config_save()

    assert response["__json__"] is True
    # secret 留空 => 沿用原值
    assert saved["qq_platforms"][0]["secret"] == "old-secret"
    assert saved["scenes"] == ["group"]
    assert config["scenes"] == ["group"]
    # 配置变了，状态缓存必须失效
    assert bundle.cache._is_fresh() is False
    assert response["data"]["scenes"] == ["group"]


@pytest.mark.asyncio
async def test_page_config_save_rejects_invalid_payload() -> None:
    from astrbot.api.web import request

    config = schema_config()

    async def save_config(_values: dict[str, Any]) -> None:  # pragma: no cover - 不应被调用
        raise AssertionError("invalid payload must not be persisted")

    bundle = make_bundle(config, make_syncer(config), save_config)
    request.payload = {"language": "fr-FR"}

    response = await bundle.page_config_save()

    assert response["__error__"] is True
    assert response["status_code"] == 400
    assert "language" in response["message"]


@pytest.mark.asyncio
async def test_page_config_save_rejects_non_object_body() -> None:
    from astrbot.api.web import request

    config = schema_config()

    async def save_config(_values: dict[str, Any]) -> None:  # pragma: no cover - 不应被调用
        raise AssertionError("invalid payload must not be persisted")

    bundle = make_bundle(config, make_syncer(config), save_config)
    request.payload = ["nope"]

    response = await bundle.page_config_save()

    assert response["__error__"] is True
    assert response["status_code"] == 400


@pytest.mark.asyncio
async def test_page_config_save_without_persistence_is_unavailable() -> None:
    config = schema_config()
    bundle = make_bundle(config, make_syncer(config))

    response = await bundle.page_config_save()

    assert response["__error__"] is True
    assert response["status_code"] == 503


@pytest.mark.asyncio
async def test_page_config_save_reports_save_failure() -> None:
    from astrbot.api.web import request

    config = schema_config()
    bundle = make_bundle(config, make_syncer(config))

    async def boom(_values: dict[str, Any]) -> None:
        raise RuntimeError("disk full")

    bundle._save_config = boom  # type: ignore[attr-defined]
    request.payload = {"scenes": ["c2c"]}

    response = await bundle.page_config_save()

    assert response["__error__"] is True
    assert response["status_code"] == 500
    assert "disk full" in response["message"]


# ---------------------------------------------------------------------------
# WebApiBundle：新版机器人配置
# ---------------------------------------------------------------------------


def make_robot_bundle(
    config: dict[str, Any],
    robot_dir: Path | None,
    *,
    legacy_config: dict[str, Any] | None = None,
) -> WebApiBundle:
    """构造带新版配置目录的 bundle，旧配置默认复用传入的兼容配置。"""
    return WebApiBundle(
        lambda: None,
        lambda: config,
        robot_config_dir=robot_dir,
        get_legacy_config=lambda: legacy_config if legacy_config is not None else config,
    )


def scene_config(
    *, enabled: bool = False, items: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    """构造一个完整的新版场景配置。"""
    return {"enabled": enabled, "items": list(items or [])}


def robot_payload(
    *,
    appid: str = "1023456789",
    name: str = "主机器人",
    secret: str = "plain-secret-value",
    platform: str = "qq_official",
    scenes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造一台新版机器人提交项。"""
    return {
        "id": "",
        "name": name,
        "appid": appid,
        "platform": platform,
        "secret": secret,
        "scenes": scenes
        or {
            "c2c": scene_config(enabled=True, items=[{"name": "help", "desc": "帮助"}]),
            "group": scene_config(),
            "channel": scene_config(),
            "dm": scene_config(),
        },
    }


def assert_robot_export(
    data: dict[str, Any],
    count: int = 1,
    version: int = 1,
) -> None:
    """断言新版接口响应符合前端 RobotConfigResponse 契约。"""
    assert data["version"] == version
    assert data["available_scenes"] == list(SCENES)
    assert data["limits"] == {
        "name_max": 14,
        "desc_max": 30,
        "items_max": PANEL_MAX_ITEMS,
    }
    assert len(data["robots"]) == count


@pytest.mark.asyncio
async def test_page_robots_get_empty_config(tmp_path: Path) -> None:
    bundle = make_robot_bundle({}, tmp_path)

    response = await bundle.page_robots_get()

    assert response["__json__"] is True
    assert_robot_export(response["data"], count=0)


@pytest.mark.asyncio
async def test_page_robots_get_reports_corrupt_config(tmp_path: Path) -> None:
    (tmp_path / "robot_config.json").write_text("{broken", encoding="utf-8")
    bundle = make_robot_bundle({}, tmp_path)

    response = await bundle.page_robots_get()

    assert response["__error__"] is True
    assert response["status_code"] == 500
    assert "JSON" in response["message"]


@pytest.mark.asyncio
async def test_page_robots_save_creates_robot_with_masked_secret(tmp_path: Path) -> None:
    from astrbot.api.web import request

    bundle = make_robot_bundle({}, tmp_path)
    request.payload = {"version": 1, "robots": [robot_payload()]}

    response = await bundle.page_robots_save()

    assert response["__json__"] is True
    assert_robot_export(response["data"], version=2)
    robot = response["data"]["robots"][0]
    assert robot["id"]
    assert robot["secret_set"] is True
    assert robot["secret_masked"].startswith("pla")
    assert "plain-secret-value" not in str(response["data"])
    stored = load_robot_config(tmp_path)
    assert stored["robots"][0]["secret"] == "plain-secret-value"


@pytest.mark.asyncio
async def test_page_robots_save_invalidates_status_cache(tmp_path: Path) -> None:
    from astrbot.api.web import request

    bundle = make_robot_bundle({}, tmp_path)
    await bundle.cache.get(_async_status_payload)
    assert bundle.cache._is_fresh()
    request.payload = {"version": 1, "robots": [robot_payload()]}

    response = await bundle.page_robots_save()

    assert response["__json__"] is True
    assert not bundle.cache._is_fresh()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["scene", "duplicate"])
async def test_page_robots_save_rejects_invalid_payload(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    from astrbot.api.web import request

    bundle = make_robot_bundle({}, tmp_path)
    if invalid_kind == "scene":
        first = robot_payload(
            scenes={
                "c2c": scene_config(enabled=True, items=[]),
                "group": scene_config(),
                "channel": scene_config(),
                "dm": scene_config(),
            }
        )
        payload = {"version": 1, "robots": [first]}
        expected = "至少需要 1 条"
    else:
        payload = {
            "version": 1,
            "robots": [robot_payload(), robot_payload(name="重复")],
        }
        expected = "重复"
    request.payload = payload

    response = await bundle.page_robots_save()

    assert response["__error__"] is True
    assert response["status_code"] == 400
    assert expected in response["message"]
    assert load_robot_config(tmp_path)["robots"] == []


@pytest.mark.asyncio
async def test_page_robots_save_keeps_secret_when_blank(tmp_path: Path) -> None:
    from astrbot.api.web import request

    bundle = make_robot_bundle({}, tmp_path)
    request.payload = {"version": 1, "robots": [robot_payload()]}
    await bundle.page_robots_save()

    request.payload = {"version": 2, "robots": [robot_payload(secret="")]}
    response = await bundle.page_robots_save()

    assert response["__json__"] is True
    assert response["data"]["version"] == 3
    stored = load_robot_config(tmp_path)
    assert stored["robots"][0]["secret"] == "plain-secret-value"
    assert response["data"]["robots"][0]["secret_set"] is True


@pytest.mark.asyncio
async def test_page_robots_save_rejects_stale_version(tmp_path: Path) -> None:
    from astrbot.api.web import request

    bundle = make_robot_bundle({}, tmp_path)
    request.payload = {"version": 1, "robots": [robot_payload(name="初次保存")]}
    first = await bundle.page_robots_save()
    assert first["data"]["version"] == 2

    request.payload = {"version": 1, "robots": [robot_payload(name="旧页面覆盖")]}
    stale = await bundle.page_robots_save()

    assert stale["__error__"] is True
    assert stale["status_code"] == 409
    assert "重新载入" in stale["message"]
    assert load_robot_config(tmp_path)["robots"][0]["name"] == "初次保存"


@pytest.mark.asyncio
async def test_page_robots_import_legacy_copies_secret_without_response_leak(
    tmp_path: Path,
) -> None:
    from astrbot.api.web import request

    legacy = schema_config(
        qq_platforms=[{"name": "旧机器人", "appid": "1023456789", "secret": "legacy-secret"}],
    )
    bundle = make_robot_bundle({}, tmp_path, legacy_config=legacy)
    request.payload = {"appid": "1023456789", "version": 1}

    response = await bundle.page_robots_import_legacy()

    assert response["__json__"] is True
    assert_robot_export(response["data"], version=2)
    assert "legacy-secret" not in str(response["data"])
    stored = load_robot_config(tmp_path)
    assert stored["robots"][0]["secret"] == "legacy-secret"


@pytest.mark.asyncio
async def test_page_robots_import_invalidates_status_cache(tmp_path: Path) -> None:
    from astrbot.api.web import request

    legacy = schema_config(
        qq_platforms=[{"name": "旧机器人", "appid": "1023456789", "secret": "legacy-secret"}],
    )
    bundle = make_robot_bundle({}, tmp_path, legacy_config=legacy)
    await bundle.cache.get(_async_status_payload)
    assert bundle.cache._is_fresh()
    request.payload = {"appid": "1023456789", "version": 1}

    response = await bundle.page_robots_import_legacy()

    assert response["__json__"] is True
    assert not bundle.cache._is_fresh()


@pytest.mark.asyncio
async def test_page_robots_import_legacy_rejects_duplicate_appid(tmp_path: Path) -> None:
    from astrbot.api.web import request

    legacy = schema_config(
        qq_platforms=[{"name": "旧机器人", "appid": "1023456789", "secret": "legacy-secret"}],
    )
    bundle = make_robot_bundle({}, tmp_path, legacy_config=legacy)
    request.payload = {"version": 1, "robots": [robot_payload()]}
    saved = await bundle.page_robots_save()

    request.payload = {"appids": ["1023456789"], "version": saved["data"]["version"]}
    response = await bundle.page_robots_import_legacy()

    assert response["__error__"] is True
    assert response["status_code"] == 400
    assert "已存在" in response["message"]


@pytest.mark.asyncio
async def test_page_robots_unavailable_without_config_dir() -> None:
    from astrbot.api.web import request

    bundle = WebApiBundle(lambda: None, lambda: {})
    request.payload = {"version": 1, "robots": []}

    get_response = await bundle.page_robots_get()
    save_response = await bundle.page_robots_save()
    import_response = await bundle.page_robots_import_legacy()

    for response in (get_response, save_response, import_response):
        assert response["__error__"] is True
        assert response["status_code"] == 503
        assert "尚未启用" in response["message"]


@pytest.mark.asyncio
async def test_page_robots_reports_explicit_loader_errors(tmp_path: Path, monkeypatch: Any) -> None:
    bundle = make_robot_bundle({}, tmp_path)

    def fail(_data_dir: Path) -> dict[str, Any]:
        raise RobotConfigError("配置损坏")

    monkeypatch.setattr("core.web_api.load_robot_config", fail)

    response = await bundle.page_robots_get()

    assert response["__error__"] is True
    assert response["status_code"] == 500
    assert "配置损坏" in response["message"]


# ---------------------------------------------------------------------------
# WebApiBundle：同步入口
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_page_sync_start_and_busy() -> None:
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    client = FakeQQClient(existing={})
    stub_clients(syncer, {"pf1": client})
    bundle = make_bundle(config, syncer)

    first = await bundle.page_sync_start()
    assert first["__json__"] is True
    assert first["data"] == {"started": True, "busy": False}
    await bundle.runner.join()
    assert client.created  # 同步确实写入了 FakeQQClient

    # 挂一个不结束的任务，验证"已有任务在跑"的分支
    release = asyncio.Event()

    async def slow_run(_emit: Any) -> dict[str, Any]:
        await release.wait()
        return {}

    assert bundle.runner.start(slow_run) is True
    second = await bundle.page_sync_start()
    assert second["data"] == {"started": False, "busy": True}

    release.set()
    await bundle.runner.join()


@pytest.mark.asyncio
async def test_page_sync_start_not_ready() -> None:
    bundle = WebApiBundle(lambda: None, lambda: {})

    response = await bundle.page_sync_start()

    assert response["__error__"] is True
    assert response["status_code"] == 503


@pytest.mark.asyncio
async def test_page_sync_start_streams_structured_events() -> None:
    """同步任务的进度事件：message + start/platform/finish 结构化事件"""
    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    stub_clients(syncer, {"pf1": FakeQQClient(existing={})})
    bundle = make_bundle(config, syncer)

    await bundle.page_sync_start()
    events = [event async for event in bundle.runner.stream(0)]

    types = [event["type"] for event in events]
    # start 先到：dashboard 收到 start 会清空日志，开场文本必须排在其后
    assert types[0] == "start"
    assert types[1] == "message"
    assert "message" in types
    assert "platform" in types
    assert types[-1] == "finish"

    start = next(event for event in events if event["type"] == "start")
    assert start["platforms"] == 1
    assert start["scenes"] == 1
    assert start["items"] == 1

    platform_event = next(event for event in events if event["type"] == "platform")
    assert platform_event["pf_id"] == "pf1"
    assert platform_event["status"] == "ok"
    assert platform_event["index"] == 1
    assert platform_event["total"] == 1

    finish = events[-1]
    assert finish["ok"] is True
    assert finish["succeeded"] == 1
    assert finish["failed"] == 0


@pytest.mark.asyncio
async def test_page_sync_events_returns_stream_and_honours_since() -> None:
    from astrbot.api.web import request

    config = schema_config(scenes=["c2c"])
    syncer = make_syncer(config)
    stub_clients(syncer, {"pf1": FakeQQClient(existing={})})
    bundle = make_bundle(config, syncer)

    await bundle.page_sync_start()
    request.query.set_values({"since": str(bundle.runner.last_seq)})

    response = await bundle.page_sync_events()

    assert response["__stream__"] is True


@pytest.mark.asyncio
async def test_page_sync_events_not_ready() -> None:
    bundle = WebApiBundle(lambda: None, lambda: {})

    response = await bundle.page_sync_events()

    assert response["__error__"] is True
    assert response["status_code"] == 503


# ---------------------------------------------------------------------------
# register_web_apis
# ---------------------------------------------------------------------------


def test_register_web_apis_registers_all_routes() -> None:
    config = schema_config()
    syncer = make_syncer(config)
    context = FakeContext()

    bundle = register_web_apis(context, lambda: syncer, lambda: config)

    assert bundle is not None
    routes = {(route, tuple(methods)) for route, _h, methods, _d in context.routes}
    assert routes == {
        (f"/{PLUGIN_NAME}/{STATUS_ROUTE_SUFFIX}", ("GET",)),
        (f"/{PLUGIN_NAME}/{CONFIG_ROUTE_SUFFIX}", ("GET",)),
        (f"/{PLUGIN_NAME}/{CONFIG_ROUTE_SUFFIX}", ("POST",)),
        (f"/{PLUGIN_NAME}/{ROBOTS_ROUTE_SUFFIX}", ("GET",)),
        (f"/{PLUGIN_NAME}/{ROBOTS_ROUTE_SUFFIX}", ("POST",)),
        (f"/{PLUGIN_NAME}/{ROBOTS_IMPORT_ROUTE_SUFFIX}", ("POST",)),
        (f"/{PLUGIN_NAME}/{SYNC_ROUTE_SUFFIX}", ("POST",)),
        (f"/{PLUGIN_NAME}/{SYNC_EVENTS_ROUTE_SUFFIX}", ("GET",)),
    }


def test_register_web_apis_skips_without_host_method() -> None:
    """老版本 AstrBot 的 context 没有 register_web_api 时应静默降级"""
    assert register_web_apis(SimpleNamespace(), lambda: None, lambda: {}) is None
