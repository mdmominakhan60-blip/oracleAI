from __future__ import annotations

import pytest

from app.core import astro
from app.core.chart_contract import ASPECT_ORBS, CHART_CONTRACT_VERSION


def test_full_chart_exposes_versioned_calculation_contract():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12,
        "Europe/Moscow", time_known=True,
    )

    assert chart["mode"] == "full"
    contract = chart["calculation"]
    assert contract["contract_version"] == CHART_CONTRACT_VERSION
    assert contract["precision"] == "exact"
    assert contract["angular_data_available"] is True
    assert contract["config"]["zodiac_type"] == "Tropical"
    assert contract["config"]["house_system"] == "P"
    assert contract["config"]["house_system_name"] == "Placidus"
    assert contract["config"]["perspective_type"] == "Apparent Geocentric"
    assert contract["config"]["node_mode"] == "true"
    assert contract["config"]["node_mode_label"] == "True Node"
    assert contract["config"]["aspect_policy"]["orbs_deg"] == ASPECT_ORBS
    assert contract["input"]["birth_date"] == "1990-06-21"
    assert contract["input"]["birth_time"] == "14:30"
    assert contract["input"]["tz"] == "Europe/Moscow"
    assert "Chiron" in contract["config"]["active_points"]
    assert "True_North_Lunar_Node" in contract["config"]["active_points"]
    assert "True_Lilith" in contract["config"]["active_points"]


def test_date_only_contract_does_not_claim_angular_precision():
    chart = astro.compute_chart(
        "1990-06-21", None, "Казань", 55.79, 49.12,
        "Europe/Moscow", time_known=False,
    )

    assert chart["precision"] == "date_only"
    assert chart["ascendant"] is None
    assert chart["houses"] == []
    assert chart["calculation"]["angular_data_available"] is False
    assert chart["calculation"]["input"]["time_known"] is False


def test_aspect_policy_is_applied_to_full_chart_output():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12,
        "Europe/Moscow", time_known=True,
    )

    assert all(item["aspect"] in {
        "соединение", "оппозиция", "трин", "квадрат", "секстиль",
    } for item in chart["aspects"])
    assert all(item["orb_exact"] <= ASPECT_ORBS[
        next(code for code, (label, _glyph) in astro.ASPECT_RU.items()
             if label == item["aspect"])
    ] for item in chart["aspects"])


def test_dst_timezone_is_preserved_and_can_produce_exact_angles():
    chart = astro.compute_chart(
        "2024-03-10", "03:30", "New York", 40.7128, -74.0060,
        "America/New_York", time_known=True,
    )
    assert chart["calculation"]["input"]["tz"] == "America/New_York"
    assert chart["calculation"]["angular_data_available"] is True
    assert chart["precision"] == "exact"


def test_invalid_coordinates_hide_angles_without_failing_planet_calculation():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Unknown", 91.0, 181.0,
        "Europe/Moscow", time_known=True,
    )
    assert chart["precision"] == "time_without_location"
    assert chart["ascendant"] is None
    assert chart["houses"] == []
    assert len(chart["planets"]) >= 10
    assert chart["calculation"]["angular_data_available"] is False


def test_polar_latitude_is_a_safe_edge_case():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Longyearbyen", 78.2232, 15.6469,
        "Arctic/Longyearbyen", time_known=True,
    )
    assert chart["mode"] in {"full", "lite"}
    assert chart["calculation"]["input"]["lat"] == 78.2232


def test_invalid_iana_timezone_fails_closed():
    with pytest.raises(ValueError, match="IANA"):
        astro.compute_chart(
            "1990-06-21", "14:30", "Казань", 55.79, 49.12,
            "Mars/Olympus", time_known=True,
        )


def test_chart_brief_contains_contract_provenance_for_followups():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12,
        "Europe/Moscow", time_known=True,
    )
    brief = astro.chart_brief(chart, time_known=True)
    assert "Канонический контракт v2" in brief
    assert "узлы: True Node" in brief
    assert "conjunction 8.0°" in brief


def test_calculation_records_coordinate_provenance_and_fingerprints_config():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12,
        "Europe/Moscow", time_known=True, coordinate_source="manual",
        coordinate_confidence=0.95, timezone_source="manual",
    )
    calculation = chart["calculation"]
    assert calculation["configuration_fingerprint"]
    assert calculation["input"]["coordinate_source"] == "manual"
    assert calculation["input"]["coordinate_confidence"] == 0.95
    assert calculation["input"]["timezone_source"] == "manual"
    assert calculation["input"]["precision_state"] == "exact"
    assert calculation["input"]["uncertainty"]["kind"] == "none"


def test_ambiguous_fold_interval_is_explicit_and_has_no_angles():
    chart = astro.compute_chart(
        "2024-10-27", "02:30", "Berlin", 52.52, 13.40,
        "Europe/Berlin", time_known=True, ambiguity_mode="interval",
    )
    assert chart["precision"] == "interval"
    assert chart["ascendant"] is None
    assert chart["houses"] == []
    uncertainty = chart["calculation"]["input"]["uncertainty"]
    assert uncertainty["kind"] == "ambiguous_local_time"
    assert len(uncertainty["candidate_instants"]) == 2


def test_configuration_change_invalidates_engine_request_fingerprint():
    from app.core.astrology_engine import ENGINE
    first = ENGINE.normalize(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12, "Europe/Moscow",
        time_known=True, active_points=tuple(astro.ACTIVE_POINTS),
    )
    second = ENGINE.normalize(
        "1990-06-21", "14:30", "Казань", 55.79, 49.12, "Europe/Moscow",
        time_known=True, active_points=("Sun",),
    )
    assert first.configuration_fingerprint != second.configuration_fingerprint
    assert first.fingerprint != second.fingerprint
