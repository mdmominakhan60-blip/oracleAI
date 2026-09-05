"""HTTP-контракты приёма funnel-событий (EXP-004)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FunnelEvent(BaseModel):
    # extra="forbid": клиент не может протащить поля вне контракта
    # (в т.ч. свободные props) — они молча игнорировались бы.
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=32)
    session_id: str = Field(min_length=8, max_length=64)
    surface: str = Field(default="web", min_length=1, max_length=16)
    source: str = Field(default="direct", min_length=1, max_length=32)
    medium: str = Field(default="none", min_length=1, max_length=32)
    campaign: str | None = Field(default=None, max_length=64)
    path: str | None = Field(default=None, max_length=128)
    activation_action: str | None = Field(default=None, max_length=32)
    signup_method: str | None = Field(default=None, max_length=32)


class FunnelEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # batch — до 20 событий сессии одним запросом (beacon на pagehide).
    events: list[FunnelEvent] = Field(min_length=1, max_length=20)

