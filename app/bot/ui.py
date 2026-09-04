"""Telegram-native presentation primitives shared by Bot handlers."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from enum import StrEnum

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message


class BotStage(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    USING_TOOL = "using_tool"
    CALCULATING = "calculating"
    GENERATING_REPORT = "generating_report"
    WAITING_FOR_PAYMENT = "waiting_for_payment"
    SUCCESS = "success"
    RECOVERABLE_ERROR = "recoverable_error"


STATUS_COPY = {
    "ru": {
        BotStage.THINKING: "✨ Настраиваюсь на твой вопрос…",
        BotStage.USING_TOOL: "🌌 Сверяю сохранённые данные…",
        BotStage.CALCULATING: "🌌 Проверяю расчёт…",
        BotStage.GENERATING_REPORT: "📜 Собираю твой разбор…",
        BotStage.WAITING_FOR_PAYMENT: "💎 Жду подтверждение оплаты…",
        BotStage.SUCCESS: "✨ Готово",
        BotStage.RECOVERABLE_ERROR: "Не получилось завершить этот шаг.",
    },
    "en": {
        BotStage.THINKING: "✨ Tuning in to your question…",
        BotStage.USING_TOOL: "🌌 Checking your saved data…",
        BotStage.CALCULATING: "🌌 Running the calculation…",
        BotStage.GENERATING_REPORT: "📜 Building your reading…",
        BotStage.WAITING_FOR_PAYMENT: "💎 Waiting for payment confirmation…",
        BotStage.SUCCESS: "✨ Done",
        BotStage.RECOVERABLE_ERROR: "I could not finish this step.",
    },
}


def lang(user_or_lang) -> str:
    value = user_or_lang if isinstance(user_or_lang, str) else (user_or_lang["lang"] if user_or_lang else "ru")
    return "en" if str(value or "").lower().startswith("en") else "ru"


def copy(user_or_lang, ru: str, en: str) -> str:
    return en if lang(user_or_lang) == "en" else ru


def status_text(user_or_lang, stage: BotStage, detail: str | None = None) -> str:
    value = STATUS_COPY[lang(user_or_lang)].get(stage, STATUS_COPY[lang(user_or_lang)][BotStage.THINKING])
    return f"{value}\n\n<i>{html.escape(detail)}</i>" if detail else value


@dataclass
class Status:
    message: Message
    user_or_lang: object
    stage: BotStage = BotStage.IDLE

    async def set(self, stage: BotStage, detail: str | None = None) -> Message:
        self.stage = stage
        try:
            await self.message.edit_text(status_text(self.user_or_lang, stage, detail))
        except Exception:
            # Telegram rejects edits after media replacement/deletion/timeout.
            try:
                await self.message.answer(status_text(self.user_or_lang, stage, detail))
            except Exception:
                pass
        return self.message


async def begin_status(message: Message, user_or_lang, stage: BotStage = BotStage.THINKING,
                       detail: str | None = None) -> Status:
    status_message = await message.answer(status_text(user_or_lang, stage, detail))
    return Status(status_message, user_or_lang, stage)


def semantic_chunks(text: str, limit: int = 3900) -> list[str]:
    """Split at headings, paragraphs, list boundaries, then words."""
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    blocks = re.split(r"\n{2,}", text)
    result: list[str] = []
    current = ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            result.append(current.strip())
            current = ""
        if len(block) <= limit:
            current = block
            continue
        words = block.split()
        chunk = ""
        for word in words:
            candidate = f"{chunk} {word}".strip()
            if len(candidate) > limit and chunk:
                result.append(chunk)
                chunk = word
            else:
                chunk = candidate
        if chunk:
            current = chunk
    if current:
        result.append(current.strip())
    return result


def action_keyboard(*, lang_value: str = "ru", followup: bool = True,
                    deep: bool = False, menu: bool = True) -> InlineKeyboardMarkup:
    """Кнопки после разбора. Share убрали: без trackable-механики «поделиться»
    вело в никуда (callback `share:last` не имел обработчика)."""
    en = lang(lang_value) == "en"
    rows = []
    if followup:
        rows.append([InlineKeyboardButton(text="Ask a follow-up" if en else "Задать уточняющий вопрос", callback_data="ask")])
    if deep:
        rows.append([InlineKeyboardButton(text="See a deeper reading" if en else "Посмотреть глубже", callback_data="shop_reports")])
    if menu:
        rows.append([InlineKeyboardButton(text="Menu" if en else "Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
