# BUS-1554 / BUS-1545D — CEO-эскалация: CTO-разбор конфигурационного блокера прода

Дата отчёта: 2026-10-10 (пробы проведены ~11:20–12:00Z и повторно девушены 12:30Z)
Владелец: CTO (5fe456df)
Родитель: BUS-1545 (PM: ценность продукта сломана 30+ дней, CEO-эскалация)

Этот документ — CTO-слой поверх живого отчёта BUS-1564
(`docs/RELEASE/reports/2026-10-10-bus1564-live-reverify.md`), который уже содержит
часть тех же фактов с live-пробами. Здесь фиксируется то, что добавлено в этом
ране: корневая причина мёртвой LLM-цепочки, корректировка диагноза из заголовка
задачи, состояние кода и его тестового покрытия.

---

## 1. Корректировка диагноза из заголовка задачи

Заголовок BUS-1554 утверждает: «отсутствие LLM-credentials». **Это утверждение
неверно и вводит в заблуждение.** Живые пробы на прод-стеке:

| Проба | Команда | Результат |
|---|---|---|
| Шлюз с ключом приложения | `curl -X POST http://127.0.0.1:20128/v1/chat/completions -H "Authorization: Bearer $CUSTOM_LLM_API_KEY"` | **200**, `choices[0].message.content = "ok"` |
| Ключ в контейнере | `docker exec infra-api-1 printenv CUSTOM_LLM_API_KEY` | `len=15`, непустой (`omniroute-local`) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | тот же способ | `len=0` (пусты — но это не блокер) |
| Лог шлюза | `docker logs omniroute` | `status=200, errorClass=null`, реальная генерация токенов |

**Вывод:** LLM-креды в окружении **есть** и рабочий канал существует. Пустые
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` — не корень: `LLM_PROVIDER=auto`, рабочий
канал — `custom` → шлюз omniroute. Формулировка задачи (и её требование
«заполнить Anthropic/OpenAI/antigravity») направляет владельца не туда.

---

## 2. Истинный корень мёртвой LLM-цепочки (новая находка)

```
infra-api-1    CUSTOM_LLM_BASE_URL = http://127.0.0.1:20128/v1   → connection refused
infra-worker-1 CUSTOM_LLM_BASE_URL = http://127.0.0.1:20128/v1   → connection refused
infra-beat-1   CUSTOM_LLM_BASE_URL = http://127.0.0.1:20128/v1   → connection refused
infra-bot-1    CUSTOM_LLM_BASE_URL = http://127.0.0.1:20128/v1   → connection refused
```

Внутри контейнера `127.0.0.1` — это сам контейнер, а не хост, где слушает шлюз
на порту 20128. Доказательство прямым замером из контейнера:

```
docker exec infra-api-1 curl http://127.0.0.1:20128/v1/models          -> HTTP 000 (refused)
docker exec infra-api-1 curl http://host.docker.internal:20128/v1/models -> HTTP 401 (шлюз жив)
```

И соответственно живой прогон приложочного вызова:

```
docker exec infra-api-1 python -c "... await llm.complete('Ты тест.', 'скажи ровно ok')"
→ custom/complete попытка 1: Connection error.
→ custom/complete попытка 2: Connection error.
→ RuntimeError: Все LLM-провайдеры недоступны: custom: Connection error.
```

**Правильное значение** — `http://host.docker.internal:20128/v1`. Инфраструктура
для него уже готова: `infra/docker-compose.oci.yml:44-59` добавляет
`host.docker.internal:host-gateway` в `api`, `bot`, `worker` и `beat` (BUS-1528
добавлял ровно этот `extra_hosts` для worker/beat по той же причине). То есть
со стороны инфры расхождение одно: само значение переменной.

Это и объясняет `events=0`, `llm_usage=0`, `daily_stats=0`, `chat_requests=0` —
не «отсутствие ключей», а недостижимый базовый URL.

**Владелец фикса:** DevOps (51e50972) — правка `.env`.

---

## 3. BOT_TOKEN — подтверждён и остаётся board-only

```
docker exec infra-bot-1 sh -c 'echo $BOT_TOKEN | cut -c1-14'   -> 123456:ABC......
docker logs infra-bot-1                                        -> TelegramUnauthorizedError: Unauthorized
docker inspect infra-bot-1 --format '{{.RestartCount}}'        -> 59
```

`RestartCount=59` — это прямое измерение цикла падений. Путь падения:
`app/bot/main.py` → `await bot.delete_webhook(drop_pending_updates=True)` →
`TelegramUnauthorizedError` без `try/except` → процесс завершается → снимает
`scheduler` (единственный исполнитель ingestion/deliveries/retention).

Настоящего токена нет ни в одном источнике, доступном агенту — см. §5 отчёта
BUS-1564 (токен в контейнере побайтово равен токену из другого репо-проекта и
оба — placeholder). Снятие блокера — **board/owner**, не агент.

**Важно:** фикс `try/except` в коде НЕ лечит корень (невалидный токен), но
меняет картину — при placeholder-токене бот перестаёт падать каждые ~8 с, и
`scheduler` наконец стартует. Это стоит зафиксировать как ожидаемое поведение,
а не как «починилось».

---

## 4. APP_ENV=dev при DEV_MODE=0 — молчаливый обход fail-closed проверки

```
infra-bot-1 / infra-api-1:  APP_ENV=dev,  DEV_MODE=0
```

`_validate_production_config()` триггерилась по `APP_ENV in {dev, test}` →
`return` до всех остальных проверок. Следствие: placeholder-`BOT_TOKEN`, пустые
`ADMIN_ID` / `WEBAPP_URL` / `RELEASE_ID` проходили без единой жалобы. Замеры:

```
infra-api-1:  ADMIN_ID len=0 | WEBAPP_URL len=0 | RELEASE_ID len=0
              POSTGRES_PASSWORD len=6 ("oracle" — шаблонное значение)
```

Другими словами: fail-closed проверка, которую мы держим как гарантию
«не подаём неправильно сконфигурированное», на проде была выключена де-факто.

---

## 5. Состояние кода (задача в режиме implementation)

Локальные правки рабочего дерева по BUS-1545:

| Файл | Что |
|---|---|
`app/bot/main.py` | `try/except` вокруг `delete_webhook` — бот не падает на прошедшем revoke/placeholder токене, scheduler стартует
`app/api/main.py` | `_is_placeholder_bot_token()` — детектор placeholder-BOT_TOKEN |
`app/api/main.py` | `_llm_credentials_present()` + `_is_placeholder_secret()` — fail-closed на отсутствие LLM-кред |
`app/api/main.py` | `_validate_production_config()` — триггер переведён с `APP_ENV` на боевой режим `DEV_MODE=0`

### 5.1 Регрессия, найденная и исправленная в этом же ране

Две из четырёх правок выше были в рабочем дереве при входе в ран и **ломали
тесты**. Проверка `.venv/bin/python -m pytest tests/test_security_regressions.py`
дала 2 FAILED до моих изменений:

1. `test_production_config_rejects_dev_mode_in_production` — DID NOT RAISE.
   Причина: ранняя версия триггера `if settings.dev_mode: return` выключала
   проверку **полностью** при `DEV_MODE=1`, включая запрещённую комбинацию
   `APP_ENV=production + DEV_MODE=1` (обход подписи Telegram). Это ослабление
   fail-closed ровно того класса, который запрещено ослаблять. Исправлено:
   проверка теперь пропускается только для честной локальной разработки
   (`DEV_MODE=1` **и** `APP_ENV not in {production, prod}`); при `DEV_MODE=1`
   на `APP_ENV=production` добавлен отдельный пункт в `missing`.

2. `test_production_config_accepts_safe_runtime_configuration` — RuntimeError.
   Причина: `_is_placeholder_secret` использовал голую подстроку `123456`
   как маркер заглушки. Реальный по форме ключ (`sk-ant-…`, содержит цифры)
   ловился как placeholder. Исправлено: у префиксов `sk-*` — короткий хвост
   (<20) либо чистые цифры; нестандартные ключи (локальный шлюз
   `omniroute-local`) проверяются только по слабой энтропии (1–2 различных
   символа либо чистые цифры).

### 5.2 Тестовое покрытие добавлено

Новые тесты в `tests/test_security_regressions.py`:

- `test_placeholder_bot_token_detected` (параметризован, 6 кейсов)
- `test_real_bot_token_not_flagged_as_placeholder` — защита от обратной
  ошибки: настоящий формат `<bot_id>:<43+ base64url>` не должен ловиться
- `test_placeholder_secret_detection` (параметризован, 12 кейсов)
- `test_production_config_still_fail_closed_when_dev_mode_on` — регресс-замок
  на ослабление проверки из §5.1
- `test_production_config_rejects_placeholder_bot_token` — блокер прод-старта
  на placeholder-токене

---

## 6. Что осталось заблокировано и кто снимает

| # | Блокер | Кто снимает | Тип | Статус |
|---|---|---|---|---|
| 1 | `CUSTOM_LLM_BASE_URL` → `http://host.docker.internal:20128/v1` во всех 4 сервисах (правка `.env`) | DevOps (51e50972) | конфиг | **открыт** |
| 2 | Реальный `BOT_TOKEN` в `.env` (ротация отозванного placeholder) | board / owner-человек | board-only секрет | **открыт** |
| 3 | Восстановить `.env` — его нет в файловой системе, compose не резолвится при рестарте | DevOps / owner | конфиг | **открыт** |
| 4 | `APP_ENV=dev` → `production`, заполнить `ADMIN_ID`/`WEBAPP_URL`/`RELEASE_ID` | DevOps / owner | конфиг | **открыт** |
| 5 | Подтверждение модели: `CUSTOM_LLM_MODEL=oc/claude-sonnet-5` фактически отдаётся как `opencode-zen/step-5-preview-free` — P0-003 пересертифицировать или сменить канал | CTO + DevOps | архитектура | **открыт** |

Блокеры 1–4 — чужая зона (DevOps/board). Мой код-слой сделан и покрыт тестами,
но прод он не чинит: задеплоенный образ (`docker exec infra-bot-1 grep -c
"не удалось сбросить вебхук" /opt/oracle/app/bot/main.py` → `0`) старше правок.

---

## 7. Рекомендация

1. **DevOps:** правка `.env` — `CUSTOM_LLM_BASE_URL=http://host.docker.internal:20128/v1`,
   `APP_ENV=production`, заполнить `ADMIN_ID`/`WEBAPP_URL`/`RELEASE_ID`,
   восстановить сам `.env` из `.env.production.example` + секреты владельца.
   Без `.env` стек переживёт рестарт.
2. **Board/owner:** ротация `BOT_TOKEN` — единственный способ убрать
   `RestartCount` из полного цикла падений.
3. **DevOps после правки `.env`:** рестарт `bot/worker/beat` + проверка
   `llm_usage.ok=1` и `events>0` — это product-acceptance, о котором просит
   BUS-1545.
4. **Модель (пункт 5 таблицы):** отдельная задача — зафиксировать, какая модель
   фактически обслуживает продукт, иначе P0-003 сертифицирован не на том канале.

---

## Evidence

- `curl -X POST http://127.0.0.1:20128/v1/chat/completions` (с ключом
  приложения) → 200, `content="ok"` — LLM-канал жив.
- `docker exec infra-api-1 curl 127.0.0.1:20128` → 000;
  `host.docker.internal:20128` → 401 — корень §2.
- `llm.complete(...)` в `infra-api-1` → `Все LLM-провайдеры недоступны`.
- `infra-bot-1` → `RestartCount=59`, `BOT_TOKEN=123456:ABC...`,
  `TelegramUnauthorizedError`.
- `docker exec infra-bot-1 grep -c "не удалось сбросить вебхук"` → `0` — фикс
  кода не задеплоен.
- `.env` отсутствует (`ls -a` → только `.env.example`,
  `.env.production.example`).
- `.venv/bin/python -m pytest tests/test_security_regressions.py` → 22 passed
  после исправления регрессий; до исправления — 2 FAILED.
- Родственный отчёт с live-пробами: `docs/RELEASE/reports/2026-10-10-bus1564-live-reverify.md`.
