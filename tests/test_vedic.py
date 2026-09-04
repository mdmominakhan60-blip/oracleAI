import asyncio
from datetime import datetime

import pytest

from app.core import tool_registry as skills, vedic


BIRTH = ("1990-01-15", "12:30", "Moscow", 55.75, 37.62, "Europe/Moscow")


def test_vedic_chart_is_separate_lahiri_evidence_contract():
    envelope = vedic.compute_vedic_chart(*BIRTH, time_known=True)
    result = envelope["result"]
    assert envelope["tradition"] == "Vedic/Jyotish"
    assert envelope["ayanamsa"] == "Lahiri"
    assert result["zodiac"] == "sidereal"
    assert result["precision"] == "exact"
    assert len(result["planets"]) == 9
    assert len(result["houses"]) == 12
    rahu = result["lunar_nodes"]["Rahu"]["longitude"]
    ketu = result["lunar_nodes"]["Ketu"]["longitude"]
    assert abs(((ketu - rahu) % 360) - 180) < 1e-6


def test_date_only_omits_lagna_and_houses():
    envelope = vedic.compute_vedic_chart(
        "1990-01-15", None, "Moscow", 55.75, 37.62, "Europe/Moscow", time_known=False)
    assert envelope["result"]["precision"] == "date_only"
    assert envelope["result"]["lagna"] is None
    assert envelope["result"]["houses"] == []
    assert envelope["limitations"]


def test_nakshatra_covers_boundaries_and_four_padas():
    span = 360 / 27
    for index in range(27):
        base = index * span
        assert vedic.get_nakshatra(base)["result"]["index"] == index + 1
        for pada in range(4):
            longitude = base + (pada + 0.5) * (span / 4)
            assert vedic.get_nakshatra(longitude)["result"]["pada"] == pada + 1
    with pytest.raises(ValueError):
        vedic.get_nakshatra(360.01)


def test_vimshottari_has_start_lord_and_contiguous_timeline():
    envelope = vedic.get_vimshottari_dasha("1990-01-15", "12:30", "Europe/Moscow", as_of="2026-08-24")
    result = envelope["result"]
    assert result["cycle_years"] == 120
    assert result["starting_lord"] in vedic.DASHA_ORDER
    periods = result["periods"]
    assert all(len(period["antardasha"]) == 9 for period in periods)
    assert periods
    for previous, current in zip(periods, periods[1:]):
        assert previous["end"] == current["start"]
    assert result["current"] is not None
    with pytest.raises(ValueError):
        vedic.get_vimshottari_dasha("1990-01-15", None, "Europe/Moscow")


def test_panchang_and_rahu_kaal_have_local_time_evidence():
    panchang = vedic.get_panchang("2026-08-24", 55.75, 37.62, "Europe/Moscow")["result"]
    assert 1 <= panchang["tithi"]["number"] <= 30
    assert 1 <= panchang["nakshatra"]["index"] <= 27
    assert 1 <= panchang["nakshatra"]["pada"] <= 4
    assert panchang["sunrise"] < panchang["sunset"]
    rahu = vedic.get_rahu_kaal("2026-08-24", 55.75, 37.62, "Europe/Moscow")["result"]
    assert rahu["start"] < rahu["end"]
    assert datetime.fromisoformat(rahu["start"]).tzinfo is not None


def test_varga_guna_and_strengths_are_bounded_and_symmetric():
    chart = vedic.compute_vedic_chart(*BIRTH, time_known=True)["result"]
    d9 = vedic.get_varga_chart(chart, "D9")["result"]
    d10 = vedic.get_varga_chart(chart, "D10")["result"]
    assert d9["varga"] == "D9"
    assert d10["varga"] == "D10"
    assert len(d9["planets"]) == len(chart["planets"])
    strengths = vedic.get_graha_strengths(chart)["result"]
    assert strengths["method"] == "dignity-lite-v1"
    assert all(0 <= row["score"] <= 100 for row in strengths["planets"])
    first = vedic.get_guna_milan(chart, chart)["result"]
    second = vedic.get_guna_milan(chart, chart)["result"]
    assert first["total"] == second["total"]
    assert 0 <= first["total"] <= 36
    assert first["symmetric"] is True


def test_tool_registry_dispatches_vedic_chart_with_evidence():
    user = {"birth_date": BIRTH[0], "birth_time": BIRTH[1], "birth_city": BIRTH[2],
            "birth_lat": BIRTH[3], "birth_lon": BIRTH[4], "tz": BIRTH[5],
            "birth_time_known": True}
    payload = asyncio.run(skills.execute(None, user, "get_vedic_chart", {}))
    assert "Vedic evidence" in payload
    assert "Lahiri" in payload
    assert "Vedic/Jyotish" in payload


def test_muhurta_keeps_user_criteria_and_no_guarantee_limitations():
    envelope = vedic.get_muhurta(
        "2026-08-24", "2026-08-25", 55.75, 37.62, "Europe/Moscow", "launch project")
    assert envelope["result"]["criteria"] == "launch project"
    assert "guarantee" in " ".join(envelope["limitations"])
