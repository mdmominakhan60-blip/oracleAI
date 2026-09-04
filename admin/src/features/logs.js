import { $, esc, get, state, apiClient, toast, fail } from '../core/runtime.js';

const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

export class LogsFeature {
  constructor() {
    this.controller = null;
    this.reader = null;
    this.paused = false;
    this.reconnectTimer = null;
    this.bound = false;
  }

  init() {
    if (this.bound) return;
    this.bound = true;
    $('logs-level').innerHTML = LEVELS.map((level) => `<option value="${level}">${level || 'Все уровни'}</option>`).join('');
    $('logs-refresh').addEventListener('click', () => this.refresh().catch(fail));
    $('logs-pause').addEventListener('click', () => this.togglePause());
    $('logs-clear').addEventListener('click', () => this.clear());
    let timer;
    ['logs-level', 'logs-logger', 'logs-query'].forEach((id) => $(id).addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => this.refresh().catch(fail), 250);
    }));
  }

  filters() {
    const params = new URLSearchParams();
    const level = $('logs-level').value;
    const logger = $('logs-logger').value.trim();
    const query = $('logs-query').value.trim();
    if (level) params.set('level', level);
    if (logger) params.set('logger', logger);
    if (query) params.set('query', query);
    return params;
  }

  async refresh() {
    this.stopStream();
    const data = await get(`/api/admin/logs?limit=200&${this.filters()}`);
    this.render(data.entries || []);
    $('logs-buffer').textContent = `${data.count || 0}/${data.buffer_size || 0} записей в буфере`;
    $('logs-status').textContent = 'Подключение…';
    if (!this.paused) this.startStream();
  }

  render(entries) {
    const element = $('logs-list');
    element.innerHTML = entries.length ? entries.map((entry) => this.row(entry)).join('') : '<div class="empty">Логи пока не поступали</div>';
    element.scrollTop = 0;
  }

  append(entry) {
    if (this.paused) return;
    const element = $('logs-list');
    const empty = element.querySelector('.empty');
    if (empty) empty.remove();
    element.insertAdjacentHTML('beforeend', this.row(entry));
    while (element.children.length > 500) element.firstElementChild.remove();
    element.scrollTop = element.scrollHeight;
  }

  row(entry) {
    const fields = Object.entries(entry).filter(([key]) => key !== 'id' && !['ts', 'level', 'logger', 'message'].includes(key)).map(([key, value]) => `${esc(key)}=${esc(typeof value === 'object' ? JSON.stringify(value) : String(value))}`).join(' · ');
    const id = entry.id ? `#${entry.id}` : '';
    return `<div class="log-row log-${String(entry.level || 'INFO').toLowerCase()}" data-log-id="${esc(id)}"><time>${esc(this.time(entry.ts))}</time><span class="log-level">${esc(entry.level || 'INFO')}</span><code>${esc(entry.logger || 'root')}</code><span class="log-message">${esc(entry.message || '')}</span>${fields ? `<span class="log-fields">${fields}</span>` : ''}</div>`;
  }

  time(value) {
    if (!value) return '—';
    const parsed = new Date(value);
    return Number.isNaN(+parsed) ? value : parsed.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  async startStream() {
    this.stopStream(false);
    const controller = new AbortController();
    this.controller = controller;
    try {
      const response = await apiClient.stream(`/api/admin/logs/stream?${this.filters()}`, controller.signal);
      if (!response.ok || !response.body) throw new Error(`Log stream HTTP ${response.status}`);
      $('logs-status').textContent = 'Онлайн';
      this.reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!controller.signal.aborted) {
        const { value, done } = await this.reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';
        frames.forEach((frame) => {
          const data = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('');
          if (!data) return;
          try { const entry = JSON.parse(data); if (entry.id) this.append(entry); } catch { /* malformed frame is ignored */ }
        });
      }
    } catch (error) {
      if (!controller.signal.aborted && this.controller === controller) {
        $('logs-status').textContent = 'Переподключение…';
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => this.startStream(), 2500);
      }
    }
  }

  stopStream(scheduleReconnect = true) {
    const controller = this.controller;
    const reader = this.reader;
    if (controller) controller.abort();
    reader?.cancel().catch(() => {});
    this.controller = null;
    this.reader = null;
    if (!scheduleReconnect) clearTimeout(this.reconnectTimer);
  }

  togglePause() {
    this.paused = !this.paused;
    $('logs-pause').textContent = this.paused ? '▶ Возобновить' : 'Ⅱ Пауза';
    $('logs-pause').setAttribute('aria-pressed', String(this.paused));
    $('logs-status').textContent = this.paused ? 'Пауза' : 'Подключение…';
    if (this.paused) this.stopStream(); else this.startStream();
  }

  clear() {
    $('logs-list').innerHTML = '<div class="empty">Поток очищен на экране. История процесса остаётся в серверном JSONL sink.</div>';
    toast('Отображение очищено');
  }
}
