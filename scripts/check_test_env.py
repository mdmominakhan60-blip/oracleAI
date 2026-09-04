#!/usr/bin/env python3
"""Verify local Python env matches requirements before running pytest.

Guards against running the suite with missing/old deps (36 silent
collection-errors incident). Exit non-zero listing every mismatch.
"""
import importlib.metadata as im
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements.txt"
REQ_DEV = ROOT / "requirements-dev.txt"

PIN = re.compile(r"^([A-Za-z0-9_.-]+)\[?[A-Za-z0-9_,.-]*\]?==(.+)$")


def load(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = PIN.match(line)
        if m:
            pins[m.group(1).lower().replace("-", "_")] = m.group(2)
    return pins


def main() -> int:
    pins = load(REQ)
    if REQ_DEV.exists():
        pins.update(load(REQ_DEV))
    problems = []
    for name, want in pins.items():
        try:
            have = im.version(name)
        except im.PackageNotFoundError:
            problems.append(f"MISSING  {name}=={want}")
            continue
        if have != want:
            problems.append(f"VERSION  {name}: pinned {want}, installed {have}")
    if problems:
        print("Env does not match requirements:")
        print("\n".join(problems))
        print("Fix: uv venv && uv pip install -r requirements.txt -r requirements-dev.txt")
        return 1
    print(f"OK: {len(pins)} pinned deps match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
