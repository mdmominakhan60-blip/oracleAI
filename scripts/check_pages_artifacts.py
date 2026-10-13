#!/usr/bin/env python3
"""Проверка артефактов weboracleai.pages.dev (BUS-1515 / BUS-1519).

Цель: ловить SPA-фолбэк Cloudflare Pages на служебных file-маршрутах.
Без этого /indexnow.txt и /c32b...txt отдают index.html (text/html, 23072 байта),
и GSC не верифицирует домен, а IndexNow не принимает ключ.

Проверяемый инвариант: каждый служебный route отдаёт ожидаемый content-type
и ожидаемый размер (или, для динамичных — только content-type).

Использование:
    python3 scripts/check_pages_artifacts.py            # exit 0 = healthy
    python3 scripts/check_pages_artifacts.py --json      # machine-readable report
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

HOST = "https://weboracleai.pages.dev"

# route -> (expected content-type substring, expected size or None)
CHECKS = {
    "/indexnow.txt": ("text/plain", 32),
    "/c32b0191d6224b729f90051996820689.txt": ("text/plain", 32),
    "/robots.txt": ("text/plain", 75),
    "/sitemap.xml": ("application/xml", None),
    "/404.html": ("text/html", None),  # должен быть real 404-страницей, а не index.html
}


def probe(path: str) -> dict:
    # Cloudflare bot-fight: без browser UA urllib получает 403.
    req = urllib.request.Request(
        HOST + path,
        method="GET",
        headers={"User-Agent": "oracleAI-pages-healthcheck/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
            return {
                "route": path,
                "status": resp.status,
                "content_type": resp.headers.get("Content-Type", ""),
                "size": len(body),
                "error": None,
            }
    except Exception as exc:  # noqa: BLE001
        return {"route": path, "status": None, "content_type": "", "size": 0, "error": str(exc)}


def evaluate(route: str, got: dict, expected_ct: str, expected_size: int | None) -> list[str]:
    problems: list[str] = []
    if got["error"]:
        problems.append(f"request error: {got['error']}")
        return problems
    ct = got["content_type"].lower()
    if expected_ct not in ct:
        problems.append(
            f"content-type mismatch: got '{got['content_type']}' expected '{expected_ct}' "
            f"(SPA-фолбэк? ретранслируется index.html)"
        )
    if expected_size is not None and got["size"] != expected_size:
        problems.append(
            f"size mismatch: got {got['size']} expected {expected_size} "
            f"(SPA-фолбэк = 23072 байта index.html)"
        )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args()

    report = {"host": HOST, "checks": [], "problems": []}
    for route, (ct, size) in CHECKS.items():
        got = probe(route)
        problems = evaluate(route, got, ct, size)
        entry = {"route": route, **got, "ok": not problems, "problems": problems}
        report["checks"].append(entry)
        report["problems"].extend(problems)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for c in report["checks"]:
            flag = "OK " if c["ok"] else "BAD"
            print(f"[{flag}] {c['route']:55s} HTTP {c['status']} {c['content_type']} {c['size']}B")
            for p in c["problems"]:
                print(f"        {p}")

    return 0 if not report["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())