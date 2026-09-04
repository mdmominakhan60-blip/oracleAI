from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.session import connect  # noqa: E402


async def main() -> None:
    if os.getenv("APP_ENV", "").lower() not in {"dev", "test"}:
        raise RuntimeError("startup smoke requires APP_ENV=dev or APP_ENV=test")
    db = await connect(seed=False)
    try:
        from app.data.seed import _seed_monetization_v2

        await _seed_monetization_v2(db)
        await db.commit()
        for table in (
            "catalog_versions",
            "price_book_items",
            "subscription_state",
            "monetization_usage",
            "crystal_lots",
            "monetization_assignments",
        ):
            cur = await db.execute(f"SELECT COUNT(*) FROM {table}")
            print(table, (await cur.fetchone())[0])
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
