"""Знакомство: /start, промокод из ссылки, данные рождения, образ и имя Оракула.

Онбординг — самое дорогое место продукта: здесь теряется больше всего людей.
Поэтому шагов минимум, каждый объясняет, зачем он нужен, а после расчёта карты
пользователь сразу получает «три откровения» — первую ценность до любой оплаты.
"""
from __future__ import annotations

import json
import logging
from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..core import astro, geo
from ..core.personas import persona_list
from ..services import access, analytics, billing as billing_svc, referrals
from ..repo import content as content_repo, readings, users
from .formatting import tg_esc
from .onboarding_parsers import date_error_copy, parse_birth_date, parse_birth_time, time_error_copy
from .keyboards import (ask_starters_kb, back_menu, city_pick_kb,
                        confirmation_kb, date_decades_kb, date_days_kb,
                        date_months_kb, date_years_kb, gender_kb, language_kb,
                        main_menu, onboarding_edit_kb,
                        personas_kb, technique_kb, time_kb, welcome_kb)

log = logging.getLogger("oracle.bot.onboarding")
router = Router()

# BOT-005: мёртвые DATE_RE/TIME_RE/UNKNOWN_TIME/WELCOME_FALLBACK* удалены —
# парсинг давно живёт в onboarding_parsers.py (естественные RU/EN-даты), а
# welcome-копия — в content registry; дубли здесь только дрейфовали.


def _lang(user) -> str:
    return "en" if user["lang"] == "en" else "ru"


def _step_label(step: str, lang: str) -> str:
    """Прогресс онбординга «Шаг N/5» — честная нумерация шагов ввода.

    Подтверждение (confirm) и пост-шаги (technique, oracle_name) не нумеруем:
    это проверка данных и выбор способа чтения, а не шаги ввода."""
    numbers = {"name": 1, "gender": 2, "date": 3, "time": 4, "city": 5}
    n = numbers.get(step)
    if not n:
        return ""
    return (f"Шаг {n}/5" if lang == "ru" else f"Step {n}/5") + "\n"


def _copy(user, ru: str, en: str) -> str:
    return en if _lang(user) == "en" else ru


def _g(user, feminine: str, masculine: str, neutral: str) -> str:
    """Русская форма обращения; для старых профилей оставляем нейтральный текст."""
    if user["gender"] == "f":
        return feminine
    if user["gender"] == "m":
        return masculine
    return neutral


class Onb(StatesGroup):
    # BOT-004: legacy-состояние `age` удалено — поток его не использовал, а
    # висящее состояние путало чтение FSM; обрабатывавшие его кнопки age:confirm
    # также удалены (GAUNTLET v2).
    language = State()
    name = State()
    gender = State()
    date = State()
    time = State()
    city = State()
    confirm = State()
    technique = State()
    oracle_name = State()


class Promo(StatesGroup):
    waiting = State()


class DeleteMe(StatesGroup):
    confirm = State()


async def _is_admin(db, tg_id: int) -> bool:
    return await access.is_admin(db, tg_id)


async def _menu(db, tg_id: int):
    user = await users.get(db, tg_id)
    return main_menu(is_admin=await _is_admin(db, tg_id), lang=_lang(user))


# ─────────────────────────────── /start ───────────────────────────────────────

@router.message(CommandStart(deep_link=True))
async def start_deeplink(message: Message, command: CommandObject,
                         state: FSMContext, db):
    """`/start ref_123` — приглашение, `/start КОД` — промокод с Etsy."""
    await users.ensure(db, message.from_user.id, message.from_user.first_name,
                       message.from_user.username, lang=message.from_user.language_code)
    arg = (command.args or "").strip()

    ref_id = referrals.parse_ref(arg)
    if ref_id:
        result = await referrals.apply(db, message.from_user.id, ref_id)
        if result:
            user = await users.get(db, message.from_user.id)
            await message.answer(_copy(
                user,
                "💫 Тебя пригласили к Оракулу — это добрый знак.\n"
                f"Вам обоим — по ✦{result['bonus']} Кристаллов ✨",
                "💫 You were invited to Oracle — a lovely sign.\n"
                f"You both receive ✦{result['bonus']} Crystals ✨",
            ))
            try:
                referrer = await users.get(db, ref_id)
                await message.bot.send_message(ref_id, _copy(
                    referrer,
                    f"🌟 К Оракулу пришёл новый человек — тебе ✦{result['bonus']}!",
                    f"🌟 A new person has joined Oracle — you received ✦{result['bonus']}!",
                ))
            except Exception as e:  # noqa: BLE001
                log.info("не смогла уведомить пригласившую %s: %s", ref_id, e)
    elif arg:
        granted = await billing_svc.redeem_promo(db, message.from_user.id, arg)
        if granted:
            await message.answer(_promo_text(granted))

    await analytics.track(db, analytics.E_START, message.from_user.id,
                          props={"arg": arg[:40]})
    await _begin(message, state, db)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, db):
    await users.ensure(db, message.from_user.id, message.from_user.first_name,
                       message.from_user.username, lang=message.from_user.language_code)
    await analytics.track(db, analytics.E_START, message.from_user.id)
    await _begin(message, state, db)


async def _begin(message: Message, state: FSMContext, db):
    user = await users.get(db, message.from_user.id)
    if user["onboarded"]:
        await state.clear()
        await analytics.track(db, "home_view", message.from_user.id, props={"returning": True}, surface="bot")
        last = (await readings.recent_readings(db, message.from_user.id, limit=1) or [None])[0]
        if last:
            from ..core.tarot import SPREADS
            kind = SPREADS.get(last["spread"], {}).get("title") or last["spread"]
            last_line = (_copy(user, f"Последнее исследование: {kind}, {last['created_at'][:10]}",
                               f"Last reading: {kind}, {last['created_at'][:10]}"))
            text = _copy(user,
                         f"С возвращением, {tg_esc(user['name'])} 🌙\n{last_line}\nРада видеть тебя снова 🌙",
                         f"Welcome back, {tg_esc(user['name'])} 🌙\n{last_line}\nGood to see you again 🌙")
        else:
            text = _copy(user,
                         f"С возвращением, {tg_esc(user['name'])} 🌙\nРада видеть тебя снова 🌙",
                         f"Welcome back, {tg_esc(user['name'])} 🌙\nGood to see you again 🌙")
        await message.answer(text, reply_markup=await _menu(db, message.from_user.id))
        return
    step = user["onboarding_step"]
    resume_states = {"name": Onb.name, "gender": Onb.gender, "date": Onb.date,
                     "time": Onb.time, "city": Onb.city, "confirm": Onb.confirm,
                     "technique": Onb.technique, "persona": Onb.oracle_name}
    if step and step != "language" and step in resume_states:
        await state.set_state(resume_states[step])
        lang = _lang(user)
        if step == "confirm":
            text, markup = (_copy(user, "Мы остановились на подтверждении. Данные уже сохранены — проверь их и продолжим.", "We stopped at confirmation. Your data is saved — check it and we’ll continue."), confirmation_kb(lang))
        elif step == "technique":
            text, markup = (_copy(user, "Мы остановились на выборе способа чтения карты.", "We stopped at the chart-reading method."), technique_kb(lang))
        elif step == "persona":
            text, markup = (_copy(user, "Выбери характер нашего разговора.", "Choose the character of our conversation."), personas_kb(await persona_list(db)))
        elif step == "time":
            text, markup = (_copy(user, "Продолжим со временем рождения — выбери вариант или напиши его.", "Let’s continue with your birth time — choose an option or type it."), time_kb(lang))
        elif step == "city":
            text, markup = (_copy(user, "Продолжим с городом рождения.", "Let’s continue with your birth city."), back_menu())
        elif step == "date":
            text, markup = (_copy(user, "Продолжим с датой рождения. Напиши её в любом понятном формате.", "Let’s continue with your birth date. Send it in any clear format."), back_menu())
        elif step == "gender":
            text, markup = (_copy(user, "Выбери форму обращения — это можно пропустить.", "Choose how I should address you — you can skip this."), gender_kb(lang))
        else:
            text, markup = (_copy(user, "Как мне тебя называть?", "What should I call you?"), back_menu())
        await message.answer(text, reply_markup=markup)
        return
    await state.set_state(Onb.language)
    await users.update(db, message.from_user.id, onboarding_step="language")
    await analytics.track(db, "onboarding_started", message.from_user.id, surface="bot")
    await message.answer(_copy(
        user,
        "✨ Добро пожаловать в Oracle\n\n"
        "Я умею:\n"
        "• отвечать на вопросы через оракула\n"
        "• собирать твою натальную карту\n"
        "• раскладывать Таро\n\n"
        "Начнём знакомство?",
        "✨ Welcome to Oracle\n\n"
        "I can:\n"
        "• answer your questions through the oracle\n"
        "• build your natal chart\n"
        "• lay out Tarot\n\n"
        "Shall we begin?",
    ), reply_markup=welcome_kb(_lang(user) if user else "ru"))


# ─────────────────────────────── шаги FSM ─────────────────────────────────────

@router.callback_query(F.data == "onb:begin")
async def onb_begin(cb: CallbackQuery, state: FSMContext, db):
    """[Начать] с welcome-экрана — тот же старт онбординга, что раньше с /start."""
    user = await users.get(db, cb.from_user.id)
    await state.set_state(Onb.language)
    await analytics.track(db, "onboarding_started", cb.from_user.id, surface="bot")
    await cb.message.edit_text(_copy(
        user,
        "🌙 Рада тебя видеть. Сначала выберем язык — его можно изменить в любой момент.",
        "🌙 I’m glad you’re here. First, choose your language — you can change it anytime.",
    ), reply_markup=language_kb())
    await cb.answer()


@router.callback_query(F.data == "onb:features")
async def onb_features(cb: CallbackQuery, state: FSMContext, db):
    """[Возможности] — показываем главное меню, FSM не трогаем."""
    user = await users.get(db, cb.from_user.id)
    await cb.message.edit_text(_copy(
        user,
        "Вот что я умею — выбери в любой момент:",
        "Here is what I can do — pick any time:",
    ), reply_markup=main_menu(is_admin=await _is_admin(db, cb.from_user.id),
                              lang=_lang(user) if user else "ru"))
    await cb.answer()


@router.callback_query(F.data.startswith("language:"))
async def onb_language(cb: CallbackQuery, state: FSMContext, db):
    value = cb.data.split(":", 1)[1]
    if value not in {"ru", "en"}:
        await cb.answer("Choose Russian or English", show_alert=True)
        return
    existing = await users.get(db, cb.from_user.id)
    onboarded = bool(existing and existing["onboarded"])
    await users.update(db, cb.from_user.id, lang=value,
                       onboarding_step=None if onboarded else "name")
    user = await users.get(db, cb.from_user.id)
    await analytics.track(db, "language_selected", cb.from_user.id, props={"lang": value}, surface="bot")
    if onboarded:
        await state.clear()
        await cb.message.edit_text(
            "Language updated." if value == "en" else "Язык обновлён.",
            reply_markup=main_menu(is_admin=await _is_admin(db, cb.from_user.id), lang=value))
    else:
        await state.set_state(Onb.name)
        await cb.message.edit_text(_step_label("name", _lang(user)) + _copy(
            user,
            "Как мне тебя называть? Имя можно изменить позже.",
            "What should I call you? You can change it later.",
        ))
    await cb.answer()


@router.message(Onb.name, F.text)
async def onb_name(message: Message, state: FSMContext, db):
    name = message.text.strip()[:40]
    user = await users.get(db, message.from_user.id)
    if not name:
        await message.answer(_copy(user, "Как мне тебя называть? ✨", "What should I call you? ✨"))
        return
    await users.update(db, message.from_user.id, name=name, onboarding_step="gender")
    await analytics.track(db, "onboarding_step", message.from_user.id, props={"step": "name"}, surface="bot")
    await state.set_state(Onb.gender)
    await message.answer(
        _step_label("gender", _lang(user)) + _copy(
            user,
            f"{tg_esc(name)}... красивое имя, в нём есть свет. 💫\n\n"
            "Чтобы подобрать форму обращения, выбери свой пол. Это можно изменить позже.",
            f"{tg_esc(name)}... a beautiful name with its own light. 💫\n\n"
            "Choose how I should address you. You can change this later.",
        ),
        reply_markup=gender_kb(_lang(user)),
    )


@router.callback_query(Onb.gender, F.data.startswith("gender:"))
async def onb_gender(cb: CallbackQuery, state: FSMContext, db):
    value = cb.data.split(":", 1)[1]
    if value not in {"f", "m", "skip"}:
        await cb.answer("Invalid choice", show_alert=True)
        return
    gender = value if value in {"f", "m"} else None
    await users.update(db, cb.from_user.id, gender=gender, onboarding_step="date")
    user = await users.get(db, cb.from_user.id)
    await state.set_state(Onb.date)
    await cb.message.edit_text(
        _step_label("date", _lang(user)) + _copy(
            user,
            "Спасибо. Теперь — дата рождения. Выбери декаду, а дальше подскажу:",
            "Thank you. Now your birth date. Pick a decade and I will guide you:",
        ),
        reply_markup=date_decades_kb(_lang(user)),
    )
    await cb.answer()


@router.message(Onb.date, F.text)
async def onb_date(message: Message, state: FSMContext, db):
    user = await users.get(db, message.from_user.id)
    try:
        parsed = parse_birth_date(message.text, lang=_lang(user))
    except ValueError as exc:
        await analytics.track(db, "onboarding_error", message.from_user.id,
                              props={"step": "date", "reason": str(exc)}, surface="bot")
        await message.answer(date_error_copy(str(exc), _lang(user)))
        return
    await _save_birth_date(message, state, db, user,
                           parsed.value.day, parsed.value.month, parsed.value.year,
                           tg_id=message.from_user.id)


async def _advance_from_time(target: Message, state: FSMContext, db, parsed,
                             tg_id: int) -> None:
    # tg_id передаётся явно: у cb.message.from_user это бот, не человек
    user = await users.get(db, tg_id)
    await users.update(db, tg_id, birth_time=parsed.value,
                       birth_time_known=int(parsed.known), birth_time_precision=parsed.precision,
                       onboarding_step="city")
    await analytics.track(db, "onboarding_step", tg_id,
                          props={"step": "time", "precision": parsed.precision}, surface="bot")
    await state.set_state(Onb.city)
    city_question = _g(user, "город, где ты родилась", "город, где ты родился", "город рождения")
    await target.answer(_step_label("city", _lang(user)) + _copy(
        user,
        f"Поняла: <b>{tg_esc(parsed.label)}</b>. И последнее — {city_question}? 🏙\n\nВыбери город или напиши свой.",
        f"Got it: <b>{tg_esc(parsed.label)}</b>. One last detail — your birth city? 🏙\n\nPick a city or type your own.",
    ), reply_markup=city_pick_kb(_lang(user)))


async def _save_birth_date(target, state, db, user, day: int, month: int,
                           year: int, tg_id: int) -> None:
    """Общая запись даты рождения для кнопочного выбора и текстового ввода."""
    from datetime import date as _date
    try:
        parsed_date = _date(year, month, day)
    except ValueError:
        await target.answer(date_error_copy("invalid_calendar_date", _lang(user)))
        return
    await users.update(db, tg_id, birth_date=parsed_date.isoformat(),
                       onboarding_step="time")
    await analytics.track(db, "onboarding_step", tg_id,
                          props={"step": "date"}, surface="bot")
    await state.set_state(Onb.time)
    label = parsed_date.strftime("%d.%m.%Y")
    await target.answer(_step_label("time", _lang(user)) + _copy(
        user,
        f"Поняла: <b>{tg_esc(label)}</b> 🌙\n\nЗнаешь ли ты время рождения? Выбери вариант или напиши его текстом.",
        f"Got it: <b>{tg_esc(label)}</b> 🌙\n\nDo you know your birth time? Choose an option or type it.",
    ), reply_markup=time_kb(_lang(user)))


@router.callback_query(Onb.date, F.data.startswith("bd:"))
async def onb_date_pick(cb: CallbackQuery, state: FSMContext, db):
    """Кнопочный выбор даты: декада → год → месяц → день. Текст — всегда fallback."""
    user = await users.get(db, cb.from_user.id)
    lang = _lang(user)
    parts = cb.data.split(":")
    kind = parts[1]
    if kind == "text":
        await cb.message.edit_text(_copy(
            user,
            "Напиши дату рождения — например 21.06.1999 или 21 июня 1999.",
            "Send your birth date — for example 21.06.1999 or June 21 1999.",
        ), reply_markup=back_menu())
        await cb.answer()
        return
    if kind == "decades":
        await cb.message.edit_reply_markup(reply_markup=date_decades_kb(lang))
        await cb.answer()
        return
    if kind == "yg":
        decade = int(parts[2])
        await cb.message.edit_text(_step_label("date", lang) + _copy(
            user, "Выбери год рождения:", "Pick your birth year:"),
            reply_markup=date_years_kb(decade, lang))
        await cb.answer()
        return
    if kind == "y":
        year = int(parts[2])
        await cb.message.edit_text(_step_label("date", lang) + _copy(
            user, "Выбери месяц:", "Pick the month:"),
            reply_markup=date_months_kb(year, lang))
        await cb.answer()
        return
    if kind == "m":
        year, month = int(parts[2]), int(parts[3])
        await cb.message.edit_text(_step_label("date", lang) + _copy(
            user, "Выбери день:", "Pick the day:"),
            reply_markup=date_days_kb(year, month, lang))
        await cb.answer()
        return
    if kind == "day":
        await cb.answer()
        await _save_birth_date(cb.message, state, db, user,
                               int(parts[4]), int(parts[3]), int(parts[2]),
                               tg_id=cb.from_user.id)
        return
    await cb.answer("Invalid choice", show_alert=True)


@router.callback_query(Onb.time, F.data.startswith("time:"))
async def onb_time_choice(cb: CallbackQuery, state: FSMContext, db):
    value = cb.data.split(":", 1)[1]
    labels = {"unknown": ("12:00", False, "unknown", "время не указано"),
              "approximate": ("14:00", False, "approximate", "примерно 14:00")}
    if value == "exact":
        await cb.message.edit_text(_copy(await users.get(db, cb.from_user.id),
            "Напиши время, например 14:30.", "Type the time, for example 14:30."))
        await cb.answer()
        return
    if value not in labels:
        await cb.answer("Выбери вариант времени", show_alert=True)
        return
    from .onboarding_parsers import ParsedTime
    parsed = ParsedTime(*labels[value])
    await _advance_from_time(cb.message, state, db, parsed, tg_id=cb.from_user.id)
    await cb.answer()


@router.message(Onb.time, F.text)
async def onb_time(message: Message, state: FSMContext, db):
    user = await users.get(db, message.from_user.id)
    try:
        parsed = parse_birth_time(message.text, lang=_lang(user))
    except ValueError as exc:
        await analytics.track(db, "onboarding_error", message.from_user.id,
                              props={"step": "time", "reason": str(exc)}, surface="bot")
        await message.answer(time_error_copy(str(exc), _lang(user)), reply_markup=time_kb(_lang(user)))
        return
    await _advance_from_time(message, state, db, parsed, tg_id=message.from_user.id)


@router.callback_query(Onb.city, F.data.startswith("city:"))
async def onb_city_pick(cb: CallbackQuery, state: FSMContext, db):
    from .keyboards import CITY_PICKS
    user = await users.get(db, cb.from_user.id)
    choice = cb.data.split(":", 1)[1]
    if choice == "other":
        await cb.message.edit_text(_copy(
            user,
            "Напиши город рождения — на русском, английском или в транслитерации.",
            "Send your birth city — in your local language, English, or transliteration.",
        ), reply_markup=back_menu())
        await cb.answer()
        return
    idx = int(choice)
    if not 0 <= idx < len(CITY_PICKS):
        await cb.answer("Invalid choice", show_alert=True)
        return
    await cb.answer()
    await onb_city(cb.message, state, db, city=CITY_PICKS[idx], tg_id=cb.from_user.id)


@router.message(Onb.city, F.text)
async def onb_city(message: Message, state: FSMContext, db, city: str | None = None,
                   tg_id: int | None = None):
    city = (city or message.text or "").strip()[:60]
    # tg_id передаётся явно из колбэка: cb.message.from_user — это бот
    tg_id = tg_id or message.from_user.id
    user = await users.get(db, tg_id)
    wait = await message.answer(_copy(
        user,
        "🌌 <i>Собираю звёзды в твою карту...</i>",
        "🌌 <i>Gathering the stars for your chart...</i>",
    ))

    if not city:
        await wait.edit_text(_copy(
            user,
            "Напиши город рождения — он нужен, чтобы определить координаты и часовой пояс карты.",
            "Please send your birth city — it is needed to determine the chart’s coordinates and time zone.",
        ))
        return

    # Оба вызова уходят в отдельный поток: геокодирование ходит в сеть, а расчёт
    # эфемерид держит GIL — синхронно они вешали бота для всех остальных.
    try:
        lat, lon, tz = await geo.resolve_city_async(city, db)
        if lat is None or lon is None:
            await wait.edit_text(_copy(
                user,
                "Я не нашла этот город. Напиши ближайший крупный город или попробуй другое написание — "
                "это нужно для точных координат и часового пояса.",
                "I could not find that city. Try a nearby major city or a different spelling — "
                "the location is needed for accurate coordinates and time zone.",
            ))
            return
        chart = await astro.compute_chart_async(
            user["birth_date"], user["birth_time"], city, lat, lon, tz,
            time_known=bool(user["birth_time_known"]),
        )
    except Exception:  # noqa: BLE001
        log.exception("onboarding chart build failed for %s", tg_id)
        await wait.edit_text(_copy(
            user,
            "Не получилось собрать карту сейчас. Данные не потерялись — попробуй ещё раз через минуту "
            "или укажи ближайший крупный город.",
            "I could not build the chart right now. Your data is safe — try again in a minute "
            "or enter a nearby major city.",
        ))
        return

    await users.update(db, tg_id, birth_city=city, birth_lat=lat,
                       birth_lon=lon, tz=tz,
                       chart_json=json.dumps(chart, ensure_ascii=False),
                       onboarding_step="confirm")
    await wait.edit_text(_confirm_summary(user, city, chart),
                         reply_markup=confirmation_kb(_lang(user)))
    await state.set_state(Onb.confirm)
    await analytics.track(db, "onboarding_step", tg_id,
                          props={"step": "confirm"}, surface="bot")


def _confirm_summary(user, city: str, chart: dict) -> str:
    """Суммари шага подтверждения — единый источник для onb_city и onb:back."""
    sun = chart["sun"]
    moon = next((item for item in chart.get("planets", [])
                 if item.get("name") in {"Луна", "Moon"}), None)
    precision_value = user["birth_time_precision"] or "exact"
    precision_ru = ("Время точное" if precision_value == "exact"
                    else "Время приблизительное — дома и Асцендент не используются")
    precision_en = ("Exact birth time" if precision_value == "exact"
                    else "Approximate time — houses and Ascendant are not used")
    return _copy(
        user,
        "🌌 <b>Твои данные</b>\n\n"
        f"Имя: <b>{tg_esc(user['name'] or '—')}</b>\n"
        f"Дата: <b>{tg_esc(user['birth_date'] or '—')}</b>\n"
        f"Время: <b>{tg_esc(user['birth_time'] or '—')}</b> · {precision_ru}\n"
        f"Город: <b>{tg_esc(city)}</b>\n\n"
        f"Солнце в <b>{tg_esc(sun['sign'])}</b> · {tg_esc(sun['element'])}\n"
        f"Луна: <b>{tg_esc((moon or {}).get('sign', '—'))}</b>\n\n"
        "Всё верно? После подтверждения выберем способ чтения карты.",
        "🌌 <b>Your details</b>\n\n"
        f"Name: <b>{tg_esc(user['name'] or '—')}</b>\n"
        f"Date: <b>{tg_esc(user['birth_date'] or '—')}</b>\n"
        f"Time: <b>{tg_esc(user['birth_time'] or '—')}</b> · {precision_en}\n"
        f"City: <b>{tg_esc(city)}</b>\n\n"
        f"Sun in <b>{tg_esc(sun['sign'])}</b> · {tg_esc(sun['element'])}\n"
        f"Moon: <b>{tg_esc((moon or {}).get('sign', '—'))}</b>\n\n"
        "Does this look right? We will choose how to read your chart next.",
    )


@router.callback_query(Onb.confirm, F.data == "onb:confirm")
async def onb_confirm(cb: CallbackQuery, state: FSMContext, db):
    user = await users.get(db, cb.from_user.id)
    await users.update(db, cb.from_user.id, onboarding_step="technique")
    await state.set_state(Onb.technique)
    await cb.message.edit_text(_copy(
        user,
        "✨ Как ты хочешь исследовать карту?\n\n<b>Астрологический разбор</b> — факты карты → аспекты → интерпретация.\n\n<b>Натальная история Ленорман</b> — карта рождения → символы → narrative exploration.",
        "✨ How would you like to explore your chart?\n\n<b>Astrology reading</b> — chart facts → aspects → interpretation.\n\n<b>Lenormand natal story</b> — birth chart → symbols → narrative exploration.",
    ), reply_markup=technique_kb(_lang(user)))
    await cb.answer()


@router.callback_query(Onb.confirm, F.data == "onb:edit")
async def onb_edit_prompt(cb: CallbackQuery, state: FSMContext, db):
    user = await users.get(db, cb.from_user.id)
    await cb.message.edit_text(_copy(user, "Что изменить?", "What would you like to change?"),
                               reply_markup=onboarding_edit_kb(_lang(user)))
    await cb.answer()


@router.callback_query(F.data.startswith("onb:edit:"))
async def onb_edit_field(cb: CallbackQuery, state: FSMContext, db):
    field = cb.data.split(":", 2)[2]
    user = await users.get(db, cb.from_user.id)
    state_map = {"name": Onb.name, "date": Onb.date, "time": Onb.time, "city": Onb.city}
    if field not in state_map:
        await cb.answer("Этот шаг уже закрыт", show_alert=True)
        return
    await state.set_state(state_map[field])
    await users.update(db, cb.from_user.id, onboarding_step=field)
    prompts = {
        "name": ("Как тебя называть?", "What should I call you?"),
        "date": ("Выбери дату рождения или напиши её — например 21 июня 1999.",
                 "Pick your birth date or type it — for example June 21 1999."),
        "time": ("Выбери или напиши время рождения.", "Choose or type your birth time."),
        "city": ("Выбери город рождения или напиши свой.", "Pick your birth city or type your own."),
    }
    text = _copy(user, *prompts[field])
    keyboards = {"time": time_kb(_lang(user)), "date": date_decades_kb(_lang(user)),
                 "city": city_pick_kb(_lang(user))}
    await cb.message.edit_text(text, reply_markup=keyboards.get(field, back_menu()))
    await cb.answer()


@router.callback_query(F.data == "onb:back")
async def onb_back(cb: CallbackQuery, state: FSMContext, db):
    user = await users.get(db, cb.from_user.id)
    current = await state.get_state()
    if current == Onb.time.state:
        await state.set_state(Onb.date)
        await users.update(db, cb.from_user.id, onboarding_step="date")
        text = _step_label("date", _lang(user)) + _copy(
            user,
            "Вернёмся к дате рождения. Выбери декаду или напиши её.",
            "Let’s return to your birth date. Pick a decade or type it.")
        markup = date_decades_kb(_lang(user))
    elif current == Onb.city.state:
        await state.set_state(Onb.time)
        await users.update(db, cb.from_user.id, onboarding_step="time")
        text = _step_label("time", _lang(user)) + _copy(
            user, "Вернёмся ко времени рождения.", "Let’s return to your birth time.")
        markup = time_kb(_lang(user))
    elif current == Onb.confirm.state or current == Onb.name.state and user["onboarding_step"] == "name" and user["chart_json"]:
        await state.set_state(Onb.confirm)
        await users.update(db, cb.from_user.id, onboarding_step="confirm")
        text = _confirm_summary(user, user["birth_city"] or "",
                                users.chart_of(user) or {"sun": {"sign": "—", "element": "—"},
                                                         "planets": []})
        await cb.message.edit_text(text, reply_markup=confirmation_kb(_lang(user)))
        await cb.answer()
        return
    else:
        await state.clear()
        text = _copy(user, "Пауза сохранена. Нажми /start, когда захочешь продолжить.", "Paused here. Press /start when you want to continue.")
        markup = back_menu()
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(Onb.technique, F.data.startswith("technique:"))
async def onb_technique(cb: CallbackQuery, state: FSMContext, db):
    technique = cb.data.split(":", 1)[1]
    if technique not in {"astrology", "lenormand"}:
        await cb.answer("Unknown technique", show_alert=True)
        return
    await users.update(db, cb.from_user.id, natal_technique=technique,
                       natal_technique_version="v1", onboarding_step="persona")
    user = await users.get(db, cb.from_user.id)
    await analytics.track(db, "technique_selected", cb.from_user.id,
                          props={"technique": technique}, surface="bot")
    await state.set_state(Onb.oracle_name)
    await cb.message.edit_text(_copy(
        user,
        "Теперь выберем характер нашего разговора. Можно оставить вариант по умолчанию.",
        "Now choose the character of our conversation. You can keep the default.",
    ), reply_markup=personas_kb(await persona_list(db)))
    await cb.answer()


@router.callback_query(F.data.startswith("persona:"))
async def onb_persona(cb: CallbackQuery, state: FSMContext, db):
    code = cb.data.split(":", 1)[1]
    known = {p["code"] for p in await persona_list(db)}
    if code not in known:
        code = "friend"
    await users.update(db, cb.from_user.id, persona=code)

    user = await users.get(db, cb.from_user.id)
    if user["onboarded"]:
        # смена образа из профиля — онбординг проходить заново не нужно
        await cb.message.edit_text(_copy(
            user,
            "Хорошо. Теперь я буду говорить с тобой иначе 🌙",
            "All right. I will speak to you differently now 🌙",
        ), reply_markup=back_menu())
        await cb.answer(_copy(user, "Образ изменён", "Persona updated"))
        return

    await state.set_state(Onb.oracle_name)
    persona = next(p for p in await persona_list(db) if p["code"] == code)
    await cb.message.edit_text(_copy(
        user,
        f"{persona['emoji']} Я — {persona['title'].lower()}.\n"
        "Дай мне имя (или напиши «сама» — выберу из древних):",
        f"{persona['emoji']} I am {persona['title']}.\n"
        "Give me a name (or write ‘myself’ and I will choose an ancient one):",
    ))
    await cb.answer()


ANCIENT_NAMES = ("Лилит", "Селена", "Аврора", "Веда", "Итара", "Нимуэ", "Кассандра")


@router.message(Onb.oracle_name, F.text)
async def onb_oracle_name(message: Message, state: FSMContext, db):
    name = message.text.strip()[:30]
    if name.lower() in ("сама", "сам", "выбери", "не знаю", "myself"):
        from ..core.stable import stable_seed
        name = ANCIENT_NAMES[stable_seed(message.from_user.id) % len(ANCIENT_NAMES)]
    await users.update(db, message.from_user.id, oracle_name=name, onboarded=1, onboarding_step=None)
    await state.clear()

    user = await users.get(db, message.from_user.id)
    from ..services import limits
    allowance = await limits.allowance(db, user, check_followup=False)
    await analytics.track(db, analytics.E_ONBOARD_DONE, message.from_user.id, surface="bot")
    unit = {"day": "вопросов сегодня", "week": "вопросов за 7 дней", "month": "сообщений AI в месяц"}.get(allowance.period, "доступных вопросов")
    unit_en = {"day": "questions today", "week": "questions in 7 days", "month": "AI messages this month"}.get(allowance.period, "available questions")
    await analytics.track(db, "onboarding_completed", message.from_user.id, props={"technique": user["natal_technique"]}, surface="bot")
    await message.answer(_copy(
        user,
        f"✨ Я — <b>{tg_esc(name)}</b>, и я знаю твою карту, {tg_esc(user['name'])}.\n\n"
        f"У тебя {f'<b>{allowance.limit}</b> {unit}' if allowance.limit else 'свободный доступ к превью и сохранённым результатам'}.\n\n"
        "Что хочется понять яснее? Просто напиши вопрос — я сама выберу нужный путь.",
        f"✨ I am <b>{tg_esc(name)}</b>, and I know your chart, {tg_esc(user['name'])}.\n\n"
        f"You have {f'<b>{allowance.limit}</b> {unit_en}' if allowance.limit else 'free access to previews and saved results'}.\n\n"
        "What would you like to understand more clearly? Just ask — I will choose the right path.",
    ), reply_markup=await _menu(db, message.from_user.id))
    chart = users.chart_of(user)
    sun = (chart or {}).get("sun") or {}
    moon = next((p for p in (chart or {}).get("planets", []) if p.get("name") in {"Луна", "Moon"}), None)
    if sun:
        await message.answer(_copy(
            user,
            f"🔎 <b>Первое наблюдение</b>\nТвоё Солнце в {tg_esc(sun.get('sign', '—'))} — отправная точка карты, а Луна в {tg_esc((moon or {}).get('sign', '—'))} показывает, как ты проживаешь чувства.\n\nСпроси меня о том, что сейчас действительно важно.",
            f"🔎 <b>First insight</b>\nYour Sun in {tg_esc(sun.get('sign', '—'))} is the starting point of the chart, while the Moon in {tg_esc((moon or {}).get('sign', '—'))} describes how you process feelings.\n\nAsk me about what actually matters to you right now.",
        ), reply_markup=ask_starters_kb("en" if user["lang"] == "en" else "ru"))


# ─────────────────────────────── промокод ─────────────────────────────────────

def _promo_text(granted: dict, lang: str = "ru") -> str:
    """Что именно получил пользователь — говорим конкретно, а не «код принят».
    BOT-018: копия на языке интерфейса."""
    en = lang == "en"
    item = granted.get("granted") or {}
    kind = item.get("kind")
    if kind == "plan":
        if en:
            return (f"🎟 <b>Golden ticket accepted!</b>\n"
                    f"You have unlocked {item.get('days', 0)} days of "
                    f"«{item.get('title', 'VIP')}» access. ✨")
        return (f"🎟 <b>Золотой билет принят!</b>\n"
                f"Тебе открыто {item.get('days', 0)} дней доступа "
                f"«{item.get('title', 'VIP')}». ✨")
    if kind == "crystals":
        return (f"🎟 Done! +✦{item.get('amount', 0)} Crystals ✨" if en else
                f"🎟 Принято! +✦{item.get('amount', 0)} Кристаллов ✨")
    if kind in ("spread", "report", "question"):
        return (f"🎟 Done! Unlocked: {item.get('title', 'gift')} ✨" if en else
                f"🎟 Принято! Открыто: {item.get('title', 'подарок')} ✨")
    return "🎟 Code accepted ✨" if en else "🎟 Код принят ✨"


def _promo_prompt(lang: str) -> str:
    return ("Enter your promo code — the golden ticket: 🎟" if lang == "en"
            else "Введи промокод — золотой билет: 🎟")


@router.message(Command("promo"))
async def promo_cmd(message: Message, state: FSMContext, db):
    user = await users.get(db, message.from_user.id)
    await state.set_state(Promo.waiting)
    await message.answer(_promo_prompt(_lang(user) if user else "ru"))


@router.callback_query(F.data == "promo")
async def promo_cb(cb: CallbackQuery, state: FSMContext, db):
    user = await users.get(db, cb.from_user.id)
    await state.set_state(Promo.waiting)
    await cb.message.answer(_promo_prompt(_lang(user) if user else "ru"))
    await cb.answer()


@router.message(Promo.waiting, F.text)
async def promo_enter(message: Message, state: FSMContext, db):
    await state.clear()
    user = await users.get(db, message.from_user.id)
    lang = _lang(user) if user else "ru"
    granted = await billing_svc.redeem_promo(db, message.from_user.id,
                                         message.text.strip())
    menu = await _menu(db, message.from_user.id)
    if granted:
        await message.answer(_promo_text(granted, lang), reply_markup=menu)
    else:
        # BOT-011: отказ тоже на языке интерфейса.
        await message.answer(
            "This code does not respond... Check the spelling — it may already "
            "be redeemed or expired 🌙" if lang == "en" else
            "Этот код не отзывается... Проверь написание — возможно, он уже "
            "активирован или истёк 🌙", reply_markup=menu)


# ─────────────────────────────── помощь ───────────────────────────────────────

@router.message(Command("help"))
async def help_cmd(message: Message, db):
    user = await users.get(db, message.from_user.id)
    en = _lang(user) == "en" if user else False
    disclaimer = await content_repo.get_setting(
        db, "disclaimer_en" if en else "disclaimer",
        "Oracle is made for self-discovery and inspiration." if en else
        "Оракул создан для самопознания и вдохновения.")
    faq = await content_repo.list_content(db, "faq_en" if en else "faq",
                                     active_only=True)
    if not faq and en:
        faq = await content_repo.list_content(db, "faq", active_only=True)
    if en:
        lines = ["🔮 <b>How I work</b>", ""]
        for item in faq[:4]:
            lines.append(f"<b>{item['title']}</b>\n{item['body']}\n")
        lines += [
            "<b>Commands</b>",
            "/start — begin again · /today — daily forecast",
            "/promo — promo code · /help — this guide",
            "/delete_me — delete my data",
            "",
            f"<i>{disclaimer}</i>",
        ]
    else:
        lines = ["🔮 <b>Как я работаю</b>", ""]
        for item in faq[:4]:
            lines.append(f"<b>{item['title']}</b>\n{item['body']}\n")
        lines += [
            "<b>Команды</b>",
            "/start — начать заново · /today — прогноз дня",
            "/promo — промокод · /help — эта справка",
            "/delete_me — удалить мои данные",
            "",
            f"<i>{disclaimer}</i>",
        ]
    await message.answer("\n".join(lines),
                         reply_markup=await _menu(db, message.from_user.id))


@router.message(Command("delete_me"))
async def delete_me(message: Message, state: FSMContext, db):
    """Право на удаление данных — обязательное для сервиса с датами рождения."""
    await state.clear()
    user = await users.get(db, message.from_user.id)
    en = _lang(user) == "en" if user else False
    # BOT-007: слово подтверждения — на языке интерфейса, иначе EN-пользователь
    # физически не мог набрать «УДАЛИТЬ».
    await message.answer(
        "If you want me to forget you — I will: your birth date, chart, diary, "
        "memory and our chats.\n\nType <b>DELETE</b> in capital letters to confirm."
        if en else
        "Если ты хочешь, чтобы я забыла тебя — я забуду: сотру дату рождения, "
        "карту, дневник, память и переписку.\n\n"
        "Напиши <b>УДАЛИТЬ</b> заглавными буквами, чтобы подтвердить.")
    await state.set_state(DeleteMe.confirm)


@router.message(DeleteMe.confirm, F.text)
async def delete_me_confirm(message: Message, state: FSMContext, db):
    await state.clear()
    user = await users.get(db, message.from_user.id)
    en = _lang(user) == "en" if user else False
    if message.text.strip().upper() not in {"УДАЛИТЬ", "DELETE"}:
        await message.answer(
            "Cancelled. I am staying with you 🌙" if en else
            "Отменила. Я остаюсь с тобой 🌙",
            reply_markup=await _menu(db, message.from_user.id))
        return
    await users.anonymize(db, message.from_user.id)
    await analytics.track(db, "self_delete", message.from_user.id)
    await message.answer(
        "Done. I erased everything I knew about you.\n"
        "If you ever want to start over — just send /start 🕯" if en else
        "Готово. Я стёрла всё, что о тебе знала.\n"
        "Если однажды захочешь начать заново — просто напиши /start 🕯")
