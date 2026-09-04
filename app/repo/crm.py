"""CRM: заметки, теги и карточка клиентки 360° для поддержки."""
from __future__ import annotations

from ..data.session import transaction, utcnow
from . import analytics, billing, dialog, growth, readings, users

# ─────────────────────────────── заметки ──────────────────────────────────────


async def add_note(db, tg_id: int, text: str, author_id: int | None = None) -> int:
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO user_notes(tg_id, author_id, text, created_at) "
            "VALUES(:tg_id, :author_id, :text, :created_at) RETURNING id",
            {"tg_id": tg_id, "author_id": author_id,
             "text": text, "created_at": utcnow()})
        row = await cur.fetchone()
        return row["id"]


async def list_notes(db, tg_id: int, limit: int = 50) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM user_notes WHERE tg_id=:tg_id ORDER BY id DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit})
    return [dict(r) for r in await cur.fetchall()]


async def delete_note(db, note_id: int) -> None:
    async with transaction(db):
        await db.execute(
            "DELETE FROM user_notes WHERE id=:id", {"id": note_id})


# ──────────────────────────────── теги ────────────────────────────────────────

async def add_tag(db, tg_id: int, tag: str, author_id: int | None = None) -> None:
    tag = (tag or "").strip().lower()[:40]
    if not tag:
        return
    async with transaction(db):
        await db.execute(
            "INSERT INTO user_tags(tg_id, tag, author_id, created_at) "
            "VALUES(:tg_id, :tag, :author_id, :created_at) "
            "ON CONFLICT (tg_id, tag) DO NOTHING",
            {"tg_id": tg_id, "tag": tag, "author_id": author_id,
             "created_at": utcnow()})


async def remove_tag(db, tg_id: int, tag: str) -> None:
    async with transaction(db):
        await db.execute(
            "DELETE FROM user_tags WHERE tg_id=:tg_id AND tag=:tag",
            {"tg_id": tg_id, "tag": (tag or "").strip().lower()})


async def tags_of(db, tg_id: int) -> list[str]:
    cur = await db.execute(
        "SELECT tag FROM user_tags WHERE tg_id=:tg_id ORDER BY tag",
        {"tg_id": tg_id})
    return [r["tag"] for r in await cur.fetchall()]


async def all_tags(db) -> list[dict]:
    cur = await db.execute(
        "SELECT tag, COUNT(*) n FROM user_tags GROUP BY tag ORDER BY n DESC")
    return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────── карточка 360° ────────────────────────────────────

async def user_card(db, tg_id: int) -> dict | None:
    """Всё о клиентке в одном ответе — экран поддержки открывается одним запросом."""
    user = await users.get(db, tg_id)
    if not user:
        return None
    plan = await billing.get_plan(db, user["sub_level"] or "free")
    return {
        "user": dict(user),
        "plan": plan,
        "sub_active": users.sub_active(user),
        "sub_days_left": users.sub_days_left(user),
        "chart": users.chart_of(user),
        "tags": await tags_of(db, tg_id),
        "notes": await list_notes(db, tg_id, limit=20),
        "memories": await dialog.memories_full(db, tg_id, limit=40),
        "threads": await dialog.list_threads(db, tg_id),
        "diary_streak": await dialog.diary_streak(db, tg_id),
        "questions_today": await dialog.questions_used_today(db, user),
        "readings": await readings.recent_readings(db, tg_id, limit=10),
        "reports": await readings.list_reports(db, tg_id),
        "partners": await readings.list_partners(db, tg_id),
        "orders": await billing.user_orders(db, tg_id, limit=20),
        "entitlements": await billing.list_entitlements(db, tg_id),
        "crystals_history": await billing.crystal_history(db, tg_id, limit=20),
        "referrals": await growth.referral_stats(db, tg_id),
        "referrer": await growth.referrer_of(db, tg_id),
        "events": await analytics.user_events(db, tg_id, limit=60),
    }
