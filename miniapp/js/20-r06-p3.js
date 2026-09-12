/* BUS-1070 p3 R06: Сегодня S15, Библиотека S20, Память S22, Уведомления S23,
 * Тариф S24 (plan/paywall), Ожидание оплаты S25, Заказы S26, Кельтский
 * крест S13, матрица состояний §11.2. Макет: design/r06/p3.
 * Состояние — в app.* (библиотека/заказы/промо/крест), не в DOM.
 */
(function () {
  'use strict';

  function escHtml(s) { return esc(String(s == null ? '' : s)); }
  function en2(ru, en) { return oracleLang() === 'en' ? en : ru; }
  function fmtDate(ts) {
    const d = ts ? new Date(ts) : new Date();
    try { return d.toLocaleDateString(oracleLang(), { day: 'numeric', month: 'long' }); }
    catch (e) { return d.toLocaleDateString(); }
  }

  /* ══ S15: Сегодня (R06) ══════════════════════════════════════════════ */

  app.renderTodayR06 = function (main) {
    if (!main) return;
    const t0 = this.today || {};
    /* /api/today отдаёт forecast строкой; .text — страховка от старого кеша */
    const fc = (typeof t0.forecast === 'string' ? t0.forecast : (t0.forecast && t0.forecast.text)) || '';
    const me = this.me || {};
    const hasBirth = !!me.birth_date;
    const moon = (this.moonWeek && this.moonWeek[0]) || (t0.moon || null);
    const now = new Date();
    const dateLabel = now.toLocaleDateString(oracleLang(), { weekday: 'long', day: 'numeric', month: 'long' });
    const astroAvatar = (app.agents && app.agents.find(function (a) { return a.code === 'astro'; }) || {}).avatar || '/static/img/agents/astro.jpg';

    const kicker = '<div class="today__forecast-kicker"><img src="' + escHtml(astroAvatar) + '" alt="" width="18" height="18" loading="lazy">' + escHtml(en2('Прогноз дня · Урания', 'Daily forecast · Urania')) + '</div>';

    const forecastBlock = fc
      ? '<section class="today__forecast" aria-label="' + escHtml(en2('Прогноз дня', 'Daily forecast')) + '">' + kicker +
          '<p class="today__forecast-text today__forecast--clamped" id="today-fc">' + escHtml(fc) + '</p>' +
          '<button type="button" class="today__expand" aria-expanded="false" aria-controls="today-fc" data-act="today-expand">' + escHtml(en2('Развернуть', 'Expand')) + ' <span aria-hidden="true">▾</span></button>' +
          '<button type="button" class="btn btn--primary btn--block today__ask" data-act="today-ask">' + escHtml(en2('Обсудить день', 'Discuss the day')) + '</button>' +
        '</section>'
      : '<section class="today__forecast" aria-label="' + escHtml(en2('Прогноз дня', 'Daily forecast')) + '">' + kicker +
          '<p class="today__forecast-text">' + escHtml(en2('Прогноз ещё не собран. Он появится утром — или спроси Уранию напрямую.', 'The forecast is not ready yet. It arrives in the morning — or ask Urania directly.')) + '</p>' +
          '<button type="button" class="btn btn--secondary btn--block" data-act="chat-fn" data-chat="astro" data-fn="featureForecast">' + escHtml(en2('Спросить Уранию', 'Ask Urania')) + '</button>' +
        '</section>';

    const cardCard = t0.card
      ? '<button type="button" class="today-card" data-act="day-flip">' +
          '<span class="today-card__icon" aria-hidden="true">🃏</span>' +
          '<span class="today-card__title">' + escHtml(en2('Карта дня', 'Card of the day')) + '</span>' +
          '<span class="today-card__meta">' + escHtml(t0.card.name + (t0.card.meaning ? ' · ' + t0.card.meaning : '')) + '</span>' +
          '<span class="today-card__go">' + escHtml(en2('Открыть карту →', 'Open the card →')) + '</span>' +
        '</button>'
      : '<button type="button" class="today-card today-card--empty" data-act="go" data-goto="hub">' +
          '<span class="today-card__icon" aria-hidden="true">🃏</span>' +
          '<span class="today-card__title">' + escHtml(en2('Карта дня', 'Card of the day')) + '</span>' +
          '<span class="today-card__meta">' + escHtml(en2('Ещё не вытянута. Один тап — и карта дня твоя.', 'Not drawn yet. One tap and the daily card is yours.')) + '</span>' +
          '<span class="today-card__go">' + escHtml(en2('Вытянуть карту →', 'Draw the card →')) + '</span>' +
        '</button>';

    const moonBlock = moon
      ? '<button type="button" class="today-card" data-act="moon">' +
          '<span class="today-card__icon" aria-hidden="true">' + escHtml(moon.emoji || '🌙') + '</span>' +
          '<span class="today-card__title">' + escHtml(en2('Луна недели', 'Moon of the week')) + '</span>' +
          '<span class="today-card__meta">' + escHtml([moon.name, moon.day, moon.advice].filter(Boolean).slice(0, 2).join(' · ')) + '</span>' +
          '<span class="today-card__go">' + escHtml(en2('Полный инструмент →', 'Full tool →')) + '</span>' +
        '</button>'
      : '<button type="button" class="today-card today-card--empty" data-act="moon">' +
          '<span class="today-card__icon" aria-hidden="true">🌙</span>' +
          '<span class="today-card__title">' + escHtml(en2('Луна недели', 'Moon of the week')) + '</span>' +
          '<span class="today-card__meta">' + escHtml(en2('Лунный ритм ещё не загружен — открой инструмент, чтобы посмотреть фазу.', 'The lunar rhythm is not loaded yet — open the tool to see the phase.')) + '</span>' +
          '<span class="today-card__go">' + escHtml(en2('Полный инструмент →', 'Full tool →')) + '</span>' +
        '</button>';

    const diaryToday = this._diaryTodayWritten ? true : false;
    const diaryBlock = diaryToday
      ? '<button type="button" class="today-card" data-act="go" data-goto="profile">' +
          '<span class="today-card__icon" aria-hidden="true">📖</span>' +
          '<span class="today-card__title">' + escHtml(en2('Дневник', 'Diary')) + '</span>' +
          '<span class="today-card__meta">' + escHtml(en2('Сегодня уже записано.', 'Today is already written.')) + '</span>' +
          '<span class="today-card__go">' + escHtml(en2('Прочитать →', 'Read →')) + '</span>' +
        '</button>'
      : '<button type="button" class="today-card today-card--empty" data-act="go" data-goto="profile">' +
          '<span class="today-card__icon" aria-hidden="true">📖</span>' +
          '<span class="today-card__title">' + escHtml(en2('Дневник', 'Diary')) + '</span>' +
          '<span class="today-card__meta">' + escHtml(en2('Сегодня ещё не записано. Две минуты вечером — и день останется с тобой.', 'Nothing written today. Two minutes in the evening and the day stays with you.')) + '</span>' +
          '<span class="today-card__go">' + escHtml(en2('Записать →', 'Write →')) + '</span>' +
        '</button>';

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="section-head">' +
            '<span class="section-head__date">' + escHtml(dateLabel) + '</span>' +
            '<h1 class="section-head__title">' + escHtml(en2('Сегодня', 'Today')) + '</h1>' +
          '</div>' +
          (!hasBirth
            ? '<div class="today__needdata" role="status"><span aria-hidden="true">🌍</span> ' +
                escHtml(en2('Чтобы прогноз был точнее, укажи дату рождения в профиле.', 'For a more precise forecast, add your birth date in the profile.')) +
                ' <button type="button" class="btn btn--ghost" data-act="go" data-goto="welcome">' + escHtml(en2('Заполнить', 'Fill in')) + '</button></div>'
            : '') +
          forecastBlock +
          '<div class="today__blocks">' + cardCard + moonBlock + diaryBlock + '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
    /* Дневник: пишется ли сегодня — узнаём после рендера, молча */
    api('/api/diary').then(function (r) {
      const rows = (r && r.entries) || (Array.isArray(r) ? r : []);
      const todayStr = new Date().toDateString();
      app._diaryTodayWritten = rows.some(function (e) { return e && e.created_at && new Date(e.created_at).toDateString() === todayStr; });
      if (app.view === 'today' && !app._diaryTodayWritten) return; /* начальный render уже верен */
      if (app.view === 'today' && app._diaryTodayWritten) app.renderTodayR06(document.getElementById('app-main'));
    }).catch(function () {});
  };

  app.todayExpand = function (btn) {
    const fc = document.getElementById('today-fc');
    if (!fc || !btn) return;
    const clamped = fc.classList.toggle('today__forecast--clamped');
    btn.setAttribute('aria-expanded', String(!clamped));
    btn.innerHTML = (clamped ? escHtml(en2('Развернуть', 'Expand')) : escHtml(en2('Свернуть', 'Collapse'))) + ' <span aria-hidden="true">' + (clamped ? '▾' : '▴') + '</span>';
  };

  /* ══ S20: Библиотека ══════════════════════════════════════════════════ */

  app.renderLibrary = function (main) {
    if (!main) return;
    const tab = this.libraryTab || 'readings';
    const TABS = [
      { id: 'readings', ru: 'Разборы', en: 'Readings' },
      { id: 'sessions', ru: 'Диалоги', en: 'Conversations' },
      { id: 'diary', ru: 'Дневник', en: 'Diary' }
    ];

    const tabs = '<div class="seg-tabs" role="tablist" aria-label="' + escHtml(en2('Вкладки библиотеки', 'Library tabs')) + '">' +
      TABS.map(function (x) {
        const sel = tab === x.id;
        return '<button type="button" class="seg-tabs__tab" role="tab" aria-selected="' + sel + '" id="tab-' + x.id + '" aria-controls="pane-' + x.id + '" data-act="lib-tab" data-tab="' + x.id + '">' + escHtml(oracleLang() === 'en' ? x.en : x.ru) + '</button>';
      }).join('') +
    '</div>';

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="section-head">' +
            '<h1 class="section-head__title">' + escHtml(en2('Библиотека', 'Library')) + '</h1>' +
            '<p class="section-head__sub">' + escHtml(en2('Всё, что ты уже получила: разборы, диалоги и записи дневника.', 'Everything you have received: readings, conversations and diary entries.')) + '</p>' +
          '</div>' +
          tabs +
          '<div role="tabpanel" id="pane-' + tab + '" aria-labelledby="tab-' + tab + '" style="margin-top:var(--space-3)">' + this._libPane(tab) + '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
    if (!this._libLoaded) this._libLoad();
  };

  app._libPane = function (tab) {
    const st = this._libState || {};
    if (tab === 'sessions') return this._libSessionsPane(st);
    if (tab === 'diary') return this._libDiaryPane(st);
    return this._libReadingsPane(st);
  };

  app._libLoad = function () {
    this._libLoaded = true;
    const st = this._libState = this._libState || {};
    /* /api/history — единый архив: report/tarot/chat/diary в одном ответе
     * с owner-scope. Сессии чата несут только title (privacy: preview=""). */
    api('/api/history').then(function (h) {
      const items = (h && h.items) || [];
      st.readings = items.filter(function (it) { return it.kind === 'report' || it.kind === 'tarot'; });
      st.sessions = items.filter(function (it) { return it.kind === 'chat'; });
      st.diary = items.filter(function (it) { return it.kind === 'diary'; });
      if (app.view === 'library') app.renderLibrary(document.getElementById('app-main'));
    }).catch(function () {
      st.readings = null; st.sessions = null; st.diary = null;
      if (app.view === 'library') app.renderLibrary(document.getElementById('app-main'));
    });
  };

  app._libSkeleton = function () {
    return '<div class="state-cell"><span class="skeleton skeleton--w60"></span>' +
      '<span class="skeleton" style="margin-top:6px"></span>' +
      '<span class="skeleton skeleton--w80" style="margin-top:6px"></span></div>';
  };

  app._libEmpty = function (title, copy, act, data) {
    return '<div class="empty-state">' +
      '<span class="empty-state__icon" aria-hidden="true">✳️</span>' +
      '<div class="empty-state__title">' + escHtml(title) + '</div>' +
      '<p class="empty-state__text">' + escHtml(copy) + '</p>' +
      '<button type="button" class="btn btn--secondary" data-act="' + escHtml(act || 'go') + '"' + (data || '') + '>' + escHtml(en2('Открыть инструменты', 'Open tools')) + '</button>' +
    '</div>';
  };

  app._libReadingsPane = function (st) {
    if (st.readings === undefined) return this._libSkeleton();
    if (st.readings === null) return this._libError();
    const en = oracleLang() === 'en';
    const rows = (st.readings || []).map(function (it) {
      const isTarot = it.kind === 'tarot';
      return {
        kind: it.kind, id: it.entry_id,
        icon: isTarot ? '🃏' : '✳️',
        name: it.title || (isTarot ? (en ? 'Tarot spread' : 'Расклад') : (en ? 'Reading' : 'Разбор')),
        time: it.created_at ? fmtDate(it.created_at) : '',
        preview: it.preview || '',
        src: isTarot ? (en ? 'Madame Lenormand · Tarot reader' : 'Мадам Ленорман · Таролог')
          : (it.source_kind ? it.source_kind : (en ? 'Urania · Astrologer' : 'Урания · Астролог')),
        act: isTarot ? 'reading' : 'report',
        data: isTarot
          ? ' data-id="' + escHtml(String(it.entry_id)) + '"'
          : ' data-kind="' + escHtml(it.source_kind || 'natal') + '" data-report-id="' + escHtml(String(it.entry_id)) + '"'
      };
    });
    if (!rows.length) return this._libEmpty(
      en2('Разборов пока нет', 'No readings yet'),
      en2('Построй натальную карту или вытяни расклад — они появятся здесь.', 'Build a natal chart or draw a reading — they will appear here.'),
      'go', ' data-goto="hub"');
    return '<div class="profile-list">' + rows.map(function (x) {
      return '<button type="button" class="lib-row" data-act="' + x.act + '"' + x.data + '>' +
        '<span class="lib-row__icon" aria-hidden="true">' + x.icon + '</span>' +
        '<span class="lib-row__body">' +
          '<span class="lib-row__top"><span class="lib-row__name">' + escHtml(x.name) + '</span><span class="lib-row__time">' + escHtml(x.time) + '</span></span>' +
          '<span class="lib-row__preview">' + escHtml(x.preview) + '</span>' +
          '<span class="lib-row__src">' + escHtml(x.src) + '</span>' +
        '</span>' +
      '</button>';
    }).join('') + '</div>';
  };

  app._libSessionsPane = function (st) {
    if (st.sessions === undefined) return this._libSkeleton();
    if (st.sessions === null) return this._libError();
    const en = oracleLang() === 'en';
    if (!st.sessions.length) return this._libEmpty(
      en2('Диалогов пока нет', 'No conversations yet'),
      en2('Начни разговор с Лилит или Уранией — он появится здесь.', 'Start a conversation with Lilith or Urania — it will appear here.'),
      'go', ' data-goto="welcome"');
    return '<div class="profile-list">' + st.sessions.map(function (s) {
      const agent = s.source_kind || s.agent || 'oracle';
      return '<button type="button" class="lib-row" data-act="history-chat" data-agent="' + escHtml(agent) + '" data-id="' + escHtml(String(s.entry_id != null ? s.entry_id : s.id)) + '">' +
        '<span class="lib-row__icon" aria-hidden="true">💬</span>' +
        '<span class="lib-row__body">' +
          '<span class="lib-row__top"><span class="lib-row__name">' + escHtml(s.title || (en ? 'Conversation' : 'Диалог')) + '</span><span class="lib-row__time">' + escHtml(fmtDate(s.created_at)) + '</span></span>' +
          /* privacy: архив отдаёт preview="" для чатов — честная строка вместо выдумки */
          '<span class="lib-row__preview">' + escHtml(en ? 'Open to continue reading' : 'Открой диалог, чтобы продолжить чтение') + '</span>' +
          '<span class="lib-row__src">' + escHtml(agent) + '</span>' +
        '</span>' +
      '</button>';
    }).join('') + '</div>';
  };

  app._libDiaryPane = function (st) {
    if (st.diary === undefined) return this._libSkeleton();
    if (st.diary === null) return this._libError();
    if (!st.diary.length) return this._libEmpty(
      en2('Записей пока нет', 'No entries yet'),
      en2('Запиши день вечером — и библиотека начнёт наполняться.', 'Write about your evening — and the library starts filling up.'),
      'go', ' data-goto="profile"');
    return '<div class="profile-list">' + st.diary.map(function (e) {
      return '<button type="button" class="lib-row" data-act="history-diary" data-id="' + escHtml(String(e.entry_id != null ? e.entry_id : e.id)) + '">' +
        '<span class="lib-row__icon" aria-hidden="true">📖</span>' +
        '<span class="lib-row__body">' +
          '<span class="lib-row__top"><span class="lib-row__name">' + escHtml(fmtDate(e.created_at)) + '</span></span>' +
          '<span class="lib-row__preview">' + escHtml(e.preview || (en2('Дневник', 'Diary'))) + '</span>' +
          '<span class="lib-row__src">' + escHtml(en2('Дневник', 'Diary')) + '</span>' +
        '</span>' +
      '</button>';
    }).join('') + '</div>';
  };

  app._libError = function () {
    return '<div class="lib-stale" role="status">' +
      '<span class="lib-stale__icon" aria-hidden="true">⚠️</span>' +
      '<div class="lib-stale__text"><strong>' + escHtml(en2('Библиотека не загрузилась', 'The library did not load')) + '</strong> ' +
      escHtml(en2('— проверь интернет и повтори.', '— check your connection and retry.')) +
      '<div class="lib-stale__actions"><button type="button" class="btn btn--secondary" data-act="lib-retry">' + escHtml(en2('Повторить', 'Retry')) + '</button></div>' +
    '</div></div>';
  };

  app.switchLibTab = function (tab) { this.libraryTab = tab; this.renderLibrary(document.getElementById('app-main')); };
  app.libRetry = function () { this._libLoaded = false; this.renderLibrary(document.getElementById('app-main')); };

  /* ══ S21: Профиль (R06) — карточка + 4 группы строк ═══════════════════ */

  app.renderProfileR06 = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const me = this.me || {};
    const firstName = (me.name || '').split(' ')[0] || (en ? 'You' : 'Ты');
    const plan = me.plan || 'free';
    const planLabel = plan === 'vip_plus' ? 'VIP Plus' : plan === 'vip' ? 'VIP' : (en ? 'Basic' : 'Базовый');
    const birthMeta = me.birth_date
      ? [me.birth_date, me.birth_time_known ? me.birth_time : '', me.birth_city || ''].filter(Boolean).join(' · ')
      : (en ? 'not filled in' : 'не заполнены');
    const memCount = Array.isArray(this._memFull) ? this._memFull.length : null;
    const bgOn = this.bgAnimationEnabled();
    const langLabel = oracleLang() === 'en' ? 'English' : 'Русский';

    const row = function (o) {
      return '<button type="button" class="profile-row' + (o.danger ? ' profile-row--danger' : '') + '"' +
        (o.act ? ' data-act="' + o.act + '"' : '') +
        (o.goto ? ' data-goto="' + o.goto + '"' : '') +
        (o.aria ? ' aria-label="' + escHtml(o.aria) + '"' : '') + '>' +
        '<span class="profile-row__icon" aria-hidden="true">' + o.icon + '</span>' +
        '<span class="profile-row__label">' + escHtml(o.label) + '</span>' +
        (o.value ? '<span class="profile-row__value">' + escHtml(o.value) + '</span>' : '') +
        '<span class="profile-row__chev" aria-hidden="true">›</span>' +
      '</button>';
    };
    const group = function (title, rowsHtml) {
      return '<section class="profile-group" aria-label="' + escHtml(title) + '">' +
        '<h2 class="profile-group__title">' + escHtml(title) + '</h2>' +
        '<div class="profile-list">' + rowsHtml + '</div></section>';
    };

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="section-head"><h1 class="section-head__title">' + escHtml(en ? 'Profile' : 'Профиль') + '</h1></div>' +
          '<div class="profile-card">' +
            '<img class="profile-card__avatar" src="' + escHtml((this.agents && this.agents.find(function (a) { return a.code === 'oracle'; }) || {}).avatar || '/static/img/agents/oracle.jpg') + '" alt="" width="56" height="56" loading="lazy">' +
            '<div class="profile-card__body">' +
              '<div class="profile-card__name">' + escHtml(firstName) + '</div>' +
              '<div class="profile-card__meta">' + escHtml(birthMeta) + '</div>' +
            '</div>' +
            '<span class="profile-card__plan badge badge--accent">' + escHtml(planLabel) + '</span>' +
          '</div>' +
          group(en ? 'Data and memory' : 'Данные и память',
            row({ icon: '🌍', label: en ? 'Birth data' : 'Данные рождения', value: me.birth_date ? (me.birth_date + (me.birth_city ? ' · ' + me.birth_city : '')) : null, act: 'chat', aria: 'chat', goto: null }) +
            row({ icon: '🧠', label: en ? 'Context and memory' : 'Контекст и память', value: memCount != null ? memCount + ' ' + (en ? 'facts' : genFactsRu(memCount)) : null, goto: 'memory-r06' }) +
            row({ icon: '💞', label: en ? 'Saved partners' : 'Сохранённые партнёры', value: '', act: 'all-readings', aria: '', goto: null })
          ) +
          group(en ? 'Plan and payment' : 'Тариф и оплата',
            row({ icon: '✦', label: en ? 'Plan and balance' : 'Тариф и баланс', value: planLabel + ' · ' + (me.crystals != null ? me.crystals : '—') + ' ✦', goto: 'plan-r06' }) +
            row({ icon: '🧾', label: en ? 'Order history' : 'История заказов', goto: 'orders-r06' })
          ) +
          group(en ? 'Settings' : 'Настройки',
            row({ icon: '🔔', label: en ? 'Notifications' : 'Уведомления', goto: 'notifications-r06' }) +
            row({ icon: '🌐', label: en ? 'Language' : 'Язык', value: langLabel, act: 'language' }) +
            row({ icon: '✨', label: en ? 'Background animation' : 'Анимация фона', value: bgOn ? (en ? 'On' : 'Вкл') : (en ? 'Off' : 'Выкл'), act: 'bg-anim' })
          ) +
          group(en ? 'Help and data' : 'Помощь и данные',
            row({ icon: '💬', label: en ? 'Help and support' : 'Помощь и поддержка', act: 'noop' }) +
            row({ icon: '🎁', label: en ? 'Invite a friend' : 'Пригласить подругу', value: '+50 ✦', act: 'ref-copy' }) +
            row({ icon: '📦', label: en ? 'My data' : 'Мои данные', act: 'account-privacy' }) +
            row({ icon: '⚠️', label: en ? 'Delete account' : 'Удалить аккаунт', act: 'account-delete', danger: true })
          ) +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* Русская плюрализация «N факта/фактов» для счётчика памяти */
  function genFactsRu(n) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'факт';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'факта';
    return 'фактов';
  }

  /* ══ S22: Память (подраздел профиля) ═════════════════════════════════ */

  app.renderMemoryR06 = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const memoryOn = !(this.me && this.me.memory_enabled === false);
    const rows = this._memFull;

    const backBtn = '<button type="button" class="screenheader__back" data-act="go" data-goto="profile" aria-label="' + escHtml(en ? 'Back to profile' : 'Назад в профиль') + '"><span aria-hidden="true">‹</span> ' + escHtml(en ? 'Профиль' : 'Profile') + '</button>';
    const header = '<div class="screenheader screenheader--flush">' + backBtn +
      '<div class="screenheader__title">' + escHtml(en ? 'Context and memory' : 'Контекст и память') + '</div></div>';

    let body;
    if (rows === undefined) {
      body = this._libSkeleton();
      api('/api/memories').then(function (r) {
        app._memFull = Array.isArray(r) ? r : [];
        if (app.view === 'memory-r06') app.renderMemoryR06(document.getElementById('app-main'));
      }).catch(function () {
        app._memFull = null;
        if (app.view === 'memory-r06') app.renderMemoryR06(document.getElementById('app-main'));
      });
    } else if (rows === null) {
      body = this._libError();
    } else if (!rows.length) {
      body = this._libEmpty(
        en ? 'It is quiet here for now' : 'Здесь пока тихо',
        memoryOn
          ? (en ? 'Add one fact yourself or share something important in a conversation — Lilith will ask permission before saving it.' : 'Добавь факт вручную или расскажи о важном в диалоге — Лилит спросит разрешение сохранить его.')
          : (en ? 'Turn memory on when you want to keep important things between conversations.' : 'Включи память, когда захочешь сохранять важное между диалогами.'),
        'add-mem', '');
    } else {
      body = '<div class="profile-list">' + rows.map(function (m, i) {
        return '<div class="memory-row" data-mem-row="' + escHtml(String(m.id)) + '">' +
          '<span class="memory-row__text">«' + escHtml(m.fact || '') + '»' +
            '<span class="memory-row__src">' + escHtml(en ? 'saved ' : 'сохранено ') + escHtml((m.created_at || '').slice(0, 10) || (en ? 'earlier' : 'ранее')) + '</span>' +
          '</span>' +
          '<button type="button" class="memory-row__del" data-act="mem-del-confirm" data-id="' + escHtml(String(m.id)) + '" aria-label="' + escHtml(en ? 'Delete fact' : 'Удалить факт') + '">' + escHtml(en ? 'Delete' : 'Удалить') + '</button>' +
        '</div>';
      }).join('') + '</div>';
    }

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' + header +
          '<p class="subpage__lede">' + escHtml(en
            ? 'Lilith remembers what matters between conversations. Every fact can be removed here — the archive belongs to you.'
            : 'Лилит помнит важное между разговорами. Любой факт можно убрать здесь — архив принадлежит тебе.') + '</p>' +
          (!memoryOn ? '<p class="memory-paused-note" role="status">' + escHtml(en ? 'Memory is paused: new facts are not saved, but the archive stays visible.' : 'Память на паузе: новые факты не сохраняются, но архив остаётся видимым.') + '</p>' : '') +
          body +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* Inline-подтверждение удаления (SPEC §6): под фактом, не модалка/тост */
  app._memConfirm = function (id) {
    const row = document.querySelector('[data-mem-row="' + id + '"]');
    if (!row) return;
    const existing = row.querySelector('.memory-confirm');
    if (existing) { existing.remove(); return; }
    const en = oracleLang() === 'en';
    const box = document.createElement('div');
    box.className = 'memory-confirm';
    box.setAttribute('role', 'status');
    box.innerHTML =
      '<p>' + escHtml(en ? 'Delete this fact? Lilith will stop using it. This cannot be undone.' : 'Удалить факт? Лилит перестанет его учитывать. Это нельзя отменить.') + '</p>' +
      '<div class="memory-confirm__actions">' +
        '<button type="button" class="btn btn--ghost" data-act="mem-confirm-cancel">' + escHtml(en ? 'Cancel' : 'Отмена') + '</button>' +
        '<button type="button" class="btn btn--primary" data-act="mem-confirm-yes" data-id="' + escHtml(String(id)) + '">' + escHtml(en ? 'Delete' : 'Удалить') + '</button>' +
      '</div>';
    row.appendChild(box);
  };

  app._memConfirmCancel = function () {
    const box = document.querySelector('.memory-confirm');
    if (box) box.remove();
  };

  app._memConfirmYes = function (id) {
    this._memConfirmCancel();
    /* delMem звать нельзя: он рендерит модалку памяти, а мы — на отдельной странице.
     * Повторяем его минимальный путь: DELETE + обновление _memFull/me. */
    api('/api/memories/' + id, { method: 'DELETE' })
      .then(function () {
        app._memFull = (app._memFull || []).filter(function (m) { return String(m.id) !== String(id); });
        return api('/api/me');
      })
      .then(function (me) { app.me = me; })
      .then(function () { if (app.view === 'memory-r06') app.renderMemoryR06(document.getElementById('app-main')); })
      .catch(function () { if (app.view === 'memory-r06') app.renderMemoryR06(document.getElementById('app-main')); });
  };

  /* ══ S23: Уведомления (подраздел профиля) ════════════════════════════ */

  app.renderNotificationsR06 = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const me = this.me || {};
    const morning = !(me.morning_push === false);

    function switchRow(name, hint, key, checked) {
      return '<div class="notif-demo-row">' +
        '<div class="notif-demo-row__body"><div class="notif-demo-row__name">' + escHtml(name) + '</div><div class="notif-demo-row__hint">' + escHtml(hint) + '</div></div>' +
        '<label class="switch switch--r06"><input type="checkbox"' + (checked ? ' checked' : '') + ' data-act="notif-toggle" data-key="' + key + '" aria-label="' + escHtml(name) + '"><span class="switch__track" aria-hidden="true"></span><span class="switch__thumb" aria-hidden="true"></span></label>' +
      '</div>';
    }

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="screenheader screenheader--flush">' +
            '<button type="button" class="screenheader__back" data-act="go" data-goto="profile" aria-label="' + escHtml(en ? 'Back to profile' : 'Назад в профиль') + '"><span aria-hidden="true">§</span> ' + escHtml(en ? 'Профиль' : 'Профиль') + '</button>' +
            '<div class="screenheader__title">' + escHtml(en ? 'Notifications' : 'Уведомления') + '</div>' +
          '</div>' +
          '<p class="subpage__lede">' + escHtml(en
            ? 'Reminders arrive in Telegram. The delivery time uses your current time zone — it may differ from your birth city.'
            : 'Напоминания приходят в Telegram. Время доставки считается по твоему текущему часовому поясу — он может отличаться от города рождения.') + '</p>' +
          '<div class="profile-list">' +
            switchRow(en ? 'Daily forecast' : 'Прогноз дня', en ? 'Every morning' : 'Каждое утро', 'morning', morning) +
            switchRow(en ? 'Lunar rhythm' : 'Лунный ритм', en ? 'Phase start · every few days' : 'Начало фазы · раз в несколько дней', 'moon', morning) +
            switchRow(en ? 'Pause all notifications' : 'Пауза всех уведомлений', en ? 'Toggled on and off here' : 'Включается и снимается здесь же', 'pause', false) +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  app._notifToggle = function (key) {
    const en = oracleLang() === 'en';
    /* Бекенд поддерживает только morning_forecast (notifications.py).
     * toggleMorningNotifications после PATCH открывает колокольчик-модалку —
     * на странице R06 перерисовываем себя вместо модалки. */
    if (key === 'morning' || key === 'moon') {
      const next = !(this.me && this.me.morning_push);
      api('/api/notifications/preferences', { method: 'PATCH', body: JSON.stringify({ morning_forecast: next }) })
        .then(function (r) {
          app.me = Object.assign({}, app.me, { morning_push: !!(r && r.morning_forecast) });
          if (app.view === 'notifications-r06') app.renderNotificationsR06(document.getElementById('app-main'));
        })
        .catch(function () {
          app.toast(en ? 'Notification settings are temporarily unavailable.' : 'Настройки уведомлений временно недоступны.');
          if (app.view === 'notifications-r06') app.renderNotificationsR06(document.getElementById('app-main'));
        });
      return;
    }
    this.toast(en ? 'Pause is managed in Telegram bot settings.' : 'Пауза управляется в настройках бота Telegram.');
  };

  /* ══ S24: Тариф и баланс ═════════════════════════════════════════════ */

  app.renderPlanR06 = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const me = this.me || {};
    const crystals = (me.crystals != null) ? me.crystals : '—';

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="screenheader screenheader--flush">' +
            '<button type="button" class="screenheader__back" data-act="go" data-goto="profile" aria-label="' + escHtml(en ? 'Back to profile' : 'Назад в профиль') + '"><span aria-hidden="true">‹</span> ' + escHtml(en ? 'Профиль' : 'Профиль') + '</button>' +
            '<div class="screenheader__title">' + escHtml(en ? 'Plan and balance' : 'Тариф и баланс') + '</div>' +
          '</div>' +
          '<div class="balance-box">' +
            '<span class="balance-box__icon" aria-hidden="true">✦</span>' +
            '<span class="balance-box__body"><span class="balance-box__label">' + escHtml(en ? 'Your Crystals' : 'Твои Кристаллы') + '</span>' +
            '<span class="balance-box__amount">' + escHtml(String(crystals)) + ' ✦</span></span>' +
            '<button type="button" class="btn btn--secondary balance-box__buy" data-act="payment-retry">' + escHtml(en ? 'Top up' : 'Пополнить') + '</button>' +
          '</div>' +
          this._planCardCurrent() +
          '<div class="pay-methods" role="group" aria-label="' + escHtml(en ? 'Payment method' : 'Способ оплаты') + '">' +
            '<button type="button" class="pay-method pay-method--r06" aria-pressed="true" data-act="r06-pay-stars"><span class="pay-method__icon" aria-hidden="true">⭐</span><span class="pay-method__copy"><b>' + escHtml(en ? 'Telegram Stars' : 'Telegram Stars') + '</b><small>' + escHtml(en ? 'in the Telegram window' : 'в окне Telegram') + '</small></span></button>' +
            '<button type="button" class="pay-method pay-method--r06" aria-pressed="false" data-act="r06-pay-crypto"><span class="pay-method__icon" aria-hidden="true">💎</span><span class="pay-method__copy"><b>' + escHtml(en ? 'Crypto payment' : 'Криптоплатёж') + '</b><small>TON · USDT</small></span></button>' +
          '</div>' +
          '<button type="button" class="btn btn--primary btn--block" data-act="payment-retry" style="margin-top:var(--space-4)">' + escHtml(en ? 'Open catalog' : 'Открыть каталог') + '</button>' +
          this._promoBlock() +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  app._planCardCurrent = function () {
    const en = oracleLang() === 'en';
    const me = this.me || {};
    const plan = me.plan || 'free';
    const isVip = plan === 'vip' || plan === 'vip_plus';
    const planLabel = plan === 'vip_plus' ? 'VIP Plus' : plan === 'vip' ? 'VIP' : (en ? 'Free' : 'Базовый');
    return '<section class="plan-card plan-card--current" aria-label="' + escHtml(en ? 'Current plan' : 'Текущий тариф') + '">' +
      '<div class="plan-card__top"><span class="plan-card__name">' + escHtml(planLabel) + '</span>' + (isVip ? '<span class="plan-card__badge">' + escHtml(en ? 'Current' : 'Текущий') + '</span>' : '') + '</div>' +
      '<p class="plan-card__tagline">' + escHtml(isVip
        ? (en ? 'Your personal AI guide, memory and regular depth.' : 'Личный AI-проводник, память и регулярная глубина.')
        : (en ? 'Daily signs and one question per day.' : 'Знаки дня и один вопрос в день.')) + '</p>' +
      '<ul class="plan-card__list">' +
        '<li>' + escHtml(en ? 'Unlimited conversations with Lilith' : 'Неограниченные разговоры с Лилит') + '</li>' +
        '<li>' + escHtml(en ? 'Tarot spreads included, personal meaning separately' : 'Расклады Таро — включены, личный смысл отдельно') + '</li>' +
      '</ul>' +
    '</section>';
  };

  /* Промокод: form state (SPEC §6 — не replaceWith), отправка в /api/shop/promo */
  app._promoBlock = function () {
    const en = oracleLang() === 'en';
    return '<div class="promo-box">' +
      '<button type="button" class="promo-link" aria-expanded="' + (this._promoOpen ? 'true' : 'false') + '" aria-controls="promo-form" data-act="promo-toggle">' + escHtml(en ? 'Have a promo code?' : 'Есть промокод?') + '</button>' +
      '<div class="promo-form" id="promo-form"' + (this._promoOpen ? '' : ' hidden') + '>' +
        '<input class="field__input" id="promo-code" type="text" placeholder="' + escHtml(en ? 'Enter promo code' : 'Введите промокод') + '" aria-label="' + escHtml(en ? 'Promo code' : 'Промокод') + '">' +
        '<button type="button" class="btn btn--secondary" data-act="promo-apply">' + escHtml(en ? 'Apply' : 'Применить') + '</button>' +
      '</div>' +
    '</div>';
  };

  app._promoToggle = function (btn) {
    this._promoOpen = !this._promoOpen;
    const form = document.getElementById('promo-form');
    if (form) form.hidden = !this._promoOpen;
    if (btn) btn.setAttribute('aria-expanded', String(this._promoOpen));
    if (this._promoOpen) { const inp = document.getElementById('promo-code'); if (inp) inp.focus(); }
  };

  app._promoApply = function () {
    const inp = document.getElementById('promo-code');
    if (!inp) return;
    const code = inp.value.trim();
    const en = oracleLang() === 'en';
    const wrap = inp.closest('.promo-form');
    let note = document.getElementById('promo-note');
    if (!note && wrap) {
      note = document.createElement('p');
      note.id = 'promo-note';
      note.className = 'field__error';
      note.setAttribute('role', 'alert');
      wrap.appendChild(note);
    }
    if (!code) { if (note) note.textContent = en ? 'Enter the code first' : 'Сначала введи код'; return; }
    if (note) note.textContent = en ? 'Checking the code…' : 'Проверяем код…';
    api('/api/shop/promo', { method: 'POST', body: JSON.stringify({ code: code }) }).then(function (r) {
      if (note) note.textContent = (r && r.ok) ? (en ? 'Promo code applied!' : 'Промокод применён!') : (en ? 'Code not accepted' : 'Код не принят');
    }).catch(function () {
      if (note) note.textContent = en ? 'Code not accepted' : 'Код не принят';
    });
  };

  /* ══ S24b: Paywall (H6/E16: возврат к намерению после оплаты) ════════ */

  app.renderPaywall = function (main, opts) {
    if (!main) return;
    const en = oracleLang() === 'en';
    /* Откуда пришёл paywall — туда и вернёмся; дефолт hub */
    const returnTo = (opts && opts.return_to) || this._paywallReturn || 'hub';
    const returnLabel = (opts && opts.return_label) || this._paywallLabel || (en ? 'the conversation' : 'диалог');
    this._paywallReturn = returnTo;
    this._paywallLabel = returnLabel;

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="tool-view" style="max-width:560px">' +
            '<header class="screenheader screenheader--flush">' +
              '<button type="button" class="screenheader__back" data-act="paywall-back" aria-label="' + escHtml(en ? 'Back' : 'Назад') + '"><span aria-hidden="true">‹</span> ' + escHtml(t('toolBack')) + '</button>' +
              '<div class="screenheader__title">' + escHtml(en ? 'VIP plan' : 'Тариф VIP') + '</div>' +
            '</header>' +
            '<div class="paywall__return-note" role="status">' +
              '<span aria-hidden="true">↩</span> ' +
              (en ? 'After payment you return to <strong>' + escHtml(returnLabel) + '</strong> — the draft and the question are saved.' : 'После оплаты вернёшься к <strong>' + escHtml(returnLabel) + '</strong> — черновик и вопрос сохранены.') +
            '</div>' +
            '<section class="plan-card plan-card--current paywall__card">' +
              '<div class="plan-card__top"><span class="plan-card__name">VIP</span></div>' +
              '<div class="paywall__price-row"><span class="paywall__price">490 ₽</span><span class="paywall__period">' + escHtml(en ? 'per month · cancel any time' : 'в месяц · отмена в любой момент') + '</span></div>' +
              '<ul class="plan-card__list paywall__what">' +
                '<li>' + escHtml(en ? 'Unlimited conversations with Lilith' : 'Неограниченные разговоры с Лилит') + '</li>' +
                '<li>' + escHtml(en ? 'Natal chart and Urania readings' : 'Натальная карта и разборы Урании') + '</li>' +
                '<li>' + escHtml(en ? 'Tarot spreads included' : 'Расклады Таро — включены') + '</li>' +
              '</ul>' +
              '<button type="button" class="btn btn--primary btn--block" data-act="paywall-pay">' + escHtml(en ? 'Pay via Telegram Stars' : 'Оплатить через Telegram Stars') + '</button>' +
              '<p class="paywall__legal">' + escHtml(en ? 'Payment happens in the Telegram window. We never see or store card data.' : 'Оплата проходит в окне Telegram. Мы не видим и не храним данные карты.') + '</p>' +
              '<button type="button" class="btn btn--ghost btn--block paywall__no" data-act="paywall-back">' + escHtml(en ? 'Not now' : 'Не сейчас') + '</button>' +
            '</section>' +
            this._promoBlock() +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  app._paywallBack = function () {
    const target = this._paywallReturn || 'hub';
    this._paywallReturn = null;
    this._paywallLabel = null;
    this.go(target);
  };

  app._paywallPay = function () {
    /* Оплата открывает прод-каталог (17-payments), paywall хранит возврат */
    this.goPayment();
  };

  /* ══ S25: Ожидание оплаты (E17: закрытие окна ≠ оплата) ══════════════ */

  app.renderPayPending = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="screenheader screenheader--flush">' +
            '<button type="button" class="screenheader__back" data-act="go" data-goto="plan-r06" aria-label="' + escHtml(en ? 'Back to plan' : 'Назад к тарифу') + '"><span aria-hidden="true">‹</span> ' + escHtml(en ? 'Тариф' : 'Тариф') + '</button>' +
            '<div class="screenheader__title">' + escHtml(en ? 'Checking payment' : 'Ожидание оплаты') + '</div>' +
          '</div>' +
          '<div class="pay-pending" role="status" style="margin-top:var(--space-3)">' +
            '<div class="tool-run__spinner" aria-hidden="true"></div>' +
            '<div class="pay-pending__title">' + escHtml(en ? 'Checking your payment' : 'Проверяем оплату') + '</div>' +
            '<p class="pay-pending__text">' + escHtml(en
              ? 'This usually takes less than a minute. The invoice is already created — do not pay again, even if the window closed.'
              : 'Это занимает обычно меньше минуты. Счёт уже создан — не оплачивай повторно, даже если окно закрылось.') + '</p>' +
            '<button type="button" class="btn btn--secondary" data-act="pay-check-status">' + escHtml(en ? 'Check status' : 'Проверить статус') + '</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  app._payCheckStatus = function () {
    /* Сверка статуса на сервере (E17): заказы перечитываются, вид перерисуется */
    this._ordersLoaded = false;
    this._ordersLoad().then(function () {
      if (app.view === 'pay-pending') app.go('orders-r06');
      else if (app.view === 'orders-r06') app.renderOrdersR06(document.getElementById('app-main'));
    });
  };

  /* ══ S26: История заказов ════════════════════════════════════════════ */

  app.renderOrdersR06 = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const st = this._ordersState || {};

    const CHIP = {
      paid: { cls: 'paid', ru: 'Оплачен', en: 'Paid' },
      pending: { cls: 'pending', ru: 'Ожидает', en: 'Pending' },
      refunded: { cls: 'refunded', ru: 'Возвращён', en: 'Refunded' },
      failed: { cls: 'failed', ru: 'Ошибка', en: 'Failed' }
    };
    function chip(status) {
      const c = CHIP[status] || { cls: 'pending', ru: 'Ожидает', en: 'Pending' };
      return '<span class="status-chip status-chip--' + c.cls + '">' + escHtml(en ? c.en : c.ru) + '</span>';
    }

    let body;
    if (st.rows === undefined) {
      body = this._libSkeleton();
      this._ordersLoad();
    } else if (st.rows === null) {
      body = this._libError();
    } else if (!st.rows.length) {
      body = this._libEmpty(
        en ? 'No orders yet' : 'Заказов пока нет',
        en ? 'Subscriptions and purchases will appear here.' : 'Подписки и покупки появятся здесь.',
        'go', ' data-goto="plan-r06"');
    } else {
      body = '<div class="profile-list">' + st.rows.map(function (o) {
        const stars = o.amount_stars ? (o.amount_stars + ' ⭐') : '';
        const meta = [o.created_at ? fmtDate(o.created_at) : '', stars, o.provider || ''].filter(Boolean).join(' · ');
        return '<div class="order-row">' +
          '<span class="order-row__body">' +
            '<span class="order-row__name">' + escHtml(o.title || (en ? 'Purchase' : 'Покупка')) + '</span>' +
            '<span class="order-row__meta">' + escHtml(meta) + '</span>' +
          '</span>' +
          chip(o.status) +
          (o.status === 'pending' ? '<button type="button" class="btn btn--ghost order-row__check" data-act="pay-check-status">' + escHtml(en ? 'Check status' : 'Проверить статус') + '</button>' : '') +
        '</div>';
      }).join('') + '</div>';
    }

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="screenheader screenheader--flush">' +
            '<button type="button" class="screenheader__back" data-act="go" data-goto="profile" aria-label="' + escHtml(en ? 'Back to plan' : 'Назад к тарифу') + '"><span aria-hidden="true">‹</span> ' + escHtml(en ? 'План' : 'Тариф') + '</button>' +
            '<div class="screenheader__title">' + escHtml(en ? 'Order history' : 'История заказов') + '</div>' +
          '</div>' +
          '<div style="margin-top:var(--space-3)">' + body + '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* Единый источник заказов — /api/shop/payment-history (стадии на сервере) */
  app._ordersLoad = function () {
    const st = this._ordersState = { rows: undefined };
    return api('/api/shop/payment-history').then(function (rows) {
      st.rows = Array.isArray(rows) ? rows : [];
      if (app.view === 'orders-r06') app.renderOrdersR06(document.getElementById('app-main'));
    }).catch(function () {
      st.rows = null;
      if (app.view === 'orders-r06') app.renderOrdersR06(document.getElementById('app-main'));
    });
  };

  /* ══ S13 большой: Кельтский крест — сетка 10 позиций + список ═════════ */

  /* Класс .tarot-grid занят каруселью — тут scoped .tarot-cross.
   * Колода — 78 существующих изображений; порядок открытия — §6.4. */
  app.renderTarotGrid = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const state = this.tarotRun || (this.tarotRun = {});
    if (!state.crossCards) state.crossCards = app._tarotDeck10();
    const cards = state.crossCards;
    const opened = state.crossOpened || 0;

    const POSITIONS = [
      { n: 1, ru: 'Суть', en: 'Essence' },
      { n: 2, ru: 'Пересечение', en: 'Crossing' },
      { n: 3, ru: 'Основание', en: 'Foundation' },
      { n: 4, ru: 'Недавнее прошлое', en: 'Recent past' },
      { n: 5, ru: 'Возможное', en: 'Possible' },
      { n: 6, ru: 'Ближайшее будущее', en: 'Near future' },
      { n: 7, ru: 'Ты сама', en: 'You yourself' },
      { n: 8, ru: 'Окружение', en: 'Environment' },
      { n: 9, ru: 'Надежды и страхи', en: 'Hopes and fears' },
      { n: 10, ru: 'Итог', en: 'Outcome' }
    ];

    const cells = POSITIONS.map(function (p) {
      const c = cards[p.n - 1] || {};
      const isOpen = p.n <= opened;
      const label = (en ? 'Position ' : 'Позиция ') + p.n + ', ' + (en ? p.en : p.ru) +
        (isOpen ? (en ? '. Card: ' : '. Карта: ') + (c.name || '') : '');
      return '<button type="button" class="tarot-cross__cell' + (isOpen ? ' is-open' : '') + '" aria-pressed="' + isOpen + '" aria-label="' + escHtml(label) + '" data-act="tarot-cross-open" data-pos="' + p.n + '">' +
        '<span class="tarot-cross__cell-num" aria-hidden="true">' + p.n + '</span>' +
        (isOpen
          ? '<img class="tarot-cross__cell-img" src="/static/img/tarot/' + escHtml(c.img || 'm00') + '.jpg" alt="' + escHtml((c.name || '') + ', ' + (en ? 'position ' : 'позиция ') + p.n) + '" width="120" height="200" loading="lazy">'
          : '<span class="tarot-cross__back" aria-hidden="true"></span>') +
      '</button>';
    }).join('');

    const listRows = POSITIONS.map(function (p) {
      const c = cards[p.n - 1] || {};
      const isOpen = p.n <= opened;
      return '<p style="margin:0 0 6px">' + p.n + ' · ' + escHtml(en ? p.en : p.ru) + ' — ' +
        (isOpen ? escHtml(c.name || '—') : escHtml(en ? 'closed' : 'закрыта')) + '</p>';
    }).join('');

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="tool-view" style="max-width:640px">' +
            '<header class="screenheader screenheader--flush">' +
              '<button type="button" class="screenheader__back" data-act="tool-back" aria-label="' + escHtml(en ? 'Back' : 'Назад') + '"><span aria-hidden="true">‹</span> ' + escHtml(t('toolBack')) + '</button>' +
              '<div class="screenheader__title">' + escHtml(en ? 'Celtic Cross · 10 cards' : 'Кельтский крест · 10 карт') + '</div>' +
            '</header>' +
            '<p class="tarot-scene__status" style="margin-bottom:var(--space-3)">' +
              (en ? 'Opened {n} of 10 · open in position order'.replace('{n}', opened) : 'Открыто ' + opened + ' из 10 · открывай по порядку позиций') +
            '</p>' +
            '<div class="tarot-cross" role="group" aria-label="' + escHtml(en ? 'Spread positions' : 'Позиции расклада') + '">' + cells + '</div>' +
            '<details class="result-details">' +
              '<summary class="result-details__summary">' + escHtml(en ? 'Positions as a list' : 'Позиции списком') + '</summary>' +
              '<div class="result-details__body">' + listRows + '</div>' +
            '</details>' +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* 10 карт для креста из существующей колоды (0 новых изображений) */
  app._tarotDeck10 = function () {
    const imgs = ['m00', 'm01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08', 'm09'];
    const names = ['Шут', 'Маг', 'Жрица', 'Императрица', 'Император', 'Иерофант', 'Влюблённые', 'Колесница', 'Сила', 'Отшельник'];
    const namesEn = ['The Fool', 'The Magician', 'The High Priestess', 'The Empress', 'The Emperor', 'The Hierophant', 'The Lovers', 'The Chariot', 'Strength', 'The Hermit'];
    const en = oracleLang() === 'en';
    return imgs.map(function (img, i) {
      return { img: img, name: en ? namesEn[i] : names[i] };
    });
  };

  app.tarotCrossOpen = function (pos) {
    const state = this.tarotRun;
    if (!state || !state.crossCards) return;
    const opened = state.crossOpened || 0;
    if (pos <= opened) return; /* уже открыта — клетка показывает карту, повторный тап не нужен */
    /* §6.4: открытие строго по порядку — следующая позиция = opened+1 */
    if (pos !== opened + 1) { this._tarotWarnOrder(pos); return; }
    state.crossOpened = pos;
    tactile('select');
    this.renderTarotGrid(document.getElementById('app-main'));
    if (pos === state.crossCards.length) this._announceTarotDone();
  };

  /* ══ Матрица состояний §11.2 (qa-вид, кадры из SPEC) ═════════════════ */

  app.renderStates = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';

    function frame(title, inner) {
      return '<section class="profile-group" aria-label="' + escHtml(title) + '">' +
        '<h2 class="profile-group__title">' + escHtml(title) + '</h2>' +
        '<div class="state-cell">' + inner + '</div>' +
      '</section>';
    }

    main.innerHTML =
      '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="section-head">' +
            '<h1 class="section-head__title">' + escHtml(en ? 'State matrix' : 'Матрица состояний') + '</h1>' +
            '<p class="section-head__sub">' + escHtml(en ? 'State frames from the SPEC. Each screen uses only its own class of state.' : 'Кадры состояний из SPEC. Каждый экран использует только свой класс состояния.') + '</p>' +
          '</div>' +
          frame(en ? 'Loading (skeleton)' : 'Загрузка (skeleton)',
            '<span class="skeleton skeleton--w60"></span><span class="skeleton" style="margin-top:6px"></span><span class="skeleton skeleton--w80" style="margin-top:6px">') +
          frame(en ? 'Empty (no data — not zero)' : 'Пусто (нет данных — не ноль)',
            '<div class="empty-state"><span class="empty-state__icon" aria-hidden="true">✳️</span>' +
            '<div class="empty-state__title">' + escHtml(en ? 'No readings yet' : 'Разборов пока нет') + '</div>' +
            '<p class="empty-state__text">' + escHtml(en ? 'Build a natal chart or draw a reading — they will appear here.' : 'Построй натальную карту или вытяни расклад — они появятся здесь.') + '</p>' +
            '<button type="button" class="btn btn--secondary" data-act="go" data-goto="hub">' + escHtml(en ? 'Open tools' : 'Открыть инструменты') + '</button></div>') +
          frame(en ? 'No access → paywall (H6)' : 'Нет доступа → paywall (H6)',
            '<div class="paywall__return-note" role="status"><span aria-hidden="true">✦</span> ' +
            escHtml(en ? 'The synastry reading is part of VIP. The draft is saved — you will return to it after payment.' : 'Разбор синастрии входит в VIP. Черновик сохранён — вернёшься к нему после оплаты.') +
            '<div class="lib-stale__actions"><button type="button" class="btn btn--primary" data-act="go" data-goto="plan-r06">' + escHtml(en ? 'See plans' : 'Смотреть тариф') + '</button> ' +
            '<button type="button" class="btn btn--ghost" data-act="paywall-back">' + escHtml(en ? 'Not now' : 'Не сейчас') + '</button></div></div>') +
          frame(en ? 'Network error / offline' : 'Ошибка сети / offline',
            '<div class="lib-stale" role="status"><span class="lib-stale__icon" aria-hidden="true">⚠️</span>' +
            '<div class="lib-stale__text"><strong>' + escHtml(en ? 'No connection' : 'Нет соединения') + '</strong> ' +
            escHtml(en ? '— the forecast did not load. Retry when you are back online.' : '— прогноз не загрузился. Повтори, когда появится сеть.') +
            '<div class="lib-stale__actions"><button type="button" class="btn btn--secondary" data-act="go" data-goto="today">' + escHtml(en ? 'Retry' : 'Повторить') + '</button></div>' +
            '</div></div>') +
          frame(en ? 'Session expired' : 'Сессия истекла',
            '<div class="lib-stale" role="alert"><span class="lib-stale__icon" aria-hidden="true">🔐</span>' +
            '<div class="lib-stale__text"><strong>' + escHtml(en ? 'Session expired' : 'Сессия истекла') + '</strong> ' +
            escHtml(en ? '— restart the app to continue. Data and drafts are saved.' : '— перезапусти приложение, чтобы продолжить. Данные и черновики сохранены.') +
            '<div class="lib-stale__actions"><button type="button" class="btn btn--primary" data-act="go" data-goto="welcome">' + escHtml(en ? 'Restart' : 'Перезапустить') + '</button></div>' +
            '</div></div>') +
          frame(en ? 'Not found (deep link, H10)' : 'Не найдено (deep link, H10)',
            '<div class="lib-stale" role="status"><span class="lib-stale__icon" aria-hidden="true">🔍</span>' +
            '<div class="lib-stale__text"><strong>' + escHtml(en ? 'Reading not found' : 'Разбор не найден') + '</strong> ' +
            escHtml(en ? '— it may have been deleted or the link is outdated.' : '— возможно, он удалён или ссылка устарела.') +
            '<div class="lib-stale__actions"><button type="button" class="btn btn--secondary" data-act="go" data-goto="library">' + escHtml(en ? 'To library' : 'В библиотеку') + '</button></div>' +
            '</div></div>') +
          frame(en ? 'Field error (at the field)' : 'Ошибка поля (у поля)',
            '<div class="field" style="max-width:360px">' +
            '<label class="field__label" for="st-city">' + escHtml(en ? 'Birth city' : 'Город рождения') + '</label>' +
            '<input class="field__input" id="st-city" value="' + escHtml(en ? 'Mosc' : 'Москв') + '" aria-invalid="true" aria-describedby="st-city-err">' +
            '<p class="field__error" id="st-city-err">' + escHtml(en ? 'Pick a city from the suggestions — so the time zone is correct' : 'Выбери город из подсказок — так часовой пояс будет верным') + '</p>' +
            '</div>') +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };
}());
