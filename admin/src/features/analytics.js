import {
  $, esc, num, pct, usd, date, get, state, actions, table, bindRows,
  fillSegmentSelect, fail,
} from '../core/runtime.js';
import { segmentLabel } from './users.js';

// BUS-178: аналитический раздел — срезы воронки/retention/revenue + сегменты аудитории.
// Источники — существующие агрегаты /api/admin/dashboard и /api/admin/users.
// Методология и data_quality — по спеке BUS-176 (metrics/reports/BUS-176-owner-analytics-spec.md):
// retention в админке считается по активности (activity fallback, §5.2), воронка —
// по registrations-когорте (§5.3); таргеты §6 — гипотезы, только подсветка, без алертов.

// Общая для аналитических экранов метка качества данных (BUS-176 §4):
// ✓ полные, ~ частичные, ∅ пусто — расшифровка всегда в sr-only, а не
// только в title (axe не считает title именем для голого глифа).
export function setDq(id, { status, note }) {
  const el = $(id);
  if (!el) return;
  const labels = { full: '✓', partial: '~', empty: '∅' };
  const titles = {
    full: 'Данные полные за выбранный период',
    partial: note || 'Данные частичные — смотри методологию',
    empty: 'Данных за период нет',
  };
  // sr-only текст нужен axe: title и aria-label на span без роли axe не
  // считает именем, а голый глиф ✓/~ — non-text content без контраста
  el.dataset.dq = status;
  el.textContent = labels[status] || '?';
  el.title = titles[status] || '';
  el.innerHTML = `${labels[status] || '?'}<span class="sr-only">${titles[status] || ''}</span>`;
}

// BUS-264 R7: названия и подсказки CRM-сценариев волны 3. Ключи = kinds
// из deliveries; подсказка объясняет, что считается «вошло».
const SCENARIO_META = {
  welcome_chain: {
    title: 'Welcome-цепочка',
    hint: 'новые клиентки после знакомства, first-value ещё нет',
    target: 'первая практика / вопрос',
  },
  onboard_nudge: {
    title: 'Дожим онбординга',
    hint: 'начали, но не закончили знакомство',
    target: 'завершение онбординга',
  },
  reactivate: {
    title: 'Реактивация',
    hint: 'спящие 14+ дней',
    target: 'возврат в Mini App',
  },
  winback2: {
    title: 'Winback',
    hint: 'подписка истекла, оффер отправлен',
    target: 'промокод активирован',
  },
  post_limit: {
    title: 'Лимит разборов',
    hint: 'бесплатный лимит достигнут',
    target: 'переход в тариф',
  },
  low_balance: {
    title: 'Мало кристаллов',
    hint: 'баланс на исходе',
    target: 'пополнение',
  },
};

// Подписи R9-гэпов (контракт BUS-264 §4): метрика честно отсутствует,
// показываем причину вместо нуля.
const SCENARIO_GAP_REASONS = {
  'G-1': 'конверсия недоступна: атрибуция push→открытие (событие G-1)',
  'G-2': 'payback недоступен: продления после winback-оффера (событие G-2)',
};

const ACTIVATION_LABELS = {
  first_ritual: 'Первая практика',
  first_question: 'Первый вопрос',
  d1_return: 'Возврат D1',
  d7_return: 'Возврат D7',
};

const MONEY_EVENTS = [
  ['paywall_view', 'Увидели пейволл'],
  ['paywall_choice', 'Выбрали оффер'],
  ['invoice_created', 'Создан счёт'],
  ['paid', 'Оплатили'],
  ['first_paid_action', 'Первая оплата'],
  ['subscription_lifecycle', 'События подписки'],
  ['credit_pack_checkout_started', 'Чекаут кристаллов'],
  ['credit_pack_paid', 'Кристаллы оплачены'],
  ['credit_spent', 'Кристаллы потрачены'],
  ['report_delivered', 'Разбор доставлен'],
  ['refund_completed', 'Возврат завершён'],
];

// Пороги воронки — из §6 спеки BUS-176: Visit→Signup и Signup→Activation.
// Все таргеты — гипотезы до ≥2 недель прод-трафика; подсветка без алертов.
const FUNNEL_TARGETS = {
  'Пришли': null,
  'Прошли знакомство': { green: 25, red: 10 },
  'Задали вопрос': { green: 25, red: 15 },
  'Вернулись на 2-й день': null,
  'Заплатили': { green: 2, red: 1 },
};

// Карточки-сегменты: показываем только те коды, чей размер можно честно
// посчитать из overview без отдельного counts-эндпоинта.
function segmentCards(overview) {
  const total = overview?.users_total ?? 0;
  return [
    ['all', 'Все клиентки', total],
    ['onboarded', 'Прошли знакомство', overview?.onboarded],
    ['not_onboarded', 'Не дошли до конца', Math.max(0, total - (overview?.onboarded ?? 0))],
    ['active_sub', 'С подпиской', overview?.subs_active],
    ['expired', 'Без активной подписки', Math.max(0, total - (overview?.subs_active ?? 0))],
    ['paying', 'Платящие', overview?.payers],
    ['never_paid', 'Ни разу не платили', Math.max(0, total - (overview?.payers ?? 0))],
    ['active_7d', 'Активны за неделю', overview?.wau],
  ];
}

export class AnalyticsFeature {
  constructor() {
    this.q = '';
    this.segment = 'all';
    this.order = 'created_at';
    this.offset = 0;
    this.limit = 50;
    this.searchTimer = null;
    this.bound = false;
  }

  bind() {
    if (this.bound) return;
    this.bound = true;
    $('anx-period').addEventListener('change', (event) => {
      state.period = +event.target.value;
      this.loadMetrics().catch(fail);
    });
    $('anx-q').addEventListener('input', (event) => {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => {
        this.q = event.target.value.trim();
        this.offset = 0;
        this.loadUsers().catch(fail);
      }, 350);
    });
    $('anx-segment').addEventListener('change', (event) => {
      this.segment = event.target.value;
      this.offset = 0;
      this.highlightSegments();
      this.loadUsers().catch(fail);
    });
    $('anx-order').addEventListener('change', (event) => {
      this.order = event.target.value;
      this.loadUsers().catch(fail);
    });
    $('anx-prev').addEventListener('click', () => {
      this.offset = Math.max(0, this.offset - this.limit);
      this.loadUsers().catch(fail);
    });
    $('anx-next').addEventListener('click', () => {
      this.offset += this.limit;
      this.loadUsers().catch(fail);
    });
    $('anx-segments').addEventListener('click', (event) => {
      const card = event.target.closest('[data-segment]');
      if (!card) return;
      this.segment = card.dataset.segment;
      $('anx-segment').value = this.segment;
      this.offset = 0;
      this.highlightSegments();
      this.loadUsers().catch(fail);
    });
  }

  async load() {
    this.bind();
    await Promise.all([this.loadMetrics(), this.loadUsers()]);
  }

  async loadMetrics() {
    const path = state.demo
      ? `/api/admin/dashboard/demo?days=${state.period}`
      : `/api/admin/dashboard?days=${state.period}`;
    const dash = await get(path);
    this.renderActivation(dash.activation);
    this.renderFunnel(dash.funnel);
    this.renderRetention(dash.retention);
    this.renderSources(dash.sources);
    this.renderMoney(dash);
    this.renderSegments(dash.overview);
    this.renderDataQuality(dash);
    this.loadScenarios().catch(() => {});
  }

  // BUS-264 R7: карточки CRM-сценариев из /api/admin/analytics/scenarios.
  // Период — общий селект anx-period, пересчитанный в from/to ISO.
  // R9-гэпы: no_data-карточка показывает причину вместо null-метрик.
  // Анти-reid: rate=null при entered<5 — на месте ставки пишем «мало данных».
  async loadScenarios() {
    // Локальная дата, не toISOString(): UTC-строка до полуночи по МСК даёт
    // «вчера» и сдвигает окно относительно остальной аналитики.
    const iso = (d) => {
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${d.getFullYear()}-${m}-${day}`;
    };
    const to = new Date();
    const from = new Date(to);
    from.setDate(from.getDate() - (state.period - 1));
    try {
      const data = await get(`/api/admin/analytics/scenarios?from=${iso(from)}&to=${iso(to)}`);
      this.renderScenarios(data.scenarios || []);
    } catch (error) {
      setDq('anx-scen-dq', { status: 'empty', note: 'API сценариев недоступен' });
      $('anx-scenarios').innerHTML = '<div class="empty">Нет данных — API сценариев недоступен</div>';
    }
  }

  renderScenarios(scenarios) {
    if (!scenarios.length) {
      setDq('anx-scen-dq', { status: 'empty', note: 'сценарии волны 3 не активны' });
      $('anx-scenarios').innerHTML = '<div class="empty">Цепочки волны 3 за период не срабатывали</div>';
      return;
    }
    setDq('anx-scen-dq', {
      status: scenarios.every((card) => card.data_status === 'ok') ? 'full' : 'partial',
      note: 'часть метрик закрыта R9-гэпами (G-1/G-2) — подписаны на карточках',
    });
    $('anx-scenarios').innerHTML = scenarios.map((card) => {
      const meta = SCENARIO_META[card.key] || { title: card.key, hint: '', target: '' };
      const noData = card.data_status === 'no_data';
      const gap = noData && card.no_data_reason ? SCENARIO_GAP_REASONS[card.no_data_reason] : null;
      // Анти-reid: null-ставка при entered<5 — честная пометка вместо 0%.
      const rateShown = card.conversion_rate == null
        ? '<span class="scen-rate muted">мало данных</span>'
        : `<span class="scen-rate good">${pct(card.conversion_rate * 100)}</span>`;
      const metric = (label, value) => `<span class="scen-metric"><span class="scen-metric-value">${num(value)}</span>${esc(label)}</span>`;
      // stops — всегда объект (контракт §4): forbidden=запрет, segment_exit=выход
      // из сегмента, other=failed/прочее.
      const stops = card.stops
        ? `<span class="scen-stops">стопы: запрет ${num(card.stops.forbidden)} · выход ${num(card.stops.segment_exit)} · прочее ${num(card.stops.other)}</span>`
        : '';
      const body = noData
        ? `<span class="scen-gap">${esc(gap || 'данные недоступны')}</span>
           ${card.entered != null ? metric('вошло', card.entered) : ''}
           ${card.reached != null ? metric('дошло', card.reached) : ''}
           ${card.converted != null ? metric('конверсия', card.converted) : ''}
           ${card.conversion_rate != null ? rateShown : ''}
           ${stops}`
        : `${metric('вошло', card.entered)}
           ${metric('дошло', card.reached)}
           ${metric('конверсия', card.converted)}
           ${rateShown}
           ${stops}`;
      // Карточка — не интерактив: без tabindex/aria-label, текст читается
      // скринридером как есть (aria-label на div без роли ненадёжен).
      return `<div class="scen-card${noData ? ' scen-card-gap' : ''}">
        <span class="scen-title">${esc(meta.title)}</span>
        <span class="scen-hint">${esc(meta.hint)}</span>
        ${body}
        <span class="scen-target">целевое действие: ${esc(meta.target)}</span>
      </div>`;
    }).join('');
  }

  // BUS-176 §4: каждый виджет несёт метку качества данных. Бэкенд пока не
  // отдаёт data_quality в /dashboard — честные пометки считаем на фронте
  // из известных ограничений (спека §7).
  renderDataQuality(dash) {
    const d30Matured = (dash.retention || []).some((row) => (row.d30 ?? 0) > 0);
    setDq('anx-funnel-dq', {
      status: 'partial',
      note: 'по регистрациям окна; visit-сессии — после BUS-144',
    });
    setDq('anx-retention-dq', {
      status: 'partial',
      note: 'по активности; D30 нематюрит у свежих когорт',
    });
    setDq('anx-activation-dq', {
      status: dash.activation?.cohort ? 'full' : 'empty',
      note: dash.activation?.cohort ? null : 'открытий за период нет',
    });
    setDq('anx-sources-dq', { status: (dash.sources || []).length ? 'full' : 'empty' });
    setDq('anx-rev-dq', {
      status: dash.monetization_v2 ? 'full' : 'empty',
      note: dash.monetization_v2 ? 'gross в Stars, не revenue' : null,
    });
    setDq('anx-sku-dq', { status: (dash.monetization_v2?.revenue?.by_sku || []).length ? 'full' : 'empty' });
    setDq('anx-tiers-dq', { status: Object.keys(dash.monetization_v2?.subscription?.active_by_tier || {}).length ? 'full' : 'empty' });
    setDq('anx-crystals-dq', { status: (dash.monetization_v2?.crystals?.by_source || []).length ? 'full' : 'empty' });
    setDq('anx-money-dq', { status: dash.monetization_v2?.funnel ? 'full' : 'empty' });
    setDq('anx-segments-dq', { status: dash.overview ? 'full' : 'empty' });
  }

  renderActivation(activation) {
    const steps = activation?.steps || [];
    $('anx-activation-cohort').textContent = activation?.cohort
      ? `когорта: ${num(activation.cohort)} открытий Mini App за ${num(activation.days ?? state.period)} дн.`
      : '';
    $('anx-activation').innerHTML = steps.length
      ? steps.map((step) => {
          const label = ACTIVATION_LABELS[step.event] || step.step;
          return `<div class="funnel-step"><div class="funnel-top"><span>${esc(label)}</span><span>${num(step.value)} · ${pct(step.of_cohort)}</span></div><div class="funnel-bar"><div class="funnel-fill" style="width:${Math.max(1, step.of_cohort)}%"></div></div></div>`;
        }).join('')
      : '<div class="muted small">Открытий Mini App за период пока нет</div>';
  }

  renderFunnel(funnel) {
    const days = $('anx-funnel-days');
    if (days) days.textContent = String(state.period);
    $('anx-funnel').innerHTML = (funnel || []).length
      ? funnel.map((step, index) => {
          const previous = index ? funnel[index - 1].value : step.value;
          const drop = previous ? Math.round((1 - step.value / previous) * 100) : 0;
          // Таргет §6 — доля от первого шага (visit→paid для «Заплатили»).
          const target = FUNNEL_TARGETS[step.step];
          const rate = step.of_total;
          const tone = !target || !previous ? ''
            : rate >= target.green ? ' good' : rate < target.red ? ' bad' : ' warn';
          const toneTitle = tone === ' good' ? 'в таргете (гипотеза)' : tone === ' warn' ? 'в амбер-зоне (гипотеза)' : 'ниже таргета (гипотеза)';
          return `<div class="funnel-step${tone}"><div class="funnel-top"><span>${esc(step.step)}${tone ? ` <span class="funnel-target-mark" title="${toneTitle}" aria-hidden="true">${tone === ' good' ? '●' : tone === ' warn' ? '◐' : '○'}</span><span class="sr-only">, ${toneTitle}</span>` : ''}</span><span>${num(step.value)} · ${pct(step.of_total)}${index && drop > 0 ? `<span class="funnel-drop">−${drop}%</span>` : ''}</span></div><div class="funnel-bar"><div class="funnel-fill" style="width:${Math.max(1, step.of_total)}%"></div></div></div>`;
        }).join('')
      : '<div class="muted small">Данных за период нет</div>';
    const funnelCard = $('anx-funnel').closest('.card');
    if (funnelCard) {
      funnelCard.title = 'Воронка по клиентам, зарегистрированным в окне. Подсветка — гипотетические таргеты (BUS-176 §6), не алерты.';
    }
  }

  renderSources(sources) {
    $('anx-sources').innerHTML = table([
      { title: 'Канал', render: (row) => esc(row.source || 'organic') },
      { title: 'Пришло', num: true, render: (row) => num(row.users) },
      { title: 'Платящих', num: true, render: (row) => num(row.payers) },
      { title: 'Доля платящих', num: true, render: (row) => (row.users ? pct((row.payers * 100) / row.users) : '—') },
      { title: 'LTV, Stars', num: true, render: (row) => num(row.stars) },
    ], sources || [], { empty: 'Каналов за период нет' });
  }

  renderRetention(retention) {
    $('anx-retention').innerHTML = table([
      { title: 'Когорта', render: (row) => date(row.cohort) },
      { title: 'Людей', num: true, render: (row) => num(row.size) },
      { title: 'D1', num: true, render: (row) => pct(row.d1) },
      { title: 'D3', num: true, render: (row) => pct(row.d3) },
      { title: 'D7', num: true, render: (row) => pct(row.d7) },
      { title: 'D14', num: true, render: (row) => pct(row.d14) },
      { title: 'D30', num: true, render: (row) => pct(row.d30) },
    ], retention || [], { empty: 'Когорт пока нет — нужны первые недели' });
  }

  renderMoney(dash) {
    const v2 = dash.monetization_v2;
    if (!v2) {
      $('anx-rev-kpi').innerHTML = '<div class="empty">v2-монетизация недоступна (демо-режим)</div>';
      ['anx-rev-sku', 'anx-tiers', 'anx-money-funnel', 'anx-crystals']
        .forEach((id) => { $(id).innerHTML = '<div class="empty">Нет данных</div>'; });
      $('anx-crystal-sub').textContent = '';
      return;
    }
    const rev = v2.revenue || {};
    const sub = v2.subscription || {};
    const cogs = v2.cogs || {};
    const kpis = [
      { label: 'Gross, Stars', value: num(rev.gross_stars), sub: usd(rev.gross_stars), cls: 'accent' },
      { label: 'Оплаченных заказов', value: num(rev.paid_orders), sub: `возвратов: ${num(rev.refunded_orders)}`, cls: '' },
      { label: 'Доля возвратов', value: pct(rev.refund_rate_pct), sub: 'от оплаченных заказов', cls: (rev.refund_rate_pct ?? 0) > 5 ? 'bad' : 'good' },
      { label: 'Новых плательщиков', value: num(sub.new_paid_users), sub: `за ${num(v2.window_days ?? state.period)} дн.`, cls: '' },
      { label: 'Повторных плательщиков', value: num(sub.repeat_payers), sub: 'больше одной оплаты', cls: '' },
      { label: 'Переменные расходы', value: `$${(cogs.total_variable_cost_usd ?? 0).toFixed(2)}`, sub: `${num((cogs.by_kind || []).reduce((sum, item) => sum + (item.events || 0), 0))} событий`, cls: '' },
    ];
    $('anx-rev-kpi').innerHTML = kpis.map((item) =>
      `<div class="kpi ${item.cls}"><div class="kpi-label">${esc(item.label)}</div><div class="kpi-value">${item.value}</div><div class="kpi-sub">${esc(item.sub)}</div></div>`).join('');

    $('anx-rev-sku').innerHTML = table([
      { title: 'SKU', render: (row) => esc(row.sku) },
      { title: 'Заказов', num: true, render: (row) => num(row.orders) },
      { title: 'Stars', num: true, render: (row) => num(row.stars) },
    ], rev.by_sku || [], { empty: 'Оплаченных заказов за период нет' });

    const tiers = Object.entries(sub.active_by_tier || {});
    $('anx-tiers').innerHTML = tiers.length
      ? table([
          { title: 'Тариф', render: (row) => esc(row[0]) },
          { title: 'Активных', num: true, render: (row) => num(row[1]) },
        ], tiers)
      : '<div class="empty">Активных подписок нет</div>';

    const funnelCounts = v2.funnel || {};
    const base = funnelCounts.paywall_view || 0;
    $('anx-money-funnel').innerHTML = table([
      { title: 'Событие', render: (row) => esc(row.label) },
      { title: 'Раз', num: true, render: (row) => num(row.value) },
      { title: 'От пейволла', num: true, render: (row) => (base ? pct((row.value * 100) / base) : '—') },
    ], MONEY_EVENTS.map(([key, label]) => ({ key, label, value: funnelCounts[key] ?? 0 })));

    const crystals = v2.crystals || {};
    $('anx-crystal-sub').textContent = `в обороте: ${num(crystals.outstanding)} ✦ · повторных покупок: ${num(crystals.repeat_purchase_users)}`;
    $('anx-crystals').innerHTML = table([
      { title: 'Источник', render: (row) => esc(row.source) },
      { title: 'Выдано', num: true, render: (row) => num(row.granted) },
      { title: 'Потрачено', num: true, render: (row) => num(row.spent) },
    ], crystals.by_source || [], { empty: 'Движений кристаллов за период нет' });
  }

  renderSegments(overview) {
    if (!overview) { $('anx-segments').innerHTML = ''; return; }
    $('anx-segments').innerHTML = segmentCards(overview).map(([code, label, value]) =>
      `<button type="button" class="segment-card${this.segment === code ? ' active' : ''}" data-segment="${esc(code)}" aria-pressed="${this.segment === code}"><span class="segment-value">${num(value)}</span><span class="segment-label">${esc(label)}</span></button>`).join('');
  }

  highlightSegments() {
    $('anx-segments').querySelectorAll('.segment-card').forEach((card) => {
      const active = card.dataset.segment === this.segment;
      card.classList.toggle('active', active);
      card.setAttribute('aria-pressed', String(active));
    });
  }

  async loadUsers() {
    const query = new URLSearchParams({
      q: this.q, segment: this.segment, order: this.order,
      limit: String(this.limit), offset: String(this.offset),
    });
    const data = await get(`/api/admin/users?${query}`);
    fillSegmentSelect($('anx-segment'), data.segments || [], segmentLabel);
    $('anx-segment').value = this.segment;
    this.highlightSegments();
    $('anx-total').textContent = `найдено: ${num(data.total)}`;
    $('anx-page').textContent = `${data.total ? this.offset + 1 : 0}–${Math.min(this.offset + this.limit, data.total)} из ${num(data.total)}`;
    $('anx-prev').disabled = this.offset === 0;
    $('anx-next').disabled = this.offset + this.limit >= data.total;
    const element = $('anx-users-table');
    element.innerHTML = table([
      { title: 'Клиентка', render: (row) => `<b>${esc(row.name || '—')}</b><div class="muted small">${row.username ? '@' + esc(row.username) : row.tg_id}</div>` },
      { title: 'Тариф', render: (row) => (row.sub_active ? `<span class="badge on">${esc(row.sub_level)}</span>` : '<span class="badge off">нет</span>') },
      { title: 'Теги', render: (row) => (row.tags || []).map((tag) => `<span class="badge tag">${esc(tag)}</span>`).join(' ') },
      { title: 'Кристаллы', num: true, render: (row) => num(row.crystals) },
      { title: 'Stars', num: true, render: (row) => num(row.ltv_stars) },
      { title: 'Была', render: (row) => date(row.last_seen, true) },
      { title: 'Пришла', render: (row) => date(row.created_at) },
    ], data.items, { onRow: true, empty: 'Никого не нашлось' });
    bindRows(element, data.items, (row) => actions.openUser(row.tg_id));
  }
}
