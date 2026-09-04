"""Разделы, добавленные из исходной идеи: практики, карьера, гороскоп.

Логика целиком в сервисах (`services.practices`, `services.horoscopes`,
`core.tool_registry`) — здесь только Telegram: как показать, что нажать и что ответить.
Те же данные отдаются в Mini App, поэтому бот и приложение не расходятся.
"""
from __future__ import annotations

import logging
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..core import tool_registry as skills
from ..repo import users
from ..services import access, horoscopes, analytics
from ..services import practices as practices_svc
from .chat import _send_long
from .keyboards import career_kb, main_menu, practice_kb, practices_kb

log = logging.getLogger("oracle.bot.growth")
router = Router()


async def _menu(db, tg_id: int):
    user = await users.get(db, tg_id)
    return main_menu(is_admin=await access.is_admin(db, tg_id),
                     lang="en" if user and user["lang"] == "en" else "ru")


# ───────────────────────────── практики и шаги ─────────────────────────────────

def _practice_card(item: dict) -> str:
    """Карточка практики: зачем, когда, что делать сегодня и как понять эффект."""
    lines = [f"{item['emoji']} <b>{item['title']}</b>"]
    if item["goal"]:
        lines.append(f"<i>{item['goal']}</i>")
    lines.append("")
    if item["about"]:
        lines += [item["about"], ""]

    meta = []
    meta.append(f"⏳ Программа: {item['days']} дней")
    if item["best_time"]:
        meta.append(f"🕐 Когда: {item['best_time']}")
    if item["moon"]:
        meta.append(f"🌙 Луна: {item['moon']}")
    lines += meta + [""]

    if item["started"] and not item["finished"]:
        lines.append(f"📍 <b>Твой день {item['day_index']} из {item['days']}</b>"
                     + (f" · стрик {item['streak']} 🔥" if item["streak"] >= 2 else ""))
        if item["today_step"]:
            lines.append(f"<i>{item['today_step']}</i>")
        lines.append("")
    elif item["finished"]:
        lines += ["🎉 <b>Программа пройдена целиком.</b>", ""]

    if item["text"]:
        lines += ["<b>Текст:</b>", f"<code>{item['text']}</code>", ""]

    lines.append("<b>Что делать:</b>")
    lines += [f"{i}. {step}" for i, step in enumerate(item["steps"], 1)]

    if item["signs"]:
        lines += ["", "<b>По чему поймёшь, что работает:</b>"]
        lines += [f"• {sign}" for sign in item["signs"]]
    if item["warning"]:
        lines += ["", f"⚠️ <i>{item['warning']}</i>"]
    return "\n".join(lines)


async def _show_practices(target: Message, db, tg_id: int,
                          category: str | None = None) -> None:
    user = await users.get(db, tg_id)
    items = await practices_svc.list_for_user(db, user, category=category)
    categories = await practices_svc.categories()
    running = [p for p in items if p["started"] and not p["finished"]]
    head = ["🕯 <b>Практики и маленькие шаги</b>", ""]
    if running:
        head.append("Ты сейчас проходишь:")
        head += [f"• {p['emoji']} {p['title']} — день {p['day_index']} "
                 f"из {p['days']}" + (f", стрик {p['streak']} 🔥"
                                      if p["streak"] >= 2 else "")
                 for p in running]
        head.append("")
    head.append("<i>Короткие упражнения для внимания, решения и заботы о себе. "
                "У каждой — программа по дням, понятное действие и признаки, "
                "по которым можно заметить свой эффект.</i>")
    await target.answer("\n".join(head),
                        reply_markup=practices_kb(items, categories,
                                                  active=category))


@router.callback_query(F.data == "practices")
async def practices_menu(cb: CallbackQuery, db):
    await cb.answer()
    await _show_practices(cb.message, db, cb.from_user.id)


@router.message(Command("practice"))
async def practices_cmd(message: Message, db):
    await _show_practices(message, db, message.from_user.id)


@router.callback_query(F.data.startswith("practice_cat:"))
async def practices_category(cb: CallbackQuery, db):
    category = cb.data.split(":", 1)[1]
    await cb.answer()
    await _show_practices(cb.message, db, cb.from_user.id, category=category)


@router.callback_query(F.data.startswith("practice:"))
async def practice_card(cb: CallbackQuery, db):
    code = cb.data.split(":", 1)[1]
    user = await users.get(db, cb.from_user.id)
    items = await practices_svc.list_for_user(db, user)
    item = next((p for p in items if p["code"] == code), None)
    if not item:
        await cb.answer("Такой практики нет", show_alert=True)
        return
    await cb.answer()
    await _send_long(cb.message, _practice_card(item),
                     reply_markup=practice_kb(item))


@router.callback_query(F.data.startswith("practice_start:"))
async def practice_start(cb: CallbackQuery, db):
    code = cb.data.split(":", 1)[1]
    user = await users.get(db, cb.from_user.id)
    try:
        item = await practices_svc.start(db, user, code)
    except LookupError:
        await cb.answer("Такой практики нет", show_alert=True)
        return
    await analytics.track(db, "practice_start", user["tg_id"], props={"code": code})
    await cb.answer("Начали ✨")
    await cb.message.answer(
        f"{item['emoji']} <b>{item['title']}</b> — поехали.\n\n"
        f"Программа: {item['days']} дней. "
        f"{'Лучшее время: ' + item['best_time'] + '. ' if item['best_time'] else ''}"
        f"{'Луна: ' + item['moon'] + '.' if item['moon'] else ''}\n\n"
        f"Я буду напоминать по утрам. Главное правило — не пропускать дни: "
        f"на непрерывности всё и держится.",
        reply_markup=practice_kb(item))


@router.callback_query(F.data.startswith("practice_done:"))
async def practice_done(cb: CallbackQuery, db):
    code = cb.data.split(":", 1)[1]
    user = await users.get(db, cb.from_user.id)
    try:
        result = await practices_svc.mark_done(db, user, code)
    except LookupError:
        await cb.answer("Такой практики нет", show_alert=True)
        return
    if not result["already"]:
        await analytics.track(db, "practice_done", user["tg_id"],
                              props={"code": code, "streak": result["streak"]})
        await analytics.track_once(
            db, analytics.E_FIRST_RITUAL, user["tg_id"],
            props={"surface_action": "practice_done"}, surface="bot",
        )
    await cb.answer("Отмечено ✨" if not result["already"] else "Уже отмечено")
    tail = ""
    if not result["finished"] and result.get("today_step"):
        tail = f"\n\n<i>Завтра: {result['today_step']}</i>"
    await cb.message.answer(result["message"] + tail,
                            reply_markup=practice_kb(result))


@router.callback_query(F.data.startswith("practice_stop:"))
async def practice_stop(cb: CallbackQuery, db):
    code = cb.data.split(":", 1)[1]
    user = await users.get(db, cb.from_user.id)
    await practices_svc.stop(db, user, code)
    await cb.answer("Остановила")
    await cb.message.answer(
        "Практика остановлена. Вернуться к ней можно в любой момент — "
        "начнём заново с первого дня 🌙",
        reply_markup=await _menu(db, cb.from_user.id))


# ──────────────────────────── карьера и работа ────────────────────────────────

@router.callback_query(F.data == "career")
async def career_menu(cb: CallbackQuery, db):
    await cb.answer()
    await cb.message.answer(
        "🧭 <b>Карьера и работа</b>\n\n"
        "Здесь про предназначение, деньги и рабочие решения:\n"
        "• расклад на карьеру — где ты сейчас и куда ведёт путь;\n"
        "• расклад на проблемы — кому верить и чего избегать;\n"
        "• деловые окна — когда начинать, а когда лучше промолчать;\n"
        "• полный разбор — предназначение по карте и Матрице.\n\n"
        "<i>А ещё можно просто спросить Астролога: «когда просить повышение?»</i>",
        reply_markup=career_kb())


@router.callback_query(F.data == "career_windows")
async def career_windows(cb: CallbackQuery, db):
    """Деловые окна: тот же расчёт, что получает агент через скилл."""
    user = await users.get(db, cb.from_user.id)
    await cb.answer("Смотрю на Луну... 🌙")
    raw = await skills.execute(db, user, "get_career_windows", {"days": 14})
    # у скилла первым блоком идут правила трактовки — они для модели, не для неё
    body = raw.split("Деловые окна", 1)[-1]
    await _send_long(
        cb.message,
        "📅 <b>Деловые окна на две недели</b>\n"
        "<i>Растущая Луна — начинать, убывающая — завершать, "
        "полнолуние — не подписывать.</i>\n" + body,
        reply_markup=career_kb())


# ──────────────────────────── гороскоп по знаку ───────────────────────────────

@router.message(Command("horoscope"))
async def horoscope_cmd(message: Message, db):
    await _send_horoscope(message, db, message.from_user.id)


@router.callback_query(F.data == "horoscope")
async def horoscope_cb(cb: CallbackQuery, db):
    await cb.answer("Смотрю на небо... ✨")
    await _send_horoscope(cb.message, db, cb.from_user.id)


async def _send_horoscope(target: Message, db, tg_id: int) -> None:
    """Общий гороскоп по знаку — бесплатная витрина персонального прогноза."""
    user = await users.get(db, tg_id)
    if not user or not user["birth_date"]:
        await target.answer("Сначала познакомимся — нажми /start 🌙")
        return
    chart = users.chart_of(user)
    sign = (chart.get("sun") or {}).get("sign")
    if not sign:
        from ..core.astro import sun_sign
        sign = sun_sign(date.fromisoformat(user["birth_date"]))[0]

    text = await horoscopes.get_or_build(db, sign)
    await analytics.track(db, "horoscope_view", tg_id, props={"sign": sign})
    await _send_long(
        target,
        f"{text}\n\n"
        f"<i>Это общий гороскоп для знака {sign}. Твой личный прогноз — "
        f"по натальной карте, он в «🌅 Прогноз дня».</i>",
        reply_markup=await _menu(db, tg_id))
