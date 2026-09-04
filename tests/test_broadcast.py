"""Рассылки: атомарный захват целей (G9).

Два параллельных `run()` (долгая рассылка перекрывает соседний тик планировщика)
не должны отправить одному адресату дважды: захват цели — атомарный UPDATE с
условием `status='pending'`, из гонки выходит ровно один. Брошенные заявки
(крэш между claim и mark) возвращаются в очередь по таймауту claimed_at.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.repo import comms, users
from app.services import broadcast


class FakeBot:
    """Бот-заглушка: считает отправки, реально ничего не шлёт."""

    def __init__(self):
        self.sent: list[int] = []

    async def send_message(self, tg_id, body, reply_markup=None):
        self.sent.append(tg_id)


async def _make_broadcast(db, ids: list[int]) -> int:
    bid = await comms.create_broadcast(db, "Тест", "Сообщение")
    await comms.enqueue_targets(db, bid, ids)
    return bid


async def test_claim_target_atomic(db):
    """Цель занимается ровно один раз; release возвращает её в очередь."""
    bid = await _make_broadcast(db, [1001, 1002, 1003])

    assert await comms.claim_target(db, bid, 1001) is True
    assert await comms.claim_target(db, bid, 1001) is False   # занята другим run()
    await comms.release_target(db, bid, 1001)
    assert await comms.claim_target(db, bid, 1001) is True    # вернулась в pending


async def test_next_targets_reclaims_stale_claims(db):
    """Заявка, брошенная крэшем дольше таймаута назад, снова в очереди."""
    bid = await _make_broadcast(db, [1001])
    await comms.claim_target(db, bid, 1001)

    stale = (datetime.now(timezone.utc) - timedelta(seconds=comms.CLAIM_TIMEOUT_S + 60)
             ).isoformat()
    await db.execute(
        "UPDATE broadcast_targets SET claimed_at=? WHERE broadcast_id=? AND tg_id=?",
        (stale, bid, 1001))
    await db.commit()

    targets = await comms.next_targets(db, bid)
    assert 1001 in targets, "брошенная заявка не вернулась в очередь"


async def test_parallel_runs_send_each_target_once(db):
    """Два перекрывающихся run() не отправляют адресату дважды."""
    await users.ensure(db, 1001, "А")
    await users.ensure(db, 1002, "Б")
    await users.ensure(db, 1003, "В")
    await users.ensure(db, 1004, "Г")
    await users.ensure(db, 1005, "Д")
    await users.ensure(db, 1006, "Е")
    await users.ensure(db, 1007, "Ё")
    await users.ensure(db, 1008, "Ж")
    await users.ensure(db, 1009, "З")
    await users.ensure(db, 1010, "И")
    bid = await broadcast.schedule(db, title="Тест", body="Тело", segment="all")
    assert bid["total"] == 10

    bot = FakeBot()
    await asyncio.gather(
        broadcast.run(bot, db, bid["id"], batch=3),
        broadcast.run(bot, db, bid["id"], batch=3),
    )

    assert sorted(bot.sent) == [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010]
    assert len(bot.sent) == 10, f"дубли: {[x for x in bot.sent if bot.sent.count(x) > 1]}"

    done = await comms.get_broadcast(db, bid["id"])
    assert done["status"] == "done"
    assert done["sent"] == 10
