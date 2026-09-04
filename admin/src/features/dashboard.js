import { $, date, esc, num, pct, usd, get, state, actions, table, fail, setViewVisibility } from '../core/runtime.js';
import { charts } from '../components/charts.js';

export class DashboardFeature {
  constructor() {
    actions.navigate = (view) => setViewVisibility(view);
  }

  async load() {
    const path = state.demo ? `/api/admin/dashboard/demo?days=${state.period}` : `/api/admin/dashboard?days=${state.period}`;
    const [dashboard, health] = await Promise.all([get(path), get('/api/admin/payment-health')]);
    const overview = dashboard.overview;
    $('demo-banner').classList.toggle('hidden', !state.demo);
    this.renderPaymentHealth(health);
    $('kpi').innerHTML = [
      ...(state.demo ? [{ label: 'Проект работает', value: '17 дней', sub: 'демо-срез · не production', cls: 'accent' }] : []),
      { label: 'Клиентки', value: num(overview.users_total), sub: `+${num(overview.users_today)} за сутки`, cls: '' },
      { label: 'Активны за 30 дн.', value: num(overview.mau), sub: `${num(overview.dau)} сегодня`, cls: '' },
      { label: 'Живые подписки', value: num(overview.subs_active), sub: `онбординг: ${num(overview.onboarded)}`, cls: 'good' },
      { label: 'Stars всего', value: num(overview.stars_total), sub: `${usd(overview.stars_total)} · ${num(overview.payers)} плательщиц`, cls: 'accent' },
      { label: `Stars за ${state.period} дн.`, value: num(overview.stars_30d), sub: usd(overview.stars_30d), cls: 'accent' },
      { label: 'Вопросов за 7 дн.', value: num(overview.questions_7d), sub: `${num(overview.questions_today)} сегодня`, cls: '' },
      { label: 'Раскладов', value: num(overview.readings_total), sub: `${num(overview.readings_7d)} за неделю`, cls: '' },
      { label: 'Кристаллы в обороте', value: num(overview.crystals_outstanding), sub: 'не потрачено клиентками', cls: '' },
    ].map((item) => `<div class="kpi ${item.cls}"><div class="kpi-label">${esc(item.label)}</div><div class="kpi-value">${item.value}</div><div class="kpi-sub">${esc(item.sub)}</div></div>`).join('');

    const days = dashboard.timeseries.map((item) => item.day);
    charts.line($('chart-activity'), days, [
      { values: dashboard.timeseries.map((item) => item.active), color: '#e8c56b', fill: true },
      { values: dashboard.timeseries.map((item) => item.questions), color: '#7fb4e8' },
      { values: dashboard.timeseries.map((item) => item.users), color: '#7fd8a8' },
    ]);
    charts.bar($('chart-revenue'), days, dashboard.timeseries.map((item) => item.stars));

    const monetization = dashboard.monetization || {};
    $('kpi-monetization').innerHTML = [
      { label: `ARPPU за ${monetization.days ?? state.period} дн.`, value: `${num(monetization.paid_arppu_stars)} ⭐`, sub: `${num(monetization.paid_payers)} плательщиц`, cls: 'accent' },
      { label: 'Повторных оплат', value: pct(monetization.repeat_payer_rate), sub: `${num(monetization.repeat_payers)} человек`, cls: '' },
      { label: 'Возвраты', value: pct(monetization.refund_rate), sub: `${num(monetization.refund_orders)} заказов`, cls: monetization.refund_rate > 5 ? 'bad' : 'good' },
      { label: 'Активаций купонов', value: num(dashboard.promo_batches.reduce((sum, batch) => sum + batch.used, 0)), sub: `в ${num(dashboard.promo_batches.length)} партиях`, cls: '' },
    ].map((item) => `<div class="kpi ${item.cls}"><div class="kpi-label">${esc(item.label)}</div><div class="kpi-value">${item.value}</div><div class="kpi-sub">${esc(item.sub)}</div></div>`).join('');

    const revenue = dashboard.revenue;
    $('revenue-facts').innerHTML = `<span>оплат: <b>${num(revenue.orders_paid)}</b></span><span>за период: <b>${num(revenue.orders_period)}</b></span><span>средний чек: <b>${num(revenue.orders_paid ? Math.round(revenue.stars_total / revenue.orders_paid) : 0)} ⭐</b></span><span>возвраты: <b>${num(revenue.refunds)}</b></span>`;
    $('funnel').innerHTML = dashboard.funnel.map((step, index) => {
      const previous = index ? dashboard.funnel[index - 1].value : step.value;
      const drop = previous ? Math.round((1 - step.value / previous) * 100) : 0;
      return `<div class="funnel-step"><div class="funnel-top"><span>${esc(step.step)}</span><span>${num(step.value)} · ${pct(step.of_total)} ${index && drop > 0 ? `<span class="funnel-drop">−${drop}%</span>` : ''}</span></div><div class="funnel-bar"><div class="funnel-fill" style="width:${Math.max(1, step.of_total)}%"></div></div></div>`;
    }).join('');
    $('retention').innerHTML = table([
      { title: 'Когорта', render: (row) => date(row.cohort) }, { title: 'Людей', num: true, render: (row) => num(row.size) },
      { title: 'D1', num: true, render: (row) => pct(row.d1) }, { title: 'D3', num: true, render: (row) => pct(row.d3) },
      { title: 'D7', num: true, render: (row) => pct(row.d7) }, { title: 'D14', num: true, render: (row) => pct(row.d14) },
      { title: 'D30', num: true, render: (row) => pct(row.d30) },
    ], dashboard.retention, { empty: 'Когорт пока нет — нужны первые недели' });
    $('top-products').innerHTML = table([
      { title: 'Товар', render: (row) => esc(row.title || row.sku) }, { title: 'Продаж', num: true, render: (row) => num(row.sales) }, { title: 'Stars', num: true, render: (row) => num(row.stars) },
    ], dashboard.top_products, { empty: 'Продаж пока нет' });
    $('sources').innerHTML = table([
      { title: 'Канал', render: (row) => esc(row.source) }, { title: 'Пришло', num: true, render: (row) => num(row.users) }, { title: 'Платят', num: true, render: (row) => num(row.payers) }, { title: 'Stars', num: true, render: (row) => num(row.stars) },
    ], dashboard.sources, { empty: 'Нет данных о каналах' });
    $('referrers').innerHTML = table([
      { title: 'Кто', render: (row) => esc(row.name || row.tg_id) }, { title: 'Привела', num: true, render: (row) => num(row.invited) }, { title: '✦', num: true, render: (row) => num(row.bonus) },
    ], dashboard.top_referrers, { empty: 'Приглашений пока нет' });
  }

  renderPaymentHealth(health) {
    const checks = health?.checks || {};
    const reconciliation = checks.reconciliation || {};
    const failures = Object.values(checks.webhook_failures_24h || {}).reduce((sum, value) => sum + (value || 0), 0);
    const anomalies = Object.values(reconciliation).reduce((sum, value) => sum + (value || 0), 0);
    const status = health?.status || 'unknown';
    const statusLabel = { ok: 'OK', degraded: 'DEGRADED', critical: 'CRITICAL', unknown: 'нет snapshot' }[status] || status;
    const statusClass = status === 'ok' ? 'on' : status === 'critical' ? 'bad' : 'warn';
    const providers = Object.entries(health?.providers || {}).map(([name, provider]) => {
      const providerClass = provider.status === 'ok' ? 'on' : provider.status === 'degraded' ? 'warn' : 'off';
      const balance = (provider.balances || []).map((item) => `${esc(item.asset)}: ${esc(item.available)}`).join(', ');
      const dashboard = provider.dashboard_url ? `<a class="health-dashboard-link" href="${esc(provider.dashboard_url)}" target="_blank" rel="noopener noreferrer">кабинет</a>` : '';
      return `<span class="health-provider"><b>${esc(name)}</b><span class="badge ${providerClass}">${esc(provider.status || 'unknown')}</span>${balance ? `<span>${balance}</span>` : ''}${dashboard}</span>`;
    }).join('');
    $('payment-health-updated').textContent = health?.checked_at ? `проверено ${date(health.checked_at, true)}` : 'проверка ещё не запускалась';
    const timeline = checks.webhook_timeline || [];
    const timelineHtml = timeline.length ? `<div class="health-timeline" aria-label="Последние события webhook">${timeline.slice(0, 8).map((item) => `<div class="health-timeline-row"><span class="badge ${item.status === 'failed' ? 'bad' : 'on'}">${item.status === 'failed' ? 'ошибка' : 'получен'}</span><b>${esc(item.provider)}</b><span>${esc(item.event)}</span><time>${date(item.at, true)}</time></div>`).join('')}</div>` : '<div class="muted small">Webhook-событий за последние 24 часа нет.</div>';
    $('payment-health').innerHTML = `<div class="payment-health-summary"><span class="badge ${statusClass}">${esc(statusLabel)}</span><span class="muted small">Проверки выполняются автоматически каждые 10 минут в активном bot process.</span><button id="open-reconciliation" class="btn ghost" type="button">Открыть сверку</button></div><div class="payment-health-grid"><div class="health-stat"><span>Зависшие pending &gt; ${num(health?.stale_pending_threshold_hours || 2)} ч</span><b>${num(checks.pending_orders_stale)}</b></div><div class="health-stat"><span>Ошибки webhook за 24 ч</span><b>${num(failures)}</b></div><div class="health-stat"><span>Ошибки заказов за 24 ч</span><b>${num(checks.failed_orders_24h)}</b></div><div class="health-stat"><span>Аномалии сверки</span><b>${num(anomalies)}</b></div></div><div class="health-provider">Поставщики: ${providers || '<span>не настроены</span>'}</div><div class="health-timeline-title">Последние webhook events</div>${timelineHtml}`;
    $('open-reconciliation')?.addEventListener('click', () => actions.navigate('reconciliation'));
  }
}
