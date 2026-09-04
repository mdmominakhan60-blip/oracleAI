/* tarot: расклад, выбор схемы, переворот карт, интерпретация */
const TAROT_I18N = {
  ru: {
    pickerTitle: '🎴 Схема расклада', pickerSub: 'Листай, читай описание и выбирай', pickerNote: 'Выбор вернёт тебя к вопросу в чате — задай его и тяни карты ✨',
    cards: 'карт', progressOf: 'из', openInOrder: 'Открывай карты по порядку — так нить расклада собирается бережно.',
    questionRequired: 'Сформулируй вопрос картам — чем точнее, тем яснее ответ ✨', savedQuestion: 'Мой вопрос к картам: ',
    drawFailed: 'Колода пока не ответила. Попробуй ещё раз — вопрос уже сохранён.',
    premiumCopy: 'Это премиум-расклад. Купи Кристаллы в лавке 💎 или приведи подругу — и получи доступ к нему.', understood: 'Понятно ✨',
    threadKicker: 'НИТЬ РАСКЛАДА', threadCopy: 'Карты раскрылись. Сначала почувствуй, как роли откликаются вместе, а затем соберём личный смысл без поспешных выводов.',
    proof: 'Доказательная карточка', deck: 'Колода', ledger: 'Ledger', notSpecified: 'не указан', proofCopy: 'Это подтверждает состав и порядок расклада; теперь раскрой его сюжет через позиции и свой вопрос.',
    interpret: 'Собрать личный смысл', revealing: '✨ Раскрываю смысл карт по очереди…', historyEmpty: 'Расклад', schemesLoading: 'Схемы ещё подгружаются…',
    ritualKicker: 'ЛИЧНЫЙ РИТУАЛ', chooseTitle: 'Выбери схему и задай вопрос', pickerCopy: 'Карты не дают готовых приказов — они помогают заметить то, что уже просится в твоё внимание.', tapToBrowse: 'Тапни — откроется весь список раскладов', askAbout: 'О чём хочешь спросить?', ariaQuestion: 'Сформулируй вопрос к картам', placeholder: 'Твой вопрос к картам…', drawingStatus: 'Колода собирает твой расклад…', readyStatus: 'После вопроса вытянем карты по одной.', drawingButton: 'Собираем расклад…', drawButton: 'Потянуть карты', cardKicker: 'ТВОЙ РАСКЛАД', openCards: 'Открой карты по одной', questionLabel: 'Твой вопрос:', ariaOpenCard: 'Открыть карту', reversed: 'перевёрнута', threadHint: 'Открывай карты по порядку: каждая роль подскажет, как читать следующую.',
    deckLabel: 'Колода', deckDefault: 'Классическое Таро', deckSecond: 'Таро Мэри-Эль (Ленорман)', deckPickerTitle: 'Выбери колоду', deckPickerSub: 'Художественная школа карт для раскладов',
  },
  en: {
    pickerTitle: '🎴 Reading spread', pickerSub: 'Browse the options, read the details and choose', pickerNote: 'Your choice returns you to the question — ask it and draw the cards ✨',
    cards: 'cards', progressOf: 'of', openInOrder: 'Open the cards in order so the thread of the reading can unfold gently.',
    questionRequired: 'Write a question for the cards — the clearer it is, the clearer the answer ✨', savedQuestion: 'My question for the cards: ',
    drawFailed: 'The deck did not answer yet. Try again — your question is still here.',
    premiumCopy: 'This is a premium reading. Buy Crystals in the shop 💎 or invite a friend to unlock it.', understood: 'Got it ✨',
    threadKicker: 'READING THREAD', threadCopy: 'The cards are open. First notice how their roles respond to one another, then we will gather a personal meaning without rushing.',
    proof: 'Evidence card', deck: 'Deck', ledger: 'Ledger', notSpecified: 'not specified', proofCopy: 'This confirms the reading composition and order; now explore its story through the positions and your question.',
    interpret: 'Gather the meaning', revealing: '✨ Unfolding the meaning of the cards…', historyEmpty: 'Reading', schemesLoading: 'The spreads are still loading…',
    ritualKicker: 'PERSONAL RITUAL', chooseTitle: 'Choose a spread and ask a question', pickerCopy: 'Cards do not give ready-made orders — they help you notice what is already asking for your attention.', tapToBrowse: 'Tap to browse all reading spreads', askAbout: 'What would you like to ask?', ariaQuestion: 'Write a question for the cards', placeholder: 'Your question for the cards…', drawingStatus: 'The deck is gathering your reading…', readyStatus: 'After your question, the cards will open one by one.', drawingButton: 'Gathering the reading…', drawButton: 'Draw the cards', cardKicker: 'YOUR READING', openCards: 'Open the cards one by one', questionLabel: 'Your question:', ariaOpenCard: 'Open card', reversed: 'reversed', threadHint: 'Open the cards in order: each role will guide how to read the next one.',
    deckLabel: 'Deck', deckDefault: 'Classic Tarot', deckSecond: 'Mary-El Tarot (Lenormand)', deckPickerTitle: 'Choose a deck', deckPickerSub: 'Artistic card school for readings',
  },
};
const TAROT_CATALOG_EN = {
  one: { title: 'One card', hint: 'One clear answer to a specific question', positions: ['Answer'] },
  three: { title: 'Past · Present · Future', hint: 'How the situation developed — and where it leads', positions: ['Past', 'Present', 'Future'] },
  love: { title: 'Relationships', hint: 'Your feeling, your partner and the connection between you', positions: ['You', 'The other person', 'The connection', 'Advice'] },
  choice: { title: 'Choice between two', hint: 'Two paths, their fruits and what you do not yet see', positions: ['Your situation', 'Path A', 'Path B', 'Advice'] },
  money: { title: 'Money and work', hint: 'Your resource, what slows you down and the first step', positions: ['Your resource', 'What blocks you', 'First step'] },
  career: { title: 'Career and path', hint: 'Where you are, what blocks growth and where the path leads', positions: ['Where you are', 'What blocks growth', 'The path', 'Next step'] },
  work: { title: 'Work tension', hint: 'Whom to hear, what to avoid and how to leave with dignity', positions: ['The situation', 'What to hear', 'What to avoid', 'Next step'] },
  celtic: { title: 'Celtic Cross', hint: 'Ten cards for the full picture of a situation', positions: ['The heart of the matter', 'The challenge', 'The foundation', 'The past', 'The possible direction', 'The near future', 'Your stance', 'The environment', 'Hopes and fears', 'The outcome'] },
  year: { title: 'Wheel of the year', hint: 'Twelve cards — one for each month', positions: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] },
};
const tarotLang = () => oracleLang() === 'en' ? 'en' : 'ru';
const tarotT = (key, fallback = '') => TAROT_I18N[tarotLang()][key] || fallback || key;
const tarotSpreadText = (spread, field, fallback = '') => {
  const code = spread && (spread.code || spread.spread);
  return (tarotLang() === 'en' ? TAROT_CATALOG_EN[code]?.[field] : '')
    || (spread && spread[field]) || fallback || code || '';
};
const tarotPositionText = (code, position, index) =>
  (tarotLang() === 'en' ? TAROT_CATALOG_EN[code]?.positions?.[index] : '') || position;

  app.featureTarot = async function() {
    if (this.chat.pending && this.chat.pending.kind.startsWith('tarot')) return;
    this.chat.pending = { kind: 'tarot-pick', spreads: [], spread: 'three', q: '' };
    this.renderChat(document.getElementById('app-main'));
    try {
      this.spreads = this.spreads || await api('/api/tarot/spreads');
      this.chat.pending.spreads = this.spreads;
    } catch (e) {
      this.chat.pending.spreads = [
        { code: 'one', title: 'Одна карта', emoji: '🂠', tier: 'included', desc: 'Один ясный ответ на конкретный вопрос' },
        { code: 'three', title: 'Прошлое · Настоящее · Будущее', emoji: '🂠🂠🂠', tier: 'included', desc: 'Как развивалась ситуация — и куда ведёт' },
        { code: 'love', title: 'На отношения', emoji: '💞', tier: 'included', desc: 'Твоё чувство, партнёр и связь между вами' },
      ];
    }
    this.renderChat(document.getElementById('app-main'));
  };


  app.openSpreadPicker = function() {
    const p = this.chat.pending;
    if (!p || !p.spreads || !p.spreads.length) { this.toast(tarotT('schemesLoading')); return; }
    haptic('light');
    const sel = p.spread || 'three';
    const rows = p.spreads.map(s => `
      <div class="sp-pick-row ${s.code === sel ? 'sel' : ''} ${s.tier === 'premium' ? 'premium' : ''}"
           data-act="pick-choose" data-code="${s.code}" data-owned="${s.owned ? 1 : 0}">
        <div class="sp-pick-ico sp-pick-scheme">${spreadScheme(s.code)}</div>
        <div class="sp-pick-main">
                     <div class="sp-pick-title">${esc(tarotSpreadText(s, 'title'))}${s.tier === 'premium' ? `<span class="sp-pick-lock">🔒 ${s.price_crystals ? s.price_crystals + ' ✦' : (tarotLang() === 'en' ? 'premium' : 'премиум')}</span>` : ''}</div>
          <div class="sp-pick-desc">${esc(tarotSpreadText(s, 'hint', s.desc || ''))}</div>
        </div>
        <div class="sp-pick-meta">
          <span class="sp-pick-cards">${s.cards} ${esc(tarotT('cards'))}</span>

          ${s.code === sel ? '<span class="sp-pick-check">✓</span>' : '<span class="sp-pick-radio"></span>'}
        </div>
      </div>`).join('');
    this.showModal(`
      <div class="picker-head">
        <div>
          <div class="picker-title">${esc(tarotT('pickerTitle'))}</div>
          <div class="picker-sub">${esc(tarotT('pickerSub'))}</div>
        </div>
        <button class="m-close" data-act="modal-close">✕</button>
      </div>
      <div class="picker-schemes">${rows}</div>
      <div class="picker-note">${esc(tarotT('pickerNote'))}</div>`, 'full');
  };
  // Выбор схемы из полноэкранного списка (премиум → мягкий модал «как открыть»)

  app.currentDeck = function() {
    try { return localStorage.getItem('oracle_tarot_deck') || 'tarot'; }
    catch (e) { return 'tarot'; }
  };
  app.tarotImagePath = function(slug) {
    const deck = this.currentDeck();
    const base = deck === 'lenormand' ? 'lenormand' : 'tarot';
    return `/static/img/${base}/${esc(slug || 'm00')}.jpg`;
  };

  app.openDeckPicker = function() {
    haptic('light');
    const decks = [
      { id: 'tarot', title: tarotT('deckDefault'), sub: tarotLang() === 'en' ? 'Classic Rider–Waite' : 'Классика Райдера-Уэйта' },
      { id: 'lenormand', title: tarotT('deckSecond'), sub: tarotLang() === 'en' ? 'Mary-El Tarot (Lenormand school)' : 'Таро Мэри-Эль (школа Ленорман)' },
    ];
    const sel = this.currentDeck();
    const rows = decks.map(d => `
      <div class="sp-pick-row ${d.id === sel ? 'sel' : ''}" data-act="deck-choose" data-deck="${d.id}">
        <div class="sp-pick-ico sp-pick-scheme">🂠</div>
        <div class="sp-pick-main">
          <div class="sp-pick-title">${esc(d.title)}</div>
          <div class="sp-pick-desc">${esc(d.sub)}</div>
        </div>
        <div class="sp-pick-meta">${d.id === sel ? '<span class="sp-pick-check">✓</span>' : '<span class="sp-pick-radio"></span>'}</div>
      </div>`).join('');
    this.showModal(`
      <div class="picker-head">
        <div>
          <div class="picker-title">${esc(tarotT('deckPickerTitle'))}</div>
          <div class="picker-sub">${esc(tarotT('deckPickerSub'))}</div>
        </div>
        <button class="m-close" data-act="modal-close">✕</button>
      </div>
      <div class="picker-schemes">${rows}</div>`, 'full');
  };

  app.chooseDeck = function(id) {
    haptic('soft');
    try { localStorage.setItem('oracle_tarot_deck', id); } catch (e) {}
    this.closeModal();
  };

  app.chooseSpread = function(code) {
    const p = this.chat.pending;
    if (!p || !p.spreads) return;
    haptic('soft');
    const s = p.spreads.find(x => x.code === code);
    if (s && s.tier === 'premium' && !s.owned) {
      this.showModal(`<h3>✨ ${esc(tarotSpreadText(s, 'title'))}</h3>
        <button class="m-close" data-act="modal-close">✕</button>
        <div class="fc-adv" style="margin-top:4px">
          ${esc(tarotT('premiumCopy'))}
        </div>
        <button class="btn btn-primary" style="margin-top:14px" data-act="modal-close">${esc(tarotT('understood'))}</button>`);
      return;
    }
    p.spread = code;
    this.closeModal();
    this.renderChat(document.getElementById('app-main'));
  };


  app.setTarotQuestion = function(value) {
    const p = this.chat.pending;
    if (!p || p.kind !== 'tarot-pick' || p.drawing) return;
    const field = document.getElementById('tarot-q');
    if (field) {
      field.value = value;
      field.focus();
    }
    p.q = value;
    document.querySelectorAll('[data-act="tarot-question"]').forEach(el => {
      el.classList.toggle('is-active', el.dataset.value === value);
    });
    haptic('light');
    vb(12);
  };

  app.doDraw = async function() {
    const p = this.chat.pending;
    if (!p || p.kind !== 'tarot-pick' || p.drawing) return;
    const q = (document.getElementById('tarot-q') || {}).value || p.q;
    const qv = (q || '').trim();
    if (!qv) {
      // Inline-валидация: вопрос остаётся в фокусе сценария и не теряется.
      p.err = tarotT('questionRequired');
      this.renderChat(document.getElementById('app-main'));
      return;
    }
    const spread = p.spread || 'three';
    const spreads = p.spreads;
    this.chat.busy = true;
    this.chat.pending = { kind: 'tarot-pick', spreads, spread, q: qv, err: '', drawing: true };
    this.renderChat(document.getElementById('app-main'));
    try {
      const r = await api('/api/tarot/draw?spread=' + spread, {
        method: 'POST',
        body: JSON.stringify({ question: qv, deck: this.currentDeck() }),
      });
      this.chat.messages.push({ role: 'user', text: tarotT('savedQuestion') + qv });
      if (r.deck) { try { localStorage.setItem('oracle_tarot_deck', r.deck); } catch (e) {} }
      this.chat.pending = {
        kind: 'tarot-cards', question: qv, cards: r.cards, spread,
        positions: r.positions, ledger: r.ledger || null, deck: r.deck || this.currentDeck(),
        revealed: r.cards.map(() => false), nextReveal: 0,
        turning: false, allRevealed: false, reading_id: r.reading_id,
      };
      haptic('soft');
    } catch (e) {
      this.chat.pending = {
        kind: 'tarot-pick', spreads, spread, q: qv,
        err: tarotT('drawFailed'), drawing: false,
      };
    }
    this.chat.busy = false;
    this.renderChat(document.getElementById('app-main'));
  };

  // Переворот карты БЕЗ полного ререндера ленты — иначе скролл прыгает наверх.
  // Работаем точечно: класс .open на конкретной карте + кнопка интерпретации.

  app.flipCard = function(i) {
    const p = this.chat.pending;
    if (!p || p.kind !== 'tarot-cards' || p.revealed[i] || p.turning) return;
    const next = Number.isInteger(p.nextReveal) ? p.nextReveal : p.revealed.filter(Boolean).length;
    if (i !== next) {
      haptic('soft');
      this.toast(tarotT('openInOrder'));
      return;
    }
    const card = document.querySelector('.tcard[data-i="' + i + '"]');
    if (!card) return;
    const key = this.chat.key, tid = this.chat.tid;
    p.turning = true;
    card.classList.add('is-turning');
    haptic('light');
    vb(25);
    setTimeout(() => {
      if (this.chat.key !== key || this.chat.tid !== tid || this.chat.pending !== p) return;
      card.classList.remove('is-turning');
      card.classList.add('open');
      p.revealed[i] = true;
      p.nextReveal = i + 1;
      p.turning = false;
      p.allRevealed = p.revealed.every(Boolean);
      this.updateTarotProgress();
      if (p.allRevealed) {
        haptic('success');
        this.addInterpretBtn();
      }
    }, 130);
  };

  app.updateTarotProgress = function() {
    const p = this.chat.pending;
    const el = document.querySelector('.tarot-card-progress');
    if (!p || p.kind !== 'tarot-cards' || !el) return;
    const opened = p.revealed.filter(Boolean).length;
    el.innerHTML = `<span>${opened} ${tarotT('progressOf')} ${p.cards.length}</span><i style="--tarot-progress:${(opened / p.cards.length) * 100}%"></i>`;
  };

  app.addInterpretBtn = function() {
    const p = this.chat.pending;
    const w = document.querySelector('.chat-widget');
    const hint = document.querySelector('.t-hint');
    if (hint) hint.remove();
    if (!p || p.kind !== 'tarot-cards' || !w || w.querySelector('[data-act="interpret"]')) return;
    const thread = document.createElement('section');
    thread.className = 'tarot-thread tarot-thread--revealed';
    thread.setAttribute('aria-label', tarotT('threadKicker'));
    const ledger = p.ledger || {};
    const pairs = Array.isArray(ledger.adjacent_combinations) ? ledger.adjacent_combinations : [];
    thread.innerHTML = `<div class="tarot-thread-kicker">${esc(tarotT('threadKicker'))}</div>
      <p>${esc(tarotT('threadCopy'))}</p>
      <div class="tarot-thread-map">${p.positions.map((pos, i) => {
        const c = p.cards[i] || {};
        const orientation = tarotLang() === 'en'
          ? (c.reversed ? ' · reversed' : ' · upright')
          : (c.reversed ? ' · перевёрнутая' : ' · прямая');
        return `<span><b>${esc(tarotPositionText(p.spread, pos, i))}:</b> ${esc(c.name || (tarotLang() === 'en' ? 'card' : 'карта'))}${esc(orientation)}</span>`;
      }).join('')}</div>
      <div class="tarot-proof"><b>${esc(tarotT('proof'))}</b><span>${esc(tarotT('deck'))}: ${esc(ledger.deck_id || 'RWS')}</span><span>${esc(tarotT('ledger'))}: ${esc(ledger.version || tarotT('notSpecified'))} · checksum ${esc(ledger.checksum || '—')}</span>${pairs.length ? `<div class="tarot-proof__pairs">${pairs.map(pair => `<span>${esc(pair.left)} + ${esc(pair.right)} · ${esc(pair.rule)}</span>`).join('')}</div>` : ''}<small>${esc(tarotT('proofCopy'))}</small></div>`;
    w.appendChild(thread);
    const b = document.createElement('button');
    b.className = 'btn btn-primary tarot-interpret-btn';
    b.style.marginTop = '14px';
    b.dataset.act = 'interpret';
    b.textContent = tarotT('interpret');
    w.appendChild(b);
  };

  // Карта дня: переворот раскрывает смысл

  app.flipDayCard = function(el) {
    haptic('light');
    const c = el && el.closest ? el.closest('.tarot-card-big') : null;
    if (c) c.classList.toggle('flipped');
  };


  app.doInterpret = async function() {
    const p = this.chat.pending;
    if (!p || p.kind !== 'tarot-cards') return;
    this.chat.busy = true;
    this.renderChat(document.getElementById('app-main'));
    try {
      const r = await api('/api/tarot/interpret/' + p.reading_id, { method: 'POST' });
      // B3: гард гонки — если юзер ушёл/переключил чат, не вливаем ответ в чужой тред
      const key = this.chat.key, tid = this.chat.tid;
      const inThread = () => this.chat.key === key && this.chat.tid === tid;
      // Эффект «раскрытия смысла»: карты переворачиваются одна за другой с задержкой 120 мс
      // (даже если все уже открыты — визуальный ритуал перед трактовкой)
      p.revealed.forEach((_, i) => {
        setTimeout(() => {
          if (!inThread()) return;
          const cards = document.querySelectorAll('.tcard[data-i="' + i + '"]');
          if (cards[0]) cards[0].classList.add('open');
        }, i * 120);
      });
      // Ждём завершения анимации (max delay + transition time) перед показом ответа
      setTimeout(() => {
        if (!inThread()) return;
        this.chat.messages.push({ role: 'assistant', text: r.answer });
        this.chat.pending = null;
        this.chat.busy = false;
        this.renderChat(document.getElementById('app-main'));
      }, p.revealed.length * 120 + 750);
      // Во время ожидания показываем индикатор «раскрываю смысл…»
      if (inThread()) {
        this.chat.messages.push({ role: 'assistant', text: tarotT('revealing') });
        this.renderChat(document.getElementById('app-main'));
      }
    } catch (e) {
      this.chat.messages.push({ role: 'assistant', text: '😔 ' + friendlyError(e) });
      this.chat.pending = null;
      this.chat.busy = false;
      this.renderChat(document.getElementById('app-main'));
    }
  };


  app.featureTarotHistory = async function() {
    if (this.chat.pending && this.chat.pending.kind === 'history') return; // B4 re-entry
    this.chat.pending = { kind: 'history', loading: true };
    this.renderChat(document.getElementById('app-main'));
    try {
      const rows = await api('/api/tarot/history');
      this.chat.pending = {
        kind: 'history', loading: false,
        rows: rows.map(r => `
          <div class="result-card" style="margin-bottom:8px" data-act="reading" data-id="${r.id}">
            <div class="rc-top">
              <span style="font-size:18px">${r.cards && r.cards[0] ? r.cards[0].emoji : '🎴'}</span>
              <div style="flex:1;min-width:0">
                <div class="rc-title">${esc(r.question || tarotT('historyEmpty'))}</div>
                <div class="rc-meta">${fmtDay(r.created_at.slice(0, 10))} · ${esc(r.spread || '')}</div>
              </div>
              <span class="rc-open">›</span>
            </div>
          </div>`).join(''),
      };
    } catch (e) {
      this.chat.pending = { kind: 'history', loading: false, rows: '<div style="color:var(--text-faint)">' + esc(friendlyError(e)) + '</div>' };
    }
    this.renderChat(document.getElementById('app-main'));
  };

  /* ═══ ФИЧА: НАТАЛЬНАЯ КАРТА → строится и сохраняется в профиль ═══ */

