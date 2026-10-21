"""插件日志的内存缓冲与实时订阅。

dashboard 的日志页需要看到插件启动后的最近日志，并在页面打开时实时追加。
本模块在 AstrBot 共享 logger 上安装一个带前缀过滤的 Handler，避免把宿主和其他
插件的日志一起暴露给面板。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from .i18n import LOG_TAG, t

DEFAULT_LOG_BUFFER_CAPACITY = 1000
DEFAULT_LOG_HEARTBEAT_SECONDS = 15.0
MAX_LOG_ENTRY_CHARS = 32 * 1024
LOG_HANDLER_NAME = "qq-command-panel-dashboard"


@dataclass(frozen=True)
class LogEntry:
    """一条供 dashboard 展示的插件日志。"""

    seq: int
    timestamp: str
    level: str
    message: str
    traceback: str = ""

    def as_event(self) -> dict[str, Any]:
        """转换为 SSE JSON 载荷。"""
        event: dict[str, Any] = {
            "type": "log",
            "seq": self.seq,
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }
        if self.traceback:
            event["traceback"] = self.traceback
        return event


class _LogBufferHandler(logging.Handler):
    """把宿主 logger 记录转交给 LogBuffer。"""

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self.name = LOG_HANDLER_NAME
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.add_record(record)
        except Exception:  # pragma: no cover - logging 自身不应影响插件业务
            self.handleError(record)


class LogBuffer:
    """线程安全的插件日志环形缓冲与异步订阅源。"""

    def __init__(
        self,
        capacity: int = DEFAULT_LOG_BUFFER_CAPACITY,
        heartbeat_seconds: float = DEFAULT_LOG_HEARTBEAT_SECONDS,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = Lock()
        self._waiters: dict[asyncio.Event, asyncio.AbstractEventLoop] = {}
        self._seq = 0
        self._closed = False
        self._logger: logging.Logger | None = None
        self._handler: _LogBufferHandler | None = None
        self._heartbeat_seconds = heartbeat_seconds

    @property
    def last_seq(self) -> int:
        """已采集的最大序号。"""
        with self._lock:
            return self._seq

    def install(self, host_logger: logging.Logger) -> None:
        """在宿主 logger 上安装日志收集 Handler。"""
        self.close()
        with self._lock:
            self._closed = False

        for handler in list(host_logger.handlers):
            if getattr(handler, "name", None) == LOG_HANDLER_NAME:
                host_logger.removeHandler(handler)
                handler.close()

        handler = _LogBufferHandler(self)
        host_logger.addHandler(handler)
        self._logger = host_logger
        self._handler = handler

    def close(self) -> None:
        """停止收集并唤醒所有等待中的订阅者。"""
        logger = self._logger
        handler = self._handler
        self._logger = None
        self._handler = None
        if logger is not None and handler is not None:
            logger.removeHandler(handler)
            handler.close()

        with self._lock:
            self._closed = True
            waiters = list(self._waiters.items())
        self._wake(waiters)

    def add_record(self, record: logging.LogRecord) -> None:
        """把一条标准日志记录写入缓冲；非本插件记录会被忽略。"""
        entry = self._entry_from_record(record)
        if entry is None:
            return

        with self._lock:
            self._seq += 1
            entry = LogEntry(
                seq=self._seq,
                timestamp=entry.timestamp,
                level=entry.level,
                message=entry.message,
                traceback=entry.traceback,
            )
            self._entries.append(entry)
            waiters = list(self._waiters.items())
        self._wake(waiters)

    async def follow(
        self,
        since: int = 0,
        *,
        heartbeat_seconds: float | None = None,
    ) -> AsyncIterator[LogEntry | None]:
        """从 ``seq > since`` 开始产出日志；空闲时以 ``None`` 表示心跳。"""
        cursor = max(0, int(since))
        interval = self._heartbeat_seconds if heartbeat_seconds is None else heartbeat_seconds
        if interval <= 0:
            raise ValueError("heartbeat_seconds must be positive")

        loop = asyncio.get_running_loop()
        while True:
            event = asyncio.Event()
            with self._lock:
                pending = [entry for entry in self._entries if entry.seq > cursor]
                closed = self._closed
                if not pending and not closed:
                    self._waiters[event] = loop

            if pending:
                cursor = pending[-1].seq
                for entry in pending:
                    yield entry
                continue
            if closed:
                return

            try:
                await asyncio.wait_for(event.wait(), timeout=interval)
            except asyncio.TimeoutError:  # noqa: UP041 - Python 3.10 alias
                yield None
            finally:
                with self._lock:
                    self._waiters.pop(event, None)

    @staticmethod
    def _entry_from_record(record: logging.LogRecord) -> LogEntry | None:
        raw_message = record.getMessage()
        if not raw_message.startswith(LOG_TAG):
            return None

        message = raw_message[len(LOG_TAG) :].lstrip()
        if not message:
            message = LOG_TAG
        traceback = _format_record_details(record)
        message, traceback = _truncate_entry(message, traceback)
        return LogEntry(
            seq=0,
            timestamp=datetime.fromtimestamp(record.created, timezone.utc)  # noqa: UP017
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            level=_normalize_level(record),
            message=message,
            traceback=traceback,
        )

    @staticmethod
    def _wake(waiters: list[tuple[asyncio.Event, asyncio.AbstractEventLoop]]) -> None:
        for event, loop in waiters:
            if loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass


def _normalize_level(record: logging.LogRecord) -> str:
    if record.levelno >= logging.CRITICAL:
        return "critical"
    if record.levelno >= logging.ERROR:
        return "error"
    if record.levelno >= logging.WARNING:
        return "warning"
    if record.levelno >= logging.INFO:
        return "info"
    return "debug"


def _format_record_details(record: logging.LogRecord) -> str:
    formatter = logging.Formatter()
    parts: list[str] = []
    if record.exc_info:
        parts.append(formatter.formatException(record.exc_info))
    if record.stack_info:
        parts.append(formatter.formatStack(record.stack_info))
    return "\n".join(part for part in parts if part).rstrip()


def _truncate_entry(message: str, traceback: str) -> tuple[str, str]:
    marker = f"\n{t('log.stream_entry_truncated')}"
    budget = MAX_LOG_ENTRY_CHARS - len(marker)
    if len(message) + len(traceback) <= budget:
        return message, traceback

    message = message[:budget]
    remaining = budget - len(message)
    traceback = traceback[:remaining]
    if traceback:
        traceback = f"{traceback}{marker}"
    else:
        message = f"{message}{marker}"
    return message, traceback


__all__ = [
    "DEFAULT_LOG_BUFFER_CAPACITY",
    "DEFAULT_LOG_HEARTBEAT_SECONDS",
    "LOG_HANDLER_NAME",
    "MAX_LOG_ENTRY_CHARS",
    "LogBuffer",
    "LogEntry",
]
