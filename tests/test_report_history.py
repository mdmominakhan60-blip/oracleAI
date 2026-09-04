"""Report history must preserve prior deterministic/report snapshots."""
from __future__ import annotations

import pytest

from app.repo import readings


@pytest.mark.asyncio
async def test_report_versions_are_append_only(db):
    first_id = await readings.save_report(
        db, 1001, "natal", "Первый отчёт", "old body", period=None,
        meta={"snapshot": "old"})
    second_id = await readings.save_report(
        db, 1001, "natal", "Второй отчёт", "new body", period=None,
        meta={"snapshot": "new"})

    assert second_id > first_id
    row = await readings.get_report(db, 1001, "natal")
    assert row["id"] == second_id
    assert row["body"] == "new body"

    cur = await db.execute(
        "SELECT id, body, meta_json FROM reports "
        "WHERE tg_id=? AND kind=? ORDER BY id", (1001, "natal"))
    rows = await cur.fetchall()
    assert [(row["id"], row["body"]) for row in rows] == [
        (first_id, "old body"), (second_id, "new body")
    ]
    assert '"snapshot": "old"' in rows[0]["meta_json"]

    assert await readings.get_report_by_id(db, 1001, "natal", first_id)
    assert await readings.get_report_by_id(db, 1002, "natal", first_id) is None
    assert await readings.get_report_by_id(db, 1001, "matrix", first_id) is None
