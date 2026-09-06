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


app.boot();
