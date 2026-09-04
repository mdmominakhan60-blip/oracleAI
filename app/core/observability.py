"""Безопасная наблюдаемость OracleAI.

Логи считаются операционными данными: в них не должны попадать сообщения,
дневник, память, токены, initData или необезличенные Telegram ID. Модуль не
хранит пользовательский контекст и помогает наблюдать продуктовую динамику.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .log_stream import LogStreamHandler, log_stream

_REQUEST_ID: ContextVar[str] = ContextVar("oracle_request_id", default="-")
_CONFIGURED = False

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_ -]?key|token|secret|password|signature|initData)\s*[:=]\s*[^\s,;]+"
)
# Токен бота Telegram: <bot_id>:<35+ chars>. Падает в логи как есть (URL,
# исключения httpx) и без маскировки даёт полный контроль над ботом.
_BOT_TOKEN_RE = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")
_TG_ID_RE = re.compile(r"(?i)\b(?:tg[_ -]?id|telegram[_ -]?id)\s*[:=]\s*-?\d+")
_TELEGRAM_ID_RE = re.compile(r"(?<!\w)\d{5,20}(?!\w)")


def new_request_id() -> str:
    return secrets.token_hex(8)


def request_id() -> str:
    return _REQUEST_ID.get()


def set_request_id(value: str):
    return _REQUEST_ID.set(value or "-")


def reset_request_id(token) -> None:
    _REQUEST_ID.reset(token)


def redact_text(value: Any) -> str:
    """Удаляет очевидные секреты, email и идентификаторы из сообщения лога."""
    text = str(value)
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    text = _BOT_TOKEN_RE.sub("<redacted-bot-token>", text)
    text = _SECRET_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    text = _TG_ID_RE.sub(lambda m: m.group(0).split("=", 1)[0].split(":", 1)[0] + "=<redacted-id>", text)
    text = _EMAIL_RE.sub("<redacted-email>", text)
    return _TELEGRAM_ID_RE.sub("<redacted-id>", text)


class JsonRedactingFormatter(logging.Formatter):
    """Компактный JSONL formatter для stdout и опционального файла."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "request_id": request_id(),
            "release_id": os.getenv("RELEASE_ID", "local"),
            "environment": os.getenv("APP_ENV", "dev"),
        }
        for key in (
            "event", "method", "path", "status_code", "latency_ms", "provider",
            "purpose", "surface", "operation", "threshold", "count", "rate",
            "duration_ms", "latency_ms", "mode", "precision", "time_known",
            "cache_hit", "live", "planet_count", "house_count", "aspect_count",
            "section_count", "status", "error_type", "user_state",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(*, level: str | None = None, log_file: str | None = None) -> None:
    """Настраивает один JSONL stream и, при необходимости, file handler.

    Повторный вызов безопасен для импорта API и bot в одном процессе тестов.
    """
    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO))
    formatter = JsonRedactingFormatter()
    if not root.handlers:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        root.addHandler(stream)
    else:
        for handler in root.handlers:
            if not isinstance(handler, logging.NullHandler):
                handler.setFormatter(formatter)
    target = log_file or os.getenv("LOG_FILE", "")
    if target and not any(getattr(handler, "baseFilename", None) == str(Path(target).resolve())
                          for handler in root.handlers):
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    if not any(isinstance(handler, LogStreamHandler) for handler in root.handlers):
        stream_handler = LogStreamHandler(formatter, log_stream)
        root.addHandler(stream_handler)
    _CONFIGURED = True


def log_event(logger: logging.Logger, level: int, event: str, message: str, **fields: Any) -> None:
    """Записывает whitelisted operational fields без личного контекста."""
    logger.log(level, message, extra={"event": event, **fields})
