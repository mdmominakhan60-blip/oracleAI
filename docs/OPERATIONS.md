# OracleAI — operations

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Provide the operational map for running, deploying, monitoring and recovering OracleAI. |
| **Source of truth** | `infra/docker-compose.yml`, `infra/Dockerfile`, `Makefile`, `app/config.py`, `scripts/` and the linked runbooks below. |
| **Scope** | Local Docker stack, production prerequisites, migrations, worker scheduling, backup/restore and incident response. |
| **Do not change** | Do not enable dev authentication in production, publish secrets, skip migrations, or claim a local smoke check is production evidence. |
| **Key files** | `Makefile`, `infra/docker-compose.yml`, `scripts/selfcheck.py`, `scripts/release_gate.py`, `docs/DEPLOYMENT.md`. |
| **Validation** | `make selfcheck`, `python3 -m scripts.release_gate`, `python3 -m scripts.check_repository_hygiene`, and the applicable restore/worker checks. |

## Operational entry points

| Need | Read / run |
|---|---|
| Start the complete local stack | [`DEPLOYMENT.md`](DEPLOYMENT.md), then `make up`. |
| Inspect services and logs | `make ps`, `make logs`, `docker compose -f infra/docker-compose.yml ps`. |
| Validate configuration and contracts | `make selfcheck`, `python3 -m scripts.release_gate`. |
| Apply PostgreSQL migrations | The Compose `migrate` service (see `DEPLOYMENT.md`). |
| Operate background jobs | [`CELERY_REDIS.md`](CELERY_REDIS.md), `make worker-scale N=3`. |
| Back up or restore | [`BACKUP_RESTORE_DRILL.md`](BACKUP_RESTORE_DRILL.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md). |
| Respond to an incident | [`INCIDENT_RESPONSE_RUNBOOK.md`](INCIDENT_RESPONSE_RUNBOOK.md). |
| Check current launch state | [`RELEASE/CURRENT_STATUS.md`](RELEASE/CURRENT_STATUS.md). |

## Runtime topology

The production-shaped Compose stack contains an application image, PostgreSQL with pgvector, Redis, a one-shot migration service, API, Telegram bot, Celery worker, Celery Beat and Caddy. PostgreSQL is the only supported backend — `DATABASE_URL` is required and SQLite/WAL fallback was removed. The presence of PostgreSQL/Celery scaffolding is not itself evidence that the production data plane has been certified.

The API and bot share domain services and repositories. Background jobs must re-check the same eligibility and safety boundaries as the enqueue path. A local in-process limiter is suitable only for the documented single-process or controlled-beta boundary; distributed deployment requires shared rate-limit and capacity evidence.

## Environment and release safety

`.env.example` is the development template and `.env.production.example` is the production checklist. Real credentials belong outside Git. Production must use `DEV_MODE=0`, a real HTTPS `WEBAPP_URL`, valid Telegram and provider configuration, a release identifier and the approved storage/backup settings. Empty provider credentials may leave the application in offline fallback; they do not close the live-provider gate.

Before a release, run the repository’s applicable checks, inspect the diff, apply migrations in a disposable environment, verify health and security headers, and record results in the evidence directory. The release decision is **NO-GO** while any P0 gate in [`RELEASE/TASKS.md`](RELEASE/TASKS.md) is open.

## Recovery and incidents

The PostgreSQL restore path is intentionally disposable and synthetic. It demonstrates integrity and isolation of the tested path, not production key custody, object-storage permissions, retention policy or rollback readiness. It is exercised via `infra/restore-postgres.sh` and the `make migrate`/`make selfcheck` sequence. Those external checks must be executed with the operator’s approved infrastructure and recorded without secrets or user data.

Incident severity, ownership, first response, evidence capture and scenario playbooks are defined in [`INCIDENT_RESPONSE_RUNBOOK.md`](INCIDENT_RESPONSE_RUNBOOK.md). Safety, privacy, payment, provider, scheduler and restore incidents must preserve correlation IDs and redact user content from operational evidence.

## References

[1]: [Makefile](../Makefile) — supported operator commands.
[2]: [infra/docker-compose.yml](../infra/docker-compose.yml) — service topology and dependencies.
[3]: [app/config.py](../app/config.py) — runtime configuration names and defaults.
[4]: [scripts/release_gate.py](../scripts/release_gate.py) — release readiness checks.
