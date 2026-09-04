#!/usr/bin/env python3
"""Seed one disposable development user for local visual/E2E checks."""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import astro, tarot  # noqa: E402
from app.data.session import connect  # noqa: E402
from app.repo import dialog, readings, users  # noqa: E402


async def seed() -> None:
    # The visual-quality workflow owns a disposable PostgreSQL database.  Keep
    # this helper self-contained so it cannot accidentally run against an
    # uninitialised schema when called before the API quality job's migration.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
    )
    db = await connect(seed=False)
    try:
        chart = await astro.compute_chart_async(
            "1990-06-21", "14:30", "Казань", 55.79, 49.12,
            "Europe/Moscow", time_known=True)
        for tg_id, lang in ((10001, "ru"), (10002, "en")):
            await users.ensure(db, tg_id, "Synthetic Oracle", "synthetic_oracle", lang=lang)
            await users.update(
                db, tg_id, onboarded=1, birth_date="1990-06-21",
                birth_time="14:30", birth_time_known=1, birth_city="Казань",
                birth_lat=55.79, birth_lon=49.12, tz="Europe/Moscow",
                chart_json=json.dumps(chart, ensure_ascii=False), memory_enabled=1,
                sub_level="vip",
                sub_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
            await dialog.save_memory(
                db, tg_id,
                "Любит тихие синтетические утра" if lang == "ru"
                else "Loves quiet synthetic mornings",
                kind="preference")
            await dialog.add_diary(db, tg_id, "Synthetic diary entry", mood="calm")
            cards = tarot.draw(3, seed="visual-baseline")
            await readings.save_reading(
                db, tg_id, "three", "Synthetic visual question", cards,
                "Synthetic reading answer")
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(seed())
    print("seeded synthetic visual users 10001 (ru), 10002 (en) in DATABASE_URL")
