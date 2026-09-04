"""Рассылки по сегментам: постановка в очередь и отправка с ограничением темпа.

Почему через очередь в БД, а не циклом по списку. Рассылка на несколько тысяч
человек идёт минуты; за это время процесс может быть перезапущен деплоем.
Очередь в `broadcast_targets` даёт возобновляемость (после рестарта продолжим
с pending) и точную статистику доставки.

Telegram ограничивает бота примерно 30 сообщениями в секунду; берём 20 с запасом
и уважаем `retry_after` при 429 — иначе бот получает временную блокировку.
"""
from __future__ import annotations

import asyncio
import logging

from ..repo import comms, content, users
from ..repo.admin import audit

log = logging.getLogger("oracle.broadcast")

DEFAULT_RATE = 20


async def schedule(db, *, title: str, body: str, segment: str = "all",
                   button_text: str | None = None, button_url: str | None = None,
                   scheduled_at: str | None = None,
                   admin_id: int | None = None) -> dict:
    """Создаёт рассылку и наполняет очередь адресатов."""
    broadcast_id = await comms.create_broadcast(
        db, title, body, segment=segment, button_text=button_text,
        button_url=button_url, scheduled_at=scheduled_at, created_by=admin_id)
    ids = await users.segment_ids(db, segment)
    await comms.enqueue_targets(db, broadcast_id, ids)
    await audit(db, admin_id, "broadcast.create", target=str(broadcast_id),
                payload={"segment": segment, "total": len(ids), "title": title})
    return {"id": broadcast_id, "total": len(ids), "segment": segment}


async def preview(db, segment: str) -> dict:
    return {"segment": segment, "count": await users.segment_count(db, segment)}


def _keyboard(broadcast):
    """Кнопка под сообщением, если задана."""
    if not (broadcast["button_text"] and broadcast["button_url"]):
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=broadcast["button_text"],
                             url=broadcast["button_url"])]])


async def run(bot, db, broadcast_id: int, *, batch: int = 100) -> dict:
    """Отправляет рассылку. Возвращает итоговую статистику.

    Функция возобновляемая: повторный вызов доотправит то, что осталось в
    статусе pending.
    """
    from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                    TelegramRetryAfter)

    broadcast = await comms.get_broadcast(db, broadcast_id)
    if not broadcast:
        return {"error": "not_found"}
    if broadcast["status"] in ("done", "cancelled"):
        return await comms.broadcast_progress(db, broadcast_id)

    rate = int(await content.get_setting(db, "broadcast.rate_per_second",
                                         DEFAULT_RATE) or DEFAULT_RATE)
    pause = 1.0 / max(1, rate)
    markup = _keyboard(broadcast)
    await comms.set_broadcast_status(db, broadcast_id, "running",
                                     started_at=comms.utcnow())

    while True:
        targets = await comms.next_targets(db, broadcast_id, limit=batch)
        if not targets:
            break
        for tg_id in targets:
            # атомарный захват: из двух параллельных `run()` (долгая рассылка
            # перекрывает соседний тик) цель достаётся ровно одной — без дублей
            if not await comms.claim_target(db, broadcast_id, tg_id):
                continue
            try:
                # Токен из корзины рассылок (не общей): в бот-процессе сессия
                # и так _BroadcastSession, но run() могут звать и с обычной
                # сессией/тестовым ботом — тогда рассылка всё равно не выест
                # токены живых диалогов.
                from ..core import flood
                if not getattr(getattr(bot, "session", None),
                               "_is_broadcast_session", False):
                    await flood.acquire_broadcast()
                await bot.send_message(tg_id, broadcast["body"], reply_markup=markup)
                await comms.mark_target(db, broadcast_id, tg_id, "sent")
            except TelegramRetryAfter as e:
                # флуд-контроль: ждём столько, сколько просит Telegram, и пробуем снова
                log.warning("рассылка %s: флуд-контроль, пауза %s с",
                            broadcast_id, e.retry_after)
                await asyncio.sleep(e.retry_after + 1)
                await comms.release_target(db, broadcast_id, tg_id)
                continue
            except (TelegramForbiddenError, TelegramBadRequest) as e:
                # заблокировала бота или чат удалён — повторять бессмысленно
                await comms.mark_target(db, broadcast_id, tg_id, "skipped", type(e).__name__)
            except Exception as e:  # noqa: BLE001
                error_type = type(e).__name__
                await comms.mark_target(db, broadcast_id, tg_id, "failed", error_type)
                log.warning("рассылка %s не удалась: %s", broadcast_id, error_type)
            await asyncio.sleep(pause)

    progress = await comms.broadcast_progress(db, broadcast_id)
    # Свежие заявки (крэш случился меньше паузы назад) — это не конец: их вернёт
    # в очередь следующий next_targets. Не помечаем done, пока что-то в работе.
    if progress["pending"] or progress["claiming"]:
        return progress
    await comms.set_broadcast_status(db, broadcast_id, "done",
                                     finished_at=comms.utcnow(),
                                     sent=progress["sent"],
                                     failed=progress["failed"])
    log.info("рассылка %s завершена: %s", broadcast_id, progress)
    return progress


async def cancel(db, broadcast_id: int, admin_id: int | None = None) -> None:
    await comms.set_broadcast_status(db, broadcast_id, "cancelled")
    await audit(db, admin_id, "broadcast.cancel", target=str(broadcast_id))


async def tick(bot, db) -> None:
    """Вызывается планировщиком: отправляет всё, чему пора."""
    for broadcast in await comms.due_broadcasts(db):
        try:
            await run(bot, db, broadcast["id"])
        except Exception as e:  # noqa: BLE001
            log.error("рассылка %s упала: %s", broadcast["id"], e)
