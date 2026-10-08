"""Check OracleAI's shared design tokens and visual release contract."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "miniapp" / "css" / "00-tokens.css"
STYLES = ROOT / "miniapp" / "styles.css"
INVENTORY = ROOT / "docs" / "DESIGN_COMPONENT_INVENTORY.md"
VISUAL_QA = ROOT / "miniapp" / "css" / "16-visual-qa.css"
# BUS-960 (§3.4): legacy-золотая палитра #E6C178 запрещена и в JS миниаппа.
JS_DIR = ROOT / "miniapp" / "js"
LEGACY_GOLD_RE = re.compile(r"230,\s*193,\s*120|e6c178", re.IGNORECASE)

REQUIRED_TOKENS = {
    "--bg-0", "--bg-1", "--bg-2", "--gold", "--gold-bright", "--violet",
    "--text", "--text-dim", "--text-faint", "--border", "--border-strong",
    "--font-body", "--r-s", "--r-m", "--r-l", "--motion-quick",
    "--motion-base", "--motion-slow", "--sh-card", "--sh-gold",
    "--color-bg-primary", "--color-bg-secondary", "--color-bg-elevated",
    "--color-accent", "--color-text-primary", "--color-text-secondary",
    "--color-border", "--color-success", "--color-error", "--color-warning",
    "--font-size-h1", "--font-size-body", "--font-size-caption", "--space-4",
    "--radius-control", "--touch-target", "--motion-enter", "--focus-ring",
}


def main() -> int:
    tokens = TOKENS.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    inventory = INVENTORY.read_text(encoding="utf-8")
    visual_qa = VISUAL_QA.read_text(encoding="utf-8")
    missing = sorted(token for token in REQUIRED_TOKENS
                     if not re.search(rf"{re.escape(token)}\s*:", tokens))
    imports = [item.split("?", 1)[0] for item in re.findall(r"@import\s+url\('css/([^']+)'", styles)]
    # Order is validated by prefix sequence; two features may share a numeric
    # prefix (16-visual-qa + 16-payments, 18-pixel-reconstruction + precision);
    # total count must match files on disk. 20-chat-viewport — BUS-509.
    # 21-chat-stage — BUS-636 (стадия работы чата); гейт пропустил добавление.
    # 22-components — BUS-969 инкремент 2 (библиотека §4 R03);
    # 22-background-states — BUS-993 (R05: data-bg состояния, пауза E18, reduce E23).
    # 23-r06-tools — BUS-1070 p2 (волна B: S11 инструменты + S12 результат + S13 таро).
    # 24-r06-p3 — BUS-1070 p3 (волна B: S15 сегодня + S20 библиотека + S22 память
    # + S23 уведомления + S24 тариф/paywall + S25 ожидание + S26 заказы
    # + S13 крест + состояния §11.2).
    # 25-r06-s14 — BUS-1103 (волна B: S14 натальная карта, G-кадр explain-chart,
    # макет BUS-1067 p4).
    # 27-observatory — BUS-1236 (обсерватория; импорт добавлен в 66d1d43).
    expected_prefixes = ["00-", "01-", "02-", "03-", "04-", "05-", "06-", "07-",
                         "08-", "09-", "10-", "11-", "12-", "13-", "14-", "15-",
                         "16-", "16-", "17-", "18-", "18-", "19-", "20-", "21-",
                         "22-", "22-", "23-", "24-", "24-", "25-", "26-", "24-",
                         "25-", "27-"]
    import_order_ok = (
        len(imports) == len(expected_prefixes)
        and len(imports) == len(list((ROOT / "miniapp" / "css").glob("*.css")))
        and all(imports[idx].startswith(expected_prefixes[idx])
                for idx in range(len(expected_prefixes)))
        and imports[16] == "16-visual-qa.css"
        and imports[17] == "16-payments.css"
        and imports[18] == "17-premium-shell.css"
        and imports[19] == "18-pixel-reconstruction.css"
        and imports[20] == "18-pixel-precision.css"
        and imports[21] == "19-feedback.css"
        and imports[22] == "20-chat-viewport.css"
        and imports[23] == "21-chat-stage.css"
        and imports[24] == "22-components.css"
        and imports[25] == "22-background-states.css"
        and imports[26] == "23-r06-tools.css"
        and imports[27] == "24-r06-tokens.css"
        and imports[28] == "24-r06-p1.css"
        and imports[29] == "25-r06-p2.css"
        and imports[30] == "26-r06-p3.css"
        and imports[31] == "24-r06-p3.css"
        and imports[32] == "25-r06-s14.css"
        and imports[33] == "27-observatory.css"
    )
    reduced_motion = "prefers-reduced-motion: reduce" in styles or any(
        "prefers-reduced-motion: reduce" in path.read_text(encoding="utf-8")
        for path in (ROOT / "miniapp" / "css").glob("*.css")
    )
    required_components = [
        "Chat composer", "Tool chip", "Tool sheet", "Age gate", "Memory control",
        "Tarot widget", "Chart widget", "Compatibility widget", "Safety banner",
    ]
    missing_components = [item for item in required_components if item not in inventory]
    touch_target_ok = bool(re.search(r"--touch-target\s*:\s*44px", tokens))
    focus_contract_ok = all(marker in visual_qa for marker in (":focus-visible", "outline: 2px", "outline-offset: 3px"))
    legacy_gold_js = sorted(
        path.name for path in JS_DIR.glob("*.js")
        if LEGACY_GOLD_RE.search(path.read_text(encoding="utf-8"))
    )
    if missing or not import_order_ok or not reduced_motion or missing_components or not touch_target_ok or not focus_contract_ok or legacy_gold_js:
        print({
            "missing_tokens": missing,
            "import_order_ok": import_order_ok,
            "reduced_motion": reduced_motion,
            "missing_components": missing_components,
            "touch_target_ok": touch_target_ok,
            "focus_contract_ok": focus_contract_ok,
            "legacy_gold_js": legacy_gold_js,
        })
        return 1
    print("design contract ok: tokens, import order, reduced motion, component inventory, touch target, focus ring, no legacy gold in js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
