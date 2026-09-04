"""Shared eligibility rules for sensitive product operations.

The HTTP layer may reject early for a better response, but every business entry
point must call this module again. In particular, a queued Celery job can outlive
the user's age confirmation or account status at enqueue time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class EligibilityDenied(Exception):
    """Non-retryable denial that must never reach an LLM or billing operation."""

    code: str
    reason: str

    def __str__(self) -> str:
        return self.reason


_ACTIVE_STATUS = "active"


def _value(user: Mapping[str, object], key: str, default=None):
    """Read both dict-like mappings and PostgresRow-compatible objects."""
    getter = getattr(user, "get", None)
    if getter is not None:
        return getter(key, default)
    try:
        return user[key]
    except (KeyError, IndexError):
        return default


def require_eligible_user(user: Mapping[str, object] | None, *, operation: str = "chat") -> None:
    """Raise :class:`EligibilityDenied` unless a user may use *operation*.

    This is deliberately transport-agnostic: HTTP routers, bot handlers and
    background workers can share the same rule without importing FastAPI or
    Celery. The check fails closed for missing users and every status other than
    the schema's active value.
    """
    if not user:
        raise EligibilityDenied("user_not_found", "пользователь не найден")

    if _value(user, "status") != _ACTIVE_STATUS:
        raise EligibilityDenied(
            "account_not_active",
            f"операция {operation} недоступна для неактивного аккаунта",
        )
