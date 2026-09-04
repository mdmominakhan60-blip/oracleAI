"""Кризисный протокол: что происходит, когда вопрос выходит за рамки эзотерики.

Здесь проверяется не текст ответа, а поведение продукта: кризисное сообщение
не доходит до модели, не тратит лимит и попадает в журнал. Это единственная
часть системы, где «пропустить» дороже, чем «сработать зря», поэтому набор
формулировок нарочно широкий.
"""
from __future__ import annotations

import pytest

from app.core import safety
from app.services import chat as chat_svc
from app.services import limits


@pytest.mark.parametrize("text", [
    "не хочу жить",
    "Я больше не хочу жить, ничего не помогает",
    "думаю покончить с собой",
    "иногда хочется уйти из жизни",
    "н е   х о ч у   ж и т ь",          # обход фильтра пробелами
    "н😀е х🔹оч̶у ж и т ь",              # обход эмодзи/ZWJ между буквами
    "не​хочу​жить",           # нулевые пробелы
    "НЕ ХОЧУ ЖИТЬ",
    "I want to end it all",
    "i want to end- -my- -life",
    "better off dead",
    "I don't want to be alive",
    "no reason to live anymore",
    "я режу себя когда плохо",
    "он меня бьёт, я боюсь",
    "муж бьет и угрожает убить",
])
def test_crisis_detected(text):
    level, category = safety.classify(text)
    assert level == safety.CRISIS
    assert category


@pytest.mark.parametrize("text", [
    "мне поставили диагноз, что говорят карты",
    "у мамы онкология, что будет",
    "стоит ли брать ипотеку",
    "я беременна, что меня ждёт",
])
def test_sensitive_softened(text):
    level, category = safety.classify(text)
    assert level == safety.SOFTEN
    assert safety.soften_rule(category)


@pytest.mark.parametrize("text", [
    "что меня ждёт в любви?",
    "когда я встречу своего человека",
    "стоит ли ему написать первой",
    "расскажи про мою венеру",
    "хочу расклад на неделю",
])
def test_normal_questions_pass(text):
    level, _ = safety.classify(text)
    assert level == safety.NONE


def test_empty_text_is_safe():
    assert safety.classify("") == (safety.NONE, "")
    assert safety.classify(None) == (safety.NONE, "")


async def test_crisis_answer_does_not_spend_limit(db, user):
    """Главный инвариант: за кризисное обращение не берут вопрос дня."""
    before = await limits.allowance(db, user, check_followup=False)

    result = await chat_svc.ask(db, user, "я не хочу жить")

    assert result["charge"] == "none"
    assert result["safety"]
    after = await limits.allowance(db, await _fresh(db, user),
                                   check_followup=False)
    assert after.used == before.used, "кризисный ответ списал вопрос дня"


async def test_crisis_answer_has_helplines(db, user):
    result = await chat_svc.ask(db, user, "хочу покончить с собой")
    answer = result["answer"]
    assert "112" in answer or "8-800" in answer, "нет контактов помощи"
    assert len(answer) > 200, "отписка вместо поддержки"
    # в кризисе не гадаем: ни карт, ни предсказаний
    assert "расклад" not in answer.lower()
    assert "выпал" not in answer.lower()


async def test_crisis_logged(db, user):
    await chat_svc.ask(db, user, "он меня бьёт")
    cur = await db.execute(
        "SELECT category, action FROM safety_events WHERE tg_id=?",
        (user["tg_id"],))
    rows = await cur.fetchall()
    assert rows, "срабатывание не попало в журнал"
    assert rows[0]["action"] == "support"


async def test_helplines_configurable(db):
    from app.repo import content
    await content.set_setting(db, "safety.helplines", ["🇩🇪 Германия — 0800 111 0 111"])
    lines = await safety.helplines(db)
    assert lines == ["🇩🇪 Германия — 0800 111 0 111"]


async def _fresh(db, user):
    from app.repo import users
    return await users.get(db, user["tg_id"])
