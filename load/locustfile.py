"""Locust-сценарий: API Mini App под 50 RPS (SLO из docs/RELEASE/PRODUCTION_READINESS.md §2).

API ходит на сервер, поднятый в DEV_MODE: подписанную Telegram-initData не
шлём, а эмулируем распределение по клиенткам через `?dev_user=`, как
умеет `app/api/deps.py` (current_user/rate_limit читают dev_user из query).
dev_user обходит сегмент 100_000_000.. из scripts/seed_load.py, чтобы каждый
виртуальный пользователь попадал на существующую запись и свой rate-limit.

Запуск (~50 RPS: 1 000 пользователей, 25 новых/с, пауза 15–25 с между запросами):

    pip install locust
    DEV_MODE=1 .venv/bin/python -m uvicorn app.api.main:app --port 8000
    locust -f load/locustfile.py --host http://127.0.0.1:8000 -u 1000 -r 25 --run-time 2m

При паузе 15–25 секунд 1 000 подключённых читателей дают около 50 RPS —
целевой поток из production readiness. Смотреть p95 (SLO < 400 мс, кроме
генераций) в сводке Locust.
"""
from __future__ import annotations

from itertools import count

from locust import HttpUser, between, task

BASE_ID = 100_000_000
POOL = 5_000  # столько виртуальных клиенток из сида держим в памяти


def _url(path: str, uid: int) -> str:
    return f"{path}?dev_user={BASE_ID + uid % POOL}"


class MiniAppUser(HttpUser):
    """Читающее поведение Mini App: небольшие GET-запросы, паузы читателя."""

    # Человек читает экран между переходами; такой темп сохраняет 1 000
    # одновременных сессий, но создаёт целевой поток около 50 RPS, а не
    # синтетическую тысячу кликов в секунду с каждого устройства.
    wait_time = between(15.0, 25.0)
    _user_numbers = count()

    def on_start(self):
        # Locust не задаёт стабильного ``id`` экземпляру HttpUser. Свой счётчик
        # сохраняет распределение по seed-профилям и их независимым лимитам.
        self.dev_user_number = next(self._user_numbers)
        # DEV_KEY обязателен при DEV_MODE=1 (BUS-90): без заголовка ?dev_user
        # ловит 401 и прогон меряет не нагрузку, а отказы авторизации.
        import os
        if os.getenv("DEV_KEY"):
            self.client.headers.update({"X-Dev-Key": os.environ["DEV_KEY"]})

    @task(3)
    def moon_week(self):
        self.client.get(_url("/api/moon/week", self.dev_user_number), name="/api/moon/week")

    @task(2)
    def sky(self):
        self.client.get(_url("/api/sky", self.dev_user_number), name="/api/sky")

    @task(2)
    def me(self):
        self.client.get(_url("/api/me", self.dev_user_number), name="/api/me")

    @task(1)
    def diary(self):
        self.client.get(_url("/api/diary", self.dev_user_number), name="/api/diary")

    @task(1)
    def horoscope(self):
        # отдельный лимит-бакет "read", у каждого dev_user свои 120/мин
        self.client.get(_url("/api/horoscope", self.dev_user_number), name="/api/horoscope")
