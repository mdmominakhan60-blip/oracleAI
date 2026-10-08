"""BUS-807 (R07 G-2): нормированный /api/me/v2 за флагом r07_api_v2.

Старый /api/me — контракт текущего UI: бит-в-бит не должен измениться.
/api/me/v2 — те же данные, но нормированные объекты (profile/chart/subscription/
activity); включается только флагом r07_api_v2 (seed: default off).
"""
from __future__ import annotations

import json

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import content as content_repo  # noqa: E402
from app.services import analytics  # noqa: E402

FLAG_CODE = "r07_api_v2"


async def set_flag(db, *, is_on: bool | None = None, exists: bool = True) -> None:
    """Включить/выключить/удалить строку флага (нет строки = default off)."""
    if not exists:
        await db.execute("DELETE FROM feature_flags WHERE code=:code", {"code": FLAG_CODE})
        return
    await content_repo.set_flag(db, FLAG_CODE, is_on=is_on)


async def client_for(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test",
                       headers={"X-Dev-Key": TEST_DEV_KEY})


def as_user(user, params: dict | None = None) -> dict:
    return {"dev_user": user["tg_id"], **(params or {})}


def flatten_v2(payload: dict) -> dict:
    """Развернуть нормированный v2 в плоское пространство ключей старого /api/me."""
    flat: dict = {}
    for key, value in payload["profile"].items():
        flat[key] = value
    chart = payload["chart"]
    flat["sun"] = chart["sun"]
    flat["ascendant"] = chart["ascendant"]
    flat["chart_mode"] = chart["mode"]
    flat["chart_precision"] = chart["precision"]
    flat["chart_note"] = chart["note"]
    flat["planets"] = chart["planets"]
    flat["birth_time"] = payload["profile"]["birth_time"]
    flat["birth_time_precision"] = payload["profile"]["birth_time_precision"]
    flat["onboarding_step"] = payload["profile"]["onboarding_step"]
    flat["natal_technique"] = payload["profile"]["natal_technique"]
    sub = payload["subscription"]
    flat["plan"] = sub["plan"]
    flat["allowance"] = sub["allowance"]
    flat["questions_left"] = sub["questions_left"]
    flat["questions_total"] = sub["questions_total"]
    flat["sub_active"] = sub["sub_active"]
    flat["sub_days_left"] = sub["sub_days_left"]
    flat["entitlements"] = sub["entitlements"]
    flat["canonical_entitlements"] = sub["canonical_entitlements"]
    flat["subscription_lifecycle"] = sub["lifecycle"]
    activity = payload["activity"]
    flat["memories"] = activity["memories"]
    flat["diary_streak"] = activity["diary_streak"]
    flat["global_streak"] = activity["global_streak"]
    flat["feedback_pending"] = activity["feedback_pending"]
    flat["agents"] = payload["agents"]
    flat["reports"] = payload["reports"]
    flat["flags"] = payload["flags"]
    flat["webapp_url"] = payload["webapp_url"]
    return flat


async def test_me_v2_is_404_without_flag_row(db, user):
    """Флага нет в таблице вовсе → 404 (content.is_on default=False)."""
    await set_flag(db, exists=False)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params=as_user(user))
    assert res.status_code == 404


async def test_me_v2_is_404_when_flag_off(db, user):
    await set_flag(db, is_on=False)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params=as_user(user))
    assert res.status_code == 404


async def test_me_v2_is_200_and_normalized_when_flag_on(db, user):
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    for key in ("profile", "chart", "subscription", "activity", "agents",
                "reports", "flags", "webapp_url"):
        assert key in data, key
    profile = data["profile"]
    assert profile["tg_id"] == user["tg_id"]
    assert profile["name"] == user["name"]
    assert profile["lang"] == (user["lang"] or "ru")
    assert "questions_left" not in profile, "лимиты — зона subscription"
    sub = data["subscription"]
    assert isinstance(sub["plan"], dict) and "code" in sub["plan"]
    assert isinstance(sub["questions_total"], int)
    assert set(sub["lifecycle"]) == {"status", "period_end",
                                     "cancel_at_period_end", "grace_until"}
    assert data["flags"].get(FLAG_CODE) is True


async def test_me_v2_requires_identity(db):
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2")
    assert res.status_code == 401


async def test_me_v2_unknown_user_404(db, user):
    """С флагом on неизвестный пользователь получает обычный 404 деп-зависимостей."""
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params={"dev_user": 999999})
    assert res.status_code == 404


GOLDEN_ME_KEYS = {
    "tg_id", "name", "username", "oracle_name", "persona", "tz",
    "birth_date", "birth_city", "birth_time_known", "birth_time",
    "birth_time_precision", "onboarding_step", "natal_technique",
    "onboarded",
    "sun", "ascendant", "chart_mode", "chart_precision", "chart_note",
    "planets", "crystals", "sub_active", "sub_days_left",
    "plan", "allowance", "questions_left", "questions_total",
    "memories", "diary_streak", "global_streak",
    "morning_push", "memory_enabled", "lang", "gender",
    "entitlements", "reports", "canonical_entitlements",
    "subscription_lifecycle", "agents", "flags", "feedback_pending",
    "webapp_url",
}


async def test_me_v2_flat_matches_me_bit_for_bit(db, user):
    """Контраст-критерий: flatten(v2) == /api/me по каждому полю одного ответа."""
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        old = await client.get("/api/me", params=as_user(user))
        new = await client.get("/api/me/v2", params=as_user(user))
    assert old.status_code == 200
    assert new.status_code == 200
    old_data, new_data = old.json(), new.json()
    assert set(old_data) == GOLDEN_ME_KEYS
    flat = flatten_v2(new_data)
    for key in GOLDEN_ME_KEYS:
        assert flat.get(key) == old_data.get(key), key


async def test_me_contract_unchanged_with_v2_code(db, user):
    """Старый /api/me отдаёт тот же golden-набор ключей — контракт не тронут."""
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        res = await client.get("/api/me", params=as_user(user))
    assert res.status_code == 200
    assert set(res.json()) == GOLDEN_ME_KEYS


async def test_me_v2_tracks_miniapp_open_utm_like_me(db, user):
    """v2 — полноценная замена: X-Start-Param доезжает до miniapp_open.props.utm."""
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params=as_user(user),
                               headers={"X-Start-Param": "bc42"})
    assert res.status_code == 200
    cur = await db.execute(
        "SELECT props_json FROM events WHERE tg_id=:tg_id AND name='miniapp_open' "
        "ORDER BY created_at DESC, id DESC LIMIT 1", {"tg_id": user["tg_id"]})
    row = await cur.fetchone()
    assert row is not None
    assert json.loads(row["props_json"]) == {"utm": "bc42"}


async def test_me_v2_session_link_side_effect_live(db, user):
    """session-link мост (BUS-195) работает и с v2: session_linked в events."""
    await set_flag(db, is_on=True)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params=as_user(user),
                               headers={"X-Session-Id": "sess-bus807"})
    assert res.status_code == 200
    await analytics.drain()
    cur = await db.execute(
        "SELECT tg_id FROM events WHERE name='session_linked' AND session_id=:sid",
        {"sid": "sess-bus807"})
    row = await cur.fetchone()
    assert row is not None and row["tg_id"] == user["tg_id"]


async def test_flag_rollout_pct_respected_by_me_v2(db, user):
    """rollout_pct=0 при is_on=1 → флаг фактически выключен → 404."""
    await content_repo.set_flag(db, FLAG_CODE, is_on=True, rollout_pct=0)
    async with await client_for(db) as client:
        res = await client.get("/api/me/v2", params=as_user(user))
    assert res.status_code == 404
