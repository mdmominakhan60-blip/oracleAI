import { $, esc, num, date, get, post, state, actions, table, bindRows, fillSegmentSelect, toast, fail } from '../core/runtime.js';
import { segmentLabel } from './users.js';

export class EngagementFeature {
  constructor() {
    $('promo-unused').addEventListener('change', () => this.loadPromo().catch(fail));
    $('promo-create').addEventListener('click', (event) => this.createPromo(event));
    $('bc-preview').addEventListener('click', () => this.previewBroadcast().catch(fail));
    $('bc-create').addEventListener('click', (event) => this.createBroadcast(event));
  }

  async loadPromo() {
    if (!state.plans.length) await actions.loadCatalog?.();
    const query = new URLSearchParams();
    if ($('promo-unused').checked) query.set('unused', 'true');
    if (state.promoBatch) query.set('batch', state.promoBatch);
    const [data, redemptions] = await Promise.all([get(`/api/admin/promo?${query}`), get('/api/admin/promo/redemptions?limit=300')]);
    $('promo-batches').innerHTML = table([
      { title: 'Партия', render: (row) => `<code>${esc(row.batch)}</code>${state.promoBatch === row.batch ? '<span class="badge on">фильтр</span>' : ''}` },
      { title: 'Кодов', num: true, render: (row) => num(row.total) }, { title: 'Активировано', num: true, render: (row) => num(row.used) },
      { title: 'Конверсия', num: true, render: (row) => `${row.total ? ((row.used * 100) / row.total).toFixed(1) : '0.0'}%` }, { title: 'Создана', render: (row) => date(row.created_at) },
    ], data.batches, { onRow: true, empty: 'Партий пока нет' });
    bindRows($('promo-batches'), data.batches, (row) => { state.promoBatch = state.promoBatch === row.batch ? '' : row.batch; $('promo-batch-hint').textContent = state.promoBatch ? `фильтр: партия «${state.promoBatch}» (клик по партии ещё раз — снять)` : ''; this.loadPromo().catch(fail); });
    const redemptionByCode = new Map(redemptions.map((row) => [row.code, row]));
    $('promo-codes').innerHTML = table([
      { title: 'Код', render: (row) => `<code>${esc(row.code)}</code>` },
      { title: 'Что даёт', render: (row) => row.kind === 'crystals' ? `✦${row.crystals}` : row.kind === 'product' ? esc(row.sku || '') : `${row.days} дн. ${esc(row.plan_code || '')}` },
      { title: 'Партия', render: (row) => esc(row.batch || '—') }, { title: 'Использован', num: true, render: (row) => `${row.used_count || 0}/${row.max_uses || 1}` },
      { title: 'Кем', render: (row) => { const redemption = redemptionByCode.get(row.code); return redemption ? `<b>${esc(redemption.name || redemption.tg_id)}</b>${redemption.username ? ` <span class="muted small">@${esc(redemption.username)}</span>` : ''}` : '—'; } },
      { title: 'Когда', render: (row) => { const redemption = redemptionByCode.get(row.code); return redemption ? date(redemption.created_at, true) : '—'; } }, { title: 'Действует до', render: (row) => date(row.expires_at) },
    ], data.codes, { onRow: true, empty: 'Кодов нет' });
    bindRows($('promo-codes'), data.codes, (row) => row.used_by && actions.openUser?.(row.used_by));
    $('promo-redemptions').innerHTML = table([
      { title: 'Когда', render: (row) => date(row.created_at, true) }, { title: 'Кто', render: (row) => `<b>${esc(row.name || row.tg_id)}</b>${row.username ? `<div class="muted small">@${esc(row.username)}</div>` : ''}` },
      { title: 'Код', render: (row) => `<code>${esc(row.code)}</code>` }, { title: 'Партия', render: (row) => esc(row.batch || '—') },
      { title: 'Что дало', render: (row) => row.kind === 'crystals' ? `✦${row.crystals}` : row.kind === 'product' ? esc(row.sku || '') : `${row.days} дн. ${esc(row.plan_code || '')}` },
    ], redemptions, { onRow: true, empty: 'Активаций пока не было' });
    bindRows($('promo-redemptions'), redemptions, (row) => actions.openUser?.(row.tg_id));
  }

  async createPromo(event) {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const result = await post('/api/admin/promo', { count: +$('promo-count').value || 1, kind: $('promo-kind').value, days: +$('promo-days').value || 30, plan_code: $('promo-plan').value, crystals: +$('promo-crystals').value || 0, sku: $('promo-sku').value.trim() || null, batch: $('promo-batch').value.trim() || 'manual', max_uses: +$('promo-uses').value || 1, valid_days: +$('promo-valid').value || null });
      $('promo-out').textContent = result.codes.join('\n');
      $('promo-out').classList.remove('hidden');
      toast(`Создано кодов: ${result.codes.length}`);
      await this.loadPromo();
    } catch (error) { fail(error); } finally { button.disabled = false; }
  }

  async loadBroadcasts() {
    if (!state.segments.length) await actions.loadUsers?.();
    fillSegmentSelect($('bc-segment'), state.segments, segmentLabel);
    const rows = await get('/api/admin/broadcasts');
    const element = $('bc-list');
    element.innerHTML = table([
      { title: 'Рассылка', render: (row) => `${esc(row.title)}<div class="muted small">${esc(row.body || '').slice(0, 60)}…</div>` },
      { title: 'Статус', render: (row) => `<span class="badge ${row.status === 'done' ? 'on' : row.status === 'running' ? 'warn' : row.status === 'cancelled' ? 'bad' : 'off'}">${esc(row.status)}</span>` },
      { title: 'Ушло', num: true, render: (row) => `${num(row.progress.sent)}/${num(row.total)}` }, { title: 'Ошибок', num: true, render: (row) => num(row.progress.failed + row.progress.skipped) },
      { title: 'Когда', render: (row) => date(row.started_at || row.scheduled_at || row.created_at, true) },
      { title: '', render: (row) => row.status === 'scheduled' || row.status === 'running' ? `<button class="btn tiny danger" data-cancel="${row.id}" type="button">Отменить</button>` : row.status === 'draft' ? `<button class="btn tiny ghost" data-start="${row.id}" type="button">Отправить</button>` : '' },
    ], rows, { empty: 'Рассылок не было' });
    element.querySelectorAll('[data-cancel]').forEach((button) => button.addEventListener('click', async () => { try { await post(`/api/admin/broadcasts/${button.dataset.cancel}/cancel`); toast('Отменено'); await this.loadBroadcasts(); } catch (error) { fail(error); } }));
    element.querySelectorAll('[data-start]').forEach((button) => button.addEventListener('click', async () => { try { await post(`/api/admin/broadcasts/${button.dataset.start}/start`); toast('Отправка запущена'); await this.loadBroadcasts(); } catch (error) { fail(error); } }));
  }

  payload(sendNow) {
    return { title: $('bc-title').value.trim(), body: $('bc-body').value.trim(), segment: $('bc-segment').value, button_text: $('bc-btn-text').value.trim() || null, button_url: $('bc-btn-url').value.trim() || null, send_now: sendNow };
  }

  async previewBroadcast() {
    const result = await post('/api/admin/broadcasts/preview', this.payload(false));
    $('bc-preview-out').textContent = `В сегменте «${segmentLabel(result.segment)}» — ${num(result.count)} человек.`;
  }

  async createBroadcast(event) {
    const payload = this.payload(true);
    if (!payload.title || !payload.body) { toast('Нужны название и текст', true); return; }
    if (!confirm(`Отправить рассылку сегменту «${segmentLabel(payload.segment)}»?`)) return;
    event.currentTarget.disabled = true;
    try { const result = await post('/api/admin/broadcasts', payload); toast(`Поставлено в очередь: ${num(result.total)} получателей`); $('bc-body').value = ''; $('bc-title').value = ''; await this.loadBroadcasts(); } catch (error) { fail(error); } finally { event.currentTarget.disabled = false; }
  }
}
