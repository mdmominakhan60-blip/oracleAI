/* chat: чат-агент, сессии, лунная неделя, тулбокс, отправка */
const CHAT_I18N = {
  ru: {
    back: 'Вернуться к проводникам', toGuides: 'К проводникам', space: 'Пространство', myChats: 'МОИ ЧАТЫ', chats: 'чатов', newChat: 'Новый чат', startChat: 'Начать новый чат',
    myChatsAria: 'Открыть мои чаты', conversations: 'Твои разговоры', sessionCopy: 'каждый чат хранит свой контекст', deleteChat: 'Удалить этот чат', deleteChatTitle: 'Удалить чат', deleteAllChats: 'Удалить все чаты', deleteAllChatsCopy: 'Память и сохранённые факты останутся', deleteAllChatsConfirm: 'Удалить все чаты? Сообщения будут убраны из списка, но память сохранится.', chatsCleared: 'Все чаты удалены из списка. Память сохранена.',
    firstConversation: 'Первый разговор создастся, когда ты отправишь сообщение.', continueDialog: 'Здесь можно продолжить диалог.', chooseGuide: 'Выбор проводника', presence: 'рядом', addPalm: 'Добавить фото ладони', palmPhoto: 'Фото ладони', tools: 'Инструменты',
    messageFor: 'Сообщение для', stop: 'Остановить запрос', send: 'Отправить сообщение', ideas: 'Идеи для своего вопроса', toolAria: 'Инструменты текущего проводника', toolsEyebrow: 'ИНСТРУМЕНТЫ ДИАЛОГА', toolsTitle: 'С чем поработаем?', toolsIntro: 'Выбери один точный шаг — результат появится прямо в этом разговоре.', closeTools: 'Закрыть инструменты', withGuide: 'С', inDialog: 'в этом диалоге',
    deleteAllChatsTitle: 'Удалить все чаты', deleteAllChatsConfirmBtn: 'Удалить все', newChatTitle: 'Новый чат', newChatConfirm: 'Начать новый чат с чистого листа? Текущий диалог будет удалён из списка.', newChatConfirmBtn: 'Начать заново',
  },
  en: {
    back: 'Back to guides', toGuides: 'Back to guides', space: 'Workspace', myChats: 'MY CHATS', chats: 'chats', newChat: 'New chat', startChat: 'Start a new chat',
    myChatsAria: 'Open my chats', conversations: 'Your conversations', sessionCopy: 'each chat keeps its own context', deleteChat: 'Delete this chat', deleteChatTitle: 'Delete chat', deleteAllChats: 'Delete all chats', deleteAllChatsCopy: 'Memory and saved facts stay safe', deleteAllChatsConfirm: 'Delete all chats? Messages will leave the list, but your memory will stay.', chatsCleared: 'All chats removed from the list. Memory preserved.',
    firstConversation: 'Your first conversation will appear when you send a message.', continueDialog: 'Continue the conversation here.', chooseGuide: 'Choose a guide', presence: 'here', addPalm: 'Add a palm photo', palmPhoto: 'Palm photo', tools: 'Tools',
    messageFor: 'Message for', stop: 'Stop request', send: 'Send message', ideas: 'Ideas for your question', toolAria: 'Tools for this guide', toolsEyebrow: 'DIALOGUE TOOLS', toolsTitle: 'What would you like to explore?', toolsIntro: 'Choose one focused step — the result will appear in this conversation.', closeTools: 'Close tools', withGuide: 'With', inDialog: 'in this conversation',
    deleteAllChatsTitle: 'Delete all chats', deleteAllChatsConfirmBtn: 'Delete all', newChatTitle: 'New chat', newChatConfirm: 'Start a new chat with a clean slate? The current conversation will be removed from the list.', newChatConfirmBtn: 'Start fresh',
  },
};
const CHAT_AGENT_EN = {
  oracle: { name: 'Lilith', title: 'Personal Oracle' },
  astro: { name: 'Urania', title: 'Astrologer' },
  tarot: { name: 'Madame Lenormand', title: 'Tarot reader' },
  chiromant: { name: 'Mira', title: 'Palm guide' },
};
const CHAT_SUGGESTIONS_EN = {
  oracle: ['Help me sort through what I feel today.', 'What is one gentle step I can take?', 'Help me name what matters right now.'],
  astro: ['What does my chart say about my strengths?', 'Explain my current rhythm through the chart.', 'What can I notice about my Moon and Venus?'],
  tarot: ['What matters most to notice in this situation?', 'How can I move gently in this relationship?', 'Where should I place my energy this week?'],
  chiromant: ['Can you check the quality of my palm photo?', 'Show me the visible zones of my palm.', 'Compare my two palm readings without fate claims.'],
};
const chatLang = () => oracleLang() === 'en' ? 'en' : 'ru';
const chatT = (key, fallback = '') => CHAT_I18N[chatLang()][key] || fallback || key;
const chatCount = count => {
  const n = Number(count) || 0;
  if (chatLang() === 'en') return `${n} ${n === 1 ? 'chat' : 'chats'}`;
  const mod10 = n % 10;
  const mod100 = n % 100;
  const noun = mod10 === 1 && mod100 !== 11 ? 'чат' : mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20) ? 'чата' : 'чатов';
  return `${n} ${noun}`;
};
const chatAgentField = (agent, field) => (chatLang() === 'en' ? CHAT_AGENT_EN[agent.code]?.[field] : '') || agent[field] || '';

  app.openChat = function(key, after) {
    haptic('soft');
    // Панель инструментов не должна оставаться поверх нового диалога.
    if (typeof this.setToolbox === 'function') this.setToolbox(false);
    if (this.chat.key !== key) {
      this.chat.key = key;
      this.chat.spec = this.agentSpec(key);
      this.chat.messages = [];
      this.chat.pending = null;
      this.chat.tid = null;
      this.chat.sessions = [];
      this.loadThread(key);
    }
    this.view = 'hub';
    this.renderNav();
    if (typeof this.syncBackButton === 'function') this.syncBackButton();
    this.renderChat(document.getElementById('app-main'));
    if (after) setTimeout(after, 60);
    this.maybeChatGuide();
  };

  // список чатов-сессий агента; лимита количества нет

  app.refreshSessions = async function() {
    try { this.chat.sessions = await api('/api/chat/' + this.chat.key + '/sessions'); }
    catch (e) { this.chat.sessions = this.chat.sessions || []; }
  };


  app.loadThread = async function(key) {
    try {
      const r = await api('/api/chat/' + key);
      this.chat.spec = this.normalizeAgent(r.agent, key);
      this.chat.tid = r.thread_id || null;
      this.chat.messages = (r.messages || []).map(m => ({ role: m.role, text: m.text }));
      // если истории нет — приветствие агента, чат не выглядит пустым
      if (!this.chat.messages.length && (r.agent && r.agent.greeting)) {
        this.chat.messages = [{ role: 'assistant', text: r.agent.greeting }];
      }
    } catch (e) {
      this.chat.messages = [{ role: 'assistant', widget: this.chatRecoveryHtml('history') }];
    }
    await this.refreshSessions();
    if (this.chat.key === key) this.renderChat(document.getElementById('app-main'));
  };


  app.toast = function(msg) {
    const t = document.createElement('div');
    t.className = 'toast'; t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2400);
  };

  app.proofHtml = function(proof) {
    if (!proof) return '';
    const en = oracleLang() === 'en';
    const mode = proof.mode === 'deterministic'
      ? (en ? 'Grounded in calculated tools' : 'Проверено по расчётным инструментам')
      : proof.mode === 'safety'
        ? (en ? 'Safety-first response' : 'Ответ по safety-протоколу')
        : (en ? 'Offline reflective mode' : 'Офлайн-рефлексия');
    const labels = en ? {
      get_chart: 'Natal chart', get_all_placements: 'All placements', get_placement: 'Single placement',
      get_matrix: 'Matrix', get_life_path: 'Life path', get_chinese_zodiac: 'Chinese zodiac',
      get_transits: 'Current sky', get_composite: 'Composite', get_returns: 'Solar return', get_moon_week: 'Moon week', get_career_windows: 'Career windows',
      get_compatibility: 'Compatibility', list_partners: 'Saved partners', draw_tarot: 'Tarot draw',
      palm_scanner: 'Palm evidence', palm_photo_guide: 'Photo guide', palm_history: 'Palm history',
      suggest_practice: 'Practice catalogue', recall_diary: 'Diary', recall_memory: 'Memory', save_memory: 'Memory'
    } : {
      get_chart: 'Натальная карта', get_all_placements: 'Все placements', get_placement: 'Один placement',
      get_matrix: 'Матрица', get_life_path: 'Число пути', get_chinese_zodiac: 'Китайский зодиак',
      get_transits: 'Текущее небо', get_composite: 'Композит', get_returns: 'Солнечный возврат', get_moon_week: 'Лунная неделя', get_career_windows: 'Окна решений',
      get_compatibility: 'Совместимость', list_partners: 'Сохранённые люди', draw_tarot: 'Расклад Таро',
      palm_scanner: 'Evidence ладони', palm_photo_guide: 'Гид по фото', palm_history: 'История ладони',
      suggest_practice: 'Каталог практик', recall_diary: 'Дневник', recall_memory: 'Память', save_memory: 'Память'
    };
    const used = (proof.tools_used || []).map(name => labels[name] || name).slice(0, 4);
    return `<div class="message-proof" aria-label="${esc(mode)}"><span class="message-proof__mode">✦ ${esc(mode)}</span>${used.length ? `<span class="message-proof__tools">${used.map(item => esc(item)).join(' · ')}</span>` : ''}</div>`;
  };

  app.routingHtml = function(routing) {
    if (!routing || !routing.auto_route || !routing.agent) return '';
    const en = oracleLang() === 'en';
    const pool = this.agents && this.agents.length ? this.agents : AGENT_FALLBACK;
    const target = pool.find(item => item.code === routing.agent);
    const name = target ? (target.name || target.code) : routing.agent;
    const label = en ? `Handed to ${name}` : `Передала вопрос ${name}`;
    return `<div class="message-route" role="status" aria-label="${esc(label)}">↗ ${esc(label)}</div>`;
  };

  // Ошибки остаются отдельными бережными состояниями, без технического текста.
  // FE-012: у неотправленного ответа есть кнопка «Повторить» — черновик вопроса
  // сохраняется в chat.draft, так что ретрай не просит ничего перепечатывать.
  app.chatRecoveryHtml = function(kind) {
    const history = kind === 'history';
    const en = chatLang() === 'en';
    const title = history
      ? (en ? 'History could not be opened' : 'История сейчас не открылась')
      : (en ? 'The reply has not arrived yet' : 'Ответ пока не пришёл');
    const copy = history
      ? (en ? 'You can start the conversation right now or try loading the saved messages again.'
           : 'Можно начать разговор прямо сейчас или попробовать загрузить сохранённые сообщения ещё раз.')
      : (en ? 'Your question is safe in this conversation. Check the connection and send it again when you are ready.'
            : 'Твой вопрос не потерялся в этом диалоге. Проверь соединение и отправь его ещё раз, когда будешь готов(а).');
    const action = history
      ? `<button class="chat-retry" data-act="retry-chat">${en ? 'Load history' : 'Загрузить историю'}</button>`
      : `<button class="chat-retry" data-act="retry-send">${en ? 'Try again' : 'Повторить отправку'}</button>`;
    return `<div class="chat-recovery" role="status">
      <strong>${title}</strong>
      <p>${copy}</p>
      ${action}
    </div>`;
  };

  // отправка в активную сессию (если есть) — иначе первый вопрос создаёт тред

  app.chatPost = async function(text, options = {}) {
    const a = this.chat.spec;
    const headers = options.idempotencyKey
      ? { 'X-Idempotency-Key': options.idempotencyKey } : {};
    const request = { method: 'POST', body: JSON.stringify({ text }), headers };
    if (options.signal) request.signal = options.signal;
    if (this.chat.tid) {
      return await api(`/api/chat/${a.code}/sessions/${this.chat.tid}`, request);
    }
    const r = await api(`/api/chat/${a.code}`, request);
    if (r.thread_id) this.chat.tid = r.thread_id;
    return r;
  };


  app.toggleSessions = function() {
    haptic('light');
    const panel = document.getElementById('sess-panel');
    const trigger = document.querySelector('.chat-thread-toggle');
    if (!panel) return;
    const open = panel.style.display === 'none';
    panel.style.display = open ? 'block' : 'none';
    if (trigger) trigger.setAttribute('aria-expanded', String(open));
  };

  // Лунный календарь: компакт — «кратко о сегодня» + раскрытие всей недели по кнопке

  app.toggleMoonWeek = function() {
    haptic('light');
    const wk = document.getElementById('moon-week');
    if (!wk) return;
    const open = wk.classList.toggle('show');
    document.querySelectorAll('.moon-toggle, .moon-today').forEach(el => {
      if (!el.closest('#moon-week')) el.classList.toggle('open', open);
    });
    if (!open) this.collapseMoonDays();
  };

  app.collapseMoonDays = function() {
    document.querySelectorAll('#moon-week .mc-day').forEach(d => {
      d.classList.remove('open');
      const det = d.querySelector('.mc-detail');
      if (det) det.hidden = true;
    });
  };

  app.toggleMoonDay = function(i) {
    haptic('soft');
    const day = Array.from(document.querySelectorAll('#moon-week .mc-day'))
      .find(d => d.dataset.i === String(i));
    if (!day) return;
    const det = day.querySelector('.mc-detail');
    const open = day.classList.toggle('open');
    if (det) det.hidden = !open;
  };

  // Лунный календарь: детальный модал со всей неделей (загружена в moonWeek)

  app.openMoon = function() {
    haptic('light');
    const arr = this.moonWeek || [];
    if (!arr.length) { this.toast('Лунный календарь скоро подтянет свет 🌙'); return; }
    const wd = WD_SHORT, months = MON_RU;
    const rows = arr.map((d, i) => {
      const today = i === 0;
      const m = months[parseInt(d.date.slice(5, 7), 10) - 1] || '';
      return `<div class="md-row${today ? ' today' : ''}">
        <span class="md-ico">${moonSvg(d.emoji)}</span>
        <div class="md-main">
          <div class="md-wd">${wd[d.weekday]} · ${d.day_num} ${m}${today ? ' <em>· сегодня</em>' : ''}</div>
          <div class="md-name"><b>${esc(d.name)}</b> · ${d.day}-й лунный день</div>
          <div class="md-adv">${esc(d.advice)}</div>
        </div>
      </div>`;
    }).join('');
    this.showModal(`<h3>🌙 Лунный календарь</h3><button class="m-close" data-act="modal-close">✕</button>
      <div class="moon-detail">${rows}</div>`);
  };


  app.switchPTab = function(tab) {
    haptic('light');
    document.querySelectorAll('.ptab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.ptab-pane').forEach(p => p.classList.toggle('active', p.id === 'ptab-' + tab));
  };


  app.newSession = async function() {
    haptic('light');
    const r = await api(`/api/chat/${this.chat.key}/sessions`, { method: 'POST' });
    this.chat.tid = r.thread_id;
    this.chat.messages = [];
    this.chat.pending = null;
    await this.refreshSessions();
    this.renderChat(document.getElementById('app-main'));
  };


  app.openSession = async function(id) {
    try {
      const r = await api(`/api/chat/${this.chat.key}/sessions/${id}`);
      this.chat.spec = this.normalizeAgent(r.agent, this.chat.key);
      this.chat.tid = r.thread_id;
      this.chat.messages = (r.messages || []).map(m => ({ role: m.role, text: m.text }));
      if (!this.chat.messages.length && r.agent && r.agent.greeting) {
        this.chat.messages = [{ role: 'assistant', text: r.agent.greeting }];
      }
    } catch (e) {
      this.chat.messages = [{ role: 'assistant', widget: this.chatRecoveryHtml('history') }];
    }
    await this.refreshSessions();
    this.renderChat(document.getElementById('app-main'));
  };


  app.delSession = async function(id) {
    await api(`/api/chat/${this.chat.key}/sessions/${id}`, { method: 'DELETE' });
    await this.refreshSessions();
    if (id === this.chat.tid) {
      const next = (this.chat.sessions || [])[0];
      if (next) { await this.openSession(next.id); return; }
      this.chat.tid = null;
      this.chat.messages = this.chat.spec && this.chat.spec.greeting
        ? [{ role: 'assistant', text: this.chat.spec.greeting }] : [];
    }
    this.renderChat(document.getElementById('app-main'));
  };


  app.deleteAllSessions = function() {
    // FE-005: подтверждение — фирменный модал, не системный confirm().
    this.confirmAction(chatT('deleteAllChatsTitle'), chatT('deleteAllChatsConfirm'),
      chatT('deleteAllChatsConfirmBtn'), async () => {
        await api(`/api/chat/${this.chat.key}/sessions`, { method: 'DELETE' });
        this.chat.tid = null;
        this.chat.messages = this.chat.spec && this.chat.spec.greeting
          ? [{ role: 'assistant', text: this.chat.spec.greeting }] : [];
        this.chat.pending = null;
        await this.refreshSessions();
        this.toast(chatT('chatsCleared'));
        this.renderChat(document.getElementById('app-main'));
      });
  };


  app.renderChat = function(main) {
    const a = this.chat.spec || this.agentSpec(this.chat.key || 'oracle');
    const messages = this.chat.messages;
    const busy = this.chat.busy;
    const pending = this.chat.pending;
    const agents = this.agents.length ? this.agents : AGENT_FALLBACK;
    const suggest = (chatLang() === 'en' ? CHAT_SUGGESTIONS_EN[a.code] : null)
      || (TEMPLATES[a.code] || a.suggestions || []).slice(0, 3);
    const displayName = chatAgentField(a, 'name');
    const displayTitle = chatAgentField(a, 'title') || a.role || (chatLang() === 'en' ? 'Guide' : 'Проводник');
    const currentFeatures = FEATURES[a.code] || [];
    const sessionCount = (this.chat.sessions || []).length;
    const last = messages[messages.length - 1];
    const cheer = messages.length > 1 && last.role === 'assistant' && !busy && !(last.text || '').startsWith('😔') && !last.widget;

    // виджет-сообщение (спидометр любви и т.п.) — это готовый HTML, не текст:
    // rich() его экранировал бы, поэтому рендерим как есть в .msg.assistant
    const body = messages.map(m =>
      m.widget ? `<div class="msg assistant">${m.widget}</div>`
        : `<div class="msg ${m.role === 'user' ? 'user' : 'assistant'}">${richMd(m.text)}${m.routing ? this.routingHtml(m.routing) : ''}${m.proof ? this.proofHtml(m.proof) : ''}</div>`).join('');

    // Первый экран чата — короткая, персональная точка входа вместо универсального hero-текста.
    const introGuides = chatLang() === 'en' ? {
      oracle: { kicker: 'A SPACE FOR CLARITY', title: 'Start with what matters most right now', text: 'Write one thought, feeling or question — together we will find a gentle orientation.' },
      astro: { kicker: 'AN ASTROLOGICAL ORIENTATION', title: 'See your rhythm through the chart', text: 'Build your natal chart or ask about a coming period — using only the data available.' },
      tarot: { kicker: 'A READING FOR YOUR QUESTION', title: 'Shape your question for the cards', text: 'Choose a spread and look at the situation from several calm perspectives.' },
      chiromant: { kicker: 'A CAREFUL PALM READING', title: 'Start with what is actually visible', text: 'Share a palm photo: Mira will read visible zones and connect them to your question.' },
    } : {
      oracle: { kicker: 'ТВОЁ ПРОСТРАНСТВО ДЛЯ ЯСНОСТИ', title: 'Начни с того, что сейчас важнее всего', text: 'Можно написать одну мысль, чувство или вопрос — вместе найдём бережный ориентир.' },
      astro: { kicker: 'АСТРОЛОГИЧЕСКИЙ ОРИЕНТИР', title: 'Посмотри на свой ритм через карту', text: 'Собери натальную карту или задай вопрос о ближайшем периоде — только на основе доступных данных.' },
      tarot: { kicker: 'РАСКЛАД ПО СЮЖЕТУ ВОПРОСА', title: 'Сформулируй вопрос к картам', text: 'Выберем схему и спокойно посмотрим на ситуацию с разных сторон.' },
      chiromant: { kicker: 'БЕРЕЖНОЕ ЧТЕНИЕ ЛАДОНИ', title: 'Сначала — что действительно видно', text: 'Пришли фото ладони: Мира разберёт видимые зоны и свяжет их с твоим вопросом.' },
    };
    const introGuide = introGuides[a.code] || introGuides.oracle;
    const introHtml = messages.length <= 1 ? `
        <section class="agent-intro agent-intro--compact agent-intro--${esc(a.code)}" style="${this.agentThemeStyle(a, a.code)}" aria-label="${esc(chatLang() === 'en' ? 'Guide introduction' : 'Знакомство с проводником')}">
          <span class="ai-kicker">${introGuide.kicker}</span>
          <div class="ai-persona">
            <div class="ai-face">${agentSprite(a, false)}</div>
            <div class="ai-persona-copy">
              <div class="ai-name">${esc(displayName || (chatLang() === 'en' ? 'Guide' : 'Проводник'))}</div>
              <div class="ai-role">${esc(displayTitle)}</div>
            </div>
          </div>
          <div class="ai-next">
            <b>${introGuide.title}</b>
            <span>${introGuide.text}</span>
          </div>
        </section>` : '';

    const pendHtml = pending ? this.pendingHtml(pending) : '';

    main.innerHTML = `
      <div class="chat-shell chat-shell--${esc(a.code)}" style="${this.agentThemeStyle(a, a.code)}">
        <div class="chat-head">
          <button class="back" data-act="back" aria-label="${esc(chatT('back'))}" title="${esc(chatT('toGuides'))}">‹</button>
          <div class="agent-avatar" style="${this.agentThemeStyle(a, a.code)}">${agentSprite(a, cheer)}</div>
          <div style="flex:1;min-width:0">
            <h1 class="cname">${esc(displayName || (chatLang() === 'en' ? 'Guide' : 'Проводник'))}</h1>
            <div class="tsub">${esc(displayTitle)}</div>
            <div class="chat-proof-strip" role="group" aria-label="${homeT('profileQuality')}">
              <span>✦ ${homeT('evidenceFirst')}</span>${(a.capabilities && a.capabilities.length) ? `<span>· ${homeFormat('toolCount', { count: a.capabilities.length })}</span>` : ''}
            </div>
          </div>
          <button type="button" class="chat-thread-toggle chat-space-picker" data-act="sessions" aria-expanded="false" aria-controls="sess-panel" aria-label="${esc(chatT('myChatsAria'))}">
            <span class="chat-thread-toggle__icon">${sigilIcon('monthly')}</span>
            <span class="chat-thread-toggle__copy"><small>${esc(chatT('space'))}</small><b>${esc(displayName || chatT('myChats'))}</b><em>${esc(chatCount(sessionCount))}</em></span>
            <span class="chat-thread-toggle__chevron" aria-hidden="true">⌄</span>
          </button>
          <button type="button" class="chat-new-session" data-act="new-session" aria-label="${esc(chatT('startChat'))}" title="${esc(chatT('startChat'))}">
            ${sigilIcon('spark')}<span>${esc(chatT('newChat'))}</span>
          </button>
        </div>
        <section class="sess-panel" id="sess-panel" style="display:none" aria-label="${esc(chatT('myChats'))} ${esc(displayName)}">
          <div class="sess-head">
            <div><span>${esc(chatT('conversations'))}</span><small>${esc(chatCount(sessionCount))} · ${esc(chatT('sessionCopy'))}</small></div>
            <button type="button" class="sess-create" data-act="new-session">${sigilIcon('spark')}<span>${esc(chatT('newChat'))}</span></button>
          </div>
          <div class="sess-list">
            ${sessionCount ? (this.chat.sessions || []).map(s => `
              <div class="sess-row ${s.id === this.chat.tid ? 'active' : ''}" data-act="open-session" data-tid="${s.id}">
                <span class="sess-status" aria-hidden="true"></span>
                <div class="sess-copy"><div class="sess-t">${esc(s.title || (chatLang() === 'en' ? 'New conversation' : 'Новый разговор'))}</div><div class="sess-prev">${esc(s.last_text || chatT('continueDialog'))}</div></div>
                <button type="button" class="sess-del" data-act="del-session" data-tid="${s.id}" aria-label="${esc(chatT('deleteChat'))}" title="${esc(chatT('deleteChatTitle'))}">✕</button>
              </div>            `).join('') : `<div class="sess-empty">${esc(chatT('firstConversation'))}</div>`}

          </div>
          ${sessionCount ? `<button type="button" class="sess-clear" data-act="delete-all-sessions"><span>${esc(chatT('deleteAllChats'))}</span><small>${esc(chatT('deleteAllChatsCopy'))}</small></button>` : ''}
        </section>
        <div class="agent-tabs" role="tablist" aria-label="${esc(chatT('chooseGuide'))}">
          ${agents.slice(0, 4).map(b => `
            <button type="button" class="atab ${b.code === a.code ? 'active' : ''}" style="${this.agentThemeStyle(b, b.code)}" data-act="chat" data-chat="${b.code}" role="tab" aria-selected="${b.code === a.code ? 'true' : 'false'}">
              <span class="atab-face"><img src="${esc(b.avatar || `/static/img/agents/${b.code}.jpg`)}" alt="" width="24" height="24" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='/static/img/oracle-mark.png'"></span><span>${esc(chatAgentField(b, 'name').split(' ')[0])}</span>
            </button>`).join('')}
        </div>
        <div class="chat-messages" id="chat-messages" tabindex="0" role="log" aria-label="${esc(chatLang() === 'en' ? 'Conversation history' : 'История разговора')}">
          ${introHtml}
          ${body}
          ${pendHtml}
          ${busy ? `<div class="msg assistant"><div class="typing"><span></span><span></span><span></span></div></div>` : ''}
        </div>
        <div class="composer">
                      <div class="composer-context">
            <span class="composer-presence"><i aria-hidden="true"></i>${esc(displayName || chatT('presence'))} ${esc(chatT('presence'))}</span>
            <div class="composer-context-actions">
              ${a.code === 'chiromant' ? `<button type="button" class="palm-quick-upload" data-act="palm-start" aria-label="${esc(chatT('addPalm'))}"><span aria-hidden="true">✋</span><span>${esc(chatT('palmPhoto'))}</span></button>` : ''}
              <button type="button" class="composer-tools-copy" data-act="tool-toggle" aria-label="${esc(chatT('tools'))}" aria-expanded="false" aria-controls="tool-expand"><span class="composer-tools-copy__icon">${sigilIcon('spark')}</span><span>${esc(chatT('tools'))}</span><span class="composer-tools-copy__chevron" aria-hidden="true">↑</span></button>
            </div>
          </div>

          <div class="composer-top">
            <textarea class="ipt" id="chat-input" rows="1" maxlength="1000" placeholder="${esc(chatLang() === 'en' ? 'Write to ' : 'Напиши ')}${esc(displayName || (chatLang() === 'en' ? 'your guide' : 'Проводник'))} — ${chatLang() === 'en' ? 'just as it is…' : 'как есть…'}" autocomplete="off" spellcheck="true" aria-label="${esc(chatT('messageFor'))} ${esc(displayName || (chatLang() === 'en' ? 'your guide' : 'Проводник'))}">${esc(this.chat.draft || '')}</textarea>
            ${busy ? `<button class="send-btn" id="send-btn" data-act="cancel-chat" aria-label="${esc(chatT('stop'))}">×</button>` : `<button class="send-btn" id="send-btn" data-act="send" aria-label="${esc(chatT('send'))}">➤</button>`}
          </div>
          ${suggest.length ? `
          <div class="suggest-chips" role="group" aria-label="${esc(chatT('ideas'))}">
            ${suggest.map(s => `<button type="button" class="chip tpl" data-act="fill" data-val="${esc(s)}">${esc(s)}</button>`).join('')}
          </div>` : ''}
        </div>
        <div class="tool-expand" id="tool-expand" aria-hidden="true">
          <div class="te-mask" data-act="tool-toggle"></div>
          <section class="te-sheet" role="dialog" aria-modal="true" aria-label="${esc(chatT('toolAria'))}">
            <div class="te-handle" aria-hidden="true"></div>
            <div class="te-head">
              <div><span class="te-eyebrow">${esc(chatT('toolsEyebrow'))}</span><span class="te-title">${esc(chatT('toolsTitle'))}</span><p class="te-intro">${esc(chatT('toolsIntro'))}</p></div>
              <button class="te-close" data-act="tool-toggle" aria-label="${esc(chatT('closeTools'))}">✕</button>
            </div>
            <div class="te-body">
              ${currentFeatures.length ? `
                <div class="te-group te-current">
                  <div class="te-current-title" style="${this.agentThemeStyle(a, a.code)}">
                    <span>${esc(chatT('withGuide'))} ${esc(displayName || (chatLang() === 'en' ? 'guide' : 'проводником'))}</span><small>${esc(chatT('inDialog'))}</small>
                  </div>
                  <div class="te-grid">
                    ${currentFeatures.map(f => `
                      <button class="te-chip" data-act="chat-fn" data-chat="${a.code}" data-fn="${f.h}" data-testid="fn-${f.id}" aria-label="${esc(f.t)}: ${esc(f.d || '')}">
                        <span class="te-ico">${sigilIcon(f.id)}</span><span class="te-chip-copy"><b>${esc(f.t)}</b><small>${esc(f.d)}${f.m ? ' · ' + esc(f.m) : ''}</small></span><span class="te-arrow" aria-hidden="true">›</span>
                      </button>`).join('')}
                  </div>
                </div>` : ''}
            </div>
          </section>
        </div>
      </div>`;
    this.scrollToBottom();
  };


  app.pendingHtml = function(p) {
    const q = s => esc(s).replace(/'/g, "&#39;");
    switch (p.kind) {
      case 'tarot-pick':
        return (() => {
          const cur = p.spreads.find(s => s.code === p.spread) || { title: tarotLang() === 'en' ? 'Reading' : 'Расклад', emoji: '🎴', hint: tarotLang() === 'en' ? 'Tap to choose a spread' : 'Тапни, чтобы выбрать схему' };
          const prompts = tarotLang() === 'en' ? [
            'What matters most to notice in this situation?',
            'How can I move gently in this relationship?',
            'Where should I place my energy this week?',
          ] : [
            'Что сейчас важнее всего увидеть в этой ситуации?',
            'Как мне бережно действовать в отношениях?',
            'На что направить энергию в ближайшую неделю?',
          ];
          return `<div class="msg assistant">
            <div class="chat-widget tarot-picker-widget ${p.drawing ? 'is-drawing' : ''}">
              <div class="tarot-kicker">${esc(tarotT('ritualKicker'))}</div>
              <div class="w-title" style="margin:0">🎴 ${esc(tarotT('chooseTitle'))}</div>
              <div class="w-sub tarot-picker-sub">${esc(tarotT('pickerCopy'))}</div>
              <button class="pick-sel-btn" data-act="pick-open" ${p.drawing ? 'disabled' : ''}>
                <span class="pick-sel-ico">${esc(cur.emoji || '🎴')}</span>
                <span class="pick-sel-txt">
                  <span class="pick-sel-t">${esc(tarotSpreadText(cur, 'title'))}</span>
                  <span class="pick-sel-d">${esc(tarotSpreadText(cur, 'hint', cur.desc || (tarotLang() === 'en' ? 'Choose a reading spread' : 'Выбрать схему расклада')))}</span>
                </span>
                <span class="pick-sel-go">›</span>
              </button>
              <div class="swipe-hint">${esc(tarotT('tapToBrowse'))}</div>
              <div class="tarot-question-label">${esc(tarotT('askAbout'))}</div>
              <div class="tarot-question-prompts">${prompts.map(value => `<button class="tarot-question-prompt${p.q === value ? ' is-active' : ''}" data-act="tarot-question" data-value="${q(value)}" ${p.drawing ? 'disabled' : ''}>${esc(value)}</button>`).join('')}</div>
              ${p.err ? `<div class="s-err">${esc(p.err)}</div>` : ''}
              <textarea class="ipt" id="tarot-q" rows="2" aria-label="${esc(tarotT('ariaQuestion'))}" placeholder="${esc(tarotT('placeholder'))}" ${p.drawing ? 'disabled' : ''}
                style="margin-top:10px;resize:none">${q(p.q || '')}</textarea>
              <div class="tarot-draw-status" aria-live="polite">${p.drawing ? `<span class="tarot-draw-orbit" aria-hidden="true"></span><span>${esc(tarotT('drawingStatus'))}</span>` : `<span class="tarot-draw-dot" aria-hidden="true"></span><span>${esc(tarotT('readyStatus'))}</span>`}</div>
              <button class="btn btn-primary tarot-draw-btn" style="margin-top:10px" data-act="draw" ${p.drawing ? 'disabled aria-busy="true"' : ''}>${esc(p.drawing ? tarotT('drawingButton') : tarotT('drawButton'))}</button>
              <div class="tarot-deck-bar" style="margin-top:8px; display:flex; gap:6px; justify-content:center">
                <button class="chip" data-act="deck-open" style="font-size:11px; opacity:.7">🂠 ${esc(app.currentDeck ? (app.currentDeck() === 'lenormand' ? tarotT('deckSecond') : tarotT('deckDefault')) : tarotT('deckDefault'))}</button>
              </div>
            </div></div>`;
        })();

      case 'tarot-cards': {
        const opened = p.revealed.filter(Boolean).length;
        const total = p.cards.length;
        return `<div class="msg assistant">
          <div class="chat-widget tarot-cards-widget">
            <div class="tarot-kicker">${esc(tarotT('cardKicker'))}</div>
            <div class="tarot-cards-head">
              <div>
                <div class="w-title">${esc(tarotT('openCards'))}</div>
                ${p.question ? `<div class="w-sub">${esc(tarotT('questionLabel'))} <b>«${esc(p.question)}»</b></div>` : ''}
              </div>
              <div class="tarot-card-progress" aria-label="${esc(tarotT('openCards'))}: ${opened} ${esc(tarotT('progressOf'))} ${total}"><span>${opened} ${esc(tarotT('progressOf'))} ${total}</span><i style="--tarot-progress:${(opened / total) * 100}%"></i></div>
            </div>
            <div class="tarot-grid sh-${esc(p.spread || 'three')}">
              ${p.positions.map((pos, i) => {
                const c = p.cards[i] || {};
                const canReveal = i === (Number.isInteger(p.nextReveal) ? p.nextReveal : opened);
                return `
                <div class="tpos${canReveal && !p.revealed[i] ? ' is-next' : ''}" data-i="${i}">
                  <button type="button" class="tcard ${p.revealed[i] ? 'open' : 'dealt'}" style="${p.revealed[i] ? '' : 'animation-delay:' + (i * 80) + 'ms'}" data-act="flip" data-i="${i}" aria-label="${p.revealed[i] ? esc(c.name) : tarotT('ariaOpenCard') + ': ' + esc(tarotPositionText(p.spread, pos, i))}" ${p.revealed[i] ? 'aria-pressed="true"' : 'aria-pressed="false"'}>
                    <span class="tcard-inner">
                      <span class="tcard-face tcard-back"><img src="/static/img/card-back.jpg" alt="" loading="lazy"></span>
                      <span class="tcard-face tcard-front${c.reversed ? ' rev' : ''}"><img src="${app.tarotImagePath ? app.tarotImagePath(c.img || 'm00') : '/static/img/tarot/' + esc(c.img || 'm00') + '.jpg'}" alt="${esc(c.name)}" loading="lazy">
                        ${c.reversed ? `<span class="t-rev">↺ ${esc(tarotT('reversed'))}</span>` : ''}</span>
                    </span>
                  </button>
                  <div class="tpos-pos">${esc(tarotPositionText(p.spread, pos, i))}</div>
                  <div class="tpos-mean">${esc(c.name)}${c.reversed ? ' ↺' : ''}</div>
                  <div class="tpos-desc">${esc(c.meaning)}</div>
                </div>`;
              }).join('')}
            </div>
            ${p.allRevealed ? `<section class="tarot-thread tarot-thread--revealed" aria-label="${esc(tarotT('threadKicker'))}">
                <div class="tarot-thread-kicker">${esc(tarotT('threadKicker'))}</div>
                <p>${esc(tarotT('threadCopy'))}</p>
                <div class="tarot-thread-map">${p.positions.map((pos, i) => {
                  const c = p.cards[i] || {};
                  return `<span><b>${esc(tarotPositionText(p.spread, pos, i))}:</b> ${esc(c.name || (tarotLang() === 'en' ? 'card' : 'карта'))}</span>`;
                }).join('')}</div>
              </section>
              <button class="btn btn-primary tarot-interpret-btn" style="margin-top:14px" data-act="interpret">${esc(tarotT('interpret'))}</button>`
              : `<div class="t-hint">${esc(tarotT('threadHint'))}</div>`}
          </div></div>`;
      }

      case 'chart':
        return `<div class="msg assistant">
          <div class="chat-widget">${p.html || (p.loading ? '<div class="typing"><span></span><span></span><span></span></div>' : '')}</div>
        </div>`;

      case 'synastry-select':
        return `<div class="msg assistant"><div class="chat-widget">${p.loading ? '<div class="typing"><span></span><span></span><span></span></div>' : (p.error ? `<div class="s-err">${esc(p.error)}</div>` : '') + (this.synastrySelectHtml ? this.synastrySelectHtml(p.partners || []) : '')}</div></div>`;

      case 'synastry-loading':
        return `<div class="msg assistant"><div class="chat-widget"><div class="typing"><span></span><span></span><span></span></div><p class="product-muted">Собираю две точные карты и ищу межпланетные связи…</p></div></div>`;

      case 'synastry-result':
        return `<div class="msg assistant">${p.data && this.synastryProductHtml ? this.synastryProductHtml(p.data) : `<div class="chat-widget"><div class="s-err">${esc(p.error || 'Синастрия пока недоступна.')}</div></div>`}</div>`;

      case 'transits-loading':
        return `<div class="msg assistant"><div class="chat-widget"><div class="typing"><span></span><span></span><span></span></div><p class="product-muted">Сверяю сегодняшнее небо с твоей натальной картой…</p></div></div>`;

      case 'transits-result':
        return `<div class="msg assistant">${p.data && this.transitProductHtml ? this.transitProductHtml(p.data) : `<div class="chat-widget"><div class="s-err">${esc(p.error || 'Транзиты пока недоступны.')}</div></div>`}</div>`;

      case 'composite-select':
        return `<div class="msg assistant"><div class="chat-widget">${p.loading ? '<div class="typing"><span></span><span></span><span></span></div>' : (p.error ? `<div class="s-err">${esc(p.error)}</div>` : '') + (this.compositeSelectHtml ? this.compositeSelectHtml(p.partners || []) : '')}</div></div>`;

      case 'composite-loading':
        return `<div class="msg assistant"><div class="chat-widget"><div class="typing"><span></span><span></span><span></span></div><p class="product-muted">Собираю общий рисунок двух точных карт…</p></div></div>`;

      case 'composite-result':
        return `<div class="msg assistant">${p.data && this.compositeProductHtml ? this.compositeProductHtml(p.data) : `<div class="chat-widget"><div class="s-err">${esc(p.error || 'Композит пока недоступен.')}</div></div>`}</div>`;

      case 'returns-loading':
        return `<div class="msg assistant"><div class="chat-widget"><div class="typing"><span></span><span></span><span></span></div><p class="product-muted">Ищу точный момент солнечного возврата…</p></div></div>`;

      case 'returns-result':
        return `<div class="msg assistant">${p.data && this.returnsProductHtml ? this.returnsProductHtml(p.data) : `<div class="chat-widget"><div class="s-err">${esc(p.error || 'Возврат планеты пока недоступен.')}</div></div>`}</div>`;

      case 'compat':
        return `<div class="msg assistant compat-message">
          <section class="chat-widget compat-flow" aria-label="Проверка совместимости">
            <div class="compat-flow__head"><span class="compat-flow__sigil" aria-hidden="true">${sigilIcon('compat')}</span><div><span class="result-kicker">ЛИЧНЫЙ РАЗБОР</span><div class="w-title">Посмотрим на ритм связи</div></div></div>
            <div class="w-sub">Выбери контекст и дату рождения. Это ориентир для разговора, а не оценка вас или ваших отношений.</div>
            <div class="compat-steps" aria-label="Три спокойных шага">
              <span class="is-current"><i>1</i> Связь</span><span><i>2</i> Дата</span><span><i>3</i> Ориентир</span>
            </div>
            <p class="compat-flow__prompt">Как вы связаны сейчас?</p>
            <div class="rel-chips" role="group" aria-label="Тип связи">
              ${[['love','compat','Пара'],['friend','spark','Дружба'],['work','career','Дело'],['family','home','Семья']].map(([k, icon, t]) =>
                `<button type="button" class="rel-chip${p.relation === k ? ' sel' : ''}" data-act="compat-rel" data-rel="${k}" aria-pressed="${p.relation === k ? 'true' : 'false'}"><span>${sigilIcon(icon)}</span>${t}</button>`).join('')}
            </div>
            <div class="compat-flow__fields">
              <label class="compat-field"><span>Имя человека <em>необязательно</em></span><input class="ipt" id="cp-name" value="${esc(p.name || '')}" placeholder="Например, Аня" autocomplete="name"/></label>
              <label class="compat-field"><span>Дата рождения <em>обязательно</em></span><input class="ipt" id="cp-date" type="date" value="${esc(p.date || '')}" required aria-describedby="compat-date-help"/></label>
            </div>
            <small id="compat-date-help" class="compat-help"><span aria-hidden="true">✦</span> Дата нужна для расчёта; имя только добавит тепла в обращение.</small>
            <button class="btn btn-primary compat-submit" data-act="compat"><span>Открыть мой ориентир</span><span aria-hidden="true">→</span></button>
          </section></div>`;

      case 'compat-processing':
        return `<div class="msg assistant compat-message">
          <section class="chat-widget compat-processing" role="status" aria-live="polite">
            <div class="compat-processing__orb" aria-hidden="true"><span></span><span></span><span>${sigilIcon('compat')}</span></div>
            <div><span class="result-kicker">СОВМЕСТИМОСТЬ</span><strong>Собираю ритм вашей связи</strong><p>Сопоставляю основные сферы. Через несколько секунд здесь появится спокойный ориентир.</p><span class="compat-processing__note">Можно просто остаться в этом диалоге</span></div>
          </section></div>`;

      case 'moon':
        return this.moonWidget(p);

      case 'matrix':
        return this.matrixWidget(p);

      case 'today':
        return this.todayWidget(p);

      case 'practices':
        return this.practicesWidget(p);

      case 'diary':
        return this.diaryWidget(p);

      case 'career':
        return this.careerWidget(p);

      case 'palm':
        return p.html ? `<div class="msg assistant">${p.html}</div>` : '';

      case 'history':
        return `<div class="msg assistant">
          <div class="chat-widget">
            <div class="w-title">📚 Твои расклады</div>
            ${p.loading ? '<div class="loader-ring"></div>' : (p.rows || '<div style="color:var(--text-faint);font-size:12.5px">Пока пусто — первый расклад ждёт тебя ✨</div>')}
          </div></div>`;

      default: return '';
    }
  };

  /* ═══ ВИДЖЕТЫ v5.3: утро, луна, матрица, карьерные окна, практики, дневник ═══ */


  app.closeChat = function() {
    this.chat.key = null;
    this.chat.pending = null; // гонка B1: закрыли чат — несозревший виджет никому не нужен
    this.go('hub');
  };
  // свайп по табам агентов: вбок листаем Оракул → Астролог → Таролог → …

  app.cycleAgent = function(dir) {
    const list = this.agents.length ? this.agents.map(b => b.code) : ['oracle', 'astro', 'tarot', 'chiromant'];
    const i = list.indexOf(this.chat.key);
    if (i < 0) return;
    this.openChat(list[(i + dir + list.length) % list.length]);
  };
  // панель «Все инструменты» (bottom sheet): свайп вверх у нижнего края ленты

  app.setToolbox = function(open) {
    const el = document.getElementById('tool-expand');
    const triggers = document.querySelectorAll('.composer-tools-copy');
    const next = !!open;
    if (!el) return;

    el.classList.toggle('open', next);
    el.setAttribute('aria-hidden', next ? 'false' : 'true');
    document.body.classList.toggle('toolbox-open', next);
    triggers.forEach(trigger => trigger.setAttribute('aria-expanded', next ? 'true' : 'false'));
    if (typeof this.syncBackButton === 'function') this.syncBackButton();

    if (!this._toolboxKeydownReady) {
      this._toolboxKeydownReady = true;
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && document.getElementById('tool-expand')?.classList.contains('open')) {
          event.preventDefault();
          this.setToolbox(false);
        }
      });
    }

    if (next) {
      haptic('soft');
      const first = el.querySelector('.te-chip, .te-close');
      if (first) setTimeout(() => first.focus(), 180);
    } else if (triggers[0]) {
      triggers[0].focus();
    }
  };

  app.toggleToolbox = function() {
    const el = document.getElementById('tool-expand');
    this.setToolbox(el ? !el.classList.contains('open') : false);
  };

  app.clearThread = function() {
    const key = this.chat.key;
    // FE-007: тот же фирменный модал подтверждения, что и у deleteAllSessions.
    this.confirmAction(chatT('newChatTitle'), chatT('newChatConfirm'),
      chatT('newChatConfirmBtn'), async () => {
        if (this.chat.tid) {
          try { await api(`/api/chat/${key}/sessions/${this.chat.tid}`, { method: 'DELETE' }); } catch (e) {}
          await this.refreshSessions();
          await this.newSession();
          return;
        }
        try { await api('/api/chat/' + key, { method: 'DELETE' }); } catch (e) {}
        this.chat.messages = [];
        this.chat.pending = null;
        this.renderChat(document.getElementById('app-main'));
      });
  };

  /* ── отправка вопроса агенту ── */

  app.cancelChatRequest = function() {
    const request = this.chat.request;
    if (request && request.controller) request.controller.abort();
  };

  app.doSend = async function(text, opts = {}) {
    const a = this.chat.spec;
    const val = (text || (document.getElementById('chat-input') || {}).value || '').trim();
    if (!val || this.chat.busy) return;
    haptic('light');
    vb(15);
    const input = document.getElementById('chat-input');
    if (input) input.value = '';
    this.chat.draft = '';
    // echo=false — ретрай после ошибки: «пузырь» вопроса уже в ленте,
    // второй раз его не дублируем (FE-012).
    if (opts.echo !== false) this.chat.messages.push({ role: 'user', text: val });
    this.chat.busy = true;
    const requestKey = newRequestKey();
    const controller = new AbortController();
    this.chat.request = { key: requestKey, controller, text: val };
    this.renderChat(document.getElementById('app-main'));
    try {
      const r = await this.chatPost(val, { idempotencyKey: requestKey, signal: controller.signal });
      haptic('success');
      vb([10, 40, 14]);
      if (r.routing && r.routing.auto_route && r.agent && r.agent !== a.code) {
        this.chat.key = r.agent;
        this.chat.spec = this.normalizeAgent(r.agent, r.agent);
        await this.refreshSessions();
      }
      this.chat.messages.push({ role: 'assistant', text: r.answer, routing: r.routing || null, proof: r.proof || null });
    } catch (e) {
      const cancelled = e && e.name === 'AbortError';
      if (cancelled) {
        this.chat.messages.pop();
        this.chat.draft = val;
      } else {
        this.chat.messages.push({ role: 'assistant', widget: this.chatRecoveryHtml('reply') });
        this.chat.draft = val;
      }
    }
    this.chat.busy = false;
    this.chat.request = null;
    this.renderChat(document.getElementById('app-main'));
    // деликатная подсветка только что пришедшего ответа
    const lastMsg = document.querySelector('.chat-messages .msg:last-child');
    if (lastMsg) lastMsg.classList.add('fresh');
  };

  /* ═══ ФИЧА: РАСКЛАД ТАРО (вопрос → карты → LLM) ═══ */

  app.pendingQ = function(v) { if (this.chat.pending) { this.chat.pending.q = v; this.chat.pending.err = ''; } };

  // Полноэкранный выбор схемы расклада — весь список с описаниями (премium)

