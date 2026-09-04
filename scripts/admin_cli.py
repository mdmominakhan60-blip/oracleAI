"""Удалённое управление OracleAI CRM через HTTP API.

Работает с любого ПК: ходит в admin API по `X-Admin-Key` (см. ADMIN_API_KEY в
.env сервера), ничего локального (БД/бот) не трогает.

    export ORA_API="https://your-host" ORA_KEY="<ADMIN_API_KEY>"

    python -m scripts.admin_cli dashboard
    python -m scripts.admin_cli users --q "Аня" --segment active
    python -m scripts.admin_cli user 12345678
    python -m scripts.admin_cli grant 12345678 --kind plan --days 30 --reason "компенсация"
    python -m scripts.admin_cli status 12345678 --status blocked
    python -m scripts.admin_cli message 12345678 --text "Здравствуйте!"
    python -m scripts.admin_cli broadcasts
    python -m scripts.admin_cli analytics --days 90   # LTV/KPI/визиты для LLM
    python -m scripts.admin_cli admins
    python -m scripts.admin_cli orders --limit 20

Настройки берутся из env ORA_API/ORA_KEY или флагов --api/--key.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_API = os.getenv("ORA_API", "http://localhost:8000")


class AdminCLI:
    def __init__(self, base: str, key: str):
        self.base = base.rstrip("/")
        self.key = key

    def _headers(self) -> dict:
        return {"X-Admin-Key": self.key, "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base}/api/admin{path}"

    def _request(self, method: str, path: str, body: dict | None = None,
                 params: dict | None = None) -> dict:
        url = self._url(path)
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read() or b"{}").get("detail", "")
            except Exception:  # noqa: BLE001
                detail = e.read().decode(errors="replace")[:300]
            sys.stderr.write(f"HTTP {e.code}: {detail}\n")
            raise SystemExit(1)

    # ── команды ────────────────────────────────────────────────────────────
    def cmd_dashboard(self) -> None:
        print(json.dumps(self._request("GET", "/dashboard"),
                         ensure_ascii=False, indent=2))

    def cmd_users(self, q: str, segment: str, limit: int) -> None:
        data = self._request("GET", "/users", params={
            "q": q, "segment": segment, "limit": limit})
        print(f"всего: {data.get('total')}  сегменты: {data.get('segments')}")
        for u in data.get("items", []):
            tags = ",".join(u.get("tags") or [])
            print(f"[{u['tg_id']}] {u.get('name','')} | {u.get('status')} | "
                  f"подписка:{'да' if u.get('sub_active') else 'нет'}"
                  f"{(' | '+tags) if tags else ''}")

    def cmd_user(self, tg_id: int) -> None:
        print(json.dumps(self._request("GET", f"/users/{tg_id}"),
                         ensure_ascii=False, indent=2))

    def cmd_grant(self, tg_id: int, kind: str, code: str | None,
                  qty: int, days: int | None, reason: str) -> None:
        body = {"kind": kind, "qty": qty, "reason": reason}
        if code:
            body["code"] = code
        if days:
            body["days"] = days
        print(json.dumps(self._request("POST", f"/users/{tg_id}/grant", body),
                         ensure_ascii=False, indent=2))

    def cmd_status(self, tg_id: int, status: str) -> None:
        print(json.dumps(self._request("POST", f"/users/{tg_id}/status",
                                       {"status": status}), ensure_ascii=False))

    def cmd_message(self, tg_id: int, text: str) -> None:
        print(json.dumps(self._request("POST", f"/users/{tg_id}/message",
                                       {"text": text}), ensure_ascii=False))

    def cmd_note(self, tg_id: int, text: str) -> None:
        print(json.dumps(self._request("POST", f"/users/{tg_id}/notes",
                                       {"text": text}), ensure_ascii=False))

    def cmd_admins(self) -> None:
        print(json.dumps(self._request("GET", "/admins"),
                         ensure_ascii=False, indent=2))

    def cmd_orders(self, limit: int) -> None:
        print(json.dumps(self._request("GET", "/orders",
                                       params={"limit": limit}),
                         ensure_ascii=False, indent=2))

    def cmd_broadcasts(self) -> None:
        print(json.dumps(self._request("GET", "/broadcasts"),
                         ensure_ascii=False, indent=2))

    def cmd_settings(self) -> None:
        print(json.dumps(self._request("GET", "/settings"),
                         ensure_ascii=False, indent=2))

    def cmd_analytics(self, days: int) -> None:
        print(json.dumps(self._request("GET", "/analytics",
                                       params={"days": days}),
                         ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Удалённое управление OracleAI CRM")
    ap.add_argument("--api", default=DEFAULT_API, help="базовый URL сервера")
    ap.add_argument("--key", default=os.getenv("ORA_KEY", ""),
                    help="ADMIN_API_KEY сервера")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dashboard", help="сводка за сегодня")
    p = sub.add_parser("users", help="поиск клиенток")
    p.add_argument("--q", default="")
    p.add_argument("--segment", default="all")
    p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("user", help="карточка клиентки")
    p.add_argument("tg_id", type=int)
    p = sub.add_parser("grant", help="выдать доступ/кристаллы")
    p.add_argument("tg_id", type=int)
    p.add_argument("--kind", required=True, help="plan|crystals|spread|report|question")
    p.add_argument("--code", default=None)
    p.add_argument("--qty", type=int, default=1)
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--reason", default="")
    p = sub.add_parser("status", help="active|blocked")
    p.add_argument("tg_id", type=int)
    p.add_argument("--status", required=True)
    p = sub.add_parser("message", help="личное сообщение клиентке")
    p.add_argument("tg_id", type=int)
    p.add_argument("--text", required=True)
    p = sub.add_parser("note", help="заметка в карточку")
    p.add_argument("tg_id", type=int)
    p.add_argument("--text", required=True)
    p = sub.add_parser("admins", help="список администраторов")
    p = sub.add_parser("orders", help="последние заказы")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("broadcasts", help="рассылки")
    p = sub.add_parser("analytics", help="LTV/KPI/визиты для LLM")
    p.add_argument("--days", type=int, default=30)
    p = sub.add_parser("settings", help="настройки бренда")
    return ap


def main() -> None:
    args = build_parser().parse_args()
    if not args.key:
        sys.exit("задай ключ: --key или env ORA_KEY (ADMIN_API_KEY сервера)")
    cli = AdminCLI(args.api, args.key)
    name = args.cmd.replace("-", "_")
    dispatch = {
        "dashboard": lambda: cli.cmd_dashboard(),
        "users": lambda: cli.cmd_users(args.q, args.segment, args.limit),
        "user": lambda: cli.cmd_user(args.tg_id),
        "grant": lambda: cli.cmd_grant(args.tg_id, args.kind, args.code,
                                       args.qty, args.days, args.reason),
        "status": lambda: cli.cmd_status(args.tg_id, args.status),
        "message": lambda: cli.cmd_message(args.tg_id, args.text),
        "note": lambda: cli.cmd_note(args.tg_id, args.text),
        "admins": lambda: cli.cmd_admins(),
        "orders": lambda: cli.cmd_orders(args.limit),
        "broadcasts": lambda: cli.cmd_broadcasts(),
        "analytics": lambda: cli.cmd_analytics(args.days),
        "settings": lambda: cli.cmd_settings(),
    }
    dispatch[name]()


if __name__ == "__main__":
    main()
