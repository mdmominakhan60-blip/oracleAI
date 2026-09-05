# OracleAI — Accessibility Checklist (гейт P2-002)

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Операционный чек-лист ручного accessibility-прогона Mini App в Telegram WebView на реальных устройствах. |
| **Owner** | UX/UI Designer (владелец гейта P2-002); исполнители фиксов — Frontend Engineer. |
| **Source of truth** | `miniapp/` (index.html, js/, css/), `miniapp/css/00-tokens.css`, `docs/DESIGN_SYSTEM.md`. |
| **When to run** | После закрытия MVP-1: staging URL Mini App, реальные iOS + Android. Локально прогон не засчитывается (правило CURRENT_STATUS: local ≠ staging). |
| **Pre-pass status** | Статический pre-pass выполнен 2026-09-05 (см. раздел «Pre-pass находки»); автоматика: axe-core + Lighthouse (`scripts/run_axe_core.mjs`, `scripts/run_lighthouse_axe.mjs`, артефакты `artifacts/lighthouse-axe-final/`) — локально зелёные. |
| **Evidence** | Заполненный протокол (раздел «Протокол прогона») + скриншоты/записи экрана прикладываются к issue BUS-112 и TASKS.md P2-002. |
| **Вердикт гейта** | P2-002 закрывается, когда все blocker/major находки исправлены и перепроверены на staging. Minor — фиксируются как исключения с обоснованием. |

## Условия прогона

| Параметр | Требование |
|---|---|
| Staging | Staging URL Mini App (после MVP-1), реальный подписанный `initData` |
| iOS | Реальный iPhone (notch/Dynamic Island), актуальная iOS, Telegram iOS, VoiceOver |
| Android | Реальный Android-телефон, актуальная Android, Telegram Android, TalkBack |
| Ориентации | Портрет + ландшафт (минимум для safe-area чеков) |
| Языки | RU и EN (переключение в профиле) |
| Темы | Системная светлая и тёмная (приложение dark-only — см. находку A-2) |
| Динамический текст | iOS Dynamic Type максимальный доступный; Android font scale 1.3x |
| Запись | Скриншот/видеозапись на каждый Fail; протокол ведётся по ходу |

## 1. Keyboard navigation (WCAG 2.1.1, 2.1.2, 2.4.3, 2.4.7)

> На мобильных проверяется через внешнюю клавиатуру (Bluetooth) — Telegram WebView поддерживает Tab/Shift+Tab. Частично заменяется VoiceOver/TalkBack-навигацией.

| № | Сценарий | Ожидание |
|---|---|---|
| K-1 | Tab по всему онбордингу (intro → выбор гайда) | Каждый интерактив достигается Tab, порядок = визуальный, фокус-рининг виден (`--focus-ring`) |
| K-2 | Tab по home/ritual, чату, профилю, карте, Таро | Нет «потерянного» фокуса; скрытые элементы не получают фокус |
| K-3 | Открыть tools sheet (`te-sheet`, role=dialog, aria-modal) | Фокус попадает внутрь; Tab не уходит за пределы (нет trap-нарушения, есть containment) |
| K-4 | Esc в открытом sheet/модалке | Закрытие; фокус возвращается на кнопку, открывшую диалог |
| K-5 | Enter в чат-инпуте — отправка; Shift+Enter — перенос строки | Работает (реализовано в `js/13-events.js`), не конфликтует с IME RU |
| K-6 | Tab-порядок формы compat (имя → дата → выбор связи → submit) | Логичный, метки связаны через `<label for>` |
| K-7 | Карусель Таро с клавиатуры | Есть альтернатива свайпу (кнопки/Tab-карты + Enter) — см. находку A-4 |
| K-8 | Внешняя клавиатура: Tab по нижней навигации (`main-nav`) | Каждый dock-item фокусируем, имя озвучивается |

## 2. Screen reader — iOS VoiceOver

| № | Сценарий | Ожидание |
|---|---|---|
| V-1 | Swipe right от верха: обходит ли VoiceOver декоративный starfield (`aria-hidden` на `.constellations`, `.lilith-sil`) | Декор не озвучивается |
| V-2 | Онбординг: заголовки, тексты, кнопка Skip | Каждый элемент имеет осмысленное имя; Skip доступен сразу |
| V-3 | Главный экран: ритуал, виджеты, CTA | Кнопки озвучиваются как «кнопка» + имя, не как «просто текст» |
| V-4 | Чат: история сообщений (`role="log"` на `.chat-messages`) | Новые сообщения озвучиваются автоматически без переспама |
| V-5 | Чат: отправка сообщения → индикатор загрузки (`role="status"`) | Состояние «печатает/загружаем» объявляется (aria-live polite) |
| V-6 | Ошибка отправки / toast | Объявляется скринридером (проверить aria-live на toast-контейнере) |
| V-7 | Tools sheet: открытие → VoiceOver фокус внутри диалога; Z-жест (escape) закрывает | Да; фокус возвращается на триггер |
| V-8 | Форма compat: поля даты/имени | Метка и обязательность (`обязательно`, `aria-describedby` для хинта даты) озвучиваются |
| V-9 | Карта (chart): загрузка (`role="status"`), результат, plaque | Статусы объявляются; декоративные SVG скрыты |
| V-10 | Таро: выбор карты, статус расклада (`aria-live` на `.tarot-draw-status`) | Переход «готов → тянем → результат» озвучивается |
| V-11 | Платежи: тарифы, кнопка оплаты, ошибки | Кнопка оплаты имеет имя; состояние ошибки читается |
| V-12 | Заголовок/хедер Telegram vs контент: прокрутка жестом | Нет «невидимых» перехватчиков жестов |

## 3. Screen reader — Android TalkBack

| № | Сценарий | Ожидание |
|---|---|---|
| T-1 | Линейная навигация свайпами по онбордингу и home | Соответствует V-1–V-3 |
| T-2 | Чат: чтение истории и новых сообщений | Соответствует V-4–V-5 |
| T-3 | Диалоги/sheet: TalkBack фокус внутри, закрытие жестом «назад» | Да |
| T-4 | Двойной тап по чипам инструментов и док-панели | Активация работает с первого раза (нет ложных pointer-перехватов из `js/14-gestures.js`) |
| T-5 | Таро-карусель: перелистывание через TalkBack | Эквивалентная альтернатива свайпу |

## 4. Contrast (WCAG 1.4.3 AA)

Замеренные статически значения токенов (`00-tokens.css`) — не перепроверять вручную, только новые составы (скриншот + пипетка в случае сомнений):

| Пара | Контраст | Статус |
|---|---|---|
| `--color-text-primary` #faf8ff на `--color-bg-primary/secondary/elevated` | 18.6 / 17.9 / 16.5 : 1 | AA ✔ |
| `--color-text-secondary` #d4cee7 на тех же фонах | 12.9 / 12.3 / 11.4 : 1 | AA ✔ |
| `--color-text-muted` #a39bbd на тех же фонах | 7.4 / 7.2 / 6.6 : 1 | AA ✔ |
| `--color-text-subtle` #948cb2 на тех же фонах | 6.2 / 6.0 / 5.5 : 1 | AA ✔ (BUS-115: был #6f6890, 3.8/3.6/3.4 — исправлено 2026-09-05) |
| `--color-on-accent` #251d39 на `--color-accent` #f5d48b | 11.2 : 1 | AA ✔ |
| `--color-error` #f5a9c7 / `--color-success` #7be0c5 на тёмных фонах | (замерить в прогоне для конкретных составов) | проверить на новых составах |

| № | Сценарий | Ожидание |
|---|---|---|
| C-1 | Все экраны RU/EN при тусклом дневном свете (реальная яркость ~50%) | Основной и вторичный текст читаемы |
| C-2 | Состояния disabled кнопок, чипов, платёжных статусов | Текст disabled-контролов ≥ 3:1 (4.5:1, если это смысловой текст) |
| C-3 | Текст поверх фото/градиентов (bg-cosmos, nebula) в реальном Telegram WebView | Локальные замеры на чистом фоне могут отличаться от композиции — проверить |

## 5. Touch targets (WCAG 2.5.8 AA / 2.5.5 AAA-цель)

Статически: правило `button, .btn, .nav-btn, .chip, .ask-chip, .tool, .dock-item, .moon-toggle, .moon-today { min-height: 44px }` (`15-ritual-redesign.css`) + `--touch-target: 44px`.

| № | Сценарий | Ожидание |
|---|---|---|
| TT-1 | Все кнопки нижней навигации, чипы инструментов, кнопки чата на реальном пальце | ≥ 44×44px, интервал между соседними целями не приводит к промаху |
| TT-2 | Мелкие иконки-действия: удаление записи памяти (`mem-del`), закрытие sheet, карточные меню | ≥ 44px или ≥ 24px цель с достаточным отступом (AA) — замерить линейкой скриншота |
| TT-3 | Элементы карусели Таро и выбора связи (compat) | Переключение без случайных соседних активаций |
| TT-4 | Поля ввода (дата/время/город) в нативных пикерах Telegram | Открываются с первого тапа |

## 6. Safe-area

| № | Сценарий | Ожидание |
|---|---|---|
| SA-1 | iPhone с notch/Dynamic Island: контент не под «ушами», хедер читаем | Да |
| SA-2 | Home indicator: нижняя навигация и composer чата не перекрываются (`env(safe-area-inset-bottom)` применяется) | Да; интерактив выше индикатора |
| SA-3 | Ландшафт iOS: чат-композер, нижняя навигация, sheets | Не перекрыты, не обрезаны |
| SA-4 | Android с жестовой навигацией: нижние панели | Аналогично SA-2 |
| SA-5 | Клавиатура Telegram открыта: composer не уезжает за клавиатуру, фокус-элемент виден | Да |

## 7. Reduced motion (WCAG 2.3.3 / `prefers-reduced-motion`)

Статически: покрытие в 11 CSS-модулях + `matchMedia` в `js/11-compat.js` (smooth→auto scroll).

| № | Сценарий | Ожидание |
|---|---|---|
| RM-1 | Включить «Уменьшить движение» в iOS / Android; открыть онбординг, home, чат, Таро | Метеоры/мерцание/орбиты/параксис не анимируются или сведены к минимуму |
| RM-2 | Отправить сообщение, открыть/закрыть sheet, тянуть карту | Переходы мгновенные/короткие, без крупных смещений |
| RM-3 | Прокрутка к результату compat/расклада | Scroll «auto» вместо «smooth» |
| RM-4 | Все функциональные действия доступны при reduced-motion | Ничто не «живёт» только в анимации |

## 8. Дополнительные чеки

| № | Сценарий | Ожидание |
|---|---|---|
| D-1 | iOS Dynamic Type max / Android font scale 1.3x: чат, профиль, платёж | Текст растёт, layout не обрезает смысл (WCAG 1.4.4) |
| D-2 | Browser zoom 200% (если доступен в WebView) | Reflow без двойного скролла (WCAG 1.4.10) |
| D-3 | RU ↔ EN переключение: имена aria-label, live-регионы | Локализуются вместе с UI |
| D-4 | `lang` документа | Меняется при переключении языка (`documentElement.lang`) |
| D-5 | Ландшафт + открытая клавиатура + VoiceOver одновременно (стресс) | Нет блокирующих зависаний фокуса |

## Pre-pass находки (2026-09-05, статический анализ кода)

| ID | Приоритет | Находка | Evidence | Действие |
|---|---|---|---|---|
| A-1 | **major** → **исправлено (2026-09-05)** | Токен `--text-faint` / `--color-text-subtle` (#6f6890) давал 3.36–3.78:1 — ниже AA 4.5:1 — на мелком смысловом тексте и интерактиве (`.intro-skip`, `.tc-meta`, `.dock-role`, `.sess-prev`, placeholder'ы `ipt`). **Фикс:** `--color-text-subtle` → `#948cb2` в `00-tokens.css` (корневой фикс: все 61 использования идут через `var(--text-faint)` → `var(--color-text-subtle)`, literal был один). Замер: 5.50–6.20:1 на всех фонах (AA pass), включая `.sec-hint` с `opacity: .9` (4.70:1). Иерархия сохранена: subtle 5.5–6.2 < muted 7.15 < secondary 12.3. Hover-инварианты (`--text-faint` → `--text-dim` при hover) не нарушены — новый subtle всё ещё темнее muted. Placeholder'ы прошли AA автоматически — исключение не потребовалось. | Расчёт WCAG-контрастов по `00-tokens.css` (до/после); использования: `css/00-tokens.css:27,97`, `css/01-sky-shell.css:129`, `css/03-profile.css:10,129,251`, `css/05-agents.css:30,60,61`, `css/06-composer-chat.css:31,171,180,192`, `css/08-day-memory.css:74,93,96,117`, `css/09-chart-panels.css:54,57`, `css/10-tarot-carousel.css:27,99,138,161`, `css/11-misc.css:60`, `css/12-compat.css:58`, `css/14-widgets.css` (×12), `css/15-ritual-redesign.css` (×19), `css/16-visual-qa.css:359,385`; inline в `js/07-chat.js:627`, `js/08-widgets.js:7,29,30`, `js/09-tarot.js:362`, `js/10-chart.js:152,205,208`, `js/12-misc.js:242,580,685,692,817,826` | ~~Задача Frontend~~ Выполнено в BUS-115; перепроверка на staging в ручном прогоне (раздел 4) |
| A-2 | minor (verify) | Приложение dark-only: `data-theme="dark"` захардкожен, `setHeaderColor('#08070f')`; светлой темы нет. Риск: при светлой системной теме Telegram-хедер/клавиатура могут рассинхронизироваться с тёмным контентом. | `index.html:2`, `js/05-app.js:26` | Проверить в прогоне (SA/D-чеки на светлой системной теме); при подтверждении — решение: тема Telegram-хедера или осознанное исключение |
| A-3 | major → **закрыто (патч 509d588, ревью APPROVE, staging-перепрогон 2026-09-05)** | Фокус-менеджмент `te-sheet` частично реализован: открытие → фокус на первый `.te-chip`/`.te-close`, закрытие → возврат на триггер, Esc-закрытие. Отсутствовал фокус-trap при открытом sheet: Tab уводил фокус за пределы `aria-modal="true"` диалога. | `js/07-chat.js:425,652-681`; smoke `scripts/bus133_modal_focus_smoke.mjs` 20/20 | **Закрыто:** `app.activeDialog()` покрывает app-modal И открытый te-sheet; `app.trapTabKey()` циклит Tab/Shift+Tab внутри активного диалога; Esc закрывает верхний диалог. Wiring: `js/13-events.js:15-38`. Verify K-3/K-4/V-7/T-3 на устройстве остаётся. |
| A-4 | **снято в коде (2026-09-05, verify на устройстве)** | Кнопочные эквиваленты всем жестам существуют: свайп между экранами → нижняя навигация `renderNav` (кнопки с `aria-label`+`aria-current`, `05-app.js:321-325`); Таро-карты — не свайп-карусель, а `<button>` с `aria-label`, `aria-pressed`, `data-act="flip"` (`07-chat.js:507-524`); выбор схем — кнопка `pick-open` (`07-chat.js:472`); вкладки проводников — `role="tablist"` кнопки (`07-chat.js:393-397`); закрытие sheet — `.te-close` + Esc + BackButton. | `js/14-gestures.js`, `js/05-app.js:314-326`, `js/07-chat.js:393-397,472-490,507-524` | На устройстве подтвердить только K-7 (фокусируемость карт с внешней клавиатуры); в задачу Frontend не выносить |
| A-5 | major → **закрыто (патч 509d588, ревью APPROVE, staging-перепрогон 2026-09-05)** | Все модальные окна через `showModal` (16 вызовов) рендерились без `role="dialog"`, `aria-modal="true"` и фокус-менеджмента: фокус оставался на триггере под overlay, SR анонсировал окно как обычный div, Tab уводил под оверлей. Затрагивал критические флоу: `confirmAction` (удаление аккаунта/чата), Центр приватности, история чтений, платёжные заказы, смена пола/языка. | `js/12-misc.js:857-908` (единая точка фикса); smoke `scripts/bus133_modal_focus_smoke.mjs` 20/20 | **Исправлено в патче e515b50d (коммит 509d588):** `role="dialog"` + `aria-modal="true"` + `tabindex="-1"` на `.modal`; `aria-labelledby` на найденный заголовок; фокус на первый интерактивный элемент после appendChild; возврат фокуса на триггер в `closeModal`. Ревью-замечание minor про каскадные confirm (trigger читается после `old.remove()`) **учтено в коммите** — trigger читается до remove. Остаток: см. A-7 про размер `.m-close`. |
| A-6 | minor → **закрыто (патч 509d588, staging-перепрогон 2026-09-05)** | Кнопка закрытия модала `.m-close` «✕» без `aria-label` в 11 из 16 разметок (5 имеют label): VoiceOver/TalkBack озвучивают «✕»/«кнопка» вместо «Закрыть». | Без label: `js/07-chat.js:234`, `js/09-tarot.js:92,131,149`, `js/12-misc.js:330,339,352,375,579,615,877`; эталоны с label: `12-misc.js:468,744,769,801`, `17-payments.js:286` | **Закрыто:** все 16 `.m-close` имеют `aria-label` через единый ключ `profileT('closeAria')` / `payT('closeAria')` (ru/en); попутно исправлен неверный label «История заказов» на кнопке закрытия заказов (`17-payments.js:286`). |
| A-7 | major → **закрыто (патч 509d588+R-1/A-7 хвост, 2026-09-05, verify на устройстве)** | Кнопка закрытия модала `.m-close` (16 мест) не имеет padding'а и min-размера: font-size 18px, фон прозрачный, реальная тап-цель ≈ 22×25px — ниже минимума WCAG 2.5.8 (24×24), не говоря о конвенции 44×44. Риск — промах при закрытии модала, критично для confirm-модалов (удаление аккаунта). | `css/03-profile.css:360` (`.modal .m-close`), `css/10-tarot-carousel.css:134` | **Закрыто:** `.modal .m-close` получил `min-width/min-height: 44px` + flex-центрирование глифа + отрицательный margin (-8px/-12px) — хит-зона 44×44, визуальный размер «✕» не изменился, float-раскладка заголовка сохранена. Примечание: `css/10-tarot-carousel.css:134` — отдельный селектор `.te-close` (sheet), не в скоупе BUS-133. |

Позитивный pre-pass baseline (не требует действий): landmarks header/main/nav с aria-label (`05-app.js:264-278`), 84 aria-label / 54 aria-hidden / 11 aria-live / 16 role="status" / 3 role="tablist" / 1 aria-modal, `role="log"` на истории чата, форма-поля обёрнуты в `<label for>`, `documentElement.lang` обновляется при смене языка, touch-target 44px как системное правило, фокус-токены `--focus-ring`/`--focus-outline` на уровне дизайн-системы, reduced-motion покрыт в CSS и JS, безопасные зоны применяются в 11 CSS-модулях.

## Протокол прогона

1. Скопировать этот файл в `docs/RELEASE/ACCESSIBILITY_RUN_<дата>.md` (или заполнить копию в issue).
2. Прогнать разделы 1–8 на каждом устройстве; результат ячейки: `OK` / `FAIL: <описание + severity>` / `N/A: <почему>`.
3. Каждому FAIL присвоить ID `R-<n>` с приоритетом blocker/major/minor и скриншотом/записью.
4. blocker/major → отдельные задачи Frontend Engineer (зона `miniapp/`, ревьюер UX/UI); minor → таблица исключений ниже.
5. После фиксов — повторный прогон только затронутых сценариев на staging.
6. Гейт закрывается при: 0 blocker, 0 major (открытых), все minor внесены в таблицу исключений с обоснованием.

## Статический анализ разделов 5-7 (2026-09-05, до device-прогона)

**Раздел 5 — touch targets (WCAG 2.5.8):** скан `css/*.css` по интерактивным элементам.

| Элемент | Размер | Вердикт |
|---|---|---|
| `.btn` (padding 12px 16px, font 14px) | ≈44px высота | PASS (конвенция 44px) |
| `.nav-btn` (min-height 52px, 50px @≤380px) | 50-52px | PASS |
| `.tchip` / `.chip` (padding 6px 12px, font 12px) | ≈29-30px | выше 2.5.8 минимум (24px), ниже 44px-конвенции → minor: интервал между соседними чипами (gap 6px) недостаточен для компенсации |
| `.pay-period-toggle .btn` (min-height 31px) | 31px | minor (аналогично чипам) |
| `.pay-alert .btn` (min-height 34px) | 34px | minor (аналогично чипам) |
| `.m-close` | 44×44px хит-зона (margin -8/-12) | **PASS → A-7 закрыт (2026-09-05)** — мин-размер в `.modal .m-close`, глиф визуально не изменён |

**Раздел 7 — reduced-motion:** PASS статически. Глобальная гигиена `*,*::before,*::after { animation-duration:.001ms; transition-duration:.001ms }` (`11-misc.css:72-77`); ~30 точечных блоков в 11 модулях (home-bg, atmosphere, payments, premium-shell, tarot-carousel, ritual-redesign ×14, visual-qa, pixel-*, misc); `scrollIntoView` с matchMedia-проверкой (`11-compat.js:24`); модальные анимации отключены (`15-ritual-redesign.css:2405`). Остаток для device-прогона: RM-1 (метеоры/параксис в реальном WebView), RM-4.

**Раздел 6 — safe-area:** PASS статически. `viewport-fit=cover` (`index.html:5`); `env(safe-area-inset-bottom)` на всех нижних панелях (composer, app-nav, te-sheet, sheets, toast, tarot-carousel, premium-shell — 26 вхождений в 11 модулях); `env(safe-area-inset-top)` через `max()` на хедерах (`18-pixel-precision.css:42`, `15-ritual-redesign.css:67,1627`). Device-прогон (SA-1..SA-5) остаётся.

**Результат: 1 новый major (A-7), 3 minor (tchip/chip, pay-toggle, pay-alert). Minor идут в таблицу исключений после device-прогона.**

## Staging-прогон (2026-09-05, headlessaxe — частичный, до device-прогона)

**Условия:** staging-r1 (`https://localhost:3443`, self-signed), мобильный viewport 390×844 @3x, `isMobile+hasTouch`, reduced-motion, RU. Средство: `scripts/axe_staging_shell.mjs` (axe-core 4.13, wcag2a+wcag2aa+best-practice, `bypassCSP`) + точечный контраст-скрипт. Артефакты: `artifacts/axe-staging-shell.json`, `artifacts/axe-staging-shell.png`. Staging подтверждён свежим: билд содержит фикс A-1 (`#948cb2` в live CSS).

**Ограничение:** аутентифицированные экраны (home/chat/profile/payment) на staging недоступны без подписанного Telegram `initData` — `DEV_MODE=0`, QA-бэкдор `dev_user` отключён (fail-closed, корректно). Поэтому прогоном покрыт только shell + экран auth-required; полный прогон разделов 1–8 — на реальных устройствах (Telegram WebView).

**Перепрогон после патча модалей (2026-09-05, коммит 509d588):** те же условия; violations — 1 (`page-has-heading-one` = R-1, не приземлился), incomplete — те же 8 (разобраны в R-2), passes 27. Регрессий от патча A-3/A-5/A-6 на покрытой области нет. Smoke фокус-менеджмента: `scripts/bus133_modal_focus_smoke.mjs` — 20/20.

| Результат | Детали |
|---|---|
| axe violations | 1: `page-has-heading-one` (moderate) — R-1 ниже |
| axe incomplete | 8× `color-contrast` — разобраны вручную (все PASS/декоративные, R-2) |
| axe passes | 27 |

| ID | Приоритет | Находка | Evidence | Действие |
|---|---|---|---|---|
| R-1 | minor | Экран auth-required (вне Telegram) и компонент `softEmpty` (11 использований: empty-состояния истории/чартов/таро, `deleteAccountDone`) рендерят заголовок в `div` — страница без h1 (axe `page-has-heading-one`); SR-структура заголовков плоская. | `js/05-app.js:110`, `js/12-misc.js:47` (шаблон `app.softEmpty`), `js/12-misc.js:519` | Задача Frontend: `soft-empty__title` → `<h1>` в шаблоне `app.softEmpty` (12-misc.js:47) и в renderAuthRequired (05-app.js:110) — один патч закрывает все 12 мест; CSS не меняется. Вместе с A-5/A-6 патчем модалей. |
| R-2 | — (не дефект) | Все 8 axe `color-contrast` incomplete разобраны вычислением: `.soft-empty__title` 18.58:1, `.soft-empty__copy` 12.85:1, `.user-name` 11.55:1, `.brand-title` 18.58:1 — PASS; `.btn.btn-primary` — axe не видит градиент, фактически текст #271f38 на шампань-градиенте #ffe9b4→#eabf68 = 13.12:1 (стоп-ближе к фону) и 9.07:1 (тёмный стоп) — PASS; `.avatar`, `.soft-empty__orb` — декоративные `aria-hidden`. | Расчёт в прогоне 2026-09-05; `css/15-ritual-redesign.css:339`, `css/03-profile.css:256-259`, токены `00-tokens.css:21-22` | Действий нет; задокументировано как обоснование игнорирования incomplete |

**Статус:** частичный staging-прогон (shell) — 0 blocker, 0 major на покрытой области; полный device-прогон (разделы 1–8) остаётся условием закрытия гейта P2-002.

### Таблица исключений (minor, принято осознанно)

| ID | Сценарий | Исключение | Обоснование | Дата |
|---|---|---|---|---|
| _(заполняется по ходу прогона)_ | | | | |
