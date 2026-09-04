# OracleAI observability runbook

## Архитектура

По умолчанию Compose запускает Grafana, Loki, Prometheus, Alloy, cAdvisor и node-exporter вместе с приложением. Alloy читает Docker container logs через read-only `/var/run/docker.sock`, добавляет labels `compose_project`, `compose_service` и `container`, затем пишет их в Loki. cAdvisor отдаёт CPU, memory, network и container lifecycle metrics. node-exporter отдаёт host filesystem и system metrics. Grafana автоматически получает Prometheus и Loki datasources и загружает dashboard `OracleAI / OracleAI - Containers & Logs`.

Promtail не используется: он достиг EOL 2 марта 2026 года; для новых развёртываний используется Alloy.[1]

## Запуск

```bash
cp .env.production.example .env
chmod 600 .env
# обязательно задать реальные credentials и заменить GRAFANA_ADMIN_PASSWORD

docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml ps
```

Локальный Docker log rotation ограничивает каждый `json-file` лог до 5 файлов по 10 MB. Loki хранит логи 7 дней; Prometheus хранит metrics 15 дней. Изменить сроки можно в `.env`:

```dotenv
PROMETHEUS_RETENTION=30d
```

Не публикуйте Prometheus, Loki или Alloy наружу. Grafana привязана к `127.0.0.1:3000`; подключайтесь через туннель:

```bash
ssh -N -L 3000:127.0.0.1:3000 deploy@YOUR_VPS
```

## Поиск логов в Grafana

В Explore выберите datasource Loki. Полезные запросы:

```logql
{stack="oracleai"}
{stack="oracleai", compose_service="api"}
{stack="oracleai", compose_service="worker"} |= "ERROR"
{stack="oracleai"} | json | level="ERROR"
```

Приложение пишет JSONL в stdout; поля `release_id`, `operation`, `request_id`, `status_code`, `latency_ms`, `provider` и `event` помогают связать ошибку с релизом и запросом. Не добавляйте user IDs, birth data, payment payloads или API keys в labels: высококардинальные и чувствительные поля должны оставаться только в body лог-записи либо быть замаскированы.

## Metrics и alerts

Prometheus scrape-ит сам себя, cAdvisor, Alloy, node-exporter и `/metrics` API. API metrics intentionally use only `method` and `status` labels, без URL и пользовательских идентификаторов. Встроенные alerts покрывают недоступность observability targets, частые рестарты контейнера, memory pressure и свободное место `/` на VPS. Для production notification receiver добавьте Alertmanager или внешний webhook, не открывая его порт без TLS и authentication.

Примеры PromQL:

```promql
sum(rate(oracleai_http_requests_total{status=~"5.."}[5m]))
histogram_quantile(0.95, sum(rate(oracleai_http_request_duration_seconds_bucket[5m])) by (le))
sum(container_memory_working_set_bytes{name=~"infra-.*"}) by (name)
up{job=~"prometheus|cadvisor|alloy|oracleai-api|node-exporter"}
```

## Troubleshooting

```bash
# все сервисы и health status
docker compose -f infra/docker-compose.yml ps

# последние логи observability
docker compose -f infra/docker-compose.yml logs --tail=200 loki alloy prometheus grafana

# приложение и очереди
docker compose -f infra/docker-compose.yml logs --tail=200 api bot worker beat

# API health и metrics изнутри сети
docker compose -f infra/docker-compose.yml exec -T api curl -fsS http://127.0.0.1:8080/api/health
docker compose -f infra/docker-compose.yml exec -T api curl -fsS http://127.0.0.1:8080/metrics | head

# применить изменённые alert/config files после restart
docker compose -f infra/docker-compose.yml restart prometheus alloy grafana loki
```

Если диск заполняется, сначала проверьте Docker json-file logs и volumes. Не удаляйте `postgres_data`, `grafana_data`, `loki_data` или `prometheus_data` без backup/экспертизы. Для Loki retention нужен writable `loki_data`; при read-only filesystem compactor не сможет удалять истёкшие chunks.

## Security checklist

Docker socket — наиболее чувствительный mount в этом стеке: Alloy получает доступ к Docker metadata и logs, cAdvisor — runtime statistics. Не публикуйте их HTTP ports. Grafana должна иметь сильный unique admin password, а доступ — через SSH tunnel, private network или reverse proxy с SSO/TLS. Production `.env`, SSH keys и backup encryption key не коммитятся; GitHub Actions получает только deploy secrets, а production `.env` остаётся на VPS.[2]

## References

[1]: [Grafana Promtail EOL notice](https://grafana.com/docs/loki/latest/send-data/promtail/) и [Grafana Alloy Docker monitoring](https://grafana.com/docs/alloy/latest/monitor/monitor-docker-containers/).
[2]: [GitHub Actions secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) и [Docker Compose environment variables](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
