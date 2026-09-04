"""Профиль: состояние доступа, память, рефералка, образ Оракула, разборы."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..core.personas import persona_list
from ..core import agent as agent_core
from ..repo import dialog, readings, users
from ..services import billing as billing_svc, analytics
from ..services import access, limits, referrals
from .chat import _send_long
from .ui import BotStage, begin_status
from .formatting import tg_esc
from .keyboards import (back_menu, history_kb, language_kb, main_menu, personas_kb,
                        profile_kb, report_kb, settings_kb, share_kb)

log = logging.getLogger("oracle.bot.profile")
router = Router()


async def _menu(db, tg_id: int):
    user = await users.get(db, tg_id)
    return main_menu(is_admin=await access.is_admin(db, tg_id),
                     lang="en" if user and user["lang"] == "en" else "ru")


@router.callback_query(F.data == "profile")
async def profile(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    allowance = await limits.allowance(db, user, check_followup=False)
    active = users.sub_active(user)
    streak = await dialog.diary_streak(db, cb.from_user.id)
    memories = await dialog.get_memories(db, cb.from_user.id, limit=5)
    ref = await referrals.stats(db, cb.from_user.id)
    entitlements = await billing_svc.list_entitlements(db, cb.from_user.id)

    sub_line = (f"{allowance.plan['title']} · осталось "
                f"{users.sub_days_left(user)} дн." if active else "доступ завершён")
    unit = "today" if allowance.period == "day" else "this week" if user["lang"] == "en" else "сегодня" if allowance.period == "day" else "на неделе"
    mem_block = ("\n".join(f"• {tg_esc(m)}" for m in memories) if memories
                 else "<i>I’m just getting to know you</i>" if user["lang"] == "en"
                 else "<i>я только начинаю узнавать тебя</i>")

    en = user["lang"] == "en"
    lines = ([
        f"👤 <b>{tg_esc(user['name'])}</b>",
        f"🔮 Your Oracle: {tg_esc(user['oracle_name'])}",
        f"💫 Access: {allowance.plan['title']} · {users.sub_days_left(user)} days left" if active else "💫 Access: ended",
        f"✦ Crystals: <b>{user['crystals']}</b>",
        f"💬 Questions {unit}: {allowance.left} of {allowance.limit}",
        f"📖 Journal streak: {streak} days {'🔥' if streak >= 3 else ''}",
    ] if en else [
        f"👤 <b>{tg_esc(user['name'])}</b>",
        f"🔮 Твой Оракул: {tg_esc(user['oracle_name'])}",
        f"💫 Доступ: {sub_line}",
        f"✦ Кристаллы: <b>{user['crystals']}</b>",
        f"💬 Вопросов {unit}: {allowance.left} из {allowance.limit}",
        f"📖 Стрик дневника: {streak} дн. {'🔥' if streak >= 3 else ''}",
    ])
    if ref["level1"]:
        lines.append((f"🌟 Invited people: {ref['level1']}" if en else f"🌟 Приглашено людей: {ref['level1']}")
                     + (f" · paying: {ref['paying']}" if en and ref["paying"] else f" · из них платят: {ref['paying']}" if ref["paying"] else ""))
    if entitlements:
        names = ({"spread": "readings", "report": "reports", "question": "questions"}
                 if en else {"spread": "расклады", "report": "разборы", "question": "вопросы"})
        opened = ", ".join(
            f"{names.get(e['kind'], e['kind'])} ×{e['qty_total'] - e['qty_used']}"
            for e in entitlements[:4])
        lines.append((f"🎁 Unlocked: {opened}" if en else f"🎁 Открыто: {opened}"))
    lines += (["", "<b>What I know about you:</b>", mem_block] if en else ["", "<b>Что я о тебе знаю:</b>", mem_block])

    await cb.message.answer("\n".join(lines),
                            reply_markup=profile_kb(
                                push_on=bool(user["morning_push"]),
                                sub_active=active, lang="en" if en else "ru"))
    await cb.answer()


@router.callback_query(F.data == "toggle_push")
async def toggle_push(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    new_value = 0 if user["morning_push"] else 1
    await users.update(db, cb.from_user.id, morning_push=new_value)
    await analytics.track(db, "toggle_push", cb.from_user.id,
                          props={"on": bool(new_value)})
    await cb.answer("Утренний прогноз включён 🌅" if new_value
                    else "Утренний прогноз выключен 🌙")
    await profile(cb, db)


@router.callback_query(F.data == "change_persona")
async def change_persona(cb: CallbackQuery, db):
    await cb.message.answer(
        "🔮 <b>Кем мне быть для тебя?</b>\n"
        "<i>Меняется только манера речи — память и карта останутся.</i>",
        reply_markup=personas_kb(await persona_list(db)))
    await cb.answer()


@router.callback_query(F.data == "invite")
async def invite(cb: CallbackQuery, db):
    me = await cb.bot.get_me()
    link = referrals.link_for(me.username, cb.from_user.id)
    stats = await referrals.stats(db, cb.from_user.id)

    lines = [
        "🌟 <b>Поделись встречей с Оракулом</b>",
        "",
        f"Твоя личная ссылка:\n<code>{link}</code>",
        "",
        f"За каждого приглашённого — по ✦{stats['bonus_per_invite']} каждому.",
        f"Когда приглашённый оформит доступ — тебе ещё ✦{stats['revenue_share']}. ✨",
    ]
    if stats["level1"]:
        lines += ["",
                  f"Уже пришло по твоей ссылке: <b>{stats['level1']}</b>"
                  + (f" · второй уровень: {stats['level2']}" if stats["level2"] else ""),
                  f"Из них оформили доступ: <b>{stats['paying']}</b>",
                  f"Начислено всего: ✦{stats['bonus_total']}"]

    await cb.message.answer(
        "\n".join(lines),
        reply_markup=share_kb(link, referrals.share_text(stats["bonus_per_invite"]),
                              label="💌 Поделиться ссылкой"))
    await cb.answer()


@router.callback_query(F.data == "my_reports")
async def my_reports(cb: CallbackQuery, db):
    ready = await readings.list_reports(db, cb.from_user.id)
    available = [e for e in await billing_svc.list_entitlements(db, cb.from_user.id)
                 if e["kind"] == "report"]
    if not ready and not available:
        await cb.answer()
        await cb.message.answer(
            "📜 Больших разборов пока нет.\n\n"
            "Разбор натальной карты, Матрицы, пары или соляр — это длинный текст, "
            "который остаётся у тебя навсегда. Взять можно в 💎 Лавке.",
            reply_markup=back_menu())
        return

    lines = ["📜 <b>Твои разборы</b>", ""]
    rows = []
    if available:
        lines.append("<i>Оплачено и готово к сборке прямо здесь:</i>")
        for item in available:
            left = item["qty_total"] - item["qty_used"]
            lines.append(f"• {item['code']} ×{left}")
            if left > 0:
                from aiogram.types import InlineKeyboardButton
                rows.append([InlineKeyboardButton(text=f"📜 Собрать: {item['code']}"[:60], callback_data=f"report_build:{item['code']}")])
        lines.append("")
    if ready:
        lines.append("<i>Готовые:</i>")
    keyboard = report_kb(ready)
    if rows:
        keyboard.inline_keyboard = rows + keyboard.inline_keyboard
    await cb.message.answer("\n".join(lines), reply_markup=keyboard)
    await cb.answer()


@router.callback_query(F.data.startswith("report:"))
async def show_report(cb: CallbackQuery, db):
    parts = cb.data.split(":")
    kind = parts[1]
    period = parts[2] if len(parts) > 2 and parts[2] else None
    row = await readings.get_report(db, cb.from_user.id, kind, period)
    if not row:
        await cb.answer("Разбор не найден", show_alert=True)
        return
    await cb.answer()
    await _send_long(cb.message, f"<b>{row['title']}</b>\n\n{row['body']}",
                     reply_markup=back_menu())


@router.callback_query(F.data == "admin_stats")
async def admin_stats_cb(cb: CallbackQuery, db):
    """Резерв, когда WEBAPP_URL не задан и веб-панель недоступна."""
    role = await access.role(db, cb.from_user.id)
    if not role:
        await cb.answer("Нет доступа")
        return
    o = await access.admin_overview(db)
    funnel = o['funnel']
    o = o['overview']
    lines = ["📊 <b>Оракул за 30 дней</b>", ""]
    for step in funnel:
        lines.append(f"{step['step']}: <b>{step['value']}</b> ({step['of_total']}%)")
    lines += ["",
              f"⭐ Stars: {o['stars_total']} всего · {o['stars_30d']} за месяц",
              f"💫 Живых подписок: {o['subs_active']}",
              f"✦ Кристаллов у клиенток: {o['crystals_outstanding']}",
              "",
              "<i>Полная панель открывается, когда задан WEBAPP_URL.</i>"]
    await cb.message.answer("\n".join(lines),
                            reply_markup=await _menu(db, cb.from_user.id))
    await cb.answer()


# ───────────────────── Telegram-native settings and research library ───────────

@router.callback_query(F.data == "settings")
async def settings_home(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    await cb.message.answer(
        "⚙️ <b>Настройки</b>\n\nЯзык, память, уведомления и приватность — в одном месте."
        if lang == "ru" else
        "⚙️ <b>Settings</b>\n\nLanguage, memory, notifications, and privacy in one place.",
        reply_markup=settings_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "settings:language")
async def settings_language(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    await cb.message.answer(
        "Выбери язык интерфейса."
        if not user or user["lang"] != "en" else
        "Choose your interface language.",
        reply_markup=language_kb())
    await cb.answer()


@router.callback_query(F.data == "settings:memory")
async def settings_memory(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    en = user and user["lang"] == "en"
    enabled = bool(user and user["memory_enabled"])
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("Pause memory" if enabled and en else "Поставить память на паузу" if enabled else "Enable memory" if en else "Включить память"), callback_data="settings:memory:toggle")],
        [InlineKeyboardButton(text=("View saved notes" if en else "Посмотреть сохранённое"), callback_data="settings:memory:view")],
        [InlineKeyboardButton(text=("← Settings" if en else "← Настройки"), callback_data="settings")],
    ])
    await cb.message.answer(
        ("🧠 <b>Memory is on.</b> I use only explicitly saved facts and you can pause or delete them."
         if enabled and en else
         "🧠 <b>Память включена.</b> Я использую только явно сохранённые факты — её можно поставить на паузу или очистить."
         if enabled else
         "🧠 <b>Память на паузе.</b> Я всё ещё вижу текущий диалог, но не сохраняю новые факты."
         if not en else
         "🧠 <b>Memory is paused.</b> I can use the current conversation but will not save new facts."),
        reply_markup=keyboard)
    await cb.answer()


@router.callback_query(F.data == "settings:memory:toggle")
async def settings_memory_toggle(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    value = 0 if bool(user["memory_enabled"]) else 1
    await users.update(db, cb.from_user.id, memory_enabled=value)
    await analytics.track(db, "memory_toggle", cb.from_user.id, props={"on": bool(value)}, surface="bot")
    await cb.answer("Memory updated" if user["lang"] == "en" else "Память обновлена")
    await settings_memory(cb, db)


@router.callback_query(F.data == "history")
async def history_home(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    reports = await readings.list_reports(db, cb.from_user.id)
    readings_count = await readings.count_readings(db, cb.from_user.id) if hasattr(readings, "count_readings") else 0
    threads = await dialog.list_threads(db, cb.from_user.id, limit=5)
    text = ((f"📖 <b>My research</b>\n\nSaved reports: <b>{len(reports)}</b> · Tarot readings: <b>{readings_count}</b>\n"
             f"Conversations: <b>{len(threads)}</b>\n\nChoose a shelf to continue.") if lang == "en" else
            (f"📖 <b>Мои исследования</b>\n\nСохранённых разборов: <b>{len(reports)}</b> · Раскладов Таро: <b>{readings_count}</b>\n"
             f"Разговоров: <b>{len(threads)}</b>\n\nВыбери раздел, чтобы продолжить."))
    await cb.message.answer(text, reply_markup=history_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "history:tarot")
async def history_tarot(cb: CallbackQuery, db):
    """Последние расклады — shelf, которую рисовали, но не открывали."""
    user = await users.get(db, cb.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    items = await readings.recent_readings(db, cb.from_user.id, limit=8)
    if not items:
        text = ("No Tarot readings yet — the deck is waiting." if lang == "en"
                else "Раскладов пока нет — колода ждёт.")
    else:
        title = "🎴 <b>Recent readings</b>" if lang == "en" else "🎴 <b>Последние расклады</b>"
        lines = []
        for r in items:
            q = (r["question"] or r["spread"] or "").strip()[:60]
            lines.append(f"• {tg_esc(q)} · {r['created_at'][:10]}")
        text = title + "\n\n" + "\n".join(lines)
    await cb.message.answer(text, reply_markup=history_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "history:chat")
async def history_chat(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    threads = await dialog.list_threads(db, cb.from_user.id, limit=10)
    if not threads:
        text = "No saved conversations yet." if lang == "en" else "Сохранённых разговоров пока нет."
    else:
        title = "💬 <b>Conversations</b>" if lang == "en" else "💬 <b>Разговоры</b>"
        text = title + "\n\n" + "\n".join(
            f"• {tg_esc(t['title'] or t['agent'])} · {t['msg_count']} messages"
            if lang == "en" else f"• {tg_esc(t['title'] or t['agent'])} · {t['msg_count']} сообщений"
            for t in threads)
    await cb.message.answer(text, reply_markup=history_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "privacy")
async def privacy_home(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    en = user and user["lang"] == "en"
    await cb.message.answer(
        "🔐 Здесь можно экспортировать или удалить данные. Для удаления используй /delete_me."
        if not en else
        "🔐 You can export or delete your data here. Use /delete_me to start deletion.",
        reply_markup=back_menu())
    await cb.answer()


@router.callback_query(F.data == "help")
async def help_callback(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    en = user and user["lang"] == "en"
    text = (
        "? <b>How Oracle works</b>\n\nAsk a question in your own words. I choose the right guide, use only the saved evidence available to your profile, and return a grounded reflection.\n\nYou can explore your chart, Tarot, Mira, Today, practices, and your research library directly here.\n\nFor data deletion use /delete_me."
        if en else
        "? <b>Как работает Оракул</b>\n\nСпроси своими словами. Я выберу нужного проводника, использую доступные факты твоего профиля и верну бережный разбор с понятным следующим шагом.\n\nЗдесь доступны карта, Таро, Мира, Сегодня, практики и библиотека исследований.\n\nДля удаления данных используй /delete_me."
    )
    await cb.message.answer(text, reply_markup=await _menu(db, cb.from_user.id))
    await cb.answer()


REPORT_KIND_BY_CODE = {
    "natal": "natal",
    "natal_deep": "natal",
    "matrix": "matrix",
    "matrix_deep": "matrix",
    "synastry": "synastry",
    "synastry_deep": "synastry",
    "annual_deep": "solar",
    "career": "career",
    "career_deep": "career",
}


@router.callback_query(F.data.startswith("report_build:"))
async def build_report_callback(cb: CallbackQuery, db):
    code = cb.data.split(":", 1)[1]
    kind = REPORT_KIND_BY_CODE.get(code)
    user = await users.get(db, cb.from_user.id)
    if not user or not kind:
        await cb.answer("Разбор больше недоступен" if not user or user["lang"] != "en" else "This report is no longer available", show_alert=True)
        return
    consumed = await billing_svc.consume_entitlement(db, user["tg_id"], "report", code)
    if not consumed:
        await cb.answer("Покупка уже использована или истекла" if user["lang"] != "en" else "This purchase is already used or expired", show_alert=True)
        return
    status = await begin_status(cb.message, user, BotStage.GENERATING_REPORT,
                                "Факты карты уже сохранены — теперь собираю текст." if user["lang"] != "en" else "Your chart facts are saved — now I’m building the reading.")
    try:
        result = await agent_core.build_report(db, user, kind)
    except Exception as exc:  # noqa: BLE001
        log.exception("bot report build failed: %s", exc)
        await billing_svc.grant_entitlement(db, user["tg_id"], "report", code,
                                        qty=1, valid_days=None, source="refund")
        await status.set(BotStage.RECOVERABLE_ERROR,
                         "Try again later; your purchase was returned." if user["lang"] == "en" else "Попробуй позже — покупка возвращена в доступ.")
        await cb.answer()
        return
    await status.set(BotStage.SUCCESS)
    await analytics.track(db, "report_delivered", user["tg_id"],
                          props={"kind": kind, "surface": "bot"}, surface="bot")
    await _send_long(cb.message, f"<b>{result['title']}</b>\n\n{result['body']}",
                     reply_markup=back_menu())
    await cb.answer()
