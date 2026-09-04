#!/usr/bin/env python3
"""Deterministic Telegram-like WebView QA probe.

This validates the browser-side contract only. It cannot emulate native
Telegram safe-area values or a physical IME; those still require device QA.
"""
from __future__ import annotations
import os
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")


def measure(page) -> dict:
    return page.evaluate("""() => {
      const q = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const c = getComputedStyle(el);
        return {x:r.x,y:r.y,width:r.width,height:r.height,
          paddingBottom:c.paddingBottom,position:c.position,bottom:c.bottom,
          overflow:c.overflow};
      };
      const vv = window.visualViewport;
      return {
        inner: {width: innerWidth, height: innerHeight},
        client: {width: document.documentElement.clientWidth,
          height: document.documentElement.clientHeight},
        visualViewport: vv ? {width: vv.width, height: vv.height,
          offsetTop: vv.offsetTop, pageTop: vv.pageTop} : null,
        appRoot: q('#app-root'),
        chatShell: q('.chat-shell'),
        chatMessages: q('.chat-messages'),
        composer: q('.composer'),
        nav: q('.app-nav'),
        safeAreaCssSupported: CSS.supports('padding-bottom: env(safe-area-inset-bottom)') &&
          CSS.supports('padding-top: env(safe-area-inset-top)'),
        dynamicViewportCssSupported: CSS.supports('height: 100dvh'),
        bodyScrollWidth: document.body.scrollWidth,
        docScrollWidth: document.documentElement.scrollWidth,
      };
    }""")


def simulate_keyboard(page) -> dict:
    return page.evaluate("""() => {
      const vv = window.visualViewport;
      const composer = document.querySelector('.composer');
      if (!vv || !composer) return {available:false,
        reason: !vv ? 'visualViewport_missing' : 'composer_missing'};
      const original = vv.height;
      let patched = false;
      try {
        Object.defineProperty(vv, 'height', {value: Math.max(1, original - 320), configurable: true});
        patched = true;
      } catch (_) {}
      vv.dispatchEvent(new Event('resize'));
      const after = {height: vv.height,
        composerPaddingBottom: getComputedStyle(composer).paddingBottom,
        inlinePaddingBottom: composer.style.paddingBottom};
      try { Object.defineProperty(vv, 'height', {value: original, configurable: true}); } catch (_) {}
      vv.dispatchEvent(new Event('resize'));
      return {available:true, patched, original,
        simulatedKeyboardDelta: original - after.height, after,
        restoredPaddingBottom: getComputedStyle(composer).paddingBottom};
    }""")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default='http://127.0.0.1:8000')
    p.add_argument('--qa-view', default='chat')
    p.add_argument('--qa-agent', default='oracle')
    p.add_argument('--dev-user', default='10001')
    p.add_argument('--width', type=int, default=390)
    p.add_argument('--height', type=int, default=844)
    p.add_argument('--dpr', type=float, default=3)
    p.add_argument('--output', type=Path)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip('/')
    url = f'{base}/?qa=1&qa_view={args.qa_view}&qa_agent={args.qa_agent}&dev_user={args.dev_user}'
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROMIUM_PATH,
                                    args=['--no-sandbox'])
        context = browser.new_context(
            viewport={'width': args.width, 'height': args.height}, is_mobile=True,
            has_touch=True, device_scale_factor=args.dpr,
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                       'AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',
            locale='ru-RU',
            extra_http_headers={'X-Dev-Key': os.environ['DEV_KEY']} if os.getenv('DEV_KEY') else None)
        context.add_init_script("localStorage.setItem('oracle_lang','ru'); "
                                "localStorage.setItem('oracle_intro_seen','1'); "
                                "localStorage.setItem('oracle_chat_guide_v2','1');")
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.goto(url, wait_until='domcontentloaded')
        try:
            page.wait_for_selector('#app-main > *', timeout=15000)
        except Exception as exc:  # noqa: BLE001
            result = {'pass': False, 'stage': 'bootstrap', 'error': type(exc).__name__,
                      'url': url, 'page_errors': errors,
                      'diagnostics': page.evaluate("""() => ({title: document.title,
                        bodyText: document.body.innerText.slice(0, 800),
                        appMain: !!document.querySelector('#app-main')})""")}
        else:
            page.wait_for_timeout(600)
            before = measure(page)
            keyboard = simulate_keyboard(page)
            after = measure(page)
            result = {
                'pass': bool(before.get('visualViewport')) and before.get('safeAreaCssSupported')
                    and before.get('dynamicViewportCssSupported')
                    and before.get('bodyScrollWidth') <= before['inner']['width'] + 1
                    and before.get('docScrollWidth') <= before['inner']['width'] + 1
                    and keyboard.get('available')
                    and keyboard.get('simulatedKeyboardDelta', 0) >= 300
                    and keyboard.get('restoredPaddingBottom') == before['composer']['paddingBottom'],
                'url': url,
                'viewport_profile': {'width': args.width, 'height': args.height,
                                    'dpr': args.dpr, 'touch': True},
                'before': before, 'keyboard_simulation': keyboard, 'after': after,
                'page_errors': errors,
                'notes': [
                    'safe-area env resolves to 0 in Chromium; native inset requires Telegram device QA',
                    'keyboard behavior is validated by visualViewport resize simulation; physical IME requires device QA',
                ],
            }
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding='utf-8')
        print(rendered, end='')
        context.close()
        browser.close()
    return 0 if result.get('pass') else 1


if __name__ == '__main__':
    raise SystemExit(main())
