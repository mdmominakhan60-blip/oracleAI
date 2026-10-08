"""Канон точности времени рождения (BUS-1232).

Единственный источник перечисления birth_time_precision: API-контракты, ботные
парсеры и потребители обязаны использовать эти значения, иначе surfaces пишут в
одну колонку несовместимые токены ('approx' vs 'approximate') и карта/профиль
противоречат друг другу (CWE-20 enum-дрейф).
"""
from __future__ import annotations

from typing import Literal

# Canonical storage/contract tokens.
BIRTH_TIME_PRECISIONS: tuple[str, ...] = ("exact", "approx", "unknown")
BirthTimePrecision = Literal["exact", "approx", "unknown"]

# Historically the bot wrote "approximate"; treat it as an alias so stale rows
# and any legacy caller normalise to the single canonical token.
_APPROX_ALIASES = frozenset({"approx", "approximate"})


def normalize_birth_time_precision(raw: str | None, *, time_known: bool | int | None = None) -> str:
    """Приводит любое входящее значение к канону exact|approx|unknown.

    None → выводим из time_known (сохраняем прежний fallback профиль/карты).
    Неизвестный токен → консервативно 'unknown' (скрывает время, fail-closed).
    """
    val = (raw or "").strip().lower()
    if not val:
        known = bool(time_known) if time_known is not None else False
        return "exact" if known else "unknown"
    if val in _APPROX_ALIASES:
        return "approx"
    if val in BIRTH_TIME_PRECISIONS:
        return val
    return "unknown"
