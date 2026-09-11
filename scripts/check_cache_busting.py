"""Проверка единой cache-busting версии Mini App assets.

HTML и styles.css используют version query params вместо content hashes. Скрипт
падает, если JS/CSS подключены с разными версиями или aggregator содержит
рассинхронизированный import. Это policy gate, а не проверка визуального QA.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "miniapp" / "index.html"
STYLES = ROOT / "miniapp" / "styles.css"
CSS_DIR = ROOT / "miniapp" / "css"

# BUS-741 §3.5: фоновые изображения — тот же класс багов, что JS/CSS версии:
# preload в index.html и url() в css/* должны нести одну и ту же ?v=NNN,
# иначе при деплое часть пользователей останется на старом фоне из кэша.
BG_ASSETS = ("bg-cosmos.jpg", "bg-cosmos-2.jpg")


def versions(text: str) -> list[str]:
    return re.findall(r"[?&]v=(\d+)", text)


def check_bg_asset_versions(index_text: str, css_texts: dict[str, str]) -> None:
    for asset in BG_ASSETS:
        refs: dict[str, str] = {}
        for m in re.finditer(re.escape(asset) + r"\?v=(\d+)", index_text):
            refs["index.html"] = m.group(1)
        for name, text in css_texts.items():
            for m in re.finditer(re.escape(asset) + r"\?v=(\d+)", text):
                refs[name] = m.group(1)
            if asset in text and asset + "?v=" not in text:
                raise SystemExit(f"{name}: {asset} referenced without ?v= version")
        if not refs:
            continue
        if len(set(refs.values())) != 1:
            raise SystemExit(f"{asset} versions diverge across files: {refs}")


def main() -> int:
    index_text = INDEX.read_text(encoding="utf-8")
    styles_text = STYLES.read_text(encoding="utf-8")
    css_texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(CSS_DIR.glob("*.css"))}
    index_versions = versions(index_text)
    styles_versions = versions(styles_text)
    if not index_versions or not styles_versions:
        raise SystemExit("cache-busting version is missing from Mini App assets")
    all_versions = set(index_versions + styles_versions)
    # Font stylesheet may intentionally remain on an independent asset version;
    # all JS and the main styles aggregator must still share the current version.
    main_assets = re.findall(r"(?:styles\.css|/js/[^\"']+\.js)\?v=(\d+)", index_text)
    main_assets += re.findall(r"css/[^\"']+\.css\?v=(\d+)", styles_text)
    if not main_assets:
        raise SystemExit("no main Mini App assets found")
    if len(set(main_assets)) != 1:
        raise SystemExit(f"main asset versions diverge: {sorted(set(main_assets))}")
    current = main_assets[0]
    if current != max(main_assets, key=int):
        raise SystemExit("cache-busting version is not the highest referenced version")
    check_bg_asset_versions(index_text, css_texts)
    print(f"cache-busting ok: v{current}; independent versions: {sorted(all_versions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
