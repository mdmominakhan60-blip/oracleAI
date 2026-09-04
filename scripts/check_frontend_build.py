"""Validate the production Mini App bundle produced by build_frontend.mjs."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIAPP = ROOT / "miniapp"
DIST = MINIAPP / "dist"
INDEX = MINIAPP / "index.html"
STYLES = MINIAPP / "styles.css"


def main() -> int:
    manifest_path = DIST / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("frontend build missing: miniapp/dist/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    js_name = manifest.get("js", "")
    css_name = manifest.get("css", "")
    hashed = re.compile(r"^app\.[0-9a-f]{12}\.min\.(js|css)$")
    if not hashed.fullmatch(js_name) or not hashed.fullmatch(css_name):
        raise SystemExit(f"frontend assets must be content hashed: {js_name}, {css_name}")
    for name in (js_name, css_name):
        path = DIST / name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"frontend bundle missing or empty: {path}")

    source_js = re.findall(r'<script src="/static/js/([^"?]+)\?v=\d+"></script>', INDEX.read_text(encoding="utf-8"))
    source_css = re.findall(r"@import url\('css/([^?'\)]+)", STYLES.read_text(encoding="utf-8"))
    if len(source_js) != len(manifest.get("jsFiles", [])):
        raise SystemExit("frontend manifest JS coverage does not match index.html")
    if len(source_css) != len(manifest.get("cssFiles", [])):
        raise SystemExit("frontend manifest CSS coverage does not match styles.css")
    if len(source_js) + len(source_css) > 6:
        print(f"source modules: {len(source_js)} JS + {len(source_css)} CSS; production HTML emits 2 bundles")
    print(f"frontend build ok: {js_name} + {css_name}; source modules {len(source_js)} JS / {len(source_css)} CSS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
