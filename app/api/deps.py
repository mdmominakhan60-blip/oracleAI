"""Зависимости FastAPI: соединение с БД, клиентка, администратор, темп запросов."""
from __future__ import annotations

import hmac
import logging


from fastapi import Depends, Header, HTTPException, Query, Request

from ..config import settings
from ..services.repo_gateway import admin as admin_repo
from ..services.repo_gateway import users as users_repo
from ..services import rate_limit as rate_limit_service
from .security import parse_init_data

log = logging.getLogger("oracle.api")


async def get_db(request: Request):
    """Пул БД, созданный lifespan'ом и лежащий в ``app.state`` (аудит DB-005).

    Модульный синглтон ``_db = None`` удалён: он имитировал «одно соединение
    на процесс» и скрывал владельца ресурса. Пул (SQLAlchemy AsyncEngine)
    по-прежнему один на процесс — это правильно, — но теперь его жизненный
    цикл явно принадлежит приложению, а не глобальной переменной, и каждый
    запрос получает фасад пула через request-scoped зависимость.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise RuntimeError(
            "пул БД не инициализирован: lifespan приложения не запускался")
    return db


def _dev_identity_allowed(request: Request) -> bool:
    """Право на вход по ?dev_user=<id> в DEV_MODE (аудит SEC-001).

    DEV_MODE сам по себе fail-closed при импорте (см. config). Заданный
    DEV_KEY делает dev-вход подписанным короткоживущим ключом, который
    существует только в локальном docker-compose разработчика.
    """
    if not settings.dev_mode:
        return False
    if not settings.dev_key.strip():
        # Страховка в глубину (BUS-90): guard в config роняет импорт
        # DEV_MODE=1 с пустым ключом; сюда попадаем, только если настройки
        # подменены в рантайме поверх невалидной конфигурации.
        return False
    provided = request.headers.get("x-dev-key", "")
    if not provided or not hmac.compare_digest(provided, settings.dev_key):
        return False
    return True


# ─────────────────────────────── темп запросов ────────────────────────────────
# The limiter service supports process-local development and Redis-backed
# multi-process production. Identity is always derived from signed Telegram data
# (or explicit dev mode), never from a user-controlled body field.

LIMITS = {
    "read": (120, 60),
    "write": (30, 60),
    "llm": (12, 60),
    "admin": (60, 60),
}


def rate_limit(bucket: str = "read"):
    """Distributed-safe dependency limiter with bounded retry metadata."""
    limit, window = LIMITS.get(bucket, LIMITS["read"])

    async def guard(request: Request):
        data = parse_init_data(request.headers.get("x-init-data", ""))
        if data:
            tg_id = str(data["tg_id"])
        elif _dev_identity_allowed(request) and request.query_params.get("dev_user"):
            try:
                tg_id = str(int(request.query_params["dev_user"]))
            except ValueError:
                # Неаутентифицированный ключ по IP клиента, не общий tg_id=0:
                # иначе один аноним кладёт лимит для всех без подписи.
                client = request.client
                tg_id = f"ip:{client.host if client else 'unknown'}"
        else:
            client = request.client
            tg_id = f"ip:{client.host if client else 'unknown'}"
        decision = await rate_limit_service.allow(tg_id, bucket, limit, window)
        if not decision.allowed:
            log.warning(
                "rate_limit_denied bucket=%s backend=%s retry_after=%s",
                bucket, decision.backend, decision.retry_after,
            )
            raise HTTPException(
                429,
                detail={"code": "rate_limited", "backend": decision.backend,
                        "message": "слишком часто — переведи дыхание 🌙"},
                headers={"Retry-After": str(decision.retry_after)},
            )

    return guard


# ──────────────────────────────── клиентка ────────────────────────────────────

async def _authenticated_user(db, x_init_data: str | None, dev_user: int | None,
                              *, allow_deleted: bool = False,
                              dev_allowed: bool = False):
    """Resolve identity and enforce the account lifecycle state.

    Deleted users remain as anonymized accounting anchors, but are not valid
    product principals. The sole exception is the confirm-gated deletion route,
    which must remain idempotent for a retried client request.
    """
    data = parse_init_data(x_init_data) if x_init_data else None
    tg_id = data["tg_id"] if data else None
    if tg_id is None and dev_allowed and dev_user:
        tg_id = dev_user
    if tg_id is None:
        raise HTTPException(401, "подпись Telegram не подтверждена")

    user = await users_repo.get(db, tg_id)
    if not user:
        raise HTTPException(404, "открой бота и нажми /start — я ещё не знаю тебя ✨")
    status = user["status"]
    if status == "blocked":
        raise HTTPException(403, "доступ приостановлен")
    if status == "deleted" and not allow_deleted:
        raise HTTPException(410, "аккаунт удалён — создай новый аккаунт через бота")
    if data and data["username"] and user["username"] != data["username"]:
        await users_repo.update(db, tg_id, username=data["username"])
    return user


async def current_user(request: Request, db=Depends(get_db),
                       x_init_data: str | None = Header(default=None),
                       dev_user: int | None = Query(default=None)):
    """Клиентка по подписи Telegram. В DEV_MODE — по `?dev_user=<id>` (+ DEV_KEY)."""
    return await _authenticated_user(db, x_init_data, dev_user,
                                     dev_allowed=_dev_identity_allowed(request))


async def deletion_user(request: Request, db=Depends(get_db),
                        x_init_data: str | None = Header(default=None),
                        dev_user: int | None = Query(default=None)):
    """Identity dependency for a retry of the confirm-gated delete operation."""
    return await _authenticated_user(db, x_init_data, dev_user, allow_deleted=True,
                                     dev_allowed=_dev_identity_allowed(request))


async def confirmed_age_user(user=Depends(current_user)):
    """Авторизованный пользователь (возрастной гейт полностью удалён).

    Имя сохранено как стабильный алиас `current_user`, чтобы не менять
    десятки ручек; возрастная проверка больше не выполняется.
    """
    return user


async def active_user(user=Depends(confirmed_age_user)):
    """Как `confirmed_age_user`, но требует живую подписку — для платного контента."""
    if not users_repo.sub_active(user):
        raise HTTPException(402, "подписка завершена — продли её в боте")
    return user


async def touched_user(user=Depends(current_user), db=Depends(get_db)):
    """Клиентка + отметка «была онлайн» (для аналитики удержания)."""
    await users_repo.touch(db, user["tg_id"])
    return user


# ─────────────────────────────── администратор ────────────────────────────────

class AdminContext:
    """Кто вошёл в панель и что ему можно."""

    def __init__(self, tg_id: int, role: str):
        self.tg_id = tg_id
        self.role = role

    def require(self, permission: str) -> None:
        if not admin_repo.can(self.role, permission):
            raise HTTPException(403, f"недостаточно прав: нужно {permission}")


async def current_admin(request: Request, db=Depends(get_db),
                        x_init_data: str | None = Header(default=None),
                        dev_user: int | None = Query(default=None)) -> AdminContext:
    """Администратор панели.

    Вход только через подпись Telegram: панель открывается кнопкой из бота, и
    отдельного пароля у неё нет — так нечего утекать. `dev_user` работает лишь
    при DEV_MODE (и с DEV_KEY, когда он задан), то есть на машине разработчика.
    """
    data = parse_init_data(x_init_data) if x_init_data else None
    tg_id = data["tg_id"] if data else None
    if tg_id is None and _dev_identity_allowed(request) and dev_user:
        tg_id = dev_user
    if tg_id is None:
        raise HTTPException(401, "подпись Telegram не подтверждена")
    role = await admin_repo.resolve_role(db, tg_id)
    if not role:
        log.warning("попытка входа в админку без роли")
        raise HTTPException(403, "нет доступа к панели")
    user = await users_repo.get(db, tg_id)
    if user and user["status"] in {"blocked", "deleted"}:
        log.warning("администратор с недействительным статусом отклонён")
        raise HTTPException(403, "доступ приостановлен")
    return AdminContext(tg_id, role)


def require(permission: str):
    """Зависимость-проверка права: `Depends(require('catalog'))`."""
    async def guard(ctx: AdminContext = Depends(current_admin)) -> AdminContext:
        ctx.require(permission)
        return ctx
    return guard
