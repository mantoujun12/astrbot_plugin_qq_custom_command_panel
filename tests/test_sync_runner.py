"""core.sync_runner 的单元测试

同步任务是 dashboard 同步入口的核心：单飞、事件缓冲、断线续看、异常兜底。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core.sync_runner import SyncRunner


async def collect(runner: SyncRunner, since: int = 0) -> list[dict[str, Any]]:
    """把进度流收成列表，便于断言"""
    return [event async for event in runner.stream(since)]


@pytest.mark.asyncio
async def test_start_is_single_flight() -> None:
    runner = SyncRunner()
    release = asyncio.Event()

    async def slow(emit: Any) -> dict[str, Any]:
        await release.wait()
        return {}

    assert runner.start(slow) is True
    assert runner.running is True
    # 已有任务在跑时不再排队，直接拒绝
    assert runner.start(slow) is False

    release.set()
    await runner.join()
    assert runner.running is False


@pytest.mark.asyncio
async def test_stream_yields_events_in_order_and_ends() -> None:
    runner = SyncRunner()

    async def run(emit: Any) -> dict[str, Any]:
        await emit({"type": "start", "platforms": 1})
        await emit({"type": "platform", "pf_id": "pf1", "index": 1, "total": 1})
        await emit({"type": "finish", "ok": True})
        return {"pf1": {"c2c": "panel_1"}}

    assert runner.start(run) is True
    events = await collect(runner)

    assert [event["type"] for event in events] == ["start", "platform", "finish"]
    # seq 从 1 开始单调递增
    assert [event["seq"] for event in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_stream_since_skips_delivered_events() -> None:
    runner = SyncRunner()

    async def run(emit: Any) -> dict[str, Any]:
        await emit({"type": "start"})
        await emit({"type": "finish", "ok": True})
        return {}

    runner.start(run)
    events = await collect(runner)

    # 全部已读：再次订阅不会再拿到任何事件，并且立即结束
    assert await collect(runner, events[-1]["seq"]) == []


@pytest.mark.asyncio
async def test_stream_emits_idle_finish_when_nothing_ran() -> None:
    """插件重启后缓冲为空，订阅者也要收到终止事件，不能永远等下去"""
    runner = SyncRunner()
    events = await collect(runner)

    assert [event["type"] for event in events] == ["finish"]
    assert events[0]["reason"] == "idle"
    assert events[0]["ok"] is False
    assert events[0]["seq"] == 0


@pytest.mark.asyncio
async def test_stream_emits_idle_finish_for_stale_cursor_after_restart() -> None:
    """前端还记着重启前的 lastSeq 时，续订同样要收到 idle 终止事件"""
    runner = SyncRunner()
    events = await collect(runner, since=42)

    assert [event["type"] for event in events] == ["finish"]
    assert events[0]["reason"] == "idle"


@pytest.mark.asyncio
async def test_stream_emits_idle_finish_when_cursor_is_past_completed_buffer() -> None:
    """新进程已有完整一轮缓冲时，超前的旧游标也不能静默返回"""

    async def run(emit: Any) -> dict[str, Any]:
        await emit({"type": "start"})
        await emit({"type": "finish", "ok": True})
        return {}

    runner = SyncRunner()
    runner.start(run)
    await runner.join()

    events = await collect(runner, since=runner.last_seq + 40)

    assert [event["type"] for event in events] == ["finish"]
    assert events[0]["reason"] == "idle"


@pytest.mark.asyncio
async def test_stream_waits_for_running_task() -> None:
    """运行中订阅要先等事件，任务结束后流自动收尾"""
    runner = SyncRunner()
    release = asyncio.Event()

    async def run(emit: Any) -> dict[str, Any]:
        await emit({"type": "start"})
        await release.wait()
        await emit({"type": "finish", "ok": True})
        return {}

    runner.start(run)
    pending = asyncio.create_task(collect(runner))
    await asyncio.sleep(0)
    assert not pending.done()  # 还在等 finish

    release.set()
    events = await pending
    assert [event["type"] for event in events] == ["start", "finish"]


@pytest.mark.asyncio
async def test_exception_becomes_finish_event() -> None:
    runner = SyncRunner()

    async def boom(_emit: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    runner.start(boom)
    events = await collect(runner)

    assert [event["type"] for event in events] == ["finish"]
    assert events[0]["ok"] is False
    assert "boom" in events[0]["error"]
    assert runner.running is False


@pytest.mark.asyncio
async def test_finish_appended_when_run_forgets_it() -> None:
    """同步函数漏发 finish 时由 runner 兜底，保证订阅者能结束"""
    runner = SyncRunner()

    async def run(emit: Any) -> dict[str, Any]:
        await emit({"type": "start", "platforms": 1})
        return {"pf1": {"c2c": "panel_1"}}

    runner.start(run)
    events = await collect(runner)

    assert events[-1]["type"] == "finish"
    assert events[-1]["ok"] is True
    assert events[-1]["platforms"] == 1


@pytest.mark.asyncio
async def test_new_run_clears_buffer_but_keeps_seq_monotonic() -> None:
    runner = SyncRunner()

    async def run(emit: Any) -> dict[str, Any]:
        await emit({"type": "finish", "ok": True})
        return {}

    runner.start(run)
    first = await collect(runner)
    first_last_seq = first[-1]["seq"]

    runner.start(run)
    second = await collect(runner)

    assert len(second) == 1  # 缓冲已清空，只剩本轮事件
    assert second[-1]["seq"] > first_last_seq


@pytest.mark.asyncio
async def test_cancel_stops_task_and_notifies_subscribers() -> None:
    runner = SyncRunner()
    release = asyncio.Event()

    async def slow(emit: Any) -> dict[str, Any]:
        await emit({"type": "start"})
        await release.wait()
        return {}

    runner.start(slow)
    pending = asyncio.create_task(collect(runner))
    await asyncio.sleep(0)

    await runner.cancel()

    # 取消后 _running 归位，订阅者不会一直挂着；没有真实 finish 时补发 idle 终止事件
    assert runner.running is False
    events = await pending
    assert [event["type"] for event in events] == ["start", "finish"]
    assert events[-1]["reason"] == "idle"
