import {
  $, esc, num, date, pct, get, state, downloadAdminFile, table, toast, fail,
} from '../core/runtime.js';

// Экран R6 «Отзывы» (BUS-168 §R6, BUS-237): NPS-сводка, список ответов
// day-7 опроса с фильтрами, CSV-экспорт агрегатов (free text не выгружается).
// Модерация: LLM-классификация асинхронная — pending до вердикта.

const LIKE_LABELS = {
  forecasts: 'Прогнозы', tarot: 'Таро', diary: 'Дневник',
  voice: 'Голос', chart: 'Натальная карта',
};
const BLOCKER_LABELS = {
  offtopic: 'Не в тему', slow: 'Медленно', paywall: 'Платно',
  lost: 'Потерялась', nothing: 'Всё ок', other: 'Другое',
};
const NEXT_LABELS = {
  compat: 'Совместимость', practices: 'Практики', lunar: 'Лунный ритм',
  personal: 'Личный разбор', other: 'Другое',
};
const MODERATION_LABELS = { pending: 'На проверке', ok: 'Ок', flagged: 'Флаг' };

const FILTER_OPTIONS = {
  like: { labels: LIKE_LABELS, title: 'Понравилось' },
  blocker: { labels: BLOCKER_LABELS, title: 'Помешало' },
  next: { labels: NEXT_LABELS, title: 'Хочется дальше' },
};

function labelOf(map, code) {
  return map[code] || code || '—';
}

function answerOf(row, question) {
  return (row.answers || []).find((entry) => entry.question_code === question) || null;
}

function npsTone(score) {
  if (score === null || score === undefined) return 'muted';
  if (score >= 9) return 'good';
  if (score <= 6) return 'bad';
  return 'warn';
}

function renderNps(nps) {
  const total = nps.nps_responses;
  const score = nps.score;
  $('fb-nps-score').textContent = score === null ? '—' : String(score);
  $('fb-nps-score').className = `fb-nps-score ${npsTone(score)}`;
  $('fb-nps-meta').textContent = score === null
    ? 'пока нет NPS-оценок'
    : `${num(total)} оценок · ${num(nps.promoters)} промоутеров · ${num(nps.passives)} нейтральных · ${num(nps.detractors)} критиков`;
  const max = Math.max(1, nps.promoters, nps.passives, nps.detractors);
  const bars = [
    { key: 'promoters', label: 'Промоутеры 9–10', tone: 'good' },
    { key: 'passives', label: 'Нейтральные 7–8', tone: 'warn' },
    { key: 'detractors', label: 'Критики 0–6', tone: 'bad' },
  ];
  $('fb-nps-bars').innerHTML = bars.map((bar) => `
    <div class="funnel-step">
      <div class="funnel-top">
        <span>${bar.label}</span>
        <span>${num(nps[bar.key])} · ${total ? pct(100 * nps[bar.key] / total) : '—'}</span>
      </div>
      <div class="funnel-bar"><div class="funnel-fill tone-${bar.tone}" style="width:${(100 * nps[bar.key]) / max}%"></div></div>
    </div>`).join('');
}

function renderDistributions(distributions) {
  const titles = {
    like: 'Что понравилось', blocker: 'Что помешало', next: 'Что хочется дальше',
  };
  $('fb-distributions').innerHTML = Object.entries(distributions).map(([question, rows]) => {
    const labels = FILTER_OPTIONS[question]?.labels || {};
    const total = Math.max(1, rows.reduce((sum, entry) => sum + entry.count, 0));
    const sorted = [...rows].sort((a, b) => b.count - a.count);
    return `
      <div class="card-subsection">
        <h4 class="muted">${esc(titles[question] || question)}</h4>
        ${rows.some((entry) => entry.count) ? sorted.map((entry) => `
          <div class="funnel-step">
            <div class="funnel-top">
              <span>${esc(labelOf(labels, entry.choice))}</span>
              <span>${num(entry.count)} · ${pct(100 * entry.count / total)}</span>
            </div>
            <div class="funnel-bar"><div class="funnel-fill" style="width:${(100 * entry.count) / total}%"></div></div>
          </div>`).join('')
        : '<div class="empty">Пока нет ответов</div>'}
      </div>`;
  }).join('');
}

function responseRate(survey) {
  if (survey.response_rate_pct === null || survey.response_rate_pct === undefined) return '—';
  return pct(survey.response_rate_pct);
}

function renderSummary(survey) {
  $('fb-kpi').innerHTML = [
    { label: 'Ответов', value: num(survey.total_responses) },
    { label: 'Приглашено', value: num(survey.invited) },
    { label: 'Response rate', value: responseRate(survey) },
  ].map((kpi) => `<div class="kpi"><span class="kpi-label">${kpi.label}</span><b>${kpi.value}</b></div>`).join('');
  renderNps(survey.nps);
  renderDistributions(survey.distributions || {});
}

function moderationBadge(moderation) {
  const cls = moderation === 'ok' ? 'on' : moderation === 'flagged' ? 'bad' : 'off';
  return `<span class="badge ${cls}">${MODERATION_LABELS[moderation] || moderation}</span>`;
}

export class FeedbackFeature {
  constructor() {
    this.bound = false;
    this.offset = 0;
    this.limit = 50;
    this.total = 0;
  }

  bind() {
    if (this.bound) return;
    this.bound = true;
    const reload = () => {
      this.offset = 0;
      this.loadResponses().catch(fail);
    };
    $('fb-days').addEventListener('change', reload);
    $('fb-moderation').addEventListener('change', reload);
    $('fb-question').addEventListener('change', (event) => {
      this.syncChoiceFilter(event.target.value);
      reload();
    });
    $('fb-choice').addEventListener('change', reload);
    $('fb-text').addEventListener('change', reload);
    $('fb-export').addEventListener('click', () => this.exportCsv());
    $('fb-prev').addEventListener('click', () => {
      this.offset = Math.max(0, this.offset - this.limit);
      this.loadResponses().catch(fail);
    });
    $('fb-next').addEventListener('click', () => {
      this.offset += this.limit;
      this.loadResponses().catch(fail);
    });
  }

  syncChoiceFilter(question) {
    const select = $('fb-choice');
    const wrap = $('fb-choice-wrap');
    const options = FILTER_OPTIONS[question];
    if (!options) {
      wrap.classList.add('hidden');
      select.innerHTML = '';
      select.value = '';
      return;
    }
    wrap.classList.remove('hidden');
    select.innerHTML = `<option value="">Все варианты</option>${Object.entries(options.labels)
      .map(([code, label]) => `<option value="${esc(code)}">${esc(label)}</option>`).join('')}`;
  }

  filters() {
    const query = new URLSearchParams({ days: $('fb-days').value });
    const question = $('fb-question').value;
    const choice = $('fb-choice').value;
    const moderation = $('fb-moderation').value;
    const text = $('fb-text').value.trim();
    if (moderation) query.set('moderation', moderation);
    if (text) query.set('text_query', text);
    if (question) {
      query.set('question', question);
      if (choice) query.set('choice', choice);
    }
    return query;
  }

  async load() {
    this.bind();
    await Promise.all([this.loadSummary(), this.loadResponses()]);
  }

  async loadSummary() {
    try {
      const survey = await get(`/api/admin/feedback/summary?days=${encodeURIComponent($('fb-days').value)}`);
      renderSummary(survey);
    } catch (error) {
      $('fb-kpi').innerHTML = '<div class="empty">Нет данных — API отзывов недоступен</div>';
      fail(error);
    }
  }

  async loadResponses() {
    const query = this.filters();
    query.set('limit', String(this.limit));
    query.set('offset', String(this.offset));
    const data = await get(`/api/admin/feedback/responses?${query}`);
    this.total = data.total;
    $('fb-total').textContent = `найдено: ${num(data.total)}`;
    $('fb-page').textContent = `${data.total ? this.offset + 1 : 0}–${Math.min(this.offset + this.limit, data.total)} из ${num(data.total)}`;
    $('fb-prev').disabled = this.offset === 0;
    $('fb-next').disabled = this.offset + this.limit >= data.total;
    this.renderTable(data.items || []);
  }

  renderTable(items) {
    const element = $('fb-responses');
    element.innerHTML = table([
      { title: 'Дата', render: (row) => date(row.created_at, true) },
      { title: 'Клиентка', render: (row) => `<b>${esc(row.user_name || '—')}</b><div class="muted small">${row.tg_id}</div>` },
      { title: 'NPS', num: true, render: (row) => (row.nps === null || row.nps === undefined
        ? '<span class="muted">—</span>'
        : `<span class="fb-nps-cell tone-${npsTone(row.nps)}">${row.nps}</span>`) },
      { title: 'Понравилось', render: (row) => {
        const answer = answerOf(row, 'like');
        return answer ? esc(labelOf(LIKE_LABELS, answer.choice)) : '—';
      } },
      { title: 'Помешало', render: (row) => {
        const answer = answerOf(row, 'blocker');
        return answer ? esc(labelOf(BLOCKER_LABELS, answer.choice)) : '—';
      } },
      { title: 'Отзыв', render: (row) => (row.free_text
        ? `<div class="fb-quote">${esc(row.free_text)}</div>`
        : '<span class="muted">—</span>') },
      { title: 'Модерация', render: (row) => moderationBadge(row.moderation) },
    ], items, { empty: 'Отзывов по выбранным фильтрам нет' });
  }

  async exportCsv() {
    if (!state.can('dashboard') || !(state.role === 'owner' || state.role === 'admin')) {
      toast('Экспорт доступен владельцу и админу', true);
      return;
    }
    try {
      await downloadAdminFile(`/api/admin/feedback/export?days=${encodeURIComponent($('fb-days').value)}`, 'feedback-day7.csv');
      toast('CSV выгружен — агрегаты без свободного текста');
    } catch (error) {
      fail(error);
    }
  }
}
