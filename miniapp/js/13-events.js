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

  // История: inline-подтверждение удаления диалога (без alert/confirm).
  const sessDel = target.closest('[data-act="sess-del"]');
  if (sessDel) {
    event.stopPropagation();
    const row = sessDel.closest('[data-sess-row], .session-card');
    if (row && row.dataset.confirmed !== '1') {
      row.dataset.confirmed = '1';
      row.style.outline = '2px solid var(--color-error)';
      row.style.outlineOffset = '-2px';
      const lbl = row.querySelector('.session-card__confirm-label');
      if (lbl) { lbl.hidden = false; lbl.textContent = t('sessionsConfirmDel'); }
      sessDel.setAttribute('aria-label', t('sessionsConfirmDel'));
      // Сброс подтверждения, если пользователь передумал в течение 3с.
      setTimeout(() => {
        if (row.dataset.confirmed === '1') {
          row.dataset.confirmed = '0';
          row.style.outline = '';
          row.style.outlineOffset = '';
          const lbl2 = row.querySelector('.session-card__confirm-label');
          if (lbl2) { lbl2.hidden = true; lbl2.textContent = ''; }
        }
      }, 3000);
    } else if (row) {
      // Второй тап — подтверждённое удаление.
      if (typeof app.delSession === 'function') {
        app.delSession(sessDel.dataset.tid);
      }
    }
    return;
  }

  // История: очистить все диалоги (inline-подтверждение по тому же паттерну).
  const sessClear = target.closest('[data-act="sess-clear"]');
  if (sessClear) {
    if (sessClear.dataset.confirmed !== '1') {
      sessClear.dataset.confirmed = '1';
      const span = sessClear.querySelector('span');
      if (span) span.textContent = t('sessionsConfirmDel');
      setTimeout(() => {
        if (sessClear.dataset.confirmed === '1') {
          sessClear.dataset.confirmed = '0';
          if (span) span.textContent = t('sessionsClear');
        }
      }, 3000);
    } else if (typeof app.deleteAllSessions === 'function') {
      app.deleteAllSessions();
    }
    return;
  }

  // Sheet инструментов: открытие.
  const openSheet = target.closest('[data-open-sheet]');
  if (openSheet) {
    if (typeof app.renderSheetTools === 'function') {
      app.renderSheetTools(document.getElementById('app-main'));
    }
    return;
  }

  // Sheet инструментов: закрытие → возврат в чат.
  const closeSheet = target.closest('[data-act="sheet-close"]');
  if (closeSheet) {
    if (app.chat && app.chat.key) app.openChat(app.chat.key);
    else app.go('hub');
    return;
  }
});

// Онбординг: Enter в полях ввода → следующий шаг; Escape → назад/закрыть.
document.addEventListener('keydown', function (event) {
  if (!document.querySelector('.onboarding')) return;
  const input = event.target;
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

// Онбординг шаг 5: подсказки городов (mock) по мере ввода.
document.addEventListener('input', function (event) {
  const input = event.target;
  if (!input || input.id !== 'ob-city') return;
  const wrap = input.closest('.combobox');
  const list = wrap && wrap.querySelector('#ob-city-list');
  const status = wrap && wrap.querySelector('[data-ob-city-status]');
  if (!wrap || !list) return;

  const q = input.value.trim().toLowerCase();
  const en = oracleLang() === 'en';
  const suggestions = ['Казань', 'Караганда', 'Касабланка'].filter(c => !q || c.toLowerCase().includes(q));

  if (status) status.hidden = true;
  wrap.setAttribute('aria-expanded', suggestions.length ? 'true' : 'false');
  list.style.display = suggestions.length ? '' : 'none';
  list.innerHTML = suggestions.map(c => `
    <li class="combobox__option" role="option" data-city-pick="${esc(c)}" aria-selected="false">
      <span class="combobox__city">${esc(c)}</span>
    </li>`).join('');
  if (app.onboardingData) app.onboardingData.city = input.value.trim();
});

// Онбординг шаг 5: выбор города из подсказок.
document.addEventListener('click', function (event) {
  const option = event.target && event.target.closest ? event.target.closest('[data-city-pick]') : null;
  if (!option) return;
  const input = document.getElementById('ob-city');
  if (!input) return;
  input.value = option.dataset.cityPick;
  if (app.onboardingData) app.onboardingData.city = option.dataset.cityPick;
  // Фокус — обратно в поле: Enter продолжает онбординг, скринридер
  // остаётся в контексте combobox.
  input.focus();
  const wrap = input.closest('.combobox');
  const list = wrap && wrap.querySelector('#ob-city-list');
  if (wrap) wrap.setAttribute('aria-expanded', 'false');
  if (list) list.style.display = 'none';
  haptic('light');
});


app.boot();
