/* compat: совместимость пары — форма, сферы, спидометр, разбор */
  app.featureCompat = function() {
    if (this.chat.pending && this.chat.pending.kind === 'compat') return;
    this.chat.pending = { kind: 'compat', relation: 'love', name: '', date: '', startedAt: Date.now() };
    this.renderChat(document.getElementById('app-main'));
  };
  // Выбор связи не должен обнулять форму: сохраняем локальный ввод до rerender.
  app.setCompatRel = function(rel) {
    haptic('light');
    if (!this.chat.pending) return;
    const name = ((document.getElementById('cp-name') || {}).value || this.chat.pending.name || '').trim();
    const date = ((document.getElementById('cp-date') || {}).value || this.chat.pending.date || '').trim();
    this.chat.pending = { ...this.chat.pending, relation: rel, name, date };
    this.renderChat(document.getElementById('app-main'));
  };

  app.revealChatResult = function() {
    requestAnimationFrame(() => {
      const anchors = document.querySelectorAll('[data-result-anchor]');
      const target = anchors[anchors.length - 1];
      if (!target) return;
      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
      target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    });
  };

  app.doCompat = async function() {
    const name = ((document.getElementById('cp-name') || {}).value || '').trim();
    const date = ((document.getElementById('cp-date') || {}).value || '').trim();
    const rel = (this.chat.pending && this.chat.pending.relation) || 'love';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      this.toast('Укажи дату рождения в формате ГГГГ-ММ-ДД');
      const field = document.getElementById('cp-date');
      if (field) field.focus();
      return;
    }
    this.chat.busy = true;
    haptic('soft');
    vb(18);
    this.chat.pending = { kind: 'compat-processing', relation: rel, name, date, startedAt: Date.now() };
    this.renderChat(document.getElementById('app-main'));
    try {
      const r = await api('/api/compat/full', { method: 'POST', body: JSON.stringify({ partner_date: date, partner_name: name, relation: rel, save: true }) });
      this.chat.messages.push({ role: 'user', text: 'Моя совместимость с ' + (name || 'партнёром') + ' · ' + date });
      if (r && r.scores) {
        this.chat.messages.push({ role: 'assistant', widget: this.compatWidgetHtml(r.scores, r.answer, { partner_name: name, partner_date: date, relation: rel }) });
      } else {
        this.chat.messages.push({ role: 'assistant', widget: this.compatTextResultHtml(r && r.answer, { partner_name: name }) });
      }
      haptic('success');
      this.toast('Разбор готов — он уже в диалоге');
    } catch (e) {
      this.chat.messages.push({ role: 'assistant', widget: this.compatErrorHtml() });
      haptic('error');
    }
    this.chat.busy = false;
    this.chat.pending = null;
    this.renderChat(document.getElementById('app-main'));
    this.revealChatResult();
  };

  app.compatTextResultHtml = function(answer, ctx) {
    const person = ctx && ctx.partner_name ? 'с ' + esc(ctx.partner_name) : 'вашей пары';
    return `<section class="compat-result-text" data-result-anchor role="status" aria-label="Результат совместимости">
      <span class="result-kicker">СОВМЕСТИМОСТЬ</span>
      <h3>Наблюдение для ${person}</h3>
      <div class="compat-result-copy">${richMd(answer || 'Я собрала первый ориентир. Спроси, какая сфера сейчас важнее всего — и разберём её глубже.')}</div>
      <button class="btn btn-ghost" data-act="chat-fn" data-chat="oracle" data-fn="featureCompat">Проверить другую дату</button>
    </section>`;
  };

  app.compatErrorHtml = function() {
    return `<section class="compat-result-error" data-result-anchor role="alert">
      <span class="result-kicker">СОВМЕСТИМОСТЬ</span>
      <h3>Расчёт не успел завершиться</h3>
      <p>Данные не потерялись. Попробуй ещё раз — это займёт несколько секунд.</p>
      <button class="btn btn-primary" data-act="chat-fn" data-chat="oracle" data-fn="featureCompat">Повторить расчёт</button>
    </section>`;
  };

  // «Спидометр любви»: кольцо из 5 сегментов-сфер, общий балл в центре, стрелка на total.

  app.compatWidgetHtml = function(scores, answer, ctx) {
    const gid = 'spdGlow' + (++spdSeq); // уникальный id фильтра: несколько спидометров в ленте не конфликтуют
    const total = Math.round(scores && scores.total != null ? scores.total : 0);
    const verdict = (scores && scores.verdict) || '';
    const spheres = (scores && Array.isArray(scores.spheres)) ? scores.spheres : [];
    ctx = ctx || {};
    const relationMeta = {
      love: { label: 'вашей пары', symbol: '♡', title: 'Ритм вашей близости' },
      friend: { label: 'вашей дружбы', symbol: '✦', title: 'Ритм вашей дружбы' },
      work: { label: 'вашего дела', symbol: '⌁', title: 'Ритм вашего союза' },
      family: { label: 'вашей семьи', symbol: '◌', title: 'Ритм вашей связи' },
    }[ctx.relation] || { label: 'вашей связи', symbol: '✦', title: 'Ритм вашей связи' };
    const partnerLabel = ctx.partner_name ? esc(ctx.partner_name) : 'этим человеком';
    const colors = ['#e6c178', '#a78bfa', '#ff9e9e', '#7fd4a8', '#8ab6ff'];
    const n = Math.max(1, spheres.length);
    const cx = 110, cy = 110, R = 84, sw = 15;
    const seg = 360 / n;
    // deg отсчитывается от 3 часов против часовой; это отдельная compatibility visual, не natal chart renderer
    const pol = (deg, rad) => [cx + Math.cos(deg * Math.PI / 180) * rad, cy - Math.sin(deg * Math.PI / 180) * rad];
    const arc = (a1, a2) => {
      const [x1, y1] = pol(a1, R);
      const [x2, y2] = pol(a2, R);
      return `M ${x1} ${y1} A ${R} ${R} 0 0 1 ${x2} ${y2}`;
    };
    const segs = spheres.map((s, i) => {
      const a1 = i * seg;
      const [mx, my] = pol(a1 + seg / 2, R + 11); // % чуть снаружи кольца
      return `<path class="spd-seg" data-sphere="${i}" d="${arc(a1, a1 + seg)}" stroke="${colors[i % colors.length]}" stroke-width="${sw}" fill="none"/>
        <text x="${mx}" y="${my}" text-anchor="middle" class="spd-pct">${Math.round(s.value || 0)}</text>`;
    }).join('');
    // шкала 0-100: деления каждые 25, крупные на 0/50/100
    const ticks = [0, 25, 50, 75, 100].map(t => {
      const [x1, y1] = pol(t / 100 * 360, 61);
      const [x2, y2] = pol(t / 100 * 360, t % 50 === 0 ? 70 : 65);
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="spd-tick${t % 50 === 0 ? ' big' : ''}"/>`;
    }).join('');
    // стрелка на общий балл
    const [nx, ny] = pol(Math.max(0, Math.min(100, total)) / 100 * 360, R - 24);
    const verdictTxt = verdict ? `<div class="spd-verdict">${esc(verdict)}</div>` : '';
    const more = answer ? `
      <button class="spd-more" type="button" data-act="spd-toggle" aria-expanded="false">Прочитать бережный разбор</button>
      <div class="spd-answer" hidden>${richMd(answer || '')}</div>` : '';
    // «в сторис»: серверный PNG открытки (/api/share/compat.png) — тот же путь,
    // что у расклада; данные пары живут в data-атрибутах кнопки
    const share = ctx.partner_date ? `
      <button class="btn btn-ghost" data-act="share-compat" data-pdate="${esc(ctx.partner_date)}" data-pname="${esc(ctx.partner_name || '')}" data-rel="${esc(ctx.relation || 'love')}" title="Открытка для сторис" style="margin-top:8px">📸 Поделиться</button>` : '';
    return `<section class="chat-widget compat-result" data-result-anchor role="status" aria-label="Результат совместимости">
      <div class="compat-result__intro">
        <span class="compat-result__sigil" aria-hidden="true">${relationMeta.symbol}</span>
        <div><div class="result-kicker">СОВМЕСТИМОСТЬ</div><div class="w-title" style="margin:0">${relationMeta.title}</div></div>
      </div>
      <p class="compat-result__lead">Я собрала спокойный ориентир для ${relationMeta.label} с ${partnerLabel}. Нажми на сферу — увидишь, что в ней важно заметить.</p>
      <div class="spd-wrap">
        <svg viewBox="0 0 220 220" class="spd-ring" aria-hidden="true">
          <defs>
            <filter id="${gid}" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="2.4" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>
          <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="${sw}"/>
          ${ticks}
          ${segs}
          <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" class="spd-needle" filter="url(#${gid})"/>
          <circle cx="${cx}" cy="${cy}" r="5" class="spd-hub"/>
          <circle cx="${cx}" cy="${cy}" r="34" class="spd-center"/>
          <text x="${cx}" y="${cy + 6}" text-anchor="middle" class="spd-total">${total}</text>
        </svg>
        ${verdictTxt}
      </div>
      <div class="spd-cards" aria-label="Сферы совместимости">
        ${spheres.map((s, i) => `
          <button class="spd-card" type="button" data-act="sphere" data-sphere="${i}" style="--sc:${colors[i % colors.length]}" aria-pressed="false">
            <span class="spd-dot"></span>
            <span class="spd-card-t">${esc(s.title || '')}</span>
            <span class="spd-card-v">${Math.round(s.value || 0)}</span>
            <span class="spd-card-arrow" aria-hidden="true">›</span>
          </button>
          ${s.note ? `<p class="spd-note" data-sphere-note="${i}" hidden>${esc(s.note)}</p>` : ''}`).join('')}
      </div>
      ${more}
      ${share}
    </section>`;
  };
  // тап по карточке сферы → подсветка её сегмента в кольце

  app.selectSphere = function(i) {
    haptic('light');
    vb(30);
    const cards = document.querySelector('.spd-cards');
    if (cards) {
      cards.querySelectorAll('.spd-card').forEach(c => {
        const active = parseInt(c.dataset.sphere, 10) === i;
        c.classList.toggle('spd-active', active);
        c.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      cards.querySelectorAll('[data-sphere-note]').forEach(note => {
        note.hidden = parseInt(note.dataset.sphereNote, 10) !== i;
      });
    }
    const ring = document.querySelector('.spd-ring');
    if (ring) ring.querySelectorAll('.spd-seg').forEach(s =>
      s.classList.toggle('spd-active', parseInt(s.dataset.sphere, 10) === i));
  };

  app.toggleSpdAnswer = function() {
    const a = document.querySelector('.spd-answer');
    const trigger = document.querySelector('.spd-more');
    if (!a) return;
    a.hidden = !a.hidden;
    if (trigger) {
      trigger.setAttribute('aria-expanded', a.hidden ? 'false' : 'true');
      trigger.textContent = a.hidden ? 'Прочитать бережный разбор' : 'Скрыть подробный разбор';
    }
    haptic('light');
  };

  // «в сторис» для совместимости: серверный PNG открытки → системный share или
  // скачивание. Данные пары приходят из data-атрибутов кнопки (13-events).
  app.shareCompat = async function(partnerDate, partnerName, relation) {
    if (!partnerDate) { this.toast('Введи дату рождения партнёра ✨'); return; }
    haptic('light');
    const qs = new URLSearchParams({
      partner_date: partnerDate,
      partner_name: partnerName || '',
      relation: relation || 'love',
    }).toString();
    try {
      const res = await fetch('/api/share/compat.png?' + qs);
      if (!res.ok) { this.toast('Картинка сейчас недоступна 🌙'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const file = new File([blob], 'oracle-compat.png', { type: 'image/png' });
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ title: 'Наша совместимость', files: [file] })
          .catch(() => this.downloadUrl(url, 'oracle-compat.png'));
      } else {
        this.downloadUrl(url, 'oracle-compat.png');
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { this.toast('Картинка сейчас недоступна 🌙'); }
  };

  /* ═══ ВИДЖЕТЫ: ПРАКТИКИ / КНИГА СУДЬБЫ / КАРЬЕРНЫЕ ОКНА ═══ */
  // Практики — каталог с прогрессом: круг 0–100%, стрик-огонь, отметка дня

