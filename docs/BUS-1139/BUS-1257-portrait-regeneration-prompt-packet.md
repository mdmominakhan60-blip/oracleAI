# BUS-1257: Пакет промптов для перегенерации мастер-портретов ART-01…04

**Задача:** BUS-1257. **Вход:** R04 паспорта (REDESIGN_R04_AGENT_IDENTITY.md rev 2), ADR-0006 (BUS-1185), паспортный пакет BUS-1204. **Формат:** PNG ≥2048², lossless. **Назначение:** talking-head видео-пайплайн (9:16, 1080×1920).

**Отличие от BUS-1204:** BUS-1204 задавал JPEG 95% и UI-кропы. BUS-1257 перезадаёт формат на PNG (потери при ресайзе/кропе для видео недопустимы) и добавляет видео-специфичные требования (чистые зоны для оверлеев, непрерывность волос/губ при повороте головы).

---

## 1. Целевые спецификации

| Параметр | Значение |
|---|---|
| Размер | 2048×2048 минимум (один ракурс — фронтальный, остальные ≥2048 по короткой стороне) |
| Формат | PNG, lossless, 8-bit |
| DPI | 300 |
| Глубина цвета | 24-bit RGB (без альфа-канала на мастере; альфа только на matte-слое) |
| Фон | rgb(240,240,240) на портрете; отдельный matte PNG с прозрачностью (зелёный screen) |
| Текст/логотипы | Запрещены. Любые символы на изображении — дефект. |
| Стилистика | Только фотографическая. Никаких иллюстраций, 3D, аниме, рисованных лиц. |

## 2. Универсальный NEGATIVE prompt (для всех 4)

```
anime, cartoon, 3d render, illustration, painting, drawing, digital art,
CGI, plastic skin, waxy skin, airbrushed, over-retouched, airbrush,
text, watermark, logo, signature, letters, numbers, symbols, captions,
deformed, disfigured, extra limbs, extra fingers, mutated, ugly,
oversaturated, HDR, vignette, film grain, lens flare, bokeh text,
stock photo, composite face, morphing, AI artifacts,
glasses, sunglasses, hat, headwear, earrings, large jewelry,
open mouth, teeth showing, tongue, yawn, grimace,
smoke, fog, haze, blurry face, out of focus eyes
```

## 3. Промпт-карты по агентам

### 3.1. ART-01 — Лилит (oracle / lilith)

**POSITIVE:**
```
Professional studio portrait photograph of a 32-year-old woman, head and shoulders,
natural warm brown wavy hair to shoulder length, soft oval face with gentle cheekbones,
warm hazel eyes with slight downward tilt at the corners — expression of active listening,
slight relaxed smile, not posed for camera, natural skin texture visible,
wearing a soft caramel cashmere V-neck sweater, thin silver bracelet on left wrist,
no other jewelry,
lighting: soft window light from upper left 45 degrees, f/5.6 depth of field,
catchlight reflections in eyes are warm champagne-colored,
background: solid rgb(240,240,240),
shot on Canon EOS R5, 85mm lens, studio quality, photorealistic,
sharp focus on eyes, hair strands individually visible, no blur on face
```

**Специфика видео:** волосы не должны перекрывать правый глаз при повороте головы 15° вправо; карамельный свитер — единственный акцентный цвет, не должно быть других ярких объектов в кадре.

**Seed:** 118501

---

### 3.2. ART-02 — Урания (astro / urania)

**POSITIVE:**
```
Professional studio portrait photograph of a 38-year-old man, head and shoulders,
dark brown straight hair below the ear, neat layered haircut, rectangular oval face,
high cheekbones, focused analytical gaze, steel grey-blue eyes, minimal makeup,
wearing a dark navy blue crewneck sweater over a white collared shirt, no tie,
thin metal-frame glasses (clear lenses, no reflection on glass),
no other jewelry,
lighting: even cool light from front-left, no harsh shadows from eyelashes,
background: solid rgb(240,240,240),
shot on Canon EOS R5, 85mm lens, studio quality, photorealistic,
sharp focus on eyes, glasses frames clean and sharp, no reflection on lenses
```

**Специфика видео:** очки — прозрачные стёкла без бликов (при повороте головы 15° блик не должен перекрывать зрачок); тёмно-синий свитер — единственный акцентный цвет.

**Seed:** 118502

---

### 3.3. ART-03 — Мадам Ленорман (tarot / lenormand)

**POSITIVE:**
```
Professional studio portrait photograph of a 58-year-old woman, head and shoulders,
dark brown hair with natural silver streaks, pulled back in a low neat bun,
several soft strands framing the face, soft oval face with natural age lines
(not smoothed, not plastic), warm knowing gaze, grey-green eyes,
wearing a dark burgundy blouse with a dark forest green cardigan over it,
simple silver ring on left hand (visible at bottom of frame),
natural minimal makeup, muted rose lip color,
lighting: warm side light from upper right, soft shadows, not high-contrast,
background: solid rgb(240,240,240),
shot on Canon EOS R5, 85mm lens, studio quality, photorealistic,
sharp focus on eyes, texture of hair and skin natural and visible,
hands visible at bottom of frame resting on table surface (natural age, not manicured)
```

**Специфика видео:** при повороте головы пряди у лица не должны перекрывать левый глаз; руки внизу кадра — естественное положение, не жест; карты не в кадре (отдельный актив ART-08).

**Seed:** 118503

---

### 3.4. ART-04 — Мира (chiromant / mira)

**POSITIVE:**
```
Professional studio portrait photograph of a 32-year-old woman, head and shoulders,
light ash brown wavy hair below shoulders, no dye, soft round face with full cheeks,
bright green eyes, open friendly gaze, slight genuine smile,
wearing a neutral beige fine-knit jumper, sleeves pushed up to mid-forearm
(forearms and hands visible), thin silver ring on right ring finger,
no other jewelry, no nail polish,
right hand resting palm-up on table surface (palm facing camera, relaxed wrist),
lighting: even soft front light, no shadows on palm,
background: solid rgb(240,240,240),
shot on Canon EOS R5, 85mm lens, studio quality, photorealistic,
sharp focus on eyes and palm, hand anatomy correct and natural,
no bracelet, no watch, no ring on left hand
```

**Специфика видео:** ладонь — центр нижней трети кадра; линия сердца видна при лёгком повороте запястья 10°; волосы не должны падать на лицо при наклоне головы 15° вниз.

**Seed:** 118504

---

## 4. Рекомендации по генератору

- **Рекомендуемый движок:** Midjourney v6+ / FLUX.1 Pro / DALL-E 3 (фотореализм).
- **Aspect ratio:** 1:1 (2048×2048 нативно).
- **CFG scale:** 7–8 (баланс следования промту vs артефактов).
- **Steps:** 30–40.
- **Стратегия:** сгенерировать 4 варианта на агента, выбрать лучший по чеклисту §5, затем upscale до 2048² при необходимости (если генератор выдает <2048).
- **Вариантность:** запускать с фиксированным seed (см. выше). При необходимости — seed ±1..3 для вариаций, но кандидат на утверждение должен соответствовать паспорту §4 REDESIGN_R04_AGENT_IDENTITY.md.

## 5. Чеклист приёмки (QC)

Для каждого из 4 портретов:

| # | Проверка | Метод | Критерий прохождения |
|---|---|---|---|
| 1 | Размер файла | PIL/ImageMagick: `identify -format "%wx%h"` | ≥2048×2048 |
| 2 | Формат | `file` / PIL | PNG, lossless |
| 3 | Текст/логотипы | Визуальный осмотр + grep по hires-версии | Отсутствуют |
| 4 | Фотореализм | Визуальный осмотр | Никаких признаков иллюстрации/3D/аниме |
| 5 | Кожный рельеф | Визуальный осмотр при 200% | Естественная текстура, не гладкий пластик |
| 6 | Волосы | Визуальный осмотр | Индивидульные пряди, не «шлем», не размытые |
| 7 | Глаза | Визуальный осмотр | Чёткие зрачки, блики, без бликов на стёклах (Урания) |
| 8 | Цвет одежды | Визуальный осмотр + pipette | Карамельный/шампань (Лилит), тёмно-синий (Урания), вишнёво-зелёный (Ленорман), бежевый (Мира) |
| 9 | Лицо в 32px | downscale до 32×32, визуал | Лицо различимо, не размазано |
| 10 | Лицо в 128px | downscale до 128×128, визуал | Все 4 в ряд — различимы без подписей |
| 11 | Video 9:16 headroom | Визуальный осмотр | Голова — верхний третий; нижние 2/3 — чистый фон для субтитров/оверлеев |
| 12 | Паспорт-соответствие | Сверка с REDESIGN_R04_AGENT_IDENTITY.md §4 | Возраст, волосы, глаза, одежда, свет — совпадают |
| 13 | Единый стиль | Сравнение всех 4 | Одинаковая глубина резкости, цветопередача, обработка |

## 6. Именование и размещение

```
assets/video/bus-1166/portraits/
├── art-01-lilith-master-2048.png      # Лилит, фронтальный
├── art-02-urania-master-2048.png      # Урания, фронтальный
├── art-03-lenormand-master-2048.png   # Ленорман, фронтальный
├── art-04-mira-master-2048.png        # Мира, фронтальный
├── art-01-lilith-matte-2048.png       # Лилит, зелёный screen (alpha)
├── art-02-urania-matte-2048.png       # Урания, зелёный screen (alpha)
├── art-03-lenormand-matte-2048.png    # Ленорман, зелёный screen (alpha)
├── art-04-mira-matte-2048.png         # Мира, зелёный screen (alpha)
└── crop-manifest.json                 # Манифест кропов (шаблон §5 паспорта R04)
```

**Matte-слой:** отдельный PNG с прозрачностью (зелёный screen #00FF00 → alpha). Лицо и одежда — непрозрачные; фон — полностью прозрачный. Нужен для наложения на видео-фон в talking-head пайплайне.

## 7. Crop manifest (шаблон)

```json
{
  "passportVersion": "R04-2026-09-10",
  "format": "PNG-lossless",
  "masters": {
    "art-01-lilith-master-2048.png":  {"agentId": "oracle", "profileId": "lilith"},
    "art-02-urania-master-2048.png":  {"agentId": "astro",  "profileId": "urania"},
    "art-03-lenormand-master-2048.png":{"agentId": "tarot",  "profileId": "lenormand"},
    "art-04-mira-master-2048.png":    {"agentId": "chiromant","profileId": "mira"}
  },
  "crops": {
    "32":  {"recognizable": true, "fallback": "emoji-🔮"},
    "56":  {"recognizable": true},
    "128": {"recognizable": true},
    "256": {"recognizable": true},
    "512": {"recognizable": true}
  },
  "video": {
    "portrait_9x16_1080p": "tbd-by-video-team",
    "portrait_9x16_4k":    "tbd-by-video-team",
    "duration_s": 12,
    "content": "лёгкий поворот головы 10-15°, естественная мимика, синхронизация губ при речи",
    "lips_verified": false,
    "hair_verified": false,
    "eyes_verified": false,
    "hands_verified": false,
    "face_continuity_frames": 360
  },
  "palette": {
    "lilith":   {"clothing_primary": "#c8a97e", "accent": "#e8c56b"},
    "urania":   {"clothing_primary": "#2c3e6b", "accent": "#7fb4e8"},
    "lenormand":{"clothing_primary": "#6b1d3a", "accent": "#c58bd8"},
    "mira":     {"clothing_primary": "#b5a58d", "accent": "#6fd6b0"}
  }
}
```

## 8. Допустимые отступления от паспорта

Никаких. Текущие 640×640 webp в `miniapp/img/agents/*-photo.webp` не соответствуют R04 паспортам (другая одежда, волосы, возраст) — они **не** являются reference для генерации. Паспорт = канон. Если генератор выдаёт сильный bias к stock-фото-эстетике — усилить `photorealistic, shot on Canon EOS R5, 85mm lens` в промте.

## 9. Зависимости

| Зависимость | Владелец | Статус |
|---|---|---|
| Генерация/рендер 4 мастеров | Оператор (арт-директор) | Ожидает исполнения |
| QC §5 (визуальная верификация) | UX/UI Designer + Video Production Lead | После поставки |
| Замена аватарок мини-аппа | Frontend Engineer (BUS-1209) | После accept мастеров |
| Видео-тесты 10-15с | Video Production Lead (BUS-1178) | После мастеров |

---

**Этот документ — рабочий пакет для оператора.** Генерация живёт за пределами возможностей агента: решается арт-директором + внешним инструментом (Midjourney / FLUX / фотостудия). Задача агента — исчерпывающая спецификация, по которой можно воспроизвести результат.
