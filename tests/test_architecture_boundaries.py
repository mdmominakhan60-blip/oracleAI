"""Небольшие архитектурные тесты, защищающие новые границы модульного монолита."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "app" / "api" / "routers"
INDEX = ROOT / "miniapp" / "index.html"


def test_api_routers_do_not_import_each_other() -> None:
    router_names = {
        path.stem for path in ROUTERS.glob("*.py") if path.name != "__init__.py"
    }
    pattern = re.compile(
        r"^\s*(?:from\s+\.|import\s+app\.api\.routers\.)"
        r"(" + "|".join(sorted(map(re.escape, router_names))) + r")"
    )

    violations = []
    for path in ROUTERS.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

    assert not violations, "router-to-router imports found:\n" + "\n".join(violations)


# ── Layering: presentation → services → repo ────────────────────────────────
# Rule: app/api/routers may only call app/services (and app/api/*), never
# app/repo directly. app/services and app/repo must never import from the
# presentation layer (app/api/routers). This is the same "frozen allowlist"
# pattern used for the other architecture guards above.
KNOWN_ROUTER_REPO_IMPORTS: dict[str, int] = {
    # ARCH-004 close-out: routers reach app/repo only through
    # app/services/repo_gateway.py; direct router→repo imports are gone.
}
REPO_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?:\.{2,3}|app)\.repo[\s.]|import\s+(?:\.{2,3}|app)\.repo)"
)
# ARCH-004 (bot): admin/analytics/billing policy routed through services
# (app/services/access.py, app/services/billing.py). Remaining repo imports
# in bot handlers are thin data reads (users/content) — frozen counts; new
# bot→repo imports in ANY file (including new files) are a hard failure.
KNOWN_BOT_REPO_IMPORTS = {
    "chat": 1,
    "features": 1,
    "growth": 1,
    "onboarding": 1,
    "profile": 1,
    "shop": 1,
}
BOT_REPO_IMPORT_RE = re.compile(r"^\s*from\s+\.\.repo[\s.]")


def test_routers_do_not_import_repo_directly() -> None:
    """Enforce presentation → services → repo layering for routers.

    15 routers still reach into app/repo directly (see KNOWN_ROUTER_REPO_IMPORTS
    above). The per-file import counts are frozen: any new repo import in any
    router — including the grandfathered files — fails this test. Existing
    counts may only go down; update the allowlist when a router is migrated.
    """
    violations = []
    for path in sorted(ROUTERS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        stem = path.stem
        count = 0
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if REPO_IMPORT_RE.search(line):
                count += 1
                if stem not in KNOWN_ROUTER_REPO_IMPORTS:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{number}: {line.strip()} "
                        "(new router→repo import is not allowed — go through app/services)"
                    )
        expected = KNOWN_ROUTER_REPO_IMPORTS.get(stem, 0)
        if count > expected:
            violations.append(
                f"{path.relative_to(ROOT)}: {count} repo imports exceed the "
                f"frozen allowance of {expected} (ARCH-004)"
            )

    assert not violations, "presentation→repo layering violations:\n" + "\n".join(
        violations
    )


def test_bot_repo_imports_frozen() -> None:
    """ARCH-004 (bot): freeze remaining bot→repo data-read imports.

    Admin/analytics/billing went through app/services (access.py, billing.py,
    bot_flows.py); the rest are thin users/content reads. Any new bot file or
    additional repo import fails — counts may only go down.
    """
    violations = []
    for path in sorted((ROOT / "app" / "bot").glob("*.py")):
        if path.name == "__init__.py":
            continue
        stem = path.stem
        count = 0
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BOT_REPO_IMPORT_RE.search(line):
                count += 1
                if stem not in KNOWN_BOT_REPO_IMPORTS:
                    violations.append(
                        f"{path.relative_to(ROOT)}:{number}: {line.strip()} "
                        "(new bot→repo import — go through app/services)"
                    )
        expected = KNOWN_BOT_REPO_IMPORTS.get(stem, 0)
        if count > expected:
            violations.append(
                f"{path.relative_to(ROOT)}: {count} repo imports exceed the "
                f"frozen allowance of {expected} (ARCH-004)"
            )
    assert not violations, "bot→repo layering violations:\n" + "\n".join(violations)


def test_services_and_repo_do_not_import_presentation() -> None:
    """Layering guard: services and repo must never import from app/api."""
    violations = []
    for layer in ("app/services", "app/repo"):
        for path in sorted((ROOT / layer).glob("*.py")):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if re.search(r"^\s*(?:from|import)\s+(?:\.+api|app\.api)\b", line):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{number}: {line.strip()}"
                    )

    assert not violations, "services/repo must not import app/api:\n" + "\n".join(
        violations
    )


def test_frontend_runtime_boundaries_have_stable_order() -> None:
    html = INDEX.read_text(encoding="utf-8")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)

    def position(filename: str) -> int:
        for index, script in enumerate(scripts):
            if script.split("?", 1)[0].endswith("/" + filename):
                return index
        raise AssertionError(f"{filename} is not declared in miniapp/index.html")

    assert position("00-runtime.js") < position("05-app.js")
    assert position("15-actions.js") < position("13-events.js")
    version = re.search(r'/static/js/00-runtime\.js\?v=(\d+)', html)
    assert version, "runtime asset must be cache-busted"
    value = version.group(1)
    assert f"/static/js/15-actions.js?v={value}" in html


def test_frontend_cache_version_covers_new_modules() -> None:
    html = INDEX.read_text(encoding="utf-8")
    styles = (ROOT / "miniapp" / "styles.css").read_text(encoding="utf-8")
    version = re.search(r"/static/styles\.css\?v=(\d+)", html)
    assert version, "styles asset must be cache-busted"
    value = version.group(1)
    assert int(value) >= 100
    assert "?v=99" not in html and "?v=99" not in styles
    assert f"/static/js/17-payments.js?v={value}" in html
    for filename in ("16-visual-qa.css", "16-payments.css"):
        assert f"css/{filename}?v={value}" in styles


def test_visual_capture_uses_distinct_server_side_locale_users() -> None:
    capture = (ROOT / "scripts" / "capture_visual_baseline.py").read_text(encoding="utf-8")
    seed = (ROOT / "scripts" / "seed_visual_user.py").read_text(encoding="utf-8")
    assert 'LOCALE_USERS = {"ru": 10001, "en": 10002}' in capture
    assert "BASE_URL_TEMPLATE.format(dev_user=LOCALE_USERS[locale_key])" in capture
    assert "(10001, \"ru\"), (10002, \"en\")" in seed
    assert 'localeContract' in capture
    assert 'paymentPlanCount' in capture and 'paymentProductCount' in capture
    assert "'.nav-btn[data-goto=\"{view_name}\"]'" in capture


def test_chat_surface_has_explicit_ru_en_copy_contract() -> None:
    chat = (ROOT / "miniapp" / "js" / "07-chat.js").read_text(encoding="utf-8")
    assert "const CHAT_I18N =" in chat
    assert "const CHAT_AGENT_EN =" in chat
    assert "Write to " in chat and "Напиши " in chat
    assert "What matters most to notice in this situation?" in chat
    assert "DIALOGUE TOOLS" in chat and "ИНСТРУМЕНТЫ ДИАЛОГА" in chat


def test_payment_surface_has_explicit_ru_en_copy_contract() -> None:
    payments = (ROOT / "miniapp" / "js" / "17-payments.js").read_text(encoding="utf-8")
    assert "const PAYMENT_I18N =" in payments
    assert "const PAYMENT_CATALOG =" in payments
    assert "payLang" in payments and "catalogText" in payments
    assert "Your Crystals" in payments and "Твои Кристаллы" in payments
    assert "Open Stars checkout" in payments and "Открыть оплату Stars" in payments


def test_refactored_backend_boundaries_exist() -> None:
    expected = [
        ROOT / "app" / "api" / "common" / "errors.py",
        ROOT / "app" / "api" / "common" / "validation.py",
        ROOT / "app" / "api" / "contracts" / "chat.py",
        ROOT / "app" / "api" / "contracts" / "compatibility.py",
        ROOT / "app" / "services" / "compatibility.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    assert not missing, "refactored boundary files are missing: " + ", ".join(missing)


# ── ARCH-001..003 monolith split — target structure boundaries ─────────────
# The multi-etap plan (Etap 5) splits app/core/palm.py, app/core/agent.py and
# app/core/tool_registry.py into sub-packages. The scenarios/* split for
# agent.py has already landed (see ADR-0002). These tests encode the
# post-split invariants so the remaining splits can proceed in separate PRs
# without introducing forward-only imports.


def test_scenarios_package_has_expected_modules() -> None:
    """ARCH-002 (agent.py → scenarios/*) already landed — every scenario
    module is present and exports the documented public function."""
    scenarios_dir = ROOT / "app" / "core" / "scenarios"
    for name in ("forecast", "tarot", "compat", "report", "memory"):
        module = scenarios_dir / f"{name}.py"
        assert module.is_file(), f"missing scenario module: {module.relative_to(ROOT)}"


def test_agent_facade_stays_thin() -> None:
    """app/core/agent.py is a compatibility facade — it must NOT grow back
    into a monolith. The facade should stay under 120 lines and contain
    zero prompt strings or business rules."""
    facade = (ROOT / "app" / "core" / "agent.py").read_text(encoding="utf-8")
    lines = facade.splitlines()
    assert len(lines) < 120, (
        f"app/core/agent.py has {len(lines)} lines — the facade is thickening. "
        "Move new logic into app/core/scenarios/<domain>.py instead."
    )
    # No prompt-shaped literals: multiline SYSTEM messages and tool-user
    # instructions belong in scenarios/_impl.py or agents/*/SYSTEM.md.
    banned = ("Правила ", "Реши задачу", "You are ", "Ты — ")
    for token in banned:
        assert token not in facade, (
            f"app/core/agent.py contains prompt-shaped literal {token!r} — "
            "move to scenarios/_impl.py or app/agents/<code>/SYSTEM.md"
        )


def test_scenarios_impl_never_imports_from_agent_facade() -> None:
    """Cycle guard: the facade re-exports from scenarios; scenarios must NOT
    import back from the facade or the whole app.core.agent module."""
    for name in ("_impl", "forecast", "tarot", "compat", "report", "memory"):
        module = ROOT / "app" / "core" / "scenarios" / f"{name}.py"
        if not module.is_file():
            continue
        text = module.read_text(encoding="utf-8")
        assert "from ..agent" not in text and "import ..agent" not in text, (
            f"{module.relative_to(ROOT)}: scenarios must not depend on the facade"
        )


def test_tool_registry_is_the_only_executable_tools_module() -> None:
    """ARCH-003 preparation: SKILL.md files must not contain executable code,
    and app/core/skills.py must remain removed. The architecture lint enforces
    this at CI time; this test provides a fast local signal."""
    assert not (ROOT / "app" / "core" / "skills.py").exists(), (
        "app/core/skills.py returned — it was renamed to tool_registry.py"
    )
    assert (ROOT / "app" / "core" / "tool_registry.py").is_file()
    for skill_md in (ROOT / "app" / "agents").rglob("SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        for fence in ("```python", "```py", "```bash", "```shell"):
            assert fence not in text.lower(), (
                f"{skill_md.relative_to(ROOT)}: SKILL.md must not embed "
                f"executable {fence} blocks — put runnable code in "
                "app/core/tool_registry.py"
            )


def test_palm_module_is_below_the_split_ceiling_or_split() -> None:
    """ARCH-001: app/core/palm.py is split into app/core/palm/{prompts,service}.py.
    The split has landed — enforce the package shape instead of the flat ceiling."""
    palm_pkg = ROOT / "app" / "core" / "palm"
    assert palm_pkg.is_dir(), "app/core/palm package missing"
    for name in ("__init__.py", "prompts.py", "service.py"):
        module = palm_pkg / name
        assert module.is_file(), f"missing palm package module: {module.relative_to(ROOT)}"
    service_lines = (palm_pkg / "service.py").read_text(encoding="utf-8").splitlines()
    assert len(service_lines) < 1200, (
        f"app/core/palm/service.py has {len(service_lines)} lines — keep the "
        "service module from re-growing (ARCH-001)."
    )
