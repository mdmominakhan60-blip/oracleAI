# Дизайн-система OracleAI

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Current Mini App visual and interaction contract. |
| **Source of truth** | `miniapp/css/`, `miniapp/js/`, `miniapp/index.html`. |
| **Scope** | Tokens, layout, components, motion, localization and accessibility states. |
| **Do not change** | Do not bypass the token cascade, delegated actions or reduced-motion contract. |
| **Key files** | `miniapp/css/00-tokens.css`, `miniapp/js/15-actions.js`, `scripts/check_design_contract.py`. |
| **Validation** | `python3 -m scripts.check_design_contract`. |


**Статус:** актуализировано после финального Visual QA, 27 августа 2026 года.
**Область:** Telegram Mini App, русская и английская локализации, экраны «Сегодня», «Диалоги», «Моё», чат проводника, Таро, натальная карта, совместимость, память, модальные окна и состояния загрузки/ошибки.

## 1. Визуальная позиция

OracleAI — это **тихий ночной ритуал**, а не игровой автомат предсказаний. Космический фон задаёт настроение, но не конкурирует с задачей. Тёплый шампань используется для основного действия и фокуса, лиловый — для вторичного контекста, а интерфейсные состояния всегда подкрепляются текстом, формой или иконкой.

> **Правило:** мистичность задаёт настроение; интерфейс остаётся предсказуемым, читаемым и управляемым.

Первичным источником cross-screen токенов является [`miniapp/css/00-tokens.css`](../miniapp/css/00-tokens.css). Последний слой [`miniapp/css/16-visual-qa.css`](../miniapp/css/16-visual-qa.css) содержит только общие инварианты: overflow safety, type rhythm, focus, touch targets, state semantics и responsive guardrails. Порядок импорта в [`miniapp/styles.css`](../miniapp/styles.css) обязателен.

## 2. Цветовые токены

| Токен | Значение | Назначение |
|---|---:|---|
| `--color-bg-primary` | `#0a0920` | Основной canvas; не использовать чистый чёрный. |
| `--color-bg-secondary` | `#100e29` | Вторичная поверхность и header. |
| `--color-bg-elevated` | `#19153a` | Поднятые карточки, sheets и активные области. |
| `--color-bg-overlay` | `rgba(10, 9, 32, .92)` | Плотный фон модального слоя. |
| `--color-accent` | `#f5d48b` | Основной CTA, активный tab, focus. |
| `--color-accent-strong` | `#ffe9b4` | Светлый акцент и текст на важных поверхностях. |
| `--color-accent-deep` | `#eabf68` | Градиентный низ CTA и декоративная глубина. |
| `--color-accent-secondary` | `#b9a6ff` | Лиловый вторичный акцент, навигация и инструменты. |
| `--color-text-primary` | `#faf8ff` | Заголовки и основной текст. |
| `--color-text-secondary` | `#d4cee7` | Пояснения, вторичный текст и описания. |
| `--color-text-muted` | `#a39bbd` | Подписи и метаданные; не использовать для ключевого текста. |
| `--color-text-subtle` | `#6f6890` | Только несущественные подсказки. |
| `--color-border` | `rgba(230, 219, 255, .14)` | Нейтральные границы. |
| `--color-border-strong` | `rgba(245, 212, 139, .38)` | Активная граница и focus-support. |
| `--color-success` | `#7be0c5` | Успешное сохранение/доступность агента. |
| `--color-warning` | `#f5d48b` | Предупреждение и мягкое ограничение. |
| `--color-error` | `#f5a9c7` | Ошибка, восстановление, отказ. |
| `--color-info` | `#b9a6ff` | Информационное состояние. |
| `--color-on-accent` | `#251d39` | Тёмный текст на шампань-CTA. |

Визуальный QA проверяет пары основных токенов скриптом [`scripts/check_visual_contrast.py`](../scripts/check_visual_contrast.py). Зафиксированные коэффициенты: primary text на primary background — **18.58:1**, secondary text — **12.85:1**, muted text — **7.44:1**, on-accent — **13.37:1**. Для обычного текста применяется минимум 4.5:1 согласно WCAG 2.2 AA.[1]

## 3. Типографика

Используются не более двух семейств: `Cinzel` для смысловых заголовков и `Plus Jakarta Sans` для текста, навигации и действий. Заголовки и CTA написаны в Sentence case; uppercase зарезервирован для коротких kicker/role labels.

| Роль | Размер | Line-height | Weight | Семейство |
|---|---:|---:|---:|---|
| H1 | 32px | 1.08 | 700 | `--font-family-display` |
| H2 | 24px | 1.08 | 700 | `--font-family-display` |
| H3 | 20px | 1.08 | 700 | `--font-family-display` |
| H4 | 18px | 1.08 | 700 | `--font-family-display` |
| H5 | 16px | 1.25 | 700 | `--font-family-display` |
| H6 | 14px | 1.4 | 700 | `--font-family-body` |
| Body large | 16px | 1.55 | 400 | `--font-family-body` |
| Body | 14px | 1.55 | 400 | `--font-family-body` |
| Caption | 12px | 1.4 | 500 | `--font-family-body` |
| Label | 11px | 1.2 | 700–800 | `--font-family-body` |
| Button text | 13px | 1.2 | 800 | `--font-family-body` |

Текстовые блоки ограничиваются примерно 68 символами в строке. Для ключевых заголовков используется `text-wrap: balance`, а для RU/EN запрещены обрезание предупреждений и бессмысленные переносы. Если английский label становится слишком длинным, сначала сокращается формулировка, а не уменьшается базовый кегль.

## 4. Сетка, отступы и геометрия

Базовая единица — **4px**. Рабочая шкала: `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64px`. Общий Mini App frame ограничен 480px и центрируется на планшете и десктопе; это осознанный Telegram-first паттерн, а не случайно узкая колонка. Внутренний контент не должен создавать горизонтальный scroll.

| Объект | Эталон |
|---|---:|
| Control/touch target | минимум 44px |
| Control radius | 14px |
| Card radius | 20px |
| Sheet/modal radius | 24px |
| Screen side padding | 16px; на очень узком экране 12px |
| Card inner padding | 16px; compact card 12px |
| Межсекционный ритм | 24px |
| Safe area | `env(safe-area-inset-top/bottom)` |

## 5. Component Library

| Компонент | Эталонные характеристики | Обязательные состояния |
|---|---|---|
| Header / brand lockup | Симметричная grid-шапка, 44px controls, бренд по центру, имя с ellipsis только в pill. | default, compact, long-name, notification-dot |
| Bottom navigation | Три равные колонки, минимум 54px высоты, иконка 18px, активный tab — шампань-градиент плюс текст. | default, active, pressed, focus |
| Primary button | 44–46px, radius 14px/999px для ritual CTA, тёмный `--color-on-accent` на акценте. | hover, active, focus, disabled, loading |
| Secondary/ghost button | Прозрачная поверхность, `--color-border`, текст secondary; не конкурирует с primary. | hover, active, focus, disabled |
| Input/textarea/select | Минимум 44px, radius 14px, placeholder muted, focus border plus visible ring. | default, focus, error, success, disabled |
| Card | Radius 20px, тонкая semantic border, мягкая elevation; один основной CTA на смысловой блок. | default, featured, interactive, loading, empty |
| Modal / sheet | Overlay с blur, единая close-zone 40–44px, sheet 24px сверху, safe-area снизу. | enter, active, exit, keyboard/focus |
| Toast / notification | Центрированная нижняя позиция, max-width 420px, тип дополнен текстом/иконкой. | success, error, info, dismiss |
| Chip / tab | Минимум 36–44px, выбранное состояние обозначено цветом и формой/контрастом. | default, selected, disabled, focus |
| Dropdown/tool sheet | Вертикальный gap 8–12px, элементы 44–60px, не перехватывает горизонтальный swipe. | closed, open, selected, focus |
| Loader/skeleton | Единый shimmer/skeleton и loading-star; сохраняет структуру карточки. | loading, reduced-motion |
| Empty/recovery state | Иконка/сигил, короткий заголовок, пояснение и, где нужно, retry/CTA. | empty, error, retry |
| Avatar/agent portrait | Контроль 44px, agent portrait 60–62px, единый radius и object-fit cover. | loaded, fallback, loading |
| Status badge | Pill, компактный padding, 11px label, semantic color плюс текст. | success, warning, error, info |
| Scrollbar | Ненавязчивый 5px thumb на `.screen`; без конкурирующей декоративной стилизации. | default |

Иконки должны приходить из единого SVG sigil-набора, иметь одинаковую оптическую толщину и не заменяться emoji в интерактивных controls. Emoji допускаются только как контентный символ в данных чтения, не как единственная маркировка действия.

## 6. Motion и доступность

Микро-переходы используют `--motion-focus: 160ms`; появление sheet/modal — `--motion-enter: 320ms`; закрытие — `--motion-exit: 220ms`; easing — `--ease`/`--motion-ritual`. Анимируются преимущественно `transform` и `opacity`. Декоративное движение отключается через `prefers-reduced-motion: reduce`; при этой настройке transition/animation практически мгновенны, а scroll behavior становится auto.

Focus-visible должен быть заметен на кнопках, ссылках, tabs, inputs и dialog actions. Цвет не является единственным индикатором: ошибка сопровождается текстом/иконкой, active tab — контрастом и формой, success — сообщением. Все touch targets не меньше 44px; Telegram safe area учитывается в header, composer, sheet и bottom navigation.

## 7. Responsive contract

Обязательные контрольные ширины: **375px**, **768px**, **1440px** и **1920px**. На 375px приоритетом являются читаемый hero, короткие nav labels и отсутствие обрезания основной копии. На 768px приложение сохраняет центрированный frame, а не растягивает карточки до нечитабельной ширины. На 1440px и 1920px фон может занимать весь экран, но декоративные элементы не создают layout overflow; контент остаётся в bounded frame.

## 8. Изменение клиентских стилей

Новые значения сначала сопоставляются с токенами. Если значение действительно уникально для иллюстрации, оно остаётся локальным только в декоративном слое и не используется как UI-состояние. После изменения клиентского CSS поднимается cache-busting в [`miniapp/index.html`](../miniapp/index.html) и [`miniapp/styles.css`](../miniapp/styles.css). Перед merge запускаются `python3 scripts/check_design_contract.py`, `python3 scripts/check_visual_contrast.py`, `python3 scripts/visual_qa_capture.py`, `node --check miniapp/js/*.js` по отдельности и `git diff --check`.

## References

[1]: [W3C, Web Content Accessibility Guidelines (WCAG) 2.2, Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
