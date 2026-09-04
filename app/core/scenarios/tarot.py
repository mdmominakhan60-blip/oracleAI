"""Сценарий Таро: трактовка КОНКРЕТНОГО расклада (карты выбрал код)."""
from __future__ import annotations

from ._impl import _reading_offline, interpret_reading  # noqa: F401

__all__ = ["interpret_reading"]
