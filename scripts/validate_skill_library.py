"""Quality gate for the composable, file-backed agent skill library."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.agents.file_loader import load_profiles, resolve_skill_dependencies

ROOT = Path(__file__).resolve().parents[1] / "app" / "agents"
EXPECTED_AGENTS = {"lilith", "urania", "lenormand", "mira"}


def main() -> None:
    profiles = load_profiles()
    assert set(profiles) == EXPECTED_AGENTS, set(profiles)
    total = 0
    for agent_id, profile in profiles.items():
        assert len(profile.skills) >= 30, (agent_id, len(profile.skills))
        assert profile.handbook, agent_id
        assert any(skill.name == "anti-barnum-protocol" for skill in profile.skills)
        names = {skill.name for skill in profile.skills}
        assert len(names) == len(profile.skills)
        for skill in profile.skills:
            assert skill.version.count(".") == 2
            assert skill.description
            resolve_skill_dependencies(profile, [skill])
        total += len(profile.skills)
        print(agent_id, "skills=", len(profile.skills), "validated")
    assert len(list(ROOT.glob("*/skills/*/SKILL.md"))) == total
    print("skill_library=PASS", "agents=", len(profiles), "skills=", total)


if __name__ == "__main__":
    main()
