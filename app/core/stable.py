"""Устойчивый сид для «случайного, но постоянного».

Встроенный hash() для строк рандомизируется при каждом запуске Python (PEP 456),
поэтому карта дня менялась после каждого перезапуска API, а балл совместимости
для одной и той же пары отличался у бота и у Mini App. crc32 даёт одно и то же
число всегда и везде.
"""
from __future__ import annotations

import zlib


def stable_seed(*parts: object) -> int:
    """Детерминированное целое из любых значений."""
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return zlib.crc32(raw)
