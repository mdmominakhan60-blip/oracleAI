"""Multilingual, multi-intent skill-routing benchmark for Urania and Lilith."""
from __future__ import annotations

# The repository-root bootstrap must execute before local `app` imports.
# ruff: noqa: E402
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.agents.file_loader import profile_for_legacy, select_skills

CASES = [
    # Urania: explicit and mixed astrology intents.
    ("astro", "Покажи Раху и Кету и объясни их ось", "lunar-nodes"),
    ("astro", "Can you compare our synastry aspects without mind-reading?", "compatibility-synastry"),
    ("astro", "my natal chart: Асцендент, MC and houses", "houses-and-angles"),
    ("astro", "Ретроградный Меркурий и practical checks", "retrogrades"),
    ("astro", "What are the current transits of Saturn for my chart?", "transits"),
    ("astro", "Что показывают Хирон, Джуно и expanded points?", "chart-synthesis"),
    ("astro", "No birth time: can you name the house of Rahu?", "date-only-mode"),
    ("astro", "Compare two launch dates using my criteria, not a guarantee", "electional-reflection"),
    ("astro", "career timing по карте — give criteria, not certainty", "career-symbolism"),
    ("astro", "Лунные фазы и дневник наблюдений на неделю", "lunar-phases"),
    # Lilith: reflection, Matrix, memory and practice intents.
    ("oracle", "Разбери мой аркан судьбы: ресурс, тень и choice", "matrix-reading"),
    ("oracle", "Help me name what I feel after that conversation", "emotion-naming"),
    ("oracle", "Мне нужно design a boundary в переписке", "boundary-design"),
    ("oracle", "Что ты помнишь обо мне, если memory disabled?", "memory-recall"),
    ("oracle", "Why do I keep scrolling at night? Find the habit loop", "habit-loop"),
    ("oracle", "Что я могу наблюдать в repeated relationship pattern?", "relationship-reflection"),
    ("oracle", "I am choosing stability or an exciting project", "values-conflict"),
    ("oracle", "Подбери gentle practice for more спокойствия", "practice-selection"),
    ("oracle", "Review my diary themes this month", "diary-dynamics"),
    ("oracle", "Help me rehearse a difficult conversation", "conversation-rehearsal"),
]


def main() -> int:
    rows = []
    failures = []
    for code, query, expected in CASES:
        profile = profile_for_legacy(code)
        selected = select_skills(profile, query, 3)
        names = [skill.name for skill in selected]
        ok = expected in names
        row = {"agent": code, "query": query, "expected": expected, "selected": names, "ok": ok}
        rows.append(row)
        if not ok:
            failures.append(row)
    report = {
        "total": len(CASES),
        "passed": len(CASES) - len(failures),
        "accuracy": round((len(CASES) - len(failures)) / len(CASES), 3),
        "failures": failures,
        "cases": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
