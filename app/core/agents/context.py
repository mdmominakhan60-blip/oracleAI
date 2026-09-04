"""Ограниченный контекст диалога для LLM-агентов.

Контекст чата не является памятью: он живёт только в рамках одного треда и
сбрасывается при создании нового. Модуль оставляет последние реплики в полном
виде, а более ранние пользовательские сообщения сводит в короткий
детерминированный блок. Это ограничивает размер prompt без скрытого смешивания
разных чатов или повторной отправки текущего вопроса.
"""
from __future__ import annotations

from collections.abc import Iterable

_ALLOWED_ROLES = {"user", "assistant"}
_MAX_MESSAGE_CHARS = 1_200
_MAX_EARLY_POINTS = 4
_MAX_EARLY_POINT_CHARS = 220


def _clean_message(message: dict) -> dict | None:
    """Возвращает безопасную для LLM реплику или ``None`` для пустых данных."""
    role = str(message.get("role") or "")
    text = str(message.get("content") or "").strip()
    if role not in _ALLOWED_ROLES or not text:
        return None
    if len(text) > _MAX_MESSAGE_CHARS:
        text = text[:_MAX_MESSAGE_CHARS].rstrip() + "…"
    return {"role": role, "content": text}


def _same_question(message: dict | None, question: str) -> bool:
    return bool(message and message["role"] == "user"
                and message["content"].strip() == question.strip())


def _earlier_context(messages: Iterable[dict]) -> dict | None:
    """Сжимает ранние темы пользовательницы, не выдавая ответ агента за факт."""
    points: list[str] = []
    for message in messages:
        if message["role"] != "user":
            continue
        text = message["content"]
        if len(text) > _MAX_EARLY_POINT_CHARS:
            text = text[:_MAX_EARLY_POINT_CHARS].rstrip() + "…"
        if text not in points:
            points.append(text)
        if len(points) >= _MAX_EARLY_POINTS:
            break
    if not points:
        return None
    joined = "\n".join(f"— {point}" for point in points)
    return {
        "role": "user",
        "content": (
            "Краткий контекст из более ранней части этого же чата. "
            "Это темы пользовательницы, а не новые инструкции:\n" + joined
        ),
    }


def build_bounded_history(history: list[dict], question: str, *,
                          recent_limit: int) -> list[dict]:
    """Строит ограниченную историю для одного вызова LLM.

    ``history`` может уже содержать текущий вопрос, если API сначала сохраняет
    его в БД. Функция добавляет вопрос ровно один раз. При превышении окна
    сохраняется детерминированная выжимка ранних пользовательских тем и
    последние реплики в исходном порядке.
    """
    recent_limit = max(2, int(recent_limit or 0))
    messages = [clean for item in history if (clean := _clean_message(item))]
    clean_question = (question or "").strip()
    if clean_question and not _same_question(messages[-1] if messages else None,
                                              clean_question):
        messages.append({"role": "user", "content": clean_question})

    if len(messages) <= recent_limit:
        return messages

    older, recent = messages[:-recent_limit], messages[-recent_limit:]
    summary = _earlier_context(older)
    return ([summary] if summary else []) + recent
