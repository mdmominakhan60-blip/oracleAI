"""Регрессии локализации server-managed copy."""
from __future__ import annotations

import pytest

from app.repo import content


@pytest.mark.asyncio
async def test_get_text_uses_english_default_instead_of_legacy_russian_body(db):
    await content.upsert_content(
        db, "copy", "limit_reached", title="Лимит", body="Русский текст",
    )

    text = await content.get_text(
        db, "copy", "limit_reached", "English caller fallback", lang="en",
    )

    assert "stars are resting" in text
    assert "Русский" not in text


@pytest.mark.asyncio
async def test_get_text_uses_admin_english_override_and_keeps_russian_body(db):
    await content.upsert_content(
        db, "copy", "winback", title="Возврат", body="Русская версия",
        meta={"title_en": "Return", "body_en": "English version"},
    )

    assert await content.get_text(db, "copy", "winback", lang="ru") == "Русская версия"
    assert await content.get_text(db, "copy", "winback", lang="en") == "English version"
    item = await content.get_content(db, "copy", "winback")
    assert content.localized_item(item, "en")["title"] == "Return"


@pytest.mark.asyncio
async def test_unknown_english_content_uses_explicit_caller_fallback(db):
    await content.upsert_content(
        db, "copy", "custom_notice", title="Уведомление", body="Только русский",
    )

    assert await content.get_text(
        db, "copy", "custom_notice", "English fallback", lang="en",
    ) == "English fallback"
