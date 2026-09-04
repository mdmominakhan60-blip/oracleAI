"""Run a deterministic Admin Dashboard visual/accessibility contract.

The script expects a local/staging API with a synthetic owner or an already
authenticated browser session. It writes screenshots and a JSON report outside
this repository by default, so generated artifacts do not pollute release
history.
"""
from __future__ import annotations
import os
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")

DEFAULT_VIEWPORTS = (
    ("desktop", 1280, 900),
    ("mobile", 390, 844),
)


CONTRACT_SCRIPT = r"""
() => {
  const visible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      rect.width > 0 && rect.height > 0;
  };
  const named = (el) => {
    const id = el.id;
    return Boolean(
      (el.getAttribute('aria-label') || '').trim() ||
      (el.getAttribute('aria-labelledby') || '').trim() ||
      (el.getAttribute('title') || '').trim() ||
      (el.innerText || '').trim() ||
      (el.value || '').trim() ||
      (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) ||
      el.closest('label')
    );
  };
  const rect = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: r.x, y: r.y, width: r.width, height: r.height};
  };
  const focusable = [...document.querySelectorAll(
    'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )].filter(visible);
  const controls = [...document.querySelectorAll('button, input, select, textarea')]
    .filter(visible);
  const unnamed = focusable.filter((el) => !named(el)).map((el) => ({
    tag: el.tagName, id: el.id, className: el.className
  }));
  const belowTarget = controls.filter((el) => el.getBoundingClientRect().height < 44)
    .map((el) => ({tag: el.tagName, id: el.id, className: el.className}));
  const imagesWithoutAlt = [...document.images].filter((el) => visible(el) &&
    !el.hasAttribute('alt')).map((el) => el.src);
  return {
    viewport: {width: innerWidth, height: innerHeight},
    scroll: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight},
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
    unnamedFocusable: unnamed,
    controlsBelow44: belowTarget,
    imagesWithoutAlt,
    geometry: {
      shell: rect('.shell'), sidebar: rect('.sidebar'), main: rect('.main'),
      topbar: rect('.topbar'), kpiGrid: rect('.kpi-grid'),
      paymentHealth: rect('.payment-health-card')
    },
    kpiCount: document.querySelectorAll('.kpi').length
  };
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.environ.get(
            "ADMIN_VISUAL_URL",
            "http://127.0.0.1:8080/admin/?dev_user=10001&qa=visual",
        ),
    )
    parser.add_argument("--out", type=Path, default=Path("/tmp/oracleai-admin-visual-contract"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
            args=["--no-sandbox"],
        )
        for name, width, height in DEFAULT_VIEWPORTS:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                reduced_motion="reduce",
                extra_http_headers={'X-Dev-Key': os.environ['DEV_KEY']} if os.getenv('DEV_KEY') else None,
            )
            page.goto(args.url, wait_until="networkidle")
            page.screenshot(path=str(args.out / f"{name}.png"), full_page=True)
            report[name] = page.evaluate(CONTRACT_SCRIPT)
            page.close()
        browser.close()

    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    errors = []
    for name, result in report.items():
        if result["horizontalOverflow"]:
            errors.append(f"{name}: horizontal overflow")
        if result["unnamedFocusable"]:
            errors.append(f"{name}: unnamed focusables={len(result['unnamedFocusable'])}")
        if result["controlsBelow44"]:
            errors.append(f"{name}: controls below 44px={len(result['controlsBelow44'])}")
        if result["imagesWithoutAlt"]:
            errors.append(f"{name}: images without alt={len(result['imagesWithoutAlt'])}")
    print(json.dumps({"pass": not errors, "errors": errors, "report": str(args.out / 'report.json')}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
