#!/usr/bin/env python3
"""Synthetic HTTP load test for an isolated OracleAI staging/dev API.

The tool never creates or mutates production data. Run it against a dedicated
DB with ``DEV_MODE=1`` and ``LLM_PROVIDER=off`` for a deterministic API/storage
baseline. Provider-on capacity testing requires a separately approved staging
profile and must not use this script's synthetic defaults.

Example::

    python scripts/load_test_api.py --base-url http://127.0.0.1:8002 \
        --users 300 --concurrency 32 --output /tmp/load.json
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

READ_ROUTES = [
    ("me", "/api/me"),
    ("agents", "/api/agents"),
    ("today", "/api/today"),
    ("moon_week", "/api/moon/week?days=7"),
    ("sky", "/api/sky"),
    ("horoscope_all", "/api/horoscope/all"),
]
AGENTS = ["oracle", "astro", "tarot", "chiromant"]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def request(base_url: str, route_name: str, path: str, user: int,
            method: str = "GET", body: bytes | None = None,
            headers: dict[str, str] | None = None) -> dict:
    separator = "&" if "?" in path else "?"
    url = f"{base_url}{path}{separator}dev_user={user}"
    req = urllib.request.Request(url, method=method, data=body,
                                 headers=headers or {})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
            status = response.status
            error = None
    except urllib.error.HTTPError as exc:
        exc.read()
        status = exc.code
        error = f"http_{exc.code}"
    except Exception as exc:  # noqa: BLE001
        status = 0
        error = type(exc).__name__
    return {
        "route": route_name,
        "status": status,
        "error": error,
        "ms": (time.perf_counter() - started) * 1000,
    }


def summarize(rows: list[dict], wall_ms: float, *, base_url: str,
             users: int, concurrency: int, include_posts: bool) -> dict:
    grouped: dict[str, list[float]] = defaultdict(list)
    statuses: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        grouped[row["route"]].append(row["ms"])
        statuses[row["route"]][str(row["status"])] += 1
    by_route = {}
    for route, values in sorted(grouped.items()):
        by_route[route] = {
            "requests": len(values),
            "p50_ms": round(percentile(values, 0.50), 2),
            "p95_ms": round(percentile(values, 0.95), 2),
            "p99_ms": round(percentile(values, 0.99), 2),
            "max_ms": round(max(values), 2),
            "statuses": dict(statuses[route]),
        }
    all_values = [row["ms"] for row in rows]
    successful = sum(200 <= row["status"] < 300 for row in rows)
    return {
        "base_url": base_url,
        "synthetic": True,
        "synthetic_users": users,
        "concurrency": concurrency,
        "include_agent_posts": include_posts,
        "requests": len(rows),
        "successful_2xx": successful,
        "success_rate": round(successful / len(rows), 4) if rows else 0,
        "wall_ms": round(wall_ms, 2),
        "throughput_rps": round(len(rows) / (wall_ms / 1000), 2) if wall_ms else 0,
        "overall": {
            "p50_ms": round(percentile(all_values, 0.50), 2),
            "p95_ms": round(percentile(all_values, 0.95), 2),
            "p99_ms": round(percentile(all_values, 0.99), 2),
            "max_ms": round(max(all_values), 2) if all_values else 0,
        },
        "by_route": by_route,
        "llm_provider": os.getenv("LLM_PROVIDER", "unknown"),
        "note": "Synthetic local HTTP stress baseline; not a production capacity guarantee.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("ORACLEAI_LOAD_BASE_URL", "http://127.0.0.1:8001"),
                        help="isolated API base URL")
    parser.add_argument("--users", type=int, default=300, help="synthetic dev_user IDs")
    parser.add_argument("--user-start", type=int, default=100_000_000,
                        help="first synthetic Telegram ID")
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--skip-agent-posts", action="store_true",
                        help="only run read/history routes")
    parser.add_argument("--output", type=Path, help="write JSON result to this path")
    return parser.parse_args()


def dev_headers() -> dict[str, str]:
    """Заголовок X-Dev-Key обязателен против комплаент-стека (BUS-90):
    DEV_MODE=1 без DEV_KEY не поднимается, а с заданным ключом ?dev_user
    без заголовка ловит 401."""
    return {"X-Dev-Key": os.getenv("DEV_KEY", "")} if os.getenv("DEV_KEY") else {}


def main() -> int:
    args = parse_args()
    if args.users < 1 or args.concurrency < 1:
        raise SystemExit("--users and --concurrency must be positive")
    base_url = args.base_url.rstrip("/")
    include_posts = not args.skip_agent_posts
    jobs = []
    for index in range(args.users):
        user = args.user_start + index
        for route, path in READ_ROUTES:
            jobs.append((base_url, route, path, user, "GET", None, dev_headers()))
        for agent in AGENTS:
            jobs.append((base_url, f"agent_history_{agent}", f"/api/chat/{agent}",
                         user, "GET", None, dev_headers()))
        if include_posts:
            agent = AGENTS[index % len(AGENTS)]
            payload = json.dumps({"text": "synthetic load probe", "allow_paid": False}).encode()
            jobs.append((base_url, f"agent_post_{agent}", f"/api/chat/{agent}", user,
                         "POST", payload, {
                             "Content-Type": "application/json",
                             "X-Idempotency-Key": f"load-{user}-{agent}",
                             **dev_headers(),
                         }))

    started = time.perf_counter()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(request, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            rows.append(future.result())
    result = summarize(rows, (time.perf_counter() - started) * 1000,
                       base_url=base_url, users=args.users,
                       concurrency=args.concurrency, include_posts=include_posts)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["success_rate"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
