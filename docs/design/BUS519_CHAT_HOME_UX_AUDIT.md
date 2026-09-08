# BUS-519 [BUS-501/A1] — UX/UI-аудит миниаппа: чат и главная

Статус: ready for review → на согласование EL.
Метод: аудит по коду репо `oracleAI/miniapp/` + базовые скриншоты (`docs/design/bus519-audit-screens/`, playwright-прогон с моками API, 390×844 iPhone, dark) + research паттернов (§RESEARCH).
Принцип спеки BUS-501: UX → information architecture → interaction → visual design (р.11); «дизайн ради дизайна» запрещён; ничего не ломаем (р.12), не реализуем вслепую (р.14).

## Скриншот-база (текущее состояние)

Файлы в `docs/design/bus519-audit-screens/`:

| # | Экран | Что зафиксировано |
|---|-------|-------------------|
| 01 | welcome (язык) | интро-шаг 1: логотип, «Выбери язык», 2 кнопки |
| 02 | home fresh | главная сразу после интро |
| 03 | home | главная с данными /api/today |
| 04 | hub | «Твои проводники», карточка Лилит |
| 05 | chat oracle | чат с intro-карточкой и чипами |
| 06 | chat scrolled | 30 сообщений, heads-hidden активен |
| 07 | chat sessions | панель «Твои разговоры» |
| 08 | chat tools | bottom-sheet «Инструменты диалога» |
| 09 | chat tarot | чат Мадам Ленорман |

Прогон: `.scratch-bus519/shoot2.py` (моки `/api/**`, локальный статик-сервер) — воспроизводим.

---

## 1. CURRENT STATE (по коду)

### 1.1. Каркас приложения
- `#app-root` — flex-колонка: `.app-header` → `#app-main` → `.app-nav` (`js/05-app.js:377-395`).
- Шапка двухрядная (BUS-399): ряд 1 — user-pill (имя), бренд ORACLE AI, колокольчик; ряд 2 `.header-status` — кристаллы + кнопка «Тарифы ›» (`css/18-pixel-precision.css:169-192`). min-height 66px, padding-top `max(12px, env(safe-area-inset-top))` (`css/15-ritual-redesign.css:67`). Фактическая высота ≈ 100–110px.
- Нижняя навигация: 4 таба — Сегодня / Диалоги / Оплата / Моё. Padding `8px 16px calc(10px + env(safe-area-inset-bottom))`, кнопки min-height 44px + иконки 42px (`css/01-sky-shell.css:118-135`). Итог ≈ 75–80px.
- Тач-таргет 44px — глобальный инвариант (`button { min-height: 44px }`, `--touch-target: 44px`).
- Viewport: `viewport-fit=cover` (`index.html:5`); высота app-root = `--tg-viewport-stable-height` когда известна, иначе `100dvh` (`css/20-chat-viewport.css:56-62`).
- Тема: только dark (`:root { color-scheme: dark }`, `css/15-ritual-redesign.css:1669`); light-темы нет. `prefers-reduced-motion` гейтится (4 CSS-файла).
- Свайпы (`js/14-gestures.js`): горизонталь — смена вкладок; в чате свайп вправо — закрыть чат, свайп влево/вверх — открыть тулзы; на agent-tabs горизонталь — переключение проводника.

### 1.2. Чат (после R-8, BUS-509/510 — уже реализовано)
- **nav-hidden**: в чате скрываются `.app-nav` и `.app-header` (`display: none` — высота реально возвращается ленте) (`css/20-chat-viewport.css:15-21`).
- **chat-head** (свой этаж чата): back ‹ (42px) + аватар 44px + имя/титул + proof-строка «✦ Доказательно сначала · N инструментов» + пикер «Пространство Лилит · 3 чата» + кнопка «Новый чат». min-height 64px, фактически до ~76px (2 строки текста) (`css/15-ritual-redesign.css:288-293`, `js/07-chat.js:452-472`).
- **agent-tabs**: лента из 4 пилюль персон под chat-head, ~48px (`css/15-ritual-redesign.css:296`).
- **heads-hidden**: chat-head сворачивается (`max-height: 0`) при скролле ленты вниз >36px, возвращается при скролле вверх или y≤0; анти-осцилляция 400ms; transition 280ms без `prefers-reduced-motion` (`js/07-chat.js:86-122`, `css/20-chat-viewport.css:26-44`). **agent-tabs при этом не скрывается** — он не входит в селектор.
- **chat-live** (≥2 сообщений): suggest-chips скрываются (`css/20-chat-viewport.css:52`).
- **viewport-compact** (stable height < 480px): intro-карточка коллапсирует до kicker-строки (`js/05-app.js:226-238`).
- **Композер** — 3 слоя: `composer-context` (presence «● Лилит рядом» + «Инструменты ↑»), `composer-top` (textarea + send 40px), `suggest-chips` (`js/07-chat.js:499-516`, `css/06-composer-chat.css:11-14`). Padding-bottom `calc(12px + env(safe-area-inset-bottom))`.
- **Клавиатура**: `viewportChanged` + `isStateStable` → stable-height; `visualViewport.resize` → composer padding-bottom = (innerHeight − vv.height) + 8px (`js/05-app.js:213-220`). `interactive-widget` в meta viewport **не задан** — поведение клавиатуры Android отдаётся на усмотрение WebView.
- **BackButton Telegram**: иерархия модал → тулзы → чат → home (`js/05-app.js:479-497`); в chat-head дублирующая back-кнопка.

### 1.3. Главная (после BUS-517/R-10 — уже реализовано)
- Hero welcome-card: kicker «СЕГОДНЯ — БЕЗ СПЕШКИ» + дата, приветствие с именем, лунный чип, блок «ЗНАК НА СЕГОДНЯ» (3-строчный кламп + «РАЗВЕРНУТЬ ▼»), CTA «Спросить о своём дне →», ghost-строка next_action (`js/06-home.js:29-56`, `css/16-visual-qa.css:370-378`).
- Ниже 2 свёрнутых аккордеона: «Вернуться к себе» (ритуал 0/2) и «Карта, которая рядом» (`js/06-home.js:59-115`); третий — «Неделя луны» при наличии данных.
- Типографика forecast-блока: `::before` — большая кавычка «, `::first-letter` — drop-cap 27px champagne, `::after` — подпись «твой маленький ориентир» (`css/15-ritual-redesign.css:158-165`). Три декоративных приёма на одном блоке.
- Хуб проводников: на каждого агента карточка с именем, outcome, proof-бейджами, 3 ask-чипами, 4 tool-кнопками; у астролога — vedic-surface ещё с 4 картами (`js/06-home.js:186-237`).

### 1.4. Наблюдения со скриншотов
- **05/09 (чат)**: над первым сообщением ~260px служебных слоёв: chat-head (~76px) + agent-tabs (~48px) + intro-карточка (~120px) + композер с presence (~140px). suggest-чипы обрезаны нижним краем вьюпорта — видны наполовину (нестабильная stable-height раскладка при первом входе).
- **06 (скролл)**: heads-hidden работает (скриншот подтверждает скрытый chat-head), но agent-tabs остаётся — вертикаль экономится лишь наполовину.
- **03 (home)**: топ-бар 5 сущностей в 2 рядах; имя в user-pill обрезается («Анна С...»); текст знака дня обрывается жёстко посреди фразы (кламп 3 строки без ellipsis-маски).
- **04 (hub)**: 4 равнозначные крупные карточки — все инструменты одной массы, иерархии Primary/Secondary/Tertiary нет (против р.7.4 спеки).
- **08 (tools)**: bottom-sheet корректен: ручка, заголовок, группа «С Лилит», элементы с метаданными (цена времени). Паттерн здоров.

---

## 2. PROBLEM

### Чат (B1) — приоритет спеки р.5.2 «CHAT — главный элемент экрана»

| # | Проблема | Эффект | Принцип спеки |
|---|----------|--------|----------------|
| C1 | Двухэтажная верхняя зона: chat-head (~76px) + agent-tabs (~48px) = **~124px до ленты**; heads-hidden убирает только chat-head | При скролле вниз чат получает лишь ~50% возможного пространства; agent-tabs остаётся «вечной полосой» | р.5.2, р.5.3 |
| C2 | intro-карточка + suggest-чипы + presence-строка в холодном старте: **~260px служебного** до первого сообщения; чипы обрезаны краем вьюпорта | Первый экран чата — не диалог, а витрина; обрезанный чип выглядит багом | р.5.2, р.6.1 |
| C3 | Композер 3 слоя постоянной высоты: presence «Лилит рядом» + input + чипы (~140px) | Поле ввода — единственный обязательный элемент, но 2 из 3 слоёв — декоративно-контекстные | р.5.4 |
| C4 | chat-head перегружен: back + аватар + имя + титул + proof-строка + пикер сессий + «Новый чат» — 3 навигационных контрола разной природы в одной строке; на узких экранах титул режется (max-width 60px ellipsis) | Плотность выше читаемой; proof-маркетинг в постоянной шапке дублирует хуб | р.5.5 |
| C5 | `interactive-widget` не задан в meta viewport | На Android-WebView клавиатура может вести себя иначе (resize visual vs content); текущий обход через visualViewport-padding работает, но зависит от ненадёжных событий Telegram | р.5.4 |

### Главная (B2)

| # | Проблема | Эффект | Принцип спеки |
|---|----------|--------|----------------|
| H1 | Топ-бар: 5 сущностей в 2 рядах (~100–110px) + сверху системный заголовок Telegram — двойной брендинг; «Тарифы ›» — CTA монетизации в постоянной шапке наравне с профилем | Ровно то, против чего р.7: «навигация не должна занимать экран»; монетизация визуально равна контенту | р.7, р.7.4 |
| H2 | Три типографских приёма в одном forecast-блоке (кавычка + drop-cap + after-подпись) | «Дизайн ради дизайна» (прямо запрещён р.11); drop-cap «Д» визуально отрывается от слова | р.11 |
| H3 | Кламп 3 строки без ellipsis-маски: текст обрывается посреди фразы | Читается как баг рендера, а не как «есть ещё» | р.10 (состояния) |
| H4 | Секции главной одинаковой визуальной массы: hero, 2 аккордеона, (луна) — Primary/Secondary/Tertiary не разделены | «Что я могу сделать прямо сейчас?» — вопрос р.7.2 — отвечает только hero; остальное конкурирует за внимание | р.7.4 |
| H5 | Хуб: 4 равнозначные карточки-простыни (у каждой до 8+ кнопок) | Каталог всех функций — прямо названный антипаттерн р.7.1 | р.7.1 |

### Кросс-темы (не блокируют B1/B2, фиксируем)
| # | Проблема |
|---|----------|
| X1 | Light-темы нет (р.10 «dark/light appearance»); осознанное ограничение бренда — оставить dark-only, но задокументировать |
| X2 | Таб «Оплата» — 25% нижней навигации отдано монетизации; кандидат на перенос в «Моё»/профиль (изменение IA — согласовать) |
| X3 | Класс `viewport-compact` ставится на `<html>` (`js/05-app.js:235`), но не используется ни в одном CSS-файле — работает только прямой класс `agent-intro--collapsed` на intro. Мёртвый флаг: либо задействовать, либо убрать |

---

## 3. RESEARCH

### 3.1. Telegram WebApp: viewport, клавиатура, safe area (по оф. документации core.telegram.org)

| Факт | Источник | Следствие для миниаппа |
|------|----------|------------------------|
| `viewportHeight` — «refresh rate… not sufficient to smoothly follow the lower border»; прямо запрещено пинить к нему нижний UI | docs.telegram.org (webapps#viewport) | R-8 уже верно использует `viewportStableHeight` (`css/20-chat-viewport.css:60`) |
| `viewportStableHeight` меняется «after all gestures and animations are completed» | там же | текущая логика `isStateStable` (`js/05-app.js:199-205`) соответствует документации |
| **SafeAreaInset / ContentSafeAreaInset** (Bot API 8.0+): CSS-переменные `--tg-safe-area-inset-*` и `--tg-content-safe-area-inset-*`, события `safeAreaChanged`/`contentSafeAreaChanged` — «to avoid overlapping with system UI elements» | docs.telegram.org (webapps#safeareainset) | **миниапп не использует ни одну** `--tg-*safe-area*` переменную (grep пуст) — только `env(safe-area-inset-*)`. Внутри Telegram на Android/iOS `env()` может не совпадать с реальными отступами Telegram UI (header, bottom bar) |
| `interactive-widget` (Chrome 108+ Android): по умолчанию `resizes-visual` — «Elements that use position: fixed remain in place and can be obscured by the OSK»; **«These changes do not affect WebView»** | developer.chrome.com/blog/viewport-resize-behavior | Telegram Android = WebView → там layout-resize поведение сохраняется; но Telegram Desktop/внешние браузеры — Chrome 108+ с `resizes-visual`. Миниапп **не задаёт** `interactive-widget` (grep пуст) → поведение композера различается по платформам, текущий JS-обход (`visualViewport.resize` → padding, `js/05-app.js:213-220`) компенсирует эмпирически |
| `hideKeyboard()` (Bot API 9.1+) | docs.telegram.org | не используется; кандидат для «отправил — клавиатура ушла» (паттерн WhatsApp/TG) |
| `requestFullscreen()` / `mode=compact` (Bot API 8.0+) | docs.telegram.org | вне скоупа B1; immersive-режим за счёт уже реализованных nav-hidden/heads-hidden |

**Вывод:** главные Telegram-специфичные пробелы — неиспользуемые `--tg-content-safe-area-inset-*` (Bot API 8.0, поддерживается во всех актуальных клиентах) и незакреплённый `interactive-widget`.

### 3.2. Паттерны consumer AI / messaging чата

| Паттерн | Кто применяет | Фактура |
|---------|---------------|---------|
| **Suggestion chips в потоке ленты** (не fixed) | AI-чаты (пишет Josh Comeau: «render suggestion chips inside the message list so they scroll away naturally») | joshcomeau.com/blog/ai-chat-ui; согласуется с NN/g про «disappearing vs persistent suggested responses» (nngroup.com/articles/chat-apps) — chips, которые остаются навсегда, «obtrusive» |
| **Чипы исчезают после первого ввода — консенсус индустрии** | Deutsche Telekom Design System: «Once a user selects a chip or enters a prompt, the chips are dismissed»; разборы AI-чатов: «once the user has started typing, the purpose of suggestion chips diminishes» | design.system.telekom/dev (Chips — AI guidelines); follow-up чипы у ChatGPT/Perplexity появляются под последним ответом (контекстные, не статические) |
| **Hide-on-scroll header** | Material `HideOnScroll` — канон: collapse при скролле вниз, reveal вверх | mui.com/material-ui/react-app-bar |
| **Collapsing header — M3-дисциплина** | Material3 scrolling patterns: `exitUntilCollapsed` — шапка схлопывается «до закреплённой высоты», а не исчезает полностью; reverse scroll обязан возвращать; при схлопывании нужен status-bar scrim. Apple HIG (iOS 17 collapsing toolbars): действия схлопнувшейся шапки переносятся в overflow «⋯» | m3.material.io/foundations/designing/structure/patterns-scrolling; developer.android.com (TopAppBarScrollBehavior); hackingwithswift.com/articles/266 |
| **Empty-state ChatGPT**: композер по центру экрана + чипы; при первом вводе уезжает вниз. Header минимален (одна строка: меню + селектор модели в выпадашке + аватар); служебных строк над композером нет | help.openai.com; анонс редизайна 2025 | chat-head OracleAI в этом смысле избыточен (3 контроллера + proof-строка) |
| **Sticky composer + growing textarea** | все мессенджеры; composer dock к клавиатуре и safe area | ramotion.com/blog/designing-chat-input-mobile-app; headway.io/blog/scrolling-chat-view-composer-in-ios |
| **Follow-up чипы под ответом (не constant layer)** | Perplexity: «Related»-подсказки появляются под ответом модели, над композером, скроллятся горизонтально; ChatGPT возвращает context chips после ответа | uxchecklist.net/patterns/ai-suggestions; darrenchuang.com/studies/perplexity |
| **Scroll-to-bottom FAB** — показывать только когда лента дальше экрана от низа | паттерн-сводка чат-UI | тот же набор источников |
| **Character.AI чат-герой**: шапка = имя персонажа + back + меню (⋯); переключение персонажей — вне шапки чата | mobbin.com (скриншоты флоу) | переключение проводников OracleAI через ряд tabs над лентой — валидный, но редкий вариант; у Character.AI выбор героя живёт на отдельном экране |
| **Композер при фокусе** — hiding UI on scroll + contextual/adaptive input; chips исчезают после использования | Medium: «Trends in Interface Design for Mobile Chat Apps» | chat-live-механика OracleAI уже скрывает чипы; presence-строка остаётся |

Проверка на выдумки: по Character.AI/Mobbin фактура поверхностная (источник — обзорные статьи), использована только как «в индустрии шапка чата одноэтажная»; числа/заявления без источника в §3 не внесены.

### 3.3. Консенсус и антипаттерны

- **Консенсус индустрии:** одноэтажная шапка чата (имя + back + минимум контролов); чипы — временный элемент пустого состояния; композер — одна строка ввода + send; всё остальное (presence, proof, маркетинговые строки) — кандидаты на скрытие после начала диалога.
- **Антипаттерны:** постоянный многослойный композер; дублирование одного факта в шапке и теле экрана; декоративная типографика в utility-текстах.

## 4. DESIGN OPTIONS

### Чат (C1–C4)

**C1 — верхняя зона 124px.**
- (a) Включить `.agent-tabs` в скрытие `heads-hidden` (1 строка CSS: `#app-root.heads-hidden .agent-tabs { max-height:0; … }` по образцу `.chat-head`). Дёшево; экономит ~48px при скролле. Минус: холодный старт не меняется.
- (b) Влить tabs в chat-head: тап по аватару в шапке = цикл проводников (свайп уже работает, `app.cycleAgent`). Экономит 48px всегда. Минус: discoverability, нужен onboarding-хинт.
- (c) Tabs под композером. Минус: ломает ментальную модель «шапка = кто говорит».

**C2 — 260px служебных до первого сообщения.**
- (a) Чипы → в поток ленты как «нулевое сообщение» (Comeau/NN/g): скроллятся естественно, исчезают при переполнении. Меняет DOM-узел — риск для e2e-селекторов.
- (b) Intro-карточку укоротить: убрать `.ai-persona` (имя+титул+аватар дублируют chat-head в 76px выше), оставить kicker + заголовок + текст. Экономит ~60px, DOM-селекторы чипов не трогает.
- (c) Скрыть presence-строку до начала диалога. Экономит ~28px.

**C3 — композер 3 слоя.** Расширить `chat-live`: скрывать `.composer-context` (presence + «Инструменты») вместе с чипами; тулзы остаются доступными через «＋» в строке ввода или sheet. Альтернатива — left-icon «＋» прямо в composer-top (одна строка ввода, как ChatGPT).

**C4 — перегруженный chat-head.** Убрать proof-строку («✦ Факты → интерпретация · N инструментов») — она дублирует хаб-бейдж того же содержания (`js/06-home.js:205`) и не помогает в диалоге. «Новый чат» — иконка без текста (label в aria). Итог: back + аватар + имя + пикер сессий + icon-кнопка.

### Главная (H1–H4)

**H1 — двухрядная шапка.**
- (a) Collapsing header: ряд 2 (кристаллы + «Тарифы») схлопывается при скролле вниз, как large-title iOS. Средний риск.
- (b) Слить в один ряд (кристаллы-иконка без суммы, тарифы → «Моё»). Меняет IA доступов.

**H2 — 3 декоративных приёма на forecast-блоке.** Оставить drop-cap (узнаваемая фишка бренда), убрать `::before` кавычку 38px и `::after` подпись «твой маленький ориентир» (декорация декорирует декорацию).

**H3 — кламп без маски.** Fade-маска на последней строке: `mask-image: linear-gradient(180deg, #000 70%, transparent)` — текст «растворяется» вместо жёсткого обрыва; «РАЗВЕРНУТЬ» остаётся явным.

**H4 — иерархия секций.** В рамках существующих аккордеонов BUS-517: hero = Primary (уже), «Вернуться к себе» = Secondary, луна/карта = Tertiary (визуально тише: меньше тени/насыщенности).

## 5. CHOSEN SOLUTION

### B1 (чат) — «пространство диалогу» доводится до конца R-8
1. **C1a** — agent-tabs сворачивается вместе с chat-head при скролле (P0).
2. **C2b** — intro-карточка без persona-блока (P0); **C3** — `chat-live` скрывает presence-строку, композер становится «input + send» (P0).
3. **C4** — proof-строку из шапки убрать, «Новый чат» — icon-button (P1).
4. **C5** — meta viewport дополнить `interactive-widget=resizes-content` (фиксирует поведение композера на Chrome-платформах; WebView не затронут) + принять `--tg-content-safe-area-inset-*` в padding шапки/композера, с fallback на текущие `env()` (P1).
5. **C1b/C2a** — отложены: вливание tabs в шапку и чипы-в-ленту меняют DOM-контракты e2e; решать после Q1 с QA.

Обоснование против альтернатив: выбрана линия «минимум DOM-изменений, максимум высоты ленты» — спека р.12 «не сломать продукт»; все P0-правки обратимы и не меняют навигационную модель.

### B2 (главная + welcome) — иерархия вместо равнозначности
1. **H3** — fade-маска клампа прогноза (P0, косметика рендера).
2. **H2** — убрать кавычку и after-подпись с forecast-блока (P1).
3. **H1a** — collapsing второй ряд шапки (P1, с Frontend).
4. **H4** — визуальная деградация Tertiary-секций (P1). Хуб-каталог (H5) — уже в скоупе B2 спеки BUS-501 («Все инструменты →»), здесь фиксируем как вход.

### Кросс-темы
- **X1** — dark-only остаётся осознанным решением бренда; фиксируем документально (без работ).
- **X2** — таб «Оплата» → кандидат на перенос в «Моё»; изменение IA — на согласование EL отдельно (не в P0/P1).
- **X3** — `viewport-compact` на `<html>` мёртв (grep: единственное место — установка класса, в CSS не читается). P2: либо задействовать для композера, либо убрать флаг.

## 6. Приоритизированный список правок (вход B1/B2)

| P | # | Правка | Файлы | Проверка |
|---|---|--------|-------|----------|
| **P0** | C1a | agent-tabs скрывается в heads-hidden | `css/20-chat-viewport.css` (+5 строк) | скриншот 06-аналог: tabs исчез; e2e чата зелёные |
| **P0** | C2b | intro без `.ai-persona` (kicker+title+text) | `js/07-chat.js:432-446` | высота intro ↓ ~60px; скриншот до/после |
| **P0** | C3 | `chat-live` скрывает `.composer-context` | `css/20-chat-viewport.css` (+2 строки) | после 2-го сообщения композер = input+send |
| **P0** | H3 | fade-маска на `.forecast-clamped` | `css/16-visual-qa.css:372` (+2 строки) | скриншот главной: нет жёсткого обрыва |
| **P1** | C4 | без proof-строки в chat-head; «Новый чат» icon | `js/07-chat.js:452-470`, `css/15-ritual-redesign.css` | высота head ↓ ~18px; a11y: aria-метки сохранены |
| **P1** | C5 | `interactive-widget=resizes-content` + `--tg-content-safe-area-inset-*` | `index.html:5`, `css/01-sky-shell.css`, `css/06-composer-chat.css` | девайс-прогон Android/iOS: композер не перекрыт |
| **P1** | H1a | collapsing ряд 2 шапки главной | `js/05-app.js` (scroll-heads механика на home), `css/18-pixel-precision.css` | скролл вниз: кристаллы/тарифы ушли; вверх: вернулись |
| **P1** | H2 | forecast: без кавычки-««» и after-подписи | `css/15-ritual-redesign.css:163,165` | скриншот: 1 декоративный приём |
| **P1** | H4 | Tertiary-секции тише визуально | `css/16-visual-qa.css` (тени/фоны аккордеонов) | снизшот: контраст Primary/Secondary/Tertiary виден |
| **P2** | X3 | `viewport-compact`: задействовать или удалить | `js/05-app.js:235` + CSS | grep: либо есть потребитель, либо флага нет |
| **вход B2** | H5 | хуб: «Все инструменты →», карточки-простыни режутся | скоуп B2 BUS-501 | — |
| **согласование** | X2 | таб «Оплата» → в «Моё» | IA-решение | EL-confirm |

---

*Аудит подготовлен UX/UI Designer, 2026-09-08. Скриншоты: `bus519-audit-screens/01–09`. Код: коммит ветки master репо oracleAI на дату аудита.*
