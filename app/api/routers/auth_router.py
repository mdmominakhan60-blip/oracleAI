"""Аутентификация и replay-защита initData (BUS-200).

Поток:
  1. Клиент шлёт initData один раз в `POST /auth/session`.
  2. Сервер проверяет подпись Telegram (`parse_init_data`) и атомарно
     резервирует hash initData в Redis (SET NX, TTL = срок годности подписи).
  3. Повторный минт с той же initData → 401: строка потребляется один раз.
  4. При успехе минтится stateless `X-Session-Token` = HMAC(tg_id:expiry);
     дальше клиент ходит токеном, initData не нужен.
  5. До миграции Mini App на токены read-ручки продолжают принимать initData
     напрямую. Replay GET не расширяет полномочия: украденная строка даёт не
     больше, чем одно легитимное окно 24ч жизни подписи.

Redis нужен только на минте: токен проверяется без бэкенда. Сбой Redis
fail-open (REPLAY_FAIL_CLOSED=1 включает fail-closed) — у авторизации не
появляется второго источника тотального отказа, а окно replay и так
ограничено 24ч. Решение согласовано с Engineering Lead; security-review:
BUS-200. BUS-344: fail-closed отвечает 503 «auth store unavailable», а не
401 «replay» — при живой initData сообщение «уже использована» вводит в
заблуждение при диагностике (клиент miniapp обрабатывает любой не-2xx
одинаково: тихий fallback на x-init-data).
"""
from __future__ import annotations

import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Counter
from pydantic import BaseModel

from ...config import settings
from ...services import rate_limit as rate_limit_service
from ...services.repo_gateway import users as users_repo
from ..auth_common import sign_session_token
from ..deps import get_db, rate_limit
from ..security import MAX_AGE_SECONDS, parse_init_data

log = logging.getLogger("oracle.api.auth")

#: BUS-343: видимость сбоя replay-store. Решение EL по BUS-342 — fail-open
#: валиден только при наблюдаемости инцидента: без этой метрики немой fail-open
#: незаметен оператору. Инкремент в _mark_init_data_used (и api, и локальные
#: сценарии без прометея должны просто работать — Counter сам регистрируется
#: в дефолтном реестре /metrics).
REPLAY_STORE = Counter(
    "oracleai_replay_store_total",
    "Replay-store outcomes at init-data mint: fail-open/fail-closed on Redis errors.",
    ("result",),
)
# Пре-инициализация детей обязательна: prometheus_client создаёт ряд только при
# первом .inc(), а increase()/rate() игнорируют переход "серии не было → N"
# (нет предыдущей точки). Без этого алерт молчал бы на первом инциденте после
# рестарта API — ровно тот случай, ради которого он существует (проверено на
# staging 2026-09-06: счётчик=2, increase(...[10m])=0, алерт inactive).
REPLAY_STORE.labels(result="open")
REPLAY_STORE.labels(result="closed")

router = APIRouter(prefix="/api", tags=["auth"])

SESSION_TTL = MAX_AGE_SECONDS
MINT_LIMIT_PER_MINUTE = 10

try:
    from redis.asyncio import Redis as _Redis
    _redis: _Redis | None = _Redis.from_url(settings.redis_url,
                                            decode_responses=True)
except Exception:
    _redis = None


class InitDataRequest(BaseModel):
    # Optional: отсутствующее поле — 401 (как и пустая строка), не 422:
    # единый контракт ошибки аутентификации для клиента.
    init_data: str = ""


def _init_data_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ReplayStoreUnavailable(Exception):
    """BUS-344: недоступность replay-store при fail-closed.

    Отличается от replay (возврат False): живая initData не должна получать
    401 «уже использована» — это деградация сервиса, endpoint отвечает 503.
    """


async def _mark_init_data_used(raw: str) -> bool:
    """Атомарная бронь nonce. True — initData видна впервые, False — replay.

    Сбой Redis: fail-open по умолчанию, REPLAY_FAIL_CLOSED=1 — кидает
    ReplayStoreUnavailable (endpoint отдаёт 503, см. класс).
    Хеш в логе усечён: он не секрет (вход — сама строка), но и не нужен целиком.
    """
    digest = _init_data_hash(raw)
    try:
        if _redis is None:
            raise RuntimeError("redis не сконфигурирован")
        created = await _redis.set(f"oracleai:initdata:{digest}", "1",
                                   nx=True, ex=MAX_AGE_SECONDS)
        if not created:
            log.warning("auth_replay_blocked hash=%s", digest[:12])
        return bool(created)
    except Exception as e:
        if settings.replay_fail_closed:
            log.error("auth_replay_store_down fail-closed: %s", e)
            REPLAY_STORE.labels(result="closed").inc()
            raise ReplayStoreUnavailable(str(e)) from e
        log.warning("auth_replay_store_down fail-open: %s", e)
        REPLAY_STORE.labels(result="open").inc()
        return True


@router.post("/auth/session", dependencies=[Depends(rate_limit("write"))])
async def mint_session(req: InitDataRequest, db=Depends(get_db)):
    """Обмен подписанной initData на долгоживущий session-токен.

    Публичный эндпоинт: валидация подписи обязательна, темп ограничен и по IP
    (guard rate_limit), и по tg_id после валидации.
    """
    data = parse_init_data(req.init_data)
    if not data:
        raise HTTPException(401, "подпись Telegram не подтверждена")

    tg_id = data["tg_id"]
    decision = await rate_limit_service.allow(str(tg_id), "auth",
                                              MINT_LIMIT_PER_MINUTE, 60)
    if not decision.allowed:
        raise HTTPException(429, "слишком часто — переведи дыхание 🌙",
                            headers={"Retry-After": str(decision.retry_after)})

    try:
        first_seen = await _mark_init_data_used(req.init_data)
    except ReplayStoreUnavailable:
        # BUS-344: store недоступен при fail-closed — деградация сервиса,
        # а не replay: 503 «store unavailable» вместо 401 «replay»
        # (клиент любой не-2xx обрабатывает одинаково).
        raise HTTPException(503, "auth store unavailable")
    if not first_seen:
        raise HTTPException(401, "initData уже использована (replay)")

    await users_repo.ensure(db, tg_id, data["first_name"], data["username"],
                            lang=data["language_code"])

    expiry = int(time.time()) + SESSION_TTL
    log.info("session minted tg_id=%s", tg_id)
    return {"session_token": sign_session_token(tg_id, expiry),
            "expires_in": SESSION_TTL}
