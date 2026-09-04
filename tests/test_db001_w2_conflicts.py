"""DB-001 w2 — граничные тесты ON CONFLICT-путей портированного диалекта.

Каждый тест покрывает конкретный конфликт-кейс: повторный вебхук, дублирующий
INSERT по уникальному ключу, параллельная оплата и другие ситуации, где раньше
стоял INSERT OR IGNORE и теперь стоит ON CONFLICT (<col>) DO NOTHING.
"""
from __future__ import annotations

import asyncio

from app.repo import billing as billing_repo
from app.repo import comms, growth
from app.repo.crm import add_tag, tags_of
from app.repo.jobs import create as create_job
from app.repo.jobs import get as get_job
from app.services import billing as billing_svc
from app.services.horoscopes import _save_if_absent, get as get_horoscope


# ──────────────────────────── billing: заказы ─────────────────────────────────

async def test_mark_order_paid_webhook_retry_no_duplicate_payment(db, user):
    """Повторный вебхук (ретрай Telegram Stars) не создаёт дубль строки payments.

    ON CONFLICT (id) в UPDATE ... WHERE status='pending' возвращает None
    при повторном вызове — товар не выдаётся дважды.
    """
    order = await billing_svc.checkout_plan(db, user["tg_id"], "vip")

    first = await billing_repo.mark_order_paid(
        db, order["payload"], charge_id="ch_retry", amount_stars=order["amount_stars"])
    assert first is not None, "первая оплата должна вернуть строку заказа"

    second = await billing_repo.mark_order_paid(
        db, order["payload"], charge_id="ch_retry", amount_stars=order["amount_stars"])
    assert second is None, "повторный вебхук не должен вернуть заказ"

    cur = await db.execute(
        "SELECT COUNT(*) c FROM payments WHERE order_id=:oid",
        {"oid": order["id"]})
    assert (await cur.fetchone())["c"] == 1, "дубль строки в payments"


async def test_mark_order_paid_parallel_webhooks_one_wins(db, user):
    """Параллельные вебхуки: только один UPDATE ... WHERE status='pending' побеждает."""
    order = await billing_svc.checkout_plan(db, user["tg_id"], "vip")

    results = await asyncio.gather(
        billing_repo.mark_order_paid(
            db, order["payload"], charge_id="ch_a",
            amount_stars=order["amount_stars"]),
        billing_repo.mark_order_paid(
            db, order["payload"], charge_id="ch_b",
            amount_stars=order["amount_stars"]),
    )
    winners = [r for r in results if r is not None]
    assert len(winners) == 1, "больше одного вызова пометило заказ оплаченным"

    cur = await db.execute(
        "SELECT COUNT(*) c FROM payments WHERE order_id=:oid",
        {"oid": order["id"]})
    assert (await cur.fetchone())["c"] == 1, "дубль строки в payments при параллельном вебхуке"


async def test_upsert_plan_no_duplicate_on_conflict(db):
    """ON CONFLICT (code) DO NOTHING: повторный upsert_plan не создаёт дубль."""
    await billing_repo.upsert_plan(db, "testplan", title="Test", price_stars=500)
    await billing_repo.upsert_plan(db, "testplan", title="Test Updated", price_stars=600)

    cur = await db.execute(
        "SELECT COUNT(*) c, MAX(price_stars) p FROM plans WHERE code='testplan'")
    row = await cur.fetchone()
    assert row["c"] == 1, "дубль строки в plans"
    # Второй вызов должен обновить цену через UPDATE
    assert row["p"] == 600, "UPDATE после ON CONFLICT не применился"


async def test_upsert_product_no_duplicate_on_conflict(db):
    """ON CONFLICT (sku) DO NOTHING: повторный upsert_product не создаёт дубль."""
    await billing_repo.upsert_product(db, "test_sku", title="Item", price_stars=100)
    await billing_repo.upsert_product(db, "test_sku", title="Item v2", price_stars=200)

    cur = await db.execute(
        "SELECT COUNT(*) c, MAX(price_stars) p FROM products WHERE sku='test_sku'")
    row = await cur.fetchone()
    assert row["c"] == 1, "дубль строки в products"
    assert row["p"] == 200, "UPDATE после ON CONFLICT не применился"


# ──────────────────────────── growth: промокоды ───────────────────────────────

async def test_create_codes_collision_skips_to_next(db, monkeypatch):
    """ON CONFLICT (code) DO NOTHING при коллизии: генератор пробует следующий код."""
    import itertools

    call_count = itertools.count()
    codes_seq = ["SAMECODE", "SAMECODE", "UNIQUE01"]

    def patched_generate(prefix="", length=8):
        return codes_seq[min(next(call_count), len(codes_seq) - 1)]

    monkeypatch.setattr(growth, "generate_code", patched_generate)

    # Вставляем SAMECODE вручную так, чтобы ON CONFLICT сработал
    await db.execute(
        "INSERT INTO promo_codes(code, kind, days, plan_code, crystals, "
        "sku, batch, max_uses, used_count, created_at) "
        "VALUES('SAMECODE','plan_days',30,'vip',0,NULL,'',1,0,:now)",
        {"now": "2026-01-01T00:00:00+00:00"})
    await db.commit()

    result = await growth.create_codes(db, 1, batch="test")
    assert "UNIQUE01" in result, "коллизия кода не была пропущена"
    assert len(result) == 1


async def test_record_referral_duplicate_returns_false(db, user, free_user):
    """ON CONFLICT (referrer_id, invitee_id, level): повторный record_referral → False."""
    first = await growth.record_referral(db, user["tg_id"], free_user["tg_id"])
    assert first is True, "первая запись реферала должна вернуть True"

    second = await growth.record_referral(db, user["tg_id"], free_user["tg_id"])
    assert second is False, "дублирующий реферал должен вернуть False"

    cur = await db.execute(
        "SELECT COUNT(*) c FROM referrals WHERE referrer_id=:r AND invitee_id=:i",
        {"r": user["tg_id"], "i": free_user["tg_id"]})
    assert (await cur.fetchone())["c"] == 1, "дубль строки в referrals"


async def test_redeem_promo_second_activation_same_user_returns_none(db, user):
    """Повторная активация того же промокода одним человеком → None (не дубль)."""
    codes = await growth.create_codes(db, 1, days=30, max_uses=2, batch="dedup-test")
    first = await growth.redeem(db, codes[0], user["tg_id"])
    assert first is not None, "первая активация должна успешно пройти"

    second = await growth.redeem(db, codes[0], user["tg_id"])
    assert second is None, "повторная активация тем же пользователем не должна проходить"

    cur = await db.execute(
        "SELECT COUNT(*) c FROM promo_redemptions WHERE code=:code AND tg_id=:tg_id",
        {"code": codes[0], "tg_id": user["tg_id"]})
    assert (await cur.fetchone())["c"] == 1, "дубль строки в promo_redemptions"


# ──────────────────────────── comms: доставки ─────────────────────────────────

async def test_mark_sent_duplicate_returns_false(db, user):
    """ON CONFLICT (tg_id, kind, key): второй mark_sent по тому же ключу → False."""
    first = await comms.mark_sent(db, user["tg_id"], "forecast", "2026-08-29")
    assert first is True, "первая отметка должна вернуть True"

    second = await comms.mark_sent(db, user["tg_id"], "forecast", "2026-08-29")
    assert second is False, "дублирующая отметка должна вернуть False"

    cur = await db.execute(
        "SELECT COUNT(*) c FROM deliveries WHERE tg_id=:tg_id AND kind='forecast'",
        {"tg_id": user["tg_id"]})
    assert (await cur.fetchone())["c"] == 1, "дубль строки в deliveries"


async def test_mark_sent_parallel_only_one_wins(db, user):
    """Параллельные отметки об отправке — побеждает ровно одна."""
    results = await asyncio.gather(
        comms.mark_sent(db, user["tg_id"], "weekly", "2026-W35"),
        comms.mark_sent(db, user["tg_id"], "weekly", "2026-W35"),
    )
    assert sum(results) == 1, "больше одной параллельной отметки прошло"

    cur = await db.execute(
        "SELECT COUNT(*) c FROM deliveries "
        "WHERE tg_id=:tg_id AND kind='weekly' AND key='2026-W35'",
        {"tg_id": user["tg_id"]})
    assert (await cur.fetchone())["c"] == 1, "дубль строки в deliveries при гонке"


# ──────────────── broadcast_targets: enqueue_targets ──────────────────────────

async def test_enqueue_targets_duplicate_ids_no_conflict(db):
    """ON CONFLICT (broadcast_id, tg_id) DO NOTHING: повторное enqueue не падает."""
    bid = await comms.create_broadcast(db, "Тест", "Тело")
    await comms.enqueue_targets(db, bid, [1001, 1002, 1003])
    # Второй вызов с теми же id не должен ни упасть, ни задвоить строки
    await comms.enqueue_targets(db, bid, [1002, 1003, 1004])

    cur = await db.execute(
        "SELECT COUNT(*) c FROM broadcast_targets WHERE broadcast_id=:bid",
        {"bid": bid})
    # 1001, 1002, 1003 из первого + 1004 из второго = 4 уникальных
    assert (await cur.fetchone())["c"] == 4, "дубли или пропуски в broadcast_targets"


# ──────────────── task_jobs: ON CONFLICT (id) DO NOTHING ──────────────────────

async def test_create_job_duplicate_id_no_error(db):
    """ON CONFLICT (id) DO NOTHING: повторный create той же задачи не падает."""
    await create_job(db, "task-abc", "test_kind", payload={"x": 1})
    # Повторный вызов с тем же task_id не должен упасть
    await create_job(db, "task-abc", "test_kind", payload={"x": 2})

    job = await get_job(db, "task-abc")
    assert job is not None
    # Первый payload сохранился (ON CONFLICT DO NOTHING не обновляет)
    assert job["payload"] == {"x": 1}, "ON CONFLICT не должен перезаписывать задачу"


# ─────────────── horoscopes: ON CONFLICT (day, sign) DO NOTHING ───────────────

async def test_save_if_absent_parallel_only_one_saves(db):
    """ON CONFLICT (day, sign): при параллельном сохранении только один побеждает."""
    day = "2026-08-29"
    sign = "Лев"

    results = await asyncio.gather(
        _save_if_absent(db, sign, day, "Гороскоп A"),
        _save_if_absent(db, sign, day, "Гороскоп B"),
    )
    assert sum(results) == 1, "больше одного параллельного INSERT сохранилось"

    text = await get_horoscope(db, sign, day)
    assert text in ("Гороскоп A", "Гороскоп B"), "текст не сохранился"


async def test_save_if_absent_second_call_returns_false(db):
    """Второй _save_if_absent на ту же (day, sign) → False."""
    day = "2026-08-28"
    sign = "Овен"
    first = await _save_if_absent(db, sign, day, "Первый")
    assert first is True

    second = await _save_if_absent(db, sign, day, "Второй")
    assert second is False, "второй INSERT не должен перезаписывать"

    text = await get_horoscope(db, sign, day)
    assert text == "Первый", "существующий текст затёрт"


# ─────────────────────── crm: user_tags ON CONFLICT ───────────────────────────

async def test_add_tag_duplicate_no_error(db, user):
    """ON CONFLICT (tg_id, tag) DO NOTHING: дублирующий add_tag не падает."""
    await add_tag(db, user["tg_id"], "vip")
    await add_tag(db, user["tg_id"], "vip")  # не должно упасть

    tags = await tags_of(db, user["tg_id"])
    assert tags.count("vip") == 1, "дубль тега в user_tags"
