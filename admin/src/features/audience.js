import {
  $, esc, num, date, pct, get, state, actions, table, bindRows, toast, fail,
} from '../core/runtime.js';
import { setDq } from './analytics.js';
import { segmentLabel } from './users.js';
import { renderChurnCards } from './churn-cards.js';

// Экран A «Audience Overview» (BUS-168 §1.1; R1/R2/R9/R10).
// Счётчики — /api/admin/audience/segments (BUS-230): предикаты только из
// SEGMENTS (app/repo/users.py) через segment_count — равенство broadcast
// preview (§3.3 BUS-168) соблюдается конструкцией. Δ7д событийных сегментов
// приходит null → R9: «нет данных», а не ноль.

const GOAL_LABELS = {
  love: 'Любовь', career: 'Карьера', practice: 'Практика', unset: 'Без цели',
};

function renderDelta(delta) {
  if (delta === null || delta === undefined) {
    return '<span class="muted small" title="Δ7д не считается: событийный предикат сегмента">—<span class="sr-only">нет данных за 7 дней</span></span>';
  }
  const arrow = delta > 0 ? '▲ +' : delta < 0 ? '▼ ' : '± ';
  const tone = delta > 0 ? ' up' : delta < 0 ? ' down' : '';
  return `<span class="seg-delta${tone}">${arrow}${num(Math.abs(delta))}<span class="sr-only">за 7 дней</span></span>`;
}

export class AudienceFeature {
  constructor() {
    this.bound = false;
    this.segment = null;
    this.q = '';
    this.offset = 0;
    this.limit = 50;
    this.sortBy = 'count';
    this.segments = [];
  }

  bind() {
    if (this.bound) return;
    this.bound = true;
    $('aud-sort').addEventListener('change', (event) => {
      this.sortBy = event.target.value;
      this.renderTable();
    });
    $('aud-churn').addEventListener('click', (event) => {
      const card = event.target.closest('[data-churn-segment]');
      if (card) this.openSegmentList(card.dataset.churnSegment);
    });
    $('aud-detail-back').addEventListener('click', () => this.closeDetail());
    $('aud-detail-prev').addEventListener('click', () => {
      this.offset = Math.max(0, this.offset - this.limit);
      this.loadDetail().catch(fail);
    });
    $('aud-detail-next').addEventListener('click', () => {
      this.offset += this.limit;
      this.loadDetail().catch(fail);
    });
  }

  async load() {
    this.bind();
    await Promise.all([
      this.loadSegments(),
      this.loadGoals(),
      renderChurnCards('aud-churn', 'aud-churn-dq'),
    ]);
    // Приход с «Когорт» по клику на churn-карточку: цифра кликабельна
    // до источника (§3.3 BUS-168) и между экранами тоже.
    const pending = state.audiencePending;
    state.audiencePending = null;
    if (pending) this.openSegmentList(pending);
  }

  async loadSegments() {
    try {
      const data = await get('/api/admin/audience/segments');
      this.segments = data.segments || [];
      setDq('aud-dq', data.data_quality || { status: 'empty', note: 'API аудитории недоступен' });
      this.renderTable();
    } catch (error) {
      setDq('aud-dq', { status: 'empty', note: 'API аудитории недоступен' });
      $('aud-segments').innerHTML = '<div class="empty">Нет данных — API аудитории недоступен</div>';
      fail(error);
    }
  }

  renderTable() {
    const rows = [...this.segments];
    if (this.sortBy === 'delta') {
      // null-дельты — в конец: «нет данных» не ранжируется как ноль (R9)
      rows.sort((a, b) => (b.delta_7d ?? -Infinity) - (a.delta_7d ?? -Infinity));
    } else {
      rows.sort((a, b) => b.count - a.count);
    }
    $('aud-segments').innerHTML = table([
      { title: 'Сегмент', render: (row) => esc(segmentLabel(row.segment)) },
      { title: 'Клиенток', num: true, render: (row) => num(row.count) },
      { title: 'Δ7д', num: true, render: (row) => renderDelta(row.delta_7d) },
    ], rows, { onRow: true, empty: 'Сегментов нет' });
    bindRows($('aud-segments'), rows, (row) => this.openSegmentList(row.segment));
  }

  async loadGoals() {
    try {
      const data = await get('/api/admin/audience/goals');
      const goals = data.goals || [];
      setDq('aud-goals-dq', goals.length
        ? { status: 'full' }
        : { status: 'empty', note: 'поле goal у клиенток не заполнено' });
      const max = Math.max(1, ...goals.map((goal) => goal.users));
      $('aud-goals').innerHTML = goals.length
        ? goals.map((goal) => `
          <div class="funnel-step">
            <div class="funnel-top">
              <span>${esc(GOAL_LABELS[goal.goal] || goal.goal)}</span>
              <span>${num(goal.users)} · ${pct(goal.share_pct)} · платящих: ${num(goal.payers)}</span>
            </div>
            <div class="funnel-bar"><div class="funnel-fill" style="width:${Math.max(1, (goal.users * 100) / max)}%"></div></div>
          </div>`).join('')
        : '<div class="empty">Нет данных — требуется G-11 (GROUP BY goal)</div>';
    } catch (error) {
      setDq('aud-goals-dq', { status: 'empty', note: 'API недоступен' });
      $('aud-goals').innerHTML = '<div class="empty">Нет данных — API недоступен</div>';
      fail(error);
    }
  }

  openSegmentList(segment) {
    if (!state.can('users:read')) {
      toast('Список клиенток требует право users:read', true);
      return;
    }
    this.segment = segment;
    this.offset = 0;
    $('aud-detail-card').classList.remove('hidden');
    $('aud-detail-title').textContent = `Сегмент: ${segmentLabel(segment)}`;
    $('aud-detail-card').scrollIntoView({ block: 'nearest' });
    this.loadDetail().catch(fail);
  }

  closeDetail() {
    $('aud-detail-card').classList.add('hidden');
    this.segment = null;
  }

  async loadDetail() {
    if (!this.segment) return;
    const query = new URLSearchParams({ limit: String(this.limit), offset: String(this.offset) });
    const data = await get(`/api/admin/audience/segments/${encodeURIComponent(this.segment)}/users?${query}`);
    $('aud-detail-total').textContent = `найдено: ${num(data.total)}`;
    $('aud-detail-page').textContent = `${data.total ? this.offset + 1 : 0}–${Math.min(this.offset + this.limit, data.total)} из ${num(data.total)}`;
    $('aud-detail-prev').disabled = this.offset === 0;
    $('aud-detail-next').disabled = this.offset + this.limit >= data.total;
    const element = $('aud-detail-table');
    element.innerHTML = table([
      { title: 'Клиентка', render: (row) => `<b>${esc(row.name || '—')}</b><div class="muted small">${row.username ? '@' + esc(row.username) : row.tg_id}</div>` },
      { title: 'Тариф', render: (row) => (row.sub_active ? `<span class="badge on">${esc(row.sub_level)}</span>` : '<span class="badge off">нет</span>') },
      { title: 'Теги', render: (row) => (row.tags || []).map((tag) => `<span class="badge tag">${esc(tag)}</span>`).join(' ') },
      { title: 'Кристаллы', num: true, render: (row) => num(row.crystals) },
      { title: 'Stars', num: true, render: (row) => num(row.ltv_stars) },
      { title: 'Была', render: (row) => date(row.last_seen, true) },
      { title: 'Пришла', render: (row) => date(row.created_at) },
    ], data.items || [], { onRow: true, empty: 'В сегменте пока никого' });
    bindRows(element, data.items || [], (row) => actions.openUser(row.tg_id));
  }
}
