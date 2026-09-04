"""Контент и конфигурация, управляемые из админки: настройки, тексты, флаги.

Всё, что здесь лежит, правится без деплоя — это требование ТЗ («все тексты и
промпты в конфигах, не в коде»). Код всегда имеет значение по умолчанию, а БД
его перекрывает: пустая база и упавший запрос не должны ломать продукт.
"""
from __future__ import annotations

import json
import zlib

from ..data.session import transaction, utcnow

# ─────────────────────────────── настройки ────────────────────────────────────


async def get_setting(db, key: str, default=None):
    cur = await db.execute("SELECT value_json FROM settings WHERE key=:key", {"key": key})
    row = await cur.fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except (TypeError, ValueError):
        return default


async def set_setting(db, key: str, value, admin_id: int | None = None) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO settings(key, value_json, updated_at, updated_by) "
            "VALUES(:key, :value_json, :updated_at, :updated_by) ON CONFLICT(key) DO UPDATE SET "
            "value_json=excluded.value_json, updated_at=excluded.updated_at, "
            "updated_by=excluded.updated_by",
            {"key": key, "value_json": json.dumps(value, ensure_ascii=False),
             "updated_at": utcnow(), "updated_by": admin_id})


async def all_settings(db) -> dict:
    cur = await db.execute("SELECT key, value_json FROM settings ORDER BY key")
    out = {}
    for row in await cur.fetchall():
        try:
            out[row["key"]] = json.loads(row["value_json"])
        except (TypeError, ValueError):
            out[row["key"]] = None
    return out


# ─────────────────────────── тексты и промпты ─────────────────────────────────

# Англоязычные defaults для текстов, которые первоначально были заведены только
# по-русски. Администратор может переопределить любой из них через meta_json:
# `title_en` и `body_en`; это не требует дублей строк и не ломает UNIQUE(kind, code).
DEFAULT_EN_CONTENT: dict[tuple[str, str], dict[str, str]] = {
    ("copy", "welcome"): {
        "title": "Onboarding welcome",
        "body": ("🌌 <b>The stars have been waiting for you.</b>\n\n"
                 "I am your personal Oracle: astrology, Tarot, and Destiny Matrix, "
                 "made for <i>you</i>.\n\n"
                 "To create your birth chart, I need only a few details. "
                 "What should I call you? ✨\n\n"
                 "By continuing, you accept the service rules and consent to the "
                 "processing of personal data. The full text is available in /help."),
    },
    ("copy", "limit_reached"): {
        "title": "Question limit reached",
        "body": ("🌙 <i>The stars are resting and the threads of possibility have "
                 "grown quiet...</i>\n\nYou've reached today's question limit. "
                 "Save your next question for dawn — or open the space with Crystals:"),
    },
    ("copy", "sub_over"): {
        "title": "Subscription ended",
        "body": ("💫 Our connection has grown thin — your access has ended.\n"
                 "I have kept everything you shared. Renew your connection with "
                 "the Universe 🎟"),
    },
    ("copy", "expiry_soon"): {
        "title": "Two days before subscription ends",
        "body": ("🌙 {name}, our connection is growing thin — fewer than two days remain...\n\n"
                 "I remember the words you shared, both the tender ones and the dreams. "
                 "Stay with me and I will keep them safe and meet you with a morning "
                 "forecast, as always. ✨"),
    },
    ("copy", "winback"): {
        "title": "Return after subscription ends",
        "body": ("💫 The stars have grown quiet, but I have not left — I am simply "
                 "waiting beyond the veil.\nYour memories are safe with me: return, "
                 "and we will continue where we paused."),
    },
    ("copy", "free_forecast_cta"): {
        "title": "Free forecast CTA",
        "body": "\n\n🔮 <b>Oracle</b> — your free daily forecast. Open it in Telegram: {url}",
    },
    ("copy", "free_lunar_alert"): {
        "title": "Free lunar alert",
        "body": "🌕 {moon} — a special night for you.\n\nOpen Oracle for a gentle lunar guide: {url}",
    },
    ("faq", "what_is_it"): {
        "title": "What is this service?",
        "body": ("Oracle is a personal AI astrologer. It creates your birth chart "
                 "from ephemerides, draws Tarot with an honest random selection, and "
                 "remembers what you choose to share. Code performs calculations; a "
                 "language model explains them."),
    },
    ("faq", "is_it_real"): {
        "title": "Are the calculations real?",
        "body": ("Yes. Birth charts use Swiss Ephemeris, the same data used by "
                 "professional astrologers, and Tarot cards are chosen with a "
                 "cryptographic random-number generator. The model receives completed "
                 "calculations and explains them rather than inventing them."),
    },
    ("faq", "privacy"): {
        "title": "What happens to my data?",
        "body": ("Your birth date and city are used only to calculate your chart. "
                 "Data is stored on our server and is not shared with third parties. "
                 "You may ask support to delete everything; your account will be anonymized."),
    },
}


def _lang(lang: str | None) -> str:
    return "en" if (lang or "").lower().startswith("en") else "ru"


def localized_item(item: dict, lang: str | None) -> dict:
    """Возвращает административную запись с выбранными title/body без мутации исходной."""
    result = dict(item)
    if _lang(lang) != "en":
        return result
    meta = content_meta(item)
    fallback = DEFAULT_EN_CONTENT.get((item.get("kind", ""), item.get("code", "")), {})
    result["title"] = meta.get("title_en") or fallback.get("title") or result.get("title")
    result["body"] = meta.get("body_en") or fallback.get("body") or result.get("body")
    return result


async def get_content(db, kind: str, code: str) -> dict | None:
    cur = await db.execute(
        "SELECT * FROM content_items WHERE kind=:kind AND code=:code AND is_active=1",
        {"kind": kind, "code": code})
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_text(db, kind: str, code: str, default: str = "", *,
                   lang: str | None = None) -> str:
    """Берёт текст на языке профиля с English fallback для legacy seed-контента."""
    item = await get_content(db, kind, code)
    if not item:
        return default
    localized = localized_item(item, lang)
    # Для EN не возвращаем случайно русский legacy body: если у ключа нет
    # перевода, используем явно заданный fallback вызывающего кода.
    if _lang(lang) == "en" and (kind, code) not in DEFAULT_EN_CONTENT:
        meta = content_meta(item)
        return meta.get("body_en") or default
    return localized.get("body") or default


async def list_content(db, kind: str | None = None, *,
                       active_only: bool = False) -> list[dict]:
    sql = ["SELECT * FROM content_items WHERE 1=1"]
    params: dict = {}
    if kind:
        sql.append("AND kind=:kind")
        params["kind"] = kind
    if active_only:
        sql.append("AND is_active=1")
    sql.append("ORDER BY kind, sort, code")
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


async def upsert_content(db, kind: str, code: str, *, title: str | None = None,
                         body: str | None = None, meta: dict | None = None,
                         is_active: int | None = None, sort: int | None = None,
                         admin_id: int | None = None) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO content_items(kind, code, title, body, is_active, "
            "sort, created_at, updated_at) VALUES(:kind, :code, :title, :body, 1, 100, :created_at, :updated_at) "
            "ON CONFLICT (kind, code) DO NOTHING",
            {"kind": kind, "code": code, "title": title or code, "body": body or "",
             "created_at": utcnow(), "updated_at": utcnow()})
        fields: dict = {}
        if title is not None:
            fields["title"] = title
        if body is not None:
            fields["body"] = body
        if meta is not None:
            fields["meta_json"] = json.dumps(meta, ensure_ascii=False)
        if is_active is not None:
            fields["is_active"] = int(is_active)
        if sort is not None:
            fields["sort"] = sort
        if fields:
            keys = ", ".join(f"{k}=:{k}" for k in fields)
            # INVARIANT: keys only from allowlist above — never interpolate user input
            await db.execute(
                f"UPDATE content_items SET {keys}, updated_at=:updated_at, updated_by=:updated_by "
                f"WHERE kind=:kind AND code=:code",
                {**fields, "updated_at": utcnow(), "updated_by": admin_id,
                 "kind": kind, "code": code})


async def delete_content(db, kind: str, code: str) -> None:
    async with transaction(db):
        await db.execute("DELETE FROM content_items WHERE kind=:kind AND code=:code",
                         {"kind": kind, "code": code})


def content_meta(item: dict | None) -> dict:
    if not item:
        return {}
    try:
        return json.loads(item.get("meta_json") or "{}")
    except (TypeError, ValueError):
        return {}


# ─────────────────────────────── фиче-флаги ───────────────────────────────────

async def flag_row(db, code: str):
    cur = await db.execute("SELECT * FROM feature_flags WHERE code=:code", {"code": code})
    return await cur.fetchone()


async def is_on(db, code: str, tg_id: int | None = None, *,
                default: bool = False) -> bool:
    """Включена ли фича. При `rollout_pct < 100` — стабильный процент аудитории.

    Попадание в процент считается от хеша (код фичи + id), а не от случайного
    числа: иначе одна и та же клиентка при каждом запросе то видела бы фичу, то
    нет, и это выглядело бы как поломка.
    """
    row = await flag_row(db, code)
    if row is None:
        return default
    if not row["is_on"]:
        return False
    pct = row["rollout_pct"] if row["rollout_pct"] is not None else 100
    if pct >= 100 or tg_id is None:
        return True          # без id раскатку не посчитать — считаем включённой
    bucket = zlib.crc32(f"{code}:{tg_id}".encode()) % 100
    return bucket < pct


async def list_flags(db) -> list[dict]:
    cur = await db.execute("SELECT * FROM feature_flags ORDER BY code")
    return [dict(r) for r in await cur.fetchall()]


async def set_flag(db, code: str, *, is_on: bool | None = None,
                   rollout_pct: int | None = None, description: str | None = None,
                   admin_id: int | None = None) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO feature_flags(code, is_on, rollout_pct, updated_at) "
            "VALUES(:code, 0, 100, :updated_at) ON CONFLICT (code) DO NOTHING",
            {"code": code, "updated_at": utcnow()})
        fields: dict = {}
        if is_on is not None:
            fields["is_on"] = int(is_on)
        if rollout_pct is not None:
            fields["rollout_pct"] = max(0, min(100, int(rollout_pct)))
        if description is not None:
            fields["description"] = description
        if fields:
            keys = ", ".join(f"{k}=:{k}" for k in fields)
            # INVARIANT: keys only from allowlist above — never interpolate user input
            await db.execute(
                f"UPDATE feature_flags SET {keys}, updated_at=:updated_at, updated_by=:updated_by "
                f"WHERE code=:code",
                {**fields, "updated_at": utcnow(), "updated_by": admin_id, "code": code})
