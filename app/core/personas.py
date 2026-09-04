"""Образы Оракула — тон, который клиентка выбирает при знакомстве.

Персона влияет только на манеру речи главного агента; специализированные агенты
(Таролог, Астролог, Нумеролог, Хранитель) говорят своим голосом — см.
`core/agents/registry.py`.

Тексты образов правятся в админке (`content_items(kind='persona')`), константы
здесь — значение по умолчанию для пустой базы.
"""
from __future__ import annotations

import logging

log = logging.getLogger("oracle.personas")

PERSONAS: dict[str, dict] = {
    "friend": {
        "title": "Мудрая подруга",
        "emoji": "🌸",
        "sort": 10,
        "style": (
            "Ты — старшая мудрая подруга. Тёплая, поддерживающая, немного ироничная. "
            "Говоришь просто и по-сестрински, обнимаешь словами, но честна."
        ),
    },
    "witch": {
        "title": "Таинственная ведунья",
        "emoji": "🔮",
        "sort": 20,
        "style": (
            "Ты — таинственная ведунья. Говоришь образами: нити судьбы, зеркала, травы, "
            "луна. Загадочна, но добра. Каждый ответ — маленькое пророчество."
        ),
    },
    "mentor": {
        "title": "Духовный наставник",
        "emoji": "🕉",
        "sort": 30,
        "style": (
            "Ты — спокойный духовный наставник. Глубина, метафоры пути и энергии, "
            "мягкие практические шаги. Ведёшь к осознанности без осуждения."
        ),
    },
}

DEFAULT_PERSONA = "friend"


def persona(code: str | None) -> dict:
    return PERSONAS.get(code or "", PERSONAS[DEFAULT_PERSONA])


async def persona_style(db, user) -> str:
    """Образ клиентки: из админки, иначе встроенный."""
    code = user["persona"] or DEFAULT_PERSONA
    fallback = persona(code)["style"]
    if db is None:
        return fallback
    try:
        from ..repo import content as content_repo
        return await content_repo.get_text(db, "persona", code, fallback) or fallback
    except Exception as e:  # noqa: BLE001
        log.warning("образ %s из БД недоступен: %s", code, e)
        return fallback


async def persona_list(db) -> list[dict]:
    """Витрина образов для онбординга и профиля."""
    out = []
    for code, item in sorted(PERSONAS.items(), key=lambda kv: kv[1].get("sort", 100)):
        title, emoji = item["title"], item["emoji"]
        if db is not None:
            try:
                from ..repo import content as content_repo
                row = await content_repo.get_content(db, "persona", code)
                if row:
                    title = row.get("title") or title
                    emoji = content_repo.content_meta(row).get("emoji", emoji)
            except Exception:  # noqa: BLE001
                pass
        out.append({"code": code, "title": title, "emoji": emoji})
    return out
