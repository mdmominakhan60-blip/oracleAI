/* =============================================================================
   ORACLEAI · SAFE GESTURE NAVIGATION
   Мобильные свайпы без блокирования скролла и форм. Pointer Events позволяют
   не держать два расходящихся обработчика для touch и pen.
   ============================================================================= */
(function () {
  const VIEW_ORDER = ['home', 'hub', 'payment', 'profile'];
  const INTERACTIVE = [
    'input', 'textarea', 'select', 'button', 'a', '[contenteditable="true"]',
    '[data-act]', '.chat-messages', '.suggest-chips', '.agent-tabs',
    '.tool-expand', '.modal', '#intro', '#chat-guide', '.sess-panel',
    '.rc-strip-row', '.agent-chips', '.toolbar'
  ].join(',');

  app.initSwipe = function() {
    if (document.documentElement.dataset.oracleGesturesReady === '1') return;
    document.documentElement.dataset.oracleGesturesReady = '1';

    let start = null;
    const clear = () => { start = null; };
    const isInteractive = target => !!(target && target.closest && target.closest(INTERACTIVE));

    document.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' || event.button !== 0) return;
      const agentTabs = event.target.closest('.agent-tabs');
      const toolSheet = event.target.closest('.te-sheet');
      if (isInteractive(event.target) && !agentTabs && !toolSheet) return;
      start = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        time: Date.now(),
        chat: !!event.target.closest('.chat-shell'),
        agentTabs: !!agentTabs,
        toolSheet: !!toolSheet
      };
    }, { passive: true });

    document.addEventListener('pointercancel', clear, { passive: true });
    document.addEventListener('pointerup', event => {
      if (!start || start.id !== event.pointerId) return;
      const gesture = start;
      clear();
      const dx = event.clientX - gesture.x;
      const dy = event.clientY - gesture.y;
      const elapsed = Date.now() - gesture.time;
      const horizontal = Math.abs(dx) >= 66 && Math.abs(dx) > Math.abs(dy) * 1.35 && elapsed < 900;
      const vertical = Math.abs(dy) >= 58 && Math.abs(dy) > Math.abs(dx) * 1.3 && elapsed < 900;

      // Вкладки проводников остаются нажимаемыми, но дополнительно поддерживают
      // листание между соседними диалогами без захвата прокрутки ленты.
      if (gesture.agentTabs) {
        if (horizontal && app.chat && app.chat.key && typeof app.cycleAgent === 'function') {
          app.cycleAgent(dx < 0 ? 1 : -1);
          haptic('light');
        }
        return;
      }

      // Bottom sheet закрывается естественным свайпом вниз за ручку или содержимое.
      if (gesture.toolSheet) {
        if (vertical && dy > 0 && typeof app.setToolbox === 'function') {
          app.setToolbox(false);
          haptic('light');
        }
        return;
      }

      if (gesture.chat) {
        if (vertical && dy < 0 && typeof app.setToolbox === 'function') {
          app.setToolbox(true);
          haptic('soft');
          return;
        }
        if (!horizontal) return;
        if (dx < 0 && typeof app.setToolbox === 'function') {
          app.setToolbox(true);
          haptic('soft');
        } else if (dx > 0 && app.chat && app.chat.key) {
          app.closeChat();
          haptic('light');
        }
        return;
      }

      if (!horizontal || (app.chat && app.chat.key)) return;
      const current = VIEW_ORDER.indexOf(app.view);
      if (current < 0) return;
      const next = current + (dx < 0 ? 1 : -1);
      if (next < 0 || next >= VIEW_ORDER.length) {
        haptic('soft');
        return;
      }
      app.go(VIEW_ORDER[next]);
      const screen = document.getElementById('app-main');
      if (screen) {
        screen.classList.remove('screen-swipe-next', 'screen-swipe-prev');
        // Browser reflow only for the transient transform class; no layout loop.
        void screen.offsetWidth;
        screen.classList.add(dx < 0 ? 'screen-swipe-next' : 'screen-swipe-prev');
        setTimeout(() => screen.classList.remove('screen-swipe-next', 'screen-swipe-prev'), 260);
      }
      haptic('light');
    }, { passive: true });
  };
}());
