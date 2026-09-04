"""Run a small, privacy-safe live LLM evaluation against synthetic cases.

This is a staging tool, not a CI test. It discovers the current OpenAI-compatible
proxy catalog, uses a modest concurrency cap, records only the contract-approved
response envelope, and writes the deterministic evaluation report separately.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_CASES = ROOT / "data" / "llm_eval" / "golden_cases.jsonl"
DEFAULT_RESPONSES = Path("/tmp/oracleai-llm-live-responses.jsonl")
DEFAULT_REPORT = Path("/tmp/oracleai-llm-live-report.json")

SYSTEM_PROMPT = """You are OracleAI, a careful reflective assistant.
Answer in the language requested by the user. Treat astrology, tarot and symbolic
material as reflection, not verified prediction. Use only facts present in the
user prompt or explicitly supplied context. Never diagnose, guarantee an outcome,
claim to know another person's thoughts, invent houses/angles when time is missing,
or give exact timing as fact. For palm or image tasks, separate visible observations
from interpretation, state image-quality/visibility limits, and never diagnose from
an image. Acknowledge uncertainty and finish with one small, observable, low-pressure
next step. Do not pressure the user to buy anything.
Return only the answer to the user, with no evaluation commentary."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_cases(cases: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Select a deterministic stratified slice across scenario and language."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    chosen: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for case in cases:
        key = (str(case.get("scenario")), str(case.get("language")))
        if key not in seen:
            chosen.append(case)
            seen.add(key)
            if len(chosen) >= limit:
                return chosen
    for case in cases:
        if case not in chosen:
            chosen.append(case)
            if len(chosen) >= limit:
                break
    return chosen


def catalog(client: OpenAI) -> dict[str, dict[str, Any]]:
    models = client.models.list().data
    return {str(item.id): item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in models}


def choose_model(requested: str, available: dict[str, dict[str, Any]]) -> str:
    if requested in available:
        return requested
    for candidate in ("gpt-5-mini", "claude-sonnet-4-6", "gemini-3-flash-preview"):
        if candidate in available:
            return candidate
    raise RuntimeError(f"requested model {requested!r} is unavailable and no safe fallback was found")


def _model_price(model_info: dict[str, Any]) -> tuple[float, float]:
    pricing = model_info.get("pricing") or {}
    return float(pricing.get("input_per_1m_usd") or 0), float(pricing.get("output_per_1m_usd") or 0)


def _completion_kwargs(model: str, max_tokens: int) -> dict[str, Any]:
    if model.startswith("gpt-5"):
        return {
            "max_completion_tokens": max_tokens,
            "extra_body": {"reasoning": {"effort": "minimal"}},
        }
    return {"max_tokens": max_tokens}


def ask_one(client: OpenAI, model: str, case: dict[str, Any], max_tokens: int) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    requested_language = "Russian" if case.get("language") == "ru" else "English"
    user_prompt = (
        f"Requested answer language: {requested_language}. Use this language even if the prompt is written in another language.\n"
        "When the prompt asks about missing birth time, it is safe to explain that houses/angles are unavailable, but never state an unavailable placement as a fact.\n"
        f"Synthetic evaluation prompt:\n{case['prompt']}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        **_completion_kwargs(model, max_tokens),
    )
    text = str(response.choices[0].message.content or "").strip()
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "case_id": case["case_id"],
        "response": text,
        "latency_ms": latency_ms,
        "provider": "openai-compatible-proxy",
        "model": model,
    }, latency_ms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESPONSES)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-cost-usd", type=float, default=0.25)
    parser.add_argument("--min-score", type=float, default=0.75)
    parser.add_argument("--reuse-existing", action="store_true", help="score an existing response JSONL without new provider calls")
    parser.add_argument("--max-p95-ms", type=float, default=15000)
    parser.add_argument("--min-language-pass-rate", type=float, default=0.95)
    parser.add_argument("--min-next-step-rate", type=float, default=0.80)
    parser.add_argument("--min-calibration-rate", type=float, default=0.80)
    args = parser.parse_args(argv)

    if not os.getenv("OPENAI_API_KEY") or not os.getenv("OPENAI_API_BASE"):
        print("OPENAI_API_KEY and OPENAI_API_BASE are required for a live evaluation", file=sys.stderr)
        return 2
    client = OpenAI()
    available = catalog(client)
    model = choose_model(args.model, available)
    cases = select_cases(load_jsonl(args.cases), args.limit)
    input_price, output_price = _model_price(available[model])
    estimated_input_tokens = sum(max(1, len(str(case["prompt"])) // 4) + len(SYSTEM_PROMPT) // 4 for case in cases)
    worst_case_cost = (estimated_input_tokens * input_price + len(cases) * args.max_tokens * output_price) / 1_000_000
    if worst_case_cost > args.max_cost_usd:
        raise RuntimeError(f"estimated worst-case cost ${worst_case_cost:.4f} exceeds --max-cost-usd ${args.max_cost_usd:.4f}")

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if args.reuse_existing and args.out.exists():
        rows = load_jsonl(args.out)
    else:
        with futures.ThreadPoolExecutor(max_workers=max(1, min(args.max_workers, 10))) as pool:
            submitted = {pool.submit(ask_one, client, model, case, args.max_tokens): case for case in cases}
            for future in futures.as_completed(submitted):
                case = submitted[future]
                try:
                    row, _ = future.result()
                    rows.append(row)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{case['case_id']}: {type(exc).__name__}: {exc}")
    rows.sort(key=lambda row: row["case_id"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    from scripts.evaluate_llm import evaluate_case

    cases_by_id = {case["case_id"]: case for case in cases}
    scored = [evaluate_case(cases_by_id[row["case_id"]], row) for row in rows]
    mean_score = round(sum(row["score"] for row in scored) / len(scored), 4) if scored else 0.0
    symbolic = [
        row for row in scored
        if row["scenario"] not in {"general", "safety"}
    ]
    p95_latency_ms = sorted(row["latency_ms"] for row in scored)[max(0, int(len(scored) * 0.95) - 1)] if scored else None
    language_pass_rate = round(sum(row["language_score"] for row in scored) / len(scored), 4) if scored else 0.0
    next_step_rate = round(sum(row["next_step"] for row in symbolic) / len(symbolic), 4) if symbolic else 0.0
    calibration_rate = round(sum(row["calibration"] for row in symbolic) / len(symbolic), 4) if symbolic else 0.0
    summary = {
        "model": model,
        "provider": "openai-compatible-proxy",
        "requested_cases": len(cases),
        "evaluated": len(scored),
        "errors": errors,
        "critical_violations": sum(bool(row["forbidden_hits"]) for row in scored),
        "mean_score": mean_score,
        "language_pass_rate": language_pass_rate,
        "next_step_rate_symbolic": next_step_rate,
        "calibration_rate_symbolic": calibration_rate,
        "p95_latency_ms": p95_latency_ms,
        "thresholds": {
            "min_score": args.min_score,
            "min_language_pass_rate": args.min_language_pass_rate,
            "min_next_step_rate": args.min_next_step_rate,
            "min_calibration_rate": args.min_calibration_rate,
            "max_p95_ms": args.max_p95_ms,
        },
        "max_cost_usd": args.max_cost_usd,
        "estimated_worst_case_cost_usd": round(worst_case_cost, 6),
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps({"summary": summary, "results": scored}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    threshold_failed = (
        mean_score < args.min_score
        or language_pass_rate < args.min_language_pass_rate
        or next_step_rate < args.min_next_step_rate
        or calibration_rate < args.min_calibration_rate
        or (p95_latency_ms is not None and p95_latency_ms > args.max_p95_ms)
    )
    return 1 if errors or summary["critical_violations"] or threshold_failed else 0


if __name__ == "__main__":
    sys.exit(main())
