# OracleAI

OracleAI is a Telegram bot and Mini App for bounded self-reflection through daily rituals, astrology, Tarot, diary practices and AI guides. It is for users **16+** and does not replace medical, psychological, legal or financial support.

## Start

The Docker Compose stack is the supported local path. From the repository root:

```bash
cp .env.example .env
# Set BOT_TOKEN/ADMIN_ID for Telegram flows and at least one LLM provider when needed.
make up
curl http://localhost:8080/api/health
```

Use `APP_ENV=dev DEV_MODE=1` only on a loopback development server. The `dev_user` query parameter bypasses Telegram signature verification and must never be exposed in production. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for deployment and [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for recovery and incident work.

## Stack and boundaries

| Layer | Implementation |
|---|---|
| Client | Telegram Mini App, vanilla JavaScript, modular CSS and Telegram WebApp API. |
| Server | Python, FastAPI, Pydantic and aiogram. |
| Data | PostgreSQL + pgvector (SQLite/WAL fallback was removed). |
| AI | Server-owned agents, deterministic evidence, bounded tools, provider fallback and safety checks. |
| Operations | Docker Compose, Caddy, Redis/Celery scaffolding, migrations, health checks and release gates. |

The bot and Mini App share services, core calculations, repositories and safety boundaries. Domain calculations are produced by code; AI explains supplied evidence and must not invent placements, cards, diagnoses or certainty.

## Validation

```bash
make test             # runs the suite against the Compose stack (PostgreSQL)
# or, given a reachable PostgreSQL and DATABASE_URL:
pytest -q
python3 -m scripts.selfcheck
python3 -m scripts.release_gate
ruff check app scripts tests
python3 -m compileall -q app scripts tests
```

Tests require a PostgreSQL server and `DATABASE_URL`; the SQLite dev/test fallback no longer exists.

## Documentation

Start with the [documentation map](docs/README.md). It identifies one current source of truth for product, architecture, AI, UI, API, security, operations, testing, domain features and release status. 
The repository is currently **BLOCKED** for public launch until the external gates in [`docs/RELEASE/CURRENT_STATUS.md`](docs/RELEASE/CURRENT_STATUS.md) are completed.
