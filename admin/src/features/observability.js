import { $, esc, num, date, get, post, state, table, toast, fail } from '../core/runtime.js';

const SAFETY_LABELS = { suicide: 'Суицидальные мысли', self_harm: 'Самоповреждение', violence: 'Насилие', medical: 'Здоровье', high_stakes: 'Крупные решения' };

export class ObservabilityFeature {
  async loadHoroscopes() {
    const day = $('horo-day').value || undefined;
    const data = await get(`/api/admin/horoscopes${day ? `?day=${encodeURIComponent(day)}` : ''}`);
    const channels = Object.keys(data.channels || {}).length;
    $('horo-channels').textContent = channels ? `каналов настроено: ${channels}` : 'каналы не настроены (HOROSCOPE_CHANNELS в .env)';
    $('horo-list').innerHTML = table([{ title: 'Знак', render: (row) => `${esc(row.symbol)} ${esc(row.sign)}` }, { title: 'Стихия', render: (row) => `<span class="muted">${esc(row.element)}</span>` }, { title: 'Текст', render: (row) => row.text ? `<span class="muted small">${esc(row.text.slice(0, 160))}…</span>` : '<span class="bad">не собран</span>' }, { title: 'В канале', render: (row) => row.posted_at ? date(row.posted_at, true) : '<span class="muted">—</span>' }], data.items, { empty: 'На этот день ничего нет' });
  }

  async buildHoroscopes() {
    const button = $('horo-build'); button.disabled = true;
    try { const day = $('horo-day').value; const result = await post(`/api/admin/horoscopes/build${day ? `?day=${encodeURIComponent(day)}` : ''}`); toast(result.built ? `Собрано знаков: ${result.built}` : 'Всё уже собрано'); await this.loadHoroscopes(); } catch (error) { fail(error); } finally { button.disabled = false; }
  }

  async loadCosts() {
    const costs = await get(`/api/admin/costs?days=${state.period}`);
    $('cost-kpi').innerHTML = [{ label: `Расход за ${costs.days} дн.`, value: `$${costs.cost_usd.toFixed(2)}`, sub: `${num(costs.calls)} вызовов`, cls: '' }, { label: 'На платящую', value: `$${costs.per_paying_usd.toFixed(2)}`, sub: 'цель ≤ $2.50', cls: costs.per_paying_usd > 2.5 ? 'bad' : 'good' }, { label: 'Сбои', value: `${costs.fail_rate.toFixed(1)}%`, sub: `${num(costs.failed)} вызовов`, cls: costs.fail_rate > 5 ? 'bad' : 'good' }].map((item) => `<div class="kpi ${item.cls}"><div class="kpi-label">${esc(item.label)}</div><div class="kpi-value">${esc(item.value)}</div><div class="kpi-sub">${esc(item.sub)}</div></div>`).join('');
    $('cost-purpose').innerHTML = table([{ title: 'На что', render: (row) => `<code>${esc(row.purpose || '—')}</code>` }, { title: 'Вызовов', num: true, render: (row) => num(row.calls) }, { title: 'Токенов вход', num: true, render: (row) => num(row.tokens_in) }, { title: 'Токенов выход', num: true, render: (row) => num(row.tokens_out) }, { title: 'Стоимость', num: true, render: (row) => `$${(row.cost || 0).toFixed(3)}` }, { title: 'Среднее, мс', num: true, render: (row) => num(Math.round(row.avg_ms)) }], costs.by_purpose, { empty: 'Вызовов ещё не было' });
    $('cost-models').innerHTML = table([{ title: 'Провайдер', render: (row) => esc(row.provider) }, { title: 'Модель', render: (row) => `<code>${esc(row.model)}</code>` }, { title: 'Вызовов', num: true, render: (row) => num(row.calls) }, { title: 'Стоимость', num: true, render: (row) => `$${(row.cost || 0).toFixed(3)}` }], costs.by_model, { empty: 'Вызовов ещё не было' });
  }

  async loadSafety() {
    const data = await get(`/api/admin/safety?days=${state.period}`);
    $('safety-summary').innerHTML = table([{ title: 'Категория', render: (row) => esc(SAFETY_LABELS[row.category] || row.category) }, { title: 'Реакция', render: (row) => row.action === 'support' ? '<span class="bad">поддержка вместо гадания</span>' : '<span class="muted">смягчённый ответ</span>' }, { title: 'Случаев', num: true, render: (row) => num(row.n) }], data.summary, { empty: 'Срабатываний не было' });
    $('safety-recent').innerHTML = table([{ title: 'Когда', render: (row) => date(row.created_at, true) }, { title: 'Кто', render: (row) => esc(row.name || row.tg_id || '—') }, { title: 'Категория', render: (row) => esc(SAFETY_LABELS[row.category] || row.category) }, { title: 'Сообщение', render: (row) => `<span class="muted small">${esc(row.excerpt || '')}</span>` }], data.recent, { empty: 'Обращений не было' });
  }

  async loadAudit() {
    const rows = await get('/api/admin/audit?limit=300');
    $('audit-table').innerHTML = table([{ title: 'Когда', render: (row) => date(row.created_at, true) }, { title: 'Кто', render: (row) => esc(row.admin_name || row.admin_id || '—') }, { title: 'Действие', render: (row) => `<code>${esc(row.action)}</code>` }, { title: 'Объект', render: (row) => esc(row.target || '') }, { title: 'Детали', render: (row) => `<span class="muted small">${esc(row.payload_json || '')}</span>` }], rows, { empty: 'Записей нет' });
  }
}
