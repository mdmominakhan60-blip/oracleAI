import { $, esc, date, get, post, del, state, can, toast, fail } from '../core/runtime.js';

const CONTENT_HINTS = {
  agent: 'Тело — образ и манера речи агента. В meta можно задать rules и tagline.',
  persona: 'Образ Оракула, который выбирает клиентка при знакомстве.',
  guide: 'Правила трактовки: подмешиваются к данным расчёта перед ответом модели.',
  copy: 'Текст сценария. {name} подставляется автоматически.',
  faq: 'Вопрос-ответ для Mini App.',
  spread: 'Свой расклад. В meta обязательно positions: ["Позиция 1", …].',
  practice: 'Практика с трекером дней.',
};

export class ContentFeature {
  constructor() {
    $('content-kind').addEventListener('change', () => { state.content.current = null; this.load().catch(fail); });
    $('content-new').addEventListener('click', () => this.create());
  }

  async load() {
    const kind = $('content-kind').value;
    state.content.kind = kind;
    const items = await get(`/api/admin/content${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`);
    state.content.items = items;
    $('content-list').innerHTML = items.map((item, index) => `<div class="list-item ${state.content.current === index ? 'active' : ''}" data-i="${index}"><div class="li-title">${esc(item.title || item.code)}${item.is_active ? '' : '<span class="badge off">выкл</span>'}</div><div class="li-code">${esc(item.kind)} / ${esc(item.code)}</div></div>`).join('') || '<div class="empty">Нет записей</div>';
    $('content-list').querySelectorAll('.list-item').forEach((element) => element.addEventListener('click', () => this.open(+element.dataset.i)));
    if (items.length) this.open(state.content.current ?? 0);
  }

  open(index) {
    const item = state.content.items[index];
    if (!item) return;
    state.content.current = index;
    $('content-list').querySelectorAll('.list-item').forEach((element) => element.classList.toggle('active', +element.dataset.i === index));
    $('content-editor-title').textContent = `${item.kind} / ${item.code}`;
    const editable = can('content:write');
    $('content-editor').innerHTML = `<p class="muted small">${esc(CONTENT_HINTS[item.kind] || '')}</p><label>Заголовок<input id="c-title" class="input" value="${esc(item.title || '')}"></label><label>Текст<textarea id="c-body" class="input" rows="14">${esc(item.body || '')}</textarea></label><label>meta (JSON)<textarea id="c-meta" class="input" rows="4">${esc(item.meta_json || '')}</textarea></label><div class="row-2 tight"><label class="check"><input type="checkbox" id="c-active" ${item.is_active ? 'checked' : ''}> активна</label><label>Порядок<input id="c-sort" class="input" type="number" value="${item.sort ?? 100}"></label></div><div class="btn-row"><button class="btn gold" id="c-save" type="button" ${editable ? '' : 'disabled'}>Сохранить</button><button class="btn danger" id="c-del" type="button" ${editable ? '' : 'disabled'}>Удалить</button></div><p class="muted small">Обновлено: ${date(item.updated_at, true)}</p>`;
    $('c-save').addEventListener('click', () => this.save(item));
    $('c-del').addEventListener('click', () => this.remove(item));
  }

  async save(item) {
    let meta = null;
    const raw = $('c-meta').value.trim();
    if (raw) { try { meta = JSON.parse(raw); } catch { toast('meta — не корректный JSON', true); return; } }
    try { await post('/api/admin/content', { kind: item.kind, code: item.code, title: $('c-title').value, body: $('c-body').value, meta, is_active: $('c-active').checked, sort: +$('c-sort').value || 100 }); toast('Сохранено'); await this.load(); } catch (error) { fail(error); }
  }

  async remove(item) {
    if (!confirm(`Удалить ${item.kind}/${item.code}?`)) return;
    try { await del(`/api/admin/content/${encodeURIComponent(item.kind)}/${encodeURIComponent(item.code)}`); state.content.current = null; toast('Удалено'); await this.load(); } catch (error) { fail(error); }
  }

  async create() {
    const kind = $('content-kind').value || prompt('Вид (agent, persona, guide, copy, faq, spread, practice)');
    if (!kind) return;
    const code = prompt('Код записи (латиницей, без пробелов)');
    if (!code) return;
    try { await post('/api/admin/content', { kind, code, title: code, body: '' }); $('content-kind').value = kind; state.content.current = null; toast('Создано'); await this.load(); } catch (error) { fail(error); }
  }
}
