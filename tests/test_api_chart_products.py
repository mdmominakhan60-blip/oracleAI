from __future__ import annotations

import json

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.main import app
from app.core import chart_products
from app.repo import readings, users


@pytest.fixture
async def product_client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def auth(user) -> dict:
    return {"dev_user": user["tg_id"]}


async def test_synastry_returns_versioned_owner_scoped_contract(product_client, db, user):
    chart = json.loads(user["chart_json"])
    partner_id = await readings.add_partner(
        db, user["tg_id"], "Алексей", "1991-02-03", birth_time="10:00",
        birth_city="Казань", lat=55.79, lon=49.12, tz="Europe/Moscow", chart=chart,
    )

    response = await product_client.post("/api/synastry", params=auth(user),
                                         json={"partner_id": partner_id})

    assert response.status_code == 200
    data = response.json()
    assert data["synastry_schema_version"] == 1
    assert data["product"] == "synastry"
    assert data["partner"]["partner_id"] == partner_id
    assert data["person"]["planets"]
    assert all("birth_date" not in item for item in data["person"]["planets"])


async def test_synastry_does_not_cross_owner_boundary(product_client, db, user):
    other = await users.ensure(db, 2002, "Другой пользователь", "other")
    partner_id = await readings.add_partner(
        db, other["tg_id"], "Чужой партнёр", "1991-02-03",
    )

    response = await product_client.post("/api/synastry", params=auth(user),
                                         json={"partner_id": partner_id})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "partner_not_found"


async def test_synastry_rejects_date_only_partner(product_client, db, user):
    chart = json.loads(user["chart_json"])
    chart["precision"] = "date_only"
    partner_id = await readings.add_partner(
        db, user["tg_id"], "Без времени", "1991-02-03", chart=chart,
    )

    response = await product_client.post("/api/synastry", params=auth(user),
                                         json={"partner_id": partner_id})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "exact_charts_required"
    assert response.json()["detail"]["missing"] == ["partner"]


async def test_transits_returns_date_aware_contract_without_birth_pii(product_client, user):
    response = await product_client.post(
        "/api/transits", params=auth(user),
        json={"as_of": "2026-08-26", "time": "09:30"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transit_schema_version"] == 1
    assert data["product"] == "transits"
    assert data["precision"] == "instant"
    assert data["sampled_at"] == "2026-08-26T09:30:00+00:00"
    assert data["transit_planets"]
    assert "birth_date" not in json.dumps(data, ensure_ascii=False)


async def test_transits_rejects_invalid_date(product_client, user):
    response = await product_client.post(
        "/api/transits", params=auth(user),
        json={"as_of": "not-a-date"},
    )

    assert response.status_code == 422


async def test_composite_returns_versioned_owner_scoped_contract(product_client, db, user):
    chart = json.loads(user["chart_json"])
    partner_id = await readings.add_partner(
        db, user["tg_id"], "Алексей", "1991-02-03", birth_time="10:00",
        birth_city="Казань", lat=55.79, lon=49.12, tz="Europe/Moscow", chart=chart,
    )

    response = await product_client.post("/api/composite", params=auth(user),
                                         json={"partner_id": partner_id})

    assert response.status_code == 200
    data = response.json()
    assert data["composite_schema_version"] == 1
    assert data["product"] == "composite"
    assert data["precision"] == "exact"
    assert data["sources"]["partner"]["partner_id"] == partner_id
    assert len(data["points"]) == 10
    assert "birth_date" not in json.dumps(data, ensure_ascii=False)


async def test_composite_does_not_cross_owner_boundary(product_client, db, user):
    other = await users.ensure(db, 2002, "Другой пользователь", "other")
    partner_id = await readings.add_partner(
        db, other["tg_id"], "Чужой партнёр", "1991-02-03",
    )

    response = await product_client.post("/api/composite", params=auth(user),
                                         json={"partner_id": partner_id})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "partner_not_found"


async def test_composite_rejects_non_exact_partner(product_client, db, user):
    chart = json.loads(user["chart_json"])
    chart["precision"] = "date_only"
    partner_id = await readings.add_partner(
        db, user["tg_id"], "Без времени", "1991-02-03", chart=chart,
    )

    response = await product_client.post("/api/composite", params=auth(user),
                                         json={"partner_id": partner_id})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "exact_charts_required"
    assert response.json()["detail"]["missing"] == ["partner"]


async def test_returns_passes_owner_location_without_birth_pii(product_client, db, user, monkeypatch):
    seen = {}

    def fake_returns(natal_chart, *, target_year, planet_id, lat, lon, tz_name):
        seen.update(target_year=target_year, planet_id=planet_id, lat=lat,
                    lon=lon, tz_name=tz_name, has_chart=bool(natal_chart))
        return {
            "returns_schema_version": 1,
            "product": "returns",
            "planet": planet_id,
            "target_year": target_year,
            "precision": "exact",
            "match_count": 1,
            "matches": [],
            "limitations": ["Это астрономический момент возврата, а не гарантия события."],
        }

    await users.update(db, user["tg_id"], birth_lat=55.79, birth_lon=49.12)
    monkeypatch.setattr(chart_products, "build_returns_contract", fake_returns)
    response = await product_client.post(
        "/api/returns", params=auth(user), json={"planet": "Sun", "year": 2027},
    )

    assert response.status_code == 200
    assert response.json()["returns_schema_version"] == 1
    assert response.json()["product"] == "returns"
    assert seen == {
        "target_year": 2027, "planet_id": "Sun", "lat": 55.79,
        "lon": 49.12, "tz_name": "Europe/Moscow", "has_chart": True,
    }
    assert "birth_date" not in json.dumps(response.json(), ensure_ascii=False)


async def test_returns_validates_supported_planet_and_year(product_client, user):
    unsupported = await product_client.post(
        "/api/returns", params=auth(user), json={"planet": "Jupiter", "year": 2027},
    )
    invalid_year = await product_client.post(
        "/api/returns", params=auth(user), json={"planet": "Sun", "year": 1800},
    )

    assert unsupported.status_code == 422
    assert invalid_year.status_code == 422


async def test_returns_real_solar_event(product_client, db, user):
    await users.update(db, user["tg_id"], birth_lat=55.79, birth_lon=49.12)
    response = await product_client.post(
        "/api/returns", params=auth(user), json={"planet": "Sun", "year": 2027},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["returns_schema_version"] == 1
    assert data["product"] == "returns"
    assert data["match_count"] >= 1
    assert data["return_at_utc"].startswith("2027-")
    assert data["return_at_local"].endswith("+03:00")
    assert "birth_date" not in json.dumps(data, ensure_ascii=False)


async def test_returns_requires_saved_owner_location(product_client, user):
    response = await product_client.post(
        "/api/returns", params=auth(user), json={"planet": "Sun", "year": 2027},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "return_location_required"
