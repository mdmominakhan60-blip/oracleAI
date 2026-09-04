"""Точка входа бота: python -m app.bot.main

Процесс бота владеет: поллингом Telegram, планировщиком и отправкой рассылок.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from ..config import settings
from ..core import flood, sentry
from ..core.observability import configure_logging
from ..data.session import connect
from ..services import access, analytics, broadcast, chat as chat_service, scheduler
from . import chat, features, growth, onboarding, palm, profile, shop

configure_logging(level=settings.log_level, log_file=settings.log_file)
log = logging.getLogger("oracle")
BROADCAST_TICK = 60

COMMANDS = [
    BotCommand(command="start", description="Начать / вернуться в меню"),
    BotCommand(command="today", description="Прогноз дня"),
    BotCommand(command="horoscope", description="Гороскоп на сегодня"),
    BotCommand(command="practice", description="Практики"),
    BotCommand(command="moon", description="Лунная неделя"),
    BotCommand(command="promo", description="Ввести промокод"),
    BotCommand(command="help", description="Как я работаю"),
]
COMMANDS_EN = [
    BotCommand(command="start", description="Start / back to menu"),
    BotCommand(command="today", description="Today's forecast"),
    BotCommand(command="horoscope", description="Today's horoscope"),
    BotCommand(command="practice", description="Practices"),
    BotCommand(command="moon", description="Moon week"),
    BotCommand(command="promo", description="Enter a promo code"),
    BotCommand(command="help", description="How I work"),
]


class DbMiddleware(BaseMiddleware):
    def __init__(self, db):
        self.db = db

    async def __call__(self, handler, event, data):
        data["db"] = self.db
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, interval: float = 1.2):
        self.interval = interval
        self.last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            now = time.monotonic()
            if now - self.last.get(user.id, 0) < self.interval:
                msg = getattr(event, "message", None) or event
                answer = getattr(msg, "answer", None)
                if callable(answer):
                    en = getattr(user, "language_code", "") or ""
                    try:
                        await answer("Too fast 🌙 Try again in a moment." if en.startswith("en") else "Не так быстро 🌙 Напиши через пару секунд.")
                    except Exception:
                        pass
                return None
            self.last[user.id] = now
            if len(self.last) > 20_000:
                for _ in range(len(self.last) // 10):
                    self.last.pop(next(iter(self.last)))
        return await handler(event, data)


async def on_error(event, exception=None, **kwargs):
    exc = exception or getattr(event, "exception", None)
    log.exception("ошибка обработки апдейта: %s", exc or "?")
    if exc is not None:
        sentry.capture_exception(exc)
    return True


async def broadcast_loop(bot: Bot, db) -> None:
    async with Bot(settings.bot_token,
                   default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                   session=_BroadcastSession(timeout=60)) as bcast_bot:
        while True:
            try:
                await broadcast.tick(bcast_bot, db)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("цикл рассылок: %s", e)
            await asyncio.sleep(BROADCAST_TICK)


async def _remember_username(bot: Bot, db) -> None:
    try:
        me = await bot.get_me()
        if me.username:
            await access.set_brand_setting(db, "brand.bot_username", me.username)
        log.info("бот @%s готов", me.username)
    except Exception as e:
        log.warning("не удалось узнать имя бота: %s", e)


class _ThrottledSession(AiohttpSession):
    async def make_request(self, bot, method, timeout=None):
        if not flood.is_control(method.__api_method__):
            await flood.acquire()
        return await super().make_request(bot, method, timeout)


class _BroadcastSession(AiohttpSession):
    _is_broadcast_session = True

    async def make_request(self, bot, method, timeout=None):
        if not flood.is_control(method.__api_method__):
            await flood.acquire_broadcast()
        return await super().make_request(bot, method, timeout)


def build_dispatcher(db) -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(DbMiddleware(db))
    dp.message.middleware(ThrottleMiddleware())
    dp.errors.register(on_error)
    # Palm intake must run before the legacy feature router so photo and document
    # events share one canonical path and receive explicit recovery responses.
    dp.include_router(onboarding.router)
    dp.include_router(palm.router)
    dp.include_router(features.router)
    dp.include_router(growth.router)
    dp.include_router(shop.router)
    dp.include_router(profile.router)
    dp.include_router(chat.router)
    return dp


async def main() -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан в .env")
    for warning in settings.ready:
        log.warning("проверь конфигурацию: %s", warning)
    sentry.init()
    db = await connect()
    bot = Bot(settings.bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML),
              session=_ThrottledSession(timeout=60))
    dp = build_dispatcher(db)
    names = {"anthropic": "Claude API", "openai": "OpenAI API",
             "custom": f"свой сервер ({settings.custom_model_main})",
             "off": "офлайн-режим (без LLM)"}
    chain = " → ".join(names.get(p, p) for p in settings.provider_chain) or names["off"]
    log.info("Оракул запускается. LLM-цепочка: %s", chain)
    await _remember_username(bot, db)
    try:
        await bot.set_my_commands(COMMANDS)
        await bot.set_my_commands(COMMANDS_EN, language_code="en")
        if settings.webapp_url:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="✨ Оракул", web_app=WebAppInfo(url=settings.webapp_url + "/")))
    except Exception as e:
        log.warning("не удалось задать меню команд: %s", e)
    tasks = [
        asyncio.create_task(scheduler.run(bot, db), name="scheduler"),
        asyncio.create_task(broadcast_loop(bot, db), name="broadcasts"),
    ]
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await chat_service.drain_background()
        await analytics.drain()
        await access.drain_touch_tasks()
        await bot.session.close()
        await db.close()
        log.info("Оракул остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("остановка по Ctrl+C")
