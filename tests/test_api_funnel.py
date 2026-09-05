"""Funnel-события (EXP-004): приём, идемпотентность, allowlist, границы.

Проверяем контракт публичного эндпоинта /api/funnel/events и поведение
track_funnel: одно (session_id, name) на сессию, без PII, allowlist имён.
"""
from __future__ import annotations

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import analytics as analytics_repo  # noqa: E402


SID = "sess-0123456789abcdef"


async def _count(db, name: str, sid: str = SID) -> int:
    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE name=:name AND session_id=:sid",
        {"name": name, "sid": sid})
    return (await cur.fetchone())["c"]


async def test_track_funnel_idempotent_per_session(db):
    """Повтор события той же сессии не создаёт дубль (ON CONFLICT DO NOTHING)."""
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id=SID,
        source="organic", medium="organic", path="/landing") is True
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id=SID,
        source="organic", medium="organic", path="/landing") is False
    assert await _count(db, analytics_repo.E_VISIT) == 1


async def test_track_funnel_same_name_different_sessions(db):
    """Дедупликация по сессии: две сессии — две записи одного события."""
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id=SID) is True
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id=SID + "2") is True
    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE name=:name",
        {"name": analytics_repo.E_VISIT})
    assert (await cur.fetchone())["c"] == 2


async def test_track_funnel_rejects_unknown_name_and_bad_sid(db):
    """Allowlist имён и формат sid: произвольное событие от клиента не пишется."""
    assert await analytics_repo.track_funnel(
        db, name="arbitrary_event", session_id=SID) is False
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id="bad sid!with spaces") is False
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id="x" * 65) is False
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id="") is False


async def test_track_funnel_props_are_categorical_no_pii(db):
    """В props попадают только allowlist-ключи; свободный текст отбрасывается."""
    await analytics_repo.track_funnel(
        db, name=analytics_repo.E_VISIT, session_id=SID,
        campaign="exp_004.sept", path="/landing/en")
    cur = await db.execute(
        "SELECT props_json, surface, session_id, day FROM events "
        "WHERE name=:name AND session_id=:sid",
        {"name": analytics_repo.E_VISIT, "sid": SID})
    row = await cur.fetchone()
    assert row["surface"] == "web"
    assert row["session_id"] == SID
    assert row["day"] and len(row["day"]) == 10
    import json
    props = json.loads(row["props_json"])
    assert props["source"] == "direct"
    assert props["campaign"] == "exp_004.sept"
    assert props["path"] == "/landing/en"
    # PII-подобное значение не должно пройти валидацию пути/кампании.
    await analytics_repo.track_funnel(
        db, name=analytics_repo.E_SIGNUP, session_id=SID + "3",
        campaign="user@mail.com <script>", path="/..%2F.env?email=me@x.io")
    cur = await db.execute(
        "SELECT props_json FROM events WHERE name=:name AND session_id=:sid",
        {"name": analytics_repo.E_SIGNUP, "sid": SID + "3"})
    props = json.loads((await cur.fetchone())["props_json"])
    assert "campaign" not in props
    assert "path" not in props


async def test_track_funnel_activation_action_allowlist(db):
    """activation без action или с несписочным action — отказ, не запись."""
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_ACTIVATION, session_id=SID,
        activation_action="first_question") is True
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_ACTIVATION, session_id=SID + "4",
        activation_action="arbitrary nonsense") is False
    assert await analytics_repo.track_funnel(
        db, name=analytics_repo.E_ACTIVATION, session_id=SID + "5") is False
    assert await _count(db, analytics_repo.E_ACTIVATION) == 1


# ─────────────────────────────── HTTP-контракт ───────────────────────────────

@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


async def test_api_accepts_funnel_batch_and_is_idempotent(client, db):
    payload = {"events": [
        {"name": "visit", "session_id": SID, "source": "organic",
         "medium": "organic", "path": "/landing"},
        {"name": "signup", "session_id": SID, "signup_method": "telegram"},
        {"name": "activation", "session_id": SID,
         "activation_action": "first_question"},
    ]}
    response = await client.post("/api/funnel/events", json=payload)
    assert response.status_code == 200
    assert response.json() == {"accepted": 3, "duplicates": 0, "rejected": 0}
    # Повтор того же батча — всё дедуплицировано на уровне БД.
    response = await client.post("/api/funnel/events", json=payload)
    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "duplicates": 3, "rejected": 0}
    for name in (analytics_repo.E_VISIT, analytics_repo.E_SIGNUP,
                 analytics_repo.E_ACTIVATION):
        assert await _count(db, name) == 1


async def test_api_rejects_unknown_event_names(client, db):
    response = await client.post("/api/funnel/events", json={"events": [
        {"name": "steal_credit", "session_id": SID},
        {"name": "visit", "session_id": SID + "x"},
    ]})
    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "duplicates": 0, "rejected": 1}
    assert await _count(db, "steal_credit") == 0


async def test_api_validation_rejects_bad_payloads(client):
    # Пустой батч, слишком длинный sid, неизвестное поле — 422 от pydantic.
    assert (await client.post(
        "/api/funnel/events", json={"events": []})).status_code == 422
    assert (await client.post(
        "/api/funnel/events",
        json={"events": [{"name": "visit", "session_id": "x" * 100}]})).status_code == 422
    assert (await client.post(
        "/api/funnel/events",
        json={"events": [{"name": "visit", "session_id": SID,
                          "props_json": '{"hack": 1}'}]})).status_code == 422
