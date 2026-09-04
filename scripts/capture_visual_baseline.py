"""Capture deterministic Mini App states for visual and accessibility QA.

The harness is intentionally deterministic: it uses the local dev identity,
accepts the self-confirmed age gate, never stores real user data, and writes only
screenshots plus aggregate DOM checks.
"""
from __future__ import annotations
import os

import json
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")
OUT = ROOT / "artifacts" / "visual-baseline"
BASE_URL_TEMPLATE = os.getenv("ORACLEAI_QA_BASE_URL", "http://127.0.0.1:8080/?dev_user={dev_user}")
LOCALE_USERS = {"ru": 10001, "en": 10002}
VIEWPORTS = {
    "mobile-360": (360, 800),
    "reference-390": (390, 844),
    "large-430": (430, 932),
}
LOCALES = {"ru": "ru-RU", "en": "en-US"}


def locale_contract(page, locale_key: str) -> dict:
    body_text = page.locator("body").inner_text()
    expected = {
        "ru": ("СЕГОДНЯ — БЕЗ СПЕШКИ", "Рады видеть тебя"),
        "en": ("TODAY — WITHOUT RUSH", "Glad you’re here"),
    }[locale_key]
    opposite = "Your gentle daily ritual" if locale_key == "ru" else "Твой мягкий ритуал дня"
    return {
        "expected_markers": list(expected),
        "expected_present": all(marker in body_text for marker in expected),
        "opposite_marker_absent": opposite not in body_text,
        "pass": all(marker in body_text for marker in expected) and opposite not in body_text,
    }


def dom_contract(page) -> dict:
    return page.evaluate(
        """
        () => {
          const body = document.body;
          const focusable = [...document.querySelectorAll(
            'button, a[href], input, textarea, select, [tabindex]:not([tabindex="-1"])'
          )];
          const unnamed = focusable.filter((el) => {
            const id = el.id;
            return !(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') ||
              el.getAttribute('title') || el.innerText || el.value ||
              (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) ||
              el.closest('label'));
          });
          const imagesWithoutAlt = [...document.images].filter((img) =>
            !img.hasAttribute('alt')
          );
          return {
            viewportWidth: window.innerWidth,
            scrollWidth: Math.max(body.scrollWidth, document.documentElement.scrollWidth),
            horizontalOverflow: Math.max(body.scrollWidth, document.documentElement.scrollWidth) > window.innerWidth + 1,
            unnamedFocusableCount: unnamed.length,
            unnamedFocusable: unnamed.map((el) => ({tag: el.tagName, className: el.className, text: (el.innerText || '').slice(0, 80)})),
            imagesWithoutAltCount: imagesWithoutAlt.length,
            visiblePrimaryActions: [...document.querySelectorAll('.btn-primary, [data-primary]')]
              .filter((el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)).length,
            paymentPlanCount: document.querySelectorAll('.pay-plan').length,
            paymentProductCount: document.querySelectorAll('.pay-product').length,
            reducedMotionPreference: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
          };
        }
        """
    )


def geometry_contract(page) -> dict:
    return page.evaluate(
        """
        () => {
          const selectors = [
            ['appRoot', '#app-root'], ['header', '.app-header'],
            ['main', '#app-main'], ['screen', '.screen'],
            ['hero', '.hero-orb'], ['seasonal', '.seasonal-moment'],
            ['dailyRitual', '.daily-ritual'], ['agentCard', '.agent-card'],
            ['profileHero', '.profile-hero'], ['nav', '.app-nav'],
            ['navButton', '.nav-btn'], ['primary', '.btn-primary']
          ];
          const rect = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            return {
              x: Math.round(r.x * 10) / 10,
              y: Math.round(r.y * 10) / 10,
              width: Math.round(r.width * 10) / 10,
              height: Math.round(r.height * 10) / 10,
              padding: cs.padding,
              gap: cs.gap,
              borderRadius: cs.borderRadius
            };
          };
          return Object.fromEntries(selectors.map(([name, selector]) => [name, rect(selector)]));
        }
        """
    )


def snapshot(page) -> dict:
    return {**dom_contract(page), "geometry": geometry_contract(page)}


def capture() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROMIUM_PATH, args=["--no-sandbox"])
        for locale_key, locale in LOCALES.items():
            base_url = BASE_URL_TEMPLATE.format(dev_user=LOCALE_USERS[locale_key])
            for name, (width, height) in VIEWPORTS.items():
                context = browser.new_context(
                    viewport={"width": width, "height": height}, locale=locale,
                    reduced_motion="reduce" if name == "reference-390" else "no-preference",
                    extra_http_headers={'X-Dev-Key': os.environ['DEV_KEY']} if os.getenv('DEV_KEY') else None)
                context.add_init_script(
                    "localStorage.setItem('oracle_lang', %r); "
                    "localStorage.removeItem('oracle_intro_seen'); "
                    "localStorage.removeItem('oracle_age_confirmed');" % locale_key
                )
                page = context.new_page()
                page.goto(base_url, wait_until="networkidle")
                page.evaluate("localStorage.setItem('oracle_chat_guide_v2', '1')")
                page.screenshot(path=str(OUT / f"{locale_key}-{name}-age-gate.png"), full_page=True)
                accept = page.locator("[data-age-accept]")
                if accept.count():
                    accept.first.click()
                    page.wait_for_timeout(250)
                skip = page.locator("[data-intro-skip]")
                if skip.count() and skip.first.is_visible():
                    skip.first.click()
                    page.wait_for_timeout(250)
                page.screenshot(path=str(OUT / f"{locale_key}-{name}-home.png"), full_page=True)
                states = {"home": snapshot(page)}
                states["home"]["localeContract"] = locale_contract(page, locale_key)
                try:
                    for view_name, state_name in (("hub", "chat"), ("payment", "payment"), ("profile", "profile")):
                        nav_button = page.locator(f'.nav-btn[data-goto="{view_name}"]')
                        if not nav_button.count():
                            continue
                        nav_button.first.click(force=True)
                        page.wait_for_timeout(350)
                        page.screenshot(path=str(OUT / f"{locale_key}-{name}-{state_name}.png"), full_page=True)
                        states[state_name] = snapshot(page)
                        if view_name != "profile":
                            continue
                        for tab_name, tab_state_name in (("chart", "chart-tab"), ("history", "history"), ("memory", "memory-tab")):
                            tab = page.locator(f'.ptab[data-tab="{tab_name}"]')
                            if tab.count() and tab.first.is_visible():
                                tab.first.click(force=True)
                                page.wait_for_timeout(350)
                                page.screenshot(path=str(OUT / f"{locale_key}-{name}-{tab_state_name}.png"), full_page=True)
                                states[tab_state_name] = snapshot(page)
                                if tab_name == "chart":
                                    full_chart = page.locator('[data-act="full-chart"]')
                                    if full_chart.count() and full_chart.first.is_visible():
                                        full_chart.first.click(force=True)
                                        page.wait_for_timeout(250)
                                        page.screenshot(path=str(OUT / f"{locale_key}-{name}-chart-modal.png"), full_page=True)
                                        states["chart-modal"] = snapshot(page)
                                        page.evaluate("window.app && app.closeModal && app.closeModal()")
                                        page.wait_for_timeout(100)
                                elif tab_name == "memory":
                                    memory_button = page.locator('[data-act="memories"]')
                                    if memory_button.count() and memory_button.first.is_visible():
                                        memory_button.first.click(force=True)
                                        page.wait_for_timeout(250)
                                        page.screenshot(path=str(OUT / f"{locale_key}-{name}-memory-modal.png"), full_page=True)
                                        states["memory-modal"] = snapshot(page)
                                        page.evaluate("window.app && app.closeModal && app.closeModal()")
                                        page.wait_for_timeout(100)

                    page.evaluate("window.app && app.go && app.go('home')")
                    page.wait_for_timeout(250)
                    page.evaluate("window.app && app.openChat && app.openChat('tarot', () => app.featureTarot())")
                    page.wait_for_timeout(450)
                    page.screenshot(path=str(OUT / f"{locale_key}-{name}-tarot.png"), full_page=True)
                    states["tarot"] = snapshot(page)
                    page.evaluate("window.app && app.closeChat && app.closeChat()")
                except PlaywrightError as exc:
                    states["navigation_error"] = str(exc)
                results[f"{locale_key}-{name}"] = states
                context.close()
        browser.close()
    report = {
        "base_urls": {
            locale_key: BASE_URL_TEMPLATE.format(dev_user=user_id)
            for locale_key, user_id in LOCALE_USERS.items()
        },
        "synthetic_users": LOCALE_USERS,
        "synthetic_identity": True,
        "viewports": results,
        "pass": not any("navigation_error" in states for states in results.values()) and all(
            state.get("horizontalOverflow") is False
            and state.get("unnamedFocusableCount", 0) == 0
            and state.get("imagesWithoutAltCount", 0) == 0
            for states in results.values()
            for state in states.values()
            if isinstance(state, dict) and "horizontalOverflow" in state
        ) and all(
            states.get("home", {}).get("localeContract", {}).get("pass") is True
            for states in results.values()
        ) and all(
            states.get("payment", {}).get("paymentPlanCount", 0) > 0
            and states.get("payment", {}).get("paymentProductCount", 0) > 0
            for states in results.values()
        ),
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(capture())
