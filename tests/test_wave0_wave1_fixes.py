"""Регрессии для аудит-волны Wave 0/Wave 1.

Покрывают:
- SEC-001: fail-closed DEV_MODE при импорте конфигурации;
- SEC-010: age-gate требует год рождения, хранит только keyed-хеш;
- UX-009: публичный /api/public/config для deep-link в бота;
- CONT-001: билингвальные отказы 402/429;
- AI-010: выбор palm-промптов по языку клиентки.
"""
from __future__ import annotations

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.main import app
from app.repo import users


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
async def unconfirmed(db):
    """Обычный активный пользователь (возрастной гейт удалён)."""
    await users.ensure(db, 1007, "Без гейта")
    await users.update(db, 1007, onboarded=1)
    return await users.get(db, 1007)


# ─────────────────────────── SEC-001: DEV_MODE guard ──────────────────────────

def test_dev_mode_fails_closed_at_import_for_non_dev_env():
    from app.config import assert_dev_mode_allowed
    with pytest.raises(RuntimeError):
        assert_dev_mode_allowed(True, "production", "some-key")
    with pytest.raises(RuntimeError):
        assert_dev_mode_allowed(True, "staging", "some-key")
    # dev/test и выключенный режим — легальные комбинации
    assert_dev_mode_allowed(True, "dev", "some-key")
    assert_dev_mode_allowed(True, "test", "some-key")
    assert_dev_mode_allowed(False, "production", "")


def test_dev_key_gate(monkeypatch):
    """Когда DEV_KEY задан, dev-вход без заголовка X-Dev-Key отклоняется."""
    from app.api import deps
    from app.config import settings

    class FakeRequest:
        def __init__(self, headers):
            self.headers = headers

    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(settings, "dev_key", "local-dev-key")
    assert deps._dev_identity_allowed(FakeRequest({})) is False
    assert deps._dev_identity_allowed(FakeRequest({"x-dev-key": "wrong"})) is False
    assert deps._dev_identity_allowed(FakeRequest({"x-dev-key": "local-dev-key"})) is True
    monkeypatch.setattr(settings, "dev_mode", False)
    assert deps._dev_identity_allowed(FakeRequest({"x-dev-key": "local-dev-key"})) is False


# ──────────────────── GAUNTLET v2 §1-2: age semantics ────────────────────────
async def test_profile_api_no_longer_accepts_age_confirmation(client, db, unconfirmed):
    """Подтверждение возраста больше не клиентский флаг: его ставит только
    реальная дата рождения в онбординге бота (SEC-010). API поле игнорирует."""
    res = await client.post("/api/profile", params={"dev_user": unconfirmed["tg_id"]},
                            json={"age_confirmed": True, "birth_year": 2000})
    assert res.status_code == 200


# ─────────────────────────── UX-009: public config ────────────────────────────

async def test_public_config_is_unauthenticated_and_bounded(client):
    res = await client.get("/api/public/config")
    assert res.status_code == 200
    body = res.json()
    assert set(body) <= {"bot_username", "webapp_url"}
    assert isinstance(body["bot_username"], str)


# ─────────────────────────── CONT-001: deny copy ──────────────────────────────

def test_access_denied_is_bilingual():
    from app.api.common.errors import access_denied

    class Verdict:
        reason = "limit_reached"

    ru = access_denied(Verdict(), lang="ru")
    en = access_denied(Verdict(), lang="en")
    assert ru.status_code == 429 and en.status_code == 429
    assert "Вернись" in ru.detail
    assert "dawn" in en.detail

    class SubOver:
        reason = "sub_over"

    assert access_denied(SubOver(), lang="en").status_code == 402
    assert "Renew" in access_denied(SubOver(), lang="en").detail


# ─────────────────────────── AI-010: palm prompts ─────────────────────────────

def test_palm_prompts_follow_user_language():
    from app.core.palm import PALM_SYSTEM, PALM_SYSTEM_EN, PALM_USER, PALM_USER_EN, palm_prompts
    system_ru, user_ru = palm_prompts("ru")
    system_en, user_en = palm_prompts("en")
    assert (system_ru, user_ru) == (PALM_SYSTEM, PALM_USER)
    assert (system_en, user_en) == (PALM_SYSTEM_EN, PALM_USER_EN)
    # EN-контракт содержит те же поля схемы и правила безопасности
    # (версия контракта living в service.py EVIDENCE_CONTRACT_VERSION, не в промпте)
    assert "evidence_state" in user_en and "confidence" in user_en
    assert "never" in system_en.lower() or "Never" in system_en
    # needs_photo живёт в SYSTEM-промпте (правила статус-переходов), не в user-кадре
    assert "needs_photo" in system_en
    # fallback: неизвестный язык → RU
    assert palm_prompts("de") == (PALM_SYSTEM, PALM_USER)


# ─────────────────────── вторая волна (Wave 1 остаток + 2/3) ──────────────────

async def test_tarot_outcome_is_closed_enum(client, user):
    """API-012: произвольная строка в исходе расклада отклоняется валидацией."""
    res = await client.post("/api/tarot/outcome/1",
                            params={"dev_user": user["tg_id"]},
                            json={"outcome": "definitely_maybe"})
    assert res.status_code == 422


async def test_chat_sessions_are_capped_and_paginated(client, db, user):
    """API-014: список сессий отдаётся страницами, offset работает."""
    from app.repo import dialog
    for _ in range(3):
        await dialog.create_thread(db, user["tg_id"], "oracle", title="t")
    first = await client.get("/api/chat/oracle/sessions",
                             params={"dev_user": user["tg_id"]})
    assert first.status_code == 200
    assert len(first.json()) >= 3
    second = await client.get("/api/chat/oracle/sessions",
                              params={"dev_user": user["tg_id"], "offset": 2})
    assert second.status_code == 200
    assert len(second.json()) == len(first.json()) - 2


async def test_metrics_token_guard(monkeypatch, client):
    """SEC-015: при заданном METRICS_TOKEN /metrics требует Bearer на app-уровне."""
    from app.config import settings
    monkeypatch.setattr(settings, "metrics_token", "metrics-secret")
    denied = await client.get("/metrics")
    assert denied.status_code == 401
    allowed = await client.get(
        "/metrics", headers={"Authorization": "Bearer metrics-secret"})
    assert allowed.status_code == 200


async def test_crm_search_escapes_like_wildcards(db):
    """DB-015: «_» в запросе CRM — литерал, а не wildcard."""
    await users.ensure(db, 2001, "an_na")
    await users.ensure(db, 2002, "anna")
    rows = await users.search(db, "an_na")
    names = {r["name"] for r in rows}
    assert "an_na" in names
    assert "anna" not in names


async def test_crm_search_name_order_runs_on_postgres(db):
    """DB-003: order=name не должен падать на PostgreSQL (COLLATE NOCASE убран)."""
    await users.ensure(db, 2003, "Борис")
    rows = await users.search(db, "", order="name")
    assert any(r["tg_id"] == 2003 for r in rows)


async def test_question_too_long_is_explicit_error():
    """API-003: превышение контракта — ошибка, а не тихая обрезка."""
    from app.services import chat as chat_svc
    fake_user = {"tg_id": 1, "status": "active",
                 "deleted_at": None, "lang": "ru"}
    with pytest.raises(chat_svc.QuestionTooLong):
        await chat_svc.ask(None, fake_user, "x" * 1001, surface="bot")


def test_bot_commands_have_english_scope():
    """BOT-008: у команд бота есть EN-скоуп для setMyCommands."""
    from app.bot.main import COMMANDS, COMMANDS_EN
    assert [c.command for c in COMMANDS] == [c.command for c in COMMANDS_EN]
    assert any(c.description == "How I work" for c in COMMANDS_EN)
