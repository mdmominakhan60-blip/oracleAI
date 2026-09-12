"""Контент и конфигурация, управляемые из админки: настройки, тексты, флаги.

Всё, что здесь лежит, правится без деплоя — это требование ТЗ («все тексты и
промпты в конфигах, не в коде»). Код всегда имеет значение по умолчанию, а БД
его перекрывает: пустая база и упавший запрос не должны ломать продукт.
"""
from __future__ import annotations

import json
import zlib

from ..data.session import transaction, utcnow

# ─────────────────────────────── настройки ────────────────────────────────────


async def get_setting(db, key: str, default=None):
    cur = await db.execute("SELECT value_json FROM settings WHERE key=:key", {"key": key})
    row = await cur.fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except (TypeError, ValueError):
        return default


async def set_setting(db, key: str, value, admin_id: int | None = None) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO settings(key, value_json, updated_at, updated_by) "
            "VALUES(:key, :value_json, :updated_at, :updated_by) ON CONFLICT(key) DO UPDATE SET "
            "value_json=excluded.value_json, updated_at=excluded.updated_at, "
            "updated_by=excluded.updated_by",
            {"key": key, "value_json": json.dumps(value, ensure_ascii=False),
             "updated_at": utcnow(), "updated_by": admin_id})


async def all_settings(db) -> dict:
    cur = await db.execute("SELECT key, value_json FROM settings ORDER BY key")
    out = {}
    for row in await cur.fetchall():
        try:
            out[row["key"]] = json.loads(row["value_json"])
        except (TypeError, ValueError):
            out[row["key"]] = None
    return out


# ─────────────────────────── тексты и промпты ─────────────────────────────────

# Англоязычные defaults для текстов, которые первоначально были заведены только
# по-русски. Администратор может переопределить любой из них через meta_json:
# `title_en` и `body_en`; это не требует дублей строк и не ломает UNIQUE(kind, code).
DEFAULT_EN_CONTENT: dict[tuple[str, str], dict[str, str]] = {
    ("copy", "welcome"): {
        "title": "Onboarding welcome",
        "body": ("🌌 <b>The stars have been waiting for you.</b>\n\n"
                 "I am your personal Oracle: astrology, Tarot, and Destiny Matrix, "
                 "made for <i>you</i>.\n\n"
                 "To create your birth chart, I need only a few details. "
                 "What should I call you? ✨\n\n"
                 "By continuing, you accept the service rules and consent to the "
                 "processing of personal data. The full text is available in /help."),
    },
    ("copy", "limit_reached"): {
        "title": "Question limit reached",
        "body": ("🌙 <i>The stars are resting and the threads of possibility have "
                 "grown quiet...</i>\n\nYou've reached today's question limit. "
                 "Save your next question for dawn — or open the space with Crystals:"),
    },
    ("copy", "sub_over"): {
        "title": "Subscription ended",
        "body": ("💫 Our connection has grown thin — your access has ended.\n"
                 "I have kept everything you shared. Renew your connection with "
                 "the Universe 🎟"),
    },
    ("copy", "expiry_soon"): {
        "title": "Two days before subscription ends",
        "body": ("🌙 {name}, our connection is growing thin — fewer than two days remain...\n\n"
                 "I remember the words you shared, both the tender ones and the dreams. "
                 "Stay with me and I will keep them safe and meet you with a morning "
                 "forecast, as always. ✨"),
    },
    ("copy", "winback"): {
        "title": "Return after subscription ends",
        "body": ("💫 The stars have grown quiet, but I have not left — I am simply "
                 "waiting beyond the veil.\nYour memories are safe with me: return, "
                 "and we will continue where we paused."),
    },
    ("copy", "winback2"): {
        "title": "WB2: gift offer",
        "body": ("🎁 {name}, I have kept everything you shared with me, and I miss "
                 "our conversations ✨\n\n"
                 "Here is a gift from me — full VIP access for 7 days. Your personal "
                 "promo code: {code}\n\n"
                 "Activate it within 14 days — enter this command in the chat:\n"
                 "/promo {code}\n"
                 "The stars will wait, but a gift is best enjoyed soon 🌙"),
    },
    ("copy", "post_limit"): {
        "title": "After limit: gentle invite",
        "body": ("{name}, yesterday's questions are gone, but I can see the curiosity "
                 "is still there ✨\n\n"
                 "Without limits, these are always open to you: your card of the day "
                 "and forecast, your diary and practices, Tarot readings.\n\n"
                 "And if you'd like to ask as many questions as you wish — a "
                 "subscription opens my full depth for you. Drop by whenever the mood "
                 "strikes — I'm here 🌙"),
    },
    ("copy", "low_balance"): {
        "title": "Low balance: gentle reminder",
        "body": ("{name}, the Crystals in your balance are melting 🌙 Top up so our "
                 "connection isn't interrupted mid-practice.\n\n"
                 "You can do it anytime — in your Profile. No rush — I'll keep "
                 "everything safe."),
    },
    # Attention-queue playbook frames (BUS-293 §6, seeded per BUS-622/BUS-313 F2).
    ("copy", "pb1_vip_sleeping"): {
        "title": "Playbook PB-1: sleeping VIP",
        "body": ("{name}, it's been a while — this is {oracle_name} 🌙\n\n"
                 "I noticed your pause and wanted to ask: is everything alright?\n\n"
                 "If you're tired of forecasts or something isn't working for you — "
                 "tell me honestly, I'll adjust. If life simply got in the way — "
                 "write anyway, I'm here.\n\n"
                 "Your chart isn't going anywhere: I've kept everything you've "
                 "shared with me ✨"),
    },
    ("copy", "pb2_welcome_back"): {
        "title": "Playbook PB-2: welcome back",
        "body": ("{name}, how lovely to see you here again ✨\n\n"
                 "What brings you today — advice, or just a visit? Tell me — "
                 "I'm listening."),
    },
    ("copy", "pb3_offer_unclaimed"): {
        "title": "Playbook PB-3: unclaimed gift",
        "body": ("{name}, my gift from last week is still waiting unwrapped 🎁\n\n"
                 "It's yours until {code_until}.\n\n"
                 "If it's a stretch right now or something didn't feel right — "
                 "just say so, we'll find a solution. No hard feelings and no "
                 "pressure 🌙"),
    },
    ("copy", "pb4_plan_pain"): {
        "title": "Playbook PB-4: plan feels tight",
        "body": ("{name}, this week you hit the limit {N} times — the «{plan}» "
                 "plan feels tight for you ✨\n\n"
                 "On «{next_plan}» that's solved: {diff}.\n\n"
                 "Drop by whenever the mood strikes: {deep_link}"),
    },
    ("copy", "pb6_onboard_stuck"): {
        "title": "Playbook PB-6: onboarding stalled",
        "body": ("{name}, I noticed our introduction paused halfway — and I won't "
                 "rush you 🌙\n\n"
                 "Which step got stuck? Maybe something felt unclear — or the "
                 "timing just wasn't right. Tell me how to help, or come back "
                 "whenever you're ready ✨"),
    },
    ("copy", "pb7_refund"): {
        "title": "Playbook PB-7: refund",
        "body": ("{name}, I see the refund on your payment 🌙\n\n"
                 "I'm sorry it turned out this way. Tell me what happened — I want "
                 "to understand and make it right."),
    },
    # pb5_no_channel is an operator reference card (delivery statuses), not
    # client copy; seeded too so admins can override it without a release.
    ("copy", "pb5_no_channel"): {
        "title": "Playbook PB-5: channel closed",
        "body": ("forbidden — the client has closed the channel: messages won't "
                 "get through until the first successful delivery after "
                 "unblocking. Action: tag no-channel.\n\n"
                 "failed — a temporary delivery error: the scheduler will retry on "
                 "its own, no intervention needed. Action: observe.\n\n"
                 "Escalate to DevOps — only on a mass spike of failed within a "
                 "short window at regular volume."),
    },
    # welcome-цепочка W1-W3 (BUS-258, §1; копирайт BUS-263 §4)
    ("copy", "welcome_d1"): {
        "title": "Welcome: day 1",
        "body": ("{name}, the stars are ready for your first step ✨ Begin with a "
                 "5-minute practice — it will adapt to your rhythm and mood."),
    },
    ("copy", "welcome_d3"): {
        "title": "Welcome: day 3",
        "body": ("Three days have passed, and your first step is still waiting... "
                 "Perhaps a practice isn't what you need right now. Try asking "
                 "Oracle about whatever is on your mind — sometimes the answer "
                 "comes not through ritual but through conversation ✨"),
    },
    ("copy", "welcome_d7"): {
        "title": "Welcome: day 7",
        "body": ("{name}, a week has flown by — and I'm still here whenever you "
                 "need me ✨\n\n"
                 "A gentle hint: the most common first step here is "
                 "{top_first_step}. But your step can be anything at all — "
                 "it's yours."),
    },
    # onboarding-дожим O1-O2 (BUS-259, §2; копирайт BUS-263 §5)
    ("copy", "onboard_d1"): {
        "title": "Onboarding: day 1",
        "body": ("Just one step left — tell me your name, and I'll build your "
                 "chart of the day: the stars have already arranged themselves "
                 "into a pattern ✨\n\nIt only takes a minute."),
    },
    ("copy", "onboard_d3"): {
        "title": "Onboarding: day 3",
        "body": ("It seems this isn't the moment — and that's perfectly fine ✨\n\n"
                 "I won't bother you again: the stars can wait. I'll be here "
                 "when you call."),
    },
    ("copy", "onboard_btn_continue"): {
        "title": "Onboarding: continue button",
        "body": "✨ Continue",
    },
    # реактивация спящих R1-R2 (BUS-260, §3; копирайт BUS-263 §6)
    ("copy", "reactivate_r1"): {
        "title": "Reactivation: R1 personal",
        "body": ("{name}, your practice \"{practice_title}\" is still waiting "
                 "at step {day_index} — I've kept it safe for you ✨\n\n"
                 "It hasn't gone anywhere: return, and we'll continue right "
                 "where we paused."),
    },
    ("copy", "reactivate_r2"): {
        "title": "Reactivation: R2 fresh value",
        "body": ("{name}, life without practices works too. Sometimes it's "
                 "enough to simply drop by: your card of the day — a small, "
                 "one-minute ritual ✨\n\n"
                 "It's already waiting for you."),
    },
    # day-7 опрос (BUS-234)
    ("copy", "feedback_survey_invite"): {
        "title": "Survey: day-7 invite",
        "body": ("{name}, a week with me — time to look back 🌙\n"
                 "Tell me how you're finding Oracle — it takes a minute, "
                 "and I'll gift you 40 Crystals ✦"),
    },
    ("copy", "feedback_survey_remind"): {
        "title": "Survey: day-10 reminder",
        "body": ("{name}, I'm still gathering first-week impressions ✨ "
                 "A couple of your minutes = 40 Crystals ✦"),
    },
    ("copy", "feedback_form_head"): {
        "title": "Survey: form heading",
        "body": "A Week with Oracle 🌙",
    },
    ("copy", "feedback_form_intro"): {
        "title": "Survey: form intro",
        "body": ("Five short questions. For a thoughtful review — 40 Crystals ✦ "
                 "to your balance (enough for an in-depth Tarot reading). "
                 "Valid for 90 days."),
    },
    ("copy", "feedback_q_like"): {
        "title": "Survey: question Q1 (like)", "body": "What did you enjoy most?"},
    ("copy", "feedback_q_blocker"): {
        "title": "Survey: question Q2 (blocker)", "body": "What gets in the way?"},
    ("copy", "feedback_q_nps"): {
        "title": "Survey: question Q3 (nps)",
        "body": "How likely are you to recommend Oracle to a friend (0–10)?"},
    ("copy", "feedback_q_dream"): {
        "title": "Survey: question Q4 (dream)",
        "body": "What's missing? What do you dream of when you think of Oracle?"},
    ("copy", "feedback_q_next"): {
        "title": "Survey: question Q5 (next)", "body": "What should we add first?"},
    ("copy", "feedback_opt_like_forecasts"): {
        "title": "Survey: option like/forecasts", "body": "Forecasts"},
    ("copy", "feedback_opt_like_tarot"): {
        "title": "Survey: option like/tarot", "body": "Tarot"},
    ("copy", "feedback_opt_like_diary"): {
        "title": "Survey: option like/diary", "body": "Diary & practices"},
    ("copy", "feedback_opt_like_voice"): {
        "title": "Survey: option like/voice", "body": "Voice & answers"},
    ("copy", "feedback_opt_like_chart"): {
        "title": "Survey: option like/chart", "body": "Birth chart"},
    ("copy", "feedback_opt_blocker_offtopic"): {
        "title": "Survey: option blocker/offtopic", "body": "Answers miss the mark"},
    ("copy", "feedback_opt_blocker_slow"): {
        "title": "Survey: option blocker/slow", "body": "Too long a wait"},
    ("copy", "feedback_opt_blocker_paywall"): {
        "title": "Survey: option blocker/paywall", "body": "Too little for free"},
    ("copy", "feedback_opt_blocker_lost"): {
        "title": "Survey: option blocker/lost", "body": "Unclear what comes next"},
    ("copy", "feedback_opt_blocker_nothing"): {
        "title": "Survey: option blocker/nothing", "body": "Nothing gets in the way"},
    ("copy", "feedback_opt_next_compat"): {
        "title": "Survey: option next/compat", "body": "Compatibility"},
    ("copy", "feedback_opt_next_practices"): {
        "title": "Survey: option next/practices", "body": "More practices"},
    ("copy", "feedback_opt_next_lunar"): {
        "title": "Survey: option next/lunar", "body": "Lunar rhythm"},
    ("copy", "feedback_opt_next_personal"): {
        "title": "Survey: option next/personal", "body": "Personal guidance"},
    ("copy", "feedback_survey_hint_text"): {
        "title": "Survey: Q4 hint",
        "body": "A couple of sentences — and 40 Crystals are yours ✦ (50+ characters)"},
    ("copy", "feedback_thanks_bonus"): {
        "title": "Survey: thanks (bonus granted)",
        "body": ("Thank you for sharing! ✨\n"
                 "40 Crystals are already on your balance — enough for an "
                 "in-depth Tarot reading."),
    },
    ("copy", "feedback_thanks_saved"): {
        "title": "Survey: thanks (saved)",
        "body": "Thank you — your review is saved 🌙"},
    ("copy", "feedback_btn_webapp"): {
        "title": "Survey: web_app button", "body": "Answer and get 40 Crystals"},
    ("copy", "feedback_btn_later"): {
        "title": "Survey: 'not now' button", "body": "Not now"},
    ("copy", "feedback_btn_never"): {
        "title": "Survey: opt-out button", "body": "Don't ask again"},
    ("copy", "feedback_btn_back"): {
        "title": "Survey: 'back to Oracle' button", "body": "Back to Oracle"},
    ("copy", "feedback_btn_skip"): {
        "title": "Survey: skip button", "body": "Skip"},
    ("copy", "feedback_btn_other"): {
        "title": "Survey: 'other' button", "body": "Other…"},
    ("copy", "free_forecast_cta"): {
        "title": "Free forecast CTA",
        "body": "\n\n🔮 <b>Oracle</b> — your free daily forecast. Open it in Telegram: {url}",
    },
    ("copy", "free_lunar_alert"): {
        "title": "Free lunar alert",
        "body": "🌕 {moon} — a special night for you.\n\nOpen Oracle for a gentle lunar guide: {url}",
    },
    ("faq", "what_is_it"): {
        "title": "What is this service?",
        "body": ("Oracle is a personal AI astrologer. It creates your birth chart "
                 "from ephemerides, draws Tarot with an honest random selection, and "
                 "remembers what you choose to share. Code performs calculations; a "
                 "language model explains them."),
    },
    ("faq", "is_it_real"): {
        "title": "Are the calculations real?",
        "body": ("Yes. Birth charts use Swiss Ephemeris, the same data used by "
                 "professional astrologers, and Tarot cards are chosen with a "
                 "cryptographic random-number generator. The model receives completed "
                 "calculations and explains them rather than inventing them."),
    },
    ("faq", "privacy"): {
        "title": "What happens to my data?",
        "body": ("Your birth date and city are used only to calculate your chart. "
                 "Data is stored on our server and is not shared with third parties. "
                 "You may ask support to delete everything; your account will be anonymized."),
    },
}


def _lang(lang: str | None) -> str:
    return "en" if (lang or "").lower().startswith("en") else "ru"


def localized_item(item: dict, lang: str | None) -> dict:
    """Возвращает административную запись с выбранными title/body без мутации исходной."""
    result = dict(item)
    if _lang(lang) != "en":
        return result
    meta = content_meta(item)
    fallback = DEFAULT_EN_CONTENT.get((item.get("kind", ""), item.get("code", "")), {})
    result["title"] = meta.get("title_en") or fallback.get("title") or result.get("title")
    result["body"] = meta.get("body_en") or fallback.get("body") or result.get("body")
    return result


async def get_content(db, kind: str, code: str) -> dict | None:
    cur = await db.execute(
        "SELECT * FROM content_items WHERE kind=:kind AND code=:code AND is_active=1",
        {"kind": kind, "code": code})
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_text(db, kind: str, code: str, default: str = "", *,
                   lang: str | None = None) -> str:
    """Берёт текст на языке профиля с English fallback для legacy seed-контента."""
    item = await get_content(db, kind, code)
    if not item:
        return default
    localized = localized_item(item, lang)
    # Для EN не возвращаем случайно русский legacy body: если у ключа нет
    # перевода, используем явно заданный fallback вызывающего кода.
    if _lang(lang) == "en" and (kind, code) not in DEFAULT_EN_CONTENT:
        meta = content_meta(item)
        return meta.get("body_en") or default
    return localized.get("body") or default


async def list_content(db, kind: str | None = None, *,
                       active_only: bool = False) -> list[dict]:
    sql = ["SELECT * FROM content_items WHERE 1=1"]
    params: dict = {}
    if kind:
        sql.append("AND kind=:kind")
        params["kind"] = kind
    if active_only:
        sql.append("AND is_active=1")
    sql.append("ORDER BY kind, sort, code")
    cur = await db.execute(" ".join(sql), params)
    return [dict(r) for r in await cur.fetchall()]


async def upsert_content(db, kind: str, code: str, *, title: str | None = None,
                         body: str | None = None, meta: dict | None = None,
                         is_active: int | None = None, sort: int | None = None,
                         admin_id: int | None = None) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO content_items(kind, code, title, body, is_active, "
            "sort, created_at, updated_at) VALUES(:kind, :code, :title, :body, 1, 100, :created_at, :updated_at) "
            "ON CONFLICT (kind, code) DO NOTHING",
            {"kind": kind, "code": code, "title": title or code, "body": body or "",
             "created_at": utcnow(), "updated_at": utcnow()})
        fields: dict = {}
        if title is not None:
            fields["title"] = title
        if body is not None:
            fields["body"] = body
        if meta is not None:
            fields["meta_json"] = json.dumps(meta, ensure_ascii=False)
        if is_active is not None:
            fields["is_active"] = int(is_active)
        if sort is not None:
            fields["sort"] = sort
        if fields:
            keys = ", ".join(f"{k}=:{k}" for k in fields)
            # INVARIANT: keys only from allowlist above — never interpolate user input
            await db.execute(
                f"UPDATE content_items SET {keys}, updated_at=:updated_at, updated_by=:updated_by "
                f"WHERE kind=:kind AND code=:code",
                {**fields, "updated_at": utcnow(), "updated_by": admin_id,
                 "kind": kind, "code": code})


async def delete_content(db, kind: str, code: str) -> None:
    async with transaction(db):
        await db.execute("DELETE FROM content_items WHERE kind=:kind AND code=:code",
                         {"kind": kind, "code": code})


def content_meta(item: dict | None) -> dict:
    if not item:
        return {}
    try:
        return json.loads(item.get("meta_json") or "{}")
    except (TypeError, ValueError):
        return {}


# ─────────────────────────────── фиче-флаги ───────────────────────────────────

async def flag_row(db, code: str):
    cur = await db.execute("SELECT * FROM feature_flags WHERE code=:code", {"code": code})
    return await cur.fetchone()


async def is_on(db, code: str, tg_id: int | None = None, *,
                default: bool = False) -> bool:
    """Включена ли фича. При `rollout_pct < 100` — стабильный процент аудитории.

    Попадание в процент считается от хеша (код фичи + id), а не от случайного
    числа: иначе одна и та же клиентка при каждом запросе то видела бы фичу, то
    нет, и это выглядело бы как поломка.
    """
    row = await flag_row(db, code)
    if row is None:
        return default
    if not row["is_on"]:
        return False
    pct = row["rollout_pct"] if row["rollout_pct"] is not None else 100
    if pct >= 100 or tg_id is None:
        return True          # без id раскатку не посчитать — считаем включённой
    bucket = zlib.crc32(f"{code}:{tg_id}".encode()) % 100
    return bucket < pct


async def list_flags(db) -> list[dict]:
    cur = await db.execute("SELECT * FROM feature_flags ORDER BY code")
    return [dict(r) for r in await cur.fetchall()]


async def set_flag(db, code: str, *, is_on: bool | None = None,
                   rollout_pct: int | None = None, description: str | None = None,
                   admin_id: int | None = None) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO feature_flags(code, is_on, rollout_pct, updated_at) "
            "VALUES(:code, 0, 100, :updated_at) ON CONFLICT (code) DO NOTHING",
            {"code": code, "updated_at": utcnow()})
        fields: dict = {}
        if is_on is not None:
            fields["is_on"] = int(is_on)
        if rollout_pct is not None:
            fields["rollout_pct"] = max(0, min(100, int(rollout_pct)))
        if description is not None:
            fields["description"] = description
        if fields:
            keys = ", ".join(f"{k}=:{k}" for k in fields)
            # INVARIANT: keys only from allowlist above — never interpolate user input
            await db.execute(
                f"UPDATE feature_flags SET {keys}, updated_at=:updated_at, updated_by=:updated_by "
                f"WHERE code=:code",
                {**fields, "updated_at": utcnow(), "updated_by": admin_id, "code": code})
