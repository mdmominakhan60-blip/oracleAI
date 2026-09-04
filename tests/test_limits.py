"""Лимиты вопросов и путь диалога: кому что можно и что за это списывается."""
from __future__ import annotations

import pytest

from app.core import agents
from app.repo import billing, dialog, readings, users
from app.services import catalog, chat, limits


async def _ask_n_times(db, user, n: int) -> None:
    """Имитирует n «платных» вопросов, потраченных из лимита тарифа."""
    for i in range(n):
        await dialog.save_message(db, user["tg_id"], "user", f"вопрос {i}",
                                  is_question=True)


async def test_first_message_sets_privacy_safe_thread_title(db, user):
    thread = await dialog.ensure_thread(db, user["tg_id"], "oracle", title="Личный Оракул")
    await dialog.save_message(
        db, user["tg_id"], "user", "Мне тревожно из-за работы и денег",
        is_question=True, thread_id=thread["id"], agent="oracle",
    )
    await dialog.save_message(
        db, user["tg_id"], "assistant", "Один маленький шаг",
        thread_id=thread["id"], agent="oracle",
    )
    await dialog.save_message(
        db, user["tg_id"], "user", "Ещё один вопрос про отношения",
        is_question=False, thread_id=thread["id"], agent="oracle",
    )
    fresh = await dialog.get_thread(db, thread["id"], user["tg_id"])
    assert fresh["title"] == "Дело и ресурсы"
    assert "тревожно" not in fresh["title"]


async def test_vip_gets_three_questions_per_day(db, user):
    allowance = await limits.allowance(db, user)
    assert allowance.period == "day"
    assert allowance.limit == 3
    assert allowance.left == 3


async def test_limit_decreases_with_questions(db, user):
    await _ask_n_times(db, user, 2)
    allowance = await limits.allowance(db, user)
    assert allowance.used == 2
    assert allowance.left == 1


async def test_free_plan_is_weekly(db, free_user):
    allowance = await limits.allowance(db, free_user)
    assert allowance.period == "week"
    assert allowance.limit == 1


async def test_expired_subscription_falls_back_to_free(db, free_user):
    plan = await limits.active_plan(db, free_user)
    assert plan["code"] == "free", "истёкшая подписка всё ещё считается активной"


async def test_check_uses_plan_first_then_purchases(db, user):
    verdict = await limits.check(db, user)
    assert verdict.allowed and verdict.charge == limits.PLAN

    await _ask_n_times(db, user, 3)
    await billing.grant_entitlement(db, user["tg_id"], "question", "*", qty=1)
    verdict = await limits.check(db, user)
    assert verdict.charge == limits.ENT_QUESTION, "купленный вопрос не подхватился"


async def test_crystals_are_last_resort(db, user):
    await _ask_n_times(db, user, 3)
    await users.update(db, user["tg_id"], crystals=100)
    fresh = await users.get(db, user["tg_id"])
    verdict = await limits.check(db, fresh)
    assert verdict.charge == limits.CRYSTALS


async def test_denied_when_nothing_left(db, user):
    await _ask_n_times(db, user, 3)
    await users.update(db, user["tg_id"], crystals=0)
    fresh = await users.get(db, user["tg_id"])
    verdict = await limits.check(db, fresh)
    assert not verdict.allowed
    assert verdict.reason == "limit_reached"


async def test_followup_does_not_consume_limit(db, user):
    """Уточнение к только что заданному вопросу не должно съедать второй вопрос."""
    await dialog.save_message(db, user["tg_id"], "user", "первый вопрос",
                              is_question=True)
    verdict = await limits.check(db, user)
    assert verdict.charge == limits.FOLLOWUP
    assert not limits.counts_toward_limit(verdict)


async def test_followups_are_capped(db, user):
    await dialog.save_message(db, user["tg_id"], "user", "вопрос", is_question=True)
    for _ in range(limits.FOLLOWUP_MAX):
        await dialog.save_message(db, user["tg_id"], "user", "а что это значит?",
                                  is_question=False)
    verdict = await limits.check(db, user)
    assert verdict.charge != limits.FOLLOWUP, "бесконечные бесплатные уточнения"


async def test_consume_crystals_actually_charges(db, user):
    await _ask_n_times(db, user, 3)
    await users.update(db, user["tg_id"], crystals=50)
    fresh = await users.get(db, user["tg_id"])
    verdict = await limits.check(db, fresh)
    assert await limits.consume(db, fresh, verdict)
    after = await users.get(db, user["tg_id"])
    assert after["crystals"] == 50 - verdict.allowance.emergency_cost


# ─────────────────────── доступ к раскладам ───────────────────────────────────

async def test_included_spread_needs_only_plan(db, user):
    verdict = await limits.spread_access(db, user, "three")
    assert verdict.allowed and verdict.charge == limits.PLAN


async def test_premium_spread_uses_entitlement_first(db, user):
    await billing.grant_entitlement(db, user["tg_id"], "spread", "celtic", qty=1)
    verdict = await limits.spread_access(db, user, "celtic")
    assert verdict.charge == limits.ENT_SPREAD
    assert await limits.consume(db, user, verdict)
    # право потратилось, лимит тарифа остался целым
    assert await billing.available_entitlements(db, user["tg_id"], "spread", "celtic") == 0
    allowance = await limits.allowance(db, user)
    assert allowance.left == 3


async def test_premium_spread_not_available_without_purchase(db, user):
    assert not await catalog.is_available(db, user, "celtic")
    assert await catalog.is_available(db, user, "three")


async def test_spread_catalog_shows_prices(db, user):
    items = await catalog.spread_list(db, user)
    celtic = next(s for s in items if s["code"] == "celtic")
    assert celtic["tier"] == "premium"
    assert celtic["price_stars"] > 0 and celtic["sku"]
    three = next(s for s in items if s["code"] == "three")
    assert three["tier"] == "included"


# ─────────────────────────── путь диалога ─────────────────────────────────────

async def test_ask_saves_messages_and_returns_answer(db, user):
    result = await chat.ask(db, user, "Что меня ждёт в любви?")
    assert result["answer"], "агент не ответил даже в офлайн-режиме"
    assert result["agent"] == agents.DEFAULT_AGENT
    history = await dialog.thread_messages(db, result["thread_id"])
    assert [m["role"] for m in history] == ["user", "assistant"]


async def test_ask_is_denied_without_access(db, free_user):
    await dialog.save_message(db, free_user["tg_id"], "user", "вопрос",
                              is_question=True)
    await users.update(db, free_user["tg_id"], crystals=0)
    fresh = await users.get(db, free_user["tg_id"])
    with pytest.raises(chat.ChatDenied):
        await chat.ask(db, fresh, "ещё вопрос")


async def test_parallel_asks_cannot_overspend_weekly_limit(db, free_user,
                                                           monkeypatch):
    """Гонка двух устройств: недельный лимит 1, а оплачено должно быть одно.

    Замок бюджета (G19) держит «проверил → списал → записал вопрос», поэтому
    второй запрос видит расход первого до генерации ответа.
    """
    import asyncio

    async def no_followup(db_, user_):
        return False            # мгновенная вторая фраза — отдельный вопрос

    monkeypatch.setattr(limits, "_is_followup", no_followup)
    await users.update(db, free_user["tg_id"], crystals=0)
    fresh = await users.get(db, free_user["tg_id"])

    async def ask_once() -> str:
        try:
            await chat.ask(db, fresh, "Во сколько мне проснуться завтра?")
            return "ok"
        except chat.ChatDenied:
            return "denied"

    results = await asyncio.gather(ask_once(), ask_once())
    assert results.count("ok") == 1, "по недельному лимиту 1 прошло больше одного"
    assert results.count("denied") == 1


async def test_ask_to_each_agent_uses_own_thread(db, user):
    first = await chat.ask(db, user, "Разложи карты", agent="tarot")
    second = await chat.ask(db, user, "Что с моей Венерой?", agent="astro")
    assert first["thread_id"] != second["thread_id"]
    threads = await dialog.list_threads(db, user["tg_id"])
    assert {t["agent"] for t in threads} >= {"tarot", "astro"}


async def test_empty_question_is_rejected(db, user):
    with pytest.raises(ValueError):
        await chat.ask(db, user, "   ")


async def test_draw_and_interpret_flow(db, user):
    drawn = await chat.draw(db, user, "three")
    assert len(drawn["cards"]) == 3
    assert len(drawn["positions"]) == 3

    answer = await chat.interpret(db, user, drawn["reading_id"])
    assert answer
    # повторная трактовка отдаёт сохранённый текст, а не генерирует заново
    assert await chat.interpret(db, user, drawn["reading_id"]) == answer

    history = await readings.recent_readings(db, user["tg_id"])
    assert history and history[0]["spread"] == "three"


async def test_draw_premium_without_right_is_denied(db, user):
    with pytest.raises(chat.ChatDenied):
        # лимит тарифа съеден, права нет
        await _ask_n_times(db, user, 3)
        await users.update(db, user["tg_id"], crystals=0)
        fresh = await users.get(db, user["tg_id"])
        await chat.draw(db, fresh, "celtic")


async def test_interpret_unknown_reading_raises(db, user):
    with pytest.raises(LookupError):
        await chat.interpret(db, user, 999999)


async def test_threads_view_lists_all_agents(db, user):
    view = await chat.threads_view(db, user)
    assert {t["code"] for t in view} == set(agents.codes())
    assert all(t["last_text"] for t in view), "у чата нет превью"


async def test_outcome_marks_reading(db, user):
    drawn = await chat.draw(db, user, "one")
    await chat.interpret(db, user, drawn["reading_id"])
    assert await readings.set_outcome(db, drawn["reading_id"], user["tg_id"],
                                      "came_true")
    assert not await readings.set_outcome(db, drawn["reading_id"], user["tg_id"],
                                          "мусор")
    history = await readings.recent_readings(db, user["tg_id"])
    assert history[0]["outcome"] == "came_true"
