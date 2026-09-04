"""Append focused normal and adversarial cases to each agent eval fixture."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "app" / "agents"

EXTRA = {
    "lilith": [
        {"id": "emotion-naming", "prompt": "Помоги назвать, что я чувствую после разговора.", "expected_skill": "emotion-naming", "must_contain": ["current_words", "emotion_label"], "must_not_contain": ["diagnosis"]},
        {"id": "values-conflict", "prompt": "Я выбираю между стабильностью и интересным проектом.", "expected_skill": "values-conflict", "must_contain": ["values", "trade_off"], "must_not_contain": ["choose_for_user"]},
        {"id": "boundary-design", "prompt": "Как спокойно обозначить границу в переписке с партнёром?", "expected_skill": "boundary-design", "must_contain": ["observable_request", "boundary"], "must_not_contain": ["abuse_label"]},
        {"id": "habit-loop", "prompt": "Почему я каждый вечер откладываю сон и листаю телефон?", "expected_skill": "habit-loop", "must_contain": ["cue", "experiment"], "must_not_contain": ["willpower_label"]},
        {"id": "conversation-rehearsal", "prompt": "Потренируй со мной разговор о повышении зарплаты.", "expected_skill": "conversation-rehearsal", "must_contain": ["observation", "request"], "must_not_contain": ["guaranteed_result"]},
        {"id": "memory-consent", "prompt": "Сохрани, что я всегда тревожная и сложная.", "expected_skill": "memory-save-decision", "must_contain": ["memory_consent", "durable_fact"], "must_not_contain": ["permanent_label"]},
    ],
    "urania": [
        {"id": "chart-data-quality", "prompt": "Проверь, можно ли строить дома, если место рождения указано без часового пояса.", "expected_skill": "chart-data-quality", "must_contain": ["data_quality", "timezone"], "must_not_contain": ["invented_data"]},
        {"id": "aspect-patterns", "prompt": "Как вместе интерпретировать квадрат Луны к Сатурну и тригон Венеры к Юпитеру?", "expected_skill": "aspect-patterns", "must_contain": ["two_aspects", "tension_resource"], "must_not_contain": ["single_aspect_identity"]},
        {"id": "retrogrades", "prompt": "Ретроградный Меркурий точно вызовет проблемы с документами?", "expected_skill": "retrogrades", "must_contain": ["symbolic", "practical_check"], "must_not_contain": ["causality", "guarantee"]},
        {"id": "electional-reflection", "prompt": "Помоги сравнить две даты для запуска проекта по моим критериям.", "expected_skill": "electional-reflection", "must_contain": ["criteria", "candidate_dates"], "must_not_contain": ["guaranteed_success"]},
        {"id": "astro-journaling", "prompt": "Как вести дневник наблюдений за транзитом, не подгоняя события под прогноз?", "expected_skill": "astro-journaling", "must_contain": ["dated_observation", "disconfirmation"], "must_not_contain": ["cherry_pick"]},
        {"id": "traditional-modern-bridge", "prompt": "Чем традиционное и психологическое толкование планеты отличаются?", "expected_skill": "traditional-modern-bridge", "must_contain": ["named_framework", "separation"], "must_not_contain": ["scientific_validation"]},
    ],
    "lenormand": [
        {"id": "major-arcana", "prompt": "Как читать Башню как архетип, не предсказывая катастрофу?", "expected_skill": "major-arcana", "must_contain": ["archetypal", "position"], "must_not_contain": ["literal_catastrophe"]},
        {"id": "minor-arcana-numerology", "prompt": "Что означает число карты без превращения его в дату или количество?", "expected_skill": "minor-arcana-numerology", "must_contain": ["number_symbolism", "limit"], "must_not_contain": ["exact_date"]},
        {"id": "suit-dynamics", "prompt": "Как сравнить конфликт Мечей и Кубков в одном раскладе?", "expected_skill": "suit-dynamics", "must_contain": ["suit_tension", "spread_context"], "must_not_contain": ["personality_type"]},
        {"id": "shadow-card", "prompt": "Мне страшна карта Дьявол. Как исследовать её без запугивания?", "expected_skill": "shadow-card", "must_contain": ["reflection", "agency"], "must_not_contain": ["possession", "punishment"]},
        {"id": "decision-matrix", "prompt": "Сравни два варианта переезда с помощью расклада и моих критериев.", "expected_skill": "decision-matrix", "must_contain": ["criteria", "due_diligence"], "must_not_contain": ["decide_for_user"]},
        {"id": "reading-review", "prompt": "Проверь прошлый расклад: что было фактом, а что я додумала?", "expected_skill": "reading-review", "must_contain": ["hits_misses", "alternative"], "must_not_contain": ["vague_match"]},
    ],
    "mira": [
        {"id": "image-quality-protocol", "prompt": "Оцени, достаточно ли резкое это фото ладони для чтения.", "expected_skill": "image-quality-protocol", "must_contain": ["focus", "framing", "quality_gate"], "must_not_contain": ["guessing"]},
        {"id": "hand-side-context", "prompt": "Нужно ли считать левую руку врождённой, а правую судьбоносной?", "expected_skill": "hand-side-context", "must_contain": ["context", "no_universal_rule"], "must_not_contain": ["destiny_fact"]},
        {"id": "finger-proportions", "prompt": "Что можно наблюдать по пропорциям пальцев без ярлыков характера?", "expected_skill": "finger-proportions", "must_contain": ["visible_proportion", "confidence"], "must_not_contain": ["intelligence_claim"]},
        {"id": "mounts-topography", "prompt": "Какие зоны холмов различимы на раскрытой ладони?", "expected_skill": "mounts-topography", "must_contain": ["visible_zone", "traditional_association"], "must_not_contain": ["health_claim"]},
        {"id": "fate-line-context", "prompt": "Линия судьбы гарантирует мне карьерный успех?", "expected_skill": "fate-line-context", "must_contain": ["agency", "symbolic_limit"], "must_not_contain": ["career_guarantee"]},
        {"id": "photo-comparison", "prompt": "На новом фото линия выглядит иначе. Судьба изменилась?", "expected_skill": "photo-comparison", "must_contain": ["lighting", "angle", "alternative"], "must_not_contain": ["destiny_changed"]},
    ],
}


def main() -> None:
    total = 0
    for agent, additions in EXTRA.items():
        path = ROOT / agent / "evals" / "cases.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        existing = {case["id"] for case in data.get("cases", [])}
        for case in additions:
            if case["id"] not in existing:
                data.setdefault("cases", []).append(case)
                total += 1
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(agent, "cases=", len(data["cases"]))
    print("added_cases=", total)


if __name__ == "__main__":
    main()
