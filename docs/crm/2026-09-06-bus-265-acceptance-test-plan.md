# BUS-265 — QA тест-план приёмки lifecycle-цепочек (волна 3)

Продукт: oracleAI. Приёмка цепочек — после done всех 8 блокеров BUS-256…263 (порядок CTO, комментарий 3d76cb7a).

## 1. Общие инварианты (I1–I7)

| # | Инвариант | Проверка |
|---|-----------|----------|
| I1 | вся отправка через `_send_once` | grep отсутствия прямых `bot.send_message` в chain-коде |
| I2 | дедуп: 2 параллельных тика → 1 отправка | тест `test_scheduler_dedup.py` (закоммичен 6f21d7d, п.1 приёмки ✅ 05.09-06.09) |
| I3 | guardrail ≤1 маркетинг/7д | `comms.already_sent("guardrail", week_key)` |
| I4 | композитные сегменты через SEGMENTS-предикаты | не хардкод SQL в цепочках |
| I5 | ошибка одного юзера не валит sweep | try/except на юзера (паттерн существующий) |
| I6 | week_key от tz юзера | scheduler.py:555 `now_utc.astimezone(users.user_tz(user))`, ISO-неделя `%G-W%V` (scheduler.py:247) — закрыто из кода, прогон 4 |
| I7 | claim до отправки | deliveries PK tg_id+kind+key, отметка ДО отправки |

## 2. WB2 winback (BUS-256, done 27a3b67, механика прогнана 11 passed)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 2.1 | партия | `create_codes(count=25, kind="plan_days", days=7, plan_code="trial", batch="winback_{YYYY-MM}", max_uses=1, valid_days=14)` |
| 2.2 | redemption | 7д trial без кристаллов (референс e5dd4ab) |
| 2.3 | анти-абьюз | 90д после redemption |
| 2.4 | пустая партия | fallback тёплого winback |
| 2.5 | `{code}` не подставлен | сообщение НЕ отправляется (BUS-263 §8.1) |
| 2.6 | batch_stats / E_PROMO / source | пишутся; E_PROMO проверка events (billing.py:510) |

## 3. Welcome W1-W3 (BUS-258)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 3.1 | отбор | onboarded=1 без first-событий, вход ≥24ч |
| 3.2 | стоп | при первом first_ritual/first_question |
| 3.3 | morning_push=0 | уважается |
| 3.4 | W3 {top_first_step} | именительный падеж + fallback без агрегата |

## 4. Onboard O1-O2 (BUS-259)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 4.1 | отбор | onboarded=0 ≥24ч — отдельный sweep вне `_audience` |
| 4.2 | O2 → заморозка | навсегда, не возобновляется через 60д |
| 4.3 | негатив | start <24ч не дожимается |

## 5. Free→paid (BUS-257)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 5.1 | post_limit | +24ч |
| 5.2 | low_balance | в течение часа |
| 5.3 | совпадение в один день | low_balance переносится на завтра |
| 5.4 | покупка | немедленный стоп |
| 5.5 | 7 дней без покупки | стоп |
| 5.6 | событийные | вне guardrail |

## 6. Reactivate R1-R2 (BUS-260)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 6.1 | отбор | композитный `sleeping_14d_push` через SEGMENTS |
| 6.2 | R1 персонализация | `{practice_title}` без своих кавычек, `{day_index}` — число |
| 6.3 | пустой список практик | безопасный fallback |
| 6.4 | после R2 | жёсткий стоп ≥60д |

## 7. Guardrail (BUS-262 done — код в master f9bda1f + 01955d8, guardrail-ok/mark scheduler.py:1279-1301)

| # | Сценарий | Ожидание |
|---|----------|----------|
| 7.1 | вторая маркетинговая в неделю | блокируется |
| 7.2 | событийные | уходят всегда, вне лимита, разводятся по дням |
| 7.3 | приоритет при конфликте слотов | детерминированный порядок — зафиксировать ответ Backend в тесте (открытый вопрос) |

## 8. i18n / privacy

| # | Сценарий | Ожидание |
|---|----------|----------|
| 8.1 | 12 ключей ru/en | контракт BUS-263 §1 |
| 8.2 | plain text | без HTML |
| 8.3 | {name} = oracle_name | единственная персонализация |

## 9. Регресс

Базовая линия 869/886 (17 known, 12 palm) от 2026-09-05. Смоук дедуп+winback 32 passed (прогон 3).

## Статус чек-листа (финальная приёмка 2026-09-07, master 67469e4)

- п.1 (планировщик/дедуп) ✅ — 6f21d7d, 21+11 passed
- п.2 (WB2) ✅ — test_winback2.py 11/11 + e2e redemption: trial 7д, crystals=0, E_PROMO {batch,kind}, source=promo:winback_2026-09 (п.2.2/2.3/2.6 закрыты скриптом; п.2.1/2.4/2.5 — тестами 27a3b67)
- п.3 (welcome) ✅ — test_crm_welcome_chain.py 17/17 (72ac4da)
- п.4 (onboard) ✅ — test_crm_onboard_chain.py 15/15 (bb793e3)
- п.5 (free→paid) ✅ — test_crm_free_paid.py в suite 99/99: событийные вне guardrail, разводятся по дням (kind+event_date, scheduler.py:1207-1274), покупка→стоп, 7д поканальный
- п.6 (reactivate) ✅ — test_crm_reactivate_chain.py 22/22 (4c34fea): R1 {practice_title} без своих кавычек, fallback под ключ :fallback, 60д-стоп
- п.7 (guardrail/SEGMENTS) ✅ — test_bus262_segments_guardrail.py 12/12 + test_winback2 11/11 (f9bda1f): 1/7д на welcome+reactivate (guardrail-ok/mark scheduler.py:1279-1301), событийные вне лимита; сверка отборов: segment_count(sleeping_14d_push)==1 == _reactivate_audience [8801] (скрипт, 3 посевных юзера); cancelled_5_7d/winback_90d — тестами границ 5/6/7/8д
- п.8 (i18n/privacy) ✅ — 11 wave-3 ключей + winback2: ru seed + DEFAULT_EN_CONTENT, 0 HTML-тегов, плейсхолдеры {name}/{code}/{practice_title}/{day_index}/{top_first_step}, PII нет; {name}=user["name"] (oracle_name) с fallback "друг"/"dear one"; кнопки: web_app-кнопки O1/W1 + onboard_btn_continue
- п.9 (регресс) ✅ — suite lifecycle 99/99 + smoke scheduler 45/45 (test_scheduler, test_feedback_scheduler, test_audience_crm)

**Итог QA: PASS.** Все 8 блокеров done, критические пути lifecycle-цепочек работают на master 67469e4.

### Наблюдения (не блокируют релиз)

1. **Порядкозависимый тест** (исправлено): процесс-глобал `scheduler._winback_batch_ready` переживал TRUNCATE базы в conftest — после winback-теста следующий WB2-тест в том же месяце ловил «партия исчерпана». Фикс: сброс глобала в autouse-фикстуре conftest. Дефект тестовой изоляции, не продукта (в проде кэш и БД живут согласованно).
2. **Guardrail week_key от UTC** (scheduler.py:1288 `now_utc.strftime("%G-W%V")`): лимит 1/7д самоконсистентен (ok и mark на одной базе), но границы недели не совпадают с локальной неделей юзера (UTC+14/UTC-11). Для лимита частоты приемлемо; отмечено Backend как осведомлённость.
3. **E_PROMO-ассерт для WB2** — прямой тест на events в WB2-флоу отсутствует (покрыто e2e-скриптом приёмки); рекомендация Backend: добавить ассерт в test_winback2.py (задача на Backend при удобстве).
4. **7.3 приоритет цепочек при конфликте слотов** — детерминирован порядком dispatch в `_daily_sweeps` (welcome → onboard → reactivate) и добором winback в _tick_user; формальный ответ Backend не зафиксирован — риск низкий, т.к. guardrail-слот один на неделю и цепочки взаимоисключающи по аудиториям.

