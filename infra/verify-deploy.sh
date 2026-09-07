#!/usr/bin/env bash
# Верификация деплоя (BUS-382): анти-рецидив недодеплоя (BUS-194/350/373).
#
# Класс ошибки: при избирательном перекате («только api», «api/bot/worker»)
# beat или бот молча остаются на старом образе. Healthcheck это не видит
# (beat вообще без healthcheck в prod-compose) — видно только по сверке
# контейнеров/образов/env против целевого коммита.
#
# Использование:
#   bash infra/verify-deploy.sh <target-sha> [--project <compose-project>]
#        [--symbol SYM] [--absent SYM] [--dir /path/to/repo] [--env-file F]
# Примеры:
#   bash infra/verify-deploy.sh 78a4f36                          # прод (проект infra)
#   bash infra/verify-deploy.sh a6aa63d --project oracleai-staging \
#        --symbol 'нет такой памяти'                             # строка из дельты коммита
#
# Скоуп проверки выводится из compose, а не из рукописного списка:
# это работающие контейнеры проекта, чей образ строится каким-либо
# build-сервисом compose (прод: infra-api/bot/worker/beat; staging: все
# app-сервисы на образе oracleai-staging:*). Профильные сервисы (backup)
# и одноразовый migrate не проверяются. Новый build-сервис compose
# попадает в проверку автоматически.
#
# Проверки (exit 1 при любом FAIL):
#   P1. Каждый контейнер скоупа пересоздан ПОСЛЕ даты target-коммита
#       (Created >= commit) — «перекат обязателен всех build-сервисов,
#       не только явно названных».
#   P2. RELEASE_ID внутри каждого контейнера == target-sha (env-проба).
#       Prod: RELEASE_ID живёт в .env и захватывается контейнером при
#       создании — обновлять .env ДО сборки (см. DEPLOYMENT.md).
#       Staging: deploy-staging.sh экспортирует его сам.
#   P3. Content-пробы: --symbol SYM — символьная строка ИЗ дельты свежего
#       коммита (строка кода/текста, не хеш!) ДОЛЖНА найтись в /opt/oracle
#       каждого контейнера (обязательна, если дельта деплоя трогает
#       app-код); --absent SYM — символ коммита, НОВЕЕ target, должен
#       ОТСУТСТВОВАТЬ (детект сборки из WIP/дрейфа).
#   P5. CreatedAt образа каждого контейнера >= даты target-коммита
#       (детект «recreate без rebuild»/подсовывания старого образа —
#       именно это поймало beat 2026-09-02 в BUS-373).
#   P6. Контейнеры, чьи сервисы собираются из одного Dockerfile (прод:
#       api/bot/worker/beat из infra/Dockerfile), при единой сборке
#       должны иметь одинаковый resolved SHA. Расхождение — не FAIL:
#       `docker compose build` собирает каждый сервис отдельно и SHA
#       неизбежно различаются; класс BUS-373 (beat молча отстал) ловит
#       P5, свежесть кода в каждом контейнере — P3.
#
# Коды: 0 = все пробы зелёные, 1 = FAIL (детали в выводе), 2 = ошибка использования.
set -Eeuo pipefail

TARGET="${1:?Использование: verify-deploy.sh <target-sha> [--project <name>] [--symbol SYM|--absent SYM] [--dir /path] [--env-file F]}"
shift || true
PROJECT="infra"
SYMBOL=""
ABSENT=""
REPO_DIR=""
ENV_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)  PROJECT="$2"; shift 2 ;;
    --symbol)   SYMBOL="$2"; shift 2 ;;
    --absent)   ABSENT="$2"; shift 2 ;;
    --dir)      REPO_DIR="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    *) echo "Неизвестный флаг: $1" >&2; exit 2 ;;
  esac
done

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE_FILE="$REPO_DIR/infra/docker-compose.yml"
if [[ "$PROJECT" == "oracleai-staging" ]]; then
  COMPOSE_FILE="$REPO_DIR/infra/staging/docker-compose.staging.yml"
  ENV_FILE="${ENV_FILE:-$REPO_DIR/infra/staging/.env.staging}"
else
  ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
fi
[[ -f "$ENV_FILE" ]] || { echo "FAIL: нет env-файла $ENV_FILE (нужен для docker compose config)" >&2; exit 1; }

FAILS=0
say()  { printf '%s\n' "$*"; }
fail() { say "FAIL: $*"; FAILS=$((FAILS+1)); }
pass() { say "PASS: $*"; }

# --- целевой коммит существует --- #
if ! git -C "$REPO_DIR" cat-file -e "${TARGET}^{commit}" 2>/dev/null; then
  echo "FAIL: коммит $TARGET не найден в $REPO_DIR" >&2
  exit 1
fi
COMMIT_RFC="$(git -C "$REPO_DIR" show -s --format='%cI' "$TARGET")"
say "=== verify-deploy: target=$TARGET (commit $COMMIT_RFC), project=$PROJECT ==="

# --- сравнение дат: OK если a >= b (docker RFC3339Nano vs git RFC3339) --- #
cmp_dt() {
  python3 - "$1" "$2" <<'PY'
import sys, datetime, re
def p(s):
    m = re.match(r'^(.*T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$', s.strip())
    if not m:
        raise ValueError(f'bad datetime: {s!r}')
    base, frac, off = m.groups()
    off = '+00:00' if off in (None, 'Z') else (off[:3] + ':' + off[3:] if ':' not in off else off)
    us = int((frac or '0')[:6].ljust(6, '0'))
    return datetime.datetime.fromisoformat(f'{base}{off}').replace(microsecond=us)
print('OK' if p(sys.argv[1]) >= p(sys.argv[2]) else 'STALE')
PY
}

# --- скоуп: build-сервисы из compose config JSON --- #
CFG="$(mktemp)"
trap 'rm -f "$CFG"' EXIT
if ! docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config --format json >"$CFG" 2>/dev/null; then
  echo "FAIL: docker compose config не прошёл — прогони вручную: docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE config" >&2
  exit 1
fi

declare -A BNAME=() BREPO=() BPROF=() G2S=()
while IFS=$'\t' read -r kind a b c; do
  case "$kind" in
    BSVC) BNAME[$a]=1; [[ "$c" != "PROFILED" ]] && BREPO[$b]=1; [[ "$c" == "PROFILED" ]] && BPROF[$a]=1 ;;
    GRP)  G2S[$a]="${G2S[$a]:-} $b" ;;
  esac
done < <(python3 - "$CFG" "$PROJECT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
proj = sys.argv[2]
for name, svc in sorted(d.get('services', {}).items()):
    b = svc.get('build')
    if not b:
        continue
    img = svc.get('image')
    repo = img.split(':')[0] if img else f'{proj}-{name}'
    prof = 'PROFILED' if svc.get('profiles') else 'ACTIVE'
    print(f'BSVC\t{name}\t{repo}\t{prof}')
    df = b.get('dockerfile')
    if df:
        ctx = (b.get('context') or '.').rstrip('/')
        print(f'GRP\t{ctx}|{df}\t{name}')
PY
)

# --- работающие контейнеры проекта, входящие в скоуп --- #
IN_SCOPE=()
declare -A C2SVC=() C2IMG=() C2SHA=()
while read -r c; do
  svc="$(docker inspect "$c" --format '{{index .Config.Labels "com.docker.compose.service"}}')"
  img="$(docker inspect "$c" --format '{{.Config.Image}}')"
  repo="${img%%:*}"
  if { [[ -n "${BNAME[$svc]:-}" && -z "${BPROF[$svc]:-}" ]] || [[ -n "${BREPO[$repo]:-}" ]]; }; then
    IN_SCOPE+=("$c")
    C2SVC[$c]="$svc"
    C2IMG[$c]="$img"
    C2SHA[$c]="$(docker inspect "$c" --format '{{.Image}}')"
  fi
done < <(docker ps --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Names}}' | sort)
[[ ${#IN_SCOPE[@]} -gt 0 ]] || { echo "FAIL: не найдено ни одного app-контейнера проекта $PROJECT — проверять нечего" >&2; exit 1; }
say "Скоуп (${#IN_SCOPE[@]}): ${IN_SCOPE[*]}"

# --- P1. Контейнер пересоздан после даты коммита --- #
for c in "${IN_SCOPE[@]}"; do
  created="$(docker inspect "$c" --format '{{.Created}}')"
  if [[ "$(cmp_dt "$created" "$COMMIT_RFC")" == "OK" ]]; then
    pass "P1 $c пересоздан после коммита ($created)"
  else
    fail "P1 $c created=$created РАНЬШЕ коммита $COMMIT_RFC — контейнер не пересоздавался после сборки целевого sha (недодеплой-класс BUS-194/350/373)"
  fi
done

# --- P2. RELEASE_ID == target --- #
for c in "${IN_SCOPE[@]}"; do
  rid="$(docker exec "$c" printenv RELEASE_ID 2>/dev/null || echo '<нет>')"
  if [[ "$rid" == "$TARGET" ]]; then
    pass "P2 $c RELEASE_ID=$rid"
  else
    fail "P2 $c RELEASE_ID=$rid, ожидался $TARGET (env-проба; в проде обнови RELEASE_ID в .env ДО сборки — см. DEPLOYMENT.md)"
  fi
done

# --- P3. Content-пробы по /opt/oracle --- #
if [[ -n "$SYMBOL" ]]; then
  for c in "${IN_SCOPE[@]}"; do
    n="$(docker exec "$c" sh -c "grep -rl -- '$SYMBOL' /opt/oracle 2>/dev/null | head -1" || true)"
    if [[ -n "$n" ]]; then
      pass "P3 $c содержит '$SYMBOL' ($n)"
    else
      fail "P3 $c: '$SYMBOL' НЕ найден в /opt/oracle (content-проба)"
    fi
  done
fi
if [[ -n "$ABSENT" ]]; then
  for c in "${IN_SCOPE[@]}"; do
    if docker exec "$c" sh -c "grep -rl -- '$ABSENT' /opt/oracle 2>/dev/null | head -1" | grep -q .; then
      fail "P3 $c содержит '$ABSENT' — образ собран из коммита новее $TARGET (загрязнение WIP/дрейфом)"
    else
      pass "P3 $c чист по '$ABSENT'"
    fi
  done
fi
if [[ -z "$SYMBOL" && -z "$ABSENT" ]]; then
  say "SKIP: P3 grep-проба не задана (--symbol SYM / --absent SYM). Если дельта деплоя трогает app/ — проба обязательна (см. DEPLOYMENT.md)."
fi

# --- P5. CreatedAt образа >= даты коммита (recreate без rebuild) --- #
for c in "${IN_SCOPE[@]}"; do
  icreated="$(docker image inspect "${C2SHA[$c]}" --format '{{.Created}}')"
  if [[ "$(cmp_dt "$icreated" "$COMMIT_RFC")" == "OK" ]]; then
    pass "P5 $c образ собран после коммита ($icreated)"
  else
    fail "P5 $c: образ ${C2IMG[$c]} собран $icreated, РАНЬШЕ коммита $COMMIT_RFC — контейнер пересоздан из СТАРОГО образа (recreate без rebuild)"
  fi
done

# --- P4. Одинаковый Config.Image => одинаковый resolved SHA --- #
declare -A TAG_SHA=()
for c in "${IN_SCOPE[@]}"; do
  img="${C2IMG[$c]}"
  sha="${C2SHA[$c]}"
  if [[ -n "${TAG_SHA[$img]:-}" && "${TAG_SHA[$img]}" != "$sha" ]]; then
    fail "P4 $c ($img, ${sha:7:12}) расходится по SHA с ранее проверенным контейнером того же тега (${TAG_SHA[$img]:7:12}) — рассинхрон сборки"
  else
    TAG_SHA[$img]="$sha"
  fi
done
say "P4: тегов образов: ${#TAG_SHA[@]} — расхождений SHA внутри одного тега не найдено"

# --- P6. Один Dockerfile: единая сборка => одинаковый SHA (инфо, не FAIL) --- #
for g in "${!G2S[@]}"; do
  names=()
  shas=()
  for c in "${IN_SCOPE[@]}"; do
    if [[ " ${G2S[$g]} " == *" ${C2SVC[$c]} "* ]]; then
      names+=("$c")
      shas+=("${C2SHA[$c]}")
    fi
  done
  (( ${#names[@]} > 1 )) || continue
  uniq="$(printf '%s\n' "${shas[@]}" | sort -u | wc -l)"
  disp="${g#"$REPO_DIR"/}"
  if [[ "$uniq" -eq 1 ]]; then
    pass "P6 группа $disp: ${#names[@]} контейнеров на одном Dockerfile — SHA одинаковы"
  else
    say "WARN: P6 группа $disp: SHA различаются (${names[*]}) — ожидаемо при docker compose build по-сервисно; сверку свежести кода делают P5/P3"
  fi
done

say "=== Итог: FAILS=$FAILS ==="
[[ "$FAILS" -eq 0 ]]
