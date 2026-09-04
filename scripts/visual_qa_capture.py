"""Capture deterministic OracleAI visual QA evidence at the requested breakpoints."""
from __future__ import annotations

import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")
OUT = ROOT / "artifacts" / "visual-qa"
BASE_URL = os.getenv("ORACLEAI_QA_VISUAL_URL", "http://127.0.0.1:8080/?dev_user=10001&qa=1&qa_view=home")
VIEWPORTS = {
    "mobile-320": (320, 720),
    "mobile-360": (360, 800),
    "mobile-375": (375, 812),
    "mobile-390": (390, 844),
    "mobile-430": (430, 932),
    "tablet-768": (768, 1024),
    "desktop-1024": (1024, 768),
    "desktop-1440": (1440, 900),
    "wide-1920": (1920, 1080),
}
LOCALES = {"ru": "ru-RU", "en": "en-US"}


def contract(page: object) -> dict:
    return page.evaluate(
        """
        () => {
          const body = document.body;
          const root = document.documentElement;
          const focusable = [...document.querySelectorAll('button, a[href], input, textarea, select, [tabindex]:not([tabindex="-1"])')];
          const labelled = (el) => (el.getAttribute('aria-label') || el.innerText || el.value || '').trim();
          const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const rect = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
          };
          const overflowNodes = [...document.querySelectorAll('*')].filter((el) => {
            const r = el.getBoundingClientRect();
            return visible(el) && !el.closest('.starfield') && !el.closest('.hero-orb, .welcome-card') && (r.left < -1 || r.right > innerWidth + 1);
          }).slice(0, 12).map((el) => ({tag: el.tagName, className: String(el.className || '').slice(0, 100)}));
          const decorativeOverflowNodes = [...document.querySelectorAll('.starfield, .starfield *')].filter((el) => {
            const r = el.getBoundingClientRect();
            return visible(el) && (r.left < -1 || r.right > innerWidth + 1);
          }).slice(0, 12).map((el) => ({tag: el.tagName, className: String(el.className || '').slice(0, 100)}));
          return {
            viewport: {width: innerWidth, height: innerHeight},
            scroll: {body: body.scrollWidth, document: root.scrollWidth},
            horizontalOverflow: Math.max(body.scrollWidth, root.scrollWidth) > innerWidth + 1,
            overflowNodes,
            decorativeOverflowNodes,
            unnamedFocusable: focusable.filter((el) => visible(el) && !labelled(el)).map((el) => ({tag: el.tagName, className: String(el.className || '').slice(0, 100)})),
            imagesWithoutAlt: [...document.images].filter((img) => !img.hasAttribute('alt')).length,
            visiblePrimaryActions: [...document.querySelectorAll('.btn-primary, [data-primary]')].filter(visible).length,
            visible: {
              screen: rect('.screen, .chat-shell'), header: rect('.app-header'), hero: rect('.hero-orb, .welcome-card'),
              agentCard: rect('.agent-card'), nav: rect('.main-nav'), modal: rect('.modal-overlay, .intro-overlay, .age-overlay')
            },
            bodyFont: getComputedStyle(body).fontFamily,
            reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
          };
        }
        """
    )


def first_click(page, selector: str) -> bool:
    target = page.locator(selector).first
    if target.count() and target.is_visible():
        target.click(force=True)
        page.wait_for_timeout(300)
        return True
    return False


def capture() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROMIUM_PATH, args=["--no-sandbox"])
        for locale_key, locale in LOCALES.items():
            for viewport_name, (width, height) in VIEWPORTS.items():
                context = browser.new_context(
                    viewport={"width": width, "height": height}, locale=locale,
                    reduced_motion="reduce" if viewport_name == "tablet-768" else "no-preference",
                    extra_http_headers={'X-Dev-Key': os.environ['DEV_KEY']} if os.getenv('DEV_KEY') else None,
                )
                context.add_init_script(
                    "localStorage.setItem('oracle_lang', %r); "
                    "localStorage.setItem('oracle_intro_seen', '1'); "
                    "localStorage.setItem('oracle_chat_guide_v2', '1');" % locale_key
                )
                page = context.new_page()
                page.goto(BASE_URL, wait_until="domcontentloaded")
                page.wait_for_selector('#app-main .screen, #app-main [data-auth-required], .soft-empty', timeout=15000)
                page.wait_for_timeout(400)
                page.screenshot(path=str(OUT / f"{locale_key}-{viewport_name}-home.png"), full_page=True)
                states = {"home": contract(page)}
                if first_click(page, '.nav-btn[data-goto="hub"]'):
                    page.screenshot(path=str(OUT / f"{locale_key}-{viewport_name}-hub.png"), full_page=True)
                    states["hub"] = contract(page)
                    if first_click(page, '.agent-card [data-act="chat"]'):
                        page.wait_for_timeout(400)
                        page.screenshot(path=str(OUT / f"{locale_key}-{viewport_name}-chat.png"), full_page=True)
                        states["chat"] = contract(page)
                if first_click(page, '.nav-btn[data-goto="profile"]'):
                    page.screenshot(path=str(OUT / f"{locale_key}-{viewport_name}-profile.png"), full_page=True)
                    states["profile"] = contract(page)
                    for tab_name in ("chart", "history", "memory"):
                        if first_click(page, f'.ptab[data-tab="{tab_name}"]'):
                            page.screenshot(path=str(OUT / f"{locale_key}-{viewport_name}-{tab_name}.png"), full_page=True)
                            states[tab_name] = contract(page)
                results[f"{locale_key}-{viewport_name}"] = states
                context.close()
        browser.close()
    report = {"base_url": BASE_URL, "viewports": VIEWPORTS, "locales": list(LOCALES), "results": results}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(capture())
