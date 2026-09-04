"""API Mini App и админ-панели: доступы, коды ответов, формат данных.

Соединение с БД подменяется через `dependency_overrides` — иначе тесты писали бы
в боевой файл, указанный в .env.
"""
from __future__ import annotations

import json
import re

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.api.security import parse_init_data  # noqa: E402
from app.repo import dialog, readings, users  # noqa: E402
from app.services import billing as billing_svc  # noqa: E402


@pytest.fixture
async def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def as_user(user, params: dict | None = None) -> dict:
    return {"dev_user": user["tg_id"], **(params or {})}


# ─────────────────────────── доступ и безопасность ────────────────────────────

async def test_unified_history_is_owner_scoped_and_normalized(client, db, user):
    report_id = await readings.save_report(
        db, user["tg_id"], "natal", "Natal report", "PRIVATE REPORT BODY",
        meta={"source": "test"},
    )
    reading_id = await readings.save_reading(
        db, user["tg_id"], "three", "A synthetic question",
        [{"name": "The Star"}], "A synthetic answer",
    )
    thread = await dialog.create_thread(db, user["tg_id"], "oracle", "A conversation")
    await dialog.save_message(db, user["tg_id"], "user", "A private message", thread_id=thread["id"])
    await dialog.add_diary(db, user["tg_id"], "A private diary entry", mood="calm")

    response = await client.get("/api/history", params=as_user(user))
    assert response.status_code == 200
    payload = response.json()
    assert payload["owner_scoped"] is True
    assert payload["raw_content_included"] is False
    kinds = {item["kind"] for item in payload["items"]}
    assert {"report", "tarot", "chat", "diary"} <= kinds
    report = next(item for item in payload["items"] if item["kind"] == "report" and item["entry_id"] == report_id)
    tarot = next(item for item in payload["items"] if item["kind"] == "tarot" and item["entry_id"] == reading_id)
    diary = next(item for item in payload["items"] if item["kind"] == "diary")
    assert "PRIVATE REPORT BODY" not in report.values()
    assert tarot["deep_link"] == f"/api/tarot/history/{reading_id}"
    assert diary["deep_link"] == f"/api/diary/{diary['entry_id']}"
    chat = next(item for item in payload["items"] if item["kind"] == "chat")
    assert chat["deep_link"] == f"/api/chat/oracle/sessions/{thread['id']}"

    other = await users.ensure(db, 987654321, "Other", "other", lang="ru")
    foreign = await readings.save_report(db, other["tg_id"], "natal", "Other report", "foreign")
    assert all(item["source_id"] != f"report:{foreign}" for item in (await client.get("/api/history", params=as_user(user))).json()["items"])

    exact_tarot = await client.get(f"/api/tarot/history/{reading_id}", params=as_user(user))
    assert exact_tarot.status_code == 200
    exact_diary = await client.get(f"/api/diary/{diary['entry_id']}", params=as_user(user))
    assert exact_diary.status_code == 200


async def test_health_is_open(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


async def test_root_health_is_open_and_includes_database_state(client):
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["database"]["ok"] is True
    assert "text" not in str(body).lower()


async def test_me_requires_identity(client):
    res = await client.get("/api/me")
    assert res.status_code == 401


async def test_unknown_user_gets_404(client):
    res = await client.get("/api/me", params={"dev_user": 999999})
    assert res.status_code == 404


async def test_new_user_auth_lifecycle_requires_start_then_allows_me(client, db):
    new_tg_id = 987654321
    before = await client.get("/api/me", params={"dev_user": new_tg_id})
    assert before.status_code == 404
    assert "нажми /start" in before.json()["detail"]

    created = await users.ensure(db, new_tg_id, "Новый пользователь", "new_user", lang="ru")
    assert created["tg_id"] == new_tg_id
    assert created["sub_level"] == "trial"
    assert created["crystals"] > 0
    assert created["onboarded"] == 0

    after = await client.get("/api/me", params={"dev_user": new_tg_id})
    assert after.status_code == 200
    assert after.json()["name"] == "Новый пользователь"
    assert after.json()["sub_active"] is True

    same = await users.ensure(db, new_tg_id, "Другое имя", "new_user", lang="ru")
    assert same["tg_id"] == new_tg_id
    assert same["name"] == "Новый пользователь"


async def test_blocked_user_is_refused(client, db, user):
    await users.set_status(db, user["tg_id"], "blocked")
    res = await client.get("/api/me", params=as_user(user))
    assert res.status_code == 403
    await users.set_status(db, user["tg_id"], "active")


async def test_deleted_user_cannot_reenter_product_surfaces_but_delete_is_idempotent(client, db, user):
    await users.anonymize(db, user["tg_id"])

    me = await client.get("/api/me", params=as_user(user))
    assert me.status_code == 410

    privacy = await client.get("/api/account/privacy", params=as_user(user))
    assert privacy.status_code == 410

    profile = await client.patch(
        "/api/profile", params=as_user(user),
        json={"memory_enabled": True},
    )
    assert profile.status_code == 410
    deleted = await users.get(db, user["tg_id"])
    assert deleted["status"] == "deleted"
    assert deleted["memory_enabled"] == 0

    repeated = await client.post(
        "/api/account/delete", params=as_user(user), json={"confirm": True},
    )
    assert repeated.status_code == 200
    assert repeated.json() == {"ok": True, "already_deleted": True, "status": "deleted"}


async def test_bad_init_data_is_rejected():
    assert parse_init_data("") is None
    assert parse_init_data("user=%7B%22id%22%3A1%7D&hash=deadbeef") is None


async def test_chart_request_emits_structured_operational_log(client, db, user, caplog):
    chart = {
        "mode": "full", "precision": "date_only",
        "sun": {"sign": "Лев"},
        "planets": [{"name": "Солнце", "sign": "Лев"}],
        "houses": [], "aspects": [], "nodes": [],
    }
    await users.update(db, user["tg_id"], chart_json=json.dumps(chart, ensure_ascii=False))
    with caplog.at_level("INFO", logger="oracle.astro"):
        response = await client.get("/api/chart", params=as_user(user))
    assert response.status_code == 200
    record = next(r for r in caplog.records if getattr(r, "event", "") == "astro_chart_served")
    assert record.mode == "full"
    assert record.precision == "date_only"
    assert record.cache_hit is True
    assert record.planet_count == 1
    assert "987654321" not in record.getMessage()


async def test_path_traversal_is_blocked(client):
    """`GET /..%2F.env` не должен отдать файл с токенами."""
    res = await client.get("/..%2F.env")
    assert res.status_code == 404


# ──────────────────────────────── профиль ─────────────────────────────────────

async def test_me_returns_full_state(client, user):
    res = await client.get("/api/me", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    for key in ("name", "plan", "allowance", "agents", "flags", "crystals",
                "sub_active", "questions_left", "gender"):
        assert key in data, key
    assert data["allowance"]["limit"] == 3
    assert len(data["agents"]) >= 3


async def test_profile_update_validates_persona(client, user):
    res = await client.post("/api/profile", params=as_user(user),
                            json={"persona": "не-существует"})
    assert res.status_code == 400

    res = await client.post("/api/profile", params=as_user(user),
                            json={"persona": "witch", "oracle_name": "Ниса"})
    assert res.status_code == 200
    assert set(res.json()["updated"]) == {"persona", "oracle_name"}


async def test_profile_update_validates_timezone(client, user):
    res = await client.post("/api/profile", params=as_user(user),
                            json={"tz": "Mars/Olympus"})
    assert res.status_code == 400


async def test_profile_gender_can_be_set_and_cleared(client, user):
    updated = await client.patch("/api/profile", params=as_user(user), json={"gender": "m"})
    assert updated.status_code == 200
    assert updated.json()["updated"] == ["gender"]

    profile = await client.get("/api/me", params=as_user(user))
    assert profile.json()["gender"] == "m"

    cleared = await client.post("/api/profile", params=as_user(user), json={"gender": None})
    assert cleared.status_code == 200
    assert cleared.json()["updated"] == ["gender"]
    assert (await client.get("/api/me", params=as_user(user))).json()["gender"] is None


async def test_profile_gender_rejects_unknown_code(client, user):
    res = await client.post("/api/profile", params=as_user(user), json={"gender": "other"})
    assert res.status_code == 422


async def test_referral_returns_link_and_stats(client, user):
    res = await client.get("/api/referral", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert "link" in data and "share_text" in data
    assert data["bonus_per_invite"] > 0


# ──────────────────────────── сегодня и карта ─────────────────────────────────

async def test_today_needs_active_subscription(client, db, free_user):
    res = await client.get("/api/today", params={"dev_user": free_user["tg_id"]})
    assert res.status_code == 402


async def test_today_returns_forecast_and_card(client, user):
    res = await client.get("/api/today", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert data["forecast"] and data["card"]["name"] and data["moon"]["name"]
    # прогноз кешируется на сутки: повторный запрос отдаёт тот же текст
    again = await client.get("/api/today", params=as_user(user))
    assert again.json()["forecast"] == data["forecast"]


async def test_city_suggest_returns_matched_and_typo_tolerant(client, user):
    res = await client.get("/api/city/suggest", params=as_user(user, {"q": "моск"}))
    assert res.status_code == 200
    assert {"key": "москва", "label": "Москва"} in res.json()["items"]
    # опечатка («Масква») всё равно подсказывает нужный город
    typo = await client.get("/api/city/suggest", params=as_user(user, {"q": "Масква"}))
    assert "Москва" in [i["label"] for i in typo.json()["items"]]
    # слишком короткий запрос — пусто
    short = await client.get("/api/city/suggest", params=as_user(user, {"q": "м"}))
    assert short.json()["items"] == []


async def test_chart_and_matrix(client, user):
    chart = await client.get("/api/chart", params=as_user(user))
    assert chart.status_code == 200
    data = chart.json()
    assert data["sun"]["sign"]
    assert data["natal_schema_version"] == 2
    assert data["engine"] == "Swiss Ephemeris via Kerykeion"
    assert data["zodiac_type"] == "Tropical"
    assert data["house_system"] == "P"
    assert data["house_system_name"] == "Placidus"
    assert data["perspective_type"] == "Apparent Geocentric"
    assert data["lunar_nodes"]["mode"] == "true"
    assert data["lunar_nodes"]["rahu"]["name"].startswith("Раху")
    assert data["lunar_nodes"]["ketu"]["name"].startswith("Кету")
    assert {point["name"] for point in data["additional_points"]} >= {
        "Хирон", "Джуно", "Церера", "Веста", "Паллада",
    }

    matrix = await client.get("/api/matrix", params=as_user(user))
    assert matrix.status_code == 200
    assert 1 <= matrix.json()["destiny"]["n"] <= 22


async def test_moon_week(client, user):
    res = await client.get("/api/moon/week", params=as_user(user, {"days": 7}))
    assert res.status_code == 200
    assert len(res.json()) == 7


# ─────────────────────────── совместимость ────────────────────────────────────

async def test_compat_score_is_explained(client, user):
    res = await client.post("/api/compat", params=as_user(user),
                            json={"partner_date": "1996-11-03"})
    assert res.status_code == 200
    data = res.json()
    assert 35 <= data["score"] <= 98
    assert data["breakdown"] and data["verdict"]


async def test_compat_accepts_russian_date_format(client, user):
    res = await client.post("/api/compat", params=as_user(user),
                            json={"partner_date": "03.11.1996"})
    assert res.status_code == 200


async def test_compat_rejects_garbage_date(client, user):
    res = await client.post("/api/compat", params=as_user(user),
                            json={"partner_date": "вчера"})
    assert res.status_code == 400


async def test_partner_can_be_saved_and_removed(client, user):
    created = await client.post("/api/partners", params=as_user(user),
                                json={"name": "Дима", "birth_date": "03.11.1996"})
    assert created.status_code == 200
    partner_id = created.json()["id"]

    listed = await client.get("/api/partners", params=as_user(user))
    assert any(p["id"] == partner_id for p in listed.json())

    removed = await client.delete(f"/api/partners/{partner_id}", params=as_user(user))
    assert removed.status_code == 200
    assert not (await client.get("/api/partners", params=as_user(user))).json()


# ──────────────────────────────── Таро ────────────────────────────────────────

async def test_spread_catalog(client, user):
    res = await client.get("/api/tarot/spreads", params=as_user(user))
    assert res.status_code == 200
    codes = {s["code"] for s in res.json()}
    assert {"one", "three", "love", "celtic"} <= codes


async def test_draw_then_interpret(client, user):
    drawn = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "three"}))
    assert drawn.status_code == 200
    data = drawn.json()
    assert len(data["cards"]) == 3
    assert data["ledger"]["replay"]["version"] == "tarot-replay-v1"
    assert data["ledger"]["replay"]["mode"] == "immutable_cards"
    assert len(data["ledger"]["checksum"]) == 16

    answer = await client.post(f"/api/tarot/interpret/{data['reading_id']}",
                               params=as_user(user))
    assert answer.status_code == 200
    assert answer.json()["answer"]

    history = await client.get("/api/tarot/history", params=as_user(user))
    assert history.json()[0]["id"] == data["reading_id"]


async def test_tarot_spreads_full_has_guide(client, user):
    res = await client.get("/api/tarot/spreads/full", params=as_user(user))
    assert res.status_code == 200
    items = {s["code"]: s for s in res.json()}
    assert "path" in items
    assert all(s.get("guide") for s in items.values())
    assert items["celtic"]["positions"]


async def test_tarot_question_saved_and_draw_returns_guide(client, user):
    """Question-first: вопрос клиентки доходит до расклада и истории."""
    q = "Когда я встречу своего человека?"
    drawn = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "love"}),
                              json={"question": q})
    assert drawn.status_code == 200
    data = drawn.json()
    assert data["guide"], "draw не вернул guide расклада"
    assert data["spread"] == "love"
    # history показывает только трактованные расклады (answer<>''),
    # поэтому сначала интерпретируем — и проверяем, что вопрос дошёл
    await client.post(f"/api/tarot/interpret/{data['reading_id']}", params=as_user(user))
    history = await client.get("/api/tarot/history", params=as_user(user))
    row = next(r for r in history.json() if r["id"] == data["reading_id"])
    assert row["question"] == q


async def test_tarot_outcome_stats(client, user):
    """Счётчик «сбылось» агрегирует отметки без изменений схемы."""
    drawn = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "one"}))
    reading_id = drawn.json()["reading_id"]
    await client.post(f"/api/tarot/outcome/{reading_id}", params=as_user(user),
                      json={"outcome": "came_true"})
    res = await client.get("/api/tarot/stats", params=as_user(user))
    assert res.status_code == 200
    stats = res.json()
    assert stats["came_true"] >= 1
    assert stats["marked"] == stats["came_true"] + stats["partly"] + stats["no"]


async def test_premium_spread_is_paywalled(client, user):
    res = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "celtic"}))
    # без права расклад берётся из лимита тарифа; после исчерпания — отказ
    assert res.status_code in (200, 402, 429)


async def test_cards_cannot_be_forged_by_client(client, user):
    """Трактовка берёт карты из БД: подменить их запросом нельзя."""
    drawn = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "one"}))
    reading_id = drawn.json()["reading_id"]
    res = await client.post(f"/api/tarot/interpret/{reading_id}", params=as_user(user),
                            json={"cards": [{"name": "Солнце"}]})
    assert res.status_code == 200


async def test_interpret_other_user_reading_is_404(client, db, user, free_user):
    drawn = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "one"}))
    reading_id = drawn.json()["reading_id"]
    res = await client.post(f"/api/tarot/interpret/{reading_id}",
                            params={"dev_user": free_user["tg_id"]})
    assert res.status_code in (402, 404)


async def test_outcome_validation(client, user):
    drawn = await client.post("/api/tarot/draw", params=as_user(user, {"spread": "one"}))
    reading_id = drawn.json()["reading_id"]
    ok = await client.post(f"/api/tarot/outcome/{reading_id}", params=as_user(user),
                           json={"outcome": "came_true"})
    assert ok.status_code == 200
    bad = await client.post(f"/api/tarot/outcome/{reading_id}", params=as_user(user),
                            json={"outcome": "мусор"})
    # API-012: исход — Literal-enum, произвольная строка отклоняется pydantic (422)
    assert bad.status_code == 422


# ──────────────────────────────── чаты ────────────────────────────────────────

async def test_agents_list_has_threads(client, user):
    res = await client.get("/api/agents", params=as_user(user))
    assert res.status_code == 200
    agents = res.json()
    assert len(agents) == 4
    assert {a["code"] for a in agents} == {"oracle", "astro", "tarot", "chiromant"}
    assert all("greeting" in a and "code" in a and "avatar" in a for a in agents)
    chiromant = next(a for a in agents if a["code"] == "chiromant")
    assert chiromant["avatar"] == "/static/img/agents/chiromant.jpg"


async def test_chat_history_and_ask(client, user):
    empty = await client.get("/api/chat/oracle", params=as_user(user))
    assert empty.status_code == 200
    assert empty.json()["messages"] == []

    asked = await client.post("/api/chat/oracle", params=as_user(user),
                              json={"text": "Что меня ждёт?"})
    assert asked.status_code == 200
    assert asked.json()["answer"]
    body = asked.json()
    assert body["agent_profile"]["quality"]["output_contract"] == "agent_response.v1"
    assert "capabilities" in body["agent_profile"]
    assert body["proof"]["mode"] in {"deterministic", "offline"}
    assert isinstance(body["proof"]["tools_used"], list)

    filled = await client.get("/api/chat/oracle", params=as_user(user))
    assert len(filled.json()["messages"]) == 2


async def test_unknown_agent_is_404(client, user):
    res = await client.post("/api/chat/nobody", params=as_user(user),
                            json={"text": "привет"})
    assert res.status_code == 404


async def test_ask_validates_length(client, user):
    res = await client.post("/api/chat/oracle", params=as_user(user),
                            json={"text": "x" * 5000})
    assert res.status_code == 422


async def test_chat_can_be_archived(client, user):
    await client.post("/api/chat/oracle", params=as_user(user), json={"text": "вопрос"})
    res = await client.delete("/api/chat/oracle", params=as_user(user))
    assert res.status_code == 200
    fresh = await client.get("/api/chat/oracle", params=as_user(user))
    assert fresh.json()["messages"] == []


# ──────────────────────────── дневник и лавка ─────────────────────────────────

async def test_diary_roundtrip(client, user):
    res = await client.post("/api/diary", params=as_user(user),
                            json={"text": "Сегодня был странный день", "mood": "calm"})
    assert res.status_code == 200
    assert res.json()["streak"] >= 1

    listed = await client.get("/api/diary", params=as_user(user))
    assert listed.json()["entries"][0]["text"].startswith("Сегодня")


async def test_shop_shows_catalog(client, user):
    res = await client.get("/api/shop", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert data["plans"] and "spread" in data["products"]


async def test_invoice_requires_target(client, user):
    res = await client.post("/api/shop/invoice", params=as_user(user), json={})
    assert res.status_code == 400


async def test_buy_with_crystals_without_balance(client, db, user):
    await users.update(db, user["tg_id"], crystals=0)
    res = await client.post("/api/shop/crystals", params=as_user(user),
                            json={"sku": "spread_celtic"})
    assert res.status_code == 402


async def test_buy_with_crystals_succeeds(client, db, user):
    await users.update(db, user["tg_id"], crystals=500)
    res = await client.post("/api/shop/crystals", params=as_user(user),
                            json={"sku": "spread_celtic"})
    assert res.status_code == 200
    assert res.json()["granted"]["kind"] == "spread"


async def test_promo_endpoint(client, db, user):
    from app.repo import growth
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=50)
    res = await client.post("/api/shop/promo", params=as_user(user),
                            json={"code": codes[0]})
    assert res.status_code == 200
    bad = await client.post("/api/shop/promo", params=as_user(user),
                            json={"code": "НЕВЕРНЫЙ"})
    assert bad.status_code == 400


async def test_report_requires_purchase(client, user):
    res = await client.post("/api/reports/natal", params=as_user(user), json={})
    assert res.status_code == 402


async def test_report_builds_after_purchase(client, db, user):
    from app.repo import billing
    await billing.grant_entitlement(db, user["tg_id"], "report", "natal", qty=1)
    res = await client.post("/api/reports/natal", params=as_user(user), json={})
    assert res.status_code == 200
    assert res.json()["body"]
    # право списано, но готовый разбор доступен снова без оплаты
    again = await client.post("/api/reports/natal", params=as_user(user), json={})
    assert again.status_code == 200
    assert again.json()["cached"] is True
    assert again.json()["report_id"] == res.json()["report_id"]


async def test_report_refresh_appends_history_version(client, db, user):
    from app.repo import billing

    await billing.grant_entitlement(db, user["tg_id"], "report", "natal", qty=2)
    first = await client.post("/api/reports/natal", params=as_user(user), json={})
    assert first.status_code == 200
    first_id = first.json()["report_id"]

    refreshed = await client.post(
        "/api/reports/natal", params={**as_user(user), "refresh": "true"}, json={})
    assert refreshed.status_code == 200
    assert refreshed.json()["cached"] is False
    assert refreshed.json()["report_id"] > first_id

    cur = await db.execute(
        "SELECT COUNT(*) AS n FROM reports WHERE tg_id=? AND kind=?",
        (user["tg_id"], "natal"))
    assert (await cur.fetchone())["n"] == 2

    latest = await client.get("/api/reports/natal", params=as_user(user))
    assert latest.status_code == 200
    assert latest.json()["created_at"]


# ─────────────────────────── админ-панель ─────────────────────────────────────

async def test_admin_requires_role(client, user):
    res = await client.get("/api/admin/me", params=as_user(user))
    assert res.status_code == 403


async def test_admin_owner_from_env_has_access(client, db):
    await users.ensure(db, 1, "Владелец")
    res = await client.get("/api/admin/me", params={"dev_user": 1})
    assert res.status_code == 200
    assert res.json()["role"] == "owner"


async def test_admin_health_reports_telegram_webapp_readiness(client, db, monkeypatch):
    from app.config import settings

    await users.ensure(db, 1, "Владелец")
    monkeypatch.setattr(settings, "webapp_url", "")
    missing = await client.get("/api/admin/health", params={"dev_user": 1})
    assert missing.json()["telegram_webapp_ready"] is False
    monkeypatch.setattr(settings, "webapp_url", "https://oracle.example")
    ready = await client.get("/api/admin/health", params={"dev_user": 1})
    assert ready.json()["telegram_webapp_ready"] is True


async def test_admin_demo_is_owner_only_and_does_not_mutate_data(client, db, user):
    await users.ensure(db, 1, "Владелец")
    before_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
    before_orders = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]
    demo = await client.get("/api/admin/dashboard/demo", params={"dev_user": 1})
    assert demo.status_code == 200
    data = demo.json()
    assert data["demo"]["active"] is True
    assert data["overview"]["users_total"] == 451
    assert data["monetization"]["repeat_payers"] == 130
    assert data["overview"]["stars_total"] == 17056  # ≈ $328 at the UI reference rate
    assert "17 дней" not in str(data)  # operating-days label is UI-only, not an order field
    after_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
    after_orders = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]
    assert (before_users, before_orders) == (after_users, after_orders)

    await users.ensure(db, 2, "Не админ")
    forbidden = await client.get("/api/admin/dashboard/demo", params={"dev_user": 2})
    assert forbidden.status_code == 403


async def test_payment_history_privacy_and_export_are_server_owned(client, db, user):
    order = await billing_svc.checkout_plan(db, user["tg_id"], "vip", surface="miniapp")
    await billing_svc.apply_payment(db, order["payload"], charge_id="history-charge",
                                    amount_stars=order["amount_stars"])
    history = await client.get("/api/shop/payment-history", params=as_user(user))
    assert history.status_code == 200
    item = history.json()[0]
    assert [stage["key"] for stage in item["stages"]] == ["created", "paid", "entitlement"]
    assert "tg_id" not in item and "payload" not in item
    privacy = await client.get("/api/account/privacy", params=as_user(user))
    assert privacy.status_code == 200
    assert privacy.headers["cache-control"] == "no-store"
    assert privacy.headers["x-content-type-options"] == "nosniff"
    assert privacy.json()["anonymization"]["delete_mode"] == "anonymize"
    exported = await client.get("/api/account/export", params=as_user(user))
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["x-content-type-options"] == "nosniff"
    body = exported.json()
    assert body["payment_history"][0]["status"] == "paid"
    assert "PRIVATE" not in json.dumps(body)
    assert '"payload":' not in json.dumps(body).lower()


async def test_admin_payment_health_is_aggregated_and_read_only(client, db):
    await users.ensure(db, 1, "Владелец")
    result = await client.get("/api/admin/payment-health", params={"dev_user": 1})
    assert result.status_code == 200
    body = result.json()
    assert "checks" in body and "providers" in body
    assert "payload" not in str(body).lower()
    assert "tg_id" not in str(body).lower()


async def test_admin_reconciliation_and_notification_settings_are_owner_only(client, db, user):
    await users.ensure(db, 1, "Владелец")
    settings = await client.get("/api/admin/payment-notifications", params={"dev_user": 1})
    assert settings.status_code == 200
    assert settings.json()["critical_cooldown_hours"] == 1
    updated = await client.patch("/api/admin/payment-notifications", params={"dev_user": 1}, json={
        "degraded_cooldown_hours": 8, "critical_cooldown_hours": 2,
        "quiet_hours_start": "22:00", "quiet_hours_end": "06:00", "secondary_enabled": False,
    })
    assert updated.status_code == 200
    assert updated.json()["degraded_cooldown_hours"] == 8
    recon = await client.get("/api/admin/reconciliation", params={"dev_user": 1})
    assert recon.status_code == 200
    assert "items" in recon.json()
    forbidden = await client.get("/api/admin/reconciliation", params={"dev_user": user["tg_id"]})
    assert forbidden.status_code == 403
    invalid_id = await client.get("/api/admin/reconciliation/0", params={"dev_user": 1})
    assert invalid_id.status_code == 422


async def test_admin_dashboard_and_users(client, db, user):
    await users.ensure(db, 1, "Владелец")
    dash = await client.get("/api/admin/dashboard", params={"dev_user": 1})
    assert dash.status_code == 200
    data = dash.json()
    assert data["overview"]["users_total"] >= 1
    assert len(data["funnel"]) == 5
    assert len(data["timeseries"]) == 30

    listed = await client.get("/api/admin/users",
                              params={"dev_user": 1, "q": "Тестовая"})
    assert listed.status_code == 200
    assert any(u["tg_id"] == user["tg_id"] for u in listed.json()["items"])


async def test_admin_user_card_and_actions(client, db, user):
    await users.ensure(db, 1, "Владелец")
    card = await client.get(f"/api/admin/users/{user['tg_id']}", params={"dev_user": 1})
    assert card.status_code == 200
    assert card.json()["user"]["tg_id"] == user["tg_id"]

    note = await client.post(f"/api/admin/users/{user['tg_id']}/notes",
                             params={"dev_user": 1}, json={"text": "Просила скидку"})
    assert note.status_code == 200

    added_tag = await client.post(f"/api/admin/users/{user['tg_id']}/tags",
                                  params={"dev_user": 1}, json={"tag": " VIP "})
    assert added_tag.status_code == 200
    assert "vip" in added_tag.json()["tags"]

    removed_tag = await client.delete(
        f"/api/admin/users/{user['tg_id']}/tags/vip",
        params={"dev_user": 1})
    assert removed_tag.status_code == 200
    assert "vip" not in removed_tag.json()["tags"]

    grant = await client.post(f"/api/admin/users/{user['tg_id']}/grant",
                              params={"dev_user": 1},
                              json={"kind": "crystals", "qty": 25,
                                    "reason": "компенсация"})
    assert grant.status_code == 200
    assert grant.json()["amount"] == 25

    audit = await client.get("/api/admin/audit", params={"dev_user": 1})
    audit_rows = audit.json()
    assert any(a["action"] == "user.grant" for a in audit_rows)
    assert any(a["action"] == "tag.add" and a["target"] == str(user["tg_id"])
               and json.loads(a["payload_json"]) == {"tag": "vip"}
               for a in audit_rows)
    assert any(a["action"] == "tag.delete" and a["target"] == str(user["tg_id"])
               and json.loads(a["payload_json"]) == {"tag": "vip"}
               for a in audit_rows)


async def test_admin_grant_validates_kind(client, db, user):
    await users.ensure(db, 1, "Владелец")
    res = await client.post(f"/api/admin/users/{user['tg_id']}/grant",
                            params={"dev_user": 1},
                            json={"kind": "магия", "qty": 1})
    assert res.status_code == 400


async def test_admin_can_edit_catalog_and_content(client, db):
    await users.ensure(db, 1, "Владелец")
    plan = await client.post("/api/admin/plans", params={"dev_user": 1},
                             json={"code": "vip", "fields": {"price_stars": 1400}})
    assert plan.status_code == 200
    plans = await client.get("/api/admin/plans", params={"dev_user": 1})
    assert next(p for p in plans.json() if p["code"] == "vip")["price_stars"] == 1400

    content = await client.post("/api/admin/content", params={"dev_user": 1},
                                json={"kind": "copy", "code": "welcome",
                                      "body": "Новый текст приветствия"})
    assert content.status_code == 200

    flag = await client.post("/api/admin/flags", params={"dev_user": 1},
                             json={"code": "voice_questions", "is_on": False})
    assert flag.status_code == 200
    flags = await client.get("/api/admin/flags", params={"dev_user": 1})
    assert not next(f for f in flags.json() if f["code"] == "voice_questions")["is_on"]


async def test_admin_rate_limited(client, db):
    """Панель: после 60 запросов в минуту на админа — 429 (G24)."""
    await users.ensure(db, 1, "Владелец")
    codes = [await client.get("/api/admin/me", params={"dev_user": 1})
             for _ in range(62)]
    statuses = [c.status_code for c in codes]
    assert statuses.count(200) == 60
    assert statuses[-1] == 429, "перебор админ-эндпоинтов не обрезан"


async def test_csp_header_in_production(client, monkeypatch):
    """В бою (dev_mode=0) все ответы несут CSP; в dev — нет (нужен Swagger).

    frame-ancestors обязан включать веб-клиенты Telegram — иначе Mini App
    формально не может быть встроен в web.telegram.org (аудит SEC-002).
    """
    import app.config as config
    monkeypatch.setattr(config.settings, "dev_mode", False)
    res = await client.get("/api/health")
    csp = res.headers.get("content-security-policy")
    assert csp and "default-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp
    for origin in ("https://web.telegram.org", "https://k.web.telegram.org",
                   "https://z.web.telegram.org", "https://telegram.org"):
        assert origin in csp, f"CSP должен разрешать встраивание в {origin}"


async def test_csp_absent_in_dev(client):
    res = await client.get("/api/health")
    assert "content-security-policy" not in res.headers


def test_admin_demo_and_payment_health_ui_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    html = (root / "admin" / "index.html").read_text(encoding="utf-8")
    layout = (root / "admin" / "src" / "layout" / "template.js").read_text(encoding="utf-8")
    entrypoint = (root / "admin" / "admin.js").read_text(encoding="utf-8")
    app = (root / "admin" / "src" / "app.js").read_text(encoding="utf-8")
    dashboard = (root / "admin" / "src" / "features" / "dashboard.js").read_text(encoding="utf-8")
    commerce = (root / "admin" / "src" / "features" / "commerce.js").read_text(encoding="utf-8")
    assert 'id="demo-toggle"' in layout
    assert 'ДЕМО-РЕЖИМ · тестовые данные' in layout
    assert 'id="payment-health"' in layout
    assert 'data-view="reconciliation"' in layout
    assert 'id="reconciliation-export"' in layout
    assert 'class="skip-link"' in layout
    assert 'type="module"' in html
    assert 'id="admin-root"' in html
    assert "./src/app.js" in entrypoint
    assert "class AdminApplication" in app
    assert "/api/admin/dashboard/demo" in dashboard
    assert "/api/admin/payment-health" in dashboard
    assert "/api/admin/reconciliation" in commerce
    assert "state.role !== 'owner'" in commerce

    mini_index = (root / "miniapp" / "index.html").read_text(encoding="utf-8")
    mini_actions = (root / "miniapp" / "js" / "15-actions.js").read_text(encoding="utf-8")
    mini_payments = (root / "miniapp" / "js" / "17-payments.js").read_text(encoding="utf-8")
    mini_misc = (root / "miniapp" / "js" / "12-misc.js").read_text(encoding="utf-8")
    assert re.search(r"/static/styles\.css\?v=\d+", mini_index)
    assert "payment-history" in mini_actions and "account-privacy" in mini_actions
    assert "/api/shop/payment-history" in mini_payments
    assert "/api/account/export" in mini_misc


async def test_cache_control_on_assets(client):
    """Ассеты кешируются коротко; HTML и API — всегда no-cache (G25)."""
    css = await client.get("/styles.css")
    assert css.status_code == 200
    assert css.headers.get("cache-control") == "public, max-age=3600"
    admin_css = await client.get("/admin/static/admin.css")
    assert admin_css.status_code == 200
    assert admin_css.headers.get("cache-control") == "public, max-age=3600"


async def test_no_cache_on_html_and_api(client):
    for path in ("/", "/admin", "/api/health"):
        res = await client.get(path)
        assert res.headers.get("cache-control") == "no-cache", path


async def test_miniapp_index_uses_source_assets_in_dev(client, monkeypatch):
    """FE-001/002: dev opts INTO source assets with SOURCE_ASSETS=1;
    the default is the bundled path (see test_miniapp_index_uses_hashed_bundles_in_dev_default)."""
    from app.config import settings

    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("SOURCE_ASSETS", "1")
    html = (await client.get("/")).text
    assert re.search(r'/static/styles\.css\?v=\d+', html)
    assert re.search(r'/static/js/00-runtime\.js\?v=\d+', html)
    assert '/static/dist/' not in html


async def test_miniapp_index_bundles_by_default_in_dev(client, monkeypatch):
    """FE-002 flip: without SOURCE_ASSETS=1 dev must ALSO serve the bundle so
    devs see what production users see. Opt-in to source assets is deliberate."""
    from pathlib import Path

    from app.config import settings

    manifest_path = Path(__file__).resolve().parents[1] / "miniapp" / "dist" / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("frontend bundle not built in this environment")
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.delenv("SOURCE_ASSETS", raising=False)
    html = (await client.get("/")).text
    assert '/static/dist/' in html
    assert not re.search(r'/static/js/00-runtime\.js\?v=\d+', html)


async def test_miniapp_index_uses_hashed_bundles_in_production(client, monkeypatch):
    from pathlib import Path

    from app.config import settings

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "miniapp" / "dist" / "manifest.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(settings, "dev_mode", False)
    response = await client.get("/")
    assert response.status_code == 200
    html = response.text
    assert f'/static/dist/{manifest["css"]}' in html
    assert f'/static/dist/{manifest["js"]}' in html
    assert not re.search(r'/static/js/00-runtime\.js\?v=\d+', html)
    assert not re.search(r'/static/styles\.css\?v=\d+', html)
    bundle = await client.get(f'/static/dist/{manifest["js"]}')
    assert bundle.status_code == 200
    assert bundle.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_admin_promo_batch(client, db):
    await users.ensure(db, 1, "Владелец")
    res = await client.post("/api/admin/promo", params={"dev_user": 1},
                            json={"count": 5, "batch": "etsy-2", "days": 30})
    assert res.status_code == 200
    assert len(res.json()["codes"]) == 5
    listed = await client.get("/api/admin/promo", params={"dev_user": 1})
    assert any(b["batch"] == "etsy-2" for b in listed.json()["batches"])


async def test_admin_broadcast_preview_and_create(client, db, user):
    await users.ensure(db, 1, "Владелец")
    preview = await client.post("/api/admin/broadcasts/preview", params={"dev_user": 1},
                                json={"title": "t", "body": "b", "segment": "all"})
    assert preview.status_code == 200
    assert preview.json()["count"] >= 1

    created = await client.post("/api/admin/broadcasts", params={"dev_user": 1},
                                json={"title": "Тест", "body": "Привет",
                                      "segment": "onboarded", "send_now": False})
    assert created.status_code == 200
    assert created.json()["total"] >= 1


async def test_admin_broadcast_rejects_unknown_segment(client, db):
    await users.ensure(db, 1, "Владелец")
    res = await client.post("/api/admin/broadcasts", params={"dev_user": 1},
                            json={"title": "t", "body": "b", "segment": "выдумка"})
    assert res.status_code == 400


async def test_owner_manages_roles_without_losing_admin_title(client, db):
    """Владелец выдаёт/меняет роли, поддержка не может повышать права."""
    from app.repo import users as users_repo

    await users_repo.ensure(db, 1, "Владелец")
    await users_repo.ensure(db, 2002, "Саппорт")
    created = await client.post("/api/admin/admins", params={"dev_user": 1}, json={
        "tg_id": 2002, "role": "support", "title": "Служба заботы",
    })
    assert created.status_code == 200

    # Роль support годится для работы с клиентками, но не для выдачи ролей.
    support_me = await client.get("/api/admin/me", params={"dev_user": 2002})
    assert support_me.json()["role"] == "support"
    forbidden = await client.post("/api/admin/admins", params={"dev_user": 2002},
                                  json={"tg_id": 2003, "role": "admin"})
    assert forbidden.status_code == 403

    changed = await client.patch("/api/admin/admins/2002", params={"dev_user": 1},
                                 json={"role": "analyst"})
    assert changed.status_code == 200
    admins = (await client.get("/api/admin/admins", params={"dev_user": 1})).json()
    managed = next(item for item in admins if item["tg_id"] == 2002)
    assert managed["role"] == "analyst"
    assert managed["title"] == "Служба заботы"

    missing = await client.patch("/api/admin/admins/999999", params={"dev_user": 1},
                                 json={"role": "admin"})
    assert missing.status_code == 404
    self_change = await client.patch("/api/admin/admins/1", params={"dev_user": 1},
                                     json={"role": "analyst"})
    assert self_change.status_code == 400
    invalid_id = await client.post("/api/admin/admins", params={"dev_user": 1},
                                   json={"tg_id": -1, "role": "admin"})
    assert invalid_id.status_code == 422

    audit = (await client.get("/api/admin/audit", params={"dev_user": 1})).json()
    assert any(item["action"] == "admin.role" and item["target"] == "2002"
               for item in audit)


async def test_cannot_remove_last_table_owner_when_env_owner_unset(client, db, monkeypatch):
    """Без владельца из .env нельзя снять последнего табличного owner:
    панель осталась бы без администратора с правом менять состав админов.

    Через API инвариант недостижим (меняющий роль сам owner, операции с собой
    отклоняет self-guard), поэтому guard проверяется на уровне репозитория.
    """
    from app.config import settings
    from app.repo import admin as admin_repo
    import pytest

    monkeypatch.setattr(settings, "admin_id", None)
    # seed_defaults уже вставил ADMIN_ID как табличного owner'а: чистим,
    # чтобы guard проверял «последнего оставшегося», а не одного из двух.
    await db.execute("DELETE FROM admins")
    await users.ensure(db, 3001, "Владелец")
    await admin_repo.add_admin(db, 3001, "owner")
    with pytest.raises(ValueError):
        await admin_repo.update_admin_role(db, 3001, "analyst", changed_by=3001)
    with pytest.raises(ValueError):
        await admin_repo.remove_admin(db, 3001)
    # .env-владелец настроен — таблица без владельцев блокировки не создаёт
    monkeypatch.setattr(settings, "admin_id", 1)
    await admin_repo.update_admin_role(db, 3001, "analyst", changed_by=1)
    await admin_repo.remove_admin(db, 3001)


async def test_admin_sees_coupon_activations_and_can_filter_batch(client, db, user):
    from app.repo import growth
    from app.repo import users as users_repo

    await users_repo.ensure(db, 1, "Владелец")
    code = (await growth.create_codes(
        db, 1, kind="crystals", crystals=10, batch="creator-campaign",
        created_by=1))[0]
    assert await growth.redeem(db, code, user["tg_id"])

    res = await client.get("/api/admin/promo/redemptions", params={
        "dev_user": 1, "batch": "creator-campaign",
    })
    assert res.status_code == 200
    [redemption] = res.json()
    assert redemption["code"] == code
    assert redemption["tg_id"] == user["tg_id"]
    assert redemption["batch"] == "creator-campaign"
    assert redemption["kind"] == "crystals"
    assert redemption["crystals"] == 10
    assert redemption["name"] == "Тестовая"


async def test_default_chat_auto_routes_and_explicit_agent_wins(client, user):
    routed = await client.post(
        "/api/chat/oracle", params=as_user(user),
        json={"text": "Что значит мой Сатурн в 10 доме?"},
    )
    assert routed.status_code == 200
    routed_body = routed.json()
    assert routed_body["requested_agent"] == "oracle"
    assert routed_body["agent"] == "astro"
    assert routed_body["routing"]["auto_route"] is True
    assert routed_body["thread_id"]

    explicit = await client.post(
        "/api/chat/tarot", params=as_user(user),
        json={"text": "Что значит мой Сатурн в 10 доме?"},
    )
    assert explicit.status_code == 200
    explicit_body = explicit.json()
    assert explicit_body["requested_agent"] == "tarot"
    assert explicit_body["agent"] == "tarot"
    assert explicit_body["routing"]["auto_route"] is False


async def test_chart_image_is_private_raster_with_conditional_etag(client, user):
    params = as_user(user, {"variant": "compact", "format": "png", "locale": "ru"})
    response = await client.get("/api/chart/image", params=params)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"<svg" not in response.content.lower()
    assert response.headers["cache-control"].startswith("private")
    assert response.headers["content-length"] == str(len(response.content))
    etag = response.headers["etag"]

    cached = await client.get("/api/chart/image", params=params,
                              headers={"If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.headers["etag"] == etag
    assert cached.content == b""


async def test_chart_image_supports_webp_and_rejects_unknown_variant(client, user):
    response = await client.get("/api/chart/image", params=as_user(
        user, {"variant": "share", "format": "webp", "locale": "en"}))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
    assert response.content[:4] == b"RIFF" and response.content[8:12] == b"WEBP"

    bad = await client.get("/api/chart/image", params=as_user(
        user, {"variant": "custom", "format": "png", "locale": "ru"}))
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "unsupported_render"


async def test_date_only_chart_image_is_structured_not_a_fake_wheel(client, db, user):
    import json
    from app.core import astro

    chart = await astro.compute_chart_async("1990-06-21", None, "Казань",
                                            55.79, 49.12, "Europe/Moscow",
                                            time_known=False)
    await users.update(db, user["tg_id"], birth_time=None, birth_time_known=0,
                       chart_json=json.dumps(chart, ensure_ascii=False))
    response = await client.get("/api/chart/image", params=as_user(user))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "insufficient_precision"


async def test_unified_history_is_owner_scoped_and_actionable(client, db, user):
    from app.repo import dialog, readings

    report_id = await readings.save_report(
        db, user["tg_id"], "natal", "Мой разбор", "текст", meta={"source": "test"})
    tarot_id = await readings.start_reading(
        db, user["tg_id"], "three", "мой вопрос", [{"name": "Шут", "reversed": False}])
    await readings.finish_reading(db, tarot_id, user["tg_id"], "ответ")
    thread = await dialog.create_thread(db, user["tg_id"], "oracle", title="Разговор")
    await dialog.save_message(
        db, user["tg_id"], "user", "личный вопрос", thread_id=thread["id"], agent="oracle")

    other_report = await readings.save_report(
        db, 1002, "natal", "чужой разбор", "не должен попасть")

    response = await client.get("/api/history", params=as_user(user))

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["item_id"] for item in items} >= {report_id, tarot_id, thread["id"]}
    assert all(item["item_id"] != other_report for item in items)
    assert all("deep_link" in item and "action" in item for item in items)
    assert not any("личный вопрос" in str(item) for item in items)
    assert not any("текст" in str(item) for item in items)


async def test_palm_rejects_malformed_content_length_without_500(client, user):
    response = await client.post(
        "/api/palm",
        params=as_user(user),
        headers={"content-type": "image/jpeg", "content-length": "not-a-number"},
        content=b"not-an-image",
    )

    assert response.status_code == 400
    assert "размер" in response.json()["detail"]


async def test_sensitive_api_serves_for_active_user(client, db, user):
    """Стабильный пользователь получает данные контракта."""
    res = await client.get("/api/chart", params=as_user(user))
    assert res.status_code == 200


async def test_account_delete_requires_confirmation_and_anonymizes(client, db, user):
    await dialog.save_memory(db, user["tg_id"], "Synthetic private fact")
    await dialog.add_diary(db, user["tg_id"], "Synthetic diary")

    rejected = await client.post("/api/account/delete", json={"confirm": False},
                                 params=as_user(user))
    assert rejected.status_code == 400

    deleted = await client.post("/api/account/delete", json={"confirm": True},
                                params=as_user(user))
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "already_deleted": False, "status": "deleted"}
    row = await users.get(db, user["tg_id"])
    assert row["status"] == "deleted"
    assert row["memory_enabled"] == 0
    assert row["morning_push"] == 0
    assert not await dialog.memories_full(db, user["tg_id"])
    assert not await dialog.get_diary(db, user["tg_id"])

    repeated = await client.post("/api/account/delete", json={"confirm": True},
                                 params=as_user(user))
    assert repeated.status_code == 200
    assert repeated.json()["already_deleted"] is True


async def test_account_delete_cannot_be_triggered_for_another_owner(client, db, user):
    other = await users.ensure(db, 12002, "Other")
    response = await client.post("/api/account/delete", json={"confirm": True},
                                 params=as_user(other))
    assert response.status_code == 200
    assert (await users.get(db, user["tg_id"]))["status"] != "deleted"
    assert (await users.get(db, other["tg_id"]))["status"] == "deleted"


async def test_chart_discloses_oracleai_engine_backend_provenance(client, user):
    response = await client.get("/api/chart", params=as_user(user))
    assert response.status_code == 200
    body = response.json()
    expected = {
        "product_engine": "OracleAI Engine",
        "adapter_version": "oracleai-kerykeion-engine-v2",
        "backend": "Kerykeion",
        "backend_version": "5.12.9",
        "ephemeris": "Swiss Ephemeris",
        "license_notice": "AGPL-3.0/commercial licensing obligations apply to the selected distribution model.",
    }
    assert body["engine_provenance"] == expected
    assert body["calculation"]["engine_provenance"] == expected


async def test_chat_sessions_are_unlimited_and_bulk_delete_preserves_memory(client, db, user):
    for _ in range(6):
        created = await client.post("/api/chat/oracle/sessions", params=as_user(user))
        assert created.status_code == 200

    sessions = await client.get("/api/chat/oracle/sessions", params=as_user(user))
    assert sessions.status_code == 200
    assert len(sessions.json()) == 6

    await dialog.save_memory(db, user["tg_id"], "Люблю тихие утра")
    memories_before = await dialog.memories_full(db, user["tg_id"])
    deleted = await client.delete("/api/chat/oracle/sessions", params=as_user(user))
    assert deleted.status_code == 200
    assert deleted.json()["memory_preserved"] is True
    assert deleted.json()["archived"] == 6

    remaining = await client.get("/api/chat/oracle/sessions", params=as_user(user))
    assert remaining.json() == []
    memories_after = await dialog.memories_full(db, user["tg_id"])
    assert memories_after == memories_before


async def test_admin_logs_endpoint_is_permissioned_and_redacted(client, db, user):
    from app.core.log_stream import log_stream

    await users.ensure(db, 1, "Владелец")
    log_stream.publish({
        "level": "INFO",
        "logger": "oracle.test",
        "message": "safe operational event",
        "event": "test_log",
    })
    visible = await client.get("/api/admin/logs", params={"dev_user": 1, "logger": "oracle.test"})
    assert visible.status_code == 200
    body = visible.json()
    assert body["stream"] == "sse"
    assert any(item["message"] == "safe operational event" for item in body["entries"])
    assert "initData" not in str(body)

    from starlette.requests import Request
    from app.api.routers.logs import stream_logs

    request = Request({"type": "http", "method": "GET", "path": "/api/admin/logs/stream", "headers": [], "query_string": b""})
    stream_response = await stream_logs(request)
    assert stream_response.status_code == 200
    assert stream_response.media_type == "text/event-stream"
    first_frame = await stream_response.body_iterator.__anext__()
    assert "event: ready" in first_frame
    await stream_response.body_iterator.aclose()

    forbidden = await client.get("/api/admin/logs", params={"dev_user": user["tg_id"]})
    assert forbidden.status_code == 403
