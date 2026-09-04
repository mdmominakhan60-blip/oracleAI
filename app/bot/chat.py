"""Диалог с агентами: вопросы, выбор собеседника, голосовые, экстренный доступ.

Вся логика лимитов и списаний — в `services.chat`, здесь только Telegram:
показать «печатает», разбить длинный ответ, предложить выход при отказе.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..core import agents
from ..repo import content as content_repo, users
from ..services import billing as billing_svc, analytics
from ..services import access, chat as chat_svc, limits
from .formatting import tg_esc, tg_rich
from .keyboards import agents_kb, ask_starters_kb, back_menu, limit_kb, main_menu
from .ui import BotStage, action_keyboard, begin_status, semantic_chunks

log = logging.getLogger("oracle.bot.chat")
router = Router()

# Telegram не принимает сообщения длиннее 4096 символов. Режем по абзацам,
# иначе длинный разбор пары просто не доходил до клиентки.
TG_LIMIT = 3900

TRIAL_OVER_FALLBACK = (
    "💫 Наша связь истончилась — твой доступ завершился.\n"
    "Я сохранила всё, что знаю о тебе. Продли связь со Вселенной 🎟"
)
TRIAL_OVER_FALLBACK_EN = (
    "💫 Our connection has grown thin — your access has ended.\n"
    "I have kept everything you shared. Renew your connection with the Universe 🎟"
)
LIMIT_REACHED_FALLBACK_EN = (
    "🌙 <i>The stars are resting and the threads of possibility have grown quiet...</i>\n\n"
    "You have reached today's question limit. Save your next question for dawn — "
    "or open the space with Crystals."
)


class Ask(StatesGroup):
    """Состояние «жду вопрос»: помнит, какому агенту адресован следующий текст."""

    waiting = State()


def split_message(text: str, limit: int = TG_LIMIT) -> list[str]:
    """Делит длинный текст по абзацам, не разрывая слова."""
    if len(text) <= limit:
        return [text]
    parts, chunk = [], ""
    for paragraph in text.split("\n\n"):
        if len(chunk) + len(paragraph) + 2 > limit and chunk:
            parts.append(chunk.strip())
            chunk = ""
        if len(paragraph) > limit:            # один гигантский абзац — режем жёстко
            for i in range(0, len(paragraph), limit):
                parts.append(paragraph[i:i + limit])
            continue
        chunk += paragraph + "\n\n"
    if chunk.strip():
        parts.append(chunk.strip())
    return parts


async def _menu(db, tg_id: int):
    user = await users.get(db, tg_id)
    return main_menu(is_admin=await access.is_admin(db, tg_id),
                     lang="en" if user and user["lang"] == "en" else "ru")


async def _send_long(message: Message, text: str, reply_markup=None) -> None:
    chunks = semantic_chunks(tg_rich(text))
    for i, chunk in enumerate(chunks):
        await message.answer(chunk,
                             reply_markup=reply_markup if i == len(chunks) - 1 else None)


async def _deny(message: Message, db, verdict) -> None:
    """Отказ — это тоже сценарий продажи: объясняем и даём выходы."""
    user = await users.get(db, message.chat.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    if verdict.reason == "sub_over":
        text = await content_repo.get_text(
            db, "copy", "sub_over",
            TRIAL_OVER_FALLBACK_EN if lang == "en" else TRIAL_OVER_FALLBACK,
            lang=lang)
        await message.answer(text, reply_markup=limit_kb(0, has_crystals=False, lang=lang))
        return
    allowance = verdict.allowance
    cost = allowance.emergency_cost if allowance else 20
    has = bool(allowance and allowance.crystals >= cost)
    text = await content_repo.get_text(
        db, "copy", "limit_reached",
        (LIMIT_REACHED_FALLBACK_EN if lang == "en" else
         "🌙 <i>Звёзды утомлены...</i>\n\nВопросы на сегодня исчерпаны, друг."),
        lang=lang)
    await message.answer(text, reply_markup=limit_kb(cost, has_crystals=has, lang=lang))


# ─────────────────────────── выбор собеседника ────────────────────────────────

@router.callback_query(F.data == "ask")
async def ask_menu(cb: CallbackQuery, state: FSMContext, db):
    """Кнопка «Спросить»: сразу к Оракулу, но с возможностью сменить агента."""
    user = await users.get(db, cb.from_user.id)
    allowance = await limits.allowance(db, user, check_followup=False)
    await state.set_state(Ask.waiting)
    await state.update_data(agent=agents.DEFAULT_AGENT)
    lang = "en" if user and user["lang"] == "en" else "ru"
    unit = "today" if lang == "en" and allowance.period == "day" else "this week" if lang == "en" else "сегодня" if allowance.period == "day" else "на этой неделе"
    left = (f"{allowance.left} left {unit}" if lang == "en" and allowance.limit else f"осталось {allowance.left} {unit}" if allowance.limit else "Your included questions are used" if lang == "en" else "вопросы по доступу закончились")
    await cb.message.answer(
        (f"✨ <b>I’m listening.</b> Ask me anything about love, work, or your next step.\n\n<i>{left}. I’ll choose the best guide automatically.</i>"
         if lang == "en" else
         f"✨ <b>Я слушаю.</b> Спроси о любви, работе или следующем шаге.\n\n<i>{left}. Я сама выберу нужного проводника.</i>"),
        reply_markup=ask_starters_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "agents")
async def agents_menu(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    await cb.message.answer(
        "Выбери проводника — или вернись к Оракулу." if not user or user["lang"] != "en" else "Choose a guide — or return to Oracle.",
        reply_markup=agents_kb(await agents.agent_list(db, user)))
    await cb.answer()


@router.callback_query(F.data.startswith("starter:"))
async def starter_question(cb: CallbackQuery, state: FSMContext, db):
    user = await users.get(db, cb.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    prompts = {
        "today": "What should I focus on today?" if lang == "en" else "На чём мне сфокусироваться сегодня?",
        "love": "What is happening in my relationship?" if lang == "en" else "Что происходит в моих отношениях?",
        "decision": "Help me make a decision." if lang == "en" else "Помоги мне принять решение.",
    }
    key = cb.data.split(":", 1)[1]
    text = prompts.get(key)
    if not text or not user:
        await cb.answer("Choose a prompt", show_alert=True)
        return
    await state.set_state(Ask.waiting)
    await state.update_data(agent=agents.DEFAULT_AGENT)
    await cb.answer()
    await _answer(cb.message, db, user, text, agents.DEFAULT_AGENT)


@router.callback_query(F.data.startswith("agent:"))
async def pick_agent(cb: CallbackQuery, state: FSMContext, db):
    code = cb.data.split(":", 1)[1]
    if code not in agents.codes():
        await cb.answer("Такого собеседника нет")
        return
    user = await users.get(db, cb.from_user.id)
    spec = agents.get(code)
    await state.set_state(Ask.waiting)
    await state.update_data(agent=code)
    hints = "\n".join(f"• {s}" for s in spec.suggestions)
    await cb.message.answer(
        f"{spec.emoji} <b>{spec.display_name(user)}</b> — {spec.title.lower()}\n"
        f"<i>{spec.tagline}</i>\n\n{spec.greeting}\n\n{hints}",
        reply_markup=back_menu())
    await cb.answer()


# ─────────────────────────────── вопрос ───────────────────────────────────────

async def _answer(message: Message, db, user, text: str, agent: str) -> None:
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    lang = "en" if user and user["lang"] == "en" else "ru"
    status = await begin_status(message, user, BotStage.THINKING)
    await status.set(BotStage.USING_TOOL, "Oracle is choosing the right evidence" if lang == "en" else "Оракул выбирает нужные данные")
    try:
        result = await chat_svc.ask(db, user, text, agent=agent, surface="bot")
    except chat_svc.ChatDenied as e:
        await status.set(BotStage.RECOVERABLE_ERROR, "Access boundary" if lang == "en" else "Граница доступа")
        await _deny(message, db, e.verdict)
        return
    except ValueError as e:
        if isinstance(e, chat_svc.QuestionTooLong):
            # API-003: вопрос длиннее 1000 символов — говорим об этом явно,
            # а не обрезаем молча.
            await status.set(BotStage.RECOVERABLE_ERROR,
                             "Question is too long" if lang == "en" else "Вопрос слишком длинный")
            await message.answer(
                "That question is longer than 1000 characters. Shorten it a little and send it again — I will keep the thread. 🌙" if lang == "en"
                else "Вопрос получился длиннее 1000 знаков. Сократи его чуть-чуть и пришли снова — я сохраню нить разговора. 🌙",
                reply_markup=action_keyboard(lang_value=lang, followup=False))
            return
        await status.set(BotStage.RECOVERABLE_ERROR, "Send a question in words" if lang == "en" else "Напиши вопрос словами")
        await message.answer("Please send a question in words." if lang == "en" else "Напиши вопрос словами, милая 🌙", reply_markup=action_keyboard(lang_value=lang, followup=False))
        return
    except Exception as e:  # noqa: BLE001
        log.exception("вопрос не обработан: %s", e)
        await status.set(BotStage.RECOVERABLE_ERROR, "Try again or return to the menu" if lang == "en" else "Попробуй ещё раз или вернись в меню")
        await message.answer("I could not complete this reading. Try again in a moment." if lang == "en" else "Я не смогла завершить разбор. Попробуй ещё раз через минуту.", reply_markup=action_keyboard(lang_value=lang, followup=True))
        return
    await status.set(BotStage.SUCCESS)
    await _send_long(message, result["answer"], reply_markup=action_keyboard(lang_value=lang, followup=True))


@router.message(F.voice)
async def voice_msg(message: Message, state: FSMContext, db):
    """Голосовое = вопрос: расшифровываем Whisper'ом (нужен ключ OpenAI)."""
    from io import BytesIO

    from ..core import llm

    _vuser = await users.get(db, message.from_user.id)
    _ven = bool(_vuser and _vuser["lang"] == "en")
    if not await content_repo.is_on(db, "voice_questions", message.from_user.id,
                               default=True):
        await message.answer("Voice questions are off for now — please type 🌙" if _ven
                             else "Голосовые пока отключены — напиши текстом 🌙")
        return
    if message.voice.duration > 120:
        # BOT-014: отказ по длине — на языке интерфейса.
        await message.answer("The stars cannot hold a message that long... "
                             "please keep it under 2 minutes 🙏" if _ven else
                             "Такое длинное послание звёзды не удержат... "
                             "запиши покороче, до 2 минут 🙏")
        return
    buf = BytesIO()
    try:
        await message.bot.download(message.voice.file_id, destination=buf)
    except Exception as e:  # noqa: BLE001
        log.warning("голосовое не скачалось: %s", e)
        await message.answer("I could not hear that... please type your question 🌙" if _ven
                             else "Не расслышала... напиши словами, милая 🌙")
        return
    text = await llm.transcribe(
        buf.getvalue(), db=db, tg_id=message.from_user.id, surface="bot")
    if not text:
        await message.answer("I cannot hear voices yet — please type your question 🌙" if _ven
                             else "Я пока не слышу голоса — напиши свой вопрос текстом 🌙")
        return
    heard = "I heard" if _ven else "Я услышала"
    await message.answer(f"🎙 <i>{heard}: «{tg_esc(text[:200])}»</i>")
    await _handle_text(message, state, db, text)


@router.message(F.text & ~F.text.startswith("/"))
async def any_text(message: Message, state: FSMContext, db):
    """Свободный текст = вопрос выбранному агенту."""
    await _handle_text(message, state, db, message.text)


@router.message(F.text & F.text.startswith("/"))
async def unknown_command(message: Message, state: FSMContext, db):
    """Неизвестная команда не должна утопать в тишине — показываем меню."""
    await state.clear()
    user = await users.get(db, message.from_user.id)
    if not user or not user["onboarded"]:
        await message.answer("Начнём знакомство — нажми /start 🌙")
        return
    await message.answer("У меня нет такой команды 🌙 Вот что я умею:",
                         reply_markup=await _menu(db, message.from_user.id))


async def _handle_text(message: Message, state: FSMContext, db, text: str) -> None:
    user = await users.get(db, message.from_user.id)
    if not user or not user["onboarded"]:
        await message.answer("Сначала познакомимся — нажми /start 🌙")
        return
    if user["status"] == "blocked":
        await message.answer("Доступ приостановлен. Напиши в поддержку 🌙")
        return
    await users.touch(db, user["tg_id"])

    data = await state.get_data()
    agent = data.get("agent") or agents.DEFAULT_AGENT
    await _answer(message, db, user, text, agent)


# ─────────────────────── экстренный доступ за Кристаллы ───────────────────────

@router.callback_query(F.data == "emergency")
async def emergency(cb: CallbackQuery, state: FSMContext, db):
    """Один вопрос вне лимита за Кристаллы.

    Списываем сразу и выдаём право на один вопрос: так покупка не «повисает»
    между списанием и вопросом, а если клиентка не спросит сегодня — право
    останется за ней на неделю.
    """
    user = await users.get(db, cb.from_user.id)
    _en = bool(user and user["lang"] == "en")
    cost = int(await content_repo.get_setting(db, "limits.emergency_cost", 20) or 20)
    if (user["crystals"] or 0) < cost:
        # BOT-012: покупка аварийного вопроса — на языке интерфейса.
        await cb.answer("Not enough Crystals ✦" if _en else "Не хватает Кристаллов ✦",
                        show_alert=True)
        await cb.message.answer("💎 Top up your Crystals:" if _en else
                                "💎 Пополни запас Кристаллов:",
                                reply_markup=limit_kb(cost, has_crystals=False))
        return
    if not await billing_svc.spend_crystals(db, user["tg_id"], cost, "emergency_question"):
        await cb.answer("Not enough Crystals ✦" if _en else "Не хватает Кристаллов ✦",
                        show_alert=True)
        return
    await billing_svc.grant_entitlement(db, user["tg_id"], "question", "*", qty=1,
                                    valid_days=7, source="crystals")
    await analytics.track(db, "emergency_unlock", user["tg_id"],
                          props={"cost": cost})
    await state.set_state(Ask.waiting)
    await state.update_data(agent=agents.DEFAULT_AGENT)
    await cb.message.answer(
        f"🔮 <i>I parted the veil with ✦{cost}...</i>\n"
        f"Ask your question — right now." if _en else
        f"🔮 <i>Я раздвинула завесу силой ✦{cost}...</i>\n"
        f"Задай свой вопрос — прямо сейчас.")
    await cb.answer()


@router.callback_query(F.data == "menu")
async def menu(cb: CallbackQuery, state: FSMContext, db):
    await state.clear()
    user = await users.get(db, cb.from_user.id)
    await cb.message.answer(f"Я здесь, {tg_esc(user['name'])} 🌙",
                            reply_markup=await _menu(db, cb.from_user.id))
    await cb.answer()
