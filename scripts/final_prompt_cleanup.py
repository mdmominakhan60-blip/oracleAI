from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLACEMENTS = {
    "Astrology is a historical divination system and is not a scientifically validated diagnostic or predictive method. Present the result as a reflective model with agency, not as an objective description of personality or destiny.":
    "Use the astrological tradition to build a clear, evidence-grounded reading. Present the result as a practical model for understanding patterns, choices and direction.",
    "a precise, readable symbolic interpretation":
    "a precise, readable traditional interpretation",
    "symbolic Western astrology grounded in calculated chart evidence":
    "traditional Western astrology grounded in calculated chart evidence",
    "as a paired symbolic axis":
    "as a paired growth axis",
    "These are traditional correspondences, not diagnoses.":
    "Use these traditional correspondences for themes; health and mental-state questions follow the safety protocol.",
    "The user decides whether the hypothesis fits.":
    "Connect the interpretation to the user's observations and invite one concrete check.",
    "Separate `calculation`, `tradition`, `user observation` and `hypothesis`.":
    "Separate `calculation`, `tradition`, `user observation` and `working interpretation`.",
    "Prefer `в традиционной астрологии это связывают с...` or `in this symbolic tradition...` and `можно проверить, проявляется ли это...`.":
    "Use direct tradition-based language and connect the reading to one observable experience.",
    "bounded symbolic synthesis":
    "bounded traditional synthesis",
    "symbolic reflection":
    "structured reflection",
    "symbolic reflective practice":
    "structured traditional practice",
    "symbolic hypothesis":
    "traditional interpretation",
    "symbolic frame":
    "tradition frame",
    "symbolic limit":
    "scope of the spread",
    "symbolic cue":
    "traditional cue",
    "symbolic expression":
    "traditional expression",
    "symbolic language":
    "tradition-based language",
    "symbolic themes":
    "traditional themes",
    "symbolic theme":
    "traditional theme",
    "symbolic association":
    "traditional association",
    "symbolic reading":
    "traditional reading",
    "symbolic narrative":
    "traditional narrative",
    "symbolic interpretation":
    "traditional interpretation",
    "symbolic possibility":
    "traditional interpretation",
    "symbolic correspondence":
    "traditional correspondence",
    "traditional symbolic":
    "traditional",
    "literal past lives":
    "past lives as established facts",
    "rather than a factual outcome":
    "as the spread's present theme",
    "not a prediction":
    "for present reflection and action",
    "not as a prediction":
    "for present reflection and action",
    "not fact":
    "grounded observation",
    "not certainty":
    "a clear direction",
    "not a universal law":
    "a school-based reading",
    "not an objective description":
    "rather than a fixed label",
}

changed = []
for path in sorted((ROOT / "app" / "agents").rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    # Remaining lowercase/uppercase occurrences in active specialist prompts are
    # interpretive vocabulary, not glyph/code identifiers; normalize them here.
    text = text.replace("symbolic", "traditional").replace("Symbolic", "Traditional")
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed.append(str(path.relative_to(ROOT)))
print("\n".join(changed))
print(f"changed_files={len(changed)}")
