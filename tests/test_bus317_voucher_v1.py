"""BUS-317: минимальный v1 канала маркетплейс-ваучеров.

G1 — CSV-экспорт партии из админки; G2 — точный поиск кода для CS;
G3 — kill switch is_active (отзыв партии/кода) с проверкой в redeem.
Ни один тест не касается платёжного пути: redeem_promo — это активация
ваучера мимо покупки, миграция is_active не меняет оплату.
"""
from __future__ import annotations

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import growth  # noqa: E402
from app.services import billing as svc  # noqa: E402


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


# ──────────────────────────── G3: отзыв кода ─────────────────────────────────

async def test_redeem_refuses_revoked_code(db, user):
    """is_active=0 → redeem_promo возвращает None, код не сжигается и не выдаёт."""
    codes = await growth.create_codes(db, 1, days=30, plan_code="vip",
                                      batch="mpl_test_2026-09")
    await db.execute("UPDATE promo_codes SET is_active=0 WHERE batch='mpl_test_2026-09'")
    await db.commit()
    assert await svc.redeem_promo(db, user["tg_id"], codes[0]) is None
    row = await growth.get_code(db, codes[0])
    assert row["used_count"] in (None, 0), "отозванный код засчитан как использованный"


async def test_redeem_after_restore_works(db, user):
    """Возврат в строй (is_active=1) снова делает код активируемым."""
    codes = await growth.create_codes(db, 1, days=30, plan_code="vip",
                                      batch="mpl_test_2026-09")
    await db.execute("UPDATE promo_codes SET is_active=0")
    await db.commit()
    await growth.set_codes_active(db, batch="mpl_test_2026-09", active=True)
    result = await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert result and result["granted"]["kind"] == "plan"


async def test_set_codes_active_requires_single_target(db):
    codes = await growth.create_codes(db, 2, days=30, batch="mpl_x")
    await growth.set_codes_active(db, code=codes[0], active=False)
    row = await growth.get_code(db, codes[0])
    assert row["is_active"] == 0
    other = await growth.get_code(db, codes[1])
    assert other["is_active"] != 0, "отозвался код не из таргета"


async def test_batch_revoke_covers_all_codes(db):
    codes = await growth.create_codes(db, 3, days=30, batch="mpl_y")
    changed = await growth.set_codes_active(db, batch="mpl_y", active=False)
    assert changed == 3
    actives = [int((await growth.get_code(db, c))["is_active"]) for c in codes]
    assert actives == [0, 0, 0]


# ──────────────────────────── G1: CSV-экспорт ────────────────────────────────

async def test_promo_export_csv(client, db):
    await growth.create_codes(db, 3, days=30, plan_code="vip",
                              batch="mpl_csv_2026-09", sku="VOUCHER-30")
    res = await client.get("/api/admin/promo/export",
                           params={"dev_user": 1, "batch": "mpl_csv_2026-09"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers.get("content-disposition", "")
    assert "no-store" in res.headers.get("cache-control", "")
    lines = res.text.strip().split("\n")
    assert lines[0].split(",")[0] == "code"
    assert len(lines) == 4, f"ожидались шапка + 3 кода, получено {len(lines)}"
    # коды в CSV валидны — соответствуют promo_codes в БД
    db_codes = {r["code"] for r in await growth.list_codes(db, batch="mpl_csv_2026-09")}
    csv_codes = {line.split(",")[0] for line in lines[1:]}
    assert csv_codes == db_codes


async def test_promo_export_marks_revoked(client, db):
    codes = await growth.create_codes(db, 2, days=30, batch="mpl_rev")
    await growth.set_codes_active(db, code=codes[0], active=False)
    res = await client.get("/api/admin/promo/export",
                           params={"dev_user": 1, "batch": "mpl_rev"})
    rows = {line.split(",")[0]: line.split(",")[-1]
            for line in res.text.strip().split("\n")[1:]}
    assert rows[codes[0]] == "0" and rows[codes[1]] == "1"


# ──────────────────────────── G2: поиск кода ─────────────────────────────────

async def test_admin_promo_search_by_code(client, db):
    created = await growth.create_codes(db, 2, days=30, batch="mpl_search")
    res = await client.get("/api/admin/promo",
                           params={"dev_user": 1, "code": created[1]})
    assert res.status_code == 200
    codes = res.json()["codes"]
    assert len(codes) == 1 and codes[0]["code"] == created[1]


async def test_admin_promo_search_is_case_insensitive(client, db):
    created = await growth.create_codes(db, 1, days=30, batch="mpl_search")
    res = await client.get("/api/admin/promo",
                           params={"dev_user": 1, "code": created[0].lower()})
    assert res.status_code == 200
    assert [c["code"] for c in res.json()["codes"]] == [created[0]]


async def test_admin_promo_requires_promo_grant(client, db):
    """G1/G2/G3 — админ-эндпоинты под permission promo: без роли — 403."""
    res = await client.get("/api/admin/promo/export",
                           params={"dev_user": 42, "batch": "mpl_x"})
    assert res.status_code == 403
    res = await client.post("/api/admin/promo/state", params={"dev_user": 42},
                            json={"code": "X", "active": False})
    assert res.status_code == 403


# ─────────────────────── G3 API: state endpoint + audit ──────────────────────

async def test_admin_promo_state_endpoint(client, db):
    codes = await growth.create_codes(db, 1, days=30, batch="mpl_state")
    res = await client.post("/api/admin/promo/state", params={"dev_user": 1},
                            json={"code": codes[0], "active": False})
    assert res.status_code == 200
    assert (await growth.get_code(db, codes[0]))["is_active"] == 0
    res = await client.post("/api/admin/promo/state", params={"dev_user": 1},
                            json={"code": codes[0], "active": True})
    assert res.status_code == 200
    assert (await growth.get_code(db, codes[0]))["is_active"] == 1


async def test_admin_promo_state_unknown_target_404(client, db):
    res = await client.post("/api/admin/promo/state", params={"dev_user": 1},
                            json={"code": "НЕТТАКОГО", "active": False})
    assert res.status_code == 404


async def test_admin_promo_state_needs_one_target(client, db):
    res = await client.post("/api/admin/promo/state", params={"dev_user": 1},
                            json={"active": False})
    assert res.status_code == 422
    res = await client.post("/api/admin/promo/state", params={"dev_user": 1},
                            json={"batch": "a", "code": "b", "active": False})
    assert res.status_code == 422


async def test_admin_promo_state_audited(client, db):
    from app.repo import admin as admin_repo

    codes = await growth.create_codes(db, 1, days=30, batch="mpl_audit")
    await client.post("/api/admin/promo/state", params={"dev_user": 1},
                      json={"code": codes[0], "active": False})
    await client.get("/api/admin/promo/export",
                     params={"dev_user": 1, "batch": "mpl_audit"})
    log = await admin_repo.audit_log(db, limit=50)
    actions = [r["action"] for r in log]
    assert "promo.set_state" in actions and "promo.export" in actions


# ────────────────────────── миграция: идемпотентность ────────────────────────

def test_migration_0011_is_idempotent_sql():
    from pathlib import Path

    source = Path("alembic/versions/0011_promo_is_active.py").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS" in source, "повторный прогон миграции упадёт"
    assert "DROP COLUMN IF EXISTS" in source, "downgrade должен быть идемпотентен"


async def test_schema_has_is_active_column(db):
    cur = await db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='promo_codes' AND column_name='is_active'")
    assert (await cur.fetchone()) is not None
