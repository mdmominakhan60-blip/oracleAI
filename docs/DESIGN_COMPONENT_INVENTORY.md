# OracleAI — design component inventory and visual QA matrix

Этот inventory — release contract для Mini App. Он фиксирует не только внешний вид, но и состояния, safe area, focus, copy overflow и recovery behavior. Новая поверхность должна ссылаться на существующий компонент или добавлять сюда новый variant до merge.

## Shared components

| Component | Source | Required states | Primary action | Accessibility contract |
|---|---|---|---|---|
| Brand/header | `05-app.js`, `02-skeleton.css` | default, compact, long name | one context/navigation action | brand image decorative; icon buttons have aria-label; no header overflow at 360 px. |
| Bottom dock | `05-app.js`, `15-ritual-redesign.css` | default, active, pressed, disabled | one active section | active state is not color-only; tap target >= 44 px; respects safe-area bottom. |
| Surface/card | feature JS/CSS modules | default, featured, loading, empty, error | max one primary CTA | heading hierarchy, readable contrast, no decorative frame wall. |
| Button | token/component styles | primary, ghost, secondary, loading, disabled | verb + expected outcome | focus-visible outline, disabled prevents duplicate request, label survives RU/EN expansion. |
| Tool chip | `03-data.js`, `07-chat.js`, toolbar sheet CSS | default, focus, active, unavailable | launch one current-agent action | preflight says data/duration/result; no role mixing; action remains data-act. |
| Chat composer | `07-chat.js`, composer CSS | empty, typing, sending, error, keyboard-open | send one message | textarea keeps draft after error; Enter behavior is explicit; visualViewport safe area. |
| Session list | `07-chat.js` | empty, active, max-five, delete/recovery | continue or start new | title is generic category by default; deletion has clear label; no hidden memory recap. |
| Tool sheet | `07-chat.js`, `13-toolbar-sheet.css` | closed, opening, open, closing | close or launch tool | modal label, focus/escape path, reduced motion, no second toolbar duplicate. |
| Age gate | — | — | — | Удалён (GAUNTLET v2): никакого оверлея 16+ не существует. |
| Memory control | profile/settings modules | on, off, saving, error | enable/disable/delete | explains what changes server-side; memory-off never relies on client hiding. |
| Tarot widget | `07-chat.js`, `09-tarot.js` | picker, drawing, partial reveal, complete, error | choose spread/draw/interpret | progress is textual and aria-live; no exact future/mind-reading promise. |
| Chart widget | `10-chart.js` | loading, date-only, full-time, empty, error | read one evidence block | date-only never shows ASC/houses; facts separated from interpretation. |
| Compatibility widget | `11-compat.js` | consent, input, loading, result, delete/error | choose relationship context | partner data consent/deletion is explicit; score is not an outcome verdict. |
| Safety banner | safety runtime/CSS | calm support, crisis, retry | contact support/emergency help | direct language, no mystical continuation loop, readable at large text. |

## Viewport and language matrix

| Matrix row | Required checks |
|---|---|
| 360 × 800 | no horizontal overflow; header/session title wraps; composer and primary CTA visible above safe area. |
| 390 × 844 | reference baseline for home/chat/tool sheet/profile/Tarot/chart/compatibility. |
| 430 × 932 | no excessive empty space; cards do not become a wall of decoration; long RU text remains readable. |
| RU | long safety copy, feminine/neutral language, tool metadata and session labels. |
| EN | independent copy, no literal overflow, terms/privacy links and agent names remain understandable. |
| Large text / zoom | headings/buttons expand without clipping or losing action labels. |
| Keyboard open | composer remains above keyboard, draft remains, sheet does not trap focus behind overlay. |
| Reduced motion | no essential information depends on animation; sheet/tarot still works without transitions. |

## Screenshot baseline set

Staging screenshot baselines should cover `home-empty`, `home-complete`, `chat-empty`, `chat-tools`, `chat-sending`, `chat-error`, `profile-memory-off`, `tarot-picker`, `tarot-reveal`, `chart-date-only`, `chart-full`, `compat-input`, `compat-result`, and `safety-support`. Each baseline records viewport, locale, theme, seed/test account state and commit. Personal data must be synthetic; do not save screenshots with Telegram IDs, diary text or birth data from real users.

## Review checklist

Before merging a visual change, confirm one primary action, one safe exit, visible loading/error behavior, server-owned state, keyboard/safe-area behavior, focus-visible state, RU/EN expansion, reduced-motion behavior, and cache-busting. A visual diff is an investigation signal, not an automatic approval or rejection; content and accessibility regressions block release even when pixels look similar.
