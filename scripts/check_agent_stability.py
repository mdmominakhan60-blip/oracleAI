"""Smoke-check file-backed agents without calling external LLM providers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.agents.file_loader import (
    load_profiles,
    profile_for_legacy,
    select_skills,
)
from app.core.agents.runtime import offline_answer
from app.core.agents.registry import codes, get

EXPECTED = {
    "oracle": ("pattern-mapping", "повторяется"),
    "astro": ("transits", "транзиты планет"),
    "tarot": ("three-card-spread", "расклад таро"),
    "chiromant": ("palm-photo-quality", "фото ладони"),
}

USER = {
    "name": "Тестовый пользователь",
    "tg_id": 987654321,
    "lang": "ru",
    "birth_date": "1990-01-01",
}
CHART = {"sun": {"sign": "Рак", "element": "вода"}}


def main() -> None:
    profiles = load_profiles()
    assert set(profiles) == {"lilith", "urania", "lenormand", "mira"}
    assert all(len(profile.skills) >= 20 for profile in profiles.values())
    assert set(codes()) == {"oracle", "astro", "tarot", "chiromant"}

    for legacy_code, (expected_skill, question) in EXPECTED.items():
        profile = profile_for_legacy(legacy_code)
        assert profile is not None
        selected = select_skills(profile, question, limit=1)
        assert selected and selected[0].name == expected_skill, selected

        spec = get(legacy_code)
        outputs = [offline_answer(USER, question, CHART, [], spec) for _ in range(5)]
        assert all(len(output.strip()) >= 120 for output in outputs)
        assert all("Traceback" not in output for output in outputs)
        print(legacy_code, "ok", "runs=5", "unique_outputs=", len(set(outputs)))


if __name__ == "__main__":
    main()
