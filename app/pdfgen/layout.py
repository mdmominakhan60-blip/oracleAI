"""Вёрстка PDF: страница, типографика, колесо карты, октаграмма Матрицы.

Один визуальный язык с Mini App — те же цвета и тот же «дорогой мистический»
тон. Покупательница, пришедшая с маркетплейса, должна узнать продукт, когда
откроет бота.

CSS ориентирован на печать: A4, поля, разрывы страниц по разделам. Всё внутри
одного файла без внешних ресурсов — PDF обязан собираться на машине без сети.
"""
from __future__ import annotations

import html
import math

PAGE_CSS = """
@page {
  size: A4;
  margin: 11mm 13mm 13mm 13mm;
  background: #0b0722;
  @bottom-left {
    content: "OracleAI";
    color: #6f6494;
    font-size: 8pt;
    font-family: Georgia, serif;
  }
  @bottom-center {
    content: "✦  " counter(page) "  ✦";
    color: #e8c56b;
    font-size: 8.5pt;
    font-family: Georgia, serif;
  }
  @bottom-right {
    content: "Personal natal report";
    color: #6f6494;
    font-size: 8pt;
    font-family: Georgia, serif;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #0b0722;
  color: #f4efff;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 12.4pt;
  line-height: 1.56;
  overflow-wrap: anywhere;
}
h1, h2, h3 { font-weight: normal; color: #e8c56b; }
h1 { font-size: 30pt; line-height: 1.08; margin: 0 0 7mm; }
h2 {
  font-size: 24pt;
  line-height: 1.12;
  margin: 0 0 4mm;
  padding-bottom: 2mm;
  border-bottom: 1px solid rgba(232, 197, 107, .35);
}
h3 { font-size: 17pt; line-height: 1.2; margin: 4mm 0 1.8mm; color: #f3dc9a; }
p { margin: 0 0 3.2mm; }
.muted { color: #a99fc9; }
.small { font-size: 10.5pt; line-height: 1.4; }
.pull-quote { margin: 5mm 0; padding: 4mm 5mm; border-left: 1.5mm solid #e8c56b; color: #f3dc9a; font-size: 16pt; line-height: 1.3; font-style: italic; }
.compact-columns { columns: 2; column-gap: 8mm; column-fill: balance; }
.compact-columns > * { break-inside: avoid; }
.chapter-pair { margin-bottom: 8mm; }
.chapter-pair h2 { break-after: avoid; }
.reference-columns { font-size: 9.2pt; line-height: 1.22; column-gap: 5mm; }
.reference-columns .card { padding: 2.5mm 3mm; margin-bottom: 2.5mm; break-inside: auto; }
.reference-columns h3 { font-size: 12pt; margin: 2mm 0 1mm; }
.reference-columns table { font-size: 8.3pt; line-height: 1.08; break-inside: auto; }
.reference-columns td, .reference-columns th { padding: .55mm .65mm; }
.reference-columns .small { font-size: 8.2pt; }
@media screen { .compact-columns, .reference-columns { columns: 1; } }

.center { text-align: center; }

/* Разделы текут непрерывно; отдельный page break используется только для cover. */
.section { margin: 0 0 8mm; break-inside: auto; }
.section h2 { break-after: avoid; }
.cover {
  min-height: 245mm;
  text-align: center;
  padding: 20mm 10mm 12mm;
  page-break-after: always;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.cover .brand { color: #e8c56b; font-size: 12pt; letter-spacing: 2px; text-transform: uppercase; }
.cover .eyebrow { color: #a99fc9; font-size: 9pt; letter-spacing: 1.5px; text-transform: uppercase; margin: 6mm 0; }
.cover .sub { color: #a99fc9; font-size: 12pt; margin-top: 3mm; max-width: 125mm; }
.cover .who { margin-top: 13mm; font-size: 17pt; color: #f4efff; }
.cover .born { color: #a99fc9; font-size: 10.5pt; margin-top: 2mm; }
.cover .project-link { color: #e8c56b; font-size: 9.5pt; margin-top: 12mm; overflow-wrap: anywhere; }
.brand-mark { margin: 0 auto 6mm; }
.brand-mark svg { width: 43mm; height: 43mm; }

.overview-grid { display: grid; grid-template-columns: 1.12fr .88fr; gap: 6mm; align-items: stretch; }
.overview-visuals { display: grid; gap: 3mm; align-content: start; justify-items: center; }
.overview-visuals .wheel { margin: 0; width: 100%; }
.overview-visuals svg { max-width: 100%; height: auto; }
.matrix-visual { width: 100%; min-height: 92mm; padding: 5mm 4mm 3mm; border: 1px solid rgba(232, 197, 107, .28); border-radius: 5mm; background: radial-gradient(circle at 50% 38%, rgba(185,166,255,.12), transparent 44%), linear-gradient(160deg, rgba(255,255,255,.055), rgba(16,12,38,.72)); box-sizing: border-box; }
.matrix-visual__label { color: #e8c56b; font-size: 10pt; letter-spacing: 1.2px; text-transform: uppercase; text-align: center; margin-bottom: 2mm; }
.matrix-visual svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }
.facts-constellation { min-height: 92mm; padding: 5mm; border: 1px solid rgba(232, 197, 107, .28); border-radius: 5mm; background: radial-gradient(circle at 50% 34%, rgba(232,197,107,.13), transparent 34%), linear-gradient(145deg, rgba(255,255,255,.07), rgba(20,15,43,.78)); box-sizing: border-box; }
.facts-constellation__header { display: flex; align-items: baseline; justify-content: space-between; gap: 4mm; color: #e8c56b; font-size: 10pt; letter-spacing: 1px; text-transform: uppercase; }
.facts-constellation__header small { color: #a99fc9; font-size: 7.5pt; letter-spacing: 0; text-transform: none; text-align: right; }
.facts-core { display: grid; justify-items: center; gap: 1mm; padding: 4mm 0 3mm; text-align: center; }
.facts-core__halo { display: grid; align-items: center; justify-items: center; width: 23mm; height: 23mm; border: 1px solid rgba(232,197,107,.75); border-radius: 50%; background: radial-gradient(circle, rgba(232,197,107,.23), rgba(185,166,255,.08) 58%, transparent 60%); }
.facts-core__halo strong { color: #f4d88b; font-size: 24pt; font-weight: normal; }
.facts-core > span { color: #a99fc9; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 1px; }
.facts-core > b { color: #f4efff; font-size: 13pt; font-weight: normal; }
.facts-profile { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2mm; padding: 3mm 0; border-top: 1px solid rgba(232,197,107,.22); border-bottom: 1px solid rgba(232,197,107,.22); }
.facts-profile-cell { min-width: 0; text-align: center; }
.facts-profile-cell span, .facts-placement span { display: block; color: #a99fc9; font-size: 7.5pt; line-height: 1.2; }
.facts-profile-cell b, .facts-placement b { display: block; margin-top: 1mm; color: #f4efff; font-size: 9.5pt; font-weight: normal; overflow-wrap: anywhere; }
.facts-placements { display: grid; grid-template-columns: repeat(2, 1fr); gap: 2mm 4mm; padding-top: 3mm; }
.facts-placement { min-width: 0; padding: 1.5mm 0; border-bottom: 1px dotted rgba(255,255,255,.13); }
.element-balance { margin-top: 4mm; padding-top: 3mm; border-top: 1px solid rgba(232,197,107,.22); }
.element-balance__header { display: flex; justify-content: space-between; align-items: baseline; gap: 3mm; color: #e8c56b; font-size: 8.5pt; letter-spacing: 1px; text-transform: uppercase; }
.element-balance__header small { color: #a99fc9; font-size: 7pt; letter-spacing: 0; text-transform: none; }
.element-rows { display: grid; gap: 1.5mm; margin-top: 2.5mm; }
.element-row { display: grid; grid-template-columns: 18mm 1fr 5mm; align-items: center; gap: 2mm; }
.element-row__label { color: #c8b9e8; font-size: 7.8pt; }
.element-row__track { display: block; height: 2.2mm; border-radius: 2mm; background: rgba(255,255,255,.10); overflow: hidden; }
.element-row__track i { display: block; height: 100%; border-radius: 2mm; }
.element-row b { color: #f4efff; font-size: 8pt; font-weight: normal; text-align: right; }

.natal-print-section { break-before: page; }
.natal-print-figure { margin: 0; text-align: center; break-inside: avoid; }
.natal-print-image { display: block; width: 100%; max-width: 180mm; height: auto; margin: 0 auto; background: #0c0a1d; }
.natal-print-figure figcaption { margin-top: 2mm; }
.natal-key-strip { margin: 6mm 0 0; padding: 4mm 3mm 3mm; border-top: 1px solid rgba(232,197,107,.5); border-bottom: 1px solid rgba(232,197,107,.24); background: linear-gradient(115deg, rgba(232,197,107,.08), rgba(185,166,255,.06) 52%, rgba(123,224,197,.05)); }
.natal-key-strip__title { color: #e8c56b; font-size: 8pt; letter-spacing: 1.4px; text-align: center; text-transform: uppercase; }
.natal-key-primary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin-top: 3mm; }
.natal-key-card { min-width: 0; padding: 2mm 2mm 2.5mm; border-right: 1px solid rgba(232,197,107,.22); text-align: center; }
.natal-key-card:last-child { border-right: none; }
.natal-key-card strong { display: block; color: #f4d88b; font-size: 18pt; font-weight: normal; line-height: 1; }
.natal-key-card:nth-child(2) strong { color: #b9a6ff; }
.natal-key-card:nth-child(3) strong { color: #7be0c5; font-size: 13pt; line-height: 1.4; }
.natal-key-card span { display: block; margin-top: 1mm; color: #c8b9e8; font-size: 8pt; line-height: 1.2; text-transform: uppercase; }
.natal-key-card b { display: block; margin-top: 1.2mm; color: #f4efff; font-size: 11pt; font-weight: normal; overflow-wrap: anywhere; }
.natal-key-secondary { display: grid; grid-template-columns: 1fr 1.6fr; gap: 3mm; margin-top: 2mm; padding-top: 2mm; border-top: 1px dotted rgba(255,255,255,.16); color: #a99fc9; font-size: 7.8pt; text-align: center; }
.natal-key-secondary > div + div { border-left: 1px solid rgba(232,197,107,.16); }
.natal-key-secondary span { display: block; }
.natal-key-secondary b { display: block; margin-top: .8mm; color: #e8c56b; font-weight: normal; overflow-wrap: anywhere; }
.natal-print-state { border: 1px solid rgba(232, 197, 107, .35); padding: 6mm; color: #c8b9e8; }
.closing-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-top: 5mm; }
.closing-grid .card { margin-bottom: 0; }
.closing-grid h3 { margin-top: 0; }

.card {
  border: 1px solid rgba(232, 197, 107, .30);
  border-radius: 4mm;
  padding: 4mm 5mm;
  margin: 0 0 4mm;
  background: rgba(255, 255, 255, .04);
}
.kv { display: flex; justify-content: space-between; gap: 6mm;
      padding: 1.6mm 0; border-bottom: 1px dotted rgba(255,255,255,.12); }
.kv:last-child { border-bottom: none; }
.kv b { color: #e8c56b; font-weight: normal; }

table { width: 100%; border-collapse: collapse; table-layout: fixed; }
td, th { padding: 1.15mm 1.1mm; vertical-align: top; overflow-wrap: anywhere; }
th { color: #e8c56b; text-align: left; font-weight: normal; border-bottom: 1px solid rgba(232,197,107,.35); }
td.label { color: #a99fc9; width: 42%; }
table.data-table { font-size: 10.2pt; line-height: 1.35; }
table.data-table td, table.data-table th { border-bottom: 1px dotted rgba(255,255,255,.12); }
.card, .ticket { break-inside: avoid; }
.reference-section { margin-top: 0; }
.reference-config { max-width: 150mm; margin: 8mm auto 0; }
.reference-lead { max-width: 145mm; color: #c8b9e8; font-size: 12pt; line-height: 1.5; }
.house-reference, .aspect-reference { break-before: page; }
.house-reference table.data-table { font-size: 13.2pt; line-height: 1.45; margin-top: 6mm; }
.house-reference table.data-table td, .house-reference table.data-table th { padding: 2.2mm 2.5mm; }
.house-angle-panel { margin-top: 7mm; padding: 3.5mm 6mm 4mm; border: 1px solid rgba(232,197,107,.3); border-radius: 5mm; background: linear-gradient(145deg, rgba(255,255,255,.055), rgba(20,15,43,.68)); }
.house-angle-panel__title { color: #e8c56b; font-size: 11pt; letter-spacing: 1px; text-transform: uppercase; text-align: center; }
.house-angle-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin-top: 3mm; }
.house-angle { min-width: 0; padding: 2mm 2mm; border-top: 1px solid rgba(232,197,107,.28); text-align: center; }
.house-angle span { display: block; color: #a99fc9; font-size: 8.5pt; }
.house-angle b { display: block; margin-top: 1mm; color: #f4efff; font-size: 12pt; font-weight: normal; }
.house-angle small { display: block; margin-top: 1mm; color: #e8c56b; font-size: 10pt; }
.house-reference table.data-table th:first-child, .house-reference table.data-table td:first-child { width: 18%; }
.house-reference table.data-table th:nth-child(2), .house-reference table.data-table td:nth-child(2) { width: 32%; }

@media screen {
  body { font-size: 13pt; line-height: 1.58; padding: 12px; }
  .section { margin: 0 auto 28px; max-width: 760px; }
  .cover { padding-top: 28px; min-height: 0; }
  h1 { font-size: 27pt; }
  h2 { font-size: 22pt; }
  .card { padding: 16px; border-radius: 14px; }
  td, th { padding: 7px 5px; }
  table.data-table { font-size: 11.5pt; line-height: 1.45; }
  .overview-grid { grid-template-columns: 1fr; }
  .facts-constellation { min-height: 0; }
  .natal-key-primary { grid-template-columns: repeat(3, 1fr); }
  .house-angle-grid { grid-template-columns: repeat(2, 1fr); }
  .facts-placements { grid-template-columns: repeat(3, 1fr); }
  .matrix-visual { min-height: 0; }
  .closing-grid { grid-template-columns: 1fr; }
  .wheel svg { max-width: 100%; height: auto; }
  .natal-print-image { max-width: 100%; }
}

@media print {
  body { overflow-wrap: normal; }
  .cover { page-break-after: always; }
  .overview-grid, .card, table, .ticket, .pull-quote { break-inside: avoid; }
  tr { break-inside: avoid; }
}

.wheel { text-align: center; margin: 4mm 0 6mm; }
.ticket {
  margin-top: 8mm;
  border: 1.4px dashed #e8c56b;
  border-radius: 4mm;
  padding: 7mm;
  text-align: center;
  background: rgba(232, 197, 107, .07);
}
.ticket .code {
  font-family: 'DejaVu Sans Mono', monospace;
  font-size: 20pt;
  letter-spacing: 3px;
  color: #e8c56b;
  margin: 4mm 0;
}
.aspect-legend { display: flex; flex-wrap: wrap; gap: 2mm 3mm; align-items: center; justify-content: center; margin-top: 2mm; }
.aspect-chip { font-size: 8.5pt; white-space: nowrap; }
.aspect-соединение { color: #e8c56b; }
.aspect-оппозиция { color: #e88f8f; }
.aspect-трин { color: #9edfc8; }
.aspect-квадрат { color: #b69cf4; }
.aspect-секстиль { color: #83c8ef; }
.closing-grid a, .project-link { color: #e8c56b; text-decoration: none; overflow-wrap: anywhere; }
  .disclaimer { color: #c8b9e8; font-size: 11pt; line-height: 1.45; margin-top: 7mm; }
"""

SIGN_GLYPHS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]
PLANET_GLYPHS = {
    "Солнце": "☉", "Луна": "☽", "Меркурий": "☿", "Венера": "♀", "Марс": "♂",
    "Юпитер": "♃", "Сатурн": "♄", "Уран": "♅", "Нептун": "♆", "Плутон": "♇",
    "Раху (Северный узел)": "☊", "Кету (Южный узел)": "☋", "Лилит (Чёрная Луна)": "⚸",
    "Хирон": "⚷", "Джуно": "⚵", "Церера": "⚳", "Веста": "⚶", "Паллада": "⚴",
}


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def paragraphs(text: str) -> str:
    """Текст модели → абзацы. Теги <b>/<i> из бота вычищаем: тут своя вёрстка."""
    clean = (text or "").replace("<b>", "").replace("</b>", "") \
                        .replace("<i>", "").replace("</i>", "")
    out = []
    for block in clean.split("\n"):
        block = block.strip()
        if not block:
            continue
        # строка-заголовок раздела от модели («1. Кто ты по карте»)
        if len(block) < 80 and block.rstrip().endswith(":"):
            out.append(f"<h3>{esc(block.rstrip(':'))}</h3>")
        else:
            out.append(f"<p>{esc(block)}</p>")
    return "\n".join(out)


def matrix_svg(matrix: dict, size: int = 300, labels: dict[str, str] | None = None) -> str:
    """Октаграмма Матрицы Судьбы: два наложенных квадрата и арканы по вершинам."""
    cx = cy = size / 2
    R = size * 0.38
    parts = []
    for rot in (0, 45):
        points = " ".join(
            f"{cx + R * math.cos(math.radians(a + rot - 90)):.1f},"
            f"{cy + R * math.sin(math.radians(a + rot - 90)):.1f}"
            for a in (0, 90, 180, 270))
        parts.append(f'<polygon points="{points}" fill="none" '
                     f'stroke="rgba(232,197,107,.45)" stroke-width="1.1"/>')

    keys = ["personal", "spirit", "family", "destiny", "love", "money"]
    items = [matrix[k] for k in keys if k in matrix]
    for i, item in enumerate(items):
        a = math.radians(i * 60 - 90)
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        label = (labels or {}).get(item.get("title"), item["title"])
        label = label.replace("Arcana ", "").replace("Line ", "")
        label = label.replace("Аркан ", "").replace("Линия ", "")
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="20" fill="#140c30" '
            f'stroke="rgba(232,197,107,.55)"/>'
            f'<text x="{x:.1f}" y="{y + 5:.1f}" fill="#e8c56b" font-size="14" '
            f'text-anchor="middle">{item["n"]}</text>'
            f'<text x="{x:.1f}" y="{y + 33:.1f}" fill="#a99fc9" font-size="8" '
            f'text-anchor="middle">{esc(label)}</text>')

    center = matrix.get("center")
    if center:
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="25" fill="#140c30" '
            f'stroke="rgba(232,197,107,.55)"/>'
            f'<text x="{cx}" y="{cy + 5}" fill="#e8c56b" font-size="16" '
            f'text-anchor="middle">{center["n"]}</text>')

    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')


def brand_mark_svg(size: int = 180) -> str:
    """Минималистичный векторный знак OracleAI для cover без внешних assets."""
    center = size / 2
    return (f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="OracleAI">'
            f'<circle cx="{center}" cy="{center}" r="65" fill="none" stroke="#e8c56b" stroke-width="2"/>'
            f'<circle cx="{center}" cy="{center}" r="48" fill="#140c30" stroke="#a99fc9" stroke-width="1"/>'
            f'<path d="M{center-18} {center+30} A38 38 0 1 1 {center+18} {center-30} A28 28 0 1 0 {center-18} {center+30}" fill="#e8c56b"/>'
            f'<circle cx="{center+55}" cy="{center-47}" r="4" fill="#e8c56b"/>'
            f'<circle cx="{center-63}" cy="{center+18}" r="2.5" fill="#a99fc9"/>'
            f'</svg>')


def document(title: str, blocks: list[str], *, lang: str = "ru") -> str:
    """Собирает готовую responsive HTML-страницу разбора."""
    body = "\n".join(blocks)
    html_lang = "en" if (lang or "").lower().startswith("en") else "ru"
    return (f'<!DOCTYPE html><html lang="{html_lang}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<meta name="theme-color" content="#0b0722">'
            f'<title>{esc(title)}</title><style>{PAGE_CSS}</style></head>'
            f'<body>{body}</body></html>')
