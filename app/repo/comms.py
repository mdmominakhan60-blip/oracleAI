"""Исходящие коммуникации: журнал доставок и рассылки.

`deliveries` — защита от повторной отправки. Планировщик раньше держал отметки
об отправленном в множестве внутри процесса, поэтому после каждого рестарта
утренний прогноз уходил клиентке второй раз. Отметка в БД живёт дольше процесса.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..data.session import transaction, utcnow

# ─────────────────────────── журнал доставок ─────────────────────────────────


async def already_sent(db, tg_id: int, kind: str, key: str) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM deliveries WHERE tg_id=:tg_id AND kind=:kind AND key=:key",
        {"tg_id": tg_id, "kind": kind, "key": key})
    return await cur.fetchone() is not None


async def mark_sent(db, tg_id: int, kind: str, key: str) -> bool:
    """Ставит отметку. False — отметка уже была (кто-то отправил параллельно)."""
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO deliveries(tg_id, kind, key, created_at) "
            "VALUES(:tg_id, :kind, :key, :created_at) "
            "ON CONFLICT (tg_id, kind, key) DO NOTHING",
            {"tg_id": tg_id, "kind": kind, "key": key, "created_at": utcnow()})
        return bool(cur.rowcount)


async def claim(db, tg_id: int, kind: str, key: str) -> bool:
    """Атомарно занимает право на отправку: True — отправляем, False — уже ушло.

    Отметка ставится ДО отправки. Дубль в мессенджере клиентка воспринимает как
    сбой продукта, а не пришедший прогноз — как «сегодня тихо»; поэтому из двух
    рисков выбираем пропуск, а не повтор.
    """
    return await mark_sent(db, tg_id, kind, key)


async def unclaim(db, tg_id: int, kind: str, key: str) -> None:
    """Снимает отметку — если отправка сорвалась по временной причине."""
    async with transaction(db):
        await db.execute(
            "DELETE FROM deliveries WHERE tg_id=:tg_id AND kind=:kind AND key=:key",
            {"tg_id": tg_id, "kind": kind, "key": key})


async def prune(db, days: int = 120) -> int:
    """Журнал нужен только пока актуален повод — старое удаляем."""
    before = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    async with transaction(db):
        cur = await db.execute(
            "DELETE FROM deliveries WHERE created_at < :before", {"before": before})
        return cur.rowcount or 0


# ─────────────────────────────── рассылки ─────────────────────────────────────

async def create_broadcast(db, title: str, body: str, *, segment: str = "all",
                           button_text: str | None = None,
                           button_url: str | None = None,
                           scheduled_at: str | None = None,
                           created_by: int | None = None) -> int:
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO broadcasts(title, body, button_text, button_url, segment_json, "
            "status, scheduled_at, created_by, created_at) "
            "VALUES(:title, :body, :button_text, :button_url, :segment_json, "
            ":status, :scheduled_at, :created_by, :created_at) RETURNING id",
            {"title": title, "body": body, "button_text": button_text,
             "button_url": button_url,
             "segment_json": json.dumps({"segment": segment}, ensure_ascii=False),
             "status": "scheduled" if scheduled_at else "draft",
             "scheduled_at": scheduled_at, "created_by": created_by,
             "created_at": utcnow()})
        row = await cur.fetchone()
        return row["id"]


async def get_broadcast(db, broadcast_id: int):
    cur = await db.execute(
        "SELECT * FROM broadcasts WHERE id=:id", {"id": broadcast_id})
    return await cur.fetchone()


async def list_broadcasts(db, limit: int = 50) -> list[dict]:
    cur = await db.execute(
        "SELECT * FROM broadcasts ORDER BY id DESC LIMIT :limit", {"limit": limit})
    return [dict(r) for r in await cur.fetchall()]


async def set_broadcast_status(db, broadcast_id: int, status: str, **fields) -> None:
    allowed = {"total", "sent", "failed", "started_at", "finished_at", "scheduled_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    keys = "".join(f", {k}=:{k}" for k in fields)
    async with transaction(db):
        await db.execute(
            f"UPDATE broadcasts SET status=:status{keys} WHERE id=:id",
            {"status": status, **fields, "id": broadcast_id})


async def enqueue_targets(db, broadcast_id: int, ids: list[int]) -> int:
    if not ids:
        return 0
    async with transaction(db):
        await db.executemany(
            "INSERT INTO broadcast_targets(broadcast_id, tg_id, status) "
            "VALUES(:broadcast_id, :tg_id, 'pending') "
            "ON CONFLICT (broadcast_id, tg_id) DO NOTHING",
            [{"broadcast_id": broadcast_id, "tg_id": uid} for uid in ids])
        await db.execute(
            "UPDATE broadcasts SET total=:total WHERE id=:id",
            {"total": len(ids), "id": broadcast_id})
    return len(ids)


#: Заявка на отправку живёт дольше живой паузы, но не бесконечно: если процесс
#: упал между claim и mark, заявку возвращаем в очередь.
CLAIM_TIMEOUT_S = 600


async def next_targets(db, broadcast_id: int, limit: int = 100) -> list[int]:
    """Пачка целей к отправке. Брошенные заявки (крэш) возвращает в pending.

    Захват (claim) — не здесь, а по одной цели перед отправкой: пачка из
    `pending` может перекрыться у двух параллельных запусков, а вот `claim` с
    условием `status='pending'` атомарен и отдаёт цель ровно одному.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TIMEOUT_S)
              ).isoformat()
    async with transaction(db):
        await db.execute(
            "UPDATE broadcast_targets SET status='pending', claimed_at=NULL, error=NULL "
            "WHERE broadcast_id=:broadcast_id AND status='claiming' AND claimed_at < :cutoff",
            {"broadcast_id": broadcast_id, "cutoff": cutoff})
        cur = await db.execute(
            "SELECT tg_id FROM broadcast_targets WHERE broadcast_id=:broadcast_id "
            "AND status='pending' LIMIT :limit",
            {"broadcast_id": broadcast_id, "limit": limit})
        return [r["tg_id"] for r in await cur.fetchall()]


async def claim_target(db, broadcast_id: int, tg_id: int) -> bool:
    """Атомарно занимает цель. False — её уже забрал другой процесс.

    Условие `status='pending'` в UPDATE и есть гарантия: из двух параллельных
    `run()` ровно один получит rowcount 1, второй — 0 и пропустит цель.
    """
    async with transaction(db):
        cur = await db.execute(
            "UPDATE broadcast_targets SET status='claiming', claimed_at=:now, error=NULL "
            "WHERE broadcast_id=:broadcast_id AND tg_id=:tg_id AND status='pending'",
            {"now": utcnow(), "broadcast_id": broadcast_id, "tg_id": tg_id})
        return bool(cur.rowcount)


async def release_target(db, broadcast_id: int, tg_id: int) -> None:
    """Возврат цели в очередь — временный сбой (флуд-контроль, сеть)."""
    async with transaction(db):
        await db.execute(
            "UPDATE broadcast_targets SET status='pending', claimed_at=NULL "
            "WHERE broadcast_id=:broadcast_id AND tg_id=:tg_id AND status='claiming'",
            {"broadcast_id": broadcast_id, "tg_id": tg_id})


async def mark_target(db, broadcast_id: int, tg_id: int, status: str,
                      error: str | None = None) -> None:
    async with transaction(db):
        # Условие status='claiming': после reclaim (>CLAIM_TIMEOUT_S) цель может
        # забрать другой run — первая (опоздавшая) отметка не должна засчитаться
        # или задвоить broadcasts.sent.
        cur = await db.execute(
            "UPDATE broadcast_targets SET status=:status, error=:error, sent_at=:now "
            "WHERE broadcast_id=:broadcast_id AND tg_id=:tg_id AND status='claiming'",
            {"status": status, "error": error, "now": utcnow(),
             "broadcast_id": broadcast_id, "tg_id": tg_id})
        if not cur.rowcount:
            return
        column = "sent" if status == "sent" else "failed"
        # INVARIANT: keys only from allowlist above — never interpolate user input
        await db.execute(
            f"UPDATE broadcasts SET {column} = COALESCE({column},0) + 1 WHERE id=:id",
            {"id": broadcast_id})


async def broadcast_progress(db, broadcast_id: int) -> dict:
    cur = await db.execute(
        "SELECT status, COUNT(*) n FROM broadcast_targets WHERE broadcast_id=:broadcast_id "
        "GROUP BY status", {"broadcast_id": broadcast_id})
    rows = {r["status"]: r["n"] for r in await cur.fetchall()}
    return {"pending": rows.get("pending", 0), "claiming": rows.get("claiming", 0),
            "sent": rows.get("sent", 0), "failed": rows.get("failed", 0),
            "skipped": rows.get("skipped", 0)}


async def due_broadcasts(db) -> list[dict]:
    """Рассылки, которым пора уйти (запланированные и незавершённые running)."""
    cur = await db.execute(
        "SELECT * FROM broadcasts WHERE (status='scheduled' AND scheduled_at<=:now) "
        "OR status='running' ORDER BY id", {"now": utcnow()})
    return [dict(r) for r in await cur.fetchall()]
