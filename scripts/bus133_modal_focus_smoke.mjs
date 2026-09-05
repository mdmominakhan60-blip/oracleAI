// BUS-133: smoke-проверка showModal/closeModal/trapTabKey на минимальном DOM-стабе (без jsdom).
'use strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';

class FakeNode {
  constructor(tag, attrs = {}) {
    this.tagName = (tag || 'div').toUpperCase();
    this.children = []; this.parentNode = null;
    this.attrs = { ...attrs };
    this._listeners = {};
    this._id = attrs.id || '';
    this._innerHTML = '';
  }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(html) {
    this._innerHTML = String(html);
    this.children = parseHtml(this._innerHTML, this);
  }
  get id() { return this._id; }
  set id(v) { this._id = v; this.attrs.id = v; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
  get classList() {
    const self = this;
    const set = new Set(String(self.attrs.class || '').split(/\s+/).filter(Boolean));
    return {
      contains: c => set.has(c),
      add: c => { set.add(c); self.attrs.class = [...set].join(' '); },
      toggle: (c, on) => { (on === undefined ? !set.has(c) : on) ? set.add(c) : set.delete(c); self.attrs.class = [...set].join(' '); },
    };
  }
  focus() { globalThis.__doc.__active = this; }
  contains(n) { for (let x = n; x; x = x.parentNode) if (x === this) return true; return false; }
  appendChild(c) { c.parentNode = this; this.children.push(c); }
  remove() {
    if (this.parentNode) {
      const i = this.parentNode.children.indexOf(this);
      if (i >= 0) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    }
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const out = [];
    const alts = sel.split(',').map(s => s.trim());
    const walk = n => n.children.forEach(c => { if (alts.some(p => matchEl(c, p))) out.push(c); walk(c); });
    walk(this);
    return out;
  }
}

// Упрощённый HTML-парсер: только то, что рендерит showModal в тестах.
function parseHtml(html, parent) {
  const out = [];
  const stack = [{ node: parent }];
  const re = /<\/?([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[a-zA-Z-]+(?:="[^"]*")?)*)\s*\/?>|([^<]+)/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    if (m[3] !== undefined) continue; // текст игнорируем
    const closing = m[0].startsWith('</');
    const tag = m[1].toLowerCase();
    const attrs = {};
    const are = /([a-zA-Z-]+)(?:="([^"]*)")?/g;
    let am;
    while ((am = are.exec(m[2] || '')) !== null) {
      if (!am[1] || am[1] === '/') continue;
      attrs[am[1]] = am[2] === undefined ? '' : am[2];
    }
    if (closing) {
      for (let i = stack.length - 1; i > 0; i--) if (stack[i].tag === tag) { stack.length = i; break; }
      continue;
    }
    const node = new FakeNode(tag, attrs);
    node.parentNode = stack[stack.length - 1].node;
    if (stack.length === 1) out.push(node); // прямой ребёнок parent — то, что возвращает парсер
    stack[stack.length - 1].node.children.push(node);
    stack.push({ node, tag });
  }
  return out;
}

// Селекторы, реально используемые кодом миниаппа:
// 'div', '.modal', '#app-modal', '.modal > h3, .modal .picker-title',
// 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
function matchEl(el, sel) {
  // child combinator: 'A > B'
  const comb = sel.split('>').map(s => s.trim());
  if (comb.length === 2) {
    return matchSimple(el, comb[1]) && el.parentNode && matchSimple(el.parentNode, comb[0]);
  }
  // descendant: последний сегмент — сам элемент, предыдущие — предки (упрощённо: есть предок)
  const segs = sel.split(/\s+/).filter(Boolean);
  const simple = segs[segs.length - 1];
  if (!matchSimple(el, simple)) return false;
  for (let i = segs.length - 2; i >= 0; i--) {
    let anc = el.parentNode, found = false;
    while (anc) { if (matchSimple(anc, segs[i])) { found = true; break; } anc = anc.parentNode; }
    if (!found) return false;
  }
  return true;
}
function matchSimple(el, sel) {
  const m = sel.match(/^([a-zA-Z0-9-]*)(.*)$/);
  const tag = m[1];
  let rest = m[2];
  if (tag && el.tagName !== tag.toUpperCase()) return false;
  // :not([attr="val"]) и :not([attr])
  const nots = rest.match(/:not\(\[([a-z-]+)(?:="([^"]*)")?\]\)/g) || [];
  for (const n of nots) {
    const mm = n.match(/:not\(\[([a-z-]+)(?:="([^"]*)")?\]\)/);
    const v = el.attrs[mm[1]];
    if (mm[2] === undefined) { if (v !== undefined) return false; }
    else if (String(v) === mm[2]) return false;
    rest = rest.replace(n, '');
  }
  const am = rest.match(/\[([a-z-]+)(?:="([^"]*)")?\]/);
  if (am) {
    const v = el.attrs[am[1]];
    if (v === undefined) return false;
    if (am[2] !== undefined && String(v) !== am[2]) return false;
    rest = rest.replace(am[0], '');
  }
  for (const cl of rest.match(/\.[a-zA-Z0-9_-]+/g) || []) {
    if (!String(el.attrs.class || '').split(/\s+/).includes(cl.slice(1))) return false;
  }
  return true;
}

const doc = {
  __active: null,
  body: new FakeNode('body'),
  documentElement: { lang: 'ru' },
  createElement: tag => new FakeNode(tag),
  getElementById(id) {
    const walk = n => { for (const c of n.children) { if (c.id === id) return c; const r = walk(c); if (r) return r; } return null; };
    return walk(this.body);
  },
  querySelector(sel) {
    if (sel === '#app-modal .modal') {
      const ov = this.getElementById('app-modal');
      return ov ? ov.querySelector('.modal') : null;
    }
    return null;
  },
  contains: () => true,
  addEventListener: () => {},
  get activeElement() { return this.__active || this.body; },
  set activeElement(v) { this.__active = v; },
};
globalThis.__doc = doc;
globalThis.document = doc;
globalThis.window = { document: doc };

const sandbox = {
  window: globalThis.window,
  document: doc,
  console,
  setTimeout: fn => fn(),
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  navigator: { language: 'ru', userAgent: 'test' },
  fetch: () => Promise.resolve({ ok: true, json: () => ({}) }),
  requestAnimationFrame: fn => fn(),
  location: { protocol: 'https:', host: 't.me' },
};
sandbox.window.app = undefined;
vm.createContext(sandbox);

const root = process.cwd();
for (const f of ['00-runtime.js', '01-utils.js', '05-app.js', '15-actions.js', '12-misc.js']) {
  const code = fs.readFileSync(path.join(root, 'miniapp/js', f), 'utf8');
  try { vm.runInContext(code, sandbox, { filename: f }); } catch (e) { console.error('LOAD FAIL', f, e.message); process.exit(2); }
}
const app = sandbox.window.app;

let pass = 0, fail = 0;
const t = (name, fn) => { try { fn(); pass++; console.log('ok  -', name); } catch (e) { fail++; console.log('FAIL -', name, '::', e.message); } };
const assert = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };

const trigger = new FakeNode('button', { class: 'btn' });
doc.body.appendChild(trigger);
trigger.focus();

// 1) showModal: атрибуты диалога и фокус на первый интерактивный
app.showModal(`<h3>Заголовок</h3><button class="m-close" data-act="modal-close">✕</button><button class="btn" data-act="x">Да</button>`);
const ov = doc.getElementById('app-modal');
t('overlay создан', () => assert(ov));
const dlg = ov.querySelector('.modal');
t('role=dialog', () => assert(dlg.getAttribute('role') === 'dialog', 'role'));
t('aria-modal=true', () => assert(dlg.getAttribute('aria-modal') === 'true', 'aria-modal'));
t('aria-labelledby указывает на h3', () => {
  const h3 = dlg.querySelector('h3');
  assert(h3 && h3.id && dlg.getAttribute('aria-labelledby') === h3.id);
});
t('фокус на первый интерактивный (m-close)', () => assert(doc.activeElement === dlg.querySelector('.m-close')));
t('_modalTrigger === триггер', () => assert(app._modalTrigger === trigger));

// 2) trap
const first = dlg.querySelector('.m-close');
const last = dlg.querySelector('[data-act="x"]');
// Tab с последнего зацикливается на первый — это и есть trap
last.focus();
let ev = { shiftKey: false, _pd: false, preventDefault() { this._pd = true; } };
app.trapTabKey(dlg, ev);
t('Tab с последнего зациклен на первый', () => assert(doc.activeElement === first && ev._pd));

first.focus();
ev = { shiftKey: true, _pd: false, preventDefault() { this._pd = true; } };
app.trapTabKey(dlg, ev);
t('Shift+Tab с первого → последний', () => assert(doc.activeElement === last && ev._pd));

last.focus();
ev = { shiftKey: false, _pd: false, preventDefault() { this._pd = true; } };
app.trapTabKey(dlg, ev);
t('Tab с последнего → первый', () => assert(doc.activeElement === first && ev._pd));

// 3) closeModal: возврат фокуса
app.closeModal();
t('оверлей удалён', () => assert(!doc.getElementById('app-modal')));
t('фокус вернулся на триггер', () => assert(doc.activeElement === trigger));

// 4) picker-модал без h3: aria-labelledby через .picker-title
app.showModal(`<div class="picker-head"><div class="picker-title">Схемы</div></div><div class="picker-row" tabindex="0">строка</div>`, 'full');
const dlg2 = doc.getElementById('app-modal').querySelector('.modal');
t('picker: role=dialog', () => assert(dlg2.getAttribute('role') === 'dialog'));
t('picker: aria-labelledby на .picker-title', () => {
  const pt = dlg2.querySelector('.picker-title');
  assert(pt && pt.id && dlg2.getAttribute('aria-labelledby') === pt.id);
});
t('picker: фокус на .picker-row (единственный интерактив)', () => {
  assert(doc.activeElement === dlg2.querySelector('.picker-row'));
});
app.closeModal();

// 5) backdrop-клик закрывает через closeModal (фокус возвращается)
trigger.focus();
app.showModal(`<h3>T</h3><button class="btn">ok</button>`);
const ov3 = doc.getElementById('app-modal');
ov3._listeners.click.forEach(fn => fn.call(ov3, { target: ov3 }));
t('backdrop-клик закрыл модал', () => assert(!doc.getElementById('app-modal')));
t('backdrop-клик вернул фокус на триггер', () => assert(doc.activeElement === trigger));

// 6) триггер удалён из DOM — closeModal не падает
app.showModal(`<h3>T</h3><button class="btn">ok</button>`);
const gone = new FakeNode('button');
gone.focus();
app._modalTrigger = gone;
app.closeModal();
t('closeModal безопасен при удалённом триггере', () => assert(doc.activeElement && doc.activeElement !== null));

// 7) activeDialog: te-sheet
const tool = new FakeNode('div', { id: 'tool-expand', class: '' });
const sheet = new FakeNode('section', { class: 'te-sheet' });
tool.appendChild(sheet);
doc.body.appendChild(tool);
t('activeDialog: нет открытого диалога', () => assert(app.activeDialog() === null));
tool.setAttribute('class', 'open');
t('activeDialog: возвращает .te-sheet открытого tool-expand', () => assert(app.activeDialog() === sheet));
tool.remove();

// 8) модал поверх sheet: activeDialog отдаёт модал (верхний слой)
const tool2 = new FakeNode('div', { id: 'tool-expand', class: 'open' });
tool2.appendChild(new FakeNode('section', { class: 'te-sheet' }));
doc.body.appendChild(tool2);
app.showModal(`<h3>Проверка</h3><button class="btn">ok</button>`);
t('activeDialog: модал главнее sheet', () => {
  const d = app.activeDialog();
  assert(d && d.getAttribute('role') === 'dialog');
});
app.closeModal();
tool2.remove();

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
