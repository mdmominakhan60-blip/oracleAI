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


/* ═══ BUS-1070 p1 R06: события онбординга, истории и sheet ═══ */

// Клик-делегирование для R06-элементов, не проходящих через data-act.
document.addEventListener('click', function (event) {
  const target = event.target && event.target.closest ? event.target : null;
  if (!target) return;
  if (app._obSaving && target.closest('.onboarding')) return;

  // Шаг онбординга: выбор намерения (data-intent) → шаг 2.
  const intent = target.closest('[data-intent]');
  if (intent) {
    if (app.onboardingData) app.onboardingData.intent = intent.dataset.intent;
    haptic('light');
    app.renderOnboarding(document.getElementById('app-main'), 2);
    return;
  }

  // Шаг времени: toggle choice-row (aria-pressed) + показ/скрытие полей времени.
  const choice = target.closest('.choice-row[data-time-choice]');
  if (choice) {
    const key = choice.dataset.timeChoice;
    document.querySelectorAll('.choice-row[data-time-choice]').forEach((r) => {
      const on = r === choice;
      r.setAttribute('aria-pressed', on ? 'true' : 'false');
      r.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    const fields = document.querySelector('[data-time-fields]');
    if (fields) fields.hidden = key === 'dontknow';
    if (app.onboardingData) app.onboardingData.timeKnown = key;
    haptic('light');
    return;
  }

  // Review: кнопка «исправить» → возврат на конкретный шаг.
  const jump = target.closest('.review-row__edit[data-ob-jump]');
  if (jump) {
    app.renderOnboarding(document.getElementById('app-main'), parseInt(jump.dataset.obJump, 10) || 1);
    return;
  }

  // unify-all: sess-del/sess-clear живут в реестре 15-actions (единая точка
  // входа data-act) — здесь не дублируем, иначе двойное срабатывание.
  // Sheet инструментов: открытие.
  const openSheet = target.closest('[data-open-sheet]');
  if (openSheet) {
    if (typeof app.renderSheetTools === 'function') {
      app.renderSheetTools(document.getElementById('app-main'));
    }
    return;
  }

  // unify-all: sheet-close — в реестре 15-actions, здесь не дублируем.
});

// Онбординг: Enter в полях ввода → следующий шаг; Escape → назад/закрыть.
document.addEventListener('keydown', function (event) {
  if (!document.querySelector('.onboarding')) return;
  if (event.isComposing || event.defaultPrevented || app._obSaving) return;
  const input = event.target;
  if (input?.id === 'ob-city' && input.getAttribute('aria-expanded') === 'true') {
    const options = [...document.querySelectorAll('[data-city-pick]')];
    if (['ArrowDown', 'ArrowUp'].includes(event.key) && options.length) {
      event.preventDefault();
      app._obCityIndex = ((app._obCityIndex ?? -1) + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      options.forEach((option, i) => option.setAttribute('aria-selected', String(i === app._obCityIndex)));
      input.setAttribute('aria-activedescendant', options[app._obCityIndex].id);
      options[app._obCityIndex].scrollIntoView({ block: 'nearest' });
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (app._obCityIndex >= 0) app._obSelectCity(app._obCityIndex);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      app._obCityRequest++;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      document.getElementById('ob-city-list').style.display = 'none';
      return;
    }
  }
  if (event.key === 'Enter' && input && input.tagName === 'INPUT' && input.id && input.id.startsWith('ob-')) {
    event.preventDefault();
    if (typeof app._obAdvance === 'function') app._obAdvance();
    return;
  }
  // Esc на шаге > 1 — назад; на первом — выход в home.
  if (event.key === 'Escape') {
    event.preventDefault();
    if (typeof app._obBack === 'function') app._obBack();
  }
});

// Onboarding date inputs share one draft; city results come from the API.
document.addEventListener('input', function (event) {
  const input = event.target;
  if (input?.id === 'ob-date-picker') {
    const [year = '', month = '', day = ''] = input.value.split('-');
    document.getElementById('ob-day').value = day;
    document.getElementById('ob-month').value = month;
    document.getElementById('ob-year').value = year;
  } else if (['ob-day', 'ob-month', 'ob-year'].includes(input?.id)) {
    const value = id => document.getElementById(id).value;
    document.getElementById('ob-date-picker').value = `${value('ob-year')}-${value('ob-month').padStart(2, '0')}-${value('ob-day').padStart(2, '0')}`;
  }
  if (!input || input.id !== 'ob-city') return;
  app._obSearchCity(input);
});

// Онбординг шаг 5: выбор города из подсказок.
document.addEventListener('click', function (event) {
  if (event.target?.closest?.('[data-ob-city-retry], [data-ob-city-search]')) {
    app._obSearchCity(document.getElementById('ob-city'));
    return;
  }
  const option = event.target && event.target.closest ? event.target.closest('[data-city-pick]') : null;
  if (!option) return;
  app._obSelectCity(Number(option.dataset.cityPick));
  haptic('light');
});


app.boot();
