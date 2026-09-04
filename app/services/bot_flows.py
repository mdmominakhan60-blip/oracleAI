"""Presentation-facing orchestration for bot flows (readings, diary, dialog).

Thin orchestration only: business policy stays in app/services/*, SQL in
app/repo/*. Каждый хендлер бота получает готовую агрегатную функцию вместо
прямого похода в репозиторий.
"""
from __future__ import annotations


# ── расклады / партнёры ────────────────────────────────────────────────────
async def reading(db, reading_id: int, tg_id: int):
    from ..repo import readings

    return await readings.get_reading(db, reading_id, tg_id)


async def set_reading_outcome(db, reading_id: int, tg_id: int, outcome: str) -> bool:
    from ..repo import readings

    return await readings.set_outcome(db, reading_id, tg_id, outcome)


async def partners(db, tg_id: int) -> list[dict]:
    from ..repo import readings

    return await readings.list_partners(db, tg_id)


async def add_partner(db, tg_id: int, name: str, birth_date: str) -> int:
    from ..repo import readings

    return await readings.add_partner(db, tg_id, name, birth_date)


# ── диалоги / треды ─────────────────────────────────────────────────────────
async def save_exchange(db, tg_id: int, user_text: str, answer: str, *,
                        thread_id: int, agent: str, is_question: bool) -> None:
    """Сохранить пару user/assistant в тред (например, compat-сценарий)."""
    from ..repo import dialog

    await dialog.save_message(db, tg_id, "user", user_text,
                              is_question=is_question,
                              thread_id=thread_id, agent="astro")
    await dialog.save_message(db, tg_id, "assistant", answer,
                              thread_id=thread_id, agent="astro")


async def astro_thread(db, tg_id: int) -> dict:
    from ..repo import dialog

    return await dialog.ensure_thread(db, tg_id, "astro")


# ── дневник ─────────────────────────────────────────────────────────────────
async def diary_view(db, tg_id: int, *, limit: int = 5) -> dict:
    from ..repo import dialog

    entries = await dialog.get_diary(db, tg_id, limit=limit)
    streak = await dialog.diary_streak(db, tg_id)
    return {"entries": entries, "streak": streak}


async def diary_add(db, tg_id: int, text: str) -> int:
    """Запись в дневник; возвращает текущий стрик."""
    from ..repo import dialog

    await dialog.add_diary(db, tg_id, text)
    return await dialog.diary_streak(db, tg_id)
