/* DOM transport: превращает браузерные события в команды app.
 * Business/UI action mapping находится в 15-actions.js.
 */
window.app = app;


document.addEventListener('click', function (event) {
  const el = event.target && event.target.closest
    ? event.target.closest('[data-act]')
    : null;
  if (el) app.dispatchAction(el, event);
});


document.addEventListener('keydown', function (event) {
  if (event.key === 'Enter' && event.target && event.target.id === 'chat-input' && !event.shiftKey) {
    event.preventDefault();
    app.doSend();
  }
  // Esc закрывает верхний модал/sheet — удобно на ПК и для скринридеров.
  // A11y (BUS-133, A-3): Tab/Shift+Tab зациклены внутри активного диалога.
  if (event.key === 'Escape' || event.key === 'Tab') {
    const dlg = typeof app.activeDialog === 'function' ? app.activeDialog() : null;
    if (dlg) {
      if (event.key === 'Tab') {
        if (typeof app.trapTabKey === 'function') app.trapTabKey(dlg, event);
        return;
      }
      // Escape
      const tool = document.getElementById('tool-expand');
      if (tool && tool.classList.contains('open') && typeof app.setToolbox === 'function') {
        event.preventDefault();
        app.setToolbox(false);
        return;
      }
      if (typeof app.closeModal === 'function') {
        event.preventDefault();
        app.closeModal();
      }
    }
  }
});


document.addEventListener('input', function (event) {
  if (event.target && event.target.id === 'tarot-q') {
    app.pendingQ(event.target.value);
  }
  if (event.target && event.target.id === 'chat-input') {
    app.chat.draft = event.target.value;
    // BUS-636 Э5: авто-высота инпута
    if (typeof app._autoGrowChatInput === 'function') app._autoGrowChatInput(event.target);
  }
  if (event.target && event.target.classList && event.target.classList.contains('ipt') &&
      ['ch-city', 'sp-city'].includes(event.target.id)) {
    app.citySuggest(event.target);
  }
  // BUS-240: текст опроса (dream / other) — в state формы
  if (event.target && typeof app.surveySyncInput === 'function' &&
      ['fb-dream-text', 'fb-other-text'].includes(event.target.id)) {
    app.surveySyncInput(event.target);
  }
});


// BUS-398: промокод — форма submit, Enter в поле тоже отправляет.
document.addEventListener('submit', function (event) {
  const el = event.target && event.target.closest
    ? event.target.closest('[data-act-form="promo"]')
    : null;
  if (el) {
    event.preventDefault();
    if (typeof app.submitPromo === 'function') {
      app.submitPromo(el.querySelector('[data-promo-input]'));
    }
  }
});


/* BUS-1070 (R06): делегированная навигация data-goto / data-goto-view.
 * Прототипы R06 используют свои атрибуты вместо live data-act="go".
 * ob-step-N — внутренние шаги онбординга: тот же view + dataset шага. */
document.addEventListener('click', function (event) {
  const el = event.target && event.target.closest
    ? event.target.closest('[data-goto], [data-goto-view], [data-open-sheet]')
    : null;
  if (!el) return;
  if (el.hasAttribute('data-open-sheet')) {
    const sheet = el.getAttribute('data-open-sheet');
    const target = sheet && sheet !== 'true' ? sheet : 'tool-catalog';
    if (app._r06 && app._r06.views[target]) app.go(target);
    return;
  }
  const target = el.getAttribute('data-goto') || el.getAttribute('data-goto-view');
  if (!target) return;
  const obMatch = target.match(/^ob-step-([1-5])$/);
  if (obMatch) {
    const main = document.getElementById('app-main');
    if (main) {
      main.dataset.obStep = obMatch[1];
      app._r06.views['onboarding'](main);
      tactile('open');
    }
    return;
  }
  /* live-фичи, не являющиеся r06-views: chart/tarot — флоу live-агентов */
  if (target === 'chart') { tactile('open'); app.openChat('astro', () => app.featureChart()); return; }
  if (target === 'tarot') { tactile('open'); app.openChat('tarot'); return; }
  if (target === 'chat') { tactile('open'); app.openChat('oracle'); return; }
  if (target === 'widget-moon') { tactile('open'); app.openMoon(); return; }
  if (target === 'widget-palm') { tactile('select'); app.featurePalm(); return; }
  if (target === 'widget-matrix' || target === 'widget-career') {
    tactile('open');
    app.openChat('astro', () => app.askAgent('astro', target === 'widget-career' ? 'Разбери 10-й дом и мой профессиональный путь' : 'Покажи мою матрицу судьбы'));
    return;
  }
  if (app._r06 && app._r06.views[target]) {
    tactile('open');
    app.go(target);
  } else if (typeof app[target] === 'function' || ['home', 'hub', 'profile', 'payment', 'chat'].includes(target)) {
    tactile('open');
    app.go(target);
  }
});


/* BUS-1070 (R06): sheet-закрытие (overlay/×) и «Развернуть» прогноза сегодня. */
document.addEventListener('click', function (event) {
  const t = event.target;
  if (!t || !t.closest) return;
  if (t.closest('.sheet-overlay') && !t.closest('.sheet') && !t.closest('[data-goto]')) {
    if (app._r06 && app._r06._sheetBack) app.go(app._r06._sheetBack);
    else app.go('hub');
    return;
  }
  const close = t.closest('.sheet__close');
  if (close) {
    if (app._r06 && app._r06._sheetBack) app.go(app._r06._sheetBack);
    else app.go('hub');
    return;
  }
  const expand = t.closest('[data-r06-toggle-expand]');
  if (expand) {
    const fc = document.getElementById(expand.getAttribute('aria-controls'));
    if (fc) {
      const open = expand.getAttribute('aria-expanded') === 'true';
      expand.setAttribute('aria-expanded', String(!open));
      fc.classList.toggle('today__forecast--clamped', open);
      expand.firstChild.nodeValue = open ? 'Развернуть ' : 'Свернуть ';
    }
  }
});


app.boot();
