/* chart: натальная карта — форма, построение, SVG, шаринг, планеты/стихии */
  app.featureChart = async function() {
    if (this.chat.pending && this.chat.pending.kind === 'chart') return;
    this.prepareChartOnboarding();
    const key = this.chat.key, view = this.view;
    const pend = this.chat.pending = {
      kind: 'chart',
      loading: true,
      html: this.chartLoadingHtml('restore')
    };
    this.renderChat(document.getElementById('app-main'));
    try {
      const c = await api('/api/chart');
      if (!widAlive(key, view, pend)) return;
      this.chat.pending = { kind: 'chart', loading: false, html: this.chartHtml(c) };
      haptic('soft');
    } catch (e) {
      if (!widAlive(key, view, pend)) return;
      // Карты ещё нет — собираем её прямо в чате, не отправляя в тупик профиля.
      this.chart = null;
      this.chat.pending = { kind: 'chart', loading: false, html: this.chartForm() };
    }
    this.renderChat(document.getElementById('app-main'));
    if (this.chart && this.chat.pending && !this.chat.pending.loading) {
      this.hydrateChartImage(this.chart, 'compact-chart-image', 'compact');
    }
  };


  // Onboarding показывается только на первом входе в сценарий карты и не мешает
  // человеку, который уже возвращается к сохранённому разбору.
  app.prepareChartOnboarding = function() {
    try {
      this._chartIntroPending = localStorage.getItem('oracle_chart_intro_seen') !== '1';
    } catch (e) {
      this._chartIntroPending = false;
    }
  };

  app.chartOnboardingHtml = function() {
    if (!this._chartIntroPending) return '';
    this._chartIntroPending = false;
    try { localStorage.setItem('oracle_chart_intro_seen', '1'); } catch (e) { /* private mode: guide is simply not persisted */ }
    return `<aside class="chart-onboarding" aria-label="Как читать карту">
      <span class="chart-onboarding__mark" aria-hidden="true">✦</span>
      <span class="chart-onboarding__copy"><b>Твоя карта — в три спокойных шага</b><small>Собери данные, тапни планету на колесе и затем спроси о том, что важно именно сейчас.</small></span>
    </aside>`;
  };

  app.chartLoadingHtml = function(mode) {
    const restoring = mode === 'restore';
    return `<section class="chart-loading" role="status" aria-live="polite" aria-label="${restoring ? 'Открываем сохранённую натальную карту' : 'Рассчитываем натальную карту'}">
      <span class="chart-loading__halo" aria-hidden="true"><i></i><i></i><i></i><b>✦</b></span>
      <span class="chart-loading__copy"><b>${restoring ? 'Открываем твою карту' : 'Собираем твою карту'}</b><small>${restoring ? 'Возвращаемся к твоим небесным ориентирам…' : 'Проверяем дату, место и собираем колесо…'}</small></span>
    </section>`;
  };


  app.chartSectionHtml = function(section, first) {
    if (!section) return '';
    const items = Array.isArray(section.items) ? section.items : [];
    return `<details class="chart-insight"${first ? ' open' : ''}>
      <summary><span class="chart-insight__title">${esc(section.title || 'Раздел карты')}</span><span class="chart-insight__chevron" aria-hidden="true">⌄</span></summary>
      <div class="chart-insight__body">
        ${section.intro ? `<p class="chart-insight__intro">${esc(section.intro)}</p>` : ''}
        <div class="chart-insight__items">
          ${items.map(item => `<article class="chart-insight__item${item.available ? '' : ' is-muted'}">
            <div class="chart-insight__item-head"><b>${esc(item.label || '')}</b><span>${esc(item.value || 'нет данных')}</span></div>
            <p>${esc(item.meaning || '')}</p>
          </article>`).join('')}
        </div>
        ${section.note ? `<p class="chart-insight__note">${esc(section.note)}</p>` : ''}
      </div>
    </details>`;
  };

  app.chartSectionsHtml = function(sections) {
    const map = sections && sections.sections ? sections.sections : {};
    const order = ['identity', 'mind_career', 'relationships', 'nodes'];
    return `<section class="chart-insights" aria-label="Понятный разбор натальной карты">
      <div class="chart-insights__kicker">КАК ЧИТАТЬ КАРТУ</div>
      <h3 class="chart-insights__title">Не только колесо — четыре смысловых слоя</h3>
      <p class="chart-insights__copy">Сначала смотри на факт размещения, затем на объяснение и следующий шаг — так карта раскрывается ясно и лично.</p>
      ${order.map((key, i) => this.chartSectionHtml(map[key], i === 0)).join('')}
    </section>`;
  };

  app.chartImageHtml = function(c, id, variant = 'compact') {
    if (!c || c.precision !== 'exact') {
      return `<div class="chart-engine-state chart-engine-state--precision" role="status" data-chart-image-state="precision">
        <b>${oracleLang() === 'en' ? 'Chart image needs exact birth time' : 'Для изображения карты нужно точное время рождения'}</b>
        <span>${oracleLang() === 'en' ? 'Planets remain available below; ASC, MC and houses stay hidden until the time is confirmed.' : 'Планеты доступны ниже; ASC, MC и дома останутся скрытыми, пока время не подтверждено.'}</span>
      </div>`;
    }
    return `<div class="chart-engine-image" data-chart-image="${esc(id)}" data-chart-variant="${esc(variant)}" role="status" aria-label="${oracleLang() === 'en' ? 'Natal chart image loading' : 'Загрузка изображения натальной карты'}">
      <div class="chart-engine-image__placeholder"><span class="loader-ring"></span><span>${oracleLang() === 'en' ? 'Preparing the chart image…' : 'Готовим изображение карты…'}</span></div>
    </div>`;
  };

  app.hydrateChartImage = async function(c, id, variant = 'compact') {
    const host = document.querySelector(`[data-chart-image="${id}"]`);
    if (!host || !c || c.precision !== 'exact') return;
    try {
      const blob = await apiBlob(`/api/chart/image?variant=${encodeURIComponent(variant)}&format=png&locale=${encodeURIComponent(oracleLang())}`);
      const url = URL.createObjectURL(blob);
      if (host._chartImageUrl) URL.revokeObjectURL(host._chartImageUrl);
      host.innerHTML = `<img class="chart-engine-image__img" alt="${oracleLang() === 'en' ? 'Natal chart' : 'Натальная карта'}" decoding="async">`;
      const image = host.querySelector('img');
      image.src = url;
      image.addEventListener('load', () => { host.dataset.chartImageState = 'ready'; }, { once: true });
      image.addEventListener('error', () => { URL.revokeObjectURL(url); }, { once: true });
      host._chartImageUrl = url;
    } catch (e) {
      host.dataset.chartImageState = e && e.code === 'insufficient_precision' ? 'precision' : 'error';
      host.innerHTML = `<div class="chart-engine-state" role="status"><b>${oracleLang() === 'en' ? 'Chart image is temporarily unavailable' : 'Изображение карты временно недоступно'}</b><span>${oracleLang() === 'en' ? 'The placement list below is still available.' : 'Список положений ниже по-прежнему доступен.'}</span></div>`;
    }
  };

  app.chartProvenanceHtml = function(c) {
    const raw = c && (c.engine_provenance || (c.calculation && c.calculation.engine_provenance));
    const source = raw && typeof raw === 'object' ? raw : {};
    const value = (key, max = 120) => {
      const item = source[key];
      return typeof item === 'string' && item.trim() ? item.trim().slice(0, max) : '';
    };
    const rows = [
      [profileT('provenanceProduct'), value('product_engine')],
      [profileT('provenanceBackend'), value('backend')],
      [profileT('provenanceVersion'), value('adapter_version')],
      [profileT('provenanceEphemeris'), value('ephemeris')],
      [profileT('provenanceLicense'), value('license_notice') ? profileT('provenanceLicenseCopy') : ''],
    ];
    const hasValues = rows.some(([, item]) => item);
    const body = hasValues
      ? rows.filter(([, item]) => item).map(([label, item]) => `<div class="chart-provenance__row"><span>${esc(label)}</span><b>${esc(item)}</b></div>`).join('')
      : `<p class="chart-provenance__fallback">${esc(profileT('provenanceFallback'))}</p>`;
    return `<details class="chart-provenance">
      <summary><span>${esc(profileT('provenanceTitle'))}</span><small>${esc(profileT('provenanceSummary'))}</small><span class="chart-provenance__chevron" aria-hidden="true">⌄</span></summary>
      <div class="chart-provenance__body">${body}</div>
    </details>`;
  };

  app.chartHtml = function(c) {
    this.chart = c;
    const sun = c.sun || {};
    const asc = c.ascendant || {};
    const planets = c.planets || [];
    const anglesAvailable = c.precision === 'exact';
    const precisionNotice = c.note ? `
      <div role="status" style="margin:9px 0 10px;padding:9px 10px;border:1px solid rgba(201,160,255,.26);border-radius:12px;color:var(--text-dim);font-size:11.5px;line-height:1.45">
        <b style="color:var(--gold-bright)">Точность карты</b> · ${esc(c.note)}
        ${!c.birth?.time_known ? '<br><span style="color:var(--text-faint)">Укажи время рождения в профиле, чтобы открыть ASC, MC и дома.</span>' : ''}
      </div>` : '';
    const aspects = c.aspects || [];
    const glyph = p => planetGlyph(p.name) || (p.sign ? SIGNS[p.sign] : '');
    const lines = planets.map((p, i) => `
      <div class="planet-line" data-planet-index="${i}" data-element="${esc(signElement(p.sign) || '')}">
        <div class="p-ico">${glyph(p)}</div>
        <div class="p-name">${esc(p.name)}</div>
        <div class="p-val">${esc(p.sign)}${p.house ? ' · дом ' + p.house : ''}${p.retro ? ' ☍' : ''}</div>
      </div>`).join('');
    // T6: легенда аспектов — цветные чипы, чтобы линии в колесе читались
    const legend = aspects.length ? `<div class="asp-legend">
        ${['☌ соединение', '⚹ секстиль', '△ трин'].map(a => `<span class="asp-chip" style="color:var(--gold)">${a}</span>`).join('')}
        ${[['□ квадрат', 'var(--violet)'], ['☍ оппозиция', '#ff6b6b']].map(([a, col]) => `<span class="asp-chip" style="color:${col}">${a}</span>`).join('')}
      </div>` : '';
    // легенда стихий: тап фильтрует планеты в колесе (добавлено в v2)
    const elLegend = `<div class="el-legend">
        ${[['fire','🔥 Огонь'],['earth','🌍 Земля'],['air','💨 Воздух'],['water','💧 Вода']].map(([k, l]) =>
          `<span class="el-chip" data-act="el-filter" data-el="${k}">${l}</span>`).join('')}
      </div>`;
    // «акценты карты» от бэкенда — если придут, покажем мягкими чипами; нет — тихо скроем
    const accents = Array.isArray(c.accents) ? c.accents : [];
    const accentChips = accents.length ? `<div class="asp-legend" style="margin:6px 0 8px">
        ${accents.map(a => `<span class="asp-chip" style="color:var(--violet)">${esc(a)}</span>`).join('')}
      </div>` : '';
    const takeaway = anglesAvailable
      ? `Солнце в ${esc(sun.sign || '—')} встречается с Асцендентом в ${esc(asc.sign || '—')}. Начни с этого дуэта: он помогает бережно связать внутреннее ощущение себя с тем, как ты проявляешься в мире.`
      : `Солнце в ${esc(sun.sign || '—')} — твоя надёжная точка опоры. Даже без времени рождения можно начать спокойный разговор о твоих планетах и вернуться к точным углам позже.`;
    return `
      <section class="chart-result" aria-live="polite">
        <div class="w-title">🌌 Натальная карта</div>
        ${this.chartOnboardingHtml()}
        <div class="nw" data-act="full-chart" title="Открыть полную карту">
          ${this.chartImageHtml(c, 'compact-chart-image', 'compact')}
          <div class="nw-plaque" id="nw-plaque" aria-live="polite"></div>
        </div>
        <div class="chart-wheel-hint">${oracleLang() === 'en' ? 'Open the full chart for the image · use the accessible placement list below' : 'Открой полную карту для изображения · список положений ниже доступен для чтения'}</div>
        ${elLegend}
        ${accentChips}
        <div class="chart-signature">Солнце в ${esc(sun.sign || '—')}${anglesAvailable ? ' · Асцендент ' + esc(asc.sign || '—') : ''}</div>
        ${precisionNotice}
        ${this.chartProvenanceHtml(c)}
        <div class="chart-takeaway">
          <span class="chart-takeaway__label">ТВОЯ ОТПРАВНАЯ ТОЧКА</span>
          <p>${takeaway}</p>
          <small>Это твоя отправная точка: выбери один инсайт и проверь его действием.</small>
        </div>
        ${this.chartSectionsHtml(c.sections)}
      </section>
      <details class="chart-details">
        <summary>Планеты, аспекты и детали карты</summary>
        <div class="chart-details__body">
          ${legend}
          <div>${lines || '<div style="color:var(--text-faint);font-size:12.5px">Планеты ещё не рассчитаны</div>'}</div>
        </div>
      </details>
      <div style="color:var(--text-faint);font-size:11.5px;margin:10px 0">✓ Сохранена в твоём профиле — всегда под рукой.</div>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button class="btn btn-primary" style="flex:1" data-act="ask-chart">Спросить про карту</button>
        <button class="btn btn-ghost" data-act="share-chart" title="Сохранить картинку для сторис">📸</button>
        <button class="btn btn-ghost" data-act="go" data-goto="profile">В профиль</button>
      </div>`;
  };


  app.chartForm = function(opts) {
    const me = this.me || {};
    const values = opts || {};
    const date = values.date != null ? values.date : (me.birth_date || '');
    const city = values.city != null ? values.city : (me.birth_city || '');
    const time = values.time != null ? values.time : (me.birth_time_known ? (me.birth_time || '') : '');
    const loading = !!values.loading;
    const disabled = loading ? ' disabled' : '';
    return `
      <div class="w-title">🌌 Построить натальную карту</div>
      ${this.chartOnboardingHtml()}
      <div class="chart-form-intro"><b>Начнём с даты и города.</b><span>Время рождения — по желанию: без него покажем планеты и аспекты, но честно не будем добавлять ASC, MC и дома.</span></div>
      <div class="chart-form"${loading ? ' aria-busy="true"' : ''}>
        ${values.error ? `<div class="chart-form-error" role="alert"><b>Нужна маленькая поправка</b><span>${esc(values.error)}</span></div>` : ''}
        <label class="chart-form__field" for="ch-date"><span>Дата рождения <em>обязательно</em></span><input class="ipt" id="ch-date" type="date" value="${esc(date)}" required${disabled}></label>
        <label class="chart-form__field" for="ch-city"><span>Город рождения <em>обязательно</em></span><input class="ipt" id="ch-city" value="${esc(city)}" placeholder="Например, Москва" autocomplete="address-level2"${disabled}></label>
        <div class="city-suggest" data-for="ch-city" role="listbox" aria-label="Подсказки города"></div>
        <label class="chart-form__field" for="ch-time"><span>Время рождения <em>если знаешь</em></span><input class="ipt" id="ch-time" type="time" value="${esc(time)}" placeholder="14:30"${disabled}></label>
        <button class="btn btn-primary chart-form__submit${loading ? ' is-loading' : ''}" data-act="build"${disabled}${loading ? ' aria-busy="true"' : ''}>${loading ? '<span class="chart-form__spinner" aria-hidden="true"></span><span>Собираю твою карту…</span>' : '<span>Рассчитать мою карту</span><span aria-hidden="true">✦</span>'}</button>
        ${loading ? this.chartLoadingHtml('build') : ''}
      </div>`;
  };


  app.doBuildChart = async function() {
    const date = (document.getElementById('ch-date') || {}).value || '';
    const time = (document.getElementById('ch-time') || {}).value || '';
    const city = (document.getElementById('ch-city') || {}).value || '';
    const cleanCity = city.trim();
    const validationError = !date ? 'Добавь дату рождения — она нужна для расчёта.' : (!cleanCity ? 'Добавь город рождения, чтобы корректно рассчитать карту.' : '');
    if (validationError) {
      haptic('error');
      this.chat.pending = { kind: 'chart', loading: false, html: this.chartForm({ date, time, city, error: validationError }) };
      this.renderChat(document.getElementById('app-main'));
      return;
    }
    this.chat.busy = true;
    const key = this.chat.key, view = this.view;
    const pend = this.chat.pending = { kind: 'chart', loading: true, html: this.chartForm({ date, time, city, loading: true }) };
    this.renderChat(document.getElementById('app-main'));
    try {
      const c = await api('/api/chart', {
        method: 'POST',
        body: JSON.stringify({ birth_date: date, birth_time: time.trim() || null, birth_city: cleanCity }),
      });
      if (!widAlive(key, view, pend)) { this.chat.busy = false; return; }
      this.chat.pending = { kind: 'chart', loading: false, html: this.chartHtml(c) };
      haptic('soft');
    } catch (e) {
      if (!widAlive(key, view, pend)) { this.chat.busy = false; return; }
      this.chat.pending = {
        kind: 'chart',
        loading: false,
        html: this.chartForm({ date, time, city, error: friendlyError(e, 'Не удалось построить карту прямо сейчас. Проверь соединение и попробуй ещё раз.') })
      };
      haptic('error');
    }
    this.chat.busy = false;
    this.renderChat(document.getElementById('app-main'));
    if (this.chart && this.chat.pending && !this.chat.pending.loading) {
      this.hydrateChartImage(this.chart, 'compact-chart-image', 'compact');
    }
  };


  app.chatAsk = function(text) {
    if (!text || !text.trim()) return;
    this.chat.messages.push({ role: 'user', text });
    this.chat.busy = true;
    this.renderChat(document.getElementById('app-main'));
    this.chatPost(text)
      .then(r => { this.chat.messages.push({ role: 'assistant', text: r.answer }); })
      .catch(e => { this.chat.messages.push({ role: 'assistant', text: '😔 ' + friendlyError(e) }); })
      .finally(() => { this.chat.busy = false; this.renderChat(document.getElementById('app-main')); });
  };

  // Шаблон-фраза: вставляется в поле ввода для редактирования (не авто-отправка).

  app.fillInput = function(text) {
    const input = document.getElementById('chat-input');
    if (!input) return;
    const value = text || '';
    this.chat.draft = value;
    input.value = value;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 132) + 'px';
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  };

  // Вопрос по натальной карте из виджета — prompt вынесен из inline-хендлера.

  app.askChart = function() {
    const q = prompt('О чём спросить карту?', 'моих отношениях');
    if (q && q.trim()) this.chatAsk('Что в моей натальной карте говорит о ' + q.trim());
  };

  /* Backend share: the browser receives only a raster Blob. */

  app.downloadBlob = function(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name || 'oracle-natal-card.png';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    this.toast(oracleLang() === 'en' ? 'Image saved — add it to your story.' : 'Картинка сохранена — добавь её в сторис ✨');
  };
  // G004 «в сторис»: готовый PNG расклада с бэка (/api/share/reading/{id}.png)

  app.downloadUrl = function(url, name) {
    const a = document.createElement('a');
    a.href = url; a.download = name || 'oracle-card.png';
    document.body.appendChild(a); a.click(); a.remove();
    this.toast('Картинка сохранена — добавь её в сторис ✨');
  };
  // G004 рефералка: скопировать ссылку приглашения

  app.shareChart = async function() {
    const c = this.chart;
    if (!c || !(c.planets || []).length) { this.toast('Сначала построй карту ✨'); return; }
    if (c.precision !== 'exact') {
      this.toast(oracleLang() === 'en' ? 'Add an exact birth time before sharing the chart image.' : 'Добавь точное время рождения, чтобы поделиться изображением карты.');
      return;
    }
    try {
      const blob = await apiBlob(`/api/chart/image?variant=share&format=png&locale=${encodeURIComponent(oracleLang())}`);
      if (navigator.share && navigator.canShare && this.me && this.me.flags && this.me.flags.share_cards) {
        const file = new File([blob], 'oracle-natal-card.png', { type: 'image/png' });
        navigator.share({ title: oracleLang() === 'en' ? 'My natal chart' : 'Моя натальная карта', files: [file] })
          .catch(() => this.downloadBlob(blob, 'oracle-natal-card.png'));
      } else {
        this.downloadBlob(blob, 'oracle-natal-card.png');
      }
    } catch (e) {
      this.toast(oracleLang() === 'en' ? 'The chart image is temporarily unavailable.' : 'Изображение карты временно недоступно.');
    }
  };

  /* ═══ ФИЧА: ПРОГНОЗ / НЕБО ═══ */

  app.selectPlanet = function(i) {
    const c = this.chart;
    const p = (c && c.planets) ? c.planets[i] : null;
    if (!p) return;
    haptic('light');
    vb(15);
    document.querySelectorAll('.planet-line.is-selected').forEach(row => row.classList.remove('is-selected'));
    const row = document.querySelector('.planet-line[data-planet-index="' + i + '"]');
    if (row) {
      row.classList.add('is-selected');
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    const pl = document.getElementById('nw-plaque');
    if (pl) {
      const glyph = planetGlyph(p.name) || (SIGNS[p.sign] || '');
      pl.classList.remove('is-visible');
      pl.innerHTML = `<span class="pl-glyph">${glyph}</span><span><b>${esc(p.name)}</b> · ${esc(p.sign || '—')}${p.house ? ' · дом ' + p.house : ''}${p.retro ? ' ☍' : ''}</span>`;
      window.requestAnimationFrame(() => {
        if (pl.isConnected) pl.classList.add('is-visible');
      });
    }
  };
  // стихия-фильтр: тап подсвечивает планеты этой стихии в колесе, повторный тап — сброс

  /* ── подсказки города: тап по готовому городу вместо ручного ввода ──────── */
  app.citySuggestTimer = null;
  app.citySuggest = function(input) {
    const box = document.querySelector('.city-suggest[data-for="' + input.id + '"]');
    if (!box) return;
    clearTimeout(this.citySuggestTimer);
    const q = input.value.trim();
    if (q.length < 2) { box.innerHTML = ''; return; }
    this.citySuggestTimer = setTimeout(async () => {
      try {
        const r = await api('/api/city/suggest?q=' + encodeURIComponent(q));
        const items = (r && r.items) || [];
        box.innerHTML = items.map(it =>
          `<button type="button" class="chip city-suggest__chip" data-act="city-pick" data-for="${esc(input.id)}" data-val="${esc(it.label)}" role="option">${esc(it.label)}</button>`
        ).join('');
      } catch (e) { box.innerHTML = ''; }
    }, 250);
  };
  app.pickCitySuggestion = function(el) {
    const input = document.getElementById(el.dataset.for);
    if (input) {
      input.value = el.dataset.val;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    document.querySelectorAll('.city-suggest').forEach(b => { b.innerHTML = ''; });
    haptic('light');
  };

  app.filterElement = function(el) {
    haptic('light');
    vb(10);
    const c = this.chart;
    if (!c || !c.planets) return;
    const chips = document.querySelectorAll('.el-chip');
    const active = document.querySelector('.el-chip[data-el="' + el + '"].on');
    if (active) {
      chips.forEach(ch => ch.classList.remove('on'));
      document.querySelectorAll('.planet-line').forEach(row => row.classList.remove('el-off'));
      return;
    }
    chips.forEach(ch => ch.classList.toggle('on', ch.dataset.el === el));
    document.querySelectorAll('.planet-line').forEach(row => {
      row.classList.toggle('el-off', row.dataset.element !== el);
    });
  };

  /* ═══ ПРОФИЛЬ: данные + натальная карта + расклады + отчёты ═══ */

