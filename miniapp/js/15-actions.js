/* UI command registry.
 * Views expose methods on `app`; this module owns only the mapping from
 * declarative data-act attributes to those methods.
 */
(function () {
  'use strict';

  const call = (name, ...args) => {
    if (typeof app[name] === 'function') app[name](...args);
  };

  app.dispatchAction = function (el) {
    const action = el && el.dataset && el.dataset.act;
    const handler = actionHandlers[action];
    if (handler) handler(el, el.dataset);
  };

  const actionHandlers = {
    go: (el, data) => call('go', data.goto),
    'payment-method': (el, data) => call('selectPaymentMethod', data.method),
    'payment-period': (el, data) => call('selectPaymentPeriod', data.period),
    'payment-asset': (el, data) => call('selectPaymentAsset', data.asset),
    'pay-stars': (el, data) => call('payStars', el, data),
    'pay-crypto': (el, data) => call('payCrypto', el, data),
    'payment-retry': () => call('retryPayments'),
    'payment-orders': () => call('showPaymentOrders'),
    'payment-history': () => call('showPaymentOrders'),
    'payment-history-refresh': () => call('loadPaymentHistory'),
    chat: (el, data) => call('openChat', data.chat),
    'chat-fn': (el, data) => {
      call('setToolbox', false);
      call('openChat', data.chat, () => call(data.fn));
    },
    back: () => call('closeChat'),
    clear: () => call('clearThread'),
    feature: (el, data) => { tactile('select'); call(data.fn); },
    'tool-fn': (el, data) => {
      tactile('open');
      call(data.fn);
    },
    'tool-toggle': () => { tactile('open'); call('toggleToolbox'); },
    'palm-start': () => { tactile('select'); call('featurePalm'); },
    'today-ask': () => call('todayAsk'),
    'day-flip': () => call('todayFlip'),
    'matrix-node': (el, data) => call('selectMatrixNode', data.key),
    'matrix-ask': (el, data) => call('matrixAsk', data.key),
    'moon-expand': (el, data) => call('expandMoonDay', parseInt(data.i, 10)),
    'p-action': (el, data) => call('practiceAction', data.code, data.a),
    'diary-add': () => call('diaryAdd'),
    'diary-mood': (el, data) => call('setDiaryMood', data.mood),
    'diary-summary': () => call('diarySummary'),
    'career-day': (el, data) => call('careerDay', parseInt(data.i, 10)),
    'career-ask': () => call('careerAsk'),
    sessions: () => call('toggleSessions'),
    moon: () => call('openMoon'),
    'moon-week': () => call('toggleMoonWeek'),
    'moon-day': (el, data) => call('toggleMoonDay', parseInt(data.i, 10)),
    // BUS-517 (R-10): аккордеоны главной и «Развернуть» прогноза в hero
    'home-acc': (el) => call('toggleHomeAcc', el),
    'forecast-expand': (el) => call('toggleForecastExpand', el),
    ptab: (el, data) => call('switchPTab', data.tab),
    'new-session': () => call('newSession'),
    'open-session': (el, data) => call('openSession', parseInt(data.tid, 10)),
    'del-session': (el, data) => call('delSession', parseInt(data.tid, 10)),
    'delete-all-sessions': () => call('deleteAllSessions'),
    send: (el, data) => call('doSend', data.val || undefined),
    'cancel-chat': () => call('cancelChatRequest'),
    'retry-chat': () => call('loadThread', app.chat.key),
    // FE-012: повторная отправка сохранённого черновика без дубля «пузыря»
    'retry-send': () => {
      const draft = app.chat && app.chat.draft;
      if (!draft || app.chat.busy) return;
      const msgs = app.chat.messages;
      if (msgs && msgs.length && msgs[msgs.length - 1].widget) msgs.pop();
      call('doSend', draft, { echo: false });
    },
    fill: (el, data) => call('fillInput', data.val),
    memories: () => call('openMemories'),
    'toggle-memory': () => call('toggleMemory'),
    'full-chart': () => call('openFullChart'),
    'fc-explain': () => call('explainChart'),
    // BUS-650 Э8b: кнопка разбора на экране карты (в чате), отдельный контейнер
    'explain-chart': (el) => call('explainChart', el),
    'del-mem': (el, data) => call('delMem', parseInt(data.id, 10)),
    'add-mem': () => call('addMem'),
    'pick-open': () => call('openSpreadPicker'),
    'pick-choose': (el, data) => call('chooseSpread', data.code),
    'deck-open': () => call('openDeckPicker'),
    'deck-choose': (el, data) => call('chooseDeck', data.deck),
    draw: () => call('doDraw'),
    'tarot-question': (el, data) => call('setTarotQuestion', data.value),
    flip: (el, data) => call('flipCard', parseInt(data.i, 10)),
    'flip-card': (el) => call('flipDayCard', el),
    interpret: () => call('doInterpret'),
    compat: () => call('doCompat'),
    'synastry-load': (el, data) => call('loadSynastry', parseInt(data.id, 10)),
    'synastry-create': () => call('createSynastryPartner'),
    'composite-load': (el, data) => call('loadComposite', parseInt(data.id, 10)),
    'transit-load': () => call('loadTransits', document.getElementById('transit-date')?.value),
    'returns-load': () => call('loadReturns', document.getElementById('returns-year')?.value),
    'compat-rel': (el, data) => call('setCompatRel', data.rel),
    sphere: (el, data) => call('selectSphere', parseInt(data.sphere, 10)),
    'spd-toggle': () => call('toggleSpdAnswer'),
    planet: (el, data) => call('selectPlanet', parseInt(data.p, 10)),
    'el-filter': (el, data) => call('filterElement', data.el),
    reading: (el, data) => call('openReading', parseInt(data.id, 10)),
    'share-reading': (el, data) => call('shareReading', parseInt(data.id, 10)),
    outcome: (el, data) => call('setOutcome', parseInt(data.id, 10), data.val),
    'ref-copy': () => call('refCopy'),
    report: (el, data) => call('openReport', data.kind, parseInt(data.reportId, 10)),
    'history-chat': (el, data) => call('openHistoryChat', data.agent, parseInt(data.id, 10)),
    'history-diary': (el, data) => call('openDiary', parseInt(data.id, 10)),
    build: () => call('doBuildChart'),
    ask: (el, data) => call('askAgent', data.chat, data.q),
    'all-readings': () => call('openAllReadings'),
    bell: () => call('openBell'),
    'notifications-toggle': () => call('toggleMorningNotifications'),
    'notifications-read-all': () => call('markNotificationsRead'),
    gender: () => call('openGender'),
    'set-gender': (el, data) => call('setGender', data.gender),
    language: () => call('openLanguage'),
    // R05 E18: переключение «Анимация фона» — bg-paused на root+html,
    // перерисовка строки в Профиле (кнопка живёт только там).
    'bg-anim': (el) => {
      tactile('select');
      call('setBgAnimation', !app.bgAnimationEnabled());
      if (app.view === 'profile') call('renderProfileR06', document.getElementById('app-main'));
    },
    'set-lang': (el, data) => call('setLanguage', data.lang),
    'ask-chart': () => call('askChart'),
    'share-chart': () => call('shareChart'),
    'share-compat': (el, data) => call('shareCompat', data.pdate, data.pname, data.rel),
    'modal-close': () => call('closeModal'),
    'confirm-yes': () => {
      const cb = app._confirmCb;
      app._confirmCb = null;
      call('closeModal');
      if (cb) cb();
    },
    'confirm-no': () => { app._confirmCb = null; call('closeModal'); },
    'account-delete': () => call('deleteAccount'),
    'account-privacy': () => call('openPrivacyCenter'),
    'account-export': () => call('exportAccount'),
    'city-pick': (el) => call('pickCitySuggestion', el),
    'survey-choice': (el) => call('surveyChoice', el),
    'survey-skip': () => call('surveySkip'),
    'survey-next': () => call('surveyAdvance'),
    'survey-back': () => call('surveyBack'),
    'survey-close': () => call('closeSurvey'),
    'survey-open': () => call('openSurvey'),
    // BUS-1070 p1 R06: онбординг — шаги и review
    'ob-next': () => call('_obAdvance'),
    'ob-back': () => call('_obBack'),
    // BUS-1070 p2 R06: инструменты, результат, таро
    'tool-back': () => call('go', 'hub'),
    'tool-submit': (el, data) => {
      if (data.tool === 'syn' && typeof app._synValidate === 'function' && !app._synValidate()) return;
      call('go', 'tool-run', { tool: data.tool });
    },
    'tarot-example': (el, data) => {
      const input = document.getElementById('tarot-q');
      if (input) { input.value = data.q || ''; input.focus(); }
    },
    'tarot-draw': () => {
      const btn = document.querySelector('.tarot__footer .btn, [data-act="tarot-draw"]');
      if (btn && btn.disabled) return;
      if (btn) { btn.disabled = true; btn.textContent = app.t ? app.t('tarotDrawing') : '…'; }
      call('go', 'tarot-reveal');
    },
    'tarot-card': (el, data) => call('tarotOpenCard', parseInt(data.i, 10)),
    'tarot-show-all': () => call('tarotShowAll'),
    'tarot-interpret': () => call('go', 'tarot-reading'),
    'tarot-back-cards': () => call('go', 'tarot-reveal'),
    'tarot-discuss': () => call('tarotDiscuss'),
    'tarot-config': () => call('tarotConfig'),
    'run-fail-check': () => call('runFailCheck'),
    'run-fail-retry': () => call('runFailRetry'),
    'result-share': () => call('resultShare'),
    'result-discuss': () => call('resultDiscuss'),
    'result-library': () => call('resultLibrary'),
    // BUS-1070 p3 R06: экраны S15–S26, крест, промо, состояния
    'today-expand': (el) => call('todayExpand', el),
    'lib-tab': (el, data) => { tactile('select'); call('switchLibTab', data.tab); },
    'lib-retry': () => call('libRetry'),
    'mem-del-confirm': (el, data) => call('_memConfirm', data.id),
    'mem-confirm-cancel': () => call('_memConfirmCancel'),
    'mem-confirm-yes': (el, data) => call('_memConfirmYes', data.id),
    'notif-toggle': (el, data) => { tactile('select'); call('_notifToggle', data.key); },
    'promo-toggle': (el) => call('_promoToggle', el),
    'promo-apply': () => call('_promoApply'),
    'paywall-back': () => call('_paywallBack'),
    'paywall-pay': () => call('_paywallPay'),
    'pay-check-status': () => call('_payCheckStatus'),
    'tarot-cross-open': (el, data) => call('tarotCrossOpen', parseInt(data.pos, 10)),
    'r06-pay-stars': (el) => call('selectPaymentMethod', 'stars'),
    'r06-pay-crypto': (el) => call('selectPaymentMethod', 'crypto')
  };

  app.actionHandlers = actionHandlers;
}());
