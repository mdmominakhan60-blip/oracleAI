from __future__ import annotations

import json
from pathlib import Path

from app.repo import analytics as analytics_repo
from app.services import analytics
from scripts.validate_monetization_assumptions import validate


ASSUMPTIONS = Path(__file__).resolve().parents[1] / "docs" / "MONETIZATION_ASSUMPTIONS.csv"


async def test_monetization_event_filters_unapproved_props(db):
    assert await analytics.track_monetization(
        db,
        analytics.E_PAYWALL_CHOICE,
        1001,
        surface="miniapp",
        sku="report_natal",
        channel="miniapp",
        price_variant="core_a",
        credit_band_name="large",
        result_category="report",
        reason="question_text_should_not_pass",
    )
    cur = await db.execute(
        "SELECT props_json FROM events WHERE tg_id=? AND name=?",
        (1001, analytics.E_PAYWALL_CHOICE),
    )
    props = json.loads((await cur.fetchone())["props_json"])
    assert props == {
        "sku": "report_natal",
        "channel": "miniapp",
        "price_variant": "core_a",
        "credit_band": "large",
        "result_category": "report",
    }
    assert not await analytics.track_monetization(
        db, "client_created_revenue_event", 1001, surface="miniapp",
    )


async def test_monetization_dashboard_does_not_fake_net_revenue(db):
    await analytics.track_monetization(
        db, analytics.E_CREDIT_PACK_PAID, 1001,
        surface="bot", sku="crystals_250", channel="bot", credit_band_name="large",
    )
    await analytics.track_monetization(
        db, analytics.E_CREDIT_SPENT, 1001,
        surface="bot", sku="report_natal", channel="bot",
        credit_band_name="medium", result_category="report",
    )
    kpis = await analytics_repo.monetization_kpis(db, days=30)
    assert kpis["credit_pack_paid"] == 1
    assert kpis["credit_spent"] == 1
    assert kpis["net_revenue_estimate"] is None
    assert kpis["contribution_margin_estimate"] is None
    assert kpis["status"] == "estimated_requires_settlement_inputs"


def test_monetization_assumptions_contract_is_valid():
    assert validate(ASSUMPTIONS) == []


async def test_product_cost_events_are_private_and_aggregate_by_product(db):
    await analytics_repo.record_product_cost_event(
        db,
        event_kind="llm",
        tg_id=1001,
        sku="report:natal",
        catalog_version="catalog-v1",
        channel="miniapp",
        purpose="report:natal",
        provider="openai",
        model="gpt-5-mini",
        result_category="report",
        input_tokens=100,
        output_tokens=50,
        retry_count=1,
        latency_ms=42,
        cost_usd=0.123456,
        reference_id="report:7",
    )
    await analytics_repo.record_product_cost_event(
        db,
        event_kind="delivery",
        tg_id=1001,
        sku="report:natal",
        channel="miniapp",
        result_category="report",
        status="delivered",
        reference_id="report:7",
    )
    await analytics_repo.record_product_cost_event(
        db,
        event_kind="refund",
        tg_id=1001,
        sku="report:natal",
        channel="miniapp",
        result_category="report",
        status="refunded",
        reference_id="order:9",
        order_id=9,
        reason="provider_refund",
    )
    kpis = await analytics_repo.product_cost_kpis(db, days=30)
    assert kpis["event_count"] == 3
    assert kpis["costed_event_count"] == 1
    assert kpis["cost_coverage_pct"] == 33.3
    row = kpis["by_product"][0]
    assert row["sku"] == "report:natal"
    assert row["channel"] == "miniapp"
    assert row["retry_count"] == 1
    assert row["deliveries"] == 1
    assert row["failures"] == 0
    assert row["variable_cost_usd"] == 0.123456
    assert kpis["net_revenue_estimate"] is None
    assert kpis["contribution_margin_estimate"] is None


async def test_product_cost_writer_rejects_unknown_dimensions_and_drops_free_text(db):
    import pytest

    with pytest.raises(ValueError):
        await analytics_repo.record_product_cost_event(
            db, event_kind="revenue", sku="report:natal")
    with pytest.raises(ValueError):
        await analytics_repo.record_product_cost_event(
            db, event_kind="llm", sku="report:natal", channel="client")

    await analytics_repo.record_product_cost_event(
        db,
        event_kind="support",
        sku="support:ticket",
        channel="system",
        purpose="support:refund",
        result_category="report",
        reason="support_request",
        reference_id="ticket:7",
    )
    cur = await db.execute(
        "SELECT sku, purpose, reason, reference_id FROM product_cost_events "
        "WHERE event_kind='support'")
    row = await cur.fetchone()
    assert dict(row) == {
        "sku": "support:ticket",
        "purpose": "support:refund",
        "reason": "support_request",
        "reference_id": "ticket:7",
    }


async def test_llm_usage_is_attributed_to_product_context(db):
    from app.core import llm, product_cost

    with product_cost.context(
            sku="chat:oracle", catalog_version="catalog-v1", channel="bot",
            result_category="question", reference_id="thread:12"):
        await llm.record_usage(
            db,
            provider="openai",
            model="gpt-5-mini",
            purpose="answer:oracle",
            tg_id=1001,
            prompt_tokens=1000,
            completion_tokens=250,
            retry_count=2,
            latency_ms=1234,
            ok=True,
        )
    cur = await db.execute(
        "SELECT tg_id, event_kind, sku, catalog_version, channel, purpose, "
        "result_category, retry_count, latency_ms, cost_usd, reference_id "
        "FROM product_cost_events WHERE tg_id=?",
        (1001,),
    )
    row = dict(await cur.fetchone())
    assert row["event_kind"] == "llm"
    assert row["sku"] == "chat:oracle"
    assert row["catalog_version"] == "catalog-v1"
    assert row["channel"] == "bot"
    assert row["purpose"] == "answer:oracle"
    assert row["result_category"] == "question"
    assert row["retry_count"] == 2
    assert row["latency_ms"] == 1234
    assert row["cost_usd"] > 0
    assert row["reference_id"] == "thread:12"


async def test_product_cost_events_follow_analytics_retention(db):
    await analytics_repo.record_product_cost_event(
        db, event_kind="support", tg_id=1001, sku="support:ticket",
        channel="system", purpose="support:refund", reason="old_event",
    )
    await db.execute(
        "UPDATE product_cost_events SET created_at=? WHERE tg_id=?",
        ("2020-01-01T00:00:00+00:00", 1001),
    )
    await db.commit()
    removed = await analytics_repo.prune_analytics(db, days=30, batch_size=1)
    assert removed >= 1
    cur = await db.execute(
        "SELECT COUNT(*) FROM product_cost_events WHERE tg_id=?", (1001,))
    assert (await cur.fetchone())[0] == 0


async def test_product_cost_drops_free_form_reference_and_reason(db):
    await analytics_repo.record_product_cost_event(
        db, event_kind="support", tg_id=1002, sku="support:ticket",
        channel="system", purpose="support:refund",
        reference_id="ticket:7?question=what_is_my_future",
        reason="пользователь сообщил личный текст с birth date",
    )
    cur = await db.execute(
        "SELECT reference_id, reason FROM product_cost_events WHERE tg_id=?",
        (1002,),
    )
    row = dict(await cur.fetchone())
    assert row["reference_id"] is None
    assert row["reason"] is None


async def test_product_cost_gross_booking_is_attributed_by_sku_and_channel(db):
    from app.data.session import utcnow

    now = utcnow()
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, amount_stars, status, surface, paid_at, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (1001, "product", "report:natal", 100, "paid", "bot", now, now),
    )
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, amount_stars, status, surface, paid_at, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (1002, "product", "report:natal", 50, "paid", "miniapp", now, now),
    )
    await db.commit()
    for channel in ("bot", "miniapp"):
        await analytics_repo.record_product_cost_event(
            db, event_kind="delivery", sku="report:natal", channel=channel,
            result_category="report", status="delivered",
        )
    kpis = await analytics_repo.product_cost_kpis(db, days=30)
    by_channel = {
        row["channel"]: row["gross_booking_stars"]
        for row in kpis["by_product"]
        if row["sku"] == "report:natal"
    }
    assert by_channel == {"bot": 100, "miniapp": 50}
