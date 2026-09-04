from __future__ import annotations

import pytest

from app.core.agents.routing import route_agent


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Что значит мой Сатурн в 10 доме?", "astro"),
        ("Tell me about my natal chart and rising sign", "astro"),
        ("Раху and Ketu: куда мне расти?", "astro"),
        ("Сделай расклад Таро на решение", "tarot"),
        ("What does this tarot spread show?", "tarot"),
        ("Прочитай ладонь по фото, heart line", "chiromant"),
        ("Can you analyze my palm photo?", "chiromant"),
        ("Подбери практику для спокойствия", "oracle"),
        ("Помоги с дневником и границами", "oracle"),
    ],
)
def test_clear_multilingual_domain_routes(text, expected):
    decision = route_agent(text)
    assert decision.agent == expected
    if expected != "oracle":
        assert decision.auto_route is True
        assert decision.confidence >= 0.76


def test_ambiguous_mixed_domain_stays_default_and_explains_why():
    decision = route_agent("Сделай расклад Таро и объясни мой натальный Сатурн")
    assert decision.agent == "oracle"
    assert decision.auto_route is False
    assert "ambiguous" in decision.reason
    assert set(("astro", "tarot")) <= set(decision.candidates)


def test_no_signal_stays_default():
    decision = route_agent("Помоги мне разобраться, что делать дальше")
    assert decision.agent == "oracle"
    assert decision.auto_route is False
    assert decision.confidence == 0.5


def test_route_decision_is_serializable():
    data = route_agent("my natal chart").as_dict()
    assert data["agent"] == "astro"
    assert isinstance(data["candidates"], list)
    assert data["auto_route"] is True


# ── аудит AI-002 / TEST-002: границы матчинга (confusion cases) ──────────────

def test_mixed_script_token_does_not_match_latin_term():
    """«planет» (латиница+кириллица) не должен матчить «planet»."""
    decision = route_agent("расскажи про мой planет в карте")
    # «карт» даёт слабый сигнал astro=2, но без «planet» скор ниже порога хард-домена
    assert decision.score <= 2
    assert decision.auto_route is False


def test_latin_morphology_prefix_still_matches():
    """«planets» (мн. число) по-прежнему матчит стемму «planet»."""
    decision = route_agent("what do my planets say this week?")
    assert decision.agent == "astro"


def test_latin_term_inside_longer_word_does_not_match():
    """«explanation» не должен матчить «planet»/«plan» по подстроке."""
    decision = route_agent("give me an explanation of my feelings")
    assert decision.agent == "oracle"


def test_cyrillic_stem_morphology_kept():
    """Кириллические стеммы остаются подстроками: «натальную» ⊃ «натал»."""
    decision = route_agent("разбери мою натальную карту подробнее")
    assert decision.agent == "astro"
    assert decision.auto_route is True


def test_soft_card_word_alone_stays_default():
    """«покажи мою карту» — слабый сигнал (2), недостаточный для авто-роута."""
    decision = route_agent("покажи мою карту")
    assert decision.auto_route is False
