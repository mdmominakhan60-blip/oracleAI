from __future__ import annotations

import asyncio

from app.core import agent as agent_module
from app.core import agents
from app.core import tool_registry
from app.core.agents.file_loader import profile_for_legacy, skill_context


class _FakeUser(dict):
    pass


def test_mira_grounding_detects_palm_questions() -> None:
    assert agent_module._mira_needs_grounding(
        "chiromant", "Что видно по линии сердца?"
    )
    assert agent_module._mira_needs_grounding("chiromant", "Прочитай мою ладонь")
    assert agent_module._mira_needs_grounding(
        "chiromant", "What does my heart line show?"
    )
    assert agent_module._mira_needs_grounding(
        "chiromant", "Look at this hand photo"
    )
    assert not agent_module._mira_needs_grounding("chiromant", "Что ты умеешь?")
    assert not agent_module._mira_needs_grounding(
        "astro", "Что видно по линии сердца?"
    )


def test_mira_grounding_does_not_trigger_on_substring_collisions() -> None:
    assert not agent_module._mira_needs_grounding(
        "chiromant", "Can we continue online tomorrow?"
    )
    assert not agent_module._mira_needs_grounding(
        "chiromant", "How do you handle uncertainty?"
    )
    assert not agent_module._mira_needs_grounding(
        "chiromant", "Расскажи о структуре выбора"
    )
    assert not agent_module._mira_needs_grounding(
        "chiromant", "Как устроено руководство практикой?"
    )


def test_mira_profile_has_expected_tools_and_skill_count() -> None:
    profile = profile_for_legacy("chiromant")
    assert profile is not None
    assert len(profile.skills) == 34
    assert set(profile.data["tools"]) == {
        "activate_skill", "palm_scanner", "palm_photo_guide", "palm_history"
    }
    assert any(skill.name == "palm-evidence-reading" for skill in profile.skills)
    assert any(skill.name == "comparative-reading" for skill in profile.skills)


def test_mira_skill_context_routes_line_question() -> None:
    context = skill_context(
        "chiromant", "Что означает моя линия сердца?", limit=3
    )
    assert "heart-line" in context
    assert "anti-barnum-protocol" in context


def test_mira_tools_are_allow_listed_and_have_schemas() -> None:
    spec = agents.get("chiromant")
    available = tool_registry.tools_for(spec.skills)
    names = {tool["name"] for tool in available}
    assert names == {
        "activate_skill", "palm_scanner", "palm_photo_guide", "palm_history"
    }
    for tool in available:
        assert tool["input_schema"]["type"] == "object"


def test_mira_server_grounding_prefetches_scanner(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_execute(db, user, name, args):
        events.append((name, args))
        return "[PALM_EVIDENCE] heart visible: clear, confidence 0.84"

    async def fake_answer(db, user, question, **kwargs):
        events.append(("answer", kwargs.get("extra_rules", "")))
        return "grounded answer"

    monkeypatch.setattr(agent_module.skills, "execute", fake_execute)
    monkeypatch.setattr(agent_module.agents, "answer", fake_answer)

    result = asyncio.run(
        agent_module.ask_oracle(
            object(),
            _FakeUser(name="Test"),
            "Что видно по линии сердца?",
            agent="chiromant",
            trace=[],
        )
    )

    assert result == "grounded answer"
    assert events[0][0] == "palm_scanner"
    assert events[1][0] == "answer"
    assert "SERVER-GROUNDED MIRA PALM EVIDENCE" in str(events[1][1])


def test_mira_server_grounding_skips_unrelated_chat(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    async def fake_execute(db, user, name, args):
        events.append((name, args))
        return "unexpected"

    async def fake_answer(db, user, question, **kwargs):
        events.append(("answer", kwargs.get("extra_rules", "")))
        return "normal conversational answer"

    monkeypatch.setattr(agent_module.skills, "execute", fake_execute)
    monkeypatch.setattr(agent_module.agents, "answer", fake_answer)

    result = asyncio.run(
        agent_module.ask_oracle(
            object(),
            _FakeUser(name="Test"),
            "Can we continue online tomorrow?",
            agent="chiromant",
            trace=[],
        )
    )

    assert result == "normal conversational answer"
    assert [event[0] for event in events] == ["answer"]


def test_mira_image_prompt_separates_observation_from_interpretation() -> None:
    from app.core.palm.prompts import PALM_SYSTEM, PALM_USER

    assert "Traditional symbolism is applied later" not in PALM_SYSTEM
    assert "Традиционная символика будет применена позже" in PALM_SYSTEM
    assert "summary" in PALM_SYSTEM
    assert "без традиционной трактовки" in PALM_SYSTEM
    assert "Не пиши традиционное значение линии" in PALM_USER
    assert "`narrative` — это НЕ интерпретация" in PALM_SYSTEM
    assert "традиционных значений" in PALM_USER


def test_comparative_skill_does_not_claim_raw_photo_access() -> None:
    profile = profile_for_legacy("chiromant")
    assert profile is not None
    skill = next(
        item for item in profile.skills if item.name == "comparative-reading"
    )
    assert "не хран" in skill.body.lower()
    assert "pixel" in skill.body.lower()


def test_mira_bot_escapes_untrusted_palm_text() -> None:
    from pathlib import Path

    source = Path("app/bot/features.py").read_text(encoding="utf-8")
    palm_section = source.split("async def palm_photo", 1)[1].split(
        "# ─────────────────────────────── ТАРО", 1
    )[0]
    assert "tg_esc(narrative)" in palm_section
    assert "tg_esc(str(prompts[0]))" in palm_section
    assert "tg_esc(str(item))" in palm_section
