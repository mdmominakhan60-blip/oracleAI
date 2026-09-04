"""Inspect desktop geometry and UI overflow for OracleAI screens."""
from __future__ import annotations

import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "desktop-audit"
URL = os.getenv("ORACLEAI_QA_DESKTOP_URL", "http://127.0.0.1:8080/?dev_user=10001&qa=desktop")


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        for width, height in ((1440, 900), (1920, 1080)):
            context = browser.new_context(viewport={"width": width, "height": height}, locale="ru-RU",
                                          extra_http_headers={'X-Dev-Key': os.environ['DEV_KEY']} if os.getenv('DEV_KEY') else None)
            context.add_init_script("localStorage.removeItem('oracle_intro_seen'); localStorage.removeItem('oracle_age_confirmed');")
            page = context.new_page()
            page.goto(URL, wait_until="networkidle")
            for selector in ("[data-age-accept]", "[data-intro-skip]"):
                target = page.locator(selector).first
                if target.count() and target.is_visible():
                    target.click(force=True)
                    page.wait_for_timeout(200)
            screen_data = {}
            for view, selector in (("home", '.nav-btn[data-goto="home"]'), ("hub", '.nav-btn[data-goto="hub"]'), ("profile", '.nav-btn[data-goto="profile"]')):
                page.locator(selector).click(force=True)
                page.wait_for_timeout(250)
                page.screenshot(path=str(OUT / f"{width}-{view}-top.png"), full_page=True)
                screen_data[view] = page.evaluate(
                    """
                    () => {
                      const rect = (el) => { if (!el) return null; const r=el.getBoundingClientRect(); const cs=getComputedStyle(el); return {x:r.x,y:r.y,width:r.width,height:r.height,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,overflowY:cs.overflowY,paddingBottom:cs.paddingBottom}; };
                      const screen=document.querySelector('.screen'), main=document.querySelector('#app-main'), nav=document.querySelector('.app-nav');
                      const last=screen?.lastElementChild;
                      return {viewport:{width:innerWidth,height:innerHeight},screen:rect(screen),main:rect(main),nav:rect(nav),last:rect(last),lastClass:last?.className||null,bodyScrollWidth:document.body.scrollWidth,documentScrollWidth:document.documentElement.scrollWidth};
                    }
                    """
                )
                if view in {"hub", "profile"}:
                    page.evaluate("document.querySelector('.screen') && (document.querySelector('.screen').scrollTop = document.querySelector('.screen').scrollHeight)")
                    page.wait_for_timeout(100)
                    page.screenshot(path=str(OUT / f"{width}-{view}-bottom.png"), full_page=True)
                    screen_data[f"{view}_bottom"] = page.evaluate("({scrollTop: document.querySelector('.screen')?.scrollTop || 0, scrollHeight: document.querySelector('.screen')?.scrollHeight || 0, clientHeight: document.querySelector('.screen')?.clientHeight || 0})")
            result[str(width)] = screen_data
            context.close()
        browser.close()
    (OUT / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
