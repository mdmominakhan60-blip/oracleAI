/* art: SVG/визуал-генераторы — портрет агента, фазы луны, кольца, карьерные окна */
/* SVG-фаза луны по эмодзи от сервера (🌑…🌘): освещённая доля и терминатор.
   Почти точная визуализация классического цикла без эфемерид. */

// Персонаж агента: портрет-арт из /static/img/agents/{code}.jpg + сигил роли.
// SVG не зависит от системного шрифта Telegram и сохраняет одинаковую массу в любом размере.
const AGENT_SIGILS = {
  oracle: '<path d="M3.2 12s3.15-5.35 8.8-5.35S20.8 12 20.8 12 17.65 17.35 12 17.35 3.2 12 3.2 12Z"/><circle cx="12" cy="12" r="2.35"/><path d="m12 2.55.95 3.25 3.25.95-3.25.95L12 10.95l-.95-3.25-3.25-.95 3.25-.95L12 2.55Z"/>',
  astro: '<circle cx="12" cy="12" r="8.55"/><circle cx="12" cy="12" r="2"/><path d="M12 3.45v6.55M20.55 12H14M12 20.55V14M3.45 12H10M6.1 6.1l4.55 4.55m7.25-4.55-4.55 4.55"/>',
  tarot: '<rect x="5.35" y="3.35" width="13.3" height="17.3" rx="2"/><path d="m12 6.65.95 3.3 3.3.95-3.3.95L12 15.15l-.95-3.3-3.3-.95-3.3-.95L12 6.65Z"/><path d="M8.3 17.7h7.4"/>',
  chiromant: '<path d="M8.2 20.2c-.4-2.15-.25-4.35.15-6.2.37-1.72.38-3.18.08-4.55-.22-1.03.2-1.75.9-1.75.92 0 1.13 1.25 1.34 2.45l.3 1.7.12-7.8c.02-.98.48-1.53 1.14-1.53.75 0 1.05.62 1.08 1.57l.17 5.18.15-6.12c.02-.96.48-1.52 1.14-1.5.75.02 1.02.68 1.03 1.6l.08 6.04.23-4.65c.05-.91.5-1.37 1.1-1.3.7.08.9.7.83 1.57l-.16 5.12.33-2.62c.1-.8.52-1.2 1.07-1.08.62.14.78.7.67 1.48l-.67 5.3c-.22 1.76-.2 3.57-.02 5.43"/><path d="M8.4 20.2c2.65 1.05 5.55 1.08 8.1.1"/>',
  coach: '<path d="M12 3.1c3.85 3.15 5.6 6.3 5.25 9.45-.34 3.17-2.1 5.7-5.25 7.35-3.15-1.65-4.91-4.18-5.25-7.35C6.4 9.4 8.15 6.25 12 3.1Z"/><path d="M12 7.2v8.65M12 12.2c-1.55-1.45-3.05-1.85-4.45-1.72M12 14.15c1.48-1.38 2.88-1.77 4.28-1.65"/>',
  numero: '<circle cx="6" cy="6" r="1.55"/><circle cx="18" cy="6" r="1.55"/><circle cx="12" cy="12" r="1.9"/><circle cx="6" cy="18" r="1.55"/><circle cx="18" cy="18" r="1.55"/><path d="m7.35 7.2 3.15 3.2m2.98 0 3.15-3.2m-9.3 9.6 3.15-3.2m2.98 0 3.15 3.2"/>',
  keeper: '<path d="M12 3.15c3.3 2.55 5.85 5.45 5.85 9.1 0 3.15-2.58 5.7-5.85 7.6-3.27-1.9-5.85-4.45-5.85-7.6 0-3.65 2.55-6.55 5.85-9.1Z"/><path d="M9.25 12.1h5.5M12 9.35v5.5"/><path d="m16.9 4.1.55 1.75 1.75.55-1.75.55-.55 1.75-.55-1.75-1.75-.55 1.75-.55.55-1.75Z"/>'
};
function agentSigil(code) {
  const body = AGENT_SIGILS[code] || AGENT_SIGILS.oracle;
  return `<svg class="agent-sigil" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
}
function agentSprite(a, cheer) {
  if (!a) return '';
  const ac = a.accent || '#e8c56b';
  const bright = a.accentBright || ac;
  const glow = a.accentGlow || 'rgba(230,193,120,.34)';
  const surface = a.surface || 'rgba(230,193,120,.12)';
  return `<span class="agent-sprite${cheer ? ' cheer' : ''}" style="--ac:${esc(ac)};--ac-bright:${esc(bright)};--ac-glow:${esc(glow)};--ac-surface:${esc(surface)}" role="img" aria-label="${esc(a.name || '')}">
      <img class="agent-face" src="${esc(a.avatar || `/static/img/agents/${a.code}.jpg`)}" alt="${esc(a.name || '')}" width="60" height="60" loading="eager" fetchpriority="high" decoding="async" onerror="this.onerror=null;this.src='/static/img/oracle-mark.png'">
      <span class="as-prop">${agentSigil(a.code)}</span>
    </span>`;
}

// Истинная фаза луны как SVG: внешняя дуга диска + терминатор-эллипс.
// lit=0 новолуние, 1 полнолуние; right=false — свет слева (убывающая).
// Уникальный id сквозного градиента луны на каждый SVG: несколько лун на странице
// (сегодня/профиль/док) не должны конфликтовать за один #mg, иначе fill не резолвится.
let moonGradSeq = 0;
// Уникальные id свечения для «Спидометра любви» — несколько виджетов в ленте
// не должны конфликтовать за один id фильтра (аналогично moonGradSeq).
let spdSeq = 0;
function moonSvg(emoji, cls) {
  const gid = 'mg' + (++moonGradSeq);
  const ph = MOON_DISC[emoji] || { lit: 0.5, right: true };
  const r = 45, lit = Math.max(0, Math.min(1, ph.lit));
  let d;
  if (lit <= 0) d = '';
  else if (lit >= 1) d = `M0,-${r} A${r} ${r} 0 1 1 0,${r} A${r} ${r} 0 1 1 0,-${r} Z`;
  else {
    const ex = (lit >= 0.5 ? 1 : lit * 2) * r;
    d = `M0,-${r} A${r} ${r} 0 0 1 0,${r} L0,${r} A${ex} ${r} 0 0 1 0,-${r} Z`;
  }
  const flip = ph.right ? '' : ' scale(-1,1)';
  return `<svg viewBox="0 0 100 100" class="${cls || ''}" aria-hidden="true"><defs>
    <radialGradient id="${gid}" cx="45%" cy="38%" r="75%">
      <stop offset="0%" stop-color="#f8edcf"/><stop offset="55%" stop-color="#ddc795"/>
      <stop offset="100%" stop-color="#a9966a"/>
    </radialGradient></defs>
    <circle cx="50" cy="50" r="${r}" fill="#1d1838" stroke="rgba(230,193,120,.35)" stroke-width="2"/>
    ${d ? `<g transform="translate(50,50)${flip}"><path d="${d}" fill="url(#${gid})"/></g>` : ''}</svg>`;
}

/* Карьерные окна: тип действия по имени лунной фазы (данные — код, трактовка — LLM).
   Имена фаз 1-в-1 с app/core/astro.py MOON_PHASES. */
const CAREER_WIN = {
  'Новолуние': ['🚀 Старт · планируй', '#7fd4a8'],
  'Растущий серп': ['🚀 Старт · переговоры', '#7fd4a8'],
  'Первая четверть': ['⚖️ Решение', '#e6c178'],
  'Растущая Луна': ['⚡ Действие · подпись, рост', '#7fd4a8'],
  'Полнолуние': ['⚠️ Осторожно · не решай судьбоносно', '#ff8fa3'],
  'Убывающая Луна': ['✅ Завершение · долги, финалы', '#e6c178'],
  'Последняя четверть': ['✅ Завершение · отпусти лишнее', '#e6c178'],
  'Старый серп': ['🌙 Пауза · восстановление', '#8b86a3'],
};
const careerWindow = d => {
  const w = CAREER_WIN[d && d.name] || ['·', '#8b86a3'];
  return { t: w[0], c: w[1] };
};

// круговой прогресс 0–100% (маленькое SVG-кольцо)
function ringSvg(pct) {
  const r = 17, c = 2 * Math.PI * r;
  return `<svg viewBox="0 0 44 44" class="pr-svg"><circle class="pr-ring-bg" cx="22" cy="22" r="${r}"></circle><circle class="pr-ring-fg" cx="22" cy="22" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - Math.max(0, Math.min(100, pct || 0)) / 100)}"></circle></svg>`;
}

