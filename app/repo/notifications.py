"""Owner-scoped user notification inbox built from server-owned facts."""
from __future__ import annotations

from datetime import datetime, timezone

from ..data.session import transaction, utcnow


def _day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def sync_daily_forecast(db, tg_id: int, *, lang: str = "ru", day: str | None = None) -> None:
    """Materialize an existing cached forecast as one deduplicated inbox item."""
    day = day or _day()
    cur = await db.execute(
        "SELECT text FROM forecasts WHERE tg_id=:tg_id AND day=:day "
        "AND lang=:lang LIMIT 1",
        {"tg_id": tg_id, "day": day, "lang": lang},
    )
    row = await cur.fetchone()
    if not row or not row["text"]:
        return
    titles = {"ru": "Прогноз дня", "en": "Daily forecast"}
    async with transaction(db):
        await db.execute(
            "INSERT INTO user_notifications "
            "(tg_id, kind, title, body, dedupe_key, created_at) "
            "VALUES(:tg_id, :kind, :title, :body, :dedupe_key, :created_at) "
            "ON CONFLICT (tg_id, dedupe_key) DO UPDATE SET body=excluded.body",
            {
                "tg_id": tg_id,
                "kind": "forecast",
                "title": titles.get(lang, titles["ru"]),
                "body": str(row["text"])[:4000],
                "dedupe_key": f"forecast:{day}:{lang}",
                "created_at": utcnow(),
            },
        )


async def list_for_user(db, tg_id: int, *, limit: int = 30) -> dict:
    limit = max(1, min(int(limit), 100))
    cur = await db.execute(
        "SELECT id, kind, title, body, read_at, created_at FROM user_notifications "
        "WHERE tg_id=:tg_id ORDER BY created_at DESC, id DESC LIMIT :limit",
        {"tg_id": tg_id, "limit": limit},
    )
    items = [dict(row) for row in await cur.fetchall()]
    cur = await db.execute(
        "SELECT COUNT(*) AS n FROM user_notifications "
        "WHERE tg_id=:tg_id AND read_at IS NULL",
        {"tg_id": tg_id},
    )
    row = await cur.fetchone()
    return {
        "items": items,
        "unread_count": int((row["n"] if row else 0) or 0),
        "limit": limit,
        "generated_at": utcnow(),
    }


async def mark_all_read(db, tg_id: int) -> int:
    async with transaction(db):
        cur = await db.execute(
            "UPDATE user_notifications SET read_at=:read_at "
            "WHERE tg_id=:tg_id AND read_at IS NULL",
            {"read_at": utcnow(), "tg_id": tg_id},
        )
        return int(cur.rowcount or 0)
