import {
  $, esc, num, date, pct, get, state, actions, table, bindRows, toast, fail,
} from '../core/runtime.js';
import { setDq } from './analytics.js';
import { renderChurnCards } from './churn-cards.js';

// Экран B «Retention & Cohorts» (BUS-168 §1.2; канон BUS-176 §4.2).
// Milestone-семантика (не сумма строк): d1/d7 — return milestone, d30 —
// activity_fallback; matured — календарная зрелость; дата — без времени.

export class CohortsFeature {
  constructor() { this.bound = false; }

  bind() { this.bound = true; }

  async load() {
    this.bind();
    await Promise.all([
      this.loadRetention(),
      renderChurnCards('coh-churn', 'coh-churn-dq'),
    ]);
  }

  async loadRetention() {
    try {
      const granularity = ($('coh-granularity')?.value || 'day');
      const data = await get('/api/admin/analytics/retention?granularity=' + encodeURIComponent(granularity));
      const cohorts = data.cohorts || [];
      setDq('coh-retention-dq', data.data_quality || { status: 'empty' });
      const empty = !cohorts.length
        ? 'Когорт за период нет — нужны первые открытия Mini App'
        : null;
      $('coh-retention').innerHTML = table([
        { title: 'Когорта', render: (row) => date(row.day) },
        { title: 'Людей', num: true, render: (row) => num(row.size) },
        { title: 'D1', num: true, render: (row) => this.renderD(row.d1) },
        { title: 'D7', num: true, render: (row) => this.renderD(row.d7) },
        { title: 'D30', num: true, render: (row) => this.renderD(row.d30) },
      ], cohorts, { empty, onRow: true });
      bindRows($('coh-retention'), cohorts, (row) => {
        if (!row.size) return;
        toast(`когорта ${date(row.day)}: ${num(row.size)} чел.`);
      });
      this.renderCurves(cohorts);
    } catch (error) {
      setDq('coh-retention-dq', { status: 'empty', note: 'API retention недоступен' });
      $('coh-retention').innerHTML = '<div class="empty">Нет данных — API retention недоступен</div>';
      fail(error);
    }
  }

  renderD(cell) {
    if (!cell) return '—';
    const value = cell.value;
    if (value === null || value === undefined) {
      const note = cell.matured === false
        ? 'milestone не наступил'
        : (cell.method === 'activity_fallback'
          ? 'activity_fallback (BUS-196)'
          : 'данные подчищены ретеншеном (120д)');
      return `<span class="muted small" title="${esc(note)}">∅<span class="sr-only">${esc(note)}</span></span>`;
    }
    const out = `${pct(cell.rate)}`;
    return cell.method === 'activity_fallback'
      ? `${out} <span class="sr-only">(activity_fallback)</span>`
      : out;
  }

  renderCurves(cohorts) {
    if (!cohorts.length) {
      $('coh-curves').innerHTML = '<div class="empty">Нет данных</div>';
      return;
    }
    const series = ['d1', 'd7', 'd30'].map((key) => ({
      key,
      values: cohorts.map((c) => {
        const cell = c[key];
        return (cell && cell.value !== null && cell.matured) ? cell.value : null;
      }),
    }));
    const width = 700;
    const height = 190;
    const pad = { left: 34, right: 8, top: 12, bottom: 20 };
    const flat = series.flatMap((s) => s.values).filter((v) => v !== null);
    const max = Math.max(1, ...flat);
    const x = (i) => pad.left + (i * (width - pad.left - pad.right)) / Math.max(1, cohorts.length - 1);
    const y = (v) => pad.top + (1 - v / max) * (height - pad.top - pad.bottom);
    const colors = { d1: '#7fd8a8', d7: '#e8c56b', d30: '#7fb4e8' };
    const labels = { d1: 'D1', d7: 'D7', d30: 'D30 (activity_fallback)' };
    let svg = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">`;
    for (let g = 0; g <= 3; g++) {
      const gy = pad.top + (g * (height - pad.top - pad.bottom)) / 3;
      svg += `<line x1="${pad.left}" y1="${gy}" x2="${width - pad.right}" y2="${gy}" stroke="rgba(255,255,255,.07)"/>`;
      svg += `<text x="${pad.left - 6}" y="${gy + 3}" text-anchor="end" font-size="9" fill="#9c94bd">${Math.round(max - (g * max) / 3)}%</text>`;
    }
    for (const s of series) {
      const pts = s.values.map((v, i) => v !== null ? `${x(i)},${y(v)}` : null).filter(Boolean).join(' ');
      if (!pts) continue;
      svg += `<polyline points="${pts}" fill="none" stroke="${colors[s.key]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    }
    const step = Math.max(1, Math.ceil(cohorts.length / 7));
    cohorts.forEach((c, i) => {
      if (i % step && i !== cohorts.length - 1) return;
      svg += `<text x="${x(i)}" y="${height - 4}" text-anchor="middle" font-size="9" fill="#9c94bd">${c.day.slice(8, 10)}.${c.day.slice(5, 7)}</text>`;
    });
    svg += '</svg>';
    $('coh-curves').innerHTML = `<div class="chart-legend">${Object.entries(labels).map(([k, l]) => `<span><span class="dot" style="background:${colors[k]}"></span>${l}</span>`).join('')}</div>${svg}`;
  }
}
