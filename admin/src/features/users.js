import { $, esc, num, date, get, post, del, state, actions, table, bindRows, fillSegmentSelect, can, toast, fail } from '../core/runtime.js';
import { RULE_LABELS, TIER_LABELS, RISK_FLAG_LABELS } from './attention-queue.js';

// Метки единого таймлайна card.ltv (BUS-309 §6): kind auto = доставки,
// manual = заметки/сообщения оператора.
const TL_TYPE_LABELS = { delivery: 'доставка', note: 'заметка', message: 'сообщение' };
const TL_STATUS_LABELS = { sent: 'доставлено', forbidden: 'канал закрыт', failed: 'ошибка' };

export function segmentLabel(code) {
  return ({
    all: 'Все', active_sub: 'С подпиской', expired: 'Без подписки', onboarded: 'Прошли знакомство',
    not_onboarded: 'Не дошли до конца', paying: 'Платящие', never_paid: 'Ни разу не платили',
    push_on: 'С утренним прогнозом', active_7d: 'Активны за 7 дней', sleeping_14d: 'Спят 14+ дней',
    expiring_3d: 'Подписка кончается за 3 дня',
    // CRM-предикаты BUS-230 (рамка BUS-169 §1): появляются в /api/admin/users
    // и /api/admin/audience/segments — сырой код в дропдауне недопустим.
    onboarded_unactivated: 'Прошли знакомство, без практики',
    first_value: 'Получили первую ценность',
    cancelled_recent: 'Отменились за 30 дней',
    paying_pack: 'Платили без активной подписки',
    daily_user: 'Активны 5+ дней за неделю',
    weekly_user: 'События за 7 дней',
    ritual_streak_3plus: 'Стрик практик 3+',
    limit_hitters: 'Упирались в лимит',
    sleeping_14d_push: 'Спят 14+ дней с прогнозом',
  }[code] || code);
}

export class UsersFeature {
  constructor() {
    this.searchTimer = null;
    actions.openUser = (tgId) => this.open(tgId);
    actions.loadUsers = () => this.load();
    $('user-q').addEventListener('input', (event) => {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => {
        state.users.q = event.target.value.trim();
        state.users.offset = 0;
        this.load().catch(fail);
      }, 350);
    });
    $('user-segment').addEventListener('change', (event) => {
      state.users.segment = event.target.value;
      state.users.offset = 0;
      this.load().catch(fail);
    });
    $('user-order').addEventListener('change', (event) => {
      state.users.order = event.target.value;
      this.load().catch(fail);
    });
    $('users-prev').addEventListener('click', () => {
      state.users.offset = Math.max(0, state.users.offset - state.users.limit);
      this.load().catch(fail);
    });
    $('users-next').addEventListener('click', () => {
      state.users.offset += state.users.limit;
      this.load().catch(fail);
    });
    document.querySelectorAll('[data-close]').forEach((element) => element.addEventListener('click', () => $('drawer').classList.add('hidden')));
  }

  async load() {
    const query = new URLSearchParams({ q: state.users.q, segment: state.users.segment, order: state.users.order, limit: String(state.users.limit), offset: String(state.users.offset) });
    const data = await get(`/api/admin/users?${query}`);
    state.users.total = data.total;
    state.segments = data.segments;
    fillSegmentSelect($('user-segment'), data.segments, segmentLabel);
    fillSegmentSelect($('bc-segment'), data.segments, segmentLabel);
    $('user-segment').value = state.users.segment;
    $('user-total').textContent = `найдено: ${num(data.total)}`;
    $('users-page').textContent = `${data.total ? state.users.offset + 1 : 0}–${Math.min(state.users.offset + state.users.limit, data.total)} из ${num(data.total)}`;
    $('users-prev').disabled = state.users.offset === 0;
    $('users-next').disabled = state.users.offset + state.users.limit >= data.total;
    const element = $('users-table');
    element.innerHTML = table([
      { title: 'Клиентка', render: (row) => `<b>${esc(row.name || '—')}</b><div class="muted small">${row.username ? '@' + esc(row.username) : row.tg_id}</div>` },
      { title: 'Тариф', render: (row) => row.sub_active ? `<span class="badge on">${esc(row.sub_level)}</span>` : '<span class="badge off">нет</span>' },
      { title: 'Теги', render: (row) => (row.tags || []).map((tag) => `<span class="badge tag">${esc(tag)}</span>`).join(' ') },
      { title: '✦', num: true, render: (row) => num(row.crystals) },
      { title: 'Stars', num: true, render: (row) => num(row.ltv_stars) },
      { title: 'Была', render: (row) => date(row.last_seen, true) },
      { title: 'Пришла', render: (row) => date(row.created_at) },
    ], data.items, { onRow: true, empty: 'Никого не нашлось' });
    bindRows(element, data.items, (row) => this.open(row.tg_id));
  }

  async open(tgId) {
    const card = await get(`/api/admin/users/${encodeURIComponent(tgId)}`);
    const user = card.user;
    const sun = card.chart?.sun;
    const tabs = [['profile', 'Профиль'], ['chats', 'Диалоги'], ['money', 'Платежи'], ['memory', 'Память'], ['activity', 'События'], ['ltv', 'LTV'], ['actions', 'Действия']];
    $('drawer-content').innerHTML = `<div class="u-head"><div class="u-avatar">${esc(sun?.symbol || '🔮')}</div><div><div class="u-name">${esc(user.name || 'без имени')} ${card.sub_active ? `<span class="badge on">${esc(user.sub_level)}</span>` : '<span class="badge off">без подписки</span>'}</div><div class="u-meta">${user.username ? '@' + esc(user.username) + ' · ' : ''}id ${user.tg_id} · с ${date(user.created_at)}${user.source ? ' · ' + esc(user.source) : ''}</div></div></div>
      <div class="u-stats"><div class="u-stat"><b>${num(user.crystals)}</b><span>Кристаллы ✦</span></div><div class="u-stat"><b>${num(card.sub_days_left)}</b><span>дней подписки</span></div><div class="u-stat"><b>${num(user.ltv_stars)}</b><span>Stars всего</span></div><div class="u-stat"><b>${num(card.questions_today)}</b><span>вопросов сегодня</span></div><div class="u-stat"><b>${num(card.diary_streak)}</b><span>стрик дневника</span></div><div class="u-stat"><b>${num(card.referrals.level1)}</b><span>привела подруг</span></div></div>
      <div class="chip-row" id="u-tags">${(card.tags || []).map((tag) => `<span class="badge tag">${esc(tag)} <a href="#" data-untag="${esc(tag)}" aria-label="Удалить тег ${esc(tag)}">✕</a></span>`).join(' ')}${can('crm:write') ? '<button class="btn tiny ghost" id="u-add-tag" type="button">+ тег</button>' : ''}</div>
      <div class="u-tabs">${tabs.map(([key, label], index) => `<button class="u-tab ${index === 0 ? 'active' : ''}" data-pane="${key}" type="button">${label}</button>`).join('')}</div>
      <div class="u-pane active" data-pane="profile">${this.profilePane(card, user)}</div>
      <div class="u-pane" data-pane="chats">${this.chatsPane(card)}</div>
      <div class="u-pane" data-pane="money">${this.moneyPane(card)}</div>
      <div class="u-pane" data-pane="memory">${(card.memories || []).length ? `<div class="timeline">${card.memories.map((item) => `<div>${esc(item.fact)} <span class="badge">${esc(item.kind)}</span><div class="t-when">${date(item.created_at, true)}</div></div>`).join('')}</div>` : '<div class="muted small">Память пуста</div>'}</div>
      <div class="u-pane" data-pane="activity"><div class="timeline">${(card.events || []).map((item) => `<div><b>${esc(item.name)}</b> ${esc(item.surface || '')}${item.props_json ? `<span class="muted small">${esc(item.props_json)}</span>` : ''}<div class="t-when">${date(item.created_at, true)}</div></div>`).join('') || '<div class="muted small">Событий нет</div>'}</div></div>
      <div class="u-pane" data-pane="ltv">${this.ltvPane(card, user)}</div>
      <div class="u-pane" data-pane="actions">${this.actionsPane(user)}</div>`;
    $('drawer').classList.remove('hidden');
    this.bindCard(tgId, user);
    this.loadGiftForm(tgId);
  }

  profilePane(card, user) {
    return `<table><tr><th>Рождение</th><td>${esc(user.birth_date || '—')} ${esc(user.birth_time || '')} ${user.birth_time_known ? '' : '<span class="badge">время неточное</span>'}</td></tr><tr><th>Город</th><td>${esc(user.birth_city || '—')} · ${esc(user.tz || '')}</td></tr><tr><th>Солнце</th><td>${card.chart?.sun ? esc(`${card.chart.sun.sign} (${card.chart.sun.element})`) : '—'} · режим карты: ${esc(card.chart?.mode || '—')}</td></tr><tr><th>Оракул</th><td>${esc(user.oracle_name || '—')} · образ ${esc(user.persona || '—')}</td></tr><tr><th>Тариф</th><td>${esc(card.plan?.title || user.sub_level || '—')} · до ${date(user.sub_until, true)}</td></tr><tr><th>Права</th><td>${(card.entitlements || []).map((item) => `<span class="badge warn">${esc(item.kind)}:${esc(item.code || '*')} ×${item.qty_total - item.qty_used}</span>`).join(' ') || '—'}</td></tr></table><h3 style="margin:16px 0 8px">Заметки</h3><div id="u-notes">${(card.notes || []).map((item) => `<div class="timeline"><div>${esc(item.text)}<div class="t-when">${date(item.created_at, true)}</div></div></div>`).join('') || '<div class="muted small">Заметок нет</div>'}</div>${can('crm:write') ? '<div class="form tight"><textarea id="u-note-text" class="input" rows="2" placeholder="Что важно помнить об этой клиентке…"></textarea><button class="btn ghost" id="u-note-add" type="button">Добавить заметку</button></div>' : ''}`;
  }

  chatsPane(card) {
    return `${(card.threads || []).map((item) => `<div class="muted small">${esc(item.agent)} · ${num(item.msg_count)} сообщений · ${date(item.last_at, true)}</div>`).join('')}<h3 style="margin:12px 0 8px">Расклады</h3>${table([{ title: 'Расклад', render: (row) => esc(row.spread || row.question || '—') }, { title: 'Карты', render: (row) => esc((row.cards || []).map((item) => item.name).join(', ').slice(0, 60)) }, { title: 'Сбылось', render: (row) => row.outcome ? `<span class="badge on">${esc(row.outcome)}</span>` : '—' }, { title: 'Когда', render: (row) => date(row.created_at) }], card.readings || [], { empty: 'Раскладов не было' })}<h3 style="margin:12px 0 8px">Разборы</h3>${table([{ title: 'Разбор', render: (row) => esc(row.title) }, { title: 'Период', render: (row) => esc(row.period || '—') }, { title: 'Когда', render: (row) => date(row.created_at) }], card.reports || [], { empty: 'Разборов не покупала' })}`;
  }

  moneyPane(card) {
    return `${table([{ title: 'Заказ', render: (row) => esc(row.title || row.sku || row.kind) }, { title: 'Stars', num: true, render: (row) => num(row.amount_stars) }, { title: '✦', num: true, render: (row) => num(row.amount_crystals) }, { title: 'Статус', render: (row) => `<span class="badge ${row.status === 'paid' ? 'on' : row.status === 'refunded' ? 'bad' : 'off'}">${esc(row.status)}</span>` }, { title: 'Когда', render: (row) => date(row.paid_at || row.created_at, true) }], card.orders || [], { empty: 'Покупок не было' })}<h3 style="margin:12px 0 8px">Кристаллы</h3>${table([{ title: 'Δ', num: true, render: (row) => (row.delta > 0 ? '+' : '') + num(row.delta) }, { title: 'Причина', render: (row) => esc(row.reason) }, { title: 'Баланс', num: true, render: (row) => num(row.balance) }, { title: 'Когда', render: (row) => date(row.created_at, true) }], card.crystals_history || [], { empty: 'Движений не было' })}`;
  }

  // LTV-блок (BUS-312): тир, метрики, риск-флаги, next_best_action, таймлайн.
  // card.ltv === null для синтетики — нейтральное пустое состояние без PII.
  ltvPane(card) {
    const ltv = card.ltv;
    if (!ltv) return '<div class="muted small">LTV-данных нет</div>';
    const tierBadge = ltv.tier ? `<span class="badge on">${esc(TIER_LABELS[ltv.tier] || ltv.tier)}</span>` : '<span class="badge off">вне тира</span>';
    const flags = (ltv.risk_flags || []).map((flag) => `<span class="badge bad">${esc(RISK_FLAG_LABELS[flag] || flag)}</span>`);
    if (ltv.channel_closed) flags.push('<span class="badge bad">канал закрыт</span>');
    const nba = ltv.next_best_action
      ? `<b>${esc(RULE_LABELS[ltv.next_best_action.rule] || ltv.next_best_action.rule)} · плейбук ${esc(ltv.next_best_action.playbook)}</b>`
      : '<span class="muted small">правил не сработало</span>';
    const timeline = (ltv.timeline || []).map((item) => {
      const status = item.status ? ` <span class="badge ${item.status === 'sent' ? 'on' : 'bad'}">${esc(TL_STATUS_LABELS[item.status] || item.status)}</span>` : '';
      const text = item.text ? ` — ${esc(item.text)}` : '';
      return `<div><b>${item.kind === 'auto' ? '🤖' : '👤'} ${esc(TL_TYPE_LABELS[item.type] || item.type)}</b>${status}${text}<div class="t-when">${esc(item.key || '')} · ${date(item.at, true)}</div></div>`;
    }).join('');
    return `<div class="queue-summary">${tierBadge}</div>
      <div class="u-stats">
        <div class="u-stat"><b>${num(ltv.ltv_stars)}</b><span>Stars всего</span></div>
        <div class="u-stat"><b>${num(ltv.payments_count)}</b><span>платежей</span></div>
        <div class="u-stat"><b>${num(ltv.avg_check_stars)}</b><span>средний чек</span></div>
        <div class="u-stat"><b>${ltv.days_as_payer == null ? '—' : num(ltv.days_as_payer)}</b><span>дней платит</span></div>
        <div class="u-stat"><b>+${num(ltv.crystals_bought)}</b><span>✦ куплено</span></div>
        <div class="u-stat"><b>+${num(ltv.crystals_granted)}</b><span>✦ выдано</span></div>
      </div>
      <div class="chip-row">${flags.join(' ') || '<span class="muted small">риск-флагов нет</span>'}</div>
      <h3 style="margin:14px 0 6px">Что сделать</h3>
      <div class="context-row"><span>Рекомендуется</span>${nba}</div>
      <h3 style="margin:14px 0 6px">История касаний</h3>
      <div class="timeline">${timeline || '<div class="muted small">Касаний нет</div>'}</div>`;
  }

  actionsPane(user) {
    return `${can('grants') ? `<div class="card"><div class="card-head"><h3>Выдать</h3></div><div class="form"><div class="row-2 tight"><label>Что<select id="g-kind" class="input"><option value="plan">Подписку</option><option value="crystals">Кристаллы ✦</option><option value="spread">Право на расклад</option><option value="report">Право на разбор</option><option value="question">Вопросы</option></select></label><label>Код / SKU<input id="g-code" class="input" placeholder="vip, celtic, natal…"></label></div><div class="row-2 tight"><label>Количество<input id="g-qty" class="input" type="number" value="1" min="1"></label><label>Дней<input id="g-days" class="input" type="number" placeholder="по умолчанию"></label></div><label>Причина (в аудит)<input id="g-reason" class="input" placeholder="компенсация за сбой"></label><button class="btn gold" id="g-do" type="button">Выдать</button></div></div>` : ''}${can('crm:write') ? '<div class="card"><div class="card-head"><h3>Написать клиентке</h3></div><div class="form"><textarea id="m-text" class="input" rows="4" placeholder="Здравствуйте! Мы разобрались с вашим вопросом…"></textarea><button class="btn ghost" id="m-send" type="button">Отправить в Telegram</button></div></div>' : ''}${can('crm:write') ? `<div class="card" id="gift-card"><div class="card-head"><h3>Подарок (промокод)</h3></div><div class="form" id="gift-body"><div class="muted small">Проверяем доступность…</div></div></div>` : ''}${can('users:write') ? `<div class="card"><div class="card-head"><h3>Доступ</h3></div><div class="btn-row"><button class="btn ${user.status === 'blocked' ? '' : 'danger'}" id="u-status" type="button">${user.status === 'blocked' ? 'Разблокировать' : 'Заблокировать'}</button>${state.role === 'owner' ? '<button class="btn danger" id="u-anon" type="button">Удалить данные</button>' : ''}</div><p class="muted small" style="margin-top:8px">Блокировка закрывает доступ к API и боту. Удаление данных стирает PII и историю, финансовый след остаётся.</p></div>` : ''}`;
  }

  // Подарок из партии op_* (BUS-284 §4.1): pre-check eligibility строит форму
  // заранее; machine-ошибки бэкенда (gift_cooldown, gift_batch_empty,
  // gift_days_not_allowed) рендерим по code, не по тексту ответа.
  async loadGiftForm(tgId) {
    const body = $('gift-body');
    if (!body) return;
    let eligibility;
    try {
      eligibility = await get(`/api/admin/users/${encodeURIComponent(tgId)}/gift/eligibility`);
    } catch (error) {
      body.innerHTML = '<div class="muted small">Подарки недоступны</div>';
      return;
    }
    if (!eligibility.eligible && !eligibility.cooldown) {
      body.innerHTML = '<div class="muted small">Ваша роль не может выдавать подарки</div>';
      return;
    }
    if (eligibility.cooldown) {
      const until = eligibility.next_available_at ? date(eligibility.next_available_at, true) : '—';
      body.innerHTML = `<div class="muted small">Кулдаун: следующий подарок можно выдать ${esc(until)}</div>`;
      return;
    }
    const options = (eligibility.allowed_days || []).map((days) => `<option value="${days}">${days} дн</option>`).join('');
    body.innerHTML = `<div class="row-2 tight"><label>Срок<select id="gf-days" class="input">${options}</select></label></div><label>Причина (обязательна, в аудит)<input id="gf-reason" class="input" placeholder="компенсация за сбой доставки"></label><button class="btn gold" id="gf-do" type="button">Выдать промокод</button>`;
    $('gf-do')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      const reason = $('gf-reason').value.trim();
      if (!reason) { toast('Укажите причину — она попадёт в аудит', true); return; }
      button.disabled = true;
      try {
        const granted = await post(`/api/admin/users/${encodeURIComponent(tgId)}/gift`, { days: +$('gf-days').value, reason });
        body.innerHTML = `<div class="muted small">Выдан код на ${granted.days} дн. Передайте его клиентке в личном сообщении:</div><div class="pb-msg"><code>${esc(granted.code)}</code></div>`;
        toast('Промокод зарезервирован');
      } catch (error) {
        button.disabled = false;
        const code = error?.data?.error?.code || error?.code;
        if (code === 'gift_cooldown') {
          body.innerHTML = '<div class="muted small">Кулдаун: у этой клиентки уже был подарок недавно. Повторите позже.</div>';
        } else if (code === 'gift_batch_empty') {
          body.innerHTML = '<div class="muted small">Партия промокодов исчерпана — пополните партию op_*.</div>';
        } else if (code === 'gift_days_not_allowed') {
          body.innerHTML = '<div class="muted small">Ваша роль не может выдавать подарок такого размера.</div>';
        } else {
          fail(error);
        }
      }
    });
  }

  bindCard(tgId, user) {
    const root = $('drawer-content');
    root.querySelectorAll('.u-tab').forEach((button) => button.addEventListener('click', () => {
      root.querySelectorAll('.u-tab').forEach((item) => item.classList.toggle('active', item === button));
      root.querySelectorAll('.u-pane').forEach((pane) => pane.classList.toggle('active', pane.dataset.pane === button.dataset.pane));
    }));
    root.querySelectorAll('[data-untag]').forEach((link) => link.addEventListener('click', async (event) => {
      event.preventDefault();
      try { await del(`/api/admin/users/${tgId}/tags/${encodeURIComponent(link.dataset.untag)}`); await this.open(tgId); } catch (error) { fail(error); }
    }));
    $('u-add-tag')?.addEventListener('click', async () => {
      const tag = prompt('Тег (например: vip, вернуть, конфликт)');
      if (!tag) return;
      try { await post(`/api/admin/users/${tgId}/tags`, { tag }); await this.open(tgId); } catch (error) { fail(error); }
    });
    $('u-note-add')?.addEventListener('click', async () => {
      const text = $('u-note-text').value.trim();
      if (!text) return;
      try { await post(`/api/admin/users/${tgId}/notes`, { text }); toast('Заметка сохранена'); await this.open(tgId); } catch (error) { fail(error); }
    });
    $('g-do')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try { const granted = await post(`/api/admin/users/${tgId}/grant`, { kind: $('g-kind').value, code: $('g-code').value.trim() || null, qty: +$('g-qty').value || 1, days: +$('g-days').value || null, reason: $('g-reason').value.trim() }); toast(`Выдано: ${granted.title || granted.kind}`); await this.open(tgId); } catch (error) { fail(error); } finally { button.disabled = false; }
    });
    $('m-send')?.addEventListener('click', async (event) => {
      const text = $('m-text').value.trim();
      if (!text) return;
      event.currentTarget.disabled = true;
      try { await post(`/api/admin/users/${tgId}/message`, { text }); toast('Сообщение отправлено'); await this.open(tgId); } catch (error) { fail(error); } finally { event.currentTarget.disabled = false; }
    });
    $('u-status')?.addEventListener('click', async () => {
      const next = user.status === 'blocked' ? 'active' : 'blocked';
      if (next === 'blocked' && !confirm('Закрыть доступ этой клиентке?')) return;
      try { await post(`/api/admin/users/${tgId}/status`, { status: next }); toast(next === 'blocked' ? 'Доступ закрыт' : 'Доступ открыт'); await this.open(tgId); await this.load(); } catch (error) { fail(error); }
    });
    $('u-anon')?.addEventListener('click', async () => {
      if (!confirm('Стереть персональные данные и историю? Отменить нельзя.')) return;
      try { await post(`/api/admin/users/${tgId}/anonymize`); toast('Данные удалены'); $('drawer').classList.add('hidden'); await this.load(); } catch (error) { fail(error); }
    });
  }
}
