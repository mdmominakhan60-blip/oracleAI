/* ── приложение ─────────────────────────────────────────────────────────── */
const app = window.app = {};

app.state = window.OracleRuntime
  ? window.OracleRuntime.createState()
  : {
      me: null, agents: [], today: null, spreads: null, moonWeek: null,
      dailyPulse: null, view: 'home',
      chat: { key: null, spec: null, messages: [], pending: null,
              busy: false, request: null, tid: null, sessions: [], draft: '' }
    };
if (window.OracleRuntime) window.OracleRuntime.bindLegacyState(app, app.state);

  app.boot = async function() {
    const qaParams = new URLSearchParams(location.search);
    const qaMode = qaParams.get('qa') === '1';
    const qaView = qaParams.get('qa_view') || 'home';
    const qaTab = qaParams.get('qa_tab') || '';
    if (qaMode) {
      document.documentElement.dataset.qa = '1';
      try { localStorage.setItem('oracle_intro_seen', '1'); localStorage.setItem('oracle_chat_guide_v2', '1'); } catch (e) {}
    }
    if (tg()) {
      tg().ready && tg().ready();
      tg().expand && tg().expand();
      try { tg().setHeaderColor && tg().setHeaderColor('#08070f'); } catch (e) {}
    }
    syncDocumentLocale();
    this.renderFrame();
    try {
      this.me = await api('/api/me');
      if (this.me) {
        const flags = this.me.flags ? this.me.flags : {};
        this.me.flags = flags;
        syncDocumentLocale();
      }
      const pill = document.querySelector('.user-pill');
      if (pill && this.me.name) {
        const avatar = pill.querySelector('.avatar');
        const name = pill.querySelector('.user-name');
        if (avatar) avatar.textContent = this.me.name[0].toUpperCase();
        if (name) name.textContent = this.me.name;
        pill.setAttribute('aria-label', (oracleLang() === 'en' ? 'Open profile: ' : 'Открыть профиль: ') + this.me.name);
      }
    } catch (e) {
      this.renderAuthRequired(e);
      return;
    }
    this.loadAgents();
    this.loadToday();
    this.go('home');
    if (qaMode) {
      if (qaView === 'chat') this.openChat(qaParams.get('qa_agent') || 'oracle');
      else if (['home', 'hub', 'profile'].includes(qaView)) this.go(qaView);
      if (qaView === 'profile' && ['summary', 'chart', 'history', 'memory'].includes(qaTab)) {
        setTimeout(() => document.querySelector(`.ptab[data-tab="${qaTab}"]`)?.click(), 120);
      }
    }
    this.initSwipe();
    this.initViewport();
    if (!qaMode) this.maybeLanguage();
  };
  // При первом запуске язык выбирается первым — до приветствия и онбординга.
  app.maybeLanguage = function() {
    try { if (localStorage.getItem('oracle_lang')) { this.maybeIntro(); return; } } catch (e) {}
    const ov = document.createElement('div');
    ov.id = 'intro';
    ov.className = 'intro';
    ov.innerHTML = `
      <div class="intro-track">
        <div class="intro-slide" style="text-align:center">
          <div class="intro-emoji">🌌</div>
          <div class="intro-title">OracleAI</div>
          <div class="intro-sub" data-lang-sub>Выбери язык, чтобы продолжить</div>
          <div class="lang-pick-btns" style="margin-top:22px;display:flex;flex-direction:column;gap:12px;max-width:280px;margin-left:auto;margin-right:auto">
            <button class="btn btn-primary" data-lang="ru" style="font-size:16px">🇷🇺 Русский</button>
            <button class="btn btn-ghost" data-lang="en" style="font-size:16px">🇬🇧 English</button>
          </div>
        </div>
      </div>`;
    const pick = (lang) => {
      try { localStorage.setItem('oracle_lang', lang); } catch (e) {}
      document.documentElement.lang = lang;
      syncDocumentLocale();
      ov.querySelector('[data-lang-sub]').textContent =
        lang === 'en' ? 'Choose your language to continue' : 'Выбери язык, чтобы продолжить';
      setTimeout(() => {
        ov.remove();
        this.maybeIntro();
      }, 150);
    };
    ov.querySelector('[data-lang="ru"]').addEventListener('click', () => pick('ru'));
    ov.querySelector('[data-lang="en"]').addEventListener('click', () => pick('en'));
    document.body.appendChild(ov);
  };
  app.renderAuthRequired = function(err) {
    const main = document.getElementById('app-main');
    const nav = document.querySelector('.app-nav');
    if (nav) nav.hidden = true;
    if (!main) return;
    // UX-009: 404 внутри Telegram означает «бот ещё не знает пользователя» —
    // ведём прямо в бота по deep-link вместо тупикового «открой из Telegram».
    const unknownUser = !!(err && err.status === 404);
    const title = t(unknownUser ? 'authBotTitle' : 'authRequiredTitle');
    const copy = t(unknownUser ? 'authBotCopy' : 'authRequiredCopy');
    const retry = t('authRetry');
    main.innerHTML = `<div class="screen" data-auth-required>
      <div class="soft-empty soft-empty--recovery" data-state="error">
        <div class="soft-empty__orb" aria-hidden="true">⌁</div>
        <div class="soft-empty__title">${esc(title)}</div>
        <div class="soft-empty__copy">${esc(copy)}</div>
        <div class="soft-empty__action" data-auth-actions><button class="btn btn-primary" type="button" data-auth-retry>${esc(retry)}</button></div>
      </div>
    </div>`;
    const button = main.querySelector('[data-auth-retry]');
    if (button) button.addEventListener('click', () => window.location.reload());
    if (unknownUser) {
      api('/api/public/config').then(cfg => {
        const actions = main.querySelector('[data-auth-actions]');
        if (!actions || !cfg || !cfg.bot_username) return;
        const link = document.createElement('a');
        link.className = 'btn btn-primary';
        link.href = `https://t.me/${encodeURIComponent(cfg.bot_username)}?start=miniapp`;
        link.textContent = t('authOpenBot');
        actions.prepend(link);
        if (button) button.classList.replace('btn-primary', 'btn-ghost');
      }).catch(() => {});
    }
  };

  // G001 клавиатура: композер поднимается, когда Telegram раскрывает клавиатуру

  app.initViewport = function() {
    if (!window.visualViewport) return;
    window.visualViewport.addEventListener('resize', () => {
      const vv = window.visualViewport;
      const composer = document.querySelector('.composer');
      if (!composer) return;
      const kb = Math.max(0, (window.innerHeight || vv.height) - vv.height);
      if (kb > 0) composer.style.paddingBottom = (kb + 8) + 'px';
      else composer.style.paddingBottom = '';
    }, { passive: true });
  };
  app.maybeIntro = function() {
    if (localStorage.getItem('oracle_intro_seen')) return;
    // первый день + дата рождения уже есть, а карты нет — в финал интро
    // добавляем CTA «собрать натальную карту» (строится у Астролога в чате)
    const needChart = !!(this.me && this.me.birth_date && !this.me.chart_mode);
    const firstName = this.me && this.me.name ? esc(this.me.name.split(' ')[0]) : '';
    // FE-008: слайды первого входа — на языке интерфейса, а не только на русском.
    const slides = [
      `<div class="intro-slide"><div class="intro-emoji">🔮</div><div class="intro-title">${esc(t('intro1Title'))}</div><div class="intro-sub">${esc(t('intro1Sub'))}</div></div>`,
      `<div class="intro-slide"><div class="intro-emoji">🎴</div><div class="intro-title">${esc(t('intro2Title'))}</div><div class="intro-sub">${esc(t('intro2Sub'))}</div></div>`,
      `<div class="intro-slide"><div class="intro-emoji">✨</div><div class="intro-title">${esc(t('intro3Title'))}</div><div class="intro-sub">${esc(t('intro3Sub'))}</div></div>`,
    ];
    if (needChart) {
      const lead = firstName
        ? t('introChartCopyName').replace('{name}', firstName)
        : t('introChartCopy');
      slides.push(`<div class="intro-slide">
        <div class="intro-emoji">🌌</div>
        <div class="intro-title">${esc(t('introChartTitle'))}</div>
        <div class="intro-sub">${lead} ${esc(t('introChartCopyTail'))}</div>
        <button class="btn btn-primary" style="margin-top:14px;width:100%" data-act="chat-fn" data-chat="astro" data-fn="featureChart" data-intro-chart>${esc(t('introChartCta'))}</button>
      </div>`);
    }
    const last = slides.length - 1;
    const ov = document.createElement('div');
    ov.id = 'intro';
    ov.innerHTML = `
      <div class="intro-track">
        ${slides.join('')}
      </div>
      <div class="intro-dots">${slides.map((_, k) => `<span${k === 0 ? ' class="active"' : ''}></span>`).join('')}</div>
      <button class="btn btn-primary intro-start" data-intro-start>${esc(t('introStart'))}</button>
      <button class="intro-skip" data-intro-skip>${esc(t('introSkip'))}</button>`;
    document.body.appendChild(ov);
    const track = ov.querySelector('.intro-track');
    const dots = ov.querySelectorAll('.intro-dots span');
    // Текущий слайд — состояние, а не разбор текста кнопки: подпись кнопки
    // локализована, и сравнение с RU-строкой ломало логику на EN (FE-008).
    let current = 0;
    const sync = () => {
      current = Math.max(0, Math.min(last, Math.round(track.scrollLeft / (track.clientWidth || 1))));
      dots.forEach((d, k) => d.classList.toggle('active', k === current));
      ov.querySelector('.intro-start').textContent = current === last ? t('introStart') : t('introNext');
    };
    track.addEventListener('scroll', sync, { passive: true });
    sync();
    const done = () => {
      try { localStorage.setItem('oracle_intro_seen', '1'); } catch (e) {}
      ov.remove();
      haptic('success');
    };
    ov.querySelector('[data-intro-start]').addEventListener('click', () => {
      if (current < last) {
        track.scrollBy({ left: track.clientWidth, behavior: 'smooth' });
      } else done();
    });
    ov.querySelector('[data-intro-skip]').addEventListener('click', done);
    // CTA финального слайда: гасим интро здесь, сам же клик ловит
    // делегированный обработчик 13-events (data-act="chat-fn") и открывает
    // чат Астролога с формой построения карты
    if (needChart) {
      ov.querySelector('[data-intro-chart]').addEventListener('click', () => {
        try { localStorage.setItem('oracle_intro_seen', '1'); } catch (e) {}
        ov.remove();
      });
    }
  };

  // Гайд первого входа в чат: три коротких шага, только один раз на устройстве.
  // Он не скрывает контент навсегда и всегда может быть закрыт одним тапом.

  app.maybeChatGuide = function() {
    const guideKey = 'oracle_chat_guide_v2';
    try { if (localStorage.getItem(guideKey)) return; } catch (e) { return; }
    if (document.getElementById('intro') || document.getElementById('chat-guide')) return;
    const firstName = this.me && this.me.name ? esc(this.me.name.split(' ')[0]) : '';
    const steps = [
      { e: '✦', t: firstName ? firstName + ', это твоё пространство' : 'Это твоё пространство', d: 'Пиши так, как чувствуешь. Здесь не бывает «неправильных» вопросов — только бережный разговор и ясные ориентиры.' },
      { e: '⌁', t: 'Инструменты — в одном месте', d: 'Нажми одну кнопку «Инструменты» над полем ввода. Там собраны только действия, которые подходят выбранному проводнику.' },
      { e: '◐', t: 'Выбирай своего проводника', d: 'Тапни по имени сверху или листай вкладки вбок. Каждый проводник ведёт свой спокойный разговор и свои ритуалы.' },
    ];
    const ov = document.createElement('div');
    ov.id = 'chat-guide';
    let i = 0;
    const render = () => {
      const s = steps[i];
      ov.innerHTML = `
        <div class="cg-card">
          <div class="cg-emoji">${s.e}</div>
          <div class="cg-title">${s.t}</div>
          <div class="cg-sub">${s.d}</div>
          <div class="cg-dots">${steps.map((_, k) => `<span class="${k === i ? 'active' : ''}"></span>`).join('')}</div>
          <div class="cg-btns">
            <button class="btn btn-ghost" data-cg-skip>Пропустить</button>
            <button class="btn btn-primary" data-cg-next>${i === steps.length - 1 ? 'Понятно ✨' : 'Дальше'}</button>
          </div>
        </div>`;
      ov.querySelector('[data-cg-skip]').addEventListener('click', done);
      ov.querySelector('[data-cg-next]').addEventListener('click', () => {
        haptic('light');
        if (i < steps.length - 1) { i++; render(); }
        else done();
      });
    };
    const done = () => {
      try { localStorage.setItem(guideKey, '1'); } catch (e) {}
      ov.remove();
      haptic('success');
    };
    render();
    document.body.appendChild(ov);
  };

  /* ── каркас ── */

  app.renderFrame = function() {
    const root = document.getElementById('app-root');
    const name = this.me && this.me.name ? this.me.name : 'Мой профиль';
    const initial = this.me && this.me.name ? esc(this.me.name[0].toUpperCase()) : 'О';
    root.innerHTML = `
      <header class="app-header">
        <button class="user-pill" data-act="go" data-goto="profile" aria-label="Открыть профиль: ${esc(name)}">
          <span class="avatar" aria-hidden="true">${initial}</span>
          <span class="user-name">${esc(name)}</span>
        </button>
        <div class="brand-lockup" role="img" aria-label="OracleAI — личное пространство ритуалов">
          <span class="brand-mark" aria-hidden="true">${sigilIcon('brand')}</span>
          <span class="brand-title">ORACLE<small>AI</small></span>
        </div>
        <button class="bell" data-act="bell" aria-label="${oracleLang() === 'en' ? 'Open notifications' : 'Открыть уведомления'}" title="${oracleLang() === 'en' ? 'Notifications' : 'Уведомления'}">
          ${sigilIcon('bell')}<span class="bell-dot" aria-hidden="true"></span>
        </button>
      </header>
      <main id="app-main" tabindex="-1"></main>
      <nav class="app-nav" aria-label="${oracleLang() === 'en' ? 'Main navigation' : 'Основная навигация'}"><div class="main-nav" id="main-nav"></div></nav>`;
    this.renderNav();
    this.refreshBellDot();
  };

  // Точка-непрочитанное на колокольчике: видна один раз за день,
  // пока пользователь не открыл панель уведомлений (флаг в localStorage).
  app.refreshBellDot = function() {
    const bell = document.querySelector('.bell');
    if (!bell) return;
    let unread = false;
    try {
      const todayKey = new Date().toISOString().slice(0, 10);
      unread = localStorage.getItem('oracle_bell_seen') !== todayKey;
    } catch (e) { unread = false; }
    bell.classList.toggle('has-unread', !!unread);
    bell.setAttribute('aria-label', unread
      ? (oracleLang() === 'en' ? 'Notifications · 1 new' : 'Уведомления · есть новое')
      : (oracleLang() === 'en' ? 'Open notifications' : 'Открыть уведомления'));
  };

  app.markBellSeen = function() {
    try { localStorage.setItem('oracle_bell_seen', new Date().toISOString().slice(0, 10)); } catch (e) {}
    this.refreshBellDot();
  };


  app.navItems = function() {
    return [
      { k: 'home', ico: 'home', t: t('today'), hint: t('ritual') },
      { k: 'hub', ico: 'hub', t: t('chats'), hint: t('guides') },
      { k: 'payment', ico: 'monthly', t: t('paymentTab'), hint: t('paymentHint') },
      { k: 'profile', ico: 'profile', t: t('mine'), hint: t('profile') }
    ];
  };

  app.renderNav = function() {
    const active = this.chat.key ? 'hub' : this.view;
    const nav = document.getElementById('main-nav');
    const items = this.navItems();
    const activeIndex = Math.max(0, items.findIndex(n => n.k === active));
    nav.style.setProperty('--nav-index', activeIndex);
    nav.style.setProperty('--nav-count', items.length);
    nav.innerHTML = items.map(n => `
      <button class="nav-btn ${active === n.k ? 'active' : ''}" data-act="go" data-goto="${n.k}" aria-current="${active === n.k ? 'page' : 'false'}" aria-label="${esc(n.t)}: ${esc(n.hint)}">
        <span class="nav-ico">${sigilIcon(n.ico)}</span>
        <span class="nav-copy"><b>${esc(n.t)}</b><small>${esc(n.hint)}</small></span>
      </button>`).join('');
  };

  // 7.1 Telegram BackButton: Android hardware back не закрывает Mini App,
  // а идёт по иерархии: модал → панель инструментов → чат → корневой экран.
  app.syncBackButton = function() {
    if (!tg() || !tg().BackButton) return;
    const back = (() => {
      if (document.getElementById('app-modal')) return () => app.closeModal();
      const tool = document.getElementById('tool-expand');
      if (tool && tool.classList.contains('open')) return () => app.setToolbox(false);
      if (app.chat && app.chat.key) return () => app.closeChat();
      if (app.view !== 'home') return () => app.go('home');
      return null;
    })();
    tg().BackButton.offClick(app._backHandler);
    if (back) {
      app._backHandler = () => { back(); haptic('light'); app.syncBackButton(); };
      tg().BackButton.onClick(app._backHandler);
      tg().BackButton.show();
    } else {
      app._backHandler = null;
      tg().BackButton.hide();
    }
  };

  app.go = function(v) {
    if (v === 'chat') v = 'hub';
    if (v !== 'hub') this.chat.key = null;
    this.view = v;
    this.renderNav();
    this.syncBackButton();
    const main = document.getElementById('app-main');
    if (v === 'home') this.renderHome(main);
    else if (v === 'hub') this.renderHub(main);
    else if (v === 'profile') { this.renderProfile(main); }
    else if (v === 'payment') { this.goPayment(); }
  };


  app.scrollToBottom = function() {
    const box = document.querySelector('.chat-messages, .screen');
    if (box) {
      box.scrollTop = box.scrollHeight;
      // параллакс только на экранах (Сегодня/Агенты/Профиль) — в чате фон
      // не должен двигаться при скролле ленты (иначе выглядит «битым»)
      const sf = document.querySelector('.starfield');
      if (sf && !box.classList.contains('chat-messages')) {
        sf.style.transform = 'translateY(' + (box.scrollTop * 0.08) + 'px)';
      }
    }
  };

  /* ── данные ── */

  app.loadAgents = async function() {
    try { this.agents = await api('/api/agents'); } catch (e) { this.agents = []; }
    if (this.view === 'hub') this.renderHub(document.getElementById('app-main'));
    if (this.view === 'home') this.renderHome(document.getElementById('app-main'));
  };

  app.loadToday = async function() {
    try { this.today = await api('/api/today'); } catch (e) { this.today = null; }
    try { this.moonWeek = await api('/api/moon/week'); } catch (e) { this.moonWeek = null; }
    try {
      const [diary, prompt, practices] = await Promise.all([
        api('/api/diary'),
        api('/api/diary/prompt').catch(() => null),
        api('/api/practices').catch(() => null)
      ]);
      this.dailyPulse = { diary, prompt, practices };
    } catch (e) { this.dailyPulse = null; }
    if (this.view === 'home') this.renderHome(document.getElementById('app-main'));
  };


  const AGENT_BRAND = {
    oracle: { name: 'Лилит', title: 'Личный Оракул', emoji: '🔮', accent: '#e8c56b', accentBright: '#ffe7a3', accentGlow: 'rgba(232,197,107,.34)', surface: 'rgba(232,197,107,.12)', tagline: 'Мягко помогает услышать себя и увидеть следующий шаг.' },
    astro:  { name: 'Урания', title: 'Астролог', emoji: '🌠', accent: '#8cc8ff', accentBright: '#c7e6ff', accentGlow: 'rgba(140,200,255,.34)', surface: 'rgba(140,200,255,.12)', tagline: 'Переводит язык звёзд в ясные опоры на каждый день.' },
    tarot:  { name: 'Мадам Ленорман', title: 'Таролог', emoji: '🃏', accent: '#e7a8d8', accentBright: '#ffd0ec', accentGlow: 'rgba(231,168,216,.34)', surface: 'rgba(231,168,216,.12)', tagline: 'Читает образы карт бережно, точно и по сюжету расклада.' },
    chiromant: { name: 'Мира', title: 'Проводник ладони', emoji: '✋', accent: '#6fd6b0', accentBright: '#b7f5da', accentGlow: 'rgba(111,214,176,.34)', surface: 'rgba(111,214,176,.12)', tagline: 'Собирает карту только различимых зон ладони и честно показывает границы снимка.', avatar: '/static/img/agents/chiromant.jpg' }
  };

  app.normalizeAgent = function(raw, key) {
    const code = (raw && raw.code) || key || 'oracle';
    const brand = AGENT_BRAND[code] || {};
    const agent = Object.assign({}, raw || {}, brand, { code });
    // API может вернуть служебный код вида «oracle» — нормализуем его в имя персонажа.
    if (!agent.name || String(agent.name).toLowerCase() === code) agent.name = brand.name || 'Твой Оракул';
    if (!agent.title) agent.title = brand.title || 'Проводник';
    if (!agent.emoji) agent.emoji = brand.emoji || '✦';
    agent.accent = brand.accent || agent.accent || '#e8c56b';
    agent.accentBright = brand.accentBright || agent.accentBright || agent.accent;
    agent.accentGlow = brand.accentGlow || agent.accentGlow || 'rgba(230,193,120,.34)';
    agent.surface = brand.surface || agent.surface || 'rgba(230,193,120,.12)';
    if (!agent.tagline && brand.tagline) agent.tagline = brand.tagline;
    if (!agent.avatar) agent.avatar = brand.avatar || `/static/img/agents/${esc(code)}.jpg`;
    return agent;
  };

  app.agentThemeStyle = function(raw, key) {
    const a = this.normalizeAgent(raw, key || (raw && raw.code));
    return `--ac:${esc(a.accent)};--ac-bright:${esc(a.accentBright)};--ac-glow:${esc(a.accentGlow)};--ac-surface:${esc(a.surface)}`;
  };

  app.agentSpec = function(key) {
    const a = this.agents.find(x => x.code === key);
    return this.normalizeAgent(a, key);
  };

  /* ═══ ЭКРАН «СЕГОДНЯ» — статичная база ═══ */

