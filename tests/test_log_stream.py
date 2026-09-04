import asyncio
import logging

import pytest

from app.core.log_stream import LogStream, LogStreamHandler
from app.core.observability import JsonRedactingFormatter


def test_log_handler_publishes_redacted_json_payload():
    stream = LogStream(max_entries=4)
    handler = LogStreamHandler(JsonRedactingFormatter(), stream)
    record = logging.LogRecord(
        name="oracle.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="request failed token=super-secret tg_id=123456789 email=a@example.com",
        args=(),
        exc_info=None,
    )
    record.event = "test_failure"
    handler.emit(record)

    [entry] = stream.snapshot()
    assert entry["id"] == 1
    assert entry["level"] == "ERROR"
    assert entry["event"] == "test_failure"
    assert "super-secret" not in str(entry)
    assert "123456789" not in str(entry)
    assert "a@example.com" not in str(entry)
    assert "<redacted" in entry["message"]


def test_bot_token_is_redacted_in_log_payload():
    from app.core.observability import redact_text
    text = redact_text("webhook failed for 1234567890:AAEds_pXq9R2LmNoPqRsTuVwXyZ0123456789abc")
    assert "AAEds" not in text
    assert "<redacted-bot-token>" in text


def test_log_stream_is_bounded_and_filterable():
    stream = LogStream(max_entries=2)
    stream.publish({"level": "INFO", "logger": "oracle.api", "message": "ready"})
    stream.publish({"level": "ERROR", "logger": "oracle.db", "message": "locked"})
    stream.publish({"level": "WARNING", "logger": "oracle.api", "message": "slow"})

    assert [item["message"] for item in stream.snapshot()] == ["slow", "locked"]
    assert [item["message"] for item in stream.snapshot(level="ERROR")] == ["locked"]
    assert [item["message"] for item in stream.snapshot(logger_name="oracle.api")] == ["slow"]
    assert [item["message"] for item in stream.snapshot(query="READY")] == []


@pytest.mark.asyncio
async def test_log_stream_delivers_to_async_subscriber():
    stream = LogStream()

    async def receive_one():
        async for item in stream.stream(heartbeat_seconds=1):
            if item is not None:
                return item
        return None

    task = asyncio.create_task(receive_one())
    await asyncio.sleep(0)
    stream.publish({"level": "INFO", "logger": "oracle.test", "message": "live"})
    entry = await asyncio.wait_for(task, timeout=1)
    assert entry["message"] == "live"
