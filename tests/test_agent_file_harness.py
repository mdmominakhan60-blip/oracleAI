from __future__ import annotations

from app.core.agents.file_loader import (
    activate_skill,
    load_profiles,
    profile_for_legacy,
    select_skills,
    skill_context,
)
from app.core.agents.registry import codes, get


def test_file_profiles_and_skills_are_discovered():
    profiles = load_profiles()
    assert set(profiles) == {"lilith", "urania", "lenormand", "mira"}
    assert all(len(item.skills) >= 20 for item in profiles.values())


def test_file_profile_quality_metadata_is_live():
    astro = get("astro")
    assert astro.skills_max_active == 3
    assert astro.max_turns == 6
    assert astro.max_tool_calls == 8
    assert astro.timeout_s == 35.0
    assert astro.memory_mode == "opt_in"
    assert astro.risk_level == "medium"
    assert astro.output_contract == "agent_response.v1"
    payload = astro.as_dict({"oracle_name": None})
    assert len(payload["capabilities"]) == len(astro.skills)
    assert payload["quality"]["skills_max_active"] == 3


def test_skill_frontmatter_is_portable_and_unique():
    profiles = load_profiles()
    for profile in profiles.values():
        for skill in profile.skills:
            assert skill.name == skill.path.rsplit("/", 2)[-2]
            assert skill.description
            assert skill.metadata["oracleai_agent"] == profile.agent_id
            assert skill.metadata.get("oracleai_loading", "on_demand") == "on_demand"
        assert profile.handbook


def test_lazy_skill_activation_is_available_for_every_file_agent():
    cases = (
        ("oracle", "matrix-reading"),
        ("astro", "natal-chart-foundations"),
        ("tarot", "three-card-spread"),
        ("chiromant", "heart-line-depth"),
    )
    for code, name in cases:
        context = skill_context(code, "покажи профильный разбор", limit=3)
        assert "[SKILL_INDEX]" in context
        assert "ACTIVE_SKILL:" not in context
        assert name in context
        activated = activate_skill(code, name)
        assert "[ACTIVATED_SKILL]" in activated
        assert f"ACTIVE_SKILL: {name}" in activated


def test_russian_queries_select_relevant_specialist_skill():
    mira = profile_for_legacy("chiromant")
    urania = profile_for_legacy("astro")
    tarot = profile_for_legacy("tarot")
    assert mira is not None and urania is not None and tarot is not None
    assert select_skills(mira, "фото ладони", 1)[0].name == "palm-photo-quality"
    assert select_skills(mira, "линия сердца", 1)[0].name == "heart-line"
    assert select_skills(urania, "транзиты планет", 1)[0].name == "transits"
    assert select_skills(tarot, "расклад таро", 1)[0].name == "three-card-spread"
    assert select_skills(urania, "Раху и Кету в моей карте", 1)[0].name == "lunar-nodes"
    assert select_skills(urania, "synastry and relationship aspects", 1)[0].name == "compatibility-synastry"
    assert select_skills(tarot, "выбор между двумя вариантами", 1)[0].name == "choice-spread"
    assert select_skills(mira, "холмы и форма ладони", 1)[0].name == "mounts-topography"


def test_skill_context_is_bounded_and_legacy_registry_is_unchanged():
    context = skill_context("chiromant", "фото ладони и линия сердца", limit=3)
    assert "[SKILL_INDEX]" in context
    assert "AVAILABLE_SKILL_CARDS" in context
    assert "ROUTED_SKILL_HINTS" in context
    assert "ACTIVE_SKILL:" not in context
    assert "heart-line" in context and "heart-line-depth" in context
    assert len(context) < 12000
    activated = activate_skill("chiromant", "heart-line")
    assert "[ACTIVATED_SKILL]" in activated
    assert "ACTIVE_SKILL: heart-line" in activated
    assert "ANTI-BARNUM" in activated.upper() or "evidence" in activated.lower()
    assert set(codes()) == {"oracle", "astro", "tarot", "chiromant"}
    assert get("chiromant").skills == (
        "activate_skill",
        "palm_scanner",
        "palm_photo_guide",
        "palm_history",
    )


async def test_runtime_places_active_skills_before_safety_tail(monkeypatch):
    from app.core.agents import runtime

    spec = get("astro")
    user = {"lang": "ru", "name": "Тест", "gender": None, "memory_enabled": False}
    user["oracle_name"] = None

    async def fake_resolve(db, code):
        return spec, spec.style, spec.rules

    async def fake_context(db, current_user, current_spec, question=""):
        return "chart", "matrix", [], ""

    monkeypatch.setattr(runtime, "resolve", fake_resolve)
    monkeypatch.setattr(runtime, "_context", fake_context)
    prompt = await runtime.system_for(None, user, spec, question="транзиты планет")
    assert "[SKILL_INDEX]" in prompt
    assert "ACTIVE_SKILL:" not in prompt
    assert prompt.index("[SKILL_INDEX]") < prompt.index("Правила безопасности")


def test_offline_fallback_is_domain_specific():
    from app.core.agents.runtime import offline_answer

    user = {"lang": "ru", "name": "Тест", "tg_id": 1, "birth_date": "1990-06-21",
            "memory_enabled": False}
    chart = {"precision": "exact", "sun": {"sign": "Рак"},
             "planets": [{"name": "Луна", "sign": "Рыбы"}],
             "nodes": [{"name": "Раху (Северный узел)", "sign": "Козерог"},
                       {"name": "Кету (Южный узел)", "sign": "Рак"}],
             "lunar_nodes": {"rahu": {"sign": "Козерог"}, "ketu": {"sign": "Рак"}}}
    astro_text = offline_answer(user, "Что в моей карте?", chart, [], get("astro"))
    tarot_text = offline_answer(user, "Сделай расклад", chart, [], get("tarot"))
    assert "Раху" in astro_text and "Кету" in astro_text
    assert "три карты" not in astro_text.lower()
    assert "карты" in tarot_text.lower()


def test_composable_skill_dependencies_and_tool_allowlist():
    from app.core.agents.file_loader import profile_for_legacy, resolve_skill_dependencies

    profile = profile_for_legacy("astro")
    assert profile is not None
    target = next(skill for skill in profile.skills if skill.name == "aspect-patterns")
    resolved = resolve_skill_dependencies(profile, [target])
    assert [skill.name for skill in resolved] == ["anti-barnum-protocol", "aspect-patterns"]
    assert set(target.requires_tools).issubset(set(profile.data["tools"]))


def test_complex_multilingual_routing_benchmark_is_top_three_stable():
    from scripts.benchmark_skill_routing import CASES

    failures = []
    for code, query, expected in CASES:
        profile = profile_for_legacy(code)
        assert profile is not None
        selected = [skill.name for skill in select_skills(profile, query, 3)]
        if expected not in selected:
            failures.append((code, query, expected, selected))
    assert not failures, failures


def test_vedic_adversarial_routing_benchmark_is_top_three_stable():
    from scripts.benchmark_vedic_routing import CASES

    profile = profile_for_legacy("astro")
    assert profile is not None
    failures = []
    for query, expected in CASES:
        selected = [skill.name for skill in select_skills(profile, query, 3)]
        if expected not in selected:
            failures.append((query, expected, selected))
    assert not failures, failures


def test_mira_lenormand_routing_benchmark_is_top_three_stable():
    from scripts.benchmark_mira_lenormand import CASES

    failures = []
    for code, query, expected in CASES:
        profile = profile_for_legacy(code)
        assert profile is not None
        selected = [skill.name for skill in select_skills(profile, query, 3)]
        if expected not in selected:
            failures.append((code, query, expected, selected))
    assert not failures, failures
