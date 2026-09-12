/* BUS-1070 p2 R06: инструменты S11 (quick/form/run) + результат S12 +
 * Таро S13 (question/reveal/zoom/reading). Макет: design/r06/p2.
 * Состояние таро (вопрос, расклад, счётчик открытий) — в app.tarotRun, не в DOM.
 */
(function () {
  'use strict';

  const TOOL_AGENTS = {
    forecast: { code: 'astro', name: 'Урания', role: 'Астролог' },
    syn: { code: 'astro', name: 'Урания', role: 'Астролог' },
    tarot: { code: 'tarot', name: 'Мадам Ленорман', role: 'Таролог' }
  };

  function agentAvatar(code) {
    const agents = (app.agents && app.agents.length) ? app.agents : (typeof AGENT_FALLBACK !== 'undefined' ? AGENT_FALLBACK : []);
    const a = agents.find(function (x) { return x.code === code; });
    return a && a.avatar ? a.avatar : '/static/img/oracle-mark.png';
  }

  function escHtml(s) { return esc(String(s == null ? '' : s)); }
  function tf(key) { return t(key) !== key ? t(key) : t(key, ''); }
  /* i18n с подстановкой {n}/{m} */
  function tn(key, n, m, fallback) {
    let s = t(key, fallback || key);
    s = s.replace('{n}', String(n)).replace('{m}', String(m));
    return s;
  }

  /* Кнопка назад в шапках */
  function backBtn(label) {
    return '<button type="button" class="screenheader__back" data-act="tool-back" aria-label="' + escHtml(label) + '"><span aria-hidden="true">‹</span></button>';
  }

  function fmtDate(ts) {
    const d = ts ? new Date(ts) : new Date();
    try { return d.toLocaleDateString(oracleLang(), { day: 'numeric', month: 'long' }); }
    catch (e) { return d.toLocaleDateString(); }
  }

  /* ══ S11a: быстрый инструмент (прогноз дня) ══════════════════════════ */

  app.renderToolQuick = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const ag = TOOL_AGENTS.forecast;
    main.innerHTML =
      '<div class="tool-view">' +
        '<header class="screenheader screenheader--flush">' + backBtn(t('toolBack')) +
          '<div class="screenheader__title">' + escHtml(t('toolForecastTitle')) + '</div>' +
        '</header>' +
        '<div class="tool-view__kicker"><img src="' + escHtml(agentAvatar(ag.code)) + '" alt="" aria-hidden="true">' + escHtml(ag.name) + ' · ' + escHtml(ag.role) + '</div>' +
        '<h1 class="tool-view__title">' + escHtml(t('toolForecastTitle')) + '</h1>' +
        '<p class="tool-view__why">' + escHtml(t('toolForecastWhy')) + '</p>' +
        '<label class="tarot-question__label" for="tq-date">' + escHtml(t('toolForecastDate')) + '</label>' +
        '<input id="tq-date" type="date" class="field__input tarot-question__input" value="' + new Date().toISOString().slice(0, 10) + '">' +
        '<div class="tool-view__footer">' +
          '<p class="tool-view__terms">' + t('toolForecastTerms') + '</p>' + /* содержит <strong> из i18n — экранировать нельзя */
          '<button type="button" class="btn btn--primary btn--block" data-act="tool-submit" data-tool="forecast">' + escHtml(t('toolForecastSubmit')) + '</button>' +
          '<p class="tool-view__draft-note">' + escHtml(t('toolDraftNote')) + '</p>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* ══ S11b: инструмент с формой (синастрия) ══════════════════════════ */

  app.renderToolForm = function (main) {
    if (!main) return;
    const me = this.me || {};
    const bd = me.birth_date || '';
    const bday = bd.slice(8, 10) || '05', bmon = bd.slice(5, 7) || '03', byr = bd.slice(0, 4) || '1994';
    const city = me.birth_city || '—';
    main.innerHTML =
      '<div class="tool-view">' +
        '<header class="screenheader screenheader--flush">' + backBtn(t('toolBack')) +
          '<div class="screenheader__title">' + escHtml(t('toolSynTitle')) + '</div>' +
        '</header>' +
        '<div class="tool-view__kicker"><img src="' + escHtml(agentAvatar('astro')) + '" alt="" aria-hidden="true">Урания · Астролог</div>' +
        '<h1 class="tool-view__title">' + escHtml(t('toolSynTitle')) + '</h1>' +
        '<p class="tool-view__why">' + escHtml(t('toolSynWhy')) + '</p>' +
        '<section class="review-list" aria-label="' + escHtml(t('toolSynYourData')) + '">' +
          '<div class="review-row"><span class="review-row__label">' + escHtml(t('dateLbl') || t('resDate')) + '</span><span class="review-row__value">' + escHtml(bday + '.' + bmon + '.' + byr) + '</span><button type="button" class="btn btn--ghost" data-act="tool-back">' + escHtml(t('toolSynEdit')) + '</button></div>' +
          '<div class="review-row"><span class="review-row__label">' + escHtml(t('city') || '—') + '</span><span class="review-row__value">' + escHtml(city) + '</span></div>' +
        '</section>' +
        '<fieldset class="onboarding__fields" style="border:0;padding:0;margin:16px 0 0">' +
          '<legend class="tarot-question__label">' + escHtml(t('toolSynDate')) + '</legend>' +
          '<div class="date-seg">' +
            '<input id="p-day" inputmode="numeric" maxlength="2" placeholder="ДД" class="field__input" aria-label="' + escHtml(t('toolSynDate')) + ', ' + escHtml(en2('день', 'day')) + '">' +
            '<input id="p-month" inputmode="numeric" maxlength="2" placeholder="ММ" class="field__input" aria-label="' + escHtml(t('toolSynDate')) + ', ' + escHtml(en2('месяц', 'month')) + '">' +
            '<input id="p-year" inputmode="numeric" maxlength="4" placeholder="ГГГГ" class="field__input" aria-label="' + escHtml(t('toolSynDate')) + ', ' + escHtml(en2('год', 'year')) + '">' +
          '</div>' +
        '</fieldset>' +
        '<div id="p-time-err" class="tool-run__fail" role="alert" style="margin-top:16px">' +
          '<span aria-hidden="true">⚠</span><p>' + escHtml(t('toolSynTimeWarn')) + '</p>' +
        '</div>' +
        '<div id="syn-date-err" class="field__error" role="alert" hidden></div>' +
        '<div class="tool-view__footer">' +
          '<p class="tool-view__terms">' + t('toolSynTerms') + '</p>' +
          '<button type="button" class="btn btn--primary btn--block" data-act="tool-submit" data-tool="syn">' + escHtml(t('toolSynSubmit')) + '</button>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* §11.2: валидация даты партнёра перед платным запуском (round-trip, как онбординг) */
  app._synValidate = function () {
    const errEl = document.getElementById('syn-date-err');
    const day = parseInt((document.getElementById('p-day') || {}).value, 10);
    const month = parseInt((document.getElementById('p-month') || {}).value, 10);
    const year = parseInt((document.getElementById('p-year') || {}).value, 10);
    const fail = (msg) => {
      if (!errEl) return false;
      errEl.textContent = msg;
      errEl.hidden = false;
      const seg = document.getElementById('p-day');
      if (seg) { seg.setAttribute('aria-invalid', 'true'); seg.focus(); }
      return false;
    };
    if (!day || !month || !year || year < 1900) return fail(t('synDateError'));
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return fail(t('synDateError'));
    if (errEl) errEl.hidden = true;
    ['p-day', 'p-month', 'p-year'].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.removeAttribute('aria-invalid');
    });
    return true;
  };

  /* ══ S11c: выполнение инструмента ════════════════════════════════════ */

  app.renderToolRun = function (main, opts) {
    if (!main) return;
    const fail = opts && opts.fail;
    const me = this.me || {};
    const bd = me.birth_date || '';
    const bday = bd.slice(8, 10) || '05', bmon = bd.slice(5, 7) || '03', byr = bd.slice(0, 4) || '1994';
    main.innerHTML =
      '<div class="tool-view">' +
        '<header class="screenheader screenheader--flush">' + backBtn(t('toolBack')) +
          '<div class="screenheader__title">' + escHtml(t('toolRunTitle')) + '</div>' +
        '</header>' +
        '<div class="tool-run__status" role="status">' +
          '<span class="tool-run__spinner" aria-hidden="true"></span>' +
          '<div><div class="tool-run__status-title">' + escHtml(t('toolRunTitle')) + '</div>' +
          '<div class="tool-run__status-note">' + escHtml(t('toolRunNote')) + '</div></div>' +
        '</div>' +
        '<ol class="tool-run__steps">' +
          stepHtml(1, 'is-done', t('toolRunStep1'), t('toolRunStep1n')) +
          stepHtml(2, 'is-active', t('toolRunStep2'), '') +
          stepHtml(3, '', t('toolRunStep3'), '') +
          stepHtml(4, '', t('toolRunStep4'), '') +
        '</ol>' +
        '<div id="run-fail-demo" class="tool-run__fail" role="alert" ' + (fail ? '' : 'hidden') + '>' +
          '<span aria-hidden="true">⚠</span><div><p><strong>' + escHtml(t('toolRunFailTitle')) + '</strong> ' + escHtml(t('toolRunFailCopy')) + '</p>' +
          '<div class="tool-run__fail-actions">' +
            '<button type="button" class="btn btn--secondary" data-act="run-fail-check">' + escHtml(t('toolRunFailCheck')) + '</button>' +
            '<button type="button" class="btn btn--secondary" data-act="run-fail-retry">' + escHtml(t('toolRunFailRetry')) + '</button>' +
          '</div></div>' +
        '</div>' +
        '<div class="tool-view__footer">' +
          '<button type="button" class="btn btn--primary btn--block" disabled>' + escHtml(t('toolRunWait')) + '</button>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  function stepHtml(i, state, label, note) {
    const isDone = state === 'is-done';
    const checkSvg = isDone
      ? '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.2 5 9l5-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      : String(i);
    const ariaCur = state === 'is-active' ? ' aria-current="step"' : '';
    return '<li class="tool-run__step ' + state + '"' + ariaCur + '><span class="tool-run__step-icon">' + checkSvg + '</span><span>' + escHtml(label) + (note ? ' · ' + escHtml(note) : '') + '</span></li>';
  }

  /* ══ S12: результат ═════════════════════════════════════════════════ */

  app.renderResult = function (main, opts) {
    if (!main) return;
    const o = opts || {};
    const title = o.title || (oracleLang() === 'en' ? 'Synastry: Anya & Danil' : 'Синастрия: Аня и Даниил');
    main.innerHTML =
      '<div class="result">' +
        '<header class="screenheader screenheader--flush">' + backBtn(t('resBack')) +
          '<div class="screenheader__title">' + escHtml(title) + '</div>' +
          '<div class="screenheader__spacer"></div>' +
          '<button type="button" class="chat-header__btn" data-act="result-share" aria-label="' + escHtml(t('resShare')) + '"><span aria-hidden="true">↗</span></button>' +
        '</header>' +
        '<div class="result__head"><img class="result__avatar" src="' + escHtml(agentAvatar('astro')) + '" alt="" aria-hidden="true"><h2 class="result__title">' + escHtml(title) + '</h2></div>' +
        '<div class="result__meta"><span>' + escHtml(t('resAgent')) + ': Урания</span><span>' + escHtml(t('resDate')) + ': ' + escHtml(fmtDate(Date.now())) + '</span><span>' + escHtml(t('resNumber')) + 'A-2291</span><span>' + escHtml(t('resData')) + ': 2 даты</span></div>' +
        '<p class="result__summary"><strong>' + escHtml(t('resMain')) + '</strong> ' + escHtml(oracleLang() === 'en'
          ? 'The pair is steady in everyday life: shared rhythm strengthens with time, but big decisions are better made together.'
          : 'Пара устойчива в быту: общий ритм укрепляется со временем, но крупные решения лучше принимать вместе.') + '</p>' +
        '<div class="result__visual"><img src="/static/img/agents/astro.jpg" alt=""></div>' +
        '<details class="result-details" open>' +
          '<summary class="result-details__summary">' + escHtml(t('resSpheres')) + '</summary>' +
          '<div class="result-details__body">' +
            '<h4>Эмоции · 8/10</h4><p>' + escHtml(oracleLang() === 'en' ? 'Warm and lively: emotions are easily shared and accepted.' : 'Тепло и живо: эмоции легко разделяются и принимаются.') + '</p>' +
            '<h4>Быт · 7/10</h4><p>' + escHtml(oracleLang() === 'en' ? 'Habits match on the basics; give the small things space.' : 'Привычки совпадают в главном; мелочам дайте воздух.') + '</p>' +
            '<h4>Ритмы · 9/10</h4><p>' + escHtml(oracleLang() === 'en' ? 'Days and energy align — a rare strength of this pair.' : 'Дни и энергия совпадают — редкая сила этой пары.') + '</p>' +
          '</div>' +
        '</details>' +
        '<details class="result-details">' +
          '<summary class="result-details__summary">' + escHtml(t('resFull')) + '</summary>' +
          '<div class="result-details__body">' + escHtml(oracleLang() === 'en'
            ? 'Urania’s full commentary: the Moon of one in the sign of the other’s Sun adds mutual understanding without words; Mercury aspects support easy agreement on plans.'
            : 'Полный комментарий Урании: Луна одного в знаке Солнца другого добавляет понимание без слов; аспекты Меркурия поддерживают лёгкое согласие по планам.') + '</div>' +
        '</details>' +
        '<details class="result-details">' +
          '<summary class="result-details__summary">' + escHtml(t('resLimits')) + '</summary>' +
          '<div class="result-details__body">' + escHtml(t('resLimitsBody')) + '</div>' +
        '</details>' +
        '<div class="result__actions">' +
          '<button type="button" class="btn btn--primary" data-act="result-discuss">' + escHtml(t('resDiscuss')) + '</button>' +
          '<button type="button" class="btn btn--secondary" data-act="result-library">' + escHtml(t('resLibrary')) + '</button>' +
        '</div>' +
        '<p class="result__saved-note"><span aria-hidden="true">✓</span>' + escHtml(t('resSaved')) + '</p>' +
      '</div>';
    this.syncBackButton();
  };

  /* ══ S13a: таро — вопрос ═════════════════════════════════════════════ */

  app.renderTarotQuestion = function (main) {
    if (!main) return;
    const examples = oracleLang() === 'en'
      ? ['Should I change jobs this autumn?', 'How do I support the relationship?', 'What will help me decide?']
      : ['Стоит ли менять работу осенью?', 'Как поддержать отношения?', 'Что поможет мне решиться?'];
    main.innerHTML =
      '<div class="tarot">' +
        '<header class="chat-header">' +
          backBtn(t('toolBack')) +
          '<img class="chat-header__avatar" src="' + escHtml(agentAvatar('tarot')) + '" alt="" aria-hidden="true">' +
          '<div><div class="chat-header__name">Мадам Ленорман</div><div class="chat-header__role">' + escHtml(oracleLang() === 'en' ? 'Tarot reader' : 'Таролог') + '</div></div>' +
        '</header>' +
        '<div class="tarot__feed">' +
          '<div class="tarot__panel">' +
            '<label class="tarot-question__label" for="tarot-q">' + escHtml(t('tarotAskLabel')) + '</label>' +
            '<input id="tarot-q" type="text" class="field__input tarot-question__input" placeholder="' + escHtml(t('tarotAskPh')) + '">' +
            '<div class="tarot-examples">' +
              examples.map(function (e, i) {
                return '<button type="button" class="tarot-examples__item" data-act="tarot-example" data-q="' + escHtml(e) + '">' + escHtml(e) + '</button>';
              }).join('') +
            '</div>' +
            '<div class="tarot-config">' +
              '<button type="button" class="tarot-config__row" data-act="tarot-config" aria-haspopup="dialog">' +
                '<span class="tarot-config__label">' + escHtml(t('tarotSpread')) + '</span>' +
                '<span class="tarot-config__value">' + escHtml(t('tarotSpreadValue')) + '</span>' +
                '<span class="tarot-config__arrow" aria-hidden="true">›</span>' +
              '</button>' +
              '<div class="tarot-config__row" aria-disabled="true">' +
                '<span class="tarot-config__label">' + escHtml(t('tarotDeck')) + '</span>' +
                '<span class="tarot-config__value">' + escHtml(t('tarotDeckValue')) + '</span>' +
              '</div>' +
            '</div>' +
            '<div class="tool-view__footer">' +
              '<p class="tool-view__terms">' + escHtml(t('tarotTerms')) + '</p>' +
              '<button type="button" class="btn btn--primary btn--block" id="tarot-draw" data-act="tarot-draw">' + escHtml(t('tarotDraw')) + '</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  function en2(ru, en) { return oracleLang() === 'en' ? en : ru; }

  /* ══ S13b: таро — раскрытие ══════════════════════════════════════════ */

  app.renderTarotReveal = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const state = this.tarotRun || (this.tarotRun = { opened: 0, order: 0, cards: defaultTarotDeck() });
    if (!state.cards.length) state.cards = defaultTarotDeck();
    if (state.drawn) {
      // Перерисовка уже вытянутого расклада: только актуализируем DOM.
      this._paintTarotReveal(main);
      return;
    }
    // Сперва сцена draw, после ответа «сервера» — блок раскрытия.
    main.innerHTML =
      '<div class="tarot">' +
        '<header class="chat-header">' +
          backBtn(t('toolBack')) +
          '<img class="chat-header__avatar" src="' + escHtml(agentAvatar('tarot')) + '" alt="" aria-hidden="true">' +
          '<div><div class="chat-header__name">Мадам Ленорман</div><div class="chat-header__role">' + escHtml(en ? 'Tarot reader' : 'Таролог') + '</div></div>' +
        '</header>' +
        '<div class="tarot__feed">' +
          '<div class="tarot__panel">' +
            '<div id="tarot-draw-scene" class="tarot-scene">' +
              '<div class="tarot-scene__fan" aria-hidden="true">' +
                [1, 2, 3, 4, 5].map(function (n) {
                  return '<img class="tarot-scene__card-back tarot-scene__card-back--' + n + '" src="/static/img/card-back.jpg" alt="">';
                }).join('') +
              '</div>' +
            '</div>' +
            '<p class="tarot-scene__status">' + escHtml(t('tarotSceneStatus')) + '</p>' +
            '<p class="tarot-scene__note">' + escHtml(t('tarotSceneNote')) + '</p>' +
          '</div>' +
        '</div>' +
      '</div>';
    const self = this;
    // Данные расклада выдаёт сервер (reading_id) — сейчас их заменяет локальная
    // колода; когда API таро появится, этот setTimeout заменит fetch.
    setTimeout(function () {
      if (self.view !== 'tarot-reveal') return;
      state.drawn = true;
      self._paintTarotReveal(main);
    }, 600);
    this.syncBackButton();
  };

  app._paintTarotReveal = function (main) {
    const en = oracleLang() === 'en';
    const state = this.tarotRun || (this.tarotRun = { opened: 0, order: 0, cards: defaultTarotDeck() });
    const total = state.cards.length;
    main.innerHTML =
      '<div class="tarot">' +
        '<header class="chat-header">' +
          backBtn(t('toolBack')) +
          '<img class="chat-header__avatar" src="' + escHtml(agentAvatar('tarot')) + '" alt="" aria-hidden="true">' +
          '<div><div class="chat-header__name">Мадам Ленорман</div><div class="chat-header__role">' + escHtml(en ? 'Tarot reader' : 'Таролог') + '</div></div>' +
        '</header>' +
        '<div class="tarot__feed">' +
          '<div class="tarot__panel">' +
            '<div class="tarot-reveal__counter"><span aria-hidden="true">🔮</span><span id="tarot-counter">' + escHtml(tn('tarotOpenedOf', state.opened, total)) + '</span></div>' +
            '<div class="tarot-cards">' +
              state.cards.map(function (c, i) {
                const open = i < state.opened;
                return '<div class="tcard' + (open ? ' is-open' : '') + '" data-i="' + i + '" data-act="tarot-card" data-position="' + escHtml(c.pos) + '" tabindex="0" role="button" aria-pressed="' + open + '" aria-label="' + escHtml(t('tarotOpenCard') + ' ' + c.pos) + '">' +
                  '<span class="tcard__frame"><img class="tcard__img" src="' + escHtml(c.img) + '" alt="' + escHtml(c.name + ' — ' + c.pos) + '"><img class="tcard__back" src="/static/img/card-back.jpg" alt=""></span>' +
                  '<span class="tcard__pos"><span class="tcard__pos-name">' + escHtml(c.pos) + '</span><span class="tcard__pos-mean" ' + (open ? '' : 'hidden') + '>' + escHtml(c.name) + '</span></span>' +
                '</div>';
              }).join('') +
            '</div>' +
            '<p class="tarot-reveal__grid-note">' + escHtml(en ? 'Open the cards in order. The server holds the full spread.' : 'Открывай карты по порядку. Полный расклад хранится на сервере.') + '</p>' +
            '<button type="button" class="btn btn--secondary" data-act="tarot-show-all">' + escHtml(t('tarotShowAll')) + '</button>' +
            '<div class="tarot-interpret__gate">' +
              '<span class="tarot-interpret__gate-icon" aria-hidden="true">✦</span>' +
              '<div><p>' + t('tarotInterpretGate') + '</p><small class="tarot-interpret__gate-note">' + escHtml(t('tarotInterpretNote')) + '</small>' +
              '<button type="button" class="btn btn--primary tarot-interpret__gate-btn" data-act="tarot-interpret">' + escHtml(t('tarotInterpretBtn')) + '</button></div>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* Расклад по умолчанию (макет S13b): 3 карты — Прошлое/Настоящее/Будущее */
  function defaultTarotDeck() {
    return [
      { pos: oracleLang() === 'en' ? 'Past' : 'Прошлое', name: 'Двойка Кубков', img: '/static/img/tarot/cups02.jpg', nameEn: 'Two of Cups', reversed: false },
      { pos: oracleLang() === 'en' ? 'Present' : 'Настоящее', name: 'Тройка Жезлов', img: '/static/img/tarot/wands03.jpg', nameEn: 'Three of Wands', reversed: false },
      { pos: oracleLang() === 'en' ? 'Future' : 'Будущее', name: 'Солнце', img: '/static/img/tarot/m19.jpg', nameEn: 'The Sun', reversed: false }
    ];
  }

  /* ══ S13c: рассмотреть карту ═════════════════════════════════════════ */

  app.renderTarotZoom = function (main) {
    if (!main) return;
    const state = this.tarotRun || (this.tarotRun = { opened: 0, cards: defaultTarotDeck() });
    const i = this.tarotZoomIndex || 0;
    const c = (state.cards || [])[i] || defaultTarotDeck()[0];
    main.innerHTML =
      '<div class="tarot">' +
        '<header class="chat-header">' +
          '<button type="button" class="screenheader__back" data-act="tarot-back-cards" aria-label="' + escHtml(t('tarotBackToCards')) + '"><span aria-hidden="true">‹</span></button>' +
          '<div class="screenheader__title">' + escHtml(c.name) + '</div>' +
        '</header>' +
        '<div class="tarot__feed">' +
          '<div class="tarot__panel">' +
            '<div class="card-zoom">' +
              '<img class="card-zoom__img" src="' + escHtml(c.img) + '" alt="' + escHtml(c.name) + '">' +
              '<div class="card-zoom__caption"><span class="tcard__pos-name">' + escHtml(c.name) + '</span></div>' +
              '<p class="tarot-scene__note">' + escHtml(t('tarotZoomPos') + ' ' + c.pos + ' · ' + t('tarotDirect')) + '</p>' +
              '<details class="result-details card-zoom__note"><summary class="result-details__summary">' + escHtml(en2('Значение', 'Meaning')) + '</summary><div class="result-details__body">' + escHtml(en2('выбор сердца, союз, притяжение; тень — зависимость', 'a choice of the heart, union, attraction; shadow — dependence')) + '</div></details>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* ══ S13b зум-возврат и открытие карт ════════════════════════════════ */

  app.tarotOpenCard = function (i) {
    const state = this.tarotRun;
    if (!state) return;
    // Уже открытая карта → зум (§6.4): клик по открытой не должен уходит в warn.
    if (i < state.opened) {
      this.tarotZoomIndex = i;
      this.go('tarot-zoom');
      return;
    }
    // Открытие строго по порядку (§6.4): следующая карта = state.opened.
    if (i !== state.opened) {
      this._tarotWarnOrder(i);
      return;
    }
    if (i >= state.cards.length) return;
    const card = state.cards[i];
    state.opened = i + 1;
    this._paintTarotReveal(document.getElementById('app-main'));
    if (state.opened === state.cards.length) this._announceTarotDone();
  };

  app.tarotShowAll = function () {
    const state = this.tarotRun;
    if (!state) return;
    state.opened = state.cards.length;
    this._paintTarotReveal(document.getElementById('app-main'));
    this._announceTarotDone();
  };

  app._tarotWarnOrder = function (i) {
    const card = document.querySelector('.tarot-cards .tcard[data-i="' + i + '"]');
    if (!card) return;
    card.setAttribute('data-warn', t('tarotWarnOrder'));
    const self = this;
    setTimeout(function () { card.removeAttribute('data-warn'); }, 2500);
  };

  app._announceTarotDone = function () {
    if (this.view !== 'tarot-reveal') return;
    const note = document.querySelector('.tarot-reveal__grid-note');
    if (!note) return;
    const en = oracleLang() === 'en';
    note.textContent = en ? 'All cards are open.' : 'Все карты открыты.';
  };

  /* ══ S13d: разбор расклада ═══════════════════════════════════════════ */

  app.renderTarotReading = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const state = this.tarotRun || (this.tarotRun = { opened: 0, cards: defaultTarotDeck() });
    const meanings = en
      ? [
          'A choice already made from the heart. The union of the past still supports you today.',
          'The first fruits of a new path are visible on the horizon; patience works better than a push.',
          'Warmth and clarity ahead: the sun promises support if you act openly.'
        ]
      : [
          'Выбор, уже сделанный сердцем. Союз прошлого и сегодня продолжает поддерживать.',
          'Первые плоды нового пути видны на горизонте; терпение работает лучше напора.',
          'Впереди тепло и ясность: солнце обещает поддержку, если действовать открыто.'
        ];
    const verdict = en
      ? 'changing jobs — yes, but not on impulse: prepare a bridge first, then step.'
      : 'менять работу — да, но не сгоряча: сначала подготовь мост, потом шагай.';
    main.innerHTML =
      '<div class="tarot">' +
        '<header class="chat-header">' +
          backBtn(t('tarotBackToCards')) +
          '<img class="chat-header__avatar" src="' + escHtml(agentAvatar('tarot')) + '" alt="" aria-hidden="true">' +
          '<div><div class="chat-header__name">Мадам Ленорман</div><div class="chat-header__role">' + escHtml(en ? 'Tarot reader' : 'Таролог') + '</div></div>' +
        '</header>' +
        '<div class="tarot__feed">' +
          '<div class="tarot__panel">' +
            '<h1 class="tarot-reading__title">' + escHtml(t('tarotReadingTitle')) + '</h1>' +
            '<p class="tarot-reading__verdict"><strong>' + escHtml(t('tarotVerdictLbl')) + '</strong> ' + escHtml(verdict) + '</p>' +
            '<div class="tarot-reading__cards">' +
              state.cards.map(function (c, i) {
                return '<article class="tarot-reading__card">' +
                  '<img class="tarot-reading__thumb" src="' + escHtml(c.img) + '" alt="' + escHtml(c.name) + '">' +
                  '<div class="tarot-reading__body">' +
                    '<div class="tarot-reading__pos">' + escHtml(c.pos) + '</div>' +
                    '<div class="tarot-reading__name">' + escHtml(c.name + ' · ' + t('tarotDirect')) + '</div>' +
                    '<p class="tarot-reading__text">' + escHtml(meanings[i % meanings.length]) + ' <em>' + escHtml(en ? 'Shadow: dependence' : 'Тень: зависимость') + '</em></p>' +
                  '</div>' +
                '</article>';
              }).join('') +
            '</div>' +
            '<div class="result__actions">' +
              '<button type="button" class="btn btn--primary" data-act="tarot-discuss">' + escHtml(t('tarotDiscuss')) + '</button>' +
              '<button type="button" class="btn btn--secondary" data-act="result-library">' + escHtml(t('resLibrary')) + '</button>' +
            '</div>' +
            '<p class="result__saved-note"><span aria-hidden="true">✓</span>' + escHtml(t('tarotReadingSaved')) + '</p>' +
          '</div>' +
        '</div>' +
      '</div>';
    this.syncBackButton();
  };

  /* ══ Общие действия: share / discuss / library ════════════════════════ */

  app.resultShare = function () { tactile('select'); };
  app.resultLibrary = function () { tactile('select'); };
  app.resultDiscuss = function () { tactile('select'); this.openChat('astro'); };
  app.tarotDiscuss = function () { tactile('select'); this.openChat('tarot'); };
  app.tarotConfig = function () { tactile('open'); };
  app.runFailCheck = function () { tactile('select'); };
  app.runFailRetry = function () { tactile('select'); };

  /* Эмуляция чата для smoke: openChat существует в проде, оставляем как есть. */
})();
