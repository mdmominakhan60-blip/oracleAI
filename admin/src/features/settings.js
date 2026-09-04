import { $, esc, get, post, patch, del, state, table, can, toast, fail } from '../core/runtime.js';

const SETTING_HINTS = {
  'push.morning_hour': 'Час отправки утреннего прогноза (по времени клиентки)',
  'push.weekly_hour': 'Час воскресного отчёта',
  'push.weekly_weekday': '0 — понедельник, 6 — воскресенье',
  'limits.emergency_cost': 'Сколько ✦ стоит вопрос вне лимита',
  'limits.followup_window_minutes': 'Окно уточнений, которые не тратят лимит',
  'referral.bonus': '✦ обеим за приглашение',
  'referral.bonus_level2': '✦ за подругу подруги',
  'referral.revenue_share_crystals': '✦ пригласившей с первой оплаты',
  'broadcast.rate_per_second': 'Темп рассылки (Telegram допускает ~30/с)',
  'brand.bot_username': 'Имя бота без @ — для реферальных ссылок в Mini App',
};

export class SettingsFeature {
  constructor() { $('admin-add').addEventListener('click', () => this.addAdmin()); }

  async load() {
    const [values, flags, admins] = await Promise.all([get('/api/admin/settings'), get('/api/admin/flags'), get('/api/admin/admins')]);
    const editable = can('settings:write');
    $('settings-list').innerHTML = Object.entries(values).sort().map(([key, value]) => `<label>${esc(key)}${SETTING_HINTS[key] ? `<span class="muted small"> — ${esc(SETTING_HINTS[key])}</span>` : ''}<input class="input" data-setting="${esc(key)}" value="${esc(typeof value === 'string' ? value : JSON.stringify(value))}" ${editable ? '' : 'disabled'}></label>`).join('');
    $('settings-list').querySelectorAll('[data-setting]').forEach((element) => element.addEventListener('blur', () => this.saveSetting(element)));
    $('flags-list').innerHTML = flags.map((flag) => `<div class="flag-row"><div class="flag-main"><div class="flag-code">${esc(flag.code)}</div><div class="flag-desc">${esc(flag.description || '')}</div></div><input class="input slim pct" type="number" min="0" max="100" value="${flag.rollout_pct ?? 100}" data-flag-pct="${esc(flag.code)}" ${editable ? '' : 'disabled'} title="Процент раскатки"><label class="switch"><input type="checkbox" ${flag.is_on ? 'checked' : ''} data-flag="${esc(flag.code)}" ${editable ? '' : 'disabled'}><span></span></label></div>`).join('');
    $('flags-list').querySelectorAll('[data-flag]').forEach((element) => element.addEventListener('change', () => this.saveFlag(element.dataset.flag, { is_on: element.checked })));
    $('flags-list').querySelectorAll('[data-flag-pct]').forEach((element) => element.addEventListener('blur', () => this.saveFlag(element.dataset.flagPct, { rollout_pct: +element.value })));
    $('admins-list').innerHTML = table([
      { title: 'id', render: (row) => row.tg_id },
      { title: 'Роль', render: (row) => state.role !== 'owner' || !row.created_at || row.tg_id === state.tgId ? `<span class="badge warn">${esc(row.role)}</span>` : `<select class="input slim" data-role-for="${row.tg_id}">${['analyst', 'support', 'admin', 'owner'].map((role) => `<option value="${role}" ${row.role === role ? 'selected' : ''}>${role}</option>`).join('')}</select>` },
      { title: 'Подпись', render: (row) => esc(row.title || '') },
      { title: '', render: (row) => state.role === 'owner' && row.created_at && row.tg_id !== state.tgId ? `<button class="btn tiny danger" data-rm-admin="${row.tg_id}" type="button">Убрать</button>` : '' },
    ], admins, { empty: 'Только владелец из .env' });
    $('admins-list').querySelectorAll('[data-role-for]').forEach((element) => element.addEventListener('change', async () => { try { await patch(`/api/admin/admins/${element.dataset.roleFor}`, { role: element.value }); toast('Роль обновлена'); } catch (error) { fail(error); await this.load(); } }));
    $('admins-list').querySelectorAll('[data-rm-admin]').forEach((button) => button.addEventListener('click', async () => { if (!confirm('Убрать администратора?')) return; try { await del(`/api/admin/admins/${button.dataset.rmAdmin}`); toast('Убрано'); await this.load(); } catch (error) { fail(error); } }));
  }

  parseValue(raw) {
    if (/^-?\d+(\.\d+)?$/.test(raw)) return Number(raw);
    if (raw === 'true' || raw === 'false') return raw === 'true';
    if (raw.startsWith('[') || raw.startsWith('{')) { try { return JSON.parse(raw); } catch { return raw; } }
    return raw;
  }

  async saveSetting(element) {
    try { await post('/api/admin/settings', { key: element.dataset.setting, value: this.parseValue(element.value) }); toast('Сохранено'); } catch (error) { fail(error); }
  }

  async saveFlag(code, body) { try { await post('/api/admin/flags', { code, ...body }); toast('Сохранено'); } catch (error) { fail(error); } }

  async addAdmin() {
    const tgId = +$('admin-id').value;
    if (!tgId) { toast('Нужен Telegram id', true); return; }
    try { await post('/api/admin/admins', { tg_id: tgId, role: $('admin-role').value, title: $('admin-title').value.trim() }); toast('Добавлен'); $('admin-id').value = ''; $('admin-title').value = ''; await this.load(); } catch (error) { fail(error); }
  }
}
