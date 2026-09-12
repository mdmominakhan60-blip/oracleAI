/* BUS-1103 S14 R06: натальная карта (G-кадр explain-chart), пакет p4 макета
 * BUS-1067. 7 видов: карточка-превью в чате, загрузка, нет данных, карта,
 * zoom планеты, разбор (interpret), ошибка. Inline SVG-колесо, без новых
 * изображений (BUS-963). API-контракт — backend, не мок прототипа:
 *   GET  /api/chart           → {sun, ascendant, planets[], houses[], aspects[], nodes[], birth}
 *   POST /api/chart/interpret → {text, structured(v1), human(v2: render_order/blocks)}
 * Отображение разбора: human v2 (preferred) → structured v1 → text (legacy).
 */
(function () {
  'use strict';

  const AGENT = { code: 'astro', name: 'Урания', role: 'Астролог' };

  function escHtml(s) { return esc(String(s == null ? '' : s)); }
  /* t() при отсутствии ключа возвращает сам ключ — как в соседних R06-модулях:
   * пропущенный i18n-ключ виден в UI и smoke-пробах, а не маскируется. */
  const tf = t;
  /* i18n с подстановкой {n}/{m} */
  function tn(key, n, m) {
    let s = t(key, key);
    s = s.replace('{n}', String(n)).replace('{m}', String(m == null ? '' : m));
    return s;
  }
  const L = () => oracleLang() === 'en';

  function agentAvatar() {
    const agents = (app.agents && app.agents.length) ? app.agents : [];
    const a = agents.find(function (x) { return x.code === AGENT.code; });
    return a && a.avatar ? a.avatar : '/static/img/oracle-mark.png';
  }

  /* Кнопка назад в шапке (паттерн 19-r06-tools, но с кодом S14) */
  function backBtnHtml(act) {
    return '<button type="button" class="screenheader__back" data-act="' + act + '" aria-label="' + escHtml(tf('s14BackChat')) + '"><span aria-hidden="true">‹</span> <span>' + escHtml(tf('s14BackChat')) + '</span></button>';
  }

  /* Строка рождения «05.03.1994 · 14:20 · Москва» из birth-объекта карты */
  function birthLine(birth) {
    if (!birth || !birth.date) return '';
    let s = birth.date;
    if (birth.time) s += ' · ' + birth.time;
    if (birth.city) s += ' · ' + birth.city;
    return s;
  }

  function fmtDeg(deg) {
    const d = Math.floor(Number(deg) || 0);
    return d + '°';
  }

  /* ══ Шапка видов S14 (единый Back-matrix H2 «К разговору») ═════════════ */

  function chartHeader(title, backAct, backLabel, extraBtn) {
    return '<header class="screenheader screenheader--flush">' +
      '<button type="button" class="screenheader__back" data-act="' + backAct + '" aria-label="' + escHtml(backLabel) + '">' +
      '<svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '<span>' + escHtml(backLabel) + '</span></button>' +
      '<span class="screenheader__title">' + escHtml(title) + '</span>' +
      '<span class="screenheader__spacer"></span>' +
      (extraBtn || '') +
      '</header>';
  }

  /* ══ SVG-колесо. Позиции планет — по abs_deg из API (зодиакальный градус);
   * ASC-ось не рисуется домами (упрощение прототипа p4: спицы-кресты),
   * глифы планет — короткие, подписи — в списках под колесом (§11.3).
   * Гипотетические координаты не выдумываем: если abs_deg нет — глиф
   * раскладываем равномерно по кругу. ═══════════════════════════════════ */

  function wheelPos(deg, radius) {
    /* Геометрия макета p4 (сверено по координатам прототипа): ASC слева,
     * знаки идут против часовой. SVG-угол = 180° − эклиптическая долгота,
     * ось y экранная (вниз): x=c+r·cos, y=c+r·sin. */
    const a = (180 - (Number(deg) || 0)) * Math.PI / 180;
    return { x: 200 + radius * Math.cos(a), y: 200 + radius * Math.sin(a) };
  }

  /* Глифы 12 знаков — равномерные сегменты прототипа (центр знака − 15°),
   * координаты скопированы из макета p4 построчно. */
  const ZODIAC_GLYPHS = [
    ['♈', 41, 248], ['♉', 83, 322], ['♊', 157, 364], ['♋', 243, 364],
    ['♌', 317, 322], ['♍', 359, 248], ['♎', 359, 157], ['♏', 317, 83],
    ['♐', 243, 41], ['♑', 157, 41], ['♒', 83, 83], ['♓', 41, 157]
  ];

  function wheelSvg(items, opts) {
    const o = opts || {};
    const glyphs = items.map(function (p, i) {
      /* abs_deg — эклиптическая долгота из API; без неё не выдумываем
       * позицию — раскладываем равномерно по кольцу планет. */
      const pos = wheelPos(p.abs_deg != null ? p.abs_deg : (i * (360 / Math.max(items.length, 1))), 100);
      const cls = p.isNode ? 'chart-wheel__p chart-wheel__p--node' : 'chart-wheel__p';
      if (o.clickable) {
        return '<a href="#" class="' + cls + '" data-act="chart-planet" data-p="' + i + '" ' +
          'aria-label="' + escHtml(tn('s14PlanetAria', p.name, (p.sign || '') + (p.house ? ', ' + tn('s14HouseShort', p.house) : ''))) + '">' +
          '<circle cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="13" class="chart-wheel__phit"/>' +
          '<text x="' + pos.x.toFixed(1) + '" y="' + (pos.y + 4).toFixed(1) + '" text-anchor="middle" class="pglyph' + (p.isNode ? ' pglyph--node' : '') + '">' + escHtml(p.glyph) + '</text></a>';
      }
      return '<text x="' + pos.x.toFixed(1) + '" y="' + (pos.y + 4).toFixed(1) + '" text-anchor="middle" class="pglyph' + (p.isNode ? ' pglyph--node' : '') + '" aria-hidden="true">' + escHtml(p.glyph) + '</text>';
    }).join('');
    return '<svg viewBox="0 0 400 400" class="chart-wheel" role="img" aria-label="' + escHtml(tf('s14WheelAria')) + '">' +
      '<circle cx="200" cy="200" r="190" fill="rgba(20,24,39,.55)" stroke="currentColor" stroke-opacity=".5" stroke-width="1.5"/>' +
      '<circle cx="200" cy="200" r="120" fill="none" stroke="currentColor" stroke-opacity=".4" stroke-width="1"/>' +
      '<g class="chart-wheel__spokes" stroke="currentColor" stroke-opacity=".28" stroke-width="1">' +
      '<path d="M200 12 L200 390 M12 200 L390 200"/></g>' +
      '<g class="chart-wheel__cusps" stroke="currentColor" stroke-opacity=".55" stroke-width="1.6">' +
      '<path d="M200 20 L200 78 M200 322 L200 380 M20 200 L78 200 M322 200 L380 200"/></g>' +
      '<g class="chart-wheel__signs" aria-hidden="true">' +
      ZODIAC_GLYPHS.map(function (z) {
        return '<text x="' + z[1] + '" y="' + z[2] + '" text-anchor="middle" class="zglyph">' + z[0] + '</text>';
      }).join('') + '</g>' +
      '<text x="200" y="66" text-anchor="middle" class="cmglyph">MC</text>' +
      '<text x="200" y="344" text-anchor="middle" class="cmglyph">IC</text>' +
      '<text x="34" y="205" text-anchor="middle" class="cmglyph">ASC</text>' +
      '<text x="369" y="205" text-anchor="middle" class="cmglyph">DSC</text>' +
      glyphs + '</svg>';
  }

  /* Планеты+узлы в единую кликабельную коллекцию */
  function wheelItems(chart) {
    const planets = (chart && chart.planets || []).map(function (p) {
      return { name: p.name, sign: p.sign, deg: p.deg, house: p.house, retro: p.retro,
        abs_deg: p.abs_deg, glyph: planetGlyph(p.name) || (p.sign ? SIGNS[p.sign] : '•'), isNode: false };
    });
    const nodes = (chart && chart.nodes || []).map(function (n) {
      return { name: n.name, sign: n.sign, deg: n.deg, house: n.house, retro: n.retro,
        abs_deg: n.abs_deg, glyph: planetGlyph(n.name) || '☋', isNode: true };
    });
    return planets.concat(nodes);
  }

  function miniWheelSvg(chart) {
    /* Мини-колесо карточки — упрощённый контур макета (§5.2): без знаков,
     * до 8 глифов, засечек-осей четыре. Позиции — те же долготы из API. */
    const items = wheelItems(chart).slice(0, 8);
    return '<svg viewBox="0 0 400 400" role="img" aria-hidden="true">' +
      '<circle cx="200" cy="200" r="190" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="1.5"/>' +
      '<circle cx="200" cy="200" r="120" fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width="1"/>' +
      '<path d="M200 10 L200 80 M200 320 L200 390 M10 200 L80 200 M320 200 L390 200" stroke="currentColor" stroke-opacity=".5" stroke-width="1.5"/>' +
      '<text x="200" y="70" text-anchor="middle" class="wglyph">MC</text>' +
      '<text x="200" y="345" text-anchor="middle" class="wglyph">IC</text>' +
      '<text x="35" y="205" text-anchor="middle" class="wglyph">ASC</text>' +
      '<text x="368" y="205" text-anchor="middle" class="wglyph">DSC</text>' +
      items.map(function (p, i) {
        const pos = wheelPos(p.abs_deg != null ? p.abs_deg : (i * 45), 165);
        return '<text x="' + pos.x.toFixed(1) + '" y="' + (pos.y + 4).toFixed(1) + '" text-anchor="middle" class="wplanet" aria-hidden="true">' + escHtml(p.glyph) + '</text>';
      }).join('') + '</svg>';
  }

  /* ══ Состояние S14 (app.s14): карта, выбранный индекс планеты, кэш разбора ══ */

  function s14State() {
    if (!app.s14) app.s14 = { chart: null, planet: null, interpret: null, busy: false };
    return app.s14;
  }

  /* ══ ВИД 1 · chart-card: карточка-превью в ленте (§4.2, §5.2) ══════════
   * Превью живёт в чат-ленте astro-агента: featureChart (10-chart.js)
   * рендерит виджет; здесь — standalone qa-вид для сверки с макетом. */

  app.renderChartCardR06 = function (main) {
    if (!main) return;
    const c = s14State().chart;
    main.innerHTML =
      '<div class="chart-card-view">' +
        '<header class="chat-header">' + backBtnHtml('chart-back') +
          '<img class="chat-header__avatar" src="' + escHtml(agentAvatar()) + '" alt="" aria-hidden="true">' +
          '<div><div class="chat-header__name">' + escHtml(AGENT.name) + '</div>' +
          '<div class="chat-header__role">' + escHtml(tf('s14AgentRole')) + '</div></div>' +
        '</header>' +
        '<div class="chart-card-feed" aria-label="' + escHtml(tf('s14FeedAria')) + '">' +
          '<div class="msg user">' + escHtml(tf('s14CardRequest')) + '</div>' +
          '<article class="chart-card" aria-label="' + escHtml(tf('s14CardAria')) + '">' +
            '<div class="chart-card__wheel" aria-hidden="true">' + miniWheelSvg(c) + '</div>' +
            '<div class="chart-card__body">' +
              '<span class="chart-card__kicker">' + escHtml(AGENT.name) + ' · ' + escHtml(tf('s14AgentRole')) + '</span>' +
              '<h3 class="chart-card__title">' + escHtml(tf('s14Title')) + '</h3>' +
              '<p class="chart-card__meta">' + escHtml(birthLine(c && c.birth)) + '</p>' +
            '</div>' +
            '<div class="chart-card__actions">' +
              '<button type="button" class="btn btn--primary" data-act="chart-open">' + escHtml(tf('s14OpenChart')) + '</button>' +
            '</div>' +
          '</article>' +
        '</div>' +
      '</div>';
  };

  /* ══ ВИД 2 · chart-loading: 3-шаговый прогресс (§11.2 loading) ═════════ */

  app.renderChartLoadingR06 = function (main) {
    if (!main) return;
    main.innerHTML =
      '<div class="tool-view">' +
        chartHeader(tf('s14Title'), 'chart-back', tf('s14BackChat')) +
        '<div class="tool-run__status" role="status" aria-live="polite">' +
          '<span class="tool-run__spinner" aria-hidden="true"></span>' +
          '<span><span class="tool-run__status-title">' + escHtml(tf('s14LoadingTitle')) + '</span><br>' +
          '<span class="tool-run__status-note">' + escHtml(tf('s14LoadingNote')) + '</span></span>' +
        '</div>' +
        '<div class="tool-run__steps" aria-label="' + escHtml(tf('s14StepsAria')) + '">' +
          '<div class="tool-run__step is-done"><span class="tool-run__step-icon" aria-hidden="true">' +
            '<svg viewBox="0 0 16 16" style="width:12px;height:12px"><path d="M3 8.5l3.5 3.5L13 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>' +
            '<span>' + escHtml(tn('s14Step1', birthLine(s14State().chart && s14State().chart.birth))) + '</span></div>' +
          '<div class="tool-run__step is-active" aria-current="step"><span class="tool-run__step-icon" aria-hidden="true">2</span><span>' + escHtml(tf('s14Step2')) + '</span></div>' +
          '<div class="tool-run__step"><span class="tool-run__step-icon" aria-hidden="true">3</span><span>' + escHtml(tf('s14Step3')) + '</span></div>' +
        '</div>' +
        '<button type="button" class="btn btn--secondary btn--block" disabled aria-busy="true">' + escHtml(tf('s14Building')) + '</button>' +
      '</div>';
  };

  /* ══ ВИД 3 · chart-empty: честный путь к форме (§11.2 empty) ═══════════ */

  app.renderChartEmptyR06 = function (main) {
    if (!main) return;
    const me = app.me || {};
    const noTime = me.birth_date && !me.birth_time_known;
    main.innerHTML =
      '<div class="tool-view">' +
        chartHeader(tf('s14Title'), 'chart-back', tf('s14BackChat')) +
        '<div class="chart-empty">' +
          '<div class="chart-empty__glyph" aria-hidden="true">' +
            '<svg viewBox="0 0 400 400"><circle cx="200" cy="200" r="188" fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5" stroke-dasharray="4 7"/><circle cx="200" cy="200" r="118" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-width="1" stroke-dasharray="3 6"/><path d="M200 12 L200 82 M200 318 L200 388 M12 200 L82 200 M318 200 L388 200" stroke="currentColor" stroke-opacity=".3" stroke-width="1.2"/></svg>' +
          '</div>' +
          '<h2 class="chart-empty__title">' + escHtml(tf('s14EmptyTitle')) + '</h2>' +
          '<p class="chart-empty__text">' + escHtml(tf('s14EmptyText')) + '</p>' +
          '<button type="button" class="btn btn--primary btn--block" data-act="chart-add-birth">' + escHtml(tf('s14AddBirth')) + '</button>' +
        '</div>' +
        (noTime ?
          '<section class="chart-partial" aria-label="' + escHtml(tf('s14NoTimeTitle')) + '"><h3 class="chart-partial__title">' + escHtml(tf('s14NoTimeTitle')) + '</h3>' +
          '<p class="chart-partial__text">' + escHtml(tf('s14NoTimeText')) + '</p>' +
          '<div class="chart-partial__actions">' +
          '<button type="button" class="btn btn--secondary" data-act="chart-add-birth">' + escHtml(tf('s14NoTimeBuild')) + '</button>' +
          '<button type="button" class="btn btn--ghost" data-act="chart-no-time">' + escHtml(tf('s14NoTimeCta')) + '</button></div></section>' : '') +
      '</div>';
  };

  /* ══ ВИД 4 · chart-main: колесо + списки (§3.3, §11.3) ═════════════════ */

  app.renderChartMainR06 = function (main) {
    if (!main) return;
    const st = s14State();
    const c = st.chart;
    const fail = st.failMode && String(st.failMode) === '1';
    if (fail) { app.renderChartErrorR06(main); return; }
    if (!c) { app.renderChartEmptyR06(main); return; }

    const items = wheelItems(c);
    const asc = c.ascendant;
    const lumSun = (c.planets || []).find(function (p) { return /солн/i.test(p.name); }) || (c.planets || [])[0] || {};
    const lumMoon = (c.planets || []).find(function (p) { return /лун/i.test(p.name) && !p.name.match(/узл|лилит/i); }) || {};
    const exact = !!(c.birth && c.birth.time_known);
    const aspects = (c.aspects || []).slice(0, 12);
    const houses = (c.houses || []).slice(0, 12);

    function planetRow(p, i) {
      return '<button type="button" class="chart-row" data-act="chart-planet" data-p="' + i + '">' +
        '<span class="chart-row__glyph" aria-hidden="true">' + escHtml(planetGlyph(p.name) || (p.sign ? SIGNS[p.sign] : '•')) + '</span>' +
        '<span class="chart-row__body"><span class="chart-row__name">' + escHtml(p.name) + (p.retro ? ' <span class="chart-row__retro" aria-hidden="true">☍</span>' : '') + '</span>' +
        '<span class="chart-row__val">' + escHtml(fmtDeg(p.deg) + ' ' + (p.sign || '')) + (p.house ? ' · ' + escHtml(tn('s14HouseShort', p.house)) : '') + '</span></span>' +
        '<span class="chart-row__go" aria-hidden="true">›</span></button>';
    }

    main.innerHTML =
      '<div class="tool-view tool-view--wide">' +
        chartHeader(tf('s14Title'), 'chart-back', tf('s14BackChat'),
          '<button type="button" class="chat-header__btn" data-act="chart-share" aria-label="' + escHtml(tf('s14ShareAria')) + '">' +
          '<svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M10 13V4M6 8l4-4 4 4M4 13v2.5h12V13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>') +
        '<p class="chart-provenance">' +
          '<span class="chart-provenance__mark" aria-hidden="true">✦</span>' +
          '<span>' + escHtml(tf('s14Provenance')) + ' <strong>' + escHtml(birthLine(c.birth)) + '</strong> · ' +
          escHtml(exact ? tf('s14ExactTime') : tf('s14NoExactTime')) + ' ' +
          '<button type="button" class="chart-provenance__link" data-act="chart-add-birth">' + escHtml(tf('s14EditBirth')) + '</button></span>' +
        '</p>' +
        '<div class="chart-scene">' +
          '<div class="chart-scene__wheel">' +
            wheelSvg(items, { clickable: true }) +
            '<p class="chart-scene__hint">' + escHtml(tf('s14WheelHint')) + '</p>' +
          '</div>' +
          '<div class="chart-scene__side">' +
            '<section class="chart-lum" aria-label="' + escHtml(tf('s14LumAria')) + '">' +
              '<h2 class="chart-side__title">' + escHtml(tf('s14LumTitle')) + '</h2>' +
              '<div class="chart-lum__row"><span class="chart-lum__glyph" aria-hidden="true">☉</span>' +
                '<div class="chart-lum__body"><span class="chart-lum__name">' + escHtml(lumSun.name || tf('s14Sun')) + '</span>' +
                '<span class="chart-lum__val">' + escHtml(fmtDeg(lumSun.deg) + ' ' + (lumSun.sign || '') + (lumSun.house ? ' · ' + escHtml(tn('s14HouseShort', lumSun.house)) : '')) + '</span></div></div>' +
              (lumMoon.name ? '<div class="chart-lum__row"><span class="chart-lum__glyph" aria-hidden="true">☽</span>' +
                '<div class="chart-lum__body"><span class="chart-lum__name">' + escHtml(lumMoon.name) + '</span>' +
                '<span class="chart-lum__val">' + escHtml(fmtDeg(lumMoon.deg) + ' ' + (lumMoon.sign || '') + (lumMoon.house ? ' · ' + escHtml(tn('s14HouseShort', lumMoon.house)) : '')) + '</span></div></div>' : '') +
              (asc && asc.sign ? '<div class="chart-lum__row"><span class="chart-lum__glyph chart-lum__glyph--asc" aria-hidden="true">Asc</span>' +
                '<div class="chart-lum__body"><span class="chart-lum__name">' + escHtml(tf('s14Asc')) + '</span>' +
                '<span class="chart-lum__val">' + escHtml(fmtDeg(asc.deg) + ' ' + asc.sign) + '</span></div></div>' : '') +
            '</section>' +
            '<details class="chart-details" open>' +
              '<summary class="chart-details__summary">' + escHtml(tn('s14PlanetsSummary', (c.planets || []).length)) + '</summary>' +
              '<div class="chart-details__body">' +
                items.map(function (p, i) { return planetRow(p, i); }).join('') +
              '</div>' +
            '</details>' +
            (aspects.length ? '<details class="chart-details">' +
              '<summary class="chart-details__summary">' + escHtml(tn('s14AspectsSummary', aspects.length)) + '</summary>' +
              '<div class="chart-details__body">' +
                aspects.map(function (a) {
                  return '<div class="chart-aspect"><span class="chart-aspect__glyph" aria-hidden="true">' + escHtml(a.glyph || '∠') + '</span>' +
                    '<span>' + escHtml(a.p1 + ' — ' + a.p2 + ' · ' + a.aspect) + '</span></div>';
                }).join('') +
              '</div></details>' : '') +
            (houses.length ? '<details class="chart-details">' +
              '<summary class="chart-details__summary">' + escHtml(tn('s14HousesSummary', houses.length)) + '</summary>' +
              '<div class="chart-details__body">' +
                houses.map(function (h) {
                  return '<div class="chart-house"><span class="chart-house__n">' + h.n + '</span>' +
                    '<span>' + escHtml((h.sign || '') + (h.deg != null ? ' · ' + fmtDeg(h.deg) : '')) + '</span></div>';
                }).join('') +
              '</div></details>' : '') +
          '</div>' +
        '</div>' +
        '<div class="result__actions">' +
          '<button type="button" class="btn btn--primary" data-act="chart-interpret">' + escHtml(tf('s14InterpretCta')) + '</button>' +
          '<button type="button" class="btn btn--secondary" data-act="chart-ask-agent">' + escHtml(tf('s14AskAboutChart')) + '</button>' +
        '</div>' +
      '</div>';
  };

  /* ══ ВИД 5 · chart-zoom: планета крупно (§11.3 / §6.5) ═════════════════ */

  app.renderChartZoomR06 = function (main) {
    if (!main) return;
    const st = s14State();
    const items = wheelItems(st.chart || {});
    const p = items[st.planet != null ? st.planet : 0] || items[0] || {};
    main.innerHTML =
      '<div class="tool-view">' +
        chartHeader(p.name || tf('s14Title'), 'chart-back-main', tf('s14BackChart')) +
        '<div class="chart-zoom">' +
          '<div class="chart-zoom__badge" aria-hidden="true"><span class="chart-zoom__glyph">' + escHtml(p.glyph || '☉') + '</span></div>' +
          '<h2 class="chart-zoom__title">' + escHtml((p.name || '') + (p.sign ? ' ' + (L() ? 'in ' : 'в ') + p.sign : '')) + '</h2>' +
          '<p class="chart-zoom__meta">' + escHtml((p.deg != null ? fmtDeg(p.deg) + ' ' : '') + (p.sign || '') + (p.house ? ' · ' + tn('s14HouseShort', p.house) : '') + (p.retro ? ' · ' + tf('s14Retro') : '') || '—') + '</p>' +
          '<div class="result-details__body chart-zoom__note">' +
            '<p>' + escHtml(tn('s14ZoomNote', p.name)) + '</p>' +
          '</div>' +
        '</div>' +
        '<button type="button" class="btn btn--secondary btn--block" data-act="chart-ask-about-planet">' + escHtml(tn('s14AskAboutPlanet', p.name)) + '</button>' +
      '</div>';
  };

  /* ══ ВИД 6 · chart-interpret: 11 секций explain-chart (BUS-650) ═════════
   * Контракт: POST /api/chart/interpret → {text, structured, human}.
   * Preferred — human v2 (render_order + blocks); fallback structured v1
   * (11 секций по chart_interpretation.py); последний — text (markdown). */

  function interpretSectionsV1(s) {
    /* 11 секций structured-contract v1 — ровно REQUIRED_KEYS порядок */
    const lum = s.luminaries || {};
    const rk = s.rahu_ketu || {};
    const pp = s.peak_periods || {};
    const out = [];
    if (lum.sun || lum.moon || lum.ascendant) {
      out.push({ t: tf('s14iLum'), ps: [
        lum.sun ? { b: tf('s14Sun'), v: lum.sun } : null,
        lum.moon ? { b: tf('s14Moon'), v: lum.moon } : null,
        lum.ascendant ? { b: tf('s14Asc'), v: lum.ascendant } : null
      ].filter(Boolean) });
    }
    if (s.personality_portrait) out.push({ t: tf('s14iPortrait'), ps: [{ v: s.personality_portrait }] });
    if (rk.rahu || rk.ketu || rk.growth_step) {
      out.push({ t: tf('s14iRahuKetu'), ps: [
        rk.rahu ? { b: tf('s14iRahu'), v: rk.rahu } : null,
        rk.ketu ? { b: tf('s14iKetu'), v: rk.ketu } : null,
        rk.growth_step ? { b: tf('s14iStep'), v: rk.growth_step } : null
      ].filter(Boolean) });
    }
    if (s.strengths && s.strengths.length) out.push({ t: tf('s14iStrengths'), list: s.strengths });
    if (s.weaknesses && s.weaknesses.length) out.push({ t: tf('s14iWeaknesses'), list: s.weaknesses });
    if (s.purpose) out.push({ t: tf('s14iPurpose'), ps: [{ v: s.purpose }] });
    if (s.relationships) out.push({ t: tf('s14iLove'), ps: [{ v: s.relationships }], deep: true });
    if (s.career_money) out.push({ t: tf('s14iCareer'), ps: [{ v: s.career_money }], deep: true });
    if (s.aspect_synthesis) out.push({ t: tf('s14iAspects'), ps: [{ v: s.aspect_synthesis }], deep: true });
    if (pp.status || (pp.periods && pp.periods.length)) {
      out.push({ t: tf('s14iPeriods'), ps: [{ v: pp.status || '' }].filter(function (x) { return x.v; }), list: pp.periods || [], note: pp.note || '', deep: true });
    }
    if (s.synthesis) out.push({ t: tf('s14iSynthesis'), ps: [{ v: s.synthesis }] });
    return { sections: out, disclaimer: s.disclaimer || tf('s14Disclaimer') };
  }

  function interpretSectionsHuman(h) {
    /* human v2: blocks по render_order; техно-слой и hooks — <details> */
    const blocks = h.blocks || {};
    const order = (h.render_order && h.render_order.length) ? h.render_order : Object.keys(blocks);
    const out = order.filter(function (k) { return blocks[k]; }).map(function (k) {
      const b = blocks[k];
      const sec = { t: b.title || k, deep: k === 'love' || k === 'career' };
      if (b.text) sec.ps = [{ v: b.text }];
      if (b.items) sec.list = b.items;
      if (b.fields) {
        sec.ps = Object.keys(b.fields).map(function (fk) {
          const f = b.fields[fk];
          return f && f.text ? { b: f.label, v: f.text } : null;
        }).filter(Boolean);
      }
      if (b.details) {
        const dts = [];
        if (b.details.rahu) dts.push({ b: tf('s14iRahu'), v: b.details.rahu });
        if (b.details.ketu) dts.push({ b: tf('s14iKetu'), v: b.details.ketu });
        if (dts.length) (sec.ps = sec.ps || []).push.apply(sec.ps, dts);
      }
      return sec;
    }).filter(function (sec) { return (sec.ps && sec.ps.length) || (sec.list && sec.list.length); });
    if (h.precision && h.precision.note) out.push({ t: tf('s14iPrecision'), ps: [{ v: h.precision.note }], deep: true });
    if (h.question_hooks && h.question_hooks.length) {
      out.push({ t: tf('s14iHooks'), list: h.question_hooks.map(function (q) { return q.question; }), deep: true });
    }
    return { sections: out, disclaimer: h.disclaimer || tf('s14Disclaimer') };
  }

  function sectionHtml(sec, idx) {
    let inner = '';
    if (sec.ps) {
      inner = sec.ps.map(function (p) {
        return '<p class="interpret__p">' + (p.b ? '<strong>' + escHtml(p.b) + '</strong> — ' : '') + escHtml(p.v) + '</p>';
      }).join('');
    }
    if (sec.list) {
      inner += '<ul class="interpret__list">' + sec.list.map(function (li) {
        return '<li>' + escHtml(li) + '</li>';
      }).join('') + '</ul>';
    }
    if (sec.note) inner += '<p class="interpret__note">' + escHtml(sec.note) + '</p>';
    const body = '<h2 class="interpret__sec-title" id="s14-i-' + idx + '">' + escHtml(sec.t) + '</h2>' + inner;
    if (sec.deep) {
      return '<details class="result-details interpret__deep"><summary class="result-details__summary">' + escHtml(sec.t) + '</summary>' +
        '<div class="result-details__body">' + inner + '</div></details>';
    }
    return '<section class="interpret__sec" aria-labelledby="s14-i-' + idx + '">' + body + '</section>';
  }

  app.renderChartInterpretR06 = function (main) {
    if (!main) return;
    const st = s14State();
    main.innerHTML =
      '<div class="tool-view">' +
        chartHeader(tf('s14InterpretTitle'), 'chart-back-main', tf('s14BackChart'),
          '<img class="chat-header__avatar" src="' + escHtml(agentAvatar()) + '" alt="">') +
        '<div class="interpret" aria-busy="' + (st.busy ? 'true' : 'false') + '">' +
          (st.busy ?
            '<div class="interpret__loading" role="status"><span class="tool-run__spinner" aria-hidden="true"></span>' +
            '<span>' + escHtml(tf('s14InterpretLoading')) + '</span></div>'
          : '') +
        '</div>' +
      '</div>';
    if (st.busy) return;
    if (st.interpret) renderInterpretBody();
    else app.chartInterpretRun();
  };

  function renderInterpretBody() {
    const st = s14State();
    const box = document.querySelector('.interpret');
    if (!box) return;
    const r = st.interpret || {};
    let data = null;
    if (r.human && r.human.blocks) data = interpretSectionsHuman(r.human);
    else if (r.structured) data = interpretSectionsV1(r.structured);
    if (!data) {
      /* legacy text: единственный markdown-блок, contract честно скажет об этом */
      box.innerHTML = '<div class="result-details__body">' + richMd(r.text || '') + '</div>' +
        interpretFooter();
      return;
    }
    const secs = data.sections;
    box.innerHTML =
      '<p class="interpret__meta">' + escHtml(tf('s14InterpretMeta')) + '</p>' +
      '<h1 class="interpret__title">' + escHtml(tf('s14InterpretH1')) + '</h1>' +
      (r.human && r.human.blocks && r.human.blocks.who_you_are && r.human.blocks.who_you_are.text ?
        '<div class="interpret__verdict" role="note"><strong>' + escHtml(tf('s14Verdict')) + ':</strong> ' +
        escHtml(r.human.blocks.who_you_are.text) + '</div>' : '') +
      secs.map(function (sec, i) { return sectionHtml(sec, i); }).join('') +
      '<p class="interpret__disclaimer" role="note">' + escHtml(data.disclaimer) + '</p>' +
      interpretFooter();
  }

  function interpretFooter() {
    return '<div class="result__actions">' +
        '<button type="button" class="btn btn--primary" data-act="chart-ask-agent">' + escHtml(tf('s14Discuss')) + '</button>' +
        '<button type="button" class="btn btn--secondary" data-act="chart-back-main">' + escHtml(tf('s14BackChart')) + '</button>' +
      '</div>' +
      '<p class="result__saved-note"><svg viewBox="0 0 16 16" aria-hidden="true" style="width:14px;height:14px;flex:none"><path d="M3 8.5l3.5 3.5L13 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      '<span>' + escHtml(tf('s14SavedNote')) + '</span></p>';
  }

  /* Загрузка разбора: кэш в состоянии вида (повторное открытие бесплатное). */
  app.chartInterpretRun = async function () {
    const st = s14State();
    if (st.busy) return;
    st.busy = true;
    const box = document.querySelector('.interpret');
    if (box) box.setAttribute('aria-busy', 'true');
    try {
      const r = await api('/api/chart/interpret', { method: 'POST' });
      st.interpret = r || {};
      st.busy = false;
      if (document.querySelector('.interpret')) renderInterpretBody();
      haptic('soft');
    } catch (e) {
      st.busy = false;
      const el = document.querySelector('.interpret');
      if (el) {
        el.setAttribute('aria-busy', 'false');
        el.innerHTML =
          '<div class="tool-run__fail is-open" role="alert"><span aria-hidden="true">⚠️</span><span><strong>' +
          escHtml(friendlyError(e, tf('s14InterpretFail'))) + '</strong></span></div>' +
          '<div class="result__actions"><button type="button" class="btn btn--secondary" data-act="chart-interpret-retry">' + escHtml(tf('s14Retry')) + '</button>' +
          '<button type="button" class="btn btn--ghost" data-act="chart-back-main">' + escHtml(tf('s14BackChart')) + '</button></div>';
      }
    }
  };

  /* ══ ВИД 7 · chart-error: сбой расчёта (§11.2 network error) ═══════════ */

  app.renderChartErrorR06 = function (main) {
    if (!main) return;
    main.innerHTML =
      '<div class="tool-view">' +
        chartHeader(tf('s14Title'), 'chart-back', tf('s14BackChat')) +
        '<div class="tool-run__fail is-open" role="alert">' +
          '<span aria-hidden="true">⚠️</span>' +
          '<span><strong>' + escHtml(tf('s14ErrorTitle')) + '</strong><br>' +
          '<span>' + escHtml(tf('s14ErrorText')) + '</span>' +
          '<span class="tool-run__fail-actions">' +
            '<button type="button" class="btn btn--secondary btn--sm" data-act="chart-reload">' + escHtml(tf('s14CheckStatus')) + '</button>' +
            '<button type="button" class="btn btn--ghost btn--sm" data-act="chart-reload">' + escHtml(tf('s14Restart')) + '</button>' +
          '</span></span>' +
        '</div>' +
      '</div>';
  };

  /* ══ Вход в сцену S14: грузим карту, затем роут на нужный вид ═══════════ */

  app.openChartScene = async function (view, opts) {
    const st = s14State();
    const o = opts || {};
    /* failMode — только QA-проба (?fail=1); обычный вход сбрасывает. */
    st.failMode = o.fail != null ? String(o.fail) : null;
    const target = view || 'chart-main';
    /* Карта нужна всем видам кроме error; грузим один раз и держим в состоянии. */
    if (!st.chart && !st.loadingChart && target !== 'chart-error') {
      st.loadingChart = true;
      /* Пока карта в полёте — честный loading-вид (§11.2), не flash empty. */
      app.go(target === 'chart-card' ? 'chart-card' : 'chart-loading');
      try {
        const c = await api('/api/chart');
        st.chart = c || null;
      } catch (e) {
        st.chart = null;
        const status = e && e.status;
        /* api() уже переминчивает сессию при 401 (withSessionResilient);
         * сюда 401 доходит только при финальной неудаче — честный auth-экран. */
        if (status === 401) { app.renderAuthRequired(e); return; }
        /* прочие ошибки (5xx/сеть) — целевой вид сам покажет empty по null;
         * ошибка расчёта рендерится через ?fail=1/QA или chart-error. */
      } finally {
        st.loadingChart = false;
      }
      /* 400 «карта ещё не построена» → честный empty-вид (не выдумываем данные) */
      app.go(target === 'chart-card' ? 'chart-card' : target);
      return;
    }
    app.go(target);
  };

  /* ══ Действия S14 ══════════════════════════════════════════════════════ */

  app.chartPlanetZoom = function (idx) {
    s14State().planet = Number(idx) || 0;
    haptic('light');
    app.go('chart-zoom');
  };

  app.chartAskAboutPlanet = function () {
    /* «Спросить Уранию об этой планете» — переход в чат с шаблон-фразой
     * в поле ввода (fillInput: редактирование, не авто-отправка). */
    const st = s14State();
    const p = wheelItems(st.chart || {})[st.planet || 0] || {};
    tactile('select');
    app.openChat('astro', function () {
      if (p.name) app.fillInput(tn('s14AskPlanetDraft', p.name));
    });
  };

  app.chartAskAgent = function () {
    /* «Спросить Уранию» — возврат в чат с контекстом карты (прототип p4:
     * data-goto-view="chat-card", без автогенерации вопроса). */
    tactile('select');
    app.openChat('astro');
  };

  app.chartAddBirth = function () {
    /* Честный путь к форме: тот же сборщик карты, что в чате (10-chart.js);
     * after-коллбек openChat — вместо setTimeout-хака. */
    tactile('select');
    app.openChat('astro', function () {
      if (typeof app.featureChart === 'function') app.featureChart();
    });
  };

  app.chartNoTime = function () {
    /* «Не знаю время — что делать?» — вопрос Урании без новых расчётов. */
    tactile('select');
    app.openChat('astro', function () {
      app.fillInput(tf('s14NoTimeDraft'));
    });
  };

  app.chartReload = function () {
    /* §11.2 error: «Проверить статус»/«Начать заново» — сброс кэша карты
     * и повторный вход в сцену (расчёт бесплатный, §5.3 — без списаний). */
    tactile('select');
    const st = s14State();
    st.chart = null;
    st.failMode = null;
    app.openChartScene('chart-main');
  };

  app.chartShare = function () {
    /* Без новых генераций изображений (запрет задачи): копируем текстовую
     * строку карты — тот же UX, что у реферальной ссылки (12-misc.js refCopy). */
    vb(7);
    const c = s14State().chart;
    const line = birthLine(c && c.birth);
    const text = tf('s14ShareText') + (line ? ' · ' + line : '');
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
        app.toast(tf('s14ShareCopied'));
      } else {
        app.toast(text);
      }
    } catch (e) { app.toast(text); }
  };

  app.chartSceneBack = function () {
    /* Back-matrix H2: из подэкранов — «К разговору»; но из zoom/interpret
     * возврат к карте без потери состояния (SPEC §2.5). */
    const v = app.view;
    if (v === 'chart-zoom' || v === 'chart-interpret') app.go('chart-main');
    else app.go('chat');
  };
})();
