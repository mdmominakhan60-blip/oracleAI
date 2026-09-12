"""BUS-313 приёмка §2: грани окон правил очереди внимания (вход/невход).

Точная грань (>= в SQL) верифицируется код-ревью; здесь — детерминированные
проверки по ОБЕ стороны грани с 5-минутным отступом (устойчиво к дельте
между вставкой и чтением): внутри окна — вход, за окном — невход.
Юзер может состоять в нескольких правилах — парсим set правил.
"""
from __future__ import annotations

from datetime import timedelta

from app.repo import ltv_tier as lt
from tests.test_bus309_ltv import _deliver_at, _ensure, _iso, _now, _track_at


def _iso_b(days_ago: float = 0, hours_ago: float = 0, minutes_ago: int = 0) -> str:
    delta = timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
    return (_now() - delta).isoformat()


def _rules_by_tg(queue) -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for c in queue["items"]:
        out.setdefault(c["tg_id"], set()).add(c["rule"])
    return out


async def test_q1_boundary_48h(db):
    """Q1: refund внутри 48ч (47ч55м) — вход; за окном (48ч5м) — невход."""
    await _ensure(db, 3501, ltv_stars=100)
    await _ensure(db, 3502, ltv_stars=100)
    await _track_at(db, 3501, "refund_requested", _iso_b(hours_ago=47, minutes_ago=55))
    await _track_at(db, 3502, "refund_requested", _iso_b(hours_ago=48, minutes_ago=5))
    queue = await lt.attention_queue(db, limit=50)
    rules = _rules_by_tg(queue)
    assert "q1" in rules.get(3501, set()), f"47ч55м должен входить в Q1: {rules}"
    assert "q1" not in rules.get(3502, set()), f"48ч5м не должен входить в Q1: {rules}"


async def test_q5_boundary_24h(db):
    """Q5: forbidden внутри 24ч (23ч55м) — вход; за окном (24ч5м) — невход."""
    await _ensure(db, 3511)
    await _ensure(db, 3512)
    await _deliver_at(db, 3511, "forecast", "b1", _iso_b(hours_ago=23, minutes_ago=55),
                      status="forbidden", error="TelegramForbiddenError")
    await _deliver_at(db, 3512, "forecast", "b2", _iso_b(hours_ago=24, minutes_ago=5),
                      status="forbidden", error="TelegramForbiddenError")
    queue = await lt.attention_queue(db, limit=50)
    rules = _rules_by_tg(queue)
    assert "q5" in rules.get(3511, set()), f"23ч55м должен входить в Q5: {rules}"
    assert "q5" not in rules.get(3512, set()), f"24ч5м не должен входить в Q5: {rules}"


async def test_q6_boundary_3d(db):
    """Q6: полных дней с регистрации ≥3 (3д2ч) — вход; 2д23ч — невход.
    Окно считается _days_since (.days), поэтому грань — полные 3 дня."""
    await _ensure(db, 3521, ltv_stars=0, onboarded=0, created_at=_iso_b(days_ago=2, hours_ago=23))
    await _deliver_at(db, 3521, "onboard_nudge", "d1:3521", _iso(days_ago=2))
    await _ensure(db, 3522, ltv_stars=0, onboarded=0, created_at=_iso_b(days_ago=3, hours_ago=2))
    await _deliver_at(db, 3522, "onboard_nudge", "d1:3522", _iso(days_ago=2))
    queue = await lt.attention_queue(db, limit=50)
    rules = _rules_by_tg(queue)
    assert "q6" not in rules.get(3521, set()), f"2д23ч (<3 полных дней) не должен входить в Q6: {rules}"
    assert "q6" in rules.get(3522, set()), f"3д2ч (≥3 полных дней) должен входить в Q6: {rules}"


async def test_q7_boundary_gap_30d(db):
    """Q7: гэп ≥30д (prev 30д5м назад) — вход; гэп <30д (prev 29д23ч) — невход."""
    await _ensure(db, 3531)
    await _track_at(db, 3531, "miniapp_open", _iso_b(days_ago=30, minutes_ago=5))
    await _track_at(db, 3531, "miniapp_open", _iso(hours_ago=1))
    await _ensure(db, 3532)
    await _track_at(db, 3532, "miniapp_open", _iso_b(days_ago=29, hours_ago=23))
    await _track_at(db, 3532, "miniapp_open", _iso(hours_ago=1))
    queue = await lt.attention_queue(db, limit=50)
    rules = _rules_by_tg(queue)
    assert "q7" in rules.get(3531, set()), f"гэп ≥30д должен входить в Q7: {rules}"
    assert "q7" not in rules.get(3532, set()), f"гэп <30д не должен входить в Q7: {rules}"


async def test_channel_reopen_after_forbidden_returns_to_normal_rules(db):
    """§2.7: пара VIP-sleeping юзеров, один с forbidden. Закрытый — вне Q2;
    после первой успешной доставки channel_closed=False и он вернулся в Q2."""
    await _ensure(db, 3541, ltv_stars=200, last_seen=_iso(days_ago=20))
    await _ensure(db, 3542, ltv_stars=200, last_seen=_iso(days_ago=20))
    await _deliver_at(db, 3541, "forecast", "k1", _iso(hours_ago=3),
                      status="forbidden", error="TelegramForbiddenError")
    assert await lt.channel_closed(db, 3541) is True
    assert await lt.channel_closed(db, 3542) is False
    queue = await lt.attention_queue(db, limit=50)
    rules = _rules_by_tg(queue)
    # Контроль: 3542 (без forbidden) входит в Q2 — значит без forbidden входил бы и 3541.
    assert "q2" in rules.get(3542, set()), f"контрольный юзер должен быть в Q2: {rules}"
    assert "q2" not in rules.get(3541, set()), f"закрытый канал исключён из Q2: {rules}"
    # Первая успешная доставка после forbidden → канал открыт.
    await _deliver_at(db, 3541, "forecast", "k2", _iso(hours_ago=1), status="sent")
    assert await lt.channel_closed(db, 3541) is False
    queue2 = await lt.attention_queue(db, limit=50)
    rules2 = _rules_by_tg(queue2)
    assert "q2" in rules2.get(3541, set()), f"после открытия канала ждём возврат в Q2: {rules2}"


async def test_q1_survives_forbidden_exclusion(db):
    """§2.6: юзер с forbidden и свежим refund остаётся в Q1 (Q1 не исключается);
    попадание в Q5 параллельно не отменяет Q1."""
    await _ensure(db, 3551, ltv_stars=200)
    await _track_at(db, 3551, "refund_requested", _iso(hours_ago=2))
    await _deliver_at(db, 3551, "forecast", "kf", _iso(hours_ago=3),
                      status="forbidden", error="TelegramForbiddenError")
    queue = await lt.attention_queue(db, limit=50)
    rules = _rules_by_tg(queue)
    assert "q1" in rules.get(3551, set()), f"Q1 должен пережить forbidden-исключение: {rules}"
