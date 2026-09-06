"""Replay-защита initData и session minting (BUS-200).

Требования:
- initData потребляется один раз → повторная отправка → 401.
- При успехе возвращается X-Session-Token.
- Дальнейшие запросы с X-Session-Token проходят без initData.
- Повторный минт с тем же initData отклоняется (S8_replay).
- При недоступности Redis fail-open (решение EL), при REPLAY_FAIL_CLOSED=1
  fail-closed.
- Rate-limit на минт: 10/мин на tg_id после валидации, + IP-лимит до валидации.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import pytest

from conftest import TEST_DEV_KEY
from app.api.auth_common import sign_session_token, verify_session_token
from app.api.routers.auth_router import _init_data_hash
from app.api.security import MAX_AGE_SECONDS
from app.repo import users


def _replay_store_sample(result: str) -> float | None:
    from prometheus_client import REGISTRY
    return REGISTRY.get_sample_value(
        "oracleai_replay_store_total", {"result": result})


BOT_TOKEN = os.environ.get("BOT_TOKEN", "test:token")


@pytest.fixture
async def client(db, user):
    from httpx import ASGITransport, AsyncClient
    from app.api.deps import get_db
    from app.api.main import app
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def _secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def _build_init_data(tg_id: int, auth_date: int | None = None,
                     query_id: str = "AAH-test-bus200") -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": query_id,
        "user": json.dumps({"id": tg_id, "first_name": "Bus200", "username": f"bus200-{tg_id}"}),
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    h = hmac.new(_secret(BOT_TOKEN), check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": h})


# ─────────────────────── unit: хеш + токен ─────────────────────────────────

class TestInitDataHash:
    def test_hash_deterministic(self):
        raw = "a=1&b=2"
        assert _init_data_hash(raw) == _init_data_hash(raw)

    def test_hash_differs_for_different_inputs(self):
        assert _init_data_hash("a=1") != _init_data_hash("a=2")

    def test_hash_hex_length(self):
        assert len(_init_data_hash("x")) == 64


class TestSessionToken:
    def test_roundtrip(self):
        token = sign_session_token(900200001, int(time.time()) + 3600)
        assert verify_session_token(token) == 900200001

    def test_expired(self):
        past = int(time.time()) - 10
        token = sign_session_token(1, past)
        assert verify_session_token(token) is None

    def test_bad_signature(self):
        token = "1:9999999:deadbeef" * 4
        assert verify_session_token(token) is None

    def test_malformed(self):
        assert verify_session_token("") is None
        assert verify_session_token("no-colons") is None


# ─────────────────────── integration: replay-защита ────────────────────────

@pytest.mark.usefixtures("db")
class TestReplayProtection:
    async def test_duplicate_key_in_init_data_rejected(self, client, db):
        raw = _build_init_data(900200001)
        dup = raw + "&user=" + json.dumps({"id": 900200001, "first_name": "X"})
        r = await client.post("/api/auth/session", json={"init_data": dup})
        assert r.status_code == 401

    async def test_replay_same_init_data_returns_401(self, client, db):
        init_data = _build_init_data(900200002)
        r1 = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r1.status_code == 200
        token = r1.json()["session_token"]
        assert verify_session_token(token) == 900200002

        r2 = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r2.status_code == 401

    async def test_session_token_authenticates_after_mint(self, client, db):
        init_data = _build_init_data(900200003)
        r = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r.status_code == 200
        token = r.json()["session_token"]

        r_me = await client.get("/api/me", headers={"X-Session-Token": token})
        assert r_me.status_code == 200
        assert r_me.json()["tg_id"] == 900200003

    async def test_init_data_still_works_alongside_token(self, client, db):
        init_data = _build_init_data(900200004)
        r = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r.status_code == 200
        token = r.json()["session_token"]

        r_direct = await client.get("/api/me",
                                    headers={"X-Init-Data": init_data})
        assert r_direct.status_code == 200
        assert r_direct.json()["tg_id"] == 900200004

        r_token = await client.get("/api/me",
                                   headers={"X-Session-Token": token})
        assert r_token.status_code == 200
        assert r_token.json()["tg_id"] == 900200004

    async def test_expired_init_data_rejected(self, client, db):
        past = int(time.time()) - (MAX_AGE_SECONDS + 3600)
        init_data = _build_init_data(900200005, auth_date=past)
        r = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r.status_code == 401

    async def test_admin_route_accepts_session_token(self, client, db):
        # В тестах ADMIN_ID=1, поэтому tg_id=1 всегда owner и возвращает 200.
        # Проверяем, что session-токен работает в админке (роль = owner).
        init_data = _build_init_data(1)
        r = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r.status_code == 200
        token = r.json()["session_token"]

        r_admin = await client.get("/api/admin/me",
                                   headers={"X-Session-Token": token})
        assert r_admin.status_code == 200
        assert r_admin.json()["role"] == "owner"

    async def test_dev_user_still_works_in_test(self, client, db):
        await users.ensure(db, 900200006, "Dev", "dev")
        r = await client.get("/api/me", params={"dev_user": "900200006"})
        assert r.status_code == 200
        assert r.json()["tg_id"] == 900200006

    async def test_missing_init_data_returns_401(self, client, db):
        r = await client.post("/api/auth/session", json={})
        assert r.status_code == 401

    async def test_rate_limit_blocks_rapid_mints(self, client, db):
        """Лимит минта 10/мин на один tg_id: 11-я подписанная initData → 429.

        Один tg_id, разные query_id (иначе совпадёт строка → replay-защита
        сработает раньше лимита и тест проверял бы не то).
        """
        ok = 0
        for i in range(11):
            init_data = _build_init_data(900200007, query_id=f"AAH-bus200-{i}")
            r = await client.post("/api/auth/session", json={"init_data": init_data})
            if r.status_code == 200:
                ok += 1
            else:
                assert r.status_code == 429, r.text
                break
        assert ok == 10


# ─────────────────── метрика replay-store (BUS-343) ────────────────────────

class TestReplayStoreMetric:
    """Счётчик oracleai_replay_store_total{result=...} инкрементится только в
    exception-ветке _mark_init_data_used: solution EL по BUS-342 — fail-open
    допустим только при видимости инцидента. Успех и replay счётчик не трогают.

    Сбой Redis эмулируется _redis=None (RuntimeError внутри функции) — это
    детерминированно и не зависит от состояния внешнего контейнера.
    """

    @pytest.fixture
    async def client(self, db):
        from httpx import ASGITransport, AsyncClient
        from app.api.deps import get_db
        from app.api import main as api_main
        api_main.app.dependency_overrides[get_db] = lambda: db
        transport = ASGITransport(app=api_main.app)
        async with AsyncClient(transport=transport, base_url="http://test",
                               headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
            yield http
        api_main.app.dependency_overrides.clear()

    async def test_fail_open_increments_open_counter(self, client, db, monkeypatch):
        from app.api.routers import auth_router
        monkeypatch.setattr(auth_router, "_redis", None)
        before = _replay_store_sample("open") or 0

        init_data = _build_init_data(900210001)
        r = await client.post("/api/auth/session", json={"init_data": init_data})
        assert r.status_code == 200

        after = _replay_store_sample("open")
        assert after is not None
        assert after - before == 1

    async def test_fail_open_does_not_touch_closed_counter(self, client, db, monkeypatch):
        from app.api.routers import auth_router
        monkeypatch.setattr(auth_router, "_redis", None)
        before = _replay_store_sample("closed") or 0

        r = await client.post("/api/auth/session",
                              json={"init_data": _build_init_data(900210002)})
        assert r.status_code == 200
        assert (_replay_store_sample("closed") or 0) - before == 0

    async def test_success_does_not_increment_counter(self, client, db, monkeypatch):
        # Redis доступен → успех минта: обе ветки счётчика молчат.
        # Свежий клиент обязателен: модульный _redis держит пул с соединением
        # прошлого event loop'а (loop закрыт → "Event loop is closed" → уходит
        # в exception-ветку fail-open и честно инкрементит счётчик).
        from redis.asyncio import Redis
        from app.api.routers import auth_router
        from app.config import settings
        monkeypatch.setattr(
            auth_router, "_redis",
            Redis.from_url(settings.redis_url, decode_responses=True))
        before_open = _replay_store_sample("open") or 0
        before_closed = _replay_store_sample("closed") or 0

        r = await client.post("/api/auth/session",
                              json={"init_data": _build_init_data(900210003)})
        assert r.status_code == 200
        assert (_replay_store_sample("open") or 0) - before_open == 0
        assert (_replay_store_sample("closed") or 0) - before_closed == 0

    async def test_fail_closed_increments_closed_counter(self, client, db, monkeypatch):
        from app.api.routers import auth_router
        monkeypatch.setattr(auth_router, "_redis", None)
        monkeypatch.setattr(auth_router.settings, "replay_fail_closed", True)
        before = _replay_store_sample("closed") or 0

        r = await client.post("/api/auth/session",
                              json={"init_data": _build_init_data(900210004)})
        assert r.status_code == 401

        after = _replay_store_sample("closed")
        assert after is not None
        assert after - before == 1

    async def test_counter_children_preinitialized(self):
        # Увеличение с нуля должно быть видно rate()/increase(): prometheus_client
        # создаёт ряд только при .inc(), а без предыдущей точки рост 0→N алерт
        # не видит (проверено на staging: счётчик=2, increase=0, алерт inactive).
        # Оба детей обязаны существовать сразу после импорта модуля.
        from app.api.routers import auth_router  # noqa: F401 — импорт регистрирует
        assert _replay_store_sample("open") == 0.0
        assert _replay_store_sample("closed") == 0.0
