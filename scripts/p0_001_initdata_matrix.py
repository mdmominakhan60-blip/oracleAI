#!/usr/bin/env python3
"""P0-001: матрица подписей Telegram initData + owner isolation (staging).

Гейт release-а P0-001 требует проверить, что бот/Mini App принимают ТОЛЬКО
подлинную подпись Telegram и отвергают tampered/expired/missing/replay, а
данные пользователя A недоступны пользователю B.

Скрипт обращается к РЕАЛЬНОму staging-приложению (тот же код `app/api/security.py`
и та же схема HMAC WebAppData, что в проде) и печатает вердикт pass/fail по
каждому кейсу. Никаких секретов не выводит — только статусы и tg_id.

Запуск (внутри контейнера staging-api, где есть BOT_TOKEN):
    python scripts/p0_001_initdata_matrix.py \
        --base http://localhost:8080 --tg-a 900000001 --tg-b 900000002 \
        --mem-b <id памяти B>

Кейсы подписи (against GET /api/me):
  S1 valid      — корректная подпись, свежий auth_date            → 200
  S2 expired    — auth_date старше MAX_AGE_SECONDS                → 401
  S3 future     — auth_date в будущем > MAX_FUTURE_SECONDS        → 401
  S4 tampered   — поле user.id изменено ПОСЛЕ подписи             → 401
  S5 missing    — параметр hash отсутствует                       → 401
  S6 badhash    — hash не совпадает (подпись чужого бота)         → 401
  S7 dupkey     — дублирующийся ключ user= (ambiguous)            → 401
  S8 replay     — повторный минт POST /auth/session с той же подписью  → 401
  S9 token      — минтенный X-Session-Token аутентифицирует GET /api/me → 200

Owner isolation:
  O1 A читает только себя (GET /api/me → tg_id A)
  O2 A не видит память B (GET /api/memories с подписью A не отдаёт строку B)
  O3 A не может удалить память B (DELETE /api/memories/<mem_b> с подписью A
     не стирает строку — проверяется по факту наличия)
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import urlencode

import httpx

MAX_AGE_SECONDS = 24 * 3600
MAX_FUTURE_SECONDS = 10 * 60


def _secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign_init_data(bot_token: str, fields: dict[str, str]) -> str:
    """Собирает initData c корректным hash по схеме Telegram."""
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    h = hmac.new(_secret(bot_token), check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": h})


def user_json(tg_id: int) -> str:
    return json.dumps({"id": tg_id, "first_name": "Test", "username": f"u{tg_id}"})


def build_valid(bot_token: str, tg_id: int, auth_date: int) -> str:
    return sign_init_data(bot_token, {
        "auth_date": str(auth_date),
        "query_id": "AAH-test",
        "user": user_json(tg_id),
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--tg-a", type=int, required=True)
    ap.add_argument("--tg-b", type=int, required=True)
    ap.add_argument("--mem-b", type=int, default=0,
                    help="id строки memories пользователя B (для O2/O3)")
    ap.add_argument("--bot-token", default=os.environ.get("BOT_TOKEN", ""))
    args = ap.parse_args()

    if not args.bot_token:
        print("ERROR: BOT_TOKEN не задан (запускать внутри staging-api)", file=sys.stderr)
        return 2

    tok = args.bot_token
    now = int(time.time())
    client = httpx.Client(base_url=args.base, timeout=10.0)
    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str):
        results.append((name, cond, detail))

    # ── S1 valid ────────────────────────────────────────────────────────────
    r = client.get("/api/me", headers={"x-init-data": build_valid(tok, args.tg_a, now)})
    ok = r.status_code == 200 and r.json().get("tg_id") == args.tg_a
    check("S1_valid", ok, f"HTTP {r.status_code}")

    # ── S2 expired (за рамками 24ч) ─────────────────────────────────────────
    expired = build_valid(tok, args.tg_a, now - (MAX_AGE_SECONDS + 3600))
    r = client.get("/api/me", headers={"x-init-data": expired})
    check("S2_expired", r.status_code == 401, f"HTTP {r.status_code}")

    # ── S3 future (за рамками +10мин) ───────────────────────────────────────
    future = build_valid(tok, args.tg_a, now + MAX_FUTURE_SECONDS + 120)
    r = client.get("/api/me", headers={"x-init-data": future})
    check("S3_future", r.status_code == 401, f"HTTP {r.status_code}")

    # ── S4 tampered: hash посчитан для user=A, но отправлен user=B ──────────
    # (подмена ПОСЛЕ подписи; наивный replace в url-кодированной строке не
    # работает — кавычек там уже нет, поэтому собираем честно)
    orig_fields = {"auth_date": str(now), "query_id": "AAH-test",
                   "user": user_json(args.tg_a)}
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(orig_fields.items()))
    orig_hash = hmac.new(_secret(tok), check_string.encode(),
                         hashlib.sha256).hexdigest()
    tampered_fields = dict(orig_fields)
    tampered_fields["user"] = user_json(999999999)
    tampered = urlencode({**tampered_fields, "hash": orig_hash})
    r = client.get("/api/me", headers={"x-init-data": tampered})
    got_tg = r.json().get("tg_id") if r.status_code == 200 else None
    check("S4_tampered", r.status_code == 401,
          f"HTTP {r.status_code}" + (f" tg_id={got_tg} — ПОДМЕНА ПРИНЯТА!" if got_tg else ""))

    # ── S5 missing signature ────────────────────────────────────────────────
    no_hash = urlencode({"auth_date": str(now), "user": user_json(args.tg_a)})
    r = client.get("/api/me", headers={"x-init-data": no_hash})
    check("S5_missing_sig", r.status_code == 401, f"HTTP {r.status_code}")

    # ── S6 bad hash (подпись, вычисленная чужим секретом) ────────────────────
    fields = {"auth_date": str(now), "user": user_json(args.tg_a)}
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    bad = hmac.new(_secret("wrong-bot-token"), check_string.encode(),
                   hashlib.sha256).hexdigest()
    r = client.get("/api/me", headers={"x-init-data": urlencode({**fields, "hash": bad})})
    check("S6_badhash", r.status_code == 401, f"HTTP {r.status_code}")

    # ── S7 duplicate key ────────────────────────────────────────────────────
    from urllib.parse import quote as _quote
    dup = build_valid(tok, args.tg_a, now)
    dup = dup + "&user=" + _quote(user_json(args.tg_a), safe="")
    r = client.get("/api/me", headers={"x-init-data": dup})
    check("S7_dupkey", r.status_code == 401, f"HTTP {r.status_code}")

    # ── S8 replay: повторный минт POST /auth/session с той же подписью ───────
    # Новая семантика (BUS-200): initData потребляется ОДИН раз — на минте
    # session-токена; повторный минт → 401. Read-ручки продолжают принимать
    # initData напрямую (back-compat), это не расширяет полномочия.
    replay = build_valid(tok, args.tg_a, now)
    r1 = client.post("/api/auth/session", json={"init_data": replay})
    minted_token = r1.json().get("session_token") if r1.status_code == 200 else None
    r = client.post("/api/auth/session", json={"init_data": replay})
    check("S8_replay_rejected",
          r1.status_code == 200 and r.status_code == 401,
          f"первый минт HTTP {r1.status_code}, повтор HTTP {r.status_code} "
          f"(повтор 200 = replay принят — нет защиты)")

    # ── S9 session-token: минтенный токен аутентифицирует без initData ──────
    if minted_token:
        r = client.get("/api/me", headers={"X-Session-Token": minted_token})
        check("S9_session_token_works",
              r.status_code == 200 and r.json().get("tg_id") == args.tg_a,
              f"HTTP {r.status_code}")
    else:
        check("S9_session_token_works", False, "минт не состоялся — S8 провален")

    # ── O1 A читает только себя ──────────────────────────────────────────────
    r = client.get("/api/me", headers={"x-init-data": build_valid(tok, args.tg_a, now)})
    check("O1_self_only", r.status_code == 200 and r.json().get("tg_id") == args.tg_a,
          f"HTTP {r.status_code}")

    if args.mem_b:
        # ── O2 память B не видна A ───────────────────────────────────────────
        ra = client.get("/api/memories",
                        headers={"x-init-data": build_valid(tok, args.tg_a, now)})
        ids_a = {m.get("id") for m in ra.json()} if ra.status_code == 200 else set()
        check("O2_no_read_B", args.mem_b not in ids_a,
              f"HTTP {ra.status_code}, ids={sorted(ids_a)}")

        # ── O3 A не удаляет память B ─────────────────────────────────────────
        rb = client.get("/api/memories",
                        headers={"x-init-data": build_valid(tok, args.tg_b, now)})
        before = {m.get("id") for m in rb.json()} if rb.status_code == 200 else set()
        client.delete(f"/api/memories/{args.mem_b}",
                      headers={"x-init-data": build_valid(tok, args.tg_a, now)})
        rb2 = client.get("/api/memories",
                         headers={"x-init-data": build_valid(tok, args.tg_b, now)})
        after = {m.get("id") for m in rb2.json()} if rb2.status_code == 200 else set()
        check("O3_no_delete_B", args.mem_b in after and args.mem_b not in (before - after),
              f"before={sorted(before)} after={sorted(after)}")

    # ── отчёт ────────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in results if ok)
    print("\n=== P0-001 initData matrix ===")
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:20s} {detail}")
    print(f"\nИтог: {passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
