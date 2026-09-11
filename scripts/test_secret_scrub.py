#!/usr/bin/env python3
"""Маскирование секретов в выводе pytest и его лог-файлах (BUS-847/848).

Второй механизм утечки BUS-776: asyncpg 0.31.0 хранит параметры подключения
в namedtuple, чей repr() печатает password открытым текстом. Пароль всплывает
в traceback/assertion-выводе pytest даже при выключенном xtrace (BUS-374:
170 вхождений прод-PW в make-test.log).

Модуль делает три вещи:
1. Патчит repr asyncpg ConnectionParameters (password → ***).
2. Перехватывает logging.Logger.handle: маскирует значения секретов в msg
   и строковых args ДО раздачи хендлерам — фильтр на самом логгере
   не ловил бы propagated записи дочерних логгеров (в т.ч. caplog).
3. Предоставляет scrub() для последней линии обороны — отчёта pytest
   (longrepr и sections) перед записью в лог.

Needles собираются из env (TEST_DATABASE_URL, DATABASE_URL, BOT_TOKEN,
POSTGRES_PASSWORD) и .env проекта; значения короче 8 символов игнорируются,
чтобы не маскировать шаблонные значения .env.example. Самодостаточен:
pytest запускается и без установки (degrade до no-op), только без
маскирования — это не fail-closed задача, guard BUS-304 рядом.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

_MASK = "***"

# Ключи, значения которых — секреты или DSN с паролем.
_SECRET_KEYS = (
    "POSTGRES_PASSWORD",
    "ORACLEAI_MCP_ROLE_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
    "BOT_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "CUSTOM_LLM_API_KEY",
    "PADDLE_WEBHOOK_SECRET",
    "PADDLE_API_KEY",
    "DEV_KEY",
)
_DSN_KEYS = ("TEST_DATABASE_URL", "DATABASE_URL", "POSTGRES_ADMIN_DATABASE_URL")

_MIN_URL_SECRET_LEN = 8   # пароль в URL короче 8 символов не маскируем
_MIN_SECRET_LEN = 8       # шаблонные 'test:token'-короткие значения игнорируем


def collect_secret_values(env: dict[str, str] | None = None,
                          env_file: Path | None = None) -> list[str]:
    """Значения для маскирования: пароли из DSN + секретные значения.

    URL-значения дают и полный netloc (user:password@host), и сам пароль.
    Значение включается один раз; пустые и короткие отсекаются порогом.
    """
    env = dict(os.environ if env is None else env)
    if env_file is None:
        env_file = Path(__file__).resolve().parent.parent / ".env"
    for line in _read_env_file(env_file):
        key, _, value = line.partition("=")
        if key and value and key not in env:
            env[key] = value
    values: list[str] = []
    for key in _DSN_KEYS:
        url = env.get(key, "").strip()
        if not url:
            continue
        parts = urlsplit(url)
        password = parts.password or ""
        if len(password) >= _MIN_URL_SECRET_LEN:
            values.append(password)
        if parts.netloc and len(parts.netloc) >= _MIN_URL_SECRET_LEN \
                and parts.password:
            values.append(f"{parts.scheme}://{parts.netloc}")
    for key in _SECRET_KEYS:
        value = env.get(key, "").strip()
        if value and not value.startswith("$") and len(value) >= _MIN_SECRET_LEN:
            values.append(value)
    return sorted(set(values), key=len, reverse=True)


def _read_env_file(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln for ln in lines if ln and not ln.startswith("#") and "=" in ln]


def _mask_all(text: str, needles: list[str]) -> str:
    for needle in needles:
        if needle and needle in text:
            text = text.replace(needle, _MASK)
    return text


def make_scrubber() -> tuple[list[str], "SecretScrubber"]:
    """(needles, scrubber) — needles для юнит-тестов, scrubber для маскирования."""
    needles = collect_secret_values()
    return needles, SecretScrubber(needles)


class SecretScrubber:
    """Маскирует собранные значения в произвольном тексте (longest-first)."""

    def __init__(self, needles: list[str]):
        self._needles = sorted(set(needles), key=len, reverse=True)

    def __call__(self, text: str) -> str:
        return _mask_all(text, self._needles)

    def __bool__(self) -> bool:
        return bool(self._needles)


def _scrub_record(record: logging.LogRecord, scrubber: SecretScrubber) -> None:
    """Маскирует msg и строковые args записи на месте."""
    record.msg = scrubber(str(record.msg))
    if record.args:
        args = record.args
        if isinstance(args, dict):
            record.args = {k: scrubber(v) if isinstance(v, str) else v
                           for k, v in args.items()}
        else:
            record.args = tuple(
                scrubber(a) if isinstance(a, str) else a for a in args)


def install_repr_patch(scrubber: SecretScrubber) -> bool:
    """Патчит asyncpg ConnectionParameters: repr маскируется через scrubber.

    Идемпотентна по обёртке, но scrubber перепривязывается при каждом вызове —
    свежий needle-набор (например, из теста) применяется без повторной
    обёртки repr. Возвращает False, если asyncpg не установлен.
    """
    try:
        import asyncpg.connect_utils as cu
    except ImportError:
        return False
    params = getattr(cu, "_ConnectionParameters", None)
    if params is None or not issubclass(params, tuple):
        return False

    if not getattr(params, "_bus847_patched", False):
        original_repr = params.__repr__

        def masked_repr(self) -> str:
            return self._bus847_scrub(original_repr(self))

        params.__repr__ = masked_repr
        params._bus847_patched = True

    params._bus847_scrub = staticmethod(scrubber)
    # password-доступ через атрибут namedtuple остаётся честным —
    # коду нужна реальная пара для подключения; маскируем только текст.
    return True


def install_logging_filter(scrubber: SecretScrubber) -> bool:
    """Маскирует записи всех логгеров до раздачи хендлерам.

    Патчит logging.Logger.handle, а не ставит Filter на root: фильтры
    логгера применяются только к записям, залогированным напрямую в этот
    логгер — propagated записи дочерних логгеров (и caplog) их обходят.
    Идемпотентна; повторный вызов перепривязывает scrubber.
    """
    if getattr(logging.Logger, "_bus847_scrubbing_handle", False):
        logging.Logger._bus847_scrubber = scrubber
        return True
    original_handle = logging.Logger.handle

    def scrubbing_handle(self, record):
        scrub = getattr(logging.Logger, "_bus847_scrubber", None)
        if scrub is not None:
            try:
                _scrub_record(record, scrub)
            except Exception:  # noqa: BLE001 — маскирование не роняет логгер
                pass
        return original_handle(self, record)

    logging.Logger.handle = scrubbing_handle
    logging.Logger._bus847_scrubbing_handle = True
    logging.Logger._bus847_scrubber = scrubber
    return True


def install(scrubber: SecretScrubber | None = None) -> bool:
    """Полная установка: repr-патч + logging-перехват. Идемпотентна."""
    if scrubber is None:
        _, scrubber = make_scrubber()
    repr_ok = install_repr_patch(scrubber)
    install_logging_filter(scrubber)
    return repr_ok
