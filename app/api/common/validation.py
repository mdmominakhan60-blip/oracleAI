"""Валидация входных значений на границе HTTP/API."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException


_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def parse_birth_date(value: str | None) -> str:
    """Нормализует дату рождения в ISO-формат.

    Mini App и Telegram-бот исторически отправляют разные форматы, поэтому
    совместимость сохраняется в одном месте. Ошибка остаётся HTTP 400, как в
    прежнем публичном API.
    """
    value = (value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise HTTPException(status_code=400,
                        detail="нужна дата в формате ДД.ММ.ГГГГ")
