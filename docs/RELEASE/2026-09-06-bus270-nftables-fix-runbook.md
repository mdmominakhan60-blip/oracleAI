# BUS-270: nftables-фикс — доступ docker-контейнеров к host-портам omniroute

## Диагноз (доказано 2026-09-06)

`/etc/nftables.conf`: chain input `policy drop`, разрешены только loopback / icmp / ssh
(порт 22 при этом не слушается — sshd-unix-local.socket только AF_UNIX; но это вне скоупа).

Контейнеры на docker-мостах (172.29.0.0/16 прод `infra_oracle_internal`,
172.31.0.0/16 staging `oracle_staging_internal`) при попытке соединения с host-портами
(omniroute 0.0.0.0:20128) попадают в INPUT хоста → правило `policy drop` молча дропает SYN.

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

## Фикс (требует root — sudo недоступен из heartbeat-рана)

### Вариант A (рекомендую): разрешить input с docker-мостов

Смысл: контейнеры — доверенная зона хоста; их трафик к host-портам
(omniroute:20128, prometheus, sshd в будущем) легитимен. Прочий input снаружи остаётся закрыт.

Файл `/etc/nftables.conf`, внутрь `chain input` добавить ПОСЛЕ правила loopback:
```
    # docker-мосты oracleAI (prod 172.29, staging 172.31, infra-observability 172.28):
    # доступ контейнеров к host-портам (omniroute:20128 и локальные сервисы)
    iifname { "br-2cae27dfc183", "br-53266196aaf5", "br-52b419336947" } accept comment "docker bridges oracleai"
```
Имена интерфейсов проверить ПЕРЕД применением (`ip -br link | grep br-`):
- br-2cae27dfc183 = 172.29.0.1/16 — infra_oracle_internal (прод)
- br-53266196aaf5 = 172.31.0.1/16 — oracle_staging_internal (staging)
- br-52b419336947 = 172.28.0.1/16 — наблюдаемость/прочее (по факту 06-09)

Альтернатива без привязки к именам интерфейсов (устойчива к пересозданию мостов,
но шире): `ip saddr 172.16.0.0/12 accept`.

Применение и проверка:
```
sudo nft -f /etc/nftables.conf          # атомарная замена ruleset (conntrack не рвёт)
# проверка из контейнера:
docker exec infra-api-1 python3 -c "import socket; s=socket.socket(); s.settimeout(4); s.connect(('172.29.0.1',20128)); print('OK')"
docker exec oracleai-staging-staging-api-1 python3 -c "import socket; s=socket.socket(); s.settimeout(4); s.connect(('172.31.0.1',20128)); print('OK')"
```
Устойчивость: docker при пересоздании сетей может сменить имя br-<hash>.
`ip saddr 172.16.0.0/12` от этого не зависит — вариант на выбор root-оператора.

### Вариант B (fallback, если input трогать нельзя): отдельный bridge для omniroute

Перевести omniroute с `network_mode: host` на bridge-сеть сPublished портом:
это рестарт omniroute (SPOF для всех claude-агентов хоста) — делать ТОЛЬКО
в согласованное окно, не из heartbeat-рана. Не рекомендуется.

## После применения фикса (DevOps Engineer, без root)

1. `.env.staging`: LLM_PROVIDER=custom, CUSTOM_LLM_BASE_URL=http://172.31.0.1:20128/v1,
   CUSTOM_LLM_MODEL=antigravity/gemini-2.5-flash, CUSTOM_LLM_MODEL_LITE=antigravity/gemini-2.5-flash,
   CUSTOM_LLM_API_KEY=omniroute-local (omniroute не проверяет ключ — проверено 200 с Bearer wrong-key).
   Рестарт staging-api/worker: `docker compose -p oracleai-staging -f infra/staging/docker-compose.staging.yml --env-file infra/staging/.env.staging up -d staging-api staging-worker`
2. Смоук: POST /api/chat → 200 + строка ok=1 в llm_usage (staging-БД).
3. Прод `.env`: CUSTOM_LLM_BASE_URL=http://172.29.0.1:20128/v1 (сейчас http://omniroute:20128 — NXDOMAIN).
   Рестарт api/worker прод-стека + тот же смоук.
4. Алерты и дашборд (уже в репо после коммита BUS-270) подхватываются автоматически.
