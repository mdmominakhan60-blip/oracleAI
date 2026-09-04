"""Транзакции: отмена задачи (G12).

`asyncio.CancelledError` — BaseException, а не Exception. Если транзакция ловила
только Exception, отменённая на шатдауне задача оставляла соединение в открытой
транзакции, и частичная запись уходила в базу следующим чужим commit().
"""
from __future__ import annotations

import asyncio

import pytest

from app.data.session import transaction


async def test_transaction_rolls_back_on_cancel(db):
    """Отменённая посреди записи задача не оставляет следов в базе."""
    started = asyncio.Event()

    async def worker():
        async with transaction(db):
            await db.execute("INSERT INTO users(tg_id, name) VALUES(?,?)",
                             (5001, "Отменённая"))
            started.set()
            await asyncio.sleep(10)   # точка отмены — внутри транзакции

    task = asyncio.create_task(worker())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    cur = await db.execute("SELECT COUNT(*) c FROM users WHERE tg_id=5001")
    assert (await cur.fetchone())["c"] == 0, "частичная запись осталась в базе"

    # Соединение чистое: следующая транзакция коммитится, а не валится в чужой
    # открытой транзакции отменённой задачи.
    async with transaction(db):
        await db.execute("INSERT INTO users(tg_id, name) VALUES(?,?)",
                         (5002, "Живая"))
    cur = await db.execute("SELECT COUNT(*) c FROM users WHERE tg_id=5002")
    assert (await cur.fetchone())["c"] == 1
