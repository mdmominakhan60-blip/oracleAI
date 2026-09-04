import { $, esc, num, date, get, post, patch, state, actions, table, bindRows, can, toast, fail, downloadAdminFile } from '../core/runtime.js';

function editableCell(value, { entity, id, field, type = 'text' }) {
  return `<input class="input slim" style="width:${type === 'number' ? '86px' : '160px'}" type="${type}" value="${esc(String(value ?? ''))}" data-entity="${entity}" data-id="${esc(id)}" data-field="${field}">`;
}

export class CommerceFeature {
  constructor() {
    $('order-status').addEventListener('change', () => this.loadOrders().catch(fail));
    $('reconciliation-export').addEventListener('click', () => downloadAdminFile('/api/admin/reconciliation/export', 'payment-reconciliation.json').catch(fail));
    actions.loadCatalog = () => this.loadCatalog();
  }

  async loadOrders() {
    const status = $('order-status').value;
    const rows = await get(`/api/admin/orders?limit=200${status ? `&status=${encodeURIComponent(status)}` : ''}`);
    const element = $('orders-table');
    element.innerHTML = table([
      { title: '#', render: (row) => row.id },
      { title: 'Клиентка', render: (row) => `${esc(row.name || row.tg_id)}${row.username ? `<div class="muted small">@${esc(row.username)}</div>` : ''}` },
      { title: 'Что', render: (row) => `${esc(row.title || row.sku || row.kind)}<div class="muted small">${esc(row.kind)}</div>` },
      { title: 'Stars', num: true, render: (row) => num(row.amount_stars) },
      { title: '✦', num: true, render: (row) => num(row.amount_crystals) },
      { title: 'Статус', render: (row) => `<span class="badge ${row.status === 'paid' ? 'on' : row.status === 'refunded' ? 'bad' : 'off'}">${esc(row.status)}</span>` },
      { title: 'Когда', render: (row) => date(row.paid_at || row.created_at, true) },
      { title: '', render: (row) => row.status === 'paid' && can('grants') ? `<button class="btn tiny danger" data-refund="${row.id}" type="button">Возврат</button>` : '' },
    ], rows, { onRow: true, empty: 'Заказов нет' });
    element.querySelectorAll('[data-refund]').forEach((button) => button.addEventListener('click', async (event) => {
      event.stopPropagation();
      if (!confirm('Вернуть Stars клиентке? Telegram проведёт возврат.')) return;
      button.disabled = true;
      try { await post(`/api/admin/orders/${button.dataset.refund}/refund`); toast('Возврат проведён'); await this.loadOrders(); } catch (error) { fail(error); button.disabled = false; }
    }));
    bindRows(element, rows, (row) => actions.openUser?.(row.tg_id));
  }

  async loadCatalog() {
    const [plans, products] = await Promise.all([get('/api/admin/plans'), get('/api/admin/products')]);
    state.plans = plans;
    $('plans-table').innerHTML = table([
      { title: 'Код', render: (row) => `<code>${esc(row.code)}</code>` },
      { title: 'Название', render: (row) => editableCell(row.title, { entity: 'plan', id: row.code, field: 'title' }) },
      { title: 'Stars', num: true, render: (row) => editableCell(row.price_stars, { entity: 'plan', id: row.code, field: 'price_stars', type: 'number' }) },
      { title: 'Дней', num: true, render: (row) => editableCell(row.period_days, { entity: 'plan', id: row.code, field: 'period_days', type: 'number' }) },
      { title: 'Вопр./день', num: true, render: (row) => editableCell(row.daily_questions, { entity: 'plan', id: row.code, field: 'daily_questions', type: 'number' }) },
      { title: 'Память', num: true, render: (row) => editableCell(row.memory_depth, { entity: 'plan', id: row.code, field: 'memory_depth', type: 'number' }) },
      { title: '✦ бонус', num: true, render: (row) => editableCell(row.crystals_grant, { entity: 'plan', id: row.code, field: 'crystals_grant', type: 'number' }) },
      { title: 'Витрина', render: (row) => `<label class="switch"><input type="checkbox" ${row.is_public ? 'checked' : ''} data-entity="plan" data-id="${esc(row.code)}" data-field="is_public"><span></span></label>` },
    ], plans, { empty: 'Тарифов нет' });
    $('products-table').innerHTML = table([
      { title: 'SKU', render: (row) => `<code>${esc(row.sku)}</code>` }, { title: 'Вид', render: (row) => `<span class="badge">${esc(row.kind)}</span>` },
      { title: 'Название', render: (row) => editableCell(row.title, { entity: 'product', id: row.sku, field: 'title' }) },
      { title: 'Stars', num: true, render: (row) => editableCell(row.price_stars, { entity: 'product', id: row.sku, field: 'price_stars', type: 'number' }) },
      { title: '✦', num: true, render: (row) => editableCell(row.price_crystals, { entity: 'product', id: row.sku, field: 'price_crystals', type: 'number' }) },
      { title: 'Выдаём', render: (row) => `${esc(row.grant_kind || '')}${row.grant_code ? ':' + esc(row.grant_code) : ''} ×${row.grant_qty}` },
      { title: 'Активен', render: (row) => `<label class="switch"><input type="checkbox" ${row.is_active ? 'checked' : ''} data-entity="product" data-id="${esc(row.sku)}" data-field="is_active"><span></span></label>` },
    ], products, { empty: 'Товаров нет' });
    this.bindCatalogEdits();
    const selector = $('promo-plan');
    selector.innerHTML = plans.map((plan) => `<option value="${esc(plan.code)}">${esc(plan.title)}</option>`).join('');
    selector.value = plans.some((plan) => plan.code === 'vip') ? 'vip' : plans[0]?.code;
  }

  bindCatalogEdits() {
    document.querySelectorAll('[data-entity]').forEach((element) => {
      if (!can('catalog')) { element.disabled = true; return; }
      const commit = async () => {
        const value = element.type === 'checkbox' ? (element.checked ? 1 : 0) : element.type === 'number' ? Number(element.value) : element.value;
        try { if (element.dataset.entity === 'plan') await post('/api/admin/plans', { code: element.dataset.id, fields: { [element.dataset.field]: value } }); else await post('/api/admin/products', { sku: element.dataset.id, fields: { [element.dataset.field]: value } }); toast('Сохранено'); } catch (error) { fail(error); }
      };
      element.addEventListener(element.type === 'checkbox' ? 'change' : 'blur', commit);
    });
  }

  async loadReconciliation() {
    if (state.role !== 'owner') { $('reconciliation-summary').innerHTML = '<div class="empty">Раздел доступен только владельцу.</div>'; return; }
    const [data, preferences] = await Promise.all([get('/api/admin/reconciliation'), get('/api/admin/payment-notifications')]);
    $('reconciliation-summary').innerHTML = `<div class="payment-health-grid"><div class="health-stat"><span>Аномальные записи</span><b>${num(data.count)}</b></div><div class="health-stat"><span>Ledger mismatches</span><b>${num(data.ledger_mismatches)}</b></div></div>`;
    const element = $('reconciliation-table');
    element.innerHTML = table([{ title: 'Заказ', num: true, render: (row) => num(row.order_id) }, { title: 'Проблема', render: (row) => esc(row.issue) }, { title: 'SKU', render: (row) => esc(row.sku || '—') }, { title: 'Создан', render: (row) => date(row.created_at, true) }, { title: 'Действие', render: (row) => `<button class="btn ghost btn-small" type="button" data-recheck="${row.order_id}">Проверить</button>` }], data.items || [], { empty: 'Аномалий не найдено' });
    element.querySelectorAll('[data-recheck]').forEach((button) => button.addEventListener('click', () => this.openReconciliationOrder(button.dataset.recheck)));
    $('payment-notification-form').innerHTML = `<div class="form-grid"><label>DEGRADED cooldown, часов<input id="pref-degraded" class="input" type="number" min="1" max="168" value="${preferences.degraded_cooldown_hours}"></label><label>CRITICAL cooldown, часов<input id="pref-critical" class="input" type="number" min="1" max="168" value="${preferences.critical_cooldown_hours}"></label><label>Тихие часы с<input id="pref-start" class="input" type="time" value="${preferences.quiet_hours_start}"></label><label>Тихие часы до<input id="pref-end" class="input" type="time" value="${preferences.quiet_hours_end}"></label></div><label class="check"><input id="pref-secondary" type="checkbox" ${preferences.secondary_enabled ? 'checked' : ''} ${preferences.secondary_configured ? '' : 'disabled'}> Второй webhook-канал${preferences.secondary_configured ? '' : ' (URL не настроен)'}</label><button id="pref-save" class="btn gold" type="button">Сохранить настройки</button><span id="pref-status" class="muted small" role="status"></span>`;
    $('pref-save').onclick = async () => { try { await patch('/api/admin/payment-notifications', { degraded_cooldown_hours: +$('pref-degraded').value, critical_cooldown_hours: +$('pref-critical').value, quiet_hours_start: $('pref-start').value, quiet_hours_end: $('pref-end').value, secondary_enabled: $('pref-secondary').checked }); $('pref-status').textContent = 'Сохранено'; } catch (error) { fail(error); } };
  }

  async openReconciliationOrder(orderId) {
    const detail = $('reconciliation-detail');
    detail.hidden = false;
    detail.innerHTML = '<div class="loader-ring"></div>';
    try {
      const item = await get(`/api/admin/reconciliation/${encodeURIComponent(orderId)}`);
      detail.innerHTML = `<div class="card-head"><h3>Заказ #${num(item.order_id)}</h3><button class="btn ghost btn-small" type="button" data-mark-review ${item.review_status === 'manual_review' ? 'disabled' : ''}>${item.review_status === 'manual_review' ? 'Уже на review' : 'Пометить для review'}</button></div><p class="muted small">${esc(item.title || item.sku || 'Покупка')} · ${esc(item.status || '—')} · ${num(item.amount_stars)} ⭐</p><p>Провайдер: <b>${esc(item.provider || '—')}</b> · payments: <b>${num(item.payment_count)}</b></p><p>${item.issues?.length ? `Проблемы: ${item.issues.map(esc).join(', ')}` : 'Критичных проблем не найдено.'}</p>`;
      detail.querySelector('[data-mark-review]')?.addEventListener('click', async () => { try { await post(`/api/admin/reconciliation/${encodeURIComponent(orderId)}/review`); toast('Заказ помечен для ручной сверки'); await this.openReconciliationOrder(orderId); } catch (error) { fail(error); } });
    } catch (error) { detail.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
  }
}
