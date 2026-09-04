from datetime import date, time

import pytest

from app.core import chart_products
from app.core.chart_products import (
    ChartProductError,
    build_composite_contract,
    build_returns_contract,
    build_synastry_contract,
    build_transit_contract,
    circular_midpoint,
)


def _chart(*, precision="exact", offset=0.0):
    names = [
        ("Солнце", 10.0), ("Луна", 50.0), ("Меркурий", 80.0),
        ("Венера", 100.0), ("Марс", 140.0), ("Юпитер", 180.0),
        ("Сатурн", 220.0), ("Уран", 260.0), ("Нептун", 300.0),
        ("Плутон", 340.0),
    ]
    return {
        "mode": "full",
        "precision": precision,
        "planets": [
            {
                "name": name,
                "sign": "Овен",
                "deg": round((abs_deg + offset) % 30, 1),
                "deg_exact": (abs_deg + offset) % 30,
                "abs_deg": (abs_deg + offset) % 360,
                "abs_deg_exact": (abs_deg + offset) % 360,
                "retro": False,
            }
            for name, abs_deg in names
        ],
    }


def test_synastry_contract_is_versioned_and_labeled():
    result = build_synastry_contract(_chart(), _chart(offset=120), partner_id=7,
                                     partner_label="Алексей")

    assert result["synastry_schema_version"] == 1
    assert result["product"] == "synastry"
    assert result["precision"] == "exact"
    assert result["partner"]["partner_id"] == 7
    assert result["person"]["planets"][0]["id"] == "Sun"
    assert all(item["first_role"] == "owner" for item in result["aspects"])
    assert any(item["code"] == "trine" for item in result["aspects"])


def test_synastry_rejects_non_exact_chart():
    with pytest.raises(ChartProductError) as error:
        build_synastry_contract(_chart(precision="date_only"), _chart(),
                                partner_id=7, partner_label="Алексей")

    assert error.value.code == "exact_charts_required"
    assert error.value.missing == ["owner"]


def test_transit_contract_has_day_precision_without_time():
    result = build_transit_contract(_chart(), as_of=date(2026, 8, 26))

    assert result["transit_schema_version"] == 1
    assert result["product"] == "transits"
    assert result["precision"] == "day"
    assert result["as_of"] == "2026-08-26"
    assert result["sampled_at"] == "2026-08-26T12:00:00+00:00"
    assert result["transit_planets"]
    assert "Лун" in result["limitations"][0]


def test_transit_contract_marks_explicit_time_as_instant():
    result = build_transit_contract(_chart(precision="date_only"),
                                    as_of=date(2026, 8, 26), clock=time(9, 30))

    assert result["precision"] == "instant"
    assert result["sampled_at"] == "2026-08-26T09:30:00+00:00"
    assert result["natal_precision"] == "date_only"


@pytest.mark.asyncio
async def test_agent_synastry_context_includes_versioned_contract(db, user):
    import json

    from app.core import agent
    from app.repo import readings

    chart = json.loads(user["chart_json"])
    await readings.add_partner(
        db, user["tg_id"], "Алексей", "1991-02-03", birth_time="10:00",
        birth_city="Казань", lat=55.79, lon=49.12, tz="Europe/Moscow", chart=chart,
    )
    evidence = await agent._synastry_data(db, user, "1991-02-03")

    assert evidence is not None
    assert "synastry contract" in evidence
    assert '"synastry_schema_version": 1' in evidence


@pytest.mark.asyncio
async def test_agent_transit_tool_includes_structured_evidence(db, user):
    from app.core import tool_registry as skills

    evidence = await skills._run_get_transits(db, user, {"as_of": "2026-08-26"})

    assert "Детерминированное transit evidence" in evidence
    assert '"transit_schema_version": 1' in evidence
    assert '"as_of": "2026-08-26"' in evidence


def test_circular_midpoint_handles_zero_degree_wraparound():
    assert circular_midpoint(359.0, 1.0) == pytest.approx(0.0)
    assert circular_midpoint(1.0, 359.0) == pytest.approx(0.0)
    assert circular_midpoint(10.0, 170.0) == pytest.approx(90.0)


def test_composite_contract_contains_source_longitudes_and_major_aspects():
    result = build_composite_contract(
        _chart(), _chart(offset=20.0), partner_id=7, partner_label="Алексей",
    )

    assert result["composite_schema_version"] == 1
    assert result["product"] == "composite"
    assert result["precision"] == "exact"
    assert len(result["points"]) == 10
    sun = next(item for item in result["points"] if item["id"] == "Sun")
    assert sun["source"]["owner_abs_deg_exact"] == pytest.approx(10.0)
    assert sun["source"]["partner_abs_deg_exact"] == pytest.approx(30.0)
    assert sun["abs_deg_exact"] == pytest.approx(20.0)
    assert all(item["first_role"] == "composite" for item in result["aspects"])


def test_composite_rejects_date_only_chart():
    with pytest.raises(ChartProductError) as error:
        build_composite_contract(
            _chart(precision="date_only"), _chart(), partner_id=7, partner_label="Алексей",
        )

    assert error.value.code == "exact_charts_required"
    assert error.value.missing == ["owner"]


def test_returns_requires_owner_location():
    with pytest.raises(ChartProductError) as error:
        build_returns_contract(_chart(), target_year=2027)

    assert error.value.code == "return_location_required"
    assert error.value.missing == ["lat", "lon", "tz"]


def test_returns_rejects_unsupported_planet():
    with pytest.raises(ChartProductError) as error:
        build_returns_contract(
            _chart(), target_year=2027, planet_id="Jupiter",
            lat=55.79, lon=49.12, tz_name="Europe/Moscow",
        )

    assert error.value.code == "unsupported_planet"


def test_returns_contract_finds_bounded_solar_crossing(monkeypatch):
    def fake_longitude(instant, planet_id):
        assert planet_id == "Sun"
        elapsed_hours = (
            instant - chart_products.datetime(2027, 1, 1, tzinfo=chart_products.timezone.utc)
        ).total_seconds() / 3600
        return (10.0 + elapsed_hours * 0.01) % 360

    monkeypatch.setattr(chart_products, "_return_planet_longitude", fake_longitude)
    result = build_returns_contract(
        _chart(), target_year=2027, planet_id="Sun",
        lat=55.79, lon=49.12, tz_name="Europe/Moscow",
    )

    assert result["returns_schema_version"] == 1
    assert result["product"] == "returns"
    assert result["planet"] == "Sun"
    assert result["match_count"] == 1
    assert result["return_at_utc"].startswith("2027-01-01T00:00:00")
    assert result["return_at_local"].endswith("+03:00")


@pytest.mark.asyncio
async def test_agent_composite_tool_includes_versioned_evidence(db, user):
    import json

    from app.core import tool_registry as skills
    from app.repo import readings

    chart = json.loads(user["chart_json"])
    partner_id = await readings.add_partner(
        db, user["tg_id"], "Алексей", "1991-02-03", birth_time="10:00",
        birth_city="Казань", lat=55.79, lon=49.12, tz="Europe/Moscow", chart=chart,
    )

    evidence = await skills._run_get_composite(db, user, {"partner_id": partner_id})

    assert "Детерминированное composite evidence" in evidence
    assert '"composite_schema_version": 1' in evidence
    assert '"partner_id": %d' % partner_id in evidence


@pytest.mark.asyncio
async def test_agent_returns_tool_includes_versioned_evidence(monkeypatch, db, user):
    from app.core import tool_registry as skills

    user_data = dict(user)
    user_data.update(birth_lat=55.79, birth_lon=49.12, tz="Europe/Moscow")

    def fake_returns(*args, **kwargs):
        return {
            "returns_schema_version": 1,
            "product": "returns",
            "planet": kwargs["planet_id"],
            "target_year": kwargs["target_year"],
            "precision": "exact",
            "match_count": 1,
            "matches": [],
            "limitations": [],
        }

    monkeypatch.setattr(chart_products, "build_returns_contract", fake_returns)
    evidence = await skills._run_get_returns(db, user_data, {"planet": "Sun", "year": 2027})

    assert "Детерминированное returns evidence" in evidence
    assert '"returns_schema_version": 1' in evidence
    assert '"target_year": 2027' in evidence


def test_composite_validator_rejects_corrupted_midpoint():
    from app.core.chart_products import validate_composite_contract
    contract = build_composite_contract(_chart(), _chart(offset=120), partner_id=7, partner_label="Алексей")
    contract["points"][0]["abs_deg_exact"] = (contract["points"][0]["abs_deg_exact"] + 1) % 360
    with pytest.raises(ChartProductError, match="midpoint"):
        validate_composite_contract(contract)


def test_transit_validator_rejects_unknown_aspect_role():
    from app.core.chart_products import validate_transit_contract
    contract = build_transit_contract(_chart(), as_of=date(2026, 8, 26))
    if contract["aspects_to_natal"]:
        contract["aspects_to_natal"][0]["first_role"] = "owner"
        with pytest.raises(ChartProductError, match="Роль"):
            validate_transit_contract(contract)


def test_returns_validator_rejects_unsorted_matches():
    from app.core.chart_products import validate_returns_contract
    contract = {
        "returns_schema_version": 1,
        "product": "returns",
        "precision": "exact",
        "planet": "Sun",
        "natal_longitude_deg": 10.0,
        "match_count": 2,
        "matches": [
            {"return_at_utc": "2026-09-01T00:00:00+00:00", "return_longitude_deg": 10.0},
            {"return_at_utc": "2026-08-01T00:00:00+00:00", "return_longitude_deg": 10.0},
        ],
    }
    with pytest.raises(ChartProductError, match="отсортированы"):
        validate_returns_contract(contract)
