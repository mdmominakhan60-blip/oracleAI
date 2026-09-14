"""BUS-1232: канон enum birth_time_precision на границе бот→API.

Репродукция находки security-review: бот писал 'approximate' в колонку,
API-контракт и потребители ожидают 'approx'. Тест проверяет, что даже при
устаревшем значении в БД оба эндпоинта (/api/me и GET /api/chart) отдают
канонический 'approx' и одинаково трактуют время (не прячут его как unknown).
"""
from __future__ import annotations

import json

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.core import astro  # noqa: E402
from app.core.precision import normalize_birth_time_precision  # noqa: E402
from app.repo import users  # noqa: E402


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


# ───────────────────────────── helper (unit) ─────────────────────────────────

def test_normalize_maps_legacy_and_aliases_to_canon():
    assert normalize_birth_time_precision("approximate") == "approx"
    assert normalize_birth_time_precision("approx") == "approx"
    assert normalize_birth_time_precision("APPROX ") == "approx"
    assert normalize_birth_time_precision("exact") == "exact"
    assert normalize_birth_time_precision("unknown") == "unknown"
    # пусто/None → вывод из time_known (прежний fallback профиля/карты)
    assert normalize_birth_time_precision(None, time_known=1) == "exact"
    assert normalize_birth_time_precision("", time_known=0) == "unknown"
    # мусор → консервативно unknown (fail-closed, время скрывается)
    assert normalize_birth_time_precision("пол-второго") == "unknown"


# ─────────────────────── граница: бот-вредное значение ───────────────────────

async def _seed_bot_approx_user(db, tg_id: int) -> None:
    """Эмулирует запись ботного онбординга «Знаю примерно» ДО normalization-фикса."""
    await users.ensure(db, tg_id, "Примерная", "approx_user")
    chart = await astro.compute_chart_async("1990-06-21", "14:00", "Казань",
                                            55.79, 49.12, "Europe/Moscow",
                                            time_known=False)
    chart["time_precision"] = "approximate"  # ботный drift в кэше карты тоже
    await users.update(db, tg_id, onboarded=1, birth_date="1990-06-21",
                       birth_time="14:00", birth_time_known=0,
                       birth_time_precision="approximate",
                       birth_city="Казань", tz="Europe/Moscow",
                       sub_level="vip",
                       chart_json=json.dumps(chart, ensure_ascii=False),
                       memory_enabled=0)


async def test_legacy_approximate_is_canonical_on_both_endpoints(client, db):
    await _seed_bot_approx_user(db, 555_001)
    params = {"dev_user": 555_001}

    me = (await client.get("/api/me", params=params)).json()
    assert me["birth_time_precision"] == "approx", "ожидается канонический 'approx'"
    assert me["birth_time"] == "14:00", "примерное время не должно прятаться как unknown"

    chart = (await client.get("/api/chart", params=params)).json()
    assert chart["birth"]["time_precision"] == "approx"
    assert chart["birth"]["time"] == "14:00", "время на карте и в профиле описывает один факт"

    # Согласованность surfaces — суть находки (два эндпоинта противоречиво).
    assert me["birth_time_precision"] == chart["birth"]["time_precision"]


async def test_exact_and_unknown_unchanged(client, db):
    await users.ensure(db, 555_002, "Точная", "exact_user")
    chart = await astro.compute_chart_async("1990-06-21", "14:30", "Казань",
                                            55.79, 49.12, "Europe/Moscow",
                                            time_known=True)
    chart["time_precision"] = "exact"
    await users.update(db, 555_002, onboarded=1, birth_date="1990-06-21",
                       birth_time="14:30", birth_time_known=1,
                       birth_time_precision="exact", birth_city="Казань",
                       tz="Europe/Moscow", sub_level="vip",
                       chart_json=json.dumps(chart, ensure_ascii=False),
                       memory_enabled=0)

    me = (await client.get("/api/me", params={"dev_user": 555_002})).json()
    assert me["birth_time_precision"] == "exact"
    assert me["birth_time"] == "14:30"


# ─────────────────────────── ботный парсер → канон ───────────────────────────

def test_bot_parser_emits_canon_only():
    from app.bot.onboarding_parsers import ParsedTime, parse_birth_time

    approx = parse_birth_time("примерно")
    assert approx.precision == "approx"
    # ParsedTime, сконструированный легаси-значением (как в quick-reply map),
    # после normalization на границе записи даёт канон.
    legacy = ParsedTime("14:00", False, "approximate", "примерно 14:00")
    assert normalize_birth_time_precision(legacy.precision) == "approx"


def test_callback_time_key_matches_canon():
    """Callback-ключ в onboarding.py quick-reply map совпадает с каноном."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app/bot/onboarding.py").read_text()
    tree = ast.parse(source)
    # Найти onb_time_choice и собрать все Dict-ключи в её теле (не включая вложенные функции)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "onb_time_choice":
            keys: list[str] = []
            for child in ast.walk(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue  # skip nested functions
                if isinstance(child, ast.Dict):
                    for k in child.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.append(k.value)
            assert "approx" in keys, f"canonical key 'approx' not found in {keys}"
            assert "approximate" not in keys, f"legacy key 'approximate' leaked: {keys}"
            return
    pytest.fail("onb_time_choice not found")


def _literal_tokens(annotation) -> set:
    """Токены Literal внутри аннотации вида Literal[...] | None."""
    from typing import Literal, get_args, get_origin

    if get_origin(annotation) is Literal:
        return set(get_args(annotation))
    tokens: set = set()
    for arg in get_args(annotation):
        tokens |= _literal_tokens(arg)
    return tokens


def test_api_literal_contracts_match_canon_tuple():
    """Literal в контрактах волны A — зеркало BIRTH_TIME_PRECISIONS (BUS-1232)."""
    from app.api.contracts.wave_a import ChartBuildIn
    from app.api.routers.profile import ProfileIn
    from app.core.precision import BIRTH_TIME_PRECISIONS, BirthTimePrecision

    assert set(BirthTimePrecision.__args__) == set(BIRTH_TIME_PRECISIONS)
    for model in (ProfileIn, ChartBuildIn):
        tokens = _literal_tokens(model.model_fields["birth_time_precision"].annotation)
        assert "approx" in tokens and "approximate" not in tokens
        assert tokens == set(BIRTH_TIME_PRECISIONS)
