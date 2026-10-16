"""core.panel_syncer.PanelSyncer 的单元测试（注入 FakeQQClient / fake context）

重点覆盖 AGENTS.md 中 "任一场景拉取失败要中止" 的关键约定，
以及 sync / clear / purge 的核心分支。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.panel_syncer import PanelSyncer
from tests.fakes import FakeQQClient

REMARK_PREFIX = PanelSyncer.REMARK_PREFIX


def owned_panel(scope: str, panel_id: str, pf: str = "pf1") -> dict[str, Any]:
    """构造一个带本插件 remark 前缀的面板 record"""
    platform = "qq_official"
    return {
        "panel_id": panel_id,
        "scope": scope,
        "panel": {"items": [], "remark": f"{REMARK_PREFIX} {platform}/{pf}"},
    }


def foreign_panel(scope: str, panel_id: str) -> dict[str, Any]:
    """构造一个不带 remark 前缀的面板 record（他人创建）"""
    return {
        "panel_id": panel_id,
        "scope": scope,
        "panel": {"items": [], "remark": "someone else"},
    }


def make_syncer(
    config: dict[str, Any] | None = None,
    context_attrs: dict[str, Any] | None = None,
) -> PanelSyncer:
    """构造 PanelSyncer, context 用 SimpleNamespace 代替

    data_dir 用一次性临时目录：PanelSyncer.__init__ 会用它初始化
    PanelStateStore，本文件不对其内容做断言。
    """
    context = SimpleNamespace(**(context_attrs or {}))
    return PanelSyncer(
        context,  # type: ignore[arg-type]
        http=None,
        data_dir=Path(tempfile.mkdtemp(prefix="qq-panel-test-")),
        config=config if config is not None else {},
    )


# ---------------------------------------------------------------------------
# is_owned_panel
# ---------------------------------------------------------------------------


def test_is_owned_panel_by_nested_remark() -> None:
    assert PanelSyncer.is_owned_panel(owned_panel("c2c", "p1")) is True


def test_is_owned_panel_by_flat_remark() -> None:
    panel = {"panel_id": "p1", "remark": f"{REMARK_PREFIX} x/y"}
    assert PanelSyncer.is_owned_panel(panel) is True


def test_is_owned_panel_false_for_foreign() -> None:
    assert PanelSyncer.is_owned_panel(foreign_panel("c2c", "p1")) is False


def test_is_owned_panel_false_for_missing_remark() -> None:
    assert PanelSyncer.is_owned_panel({"panel_id": "p1"}) is False


# ---------------------------------------------------------------------------
# list_all_panels: 失败场景收集（AGENTS.md 约定 2 的核心）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_all_panels_collects_failed_scopes() -> None:
    syncer = make_syncer()
    client = FakeQQClient(existing={"c2c": []}, failing_scopes={"group"})

    panels, failed = await syncer.list_all_panels(client)

    assert "group" in failed
    assert "c2c" not in failed
    assert panels == []


@pytest.mark.asyncio
async def test_list_all_panels_merges_all_scopes() -> None:
    syncer = make_syncer()
    client = FakeQQClient(
        existing={
            "c2c": [owned_panel("c2c", "p_c2c")],
            "group": [owned_panel("group", "p_group")],
        }
    )

    panels, failed = await syncer.list_all_panels(client)

    assert failed == set()
    assert {p["panel_id"] for p in panels} == {"p_c2c", "p_group"}


# ---------------------------------------------------------------------------
# sync_for_platform: 正常同步 / 中止 / 清理 / 上限
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_creates_panel_for_each_scene() -> None:
    syncer = make_syncer()
    client = FakeQQClient(existing={})
    items = [{"name": "help", "type": "command", "desc": "帮助"}]

    saved = await syncer.sync_for_platform("pf1", client, ["c2c", "group"], items)

    assert set(saved) == {"c2c", "group"}
    assert len(client.created) == 2
    assert client.updated == []


@pytest.mark.asyncio
async def test_sync_updates_existing_owned_panel() -> None:
    syncer = make_syncer()
    client = FakeQQClient(existing={"c2c": [owned_panel("c2c", "p_old")]})
    items = [{"name": "help", "type": "command", "desc": "帮助"}]

    saved = await syncer.sync_for_platform("pf1", client, ["c2c"], items)

    assert saved == {"c2c": "p_old"}
    assert client.updated == [("p_old", items)]
    assert client.created == []


@pytest.mark.asyncio
async def test_sync_aborts_when_any_scope_list_fails() -> None:
    """AGENTS.md 约定：任一场景拉取失败要中止，不许吞异常（防重复建面板）"""
    syncer = make_syncer()
    client = FakeQQClient(existing={}, failing_scopes={"channel"})

    with pytest.raises(RuntimeError, match="channel"):
        await syncer.sync_for_platform("pf1", client, ["c2c"], [{"name": "a"}])

    # 中止后不允许任何写操作
    assert client.created == []
    assert client.updated == []
    assert client.deleted == []


@pytest.mark.asyncio
async def test_sync_skips_foreign_panels_on_limit() -> None:
    """他方面板计入 total_panels: 剩余额度不足时不再新建"""
    syncer = make_syncer()
    # 20 个他方面板 → total 达上限
    existing = {s: [foreign_panel(s, f"f_{s}_{i}") for i in range(20)] for s in ("c2c",)}
    client = FakeQQClient(existing=existing)

    saved = await syncer.sync_for_platform("pf1", client, ["group"], [{"name": "a"}])

    assert saved == {}
    assert client.created == []


@pytest.mark.asyncio
async def test_sync_empty_items_deletes_owned_panels_only() -> None:
    syncer = make_syncer()
    client = FakeQQClient(
        existing={
            "c2c": [owned_panel("c2c", "p_mine"), foreign_panel("c2c", "p_theirs")],
            "group": [owned_panel("group", "p_mine_g")],
        }
    )

    saved = await syncer.sync_for_platform("pf1", client, ["c2c"], [])

    assert saved == {}
    assert sorted(client.deleted) == ["p_mine", "p_mine_g"]
    assert "p_theirs" not in client.deleted


@pytest.mark.asyncio
async def test_sync_cleans_disabled_scene_panels() -> None:
    """已停用场景的旧 owned 面板应被清理"""
    syncer = make_syncer()
    client = FakeQQClient(
        existing={
            "channel": [owned_panel("channel", "p_disabled")],
        }
    )

    await syncer.sync_for_platform("pf1", client, ["c2c", "group"], [{"name": "a"}])

    assert client.deleted == ["p_disabled"]
    # c2c/group 正常创建
    assert len(client.created) == 2


@pytest.mark.asyncio
async def test_sync_create_failure_does_not_break_other_scopes() -> None:
    """某场景 create 失败仅记录 error，不影响其他场景"""
    syncer = make_syncer()

    class PartialClient(FakeQQClient):
        async def create_panel(self, scope, items, **kwargs):  # type: ignore[override]
            if scope == "c2c":
                raise RuntimeError("boom")
            return await super().create_panel(scope, items, **kwargs)

    client = PartialClient(existing={})
    saved = await syncer.sync_for_platform("pf1", client, ["c2c", "group"], [{"name": "a"}])

    assert saved == {"group": saved["group"]}
    assert "c2c" not in saved


# ---------------------------------------------------------------------------
# build_clients
# ---------------------------------------------------------------------------


def test_build_clients_from_schema_config() -> None:
    syncer = make_syncer(
        config={
            "qq_platforms": [
                {"name": "pf1", "appid": "a1", "secret": "s1"},
            ]
        }
    )
    clients = syncer.build_clients()
    assert set(clients) == {"pf1"}
    assert clients["pf1"].appid == "a1"
    assert clients["pf1"].platform_label == "qq_official"


def test_build_clients_ignores_context_platform_settings() -> None:
    """插件读不到平台适配器的机器人信息，context 里就算有 platform_settings 也不采用"""
    syncer = make_syncer(
        context_attrs={
            "platform_settings": [
                {"enable": True, "type": "qq_official", "id": "ctx1", "appid": "a", "secret": "s"},
            ]
        }
    )
    assert syncer.build_clients() == {}


# ---------------------------------------------------------------------------
# clear_for_platform
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_removes_owned_panels_only() -> None:
    syncer = make_syncer()
    client = FakeQQClient(
        existing={
            "c2c": [owned_panel("c2c", "p_mine"), foreign_panel("c2c", "p_theirs")],
        }
    )

    await syncer.clear_for_platform("pf1", client)

    assert client.deleted == ["p_mine"]


@pytest.mark.asyncio
async def test_clear_tolerates_scope_list_failure() -> None:
    """clear 路径容忍部分场景失败（删得掉多少算多少）"""
    syncer = make_syncer()
    client = FakeQQClient(
        existing={"c2c": [owned_panel("c2c", "p_mine")]},
        failing_scopes={"channel"},  # channel 查失败不影响 clear
    )

    await syncer.clear_for_platform("pf1", client)
    assert client.deleted == ["p_mine"]


# ---------------------------------------------------------------------------
# set_config: 运行期刷新
# ---------------------------------------------------------------------------


def test_set_config_updates_reference() -> None:
    syncer = make_syncer(config={"selected_commands": []})
    syncer.set_config({"qq_platforms": [{"appid": "x", "secret": "y"}]})
    clients = syncer.build_clients()
    assert set(clients) == {"x"}


# ---------------------------------------------------------------------------
# build_clients: 显式 config 参数
# ---------------------------------------------------------------------------


def test_build_clients_accepts_explicit_config() -> None:
    """传入当前配置时应按它构建，而不是用 syncer 内部可能过期的配置"""
    syncer = make_syncer(config={"qq_platforms": [{"name": "old", "appid": "a1", "secret": "s"}]})
    clients = syncer.build_clients(
        {"qq_platforms": [{"name": "new", "appid": "a2", "secret": "s"}]}
    )
    assert set(clients) == {"new"}
    assert clients["new"].appid == "a2"


# ---------------------------------------------------------------------------
# owned_panels_by_scope: 保留全部记录
# ---------------------------------------------------------------------------


def test_owned_panels_by_scope_keeps_all_records_in_order() -> None:
    syncer = make_syncer()
    grouped = syncer.owned_panels_by_scope(
        [
            owned_panel("c2c", "p1"),
            foreign_panel("c2c", "x"),
            owned_panel("c2c", "p2"),
            owned_panel("group", "g1"),
        ]
    )
    assert [p["panel_id"] for p in grouped["c2c"]] == ["p1", "p2"]
    assert [p["panel_id"] for p in grouped["group"]] == ["g1"]


def test_owned_panels_by_scope_skips_panels_without_scope() -> None:
    syncer = make_syncer()
    panel = owned_panel("c2c", "p1")
    panel.pop("scope")
    assert syncer.owned_panels_by_scope([panel]) == {}


# ---------------------------------------------------------------------------
# 重复 owned 面板的同步行为
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_updates_first_owned_panel_when_duplicated() -> None:
    """同一 scope 有多条 owned 面板时只更新第一条（不再被后一条覆盖）"""
    syncer = make_syncer()
    client = FakeQQClient(existing={"c2c": [owned_panel("c2c", "p1"), owned_panel("c2c", "p2")]})
    items = [{"name": "a", "type": "command", "desc": ""}]

    saved = await syncer.sync_for_platform("pf1", client, ["c2c"], items)

    assert saved == {"c2c": "p1"}
    assert client.updated == [("p1", items)]


@pytest.mark.asyncio
async def test_sync_empty_items_deletes_all_duplicate_owned_panels() -> None:
    """清空指令时同 scope 的重复面板要一并删除，不能只删一条"""
    syncer = make_syncer()
    client = FakeQQClient(existing={"c2c": [owned_panel("c2c", "p1"), owned_panel("c2c", "p2")]})

    await syncer.sync_for_platform("pf1", client, ["c2c"], [])

    assert sorted(client.deleted) == ["p1", "p2"]


# ---------------------------------------------------------------------------
# sync_all: 结构化进度事件（dashboard 的 SSE 就靠这些事件渲染）
# ---------------------------------------------------------------------------


def stub_clients(syncer: PanelSyncer, clients: dict[str, FakeQQClient]) -> PanelSyncer:
    """把 build_clients 换成固定返回值，避免真实创建 QQClient"""
    syncer.build_clients = lambda config=None, **kwargs: clients  # type: ignore[method-assign]
    return syncer


async def collect_events() -> tuple[list[dict[str, Any]], Any]:
    """构造一个把事件收进列表的回调"""
    events: list[dict[str, Any]] = []

    async def on_event(event: dict[str, Any]) -> None:
        events.append(event)

    return events, on_event


@pytest.mark.asyncio
async def test_sync_all_emits_finish_when_no_scene_enabled() -> None:
    syncer = make_syncer(config={"scenes": []})
    events, on_event = await collect_events()

    result = await syncer.sync_all(on_event=on_event)

    assert result == {}
    assert [event["type"] for event in events] == ["finish"]
    assert events[0]["reason"] == "no_scene"
    assert events[0]["ok"] is True


@pytest.mark.asyncio
async def test_sync_all_emits_finish_when_no_platform() -> None:
    syncer = make_syncer(config={"scenes": ["c2c"]})
    events, on_event = await collect_events()

    result = await syncer.sync_all(on_event=on_event)

    assert result == {}
    assert [event["type"] for event in events] == ["finish"]
    assert events[0]["reason"] == "no_platform"


@pytest.mark.asyncio
async def test_sync_all_emits_start_platform_and_finish() -> None:
    syncer = make_syncer(
        config={
            "scenes": ["c2c"],
            "qq_platforms": [{"name": "pf1", "appid": "app", "secret": "sec"}],
            "selected_commands": [{"name": "help", "desc": "帮助"}],
        }
    )
    client = FakeQQClient(existing={})
    stub_clients(syncer, {"pf1": client})
    events, on_event = await collect_events()

    result = await syncer.sync_all(on_event=on_event)

    assert [event["type"] for event in events] == ["start", "platform", "finish"]
    start, platform_event, finish = events
    assert start["platforms"] == 1
    assert start["scenes"] == 1
    assert start["items"] == 1
    assert platform_event["pf_id"] == "pf1"
    assert platform_event["index"] == 1
    assert platform_event["status"] == "ok"
    assert platform_event["saved"] == 1
    assert finish["ok"] is True
    assert finish["succeeded"] == 1
    assert finish["failed"] == 0
    assert result == {"pf1": {"c2c": "panel_new_1001"}}


@pytest.mark.asyncio
async def test_sync_all_reports_failed_platform_in_events() -> None:
    syncer = make_syncer(
        config={
            "scenes": ["c2c"],
            "qq_platforms": [{"name": "pf1", "appid": "app", "secret": "sec"}],
            "selected_commands": [{"name": "help", "desc": "帮助"}],
        }
    )
    # 场景列表查询失败 => sync_for_platform 抛错 => 平台标记失败
    client = FakeQQClient(existing={}, failing_scopes={"c2c"})
    stub_clients(syncer, {"pf1": client})
    events, on_event = await collect_events()

    result = await syncer.sync_all(on_event=on_event)

    platform_event = next(event for event in events if event["type"] == "platform")
    assert platform_event["status"] == "error"
    assert platform_event["saved"] == 0
    assert platform_event["error"]
    finish = events[-1]
    assert finish["type"] == "finish"
    assert finish["ok"] is False
    assert finish["failed"] == 1
    assert "error" in result["pf1"]


@pytest.mark.asyncio
async def test_sync_all_clearing_branch_emits_structured_events() -> None:
    """selected_commands 为空时走清理分支，同样要有 start/platform/finish"""
    syncer = make_syncer(
        config={
            "scenes": ["c2c"],
            "qq_platforms": [{"name": "pf1", "appid": "app", "secret": "sec"}],
            "selected_commands": [],
        }
    )
    client = FakeQQClient(existing={"c2c": [owned_panel("c2c", "p_old")]})
    stub_clients(syncer, {"pf1": client})
    events, on_event = await collect_events()

    result = await syncer.sync_all(on_event=on_event)

    assert result == {}
    assert [event["type"] for event in events] == ["start", "platform", "finish"]
    assert events[0]["mode"] == "clear"
    assert events[0]["items"] == 0
    assert events[1]["status"] == "ok"
    assert events[2]["reason"] == "clear"
    assert client.deleted == ["p_old"]


# ---------------------------------------------------------------------------
# v2：每个机器人、每个场景使用各自的条目
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_for_platform_uses_per_scene_items() -> None:
    syncer = make_syncer()
    client = FakeQQClient(existing={})

    saved = await syncer.sync_for_platform(
        "robot-a",
        client,
        {
            "c2c": [{"name": "help", "desc": "私聊帮助"}],
            "group": [{"name": "sign", "desc": "群签到"}],
        },
    )

    assert set(saved) == {"c2c", "group"}
    by_scope = {scope: items for scope, items in client.created}
    assert [item["name"] for item in by_scope["c2c"]] == ["help"]
    assert [item["name"] for item in by_scope["group"]] == ["sign"]


@pytest.mark.asyncio
async def test_sync_for_platform_clears_disabled_scene_only() -> None:
    syncer = make_syncer()
    client = FakeQQClient(
        existing={
            "c2c": [owned_panel("c2c", "p_c2c")],
            "group": [owned_panel("group", "p_group")],
        }
    )

    saved = await syncer.sync_for_platform(
        "robot-a",
        client,
        {"group": [{"name": "sign", "desc": "群签到"}]},
    )

    assert set(saved) == {"group"}
    assert "p_c2c" in client.deleted
    assert "p_group" not in client.deleted


@pytest.mark.asyncio
async def test_sync_all_uses_v2_robot_scenes(monkeypatch) -> None:
    syncer = make_syncer()
    client_a = FakeQQClient(existing={})
    client_b = FakeQQClient(existing={})
    stub_clients(syncer, {"robot-a": client_a, "robot-b": client_b})
    monkeypatch.setattr(
        syncer,
        "build_runtime_robots",
        lambda *args, **kwargs: [
            {
                "id": "robot-a",
                "appid": "app-a",
                "secret": "sec-a",
                "platform": "qq_official",
                "source": "v2",
                "scenes": {"c2c": [{"name": "help", "desc": "私聊"}]},
            },
            {
                "id": "robot-b",
                "appid": "app-b",
                "secret": "sec-b",
                "platform": "qq_official",
                "source": "v2",
                "scenes": {"group": [{"name": "sign", "desc": "群聊"}]},
            },
        ],
    )

    result = await syncer.sync_all()

    assert set(result) == {"robot-a", "robot-b"}
    assert [item["name"] for item in client_a.created[0][1]] == ["help"]
    assert client_a.created[0][0] == "c2c"
    assert [item["name"] for item in client_b.created[0][1]] == ["sign"]
    assert client_b.created[0][0] == "group"
