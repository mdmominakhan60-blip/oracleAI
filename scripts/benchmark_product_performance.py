#!/usr/bin/env python3
"""Measure representative local product operations with synthetic inputs."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import astro, memory, palm_lines, tarot  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import io  # noqa: E402
from app.data.session import connect  # noqa: E402
from app.pdfgen import builder  # noqa: E402
from app.repo import users  # noqa: E402


async def timed_async(fn, repeats: int = 3) -> list[float]:
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        await fn()
        values.append((time.perf_counter() - started) * 1000)
    return values


def timed_sync(fn, repeats: int = 5) -> list[float]:
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        values.append((time.perf_counter() - started) * 1000)
    return values


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def summary(values: list[float]) -> dict:
    if not values:
        raise ValueError("benchmark requires at least one sample")
    sample_size = len(values)
    return {
        "runs": sample_size,
        "p50_ms": round(_percentile(values, 0.50), 2),
        "p95_ms": round(_percentile(values, 0.95), 2),
        "max_ms": round(max(values), 2),
        "percentiles_valid_for_slo": sample_size >= 20,
        "percentile_note": ("p95/p99 are directional only below n=20"
                            if sample_size < 20 else "sample size supports directional SLO comparison"),
    }


async def main() -> int:
    original_geo = builder.geo.resolve_city_async
    original_llm = builder.llm.enabled

    async def fake_geo(_city: str):
        return 55.79, 49.12, "Europe/Moscow"

    builder.geo.resolve_city_async = fake_geo
    builder.llm.enabled = lambda: False
    db = await connect(seed=False)
    try:
        user = await users.ensure(db, 15001, "Synthetic performance user")
        for i in range(20):
            await memory.remember(db, user["tg_id"], f"Synthetic preference number {i}")

        async def memory_op():
            await memory.recall(db, user["tg_id"], "Synthetic preference", limit=8)

        async def pdf_op():
            await builder.generate(
                None,
                builder.Order(name="Synthetic", birth_date="1990-06-21", birth_time="14:30", birth_city="Synthetic City"),
                concurrency=1,
            )

        image = Image.new("RGB", (640, 640), (185, 135, 105))
        draw = ImageDraw.Draw(image)
        draw.ellipse((100, 40, 540, 620), fill=(220, 170, 140))
        draw.arc((160, 190, 500, 560), 75, 290, fill=(80, 40, 30), width=7)
        draw.arc((120, 180, 530, 420), 185, 350, fill=(80, 40, 30), width=6)
        palm_buffer = io.BytesIO()
        image.save(palm_buffer, format="JPEG", quality=92)
        palm_bytes = palm_buffer.getvalue()
        palm_status = {"status": "unavailable"}

        def palm_line_op():
            nonlocal palm_status
            palm_status = palm_lines.analyze(palm_bytes)

        metrics = {
            "chart_compute": summary(timed_sync(lambda: astro.compute_chart(
                "1990-06-21", "14:30", "Казань", 55.79, 49.12, "Europe/Moscow"), repeats=5)),
            "tarot_draw": summary(timed_sync(lambda: tarot.reading_ledger(
                tarot.draw(5, seed="synthetic-performance"), "three"), repeats=20)),
            "memory_recall": summary(await timed_async(memory_op, repeats=5)),
            "pdf_html_generation": summary(await timed_async(pdf_op, repeats=20)),
            "palm_line_segmentation": summary(timed_sync(palm_line_op, repeats=3)),
        }
    finally:
        await db.close()
        builder.geo.resolve_city_async = original_geo
        builder.llm.enabled = original_llm

    result = {
        "synthetic": True,
        "metrics": metrics,
        "palm_line_engine": {
            "status": palm_status.get("status"),
            "model": palm_status.get("model"),
            "raw_mask_stored": palm_status.get("raw_mask_stored", False),
        },
        "pass": all(item["runs"] > 0 for item in metrics.values()),
        "note": "Local directional baseline only; production SLOs require staging traffic and provider instrumentation.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
