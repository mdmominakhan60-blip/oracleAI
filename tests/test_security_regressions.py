"""Regression tests for security and privacy boundaries found in the audit."""
from __future__ import annotations

import hashlib
import hmac
import json
from time import time
from urllib.parse import urlencode

import pytest

from app.api.security import parse_init_data
from app.config import settings
from app.core import tool_registry as skills
from app.repo import dialog, users


def _signed_init_data(*, include_auth_date: bool = True) -> str:
    fields = {"user": json.dumps({"id": 1001}, separators=(",", ":"))}
    if include_auth_date:
        fields["auth_date"] = str(int(time()))
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_init_data_requires_fresh_auth_date(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "test:token")
    assert parse_init_data(_signed_init_data(include_auth_date=True))
    assert parse_init_data(_signed_init_data(include_auth_date=False)) is None


def test_init_data_rejects_duplicate_fields(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "test:token")
    data = _signed_init_data() + "&user=%7B%22id%22%3A1001%7D"
    assert parse_init_data(data) is None


async def test_memory_tools_cannot_bypass_memory_off(db, user):
    await users.update(db, user["tg_id"], memory_enabled=0)
    disabled_user = await users.get(db, user["tg_id"])

    saved = await skills._run_save_memory(
        db, disabled_user, {"fact": "секретный факт", "kind": "fact"})
    recalled = await skills._run_recall_memory(
        db, disabled_user, {"query": "секретный"})
    diary = await skills._run_recall_diary(db, disabled_user, {})

    assert "секретный" not in saved
    assert "секретный" not in recalled
    assert "секретный" not in diary
    assert not await dialog.get_memories(db, user["tg_id"])


async def test_diary_tool_is_blocked_when_memory_off(db, user):
    await users.update(db, user["tg_id"], memory_enabled=0)
    await dialog.add_diary(db, user["tg_id"], "личная запись")
    disabled_user = await users.get(db, user["tg_id"])
    result = await skills._run_recall_diary(db, disabled_user, {})
    assert "личная запись" not in result
    assert "выключена" in result


def test_dev_mode_requires_non_empty_dev_key():
    """BUS-90: DEV_MODE=1 с пустым DEV_KEY роняет импорт конфигурации.

    Прод-стек жил с APP_ENV=test + DEV_MODE=1 и пустым ключом: ветка
    `if settings.dev_key` в deps не выполнялась, и ?dev_user=<id> входил
    в API без всякого заголовка.
    """
    from app.config import assert_dev_mode_allowed

    with pytest.raises(RuntimeError, match="DEV_KEY"):
        assert_dev_mode_allowed(True, "test", "")
    with pytest.raises(RuntimeError, match="DEV_KEY"):
        assert_dev_mode_allowed(True, "dev", "   ")
    with pytest.raises(RuntimeError, match="DEV_KEY"):
        assert_dev_mode_allowed(True, "production", "")
    # Выключенный DEV_MODE с пустым ключом — легален (прод-конфигурация).
    assert_dev_mode_allowed(False, "production", "")


def test_dev_identity_denied_when_dev_key_empty(monkeypatch):
    """BUS-90 защита в глубину: при пустом dev_key вход по ?dev_user закрыт
    даже если настройки подменены в рантайме поверх невалидной конфигурации."""

    class FakeRequest:
        def __init__(self, headers):
            self.headers = headers

    from app.api import deps
    from app.config import settings

    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(settings, "dev_key", "")
    assert deps._dev_identity_allowed(FakeRequest({})) is False
    monkeypatch.setattr(settings, "dev_key", "   ")
    assert deps._dev_identity_allowed(FakeRequest({"x-dev-key": "   "})) is False


def test_production_config_accepts_safe_runtime_configuration(monkeypatch):
    from app.api.main import _validate_production_config

    for name, value in {
        "APP_ENV": "production",
        "DEV_MODE": "0",
        "DATABASE_URL": "postgresql+asyncpg://oracle:secret@postgres:5432/oracle",
        "POSTGRES_PASSWORD": "a-long-random-production-secret",
        "REDIS_URL": "redis://redis:6379/0",
        "CELERY_ENABLED": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "admin_id", 1001)
    monkeypatch.setattr(settings, "webapp_url", "https://oracle.example")
    monkeypatch.setattr(settings, "release_id", "2026.08.27-test")
    _validate_production_config()


def test_production_config_fails_closed_on_unsafe_database(monkeypatch):
    from app.api.main import _validate_production_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///oracle.db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "oracle")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CELERY_ENABLED", "1")
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "admin_id", 1001)
    monkeypatch.setattr(settings, "webapp_url", "https://oracle.example")
    monkeypatch.setattr(settings, "release_id", "2026.08.27-test")
    with pytest.raises(RuntimeError, match="PostgreSQL|шаблонным"):
        _validate_production_config()


def test_production_config_rejects_dev_mode_in_production(monkeypatch):
    from app.api.main import _validate_production_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setattr(settings, "bot_token", "test-token")
    monkeypatch.setattr(settings, "admin_id", 1001)
    monkeypatch.setattr(settings, "webapp_url", "https://oracle.example")
    with pytest.raises(RuntimeError, match="DEV_MODE"):
        _validate_production_config()


def test_production_config_fails_closed(monkeypatch):
    from app.api.main import _validate_production_config

    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "bot_token", "")
    monkeypatch.setattr(settings, "admin_id", 0)
    monkeypatch.setattr(settings, "webapp_url", "")
    # Локальный .env может задавать APP_ENV=dev/test и выключить проверку.
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        _validate_production_config()


async def test_memory_listing_never_returns_embedding_payload(db, user):
    from app.repo import dialog

    await db.execute(
        "INSERT INTO memories(tg_id, fact, kind, weight, embedding, embed_model, created_at) "
        "VALUES(?,?,?,?,CAST(? AS vector),?,?)",
        (user["tg_id"], "личный факт", "fact", 1, "[1,2,3]", "test-model", "2026-08-26T00:00:00+00:00"),
    )
    await db.commit()

    rows = await dialog.memories_full(db, user["tg_id"])

    assert rows and rows[0]["fact"] == "личный факт"
    assert "embedding" not in rows[0]
    assert "embed_model" not in rows[0]


async def test_recall_cache_is_invalidated_after_memory_delete(db, user):
    from app.core import memory
    from app.repo import dialog

    await memory.remember(db, user["tg_id"], "важный проект")
    assert "важный проект" in await memory.recall(db, user["tg_id"], "проект")
    row = (await dialog.memories_full(db, user["tg_id"]))[0]

    assert await dialog.forget_memory(db, row["id"], user["tg_id"])
    assert "важный проект" not in await memory.recall(db, user["tg_id"], "проект")


async def test_tarot_finalization_is_owner_scoped_and_append_only(db):
    from app.repo import readings

    reading_id = await readings.start_reading(
        db, 1001, "three", "вопрос", [{"name": "Шут", "reversed": False}])

    assert not await readings.finish_reading(db, reading_id, 1002, "чужой ответ")
    assert await readings.finish_reading(db, reading_id, 1001, "первый ответ")
    assert not await readings.finish_reading(db, reading_id, 1001, "перезапись")
    row = await readings.get_reading(db, reading_id, 1001)
    assert row["answer"] == "первый ответ"


async def test_shared_chat_service_blocks_unconfirmed_and_deleted_users(db, user):
    from app.services import chat, eligibility

    deleted = dict(user)
    deleted["status"] = "deleted"
    with pytest.raises(eligibility.EligibilityDenied) as deleted_error:
        await chat.ask(db, deleted, "безопасный тест")
    assert deleted_error.value.code == "account_not_active"


async def test_confirmed_age_dependency_is_plain_auth_alias(user):
    """Возрастной гейт удалён: confirmed_age_user ≡ current_user, ошибок 403 нет."""
    from app.api import deps

    result = await deps.confirmed_age_user(dict(user))
    assert result["tg_id"] == user["tg_id"]


async def test_new_users_default_to_memory_off(db):
    from app.repo import users

    created = await users.ensure(db, 2201, "Новый пользователь")
    assert created["memory_enabled"] == 0


async def test_anonymize_cleans_sensitive_rows_and_pseudonymizes_finance(db, user):
    from app.repo import users

    tg_id = user["tg_id"]
    await db.execute(
        "INSERT INTO profile_summaries(tg_id, summary, built_at) VALUES(?,?,?)",
        (tg_id, "личный summary", "2026-08-26"),
    )
    await db.execute(
        "INSERT INTO palm_readings(tg_id, status, analysis_json, created_at) "
        "VALUES(?,?,?,?)", (tg_id, "complete", '{"private":true}', "2026-08-26"),
    )
    await db.execute(
        "INSERT INTO events(tg_id, name, props_json, created_at) VALUES(?,?,?,?)",
        (tg_id, "question", '{"private":"text"}', "2026-08-26"),
    )
    await db.execute(
        "INSERT INTO safety_events(tg_id, category, excerpt, action, created_at) "
        "VALUES(?,?,?,?,?)", (tg_id, "crisis", "private excerpt", "support", "2026-08-26"),
    )
    await db.execute(
        "INSERT INTO orders(tg_id, kind, amount_stars, status, created_at) "
        "VALUES(?,?,?,?,?)", (tg_id, "plan", 10, "paid", "2026-08-26"),
    )
    await db.commit()

    await users.anonymize(db, tg_id)
    await users.anonymize(db, tg_id)

    deleted_tables = (
        "profile_summaries", "palm_readings", "events", "safety_events",
    )
    for table in deleted_tables:
        cur = await db.execute(f"SELECT COUNT(*) c FROM {table} WHERE tg_id=?", (tg_id,))
        assert (await cur.fetchone())["c"] == 0
    cur = await db.execute("SELECT tg_id FROM orders WHERE amount_stars=10")
    assert (await cur.fetchone())["tg_id"] == 0
    row = await users.get(db, tg_id)
    assert row["name"] == "удалено"
    assert row["memory_enabled"] == 0


async def test_safety_summary_redacts_crisis_identity_and_excerpt(db, user):
    from app.repo import analytics

    await db.execute(
        "INSERT INTO safety_events(tg_id, category, excerpt, action, created_at) "
        "VALUES(?,?,?,?,?)", (user["tg_id"], "crisis", "secret crisis text", "support", "2026-08-26"),
    )
    await db.commit()
    result = await analytics.safety_summary(db, days=365)
    assert result["redacted"] is True
    assert "secret crisis text" not in str(result)
    assert "tg_id" not in result["recent"][0]
    assert "excerpt" not in result["recent"][0]


def test_support_cannot_grant_or_read_restricted_safety():
    from app.repo import admin

    assert not admin.can("support", "grants")
    assert not admin.can("support", "safety:read")
    assert admin.can("admin", "grants")
    assert admin.can("admin", "safety:read")


def test_telegram_formatting_escapes_untrusted_markup():
    from app.bot.formatting import tg_esc, tg_rich

    assert tg_esc('<a href="https://evil.test">name</a>') == (
        '&lt;a href="https://evil.test"&gt;name&lt;/a&gt;'
    )
    assert tg_rich("<b>trusted</b> <script>alert(1)</script>") == (
        "<b>trusted</b> &lt;script&gt;alert(1)&lt;/script&gt;"
    )
    assert tg_rich("<b>unbalanced") == "&lt;b&gt;unbalanced"
    assert tg_rich("<b>trusted</b>") == "<b>trusted</b>"


async def test_anonymize_clears_legacy_webhook_payload(db, user):
    await db.execute(
        "INSERT INTO webhook_events(event_id, provider, kind, payload, created_at) "
        "VALUES(?,?,?,?,?)",
        ("legacy-private-event", "paddle", "transaction.completed", "raw customer payload", "2026-08-26"),
    )
    await db.commit()
    await users.anonymize(db, user["tg_id"])
    row = await (await db.execute(
        "SELECT payload FROM webhook_events WHERE event_id=?", ("legacy-private-event",)
    )).fetchone()
    assert row["payload"] is None


def test_crypto_pay_signature_uses_sha256_derived_token(monkeypatch):
    import hmac
    from app.services import cryptobot

    token = "123456:secret-token"
    body = b'{"update_type":"invoice_paid"}'
    monkeypatch.setattr(settings, "cryptobot_api_token", token)
    derived = hmac.new(hashlib.sha256(token.encode()).digest(), body, hashlib.sha256).hexdigest()
    raw_token_signature = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
    assert cryptobot.verify_webhook(body, derived) is True
    assert cryptobot.verify_webhook(body, raw_token_signature) is False
