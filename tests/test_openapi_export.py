"""Экспорт OpenAPI-схемы для фронтенда волны A (BUS-805, G-1 из BUS-735).

Контракт: /api/openapi.json при DEV_MODE=0 отдаётся только под подписью
Telegram (fail-closed 401 без identity); в DEV_MODE схему отдаёт встроенный
публичный FastAPI-роут. Перенос моделей в app/api/contracts/wave_a.py не
должен менять схему эндпоинтов волны A.
"""
from __future__ import annotations

import json
from time import time
from urllib.parse import urlencode

import pytest

from app.config import settings

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app, openapi_router  # noqa: E402
from app.api.security import parse_init_data  # noqa: E402


def _signed_init_data(tg_id: int = 1001) -> str:
    fields = {"user": json.dumps({"id": tg_id}, separators=(",", ":")),
              "auth_date": str(int(time()))}
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    import hashlib
    import hmac
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
async def dev_client(db):
    """DEV_MODE=1 (настройки conftest): встроенный публичный роут на месте."""
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
async def prod_client(db, monkeypatch):
    """Прод-подобное приложение: DEV_MODE=0, auth-роут схемы зарегистрирован.

    Тестовый app собран при DEV_MODE=1, поэтому встроенный публичный роут
    `/api/openapi.json` сидит в таблице раньше gated-роута и матчится первым.
    Для честного 401 убираем его на время теста и возвращаем на прежний индекс.
    """
    monkeypatch.setattr(settings, "dev_mode", False)
    builtin = [r for r in app.routes
               if getattr(r, "path", None) == "/api/openapi.json"]
    assert len(builtin) == 1, "структура роут-таблицы app изменилась — тест врёт"
    idx = app.routes.index(builtin[0])
    app.routes.remove(builtin[0])

    app.dependency_overrides[get_db] = lambda: db
    before = len(app.routes)
    app.include_router(openapi_router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    del app.routes[before:]
    app.routes.insert(idx, builtin[0])
    app.dependency_overrides.clear()


async def test_openapi_requires_auth_when_dev_mode_off(prod_client):
    """Без подписи Telegram — 401 (fail-closed), схема не отдаётся."""
    response = await prod_client.get("/api/openapi.json")
    assert response.status_code == 401


def _unwrap(node: dict) -> dict:
    """Разворот anyOf-обёрток FastAPI (`X | None` → anyOf [$ref/схема, null])."""
    while "anyOf" in node:
        non_null = [p for p in node["anyOf"] if p.get("type") != "null"]
        if len(non_null) == 1:
            node = non_null[0]
        else:
            break
    return node


def _body_ref(schema: dict, path: str) -> tuple[str, dict]:
    """Имя модели и её схема для тела POST-запроса.

    FastAPI рендерит `item: DrawIn | None` как anyOf [$ref, null], а
    `item: AskIn` — как прямой $ref; хелпер понимает оба варианта.
    """
    node = schema["paths"][path]["post"]["requestBody"]["content"][
        "application/json"]["schema"]
    node = _unwrap(node)
    name = node["$ref"].rsplit("/", 1)[-1]
    return name, schema["components"]["schemas"][name]


async def test_openapi_requires_auth_when_dev_mode_off(prod_client):
    """Без подписи Telegram — 401 (fail-closed), схема не отдаётся."""
    response = await prod_client.get("/api/openapi.json")
    assert response.status_code == 401


async def test_openapi_serves_schema_under_signature(prod_client, user):
    """Авторизованная клиентка получает валидную схему с путями волны A."""
    response = await prod_client.get(
        "/api/openapi.json", headers={"x-init-data": _signed_init_data(user["tg_id"])})
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    # сам роут схемы в схеме не светится
    assert "/api/openapi.json" not in schema["paths"]
    assert {"paths", "components", "info"} <= schema.keys()


async def test_openapi_wave_a_request_models_match_contracts(prod_client, user):
    """Сверка схемы волны A с контрактами: chat, tarot, chart, feedback."""
    response = await prod_client.get(
        "/api/openapi.json", headers={"x-init-data": _signed_init_data(user["tg_id"])})
    assert response.status_code == 200
    schema = response.json()

    from app.api.contracts import wave_a
    from app.api.contracts.chat import AskIn

    # 1. POST /api/ask — тело AskIn (текст 1..1000, allow_paid по умолчанию)
    ask_model, ask_schema = _body_ref(schema, "/api/ask")
    assert ask_model == "AskIn"
    assert ask_schema["properties"]["text"]["minLength"] == 1
    assert ask_schema["properties"]["text"]["maxLength"] == 1000
    assert ask_schema["properties"]["allow_paid"]["default"] is True

    # 2. POST /api/tarot/draw — тело DrawIn | None (question/deck опциональны)
    draw_model, draw_schema = _body_ref(schema, "/api/tarot/draw")
    assert draw_model == "DrawIn"
    assert set(draw_schema["properties"]) == {"question", "deck"}
    deck_types = set()
    deck = draw_schema["properties"]["deck"]
    for part in deck.get("anyOf", [deck]):
        deck_types.add(_unwrap(part).get("type"))
    assert deck_types == {"string", "null"}

    # 3. POST /api/chart — тело ChartBuildIn | None
    chart_model, chart_schema = _body_ref(schema, "/api/chart")
    assert chart_model == "ChartBuildIn"
    assert _unwrap(chart_schema["properties"]["birth_city"])["maxLength"] == 60

    # 4. POST /api/tarot/outcome/{reading_id} — закрытое множество исходов
    #    OutcomeIn из contracts.wave_a.
    outcome_model, outcome_schema = _body_ref(schema, "/api/tarot/outcome/{reading_id}")
    assert outcome_model == "OutcomeIn"
    assert outcome_schema["properties"]["outcome"]["enum"] == list(
        wave_a.OutcomeIn.model_fields["outcome"].annotation.__args__)


async def test_openapi_dev_mode_keeps_builtin_public_route(dev_client):
    """В DEV_MODE встроенный публичный роут отдаёт схему без auth (регресс: не сломать Swagger)."""
    response = await dev_client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.json()["openapi"].startswith("3.")
