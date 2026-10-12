# OracleAI V2 — production-сборка и переключение

Новый интерфейс (React + Vite) живёт рядом с legacy `miniapp/`. По умолчанию
production раздаёт **legacy**; V2 включается серверным флагом и так же
выключается — без пересборки legacy-кода.

## Как устроен production-путь

`GET /` отдаёт `miniapp/index.html`, а `_miniapp_index_body()`
(`app/api/main.py`) подменяет в нём ссылки на собранный бандл из
`miniapp/dist/manifest.json`:

```
miniapp/dist/app.<12-hex>.min.js   ← scripts/build_frontend.mjs (legacy)
miniapp/dist/app.<12-hex>.min.css
miniapp/dist/manifest.json         {js, css, jsFiles, cssFiles}
```

Каталог `miniapp/dist/` в `.gitignore` — сборка происходит в Docker
(`frontend-builder` stage) и в CI.

## Сборка V2

```bash
cd frontend-v2 && npm ci && npm run build
```

Результат в `frontend-v2/dist/`:

```
app.<12-hex>.min.js      — тот же контракт имён, что у legacy
app.<12-hex>.min.css
manifest.json            {js, css, jsFiles, cssFiles} — читается как backend-манифест
index.html               — ссылается на реально существующие файлы
```

Имена совпадают с контрактом `^app\.(0-9a-f){12}\.min\.(js|css)$`, который
проверяет `scripts/check_frontend_build.py`. Hash вычисляется от содержимого,
поэтому одинаковый исходник даёт одинаковое имя (cache-busting работает, а
повторная сборка не плодит артефакты).

## Публикация в miniapp/dist

```bash
cd frontend-v2
node scripts/publish_prod.mjs --dry-run   # что легло бы
node scripts/publish_prod.mjs             # скопировать бандл + v2.json + v2index.html
node scripts/publish_prod.mjs --revert    # удалить ТОЛЬКО файлы V2 (legacy не трогает)
```

`v2.json` — marker, по которому backend отличает бандл V2 от legacy: общий
`manifest.json` в этом каталоге принадлежит legacy-сборке.

## Включение V2

Флаг читается из **серверной** конфигурации, не из клиента:

```bash
# 1. Локально / в докере, без БД
MINIAPP_V2=1

# 2. Через общую систему фиче-флагов (как остальные фичи проекта)
#    UPDATE feature_flags SET is_on=1 WHERE code='miniapp_v2';
```

Приоритет: переменная окружения → таблица `feature_flags` (`content.is_on`,
с детерминированным rollout). По умолчанию — **выключено**.

Публичного переключателя нет: пользователь не может включить V2 сам через
query-параметр или заголовок.

## Откат

```bash
# Выключить флаг — legacy вернётся тем же ответом, без пересборки
MINIAPP_V2=0

# Или убрать опубликованный V2 (тогда включение честно упадёт с 500,
# а не молча отдаст legacy)
node scripts/publish_prod.mjs --revert
```

Если V2 включён, но `miniapp/dist/v2.json` отсутствует — сервер отказывает
(500 с безличным текстом), а не подменяет режим молча. Это проверено тестом
`tests/test_miniapp_v2_switch.py`.

## Проверки

```bash
cd frontend-v2 && npx tsc --noEmit      # типы
cd frontend-v2 && npm run build         # production-сборка
cd frontend-v2 && npm test              # 24 проверки (словари, маршруты, история)

python3 scripts/check_frontend_build.py          # контракт имён manifest
python3 scripts/check_frontend_provenance.py     # legacy-строки провенанса
python3 scripts/check_static_asset_references.py  # битые /static-ссылки (включая frontend-v2/)

# Тесты переключения и отката (нужен backend-контейнер для зависимостей)
docker run --rm -v "$PWD:/src" -w /opt/oracle \
  -e APP_ENV=test -e DEV_MODE=1 -e DEV_KEY=ci-dev-key -e LLM_PROVIDER=off \
  oracle-test-tmp:latest sh -c '
    pip install -q pytest==9.1.1 pytest-asyncio==1.4.0
    cp /src/pytest.ini .
    cp /src/tests/test_miniapp_v2_switch.py tests/
    cp /src/app/api/main.py app/api/main.py
    python3 -m pytest tests/test_miniapp_v2_switch.py -q'
```

## Что осталось неподключенным

Экраны People, Person, Timeline и Memory остаются демонстрационными: их
endpoint'ов нет в backend. Пометки «Демо-данные» на них сохранены намеренно.
