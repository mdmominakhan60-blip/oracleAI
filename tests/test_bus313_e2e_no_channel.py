"""BUS-313 §6 e2e: клиентка с закрытым каналом — только Q5, тег, разблокировка.

Сценарий: VIP-клиентка, бот заблокирован (forbidden-доставка) → из обычных
правил (Q2) исключена, видна в Q5 (обслуживание канала) → первая успешная
доставка после forbidden → channel_closed=False → вернулась в Q2.

Переход «вернулась в Q2» требует, чтобы forbidden-строка вышла из окна Q5
(24ч): Q5 держится на факте failed/forbidden за окно, время имитируем
обновлением created_at forbidden-строки.
"""
from __future__ import annotations

from datetime import timedelta

from app.repo import ltv_tier as lt
from tests.test_bus309_ltv import _deliver_at, _ensure, _iso, _now


async def test_e2e_no_channel_full_path(db):
    # 1. VIP-клиентка уснула (Q2-профиль: тир A + sleeping_14d).
    await _ensure(db, 3601, ltv_stars=500, last_seen=_iso(days_ago=20))
    # 2. Бот не может написать → forbidden-доставка 2ч назад (в окне Q5 24ч).
    await _deliver_at(db, 3601, "forecast", "d1", _iso(hours_ago=2),
                      status="forbidden", error="TelegramForbiddenError")
    assert await lt.channel_closed(db, 3601) is True
    queue = await lt.attention_queue(db, limit=50)
    rules = {c["tg_id"]: c["rule"] for c in queue["items"]}
    assert rules.get(3601) == "q5", f"закрытый канал должен быть в Q5: {rules}"
    assert "q2" not in rules.get(3601, set()), "закрытый канал не должен быть в Q2"
    # 3. Оператор ставит тег no-channel (закрывается Q5-кейс тегом; на данные
    #    это не влияет — клиентка не дёргается до разблокировки канала).
    # 4. Клиентка разблокирует бота → первая успешная доставка.
    await _deliver_at(db, 3601, "forecast", "d2", _iso(hours_ago=1), status="sent")
    assert await lt.channel_closed(db, 3601) is False
    # 5. Вернулась в обычные правила: VIP sleeping → Q2. Время идёт —
    #    forbidden-строка старше 24ч, окно Q5 её отпускает.
    stale = (_now() - timedelta(hours=26)).isoformat()
    await db.execute(
        "UPDATE deliveries SET created_at=:stale "
        "WHERE tg_id=3601 AND kind='forecast' AND key='d1'",
        {"stale": stale})
    queue2 = await lt.attention_queue(db, limit=50)
    rules2 = {c["tg_id"]: c["rule"] for c in queue2["items"]}
    assert rules2.get(3601) == "q2", f"после разблокировки ждём Q2: {rules2}"
    assert "q5" not in rules2.get(3601, set()), "sent-доставки не должны держать Q5"
