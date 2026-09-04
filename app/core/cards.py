"""Картинки-карточки: расклад и прогноз дня для сторис.

Виральность в этой нише работает через скриншот: клиентка показывает подругам
не ссылку, а красивый расклад. Ссылку в подписи почти никто не открывает,
поэтому имя бота нанесено прямо на картинку — она сама себе реклама.

Формат 1080×1920 — вертикаль сторис. Рисуем через Pillow: SVG Telegram не
принимает как фото, а тянуть браузерный рендер ради одной картинки — дорого.
Если Pillow не установлен, функции возвращают None, и продукт спокойно
откатывается к текстовому шерингу ссылкой.
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date

log = logging.getLogger("oracle.cards")

W, H = 1080, 1920

BG_TOP = (26, 15, 61)
BG_BOTTOM = (11, 7, 34)
GOLD = (232, 197, 107)
GOLD_SOFT = (232, 197, 107, 90)
INK = (244, 239, 255)
MUTED = (169, 159, 201)

#: Шрифты ищем среди системных: Pillow своих не поставляет, а встроенный
#: растровый не умеет кириллицу нужного размера.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/TTF/DejaVuSerif.ttf",
    "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/noto/NotoSerif-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
]
FONT_SANS_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def available() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _font(size: int, serif: bool = True):
    """Шрифт нужного кегля. На системе без TTF откатываемся к встроенному.

    Встроенный шрифт Pillow растровый и не знает атрибута `size`, поэтому
    высоту строки везде берём через `_line_height`, а не через `font.size`.
    """
    import os

    from PIL import ImageFont
    for path in (FONT_CANDIDATES if serif else FONT_SANS_CANDIDATES):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _line_height(font, fallback: int = 16) -> int:
    return int(getattr(font, "size", fallback) * 1.35)


def _gradient(draw, width: int, height: int) -> None:
    """Вертикальный градиент неба. Рисуем полосами: Pillow не умеет градиенты."""
    for y in range(height):
        t = y / max(height - 1, 1)
        # мягче к низу: середина экрана должна быть светлее краёв
        ease = t ** 0.85
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * ease)
                      for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)


def _stars(draw, seed: int, count: int = 160) -> None:
    """Звёзды детерминированы сидом: одна и та же карточка выглядит одинаково."""
    import random
    rnd = random.Random(seed)
    for _ in range(count):
        x = rnd.randrange(W)
        y = rnd.randrange(H)
        r = rnd.choice([1, 1, 2, 2, 3])
        alpha = rnd.randint(60, 220)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(232, 215, 255, alpha))


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    """Перенос по словам. Длинное слово рвём — иначе оно уедет за край."""
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            probe = f"{current} {word}".strip()
            if draw.textlength(probe, font=font) <= max_width or not current:
                current = probe
                continue
            lines.append(current)
            current = word
        if current:
            lines.append(current)
    return lines


def _centered(draw, y: int, text: str, font, fill) -> int:
    width = draw.textlength(text, font=font)
    draw.text(((W - width) / 2, y), text, font=font, fill=fill)
    return y + _line_height(font)


def _card_slot(draw, x: int, y: int, w: int, h: int) -> None:
    """Рамка карты: тёмная подложка + золотой контур + внутренняя линия."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=18,
                           fill=(36, 22, 80), outline=GOLD, width=3)
    draw.rounded_rectangle([x + 8, y + 8, x + w - 8, y + h - 8], radius=12,
                           outline=(232, 197, 107, 110), width=1)


def _moon(draw, cx: int, cy: int, r: int) -> None:
    """Полумесяц: круг минус смещённый круг цвета фона."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(232, 197, 107, 40))
    draw.ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2],
                 outline=GOLD, width=3)
    for i in range(3):
        a = math.radians(120 * i - 30)
        sx, sy = cx + int((r + 26) * math.cos(a)), cy + int((r + 26) * math.sin(a))
        draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=GOLD)


def _footer(draw, bot_username: str) -> None:
    """Подпись-реклама. Только символы из системных шрифтов: цветных эмодзи
    в DejaVu нет, и «🔮» превратилось бы в пустой квадрат."""
    font = _font(38, serif=False)
    label = f"@{bot_username}" if bot_username else "Оракул"
    text = f"✦ {label} — личный AI-астролог"
    width = draw.textlength(text, font=font)
    draw.text(((W - width) / 2, H - 130), text, font=font, fill=MUTED)


def _render(paint) -> bytes | None:
    """Общий каркас: фон, звёзды, содержимое, PNG на выходе."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        log.info("Pillow не установлен — карточки отключены")
        return None
    try:
        image = Image.new("RGB", (W, H), BG_BOTTOM)
        draw = ImageDraw.Draw(image, "RGBA")
        paint(image, draw)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    except Exception as e:  # noqa: BLE001
        log.warning("карточка не отрисовалась: %s", e)
        return None


# ─────────────────────────── карточка расклада ────────────────────────────────

def reading_card(title: str, cards: list[dict], positions: list[str], *,
                 name: str = "", bot_username: str = "",
                 seed: int = 0) -> bytes | None:
    """Карточка расклада: до пяти карт с позициями. PNG или None."""
    shown = (cards or [])[:5]
    if not shown:
        return None

    def paint(image, draw):
        _gradient(draw, W, H)
        _stars(draw, seed or len(shown))
        y = 150
        _moon(draw, W // 2, y + 60, 62)
        y += 190
        y = _centered(draw, y, title[:40], _font(64), GOLD)
        if name:
            y = _centered(draw, y + 6, f"для {name}", _font(38, serif=False), MUTED)
        y += 40

        # Карты в ряд; при пяти картах ужимаем, чтобы поместились с полями
        count = len(shown)
        gap = 26
        card_w = min(280, (W - 120 - gap * (count - 1)) // count)
        card_h = int(card_w * 1.55)
        total = card_w * count + gap * (count - 1)
        x0 = (W - total) // 2
        for i, card in enumerate(shown):
            x = x0 + i * (card_w + gap)
            _card_slot(draw, x, y, card_w, card_h)
            # Крупно — номер аркана, а не эмодзи: цветных эмодзи в системных
            # шрифтах нет, и вместо картинки получался бы пустой квадрат
            num_font = _font(int(card_w * 0.34), serif=True)
            num = str(card.get("num") or "✦")
            nw = draw.textlength(num, font=num_font)
            draw.text((x + (card_w - nw) / 2, y + card_h * 0.16), num,
                      font=num_font, fill=GOLD)
            name_font = _font(max(20, int(card_w * 0.11)), serif=True)
            step = _line_height(name_font, 24)
            for j, line in enumerate(_wrap(draw, card.get("name", ""), name_font,
                                           card_w - 24)[:2]):
                lw = draw.textlength(line, font=name_font)
                draw.text((x + (card_w - lw) / 2, y + card_h * 0.60 + j * step),
                          line, font=name_font, fill=INK)
            if card.get("reversed"):
                rev_font = _font(19, serif=False)
                rw = draw.textlength("перевёрнутая", font=rev_font)
                draw.text((x + (card_w - rw) / 2, y + card_h - 38),
                          "перевёрнутая", font=rev_font, fill=MUTED)

        y += card_h + 30
        pos_font = _font(24, serif=False)
        for i, pos in enumerate((positions or [])[:count]):
            x = x0 + i * (card_w + gap)
            for j, line in enumerate(_wrap(draw, pos, pos_font, card_w)[:2]):
                lw = draw.textlength(line, font=pos_font)
                draw.text((x + (card_w - lw) / 2, y + j * 30), line,
                          font=pos_font, fill=GOLD)

        _footer(draw, bot_username)

    return _render(paint)


# ────────────────────────── карточка прогноза дня ─────────────────────────────

def forecast_card(text: str, *, sign: str = "", symbol: str = "",
                  card_name: str = "", name: str = "", bot_username: str = "",
                  day: str | None = None) -> bytes | None:
    """Карточка утреннего прогноза — то, что чаще всего уходит в сторис."""
    body = (text or "").strip()
    if not body:
        return None

    def paint(image, draw):
        _gradient(draw, W, H)
        _stars(draw, len(body))
        y = 140
        # Символ знака (♌) есть в DejaVu, эмодзи — нет, поэтому знак рисуем
        # символом, а там, где его нет, — нарисованным полумесяцем
        if symbol:
            y = _centered(draw, y, symbol, _font(140), GOLD)
        else:
            _moon(draw, W // 2, y + 60, 62)
            y += 190
        if sign:
            y = _centered(draw, y, sign, _font(58), INK)
        header = day or date.today().strftime("%d.%m.%Y")
        y = _centered(draw, y + 4, header, _font(34, serif=False), MUTED)
        y += 50

        text_font = _font(42, serif=False)
        clean = body.replace("<b>", "").replace("</b>", "") \
                    .replace("<i>", "").replace("</i>", "")
        step = _line_height(text_font, 46)
        lines = _wrap(draw, clean, text_font, W - 180)[:16]
        for line in lines:
            lw = draw.textlength(line, font=text_font)
            draw.text(((W - lw) / 2, y), line, font=text_font, fill=INK)
            y += step

        if card_name:
            y += 40
            draw.line([(W // 2 - 160, y), (W // 2 + 160, y)], fill=GOLD, width=2)
            y += 40
            _centered(draw, y, f"Карта дня: {card_name}", _font(40), GOLD)

        _footer(draw, bot_username)

    return _render(paint)


# ──────────────────────── открытка совместимости пары ─────────────────────────

def compat_card(*, you: dict, partner: dict, total: int, verdict: str,
                spheres: list[dict] | None = None, relation: str = "",
                bot_username: str = "") -> bytes | None:
    """Вертикальная открытка пары: два знака, кольцо-шкала %, вердикт, сферы.

    Самый виральный продукт должен уходить в сторис так же легко, как расклад:
    имя бота нанесено прямо на картинку — она сама себе реклама. Знаки передаём
    символами (♈ есть в DejaVu), цветных эмодзи в системных шрифтах нет.
    """
    you = you or {}
    partner = partner or {}
    total = max(0, min(100, int(total or 0)))
    spheres = (spheres or [])[:5]

    def paint(image, draw):
        _gradient(draw, W, H)
        _stars(draw, total or 42)
        # золотая рамка открытки: внешний контур + тонкая внутренняя линия
        draw.rectangle([36, 36, W - 36, H - 36], outline=GOLD, width=3)
        draw.rectangle([50, 50, W - 50, H - 50], outline=GOLD_SOFT, width=1)

        y = 170
        y = _centered(draw, y, "Совместимость", _font(64), GOLD)
        if relation:
            y = _centered(draw, y + 6, relation, _font(36, serif=False), MUTED)
        block_y = y + 70

        # два знака по краям, сердце между ними
        for cx, who in ((W // 4, you), (3 * W // 4, partner)):
            sym = _font(128)
            sw = draw.textlength(who.get("symbol", ""), font=sym)
            draw.text((cx - sw / 2, block_y), who.get("symbol", "✦"), font=sym,
                      fill=GOLD)
            sign = who.get("sign", "")
            sf = _font(46)
            tw = draw.textlength(sign, font=sf)
            draw.text((cx - tw / 2, block_y + 190), sign, font=sf, fill=INK)
            nm = who.get("name", "")
            if nm:
                nf = _font(30, serif=False)
                for j, line in enumerate(_wrap(draw, nm, nf, 320)[:1]):
                    lw = draw.textlength(line, font=nf)
                    draw.text((cx - lw / 2, block_y + 262 + j * 40), line,
                              font=nf, fill=MUTED)
        heart = _font(96)
        hw = draw.textlength("♡", font=heart)
        draw.text((W / 2 - hw / 2, block_y + 70), "♡", font=heart, fill=GOLD)

        # кольцо-шкала 0–100 с заполнением по баллу
        cy_ring, r, ring_w = 1080, 250, 22
        draw.arc([W // 2 - r, cy_ring - r, W // 2 + r, cy_ring + r], 0, 360,
                 fill=(232, 197, 107, 70), width=ring_w)
        draw.arc([W // 2 - r, cy_ring - r, W // 2 + r, cy_ring + r], -90,
                 -90 + 3.6 * total, fill=GOLD, width=ring_w)
        tf = _font(150)
        ts = str(total)
        tw = draw.textlength(ts, font=tf)
        draw.text((W / 2 - tw / 2, cy_ring - 92), ts, font=tf, fill=GOLD)
        lab = _font(32, serif=False)
        lw = draw.textlength("из 100", font=lab)
        draw.text((W / 2 - lw / 2, cy_ring + 78), "из 100", font=lab, fill=MUTED)

        # вердикт
        vf = _font(42)
        yv = cy_ring + 180
        for line in _wrap(draw, verdict or "", vf, W - 220)[:3]:
            lw = draw.textlength(line, font=vf)
            draw.text(((W - lw) / 2, yv), line, font=vf, fill=INK)
            yv += _line_height(vf, 46)

        # сферы: название слева, балл справа, разделительная нить
        yv += 46
        sf = _font(32, serif=False)
        for s in spheres:
            title = s.get("title", "")
            val = f"{int(s.get('value') or 0)}%"
            draw.text((240, yv), title, font=sf, fill=INK)
            vw = draw.textlength(val, font=sf)
            draw.text((W - 240 - vw, yv), val, font=sf, fill=GOLD)
            draw.line([(240, yv + 42), (W - 240, yv + 42)],
                      fill=(232, 197, 107, 60), width=1)
            yv += 66

        _footer(draw, bot_username)

    return _render(paint)
