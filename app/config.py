"""Конфигурация приложения (.env).

Здесь только то, что нельзя менять на ходу: секреты, адреса, режим работы.
Всё продуктовое (цены, лимиты, тексты, фиче-флаги) живёт в БД и правится в
админ-панели без деплоя — см. `app/data/seed.py` и `app/repo/content.py`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _int(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, "") or default)
    except ValueError:
        value = default
    return max(value, minimum) if minimum is not None else value


#: Не `frozen=True`: тесты и админские сценарии подменяют отдельные поля на
#: живом объекте (`monkeypatch.setattr(settings, ...)`), а хеширование настроек
#: нигде не используется.
@dataclass
class Settings:
    # ── Telegram ──
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_id: int = _int("ADMIN_ID", 0)
    webapp_url: str = os.getenv("WEBAPP_URL", "").rstrip("/")
    payment_alert_secondary_url: str = os.getenv("PAYMENT_ALERT_SECONDARY_URL", "").rstrip("/")
    cryptobot_dashboard_url: str = os.getenv("CRYPTOBOT_DASHBOARD_URL", "").rstrip("/")
    paddle_dashboard_url: str = os.getenv("PADDLE_DASHBOARD_URL", "").rstrip("/")
    telegram_stars_dashboard_url: str = os.getenv("TELEGRAM_STARS_DASHBOARD_URL", "").rstrip("/")

    # ── LLM ──
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")  # auto|custom|anthropic|openai|off
    anthropic_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key: str = os.getenv("OPENAI_API_KEY", "")
    custom_base_url: str = os.getenv("CUSTOM_LLM_BASE_URL", "").rstrip("/")
    custom_api_key: str = os.getenv("CUSTOM_LLM_API_KEY", "")
    custom_model_main: str = os.getenv("CUSTOM_LLM_MODEL", "")
    custom_model_lite: str = os.getenv("CUSTOM_LLM_MODEL_LITE",
                                       os.getenv("CUSTOM_LLM_MODEL", ""))
    # Defaults follow the current provider catalog; production may override them
    # explicitly after a live capability probe.
    anthropic_main: str = os.getenv("ANTHROPIC_MODEL_MAIN", "claude-sonnet-4-6")
    anthropic_lite: str = os.getenv("ANTHROPIC_MODEL_LITE", "claude-haiku-4-5")
    openai_main: str = os.getenv("OPENAI_MODEL_MAIN", "gpt-5")
    openai_lite: str = os.getenv("OPENAI_MODEL_LITE", "gpt-5-mini")
    # GPT-5 reasoning is provider-specific; minimal keeps the default responsive,
    # while staging can raise this to low/medium for difficult adjudication.
    llm_reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "minimal").lower()

    # ── мониторинг (G31): пусто = Sentry выключен ──
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    # SEC-015: когда задан, /metrics требует Authorization: Bearer <token> уже
    # на уровне приложения, а не только на edge (Caddy). Пусто = как раньше.
    metrics_token: str = os.getenv("METRICS_TOKEN", "")

    # ── возрастная проверка полностью удалена (GAUNTLET v2); соль не нужна.
    # ── защита LLM от всплеска: сколько вызовов одновременно и в минуту ──
    llm_max_concurrency: int = _int("LLM_MAX_CONCURRENCY", 8)
    llm_rate_per_min: int = _int("LLM_RATE_PER_MIN", 240)
    # Hard limits for one logical agent workflow, not for each provider retry.
    llm_workflow_timeout: float = float(os.getenv("LLM_WORKFLOW_TIMEOUT", "90"))
    llm_max_tool_calls: int = _int("LLM_MAX_TOOL_CALLS", 12)
    llm_max_cost_usd: float = float(os.getenv("LLM_MAX_COST_USD", "0.25"))

    # ── память по смыслу (необязательна: без неё работает поиск по словам) ──
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    embed_via_custom: bool = os.getenv("EMBED_VIA_CUSTOM", "0") == "1"

    # ── озвучка прогнозов (тариф «Консьерж») ──
    tts_model: str = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
    tts_voice: str = os.getenv("TTS_VOICE", "shimmer")

    # ── каналы-спутники: по каналу на знак, {sign} — латинский код знака ──
    horoscope_channels: str = os.getenv("HOROSCOPE_CHANNELS", "")

    # ── web-оплата (Paddle / LemonSqueezy): основной чек мимо комиссии Stars ──
    paddle_webhook_secret: str = os.getenv("PADDLE_WEBHOOK_SECRET", "")
    paddle_api_key: str = os.getenv("PADDLE_API_KEY", "")
    paddle_api_url: str = os.getenv("PADDLE_API_URL", "https://api.paddle.com").rstrip("/")
    paddle_checkout_url: str = os.getenv("PADDLE_CHECKOUT_URL", "").rstrip("/")
    # `vip:pri_...,basic:pri_...` — never derive a provider price from client input.
    paddle_price_ids: str = os.getenv("PADDLE_PRICE_IDS", "")

    # ── Crypto Pay (@CryptoBot): приём крипты за Кристаллы без юрлица ──
    cryptobot_api_token: str = os.getenv("CRYPTOBOT_API_TOKEN", "")
    cryptobot_app_name: str = os.getenv("CRYPTOBOT_APP_NAME", "")

    # ── окружение и наблюдаемость ──
    app_env: str = os.getenv("APP_ENV", "dev").lower()
    dev_mode: bool = os.getenv("DEV_MODE", "0") == "1"
    # Подписанный ключ для ?dev_user=<id> в DEV_MODE (аудит SEC-001): когда задан,
    # каждый dev-запрос обязан нести заголовок X-Dev-Key с этим значением.
    # Локальный docker-compose монтирует его только на машине разработчика.
    dev_key: str = os.getenv("DEV_KEY", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file: str = os.getenv("LOG_FILE", "")
    release_id: str = os.getenv("RELEASE_ID", "local")
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
    rate_limit_backend: str = os.getenv("RATE_LIMIT_BACKEND", "memory").strip().lower()
    rate_limit_fail_closed: bool = os.getenv("RATE_LIMIT_FAIL_CLOSED", "1") == "1"
    celery_enabled: bool = os.getenv("CELERY_ENABLED", "0") == "1"
    celery_task_always_eager: bool = os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1"
    celery_task_time_limit: int = _int("CELERY_TASK_TIME_LIMIT", 300)
    celery_task_soft_time_limit: int = _int("CELERY_TASK_SOFT_TIME_LIMIT", 270)
    celery_visibility_timeout: int = _int("CELERY_VISIBILITY_TIMEOUT", 3600)
    celery_worker_prefetch: int = _int("CELERY_WORKER_PREFETCH", 1)
    celery_max_retries: int = _int("CELERY_MAX_RETRIES", 3, minimum=0)
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")

    # ── продуктовые значения по умолчанию ──
    # Рабочие значения берутся из таблицы `settings`; эти нужны, пока БД пуста
    # (первый старт, тесты, офлайн-скрипты).
    daily_questions: int = 3
    auto_trial: bool = os.getenv("AUTO_TRIAL", "0") == "1"
    trial_days: int = _int("TRIAL_DAYS", 30)
    crystals_start: int = _int("TRIAL_CRYSTALS", 30)
    crystals_emergency_cost: int = 20
    ref_bonus: int = 15
    vip_stars_price: int = 1300
    crystal_packs: tuple = ((100, 550), (250, 1150), (600, 2250))

    def paddle_price_id(self, plan_code: str) -> str:
        for item in self.paddle_price_ids.split(","):
            code, sep, price_id = item.partition(":")
            if sep and code.strip() == plan_code:
                return price_id.strip()
        return ""

    @property
    def custom_ready(self) -> bool:
        return bool(self.custom_base_url and self.custom_model_main)

    @property
    def provider_chain(self) -> tuple:
        """Порядок LLM-провайдеров: основной + резервные.

        Цепочка — не роскошь: локальный сервер падает, у облачного кончаются
        кредиты, и без резерва клиентка получала бы «сервис недоступен» вместо
        ответа. Последний уровень — офлайн-режим, он в `core/agents/runtime.py`.
        """
        available = []
        if self.custom_ready:
            available.append("custom")
        if self.anthropic_key:
            available.append("anthropic")
        if self.openai_key:
            available.append("openai")
        if self.llm_provider in ("custom", "anthropic", "openai"):
            if self.llm_provider in available:
                return tuple([self.llm_provider] +
                             [p for p in available if p != self.llm_provider])
            return tuple()
        if self.llm_provider == "off":
            return tuple()
        return tuple(available)

    @property
    def provider(self) -> str:
        chain = self.provider_chain
        return chain[0] if chain else "off"

    @property
    def llm_enabled(self) -> bool:
        return self.provider != "off"

    @property
    def ready(self) -> list[str]:
        """Чего не хватает для боевого запуска — печатается при старте бота."""
        problems = []
        if not self.bot_token:
            problems.append("BOT_TOKEN не задан")
        if not self.admin_id:
            problems.append("ADMIN_ID не задан — в админ-панель будет не войти")
        if self.dev_mode:
            problems.append("DEV_MODE=1 — вход в API без подписи Telegram")
        if not self.webapp_url:
            problems.append("WEBAPP_URL пуст — кнопка Mini App не появится")
        if not self.llm_enabled:
            problems.append("нет ключей LLM — работает офлайн-режим")
        return problems


def assert_dev_mode_allowed(dev_mode: bool, app_env: str, dev_key: str) -> None:
    """Fail-closed при импорте (аудит SEC-001, BUS-90).

    DEV_MODE выключает подпись Telegram на всём API. Раньше единственной
    преградой была проверка в lifespan API-процесса — одна опечатка в .env
    (APP_ENV=dev на бою или забытый DEV_MODE=1) открывала полный обход
    авторизации. Теперь недопустимая комбинация роняет ЛЮБОЙ процесс
    (бот, API, воркер, скрипт) ещё при импорте конфигурации.

    Третий аргумент обязателен и не имеет значения по умолчанию: забытый
    вызов падает TypeError'ом, а не молча пропускает проверку. Пустой
    DEV_KEY при DEV_MODE=1 недопустим (BUS-90): ветка `if settings.dev_key`
    в deps._dev_identity_allowed просто не выполнялась, и ?dev_user=<id>
    входил в API без всякого заголовка — так прод-стек с APP_ENV=test и
    пустым ключом жил с неаутентифицированным входом.
    """
    if dev_mode and not dev_key.strip():
        raise RuntimeError(
            "DEV_MODE=1 требует непустой DEV_KEY: без него ?dev_user=<id> "
            "входит в API без заголовка X-Dev-Key, обходя подпись Telegram. "
            "Задай DEV_KEY или выключи DEV_MODE — процесс остановлен до "
            "первого запроса.")
    if dev_mode and app_env not in {"dev", "test"}:
        raise RuntimeError(
            "DEV_MODE=1 допустим только при APP_ENV=dev|test: режим выключает "
            "подпись Telegram (?dev_user=<id>). Выключи DEV_MODE или исправь "
            "APP_ENV — процесс остановлен до первого запроса.")


settings = Settings()
assert_dev_mode_allowed(settings.dev_mode, settings.app_env, settings.dev_key)
