"""Bounded operational log stream for the admin monitoring surface.

The stream is intentionally process-local and bounded. It is a live diagnostic
window, not a replacement for the canonical JSONL stdout/file sink. Every entry
is formatted by the existing redacting formatter before it reaches memory or a
browser subscriber.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator
from threading import Lock
from typing import Any


class LogStream:
    def __init__(self, max_entries: int = 500) -> None:
        self.max_entries = max_entries
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = Lock()
        self._sequence = 0

    def publish(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._sequence += 1
            record = {"id": self._sequence, **entry}
            self._entries.append(record)
            subscribers = tuple(self._subscribers)
        for loop, queue in subscribers:
            if loop.is_closed():
                self._subscribers.discard((loop, queue))
                continue
            loop.call_soon_threadsafe(self._offer, queue, record)

    @staticmethod
    def _offer(queue: asyncio.Queue, record: dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(record)
        except asyncio.QueueFull:
            pass

    def snapshot(
        self,
        *,
        limit: int = 200,
        level: str | None = None,
        logger_name: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        level = level.upper() if level else None
        query = query.lower().strip() if query else None
        with self._lock:
            entries = list(self._entries)
        result = []
        for entry in reversed(entries):
            if level and entry.get("level") != level:
                continue
            if logger_name and entry.get("logger") != logger_name:
                continue
            if query and query not in json.dumps(entry, ensure_ascii=False).lower():
                continue
            result.append(entry)
            if len(result) >= max(1, min(limit, self.max_entries)):
                break
        return result

    async def stream(
        self,
        *,
        level: str | None = None,
        logger_name: str | None = None,
        query: str | None = None,
        heartbeat_seconds: float = 15.0,
    ) -> AsyncIterator[dict[str, Any] | None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        subscriber = (loop, queue)
        with self._lock:
            self._subscribers.add(subscriber)
        normalized_level = level.upper() if level else None
        normalized_query = query.lower().strip() if query else None
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                except asyncio.TimeoutError:
                    yield None
                    continue
                if normalized_level and entry.get("level") != normalized_level:
                    continue
                if logger_name and entry.get("logger") != logger_name:
                    continue
                if normalized_query and normalized_query not in json.dumps(entry, ensure_ascii=False).lower():
                    continue
                yield entry
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)


class LogStreamHandler(logging.Handler):
    """Publishes already-redacted LogRecord payloads to the process-local stream."""

    def __init__(self, formatter: logging.Formatter, stream: LogStream | None = None) -> None:
        super().__init__(level=logging.NOTSET)
        self._formatter = formatter
        self._stream = stream or log_stream

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(self._formatter.format(record))
            self._stream.publish(payload)
        except Exception:
            self.handleError(record)


log_stream = LogStream()
