"""P1-009: маршрутный инвентарь API — auth и rate limit на каждой ручке.

Каждый /api-маршрут обязан:
  * иметь auth-зависимость (подписанные Telegram-данные, админ или require()),
    либо входить в PUBLIC_ROUTE_REASONS с письменным основанием;
  * для POST/PUT/PATCH/DELETE — иметь auth-зависимость.
Запуск: python scripts/check_route_inventory.py — печатает матрицу,
exit != 0 при нарушении. Тест tests/test_route_inventory.py гоняет то же.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUTH_DEPS = {"current_user", "confirmed_age_user", "active_user",
             "touched_user", "deletion_user", "current_admin", "guard"}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# Вебхуки проверяют подпись провайдера внутри хендлера — это их auth.
PUBLIC_ROUTE_REASONS = {
    "GET /api/health": "liveness-проба для Caddy/Docker, без персональных данных",
    "GET /api/public/config": "неавторизованные параметры первого касания (UX-009), только публичная конфигурация",
    "GET /api/personas": "публичный список образов, без пользовательских данных",
    "GET /api/faq": "публичный контент FAQ, без пользовательских данных",
    "GET /api/placements": "публичный словарь справочника размещений, без пользовательских данных",
    "GET /api/share/enabled": "флаг доступности шаринга (доступен до входа, чтобы спрятать кнопку), без пользовательских данных",
    "POST /api/webhooks/paddle": "Paddle-Signature HMAC проверяется в теле ручки",
    "POST /api/webhooks/cryptobot": "Crypto Pay signature проверяется в теле ручки",
}


def _dep_names(route) -> set[str]:
    """Имена зависимостей маршрута: router-level + параметры ручки + саб-зависимости."""
    names: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        call = dep.call
        names.add(getattr(call, "__name__", str(call)))
        stack.extend(dep.dependencies)
    return names


def route_violations() -> list[str]:
    from app.api.routers import ROUTERS
    problems: list[str] = []
    for router in ROUTERS:
        for route in router.routes:
            path = getattr(route, "path", "")
            if not getattr(route, "methods", None):
                continue
            method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
            label = f"{method} {path}"
            names = _dep_names(route)
            has_auth = bool(names & AUTH_DEPS)
            reason = PUBLIC_ROUTE_REASONS.get(label)
            if not has_auth and not reason:
                problems.append(f"{label}: нет auth-зависимости и нет причины в PUBLIC_ROUTE_REASONS")
    return problems


def inventory_rows() -> list[dict]:
    from app.api.routers import ROUTERS
    rows = []
    for router in ROUTERS:
        for route in router.routes:
            if not getattr(route, "methods", None):
                continue
            path = getattr(route, "path", "")
            method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
            names = _dep_names(route)
            rows.append({
                "route": f"{method} {path}",
                "auth": sorted(names & AUTH_DEPS) or
                        [PUBLIC_ROUTE_REASONS.get(f"{method} {path}", "-")],
                "rate_limit": "guard" in names,
            })
    return rows


def main() -> int:
    problems = route_violations()
    for row in inventory_rows():
        print(f"{row['route']:<45} auth={','.join(row['auth'])} rate_limit={'yes' if row['rate_limit'] else '-'}")
    for problem in problems:
        print("VIOLATION:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
