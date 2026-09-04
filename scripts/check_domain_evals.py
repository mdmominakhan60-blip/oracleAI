"""Validate domain eval fixtures and the file-backed skill contract."""
from __future__ import annotations

# The repository-root bootstrap must execute before local `app` imports.
# ruff: noqa: E402
import sys
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.agents.file_loader import profile_for_legacy, skill_context

ROOT = Path(__file__).resolve().parents[1] / "app" / "agents"


def main() -> None:
    total = 0
    for eval_path in sorted(ROOT.glob("*/evals/cases.yaml")):
        data = yaml.safe_load(eval_path.read_text(encoding="utf-8")) or {}
        legacy_code = str(data["legacy_code"])
        profile = profile_for_legacy(legacy_code)
        assert profile is not None, legacy_code
        skill_names = {skill.name for skill in profile.skills}
        cases = data.get("cases", [])
        assert cases, eval_path
        for case in cases:
            expected = str(case["expected_skill"])
            assert expected in skill_names, (eval_path, expected)
            assert case.get("must_contain")
            assert case.get("must_not_contain")
            context = skill_context(legacy_code, str(case["prompt"]), limit=3)
            assert "[SKILL_INDEX]" in context
            assert "anti-barnum-protocol" in context
            assert expected in context
            assert "ACTIVE_SKILL:" not in context
            total += 1
        print(eval_path.parent.parent.name, "cases=", len(cases), "ok")
    assert total == 54, total
    print("domain_evals=PASS", "cases=", total)


if __name__ == "__main__":
    main()
