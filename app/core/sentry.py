"""Sentry (G31): опциональный мониторинг падений бота и API.

Пустой `SENTRY_DSN` — модуль молчит, продукт работает как раньше. С DSN оба
процесса отправляют необработанные исключения и долгие ответы. `capture_exception`
используется там, где исключение гасится ради пользовательского пути (например,
500-обёртка middleware), но не должно теряться для диагностики.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

from .observability import redact_text

log = logging.getLogger("oracle.sentry")

_initialized = False


def init() -> None:
    global _initialized
    if _initialized:
        return
    from ..config import settings
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN задан, но sentry-sdk не установлен")
        return
    def before_send(event, hint):
        # Sentry PII flag is not enough for exception messages composed by
        # third-party clients; scrub strings and remove query parameters.
        if isinstance(event.get("message"), dict):
            message = event["message"].get("message")
            if message:
                event["message"]["message"] = redact_text(message)
        for exception in (event.get("exception", {}).get("values", []) or []):
            if exception.get("value"):
                exception["value"] = redact_text(exception["value"])
        request = event.get("request") or {}
        if request.get("url"):
            parsed = urlsplit(request["url"])
            request["url"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        event["request"] = request
        return event

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.05,        # дашборд перфоманса без лишнего расхода
        send_default_pii=False,         # в события не тащим личные данные клиенток
        environment=settings.app_env,
        release=settings.release_id,
        before_send=before_send,
    )
    _initialized = True
    log.info("Sentry подключён")


def capture_exception(exc: BaseException) -> None:
    if not _initialized:
        return
    import sentry_sdk
    sentry_sdk.capture_exception(exc)
