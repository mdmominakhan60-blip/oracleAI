"""Create focused, versioned skills without editing the loader or monolith."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "agents"

SKILLS = {
    "lilith": [
        ("emotion-naming", "Name emotions from the user's own words before interpreting a pattern.", "emotion,reflection", "current words and concrete situations", "Never infer a diagnosis or hidden trauma."),
        ("values-conflict", "Map a stated decision to competing values and trade-offs.", "values,decision", "user-stated values and choice constraints", "Do not choose for the user or turn values into identity labels."),
        ("boundary-design", "Turn a relationship concern into a specific boundary and communication experiment.", "boundaries,relationships", "user's described interaction and requested outcome", "Do not label the other person abusive or read their mind."),
        ("decision-journal", "Structure a decision journal with prediction, evidence and review date.", "decision,experiment", "options, criteria and observable outcomes", "Do not promise the best outcome or give regulated advice."),
        ("cognitive-reframe", "Offer a bounded alternative interpretation of a self-critical thought.", "thoughts,reframe", "exact thought and triggering context", "Do not use forced positivity or deny the user's experience."),
        ("grief-reflection", "Support grief reflection through pacing, memory and one manageable next step.", "grief,care", "user's stated loss and present need", "Do not rush closure, diagnose grief or replace professional support."),
        ("habit-loop", "Map cue, routine, reward and friction for one behavior change.", "habits,behavior", "one repeated behavior and its context", "Do not claim willpower failure or prescribe treatment."),
        ("conversation-rehearsal", "Rehearse a difficult conversation using observation, request and boundary.", "communication,rehearsal", "specific conversation goal and facts", "Do not script manipulation, threats or certainty about response."),
        ("self-compassion", "Convert harsh self-judgment into accountable and humane language.", "self-compassion,reflection", "user's exact self-judgment and a concrete action", "Do not absolve harm or use generic affirmations as evidence."),
        ("monthly-review", "Review recurring themes across an explicitly selected period without overfitting.", "review,memory", "dated entries and user-approved scope", "Do not cite sensitive memory without consent or call a theme permanent."),
    ],
    "urania": [
        ("chart-data-quality", "Audit birth date, time, place, timezone and calculator consistency before synthesis.", "data,precision", "calculation metadata and supplied birth data", "Never invent missing time, place or an aspect."),
        ("aspect-patterns", "Synthesize multiple aspects as a tension/resource pattern with orb and precision.", "aspects,synthesis", "tool-returned aspects and orb", "One aspect cannot define personality or cause behavior."),
        ("dignities-traditions", "Compare dignity terminology across a named astrological school.", "tradition,technique", "tradition name and calculated placement", "Do not present one school's rule as universal or scientific."),
        ("retrogrades", "Frame retrograde symbolism as a traditional review metaphor, not a causal effect.", "retrograde,reflection", "planet and retrograde flag from calculation", "Do not blame retrograde periods for real-world harm."),
        ("lunar-phases", "Use lunar phase symbolism as a time-bounded reflective planning lens.", "moon,cycles", "calculated phase and user goal", "Do not forecast guaranteed mood, fertility or event timing."),
        ("electional-reflection", "Compare candidate dates using user criteria while keeping astrology symbolic.", "timing,choice", "candidate dates, constraints and calculated data", "Do not provide legal, medical, financial or guaranteed timing."),
        ("solar-return", "Explain a solar-return chart as a yearly reflective theme with precision limits.", "solar-return,annual", "return calculation and birth-data precision", "Do not promise events or ignore timezone/location assumptions."),
        ("synastry-boundaries", "Use synastry to discuss interaction themes without third-party mind reading.", "synastry,consent", "both charts and user-observed behavior", "Do not infer hidden feelings, betrayal or inevitable compatibility."),
        ("astro-journaling", "Turn a transit or placement into a dated observation protocol.", "journaling,transits", "one calculated theme and observable behavior", "Do not retroactively confirm predictions or cherry-pick hits."),
        ("traditional-modern-bridge", "Label historical, modern psychological and user-specific interpretations separately.", "history,interpretation", "named school and chart fact", "Do not blend schools invisibly or call symbolism validated science."),
    ],
    "lenormand": [
        ("major-arcana", "Read Major Arcana as archetypal sequence and position-specific symbolism.", "major-arcana,rws", "card identity, image and spread position", "Never literalize Death, Tower, Devil or Judgement."),
        ("minor-arcana-numerology", "Combine pip number, suit and image without treating numbers as dates or quantities.", "minor-arcana,numbers", "card, suit, number and position", "Do not predict money, people or timing from a number."),
        ("suit-dynamics", "Compare Swords, Cups, Wands and Pentacles as a symbolic tension/resource map.", "suits,synthesis", "cards and positions from tool output", "A suit is not a personality type or causal force."),
        ("elemental-dignities", "Use elemental correspondences as a named tradition and explain conflicting cards.", "elements,tradition", "named deck tradition and card set", "Do not present occult correspondences as physical evidence."),
        ("shadow-card", "Explore a difficult card as an avoided question or constraint rather than a threat.", "shadow,reflection", "card image and user question", "Never use fear, punishment or fatalism to persuade."),
        ("narrative-three-act", "Build a beginning, tension and next-step narrative from spread positions.", "narrative,spread", "position labels and card evidence", "Do not smooth contradictions into a guaranteed ending."),
        ("decision-matrix", "Use cards as reflection prompts alongside explicit user criteria for a choice.", "decision,choice", "options, criteria and card positions", "Do not decide for the user or replace due diligence."),
        ("daily-draw", "Run a one-card reflective prompt with a bounded observation and journal question.", "daily,practice", "drawn card and user's intention", "Do not turn daily draws into compulsive reassurance or prediction."),
        ("reading-review", "Review a past reading for evidence, misses, alternative explanations and learning.", "review,calibration", "dated reading and actual observations", "Do not count vague matches as successful prediction."),
        ("deck-variation", "Identify deck-specific visual and symbolic differences before applying meanings.", "deck,visual", "deck name, image and guidebook tradition", "Do not silently map an unfamiliar deck to RWS."),
    ],
    "mira": [
        ("image-quality-protocol", "Score focus, lighting, framing, resolution and distortion before reading a palm.", "image,quality", "palm image and requested zone", "Never fill unreadable areas with imagination."),
        ("hand-side-context", "Record shown hand, posture and user context without universal left/right rules.", "hand,context", "which hand, pose and user question", "Do not claim innate versus acquired destiny as fact."),
        ("finger-proportions", "Describe observable finger proportions with a confidence label and symbolic option.", "fingers,observation", "clear full-palm image and reference points", "Do not infer intelligence, morality or profession."),
        ("thumb-mechanics", "Describe thumb angle, flexibility and visible joints as image observations.", "thumb,observation", "thumb in a neutral visible pose", "Do not infer willpower or medical status."),
        ("mounts-topography", "Map visible palm regions and distinguish contour from traditional association.", "mounts,topography", "well-lit palm and anatomical zone", "Do not use mounts for disease, wealth or lifespan."),
        ("head-line-depth", "Analyze visible head-line continuity and branches with uncertainty and alternatives.", "head-line,lines", "clear head-line segment and hand side", "Do not infer IQ, mental illness or fixed personality."),
        ("heart-line-depth", "Analyze visible heart-line form as a reflective relationship theme.", "heart-line,relationships", "clear heart-line segment and question", "Do not read a partner's feelings or predict marriage."),
        ("life-line-continuity", "Describe life-line shape while explicitly separating it from longevity or health.", "life-line,safety", "clear life-line image", "Never estimate age, death, illness or lifespan."),
        ("fate-line-context", "Use fate-line imagery as a question about structure and agency, not career destiny.", "fate-line,agency", "visible fate-line segment and user goal", "Do not promise success, job or money."),
        ("photo-comparison", "Compare two palm images with a confounder checklist before claiming visual change.", "comparison,image", "dated images with comparable pose and light", "Do not claim fate or character changed from a photo difference."),
    ],
}


def render(agent: str, name: str, description: str, tags: str, evidence: str, pitfall: str) -> str:
    tool = {
        "lilith": "recall_memory recall_diary",
        "urania": "get_chart get_all_placements",
        "lenormand": "draw_tarot",
        "mira": "palm_scanner palm_photo_guide",
    }[agent]
    return f'''---
name: {name}
version: 1.0.0
description: {description}
depends_on:
  - anti-barnum-protocol
requires_tools: {tool}
tags: {tags.split(",")}
license: Proprietary
compatibility: OracleAI file-backed agent harness.
metadata:
  oracleai_agent: {agent}
  oracleai_domain: specialist-domain
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# {name}

## Purpose

{description} This skill is a focused capability, not a replacement for deterministic tools, safety policy or professional services.

## Evidence contract

Use only this evidence class: **{evidence}**. Before interpretation, record what is directly available, what comes from the user's words and what remains unknown. If the required evidence is absent or low quality, stop and ask for the smallest missing input.

## Workflow

1. Classify the question and verify that this skill is the narrowest relevant capability.
2. Call only the allow-listed tool needed for the evidence; never invent tool output.
3. Write an internal ledger of observation, traditional/domain association, hypothesis and uncertainty.
4. Add one counter-hypothesis and one observation that could support or contradict the hypothesis.
5. Give one bounded interpretation and one low-pressure, observable next step.

## Domain-specific failure mode

{pitfall}

## Anti-Barnum gate

Do not use universal personality labels, deterministic predictions, third-party mind reading, diagnosis, or certainty language. Every concrete sentence must be tied to evidence or explicitly marked as a symbolic/domain hypothesis. If the user rejects the hypothesis, update the frame rather than defending it.

## Output contract

Return: evidence → bounded interpretation → limitation → alternative explanation → user-agency step. If the user requests a forbidden claim, explain the boundary and offer a grounded reflective alternative.
'''


def main() -> None:
    created = 0
    for agent, definitions in SKILLS.items():
        skill_root = ROOT / agent / "skills"
        for name, description, tags, evidence, pitfall in definitions:
            target = skill_root / name / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text(render(agent, name, description, tags, evidence, pitfall), encoding="utf-8")
                created += 1
    print(f"created_skills={created}")


if __name__ == "__main__":
    main()
