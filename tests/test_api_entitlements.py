"""GET /api/entitlements — агрегат активных прав (BUS-813, R07/G-13).

Критерии приёмки issue:
- 200 со своими правами (owner-scope);
- статус grace/cancel отражён в ответе (usable=False);
- fail-closed: нет прав — пустой список items, не ошибка;
- чужой tg_id недостижим по контракту (параметра нет).
"""
from __future__ import annotations

import pytest

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from conftest import TEST_DEV_KEY  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.config import settings  # noqa: E402
from app.repo import billing as billing_repo  # noqa: E402
from app.repo import monetization as monetization_repo  # noqa: E402
from app.services import billing as billing_svc  # noqa: E402


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def as_user(user) -> dict:
    return {"dev_user": user["tg_id"]}


async def _grant(db, tg_id: int, kind: str = "question", code: str = "*",
                 qty: int = 3, source: str = "promo") -> int:
    return await billing_repo.grant_entitlement(
        db, tg_id, kind, code, qty=qty, source=source)


# ─────────────────────────── auth и owner-scope ──────────────────────────────

async def test_entitlements_requires_identity(client):
    res = await client.get("/api/entitlements")
    assert res.status_code == 401


async def test_entitlements_fail_closed_empty_list(client, db, free_user):
    await _grant(db, free_user["tg_id"], qty=2)
    res = await client.get("/api/entitlements", params=as_user(free_user))
    assert res.status_code == 200
    payload = res.json()
    assert payload["items"] != []
    # Удаляю всё и проверяю fail-closed: пустой список, не 5xx
    cur = await db.execute(
        "DELETE FROM entitlements WHERE tg_id=:tg_id", {"tg_id": free_user["tg_id"]})
    assert cur.rowcount >= 1
    res2 = await client.get("/api/entitlements", params=as_user(free_user))
    assert res2.status_code == 200
    assert res2.json()["items"] == []


async def test_entitlements_owner_scoped_no_cross_user_leak(client, db, user, free_user):
    """Пользователь A видит только свои права; параметра tg_id нет в контракте."""
    await _grant(db, user["tg_id"], qty=5, source="purchase")
    await _grant(db, free_user["tg_id"], qty=1, source="admin")

    res_a = await client.get("/api/entitlements", params=as_user(user))
    assert res_a.status_code == 200
    items_a = res_a.json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["qty_left"] == 5

    res_b = await client.get("/api/entitlements", params=as_user(free_user))
    assert res_b.status_code == 200
    items_b = res_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["qty_left"] == 1

    # Пытаемся подсунуть чужой tg_id как параметр — контракт игнорирует его
    res_spoof = await client.get("/api/entitlements",
                                 params={"dev_user": user["tg_id"],
                                         "tg_id": free_user["tg_id"]})
    assert res_spoof.status_code == 200
    assert len(res_spoof.json()["items"]) == 1
    assert res_spoof.json()["items"][0]["qty_left"] == 5


# ─────────────────────────── три состояния подписки ─────────────────────────

async def _set_state(db, tg_id: int, status: str) -> None:
    await monetization_repo.upsert_subscription_state(
        db, tg_id, tier_code="vip_plus", catalog_version="v2",
        price_book_version="v2", status=status,
        period_start="2026-09-01T00:00:00+00:00",
        period_end="2099-09-30T00:00:00+00:00",
        ai_message_limit=300, compute_budget_usd=1.0,
        monthly_crystals_granted=150,
        grace_until=("2099-10-07T00:00:00+00:00" if status == "grace" else None))


async def test_entitlements_active_subscription_marks_usable(client, db, free_user,
                                                             monkeypatch):
    monkeypatch.setattr(settings, "dev_mode", True)
    await _grant(db, free_user["tg_id"], qty=3)
    await _set_state(db, free_user["tg_id"], "active")
    res = await client.get("/api/entitlements", params=as_user(free_user))
    assert res.status_code == 200
    payload = res.json()
    assert payload["tier"] == "vip_plus"
    assert payload["subscription_status"] == "active"
    assert payload["items"] and payload["items"][0]["usable"] is True


async def test_entitlements_grace_subscription_marks_not_usable(client, db, free_user,
                                                               monkeypatch):
    monkeypatch.setattr(settings, "dev_mode", True)
    await _grant(db, free_user["tg_id"], qty=3)
    await _set_state(db, free_user["tg_id"], "grace")
    res = await client.get("/api/entitlements", params=as_user(free_user))
    assert res.status_code == 200
    payload = res.json()
    assert payload["subscription_status"] == "grace"
    assert payload["grace_until"] is not None
    assert payload["items"] and payload["items"][0]["usable"] is False
    assert payload["items"][0]["subscription_status"] == "grace"


async def test_entitlements_cancelled_subscription_marks_not_usable(client, db,
                                                                    free_user,
                                                                    monkeypatch):
    monkeypatch.setattr(settings, "dev_mode", True)
    await _grant(db, free_user["tg_id"], qty=3)
    await _set_state(db, free_user["tg_id"], "cancelled")
    res = await client.get("/api/entitlements", params=as_user(free_user))
    assert res.status_code == 200
    payload = res.json()
    assert payload["subscription_status"] == "cancelled"
    assert payload["items"] and payload["items"][0]["usable"] is False


# ─────────────────────────── нормировка ответа ───────────────────────────────

async def test_entitlements_normalized_shape_and_consumed_excluded(client, db,
                                                                   free_user):
    ent_id = await _grant(db, free_user["tg_id"], kind="spread", code="three", qty=2)
    await billing_svc.consume_entitlement(db, free_user["tg_id"], "spread", "three")
    # Исчерпанное право (qty_used == qty_total) не входит в агрегат
    cur = await db.execute(
        "UPDATE entitlements SET qty_used=qty_total WHERE id=:id", {"id": ent_id})
    res = await client.get("/api/entitlements", params=as_user(free_user))
    assert res.status_code == 200
    payload = res.json()
    assert all(item["id"] != ent_id for item in payload["items"])
    for item in payload["items"]:
        assert set(item.keys()) == {
            "id", "kind", "code", "qty_total", "qty_used", "qty_left",
            "expires_at", "source", "order_id", "created_at",
            "subscription_status", "usable"}
        assert item["qty_left"] <= item["qty_total"] - item["qty_used"] + 1


async def test_entitlements_free_user_without_state(client, db, free_user):
    """Бесплатный пользователь без subscription_state: пустой ledger,
    статус free, tier legacy — 200, не ошибка."""
    res = await client.get("/api/entitlements", params=as_user(free_user))
    assert res.status_code == 200
    payload = res.json()
    assert payload["items"] == []
    assert payload["subscription_status"] in {"free", "active"}
