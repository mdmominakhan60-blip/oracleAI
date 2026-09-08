"""Human-first chart contract v2 (BUS-523): scales, hooks, validation, B4 blocks."""
from __future__ import annotations

import pytest

from app.core import chart_human


def sample_chart() -> dict:
    return {
        "mode": "full",
        "sun": {"sign": "Лев"},
        "ascendant": {"sign": "Скорпион", "deg": 14.2},
        "mc": {"sign": "Лев"},
        "planets": [
            {"name": "Солнце", "sign": "Лев", "house": 10},
            {"name": "Луна", "sign": "Рак", "house": 9},
            {"name": "Меркурий", "sign": "Дева", "house": 11},
            {"name": "Венера", "sign": "Близнецы", "house": 8},
            {"name": "Марс", "sign": "Овен", "house": 6},
            {"name": "Юпитер", "sign": "Стрелец", "house": 2},
            {"name": "Сатурн", "sign": "Козерог", "house": 3},
            {"name": "Уран", "sign": "Козерог"},
            {"name": "Нептун", "sign": "Козерог"},
            {"name": "Плутон", "sign": "Скорпион"},
        ],
        "nodes": [
            {"name": "Раху (Северный узел)", "sign": "Водолей"},
            {"name": "Кету (Южный узел)", "sign": "Лев"},
        ],
        "houses": [{"n": n, "sign": "Овен"} for n in range(1, 13)],
        "aspects": [
            {"p1": "Луна", "p2": "Сатурн", "aspect": "квадрат", "orb": 3.1},
            {"p1": "Солнце", "p2": "Юпитер", "aspect": "трин", "orb": 4.0},
            {"p1": "Венера", "p2": "Плутон", "aspect": "соединение", "orb": 2.0},
        ],
        "calculation": {"contract_version": 2},
    }


def valid_payload() -> dict:
    return {
        "who_you_are": "Тебе важно видеть смысл в том, что ты делаешь, и ты проверяешь решения собственным опытом.",
        "strengths": [
            "Соединяешь идеи из разных областей в один план",
            "Умеешь убеждать спокойно и аргументированно",
            "Долго держишь курс на цель без внешнего давления",
        ],
        "obstacles": [
            "Иногда ты берёшь на себя чужие задачи и перегружаешься",
            "Твой главный риск — ждать идеального момента вместо малого шага",
        ],
        "love": {
            "showing_feelings": "Ты проявляешь заботу делом и вниманием к деталям.",
            "needs_from_partner": "Тебе нужна честность и предсказуемость.",
            "attracted_to": "Тебя притягивают люди с внутренней глубиной.",
            "breaks_relationships": "Дистанция вместо разговора разрушает близость.",
            "partner_archetype": "Подходит тот, кто уважает твою независимость и умеет говорить прямо.",
        },
        "career": {
            "where_you_thrive": "Ты раскрываешься там, где можно строить своё.",
            "work_style": "Подходит работа с ясной целью и свободой в методах.",
            "motivation": "Тебя двигает влияние и видимый результат.",
            "decision_style": "Ты решаешь быстро, опираясь на картину цели.",
            "growth_potential": "Рост приходит через делегирование и доверие команде.",
            "career_mistakes": "Ошибка — браться за всё самому и выгорать на рутине.",
        },
        "purpose": {
            "human": "Твоя основная задача — выйти из привычного сценария «всё сам» и научиться опираться на людей.",
            "rahu_detail": "Раху в Водолее: рост через сообщество и новые формы сотрудничества.",
            "ketu_detail": "Кету во Льве: привычная сила — индивидуальное самовыражение.",
        },
        "profile_summary": "Портрет соединяет сильную волю с чутким внутренним ритмом.",
    }


# ---------------------------------------------------------------- scales

def test_profile_scales_deterministic_and_bounded():
    chart = sample_chart()
    first = chart_human.profile_scales(chart, time_known=True)
    second = chart_human.profile_scales(chart, time_known=True)
    assert first == second
    labels = [scale["label"] for scale in first["scales"]]
    assert labels == ["Личность", "Эмоции", "Отношения", "Амбиции", "Интуиция"]
    for scale in first["scales"]:
        assert 0 <= scale["value"] <= 100
        assert scale["drivers"]


def test_profile_scales_differ_with_time_known():
    chart = sample_chart()
    exact = chart_human.profile_scales(chart, time_known=True)
    date_only = chart_human.profile_scales(chart, time_known=False)
    assert exact != date_only


# ---------------------------------------------------------------- hooks

def test_hooks_generated_from_chart_evidence():
    hooks = chart_human.question_hooks(sample_chart(), time_known=True)
    assert any(hook["id"] == "trust" for hook in hooks)
    assert any(hook["id"] == "potential" for hook in hooks)
    for hook in hooks:
        assert hook["question"] and hook["block"] and hook["evidence"]


def test_hooks_have_personalized_fallback_without_aspects():
    chart = sample_chart()
    chart["aspects"] = []
    hooks = chart_human.question_hooks(chart, time_known=False)
    assert len(hooks) >= 3
    assert all(hook["evidence"] for hook in hooks)


def test_hooks_never_exceed_limit():
    hooks = chart_human.question_hooks(sample_chart(), time_known=True, limit=2)
    assert len(hooks) == 2


# ---------------------------------------------------------------- validation

def test_valid_payload_passes():
    chart = sample_chart()
    issues = chart_human.validate_payload(valid_payload(), chart, time_known=True)
    assert issues == []


def test_human_blocks_reject_astrological_terms():
    payload = valid_payload()
    payload["who_you_are"] = "Марс в Овне делает тебя решительным, квадрат с Сатурном добавляет строгости."
    issues = chart_human.validate_payload(payload, sample_chart(), time_known=True)
    assert any("astrological term" in issue for issue in issues)


def test_human_blocks_reject_house_references():
    payload = valid_payload()
    payload["profile_summary"] = "Твой 10-й дом указывает на карьеру."
    issues = chart_human.validate_payload(payload, sample_chart(), time_known=True)
    assert any("house" in issue for issue in issues)


def test_date_only_cannot_claim_houses_anywhere():
    payload = valid_payload()
    payload["career"]["where_you_thrive"] = "В 6-й дом ты войдёшь уверенно."
    issues = chart_human.validate_payload(payload, sample_chart(), time_known=False)
    assert any("house claim" in issue for issue in issues)


def test_node_details_require_node_evidence():
    payload = valid_payload()
    chart = sample_chart()
    chart["nodes"] = []
    issues = chart_human.validate_payload(payload, chart, time_known=True)
    assert any("rahu_detail" in issue for issue in issues)


def test_nonfatal_guarantees_rejected_everywhere():
    payload = valid_payload()
    payload["career"]["growth_potential"] = "Гарантированно получишь повышение в этом году."
    issues = chart_human.validate_payload(payload, sample_chart(), time_known=True)
    assert any("гарантия" in issue or "детерминистичная" in issue for issue in issues)


def test_wrong_shape_rejected():
    payload = valid_payload()
    payload.pop("love")
    payload["extra"] = "x"
    issues = chart_human.validate_payload(payload, sample_chart(), time_known=True)
    assert any("missing keys" in issue for issue in issues)
    assert any("unexpected keys" in issue for issue in issues)


# ---------------------------------------------------------------- B4 contract

def test_blocks_contract_shape_and_order():
    payload = valid_payload()
    chart = sample_chart()
    scales = chart_human.profile_scales(chart, time_known=True)
    hooks = chart_human.question_hooks(chart, time_known=True)
    contract = chart_human.build_blocks_contract(payload, hooks=hooks, scales=scales, time_known=True)
    assert contract["contract_version"] == 2
    assert contract["render_order"] == [
        "who_you_are", "strengths", "obstacles", "love", "career", "purpose", "profile",
    ]
    assert set(contract["blocks"]) == set(contract["render_order"])
    assert contract["blocks"]["purpose"]["text"] == payload["purpose"]["human"]
    assert contract["blocks"]["purpose"]["details"]["rahu"].startswith("Раху")
    assert contract["blocks"]["love"]["fields"]["needs_from_partner"]["label"]
    assert contract["blocks"]["profile"]["scales"] == scales["scales"]
    assert contract["question_hooks"] == hooks
    assert contract["technical_layer"]["display"] == "collapsed"
    assert contract["disclaimer"]


def test_blocks_contract_precision_note_without_time():
    contract = chart_human.build_blocks_contract(
        valid_payload(), hooks=[], scales=chart_human.profile_scales(sample_chart(), time_known=False),
        time_known=False)
    assert contract["precision"]["time_known"] is False
    assert "не подтверждено" in contract["precision"]["note"]


# ---------------------------------------------------------------- render

def test_render_human_text_order_and_hooks():
    payload = valid_payload()
    chart = sample_chart()
    scales = chart_human.profile_scales(chart, time_known=True)
    hooks = chart_human.question_hooks(chart, time_known=True)
    text = chart_human.render_human_text(payload, hooks, scales)
    assert text.index("**1. Кто ты**") < text.index("**2. Твои сильные стороны**") \
        < text.index("**3. Что может мешать тебе**") < text.index("**4. ❤️ Любовь**") \
        < text.index("**5. 💼 Карьера**") < text.index("**6. ✨ Твоя цель**") \
        < text.index("**7. Твой профиль**") < text.index("Тебе особенно интересно узнать")
    assert "Тебе особенно интересно узнать" in text
    assert "Раху" in text  # technical detail stays, only after the human meaning
    assert "█" in text and "░" in text


# ---------------------------------------------------------------- integration

@pytest.mark.asyncio
async def test_interpret_chart_prefers_human_contract(monkeypatch):
    from app.core import agent as agent_core

    payload = valid_payload()
    monkeypatch.setattr(agent_core.llm, "enabled", lambda: True)

    async def fake_system_for(*_args, **_kwargs):
        return "system"

    async def fake_guide(*_args, **_kwargs):
        return "guide"

    async def fake_complete(*_args, **_kwargs):
        return _as_json(payload)

    def _as_json(value):
        import json
        return json.dumps(value, ensure_ascii=False)

    monkeypatch.setattr(agent_core.agents, "system_for", fake_system_for)
    monkeypatch.setattr(agent_core.skills, "guide", fake_guide)
    monkeypatch.setattr(agent_core.llm, "complete", fake_complete)

    chart = sample_chart()
    text, live = await agent_core.interpret_chart(
        None, {"birth_time_known": 1, "tg_id": 1}, chart,
    )
    assert live is True
    assert "Кто ты" in text
    assert chart["interpretation_human"]["blocks"]["who_you_are"]["text"] == payload["who_you_are"]


@pytest.mark.asyncio
async def test_interpret_chart_falls_back_to_v1_contract(monkeypatch):
    from app.core import agent as agent_core

    human_payload = valid_payload()
    human_payload["who_you_are"] = "Марс квадрат Сатурн в 10-м доме."  # human-first gate fails
    v1_payload = {
        "luminaries": {
            "sun": "Солнце во Льве.",
            "moon": "Луна в Раке.",
            "ascendant": "Асцендент в Скорпионе.",
        },
        "personality_portrait": "Портрет.",
        "rahu_ketu": {
            "rahu": "Раху в Водолее.",
            "ketu": "Кету во Льве.",
            "growth_step": "Малый шаг.",
        },
        "strengths": ["Сила"], "weaknesses": ["Риск"],
        "purpose": "Вектор.", "relationships": "Отношения.", "career_money": "Карьера.",
        "aspect_synthesis": "Синтез.",
        "peak_periods": {"status": "нет данных", "periods": [], "note": "нет"},
        "synthesis": "Итог.", "disclaimer": "Не рекомендация.",
    }
    monkeypatch.setattr(agent_core.llm, "enabled", lambda: True)
    def _dumps(value):
        import json
        return json.dumps(value, ensure_ascii=False)

    responses = iter([_dumps(human_payload), _dumps(v1_payload)])

    async def fake_system_for(*_args, **_kwargs):
        return "system"

    async def fake_guide(*_args, **_kwargs):
        return "guide"

    async def fake_complete(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(agent_core.agents, "system_for", fake_system_for)
    monkeypatch.setattr(agent_core.skills, "guide", fake_guide)
    monkeypatch.setattr(agent_core.llm, "complete", fake_complete)

    chart = sample_chart()
    text, live = await agent_core.interpret_chart(
        None, {"birth_time_known": 1, "tg_id": 1}, chart,
    )
    assert live is True
    assert chart["interpretation_structured"]["synthesis"] == "Итог."
    assert "interpretation_human" not in chart
    assert "1. Солнце, Луна и Асцендент" in text
