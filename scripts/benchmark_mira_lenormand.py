from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.agents.file_loader import profile_for_legacy, select_skills  # noqa: E402

CASES = [
    ("chiromant", "Разбери мою ладонь по этому снимку: что реально видно и какая уверенность?", "visual-evidence-protocol"),
    ("chiromant", "Trace the life line: continuity, breaks, branches and visible path only", "palm-line-topology"),
    ("chiromant", "Сравни Western, Indian Hasta и Chinese подходы к моей линии головы, но не смешивай школы", "palm-technique-triangulation"),
    ("chiromant", "На открытой ладони видны ли линии брака и children? What photo should I take?", "capture-rectification"),
    ("chiromant", "Фото бликует и пальцы обрезаны — can you still read the mounts?", "capture-rectification"),
    ("chiromant", "What is visible about my heart/head/fate lines on the uploaded image?", "visual-evidence-protocol"),
    ("chiromant", "Скажи, что означает topology линии жизни: дуга, глубина, разрывы, но не срок жизни", "palm-line-topology"),
    ("chiromant", "Can you compare my old and new palm photos and report only visible changes?", "photo-comparison"),
    ("chiromant", "Знаешь все техники хиромантии? Дай разницу между школами по одному видимому холму", "palm-technique-triangulation"),
    ("chiromant", "Can palm lines show disease, pregnancy or death?", "palm-safety"),
    ("tarot", "После draw покажи deck, position, card ID и upright/reversed ledger", "card-ledger-evidence"),
    ("tarot", "Explain the adjacent pair and repeated suit pattern, not isolated card meanings", "combination-synthesis"),
    ("tarot", "Я не знаю, что спросить: what will happen in my life? Помоги выбрать spread", "question-to-spread"),
    ("tarot", "Покажи checksum расклада и объясни, что он доказывает, а чего не доказывает", "tarot-proof-safety"),
    ("tarot", "Two reversed cards together: compare their orientation tension and offer a counter-reading", "combination-synthesis"),
    ("tarot", "What does my ex think and will they return? Reframe this before drawing", "question-to-spread"),
    ("tarot", "Can the cards decide a legal case or investment for me?", "tarot-proof-safety"),
    ("tarot", "Для ежедневного journal reflection лучше one-card или Celtic Cross?", "question-to-spread"),
    ("tarot", "Read all ten Celtic Cross positions from the actual stored cards without adding cards", "card-ledger-evidence"),
    ("tarot", "Tarot vs Lenormand: clarify deck tradition and select the smallest useful spread", "question-to-spread"),
]


def main() -> int:
    rows = []
    failures = []
    for code, query, expected in CASES:
        profile = profile_for_legacy(code)
        selected = select_skills(profile, query, 3)
        names = [skill.name for skill in selected]
        rank = names.index(expected) + 1 if expected in names else None
        row = {"agent": code, "query": query, "expected": expected,
               "top3": names, "rank": rank, "ok": rank is not None}
        rows.append(row)
        if rank is None:
            failures.append(row)
    passed = len(rows) - len(failures)
    report = {"total": len(rows), "passed": passed,
              "accuracy": round(passed / len(rows), 3),
              "top1_passed": sum(r["rank"] == 1 for r in rows),
              "top3_passed": passed, "failures": failures, "cases": rows}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
