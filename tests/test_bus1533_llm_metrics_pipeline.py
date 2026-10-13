"""BUS-1533/1531: LLM-usage pipeline не пишется после перезапуска бота.

До правки `record_usage` глотал сбои записи в `llm_usage` через `log.debug`,
поэтому точка остановки метрик (один тик после ребута, потом стоп) не
попадала ни в логи, ни в prometheus, и алерты не среагировали. Проверяем:
- при неудачной записи `record_usage` пишет warning (не debug) — оператор
  видит сигнал, а не молчаливое проваливание;
- `complete()` фиксирует ok=False у мёртвого провайдера и продолжает перебор
  цепочки (fails over), чтобы следующий вызов уже шёл на рабочую модель;
- `custom_model_lite` дефолт — живая модель, а не catalog-drifted 400.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm import complete, record_usage, settings


@pytest.mark.asyncio
async def test_record_usage_warns_on_write_failure(db, caplog):
    """Сбой INSERT в llm_usage должен быть виден, а не пропадать в debug."""
    with patch("app.repo.analytics") as repo, \
         patch("app.core.product_cost") as pc:
        repo.record_llm_usage = AsyncMock(side_effect=RuntimeError("connection reset"))
        pc.record_llm = AsyncMock()
        with caplog.at_level(logging.WARNING, logger="oracle.llm"):
            await record_usage(db, provider="custom", model="m", purpose="x",
                               ok=True, tg_id=1)
    assert any("не записан в llm_usage" in r.getMessage() for r in caplog.records) or "не записан в llm_usage" in caplog.text, (
        "BUS-1533: сбой записи метрик должен логироваться на WARNING, "
        "чтобы оператор видел точку остановки пайплайна")


@pytest.mark.asyncio
async def test_complete_fails_over_and_records_ok_false_on_dead_provider(db):
    """Мёртвый провайдер (400) не роняет вызов: ok=False фиксируется,
    цепочка продолжается и следующий провайдер получает шанс."""
    chain = ("dead", "live")

    def fake_complete(provider, *args, **kwargs):
        # `_with_retries` повторяет вызов RETRIES=2 раза подряд, поэтому
        # side_effect-список съедается на одном провайдере. Функция возвращает
        # исшение для мёртвого провайдера и успех для живого — тогда failover
        # проходится корректно: dead → ok=False, live → ok=True.
        if provider == "dead":
            raise RuntimeError("bad_request: model not available")
        return "ok"

    with patch.object(settings, "_provider_chain_override", chain), \
         patch("app.core.llm._llm_slot") as slot, \
         patch("app.core.llm._complete_with", side_effect=fake_complete) as cw, \
         patch("app.core.llm.record_usage") as ru:
        slot.return_value.__aenter__ = AsyncMock(return_value=None)
        slot.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await complete("s", "u", tier="lite", tg_id=1, db=None)
    assert result == "ok"
    assert ru.call_count == 2
    assert ru.call_args_list[0].kwargs["ok"] is False
    assert ru.call_args_list[1].kwargs["ok"] is True
    assert cw.call_count == 3, (
        "complete() должен сделать 2 попытки по RETRIES на мёртвом "
        "провайдере + 1 на резервном")


def test_custom_model_lite_default_is_live_catalog_model():
    """BUS-1533 п.1: дефолт lite-модели — живая модель, не antigravity/
    gemini-3.6-flash-high, который вернёт 400 'not available in the catalog'."""
    assert settings.custom_model_lite == "oc/claude-sonnet-5"
    assert settings.custom_model_lite != "antigravity/gemini-3.6-flash-high"


@pytest.mark.asyncio
async def test_record_usage_writes_even_when_call_failed(db):
    """П.2: ok=0 (ошибочные вызовы) тоже пишутся в llm_usage — без этого
    доля ok=0 не измеряется и алерт OracleAILLMFailureRateHigh слеп."""
    with patch("app.repo.analytics") as repo, \
         patch("app.core.product_cost") as pc:
        repo.record_llm_usage = AsyncMock()
        pc.record_llm = AsyncMock()
        await record_usage(db, provider="custom", model="m", purpose="x",
                           ok=False, tg_id=1)
    assert repo.record_llm_usage.await_count == 1
    # analytics.repo.record_llm_usage(db, params: dict) — ok лежит в params.
    assert repo.record_llm_usage.await_args.args[1]["ok"] == 0