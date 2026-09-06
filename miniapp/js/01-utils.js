/* utils: Telegram WebApp, haptic, API-клиент, escaping, даты */
const tg = () => window.Telegram && window.Telegram.WebApp;

/* haptic-отклик Telegram (безопасно — если WebApp/HapticFeedback нет, молча). */
function haptic(kind) {
  try {
    const H = tg() && tg().HapticFeedback;
    if (!H) return;
    if (kind === 'success') H.notificationOccurred('success');
    else if (kind === 'error') H.notificationOccurred('error');
    else if (kind === 'soft') H.impactOccurred('soft');
    else H.impactOccurred('light');
  } catch (e) {}
}

/* вибро-отклик (безопасно): vibrate может отсутствовать или бросать — тихо глотаем.
   Заменяет повсюду копии `if (navigator.vibrate) { try { navigator.vibrate(...) } catch (e) {} }`. */
const vb = p => { try { navigator.vibrate && navigator.vibrate(p); } catch (e) {} };

/* Семантический отклик для общих UI-переходов. Локальные сценарии по-прежнему
   могут выбирать свой более выразительный сигнал на успех или ошибку. */
function tactile(event = 'select') {
  const pattern = {
    select: { kind: 'light', pulse: null },
    open: { kind: 'soft', pulse: 12 },
    reveal: { kind: 'soft', pulse: 16 },
    complete: { kind: 'success', pulse: [10, 40, 18] },
    error: { kind: 'error', pulse: null },
  }[event] || { kind: 'light', pulse: null };
  haptic(pattern.kind);
  if (pattern.pulse) vb(pattern.pulse);
}

/* гонка-предохранитель для виджетов: активен ли всё ещё тот же виджет в том же
   чате/экране. Если юзер успел открыть другой виджет/агента, закрыть чат или уйти
   с экрана — late-ответ от api() надо бросить, а не затирать чужой рендер. */
function widAlive(key, view, pend) {
  return app.chat.key === key && app.view === view && app.chat.pending === pend;
}

/* ── API-клиент ─────────────────────────────────────────────────────────── */

/* BUS-341: X-Session-Token. Подписанная initData шлётся ровно один раз — на
   минт POST /api/auth/session; дальше все запросы ходят токеном. Повторный
   минт той же initData сервер отвергает (401 replay, nonce одноразовый), поэтому
   токен переживает reload вебвью в sessionStorage (умирает с вкладкой — в
   localStorage долгоживущие креды не храним). Если минт не удался (429/сеть/
   401 replay) — тихо откатываемся на back-compat путь x-init-data для read-ручек. */
const SESSION_KEY = 'oracle_session';
const sessionState = { token: null };
try { sessionState.token = sessionStorage.getItem(SESSION_KEY); } catch (e) {}

function storeSession(token) {
  sessionState.token = token;
  try { sessionStorage.setItem(SESSION_KEY, token); } catch (e) {}
}
function clearSession() {
  sessionState.token = null;
  try { sessionStorage.removeItem(SESSION_KEY); } catch (e) {}
}

/* Минт сессии. Одна попытка без ретраев: ретрай после потерянного ответа
   получил бы 401 replay (nonce уже потреблён). Параллельные вызовы делят один
   in-flight промис — два гонящихся минта одной initData получили бы 401 replay. */
let mintInFlight = null;
async function mintSession() {
  if (mintInFlight) return mintInFlight;
  const initData = tg() && tg().initData;
  if (!initData) return false;
  mintInFlight = (async () => {
    try {
      const res = await fetch('/api/auth/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      });
      if (!res.ok) return false;
      const body = await res.json();
      if (!body || !body.session_token) return false;
      storeSession(body.session_token);
      return true;
    } catch (e) {
      return false;
    } finally {
      mintInFlight = null;
    }
  })();
  return mintInFlight;
}

/* Токен приоритетнее initData (сервер тоже приоритизирует X-Session-Token);
   call-site может переопределить через opts.headers. */
function authHeaders() {
  const h = {};
  if (sessionState.token) h['X-Session-Token'] = sessionState.token;
  else {
    const initData = tg() && tg().initData;
    if (initData) h['X-Init-Data'] = initData;
  }
  return h;
}

/* 401 с токеном = токен истёк/сменён ключ подписи: роняем его, пытаемся
   переминтить и повторить запрос один раз. 401 = не пройдена аутентификация,
   до бизнес-логики дело не дошло, так что повтор мутации безопасен.
   Гонка параллельных запросов: сверяем токен, с которым ушёл запрос, с текущим.
   Если другой запрос уже переминтил — не трогаем его свежий токен и просто
   повторяем; если нет — чистим и минтим сами (in-flight дедуп схлопнет дубль). */
async function withSessionResilient(run) {
  const used = sessionState.token;
  let out = await run();
  if (out.res.status !== 401) return out;
  if (sessionState.token === used) {
    if (!used) return out; /* 401 по x-init-data — повтор с той же initData бессмыслен */
    clearSession();
    if (!(await mintSession())) return out;
  }
  return await run();
}

function newRequestKey() {
  try {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
  } catch (e) {}
  return 'chat-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
}

async function api(path, opts = {}) {
  let url = path;
  const dev = new URLSearchParams(location.search).get('dev_user');
  if (dev) url += (url.includes('?') ? '&' : '?') + 'dev_user=' + dev;
  const run = async () => {
    // DEV_KEY обязателен при DEV_MODE=1 (BUS-90): без заголовка dev-запрос ловит 401.
    const headers = Object.assign(
      { 'Content-Type': 'application/json' }, authHeaders(), opts.headers || {});
    if (dev) {
      const devKey = localStorage.getItem('oracle_dev_key');
      if (devKey) headers['X-Dev-Key'] = devKey;
    }
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    let body = null;
    try { body = await res.json(); } catch (e) { /* пустое тело */ }
    return { res, body };
  };
  try {
    const { res, body } = await withSessionResilient(run);
    if (!res.ok) {
      const detail = body && (body.detail || JSON.stringify(body));
      const err = new Error(detail || 'Связь прервалась 🌙');
      err.status = res.status;
      throw err;
    }
    return body;
  } catch (err) {
    // ретрай: сетевой сбой — всегда; 5xx — только для GET (мутации не ретраим,
    // чтобы не задвоить эффект на сервере)
    const method = (opts.method || 'GET').toUpperCase();
    const network = !err || !err.status;
    const retriable = network || (method === 'GET' && err.status >= 500);
    if (retriable) {
      await new Promise(r => setTimeout(r, 600));
      try {
        const { res, body } = await run();
        if (!res.ok) {
          const detail = body && (body.detail || JSON.stringify(body));
          const e2 = new Error(detail || 'Связь прервалась 🌙');
          e2.status = res.status;
          throw e2;
        }
        return body;
      } catch (e2) { throw err; }
    }
    throw err;
  }
}

/* Binary API client for private chart/share images. Auth stays in headers; only
   allowlisted render parameters are present in the URL. */
async function apiBlob(path, opts = {}) {
  let url = path;
  const dev = new URLSearchParams(location.search).get('dev_user');
  if (dev) {
    url += (url.includes('?') ? '&' : '?') + 'dev_user=' + encodeURIComponent(dev);
  }
  const request = async () => {
    const used = sessionState.token;
    const headers = Object.assign({ Accept: 'image/png, image/webp' },
      authHeaders(), opts.headers || {});
    if (dev) {
      const devKey = localStorage.getItem('oracle_dev_key');
      if (devKey) headers['X-Dev-Key'] = devKey;
    }
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    if (res.status === 401) {
      if (sessionState.token === used) {
        if (used) {
          clearSession();
          if (await mintSession()) return request();
        }
      } else {
        return request(); /* другой запрос уже переминтил — повторяем сразу */
      }
    }
    if (!res.ok) {
      let body = null;
      try { body = await res.json(); } catch (e) { /* non-JSON error */ }
      const detail = body && (body.detail || body);
      const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || 'Связь прервалась 🌙'));
      err.status = res.status;
      err.code = detail && typeof detail === 'object' ? detail.code : undefined;
      throw err;
    }
    return res.blob();
  };
  try {
    return await request();
  } catch (err) {
    const retriable = !err || !err.status || err.status >= 500;
    if (!retriable) throw err;
    await new Promise(r => setTimeout(r, 600));
    return request();
  }
}

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* User-facing errors must never expose Telegram auth, provider, HTML or JSON details. */
function friendlyError(err, fallback) {
  const raw = String(err && err.message || '').trim();
  const status = err && Number(err.status);
  const secure = status === 401 || /signature|initdata|подпись|unauthori[sz]ed/i.test(raw);
  if (secure) return oracleLang() === 'en'
    ? 'Open OracleAI from Telegram to continue.'
    : 'Открой OracleAI из Telegram, чтобы продолжить.';
  const technical = !raw || status >= 500 || /<html|\{[\s\S]*\}|provider|llm|timeout|fetch|network|внутрен|не удалось подключиться/i.test(raw);
  if (technical) return fallback || (oracleLang() === 'en'
    ? 'This is temporary. Please try again in a moment.'
    : 'Это временно. Попробуй ещё раз через минуту.');
  return raw.length <= 180 ? raw : (fallback || (oracleLang() === 'en'
    ? 'Please try again.' : 'Попробуй ещё раз.'));
}

// Rich-escape для серверного текста (чат-история, ответы LLM, отчёты):
// сначала всё экранируем, затем восстанавливаем ТОЛЬКО закрытые пары <b>/<i>
// из их экранированной формы. <script>, onerror=, атрибуты остаются текстом.
const rich = s => esc(s).replace(/&lt;(\/?)(b|i)&gt;/g, '<$1$2>');
// rich + markdown-жирный **...** → <b> (для ИИ-разборов).
const richMd = s => rich(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');

const oracleLang = () => (window.app && app.me && app.me.lang) ||
  localStorage.getItem('oracle_lang') || 'ru';

function syncDocumentLocale() {
  const lang = oracleLang() === 'en' ? 'en' : 'ru';
  document.documentElement.lang = lang;
  document.documentElement.dir = 'ltr';
  document.title = lang === 'en'
    ? 'OracleAI — your gentle daily ritual'
    : 'OracleAI — твой мягкий ритуал дня';
}

// Русский род используем только при явном выборе; отсутствие значения не означает женский род.
function gendered(user, feminine, masculine, neutral) {
  if (user && user.gender === 'f') return feminine;
  if (user && user.gender === 'm') return masculine;
  return neutral || feminine;
}

const I18N = {
  ru: {
    today: 'Сегодня', chats: 'Диалоги', mine: 'Моё', ritual: 'Ритуал', guides: 'Проводники', profile: 'Профиль', paymentTab: 'Оплата', paymentHint: 'Доступ и пакеты',
    language: 'Язык интерфейса', russian: 'Русский', english: 'English',
    gender: 'Пол', female: 'Женский', male: 'Мужской', notSpecified: 'Не указан',
    femaleCopy: 'Обращения в женском роде', maleCopy: 'Обращения в мужском роде',
    notSpecifiedCopy: 'Нейтральные формулировки',
    genderCopy: 'Помогает Оракулу обращаться к тебе в правильном роде. Это можно изменить или не указывать.',
    changeGender: 'Изменить пол', saved: 'Сохранено', changeLanguage: 'Сменить язык',
    authRequiredTitle: 'Открой OracleAI в Telegram', authRequiredCopy: 'Личное пространство загружается только внутри защищённого входа Telegram.', authRetry: 'Повторить',
    authBotTitle: 'Осталось познакомиться с ботом', authBotCopy: 'Ты уже в Telegram — просто открой бота и нажми /start, а затем вернись сюда.', authOpenBot: 'Открыть бота',
    intro1Title: 'Твоё небо уже ждёт', intro1Sub: 'Личный Оракул читает твою карту, Луну и расклады — честно, по звёздам.',
    intro2Title: 'Карты отвечают на твой вопрос', intro2Sub: 'Настоящая колода Райдера-Уэйта придёт прямо в чат. Задай вопрос — карты лягут в расклад.',
    intro3Title: 'Прогноз каждый день', intro3Sub: 'Натальная карта, лунный календарь и карта дня — утро начинается с опоры.',
    introChartTitle: 'Собери натальную карту', introChartCta: 'Собрать мою натальную карту ✨',
    introChartCopyName: 'Лилит посмотрит на твою карту, {name}.', introChartCopy: 'Твоя карта рождения откроет характер и путь.',
    introChartCopyTail: 'Планеты, дома и предназначение — по дате и времени рождения.',
    introStart: 'Начать ✨', introNext: 'Дальше →', introSkip: 'Пропустить',
  },
  en: {
    today: 'Today', chats: 'Guides', mine: 'Mine', ritual: 'Ritual', guides: 'Guides', profile: 'Profile', paymentTab: 'Pay', paymentHint: 'Access and packs',
    language: 'App language', russian: 'Русский', english: 'English',
    gender: 'Gender', female: 'Female', male: 'Male', notSpecified: 'Not specified',
    femaleCopy: 'Feminine forms of address', maleCopy: 'Masculine forms of address',
    notSpecifiedCopy: 'Gender-neutral wording',
    genderCopy: 'Helps Oracle use the right form of address. You can change it later or leave it unspecified.',
    changeGender: 'Change gender', saved: 'Saved', changeLanguage: 'Change language',
    authRequiredTitle: 'Open OracleAI in Telegram', authRequiredCopy: 'Your personal space loads only inside a protected Telegram session.', authRetry: 'Retry',
    authBotTitle: 'One step left — meet the bot', authBotCopy: 'You are already in Telegram — just open the bot, tap /start, and come back here.', authOpenBot: 'Open the bot',
    intro1Title: 'Your sky is already waiting', intro1Sub: 'Your personal Oracle reads your chart, the Moon and the spreads — honestly, by the stars.',
    intro2Title: 'The cards answer your question', intro2Sub: 'A real Rider–Waite deck comes straight into the chat. Ask a question — the cards will fall into a spread.',
    intro3Title: 'A forecast every day', intro3Sub: 'Natal chart, moon calendar and card of the day — mornings begin with solid ground.',
    introChartTitle: 'Build your natal chart', introChartCta: 'Build my natal chart ✨',
    introChartCopyName: 'Lilith will look at your chart, {name}.', introChartCopy: 'Your birth chart reveals character and path.',
    introChartCopyTail: 'Planets, houses and purpose — from your date and time of birth.',
    introStart: 'Begin ✨', introNext: 'Next →', introSkip: 'Skip',
  },
};
const t = (key, fallback = '') => (I18N[oracleLang()] || I18N.ru)[key] || fallback || key;

// Тексты профиля живут отдельным словарём: экран рендерится большими шаблонами,
// поэтому так проще держать RU/EN-паритет и не смешивать перевод с логикой данных.
const PROFILE_I18N = {
  ru: {
    you: 'Ты', birth: 'Рождение', time: 'Время', city: 'Город', unknown: 'не известно',
    buildChartTitle: 'Соберём твою карту?', buildChartCopy: 'Три коротких шага — и Оракул сможет говорить с тобой точнее, бережнее и по твоему ритму.',
    date: 'дата', openMyChart: 'Открыть мою карту', space: 'Твоё пространство', path: 'твой путь',
    spaceCopy: 'Здесь собираются знаки, вопросы и мысли, которые хочется оставить рядом.',
    streakLabel: 'Серия: {count} дн.', firstRitual: 'Первый ритуал', summary: 'Сводка', chart: 'Карта', history: 'История', memory: 'Память',
    yourStreak: 'Твоя серия', streakHeadline: 'Ты в ритуале уже {count} дн.', streakContinue: 'Завтра откроется новый прогноз, чтобы мягко продолжить серию.',
    firstSign: 'Твой первый знак уже ждёт', firstSignCopy: 'Начни с одного вопроса — так рождается личный ритуал.',
    rituals: 'Ритуалы', sparks: 'Искры', questions: 'Вопросы', notes: 'Заметки', yourFoundation: 'Твоя основа', birthData: 'Данные рождения',
    natalChart: '🌌 Натальная карта', latestReadings: '🎴 Последние расклады', reports: '📜 Разборы', memoryAbout: '🧠 Что я помню о тебе',
    referralTitle: 'Поделись с близким человеком — получите {bonus} ✦', referralFallback: 'Поделись ссылкой — и получите бонус', copy: 'Скопировать',
    ascendant: 'Асцендент {sign}', chartNoTime: 'Время рождения не указано — ASC, MC и дома не показываем.', ask: 'Спросить', fullChart: 'Полная карта',
    chartDetailExact: 'Раху · Кету · дома · аспекты — в «Полной карте»', chartDetailApprox: 'Планеты и аспекты доступны без времени; ASC, MC и дома — после уточнения времени рождения.',
    chartEyebrow: 'Твоя основа', chartMissing: 'Карта ещё не собрана', chartMissingCopy: 'Укажи дату и город рождения. Время — только если ты его знаешь.', collectChart: 'Собрать карту',
    firstReadingEyebrow: 'Твой первый расклад', firstReadingTitle: 'Карты ждут твой вопрос', firstReadingCopy: 'Выбери бережный расклад — он сохранится здесь, чтобы к нему можно было вернуться.', askCards: 'Задать вопрос картам',
    allReadings: 'Все {count} раскладов ›', archive: 'Личный архив', unifiedHistory: 'Всё важное в одном месте', unifiedHistoryEmpty: 'Здесь соберутся расклады, разборы, разговоры и записи дневника.', historyReport: 'Разбор', historyTarot: 'Расклад', historyChat: 'Разговор', historyDiary: 'Дневник', reportsEmpty: 'Здесь появятся твои разборы', reportsEmptyCopy: 'Сохраняй важные ответы из диалогов, чтобы возвращаться к ним в нужный момент.',
    reportsUnavailable: 'Разборы временно недоступны', tryLater: 'Попробуй открыть этот раздел немного позже.', readingsHistory: 'История раскладов', readingsUnavailable: 'Не получилось открыть историю', readingsUnavailableCopy: 'Это временно. Новый расклад по-прежнему можно сделать в чате.', openTarot: 'Открыть Таролога',
    readingFallback: 'Расклад', saveStory: '📸 Сохранить в сторис', outcomeQuestion: 'Сбылось?', outcomeYes: '✓ Да', outcomePartial: 'Частично', outcomeNo: 'Нет',
    memoryTitle: 'Что я помню о тебе', memoryEyebrow: 'Личная память', memoryUnavailable: 'Память пока недоступна', memoryUnavailableCopy: 'Твои сохранённые факты остаются под защитой. Попробуй открыть их чуть позже.',
    noDate: 'без даты', deleteFact: 'Удалить факт', memoryOnCopy: 'Лилит использует только этот список, чтобы помнить важное между диалогами.', memoryPausedCopy: 'Память на паузе: новые факты не сохраняются и не попадают в ответы. Этот архив видишь только ты.',
    searchFacts: 'Найти в {count} {noun}', factOne: 'факте', factMany: 'фактах', searchFactAria: 'Найти факт в памяти', searchEmpty: 'Ничего не нашлось. Попробуй другое слово или очисти поиск.',
    memoryQuiet: 'Здесь пока тихо', memoryEmptyEnabled: 'Добавь факт вручную или расскажи о важном в диалоге — Лилит спросит разрешение сохранить его.', memoryEmptyPaused: 'Включи память, когда захочешь сохранять важное между диалогами.',
    context: 'Личный контекст', memoryAboutTitle: 'Память о тебе', pauseMemory: 'Поставить память на паузу', enableMemory: 'Включить память', active: 'Активна', paused: 'На паузе', factCountOne: 'факт', factCountFew: 'факта', factCountMany: 'фактов', deleteAny: 'Ты можешь удалить любой',
    addFactExample: 'Например: я люблю тихие утра', addFact: 'Добавить факт', archiveTitle: 'Твой архив', archiveUsed: 'используется в новых ответах', archiveHidden: 'сохранён и скрыт от Оракула',
    allReadingsTitle: 'Все расклады', readingsNone: 'Раскладов пока нет', firstCard: 'Вытянуть первую карту 🎴',
    fullChartTitle: '🌌 Полная натальная карта', chartPrecision: 'Точность карты', chartNoTimeShort: 'Время рождения не указано.', chartPrecisionCopy: 'Планеты и аспекты рассчитаны по дате. ASC, MC и дома не отображаются без времени рождения.', provenanceTitle: 'Источник расчёта', provenanceSummary: 'Технические сведения', provenanceProduct: 'Продуктовый движок', provenanceBackend: 'Backend', provenanceVersion: 'Версия адаптера', provenanceEphemeris: 'Эфемериды', provenanceLicense: 'Лицензия и уведомление', provenanceLicenseCopy: 'Использование backend регулируется AGPL-3.0 или коммерческой лицензией выбранной модели распространения.', provenanceUnavailable: 'Источник расчёта не указан', provenanceFallback: 'Детали источника недоступны для этой сохранённой карты.',
 house: 'дом', orb: 'орб',
    signAndRise: 'Твой знак и восход', solarFoundation: 'Твоя солнечная основа', sun: 'Солнце', signRiseCopy: 'твоя суть, воля и энергия.', ascendantCopy: 'как тебя видят со стороны.', mcCopy: 'направление и цель.', noTimeAssumptions: 'Время рождения не указано, поэтому не добавляем предположения об асценденте и направлении MC.',
    planets: 'Планеты', nodes: 'Узлы и точки', rahu: 'Предназначение этой жизни (Раху — северный узел)', ketu: 'Кармический багаж (Кету — южный узел)', lilith: 'Лилит · тёмная Луна', lilithCopy: 'Зона подсознательных желаний, тени, страсти и скрытой силы.',
    aspects: 'Аспекты (до 8)', aspectsCopy: 'Ключевые углы между планетами — как они разговаривают друг с другом.', conjunction: 'соединение', sextile: 'секстиль', trine: 'трин', square: 'квадрат', opposition: 'оппозиция', houses: 'Дома',
    askAstrologer: 'Спросить Астролога про карту', shareChart: '📸 Сохранить карту в сторис', simpleReading: '🧠 Разбор простыми словами', chartUnavailable: 'Карта пока недоступна', chartUnavailableCopy: 'Проверь соединение и попробуй открыть её чуть позже.', close: 'Закрыть', chartReading: 'Разбор карты', chartReadingUnavailable: 'Смысл пока не раскрылся', chartReadingUnavailableCopy: 'Попробуй ещё раз немного позже — твоя карта никуда не исчезнет.',
    saveGenderFailed: 'Не удалось сохранить пол', closeAria: 'Закрыть', changeLanguageFailed: 'Не удалось сменить язык', notifications: 'Уведомления', today: 'Сегодня', morningForecast: 'Утренний прогноз в боте', on: 'вкл', off: 'выкл', notificationCopy: 'Напоминания и прогнозы приходят в Telegram-боте. Включить их можно там же.', quiet: 'Пока тихо', quietCopy: 'Когда появится новый знак дня или важное напоминание, оно будет ждать тебя здесь.',
    memoryCount: '{count} записей · нажми, чтобы посмотреть и править', memoryEmpty: 'Пока пусто — нажми, чтобы добавить первое',
    account: 'Аккаунт', deleteAccount: 'Удалить аккаунт', deleteAccountCopy: 'Удаление необратимо: личные данные и материалы будут обезличены. Платёжные записи, которые нужно хранить по закону, могут остаться без связи с профилем.', deleteAccountConfirm: 'Удалить аккаунт и обезличить личные данные? Это действие нельзя отменить.', deleteAccountDone: 'Аккаунт удалён', deleteAccountDoneCopy: 'Личные данные обезличены. Если нужно уточнить остаточные платёжные или юридические записи, напиши в поддержку.', deleteAccountFailed: 'Не удалось завершить удаление. Проверь соединение и попробуй ещё раз.',
  },
  en: {
    you: 'You', birth: 'Birth', time: 'Time', city: 'City', unknown: 'unknown',
    buildChartTitle: 'Build your chart?', buildChartCopy: 'Three quick steps help Oracle respond with more precision, care and attention to your rhythm.',
    date: 'date', openMyChart: 'Open my chart', space: 'Your space', path: 'your path',
    spaceCopy: 'This is where signs, questions and thoughts worth keeping come together.',
    streakLabel: 'Streak: {count} days', firstRitual: 'First ritual', summary: 'Overview', chart: 'Chart', history: 'History', memory: 'Memory',
    yourStreak: 'Your streak', streakHeadline: 'Your ritual streak is {count} days strong', streakContinue: 'A new forecast will open tomorrow to gently continue your streak.',
    firstSign: 'Your first sign is waiting', firstSignCopy: 'Start with one question — that is how a personal ritual begins.',
    rituals: 'Rituals', sparks: 'Sparks', questions: 'Questions', notes: 'Notes', yourFoundation: 'Your foundation', birthData: 'Birth details',
    natalChart: '🌌 Natal chart', latestReadings: '🎴 Recent readings', reports: '📜 Insights', memoryAbout: '🧠 What I remember about you',
    referralTitle: 'Invite someone close — you both receive {bonus} ✦', referralFallback: 'Share your link and receive a bonus together', copy: 'Copy',
    ascendant: 'Ascendant {sign}', chartNoTime: 'Birth time is not set — ASC, MC and houses are hidden.', ask: 'Ask', fullChart: 'Full chart',
    chartDetailExact: 'Rahu · Ketu · houses · aspects — in “Full chart”', chartDetailApprox: 'Planets and aspects are available without a birth time; ASC, MC and houses appear after you add it.',
    chartEyebrow: 'Your foundation', chartMissing: 'Your chart is not ready yet', chartMissingCopy: 'Add your birth date and city. Include the time only if you know it.', collectChart: 'Build chart',
    firstReadingEyebrow: 'Your first reading', firstReadingTitle: 'The cards are waiting for your question', firstReadingCopy: 'Choose a gentle spread — it will be saved here so you can return to it later.', askCards: 'Ask the cards',
    allReadings: 'All {count} readings ›', archive: 'Personal archive', unifiedHistory: 'Everything important in one place', unifiedHistoryEmpty: 'Readings, insights, conversations and diary entries will gather here.', historyReport: 'Insight', historyTarot: 'Reading', historyChat: 'Conversation', historyDiary: 'Diary', reportsEmpty: 'Your insights will appear here', reportsEmptyCopy: 'Save meaningful answers from your conversations so you can return to them when you need to.',
    reportsUnavailable: 'Insights are temporarily unavailable', tryLater: 'Please try this section again a little later.', readingsHistory: 'Reading history', readingsUnavailable: 'Could not open reading history', readingsUnavailableCopy: 'This is temporary. You can still start a new reading in chat.', openTarot: 'Open Tarot guide',
    readingFallback: 'Reading', saveStory: '📸 Save to story', outcomeQuestion: 'Did it come true?', outcomeYes: '✓ Yes', outcomePartial: 'Partly', outcomeNo: 'No',
    memoryTitle: 'What I remember about you', memoryEyebrow: 'Personal memory', memoryUnavailable: 'Memory is temporarily unavailable', memoryUnavailableCopy: 'Your saved facts remain protected. Please try opening them again a little later.',
    noDate: 'no date', deleteFact: 'Delete fact', memoryOnCopy: 'Lilith uses only this list to remember what matters between conversations.', memoryPausedCopy: 'Memory is paused: new facts are not saved or used in responses. Only you can see this archive.',
    searchFacts: 'Search {count} {noun}', factOne: 'fact', factMany: 'facts', searchFactAria: 'Find a fact in memory', searchEmpty: 'Nothing found. Try another word or clear your search.',
    memoryQuiet: 'It is quiet here for now', memoryEmptyEnabled: 'Add one fact yourself or share something important in a conversation — Lilith will ask permission before saving it.', memoryEmptyPaused: 'Turn memory on when you want to keep important things between conversations.',
    context: 'Personal context', memoryAboutTitle: 'Memory about you', pauseMemory: 'Pause memory', enableMemory: 'Enable memory', active: 'Active', paused: 'Paused', factCountOne: 'fact', factCountFew: 'facts', factCountMany: 'facts', deleteAny: 'You can delete any item',
    addFactExample: 'For example: I love quiet mornings', addFact: 'Add fact', archiveTitle: 'Your archive', archiveUsed: 'used in new responses', archiveHidden: 'saved and hidden from Oracle',
    allReadingsTitle: 'All readings', readingsNone: 'No readings yet', firstCard: 'Draw your first card 🎴',
    fullChartTitle: '🌌 Full natal chart', chartPrecision: 'Chart precision', chartNoTimeShort: 'Birth time is not set.', chartPrecisionCopy: 'Planets and aspects are calculated from the date. ASC, MC and houses are hidden without a birth time.', provenanceTitle: 'Calculation source', provenanceSummary: 'Technical details', provenanceProduct: 'Product engine', provenanceBackend: 'Backend', provenanceVersion: 'Adapter version', provenanceEphemeris: 'Ephemeris', provenanceLicense: 'License notice', provenanceLicenseCopy: 'The backend is covered by AGPL-3.0 or a commercial license under the selected distribution model.', provenanceUnavailable: 'Calculation source not provided', provenanceFallback: 'Source details are unavailable for this saved chart.',
 house: 'house', orb: 'orb',
    signAndRise: 'Your sign and rising', solarFoundation: 'Your solar foundation', sun: 'Sun', signRiseCopy: 'your essence, will and energy.', ascendantCopy: 'how others see you.', mcCopy: 'direction and purpose.', noTimeAssumptions: 'Birth time is not set, so we do not make assumptions about the ascendant or MC.',
    planets: 'Planets', nodes: 'Nodes and points', rahu: 'Purpose in this life (Rahu — north node)', ketu: 'Karmic background (Ketu — south node)', lilith: 'Lilith · dark moon', lilithCopy: 'A space of subconscious desires, shadow, passion and hidden strength.',
    aspects: 'Aspects (up to 8)', aspectsCopy: 'Key angles between planets — how they relate to one another.', conjunction: 'conjunction', sextile: 'sextile', trine: 'trine', square: 'square', opposition: 'opposition', houses: 'Houses',
    askAstrologer: 'Ask the Astrologer about my chart', shareChart: '📸 Save chart to story', simpleReading: '🧠 Explain in simple words', chartUnavailable: 'Chart is temporarily unavailable', chartUnavailableCopy: 'Check your connection and try opening it again a little later.', close: 'Close', chartReading: 'Chart reading', chartReadingUnavailable: 'Meaning has not unfolded yet', chartReadingUnavailableCopy: 'Try again a little later — your chart is still here.',
    saveGenderFailed: 'Could not save gender', closeAria: 'Close', changeLanguageFailed: 'Could not change language', notifications: 'Notifications', today: 'Today', morningForecast: 'Morning forecast in the bot', on: 'on', off: 'off', notificationCopy: 'Reminders and forecasts arrive in the Telegram bot. You can enable them there.', quiet: 'Quiet for now', quietCopy: 'A new sign of the day or an important reminder will wait for you here.',
    memoryCount: '{count} entries · tap to view and edit', memoryEmpty: 'Nothing here yet — tap to add your first entry',
    account: 'Account', deleteAccount: 'Delete account', deleteAccountCopy: 'This cannot be undone: personal data and materials will be anonymized. Payment records required by law may remain without a link to your profile.', deleteAccountConfirm: 'Delete your account and anonymize personal data? This cannot be undone.', deleteAccountDone: 'Account deleted', deleteAccountDoneCopy: 'Your personal data has been anonymized. Contact support if you need to clarify retained payment or legal records.', deleteAccountFailed: 'The deletion could not be completed. Check your connection and try again.',
  },
};
const profileT = (key, fallback = '') => (PROFILE_I18N[oracleLang()] || PROFILE_I18N.ru)[key] || fallback || key;
const profileFormat = (key, values = {}) => Object.entries(values).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), profileT(key));

const HOME_I18N = {
  ru: {
    ritualLabel: 'Твой мягкий ритуал дня', ritualCta: 'Открыть разговор', welcomeKicker: 'СЕГОДНЯ — БЕЗ СПЕШКИ', welcomeTitle: 'Начни с того, что уже звучит внутри.', welcomeCopy: 'Один вопрос. Один бережный шаг. Остальное можно оставить на потом.', welcomePrompt: 'С чего хочется начать?', seasonalAria: 'Сезонный ритуал', seasonalKicker: 'Сезонный знак',
    rhythmAria: 'Твой ритм на сегодня', rhythmKicker: 'Твой ритм', rhythmTitle: 'Вернуться к себе', stepsAria: '{count} из 2 бережных шагов',
    diaryDoneAria: 'Дневник заполнен, открыть записи', diaryOpenAria: 'Открыть дневник состояния', diaryDone: 'Дневник уже заполнен', diaryOpen: 'Отметить своё состояние',
    diaryDoneCopy: 'Дневник уже ждёт тебя в личной библиотеке.', diaryPromptFallback: 'Одно честное предложение о том, как ты сейчас.',
    practiceDoneAria: 'Отметить шаг практики', practiceStartAria: 'Начать практику', practiceStepFallback: 'Отметить маленький шаг', practiceFallback: 'Мягкая практика на сегодня',
    ritualNote: 'Без штрафов за пропуски. Это не чек-лист «идеальной жизни», а две мягкие точки опоры для тебя.',
    week: 'Вся неделя', today: 'сегодня', lunarDay: '{day}-й лунный день', moonTitle: '🌙 Лунный календарь', moonWeek: 'Неделя',
    personal: 'Только для тебя', todaySign: 'Знак на сегодня', forecastFallbackTitle: 'Начни с того, что уже чувствуешь.', forecastFallbackCopy: 'Открой личный знак дня или задай Оракулу вопрос — это тоже хороший способ вернуться к себе.',
    daySymbol: 'Символ дня', cardNearby: 'Карта, которая рядом', cardCopy: 'Носи эту энергию сегодня — карта дня задаёт тон всему: от решений до встреч.', cardHint: 'Тапни карту — она развернётся со смыслом ↻',
    nextKicker: 'Один бережный шаг', nextTitle: 'Продолжить ритуал', chooseMood: 'Выбери настроение', talkTo: 'С кем поговорим?',
    guidesTitle: 'Твои проводники', guidesCopy: 'Не нужно знать «правильный» вопрос. Выбери того, с кем хочется побыть сегодня — он поможет разложить мысли по местам.',
    listening: 'Готов слушать тебя', nearby: 'рядом для тебя', start: 'Начать', openChatAria: 'Открыть диалог с {name}', ask: 'Можно спросить', evidenceFirst: 'Факты → интерпретация', toolCount: '{count} инструментов', profileQuality: 'Специализированный профиль',
    ritualOneDone: 'Одна опора уже есть. Второй шаг — только если захочется.', ritualNoneDone: 'Выбери одну маленькую точку опоры. Этого достаточно.',
    seasonal: [['Зимний свет', 'Разреши себе меньше спешки и больше тёплых пауз.'], ['Время расцветать', 'Выбери один маленький шаг, который хочется начать для себя.'], ['Сезон полноты', 'Заметь, что уже стало твоей опорой, и поблагодари себя.'], ['Время бережно отпустить', 'Освободи место для того, что действительно важно сейчас.']],
  },
  en: {
    ritualLabel: 'Your gentle daily ritual', ritualCta: 'Open the conversation', welcomeKicker: 'TODAY — WITHOUT RUSH', welcomeTitle: 'Start with what is already alive inside.', welcomeCopy: 'One question. One gentle step. The rest can wait.', welcomePrompt: 'What would you like to begin with?', seasonalAria: 'Seasonal ritual', seasonalKicker: 'Seasonal sign',
    rhythmAria: 'Your rhythm for today', rhythmKicker: 'Your rhythm', rhythmTitle: 'Return to yourself', stepsAria: '{count} of 2 gentle steps',
    diaryDoneAria: 'Diary completed, open entries', diaryOpenAria: 'Open mood diary', diaryDone: 'Diary completed', diaryOpen: 'Check in with yourself',
    diaryDoneCopy: 'Your entry is waiting in your private library.', diaryPromptFallback: 'One honest sentence about how you are right now.',
    practiceDoneAria: 'Mark this practice step', practiceStartAria: 'Start practice', practiceStepFallback: 'Mark one small step', practiceFallback: 'A gentle practice for today',
    ritualNote: 'No penalties for skipping. This is not an “ideal life” checklist — just two gentle anchors for your day.',
    week: 'Full week', today: 'today', lunarDay: 'lunar day {day}', moonTitle: '🌙 Moon calendar', moonWeek: 'Week',
    personal: 'Just for you', todaySign: 'Today’s sign', forecastFallbackTitle: 'Begin with what you already feel.', forecastFallbackCopy: 'Open your personal sign for today or ask the Oracle a question — both are gentle ways to return to yourself.',
    daySymbol: 'Symbol of the day', cardNearby: 'A card by your side', cardCopy: 'Carry this energy through the day — this card sets a tone for choices and encounters.', cardHint: 'Tap the card to reveal its meaning ↻',
    nextKicker: 'One gentle step', nextTitle: 'Continue your ritual', chooseMood: 'Choose a mood', talkTo: 'Who would you like to talk to?',
    guidesTitle: 'Your guides', guidesCopy: 'You do not need the “right” question. Choose the voice you want to spend time with today — it will help you sort through your thoughts.',
    listening: 'Ready to listen', nearby: 'here for you', start: 'Start', openChatAria: 'Open chat with {name}', ask: 'You can ask', evidenceFirst: 'Evidence → reflection', toolCount: '{count} tools', profileQuality: 'Specialist profile',
    ritualOneDone: 'One anchor is already here. Take the second step only if you want to.', ritualNoneDone: 'Choose one small anchor. That is enough.',
    seasonal: [['Winter light', 'Give yourself permission to hurry less and take warmer pauses.'], ['A time to bloom', 'Choose one small step you would like to begin for yourself.'], ['A season of fullness', 'Notice what has already become your anchor and thank yourself for it.'], ['A time to gently let go', 'Make room for what truly matters now.']],
  },
};
const homeT = (key, fallback = '') => (HOME_I18N[oracleLang()] || HOME_I18N.ru)[key] || fallback || key;
const homeFormat = (key, values = {}) => Object.entries(values).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), homeT(key));

// P3: детерминированный вариант без сторонних трекеров. В событие уходят только
// имя эксперимента и вариант; вопрос, дневник и другие личные данные не передаются.
function experimentVariant(experiment, variants = ['control', 'variant']) {
  const subject = String((window.app && app.me && app.me.tg_id) || 'anonymous');
  let hash = 2166136261;
  for (const char of `${experiment}:${subject}`) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return variants[(hash >>> 0) % variants.length];
}
function trackExperiment(experiment, variant) {
  const key = `oracle_exp:${experiment}:${variant}`;
  if (sessionStorage.getItem(key)) return;
  sessionStorage.setItem(key, '1');
  api('/api/experiment-exposure', { method: 'POST', body: JSON.stringify({ experiment, variant }) }).catch(() => {});
}

const fmtDate = () => new Date().toLocaleDateString(oracleLang() === 'en' ? 'en-US' : 'ru-RU',
  { weekday: 'long', day: 'numeric', month: 'long' });

const fmtDay = iso => {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(oracleLang() === 'en' ? 'en-US' : 'ru-RU', { day: 'numeric', month: 'short' });
};

// арабский номер аркана → римская цифра (для «настоящей» карты)
function toRoman(n) {
  let v = parseInt(n, 10);
  if (!isFinite(v) || v < 0) return String(n || '');
  const map = [[1000,'M'],[900,'CM'],[500,'D'],[400,'CD'],[100,'C'],[90,'XC'],[50,'L'],[40,'XL'],[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']];
  let out = '';
  for (const [num, sym] of map) { while (v >= num) { out += sym; v -= num; } }
  return out || '0';
}

