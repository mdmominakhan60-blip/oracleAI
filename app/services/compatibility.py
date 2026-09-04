"""Прикладные сценарии совместимости.

Модуль не знает о FastAPI и возвращает только данные use case либо
CompatibilityDenied. HTTP-статусы и тексты ошибок остаются в api-слое.
"""
from __future__ import annotations

from ..core import agent as agent_core
from ..core import memory, shared_context, tool_registry as skills
from ..repo import dialog, readings
from . import analytics, limits


class CompatibilityDenied(Exception):
    """Лимит или подписка не позволяют запустить полный разбор."""

    def __init__(self, verdict) -> None:
        self.verdict = verdict
        super().__init__(getattr(verdict, "reason", "access_denied"))


async def calculate(db, user, partner_date: str, *, relation: str = "love",
                    partner_name: str = "", save: bool = False) -> dict:
    """Рассчитать совместимость и при необходимости сохранить партнёра."""
    aspects = await skills.pair_aspects(db, user, partner_date)
    data = skills.compatibility_score(user["birth_date"], partner_date,
                                      relation=relation, aspects=aspects)
    if save and partner_name:
        await readings.add_partner(db, user["tg_id"], partner_name.strip(),
                                   partner_date)
    return {**data, "partner_date": partner_date}


async def explain(db, user, partner_date: str, *, partner_name: str = "",
                  relation: str = "love", save: bool = False) -> dict:
    """Сформировать полный разбор совместимости с учётом лимита."""
    verdict = await limits.check(db, user)
    if not verdict.allowed:
        raise CompatibilityDenied(verdict)
    if not await limits.consume(db, user, verdict):
        raise CompatibilityDenied(verdict)

    name = partner_name.strip()[:30]
    thread = await dialog.ensure_thread(db, user["tg_id"], "astro")
    await dialog.save_message(
        db, user["tg_id"], "user", f"Совместимость с {name or 'партнёром'}",
        is_question=limits.counts_toward_limit(verdict), thread_id=thread["id"],
        agent="astro", surface="miniapp")
    text = await agent_core.interpret_compat(db, user, partner_date, name,
                                             relation=relation)
    await dialog.save_message(db, user["tg_id"], "assistant", text,
                              thread_id=thread["id"], agent="astro",
                              surface="miniapp")
    await shared_context.record_recommendation(
        db, user, agent="astro", text=text, source_ref=f"thread:{thread['id']}"
    )
    if name:
        if bool(user["memory_enabled"]):
            await memory.remember(db, user["tg_id"],
                                  f"Партнёр {name}, дата рождения {partner_date}",
                                  kind="person")
        if save:
            await readings.add_partner(db, user["tg_id"], name, partner_date)
    await analytics.track(db, "compat_full", user["tg_id"], surface="miniapp")

    aspects = await skills.pair_aspects(db, user, partner_date)
    scores = skills.compatibility_score(user["birth_date"], partner_date,
                                        relation=relation, aspects=aspects)
    return {"answer": text, "scores": scores}
