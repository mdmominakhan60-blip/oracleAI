"""Слой данных: схема, миграции, сид, транзакции."""
from __future__ import annotations

import asyncio

import pytest

from app.data.session import healthcheck, transaction
from app.repo import content, dialog, users


async def test_fresh_database_has_full_schema(db):
    state = await healthcheck(db)
    assert state["ok"]
    assert state["journal_mode"].lower() == "postgresql"
    cur = await db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'")
    tables = {row[0] for row in await cur.fetchall()}
    for required in ("users", "messages", "threads", "orders", "payments",
                     "entitlements", "events", "settings", "content_items",
                     "feature_flags", "admins", "broadcasts", "deliveries",
                     "reports", "referrals", "promo_redemptions"):
        assert required in tables, required


async def test_seed_fills_catalog(db):
    from app.repo import billing
    plans = await billing.list_plans(db)
    assert any(p["code"] == "vip" for p in plans)
    products = await billing.list_products(db)
    assert any(p["sku"] == "spread_celtic" for p in products)
    # одиночные расклады обязаны продаваться — это отдельное требование продукта
    assert any(p["kind"] == "spread" for p in products)
    assert await content.get_setting(db, "referral.bonus") == 15
    assert await content.get_text(db, "guide", "tarot")


async def test_seed_is_idempotent_and_keeps_edits(db):
    from app.data.seed import seed_defaults
    from app.repo import billing
    await billing.upsert_plan(db, "vip", price_stars=999, title="Мой VIP")
    await seed_defaults(db)
    plan = await billing.get_plan(db, "vip")
    assert plan["price_stars"] == 999, "повторный сид перезаписал правки админа"
    assert plan["title"] == "Мой VIP"


async def test_transaction_rolls_back_on_error(db, user):
    with pytest.raises(RuntimeError):
        async with transaction(db):
            await db.execute("UPDATE users SET crystals=999 WHERE tg_id=?",
                             (user["tg_id"],))
            raise RuntimeError("сбой посреди операции")
    fresh = await users.get(db, user["tg_id"])
    assert fresh["crystals"] != 999, "откат транзакции не сработал"


async def test_ensure_race_double_start_creates_user_once(db):
    """Двойной /start в один момент не должен валить UNIQUE по tg_id.

    Оба вызова успевают пройти SELECT до INSERT; INSERT OR IGNORE + rowcount
    дают одного пользователя и один welcome в журнале.
    """
    await asyncio.gather(
        users.ensure(db, 777, "Первый"),
        users.ensure(db, 777, "Второй"),
    )
    fresh = await users.get(db, 777)
    assert fresh is not None, "пользователь не создан"
    assert fresh["name"] in ("Первый", "Второй")
    cur = await db.execute(
        "SELECT COUNT(*) c FROM crystal_ledger WHERE tg_id=? AND reason='welcome'",
        (777,))
    assert (await cur.fetchone())["c"] == 1, "welcome начислен дважды"


async def test_update_user_rejects_unknown_column(db, user):
    with pytest.raises(ValueError):
        await users.update(db, user["tg_id"], nonexistent_field=1)


async def test_memory_deduplicates(db, user):
    assert await dialog.save_memory(db, user["tg_id"], "Работает дизайнером")
    assert not await dialog.save_memory(db, user["tg_id"], "работает дизайнером  ")
    facts = await dialog.get_memories(db, user["tg_id"])
    assert facts.count("Работает дизайнером") == 1
    rows = await dialog.memories_full(db, user["tg_id"])
    assert rows[0]["weight"] == 2, "повтор должен усиливать важность факта"


async def test_recall_caches_repeated_query(db, monkeypatch):
    """Тот же вопрос в пределах окна не считает семантику заново (G15)."""
    from app.core import memory

    await users.ensure(db, 1001, "А")
    calls = []

    async def fake_semantic(db_, tg, q, limit):
        calls.append(q)
        return ["Факт про работу"]

    monkeypatch.setattr(memory, "_semantic", fake_semantic)
    r1 = await memory.recall(db, 1001, "Расскажи про работу", limit=5)
    r2 = await memory.recall(db, 1001, "расскажи про работу", limit=5)

    assert calls == ["Расскажи про работу"], "второй запрос должен прийти из кеша"
    assert r1 == r2


async def test_recall_uses_bounded_embedding_pool(db, monkeypatch):
    """Семантика сканирует окно кандидатов, а не всю историю; на 400 фактах
    результат всё равно корректный (G15)."""
    import hashlib

    from app.core import memory

    await users.ensure(db, 1001, "А")

    def _vec(text: str) -> list[float]:
        # Детерминированный, но различимый вектор на текст: иначе все факты
        # с одинаковым вектором склеились бы дедупликацией в один.
        h = hashlib.sha256(text.encode()).digest()
        return [(h[i % 32] / 255.0) * 2 - 1 for i in range(16)]

    async def fake_embed(texts):
        return [_vec(t) for t in texts]

    monkeypatch.setattr(memory, "embed", fake_embed)
    monkeypatch.setattr(memory, "embeddings_enabled", lambda: True)
    monkeypatch.setattr(memory, "RELEVANCE_FLOOR", -1.0)
    for i in range(400):
        await memory.remember(db, 1001, f"Факт номер {i}")

    facts = await memory.recall(db, 1001, "что-нибудь", limit=8)
    assert len(facts) == 8, "recall должен собрать окно из 400 фактов"
    assert all("Факт" in f for f in facts)


async def test_anonymize_keeps_row_but_clears_pii(db, user):
    await dialog.add_diary(db, user["tg_id"], "личная запись")
    await users.anonymize(db, user["tg_id"])
    fresh = await users.get(db, user["tg_id"])
    assert fresh is not None, "строка нужна для сводимости платежей"
    assert fresh["birth_date"] is None
    assert fresh["status"] == "deleted"
    assert await dialog.get_diary(db, user["tg_id"]) == []


async def test_g13_missing_indexes_exist(db):
    """Индексы под горячие выборки (G13): оплата по заказу, промо, рефералы,
    DAU/WAU по событиям, учёт LLM."""
    cur = await db.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    indexes = {row[0] for row in await cur.fetchall()}
    for required in (
        "idx_pay_order", "idx_promo_red", "idx_ref_invitee",
        "idx_events_created", "idx_usage_created",
        "idx_msg_user", "idx_msg_thread", "idx_msg_user_id",
        "idx_msg_user_thread_id", "idx_msg_user_question_id",
        "idx_thread_user", "idx_thread_user_agent", "idx_thread_user_recent",
        "idx_mem_user_rank", "idx_events_user_name", "idx_events_created_name",
        "idx_orders_status_paid", "idx_pay_status_created", "idx_users_created_source",
        "idx_promo_created",
    ):
        assert required in indexes, required


async def test_prune_analytics_uses_small_batches(db):
    from app.repo import analytics

    await db.executemany(
        "INSERT INTO events(tg_id, name, day, created_at) VALUES(?,?,?,?)",
        [(1, "old", "2020-01-01", "2020-01-01T00:00:00+00:00") for _ in range(5)]
        + [(1, "new", "2099-01-01", "2099-01-01T00:00:00+00:00")],
    )
    await db.executemany(
        "INSERT INTO llm_usage(tg_id, purpose, created_at) VALUES(?,?,?)",
        [(1, "old", "2020-01-01T00:00:00+00:00") for _ in range(5)]
        + [(1, "new", "2099-01-01T00:00:00+00:00")],
    )
    await db.commit()

    assert await analytics.prune_analytics(db, days=120, batch_size=2) == 10
    assert await analytics.prune_analytics(db, days=120, batch_size=2) == 0
    with pytest.raises(ValueError):
        await analytics.prune_analytics(db, days=120, batch_size=0)

    cur = await db.execute("SELECT COUNT(*) c FROM events WHERE name='old'")
    assert (await cur.fetchone())["c"] == 0
    cur = await db.execute("SELECT COUNT(*) c FROM events WHERE name='new'")
    assert (await cur.fetchone())["c"] == 1
    cur = await db.execute("SELECT COUNT(*) c FROM llm_usage WHERE purpose='old'")
    assert (await cur.fetchone())["c"] == 0
    cur = await db.execute("SELECT COUNT(*) c FROM llm_usage WHERE purpose='new'")
    assert (await cur.fetchone())["c"] == 1


async def test_overview_dau_wau_on_day(db):
    """DAU/WAU/MAU считаются по events.day (денормализация, G13)."""
    from datetime import datetime, timedelta, timezone

    from app.repo.analytics import overview

    today = (datetime.now(timezone.utc)).date().isoformat()
    far = (datetime.now(timezone.utc) - timedelta(days=40)).date().isoformat()
    await db.executemany(
        "INSERT INTO events(tg_id, name, day, created_at) VALUES(?,?,?,?)",
        [(7001, "question", today, f"{today}T09:00:00+00:00"),
         (7001, "question", far, f"{far}T09:00:00+00:00"),
         (7002, "question", far, f"{far}T09:00:00+00:00")])
    await db.commit()

    stats = await overview(db)
    assert stats["dau"] == 1, "вчера+сегодня активна только 7001"
    assert stats["wau"] == 1
    assert stats["mau"] == 1, "40 дней назад — за пределами окна MAU"
