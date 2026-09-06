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
from app.repo import growth, users  # noqa: E402
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
    """is_active=0 → redeem_promo отказывает (reason=revoked), код не сжигается."""
    codes = await growth.create_codes(db, 1, days=30, plan_code="vip",
                                      batch="mpl_test_2026-09")
    await db.execute("UPDATE promo_codes SET is_active=0 WHERE batch='mpl_test_2026-09'")
    await db.commit()
    with pytest.raises(svc.PromoRedeemRefused) as excinfo:
        await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert excinfo.value.reason == "revoked"
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


# ──────────────── B2: различимые отказы redeem (BUS-351) ─────────────────────

async def test_b2_unknown_code_404_vs_used_409(client, db, user):
    """API различает «код не существует» (404) и «уже использован» (409)."""
    codes = await growth.create_codes(db, 1, days=30, batch="mpl_b2")
    res = await client.post("/api/shop/promo", params={"dev_user": user["tg_id"]},
                            json={"code": "NOPE0000"})
    assert res.status_code == 404

    first = await client.post("/api/shop/promo",
                              params={"dev_user": user["tg_id"]},
                              json={"code": codes[0]})
    assert first.status_code == 200
    again = await client.post("/api/shop/promo",
                              params={"dev_user": user["tg_id"]},
                              json={"code": codes[0]})
    assert again.status_code == 409
    detail = again.json()["detail"]
    assert detail == "Ты уже активировала этот код ✨", \
        f"отказ already_redeemed должен быть конкретным, пришло: {detail}"


async def test_b2_expired_and_revoked_distinct(client, db, user):
    """expired и revoked — разные причины отказа, код не сжигается ни в одном случае."""
    codes = await growth.create_codes(db, 1, kind="plan_days", days=30,
                                      valid_days=1, batch="mpl_b2_expired")
    await db.execute("UPDATE promo_codes SET expires_at='2000-01-01T00:00:00Z' "
                     "WHERE batch='mpl_b2_expired'")
    await db.commit()
    with pytest.raises(svc.PromoRedeemRefused) as e:
        await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert e.value.reason == "expired"
    assert (await growth.get_code(db, codes[0]))["used_count"] in (None, 0)

    revoked = await growth.create_codes(db, 1, days=30, batch="mpl_b2_revoked")
    await growth.set_codes_active(db, batch="mpl_b2_revoked", active=False)
    with pytest.raises(svc.PromoRedeemRefused) as e:
        await svc.redeem_promo(db, user["tg_id"], revoked[0])
    assert e.value.reason == "revoked"


async def test_b2_exhausted_when_uses_run_out(db, user):
    """max_uses исчерпан другим человеком → для нового юзера reason=exhausted."""
    codes = await growth.create_codes(db, 1, days=30, batch="mpl_b2_exh",
                                      max_uses=1)
    await svc.redeem_promo(db, 1001, codes[0])
    await users.ensure(db, 2002, "Другая")
    with pytest.raises(svc.PromoRedeemRefused) as e:
        await svc.redeem_promo(db, 2002, codes[0])
    assert e.value.reason == "exhausted"


async def test_b2_promo_refusal_copy_known_reasons():
    from app.services.billing import promo_refusal_text

    texts = {r: promo_refusal_text(r) for r in
             ("unknown_code", "expired", "revoked", "exhausted", "already_redeemed")}
    assert len(set(texts.values())) == 5, "все причины имеют различимые тексты"
    assert promo_refusal_text("no_such_reason") != texts["unknown_code"], \
        "неизвестная причина — нейтральный текст"


async def test_b2_api_refusal_texts_differ(client, db, user):
    """detail в HTTP-ответе различим по состояниям (CS-маппинг B2)."""
    res404 = await client.post("/api/shop/promo",
                               params={"dev_user": user["tg_id"]},
                               json={"code": "NOPE1111"})
    codes = await growth.create_codes(db, 1, days=30, batch="mpl_b2_txt")
    await growth.set_codes_active(db, batch="mpl_b2_txt", active=False)
    res409revoked = await client.post("/api/shop/promo",
                                      params={"dev_user": user["tg_id"]},
                                      json={"code": codes[0]})
    assert res404.json()["detail"] != res409revoked.json()["detail"]


# ──────────────── B3: deep-link подтверждение всех kind (BUS-351) ────────────

async def _deep_link_grant(db, tg_id: int, code: str, monkeypatch) -> list[str]:
    """Прогоняет start_deeplink с ваучером, возвращает ответы бота."""
    import app.bot.onboarding as onb

    class _User:
        id = tg_id
        first_name = "Тест"
        username = None
        language_code = "ru"

    class _Msg:
        from_user = _User()
        text = f"/start {code}"
        args = f" {code}"
        replied: list[str] = []

        async def answer(self, text: str = "", **_):
            self.replied.append(text)
            return self

    class _Cmd:
        args = code

    msg = _Msg()
    state = _FakeState()
    await onb.start_deeplink(msg, _Cmd(), state, db)
    return msg.replied


class _FakeState:
    """FSM-заглушка: start_deeplink вызовет _begin → state.clear()."""

    async def clear(self):
        return None

    async def get_data(self):
        return {}

    async def set_state(self, *_):
        return None


async def test_b3_deeplink_crystals_voucher_confirmed(db, user, monkeypatch):
    """mpl_sku1_crystals100-тип (kind=crystals): подтверждение выдачи показано."""
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=100,
                                      batch="mpl_d1")
    replied = await _deep_link_grant(db, user["tg_id"], codes[0], monkeypatch)
    assert any("100" in t and ("Кристалл" in t or "Crystals" in t)
               for t in replied), \
        f"подтверждение выдачи crystals не показано: {replied}"


async def test_b3_deeplink_trial_voucher_confirmed(db, user, monkeypatch):
    """mpl_sku2_trial7d-тип (plan_days/trial 7д): подтверждение выдачи показано."""
    codes = await growth.create_codes(db, 1, kind="plan_days", days=7,
                                      plan_code="trial", batch="mpl_d2")
    replied = await _deep_link_grant(db, user["tg_id"], codes[0], monkeypatch)
    assert any("7" in t and "дней" in t for t in replied), \
        f"подтверждение выдачи trial-плана не показано: {replied}"


async def test_b3_deeplink_bad_code_gives_distinct_refusal(db, user):
    """Неверный код в deep-link — различимый отказ, не молчание."""
    replied = await _deep_link_grant(db, user["tg_id"], "NOPE2222", None)
    assert any("не найден" in t or "not found" in t for t in replied), \
        f"отказ не различим: {replied}"
