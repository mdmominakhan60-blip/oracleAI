# BUS-1175: Video Overlay Design Spec — 9:16 ×4 агента

**Issue:** BUS-1175. **Parent:** BUS-1166 → BUS-1139.
**Назначение:** Pixel-perfect UI-спецификация оверлеев (субтитры, CTA, дисклеймер) + frame composition для 4 вертикальных видео.
**Владелец:** UX/UI Designer. **Реализация:** делегировать Video Production Lead.

---

## 0. Canvas — общие параметры

| Параметр | Значение |
|---|---|
| Размер | 1080×1920 (9:16) |
| Безопасная зона | Внутри 960×1740 (20px от каждого края) |
| Safe area для лица | Глаза ≥100px от верхнего края; лицо не заходит в нижние 200px |
| Цветовой прост. | sRGB |
| Базовый шрифт | Manrope (brand sans-serif) — везде, кроме явных отступлений |

---

## 1. Типографика (единая для всех 4 видео)

| Элемент | Font | Weight | Size | Color | Stroke/Shadow |
|---|---|---|---|---|---|
| Субтитры | Manrope | 700 (Bold) | 40px | #FFFFFF | stroke 3px #000000, shadow rgba(0,0,0,0.6) blur 4px offsetY 2px |
| CTA | Manrope | 700 | 46px | accent per agent | — |
| Дисклеймер | Manrope | 400 (Regular) | 20px | rgba(255,255,255,0.9) | — |
| Счётчик/индикатор | Manrope | 600 | 16px | #FFFFFF | stroke 2px #000000 |

**Контраст:** все текстовые элементы ≥4.5:1 на предполагаемом фоне.

---

## 2. Субтитры

### 2.1. Позиционирование

- **Зона:** нижние 25% кадра (y: 1440–1560px).
- **Высота блока:** 100px минимум (расчёт на 2 строки × 40px + line-height 1.2).
- **Центрирование:** по горизонтали, отступ от краёв ≥40px (x: 40–1040px).

### 2.2. Запрещённые зоны (не перекрывать)

| Агент | Запрещённая зона | Причина |
|---|---|---|
| Лилит | y < 300px (глаза) | Взгляд в верхней трети |
| Урания | y < 280px (глаза) | Прямой взгляд, высокие скулы |
| Ленорман | y: 350–600px (карты) | Колода ≥30% высоты кадра |
| Мира | y: 700–1100px (ладонь) | Ладонь — центр кадра |

### 2.3. Фоновая полоса

```
Псевдо-element: subtitle-backdrop
├── background: rgba(0,0,0,0.45)
├── border-radius: 8px
├── padding: 12px 24px
└── max-width: 960px
```

### 2.4. SRT-тайминги (единые для всех)

```
1
00:00:02,000 --> 00:00:05,500
{subtitle line 1}

2
00:00:05,500 --> 00:00:09,000
{subtitle line 2}

3
00:00:09,000 --> 00:00:11,500
{subtitle line 3}
```

---

## 3. CTA-слой (последние 3 секунды: 9–12с)

### 3.1. Позиционирование

- **Зона:** y: 1520–1640px (над дисклеймером, 60px зазор).
- **Компонент:** pill shape, width: auto по тексту, min-width: 280px, height: 64px, border-radius: 32px.

### 3.2. Визуал

```
cta-container
├── cta-bg: pill shape
│   ├── background: {accent}15 (15% opacity brand accent)
│   ├── border: 2px solid {accent}60
│   └── border-radius: 32px
├── cta-text: Manrope Bold 46px
│   ├── color: {accent}
│   └── "Расскажи, что чувствуешь →"
└── cta-arrow: → Manrope 40px, spacing: 12px от текста
```

### 3.3. Per-agent CTA

| Агент | Текст | Accent |
|---|---|---|
| Лилит (oracle) | «Расскажи, что чувствуешь →» | #e8c56b (champagne) |
| Урания (astro) | «Спроси о планете →» | #7fb4e8 (холодный голубой) |
| Ленорман (tarot) | «Задай вопрос картам →» | #c58bd8 (приглушённая роза) |
| Мира (chiromant) | «Пришли ладонь →» | #6fd6b0 (нефрит) |

---

## 4. Дисклеймер-слой

### 4.1. Позиционирование

- **Зона:** y: 1780–1840px (нижний край, 80px от низа).
- **Ширина:** 90% кадра (x: 54–1026px).
- **Высота:** 60px.

### 4.2. Визуал

```
disclaimer-container
├── background: rgba(0,0,0,0.6)
├── border-radius: 6px
├── padding: 10px 16px
└── text: Manrope Regular 20px
    ├── color: rgba(255,255,255,0.9)
    └── content: «Агент — вымышленный AI-персонаж.
                  Не является практикующим специалистом.
                  Развлекательный / иллюстрационный контент.»
```

### 4.3. Текст (общий для всех 4 видео)

> Агент — вымышленный AI-персонаж. Не является практикующим специалистом. Развлекательный / иллюстрационный контент.

---

## 5. Frame composition per agent

### 5.1. Лилит (`oracle`, profile: `lilith`)

**Canvas layers (сверху вниз):**

| # | Слой | Тип | Параметры |
|---|---|---|---|
| 1 | `face-region` | anchor | y: 150–700px; глаза ~300px от верха |
| 2 | `bokeh-candle` | atmosphere |右下角, blur 40px, opacity 30%, не перекрывает лицо |
| 3 | `subtitles` | overlay | y: 1450–1550px, не перекрывает глаза |
| 4 | `cta` | overlay | y: 1520–1640px, accent #e8c56b |
| 5 | `disclaimer` | overlay | y: 1780–1840px |

**Цветовая схема кадра:**
- Primary: #c8a97e (одежда)
- Secondary: #f5ecd7 (фон/свет)
- Accent: #e8c56b (CTA, акценты)
- Shadow: rgba(139,90,43,0.3) (тёплые тени)

**Таймлайн-сверка:**

| Сек | Доминантный слой | Движение |
|---|---|---|
| 0–2 | face-region | fade-in 0.5s |
| 3–7 | face-region + bokeh | head-turn 10° L→R |
| 8–11 | face-region | forward lean |
| 12 | face-region | freeze |

---

### 5.2. Урания (`astro`, profile: `urania`)

**Canvas layers (сверху вниз):**

| # | Слой | Тип | Параметры |
|---|---|---|---|
| 1 | `face-region` | anchor | y: 180–720px; глаза ~340px от верха |
| 2 | `zodiac-diagram` | bg-element | за спиной, blur 60px, opacity 20%, не перекрывает лицо |
| 3 | `subtitles` | overlay | y: 1420–1520px, не перекрывает глаза |
| 4 | `cta` | overlay | y: 1520–1640px, accent #7fb4e8 |
| 5 | `disclaimer` | overlay | y: 1780–1840px |

**Цветовая схема кадра:**
- Primary: #2a3a52 (одежда/фон)
- Secondary: #e8eef5 (рубашка/свет)
- Accent: #7fb4e8 (диаграмма, CTA)
- Shadow: rgba(10,15,30,0.4) (холодные тени)

**Запрещённые элементы:** золотые украшения, свечи/кристаллы (зона Лилит).

---

### 5.3. Мадам Ленорман (`tarot`, profile: `lenormand`)

**Canvas layers (сверху вниз):**

| # | Слой | Тип | Параметры |
|---|---|---|---|
| 1 | `face-region` | anchor | y: 200–720px; глаза ~360px от верха |
| 2 | `cards-deck` | prop | y: 1100–1400px, ≥30% высоты кадра (≥576px), края не обрезаны |
| 3 | `table-surface` | bg | тёмный деревянный стол, blur 20px |
| 4 | `subtitles` | overlay | y: 1400–1500px, не перекрывает карты |
| 5 | `cta` | overlay | y: 1520–1640px, accent #c58bd8 |
| 6 | `disclaimer` | overlay | y: 1780–1840px |

**Цветовая схема кадра:**
- Primary: #4a1a2e (платье/фон)
- Secondary: #8b6914 (стол/дерево)
- Accent: #c58bd8 (помада, CTA — минимально)
- Shadow: rgba(20,5,10,0.5) (тёплые глубокие тени)

**Запрещённые элементы:** шляпа с полями, чёрные перчатки, «ведьма»-эстетика.

---

### 5.4. Мира (`chiromant`, profile: `mira`)

**Canvas layers (сверху вниз):**

| # | Слой | Тип | Параметры |
|---|---|---|---|
| 1 | `face-region` | anchor | y: 180–680px; глаза ~320px от верха |
| 2 | `palm-center` | focal | y: 700–1200px, ровный свет, без теней на линиях |
| 3 | `hand-indicator` | action | y: 800–1000px, указательный палец по линии сердца |
| 4 | `subtitles` | overlay | y: 1250–1350px, под ладонью, не перекрывает линию |
| 5 | `cta` | overlay | y: 1520–1640px, accent #6fd6b0 |
| 6 | `disclaimer` | overlay | y: 1780–1840px |

**Цветовая схема кадра:**
- Primary: #c4b896 (джемпер/фон)
- Secondary: #e8dcc8 (свет/стол)
- Accent: #6fd6b0 (фон/декор, CTA)
- Shadow: rgba(60,50,30,0.2) (мягкие тени, ровный свет)

**Запрещённые элементы:** медицинский халат, маникюр/лак, агрессивный жест.

---

## 6. Figma source structure (editable layers)

```
oracleai-video-overlays/
├── 01-lilith/
│   ├── canvas-9x16.fig       — 1080×1920
│   ├── overlays/
│   │   ├── title.fig
│   │   ├── subtitles.fig
│   │   ├── cta.fig
│   │   └── disclaimer.fig
│   └── timeline/
│       ├── 00-02s.fig
│       ├── 03-07s.fig
│       ├── 08-11s.fig
│       └── 12s.fig
├── 02-urania/ (та же структура)
├── 03-lenormand/ (та же структура)
├── 04-mira/ (та же структура)
├── components/
│   ├── text/brand-heading.fig
│   ├── text/brand-subtitle.fig
│   ├── text/brand-cta.fig
│   ├── text/brand-disclaimer.fig
│   └── shape/cta-pill.fig
└── assets/
    └── palette-r04.json       — brand цвета per agent
```

**Все текстовые слои — editable, не outlines.**

---

## 7. Acceptance criteria

- [ ] 4× Figma source (per agent) с editable text layers
- [ ] Все overlay-слои соответствуют §3–4 (позиция, размер, контраст)
- [ ] Frame composition per agent соответствует §5 (зоны, запреты)
- [ ] Субтитры: SRT + визуальный слой, позиционирование соответствует запрещённым зонам
- [ ] Дисклеймер: текст и позиционирование единые для всех 4
- [ ] CTA: per-agent текст + accent цвет, позиционирование над дисклеймером
- [ ] Контраст ≥4.5:1 на всех текстовых элементах
- [ ] Safe-area чек-лист (глаза, субтитры, CTA, дисклеймер) — заполнен

---

## 8. Dependencies

| Артефакт | Владелец | Статус |
|---|---|---|
| Мастер-портреты 9:16 | Арт-директор | open (BUS-1139) |
| Видео 12с (персонаж) | Video Production Lead | open (BUS-1139) |
| Голос/TTS | board/CTO | open (отдельное решение) |
| Figma source | Video Production Lead | delegated |
| PNG-экспорт @2x | Video Production Lead | delegated |
| QA V-03 (покадрово) | Editorial QA | open |
| QA V-07 (safe-area) | Editorial QA | open |

---

*Создано: 2026-09-13. Agent: UX/UI Designer (302640d4-9556-467a-8889-d8021b1a61ff).*
*База: R04 passports, BUS-1139-video-production-spec.md, BUS-1139-editable-layers-spec.md.*
