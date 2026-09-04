from __future__ import annotations

from app.bot.keyboards import language_kb, main_menu, plans_kb
from app.bot.onboarding_parsers import parse_birth_date, parse_birth_time
from app.repo import users


def test_natural_birth_date_parser_accepts_russian_and_iso_forms():
    assert parse_birth_date("21 июня 1999", lang="ru").normalized == "1999-06-21"
    assert parse_birth_date("1999-06-21", lang="en").normalized == "1999-06-21"
    assert parse_birth_date("June 21 1999", lang="en").normalized == "1999-06-21"


def test_birth_date_parser_rejects_ambiguous_or_impossible_values():
    try:
        parse_birth_date("21/06", lang="ru")
    except ValueError as exc:
        assert str(exc) == "ambiguous_date"
    else:
        raise AssertionError("a date without a year must not be guessed")
    try:
        parse_birth_date("31.02.1999", lang="ru")
    except ValueError as exc:
        assert str(exc) == "invalid_calendar_date"
    else:
        raise AssertionError("an impossible calendar date must be rejected")


def test_birth_time_parser_keeps_precision_honest():
    exact = parse_birth_time("1430")
    assert exact.value == "14:30" and exact.known and exact.precision == "exact"
    unknown = parse_birth_time("не знаю")
    assert unknown.value == "12:00" and not unknown.known and unknown.precision == "unknown"
    approximate = parse_birth_time("примерно")
    assert approximate.value == "14:00" and not approximate.known and approximate.precision == "approximate"


def test_main_menu_has_no_visible_age_gate_and_localizes_primary_actions():
    ru = [button.text for row in main_menu().inline_keyboard for button in row]
    en = [button.text for row in main_menu(lang="en").inline_keyboard for button in row]
    assert not any("16" in text for text in ru + en)
    assert "✨ Спросить Оракула" in ru
    assert "✨ Ask Oracle" in en


def test_language_keyboard_and_annual_plan_callbacks_are_explicit():
    buttons = [button for row in language_kb().inline_keyboard for button in row]
    assert {button.callback_data for button in buttons} == {"language:ru", "language:en"}
    plan = {"code": "vip", "title": "VIP", "price_stars": 100,
            "annual_price_stars": 1000, "badge": "Popular"}
    callbacks = [button.callback_data for row in plans_kb([plan], "free", period="annual").inline_keyboard for button in row]
    assert "buy_plan:vip:annual" in callbacks
    assert "plans:monthly" in callbacks and "plans:annual" in callbacks


async def test_new_user_has_resumable_onboarding_fields(db):
    user = await users.ensure(db, 91101, "New user")
    assert user["onboarding_step"] is None
    assert user["natal_technique"] == "astrology"
    assert user["birth_time_precision"] == "exact"
    await users.update(db, 91101, onboarding_step="city", natal_technique="lenormand",
                       birth_time_precision="unknown")
    updated = await users.get(db, 91101)
    assert updated["onboarding_step"] == "city"
    assert updated["natal_technique"] == "lenormand"
    assert updated["birth_time_precision"] == "unknown"
