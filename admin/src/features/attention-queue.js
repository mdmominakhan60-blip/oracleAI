/**
 * BUS-312 · Очередь внимания (BUS-284 §2) + плейбук-карточки (§3).
 *
 * Принципы (тред BUS-312):
 *  - UI не вычисляет бизнес-логику: приоритеты, SLA, счётчики, каналы —
 *    всё приходит с сервера (app/repo/ltv_tier.py).
 *  - rule/playbook — machine-ключи; человекочитаемые метки здесь (i18n на клиенте).
 *  - Отправка — существующий механизм сообщений; подарок — POST /gift
 *    с machine-ошибками; фиксация обработки — заметка/тег/сообщение.
 */
import { $, esc, num, date, get, post, state, actions, table, bindRows, can, toast, fail } from '../core/runtime.js';

// ── i18n: machine-ключи → человекочитаемые метки (ru) ──────────────────────

export const RULE_LABELS = {
  q1: 'Возврат средств (48 ч)',
  q2: 'VIP уснула',
  q3: 'Оффер не сработал',
  q4: 'Тариф тесен',
  q5: 'Доставка сломалась',
  q6: 'Не завершила знакомство',
  q7: 'Вернулась после паузы',
};

export const PRIORITY_LABELS = {
  p1: 'P1 · 48 ч',
  p2: 'P2 · 7 дн',
  p3: 'P3 · 7 дн',
};

export const TIER_LABELS = {
  A: 'Тир A', B: 'Тир B', C: 'Тир C', D: 'Тир D',
};

export const RISK_FLAG_LABELS = {
  sleeping: 'Спит 14+ дн',
  expiring: 'Подписка истекает',
  limit_hits: 'Лимиты',
  recent_refund: 'Недавний возврат',
};

// Канон ключей копирайта: BUS-293 (принято) + pb5_no_channel (BUS-311).
// Seed-тексты идут через content API; пока ключа нет — карточка показывает
// отредактированный каркас с подстановкой из reason_data (кнопка не блокируется).
const PLAYBOOK_FALLBACKS = {
  'pb-1': 'pb1_vip_sleeping',
  'pb-2': 'pb2_welcome_back',
  'pb-3': 'pb3_offer_unclaimed',
  'pb-4': 'pb4_plan_pain',
  'pb-6': 'pb6_onboard_stuck',
  'pb-7': 'pb7_refund',
};

const PB_NO_CHANNEL = 'pb5_no_channel';

// RU-каркасы из BUS-293 (принято): клиентский копирайт seed-ит Backend
// (kind=copy), пока ключей нет — карточка не остаётся пустой.
// EN — зона Backend seed'а, фронт не дублирует.
const PB_COPY_FALLBACKS = {
  'pb1_vip_sleeping': '{name}, давно не виделись — это {oracle_name} 🌙\n\nЗаметила твою паузу и захотела спросить: всё ли в порядке?\n\nЕсли устала от прогнозов или что-то не устраивает — скажи честно, я подстроюсь. Если просто обстоятельства сложились — тоже напиши, я рядом.\n\nТвоя карта никуда не денется: я сберегла всё, что ты мне рассказывала ✨',
  'pb2_welcome_back': '{name}, как здорово, что ты снова здесь ✨\n\nЧто привело тебя сегодня — нужен совет, или просто заглянула? Расскажи — я слушаю.',
  'pb3_offer_unclaimed': '{name}, мой подарок на прошлой неделе так и остался нераспечатанным 🎁\n\nОн ещё ждёт тебя до {code_until}.\n\nЕсли стало не по карману или что-то разонравилось — просто напиши, найдём решение. Без обид и без уговоров 🌙',
  'pb4_plan_pain': '{name}, за неделю ты {N} упёрлась в лимит — видно, что тебе тесно на тарифе «{plan}» ✨\n\nВ тарифе «{next_plan}» это решается: {diff}.\n\nЗагляни, когда будет настроение: {deep_link}',
  'pb6_onboard_stuck': '{name}, я заметила, что наше знакомство остановилось на середине — и не буду торопить 🌙\n\nНа каком шаге ты застряла? Может, что-то осталось непонятным — или просто сейчас не время. Скажи, как тебе помочь, — или вернись, когда будешь готова ✨',
  'pb7_refund': '{name}, я вижу возврат по твоему платежу 🌙\n\nПрости, что так получилось. Расскажи, что случилось — хочу разобраться и исправить.',
};

// Диффы планов PB-4 (BUS-293 §5, согласованы с PLANS в seed.py)
const PB4_DIFFS = {
  guide_vip: '3 вопроса в день, полная долгая память и все расклады Таро',
  vip_concierge: 'до 30 вопросов в день, приоритетная очередь и аудио-прогнозы',
  free_guide: 'один вопрос каждый день вместо одного в неделю, персональный прогноз дня и дневник со стриком',
};

// Действия §4.2 — существующие механизмы, роль-гейтинг по can().
const MATRIX = [
  { id: 'message', label: 'Написать клиентке', permission: 'crm:write' },
  { id: 'gift', label: 'Подарок (trial)', permission: 'crm:write' },
  { id: 'tag', label: 'Тег', permission: 'crm:write' },
  { id: 'note', label: 'Заметка', permission: 'crm:write' },
];

// Причина/эффект каждого плейбука: какие действия показывает карточка.
const PB_ACTIONS = {
  'pb-1': ['message', 'tag', 'note'],
  'pb-2': ['message', 'note'],
  'pb-3': ['message', 'gift', 'note'],
  'pb-4': ['message', 'note'],
  'pb-5': ['tag', 'note'],
  'pb-6': ['message', 'note'],
  'pb-7': ['message', 'tag', 'note'],
};

const PB_TAGS = {
  'pb-1': 'vip-warmup',
  'pb-5': 'no-channel',
  'pb-7': 'refund',
};

function fillTemplate(text, data) {
  if (!text) return '';
  return text.replace(/\{(\w+)\}/g, (match, key) => {
    if (key === 'N') {
      const count = data.limit_hits_count;
      if (count == null) return match;
      return `${count} ${count === 1 ? 'раз' : 'раза'}`;
    }
    if (key === 'code_until') return data.offer_expires_at ? date(data.offer_expires_at) : 'скоро';
    if (key === 'diff') return data.diff ?? match;
    if (key === 'oracle_name') return data.oracle_name ?? 'Оракул';
    if (key === 'name') return data.display ?? match;
    const value = data[key];
    return value == null ? match : String(value);
  });
}

export class AttentionQueueFeature {
  constructor() {
    this.cards = [];
    this.copy = null;
    actions.openPlaybook = (tgId) => this.openPlaybook(tgId);
  }

  async load() {
    if (!this.copy) this.copy = this.loadCopy();
    const data = await get('/api/admin/attention-queue');
    this.cards = data.items || [];
    this.renderHeader(data);
    this.renderList();
    this.renderOpReport();
  }

  // Тексты плейбуков — content API (kind=copy). Аналитикам content:read
  // доступен по праву; очередь сама по dashboard.
  async loadCopy() {
    try {
      const items = can('content:read') ? await get('/api/admin/content?kind=copy') : [];
      const map = {};
      (items || []).forEach((item) => { map[item.code] = item; });
      return map;
    } catch { return {}; }
  }

  renderHeader(data) {
    const counts = data.counts || {};
    const overdue = data.overdue || {};
    const total = ['p1', 'p2', 'p3'].reduce((sum, p) => sum + (counts[p] || 0), 0);
    const cell = (p) => {
      const value = counts[p] || 0;
      const late = overdue[p] || 0;
      const cls = p === 'p1' ? 'bad' : p === 'p2' ? 'warn' : '';
      return `<div class="kpi ${late ? 'bad' : ''}"><div class="kpi-label">${esc(PRIORITY_LABELS[p])}</div><div class="kpi-value">${num(value)}</div><div class="kpi-sub">${late ? `<span class="badge bad">просрочено: ${num(late)}</span>` : 'в сроке'}</div></div>`;
    };
    $('queue-header').innerHTML = `<div class="queue-summary muted small" aria-live="polite">Всего в очереди: <b>${num(total)}</b>${data.truncated ? ` · показаны первые ${num(data.limit)} карточек` : ''}</div><div class="kpi-grid">${['p1', 'p2', 'p3'].map(cell).join('')}</div>`;
  }

  renderList() {
    const element = $('queue-list');
    if (!this.cards.length) {
      element.innerHTML = '<div class="empty">Очередь пуста — все клиентки в порядке ✨</div>';
      return;
    }
    element.innerHTML = this.cards.map((card, index) => {
      const tierBadge = card.tier ? `<span class="badge">${esc(TIER_LABELS[card.tier] || card.tier)}</span>` : '';
      const channelBadge = card.channel_closed ? '<span class="badge bad">канал закрыт</span>' : '';
      const overdueBadge = card.overdue ? '<span class="badge bad">просрочено по SLA</span>' : '';
      return `<div class="queue-card" data-i="${index}">
        <div class="queue-card-head">
          <button class="queue-open btn ghost" type="button" data-open="${index}"><b>${esc(card.display)}</b><span class="muted small"> id ${num(card.tg_id)}</span></button>
          <span class="queue-card-badges">${tierBadge}${channelBadge}${overdueBadge}</span>
        </div>
        <div class="queue-card-body">
          <span class="badge ${card.priority === 'p1' ? 'bad' : card.priority === 'p2' ? 'warn' : ''}">${esc(PRIORITY_LABELS[card.priority] || card.priority)}</span>
          <span>${esc(RULE_LABELS[card.rule] || card.rule)}</span>
          <button class="btn tiny gold queue-playbook" type="button" data-playbook="${index}">Плейбук ${esc(card.playbook)}</button>
        </div>
        <div class="muted small">сработало: ${date(card.triggered_at, true)} · SLA до ${date(card.sla_due_at, true)}</div>
      </div>`;
    }).join('');
    element.querySelectorAll('[data-playbook]').forEach((button) =>
      button.addEventListener('click', () => this.openPlaybook(this.cards[+button.dataset.playbook])));
    element.querySelectorAll('[data-open]').forEach((button) =>
      button.addEventListener('click', () => actions.openUser((this.cards[+button.dataset.open]).tg_id)));
  }

  // ── Плейбук-карточка (§3): контекст, текст, действия матрицы §4.2 ────────

  async openPlaybook(card) {
    if (!card) return;
    this.currentCard = card;
    let ltv = null;
    try {
      ltv = await get(`/api/admin/users/${encodeURIComponent(card.tg_id)}`);
    } catch { /* карточка плейбука работает и без полного профиля */ }
    const touches = (ltv && ltv.ltv && ltv.ltv.timeline || []).slice(0, 8);
    const pb = card.playbook;
    const isPb5 = pb === 'pb-5';
    const copyKey = isPb5 ? PB_NO_CHANNEL : PLAYBOOK_FALLBACKS[pb];
    const copyItem = this.copy ? this.copy[copyKey] : null;
    const rd = card.reason_data || {};
    // diff для PB-4: free→guide→vip→concierge по плану клиентки
    if (pb === 'pb-4' && rd.plan && rd.next_plan && !rd.diff) rd.diff = PB4_DIFFS[`${rd.plan}_${rd.next_plan}`] || null;
    const templateText = copyItem && copyItem.body
      ? fillTemplate(copyItem.body, { ...rd, display: card.display })
      : PB_COPY_FALLBACKS[copyKey]
        ? fillTemplate(PB_COPY_FALLBACKS[copyKey], { ...rd, display: card.display })
        : null;

    const contextRows = this.contextRows(card);
    const allowedActions = MATRIX.filter((action) =>
      (PB_ACTIONS[pb] || MATRIX.map((a) => a.id)).includes(action.id));

    $('drawer-content').innerHTML = `<div class="u-head"><div class="u-avatar">📋</div><div><div class="u-name">Плейбук ${esc(pb)} · ${esc(card.display)}</div><div class="u-meta">${esc(RULE_LABELS[card.rule] || card.rule)} · ${esc(PRIORITY_LABELS[card.priority] || card.priority)}${card.tier ? ' · ' + esc(TIER_LABELS[card.tier] || card.tier) : ''}</div></div></div>
      <div class="card"><div class="card-head"><h3>Почему здесь</h3></div><div class="context-list">${contextRows}</div></div>
      ${isPb5 ? `<div class="card"><div class="card-head"><h3>Подсказка оператору</h3></div><div class="pb-hint">${templateText ? this.multiline(templateText) : this.multiline(this.pb5Hint())}</div>${can('crm:write') ? `<div class="muted small">Закрыть кейс можно тегом или заметкой — клиентку не дёргать.</div>` : ''}</div>` : templateText ? `<div class="card"><div class="card-head"><h3>Текст клиентке</h3></div>${can('crm:write') ? `<textarea id="pb-text" class="input" rows="8" aria-label="Текст сообщения">${esc(templateText)}</textarea><p class="muted small">Шаблон — каркас: отредактируй перед отправкой. Отправка — тот же механизм, что в карточке клиентки.</p>` : `<div class="pb-hint">${this.multiline(templateText)}</div><p class="muted small">Нужно право admin/owner: <i>crm:write</i> — редактирование и отправка.</p>`}</div>` : ''}
      <div class="card"><div class="card-head"><h3>Действия</h3><span class="muted small">матрица §4.2</span></div><div class="pb-actions">${this.actionsHtml(card, allowedActions)}</div></div>
      <div class="card"><div class="card-head"><h3>Последние касания</h3></div>${touches.length ? `<div class="timeline">${touches.map((item) => this.timelineRow(item)).join('')}</div>` : '<div class="muted small">Касаний не было.</div>'}</div>`;
    $('drawer').classList.remove('hidden');
    this.bindPlaybook(card);
  }

  pb5Hint() {
    return 'forbidden — канал закрыт клиенткой: сообщения не доходят до первой успешной доставки после разблокировки. Действие: тег no-channel.\n\nfailed — временный сбой: планировщик повторит сам, вмешательство не нужно. Действие: наблюдение.\n\nЭскалация DevOps — только при массовом росте failed за короткое окно при обычном объёме.';
  }

  contextRows(card) {
    const rd = card.reason_data || {};
    const rows = [];
    const row = (label, value) => { if (value !== undefined && value !== null && value !== '') rows.push(`<div class="context-row"><span class="muted">${esc(label)}</span><b>${esc(String(value))}</b></div>`); };
    row('Причина', RULE_LABELS[card.rule] || card.rule);
    row('Сработало', date(card.triggered_at, true));
    row('SLA до', date(card.sla_due_at, true));
    if (rd.order_ref) row('Заказ', rd.order_ref);
    if (rd.sleeping_days != null) row('Спит, дней', rd.sleeping_days);
    if (rd.sub_expired_days != null) row('Без подписки, дней', rd.sub_expired_days);
    if (rd.offer_expires_at) row('Оффер истекает', date(rd.offer_expires_at));
    if (rd.limit_hits_count != null) row('Упоров в лимит за 7 дн', rd.limit_hits_count);
    if (rd.plan) row('Тариф', rd.plan);
    if (rd.next_plan) row('Следующий тариф', rd.next_plan);
    if (rd.delivery_status) row('Статус доставки', rd.delivery_status);
    if (rd.delivery_kind) row('Тип доставки', rd.delivery_kind);
    if (rd.error_class) row('Класс ошибки', rd.error_class);
    if (rd.days_since_created != null) row('Дней с регистрации', rd.days_since_created);
    if (rd.o1_sent != null) row('O1 отправлялся', rd.o1_sent ? 'да' : 'нет');
    if (rd.gap_days != null) row('Пауза, дней', rd.gap_days);
    if (card.channel_closed) row('Канал', 'закрыт клиенткой');
    return rows.join('');
  }

  multiline(text) {
    return esc(text).split('\n').map((line) => `<p>${line || '<br>'}</p>`).join('');
  }

  actionsHtml(card, allowed) {
    return allowed.map((action) => {
      const permitted = can(action.permission);
      const tag = PB_TAGS[card.playbook] === 'no-channel' && action.id === 'tag'
        ? `<div class="muted small">тег «no-channel» (канал закрыт, не дёргать)</div>`
        : PB_TAGS[card.playbook] && action.id === 'tag'
          ? `<div class="muted small">рекомендованный тег: «${esc(PB_TAGS[card.playbook])}»</div>`
          : '';
      if (!permitted) {
        return `<div class="pb-action disabled" title="нужно право ${esc(action.permission)}"><span class="btn ghost" aria-disabled="true">${esc(action.label)}</span><span class="muted small">нужно право admin/owner: ${esc(action.permission)}</span>${tag}</div>`;
      }
      return `<div class="pb-action">${this.actionControl(action.id, card)}${tag}</div>`;
    }).join('');
  }

  actionControl(id, card) {
    if (id === 'message') {
      const templateText = this.currentCopyText(card);
      return `${id === 'message' && templateText ? '' : ''}<textarea class="input pb-msg" rows="4" placeholder="Текст клиентке…">${esc(templateText || '')}</textarea><button class="btn gold pb-send" type="button">Отправить в Telegram</button>`;
    }
    if (id === 'gift') return `<button class="btn gold pb-gift" type="button">Выдать подарок</button><span class="pb-gift-state muted small"></span>`;
    if (id === 'tag') return `<button class="btn ghost pb-tag" type="button">Поставить тег${PB_TAGS[card.playbook] ? ` «${esc(PB_TAGS[card.playbook])}»` : ''}</button>`;
    return `<button class="btn ghost pb-note" type="button">Заметка «обработано»</button>`;
  }

  currentCopyText(card) {
    if (card.playbook === 'pb-5') return null;
    const copyItem = this.copy ? this.copy[PLAYBOOK_FALLBACKS[card.playbook]] : null;
    return copyItem && copyItem.body
      ? fillTemplate(copyItem.body, { ...card.reason_data || {}, display: card.display })
      : '';
  }

  bindPlaybook(card) {
    $('drawer-content').querySelectorAll('[data-close-drawer]').forEach(() => {});
    const root = $('drawer-content');
    root.querySelector('.pb-send')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      const text = root.querySelector('.pb-msg').value.trim();
      if (!text) { toast('Пустой текст — нечего отправлять', true); return; }
      button.disabled = true;
      try {
        await post(`/api/admin/users/${card.tg_id}/message`, { text });
        toast('Сообщение отправлено');
        await this.load();
        this.openPlaybook(card);
      } catch (error) { fail(error); } finally { button.disabled = false; }
    });
    root.querySelector('.pb-tag')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      const tag = PB_TAGS[card.playbook] || 'обработано';
      button.disabled = true;
      try {
        await post(`/api/admin/users/${card.tg_id}/tags`, { tag });
        toast(`Тег «${tag}» поставлен`);
        this.openPlaybook(card);
      } catch (error) { fail(error); } finally { button.disabled = false; }
    });
    root.querySelector('.pb-note')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await post(`/api/admin/users/${card.tg_id}/notes`, { text: `Обработано по плейбуку ${card.playbook} (${card.rule})` });
        toast('Заметка добавлена');
        this.openPlaybook(card);
      } catch (error) { fail(error); } finally { button.disabled = false; }
    });
    root.querySelector('.pb-gift')?.addEventListener('click', (event) => this.openGiftForm(card, event.currentTarget));
  }

  // ── Форма подарка (§4): eligibility заранее, machine-коды ошибок ─────────

  async openGiftForm(card, anchor) {
    const holder = anchor?.closest('.pb-action') || $('drawer-content');
    const stateEl = holder.querySelector('.pb-gift-state');
    if (!can('crm:write')) return;
    let eligibility = null;
    try {
      eligibility = await get(`/api/admin/users/${card.tg_id}/gift/eligibility`);
    } catch (error) { fail(error); return; }
    if (!eligibility.eligible) {
      const until = eligibility.next_available_at ? date(eligibility.next_available_at) : 'позже';
      stateEl.innerHTML = `<span class="badge off">подарок недоступен до ${esc(until)}</span>`;
      toast(`Анти-абьюз: окно до ${until}`, true);
      return;
    }
    const daysOptions = eligibility.allowed_days || [];
    const form = document.createElement('div');
    form.className = 'form tight pb-gift-form';
    form.innerHTML = `<div class="row-2 tight"><label>Дней trial<select class="input pb-gift-days" aria-label="Дней триал-подарка">${daysOptions.map((d) => `<option value="${d}">${d} дн</option>`).join('')}</select></label></div><label>Причина (в аудит)<input class="input pb-gift-reason" placeholder="компенсация / жест по плейбуку"></label><div class="btn-row"><button class="btn gold pb-gift-do" type="button">Резервировать код</button><button class="btn ghost pb-gift-cancel" type="button">Отмена</button></div><p class="muted small">Код выдаётся из партии op_* — передай клиентке личным сообщением.</p>`;
    const existing = holder.querySelector('.pb-gift-form');
    if (existing) existing.remove();
    anchor.after(form);
    form.querySelector('.pb-gift-cancel').addEventListener('click', () => form.remove());
    form.querySelector('.pb-gift-do').addEventListener('click', async (event) => {
      const button = event.currentTarget;
      const reason = form.querySelector('.pb-gift-reason').value.trim();
      if (!reason) { toast('Причина обязательна (аудит)', true); return; }
      button.disabled = true;
      try {
        const result = await post(`/api/admin/users/${card.tg_id}/gift`, {
          days: +form.querySelector('.pb-gift-days').value,
          reason,
        });
        toast(`Код ${result.code} (${result.days} дн) — передай клиентке личным сообщением`);
        form.remove();
      } catch (error) {
        // machine-коды ошибок BUS-310 → понятные сообщения без технического стека
        const code = error && error.detail && error.detail.error && error.detail.error.code;
        if (code === 'gift_cooldown') {
          toast('Окно анти-абьюза: второй подарок пока нельзя', true);
        } else if (code === 'gift_batch_empty') {
          toast('Партия кодов исчерпана — попроси admin создать новую', true);
        } else if (code === 'gift_days_not_allowed') {
          toast('Эта длительность недоступна твоей роли', true);
        } else {
          fail(error);
        }
      } finally { button.disabled = false; }
    });
  }

  timelineRow(item) {
    const when = date(item.at, true);
    const icon = item.kind === 'auto' ? '🤖' : '✋';
    const label = item.type === 'delivery' ? 'Доставка' : item.type === 'note' ? 'Заметка' : item.type === 'message' ? 'Сообщение' : item.type;
    const status = item.status ? `<span class="badge ${item.status === 'sent' ? 'on' : item.status === 'failed' ? 'bad' : item.status === 'forbidden' ? 'warn' : 'off'}">${esc(this.deliveryStatusLabel(item.status))}</span>` : '';
    return `<div><b>${icon} ${esc(label)}</b> ${status}<span class="muted small">${esc(item.key || '')}</span><div class="t-when">${when}</div></div>`;
  }

  deliveryStatusLabel(status) {
    return ({ sent: 'доставлено', failed: 'сбой', forbidden: 'канал закрыт' }[status] || status);
  }

  // ── Месячный отчёт партий op_* (§5) ──────────────────────────────────────

  async renderOpReport() {
    const element = $('queue-opreport');
    if (!element) return;
    try {
      const data = await get('/api/admin/promo/op-report?months=6');
      element.innerHTML = `<div class="card-head"><h3>Партии подарков op_* — 6 мес</h3></div>${table([
        { title: 'Партия', render: (row) => esc(row.batch) },
        { title: 'Дней', num: true, render: (row) => num(row.days) },
        { title: 'Кодов', num: true, render: (row) => num(row.codes) },
        { title: 'Активаций', num: true, render: (row) => num(row.redeemers) },
        { title: 'Redemption', num: true, render: (row) => (row.redemption_rate * 100).toFixed(1) + '%' },
        { title: 'Конверсия в оплату', num: true, render: (row) => (row.conversion_rate * 100).toFixed(1) + '%' },
      ], data.batches || [], { empty: 'Партий op_* пока не было' })}`;
    } catch (error) {
      // право dashboard есть у всех операционных ролей; без права — тихо
      element.innerHTML = `<div class="card-head"><h3>Партии подарков op_*</h3></div><div class="muted small">нужно право admin/owner: dashboard</div>`;
    }
  }
}
