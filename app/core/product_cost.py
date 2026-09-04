"""Product-level cost attribution with a strict non-content boundary.

The context contains only server-owned categorical identifiers and numeric evidence:
SKU, catalog version, channel, result category and a non-sensitive reference ID.
No question text, chart payload, memory, image, payment token or model output may be
placed in this context.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class CostContext:
    sku: str | None = None
    catalog_version: str = "legacy"
    channel: str = "system"
    result_category: str | None = None
    reference_id: str | None = None
    order_id: int | None = None
    tier_code: str | None = None
    charged_source: str | None = None
    price_variant: str | None = None


_CURRENT: ContextVar[CostContext] = ContextVar(
    "oracle_product_cost_context", default=CostContext())


def current() -> CostContext:
    return _CURRENT.get()


@contextmanager
def context(*, sku: str | None = None, catalog_version: str = "legacy",
            channel: str = "system", result_category: str | None = None,
            reference_id: str | None = None,
            order_id: int | None = None, tier_code: str | None = None,
            charged_source: str | None = None, price_variant: str | None = None) -> Iterator[CostContext]:
    """Set safe product attribution for all nested LLM calls."""
    value = CostContext(
        sku=sku,
        catalog_version=catalog_version or "legacy",
        channel=channel or "system",
        result_category=result_category,
        reference_id=reference_id,
        order_id=order_id,
        tier_code=tier_code,
        charged_source=charged_source,
        price_variant=price_variant,
    )
    token = _CURRENT.set(value)
    try:
        yield value
    finally:
        _CURRENT.reset(token)


def inferred(*, purpose: str) -> CostContext:
    """Provide a safe fallback when an older call site has no explicit context."""
    purpose = (purpose or "unknown").strip()[:96]
    if purpose.startswith("answer:"):
        agent = purpose.split(":", 1)[1] or "unknown"
        return CostContext(sku=f"chat:{agent}", result_category="question")
    if purpose.startswith("report:"):
        kind = purpose.split(":", 1)[1] or "unknown"
        return CostContext(sku=f"report:{kind}", result_category="report")
    if purpose.startswith("palm:"):
        return CostContext(sku="palm:vision", result_category="palm")
    if purpose.startswith("memory"):
        return CostContext(sku="memory:maintenance", result_category="question")
    if purpose == "horoscope":
        return CostContext(sku="horoscope:daily", result_category="daily")
    return CostContext(sku=f"llm:{purpose or 'unknown'}")


async def record_llm(db, *, provider: str, model: str, purpose: str,
                     tg_id: int | None, prompt_tokens: int, completion_tokens: int,
                     retry_count: int, latency_ms: int, cost_usd: float,
                     ok: bool) -> None:
    """Persist an LLM cost event; telemetry failure must never break a response."""
    if db is None:
        return
    from ..repo import analytics

    ctx = current()
    if ctx.sku is None:
        ctx = inferred(purpose=purpose)
    try:
        await analytics.record_product_cost_event(
            db,
            event_kind="llm",
            tg_id=tg_id,
            sku=ctx.sku,
            catalog_version=ctx.catalog_version,
            channel=ctx.channel,
            purpose=purpose,
            provider=provider,
            model=model,
            result_category=ctx.result_category,
            status="succeeded" if ok else "failed",
            cost_usd=cost_usd, price_variant=ctx.price_variant,
            units=1,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            retry_count=retry_count,
            latency_ms=latency_ms,
            reference_id=ctx.reference_id,
            order_id=ctx.order_id,
        )
    except Exception:
        # Product telemetry is best-effort and must not turn a paid answer into 500.
        return


async def record_event(db, *, event_kind: str, tg_id: int | None = None,
                       sku: str | None, channel: str = "system",
                       catalog_version: str = "legacy",
                       purpose: str | None = None,
                       result_category: str | None = None,
                       status: str = "succeeded", units: int = 1,
                       input_tokens: int = 0, output_tokens: int = 0,
                       retry_count: int = 0, latency_ms: int = 0,
                       duration_ms: int = 0, artifact_bytes: int = 0,
                       cost_usd: float | None = None,
                       reference_id: str | None = None,
                       order_id: int | None = None,
                       reason: str | None = None,
                       price_variant: str | None = None) -> None:
    """Persist a server-owned non-content cost/delivery event."""
    if db is None:
        return
    from ..repo import analytics

    try:
        await analytics.record_product_cost_event(
            db, event_kind=event_kind, tg_id=tg_id, sku=sku,
            catalog_version=catalog_version, channel=channel,
            purpose=purpose, result_category=result_category, status=status,
            units=units, input_tokens=input_tokens, output_tokens=output_tokens,
            retry_count=retry_count, latency_ms=latency_ms,
            duration_ms=duration_ms, artifact_bytes=artifact_bytes,
            cost_usd=cost_usd, reference_id=reference_id, order_id=order_id,
            reason=reason, price_variant=price_variant,
        )
    except Exception:
        return
