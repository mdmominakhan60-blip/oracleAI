"""Совместимость: проверка initData переехала в `security.py` (там же срок жизни)."""
from .security import parse_init_data, validate_init_data  # noqa: F401

__all__ = ["validate_init_data", "parse_init_data"]
