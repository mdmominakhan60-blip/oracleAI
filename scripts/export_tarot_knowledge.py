"""Export the code-owned Tarot evidence catalog as a reviewable JSON artifact."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import tarot  # noqa: E402

payload = {
    "schema_version": 1,
    "tradition": "Rider-Waite-Smith",
    "orientation": {
        "upright": "use the card's primary evidence and resource",
        "reversed": "blocked, internalized, delayed, or shadow expression; not an automatic opposite",
    },
    "cards": [
        {
            "name": card["name"],
            "arcana": card["arcana"],
            "suit": card.get("suit"),
            "number": card.get("num"),
            "meaning": card.get("meaning"),
            "short": card.get("short"),
            "advice": card.get("advice"),
        }
        for card in tarot.DECK
    ],
    "spreads": {
        code: {
            "title": spread.get("title"),
            "positions": spread.get("positions", []),
            "guide": spread.get("guide"),
        }
        for code, spread in tarot.SPREADS.items()
    },
}

out = ROOT / "data" / "tarot_cards.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(payload['cards'])} cards, {len(payload['spreads'])} spreads)")
