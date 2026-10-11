"""core.panel_syncer.PanelSyncer 的单元测试 (注入 FakeQQClient / fake context)

重点覆盖 AGENTS.md 中 "任一场景拉取失败要中止" 的关键约定,
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
    """构造一个不带 remark 前缀的面板 record (他人创建)"""
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

    data_dir 用一次性临时目录: PanelSyncer.__init__ 会用它初始化
    PanelStateStore, 本文件不对其内容做断言。
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
# list_all_panels: 失败场景收集 (AGENTS.md 约定 2 的核心)
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
    """AGENTS.md 约定: 任一场景拉取失败要中止, 不许吞异常 (防重复建面板)"""
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
    """某场景 create 失败仅记录 error, 不影响其他场景"""
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


def test_build_clients_from_context() -> None:
    syncer = make_syncer(
        context_attrs={
            "platform_settings": [
                {"enable": True, "type": "qq_official", "id": "ctx1", "appid": "a", "secret": "s"},
            ]
        }
    )
    clients = syncer.build_clients()
    assert set(clients) == {"ctx1"}


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
    """clear 路径容忍部分场景失败 (删得掉多少算多少)"""
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
