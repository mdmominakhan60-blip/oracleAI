"""Клавиатуры бота.

Правило раскладки: главное действие — всегда первой строкой и во всю ширину,
остальное — парами. Кнопки, ведущие к оплате, отделены от бесплатных, чтобы не
нажимались случайно.
"""
from __future__ import annotations

from urllib.parse import quote

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           WebAppInfo)

from ..config import settings

CB_MENU = "menu"

# Онбординг: кнопочный выбор даты рождения. Год — с 1955 (аудитория 20–50),
# города — крупные из встроенного словаря geo.FALLBACK, остальное — текстом.
DATE_PICK_MIN_YEAR = 1955
CITY_PICKS = ["москва", "санкт-петербург", "казань", "новосибирск", "екатеринбург",
              "киев", "минск", "алматы", "лондон", "нью-йорк"]


def date_decades_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    en = lang == "en"
    decades = list(range(2005, DATE_PICK_MIN_YEAR - 1, -10))
    rows = [[InlineKeyboardButton(text=f"{d}–{d + 9}", callback_data=f"bd:yg:{d}")]
            for d in decades]
    rows.append([InlineKeyboardButton(text="✍ Ввести текстом" if not en else "✍ Type it",
                                      callback_data="bd:text")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def date_years_kb(decade: int, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=str(y), callback_data=f"bd:y:{y}")
             for y in range(decade, decade + 5)],
            [InlineKeyboardButton(text=str(y), callback_data=f"bd:y:{y}")
             for y in range(decade + 5, decade + 10)]]
    rows.append([InlineKeyboardButton(text="←", callback_data="bd:decades")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн",
              "июл", "авг", "сен", "окт", "ноя", "дек"]
_MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def date_months_kb(year: int, lang: str = "ru") -> InlineKeyboardMarkup:
    months = _MONTHS_EN if lang == "en" else _MONTHS_RU
    rows = [[InlineKeyboardButton(text=months[m - 1], callback_data=f"bd:m:{year}:{m}")
             for m in range(start, start + 3)]
            for start in range(1, 13, 3)]
    rows.append([InlineKeyboardButton(text="←", callback_data=f"bd:yg:{year - year % 10}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def date_days_kb(year: int, month: int, lang: str = "ru") -> InlineKeyboardMarkup:
    import calendar
    days = calendar.monthrange(year, month)[1]
    rows = [[InlineKeyboardButton(text=str(d), callback_data=f"bd:day:{year}:{month}:{d}")
             for d in range(start, min(start + 7, days + 1))]
            for start in range(1, days + 1, 7)]
    rows.append([InlineKeyboardButton(text="←", callback_data=f"bd:m:{year}:{month}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def city_pick_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    en = lang == "en"
    titles = {"москва": "Москва", "санкт-петербург": "Санкт-Петербург", "казань": "Казань",
              "новосибирск": "Новосибирск", "екатеринбург": "Екатеринбург", "киев": "Київ",
              "минск": "Минск", "алматы": "Алматы", "лондон": "London", "нью-йорк": "New York"}
    rows = [[InlineKeyboardButton(text=titles.get(c, c.title()), callback_data=f"city:{i}")]
            for i, c in enumerate(CITY_PICKS)]
    rows.append([InlineKeyboardButton(text="✍ Другой город" if not en else "✍ Other city",
                                      callback_data="city:other")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _webapp_button(text: str, path: str = "") -> InlineKeyboardButton | None:
    """Кнопка Mini App. Без https-адреса Telegram её просто не примет."""
    if not settings.webapp_url:
        return None
    url = settings.webapp_url + path
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


def main_menu(*, is_admin: bool = False, lang: str = "ru") -> InlineKeyboardMarkup:
    """Telegram-native home grammar: one primary action, then exploration and hub rows."""
    en = lang == "en"
    rows: list[list[InlineKeyboardButton]] = []
    app_btn = _webapp_button("✨ Open full Oracle" if en else "✨ Открыть полного Оракула", "/")
    if app_btn:
        rows.append([app_btn])
    rows += [
        [InlineKeyboardButton(text="✨ Ask Oracle" if en else "✨ Спросить Оракула", callback_data="ask")],
        [InlineKeyboardButton(text="🌌 My chart" if en else "🌌 Моя карта", callback_data="chart"),
         InlineKeyboardButton(text="🎴 Tarot" if en else "🎴 Таро", callback_data="tarot")],
        [InlineKeyboardButton(text="✋ Mira" if en else "✋ Мира", callback_data="palm"),
         InlineKeyboardButton(text="📖 My research" if en else "📖 Мои исследования", callback_data="history")],
        [InlineKeyboardButton(text="🌙 Today" if en else "🌙 Сегодня", callback_data="today"),
         InlineKeyboardButton(text="? Help" if en else "? Помощь", callback_data="help")],
        [InlineKeyboardButton(text="💎 Premium" if en else "💎 Premium", callback_data="shop")],
        [InlineKeyboardButton(text="👤 Profile" if en else "👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="⚙️ Settings" if en else "⚙️ Настройки", callback_data="settings")],
    ]
    if is_admin:
        admin_btn = _webapp_button("📊 Admin panel" if en else "📊 Панель управления", "/admin")
        rows.append([admin_btn] if admin_btn
                    else [InlineKeyboardButton(text="📊 Statistics" if en else "📊 Статистика",
                                               callback_data="admin_stats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="language:ru"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="language:en")],
    ])


def welcome_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Первый экран нового пользователя: начать знакомство или посмотреть меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Начать" if lang != "en" else "✨ Begin",
                              callback_data="onb:begin")],
        [InlineKeyboardButton(text="Возможности" if lang != "en" else "Features",
                              callback_data="onb:features")],
    ])


def time_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Знаю точно" if lang != "en" else "I know it exactly", callback_data="time:exact")],
        [InlineKeyboardButton(text="Знаю примерно" if lang != "en" else "I know roughly", callback_data="time:approximate")],
        [InlineKeyboardButton(text="Не знаю" if lang != "en" else "I don’t know", callback_data="time:unknown")],
        [InlineKeyboardButton(text="← Назад" if lang != "en" else "← Back", callback_data="onb:back")],
    ])


def confirmation_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✓ Всё верно" if lang != "en" else "✓ Looks right", callback_data="onb:confirm")],
        [InlineKeyboardButton(text="✎ Изменить" if lang != "en" else "✎ Edit", callback_data="onb:edit")],
    ])


def technique_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Астрологический разбор" if lang != "en" else "✨ Astrology reading", callback_data="technique:astrology")],
        [InlineKeyboardButton(text="🎴 Натальная история Ленорман" if lang != "en" else "🎴 Lenormand natal story", callback_data="technique:lenormand")],
        [InlineKeyboardButton(text="← Назад" if lang != "en" else "← Back", callback_data="onb:back")],
    ])


def onboarding_edit_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    labels = [("name", "Имя" if lang != "en" else "Name"), ("date", "Дата" if lang != "en" else "Date"),
              ("time", "Время" if lang != "en" else "Time"), ("city", "Город" if lang != "en" else "City")]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✎ {label}", callback_data=f"onb:edit:{key}") for key, label in labels[:2]],
        [InlineKeyboardButton(text=f"✎ {label}", callback_data=f"onb:edit:{key}") for key, label in labels[2:]],
        [InlineKeyboardButton(text="← К данным" if lang != "en" else "← Back to details", callback_data="onb:confirm")],
    ])


def history_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎴 Tarot" if lang == "en" else "🎴 Таро", callback_data="history:tarot")],
        [InlineKeyboardButton(text="📜 Reports" if lang == "en" else "📜 Разборы", callback_data="my_reports")],
        [InlineKeyboardButton(text="💬 Conversations" if lang == "en" else "💬 Разговоры", callback_data="history:chat")],
        [InlineKeyboardButton(text="← Menu" if lang == "en" else "← Меню", callback_data=CB_MENU)],
    ])


def gender_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Выбор формы обращения в онбординге; пропуск сохраняет нейтральный язык."""
    labels = (
        ("Female ♀", "Male ♂", "Skip")
        if lang == "en" else ("Женский ♀", "Мужской ♂", "Пропустить")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=labels[0], callback_data="gender:f"),
         InlineKeyboardButton(text=labels[1], callback_data="gender:m")],
        [InlineKeyboardButton(text=labels[2], callback_data="gender:skip")],
    ])


def personas_kb(personas: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p['emoji']} {p['title']}",
                              callback_data=f"persona:{p['code']}")]
        for p in personas
    ])


def ask_starters_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        labels = [("What should I focus on today?", "starter:today"),
                  ("What is happening in my relationship?", "starter:love"),
                  ("Help me make a decision", "starter:decision")]
    else:
        labels = [("На чём мне сфокусироваться сегодня?", "starter:today"),
                  ("Что происходит в моих отношениях?", "starter:love"),
                  ("Помоги принять решение", "starter:decision")]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in labels
    ] + [[InlineKeyboardButton(text="Change guide" if lang == "en" else "Выбрать проводника", callback_data="agents")],
         [InlineKeyboardButton(text="Menu" if lang == "en" else "Меню", callback_data=CB_MENU)]])


def agents_kb(agents: list[dict]) -> InlineKeyboardMarkup:
    """Выбор собеседника: у каждого агента своя специализация."""
    rows = [[InlineKeyboardButton(text=f"{a['emoji']} {a['title']}",
                                  callback_data=f"agent:{a['code']}")]
            for a in agents]
    rows.append([InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def spreads_kb(spreads: list[dict]) -> InlineKeyboardMarkup:
    """Расклады: входящие в тариф сверху, платные — с ценой на кнопке."""
    rows = []
    for item in spreads:
        if item["tier"] == "included":
            label = f"{item['emoji']} {item['title']}"
        elif item["owned"]:
            label = f"{item['emoji']} {item['title']} · открыт ✓"
        else:
            price = (f"⭐{item['price_stars']}" if item["price_stars"]
                     else f"✦{item['price_crystals']}")
            label = f"{item['emoji']} {item['title']} · {price}"
        rows.append([InlineKeyboardButton(text=label[:60],
                                          callback_data=f"spread:{item['code']}")])
    rows.append([InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def spread_offer_kb(item: dict) -> InlineKeyboardMarkup:
    """Расклад не входит в тариф — предлагаем купить его или подписку."""
    rows = []
    if item.get("sku") and item.get("price_stars"):
        rows.append([InlineKeyboardButton(
            text=f"⭐ Купить за {item['price_stars']} Stars",
            callback_data=f"buy_sku:{item['sku']}")])
    if item.get("sku") and item.get("price_crystals"):
        rows.append([InlineKeyboardButton(
            text=f"✦ Открыть за {item['price_crystals']} Кристаллов",
            callback_data=f"buy_crystals:{item['sku']}")])
    # Подписка на витринах скрыта (этап «только Кристаллы»); хендлер `plans`
    # оставлен — вернём кнопкой, когда решим снова продавать.
    rows.append([InlineKeyboardButton(text="← К раскладам", callback_data="tarot")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def limit_kb(cost: int, *, has_crystals: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    """Лимит исчерпан. Порядок кнопок = порядок выгоды для пользователя."""
    en = lang == "en"
    rows = []
    if has_crystals:
        rows.append([InlineKeyboardButton(
            text=(f"🔮 Emergency question · ✦{cost}" if en
                  else f"🔮 Экстренный вопрос · ✦{cost}"), callback_data="emergency")])
    rows += [
        [InlineKeyboardButton(text=("💎 Buy Crystals" if en else "💎 Купить Кристаллы"),
                              callback_data="shop_crystals")],
        [InlineKeyboardButton(text=("← Menu" if en else "← Меню"), callback_data=CB_MENU)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    en = lang == "en"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Plans" if en else "👑 Тарифы", callback_data="plans")],
        [InlineKeyboardButton(text="🎴 Single readings" if en else "🎴 Одиночные расклады", callback_data="shop_spreads")],
        [InlineKeyboardButton(text="📜 Deep readings" if en else "📜 Большие разборы", callback_data="shop_reports")],
        [InlineKeyboardButton(text="💬 Extra questions" if en else "💬 Дополнительные вопросы", callback_data="shop_questions")],
        [InlineKeyboardButton(text="✦ Crystals" if en else "✦ Кристаллы", callback_data="shop_crystals")],
        [InlineKeyboardButton(text="🎁 My purchases" if en else "🎁 Мои покупки", callback_data="my_entitlements")],
        [InlineKeyboardButton(text="🎟 Promo code" if en else "🎟 Ввести промокод", callback_data="promo")],
        [InlineKeyboardButton(text="← Menu" if en else "← Меню", callback_data=CB_MENU)],
    ])


def plans_kb(plans: list[dict], current: str, *, period: str = "monthly", lang: str = "ru") -> InlineKeyboardMarkup:
    en = lang == "en"
    rows = [[InlineKeyboardButton(text=("✓ Monthly" if period == "monthly" and en else "Monthly" if en else "✓ Месяц" if period == "monthly" else "Месяц"), callback_data="plans:monthly"),
             InlineKeyboardButton(text=("✓ Annual" if period == "annual" and en else "Annual" if en else "✓ Год" if period == "annual" else "Год"), callback_data="plans:annual")]]
    for plan in plans:
        price = plan.get("annual_price_stars") if period == "annual" else plan.get("price_stars")
        if not price:
            continue
        mark = " ✓" if plan["code"] == current else ""
        badge = f" · {plan['badge']}" if plan.get("badge") else ""
        rows.append([InlineKeyboardButton(
            text=f"{plan['title']} — ⭐{price}{badge}{mark}"[:60],
            callback_data=f"buy_plan:{plan['code']}:{period}")])
    rows.append([InlineKeyboardButton(text="← Shop" if en else "← Лавка", callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_kb(products: list[dict], *, back: str = "shop",
                crypto_skus: tuple = ()) -> InlineKeyboardMarkup:
    """Витрина товаров: Stars и Кристаллы — двумя кнопками, чтобы не путать.

    Для пакетов Кристаллов добавляется третья кнопка — крипта (Crypto Pay):
    без юрлица это единственный канал с картой/USDT и низкой комиссией.
    """
    rows = []
    for product in products:
        line = []
        if product["price_stars"]:
            line.append(InlineKeyboardButton(
                text=f"⭐{product['price_stars']}",
                callback_data=f"buy_sku:{product['sku']}"))
        if product["price_crystals"]:
            line.append(InlineKeyboardButton(
                text=f"✦{product['price_crystals']}",
                callback_data=f"buy_crystals:{product['sku']}"))
        if product["kind"] == "crystals" and product["sku"] in crypto_skus:
            line.append(InlineKeyboardButton(
                text="₿ Криптой", callback_data=f"buy_crypto:{product['sku']}"))
        rows.append([InlineKeyboardButton(text=product["title"][:60],
                                          callback_data=f"product:{product['sku']}")])
        if line:
            rows.append(line)
    rows.append([InlineKeyboardButton(text="← Лавка", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    en = lang == "en"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Language" if en else "🌐 Язык", callback_data="settings:language")],
        [InlineKeyboardButton(text="🧠 Memory" if en else "🧠 Память", callback_data="settings:memory")],
        [InlineKeyboardButton(text="🌅 Notifications" if en else "🌅 Уведомления", callback_data="profile")],
        [InlineKeyboardButton(text="🔐 Privacy & data" if en else "🔐 Приватность и данные", callback_data="privacy")],
        [InlineKeyboardButton(text="← Menu" if en else "← Меню", callback_data=CB_MENU)],
    ])


def profile_kb(*, push_on: bool, sub_active: bool, lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    # «Продлить доступ» скрыт вместе с подписками (этап «только Кристаллы»).
    en = lang == "en"
    rows += [
        [InlineKeyboardButton(text="💎 Premium" if en else "💎 Лавка", callback_data="shop"),
        InlineKeyboardButton(text="🌟 Invite someone" if en else "🌟 Пригласить близкого", callback_data="invite")],
        [InlineKeyboardButton(
            text=f"🌅 Утренний прогноз: {'вкл ✅' if push_on else 'выкл ☑️'}",
            callback_data="toggle_push")],
        [InlineKeyboardButton(text="🔮 Сменить образ Оракула",
                              callback_data="change_persona")],
        [InlineKeyboardButton(text="📜 Мои разборы", callback_data="my_reports")],
        [InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def share_kb(link: str, text: str, *, label: str = "💌 Поделиться") -> InlineKeyboardMarkup:
    share_url = "https://t.me/share/url?url=" + quote(link) + "&text=" + quote(text)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, url=share_url)],
        [InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)],
    ])


def reading_kb(reading_id: int, share_url: str, *,
               with_card: bool = True) -> InlineKeyboardMarkup:
    """Под раскладом: отметка «сбылось» (обратная связь) и шеринг (виральность).

    Картинка для сторис — отдельной кнопкой: в этой нише делятся скриншотом
    расклада, а не ссылкой, и красивая карточка работает как реклама сама.
    """
    rows = [[
        InlineKeyboardButton(text="✅ Сбылось",
                             callback_data=f"outcome:{reading_id}:came_true"),
        InlineKeyboardButton(text="🤔 Частично",
                             callback_data=f"outcome:{reading_id}:partly"),
    ]]
    if with_card:
        rows.append([InlineKeyboardButton(text="🖼 Картинка для сторис",
                                          callback_data=f"card:{reading_id}")])
    rows += [
        [InlineKeyboardButton(text="💌 Поделиться", url=share_url)],
        [InlineKeyboardButton(text="🎴 Ещё расклад", callback_data="tarot")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def practices_kb(items: list[dict], categories: list[dict],
                 *, active: str | None = None) -> InlineKeyboardMarkup:
    """Практики: сначала идущие (к ним возвращаются), потом каталог по разделам."""
    rows = []
    running = [p for p in items if p["started"] and not p["finished"]]
    for item in running[:4]:
        rows.append([InlineKeyboardButton(
            text=f"{item['emoji']} {item['title']} · день "
                 f"{item['day_index']}/{item['days']}"[:60],
            callback_data=f"practice:{item['code']}")])
    if running:
        rows.append([InlineKeyboardButton(text="— каталог —",
                                          callback_data="practices")])
    line = []
    for cat in categories:
        mark = " ✓" if cat["code"] == active else ""
        line.append(InlineKeyboardButton(
            text=f"{cat['emoji']} {cat['title']}{mark}"[:30],
            callback_data=f"practice_cat:{cat['code']}"))
        if len(line) == 2:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    for item in items:
        if item["started"] and not item["finished"]:
            continue
        mark = " ✓" if item["finished"] else ""
        rows.append([InlineKeyboardButton(
            text=f"{item['emoji']} {item['title']} · {item['days']} дн.{mark}"[:60],
            callback_data=f"practice:{item['code']}")])
    rows.append([InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def practice_kb(item: dict) -> InlineKeyboardMarkup:
    """Карточка практики: главное действие зависит от того, идёт ли она."""
    rows = []
    if item["finished"]:
        rows.append([InlineKeyboardButton(text="🔁 Пройти заново",
                                          callback_data=f"practice_start:{item['code']}")])
    elif item["started"]:
        rows.append([InlineKeyboardButton(
            text=f"✅ Отметить день {item['day_index'] + 1}",
            callback_data=f"practice_done:{item['code']}")])
        rows.append([InlineKeyboardButton(text="⏹ Остановить",
                                          callback_data=f"practice_stop:{item['code']}")])
    else:
        rows.append([InlineKeyboardButton(
            text=f"▶️ Начать · {item['days']} дней",
            callback_data=f"practice_start:{item['code']}")])
    rows.append([InlineKeyboardButton(text="← К практикам",
                                      callback_data="practices")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def career_kb() -> InlineKeyboardMarkup:
    """Карьерный раздел: расклады, деловые окна и большой разбор."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧭 Расклад «Карьера и путь»",
                              callback_data="spread:career")],
        [InlineKeyboardButton(text="⚖️ Расклад «Проблемы на работе»",
                              callback_data="spread:work")],
        [InlineKeyboardButton(text="📅 Деловые окна на 2 недели",
                              callback_data="career_windows")],
        [InlineKeyboardButton(text="📜 Полный разбор карьеры",
                              callback_data="shop_reports")],
        [InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)],
    ])


def back_menu(*, ask: bool = False) -> InlineKeyboardMarkup:
    """«← Меню», при ask — ещё и переход к вопросу Оракулу.

    Контекстный next-action: после разбора карты/матрицы естественно
    продолжить разговором, а не выходить в меню.
    """
    rows = [[InlineKeyboardButton(text="← Меню", callback_data=CB_MENU)]]
    if ask:
        rows.insert(0, [InlineKeyboardButton(
            text="✨ Спросить Оракула", callback_data="ask")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_kb(reports: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📜 {r['title']}"[:60],
                                  callback_data=f"report:{r['kind']}:{r['period'] or ''}")]
            for r in reports]
    rows.append([InlineKeyboardButton(text="← Профиль", callback_data="profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
