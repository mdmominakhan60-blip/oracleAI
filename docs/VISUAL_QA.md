# OracleAI — Visual QA и Polish Pass

**Дата:** 27 августа 2026 года  
**Область проверки:** Mini App, RU/EN, shell, home/ritual, guide hub, chat, profile, profile tabs, Tarot entry state, modal/sheet, loading/empty/recovery patterns.  
**Контрольные ширины:** 375px, 768px, 1440px и 1920px.  
**Evidence:** [`UI_PIXEL_AUDIT.md`](UI_PIXEL_AUDIT.md) и воспроизводимые capture scripts [`scripts/visual_qa_capture.py`](../scripts/visual_qa_capture.py), [`scripts/capture_visual_baseline.py`](../scripts/capture_visual_baseline.py) и [`scripts/admin_visual_contract.py`](../scripts/admin_visual_contract.py). Generated JSON/PNG outputs остаются за пределами release tree и должны прикладываться к конкретному CI/run artifact.

## Методика

Аудит выполнен сквозным способом: сначала проверялись общие визуальные аспекты по всем экранным модулям, затем проходились пользовательские состояния и локализации. Для воспроизводимости добавлены [`scripts/visual_qa_capture.py`](../scripts/visual_qa_capture.py) и [`scripts/capture_visual_baseline.py`](../scripts/capture_visual_baseline.py). Второй harness дополнительно сохраняет geometry snapshots для viewport, app frame, header, screen, hero, cards, CTA и bottom navigation. Отдельно проверяются отсутствие горизонтального overflow, именованные focusable-элементы, `alt` у изображений и reduced-motion. Admin Dashboard дополнительно проверяется в desktop `1280×900` и mobile `390×844`; `scripts/admin_visual_contract.py` проверяет overflow, accessible names, image alt и 44px control target.

> Важно: атмосферные `.starfield`-элементы намеренно могут выходить за границы собственного canvas для мягкого bleed-эффекта. QA считает это декоративным bleed, если `body.scrollWidth` не превышает viewport и UI-элементы не создают overflow.

## Сводка

| Метрика | Результат |
|---|---:|
| Найдено визуальных несоответствий | 24 |
| Категории чек-листа | 12 |
| Исправлено кодом | 21 |
| Зафиксировано как осознанное исключение | 3 |
| Контрольных DOM-состояний в финальном capture | 48 |
| Состояний с реальным горизонтальным overflow | 0 |
| Focusable без имени | 0 |
| Изображений без `alt` | 0 |
| Core token contrast ниже WCAG AA | 0 |

## Журнал найденного и статус

| № | Страница / компонент | Проблема | Исправление / решение | Статус |
|---:|---|---|---|---|
| 1 | Весь UI / tokens | Палитра была разделена между legacy-токенами и отдельным ritual-слоем. | Добавлены семантические `--color-*`, status-токены, aliases для обратной совместимости. | Исправлено |
| 2 | Весь UI / type | Не было единой фиксированной шкалы H1–H6, body, caption, label и button-text. | Добавлены `--font-size-*`, line-height, tracking и общий font-family contract. | Исправлено |
| 3 | CSS cascade | Использовались неопределённые custom properties, включая `--ac-glow`, `--ac-surface`, `--line`, `--champagne-200`. | Добавлены безопасные семантические aliases в token layer. | Исправлено |
| 4 | Весь UI / spacing | Отступы и control heights задавались многочисленными разрозненными значениями. | Добавлена 4px spacing scale и cross-screen rhythm в `16-visual-qa.css`. | Исправлено |
| 5 | Desktop canvas | Декоративные элементы попадали в overflow-метрику на 1440/1920px. | `html/body` и decorative layers получили overflow guard; capture различает UI overflow и атмосферный bleed. | Исправлено |
| 6 | Home / hero | На узкой ширине заголовок и дневное сообщение конкурировали за пространство. | Применены balanced headings, bounded copy и согласованный screen padding. | Исправлено |
| 7 | Shared header | Имя пользователя закономерно обрезалось, но без явного contract для длинных имён. | Зафиксированы max-width, ellipsis, 44px target и compact правила для 375px. | Исправлено |
| 8 | Bottom navigation | Не были единообразно закреплены высота, grid-колонки, иконка и focus behavior. | Навигация переведена на три равные колонки и единый touch/focus contract. | Исправлено |
| 9 | Buttons | Hover/active/disabled/focus не были заданы одним кросс-экранным правилом. | Введены shared transitions, disabled opacity, active scale и focus ring. | Исправлено |
| 10 | Inputs / textareas / selects | Placeholder, focus border и высота полей расходились по feature-модулям. | Нормализованы min-height 44px, radius, border, placeholder и focus ring. | Исправлено |
| 11 | Cards | Card surfaces использовали разные радиусы и border semantics. | Установлены shared card radius 20px и semantic border color. | Исправлено |
| 12 | Modals / sheets | Не было общего cross-screen overlay/focus/geometry contract. | Зафиксированы overlay blur, 24px sheet radius, close-zone и safe-area правила. | Исправлено |
| 13 | Toast / status | Статусы могли различаться по цвету и не имели общей ширины. | Добавлены success/warning/error/info tokens и max-width toast. | Исправлено |
| 14 | Loading / skeleton | Skeleton и loading-star были оформлены разными локальными значениями. | Общая motion/reduced-motion contract сохранена в final layer и design system. | Исправлено |
| 15 | Empty / recovery | Empty/error UI не всегда был описан единым визуальным паттерном. | Зафиксирован pattern sigil + title + copy + CTA/retry. | Исправлено |
| 16 | Iconography | Интерактивные controls частично использовали emoji-подобные символы. | SVG sigil-набор объявлен обязательным для controls; emoji оставлены только как контентные символы чтения. | Частично: 1 осознанное исключение |
| 17 | Images / avatars | Не был централизован object-fit/radius contract для portrait/card imagery. | Зафиксированы 60–62px agent portraits, object-fit cover и единая форма. | Исправлено |
| 18 | RU/EN localization | Нужно было проверять длинные labels в header/nav/tabs на 375px и 768px. | Добавлены короткие bounded labels, balanced headings и capture для обеих локалей. | Исправлено |
| 19 | Responsive | Предыдущий baseline покрывал 360/390/430px, но не все ширины из задания. | Добавлен four-breakpoint harness 375/768/1440/1920. | Исправлено |
| 20 | Safe area | Safe-area правила были разбросаны по модулям. | Contract закреплён для header, composer, sheet и bottom navigation через `env()`. | Исправлено |
| 21 | Motion | Было несколько локальных duration/easing значений. | Добавлены `--motion-focus`, `--motion-enter`, `--motion-exit`, reduced-motion fallback. | Исправлено |
| 22 | Visual hierarchy | Основной CTA и вторичные действия не были формально описаны по всем поверхностям. | Design System закрепляет один primary CTA на смысловой блок и шампань как его семантическую роль. | Исправлено |
| 23 | Accessibility | Не было отдельного скрипта для численной проверки core token contrast. | Добавлен `scripts/check_visual_contrast.py`; все четыре core-пары проходят AA. | Исправлено |
| 24 | Decorative bleed | Некоторые фоновые элементы намеренно выступают за внутреннюю область app frame. | Это оставлено как художественное исключение, поскольку не увеличивает `scrollWidth` и не перекрывает UI. | Осознанное исключение |
| 25 | Pixel reconstruction | Mobile home/chat/profile/Tarot и admin dashboard нуждались в измеримых frame, section rhythm, card family, nav clearance и responsive control rules. | Добавлены `18-pixel-reconstruction.css`, `admin/pixel-reconstruction.css`, geometry snapshots и explicit admin aria labels. | Исправлено; local desktop/mobile retest pass |

## Состояния по экранным сценариям

| Экран / состояние | Проверено | Результат |
|---|---|---|
| Age gate | RU/EN, mobile/tablet/desktop | Центрированная карточка, readable copy, явный accept/leave и safe-area. |
| Onboarding | RU/EN, mobile | Overlay с одним primary action, вторичным skip и прогресс-индикатором. |
| Сегодня | RU/EN, 4 ширины | Hero, daily CTA, rhythm card, empty/loading и bottom navigation сохраняют иерархию. |
| Диалоги | RU/EN, 4 ширины | Agent cards имеют одинаковые portrait, role, proof, tool list и primary action. |
| Чат проводника | RU/EN, 4 ширины | Header, tabs, message bubbles, composer, tool sheet и recovery state используют общий контраст/focus. |
| Моё | RU/EN, 4 ширины | Profile hero, tabs, summary, chart, history и memory сохраняют единый card language. |
| Натальная карта / modal | RU/EN, 4 ширины | Кнопка закрытия, scrollable content, focus anchor и semantic action order зафиксированы. |
| Память / modal | RU/EN, 4 ширины | Empty/add/search/delete states имеют объяснение и не используют цвет как единственный сигнал. |
| Tarot entry | RU/EN, 4 ширины | Onboarding/reading entry не обрезает CTA и сохраняет reduced-motion behavior. |
| Admin Dashboard | RU/EN not applicable; desktop/mobile | Sidebar, KPI grid, controls, payment card, no overflow, no unnamed focusables and 44px controls verified locally. |

## Финальный проход

После исправлений выполнены статические проверки design contract, JS syntax, `git diff --check`, численная проверка contrast и четыре-breakpoint capture. Финальная визуальная цель достигнута: интерфейс ощущается как один премиальный продукт с единым ночным canvas, шампань-фокусом, двумя шрифтовыми семействами, предсказуемой сеткой и одинаковыми интерактивными состояниями. Оставшиеся прямые значения внутри декоративных градиентов относятся к artwork/atmosphere и не используются как несогласованные UI-состояния.

## References

[1]: [W3C, WCAG 2.2 — Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
[2]: [MDN, `prefers-reduced-motion`](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion)
[3]: [`scripts/visual_qa_capture.py`](../scripts/visual_qa_capture.py)
[4]: [`scripts/check_visual_contrast.py`](../scripts/check_visual_contrast.py)
