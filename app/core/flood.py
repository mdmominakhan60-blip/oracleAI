"""Единый темп исходящих вызовов Telegram.

Telegram ограничивает бота примерно 30 сообщениями в секунду и карает 429 за
превышение. Раньше рассылку придерживала собственная пауза, а ответы бота и
запросы веб-процесса не лимитировались вовсе — три потока исходящих на пике
могли легко утопить лимит. Одна бакетная корзина на процесс, из которой берут
токены и aiogram-сессия бота, и тонкий HTTP-клиент веб-процесса, держит
суммарный темп под потолком.

Бакет in-process: два воркера дадут вдвое больший бюджет. Это осознанный выбор
на текущем масштабе (G22); общий Redis-бакет появится, когда сервис перестанет
помещаться в один воркер.
"""
from __future__ import annotations

import asyncio
import time

#: Номинальный темп, сообщений в секунду. Под мягким потолком в 25 при лимите
#: Telegram в 30 остаётся запас на 429-ретраи и шум сети.
RATE = 25.0
#: Всплеск сверх номинала: короткий залп (утренняя рассылка на старте) не должен
#: сразу превращаться в очередь, но и не должен долбить Telegram рывками.
BURST = 35.0

#: Служебные методы не лимитируем: задержка поллинга (getUpdates) резала бы
#: скорость приёма сообщений, а setMyCommands/getMe и так один раз на старте.
CONTROL_METHODS = {
    "getUpdates", "getMe", "setMyCommands", "getWebhookInfo",
    "setWebhook", "deleteWebhook", "setChatMenuButton", "close",
}

_lock = asyncio.Lock()
_tokens = BURST
_last = time.monotonic()

#: Отдельная корзина рассылок: broadcast не конкурирует с ответами клиенткам
#: за общие токены, но суммарный темп остаётся под потолком Telegram
#: (25 + 10 < 30/с с запасом на ретраи).
BROADCAST_RATE = 10.0
BROADCAST_BURST = 15.0

_broadcast_lock = asyncio.Lock()
_broadcast_tokens = BROADCAST_BURST
_broadcast_last = time.monotonic()


async def acquire_broadcast() -> None:
    """Ждёт токен из корзины рассылок (отдельный лейн, см. выше)."""
    global _broadcast_tokens, _broadcast_last
    while True:
        async with _broadcast_lock:
            now = time.monotonic()
            _broadcast_tokens = min(
                BROADCAST_BURST,
                _broadcast_tokens + (now - _broadcast_last) * BROADCAST_RATE)
            _broadcast_last = now
            if _broadcast_tokens >= 1.0:
                _broadcast_tokens -= 1.0
                return
            wait = (1.0 - _broadcast_tokens) / BROADCAST_RATE
        await asyncio.sleep(wait)


def reset_for_tests() -> None:
    """Сброс обеих корзин (тесты гоняют модуль-синглтон много раз)."""
    global _tokens, _last, _broadcast_tokens, _broadcast_last
    _tokens, _broadcast_tokens = BURST, BROADCAST_BURST
    _last = _broadcast_last = time.monotonic()


async def acquire() -> None:
    """Ждёт токен общей корзины и занимает один."""
    global _tokens, _last
    while True:
        async with _lock:
            now = time.monotonic()
            _tokens = min(BURST, _tokens + (now - _last) * RATE)
            _last = now
            if _tokens >= 1.0:
                _tokens -= 1.0
                return
            wait = (1.0 - _tokens) / RATE
        # ждём снаружи замка: держать lock во время сна — значит сериализовать
        # все исходящие и не дать всплеску разойтись
        await asyncio.sleep(wait)


def is_control(method_name: str) -> bool:
    """True для служебных методов, которые не тратят бакет."""
    return method_name in CONTROL_METHODS
