"""同步任务的后台执行与进度事件缓冲。

dashboard 的同步入口需要"异步进度反馈"，本模块负责：
- 同一时间只跑一个同步任务，重复触发直接返回忙，避免把 QQ API 打爆
- 事件写入内存缓冲并带上自增 seq，SSE 订阅者按 seq 订阅 / 回放
- 任务是 asyncio.create_task 起的后台任务，视图断开、刷新都不影响同步本身

缓冲只活在插件进程内存里，插件重载后清空，这是可接受的。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from astrbot.api import logger

from .i18n import LOG_TAG, t

# 任务函数：接收"emit 一个结构化事件"的回调，返回同步结果
SyncRunCallable = Callable[[Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[Any]]


class SyncRunner:
    """单飞的后台同步任务 + 可回放的进度事件流"""

    def __init__(self) -> None:
        # asyncio 原语在 Python 3.10+ 是惰性绑定事件循环的，可以在这里创建
        self._condition = asyncio.Condition()
        self._task: asyncio.Task[None] | None = None
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._running = False

    @property
    def running(self) -> bool:
        """当前是否有同步任务在跑"""
        return self._running

    @property
    def last_seq(self) -> int:
        """已产出的最大 seq，供订阅者续订"""
        return self._seq

    def start(self, run: SyncRunCallable) -> bool:
        """启动一次同步；已有任务在跑时返回 False

        事件缓冲在新一轮开始时清空，seq 保持单调递增，这样上一轮的订阅者
        在下一轮开始后依然能收到新事件（cursor 落后于新一轮的 seq）。
        """
        if self._running:
            return False
        self._events = []
        self._running = True
        self._task = asyncio.create_task(self._execute(run))
        return True

    async def _execute(self, run: SyncRunCallable) -> None:
        """执行任务并把异常收敛成 finish 事件，保证订阅者一定能结束"""
        try:
            result = await run(self._append)
        except Exception as exc:
            logger.error(
                f"{LOG_TAG} " + t("log.sync_task_failed", exc=exc),
                exc_info=True,
            )
            await self._append(
                {
                    "type": "finish",
                    "ok": False,
                    "reason": "exception",
                    "platforms": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "error": str(exc),
                    "result": {},
                }
            )
        else:
            # 正常情况由 PanelSyncer.sync_all 自己发 finish，这里只兜底
            if not self._events or self._events[-1].get("type") != "finish":
                await self._append(
                    {
                        "type": "finish",
                        "ok": True,
                        "reason": "sync",
                        "platforms": len(result) if isinstance(result, dict) else 0,
                        "succeeded": len(result) if isinstance(result, dict) else 0,
                        "failed": 0,
                        "result": result if isinstance(result, dict) else {},
                    }
                )
        finally:
            self._running = False
            await self._notify()

    async def _append(self, event: dict[str, Any]) -> None:
        """写入一条事件并唤醒所有订阅者"""
        async with self._condition:
            self._seq += 1
            payload = dict(event)
            payload["seq"] = self._seq
            self._events.append(payload)
            self._condition.notify_all()

    async def _notify(self) -> None:
        """唤醒所有订阅者，用于任务结束等没有新事件的状态变化"""
        async with self._condition:
            self._condition.notify_all()

    async def join(self) -> None:
        """等待当前任务结束（没有任务在跑时立即返回）"""
        task = self._task
        if task is not None and not task.done():
            await task

    async def cancel(self) -> None:
        """取消正在跑的同步任务（插件卸载时用，避免卸载后还继续写面板）"""
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def stream(self, since: int = 0) -> AsyncIterator[dict[str, Any]]:
        """从 seq > since 处开始产出事件，任务结束且事件发完就返回

        页面刷新 / 断线重连时用同一个 since 重新订阅即可续看本轮结果；
        任务已结束且缓冲还在时，会把本轮事件回放完再结束。
        """
        cursor = max(0, int(since))
        while True:
            pending: list[dict[str, Any]] = []
            finished = False
            async with self._condition:
                pending = [event for event in self._events if event["seq"] > cursor]
                if not pending and self._running:
                    await self._condition.wait()
                    continue
                if pending:
                    cursor = pending[-1]["seq"]
                    finished = pending[-1].get("type") == "finish"
                else:
                    # 没有待发事件且任务未在跑：没有后续了，结束流
                    finished = True
            for event in pending:
                yield event
            if finished:
                return


__all__ = ["SyncRunner", "SyncRunCallable"]
