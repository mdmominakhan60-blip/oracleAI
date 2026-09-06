/**
 * Admin runtime primitives.
 * Network, state and cross-feature actions are intentionally isolated from
 * feature rendering so new screens do not grow the application shell.
 */

export class AdminApiClient {
  constructor({ telegram = window.Telegram?.WebApp, locationObject = window.location } = {}) {
    this.telegram = telegram;
    this.location = locationObject;
    this.telegram?.ready();
    this.telegram?.expand();
    this.devUser = new URLSearchParams(this.location.search).get('dev_user');
  }

  devHeaders() {
    // DEV_KEY обязателен при DEV_MODE=1 (BUS-90): ключ передают параметром
    // ?dev_key=<key> один раз — он сохраняется в localStorage, и дальнейшие
    // dev-запросы идут с заголовком X-Dev-Key.
    const devKey = new URLSearchParams(this.location.search).get('dev_key');
    if (devKey) {
      try { localStorage.setItem('oracle_dev_key', devKey); } catch { /* приватный режим */ }
      return { 'X-Dev-Key': devKey };
    }
    const stored = localStorage.getItem('oracle_dev_key');
    return stored ? { 'X-Dev-Key': stored } : {};
  }

  async request(path, options = {}) {
    const url = new URL(path, this.location.origin);
    if (this.devUser) url.searchParams.set('dev_user', this.devUser);
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Init-Data': this.telegram?.initData || '',
        ...this.devHeaders(),
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      let detail = `Ошибка ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch { /* non-JSON */ }
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  get(path) { return this.request(path); }
  post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body ?? {}) }); }
  patch(path, body) { return this.request(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) }); }
  delete(path) { return this.request(path, { method: 'DELETE' }); }

  stream(path, signal) {
    const url = new URL(path, this.location.origin);
    if (this.devUser) url.searchParams.set('dev_user', this.devUser);
    return fetch(url, {
      signal,
      headers: {
        'X-Init-Data': this.telegram?.initData || '',
        ...this.devHeaders(),
      },
    });
  }

  async download(path, filename) {
    const url = new URL(path, this.location.origin);
    if (this.devUser) url.searchParams.set('dev_user', this.devUser);
    const response = await fetch(url, {
      headers: {
        'X-Init-Data': this.telegram?.initData || '',
        ...this.devHeaders(),
      },
    });
    if (!response.ok) throw new Error(`Ошибка ${response.status}`);
    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }
}

export class AdminState {
  constructor() {
    this.role = null;
    this.tgId = null;
    this.permissions = [];
    this.period = 30;
    this.demo = false;
    this.view = 'dashboard';
    this.users = { q: '', segment: 'all', order: 'created_at', offset: 0, limit: 50, total: 0 };
    this.segments = [];
    this.content = { kind: '', items: [], current: null };
    this.promoBatch = '';
    this.plans = [];
    // Кросс-экранный переход «карточка churn на „Когортах“ → открытый
    // список сегмента на „Аудитории“» (R2 BUS-168: цифра кликабельна
    // до источника); потребителя гасит сам экран аудитории.
    this.audiencePending = null;
  }

  can(permission) {
    return this.permissions.includes('*') || this.permissions.includes(permission);
  }
}

export class AdminActions {
  constructor() {
    this.openUser = null;
    this.loadCatalog = null;
    this.loadUsers = null;
    this.navigate = null;
  }
}

export const apiClient = new AdminApiClient();
export const state = new AdminState();
export const actions = new AdminActions();
export const tg = apiClient.telegram;
export const DEV_USER = apiClient.devUser;

export const get = (path) => apiClient.get(path);
export const post = (path, body) => apiClient.post(path, body);
export const patch = (path, body) => apiClient.patch(path, body);
export const del = (path) => apiClient.delete(path);
export const downloadAdminFile = (path, filename) => apiClient.download(path, filename);

export const $ = (id) => document.getElementById(id);
export const esc = (value) => {
  const element = document.createElement('div');
  element.textContent = value ?? '';
  return element.innerHTML;
};
export const num = (value) => (value ?? 0).toLocaleString('ru-RU');
export const pct = (value) => `${(value ?? 0).toFixed(1)}%`;
export const date = (iso, withTime = false) => {
  if (!iso) return '—';
  const value = new Date(iso);
  if (Number.isNaN(+value)) return '—';
  return withTime
    ? value.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : value.toLocaleDateString('ru-RU');
};

const STARS_TO_USD = 1 / 52;
export const usd = (stars) => `$${((stars || 0) * STARS_TO_USD).toFixed(0)}`;

let toastTimer;
export function toast(text, bad = false) {
  const element = $('toast');
  if (!element) return;
  element.textContent = text;
  element.className = `toast show${bad ? ' bad' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.className = 'toast'; }, 3600);
}

export function fail(error) {
  toast(error.message || 'Что-то пошло не так', true);
  console.error(error);
}

export function table(columns, rows, options = {}) {
  if (!rows.length) return `<div class="empty">${esc(options.empty || 'Пока пусто')}</div>`;
  const head = columns.map((column) => `<th class="${column.num ? 'num' : ''}">${esc(column.title)}</th>`).join('');
  const body = rows.map((row, index) => {
    const cells = columns.map((column) => `<td class="${column.num ? 'num' : ''}">${column.render(row, index)}</td>`).join('');
    return `<tr class="${options.onRow ? 'clickable' : ''}" data-i="${index}">${cells}</tr>`;
  }).join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

export function bindRows(container, rows, handler) {
  container.querySelectorAll('tbody tr').forEach((row) => {
    row.addEventListener('click', (event) => {
      if (event.target.closest('button,select,input,a')) return;
      handler(rows[+row.dataset.i]);
    });
  });
}

export function fillSegmentSelect(select, segments, labeler) {
  if (!select || select.options.length === segments.length) return;
  select.innerHTML = segments.map((segment) =>
    `<option value="${esc(segment)}">${esc(labeler(segment))}</option>`).join('');
}

export function setViewVisibility(view) {
  document.querySelectorAll('.nav-item').forEach((button) =>
    button.classList.toggle('active', button.dataset.view === view));
  document.querySelectorAll('.view').forEach((element) => element.classList.remove('active'));
  $(`view-${view}`)?.classList.add('active');
  $('view-title').textContent = document.querySelector(`.nav-item[data-view="${view}"]`)?.textContent.trim() || view;
}

export function can(permission) {
  return state.can(permission);
}
