"""BUS-310: матрица компенсаций — операторские подарки и каппинг grant.

Матрица BUS-284 §4.2: каждый порог покрыт тестом (403/400/409-ветки включительно).
Машин-readable ошибки (тред BUS-312 LTV3): FE строит форму по gift_eligibility,
не по текстовым сообщениям после submit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import growth, users  # noqa: E402


@pytest.fixture
async def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


async def _add_role(db, tg_id: int, role: str):
    """Роль админа в панели: owner (.env ADMIN_ID=1), admin/support — записью."""
    await db.execute(
        "INSERT INTO admins(tg_id, role, title, added_by, created_at) "
        "VALUES(:tg_id, :role, :role, 1, NOW()) "
        "ON CONFLICT (tg_id) DO UPDATE SET role=EXCLUDED.role",
        {"tg_id": tg_id, "role": role})
    await db.commit()


async def _seed_op_batch(db, days: int, count: int = 2,
                         batch: str = "op_a_2026-09") -> list[str]:
    return await growth.create_codes(db, count, kind="plan_days", days=days,
                                     plan_code="trial", batch=batch, max_uses=1,
                                     valid_days=30)


# ─────────────────────────── role-gating подарков ────────────────────────────

async def test_gift_support_only_3_days(client, db):
    """support: 3д — ок; 7д — 403 machine-readable, даже при наличии кодов."""
    await _add_role(db, 42, "support")
    codes = await _seed_op_batch(db, 3)
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 42},
                            json={"days": 3, "reason": "сбой доставки"})
    assert res.status_code == 200
    # Выбор кода не гарантирован по порядку вставки — сверяем множеством партии.
    assert res.json()["code"] in set(codes)

    await _seed_op_batch(db, 7, batch="op_b_2026-09")
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 42},
                            json={"days": 7, "reason": "x"})
    assert res.status_code == 403
    err = res.json()["detail"]["error"]
    assert err["code"] == "gift_days_not_allowed"
    assert err["allowed_days"] == [3]


async def test_gift_admin_matrix_3_7_10_not_14(client, db):
    """admin: 3/7/10 — ок; 14 — owner-only (усиление PB-3)."""
    await _add_role(db, 42, "admin")
    # Разным клиенткам: анти-абьюз 60д даёт одну подарочную компенсацию
    # на клиента за окно — три подарка одной упёрлись бы в 409.
    for n, days in enumerate((3, 7, 10)):
        tg = 2000 + n
        await users.ensure(db, tg, "Клиентка", f"u{tg}")
        await _seed_op_batch(db, days, count=1, batch=f"op_t{days}_2026-09")
        res = await client.post(f"/api/admin/users/{tg}/gift",
                                params={"dev_user": 42},
                                json={"days": days, "reason": "компенсация"})
        assert res.status_code == 200, f"admin {days}д должен пройти"
    await _seed_op_batch(db, 14, batch="op_t14_2026-09")
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 42},
                            json={"days": 14, "reason": "x"})
    assert res.status_code == 403
    assert res.json()["detail"]["error"]["code"] == "gift_days_not_allowed"


async def test_gift_owner_14_days(client, db):
    """owner (dev_user=1 = ADMIN_ID): 14д доступен."""
    await _seed_op_batch(db, 14, batch="op_a_2026-09")
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                            json={"days": 14, "reason": "VIP-удержание"})
    assert res.status_code == 200
    assert res.json()["days"] == 14


async def test_gift_support_role_has_no_promo_right_needed(client, db):
    """support без общего права promo выдаёт подарок — endpoint сам по себе."""
    await _add_role(db, 42, "support")
    row = await db.execute("SELECT 1 FROM admins WHERE tg_id=42 AND role='support'")
    assert await row.fetchone()
    await _seed_op_batch(db, 3)
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 42},
                            json={"days": 3, "reason": "r"})
    assert res.status_code == 200


async def test_gift_no_role_403(client, db):
    """Без роли панели — 403 (require crm:write)."""
    await _seed_op_batch(db, 3)
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 999},
                            json={"days": 3, "reason": "r"})
    assert res.status_code == 403


# ───────────────────────── причина и валидация ───────────────────────────────

async def test_gift_requires_reason(client, db):
    """Причина обязательна (§4.1.4): без reason — 422 (pydantic min_length)."""
    await _seed_op_batch(db, 3)
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                            json={"days": 3})
    assert res.status_code == 422
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                            json={"days": 3, "reason": ""})
    assert res.status_code == 422


async def test_gift_unknown_user_404(client, db):
    res = await client.post("/api/admin/users/424242/gift", params={"dev_user": 1},
                            json={"days": 3, "reason": "r"})
    assert res.status_code == 404


async def test_gift_batch_empty_409(client, db):
    """Партия исчерпана — machine-readable gift_batch_empty."""
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                            json={"days": 3, "reason": "r"})
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "gift_batch_empty"


# ───────────────────────────── анти-абьюз 60/90 ──────────────────────────────

async def test_gift_cooldown_60_days_machine_error(client, db):
    """Второй подарок в окне 60д — 409 gift_cooldown с next_available_at."""
    await _seed_op_batch(db, 3, count=3)
    first = await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                              json={"days": 3, "reason": "первый"})
    assert first.status_code == 200
    second = await client.post("/api/admin/users/1001/gift",
                               params={"dev_user": 1},
                               json={"days": 3, "reason": "второй"})
    assert second.status_code == 409
    err = second.json()["detail"]["error"]
    assert err["code"] == "gift_cooldown"
    assert err["next_available_at"]
    # окно: последний подарок + 60 дней
    expected = datetime.now(timezone.utc) + timedelta(days=60)
    got = datetime.fromisoformat(err["next_available_at"])
    assert abs((got - expected).total_seconds()) < 120


async def test_gift_eligibility_reports_cooldown(client, db):
    """GET eligibility: до выдачи eligible=true; после — cooldown c датой."""
    await _seed_op_batch(db, 3, count=2)
    res = await client.get("/api/admin/users/1001/gift/eligibility",
                           params={"dev_user": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["eligible"] is True
    assert body["allowed_days"] == [3, 7, 10, 14]  # owner

    await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                      json={"days": 3, "reason": "r"})
    res = await client.get("/api/admin/users/1001/gift/eligibility",
                           params={"dev_user": 1})
    body = res.json()
    assert body["eligible"] is False
    assert body["cooldown"] is True
    assert body["next_available_at"]


async def test_gift_eligibility_role_allowed_days(client, db):
    await _add_role(db, 42, "support")
    res = await client.get("/api/admin/users/1001/gift/eligibility",
                           params={"dev_user": 42})
    assert res.json()["allowed_days"] == [3]
    await _add_role(db, 42, "admin")
    res = await client.get("/api/admin/users/1001/gift/eligibility",
                           params={"dev_user": 42})
    assert res.json()["allowed_days"] == [3, 7, 10]


async def test_gift_redemption_outside_endpoint_blocks_too(client, db):
    """Код, активированный клиенткой напрямую из партии op_*, тоже держит окно."""
    codes = await _seed_op_batch(db, 3, count=1)
    await db.execute(
        "INSERT INTO promo_redemptions(code, tg_id, created_at) "
        "VALUES(:code, 1001, :now)",
        {"code": codes[0], "now": datetime.now(timezone.utc).isoformat()})
    await db.commit()
    res = await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                            json={"days": 3, "reason": "r"})
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "gift_cooldown"


# ─────────────────────── каппинг grant по роли (§4.2) ────────────────────────

async def test_grant_admin_plan_days_cap_7(client, db):
    """admin: план ≤7д ок; 8д — 403 grant_days_cap."""
    await _add_role(db, 42, "admin")
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 42},
                            json={"kind": "plan", "days": 7, "reason": "инцидент"})
    assert res.status_code == 200
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 42},
                            json={"kind": "plan", "days": 8, "reason": "x"})
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "grant_days_cap"
    assert res.json()["detail"]["max_days"] == 7


async def test_grant_owner_plan_days_cap_30(client, db):
    """owner: до 30д ок; 31д — 403."""
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 1},
                            json={"kind": "plan", "days": 30, "reason": "r"})
    assert res.status_code == 200
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 1},
                            json={"kind": "plan", "days": 31, "reason": "x"})
    assert res.status_code == 403
    assert res.json()["detail"]["max_days"] == 30


async def test_grant_support_403(client, db):
    """support без права grants — 403 на весь grant endpoint (матрица §4.2)."""
    await _add_role(db, 42, "support")
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 42},
                            json={"kind": "plan", "days": 3, "reason": "r"})
    assert res.status_code == 403


async def test_grant_admin_crystals_cap_30(client, db):
    """Кристаллы: admin ≤30✦; >30✦ — только owner."""
    await _add_role(db, 42, "admin")
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 42},
                            json={"kind": "crystals", "qty": 30, "reason": "r"})
    assert res.status_code == 200
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 42},
                            json={"kind": "crystals", "qty": 31, "reason": "x"})
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "grant_crystals_cap"
    res = await client.post("/api/admin/users/1001/grant", params={"dev_user": 1},
                            json={"kind": "crystals", "qty": 31, "reason": "owner"})
    assert res.status_code == 200


# ─────────────────────────────── аудит ───────────────────────────────────────

async def test_gift_audit_written_with_reason(client, db):
    """user.gift в аудите содержит code/days/reason — объяснимость задним числом."""
    await _seed_op_batch(db, 3)
    await client.post("/api/admin/users/1001/gift", params={"dev_user": 1},
                      json={"days": 3, "reason": "сбой канала PB-5"})
    cur = await db.execute(
        "SELECT action, payload_json FROM admin_audit "
        "WHERE action='user.gift' AND target='1001' ORDER BY id DESC LIMIT 1")
    row = await cur.fetchone()
    assert row, "аудит user.gift не записан"
    import json
    payload = json.loads(row["payload_json"])
    assert payload["days"] == 3 and payload["code"]
    assert payload["reason"] == "сбой канала PB-5"


# ─────────────────────────── отчёт по партиям op_* ───────────────────────────

async def test_op_report_requires_dashboard_only(client, db):
    """Право dashboard (не promo): support видит отчёт KPI."""
    await _add_role(db, 42, "support")
    res = await client.get("/api/admin/promo/op-report", params={"dev_user": 42})
    assert res.status_code == 200


async def test_op_report_redemption_and_conversion(client, db):
    """§4.3: redemption rate по кодам, конверсия — оплатившие после активации."""
    codes = await _seed_op_batch(db, 7, count=2, batch="op_a_2026-09")
    now = datetime.now(timezone.utc).isoformat()
    # код 1: активировала, оплатила; код 2: не активирован.
    # Прямая вставка redemption — инкремент used_count на себе (обычно это
    # делает redeem_promo): used в отчёте считается по promo_codes.
    await db.execute(
        "INSERT INTO promo_redemptions(code, tg_id, created_at) "
        "VALUES(:code, 1001, :now)", {"code": codes[0], "now": now})
    await db.execute(
        "UPDATE promo_codes SET used_count=1 WHERE code=:code",
        {"code": codes[0]})
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, amount_stars, status, "
        "created_at, paid_at) VALUES(1001, 'plan', 'vip', 499, 'paid', "
        ":now, :now)", {"now": now})
    await db.commit()
    res = await client.get("/api/admin/promo/op-report", params={"dev_user": 1})
    batches = {b["batch"]: b for b in res.json()["batches"]}
    rep = batches["op_a_2026-09"]
    assert rep["codes"] == 2 and rep["used"] == 1
    assert rep["redeemers"] == 1
    assert rep["redemption_rate"] == 0.5
    assert rep["converted"] == 1 and rep["conversion_rate"] == 1.0
