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
  if (event.key === 'Escape') {
    const tool = document.getElementById('tool-expand');
    if (tool && tool.classList.contains('open') && typeof app.setToolbox === 'function') {
      app.setToolbox(false);
      return;
    }
    if (document.getElementById('app-modal') && typeof app.closeModal === 'function') {
      app.closeModal();
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
});


app.boot();
