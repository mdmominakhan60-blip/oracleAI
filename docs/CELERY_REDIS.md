# Celery + Redis background jobs

OracleAI uses **Celery 5.6 + Redis 7** for heavy LLM and maintenance work that should not block FastAPI request handling. PostgreSQL remains the durable source of truth for application data and the `task_jobs` status projection; Redis transports Celery messages and short-lived task results.

> Redis is a transport and broker, not the durable user-visible job ledger. A job is considered observable only after its `task_jobs` row has been created in PostgreSQL.

## Runtime topology

| Component | Responsibility | Required configuration |
| --- | --- | --- |
| FastAPI API | Authenticates requests, creates a durable queued row, publishes a Celery message, exposes status polling | `CELERY_ENABLED=1`, `REDIS_URL`, `DATABASE_URL` |
| Redis | Broker and Celery result backend | Persistent volume, `noeviction`, protected network access |
| Celery worker | Executes `oracle.llm.chat`, `oracle.llm.forecast`, and `oracle.maintenance` | Same code, `REDIS_URL`, `DATABASE_URL`, LLM credentials if needed |
| Celery Beat | Publishes hourly maintenance task | Exactly one Beat instance |
| PostgreSQL | User data, chat history, LLM usage and durable `task_jobs` projection | Alembic head applied before API/worker rollout |
| Telegram bot | Owns Telegram polling and outbound delivery lifecycle | Do not move Telegram delivery into Celery until delivery idempotency is explicit |

The worker uses late acknowledgements, rejects tasks when a worker is lost, prefetches one task per process, and applies hard/soft time limits from environment variables. The `llm` and `maintenance` queues are routed separately so operational work cannot silently consume the entire LLM worker capacity.

## Database migration

For a PostgreSQL database that was already upgraded to `0001_pg_baseline`, apply the durable queue migration before enabling the API endpoint:

```bash
DATABASE_URL=postgresql+asyncpg://oracle:password@db:5432/oracle \
  alembic upgrade head
```

Revision `0002_task_jobs` creates `task_jobs` and these indexes:

| Index | Purpose |
| --- | --- |
| `idx_task_jobs_status_available` | Finds queued/retry jobs eligible for operational inspection or future claim logic |
| `idx_task_jobs_user_created` | Lists a user’s newest jobs efficiently |

Application startup does not create or alter schema. Alembic is the only schema authority, so every environment must run `alembic upgrade head` before enabling the API, worker or Beat. The migration service in Compose enforces this ordering.

## Environment

Copy the relevant values into `.env`. Production must use a private Redis URL and a PostgreSQL URL; never expose either service directly to the public internet.

```dotenv
DATABASE_URL=postgresql+asyncpg://oracle:strong-password@postgres:5432/oracle
REDIS_URL=redis://redis:6379/0
CELERY_ENABLED=1
CELERY_TASK_ALWAYS_EAGER=0
CELERY_TASK_TIME_LIMIT=300
CELERY_TASK_SOFT_TIME_LIMIT=270
CELERY_VISIBILITY_TIMEOUT=3600
CELERY_WORKER_PREFETCH=1
CELERY_MAX_RETRIES=3
```

`CELERY_TASK_ALWAYS_EAGER=1` is suitable only for deterministic local tests. It executes work in the request process and is not asynchronous production behavior. Keep `LLM_PROVIDER=off` for offline smoke tests; production workers inherit the configured provider and credentials through the same environment file as the API.

## Docker Compose operation

The supplied Compose file has dedicated `redis`, `worker`, and `beat` services. The API, worker, and Beat explicitly set `CELERY_ENABLED=1` and wait for the Redis health check. Start the stack after applying migrations:

```bash
cp .env.example .env
# Edit .env with real, private deployment values.
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml run --rm api alembic upgrade head
docker compose -f infra/docker-compose.yml up -d
```

Check the services and worker connectivity:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs --tail=100 worker beat redis
# The worker name is shown at startup; use it for a targeted ping if needed.
docker compose -f infra/docker-compose.yml exec worker \
  celery -A app.queue:celery_app inspect ping
```

Run exactly one Beat service. Running two Beat instances will publish duplicate periodic tasks. Worker replicas are safe for queue processing, but each replica must use the same Redis and PostgreSQL settings. Keep the API at one process until the existing process-local rate limiter is moved to shared storage.

## API contract

The authenticated endpoint queues an LLM chat request and returns immediately:

```http
POST /api/jobs/chat/{agent}?thread_id=123
Content-Type: application/json

{"text":"...", "allow_paid":false}
```

A successful enqueue returns HTTP `202` with a small acknowledgement:

```json
{"job_id":"<uuid>","status":"queued","kind":"llm.chat"}
```

Poll the user-scoped status endpoint:

```http
GET /api/jobs/<job_id>
GET /api/jobs?limit=20
```

The response exposes status, timestamps, attempts, sanitized error text, and a decoded `result` after success. The submitted prompt is deliberately not echoed by the API. A job belonging to another authenticated user is returned as `404`, preventing cross-user status discovery. Unknown agent codes are also rejected with `404`; enqueue is protected by the existing `llm` rate-limit bucket.

The status lifecycle is:

```text
queued -> running -> succeeded
                 \-> retry -> running
                 \-> failed
```

The Celery result backend is not the API contract. Clients should poll PostgreSQL-backed `/api/jobs/{job_id}` and treat `succeeded` and `failed` as terminal states.

## Retry and failure behavior

Each task creates its own asyncio event loop and database handle. No asyncpg connection is shared between Celery task invocations or event loops. Transient exceptions update `task_jobs.status` to `retry`, persist the error and next availability time, then use Celery retry with bounded exponential delay. After `CELERY_MAX_RETRIES`, the durable row becomes `failed`.

The `task_jobs.attempts` counter increments when a worker begins an attempt. A success writes the decoded task result to `result_json`; a terminal failure writes a bounded error string. Status updates protect successful jobs from a late failure overwrite. Workers use late acknowledgements so a process loss can return an unacknowledged message to Redis, but task bodies must remain safe to retry. Chat persistence and billing code therefore remain in the existing service transaction; Telegram outbound delivery is intentionally outside this first queue integration.

## Local verification

Start Redis and a worker against isolated local services:

```bash
redis-server --port 6379 --daemonize yes

DATABASE_URL=postgresql+asyncpg://oracle_test:oracle_test@127.0.0.1:5432/oracle_test \
REDIS_URL=redis://127.0.0.1:6379/15 \
CELERY_ENABLED=1 LLM_PROVIDER=off \
celery -A app.queue:celery_app worker \
  --loglevel=INFO --pool=solo --queues=llm,maintenance
```

Run the repository smoke script from the project root:

```bash
DATABASE_URL=postgresql+asyncpg://oracle_test:oracle_test@127.0.0.1:5432/oracle_test \
REDIS_URL=redis://127.0.0.1:6379/15 \
CELERY_ENABLED=1 LLM_PROVIDER=off \
python3 scripts/celery_smoke.py
```

The expected evidence is a `queued` row followed by `running` and `succeeded`, `attempts=1`, and a non-null `result_json`. For HTTP verification, start FastAPI with the same variables, POST to `/api/jobs/chat/oracle?dev_user=<isolated-user>`, and poll the returned job ID until it is terminal.

## Operational safeguards

Do not enable `CELERY_ENABLED=1` before Redis is reachable and the PostgreSQL `0002_task_jobs` migration has succeeded. Do not point the smoke script, worker, or API at production data. Keep Redis authentication/TLS and network policy at the deployment layer appropriate for the provider. Back up PostgreSQL as the durable source of job history; Redis persistence protects queued messages but is not a substitute for database backups.

If Redis is unavailable during enqueue, the service marks the durable row as failed and returns HTTP `503`. If the worker is unavailable after enqueue, the API may continue to return `queued` until the broker visibility/retry policy or an operator intervention exposes the incident. Monitor queue depth, oldest queued age, worker process health, retry rate, failed jobs, Redis memory pressure, and PostgreSQL `task_jobs` growth before increasing concurrency.
