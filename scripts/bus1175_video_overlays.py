#!/usr/bin/env python3
"""BUS-1210: ffmpeg-оверлеи для 4 видео 9:16 по спеке BUS-1175.

Спека: docs/BUS-1139/BUS-1175-video-overlay-design-spec.md
  - Canvas 1080x1920, safe-zone 20px, шрифт Manrope.
  - Субтитры: Manrope 700 40px, stroke 3px #000, backdrop rgba(0,0,0,0.45)
    radius 8 padding 12/24, max-width 960; SRT-тайминги 2.0–5.5 / 5.5–9.0 / 9.0–11.5.
    Позиция блока — per-agent (§5), нижняя граница не заходит в 200px от низа.
  - CTA: последние 3с (9–12), pill height 64 radius 32 min-width 280,
    bg accent 15%, border 2px accent 60%, текст Manrope 700 46px accent, y 1520–1640.
  - Дисклеймер: y 1780–1840, bg rgba(0,0,0,0.6) radius 6 padding 10/16,
    Manrope 400 20px rgba(255,255,255,0.9), x 54–1026.

Реализация: PNG-оверлеи рендерятся PIL (поверхности с прозрачностью, точная
геометрия спеки), композит — ffmpeg overlay с enable-выражениями по таймингам.

Использование:
  python scripts/bus1175_video_overlays.py apply --agent oracle \
      --in assets/video/bus-1166/raw/oracle.mp4 \
      --out assets/video/bus-1166/final/oracle.mp4 \
      --subtitles "строка 1" "строка 2" "строка 3"
  python scripts/bus1175_video_overlays.py verify <final.mp4>
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CANVAS = (1080, 1920)
FONT_DIR = Path(__file__).resolve().parent.parent / "miniapp" / "fonts"
# Web-копии Manrope в miniapp — subset (cyrillic/latin): без em-dash и стрелки.
# Для видео нужна полная копия — кладётся рядом как manrope-full.ttf,
# либо передаётся через --font / BUS1175_FONT.
FONT_SOURCE = FONT_DIR / "manrope-cyrillic.woff2"
FULL_FONT_CANDIDATES = [
    FONT_DIR / "manrope-full.ttf",
    FONT_DIR / "Manrope%5Bwght%5D.ttf",  # переменный релиз Google Fonts
]

# Per-agent параметры из спеки §2.2 / §3.3 / §5.
AGENTS = {
    "oracle": {
        "profile": "lilith",
        # §5.1: subtitles y 1450–1550
        "subtitle_top": 1450,
        "cta_text": "Расскажи, что чувствуешь →",
        "accent": "#e8c56b",
    },
    "astro": {
        "profile": "urania",
        # §5.2: subtitles y 1420–1520
        "subtitle_top": 1420,
        "cta_text": "Спроси о планете →",
        "accent": "#7fb4e8",
    },
    "tarot": {
        "profile": "lenormand",
        # §5.3: subtitles y 1400–1500
        "subtitle_top": 1400,
        "cta_text": "Задай вопрос картам →",
        "accent": "#c58bd8",
    },
    "chiromant": {
        "profile": "mira",
        # §5.4: subtitles y 1250–1350
        "subtitle_top": 1250,
        "cta_text": "Пришли ладонь →",
        "accent": "#6fd6b0",
    },
}

# §2.4 SRT-тайминги
SUBTITLE_CUES = [(2.0, 5.5), (5.5, 9.0), (9.0, 11.5)]
# §3 CTA: последние 3 секунды (9–12с)
CTA_WINDOW = (9.0, 12.0)
# §4.1 дисклеймер
DISCLAIMER_TEXT = (
    "Агент — вымышленный AI-персонаж.\n"
    "Не является практикующим специалистом.\n"
    "Развлекательный / иллюстрационный контент."
)


def resolve_font_source(cli_font: Path | None) -> Path:
    if cli_font:
        return cli_font
    env = os.environ.get("BUS1175_FONT")
    if env:
        return Path(env)
    for cand in FULL_FONT_CANDIDATES:
        if cand.exists():
            return cand
    print("WARNING: полная Manrope не найдена — используется subset-woff2 "
          "(спецсимволы вроде — и → дадут ошибку покрытия)", file=sys.stderr)
    return FONT_SOURCE


def _instantiate_font(weight: int, cache: dict, source: Path) -> Path:
    """Variable woff2 -> статический ttf нужного веса (кэш на процесс).
    Статический ttf возвращается как есть."""
    if weight in cache:
        return cache[weight]
    from fontTools import ttLib
    font = ttLib.TTFont(str(source))
    if "fvar" not in font:
        cache[weight] = source
        return source
    from fontTools.varLib.instancer import instantiateVariableFont

    instantiateVariableFont(font, {"wght": weight}, inplace=True)
    out = Path(tempfile.mkdtemp(prefix=f"manrope-{weight}-")
               ) / f"Manrope-{weight}.ttf"
    font.save(out)
    cache[weight] = out
    return out


_FONTS: dict = {}
_FONT_SOURCE: Path = FONT_SOURCE  # переопределяется в main через --font/BUS1175_FONT


def get_font(weight: int, size_px: int) -> ImageFont.FreeTypeFont:
    path = _instantiate_font(weight, _FONTS, _FONT_SOURCE)
    # size в спеке задан в CSS-пикселях кадра 1:1
    return ImageFont.truetype(str(path), size_px)


def check_font_coverage(texts: list[str]):
    """Web-font'ы miniapp — subset-копии (cyrillic/latin); спецсимволы (—, →, ·)
    могут отсутствовать -> PIL молча рисует tofu. Проверяем cmap и падаем явно."""
    from fontTools.ttLib import TTFont
    cmap: set = set()
    for tb in TTFont(str(_FONT_SOURCE))["cmap"].tables:
        cmap |= set(tb.cmap.keys())
    needed = {ch for t in texts for ch in t if ord(ch) > 0x7F}
    missing = sorted(ch for ch in needed if ord(ch) not in cmap)
    if missing:
        raise SystemExit(
            "Шрифт " + _FONT_SOURCE.name + " не покрывает символы: "
            + " ".join(missing)
            + " — подставьте полную копию Manrope (--font или BUS1175_FONT)."
        )


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int, fill=None,
                  outline=None, width: int = 1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline,
                           width=width)


def hex_to_rgba(hex_color: str, alpha_pct: int) -> tuple:
    """#e8c56b + 15 -> (232,197,107, 255*0.15)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, int(255 * alpha_pct / 100))


def render_subtitle_png(text: str, subtitle_top: int, path: Path):
    """Слой субтитров: backdrop rgba(0,0,0,0.45) + белый текст 40px со stroke 3px."""
    w, h = CANVAS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_font(700, 40)

    # Перенос по словам в пределах max-width 960 минус padding 2*24
    max_text_w = 960 - 48
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_text_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    line_h = int(40 * 1.2)  # §2.1 line-height 1.2
    block_h = line_h * len(lines)
    pad_x, pad_y = 24, 12  # §2.3 padding 12px 24px
    text_w_max = max((draw.textlength(ln, font=font) for ln in lines), default=0)
    box_w = int(text_w_max) + 2 * pad_x
    box_h = block_h + 2 * pad_y

    # Блок вертикально в зоне subtitle_top..subtitle_top+100 (минимум 100px)
    zone_top = subtitle_top
    zone_h = max(100, box_h)
    top = zone_top + (zone_h - box_h) // 2
    x0 = (w - box_w) // 2
    y0 = top
    x1, y1 = x0 + box_w, top + box_h

    _rounded_rect(draw, (x0, y0, x1, y1), radius=8, fill=(0, 0, 0, int(255 * 0.45)))

    # Текст с stroke 3px #000 и мягкой тенью (shadow blur 4 offsetY 2, §1)
    ty = y0 + pad_y
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        tx = x0 + (box_w - lw) / 2
        draw.text((tx + 1, ty + 3), ln, font=font, fill=(0, 0, 0, 153),
                  stroke_width=0)
        draw.text((tx, ty), ln, font=font, fill=(255, 255, 255, 255),
                  stroke_width=3, stroke_fill=(0, 0, 0, 255))
        ty += line_h

    img.save(path)


def render_cta_png(accent: str, text: str, path: Path):
    """CTA-pill: height 64, radius 32, min-width 280, bg accent15 border accent60 2px,
    текст Manrope 700 46px accent, y 1520–1640 (§3)."""
    w, h = CANVAS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_font(700, 46)

    text_w = draw.textlength(text, font=font)
    pad_x = 32
    pill_w = int(max(280, text_w + 2 * pad_x))
    pill_h = 64
    y0 = 1520 + (120 - pill_h) // 2  # зона 1520–1640, центровать 64px
    x0 = (w - pill_w) // 2
    x1, y1 = x0 + pill_w, y0 + pill_h

    _rounded_rect(draw, (x0, y0, x1, y1), radius=32,
                  fill=hex_to_rgba(accent, 15),
                  outline=hex_to_rgba(accent, 60), width=2)

    tx = x0 + (pill_w - text_w) / 2
    # высота строки 46px — центрируем по метрике шрифта
    ascent, descent = font.getmetrics()
    ty = y0 + (pill_h - (ascent + descent)) / 2
    r, g, b, _ = hex_to_rgba(accent, 100)
    draw.text((tx, ty), text, font=font, fill=(r, g, b, 255))

    img.save(path)


def render_disclaimer_png(path: Path):
    """Дисклеймер: y 1780–1840, x 54–1026, bg rgba(0,0,0,0.6) radius 6 padding 10/16,
    Manrope 400 20px rgba(255,255,255,0.9) (§4)."""
    w, h = CANVAS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = get_font(400, 20)

    lines = DISCLAIMER_TEXT.split("\n")
    line_h = int(20 * 1.25)
    text_w = max(draw.textlength(ln, font=font) for ln in lines)
    pad_x, pad_y = 16, 10
    box_w = int(min(text_w + 2 * pad_x, 1026 - 54))  # §4.1 ширина 90% кадра
    box_h = line_h * len(lines) + 2 * pad_y
    x0 = (w - box_w) // 2
    y0 = 1780 + (60 - box_h) // 2 if box_h <= 60 else 1780
    x1, y1 = x0 + box_w, y0 + box_h

    _rounded_rect(draw, (x0, y0, x1, y1), radius=6, fill=(0, 0, 0, int(255 * 0.6)))
    ty = y0 + pad_y
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        tx = x0 + (box_w - lw) / 2
        draw.text((tx, ty), ln, font=font, fill=(255, 255, 255, int(255 * 0.9)))
        ty += line_h

    img.save(path)


def apply_overlays(agent: str, in_path: Path, out_path: Path, subtitles: list,
                   overwrite: bool) -> int:
    if agent not in AGENTS:
        print(f"неизвестный агент: {agent} (ожидается {', '.join(AGENTS)})",
              file=sys.stderr)
        return 2
    if len(subtitles) != 3:
        print("субтитры: ровно 3 строки по SRT-таймингам §2.4", file=sys.stderr)
        return 2
    cfg = AGENTS[agent]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bus1175-") as td:
        tdp = Path(td)
        sub_paths = []
        for i, line in enumerate(subtitles):
            p = tdp / f"sub{i}.png"
            render_subtitle_png(line, cfg["subtitle_top"], p)
            sub_paths.append(p)
        cta_p = tdp / "cta.png"
        render_cta_png(cfg["accent"], cfg["cta_text"], cta_p)
        disc_p = tdp / "disclaimer.png"
        render_disclaimer_png(disc_p)

        # ffmpeg: дисклеймер — всё время; CTA — 9–12с; субтитры — по окнам §2.4
        inputs = ["-i", str(in_path)]
        for p in sub_paths:
            inputs += ["-i", str(p)]
        inputs += ["-i", str(cta_p), "-i", str(disc_p)]

        fc = []
        prev = "[0:v]"
        # 1..3 — субтитровые PNG (enable по окнам)
        for idx, (t0, t1) in enumerate(SUBTITLE_CUES):
            out = f"[s{idx}]"
            fc.append(f"{prev}[{idx + 1}:v]overlay=0:0:enable='between(t,{t0},{t1})'{out}")
            prev = out
        # 4 — CTA
        fc.append(f"{prev}[4:v]overlay=0:0:enable='between(t,{CTA_WINDOW[0]},{CTA_WINDOW[1]})'[cta]")
        prev = "[cta]"
        # 5 — дисклеймер (весь кадр)
        fc.append(f"{prev}[5:v]overlay=0:0[vout]")

        cmd = ["ffmpeg", "-y" if overwrite else "-n", "-hide_banner", "-loglevel", "error"]
        cmd += inputs
        cmd += ["-filter_complex", ";".join(fc),
                "-map", "[vout]", "-map", "0:a?",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-preset", "medium", "-c:a", "copy", str(out_path)]
        print("+", " ".join(cmd), file=sys.stderr)
        return subprocess.call(cmd)


def verify_video(path: Path, raw_path: Path, accent: str, subtitle_top: int) -> int:
    """Проверка финального MP4: разрешение, длительность, наличие слоёв.
    Слой сверяется относительно raw-кадра той же позиции: backdrop/дисклеймер
    затемняют полосу, CTA добавляет accent-пиксели."""
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", str(path)]))
    v = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        print("нет видеопотока", file=sys.stderr)
        return 1
    w, h = int(v["width"]), int(v["height"])
    dur = float(probe["format"].get("duration", 0))
    fps = v.get("avg_frame_rate", "25/1")
    problems = []
    if (w, h) != CANVAS:
        problems.append(f"canvas {w}x{h} != 1080x1920")
    if dur < 11.5:
        problems.append(f"длительность {dur}s < 11.5s (SRT-окно §2.4)")

    def sample(video: Path, t: float, tag: str):
        img_p = Path(td) / f"{tag}-{t}.png"
        subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                               "-ss", str(t), "-i", str(video), "-frames:v", "1", str(img_p)])
        return Image.open(img_p).convert("RGB")

    def darkened_frac(fin: Image.Image, raw: Image.Image, box) -> float:
        """Доля пикселей бокса, ставших заметно темнее после оверлея.
        Метрика не зависит от яркости фона: среднее lum падает в провал, когда
        белые глифы на тёмном raw-кадре перекрывают затемнение backdrop'а."""
        fc = fin.crop(box).convert("L"); rc = raw.crop(box).convert("L")
        fp, rp = fc.load(), rc.load()
        hits = sum(1 for y in range(fc.height) for x in range(fc.width)
                   if fp[x, y] < rp[x, y] * 0.85 - 2)
        return hits / (fc.width * fc.height)

    with tempfile.TemporaryDirectory(prefix="bus1175-verify-") as td:
        # Пороги = доля площади backdrop-полосы (не средняя яркость, см. выше):
        # backdrop субтитров покрывает окно с запасом → ≥0.5; дисклеймер-полоса
        # почти целиком в disc_box → ≥0.8 (округлые углы/поля дают запас).
        sub_box = (340, subtitle_top - 10, 740, subtitle_top + 110)
        disc_box = (340, 1780, 740, 1840)  # §4.1 (центрированная часть полосы)
        cta_box = (100, 1520, 980, 1640)   # §3.1
        fin6, raw6 = sample(path, 6.0, "fin"), sample(raw_path, 6.0, "raw")
        if darkened_frac(fin6, raw6, sub_box) < 0.5:
            problems.append("t=6s: backdrop субтитров не затемняет зону §2.1")
        fin10, raw10 = sample(path, 10.0, "fin"), sample(raw_path, 10.0, "raw")
        if darkened_frac(fin10, raw10, disc_box) < 0.8:
            problems.append("t=10s: дисклеймер-полоса (§4) не найдена")
        # CTA: пиксели в пределах ±30/40 от accent-цвета текста агента
        ar, ag, ab, _ = hex_to_rgba(accent, 100)
        def accent_frac(im: Image.Image) -> float:
            crop = im.crop(cta_box)
            px = crop.load()
            hits = sum(1 for y in range(crop.height) for x in range(crop.width)
                       if abs(px[x, y][0] - ar) < 30 and abs(px[x, y][1] - ag) < 30
                       and abs(px[x, y][2] - ab) < 40)
            return hits / (crop.width * crop.height)
        if accent_frac(fin10) - accent_frac(raw10) < 0.02:
            problems.append(f"t=10s: CTA-акцент {accent} (§3) не найден в y 1520–1640")
    for p in problems:
        print("FAIL:", p, file=sys.stderr)
    if not problems:
        print(f"OK: {path.name} {w}x{h} {fps} {dur:.1f}s — слои на месте")
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("apply", help="наложить оверлеи на raw-MP4")
    a.add_argument("--agent", required=True, choices=list(AGENTS))
    a.add_argument("--in", dest="inp", required=True, type=Path)
    a.add_argument("--out", dest="out", required=True, type=Path)
    a.add_argument("--subtitles", nargs=3, metavar=("L1", "L2", "L3"),
                   required=True, help="три строки SRT §2.4")
    a.add_argument("--font", type=Path, default=None,
                   help="полный Manrope ttf/otf (иначе BUS1175_FONT / miniapp/fonts/manrope-full.ttf)")
    a.add_argument("--overwrite", action="store_true")

    v = sub.add_parser("verify", help="проверить финальный MP4 по спеке")
    v.add_argument("path", type=Path, help="final MP4")
    v.add_argument("--raw", required=True, type=Path,
                   help="исходный raw MP4 (для сверки слоёв по разнице кадров)")
    v.add_argument("--agent", required=True, choices=list(AGENTS),
                   help="accent CTA берётся из конфига агента (§3.3)")

    args = ap.parse_args(argv)
    if args.cmd == "apply":
        global _FONT_SOURCE
        _FONT_SOURCE = resolve_font_source(args.font)
        check_font_coverage(list(args.subtitles)
                            + [AGENTS[args.agent]["cta_text"], DISCLAIMER_TEXT])
        return apply_overlays(args.agent, args.inp, args.out, args.subtitles,
                              args.overwrite)
    cfg = AGENTS[args.agent]
    return verify_video(args.path, args.raw, cfg["accent"], cfg["subtitle_top"])


if __name__ == "__main__":
    raise SystemExit(main())
