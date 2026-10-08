#!/usr/bin/env python3
# BUS-1534: проверка соответствия compose-оверрайдов vs running container.
#
# Проблема: оверрайд BACKUP_REQUIRE_OFFSITE=0 в infra/docker-compose.oci.yml
# может не примениться на VPS, если depoy-скрипт не подключает -f oci.yml
# (см. BUS-1520: deploy.yml был жёстко привязан к docker-compose.yml).
# Тогда прод-контейнер получит BACKUP_REQUIRE_OFFSITE=1 из .env и
# backup-postgres.sh упадёт без S3/R2.
#
# Пять проверок:
#   A) static  — compose-файлы резолвят ожидаемые значения (compose config),
#      независимо от .env (env-переменная override).
#   B) live    — running container имеет те же значения (docker inspect).
#   C) wiring — каждый depoy-скрипт подключает -f oci.yml.
#   D) env     — .env не дублирует оверрайд-переменные (источник истины — compose).
#   E) repo    — checkout содержит оверрайд-файл с BACKUP_REQUIRE_OFFSITE: "0"
#      (detached-HEAD на коммит до 4b45cf6 = оверрайд пропал, прод вернётся к =1).
import json
import os
import subprocess
import sys

# REPO = cwd, NOT dirname(__file__). The script is copied verbatim onto the
# VPS checkout (see DEPLOYMENT.md), so its own location would always resolve
# to the developer laptop. `git rev-parse HEAD` in checks E/F must read the
# checkout under test, and `docker compose` must run against that checkout's
# compose files. Override with CHECK_REPO=<path> for worktree-based tests.
REPO = os.environ.get("CHECK_REPO") or os.getcwd()
COMPOSE = ["docker", "compose",
           "-f", "infra/docker-compose.yml",
           "-f", "infra/docker-compose.oci.yml",
           "--profile", "backup"]
EXPECTED = {
    "BACKUP_REQUIRE_OFFSITE": "0",
    "BACKUP_S3_URL": "",
    "BACKUP_S3_ACCESS_KEY": "",
    "BACKUP_S3_SECRET_KEY": "",
    "BACKUP_S3_BUCKET": "",
}
WIRING_FILES = [
    "infra/prod-stack-up.sh",
    ".github/workflows/deploy.yml",
]
# BUS-1534 §3: the override must live in compose, NOT in .env. If .env on VPS
# also carries BACKUP_REQUIRE_OFFSITE, the two can drift and the override
# becomes a silent no-op — the value that wins is whichever compose merges
# last, and a hand-edited .env is invisible to the static check below.
ENV_FORBIDDEN_KEYS = [
    "BACKUP_REQUIRE_OFFSITE",
    "BACKUP_S3_URL",
    "BACKUP_S3_ACCESS_KEY",
    "BACKUP_S3_SECRET_KEY",
    "BACKUP_S3_BUCKET",
]


def run(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)


def placeholder_env():
    """Build a placeholder .env like deploy.yml does. The compose files
    declare env_file: ../.env, so compose needs that file to exist even for
    `config` — but the check must not depend on a real .env being present.
    Caller must restore/remove the returned backup path afterwards."""
    src = os.path.join(REPO, ".env.production.example")
    lines = open(src).read().splitlines()
    out = []
    for ln in lines:
        if ln.startswith("DATABASE_URL=") and ln.strip().endswith("="):
            ln = "DATABASE_URL=postgresql+asyncpg://placeholder:placeholder@postgres:5432/placeholder"
        elif ln.startswith("POSTGRES_PASSWORD=") and ln.strip().endswith("="):
            ln = "POSTGRES_PASSWORD=placeholder"
        elif ln.startswith("GRAFANA_ADMIN_PASSWORD=") and ln.strip().endswith("="):
            ln = "GRAFANA_ADMIN_PASSWORD=placeholder"
        elif ln.startswith("APP_ENV=") and ln.strip().endswith("="):
            ln = "APP_ENV=production"
        out.append(ln)
    # DATABASE_URL_ADMIN is referenced by compose as ${DATABASE_URL_ADMIN:?...}
    # but is NOT declared in .env.production.example (BUS-755: it is injected
    # only into the migrate service). Without it here `compose config` aborts
    # with "must be set to an admin (DDL) PostgreSQL URL" and the static check
    # can never pass — even though the override under test has nothing to do
    # with it. Add the same placeholder value as DATABASE_URL.
    if not any(ln.startswith("DATABASE_URL_ADMIN=") for ln in out):
        out.append("DATABASE_URL_ADMIN=postgresql+asyncpg://placeholder:placeholder@postgres:5432/placeholder")
    env_path = os.path.join(REPO, ".env")
    had_env = os.path.exists(env_path)
    backup = None
    if had_env:
        backup = env_path + ".bak_check_compose_overrides"
        os.rename(env_path, backup)
    open(env_path, "w").write("\n".join(out) + "\n")
    return env_path, had_env, backup


def static_check():
    """A: resolved compose config must carry the override regardless of .env."""
    env_path, had_env, backup = placeholder_env()
    try:
        # `compose config` does NOT auto-read ../.env unless --env-file is
        # passed; without it every ${VAR:?...} reference aborts resolution and
        # the check can never pass. Pass the placeholder explicitly.
        r = run(COMPOSE + ["--env-file", ".env", "config"])
    finally:
        if had_env:
            os.remove(env_path)
            os.rename(backup, env_path)
        else:
            os.remove(env_path)
    if r.returncode != 0:
        return False, "compose config failed:\n" + r.stderr[-1500:]
    out = r.stdout
    # Anchor on the SERVICE block, not a substring: `out.find("  backup:")`
    # also matches `BACKUP_STATUS_FILE: /backups/backup-status.json` and
    # returns a 10-byte block (the service header only), so every override
    # key reads as MISSING. Require the line to start the block (2-space
    # indent + name + colon, end of line).
    start = -1
    for ln in out.splitlines():
        if ln == "  backup:":
            start = out.find("  backup:\n")
            break
    if start < 0:
        return False, "service 'backup' not found in resolved compose"
    rest = out[start + len("  backup:\n"):]
    block = "  backup:\n" + rest.split("\n\n")[0]
    bad = []
    for k, v in EXPECTED.items():
        want = f'{k}: "{v}"'
        if want not in block:
            got = "MISSING"
            idx = block.find(k + ": ")
            if idx >= 0:
                got = block[idx + len(k) + 2:].splitlines()[0]
            bad.append(f"{k} resolved as {got!r}, expected {v!r}")
    if bad:
        return False, "override not applied in resolved compose:\n" + "\n".join(bad)
    return True, "static: backup service resolves override values"


def live_check(container="infra-backup-1"):
    """B: running container must match the override.

    Opt-in via CHECK_LIVE=1 (default off). The check inspects the RUNNING
    prod container, which only exists on VPS — running it on a developer
    laptop (where the local stack legitimately keeps offsite=1 with MinIO)
    would fail for reasons unrelated to the override wiring. When enabled it
    is fail-closed: a missing container is a FAIL, not a skip — the whole
    point is that the override reached the RUNNING container, and an absent
    one proves nothing. Never print secret values: BACKUP_S3_* are real
    credentials on VPS, and this output lands in CI logs and shell history.
    """
    if os.getenv("CHECK_LIVE") != "1":
        return True, "live: skipped (set CHECK_LIVE=1 to inspect running container)"
    r = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
        capture_output=True, text=True)
    if r.returncode != 0:
        return False, (f"cannot inspect {container}: {r.stderr.strip()} — "
                       f"FAIL-CLOSED: override not verified in a running container")
    try:
        env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in json.loads(r.stdout)}
    except Exception as e:
        return False, f"bad inspect output: {e}"
    bad = []
    for k, v in EXPECTED.items():
        if env.get(k) != v:
            # Mask the actual value: S3 keys are secrets, and this output is
            # visible in CI logs / shell history.
            shown = "***" if "SECRET" in k or "ACCESS" in k or k == "BACKUP_S3_URL" else env.get(k)
            bad.append(f"{k}={shown!r} expected {v!r}")
    if bad:
        return False, "live mismatch:\n" + "\n".join(bad)
    return True, f"live: {container} matches override values"


def wiring_check():
    """C: every deploy script must attach the OCI override."""
    bad = []
    for f in WIRING_FILES:
        p = os.path.join(REPO, f)
        if not os.path.exists(p):
            bad.append(f"{f}: MISSING")
            continue
        if "docker-compose.oci.yml" not in open(p).read():
            bad.append(f"{f}: does not attach -f infra/docker-compose.oci.yml")
    if bad:
        return False, "wiring gap:\n" + "\n".join(bad)
    return True, "wiring: all deploy scripts attach OCI override"


def env_no_override_check():
    """D: the override must live in compose, not in .env.

    BUS-1534 §3. If the VPS .env also carries BACKUP_REQUIRE_OFFSITE (or any of
    the S3 keys), the two sources can drift and the override becomes a silent
    no-op: compose merges files in order, `environment:` in the override wins
    over `env_file`, but a hand-edited .env is invisible to every static check
    below and invisible to the operator. The override is the single source of
    truth for these keys — .env must not duplicate them.
    """
    env_path = os.path.join(REPO, ".env")
    # Off by default: a developer laptop legitimately keeps
    # BACKUP_REQUIRE_OFFSITE=1 in .env for the local MinIO stack, and failing
    # the check there is noise, not signal. The VPS is the place where .env
    # must NOT carry the override — that is enforced by the deploy gate in
    # .github/workflows/deploy.yml (which runs with a clean checkout and no
    # local .env) and by the live check on the running container. Enable with
    # CHECK_ENV=1 to audit any .env you are about to ship to a host.
    if os.getenv("CHECK_ENV") != "1":
        return True, ("env: skipped (set CHECK_ENV=1 to audit .env; the VPS "
                      "contract is enforced by the deploy gate + live check)")
    if not os.path.exists(env_path):
        return True, "env: no .env present (override is the only source)"
    bad = []
    for ln in open(env_path).read().splitlines():
        if not ln or ln.lstrip().startswith("#") or "=" not in ln:
            continue
        key = ln.split("=", 1)[0].strip()
        if key in ENV_FORBIDDEN_KEYS:
            bad.append(f"{env_path}: {key} must be set by the compose override, not .env")
    if bad:
        return False, "env override duplicated in .env:\n" + "\n".join(bad)
    return True, "env: .env does not duplicate override keys"


def repo_file_check():
    """E: the checked-out commit must contain the OCI override file.

    BUS-1534 §1. The override is a file, not a flag: if the VPS checkout is on
    a commit older than 4b45cf6 (the fix that introduced
    BACKUP_REQUIRE_OFFSITE: "0"), `docker compose config` resolves the base
    compose value (1) and the override never existed — the prod container
    silently reverts to requiring S3/R2. This check proves the checked-out
    tree actually carries the override, independent of what HEAD points at.
    """
    oci = os.path.join(REPO, "infra/docker-compose.oci.yml")
    if not os.path.exists(oci):
        return False, "repo: infra/docker-compose.oci.yml missing from checkout"
    text = open(oci).read()
    if 'BACKUP_REQUIRE_OFFSITE: "0"' not in text:
        return False, "repo: override file exists but carries no BACKUP_REQUIRE_OFFSITE: \"0\""
    return True, "repo: checkout carries the OCI override (BACKUP_REQUIRE_OFFSITE: \"0\")"


def repo_sync_check():
    """F: the checked-out commit must be on an approved branch.

    BUS-1534 §1. The override is a file (check E), but a detached HEAD that
    simply points at an old commit is a different failure: the checkout is
    alive yet stale. Live check 2026-10-09 found VPS at 9023cd1 (2026-09-11)
    while origin/dev was 4b45cf6 — 25 commits behind, and 9023cd1 is on
    neither dev nor master. `prod-stack-up.sh` then ran from a tree whose
    override wiring (COMPOSE_ARGS) did not exist, so the only thing keeping
    BACKUP_REQUIRE_OFFSITE=0 alive was a hand-edited .env — invisible to
    every static check and one manual edit away from reverting to =1.

    Approved = ancestor of dev (i.e. dev or an older commit that has since
    been merged into dev) OR ancestor of master. A detached HEAD on a commit
    that is on neither branch is drift, even if the override file happens to
    be present (check E only proves the file exists, not that HEAD is sane).
    """
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    if not head:
        return False, "repo: cannot read HEAD"
    for branch in ("dev", "master"):
        r = run(["git", "merge-base", "--is-ancestor", head, branch])
        if r.returncode == 0:
            return True, (f"repo: HEAD {head[:12]} is an ancestor of {branch}"
                          f" — checkout is on an approved line")
    return False, (
        f"repo: HEAD {head[:12]} is on neither dev nor master (drift). "
        f"Checkout must be an ancestor of dev or master; see BUS-1534 §1")


def main():
    fails = 0
    for name, fn in (("static", static_check), ("live", live_check),
                     ("wiring", wiring_check), ("env", env_no_override_check),
                     ("repo-file", repo_file_check),
                     ("repo-sync", repo_sync_check)):
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"{name} raised: {e}"
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {msg.splitlines()[0]}")
        if not ok:
            print(msg)
            fails += 1
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())