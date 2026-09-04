"""Единый перевод прикладных отказов в HTTP-ошибки."""
from __future__ import annotations

from fastapi import HTTPException


# Аудит CONT-001: отказы 402/429 — пользовательский текст, поэтому он обязан
# быть на языке клиентки, а не только на русском.
DENY_TEXT = {
    "ru": {
        "sub_over": "Доступ завершён 🌙 Продли подписку — я сохранила всё о тебе.",
        "limit_reached": "Вопросы исчерпаны. Вернись на рассвете 🌘 "
                         "или открой поле силой Кристаллов ✦",
        "_default": "Сейчас нельзя",
    },
    "en": {
        "sub_over": "Your access has ended 🌙 Renew the subscription — I kept everything about you.",
        "limit_reached": "You are out of questions. Come back at dawn 🌘 "
                         "or open the field with Crystals ✦",
        "_default": "Not right now",
    },
}


def access_denied(verdict, lang: str = "ru") -> HTTPException:
    """Преобразует результат лимитов в стабильный HTTP-контракт.

    Сервисный слой возвращает verdict, а HTTP-слой единолично отвечает за
    статус-код и пользовательский detail. Это не даёт сервисам зависеть от
    FastAPI и не заставляет роутеры импортировать друг друга.
    """
    reason = getattr(verdict, "reason", None)
    status = 402 if reason == "sub_over" else 429
    texts = DENY_TEXT.get(lang) or DENY_TEXT["ru"]
    return HTTPException(status_code=status,
                         detail=texts.get(reason, texts["_default"]))
