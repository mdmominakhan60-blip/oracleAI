from app.core import interpretation


def _lite_chart():
    return {
        "mode": "lite",
        "sun": {"sign": "Лев", "element": "Огонь"},
        "planets": [{"name": "Солнце", "sign": "Лев", "deg": 12.4}],
        "aspects": [],
        "ascendant": {"sign": "Скорпион", "deg": 10.0},
    }


def test_chart_evidence_hides_houses_and_ascendant_without_birth_time():
    evidence = interpretation.chart_evidence(_lite_chart(), time_known=False)
    prompt = evidence.as_prompt_block()

    assert "Солнце в Лев" in prompt
    assert "Асцендент" not in prompt
    assert not evidence.has_houses
    assert "Время рождения неизвестно" in prompt


def test_chart_guardrail_rejects_unknown_point_and_house_without_time():
    evidence = interpretation.chart_evidence(_lite_chart(), time_known=False)
    result = interpretation.validate_chart_text(
        "Луна в Раке в 7 доме обещает, что ты точно встретишь любовь.", evidence
    )

    assert not result.ok
    assert any("отсутствующие" in issue for issue in result.issues)
    assert any("дом" in issue for issue in result.issues)
    assert any("детерминистичная" in issue for issue in result.issues)


def test_chart_guardrail_accepts_grounded_non_deterministic_text():
    evidence = interpretation.chart_evidence(_lite_chart(), time_known=False)
    result = interpretation.validate_chart_text(
        "Солнце во Льве можно рассмотреть как тему заметности и творческого выбора. "
        "Проверь, где сегодня тебе важно проявиться спокойно и без лишнего давления.",
        evidence,
    )

    assert result.ok


def test_tarot_guardrail_rejects_card_not_in_spread():
    cards = [{"name": "Маг", "meaning": "инициатива", "reversed": False}]
    deck = cards + [{"name": "Сила", "meaning": "смелость"}]
    result = interpretation.validate_tarot_text(
        "Маг в этой позиции предлагает начать, а Сила гарантирует успех.", cards, deck
    )

    assert not result.ok
    assert any("не выпавшие" in issue for issue in result.issues)
    assert any("детерминистичная" in issue for issue in result.issues)


def test_tarot_evidence_keeps_position_and_orientation():
    evidence = interpretation.tarot_evidence(
        [{"name": "Звезда", "meaning": "надежда", "reversed": True}],
        ["Совет"],
        title="Один шаг",
        question="На чём сосредоточиться?",
    )
    block = evidence.as_prompt_block()

    assert "Совет: Звезда (перевёрнутая)" in block
    assert "На чём сосредоточиться?" in block
