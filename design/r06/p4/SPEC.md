# R06 · Пакет 4: S14 натальная карта (G-кадр)

Задача: BUS-1067 (OracleAI R06). Вход: R01 `8fbb477`, R02 IA `7f7cd3b`, R03 дизайн-система `7f7c79a`, R05 sky `c14b5ffc`. Пакеты 1–3 — `../p1/`, `../p2/`, `../p3/`. План BUS-721: §11.3 (таблица сцен, S14 = натальная карта). Explain-chart паттерн — legacy BUS-650 (`12-misc.js` openBuildChart/explainChart, `chart_interpretation.py`).

Файлы: `index.html` (прототип, 7 видов), `styles.css` (R03 токены + компоненты S14), `probe-http.html` (инструмент верификации — НЕ прод).

CEO-директива (борд BUS-963) соблюдена: колесо — inline SVG (14 glyphs с hit-area), фоны/портреты — существующие ассеты `img/`, ничего не сгенерировано.

## 1. Как смотреть прототип

Открыть `index.html`. Плавающая панель переключает виды; прямые ссылки:

| Вид | Ссылка | Сцена R02 |
| --- | --- | --- |
| Карточка в чате | `index.html#view-chat-card` | превью карты в ленте |
| Загрузка расчёта | `index.html#view-chart-loading` | 3-шаг прогресс |
| Нет данных о рождении | `index.html#view-chart-empty` | честный путь к форме |
| Карта (основная) | `index.html#view-chart-main` | колесо + детали + интерпретация |
| Zoom планеты | `index.html#view-chart-zoom` | крупный план тела |
| Интерпретация | `index.html#view-chart-interpret` | 11 секций explain-chart |
| Ошибка расчёта | `index.html#view-chart-error` | `?fail=1` QA-хук |

Интерактив: back → «К разговору» во всех видах; колесо — hover/focus-visible на планетах; «Простая интерпретация» → POST /api/chart/interpret → 11 секций; `<details>` для списка планет/аспектов/домов.

## 2. Что покрыто и по какому требованию

### 2.1 Карточка в чате `view-chart-card`
- Мини-колесо inline SVG (72×72), заголовок, 1 строка, «Открыть карту» → fullscreen на мобильных / extended ≥1280 на десктопе (§3.3 R02).
- Действия: «Открыть карту» + «Поделиться»; кнопки ≥44px (WCAG 2.5.5).

### 2.2 Загрузка `view-chart-loading`
- 3-шаговый прогресс с aria-current; сноска «расчёт живёт в разговоре» (Back-matrix H2, §5.3).
- Не блокирует back — операция привязана к конверсации.

### 2.3 Нет данных `view-chart-empty`
- Честный путь к форме: «Добавить данные рождения» → форма S04 (паттерн p1).
- Второй путь: «Построить без домов» — работает при неизвестном времени рождения (не блокирует сцену).

### 2.4 Карта `view-chart-main`
- Inline SVG колесо: 12 планет + Lilith + 12 домов + узлы; hover/focus-visible подсветка.
- Desktop ≥1280: колесо слева (sticky) + детали справа; планеты в `<details>` (§11.3: подписи не над диаграммой).
- Аспекты и дома — списки в `<details>`; бейдж «точное время» у provenance.
- «Простая интерпретация» → открывает `view-chart-interpret`.
- Back → draft-form по tool_id (H2).

### 2.5 Zoom планеты `view-chart-zoom`
- Glyph-badge 56px, название, тип, описание; «Спросить Уранию об этой планете».
- Возврат без потери состояния карты.

### 2.6 Интерпретация `view-chart-interpret` (BUS-650 explain-chart)
- 11 секций structured-contract v1 (`chart_interpretation.py`): luminaries → personality_portrait → rahu_ketu → strengths → weaknesses → purpose → relationships → career_money → aspect_synthesis → peak_periods → synthesis + disclaimer.
- Валидация payload: REQUIRED_KEYS (luminaries, personality_portrait, rahu_ketu.growth_step, strengths 2–5, weaknesses 2–4, purpose, relationships, career_money, aspect_synthesis, peak_periods, synthesis, disclaimer).
- Действия: «Спросить Уранию» + «Назад к карте» + «К разговору».

### 2.7 Ошибка `view-chart-error`
- `?fail=1` QA-хук; role=alert; «Проверить статус» (повтор) + «Начать заново».
- Network error / session expired / no access — стойкие баннеры, не тосты.

## 3. Фон

R03 токены (SSOT) без изменений: border-control `#717B96` (3:1), Manrope 400–700, midnight-палитра, motion 140/220/480ms. Sky-фон единый с p1–p3 (`data-bg="chat"`).

## 4. Доступность (R03 §8.2, WCAG 2.1 AA)

- Inline SVG: роль `img` + `aria-label`; hit-areas — `<button>` с `aria-label` («Солнце, 15° Овна. Нажато/не нажато»).
- `view-chart-interpret`: 11 секций — heading hierarchy h2→h3; disclaimer — italic, не скрыт.
- `[hidden]{display:none!important}` глобально.
- Focus-visible ring на всех интерактивных элементах колеса.
- Toast — только краткие подтверждения; ошибки полей — у поля (aria-describedby).
- reduced-motion: spin/transition отключены.

## 5. Верификация (выполнено)

- CSS: баланс скобок 200/200.
- DOM-проба: 7 видов, 27 ссылок `data-goto-view`, 13 role=, 36 aria-label, 0 внешних URL, 72 focusable элемента.
- HTTP-сервер: все ресурсы p4 возвращают 200.
- 320px probe (`probe-http.html`, same-origin iframe): инструмент готов, верификация — FE/QA (headless Chrome <500px игнорирует `--window-size`, p1–p3 lesson).
- Визуальная приёмка — FE/QA (vision-провайдер в ране недоступен).

## 6. Найти и фиксы (важно для Frontend)

1. **`.chart-card__actions .btn` min-height 44px** (было 40px) — WCAG 2.5.5 touch target ≥44×44 CSS.
2. **Inline SVG колесо без `<title>` в `<defs>`** — aria-label на родителе `role=img` достаточен; при добавлении `<title>` убрать дубль aria-label.
3. **`view-chart-zoom` — упрощение прототипа**: в проде zoom = overlay/modal с сохранением wheel-state в URL hash или form state.
4. **Explain-chart payload** — в прототипе мок; FE должны интегрировать с POST /api/chart/interpret backend BUS-650.

## 7. Чего здесь нет (осознанно)

- Расчёт натальной карты (логика — backend BUS-650, не меняется).
- R03 токены — без изменений (SSOT).
- Детальные формы ввода данных рождения (паттерн S04 p1, не дублируется).
- S13 Таро большой расклад — p3.
- Motion-хореография — после финального R05.
- Новые изображения — только inline SVG + существующие ассеты `img/` (BUS-963).

## 8. Тексты (источник — R04 + BUS-650)

- «Простая интерпретация», «Спросить Уранию об этой планете» — интерфейсный копирайт по паттерну BUS-650.
- «К разговору» — Back-matrix H2 единый для всех сцен инструментов.
- «Построить без домов» — честный путь при неизвестном времени рождения (§11.2 empty).
- Disclaimer: «Интерпретация — обобщённый обзор, не прогноз и не медицинская консультация» — из `chart_interpretation.py`.
