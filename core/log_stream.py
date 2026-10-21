"""插件日志的内存缓冲与实时订阅。

dashboard 的日志页需要看到插件启动后的最近日志，并在页面打开时实时追加。
本模块在 AstrBot 共享 logger 上安装按插件源码过滤的日志收集器，避免把宿主和其他
插件的日志一起暴露给面板。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .i18n import LOG_TAG, t

DEFAULT_LOG_BUFFER_CAPACITY = 1000
DEFAULT_LOG_HEARTBEAT_SECONDS = 15.0
DEFAULT_LOG_MAX_SUBSCRIBERS = 32
MAX_LOG_ENTRY_CHARS = 32 * 1024
LOG_HANDLER_NAME = "qq-command-panel-dashboard"
_PLUGIN_SOURCE_ROOT = Path(__file__).resolve().parent.parent


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


class LogSubscriberLimitError(RuntimeError):
    """日志流并发订阅数已达到上限。"""


class LogBuffer:
    """线程安全的插件日志环形缓冲与异步订阅源。"""

    def __init__(
        self,
        capacity: int = DEFAULT_LOG_BUFFER_CAPACITY,
        heartbeat_seconds: float = DEFAULT_LOG_HEARTBEAT_SECONDS,
        max_subscribers: int = DEFAULT_LOG_MAX_SUBSCRIBERS,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if max_subscribers < 1:
            raise ValueError("max_subscribers must be positive")
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = Lock()
        self._waiters: dict[asyncio.Event, asyncio.AbstractEventLoop] = {}
        self._max_subscribers = max_subscribers
        self._active_subscribers = 0
        self._seq = 0
        self._stream_id = uuid4().hex
        self._closed = False
        self._remove_handler: Any | None = None
        self._handler: _LogBufferHandler | None = None
        self._sink_id: int | None = None
        self._remove_sink: Any | None = None
        self._heartbeat_seconds = heartbeat_seconds

    @property
    def stream_id(self) -> str:
        """当前缓冲区实例的标识，用于识别插件重新加载。"""
        return self._stream_id

    @property
    def last_seq(self) -> int:
        """已采集的最大序号。"""
        with self._lock:
            return self._seq

    def install(self, host_logger: Any) -> None:
        """在标准库或 Loguru 宿主 logger 上安装日志收集 sink。"""
        self.close()
        with self._lock:
            self._closed = False

        try:
            # AstrBot 4.29+ 的 `astrbot.api.logger` 是转发代理，不是 logging.Logger
            # 实例也不会暴露 Loguru 的 add/remove，但会把标准 logging 接口（如
            # addHandler / removeHandler）转发给真正的 logger，因此按能力检测。
            add_handler = getattr(host_logger, "addHandler", None)
            remove_handler = getattr(host_logger, "removeHandler", None)
            if callable(add_handler) and callable(remove_handler):
                handler = _LogBufferHandler(self)
                add_handler(handler)
                # 代理的属性解析依赖调用方所在模块，这里捕获绑定方法，
                # 保证 close() 从任意模块调用都能移除同一个 handler。
                self._remove_handler = remove_handler
                self._handler = handler
                return

            add_sink = getattr(host_logger, "add", None)
            remove_sink = getattr(host_logger, "remove", None)
            if not callable(add_sink) or not callable(remove_sink):
                raise TypeError(
                    "host_logger must provide addHandler/removeHandler or Loguru add/remove"
                )
            sink_id = add_sink(
                self._add_loguru_message,
                level="DEBUG",
                filter=self._is_loguru_source,
            )
            self._sink_id = sink_id
            self._remove_sink = remove_sink
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """停止收集并唤醒所有等待中的订阅者。"""
        handler = self._handler
        remove_handler = self._remove_handler
        sink_id = self._sink_id
        remove_sink = self._remove_sink
        self._handler = None
        self._remove_handler = None
        self._sink_id = None
        self._remove_sink = None
        try:
            if handler is not None and remove_handler is not None:
                remove_handler(handler)
                handler.close()
            elif sink_id is not None and remove_sink is not None:
                remove_sink(sink_id)
        finally:
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
            if self._closed:
                return
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

        with self._lock:
            if self._active_subscribers >= self._max_subscribers:
                raise LogSubscriberLimitError("maximum log stream subscribers reached")
            self._active_subscribers += 1

        loop = asyncio.get_running_loop()
        try:
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
        finally:
            with self._lock:
                self._active_subscribers -= 1

    @staticmethod
    def _entry_from_record(record: logging.LogRecord) -> LogEntry | None:
        if not _is_plugin_source(record.pathname):
            return None
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

    def _is_loguru_source(self, record: Mapping[str, Any]) -> bool:
        file_info = record.get("file")
        path = (
            file_info.get("path")
            if isinstance(file_info, Mapping)
            else getattr(file_info, "path", None)
        )
        return isinstance(path, str) and _is_plugin_source(path)

    def _add_loguru_message(self, message: Any) -> None:
        record = getattr(message, "record", None)
        if not isinstance(record, Mapping) or not self._is_loguru_source(record):
            return

        level = record["level"]
        file_info = record["file"]
        path = file_info.get("path") if isinstance(file_info, Mapping) else file_info.path
        exception = record.get("exception")
        exc_info = None
        if exception is not None and exception.type is not None:
            exc_info = (exception.type, exception.value, exception.traceback)
        log_record = logging.LogRecord(
            name=record.get("name") or "",
            level=level.no,
            pathname=path,
            lineno=record["line"],
            msg=record["message"],
            args=(),
            exc_info=exc_info,
            func=record.get("function"),
        )
        log_record.created = record["time"].timestamp()
        self.add_record(log_record)

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


def _is_plugin_source(path: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(_PLUGIN_SOURCE_ROOT)
    except (OSError, RuntimeError):
        return False


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
    "DEFAULT_LOG_MAX_SUBSCRIBERS",
    "LOG_HANDLER_NAME",
    "LogSubscriberLimitError",
    "MAX_LOG_ENTRY_CHARS",
    "LogBuffer",
    "LogEntry",
]
