"""Сценарий совместимости: синастрия пары с детерминированным расчётом."""
from __future__ import annotations

from ._impl import _synastry_data, _synastry_fresh, interpret_compat  # noqa: F401

__all__ = ["interpret_compat"]
