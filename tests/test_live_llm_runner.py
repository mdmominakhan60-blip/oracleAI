from __future__ import annotations

from scripts.run_llm_eval_live import _completion_kwargs, choose_model, select_cases


def test_select_cases_is_deterministic_and_stratified():
    cases = [
        {"case_id": "ru-daily", "scenario": "daily", "language": "ru"},
        {"case_id": "en-daily", "scenario": "daily", "language": "en"},
        {"case_id": "ru-tarot", "scenario": "tarot", "language": "ru"},
    ]
    selected = select_cases(cases, 2)
    assert [case["case_id"] for case in selected] == ["ru-daily", "en-daily"]


def test_model_fallback_prefers_low_cost_catalog_entry():
    assert choose_model("missing", {"gpt-5-mini": {}, "gpt-5": {}}) == "gpt-5-mini"


def test_completion_kwargs_use_correct_token_and_reasoning_parameters():
    assert _completion_kwargs("gpt-5-mini", 250) == {
        "max_completion_tokens": 250,
        "extra_body": {"reasoning": {"effort": "minimal"}},
    }
    assert _completion_kwargs("claude-haiku-4-5", 250) == {"max_tokens": 250}
