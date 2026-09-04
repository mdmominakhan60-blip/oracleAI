"""Регрессии политики краткосрочного контекста агентного чата."""
from app.core.agents.base import language_and_gender_guidance
from app.core.agents.context import build_bounded_history


def test_bounded_history_keeps_question_once_when_already_saved():
    question = "Стоит ли мне менять работу?"
    messages = build_bounded_history(
        [{"role": "user", "content": question}], question, recent_limit=6)
    assert messages == [{"role": "user", "content": question}]


def test_bounded_history_adds_question_once_when_not_persisted_yet():
    question = "Что мне важно сегодня?"
    messages = build_bounded_history(
        [{"role": "user", "content": "Я устала"},
         {"role": "assistant", "content": "Давай бережно посмотрим."}],
        question,
        recent_limit=6,
    )
    assert messages[-1] == {"role": "user", "content": question}
    assert sum(m["content"] == question for m in messages) == 1


def test_bounded_history_summarises_earlier_user_topics_only():
    history = [
        {"role": "user", "content": "Первая тема — работа"},
        {"role": "assistant", "content": "Ранний вывод агента не должен стать фактом"},
        {"role": "user", "content": "Вторая тема — отношения"},
        {"role": "assistant", "content": "Ответ про отношения"},
        {"role": "user", "content": "Третья тема — отдых"},
        {"role": "assistant", "content": "Ответ про отдых"},
    ]
    messages = build_bounded_history(history, "Что объединяет эти темы?", recent_limit=3)
    assert messages[0]["role"] == "user"
    assert "работа" in messages[0]["content"]
    assert "Ранний вывод агента" not in messages[0]["content"]
    assert messages[-1]["content"] == "Что объединяет эти темы?"
    assert len(messages) == 4


def test_bounded_history_has_no_state_between_threads():
    first = build_bounded_history(
        [{"role": "user", "content": "Тема первого чата"}],
        "Продолжим?", recent_limit=4)
    second = build_bounded_history([], "Новый разговор", recent_limit=4)
    assert any("первого чата" in m["content"] for m in first)
    assert all("первого чата" not in m["content"] for m in second)


def test_agent_guidance_uses_feminine_russian_forms_for_female_profile():
    guidance = language_and_gender_guidance({"lang": "ru", "gender": "f"})
    assert "женский род" in guidance
    assert "мужской род" not in guidance


def test_agent_guidance_uses_masculine_russian_forms_for_male_profile():
    guidance = language_and_gender_guidance({"lang": "ru", "gender": "m"})
    assert "мужской род" in guidance
    assert "женский род" not in guidance


def test_agent_guidance_requires_neutral_russian_wording_without_gender():
    guidance = language_and_gender_guidance({"lang": "ru", "gender": None})
    assert "не предполагай" in guidance.lower()
    assert "нейтрально" in guidance.lower()


def test_agent_guidance_is_gender_neutral_in_english():
    guidance = language_and_gender_guidance({"lang": "en", "gender": "m"})
    assert "gender-neutral" in guidance
    assert "they/them" in guidance
    assert "мужской род" not in guidance


def test_memory_extractor_uses_profile_gender_without_assumption():
    from app.core.agent import _memory_extract_prompt

    assert "её партнёра" in _memory_extract_prompt({"gender": "f"})
    assert "его партнёра" in _memory_extract_prompt({"gender": "m"})
    assert "у пользователя" in _memory_extract_prompt({"gender": None})


def test_offline_tarot_uses_neutral_question_label_for_every_profile():
    from app.core.agent import _reading_offline

    text = _reading_offline(
        {"name": "Алекс", "gender": "m"},
        "Одна карта",
        [{"emoji": "✦", "name": "Звезда", "meaning": "надежда", "reversed": False}],
        "✦ Звезда",
        question="Что мне важно?",
    )
    assert "Твой вопрос" in text
    assert "Ты спросила" not in text


def test_llm_fallback_does_not_assume_user_gender():
    from app.core.llm import _fallback_text

    assert "милая" not in _fallback_text().lower()
    assert "попробуй задать вопрос" in _fallback_text().lower()
