#!/usr/bin/env python3
"""Fail when runtime source references a missing static asset.

The check intentionally validates literal paths only. Dynamic template paths such as
``/static/img/agents/${a.code}.jpg`` are covered by the runtime fallback directory
check and are skipped here because their final filename is not knowable statically.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".css", ".html", ".js", ".py", ".ts", ".tsx"}
URL_RE = re.compile(r"(?P<quote>['\"])(?P<url>/(?:static|public|admin/static)/[^'\"\s)<>]+)(?P=quote)")
CSS_URL_RE = re.compile(r"url\(\s*(?P<quote>['\"]?)(?P<url>[^)'\"\s]+)(?P=quote)\s*\)", re.IGNORECASE)
DYNAMIC_MARKERS = ("${", "{{", "}}", "<%", "+", "`", "*", "[", "{", "}")
CSS_IMPORT_RE = re.compile(r"@import\s+(?:url\(\s*)?(?P<quote>['\"]?)(?P<url>[^'\";)\s]+)(?P=quote)", re.IGNORECASE)



def _is_dynamic(value: str) -> bool:
    return any(marker in value for marker in DYNAMIC_MARKERS) or value.endswith("/")


def _path_for_url(value: str) -> Path | None:
    value = urlsplit(value).path
    if value.startswith("/static/"):
        return ROOT / "miniapp" / value.removeprefix("/static/")
    if value.startswith("/public/"):
        return ROOT / "web" / value.removeprefix("/public/")
    if value.startswith("/admin/static/"):
        return ROOT / "admin" / value.removeprefix("/admin/static/")
    return None


def _check_absolute(path: Path, text: str, source: Path, errors: list[str]) -> None:
    for match in URL_RE.finditer(text):
        value = match.group("url")
        if _is_dynamic(value):
            continue
        target = _path_for_url(value)
        if target is not None and not target.is_file():
            errors.append(f"{source.relative_to(ROOT)}: missing {value}")


def _check_css_relative(path: Path, text: str, errors: list[str]) -> None:
    if path.suffix.lower() != ".css":
        return
    css_text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    for match in CSS_URL_RE.finditer(css_text):
        value = match.group("url")
        if not value or value.startswith(("data:", "http://", "https://", "//", "#")):
            continue
        if value.startswith("/"):
            continue  # validated by the absolute URL pass when it is a known app root.
        if _is_dynamic(value):
            continue
        value = urlsplit(value).path
        target = (path.parent / value).resolve()
        if ROOT not in target.parents and target != ROOT:
            errors.append(f"{path.relative_to(ROOT)}: relative asset escapes repository: {value}")
        elif not target.is_file():
            errors.append(f"{path.relative_to(ROOT)}: missing relative asset {value}")
    for match in CSS_IMPORT_RE.finditer(css_text):
        value = urlsplit(match.group("url")).path
        if not value or value.startswith(("/", "data:", "http://", "https://", "//", "#")) or _is_dynamic(value):
            continue
        target = (path.parent / value).resolve()
        if ROOT not in target.parents and target != ROOT:
            errors.append(f"{path.relative_to(ROOT)}: relative import escapes repository: {value}")
        elif not target.is_file():
            errors.append(f"{path.relative_to(ROOT)}: missing relative import {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    for directory in (root / "miniapp", root / "web", root / "admin", root / "app"):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if path.suffix == ".py":
                # FastAPI route decorators ("/public/config") are URL path
                # fragments, not static asset references — strip them.
                text = "\n".join(
                    line for line in text.splitlines()
                    if not line.lstrip().startswith(("@router.", "@app."))
                )
            _check_absolute(path, text, root, errors)
            _check_css_relative(path, text, errors)
    if errors:
        print("Static asset reference check failed:", file=sys.stderr)
        print("\n".join(sorted(set(errors))), file=sys.stderr)
        return 1
    print("Static asset reference check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
