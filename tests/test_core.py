"""Ядро без БД: колода, астрология, Матрица, совместимость, устойчивый сид."""
from __future__ import annotations

from datetime import date

import pytest

from app.core import astro, tarot
from app.core.matrix import compute_matrix
from app.core.tool_registry import _compat
from app.core.stable import stable_seed


def test_deck_has_78_cards():
    assert len(tarot.DECK) == 78
    majors = [c for c in tarot.DECK if c["arcana"] == "major"]
    assert len(majors) == 22


def test_draw_returns_distinct_cards_in_order():
    cards = tarot.draw(5)
    assert len(cards) == 5
    assert len({c["name"] for c in cards}) == 5
    assert all("reversed" in c for c in cards)


def test_draw_handles_large_spreads():
    """«Колесо года» — 12 карт: раскладов больше колоды быть не может."""
    cards = tarot.draw(12)
    assert len(cards) == 12
    assert len({c["name"] for c in cards}) == 12


def test_seeded_draw_is_reproducible_for_golden_fixtures():
    first = tarot.draw(5, seed="oracleai-golden")
    second = tarot.draw(5, seed="oracleai-golden")
    assert first == second


def test_reading_ledger_has_positions_orientation_and_combinations():
    cards = tarot.draw(3, seed="ledger-fixture")
    ledger = tarot.reading_ledger(cards, "three")
    assert ledger["deck_id"] == "rws-78-v1"
    assert ledger["version"] == "tarot-ledger-v1"
    assert [item["position"] for item in ledger["entries"]] == tarot.SPREADS["three"]["positions"]
    assert all(item["orientation"] in ("upright", "reversed") for item in ledger["entries"])
    assert len(ledger["adjacent_combinations"]) == 2
    assert len(ledger["checksum"]) == 16
    assert "traditional language" in ledger["interpretation_boundary"]


def test_reading_ledger_classifies_explicit_symbolic_combination():
    cards = [dict(next(card for card in tarot.DECK if card["name"] == name), reversed=False)
             for name in ("Смерть", "Башня")]
    ledger = tarot.reading_ledger(cards, "three")
    assert ledger["adjacent_combinations"][0]["rule"] == "transformational_pressure"


def test_tarot_spreads_have_positions_and_guide():
    for code, item in tarot.SPREADS.items():
        assert item["positions"], code
        assert item["tier"] in ("included", "premium"), code
        assert len(item["positions"]) <= len(tarot.DECK)
        assert item.get("guide"), f"{code}: нет guide"


def test_tarot_major_cards_have_depth():
    """Старшие арканы — архетип+тень: каждая карта живая, с короткой
    подписью и практическим советом, а не шаблоном."""
    majors = [c for c in tarot.DECK if c["arcana"] == "major"]
    assert len(majors) == 22
    assert all(c.get("short") for c in majors)
    assert all(c.get("advice") for c in majors)
    meanings = {c["name"]: c["meaning"] for c in majors}
    assert all(len(m) > 20 for m in meanings.values()), "meaning слишком шаблонный"
    assert len({m for m in meanings.values()}) == len(meanings), "meaning повторяются"
    first, last = majors[0], majors[-1]
    assert first["num"] == "0" and last["num"] == "XXI"


def test_spread_lookup_falls_back():
    assert tarot.spread("nope")["code"] == tarot.DEFAULT_SPREAD
    assert tarot.spread("celtic")["code"] == "celtic"
    assert tarot.spread_by_title("На отношения")["code"] == "love"


def test_sun_sign_boundaries():
    assert astro.sun_sign(date(1990, 6, 21))[0] in ("Близнецы", "Рак")
    assert astro.sun_sign(date(1990, 1, 5))[0] == "Козерог"
    assert astro.sun_sign(date(1990, 8, 1))[0] == "Лев"


def test_moon_phase_is_stable_for_a_date():
    first = astro.moon_phase(date(2026, 7, 26))
    second = astro.moon_phase(date(2026, 7, 26))
    assert first == second
    assert 1 <= first["day"] <= 31


def test_chart_never_raises_and_marks_mode():
    chart = astro.compute_chart("1990-06-21", "14:30", "Казань", 55.79, 49.12,
                                "Europe/Moscow")
    assert chart["mode"] in ("full", "lite")
    assert chart["sun"]["sign"]
    # лайт-режим обязан честно себя помечать, иначе клиентка не поймёт,
    # почему у неё нет домов
    if chart["mode"] == "lite":
        assert chart["note"]


def test_matrix_arcana_in_range():
    matrix = compute_matrix("1990-06-21")
    assert set(matrix) == {"personal", "spirit", "family", "destiny", "center",
                           "love", "money"}
    for item in matrix.values():
        assert 1 <= item["n"] <= 22
        assert item["arcana"] and item["meaning"]


def test_compat_is_deterministic_and_explained():
    first = _compat("1990-06-21", "1996-11-03")
    second = _compat("1990-06-21", "1996-11-03")
    assert first["score"] == second["score"]
    assert 35 <= first["score"] <= 98
    assert first["breakdown"] and first["verdict"]


def test_stable_seed_survives_restart():
    """crc32 вместо hash(): встроенный хеш строк рандомизируется при запуске,
    из-за чего карта дня менялась после рестарта процесса."""
    assert stable_seed("вопрос", 42) == stable_seed("вопрос", 42)
    assert stable_seed("вопрос", 42) != stable_seed("вопрос", 43)


def test_cards_text_marks_reversed():
    cards = [{"emoji": "🌙", "name": "Жрица", "meaning": "интуиция", "reversed": True}]
    text = tarot.cards_text(cards, ["Ответ"])
    assert "Ответ" in text and "перевёрнутая" in text


def test_compat_is_symmetric():
    """Балл пары не должен зависеть от того, кто спросил."""
    a = _compat("1990-06-21", "1996-11-03")
    b = _compat("1996-11-03", "1990-06-21")
    assert a["score"] == b["score"]
    assert a["verdict"] == b["verdict"]


def test_compat_same_element_uses_right_verdict():
    """«Пламя» уходит только огненной паре: два Тельца — «основа»."""
    c = _compat("1996-04-25", "1975-05-14")   # Телец + Телец (земля)
    if c["score"] >= 80:
        assert c["verdict"].startswith("союз-основа")
    else:
        assert c["verdict"].startswith("союз-")
    assert not c["verdict"].startswith("союз-пламя")


def test_matrix_love_is_personal_plus_destiny():
    """Линия любви — зеркально денежной: личность + миссия (a + dd)."""
    m = compute_matrix("1990-05-15")
    assert m["love"]["n"] == 9, "канон: 1990-05-15 даёт Отшельника на линии любви"
    assert m["money"]["n"] == 4


def test_celtic_cross_positions_are_classic():
    """Традиционные стрелки креста: 3=подсознание, 4=прошлое, 5=сознание."""
    positions = tarot.SPREADS["celtic"]["positions"]
    assert positions[2] == "Подсознание"
    assert positions[3] == "Прошлое"
    assert positions[4] == "Осознанное"


def _full_chart_fixture():
    return {
        "mode": "full",
        "ascendant": {"sign": "Лев"},
        "planets": [
            {"name": "Венера", "sign": "Весы", "house": 7, "retro": False},
            {"name": "Луна", "sign": "Рак", "house": 4, "retro": False},
        ],
        "aspects": [],
        "houses": [],
    }


def test_chart_brief_hides_houses_without_time():
    """Нет точного времени рождения — дома в промпт не попадают."""
    brief = astro.chart_brief(_full_chart_fixture(), time_known=False)
    assert "7 дом" not in brief and "4 дом" not in brief
    assert "полдн" in brief.lower()


def test_chart_brief_shows_houses_with_time():
    brief = astro.chart_brief(_full_chart_fixture(), time_known=True)
    assert "7 дом" in brief
    assert "полдн" not in brief.lower()


# ─────────────── инварианты после эзотерического аудита ─────────────────────


def test_reversed_rate_approx_half():
    """Честная тасовка: ~50% перевёрнутых вместо произвольных 25%."""
    cards = []
    for _ in range(8):
        cards += tarot.draw(78)   # полная колода за раз, статистика накапливается
    rate = sum(c["reversed"] for c in cards) / len(cards)
    assert 0.35 <= rate <= 0.65


def test_matrix_r_edges():
    from app.core.matrix import _r
    assert _r(22) == 22   # Шут — вершина диапазона арканов
    assert _r(0) == 22    # 0 физически не бывает, но обязан не упасть
    assert _r(39) == 12
    assert _r(31) == 4


def test_sun_sign_precise_agrees_on_safe_dates():
    """Спорные границы лечатся эфемеридами; на уверенных датах точный знак
    совпадает с уверенностью (не середина знака)."""
    assert astro.sun_sign_precise(date(1990, 7, 1))[0] == "Рак"
    assert astro.sun_sign_precise(date(1990, 1, 5))[0] == "Козерог"
    assert astro.sun_sign_precise(date(1990, 12, 10))[0] == "Стрелец"


def test_synastry_finds_trine_between_cards():
    asp = astro.synastry_aspects(
        [{"name": "Венера", "abs_deg": 120.0}],
        [{"name": "Луна", "abs_deg": 0.0}],
    )
    assert asp and asp[0]["aspect"] == "трин"


def test_synastry_skips_same_point():
    asp = astro.synastry_aspects(
        [{"name": "Солнце", "abs_deg": 10.0}],
        [{"name": "Солнце", "abs_deg": 10.0}],
    )
    assert asp == []


def test_synastry_bonus_sums_aspect_bonus():
    from app.core.tool_registry import synastry_bonus
    assert synastry_bonus([{"code": "trine"}, {"code": "opposition"}]) == 3
    assert synastry_bonus([]) == 0


def test_compat_has_no_magic_jitter():
    """Разбор больше не называет хеш-поправку «темпераментом пары»."""
    c = _compat("1990-06-21", "1996-11-03")
    assert all(b["title"] != "Темперамент пары" for b in c["breakdown"])


def test_card_of_day_deterministic_for_user():
    from app.core import agent as agent_core
    user = {"tg_id": 4242, "tz": "Europe/Moscow"}
    first = agent_core.card_of_day(user)
    second = agent_core.card_of_day(user)
    assert first["name"] == second["name"]
    assert first["reversed"] == second["reversed"]


def test_date_only_chart_hides_angular_data_and_marks_precision():
    """Полдень — техническая точка эфемерид, но не выдуманное время рождения."""
    chart = astro.compute_chart("1990-06-21", None, "Казань", 55.79, 49.12,
                                "Europe/Moscow")
    assert chart["precision"] in ("date_only", "sun_only")
    if chart["mode"] == "full":
        assert chart["ascendant"] is None
        assert chart["mc"] is None
        assert chart["houses"] == []
        assert all(p["house"] is None for p in chart["planets"])
        assert "Асцендент" not in astro.chart_brief(chart, time_known=True)
        assert "дома, ASC и MC отсутствуют" in astro.chart_brief(chart, time_known=True)


def test_invalid_birth_time_is_rejected_instead_of_silently_rewritten():
    try:
        astro.compute_chart("1990-06-21", "25:90", "Казань", 55.79, 49.12,
                            "Europe/Moscow")
    except ValueError as exc:
        assert "ЧЧ:ММ" in str(exc)
    else:
        raise AssertionError("некорректное время не должно превращаться в полдень")


def test_coordinate_validator_requires_physical_ranges():
    assert astro._has_valid_coordinates(55.79, 49.12) is True
    assert astro._has_valid_coordinates(91, 49.12) is False
    assert astro._has_valid_coordinates(55.79, 181) is False
    assert astro._has_valid_coordinates(float("nan"), 49.12) is False


def test_technical_noon_with_unconfirmed_time_hides_angular_data():
    """Технический полдень из onboarding не должен притворяться временем рождения."""
    chart = astro.compute_chart("1990-06-21", "12:00", "Казань", 55.79, 49.12,
                                "Europe/Moscow", time_known=False)
    assert chart["precision"] in ("date_only", "sun_only")
    if chart["mode"] == "full":
        assert chart["ascendant"] is None
        assert chart["mc"] is None
        assert chart["houses"] == []
        assert all(planet["house"] is None for planet in chart["planets"])


def test_chart_payload_uses_fresh_birth_date_after_first_run():
    """После заполнения формы карта сразу отражает введённую дату, а не stale Row."""
    from app.api.routers.chart import _chart_payload

    user = {
        "birth_date": None,
        "birth_time": "12:00",
        "birth_city": "Казань",
        "birth_time_known": 0,
    }
    payload = _chart_payload(
        {"mode": "lite", "precision": "date_only", "planets": []},
        user,
        birth_date="1999-03-08",
        time_known=False,
    )
    assert payload["birth"]["date"] == "1999-03-08"
    assert payload["birth"]["time_known"] is False



def test_chart_payload_can_clear_stale_birth_time_for_date_only_choice():
    """Явный date-only выбор не должен возвращать старое время из профиля."""
    from app.api.routers.chart import _chart_payload

    user = {
        "birth_date": "1999-03-08",
        "birth_time": "14:30",
        "birth_city": "Казань",
        "birth_time_known": 1,
    }
    payload = _chart_payload(
        {"mode": "lite", "precision": "date_only", "planets": []},
        user,
        birth_time=None,
        time_known=False,
    )
    assert payload["birth"]["time"] is None
    assert payload["birth"]["time_known"] is False


def test_chart_exposes_explicit_calculation_conventions():
    chart = astro.compute_chart("1990-06-21", "14:30", "Казань", 55.79, 49.12,
                                "Europe/Moscow", time_known=True)
    assert chart["zodiac_type"] == "Tropical"
    assert chart["house_system"] == "P"
    assert chart["perspective_type"] == "Apparent Geocentric"
    assert "Swiss Ephemeris" in chart["engine"]


def test_invalid_timezone_is_rejected_explicitly():
    try:
        astro.compute_chart("1990-06-21", "14:30", "Казань", 55.79, 49.12,
                            "Not/A_Timezone", time_known=True)
    except ValueError as exc:
        assert "IANA" in str(exc)
    else:
        raise AssertionError("invalid timezone must not silently fall back")



def test_replay_ledger_reconstructs_immutable_draw_without_redraw():
    cards = tarot.draw(3, seed="replay-fixture")
    original = tarot.reading_ledger(cards, "three")

    replayed = tarot.replay_ledger(cards, "three", original["checksum"])

    assert replayed == original
    assert replayed["replay"]["version"] == "tarot-replay-v1"
    assert replayed["replay"]["mode"] == "immutable_cards"



def test_replay_ledger_rejects_tampered_checksum():
    cards = tarot.draw(1, seed="replay-tamper")

    with pytest.raises(ValueError, match="checksum mismatch"):
        tarot.replay_ledger(cards, "one", "tampered")
