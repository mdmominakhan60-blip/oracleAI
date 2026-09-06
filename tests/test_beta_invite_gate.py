"""BUS-269 invite-gate: коды kind=invite, гейт /start, E_PROMO, флаг.

Сценарии:
- redeem invite кода → возвращает результат, granted=None, событие без code.
- повторный redeem тем же кодом другим tg_id → атомарно None (max_uses=1).
- гейт активен: /start без кода → мягкий отказ с waitlist-ссылкой.
- гейт активен: /start с invite-кодом → проходит дальше.
- гейт выключен: /start без кода → проходит.
- onboarded пользователь → гейт не трогает.
"""
from __future__ import annotations

import asyncio



async def _flag_on(*_, **__) -> bool:
    return True


async def _flag_off(*_, **__) -> bool:
    return False
from aiogram.fsm.context import FSMContext  # noqa: E402 — моки определяются до импортов
from aiogram.fsm.storage.base import StorageKey  # noqa: E402 — моки определяются до импортов
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402 — моки определяются до импортов

from app.bot import onboarding  # noqa: E402 — моки определяются до импортов
from app.repo import content as content_repo, growth, users  # noqa: E402
from app.services import analytics, billing as billing_svc  # noqa: E402


# ──────────────────────────── моки (совместимо с test_bot_fsm.py) ──────────────

class _User:
    def __init__(self, tg_id: int, first_name: str = "Тест", username: str | None = None):
        self.id = tg_id
        self.first_name = first_name
        self.username = username
        self.language_code = "ru"


class _Message:
    def __init__(self, tg_id: int, text: str = "/start", args: str = ""):
        self.from_user = _User(tg_id)
        self.text = text
        self.args = args
        self.replied: list[str] = []

    async def answer(self, text: str = "", **kwargs):
        self.replied.append(text)
        return self


class _Command:
    def __init__(self, args: str = ""):
        self.args = args


def _state_for(tg_id: int = 1) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(chat_id=tg_id, user_id=tg_id, bot_id=42, thread_id=0)
    return FSMContext(storage=storage, key=key)


def _lang(user) -> str:
    return "en" if user["lang"] == "en" else "ru"


# ──────────────────────────── redeem invite ────────────────────────────────────

async def test_redeem_invite_returns_result_without_grant(db):
    codes = await growth.create_codes(db, 1, kind="invite", batch="BETA1",
                                      max_uses=1, valid_days=14, plan_code="vip",
                                      days=0)
    result = await billing_svc.redeem_promo(db, 1001, codes[0])
    assert result is not None
    assert result["kind"] == "invite"
    assert result["granted"] is None
    assert result["batch"] == "BETA1"


async def test_invite_is_single_use_under_parallel_redemptions(db):
    codes = await growth.create_codes(db, 1, kind="invite", batch="BETA1",
                                      max_uses=1, valid_days=14, days=0)

    results = await asyncio.gather(
        *[billing_svc.redeem_promo(db, uid, codes[0]) for uid in (1001, 1002, 1003)],
        return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 1, "только один из параллельных redeem должен пройти"
    assert all(isinstance(r, billing_svc.PromoRedeemRefused) for r in results
               if isinstance(r, Exception)), "отказы — по состоянию кода, не сбои"


async def test_invite_redeem_writes_promo_event_without_code(db):
    codes = await growth.create_codes(db, 1, kind="invite", batch="BETA1",
                                      max_uses=1, valid_days=14, days=0)
    await billing_svc.redeem_promo(db, 1001, codes[0])
    await analytics.drain()
    cur = await db.execute(
        "SELECT name, props_json FROM events WHERE tg_id=1001 AND name='promo_redeemed'"
    )
    row = await cur.fetchone()
    assert row is not None
    props = __import__("json").loads(row["props_json"] or "{}")
    assert props["batch"] == "BETA1"
    assert props["kind"] == "invite"
    assert "code" not in props, "code запрещён в событии (низкая кардинальность)"


async def test_invite_redeem_sets_source_from_batch(db):
    await users.ensure(db, 1004, "Тест", "t1004")
    codes = await growth.create_codes(db, 1, kind="invite", batch="BETA1",
                                      max_uses=1, valid_days=14, days=0)
    await billing_svc.redeem_promo(db, 1004, codes[0])
    u = await users.get(db, 1004)
    assert u["source"] == "promo:BETA1"


# ──────────────────────────── гейт /start ─────────────────────────────────────

async def test_start_without_code_refused_when_flag_on(db, monkeypatch):
    await users.ensure(db, 2001, "Аня", "anya2001")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    # перехватываем проверку флага сразу на уровне is_on, чтобы не
    # завязываться на внутренний flag_row
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = _Message(2001)
    state = _state_for(2001)
    await onboarding.start_deeplink(message, _Command(), state, db)
    assert len(message.replied) == 1
    text = message.replied[0]
    assert "листе ожидания" in text or "waitlist" in text.lower()
    # E_START не записан при отказе
    await analytics.drain()
    cur = await db.execute("SELECT 1 FROM events WHERE tg_id=2001 AND name='onboarding_started' LIMIT 1")
    assert await cur.fetchone() is None


async def test_start_with_invite_code_passes_gate(db, monkeypatch):
    await users.ensure(db, 2002, "Борис", "b2002")
    codes = await growth.create_codes(db, 1, kind="invite", batch="BETA1",
                                      max_uses=1, valid_days=14, days=0)
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = _Message(2002)
    message.args = codes[0]
    state = _state_for(2002)
    await onboarding.start_deeplink(message, _Command(args=codes[0]), state, db)
    # ответ с «Инвайт принят» — invite-code deeplink проходит гейт
    assert any("Инвайт принят" in t or "Invite code accepted" in t for t in message.replied), \
        f"replies={message.replied}"
    await analytics.drain()
    cur = await db.execute("SELECT 1 FROM events WHERE tg_id=2002 AND name='onboarding_started' LIMIT 1")
    assert await cur.fetchone() is not None


async def test_start_passes_when_flag_off(db, monkeypatch):
    await users.ensure(db, 2003, "Вика", "v2003")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=False)
    monkeypatch.setattr(content_repo, "is_on", _flag_off)
    message = _Message(2003)
    state = _state_for(2003)
    await onboarding.start_deeplink(message, _Command(), state, db)
    assert any("Добро пожаловать" in t or "Welcome" in t for t in message.replied)


async def test_gate_does_not_touch_onboarded_user(db, monkeypatch):
    await users.ensure(db, 2004, "Глеб", "g2004")
    await users.update(db, 2004, onboarded=True)
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = _Message(2004)
    state = _state_for(2004)
    await onboarding.start_deeplink(message, _Command(), state, db)
    assert any("С возвращением" in t or "Welcome back" in t for t in message.replied)


# ─────────────── B4: маркетплейс-ваучеры mpl_* (BUS-355) ─────────────────────

async def _start_with(db, tg_id: int, args: str = ""):
    message = _Message(tg_id)
    message.args = args
    state = _state_for(tg_id)
    await onboarding.start_deeplink(message, _Command(args=args), state, db)
    return message


async def test_b4_mpl_voucher_deeplink_passes_gate(db, monkeypatch):
    """Критерий приёмки: redeем mpl-кода не-onboarded юзером через /start <код>
    → onboarding продолжается, waitlist-отказа нет."""
    await users.ensure(db, 2101, "Дина", "d2101")
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=100,
                                      batch="mpl_ggsel_2026-10")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = await _start_with(db, 2101, codes[0])
    assert any("Кристаллов" in t or "Crystals" in t for t in message.replied), \
        f"подтверждение выдачи ваучера не показано: {message.replied}"
    assert not any("листе ожидания" in t or "waitlist" in t.lower()
                   for t in message.replied), f"waitlist-отказ после mpl-редема: {message.replied}"
    await analytics.drain()
    cur = await db.execute(
        "SELECT 1 FROM events WHERE tg_id=2101 AND name='onboarding_started' LIMIT 1")
    assert await cur.fetchone() is not None, "onboarding не продолжился"


async def test_b4_mpl_voucher_deeplink_writes_source_attribution(db, monkeypatch):
    """Критерий приёмки: источник атрибуции promo:mpl_* записан."""
    await users.ensure(db, 2102, "Ева", "e2102")
    codes = await growth.create_codes(db, 1, kind="plan_days", days=7,
                                      plan_code="trial", batch="mpl_pok_2026-10")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    await _start_with(db, 2102, codes[0])
    u = await users.get(db, 2102)
    assert u["source"] == "promo:mpl_pok_2026-10"


async def test_b4_persistent_mpl_redemption_unblocks_later_start(db, monkeypatch):
    """Редем mpl-ваучера через /promo, повторный /start БЕЗ кода — гейт пущает:
    факт покупки персистентен (promo_redemptions), не локальная переменная."""
    await users.ensure(db, 2103, "Жанна", "z2103")
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=50,
                                      batch="mpl_ggsel_2026-10")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)

    message = _Message(2103)
    message.text = codes[0]
    state = _state_for(2103)
    await onboarding.promo_enter(message, state, db)
    assert not any("листе ожидания" in t for t in message.replied)

    second = await _start_with(db, 2103)
    assert not any("листе ожидания" in t or "waitlist" in t.lower()
                   for t in second.replied), \
        f"повторный /start после mpl-редема через /promo упёрся в гейт: {second.replied}"
    assert any("знакомство" in t or "begin" in t.lower() or "Welcome" in t
               for t in second.replied), f"onboarding не предложен: {second.replied}"


async def test_b4_free_non_mpl_promo_does_not_open_gate(db, monkeypatch):
    """Anti-bypass: бесплатный не-mpl crystals-промокод НЕ открывает бету."""
    await users.ensure(db, 2104, "Зоя", "z2104")
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=25,
                                      batch="GIFT_CRM")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = await _start_with(db, 2104, codes[0])
    assert any("Кристаллов" in t or "Crystals" in t for t in message.replied), \
        f"кристаллы по бесплатному коду должны быть выданы: {message.replied}"
    assert any("листе ожидания" in t or "waitlist" in t.lower()
               for t in message.replied), \
        f"бесплатный не-mpl код открыл гейт (bypass!): {message.replied}"


async def test_b4_free_non_mpl_promo_via_promo_cmd_does_not_onboard(db, monkeypatch):
    """Anti-bypass на пути /promo: не-mpl код не запускает онбординг."""
    await users.ensure(db, 2105, "Ира", "i2105")
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=25,
                                      batch="GIFT_CRM")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = _Message(2105)
    message.text = codes[0]
    state = _state_for(2105)
    await onboarding.promo_enter(message, state, db)
    assert any("Кристаллов" in t for t in message.replied)
    assert not any("знакомство" in t for t in message.replied), \
        f"бесплатный код запустил onboarding (bypass): {message.replied}"


async def test_b4_start_without_code_still_refused_after_fix(db, monkeypatch):
    """Критерий приёмки: обычный /start без кода при beta_invite_gate=1 →
    waitlist-отказ сохранён (никакой расширительной трактовки)."""
    await users.ensure(db, 2106, "Кира", "k2106")
    await content_repo.set_flag(db, "beta_invite_gate", is_on=True)
    monkeypatch.setattr(content_repo, "is_on", _flag_on)
    message = await _start_with(db, 2106)
    assert len(message.replied) == 1
    assert "листе ожидания" in message.replied[0] or "waitlist" in message.replied[0].lower()


async def test_b4_repo_persists_mpl_redemption_only(db):
    """redeemed_mpl_voucher: True только для mpl-партий, не для прочих кодов."""
    await users.ensure(db, 2107, "Лена", "l2107")
    mpl = await growth.create_codes(db, 1, kind="crystals", crystals=10,
                                    batch="mpl_ggsel_2026-10")
    gift = await growth.create_codes(db, 1, kind="crystals", crystals=10,
                                     batch="GIFT_CRM")
    assert await growth.redeemed_mpl_voucher(db, 2107) is False
    await billing_svc.redeem_promo(db, 2107, gift[0])
    assert await growth.redeemed_mpl_voucher(db, 2107) is False
    await billing_svc.redeem_promo(db, 2107, mpl[0])
    assert await growth.redeemed_mpl_voucher(db, 2107) is True
