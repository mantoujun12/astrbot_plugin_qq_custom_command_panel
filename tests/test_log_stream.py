"""core.log_stream 的日志采集、回放与实时订阅测试。"""

from __future__ import annotations

import asyncio
import logging

import pytest

from core.i18n import LOG_TAG, t
from core.log_stream import MAX_LOG_ENTRY_CHARS, LogBuffer


def make_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"test-log-stream-{name}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


async def next_entry(buffer: LogBuffer, since: int = 0):
    stream = buffer.follow(since, heartbeat_seconds=10)
    try:
        return await asyncio.wait_for(anext(stream), timeout=1)
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_install_filters_prefix_and_formats_record() -> None:
    buffer = LogBuffer()
    logger = make_logger("format")
    buffer.install(logger)
    try:
        logger.info("not from this plugin")
        logger.info("%s booted", f"{LOG_TAG} plugin")
    finally:
        buffer.close()

    entry = await next_entry(buffer)

    assert entry is not None
    assert entry.seq == 1
    assert entry.level == "info"
    assert entry.message == "plugin booted"
    assert entry.timestamp.endswith("Z")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "level"),
    [
        ("debug", "debug"),
        ("info", "info"),
        ("warning", "warning"),
        ("error", "error"),
        ("critical", "critical"),
    ],
)
async def test_levels_are_normalized(method: str, level: str) -> None:
    buffer = LogBuffer()
    logger = make_logger(f"level-{level}")
    buffer.install(logger)
    try:
        getattr(logger, method)(f"{LOG_TAG} level message")
    finally:
        buffer.close()

    entry = await next_entry(buffer)

    assert entry is not None
    assert entry.level == level


@pytest.mark.asyncio
async def test_exception_traceback_is_captured() -> None:
    buffer = LogBuffer()
    logger = make_logger("traceback")
    buffer.install(logger)
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception(f"{LOG_TAG} failed")
    finally:
        buffer.close()

    entry = await next_entry(buffer)

    assert entry is not None
    assert "Traceback" in entry.traceback
    assert "RuntimeError: boom" in entry.traceback


@pytest.mark.asyncio
async def test_buffer_keeps_latest_entries_with_monotonic_seq() -> None:
    buffer = LogBuffer(capacity=2)
    logger = make_logger("capacity")
    buffer.install(logger)
    try:
        logger.info(f"{LOG_TAG} one")
        logger.info(f"{LOG_TAG} two")
        logger.info(f"{LOG_TAG} three")
    finally:
        buffer.close()

    entry = await next_entry(buffer)

    assert buffer.last_seq == 3
    assert entry is not None
    assert entry.seq == 2
    assert entry.message == "two"


@pytest.mark.asyncio
async def test_follow_since_replays_only_newer_entries() -> None:
    buffer = LogBuffer(capacity=3)
    logger = make_logger("since")
    buffer.install(logger)
    try:
        logger.info(f"{LOG_TAG} one")
        logger.info(f"{LOG_TAG} two")
        logger.info(f"{LOG_TAG} three")
    finally:
        buffer.close()

    entry = await next_entry(buffer, since=2)

    assert entry is not None
    assert entry.seq == 3
    assert entry.message == "three"


@pytest.mark.asyncio
async def test_follow_receives_live_entries_and_supports_multiple_subscribers() -> None:
    buffer = LogBuffer()
    logger = make_logger("live")
    buffer.install(logger)
    first = buffer.follow(0, heartbeat_seconds=10)
    second = buffer.follow(0, heartbeat_seconds=10)
    first_next = asyncio.create_task(anext(first))
    second_next = asyncio.create_task(anext(second))
    await asyncio.sleep(0)

    try:
        logger.info(f"{LOG_TAG} live")
        one, two = await asyncio.wait_for(asyncio.gather(first_next, second_next), timeout=1)
    finally:
        await first.aclose()
        await second.aclose()
        buffer.close()

    assert one is not None and two is not None
    assert one.seq == two.seq == 1
    assert one.message == two.message == "live"


@pytest.mark.asyncio
async def test_follow_is_woken_by_logs_from_worker_threads() -> None:
    buffer = LogBuffer()
    logger = make_logger("thread")
    buffer.install(logger)
    stream = buffer.follow(0, heartbeat_seconds=10)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)

    try:
        await asyncio.to_thread(logger.info, f"{LOG_TAG} from thread")
        entry = await asyncio.wait_for(pending, timeout=1)
    finally:
        await stream.aclose()
        buffer.close()

    assert entry is not None
    assert entry.message == "from thread"


@pytest.mark.asyncio
async def test_close_removes_handler_and_ends_waiting_stream() -> None:
    buffer = LogBuffer()
    logger = make_logger("close")
    buffer.install(logger)
    assert len(logger.handlers) == 1

    stream = buffer.follow(0, heartbeat_seconds=10)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    buffer.close()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, timeout=1)
    await stream.aclose()

    assert logger.handlers == []


@pytest.mark.asyncio
async def test_oversized_entry_is_truncated() -> None:
    buffer = LogBuffer()
    logger = make_logger("truncate")
    buffer.install(logger)
    try:
        logger.info(f"{LOG_TAG} {'x' * (MAX_LOG_ENTRY_CHARS + 100)}")
    finally:
        buffer.close()

    entry = await next_entry(buffer)

    assert entry is not None
    assert len(entry.message) == MAX_LOG_ENTRY_CHARS
    assert entry.message.endswith(t("log.stream_entry_truncated"))


@pytest.mark.asyncio
async def test_follow_emits_heartbeat_when_idle() -> None:
    buffer = LogBuffer(heartbeat_seconds=0.01)
    stream = buffer.follow(0)
    try:
        assert await asyncio.wait_for(anext(stream), timeout=1) is None
    finally:
        await stream.aclose()
