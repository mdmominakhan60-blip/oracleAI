"""Explainable, deterministic routing for default free-chat questions.

Explicit agent selection always wins. Auto-routing is only used when the caller
opened the default Oracle/Lilith chat and the signal is sufficiently strong.
Ambiguous requests containing two hard specialist domains stay with the default
agent so the UI can ask a clarifying question instead of silently mixing tools.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

DEFAULT_AGENT = "oracle"

# Weights reflect routing evidence, not answer quality. Explicit domain terms
# outrank soft context words such as "journal" or "cards".
_TERMS: dict[str, dict[str, int]] = {
    "chiromant": {
        "ладон": 4, "palm": 4, "hand": 4, "рук": 3, "фото": 3,
        "photo": 3, "снимок": 3, "линия сердца": 4, "heart line": 4, "холм": 4,
    },
    "tarot": {
        "таро": 5, "tarot": 5, "ленорман": 5, "lenormand": 5,
        "celtic cross": 5, "reversed": 4, "перевёрнут": 4,
        "расклад": 3, "spread": 3, "карты": 2, "cards": 2,
    },
    "astro": {
        "натал": 4, "natal": 4, "планет": 3, "planet": 3, "асценд": 4,
        "ascendant": 4, "восход": 4, "rising": 4, "синастр": 5, "synastry": 5,
        "транзит": 4, "transit": 4, "дом": 3, "house": 3, "раху": 5, "rahu": 5,
        "кету": 5, "ketu": 5, "сатурн": 4, "saturn": 4, "юпитер": 4,
        "jupiter": 4, "венер": 4, "venus": 4, "марс": 4, "mars": 4,
        "астролог": 4, "astrolog": 4, "birth": 3, "рожд": 3, "chart": 3,
        "карта": 2, "знак": 2, "sign": 2, "placement": 3,
    },
    "oracle": {
        "матриц": 4, "matrix": 4, "практик": 3, "practice": 3,
        "ритуал": 3, "ritual": 3, "дневник": 3, "journal": 3,
        "границ": 3, "boundar": 3, "успоко": 3, "эмоц": 3,
        "emotion": 3, "ценност": 3, "values": 3, "памят": 3, "memory": 3,
    },
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


# Аудит AI-002: подстроки без учёта алфавита дают ложные совпадения — «planет»
# (латиница + кириллица) матчил «planet». Однословные латинские термы теперь
# матчатся только по ЧИСТО латинским токенам и только по префиксу токена:
# «planets» → planet ✓, «planет» → ✗, «explanation» → ✗. Кириллические стеммы
# («натал» → «натальную») остаются подстроками — морфология там намеренная.
_LATIN_WORD_TERM = re.compile(r"^[a-z]+$")
_LATIN_TOKEN = re.compile(r"[a-z]+")


def _term_matches(term: str, normalized: str, latin_tokens: frozenset[str]) -> bool:
    if _LATIN_WORD_TERM.match(term):
        return any(tok.startswith(term) for tok in latin_tokens)
    return term in normalized


@dataclass(frozen=True)
class RouteDecision:
    agent: str
    confidence: float
    score: int
    runner_up_score: int
    reason: str
    candidates: tuple[str, ...]

    @property
    def auto_route(self) -> bool:
        return self.agent != DEFAULT_AGENT and self.confidence >= 0.76 and (self.score - self.runner_up_score) >= 2

    def as_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "confidence": round(self.confidence, 3),
            "score": self.score,
            "runner_up_score": self.runner_up_score,
            "reason": self.reason,
            "candidates": list(self.candidates),
            "auto_route": self.auto_route,
        }


def route_agent(text: str) -> RouteDecision:
    """Return an explainable agent decision without an LLM call."""
    normalized = _normalize(text)
    latin_tokens = frozenset(_LATIN_TOKEN.findall(normalized))
    scores: dict[str, int] = {agent: 0 for agent in _TERMS}
    hits: dict[str, list[str]] = {agent: [] for agent in _TERMS}
    for agent, terms in _TERMS.items():
        for term, weight in sorted(terms.items(), key=lambda item: len(item[0]), reverse=True):
            if _term_matches(term, normalized, latin_tokens):
                scores[agent] += weight
                hits[agent].append(term)

    ranked = sorted(scores, key=lambda code: (-scores[code], code))
    winner = ranked[0]
    score = scores[winner]
    runner = scores[ranked[1]]
    hard = [agent for agent in ("astro", "tarot", "chiromant") if scores[agent] >= 3]
    if len(hard) >= 2:
        return RouteDecision(DEFAULT_AGENT, 0.52, score, runner, "ambiguous hard domains; ask a clarifying question", tuple(ranked[:3]))
    if score == 0:
        return RouteDecision(DEFAULT_AGENT, 0.5, 0, 0, "no domain signal; keep default", tuple(ranked[:3]))
    if winner != DEFAULT_AGENT and score - runner < 2:
        return RouteDecision(DEFAULT_AGENT, 0.52, score, runner, "ambiguous domain; ask a clarifying question", tuple(ranked[:3]))
    confidence = min(0.98, 0.68 + 0.05 * min(score, 6) + 0.04 * max(0, score - runner))
    reason = f"matched {', '.join(hits[winner][:4])}"
    return RouteDecision(winner, confidence, score, runner, reason, tuple(ranked[:3]))
