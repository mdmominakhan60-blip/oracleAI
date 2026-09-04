"""Run focused WCAG 2.1 and Telegram Mini Apps checks against OracleAI."""
from __future__ import annotations

import os

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "standards-audit"
URL = "http://127.0.0.1:8080/?dev_user=10001&qa=standards"


def collect(page, label: str) -> dict:
    return page.evaluate(
        """
        (label) => {
          const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
          const name = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.value || '').trim();
          const rect = (el) => { const r = el.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)}; };
          const focusable = [...document.querySelectorAll('button, a[href], input, textarea, select, [tabindex]:not([tabindex="-1"])')].filter(visible);
          const interactive = [...document.querySelectorAll('button, a[href], input, textarea, select, [role="button"], [data-act]')].filter(visible);
          const smallTargets = interactive.filter((el) => { const r=el.getBoundingClientRect(); return r.width < 44 || r.height < 44; }).map((el) => ({tag:el.tagName, className:String(el.className||''), text:name(el).slice(0,80), rect:rect(el)}));
          const inputsWithoutLabel = [...document.querySelectorAll('input, textarea, select')].filter(visible).filter((el) => {
            const id=el.id; return !(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) || el.closest('label'));
          }).map((el) => ({tag:el.tagName, type:el.type||'', name:el.name||'', placeholder:el.placeholder||''}));
          const focusStyles = [...document.querySelectorAll('button, a[href], input, textarea, select, [data-act]')].filter(visible).slice(0,80).map((el) => {
            const cs=getComputedStyle(el); return {tag:el.tagName,className:String(el.className||''),outline:cs.outlineStyle+' '+cs.outlineWidth+' '+cs.outlineColor,focusRule:!!el.matches(':focus-visible')};
          });
          const headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(visible).map((el)=>({tag:el.tagName,text:el.innerText.trim().slice(0,100)}));
          const dialogs=[...document.querySelectorAll('[role="dialog"], dialog')].filter(visible).map((el)=>({role:el.getAttribute('role'),modal:el.getAttribute('aria-modal'),label:el.getAttribute('aria-label')||el.getAttribute('aria-labelledby')||''}));
          const positiveTabindex=[...document.querySelectorAll('[tabindex]')].filter(el => Number(el.getAttribute('tabindex')) > 0).map(el=>({tag:el.tagName,className:String(el.className||'')}));
          const unnamed=focusable.filter(el=>!name(el)).map(el=>({tag:el.tagName,className:String(el.className||''),rect:rect(el)}));
          const imagesWithoutAlt=[...document.images].filter((img)=>!img.hasAttribute('alt')).map(img=>img.src);
          return {label, htmlLang:document.documentElement.lang, title:document.title, bodyScrollWidth:document.body.scrollWidth, viewportWidth:innerWidth, viewportHeight:innerHeight, focusableCount:focusable.length, unnamed, imagesWithoutAlt, inputsWithoutLabel, positiveTabindex, smallTargets, headings, dialogs, focusStyles, telegram: {hasWebApp:!!window.Telegram?.WebApp, viewportHeight:window.Telegram?.WebApp?.viewportHeight ?? null, isExpanded:window.Telegram?.WebApp?.isExpanded ?? null, themeParamsKeys:Object.keys(window.Telegram?.WebApp?.themeParams||{})}};
        }
        """,
        label,
    )


def click_if_visible(page, selector: str) -> bool:
    target = page.locator(selector).first
    if target.count() and target.is_visible():
        target.click(force=True)
        page.wait_for_timeout(250)
        return True
    return False


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        for locale, lang in (("ru-RU", "ru"), ("en-US", "en")):
            for width, height in ((375, 812), (1440, 900)):
                context = browser.new_context(viewport={"width": width, "height": height}, locale=locale,
                                              reduced_motion="reduce",
                                              extra_http_headers={'X-Dev-Key': os.environ['DEV_KEY']} if os.getenv('DEV_KEY') else None)
                context.add_init_script("localStorage.setItem('oracle_lang', %r); localStorage.removeItem('oracle_intro_seen'); localStorage.removeItem('oracle_age_confirmed');" % lang)
                page = context.new_page()
                page.goto(URL, wait_until="networkidle")
                click_if_visible(page, "[data-age-accept]")
                click_if_visible(page, "[data-intro-skip]")
                states = {"home": collect(page, f"{lang}-{width}-home")}
                for state, selector in (("hub", '.nav-btn[data-goto="hub"]'), ("profile", '.nav-btn[data-goto="profile"]')):
                    if click_if_visible(page, selector):
                        states[state] = collect(page, f"{lang}-{width}-{state}")
                        if state == "profile":
                            for tab in ("chart", "history", "memory"):
                                if click_if_visible(page, f'.ptab[data-tab="{tab}"]'):
                                    states[f"{tab}-tab"] = collect(page, f"{lang}-{width}-{tab}-tab")
                results[f"{lang}-{width}"] = states
                context.close()
        browser.close()
    (OUT / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
