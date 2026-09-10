"""HTTP-контракты read-only API shared context (BUS-810, gap G-12).

Панель «Память о пользователе» нового UI читает события и снапшоты
shared context. Owner-scope по tg_id аутентифицированной клиентки:
параметр tg_id в контракте отсутствует намеренно — фильтр ставится
на уровне SQL из auth-зависимости, подделка невозможна.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SharedContextEvent(BaseModel):
    """Одно событие shared context (рекомендация между агентами)."""
    id: int
    event_type: str
    agent: str
    content: str
    source_ref: str = ""
    created_at: str
    expires_at: str | None = None


class SharedContextEventList(BaseModel):
    events: list[SharedContextEvent]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    owner_scoped: bool


class SharedContextSnapshot(BaseModel):
    """Кэшированный снапшот (например, транзиты текущего дня)."""
    id: int
    snapshot_type: str
    snapshot_key: str
    created_at: str
    expires_at: str | None = None
    payload: dict[str, Any]


class SharedContextSnapshotList(BaseModel):
    snapshots: list[SharedContextSnapshot]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    owner_scoped: bool
