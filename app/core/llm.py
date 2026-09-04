"""Единый LLM-слой: Anthropic, OpenAI и любой OpenAI-совместимый сервер
(MiniMax, vLLM, LM Studio...) за одним интерфейсом.

- complete(system, user_text, tier)        — простой ответ без инструментов
- run_agent(system, messages, tools, exec) — tool-use цикл (скиллы)
- transcribe(bytes)                        — голос → текст (Whisper)
- speak(text)                              — текст → голос (TTS)

Надёжность:
- цепочка провайдеров из settings.provider_chain: упал основной → резервный;
- 2 попытки на провайдера с паузой; таймауты на каждый вызов;
- если модель не умеет tool-use (некоторые локальные) — автоматический
  фолбэк: скиллы выполняются заранее, ответ генерируется одним запросом.

OpenAI-совместимые серверы читаются ТОЛЬКО потоком (stream=True): многие прокси
и локальные раннеры отвечают SSE независимо от запроса, и тогда обычный разбор
даёт пустой content. Reasoning-модели пишут размышления в reasoning_content —
их отбрасываем, в ответ идёт только content.

Каждый вызов пишется в `llm_usage`: токены, латентность и оценка стоимости.
Без этого себестоимость платящей клиентки — догадка, а вся юнит-экономика
продукта построена на цифре «≤ $2.5 в месяц».

Формат tools — как у Anthropic: {name, description, input_schema}.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from contextvars import ContextVar
import logging
import time
from dataclasses import dataclass
from collections import deque
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from ..config import settings
from .observability import log_event

#: Аудит AI-001: последний успешный провайдер/модель в рамках текущей задачи.
#: Сервисный слой читает это для proof-конверта, чтобы жалобу на качество можно
#: было связать с конкретным провайдером (fallback иначе был невидим клиенту).
last_call: ContextVar[dict] = ContextVar("oracle_llm_last_call", default={})


log = logging.getLogger("oracle.llm")

ToolExecutor = Callable[[str, dict], Awaitable[str]]

MAX_ITERS = 6
RETRIES = 2
# 35с вместо 180: зависший провайдер не должен держать слот семафора (G6)
# и очередь других запросов ~6 минут — 180с*2 ретрая. Ответ дольше 35с
# пользователь всё равно не дождётся; лучше быстрый отказ и фейловер.
TIMEOUT = 35.0
TOOL_TIMEOUT = 15.0
MAX_TOOL_OUTPUT = 12000


@dataclass
class _WorkflowBudget:
    """Hard limits for one logical agent workflow.

    Provider retries and tool calls share the same deadline and cost ceiling.
    The object is intentionally request-local so concurrent users cannot affect
    each other's budgets.
    """

    timeout: float
    max_tool_calls: int
    max_cost_usd: float
    started: float = 0.0
    tool_calls: int = 0
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        self.started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def remaining(self) -> float:
        return max(0.0, self.timeout - self.elapsed)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def check(self) -> None:
        if self.expired:
            raise TimeoutError("LLM workflow deadline exceeded")
        if self.tool_calls >= self.max_tool_calls:
            raise RuntimeError("LLM tool-call budget exceeded")
        if self.estimated_cost_usd >= self.max_cost_usd:
            raise RuntimeError("LLM cost budget exceeded")

    def reserve_tools(self, count: int) -> None:
        if count < 0 or self.tool_calls + count > self.max_tool_calls:
            raise RuntimeError("LLM tool-call budget exceeded")
        self.tool_calls += count

    def add_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.estimated_cost_usd += estimate_cost(model, prompt_tokens, completion_tokens)
        if self.estimated_cost_usd > self.max_cost_usd:
            raise RuntimeError("LLM cost budget exceeded")


class _RateLimit:
    """Скользящее окно: не больше `rate` вызовов в минуту, глобально.

    Провайдеры режут пачки запросов 429-ми, и на пике (утренняя рассылка,
    одновременные вопросы) без лимита всплеск превращается в веер отказов.
    """

    def __init__(self, rate: int, window_sec: int = 60) -> None:
        self.rate = max(1, rate)
        self.window = window_sec
        self._calls: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            cutoff = now - self.window
            while self._calls and self._calls[0] < cutoff:
                self._calls.popleft()
            if len(self._calls) < self.rate:
                self._calls.append(now)
                return
            # Спим ровно до истечения самого старого вызова, а не поллингом
            # каждые 50 мс: меньше просыпаний, точное окно.
            wait = self._calls[0] + self.window - now
            await asyncio.sleep(max(0.01, wait))


# Ограничители живут на уровне модуля: на 10k пользователей без них всплеск
# открывает сотни одновременных соединений к провайдеру. Доступ к deque из задач
# event loop атомарен, поэтому отдельная блокировка не нужна.
_CONCURRENCY = asyncio.Semaphore(settings.llm_max_concurrency)
_RATE = _RateLimit(settings.llm_rate_per_min)


@asynccontextmanager
async def _llm_slot():
    """Слот одного логического LLM-вызова: сглаживает частоту и ограничивает
    одновременные вызовы. Оборачивает `complete` и `run_agent` целиком."""
    await _RATE.acquire()
    async with _CONCURRENCY:
        yield
# Reasoning-модели тратят часть лимита на размышления: если потолок низкий,
# ответ не успевает родиться. max_tokens — это кап, а не цель, поднять безопасно.
MIN_OPENAI_TOKENS = 2500

#: $ за миллион токенов (вход, выход). Локальные модели считаем бесплатными.
#: Цифры приблизительные и нужны для порядка величины, а не для бухгалтерии —
#: точные суммы всё равно приходят от провайдера в счёте.
PRICING = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.4),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "text-embedding-3-small": (0.02, 0.0),
}


def enabled() -> bool:
    """Есть ли хоть один рабочий провайдер. Иначе продукт идёт в офлайн-режим."""
    return settings.llm_enabled


def _models(provider: str, tier: str) -> str:
    if provider == "anthropic":
        return settings.anthropic_main if tier == "main" else settings.anthropic_lite
    if provider == "openai":
        return settings.openai_main if tier == "main" else settings.openai_lite
    return settings.custom_model_main if tier == "main" else settings.custom_model_lite


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Оценка стоимости вызова в долларах. 0 — модель не из прайса (локальная)."""
    for prefix, (price_in, price_out) in PRICING.items():
        if model.startswith(prefix):
            return (prompt_tokens * price_in + completion_tokens * price_out) / 1e6
    return 0.0


# ──────────────────────────── журнал расходов ─────────────────────────────────

async def record_usage(db, *, provider: str, model: str, purpose: str,
                       prompt_tokens: int = 0, completion_tokens: int = 0,
                       retry_count: int = 0, latency_ms: int = 0,
                       ok: bool = True, tg_id: int | None = None) -> None:
    """Пишет legacy usage и product-level cost evidence без влияния на ответ."""
    if db is None:
        return
    cost_usd = estimate_cost(model, prompt_tokens, completion_tokens)
    try:
        from ..repo import analytics as analytics_repo
        from ..data.session import utcnow
        from . import product_cost
        ctx = product_cost.current()
        now = utcnow()
        await analytics_repo.record_llm_usage(db, {
            "tg_id": tg_id, "provider": provider, "model": model,
            "purpose": purpose, "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens, "cost_usd": cost_usd,
            "latency_ms": latency_ms, "ok": int(ok), "day": now[:10],
            "created_at": now, "sku": ctx.sku,
            "catalog_version": ctx.catalog_version,
            "subscription_code": ctx.tier_code,
            "included_usage": int(ctx.charged_source == "included"),
            "crystal_spend": 0,
            "overage": int(ctx.charged_source == "crystals")})
    except Exception as e:  # noqa: BLE001
        log.debug("расход LLM не записан: %s", e)
    try:
        from . import product_cost
        await product_cost.record_llm(
            db, provider=provider, model=model, purpose=purpose, tg_id=tg_id,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            retry_count=retry_count, latency_ms=latency_ms, cost_usd=cost_usd,
            ok=ok)
    except Exception as e:  # noqa: BLE001
        log.debug("product cost не записан: %s", e)


class _Meter:
    """Считает токены и время одного логического вызова (со всеми итерациями)."""

    def __init__(self) -> None:
        self.prompt = 0
        self.completion = 0
        self.retries = 0
        self.started = time.monotonic()

    def add(self, usage) -> None:
        if not usage:
            return
        self.prompt += (getattr(usage, "input_tokens", None)
                        or getattr(usage, "prompt_tokens", None) or 0)
        self.completion += (getattr(usage, "output_tokens", None)
                            or getattr(usage, "completion_tokens", None) or 0)

    @property
    def ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)


# ──────────────────────────── клиенты провайдеров ─────────────────────────────

def _openai_client(provider: str):
    from openai import AsyncOpenAI
    if provider == "custom":
        return AsyncOpenAI(base_url=settings.custom_base_url,
                           api_key=settings.custom_api_key or "sk-local",
                           timeout=TIMEOUT)
    return AsyncOpenAI(api_key=settings.openai_key, timeout=TIMEOUT)


def _anthropic_client():
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_key, timeout=TIMEOUT)


def _openai_token_limit(model: str, max_tokens: int) -> dict[str, int]:
    """Выбирает token-параметр по семейству OpenAI-модели.

    GPT-5 proxy принимает видимый output budget через `max_completion_tokens`;
    при `max_tokens` vision-ответ может завершиться с пустым content, даже с
    HTTP 200. Legacy OpenAI-compatible и custom модели оставляем на `max_tokens`.
    """
    if str(model).lower().startswith("gpt-5"):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max(max_tokens, MIN_OPENAI_TOKENS)}


def _reasoning_kwargs(model: str) -> dict:
    """Return provider-correct reasoning controls for GPT-5, if configured."""
    if not str(model).lower().startswith("gpt-5"):
        return {}
    effort = str(getattr(settings, "llm_reasoning_effort", "minimal") or "minimal").lower()
    if effort not in {"minimal", "low", "medium", "high"}:
        effort = "minimal"
    return {"extra_body": {"reasoning": {"effort": effort}}}


async def _close_client(client) -> None:
    close = getattr(client, "close", None)
    if not close:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def _stream_chat(client, model: str, messages: list[dict], max_tokens: int,
                       tools: list[dict] | None = None,
                       meter: "_Meter | None" = None) -> tuple[str, list[dict]]:
    """Читает ответ потоком и собирает (текст, вызовы инструментов).

    tool_calls приходят фрагментами: имя в одном чанке, аргументы по кусочкам —
    склеиваем их по index. reasoning_content не попадает в ответ, но если модель
    выдала ТОЛЬКО размышления, честно сообщаем об этом (кончился лимит токенов).
    """
    kwargs: dict = {"model": model, "messages": messages, "stream": True}
    kwargs.update(_openai_token_limit(model, max_tokens))
    kwargs.update(_reasoning_kwargs(model))
    if tools:
        kwargs["tools"] = tools
    # Просим сервер вернуть расход токенов. Многие локальные раннеры и прокси
    # этого параметра не знают и отвечают TypeError или 400 — тогда считаем
    # без учёта: журнал расходов не стоит того, чтобы уронить ответ клиентке.
    try:
        stream = await client.chat.completions.create(
            **kwargs, stream_options={"include_usage": True})
    except Exception as e:  # noqa: BLE001
        if "stream_options" not in str(e) and not isinstance(e, TypeError):
            raise
        log.debug("сервер не знает stream_options — расход не посчитаю: %s", e)
        stream = await client.chat.completions.create(**kwargs)

    parts: list[str] = []
    slots: dict[int, dict] = {}
    reasoned = 0
    async for chunk in stream:
        if meter is not None:
            meter.add(getattr(chunk, "usage", None))
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        if delta.content:
            parts.append(delta.content)
        thought = (getattr(delta, "reasoning_content", None)
                   or getattr(delta, "reasoning", None))
        if thought:
            reasoned += len(thought)
        for tc in (delta.tool_calls or []):
            slot = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
            if tc.id:
                slot["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function.arguments:
                    slot["args"] += tc.function.arguments

    text = "".join(parts).strip()
    calls = [slots[i] for i in sorted(slots) if slots[i]["name"]]
    for n, call in enumerate(calls):          # некоторые серверы не шлют id
        call["id"] = call["id"] or f"call_{n}"
    if not text and not calls:
        raise RuntimeError("модель отдала только размышления без ответа"
                           if reasoned else "пустой ответ модели")
    return text, calls


async def _with_retries(coro_factory, provider: str, what: str,
                       *, meter: _Meter | None = None):
    last = None
    for attempt in range(RETRIES):
        try:
            return await coro_factory()
        except Exception as e:  # noqa: BLE001
            last = e
            if meter is not None:
                meter.retries = max(meter.retries, attempt)
            log.warning("%s/%s попытка %d: %s", provider, what, attempt + 1, e)
            await asyncio.sleep(0.8 * (attempt + 1))
    raise last


# ---------------------------------------------------------------- complete

async def complete(system: str, user_text: str, tier: str = "lite",
                   max_tokens: int = 600, *, purpose: str = "complete",
                   tg_id: int | None = None, db=None) -> str:
    if not settings.provider_chain:
        raise RuntimeError("Все LLM-провайдеры недоступны")
    budget = _WorkflowBudget(
        timeout=max(1.0, settings.llm_workflow_timeout),
        max_tool_calls=1,
        max_cost_usd=max(0.01, settings.llm_max_cost_usd),
    )
    errors = []
    async with _llm_slot():
        for provider_index, provider in enumerate(settings.provider_chain):
            if budget.expired:
                errors.append("workflow: deadline exceeded")
                break
            meter = _Meter()
            model = _models(provider, tier)
            try:
                budget.check()
                text = await asyncio.wait_for(
                    _with_retries(
                        lambda p=provider: _complete_with(p, system, user_text, tier,
                                                          max_tokens, meter),
                        provider, "complete", meter=meter),
                    timeout=budget.remaining,
                )
                budget.add_usage(model, meter.prompt, meter.completion)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{provider}: {e}")
                await record_usage(db, provider=provider, model=model,
                                   purpose=purpose,
                                   prompt_tokens=meter.prompt,
                                   completion_tokens=meter.completion,
                                   retry_count=meter.retries, latency_ms=meter.ms,
                                   ok=False, tg_id=tg_id)
                if budget.expired or "budget exceeded" in str(e).lower():
                    break
                continue
            latency_ms = meter.ms
            await record_usage(db, provider=provider, model=model, purpose=purpose,
                               prompt_tokens=meter.prompt,
                               completion_tokens=meter.completion,
                               retry_count=meter.retries, latency_ms=latency_ms,
                               ok=True, tg_id=tg_id)
            log_event(
                log,
                logging.WARNING if provider_index else logging.INFO,
                "llm_fallback" if provider_index else "llm_request",
                "LLM provider completed",
                provider=provider, purpose=purpose, latency_ms=latency_ms,
            )
            last_call.set({"provider": provider, "model": model})
            return text
    raise RuntimeError("Все LLM-провайдеры недоступны: " + "; ".join(errors))


async def _complete_with(provider, system, user_text, tier, max_tokens,
                         meter: _Meter) -> str:
    if provider == "anthropic":
        client = _anthropic_client()
        try:
            # Система батча (гороскоп на 12 знаков, разбор) не меняется между
            # вызовами — кешируем её, чтобы за повторное вхождение не платить.
            sys_block = [{"type": "text", "text": system,
                          "cache_control": {"type": "ephemeral"}}]
            resp = await client.messages.create(
                model=_models(provider, tier), max_tokens=max_tokens,
                system=sys_block,
                messages=[{"role": "user", "content": user_text}],
            )
            meter.add(getattr(resp, "usage", None))
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        finally:
            await _close_client(client)

    client = _openai_client(provider)
    try:
        text, _ = await _stream_chat(
            client, _models(provider, tier),
            [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
            max_tokens, meter=meter,
        )
        return text
    finally:
        await _close_client(client)


# ---------------------------------------------------------------- run_agent

async def run_agent(system: str, messages: list[dict], tools: list[dict],
                    execute: ToolExecutor, tier: str = "main",
                    max_tokens: int = 1500, *, purpose: str = "answer",
                    tg_id: int | None = None, db=None,
                    max_iters: int | None = None,
                    timeout_s: float | None = None,
                    max_tool_calls: int | None = None) -> str:
    """Агентный цикл: модель вызывает скиллы, мы исполняем, модель отвечает.

    `max_iters` — потолок глубины. Премиум разбирает «план + разбор + совет»
    с несколькими инструментами, поэтому может получать больше итераций, чем
    бесплатный уровень (лимит токенов всё равно стоит на `max_tokens`).
    """
    if not settings.provider_chain:
        raise RuntimeError("Все LLM-провайдеры недоступны")
    iters = max(1, max_iters or MAX_ITERS)
    budget = _WorkflowBudget(
        timeout=max(1.0, timeout_s if timeout_s is not None else settings.llm_workflow_timeout),
        max_tool_calls=max(1, max_tool_calls if max_tool_calls is not None else settings.llm_max_tool_calls),
        max_cost_usd=max(0.01, settings.llm_max_cost_usd),
    )
    errors = []
    async with _llm_slot():
        for provider_index, provider in enumerate(settings.provider_chain):
            if budget.expired:
                errors.append("workflow: deadline exceeded")
                break
            meter = _Meter()
            model = _models(provider, tier)
            try:
                budget.check()
                if provider == "anthropic":
                    text = await asyncio.wait_for(
                        _run_anthropic(system, messages, tools, execute,
                                       tier, max_tokens, meter, iters, budget),
                        timeout=budget.remaining,
                    )
                else:
                    text = await asyncio.wait_for(
                        _run_openai_like(provider, system, messages,
                                         tools, execute, tier, max_tokens,
                                         meter, iters, budget),
                        timeout=budget.remaining,
                    )
            except Exception as e:  # noqa: BLE001
                errors.append(f"{provider}: {e}")
                log.warning("run_agent %s: %s", provider, e)
                await record_usage(db, provider=provider, model=model,
                                   purpose=purpose,
                                   prompt_tokens=meter.prompt,
                                   completion_tokens=meter.completion,
                                   retry_count=meter.retries, latency_ms=meter.ms,
                                   ok=False, tg_id=tg_id)
                if budget.expired or "budget exceeded" in str(e).lower():
                    break
                continue
            latency_ms = meter.ms
            await record_usage(db, provider=provider, model=model, purpose=purpose,
                               prompt_tokens=meter.prompt,
                               completion_tokens=meter.completion,
                               retry_count=meter.retries, latency_ms=latency_ms,
                               ok=True, tg_id=tg_id)
            log_event(
                log,
                logging.WARNING if provider_index else logging.INFO,
                "llm_fallback" if provider_index else "llm_request",
                "LLM provider completed",
                provider=provider, purpose=purpose, latency_ms=latency_ms,
            )
            last_call.set({"provider": provider, "model": model})
            return text
    raise RuntimeError("Все LLM-провайдеры недоступны: " + "; ".join(errors))


async def _gather_tools(execute: ToolExecutor, calls: list[tuple[str, dict]],
                        budget: _WorkflowBudget | None = None) -> list[str]:
    """Исполняет скиллы параллельно с защитой контекста и latency.

    Модель часто просит сразу карту и транзиты; независимые calls выполняются
    параллельно. Каждый результат имеет потолок размера, а зависший или упавший
    инструмент превращается в нейтральный сигнал для модели без внутренних
    exception details.
    """
    async def one(name: str, args: dict) -> str:
        try:
            if budget is not None:
                budget.check()
                timeout = min(TOOL_TIMEOUT, budget.remaining)
            else:
                timeout = TOOL_TIMEOUT
            result = await asyncio.wait_for(execute(name, args), timeout)
            text = str(result or "").strip()
            if len(text) > MAX_TOOL_OUTPUT:
                log.info("скилл %s вернул большой результат (%d символов)", name, len(text))
                return text[:MAX_TOOL_OUTPUT] + "\n[данные сокращены; опирайся на доступную часть]"
            return text
        except asyncio.TimeoutError:
            log.warning("скилл %s превысил лимит %s с", name, TOOL_TIMEOUT)
            return "данные инструмента временно недоступны — продолжи без них или уточни вопрос"
        except Exception:  # noqa: BLE001
            log.exception("скилл %s упал в цикле агента", name)
            return "данные инструмента временно недоступны — не выдумывай их"

    return list(await asyncio.gather(*(one(n, a) for n, a in calls)))


async def _run_anthropic(system, messages, tools, execute, tier, max_tokens,
                         meter: _Meter, max_iters: int = MAX_ITERS,
                         budget: _WorkflowBudget | None = None) -> str:
    client = _anthropic_client()
    try:
        sys_block = [{"type": "text", "text": system,
                      "cache_control": {"type": "ephemeral"}}]
        msgs = [dict(m) for m in messages]
        kept = ""
        for _ in range(max_iters):
            try:
                if budget is not None:
                    budget.check()
                before_prompt, before_completion = meter.prompt, meter.completion
                resp = await _with_retries(
                    lambda: client.messages.create(
                        model=_models("anthropic", tier), max_tokens=max_tokens,
                        system=sys_block, tools=tools, messages=msgs),
                    "anthropic", "agent", meter=meter)
                meter.add(getattr(resp, "usage", None))
                if budget is not None:
                    budget.add_usage(
                        _models("anthropic", tier),
                        meter.prompt - before_prompt,
                        meter.completion - before_completion,
                    )
                piece = "".join(b.text for b in resp.content
                                if b.type == "text").strip()
                if resp.stop_reason != "tool_use":
                    return piece
                if piece:
                    # модель часто пишет предисловие до tool_use — не теряем его,
                    # если потолок итераций исчерпан (иначе уходит в офлайн-фолбэк)
                    kept = piece
                msgs.append({"role": "assistant", "content": resp.content})
                blocks = [b for b in resp.content if b.type == "tool_use"]
                if budget is not None:
                    budget.reserve_tools(len(blocks))
                tool_calls = [(b.name, dict(b.input or {})) for b in blocks]
                outputs = (await _gather_tools(execute, tool_calls, budget)
                           if budget is not None else await _gather_tools(execute, tool_calls))
                msgs.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "content": out}
                    for b, out in zip(blocks, outputs)]})
            except Exception as e:  # noqa: BLE001
                # Бюджет (tool-use/стоимость/дедлайн) — лимит всей workflow, а не
                # сетевой сбой: возвращаем уже собранный текст вместо офлайн-шаблона.
                if ("budget exceeded" in str(e).lower()
                        or "workflow deadline exceeded" in str(e).lower()):
                    log.info("anthropic: исчерпан бюджет workflow — частичный ответ")
                    return kept or _fallback_text()
                raise
        return kept or _fallback_text()
    finally:
        await _close_client(client)


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        },
    } for t in tools]


async def _run_openai_like(provider, system, messages, tools, execute,
                           tier, max_tokens, meter: _Meter,
                           max_iters: int = MAX_ITERS,
                           budget: _WorkflowBudget | None = None) -> str:
    """OpenAI и OpenAI-совместимые серверы (custom/MiniMax).

    Если сервер не поддерживает function calling — падаем в pre-tool режим:
    выполняем базовые скиллы заранее и отвечаем одним запросом.
    """
    client = _openai_client(provider)
    model = _models(provider, tier)
    msgs: list[dict] = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in messages]
    oa_tools = _to_openai_tools(tools)
    kept = ""

    try:
        for _ in range(max_iters):
            if budget is not None:
                budget.check()
            before_prompt, before_completion = meter.prompt, meter.completion
            text, calls = await _with_retries(
                lambda: _stream_chat(client, model, msgs, max_tokens, oa_tools,
                                     meter=meter),
                provider, "agent", meter=meter)
            # Сохраняем собранный текст до add_usage/reserve_tools: бюджет может
            # бросить «cost/tool-call budget exceeded», и без этого частичный
            # ответ терялся бы и уходил в офлайн-шаблон.
            if text:
                kept = text
            if budget is not None:
                budget.add_usage(
                    model,
                    meter.prompt - before_prompt,
                    meter.completion - before_completion,
                )
            if not calls:
                return text
            msgs.append({
                "role": "assistant",
                "content": text,
                "tool_calls": [{
                    "id": c["id"], "type": "function",
                    "function": {"name": c["name"], "arguments": c["args"] or "{}"},
                } for c in calls],
            })
            parsed = []
            for c in calls:
                try:
                    parsed.append((c["name"], json.loads(c["args"] or "{}")))
                except json.JSONDecodeError:
                    parsed.append((c["name"], {}))
            if budget is not None:
                budget.reserve_tools(len(parsed))
            outputs = (await _gather_tools(execute, parsed, budget)
                       if budget is not None else await _gather_tools(execute, parsed))
            for c, out in zip(calls, outputs):
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out})
        return kept or _fallback_text()
    except Exception as e:  # noqa: BLE001
        # Исчерпан бюджет (tool-use/стоимость) или дедлайн всей workflow — это
        # не «провайдер без tool-use» (в pre-tool каскад ломиться нельзя: он
        # снова упрётся в тот же бюджет). Возвращаем уже собранный текст.
        if "budget exceeded" in str(e).lower() or "workflow deadline exceeded" in str(e).lower():
            log.info("%s: исчерпан бюджет workflow — возвращаю частичный ответ", provider)
            return kept or _fallback_text()
        # сервер не умеет tools (400/устаревший API) → pre-tool режим
        if "tool" not in str(e).lower() and "function" not in str(e).lower():
            raise
        log.info("%s без tool-use, включаю pre-tool режим", provider)
        return await _run_pretool(client, model, system, messages, tools,
                                  execute, max_tokens, meter, budget=budget)
    finally:
        await _close_client(client)


async def _run_pretool(client, model, system, messages, tools, execute,
                       max_tokens, meter: _Meter,
                       budget: _WorkflowBudget | None = None) -> str:
    """Выполняет только разрешённые скиллы до single-shot ответа модели.

    Fallback для провайдера без function calling не должен подмешивать чужую
    предметную область специализированному агенту.
    """
    last = messages[-1]["content"] if messages else ""
    lower = str(last).lower()
    allowed = {tool.get("name") for tool in tools or []}
    wanted: list[tuple[str, dict]] = []

    def add(name: str, args: dict | None = None) -> None:
        if name not in allowed or any(existing == name for existing, _ in wanted):
            return
        wanted.append((name, args or {}))

    chart_markers = (
        "наталь", "карта", "планет", "аспект", "дом", "асценд", "знак", "солнц", "placement",
        "birth chart", "natal", "planet", "house", "ascendant", "sign", "sun sign",
    )
    transit_markers = (
        "транзит", "сейчас", "сегодня", "текущее небо", "небо на", "transit",
        "current sky", "today", "right now",
    )
    if any(w in lower for w in chart_markers):
        add("get_chart")
    if any(w in lower for w in transit_markers):
        add("get_transits")
    if any(w in lower for w in ("таро", "карт", "расклад", "будет", "стоит ли", "гада")):
        add("draw_tarot", {"n": 3})
    if any(w in lower for w in ("матриц", "предназнач", "карм")):
        add("get_matrix")
    if any(w in lower for w in ("работ", "карьер", "увол", "переговор", "повышен", "деньг")):
        add("get_career_windows")
    if any(w in lower for w in ("стрижк", "свадьб", "переезд", "поездк", "выбер")):
        add("get_moon_week", {"days": 7})

    if "palm_scanner" in allowed and any(
        w in lower for w in ("ладон", "лини", "холм", "пальц", "снимк", "фото", "чтени")
    ):
        add("palm_scanner")

    if budget is not None:
        budget.reserve_tools(len(wanted))
    context_parts = (await _gather_tools(execute, wanted, budget)
                     if budget is not None else await _gather_tools(execute, wanted))
    system2 = (system + "\n\n[Данные твоих инструментов для этого ответа]\n"
               + "\n\n".join(context_parts))
    msgs = [{"role": "system", "content": system2}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in messages]
    if meter is not None:
        before_prompt, before_completion = meter.prompt, meter.completion
    text, _ = await _stream_chat(client, model, msgs, max_tokens, meter=meter)
    # Обычный цикл учитывает каждый вызов в cost-потолке; pre-tool должен
    # делать то же, но превышение потолка не стоит потери готового ответа.
    if budget is not None and meter is not None:
        try:
            budget.add_usage(model, meter.prompt - before_prompt,
                             meter.completion - before_completion)
        except RuntimeError:
            pass
    return text


def _fallback_text() -> str:
    return "Звёзды сегодня говорят тихо... попробуй задать вопрос ещё раз. 🌙"


# ---------------------------------------------------------------- голос

async def transcribe(file_bytes: bytes, filename: str = "voice.ogg", *,
                     db=None, tg_id: int | None = None,
                     surface: str = "bot") -> str | None:
    """Расшифровка голосового (Whisper, только настоящий OpenAI)."""
    if not settings.openai_key:
        return None
    client = None
    started = time.monotonic()
    ok = False
    text = None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_key, timeout=60)
        resp = await client.audio.transcriptions.create(
            model="whisper-1", file=(filename, file_bytes), language="ru",
        )
        text = (resp.text or "").strip() or None
        ok = bool(text)
        return text
    except Exception:
        return None
    finally:
        if client is not None:
            await _close_client(client)
        try:
            from . import product_cost
            await product_cost.record_event(
                db, event_kind="voice", tg_id=tg_id, sku="voice:transcribe",
                channel=surface if surface in {"bot", "miniapp", "web"} else "system",
                purpose="voice:transcribe", result_category="question",
                status="succeeded" if ok else "failed", units=1,
                duration_ms=int((time.monotonic() - started) * 1000),
                artifact_bytes=len(file_bytes or b""))
        except Exception:
            pass


def tts_enabled() -> bool:
    return bool(settings.openai_key and settings.tts_model)


async def speak(text: str, *, voice: str | None = None, db=None,
                tg_id: int | None = None, surface: str = "system",
                reference_id: str | None = None) -> bytes | None:
    """Текст → голос Оракула (OGG/Opus для голосового сообщения Telegram).

    None означает «озвучки не будет» — тариф с аудио должен деградировать до
    текста, а не отдавать ошибку.
    """
    if not tts_enabled() or not (text or "").strip():
        return None
    client = None
    started = time.monotonic()
    audio = None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_key, timeout=120)
        resp = await client.audio.speech.create(
            model=settings.tts_model,
            voice=voice or settings.tts_voice,
            input=text[:4000],
            response_format="opus",
        )
        audio = resp.read() if hasattr(resp, "read") else bytes(resp.content)
        return audio
    except Exception as e:  # noqa: BLE001
        log.info("озвучка не удалась: %s", e)
        return None
    finally:
        if client is not None:
            await _close_client(client)
        try:
            from . import product_cost
            await product_cost.record_event(
                db, event_kind="voice", tg_id=tg_id, sku="voice:tts",
                channel=surface if surface in {"bot", "miniapp", "web"} else "system",
                purpose="voice:tts", result_category="daily",
                status="succeeded" if audio else "failed", units=1,
                duration_ms=int((time.monotonic() - started) * 1000),
                artifact_bytes=len(audio or b""), reference_id=reference_id)
        except Exception:
            pass


# ---------------------------------------------------------------- vision

async def complete_vision(system: str, user_text: str, image_data_url: str | list[str],
                          tier: str = "main", max_tokens: int = 1400, *,
                          purpose: str = "vision", tg_id: int | None = None,
                          db=None, response_format: dict | None = None,
                          additional_image_data_urls: list[str] | None = None) -> str:
    """Vision completion with provider fallback.

    The primary image and optional bounded focus views are passed only to the
    selected provider and never logged. The caller is responsible for validating
    data URLs and parsing the result.
    """
    if not settings.provider_chain:
        raise RuntimeError("Все LLM-провайдеры недоступны")
    budget = _WorkflowBudget(
        timeout=max(1.0, settings.llm_workflow_timeout),
        max_tool_calls=1,
        max_cost_usd=max(0.01, settings.llm_max_cost_usd),
    )
    errors = []
    image_payload = ([image_data_url] if isinstance(image_data_url, str)
                      else list(image_data_url or []))
    image_payload.extend(additional_image_data_urls or [])
    image_payload = image_payload[:3]
    if not image_payload:
        raise ValueError("vision image set is empty")
    async with _llm_slot():
        for provider_index, provider in enumerate(settings.provider_chain):
            if budget.expired:
                errors.append("workflow: deadline exceeded")
                break
            meter = _Meter()
            model = _models(provider, tier)
            try:
                budget.check()
                text = await asyncio.wait_for(
                    _with_retries(
                        lambda p=provider: _vision_with(p, system, user_text,
                                                         image_payload, tier,
                                                         max_tokens, meter,
                                                         response_format=response_format),
                        provider, "vision", meter=meter),
                    timeout=budget.remaining,
                )
                budget.add_usage(model, meter.prompt, meter.completion)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider}: {exc}")
                await record_usage(db, provider=provider, model=model,
                                   purpose=purpose, prompt_tokens=meter.prompt,
                                   completion_tokens=meter.completion,
                                   retry_count=meter.retries, latency_ms=meter.ms,
                                   ok=False, tg_id=tg_id)
                if budget.expired or "budget exceeded" in str(exc).lower():
                    break
                continue
            await record_usage(db, provider=provider, model=model,
                               purpose=purpose, prompt_tokens=meter.prompt,
                               completion_tokens=meter.completion,
                               latency_ms=meter.ms, ok=True, tg_id=tg_id)
            log_event(log, logging.WARNING if provider_index else logging.INFO,
                      "llm_fallback" if provider_index else "llm_vision_request",
                      "Vision provider completed", provider=provider,
                      purpose=purpose, latency_ms=meter.ms)
            return text
    raise RuntimeError("Все vision-провайдеры недоступны: " + "; ".join(errors))


async def _vision_with(provider: str, system: str, user_text: str,
                       image_data_url: str | list[str], tier: str, max_tokens: int,
                       meter: _Meter, response_format: dict | None = None) -> str:
    image_urls = [image_data_url] if isinstance(image_data_url, str) else list(image_data_url or [])
    image_urls = image_urls[:3]
    if not image_urls:
        raise ValueError("vision image set is empty")
    if provider == "anthropic":
        client = _anthropic_client()
        try:
            content = [{"type": "text", "text": user_text}]
            for data_url in image_urls:
                header, encoded = data_url.split(",", 1)
                media_type = header.split(";", 1)[0].split(":", 1)[1]
                content.append({"type": "image", "source": {"type": "base64",
                               "media_type": media_type, "data": encoded}})
            resp = await client.messages.create(
                model=_models(provider, tier), max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            meter.add(getattr(resp, "usage", None))
            return "".join(block.text for block in resp.content
                           if getattr(block, "type", "") == "text").strip()
        finally:
            await _close_client(client)

    client = _openai_client(provider)
    try:
        model = _models(provider, tier)
        request = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    *[{"type": "image_url", "image_url": {
                        "url": data_url, "detail": "high"}}
                      for data_url in image_urls],
                ]},
            ],
            **_openai_token_limit(model, max_tokens),
        }
        if response_format:
            request["response_format"] = response_format
        request.update(_reasoning_kwargs(model))
        resp = await client.chat.completions.create(**request)
        meter.add(getattr(resp, "usage", None))
        content = resp.choices[0].message.content if resp.choices else ""
        return (content or "").strip()
    finally:
        await _close_client(client)
