-- BUS-258: baseline-снимок KPI welcome-цепочки (crm-frame §6 — обязателен ДО запуска).
-- Запуск: docker exec -i infra-postgres-1 psql -U oracle -d oracle \
--   < infra/staging/monitoring/snapshots/bus258-welcome-baseline/run.sh 2>/dev/null
-- Формат: COPY SQL для psql; результат сохранить в kpi-baseline-<дата>.txt рядом.
-- Сравнение после запуска цепочки: та же выборка, когорты до/после даты запуска.

-- 1. Кандидаты welcome-сегмента на текущий момент: onboarded, без first-ценности,
--    onboard_done >= 24ч назад (проверка размера сегмента — сколько получит цепочку).
SELECT 'segment_size_now' AS metric, COUNT(*) AS value
FROM users u
WHERE u.onboarded = 1 AND u.status = 'active' AND u.morning_push = 1
  AND NOT EXISTS (SELECT 1 FROM events e
        WHERE e.tg_id = u.tg_id AND e.name IN ('first_ritual','first_question'))
  AND EXISTS (SELECT 1 FROM events e
        WHERE e.tg_id = u.tg_id AND e.name = 'onboard_done'
        AND e.created_at <= (now() - interval '24 hours')::text);

-- 2. Медиана time-to-first-value: дни от последнего onboard_done до первого
--    first-события, по юзерам с обоими событиями (KPI §1).
WITH od AS (
  SELECT tg_id, MAX(created_at) AS done_at FROM events
  WHERE name = 'onboard_done' GROUP BY tg_id),
fv AS (
  SELECT tg_id, MIN(created_at) AS first_at FROM events
  WHERE name IN ('first_ritual','first_question') GROUP BY tg_id),
j AS (
  SELECT EXTRACT(EPOCH FROM (fv.first_at::timestamptz - od.done_at::timestamptz)) / 86400.0 AS days,
         fv.first_at
  FROM od JOIN fv USING (tg_id)
  WHERE fv.first_at >= od.done_at)
SELECT 'ttfv_median_days' AS metric,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY days) AS value,
       COUNT(*) AS n
FROM j
WHERE first_at >= (now() - interval '30 days')::text;

-- 3. first_value rate по суточным когортам онбординга (self-control §1:
--    сравнение когорт до/после запуска цепочки).
WITH od AS (
  SELECT tg_id, MAX(created_at)::date AS done_day FROM events
  WHERE name = 'onboard_done' GROUP BY tg_id),
fv AS (
  SELECT tg_id FROM events
  WHERE name IN ('first_ritual','first_question') GROUP BY tg_id)
SELECT 'first_value_rate_by_cohort' AS metric,
       od.done_day AS cohort_day,
       COUNT(*) AS onboarded_total,
       COUNT(fv.tg_id) AS with_first_value,
       ROUND(COUNT(fv.tg_id)::numeric * 100 / GREATEST(COUNT(*), 1), 1) AS pct
FROM od LEFT JOIN fv USING (tg_id)
GROUP BY od.done_day
ORDER BY od.done_day DESC
LIMIT 14;
