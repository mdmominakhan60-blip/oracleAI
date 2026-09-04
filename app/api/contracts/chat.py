"""HTTP-контракты для диалогов с проводниками."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    allow_paid: bool = True
