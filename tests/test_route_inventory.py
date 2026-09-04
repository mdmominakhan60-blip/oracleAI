"""P1-009: каждая /api-ручка имеет auth или письменную публичную причину."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_route_inventory import inventory_rows, route_violations  # noqa: E402


def test_every_api_route_has_auth_or_documented_reason():
    violations = route_violations()
    assert not violations, "маршруты без auth: " + "; ".join(violations)


def test_inventory_covers_all_registered_routers():
    rows = inventory_rows()
    assert len(rows) >= 60  # инвентарь не выродился в пустой
    assert any(r["route"].startswith("POST /api/webhooks/") for r in rows)
    assert all(r["auth"] for r in rows)
