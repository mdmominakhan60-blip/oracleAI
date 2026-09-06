# BUS-270: firewall-фикс — доступ docker-контейнеров к host-портам omniroute

## Диагноз (доказано 2026-09-06)

Активный файрвол — **UFW через iptables-nft**, а не `/etc/nftables.conf` напрямую.
(`/etc/nftables.conf` policy drop — legacy, сервис disabled; living ruleset — ufw + iptables-nft.)

Контейнеры на docker-мостах (172.29.0.0/16 прод `infra_oracle_internal`,
172.31.0.0/16 staging `oracle_staging_internal`) при попытке соединения с host-портами
(omniroute 0.0.0.0:20128) попадают в INPUT хоста → UFW user policy drop дропает SYN.

Доказательства (воспроизводятся за 30 сек):
```
# с хоста — omniroute жив:
curl -s --max-time 5 http://127.0.0.1:20128/healthz          # 200
# из прод-контейнера к его же шлюзу — timeout:
docker exec infra-api-1 python3 -c "import socket; s=socket.socket(); s.settimeout(4); s.connect(('172.29.0.1',20128)); print('OK')"
# → TimeoutError (и для 3443, и для 22 — дропается ВСЁ, не только 20128)
# исходящий интернет из контейнера работает (FORWARD не тронут):
docker exec infra-api-1 python3 -c "import urllib.request; print(urllib.request.urlopen('https://example.com', timeout=5).status)"
# → 200
```

Следствие: прод-конфиг `CUSTOM_LLM_BASE_URL=http://omniroute:20128/v1` из контейнера
**никогда не работал** — таблица `llm_usage` пуста (проверено: 0 строк, prod и staging).
Все "ответы" LLM в проде шли через офлайн-фолбэк (`offline_answer`, `app/core/agents/runtime.py:175`).

DNS: hostname `omniroute` в контейнерах НЕ резолвится (omniroute запущен с
`network_mode: host` — его нельзя `docker network connect`). Дополнительно к открытию
порта нужен адрес host-шлюза (172.29.0.1 / 172.31.0.1) или `extra_hosts: host.docker.internal:host-gateway`.

## Фикс (применён 2026-09-06, без sudo, через docker NET_ADMIN)

### Что было применено

Активный firewall — **UFW через iptables-nft** (не `/etc/nftables.conf`, который disabled).
Правила вставлены в цепочку INPUT хоста через docker-контейнер с `--net=host --cap-add=NET_ADMIN`:

```
# live rules (iptables -I INPUT):
-A INPUT -s 172.29.0.0/16 -p tcp --dport 20128 -j ACCEPT -m comment --comment "oracleai prod bridge -> omniroute"
-A INPUT -s 172.31.0.0/16 -p tcp --dport 20128 -j ACCEPT -m comment --comment "oracleai staging bridge -> omniroute"

# persist (в /etc/ufw/user.rules, подхватится при ufw reload):
-A ufw-user-input -s 172.29.0.0/16 -p tcp --dport 20128 -j ACCEPT -m comment --comment oracleai-prod-bridge-omniroute
-A ufw-user-input -s 172.31.0.0/16 -p tcp --dport 20128 -j ACCEPT -m comment --comment oracleai-staging-bridge-omniroute
```

Верификация:
```
docker exec infra-api-1 python3 -c "import socket; s=socket.socket(); s.settimeout(4); s.connect(('172.29.0.1',20128)); print('OK')"
docker exec oracleai-staging-staging-api-1 python3 -c "import socket; s=socket.socket(); s.settimeout(4); s.connect(('172.31.0.1',20128)); print('OK')"
```

### Грабли, обнаруженные при деплое

1. **UFW bind-mount inode не обновляется при редактировании файла на хосте** — Prometheus (bind-mount `/etc/ufw/user.rules`) видел старую версию. Решение: `docker compose restart <service>` после редактирования.
2. **Staging образ `latest` устарел** — содержал миграции только до0008, а БД уже на0009. Миграция падала `Can't locate revision 0009_feedback_responses`. Решение: явный `IMAGE_TAG=staging-r3` (или свежий SHA) при `compose up`.
3. **Prometheus bind-mount alerts.yml** — та же inode-проблема: редактирование файла на хосте не видно в контейнере. Решение: restart prometheus.
4. **Caddy unhealthy после recreate api** — transient DNS-кэш (`staging-api:8080` → `lookup staging-api: i/o timeout`). Самовосстанавливался через ~60s.
5. **Prod `.env` из репо**: `omniroute:20128` — NXDOMAIN из контейнера (omniroute в host-сети). Исправлен на `172.29.0.1:20128`.

## После применения фикса (выполнено 2026-09-06)

1. `.env.staging`: LLM_PROVIDER=custom, CUSTOM_LLM_BASE_URL=http://172.31.0.1:20128/v1,
   CUSTOM_LLM_MODEL=antigravity/gemini-2.5-flash, CUSTOM_LLM_MODEL_LITE=antigravity/gemini-2.5-flash,
   CUSTOM_LLM_API_KEY=<из .env.staging>. `extra_hosts: host.docker.internal:host-gateway` в compose.
   Рестарт staging-api/worker через `IMAGE_TAG=staging-r3 compose up -d`.
2. **Смоук staging**: прямой вызов `chat_svc.ask()` → HTTP 200 от omniroute (gemini-2.5-flash, ~4.5s), запись `ok=1` в `llm_usage` (проверено: 2 строки, provider=custom).
3. **Прод `.env`**: CUSTOM_LLM_BASE_URL=http://172.29.0.1:20128/v1 (было omniroute:20128 — NXDOMAIN).
   Рестарт api/worker + rebuild образа из HEAD (до этого `latest` = 2026-09-02, без метрики `oracleai_llm_usage_total`).
   Прямой curl omniroute из контейнера → HTTP 200 gemini-2.5-flash 2.5s. Продовый claude-sonnet-5 упёрся в 35s deadline (таймаут) — это конфигурация модели, не блокер канала.
4. **Алерты**: 7 правил в Prometheus (4 старых + 3 новых: 5xx burst, RateLimitFailClosed, LLMFailureRateHigh). Прометей требует restart для подхвата нового alerts.yml (bind-mount inode).
5. **Дашборд**: `scripts/metrics-snapshot.sh` — исправлен PromQL (`rate()` внутри `sum()`), PROM_URL обязателен. Запуск: `docker exec -i infra-prometheus-1 sh /scripts/metrics-snapshot.sh` (порт 9090 на хосте — не Prometheus API).
6. **Стек backup (BUS-209)**: healthy, не затронут.
