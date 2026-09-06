"""BUS-237: админка R6 — отзывы day-7 опроса (сводка, фильтры, CSV).

Контракт:
- GET /api/admin/feedback/summary — NPS (promoters 9-10 / passives 7-8 /
  detractors 0-6), response rate по deliveries(kind='feedback_survey').
- GET /api/admin/feedback/responses — фильтры: дни, NPS-диапазон,
  вопрос+вариант, модерация, поиск по free text; пагинация.
- GET /api/admin/feedback/export — CSV только агрегаты/categorical (free text
  НЕ выгружается), права owner/admin, audit-запись feedback.export.
- Невалидные фильтры → 422; analyst/support → 403 на экспорт.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("httpx", reason="httpx нужен для тестов API")
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import feedback_admin as feedback_repo  # noqa: E402
from tests.conftest import TEST_DEV_KEY  # noqa: E402

BASE_URL = "http://test"
HEADERS = {"X-Dev-Key": TEST_DEV_KEY}


async def _ensure_user(db, tg_id: int, *, onboarded: int = 1,
                       sub_level: str = "free") -> None:
    await db.execute(
        "INSERT INTO users(tg_id, name, username, onboarded, status, sub_level, "
        "created_at) VALUES(:tg_id, :name, :name, :onb, 'active', :sub, "
        ":created_at) ON CONFLICT (tg_id) DO UPDATE SET sub_level=:sub",
        {"tg_id": tg_id, "name": f"Юзер{tg_id}", "onb": onboarded,
         "sub": sub_level, "created_at": "2026-09-01T10:00:00+00:00"})


async def _add_response(db, tg_id: int, *, nps: int | None, like: str | None,
                        blocker: str | None, next_: str | None,
                        free_text: str | None = None,
                        status: str = "submitted",
                        created_at: str = "2026-09-05T12:00:00+00:00") -> None:
    answers = []
    if like:
        answers.append({"question_code": "like", "choice": like})
    if blocker:
        answers.append({"question_code": "blocker", "choice": blocker})
    if nps is not None:
        answers.append({"question_code": "nps", "score": nps})
    if next_:
        answers.append({"question_code": "next", "choice": next_})
    await db.execute(
        "INSERT INTO feedback_responses(tg_id, survey_code, answers_json, "
        "free_text, status, bonus_granted, created_at) "
        "VALUES(:tg_id, :code, :answers, :text, :status, 0, :created_at) "
        "ON CONFLICT (tg_id, survey_code) DO NOTHING",
        {"tg_id": tg_id, "code": feedback_repo.SURVEY_CODE,
         "answers": json.dumps(answers, ensure_ascii=False),
         "text": free_text, "status": status, "created_at": created_at})


async def _invite(db, tg_id: int) -> None:
    await db.execute(
        "INSERT INTO deliveries(tg_id, kind, key, status, created_at) "
        "VALUES(:tg_id, 'feedback_survey', 'day7_v1', 'sent', :created_at) "
        "ON CONFLICT DO NOTHING",
        {"tg_id": tg_id, "created_at": "2026-09-01T10:00:00+00:00"})


@pytest.fixture
async def admin_client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL,
                           headers=HEADERS) as http:
        yield http
    app.dependency_overrides.clear()


def _admin_params(**extra):
    return {"dev_user": 1, **extra}


# ─────────────────────────────── сводка ───────────────────────────────────────

async def test_summary_nps_buckets_and_response_rate(admin_client, db):
    await _invite(db, 3001)
    await _invite(db, 3002)
    await _add_response(db, 3001, nps=9, like="forecasts", blocker=None,
                        next_=None)     # promoter
    await _add_response(db, 3002, nps=5, like=None, blocker="slow",
                        next_="compat")  # detractor
    await _invite(db, 3003)  # приглашён, но не ответил

    res = await admin_client.get("/api/admin/feedback/summary",
                                 params=_admin_params())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_responses"] == 2
    assert body["invited"] == 3
    assert body["response_rate_pct"] == round(100 * 2 / 3, 1)
    nps = body["nps"]
    assert nps["promoters"] == 1 and nps["detractors"] == 1
    assert nps["passives"] == 0
    assert nps["score"] == round(100 * (1 - 1) / 2)
    # Распределение Q1 по вариантам.
    like_dist = {d["choice"]: d["count"] for d in body["distributions"]["like"]}
    assert like_dist["forecasts"] == 1
    blocker_dist = {d["choice"]: d["count"] for d in body["distributions"]["blocker"]}
    assert blocker_dist["slow"] == 1


async def test_summary_empty_state(admin_client, db):
    res = await admin_client.get("/api/admin/feedback/summary",
                                 params=_admin_params())
    assert res.status_code == 200
    body = res.json()
    assert body["total_responses"] == 0
    assert body["nps"]["score"] is None
    assert body["response_rate_pct"] is None


# ─────────────────────────── список и фильтры ─────────────────────────────────

async def test_responses_list_includes_free_text(admin_client, db):
    await _ensure_user(db, 3011)
    await _add_response(db, 3011, nps=10, like="tarot", blocker=None,
                        next_=None, free_text="Очень тёплые прогнозы, спасибо")
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["free_text"] == "Очень тёплые прогнозы, спасибо"
    assert row["nps"] == 10
    assert row["moderation"] == "pending"  # submitted → pending до классификации
    assert row["user_name"] == "Юзер3011"


async def test_responses_filter_nps_range(admin_client, db):
    await _add_response(db, 3021, nps=9, like=None, blocker=None, next_=None)
    await _add_response(db, 3022, nps=3, like=None, blocker=None, next_=None)
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(nps_min=7, nps_max=10))
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["tg_id"] == 3021


async def test_responses_filter_question_choice(admin_client, db):
    await _add_response(db, 3031, nps=None, like="diary", blocker=None, next_=None)
    await _add_response(db, 3032, nps=None, like="chart", blocker=None, next_=None)
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(question="like", choice="diary"))
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["tg_id"] == 3031


async def test_responses_filter_text_search(admin_client, db):
    await _add_response(db, 3041, nps=None, like=None, blocker=None, next_=None,
                        free_text="Хотелось бы больше лунного ритма")
    await _add_response(db, 3042, nps=None, like=None, blocker=None, next_=None,
                        free_text="Всё нравится, не меняйте")
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(text_query="лунного"))
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["tg_id"] == 3041


async def test_responses_filter_moderation(admin_client, db):
    await _add_response(db, 3051, nps=None, like=None, blocker=None, next_=None,
                        status="flagged")
    await _add_response(db, 3052, nps=None, like=None, blocker=None, next_=None,
                        status="ok")
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(moderation="flagged"))
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["tg_id"] == 3051
    assert body["items"][0]["moderation"] == "flagged"


async def test_responses_invalid_filters_rejected(admin_client, db):
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(question="hack"))
    assert res.status_code == 422
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(question="like", choice="nope"))
    assert res.status_code == 422
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(moderation="weird"))
    assert res.status_code == 422
    res = await admin_client.get("/api/admin/feedback/responses",
                                 params=_admin_params(nps_min=8))
    assert res.status_code == 422


# ─────────────────────────────── CSV-экспорт ──────────────────────────────────

async def test_export_csv_aggregates_without_free_text(admin_client, db):
    await _add_response(db, 3061, nps=8, like="voice", blocker="paywall",
                        next_=None, free_text="Секретный текст не для CSV")
    res = await admin_client.get("/api/admin/feedback/export",
                                 params=_admin_params())
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/csv")
    body = res.text
    lines = body.strip().split("\n")
    assert lines[0] == "tg_id,created_at,nps,like,blocker,next,moderation,bonus_granted"
    assert "3061" in lines[1]
    assert "voice" in lines[1] and "paywall" in lines[1]
    assert "Секретный текст не для CSV" not in body


async def test_export_writes_audit_trail(admin_client, db):
    await _add_response(db, 3071, nps=None, like=None, blocker=None, next_=None)
    res = await admin_client.get("/api/admin/feedback/export",
                                 params=_admin_params())
    assert res.status_code == 200
    row = await db.execute(
        "SELECT action, target FROM admin_audit ORDER BY id DESC LIMIT 1")
    audit = await row.fetchone()
    assert audit["action"] == "feedback.export"
    assert audit["target"] == feedback_repo.SURVEY_CODE


async def test_export_forbidden_for_non_admin_roles(admin_client, db):
    """analyst имеет dashboard, но экспорт — только owner/admin (R8-срез)."""
    from app.repo import admin as admin_repo
    await db.execute(
        "INSERT INTO admins(tg_id, role) VALUES(3101, 'analyst') "
        "ON CONFLICT (tg_id) DO UPDATE SET role='analyst'")
    res = await admin_client.get("/api/admin/feedback/export",
                                 params={"dev_user": 3101})
    assert res.status_code == 403
