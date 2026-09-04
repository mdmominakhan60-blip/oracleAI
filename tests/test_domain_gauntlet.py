from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core import astro, tarot, vedic
from app.core.chart_products import circular_midpoint


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "domain_golden.json").read_text(encoding="utf-8")
)


def _jsonable(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def _close(a, b, rel=1e-4):
    a = _jsonable(a)  # нормализуем tuple→list до сравнения
    b = _jsonable(b)
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], rel) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_close(x, y, rel) for x, y in zip(a, b))
    if isinstance(a, float):
        return abs(a - b) <= rel * max(abs(a), abs(b), 1.0)
    return a == b


def _assert_chart_equal(actual, expected, rel=1e-4):
    assert _close(actual, expected, rel), (_jsonable(actual), _jsonable(expected))


def _chart_summary(chart: dict) -> dict:
    return {
        "mode": chart.get("mode"),
        "precision": chart.get("precision"),
        "sun": chart.get("sun"),
        "ascendant": chart.get("ascendant"),
        "mc": chart.get("mc"),
        "planets": chart.get("planets"),
        "houses": chart.get("houses"),
        "aspects": chart.get("aspects"),
        "nodes": chart.get("nodes"),
        "calculation": chart.get("calculation"),
    }


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["input"]["id"])
def test_chart_golden_case_is_reproducible(case):
    inputs = case["input"]
    actual = astro.compute_chart(
        inputs["birth_date"], inputs["birth_time"], inputs["city"],
        inputs["lat"], inputs["lon"], inputs["tz"],
        time_known=inputs["time_known"],
    )
    _assert_chart_equal(_chart_summary(actual), case["output"])
    repeated = astro.compute_chart(
        inputs["birth_date"], inputs["birth_time"], inputs["city"],
        inputs["lat"], inputs["lon"], inputs["tz"],
        time_known=inputs["time_known"],
    )
    _assert_chart_equal(_chart_summary(repeated), _chart_summary(actual))


def test_time_without_timezone_never_becomes_exact():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, None, time_known=True,
    )
    assert chart["precision"] in {"date_only", "sun_only"}
    assert chart["calculation"]["input"]["precision_reason"] == "date_only_missing_timezone"
    assert chart.get("ascendant") is None
    assert chart.get("houses") == []


def test_invalid_coordinates_are_not_promoted_to_angular_precision():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 91, 181, "Europe/Moscow", time_known=True,
    )
    assert chart["precision"] in {"time_without_location", "date_only", "sun_only"}
    assert chart.get("ascendant") is None
    assert chart.get("houses") == []


def test_aspect_orb_boundary_is_explicit_and_deterministic():
    inside = astro.synastry_aspects(
        [{"name": "Солнце", "abs_deg": 0}],
        [{"name": "Луна", "abs_deg": 8}],
    )
    outside = astro.synastry_aspects(
        [{"name": "Солнце", "abs_deg": 0}],
        [{"name": "Луна", "abs_deg": 8.0001}],
    )
    assert inside and not outside


def test_circular_midpoint_handles_zero_boundary():
    assert circular_midpoint(350, 10) == 0


def test_vedic_date_only_contract_is_separate_and_honest():
    envelope = vedic.compute_vedic_chart(
        "1990-06-21", None, "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=False,
    )
    assert envelope["tradition"] == "Vedic/Jyotish"
    assert envelope["ayanamsa"] == "Lahiri"
    assert envelope["result"]["precision"] == "date_only"
    assert envelope["result"]["lagna"] is None
    assert envelope["result"]["houses"] == []
    assert "sidereal" in envelope["limitations"][0] or envelope["limitations"]


def test_golden_pure_contracts_match_runtime_invariants():
    pure = FIXTURE["pure_contracts"]
    assert pure["circular_midpoint_350_10"] == circular_midpoint(350, 10)
    assert len(tarot.DECK) == pure["tarot_deck_counts"]["total"] == 78
    assert len({card["img"] for card in tarot.DECK}) == pure["tarot_deck_counts"]["unique_ids"] == 78
    assert pure["tarot_deck_counts"]["majors"] == 22
    assert pure["tarot_deck_counts"]["minors"] == 56
    assert set(pure["tarot_deck_counts"]["suits"]) == set(tarot.SUITS)
    assert all(count == 14 for count in pure["tarot_deck_counts"]["suits"].values())


def test_typed_domain_failures_are_not_silent():
    with pytest.raises(ValueError):
        astro.compute_chart("1990-06-21", "25:90", "Kazan", 55.79, 49.12, "Europe/Moscow")
    with pytest.raises(ValueError):
        vedic.get_nakshatra(-0.1)
    with pytest.raises(ValueError):
        tarot.replay_ledger([{"img": "not-a-card", "reversed": False}], "one")


@pytest.mark.asyncio
async def test_skill_tarot_tool_rejects_invalid_sizes_instead_of_clamping():
    from app.core import tool_registry as skills

    for raw in (0, 13, -1, 3.5, True, "3.5"):
        result = await skills._run_draw_tarot(None, {}, {"n": raw})
        assert "целым от 1 до 12" in result


@pytest.mark.asyncio
async def test_skill_chart_tool_uses_calculated_precision_not_profile_flag():
    from app.core import tool_registry as skills

    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, None, time_known=True,
    )
    user = {"chart_json": json.dumps(chart, ensure_ascii=False), "birth_time_known": 1}
    result = await skills._run_get_chart(None, user, {})

    assert "Точность рождения: дата без подтверждённого времени" in result
    assert "точное; рассчитаны углы и дома" not in result
    assert "Куспиды домов:" not in result


@pytest.mark.asyncio
async def test_skill_vimshottari_requires_confirmed_time_and_timezone():
    from app.core import tool_registry as skills

    missing_confirmation = await skills._run_get_vimshottari_dasha(
        None,
        {"birth_date": "1990-06-21", "birth_time": "14:30", "birth_time_known": 0, "tz": "Europe/Moscow"},
        {},
    )
    missing_timezone = await skills._run_get_vimshottari_dasha(
        None,
        {"birth_date": "1990-06-21", "birth_time": "14:30", "birth_time_known": 1, "tz": None},
        {},
    )

    assert "подтверждённое время" in missing_confirmation
    assert "часовой пояс" in missing_timezone


@pytest.mark.asyncio
async def test_monthly_report_persists_versioned_privacy_safe_snapshot(db, user, monkeypatch):
    from app.core import agent
    from app.repo import readings

    monkeypatch.setattr(agent.llm, "enabled", lambda: False)
    await agent.monthly_report(db, user)
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    row = await readings.get_report(db, user["tg_id"], "monthly", period)

    metadata = json.loads(row["meta_json"])
    assert metadata["evidence_schema_version"] == "monthly-evidence-v1"
    assert metadata["evidence_kind"] == "monthly"
    assert isinstance(metadata["readings_count"], int)
    assert isinstance(metadata["diary_count"], int)
    assert "raw diary" in metadata["privacy_note"]



def test_improved_engine_normalizes_truth_state_and_fingerprint():
    from app.core.astrology_engine import ENGINE, ENGINE_ADAPTER_VERSION

    request = ENGINE.normalize(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, None, time_known=True,
    )

    assert request.precision == "date_only"
    assert request.time_confirmed is False
    assert request.angular_data_available is False
    assert request.precision_reason == "date_only_missing_timezone"
    assert len(request.fingerprint) == 16
    assert request.metadata()["adapter_version"] == ENGINE_ADAPTER_VERSION


def test_improved_engine_cache_returns_defensive_copies():
    from app.core.astrology_engine import OracleKerykeionEngine

    engine = OracleKerykeionEngine(max_cache_entries=2)
    request = engine.normalize(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    calls = []

    def calculator(normalized):
        calls.append(normalized.fingerprint)
        return {"precision": normalized.precision, "nested": {"value": 1}}

    first = engine.calculate(request, calculator)
    first["nested"]["value"] = 99
    second = engine.calculate(request, calculator)

    assert calls == [request.fingerprint]
    assert second == {"precision": "exact", "nested": {"value": 1}}


def test_improved_engine_rejects_invalid_time_and_timezone():
    from app.core.astrology_engine import AstrologyInputError, ENGINE

    with pytest.raises(AstrologyInputError, match="ЧЧ:ММ"):
        ENGINE.normalize("1990-06-21", "25:90", "Kazan", 55.79, 49.12, "Europe/Moscow")
    with pytest.raises(AstrologyInputError, match="IANA"):
        ENGINE.normalize("1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Not/AZone")



def test_compute_chart_exposes_improved_engine_provenance():
    from app.core.astrology_engine import ENGINE_ADAPTER_VERSION

    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    calculation_input = chart["calculation"]["input"]

    assert chart["precision"] == "exact"
    assert calculation_input["adapter_version"] == ENGINE_ADAPTER_VERSION
    assert len(calculation_input["request_fingerprint"]) == 16
    assert chart["calculation"]["angular_data_available"] is True


@pytest.mark.parametrize(
    ("lat", "lon", "coordinates_known"),
    [(-90.0, -180.0, True), (90.0, 180.0, True), (0.0, 0.0, True), (float("inf"), 0.0, False), (0.0, float("nan"), False)],
)
def test_improved_engine_coordinate_boundaries_are_explicit(lat, lon, coordinates_known):
    from app.core.astrology_engine import ENGINE

    request = ENGINE.normalize(
        "2000-01-01", "12:00", "boundary", lat, lon, "UTC", time_known=True,
    )
    assert request.coordinates_known is coordinates_known
    assert request.angular_data_available is coordinates_known


@pytest.mark.parametrize("aspect_name", ["conjunction", "opposition", "trine", "square", "sextile"])
def test_each_configured_aspect_orb_has_inside_boundary_and_outside_cases(aspect_name):
    from app.core.chart_contract import ASPECT_ANGLES, ASPECT_ORBS

    angle = ASPECT_ANGLES[aspect_name]
    orb = ASPECT_ORBS[aspect_name]
    inside = astro.synastry_aspects(
        [{"name": "Солнце", "abs_deg": 0}],
        [{"name": "Луна", "abs_deg": (angle + orb - 0.0001) % 360}],
    )
    boundary = astro.synastry_aspects(
        [{"name": "Солнце", "abs_deg": 0}],
        [{"name": "Луна", "abs_deg": (angle + orb) % 360}],
    )
    outside = astro.synastry_aspects(
        [{"name": "Солнце", "abs_deg": 0}],
        [{"name": "Луна", "abs_deg": (angle + orb + 0.0001) % 360}],
    )
    assert inside and boundary and not outside


def test_nodes_lilith_and_retrograde_are_named_source_fields():
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    assert chart["lunar_nodes"]["mode"] == "true"
    assert {item["name"] for item in chart["nodes"]} >= {"Раху (Северный узел)", "Кету (Южный узел)"}
    assert all(isinstance(item["retro"], bool) for item in chart["planets"] + chart["nodes"])


def test_improved_engine_cache_evicts_oldest_request_deterministically():
    from app.core.astrology_engine import OracleKerykeionEngine

    engine = OracleKerykeionEngine(max_cache_entries=1)
    first = engine.normalize("2000-01-01", None, None, None, None, None)
    second = engine.normalize("2000-01-02", None, None, None, None, None)
    calls = []

    def calculator(request):
        calls.append(request.fingerprint)
        return {"fingerprint": request.fingerprint}

    engine.calculate(first, calculator)
    engine.calculate(second, calculator)
    engine.calculate(first, calculator)
    assert calls == [first.fingerprint, second.fingerprint, first.fingerprint]



def test_public_calculation_contract_discloses_backend_provenance():
    from app.core.chart_contract import public_calculation_contract

    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    provenance = public_calculation_contract(chart)["engine_provenance"]

    assert provenance == {
        "product_engine": "OracleAI Engine",
        "adapter_version": "oracleai-kerykeion-engine-v2",
        "backend": "Kerykeion",
        "backend_version": "5.12.9",
        "ephemeris": "Swiss Ephemeris",
        "license_notice": "AGPL-3.0/commercial licensing obligations apply to the selected distribution model.",
    }



def test_improved_engine_canonicalizes_equivalent_text_inputs():
    from app.core.astrology_engine import ENGINE

    first = ENGINE.normalize("1990-06-21", " 14:30 ", "  Kazan  ", 55.79, 49.12, " Europe/Moscow ", time_known=True)
    second = ENGINE.normalize("1990-06-21", "14:30", "Kazan", 55.7900, 49.1200, "Europe/Moscow", time_known=True)

    assert first.city == "Kazan"
    assert first.tz == "Europe/Moscow"
    assert first.fingerprint == second.fingerprint


def test_post_kerykeion_validator_rejects_non_finite_or_out_of_range_points():
    from app.core.astrology_engine import AstrologyOutputError, ENGINE, validate_chart_result

    request = ENGINE.normalize(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    chart = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    chart["planets"][0]["abs_deg_exact"] = 360.0

    with pytest.raises(AstrologyOutputError, match="outside zodiac bounds"):
        validate_chart_result(request, chart)


def test_malformed_backend_is_downgraded_to_bounded_sun_only(monkeypatch):
    from app.core.astrology_engine import ENGINE

    ENGINE.clear_cache()

    def malformed(*args, **kwargs):
        return {"mode": "full", "precision": "exact", "calculation": {}}

    monkeypatch.setattr(astro, "_full_chart", malformed)
    result = astro.compute_chart(
        "1990-06-21", "14:30", "Kazan", 55.79, 49.12, "Europe/Moscow", time_known=True,
    )
    ENGINE.clear_cache()

    assert result["mode"] == "lite"
    assert result["precision"] == "sun_only"
    assert result["planets"] == []
    assert result["calculation"]["angular_data_available"] is False


@pytest.mark.parametrize(
    ("birth_date", "birth_time", "expected_status", "expected_reason"),
    (
        ("2024-03-31", "02:30", "nonexistent", "date_only_nonexistent_local_time"),
        ("2024-10-27", "02:30", "ambiguous", "date_only_ambiguous_local_time"),
    ),
)
def test_engine_does_not_silently_choose_dst_gap_or_fold(
    birth_date, birth_time, expected_status, expected_reason,
):
    from app.core.astrology_engine import ENGINE

    request = ENGINE.normalize(
        birth_date, birth_time, "Berlin", 52.52, 13.405, "Europe/Berlin", time_known=True,
    )

    assert request.local_time_status == expected_status
    assert request.time_confirmed is False
    assert request.precision == "date_only"
    assert request.precision_reason == expected_reason


def test_engine_accepts_unambiguous_dst_local_time():
    from app.core.astrology_engine import ENGINE

    request = ENGINE.normalize(
        "2024-03-31", "04:30", "Berlin", 52.52, 13.405, "Europe/Berlin", time_known=True,
    )

    assert request.local_time_status == "normal"
    assert request.time_confirmed is True
    assert request.precision == "exact"


def test_tarot_grounding_rejects_non_drawn_card():
    """Гейт, завязанный на мягкий ретрай в interpret_reading, обязан ловить
    упоминание не выпавшей карты и пропускать только фактические карты."""
    from app.core import interpretation

    cards = [dict(tarot.DECK[0]), dict(tarot.DECK[1])]  # две выпавшие карты
    names = {c["name"] for c in cards}
    foreign = next(c["name"] for c in tarot.DECK if c["name"] not in names)
    clean = interpretation.validate_tarot_text(
        f"В позиции «Прошлое» — {cards[0]['name']}.", cards, tarot.DECK)
    assert clean.ok is True
    dirty = interpretation.validate_tarot_text(
        f"{cards[0]['name']} и {cards[1]['name']}, а рядом {foreign}.", cards, tarot.DECK)
    assert dirty.ok is False
    assert foreign in "; ".join(dirty.issues)
