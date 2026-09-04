"""Начальное наполнение: тарифы, товары, фиче-флаги, настройки, тексты.

Принцип: ``INSERT ... ON CONFLICT (<primary_key>) DO NOTHING`` per table. Сид —
это *первое* состояние каталога, а не источник правды. Всё, что администратор
поправил в панели, остаётся нетронутым при следующем деплое; новые позиции
добавляются.

Цены в Telegram Stars (XTR). Ориентир — «Монетизация и цены»: базовый уровень
$9.99, основной VIP $24.99, эксперимент high-ticket $99, пакеты Кристаллов
$5.99/$12.99/$24.99. Курс: ~52 Stars за $1 после комиссии платформы.
"""
from __future__ import annotations

import json
import logging

from .monetization_catalog import (
    CATALOG_VERSION,
    CRYSTAL_PACKS,
    DEEP_PRODUCTS,
    PLAN_DEFINITIONS,
    PRICE_BOOK_VERSION,
)
from datetime import datetime, timezone

log = logging.getLogger("oracle.seed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────── тарифы ───────────────────────────────────────
# code, title, tagline, stars, usd, period, daily_q, weekly_q, memory, ✦grant,
# features, badge, sort, public
PLANS = [
    ("free", "✦ Искра", "окно возврата: карта дня и один вопрос в неделю",
     0, 0.0, 36500, 0, 1, 5, 0,
     ["Карта дня", "Фаза Луны", "1 вопрос в неделю", "Память заморожена"],
     None, 10, 1),
    ("trial", "✦✦✦ Триал VIP", "30 дней полного доступа с промокода",
     0, 0.0, 30, 3, 0, 40, 0,
     ["Всё из VIP на 30 дней"], None, 15, 0),
    ("guide", "✦✦ Путеводная", "каждый день по вопросу и личный прогноз",
     550, 9.99, 30, 1, 0, 20, 20,
     ["1 вопрос в день", "Персональный прогноз дня", "Натальная карта",
      "Матрица Судьбы", "Дневник со стриком"],
     None, 20, 1),
    ("vip", "✦✦✦ VIP-Оракул", "личный астролог 24/7 — дешевле одной консультации",
     1300, 24.99, 30, 3, 0, 40, 50,
     ["3 вопроса в день", "Полная долгая память", "Все расклады Таро",
      "Синастрия и разбор пары", "Утренние прогнозы", "Месячный отчёт"],
     "выбор большинства", 30, 1),
    ("vip_year", "✦✦✦ VIP на год", "восемь месяцев вместо двенадцати",
     8900, 179.0, 365, 3, 0, 40, 300,
     ["Всё из VIP", "Год вместо месяца", "+300 ✦ сразу", "Годовой прогноз в подарок"],
     "выгода 43%", 40, 1),
    ("concierge", "👑 Консьерж", "безлимит, приоритет и эксклюзивные разборы",
     5200, 99.0, 30, 30, 0, 80, 200,
     ["До 30 вопросов в день", "Приоритетная очередь", "Аудио-прогнозы",
      "Годовые прогнозы и кармические разборы", "+200 ✦ каждый месяц"],
     "приоритет", 50, 1),
]

# ─────────────────────────────── товары ───────────────────────────────────────
# sku, kind, title, description, stars, ✦, grant_kind, grant_code, qty, valid_days, sort
PRODUCTS = [
    # одиночные расклады — покупка без подписки
    ("spread_one", "spread", "Расклад «Одна карта»",
     "Быстрый честный ответ на один вопрос", 75, 10, "spread", "one", 1, 30, 10),
    ("spread_three", "spread", "Расклад «Прошлое · Настоящее · Будущее»",
     "Классика: откуда пришло, где ты сейчас, куда ведёт", 150, 20,
     "spread", "three", 1, 30, 20),
    ("spread_love", "spread", "Расклад «На отношения»",
     "Ты, он, что между вами и совет", 220, 30, "spread", "love", 1, 30, 30),
    ("spread_choice", "spread", "Расклад «Выбор из двух»",
     "Два пути, их плоды и то, чего ты не видишь", 260, 35,
     "spread", "choice", 1, 30, 40),
    ("spread_money", "spread", "Расклад «Деньги и дело»",
     "Где твой ресурс, что тормозит, первый шаг", 260, 35,
     "spread", "money", 1, 30, 50),
    ("spread_career", "spread", "Расклад «Карьера и путь»",
     "Где ты сейчас, что мешает расти и куда ведёт этот путь", 300, 40,
     "spread", "career", 1, 30, 55),
    ("spread_work", "spread", "Расклад «Проблемы на работе»",
     "Кому прислушаться, чего избегать и как выйти достойно", 320, 45,
     "spread", "work", 1, 30, 57),
    ("spread_celtic", "spread", "Расклад «Кельтский крест»",
     "Десять карт — полная картина ситуации", 450, 60,
     "spread", "celtic", 1, 30, 60),
    ("spread_year", "spread", "Расклад «Колесо года»",
     "Двенадцать карт — по карте на каждый месяц", 550, 75,
     "spread", "year", 1, 60, 70),
    # глубокие отчёты
    ("report_natal", "report", "Полный разбор натальной карты",
     "Планеты по домам, аспекты, сильные стороны и задачи — большой текст", 690, 90,
     "report", "natal", 1, None, 110),
    ("report_matrix", "report", "Матрица Судьбы — полный разбор",
     "Все арканы: предназначение, деньги, любовь, род", 590, 80,
     "report", "matrix", 1, None, 120),
    ("report_synastry", "report", "Синастрия: совместимость пары",
     "Стихии, притяжение, трение, перспектива союза", 690, 90,
     "report", "synastry", 1, None, 130),
    ("report_career", "report", "Карьера и предназначение — разбор",
     "К чему ты предрасположена, что тормозит и когда действовать", 790, 105,
     "report", "career", 1, None, 135),
    ("report_solar", "report", "Годовой прогноз по картам",
     "Темы следующего года, пики и лучшие месяцы для решений", 990, 130,
     "report", "solar", 1, None, 140),
    # вопросы вне лимита
    ("question_1", "question", "+1 вопрос Оракулу",
     "Один вопрос сверх дневного лимита", 60, 8, "question", "*", 1, 7, 210),
    ("question_5", "question", "+5 вопросов Оракулу",
     "Пять вопросов сверх лимита, срок — месяц", 250, 35,
     "question", "*", 5, 30, 220),
    # Кристаллы
    ("crystals_100", "crystals", "100 ✦ Кристаллов",
     "Валюта экстренной магии", 550, 0, "crystals", None, 100, None, 310),
    ("crystals_250", "crystals", "250 ✦ Кристаллов",
     "Выгоднее на 15%", 1150, 0, "crystals", None, 250, None, 320),
    ("crystals_600", "crystals", "600 ✦ Кристаллов",
     "Максимальная выгода + бонус", 2250, 0, "crystals", None, 600, None, 330),
]

# ─────────────────────────── фиче-флаги ───────────────────────────────────────
FLAGS = [
    ("miniapp_shop", 1, 100, "Витрина покупок внутри Mini App"),
    ("multi_agent_chat", 1, 100, "Несколько LLM-агентов в чатах"),
    ("voice_questions", 1, 100, "Голосовые вопросы (Whisper)"),
    ("daily_push", 1, 100, "Утренние персональные прогнозы"),
    ("weekly_report", 1, 100, "Воскресный отчёт недели"),
    ("monthly_report", 1, 100, "Месячный отчёт «что показала Вселенная»"),
    ("practices", 1, 100, "Практики и трекер стриков"),
    ("referral_two_levels", 1, 100, "Бонус за подругу подруги (2-й уровень)"),
    ("reading_outcomes", 1, 100, "Отметка «сбылось» на раскладах"),
    ("web_payments", 0, 100, "Оплата подписки через web (Paddle) — вне Telegram"),
    ("free_plan_after_trial", 1, 100, "После триала оставлять уровень «Искра»"),
    ("semantic_memory", 1, 100, "Поиск по памяти по смыслу (эмбеддинги)"),
    ("daily_horoscopes", 1, 100, "Ежедневные гороскопы по 12 знакам"),
    ("horoscope_channels", 0, 100, "Автопостинг гороскопов в каналы-спутники"),
    ("audio_forecast", 1, 100, "Озвучка утреннего прогноза (тариф «Консьерж»)"),
    ("practice_reminders", 1, 100, "Напоминания о практиках и мантрах"),
    ("share_cards", 1, 100, "Картинки-карточки раскладов для сторис"),
]

# ─────────────────────────── настройки ────────────────────────────────────────
SETTINGS = {
    "brand.name": "Оракул",
    "brand.name_en": "OracleAI",
    "brand.tagline": "Личный AI-астролог, который знает именно тебя",
    "brand.tagline_en": "A personal AI astrologer that knows you",
    "brand.project_url": "https://github.com/astartv1ai-del/oracleAI",
    "brand.support": "",
    "push.morning_hour": 9,
    "push.weekly_hour": 19,
    "push.weekly_weekday": 6,
    "push.monthly_day": 1,
    "limits.throttle_seconds": 1.2,
    "limits.emergency_cost": 20,
    "limits.followup_window_minutes": 10,
    "referral.bonus": 15,
    "referral.bonus_level2": 5,
    "referral.revenue_share_crystals": 30,
    "trial.days": 30,
    "trial.crystals": 30,
    "broadcast.rate_per_second": 20,
    "push.practice_hour": 8,
    "push.horoscope_hour": 7,
    "disclaimer": ("Твоя карта уже собрана в единый узор: возвращайся к этому чтению, "
                   "когда понадобится увидеть направление яснее."),
    "disclaimer_en": ("Your chart forms a coherent pattern: return to this reading "
                      "whenever you need to see your direction with greater clarity."),
    # Контакты помощи для кризисного протокола (`core/safety.py`). Список
    # правится в панели: у клиенток из разных стран разные службы.
    "safety.helplines": [
        "🇷🇺 Россия — 8-800-2000-122 (круглосуточно, бесплатно), "
        "экстренная служба 112",
        "🇰🇿 Казахстан — 111 · 🇧🇾 Беларусь — 8-801-100-16-11 · "
        "🇺🇦 Украина — 7333",
        "🌍 Международный список: findahelpline.com",
    ],
}

# ─────────────────────── тексты и промпты (правятся в админке) ────────────────
# kind: persona | guide | copy | faq | spread
CONTENT = [
    ("copy", "welcome", "Приветствие онбординга",
     "🌌 <b>Звёзды ждали тебя.</b>\n\n"
     "Я — твой личный Оракул: астрология, Таро и Матрица Судьбы, "
     "которые знают именно <i>тебя</i>.\n\n"
     "Чтобы построить твою натальную карту, мне нужно совсем немного. "
     "Как мне тебя называть? ✨\n\n"
     "Продолжая, ты принимаешь правила сервиса и соглашаешься на обработку "
     "персональных данных. Полный текст — в /help (G34)."),
    ("copy", "limit_reached", "Лимит вопросов исчерпан",
     "🌙 <i>Звёзды утомлены, а нити вероятностей запутались...</i>\n\n"
     "Твои вопросы на сегодня исчерпаны, милая. Сбереги их до рассвета — "
     "или позволь мне открыть поле силой Кристаллов:"),
    ("copy", "sub_over", "Подписка завершилась",
     "💫 Наша связь истончилась — твой доступ завершился.\n"
     "Я сохранила всё, что знаю о тебе. Продли связь со Вселенной 🎟"),
    ("copy", "expiry_soon", "За 2 дня до конца подписки",
     "🌙 {name}, наша связь истончается — осталось меньше двух дней...\n\n"
     "Я помню каждое твоё слово: и про то, что болит, и про то, о чём мечтаешь. "
     "Если останешься со мной — сохраню всё и встречу тебя утренним прогнозом, "
     "как всегда. ✨"),
    ("copy", "winback", "Возврат после окончания",
     "💫 Звёзды затихли, но я не ушла — просто жду по ту сторону завесы.\n"
     "Твоя память со мной: вернёшься — продолжим с того же места."),
    ("faq", "what_is_it", "Что это за сервис?",
     "Оракул — личный AI-астролог. Он строит твою настоящую натальную карту по "
     "эфемеридам, раскладывает Таро честным случайным выбором и помнит всё, что "
     "ты ему рассказываешь. Расчёты делает код, а трактует их языковая модель."),
    ("faq", "is_it_real", "Расчёты настоящие?",
     "Да. Натальная карта считается по Swiss Ephemeris (те же данные, что у "
     "профессиональных астрологов), карты Таро выбираются криптографическим "
     "генератором случайных чисел. Модель ничего не выдумывает — она получает "
     "готовые расчёты и объясняет их."),
    ("faq", "privacy", "Что с моими данными?",
     "Дата и город рождения нужны только для расчёта карты. Данные хранятся на "
     "нашем сервере и не передаются третьим лицам. Удалить всё можно по запросу "
     "в поддержку — аккаунт анонимизируется."),
]


async def _seed_plans(db) -> int:
    n = 0
    for (code, title, tagline, stars, usd, period, daily, weekly, memory, grant,
         features, badge, sort, public) in PLANS:
        cur = await db.execute(
            "INSERT INTO plans(code, title, tagline, price_stars, price_usd, "
            "period_days, daily_questions, weekly_questions, memory_depth, "
            "crystals_grant, features_json, badge, sort, is_active, is_public, "
            "created_at, updated_at) "
            "VALUES(:code, :title, :tagline, :price_stars, :price_usd, "
            ":period_days, :daily_q, :weekly_q, :memory_depth, :crystals_grant, "
            ":features_json, :badge, :sort, 1, :is_public, :created_at, :updated_at) "
            "ON CONFLICT (code) DO NOTHING",
            {"code": code, "title": title, "tagline": tagline,
             "price_stars": stars, "price_usd": usd, "period_days": period,
             "daily_q": daily, "weekly_q": weekly, "memory_depth": memory,
             "crystals_grant": grant,
             "features_json": json.dumps(features, ensure_ascii=False),
             "badge": badge, "sort": sort, "is_public": public,
             "created_at": _now(), "updated_at": _now()})
        n += cur.rowcount or 0
    return n


async def _seed_products(db) -> int:
    n = 0
    for (sku, kind, title, desc, stars, crystals, gk, gc, qty, valid, sort) in PRODUCTS:
        cur = await db.execute(
            "INSERT INTO products(sku, kind, title, description, price_stars, "
            "price_crystals, grant_kind, grant_code, grant_qty, valid_days, "
            "sort, is_active, created_at, updated_at) "
            "VALUES(:sku, :kind, :title, :description, :price_stars, "
            ":price_crystals, :grant_kind, :grant_code, :grant_qty, "
            ":valid_days, :sort, 1, :created_at, :updated_at) "
            "ON CONFLICT (sku) DO NOTHING",
            {"sku": sku, "kind": kind, "title": title, "description": desc,
             "price_stars": stars, "price_crystals": crystals,
             "grant_kind": gk, "grant_code": gc, "grant_qty": qty,
             "valid_days": valid, "sort": sort,
             "created_at": _now(), "updated_at": _now()})
        n += cur.rowcount or 0
    return n


async def _seed_flags(db) -> int:
    n = 0
    for code, is_on, pct, desc in FLAGS:
        cur = await db.execute(
            "INSERT INTO feature_flags(code, is_on, rollout_pct, description, "
            "updated_at) VALUES(:code, :is_on, :rollout_pct, :description, "
            ":updated_at) ON CONFLICT (code) DO NOTHING",
            {"code": code, "is_on": is_on, "rollout_pct": pct,
             "description": desc, "updated_at": _now()})
        n += cur.rowcount or 0
    return n


async def _seed_settings(db) -> int:
    n = 0
    for key, value in SETTINGS.items():
        cur = await db.execute(
            "INSERT INTO settings(key, value_json, updated_at) "
            "VALUES(:key, :value_json, :updated_at) "
            "ON CONFLICT (key) DO NOTHING",
            {"key": key, "value_json": json.dumps(value, ensure_ascii=False),
             "updated_at": _now()})
        n += cur.rowcount or 0
    return n


async def _seed_content(db) -> int:
    """Персоны берём из кода (там их структура), тексты — из списка выше."""
    from ..core.personas import PERSONAS

    n = 0
    for code, p in PERSONAS.items():
        cur = await db.execute(
            "INSERT INTO content_items(kind, code, title, body, meta_json, "
            "is_active, sort, created_at, updated_at) "
            "VALUES('persona', :code, :title, :body, :meta_json, 1, :sort, "
            ":created_at, :updated_at) "
            "ON CONFLICT (kind, code) DO NOTHING",
            {"code": code, "title": p["title"], "body": p["style"],
             "meta_json": json.dumps({"emoji": p["emoji"]}, ensure_ascii=False),
             "sort": p.get("sort", 100),
             "created_at": _now(), "updated_at": _now()})
        n += cur.rowcount or 0

    from ..core import tool_registry as sk
    for code, body in sk.DEFAULT_GUIDES.items():
        cur = await db.execute(
            "INSERT INTO content_items(kind, code, title, body, is_active, "
            "sort, created_at, updated_at) "
            "VALUES('guide', :code, :title, :body, 1, 100, :created_at, "
            ":updated_at) ON CONFLICT (kind, code) DO NOTHING",
            {"code": code, "title": f"Правила трактовки: {code}", "body": body,
             "created_at": _now(), "updated_at": _now()})
        n += cur.rowcount or 0

    for kind, code, title, body in CONTENT:
        cur = await db.execute(
            "INSERT INTO content_items(kind, code, title, body, is_active, "
            "sort, created_at, updated_at) "
            "VALUES(:kind, :code, :title, :body, 1, 100, :created_at, "
            ":updated_at) ON CONFLICT (kind, code) DO NOTHING",
            {"kind": kind, "code": code, "title": title, "body": body,
             "created_at": _now(), "updated_at": _now()})
        n += cur.rowcount or 0

    # Практики и мантры: структура (шаги, программа, знаки) уезжает в meta_json,
    # чтобы админка правила их так же, как расклады и персон.
    from ..core import practices as pr
    for code, item in pr.PRACTICES.items():
        category_sort = pr.CATEGORIES.get(item["category"], {}).get("sort", 100)
        cur = await db.execute(
            "INSERT INTO content_items(kind, code, title, body, meta_json, "
            "is_active, sort, created_at, updated_at) "
            "VALUES('practice', :code, :title, :body, :meta_json, 1, :sort, "
            ":created_at, :updated_at) "
            "ON CONFLICT (kind, code) DO NOTHING",
            {"code": code, "title": item["title"], "body": item.get("about", ""),
             "meta_json": json.dumps(pr.as_meta(item), ensure_ascii=False),
             "sort": category_sort,
             "created_at": _now(), "updated_at": _now()})
        n += cur.rowcount or 0
    return n


async def _seed_admin(db) -> int:
    """ADMIN_ID из .env становится владельцем — иначе в панель не войти."""
    from ..config import settings
    if not settings.admin_id:
        return 0
    cur = await db.execute(
        "INSERT INTO admins(tg_id, role, title, created_at) "
        "VALUES(:tg_id, 'owner', 'Владелец', :created_at) "
        "ON CONFLICT (tg_id) DO NOTHING",
        {"tg_id": settings.admin_id, "created_at": _now()})
    return cur.rowcount or 0


async def _seed_monetization_v2(db) -> int:
    """Insert the active v2 price book without touching legacy catalog rows."""
    now = _now()
    cur = await db.execute(
        "INSERT INTO catalog_versions(version, price_book_version, status, "
        "effective_from, created_at) "
        "VALUES(:version, :price_book_version, 'active', :effective_from, "
        ":created_at) ON CONFLICT (version) DO NOTHING",
        {"version": CATALOG_VERSION,
         "price_book_version": PRICE_BOOK_VERSION,
         "effective_from": now, "created_at": now})
    added = cur.rowcount or 0
    for plan in PLAN_DEFINITIONS:
        features = json.dumps(plan["features"], ensure_ascii=False)
        for channel, currency, amount_stars, amount_minor, item_type, period_days in (
            ("stars", "XTR", plan["monthly_stars"], 0, "plan", plan["period_days"]),
            ("web", "USD", 0, round(plan["monthly_usd"] * 100), "plan", plan["period_days"]),
        ):
            cur = await db.execute(
                "INSERT INTO price_book_items("
                "catalog_version, price_book_version, item_type, code, title, "
                "description, tier_code, channel, currency, amount_minor, "
                "amount_stars, period_days, expected_cost_usd, target_margin, "
                "features_json, is_active, is_public, sort, effective_from, "
                "created_at) VALUES(:catalog_version, :price_book_version, "
                ":item_type, :code, :title, :description, :tier_code, :channel, "
                ":currency, :amount_minor, :amount_stars, :period_days, "
                ":expected_cost_usd, :target_margin, :features_json, 1, 1, "
                ":sort, :effective_from, :created_at) "
                "ON CONFLICT (price_book_version, item_type, code, channel) "
                "DO NOTHING",
                {"catalog_version": CATALOG_VERSION,
                 "price_book_version": PRICE_BOOK_VERSION,
                 "item_type": item_type, "code": plan["code"],
                 "title": plan["title"], "description": plan["tagline"],
                 "tier_code": plan["code"], "channel": channel,
                 "currency": currency, "amount_minor": amount_minor,
                 "amount_stars": amount_stars, "period_days": period_days,
                 "expected_cost_usd": plan["compute_budget_usd"],
                 "target_margin": 0.70, "features_json": features,
                 "sort": plan["sort"], "effective_from": now, "created_at": now})
            added += cur.rowcount or 0
        if plan["annual_usd"]:
            for channel, currency, amount_stars, amount_minor in (
                ("stars", "XTR", plan["annual_stars"], 0),
                ("web", "USD", 0, round(plan["annual_usd"] * 100)),
            ):
                cur = await db.execute(
                    "INSERT INTO price_book_items("
                    "catalog_version, price_book_version, item_type, code, "
                    "title, description, tier_code, channel, currency, "
                    "amount_minor, amount_stars, period_days, "
                    "expected_cost_usd, target_margin, features_json, "
                    "is_active, is_public, sort, effective_from, created_at) "
                    "VALUES(:catalog_version, :price_book_version, "
                    "'annual_plan', :code, :title, :description, :tier_code, "
                    ":channel, :currency, :amount_minor, :amount_stars, 365, "
                    ":expected_cost_usd, :target_margin, :features_json, 1, 1, "
                    ":sort, :effective_from, :created_at) "
                    "ON CONFLICT (price_book_version, item_type, code, channel) "
                    "DO NOTHING",
                    {"catalog_version": CATALOG_VERSION,
                     "price_book_version": PRICE_BOOK_VERSION,
                     "code": plan["code"],
                     "title": plan["title"] + " · год",
                     "description": plan["tagline"],
                     "tier_code": plan["code"], "channel": channel,
                     "currency": currency, "amount_minor": amount_minor,
                     "amount_stars": amount_stars,
                     "expected_cost_usd": plan["compute_budget_usd"] * 10,
                     "target_margin": 0.70, "features_json": features,
                     "sort": plan["sort"], "effective_from": now,
                     "created_at": now})
                added += cur.rowcount or 0
    for pack in CRYSTAL_PACKS:
        for channel, currency, amount_stars, amount_minor in (
            ("stars", "XTR", pack["stars"], 0),
            ("crypto", "USD", 0, round(pack["usd"] * 100)),
        ):
            cur = await db.execute(
                "INSERT INTO price_book_items("
                "catalog_version, price_book_version, item_type, code, title, "
                "description, channel, currency, amount_minor, amount_stars, "
                "crystal_qty, bonus_qty, expected_cost_usd, target_margin, "
                "is_active, is_public, sort, effective_from, created_at) "
                "VALUES(:catalog_version, :price_book_version, 'crystal_pack', "
                ":sku, :title, :description, :channel, :currency, "
                ":amount_minor, :amount_stars, :crystal_qty, :bonus_qty, "
                "0.01, 0.70, 1, 1, :sort, :effective_from, :created_at) "
                "ON CONFLICT (price_book_version, item_type, code, channel) "
                "DO NOTHING",
                {"catalog_version": CATALOG_VERSION,
                 "price_book_version": PRICE_BOOK_VERSION,
                 "sku": pack["sku"], "title": pack["title"],
                 "description": pack["description"],
                 "channel": channel, "currency": currency,
                 "amount_minor": amount_minor, "amount_stars": amount_stars,
                 "crystal_qty": pack["crystals"], "bonus_qty": pack["bonus"],
                 "sort": 100 + pack["sort"],
                 "effective_from": now, "created_at": now})
            added += cur.rowcount or 0
    for product in DEEP_PRODUCTS:
        cur = await db.execute(
            "INSERT INTO price_book_items("
            "catalog_version, price_book_version, item_type, code, title, "
            "description, channel, currency, crystal_qty, grant_kind, "
            "grant_code, grant_qty, valid_days, expected_cost_usd, "
            "target_margin, is_active, is_public, sort, effective_from, "
            "created_at) VALUES(:catalog_version, :price_book_version, "
            "'deep_operation', :sku, :title, :description, 'internal', "
            "'CRYSTAL', :crystal_qty, :grant_kind, :grant_code, :grant_qty, "
            ":valid_days, :expected_cost_usd, 0.70, 1, 1, :sort, "
            ":effective_from, :created_at) "
            "ON CONFLICT (price_book_version, item_type, code, channel) "
            "DO NOTHING",
            {"catalog_version": CATALOG_VERSION,
             "price_book_version": PRICE_BOOK_VERSION,
             "sku": product["sku"], "title": product["title"],
             "description": product["description"],
             "crystal_qty": product["crystals"],
             "grant_kind": product["grant_kind"],
             "grant_code": product["grant_code"],
             "grant_qty": product["grant_qty"],
             "valid_days": product["valid_days"],
             "expected_cost_usd": product["cost_budget_usd"],
             "sort": 200 + product["sort"],
             "effective_from": now, "created_at": now})
        added += cur.rowcount or 0
    return added


async def seed_defaults(db) -> dict:
    """Наполняет каталог значениями по умолчанию. Идемпотентно."""
    added = {
        "plans": await _seed_plans(db),
        "products": await _seed_products(db),
        "flags": await _seed_flags(db),
        "settings": await _seed_settings(db),
        "content": await _seed_content(db),
        "admins": await _seed_admin(db),
        "monetization_v2": await _seed_monetization_v2(db),
    }
    await db.commit()
    if any(added.values()):
        log.info("сид каталога: %s", ", ".join(f"{k}+{v}" for k, v in added.items() if v))
    return added
