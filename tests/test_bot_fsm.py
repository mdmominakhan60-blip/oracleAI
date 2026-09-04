"""Бот-FSM: сценарий «удали мои данные» (G28).

Хендлеры aiogram гоняем без живого бота: FSMContext на MemoryStorage ведёт
настоящие переходы состояний, а вместо Message — тонкий фейк с `text`,
`from_user` и подставным `answer`. Проверяем сам переход по FSM и то, что
данные правда стираются.
"""
from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.onboarding import (
    DeleteMe, Onb, delete_me, delete_me_confirm,
    onb_city, onb_city_pick, onb_date, onb_date_pick, onb_gender, onb_name, onb_time,
)

from app.repo import users


def test_admin_panel_button_is_visible_only_to_admin_and_uses_https_url(monkeypatch):
    from app.bot.keyboards import main_menu
    from app.config import settings

    monkeypatch.setattr(settings, "webapp_url", "https://oracle.example")
    admin_buttons = [button for row in main_menu(is_admin=True).inline_keyboard
                     for button in row if button.text == "📊 Панель управления"]
    assert len(admin_buttons) == 1
    assert admin_buttons[0].web_app.url == "https://oracle.example/admin"
    assert not any(button.text == "📊 Панель управления"
                   for row in main_menu(is_admin=False).inline_keyboard
                   for button in row)


def test_admin_command_is_hidden():
    from app.bot.main import COMMANDS

    assert not any(command.command == "admin" for command in COMMANDS)


class _User:
    def __init__(self, tg_id: int):
        self.id = tg_id

    @property
    def first_name(self) -> str:
        return "Тест"


class _Message:
    def __init__(self, tg_id: int, text: str):
        self.from_user = _User(tg_id)
        self.text = text
        self.replied = None
        self.reply_kwargs = {}

    async def answer(self, text: str = "", **kwargs):
        self.replied = text
        self.reply_kwargs = kwargs
        return self

    async def edit_text(self, text: str = "", **kwargs):
        self.replied = text
        self.reply_kwargs = kwargs

    async def edit_reply_markup(self, **kwargs):
        self.reply_kwargs.update(kwargs)


class _Callback:
    def __init__(self, tg_id: int, data: str, message: _Message):
        self.from_user = _User(tg_id)
        self.data = data
        self.message = message
        self.answered = None

    async def answer(self, text: str | None = None, **kwargs):
        self.answered = text


def _state_for() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(chat_id=1, user_id=1, bot_id=42, thread_id=0)
    return FSMContext(storage=storage, key=key)


async def test_onboarding_birth_date_saves_even_when_young(db):
    """Возрастной гейт удалён полностью: дата рождения сохраняется без отказа."""
    await users.ensure(db, 1005, "Аня")
    state = _state_for()
    await state.set_state(Onb.date)
    from datetime import date
    d = date.today()
    young = date(d.year - 12, d.month, max(1, d.day - 1)).strftime("%d.%m.%Y")
    message = _Message(1005, young)

    await onb_date(message, state, db)

    assert await state.get_state() == Onb.time.state
    from datetime import datetime as _dt
    expect = _dt.strptime(young, "%d.%m.%Y").date().isoformat()
    assert (await users.get(db, 1005))["birth_date"] == expect


async def test_onboarding_gender_is_saved_and_advances_to_date(db):
    await users.ensure(db, 1000, "Аня")
    state = _state_for()
    name_message = _Message(1000, "Аня")
    await onb_name(name_message, state, db)
    assert await state.get_state() == Onb.gender.state
    assert name_message.reply_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "gender:f"

    callback = _Callback(1000, "gender:m", name_message)
    await onb_gender(callback, state, db)
    assert await state.get_state() == Onb.date.state
    assert (await users.get(db, 1000))["gender"] == "m"


async def test_onboarding_gender_skip_keeps_neutral_fallback(db):
    await users.ensure(db, 1004, "Вера")
    state = _state_for()
    message = _Message(1004, "Вера")
    await onb_name(message, state, db)
    await onb_gender(_Callback(1004, "gender:skip", message), state, db)
    assert (await users.get(db, 1004))["gender"] is None
    assert await state.get_state() == Onb.date.state


async def test_onboarding_date_picker_saves_date_and_advances_to_time(db):
    await users.ensure(db, 1010, "Аня")
    state = _state_for()
    await state.set_state(Onb.date)
    message = _Message(1010, "")

    # декада → год → месяц → день
    await onb_date_pick(_Callback(1010, "bd:yg:1990", message), state, db)
    assert "Выбери год" in message.replied
    await onb_date_pick(_Callback(1010, "bd:y:1999", message), state, db)
    assert "Выбери месяц" in message.replied
    await onb_date_pick(_Callback(1010, "bd:m:1999:6", message), state, db)
    assert "Выбери день" in message.replied
    await onb_date_pick(_Callback(1010, "bd:day:1999:6:21", message), state, db)

    user = await users.get(db, 1010)
    assert user["birth_date"] == "1999-06-21"
    assert await state.get_state() == Onb.time.state


async def test_onboarding_date_text_fallback_button(db):
    await users.ensure(db, 1011, "Аня")
    state = _state_for()
    await state.set_state(Onb.date)
    message = _Message(1011, "")

    await onb_date_pick(_Callback(1011, "bd:text", message), state, db)
    assert "21.06.1999" in message.replied
    assert await state.get_state() == Onb.date.state

    await onb_date(_Message(1011, "21.06.1999"), state, db)
    assert (await users.get(db, 1011))["birth_date"] == "1999-06-21"
    assert await state.get_state() == Onb.time.state


async def test_onboarding_city_pick_uses_fallback_dictionary(db):
    await users.ensure(db, 1012, "Аня")
    await users.update(db, 1012, birth_date="1990-06-21", birth_time="12:00", birth_time_known=0)
    state = _state_for()
    await state.set_state(Onb.city)
    message = _Message(1012, "")

    await onb_city_pick(_Callback(1012, "city:0", message), state, db)  # Москва

    user = await users.get(db, 1012)
    assert user["birth_city"] == "москва"
    assert user["chart_json"]
    assert await state.get_state() == Onb.confirm.state


async def test_onboarding_invalid_time_stays_on_time_step(db):
    await users.ensure(db, 1007, "Тест")
    state = _state_for()
    await state.set_state(Onb.time)
    message = _Message(1007, "25:90")

    await onb_time(message, state, db)

    assert await state.get_state() == Onb.time.state
    assert "распознать время" in message.replied


async def test_onboarding_unknown_city_is_recoverable(monkeypatch, db):
    await users.ensure(db, 1008, "Тест")
    await users.update(db, 1008, birth_date="1990-06-21", birth_time="12:00", birth_time_known=0)
    state = _state_for()
    await state.set_state(Onb.city)
    message = _Message(1008, "Несуществующий город")

    async def unknown_city(*_args, **_kwargs):
        return None, None, "Europe/Moscow"

    monkeypatch.setattr("app.bot.onboarding.geo.resolve_city_async", unknown_city)
    await onb_city(message, state, db)

    assert await state.get_state() == Onb.city.state
    assert "не нашла этот город" in message.replied


async def test_onboarding_chart_failure_is_recoverable(monkeypatch, db):
    await users.ensure(db, 1009, "Тест")
    await users.update(db, 1009, birth_date="1990-06-21", birth_time="12:00", birth_time_known=0)
    state = _state_for()
    await state.set_state(Onb.city)
    message = _Message(1009, "Казань")

    async def known_city(*_args, **_kwargs):
        return 55.79, 49.12, "Europe/Moscow"

    async def failed_chart(*_args, **_kwargs):
        raise RuntimeError("calculator down")

    monkeypatch.setattr("app.bot.onboarding.geo.resolve_city_async", known_city)
    monkeypatch.setattr("app.bot.onboarding.astro.compute_chart_async", failed_chart)
    await onb_city(message, state, db)

    assert await state.get_state() == Onb.city.state
    assert "не получилось собрать карту" in message.replied.lower()


async def test_delete_me_enters_confirmation_state(db):
    await users.ensure(db, 1001, "Аня")
    state = _state_for()
    await delete_me(_Message(1001, "/delete_me"), state, db)
    assert await state.get_state() == DeleteMe.confirm.state


async def test_delete_me_ignores_wrong_keyword(db):
    await users.ensure(db, 1002, "Белла")
    state = _state_for()
    await delete_me_confirm(_Message(1002, "пока не надо"), state, db)
    assert (await users.get(db, 1002))["status"] != "deleted"


async def test_delete_me_wipes_data_and_clears_state(db):
    await users.ensure(db, 1003, "Вера")
    state = _state_for()
    await delete_me_confirm(_Message(1003, "УДАЛИТЬ"), state, db)

    user = await users.get(db, 1003)
    assert user["status"] == "deleted"
    assert user["name"] == "удалено"
    assert await state.get_state() is None, "FSM должен был очиститься"


async def test_onboarding_prompts_show_step_progress(db):
    """Онбординг показывает «Шаг N/5», чтобы клиентка видела, сколько осталось."""
    await users.ensure(db, 1010, "Аня")
    state = _state_for()
    name_message = _Message(1010, "Аня")
    await onb_name(name_message, state, db)
    assert "Шаг 2/5" in name_message.replied
    await onb_gender(_Callback(1010, "gender:f", name_message), state, db)
    assert "Шаг 3/5" in name_message.replied


def test_step_label_is_bilingual_and_empty_outside_flow():
    from app.bot.onboarding import _step_label
    assert _step_label("city", "ru") == "Шаг 5/5\n"
    assert _step_label("city", "en") == "Step 5/5\n"
    assert _step_label("language", "ru") == ""


async def test_throttle_answers_friendly_message_instead_of_silence():
    """Второе сообщение в окне не исчезает молча: бот отвечает «не так быстро»."""
    from app.bot.main import ThrottleMiddleware
    mw = ThrottleMiddleware(interval=60)

    class _ThrottledUser:
        id = 777
        language_code = "ru"
    message = _Message(777, "вопрос")
    message.from_user = _ThrottledUser()
    data = {"event_from_user": message.from_user}

    async def _handler(_event, _data):
        return "handled"

    assert await mw(_handler, message, data) == "handled"  # первое — проходит
    assert await mw(_handler, message, data) is None       # второе — гасится
    assert "быстро" in message.replied
    message.text = "вопрос на английском"
    message.from_user.language_code = "en-US"
    await mw(_handler, message, data)
    assert "Too fast" in message.replied
