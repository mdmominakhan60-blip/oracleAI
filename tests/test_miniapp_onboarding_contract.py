"""Onboarding boundary tests: no real DB, network, or paid model requests."""
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.common.onboarding import normalize_birth_time, onboarding_fields
from app.api.routers import profile


def payload(**overrides):
    return profile.ProfileIn(**{
        "name": "  Анна  ", "birth_date": "1990-06-21", "birth_time": "14:30",
        "birth_time_precision": "exact", "city": "кишинев", "intent": "astro",
        "onboarding_complete": True, **overrides,
    })


@pytest.mark.parametrize("value,precision,expected", [
    ("0:00", "exact", ("00:00", True)),
    ("23:59", "approx", ("23:59", False)),
    (None, "unknown", (None, False)),
    ("14:30", "unknown", (None, False)),
])
def test_time_precision(value, precision, expected):
    assert normalize_birth_time(value, precision) == expected


@pytest.mark.parametrize("value", [None, "", "24:00", "12:60", "-1:00", "9:9", "aa:bb"])
def test_exact_time_never_fabricates_midnight(value):
    with pytest.raises(HTTPException):
        normalize_birth_time(value, "exact")


@pytest.mark.parametrize("changes", [
    {"birth_date": "1990-02-30"}, {"birth_date": "1899-12-31"},
    {"birth_date": (date.today() + timedelta(days=1)).isoformat()},
    {"name": " "}, {"city": "Казань, несуществующая страна"},
    {"city": "невозможнонайти"}, {"birth_time_precision": None},
    {"intent": None},
])
async def test_invalid_inputs_never_compute_or_write(monkeypatch, changes):
    compute = AsyncMock()
    monkeypatch.setattr("app.api.common.onboarding.astro.compute_chart_async", compute)
    with pytest.raises(HTTPException):
        await onboarding_fields(payload(**changes), {}, None)
    compute.assert_not_awaited()


async def test_final_submission_requires_complete_fields():
    with pytest.raises(HTTPException):
        await onboarding_fields(profile.ProfileIn(onboarding_complete=True), {}, None)


@pytest.mark.parametrize("precision,stored,known", [
    ("exact", "14:30", 1), ("approx", "14:30", 0), ("unknown", None, 0),
])
async def test_profile_saves_chart_and_completion_together(monkeypatch, precision, stored, known):
    compute = AsyncMock(return_value={"mode": "full", "sun": "Близнецы"})
    update = AsyncMock()
    monkeypatch.setattr("app.api.common.onboarding.astro.compute_chart_async", compute)
    monkeypatch.setattr(profile.users, "update", update)
    monkeypatch.setattr(profile.analytics, "track", AsyncMock())
    user = {"tg_id": 71, "onboarded": 0}
    result = await profile.update_profile(payload(birth_time_precision=precision), user, None)
    assert result["ok"] and result["onboarded"]
    update.assert_awaited_once()
    fields = update.await_args.kwargs
    assert fields["name"] == "Анна"
    assert fields["birth_time"] == stored
    assert fields["birth_time_known"] == known
    assert fields["birth_time_precision"] == precision
    assert fields["onboarded"] == 1 and fields["onboarding_step"] is None
    assert fields["tz"] == "Europe/Chisinau"
    assert not {"sub_level", "sub_until", "crystals", "persona"} & fields.keys()
    assert compute.await_args.kwargs["time_known"] is bool(known)


async def test_failed_chart_does_not_mark_onboarded(monkeypatch):
    monkeypatch.setattr("app.api.common.onboarding.astro.compute_chart_async", AsyncMock(side_effect=RuntimeError("unavailable")))
    update = AsyncMock()
    monkeypatch.setattr(profile.users, "update", update)
    with pytest.raises(RuntimeError):
        await profile.update_profile(payload(), {"tg_id": 71, "onboarded": 0}, None)
    update.assert_not_awaited()


async def test_old_settings_request_does_not_trigger_onboarding(monkeypatch):
    update = AsyncMock()
    compute = AsyncMock()
    monkeypatch.setattr(profile.users, "update", update)
    monkeypatch.setattr(profile.analytics, "track", AsyncMock())
    monkeypatch.setattr("app.api.common.onboarding.astro.compute_chart_async", compute)
    await profile.update_profile(profile.ProfileIn(memory_enabled=False), {"tg_id": 71, "onboarded": 1}, None)
    assert update.await_args.kwargs == {"memory_enabled": 0}
    compute.assert_not_awaited()


def test_unknown_precision_rejected_at_http_boundary():
    with pytest.raises(ValidationError):
        payload(birth_time_precision="maybe")


async def test_city_suggestions_are_identifiable_and_can_be_submitted(monkeypatch):
    from app.api.routers.chart import city_suggest
    monkeypatch.setattr("app.api.common.onboarding.astro.compute_chart_async", AsyncMock(return_value={}))
    response = await city_suggest(q="киши", user={}, db=None)
    assert len(response["items"]) == 1
    city = response["items"][0]
    assert city["country"] == "Молдова"
    assert city["timezone"] == "Europe/Chisinau"
    fields = await onboarding_fields(payload(city=city["key"]), {}, None)
    assert fields["birth_lat"] == 47.01


async def test_short_city_query_is_empty():
    from app.api.routers.chart import city_suggest
    assert await city_suggest(q="к", user={}, db=None) == {"items": []}


@pytest.mark.parametrize("changes,precision,time,known", [
    ({"birth_city": "Казань"}, "approx", "14:30", False),
    ({"birth_time": None}, "unknown", None, False),
    ({"birth_time": "9:30"}, "exact", "09:30", True),
    ({"birth_time": "11:45", "birth_time_precision": "approx"}, "approx", "11:45", False),
])
async def test_chart_edits_preserve_precision(monkeypatch, changes, precision, time, known):
    from importlib import import_module
    from app.api.contracts.wave_a import ChartBuildIn
    route = import_module("app.api.routers.chart")
    user = {"tg_id": 71, "birth_date": "1990-06-21", "birth_city": "Казань",
            "birth_time": "14:30", "birth_time_precision": "approx", "birth_time_known": 0}
    monkeypatch.setattr(route.users, "chart_of", lambda _: {})
    monkeypatch.setattr(route.geo, "resolve_city_info_async", AsyncMock(return_value={
        "lat": 55.79, "lon": 49.12, "tz": "Europe/Moscow", "coordinate_source": "builtin",
        "coordinate_confidence": 0.8, "timezone_source": "builtin",
    }))
    monkeypatch.setattr(route.astro, "compute_chart_async", AsyncMock(return_value={"mode": "lite"}))
    update = AsyncMock()
    monkeypatch.setattr(route.users, "update", update)
    result = await route.build_chart(ChartBuildIn(**changes), user, None)
    assert result["birth"]["time_precision"] == precision
    assert result["birth"]["time"] == time
    assert result["birth"]["time_known"] is known
    assert update.await_args.kwargs["birth_time_precision"] == precision


async def test_cached_unknown_time_does_not_expose_calculation_noon():
    from app.api.routers.chart import _chart_payload
    user = {"birth_date": "1990-06-21", "birth_city": "Казань", "birth_time": "12:00", "birth_time_known": 0, "birth_time_precision": "unknown"}
    result = _chart_payload({}, user)
    assert result["birth"]["time"] is None
