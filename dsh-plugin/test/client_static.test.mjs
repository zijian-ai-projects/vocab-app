// Static / contract / real-handler tests for dsh-plugin/client.js (0.1.2).
//
// Runs in plain Node (no browser, no network, no third-party packages): the
// bundle is parsed exactly as the DSH Web `__ModuleLoader__` would parse it,
// the factory is called with a minimal React stub, every screen is rendered,
// and rendered onClick/onChange/onKeyDown handlers are actually invoked.

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLIENT_PATH = path.join(HERE, '..', 'client.js');
const SOURCE = fs.readFileSync(CLIENT_PATH, 'utf8');

// ---------------------------------------------------------------------------
// Minimal React implementation: createElement returns a serializable tree.
// ---------------------------------------------------------------------------
function createReactStub() {
  return {
    createElement(type, props, ...children) {
      return { type, props: props || {}, children };
    },
    useState(initial) {
      const value = typeof initial === 'function' ? initial() : initial;
      return [value, function noopSetState() {}];
    },
    useEffect() {},
    useRef(value) {
      return { current: value };
    },
    useMemo(factory) {
      return factory();
    },
  };
}

function requireStub(name) {
  if (name === 'react' || name === 'react/jsx-runtime') return createReactStub();
  throw new Error('client.js must not require anything except react: ' + name);
}

// The bundle closes over this object as its `window`; it also records listeners
// so drag/entry tests can drive pointer events like a browser would.
let bundleWindow = null;
const windowListeners = new Map();
function dispatchWindow(type, event) {
  for (const listener of Array.from(windowListeners.get(type) || [])) listener(event);
}
function loadBundle(source) {
  let loaded = null;
  windowListeners.clear();
  bundleWindow = {
    innerWidth: 1400,
    innerHeight: 900,
    addEventListener(type, listener) {
      if (!windowListeners.has(type)) windowListeners.set(type, new Set());
      windowListeners.get(type).add(listener);
    },
    removeEventListener(type, listener) {
      const set = windowListeners.get(type);
      if (set) set.delete(listener);
    },
    __ModuleLoader__: {
      load(spec) {
        loaded = spec;
      },
    },
  };
  const factory = new Function('window', 'console', source);
  factory(bundleWindow, console);
  assert.ok(loaded, 'window.__ModuleLoader__.load must be called');
  return loaded;
}

const loaded = loadBundle(SOURCE);
const module = loaded.factory(requireStub);
const testing = module.__testing;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const BASE_KEYS = {
  remember: 'Enter', forget: 'Space',
  choice1: '1', choice2: '2', choice3: '3', choice4: '4',
  unknown: 'Space', next: 'Enter',
};
const BASE_CAPTIONS = {
  remember: 'Enter', forget: '空格',
  choice1: '1', choice2: '2', choice3: '3', choice4: '4',
  unknown: '空格', next: 'Enter',
};
const WINDOW_PRESETS = [
  { key: 'mini', label: '迷你', width: 400, height: 400 },
];
// Untrusted/stale Host geometry is deliberately inconsistent with the fixed UI.
const STALE_WINDOW_PRESETS = [
  { key: 'mini', label: '旧迷你', width: 999, height: 888 },
  { key: 'small', label: '小窗', width: 520, height: 430 },
  { key: 'medium', label: '中窗', width: 700, height: 560 },
  { key: 'large', label: '大窗', width: 900, height: 700 },
];

function baseView(screen, extra) {
  return Object.assign({
    screen,
    theme: 'light',
    compact: false,
    status: '',
    keys: BASE_KEYS,
    keyCaptions: BASE_CAPTIONS,
    storageNote: '',
    windowSize: 'mini',
    windowPresets: WINDOW_PRESETS,
  }, extra || {});
}

const frontView = baseView('front', {
  studyStatus: '新词',
  studyCaption: '新词',
  word: { w: 'abandon', ipa: '/əˈbændən/', meaning: 'v. 放弃；抛弃' },
  learned: 12, total: 100, due: 3, studyMode: 'brush', revealed: false, canUndo: true,
});
const backView = baseView('back', {
  studyStatus: '复习',
  studyCaption: '复习 · 记忆等级 3',
  word: { w: 'abandon', ipa: '', meaning: 'v. 放弃；抛弃' },
  revealed: true, canCorrect: true, canUndo: true,
});
const backNoCorrectView = Object.assign({}, backView, { canCorrect: false, canUndo: false });
const emptyView = baseView('empty', {
  studyStatus: '',
  word: { w: '高考核心', ipa: '', meaning: '当前没有新词和到期词\n可在设置中查看或更换词书' },
  revealed: true, canUndo: false,
});
const choiceView = baseView('choice', {
  studyStatus: '新词',
  word: { w: 'abandon', ipa: '/əˈbændən/' },
  options: [
    { index: 0, text: '放弃；抛弃', state: '' },
    { index: 1, text: '勇敢的', state: '' },
    { index: 2, text: '快速的', state: '' },
    { index: 3, text: '安静的', state: '' },
  ],
  locked: false, studyMode: 'choice', revealed: false, canUndo: true,
});
const choiceBackView = baseView('choice_back', {
  studyStatus: '复习',
  word: { w: 'abandon', ipa: '/əˈbændən/' },
  options: [
    { index: 0, text: '放弃；抛弃', state: 'ok' },
    { index: 1, text: '勇敢的', state: 'bad' },
    { index: 2, text: '快速的', state: '' },
    { index: 3, text: '安静的', state: '' },
  ],
  locked: true, studyMode: 'choice', revealed: true, canUndo: true,
});
const choiceUnavailableView = baseView('choice', {
  studyStatus: '新词',
  word: { w: 'abandon', ipa: '/əˈbændən/', meaning: 'v. 放弃；抛弃' },
  options: [],
  unavailable: true,
  locked: true,
  studyMode: 'choice',
  revealed: false,
  canUndo: true,
});
const settingsView = baseView('settings', {
  studyMode: 'brush',
  school: 'off',
  book: { id: 'gk-1', name: '高考核心', num: 120, total: 3500, numText: '已学 120 / 3,500', path: '高考 · 高频' },
  quiz: { hasSession: true, remainingDays: 12 },
  theme: 'sepia',
  version: '0.1.2',
  windowSize: 'mini',
});
const quizView = baseView('quiz', {
  status: '词汇测试 · 已答 12 / 最多80',
  index: 12, total: 40,
  word: { w: 'brave' },
  options: [
    { index: 0, text: '勇敢的', state: '' },
    { index: 1, text: '懒惰的', state: '' },
    { index: 2, text: '聪明的', state: '' },
    { index: 3, text: '安静的', state: '' },
  ],
  locked: false, unknownPicked: false, canPause: true,
});
const quizLockedView = Object.assign({}, quizView, {
  locked: true, index: 13,
  options: quizView.options.map((option, index) => Object.assign({}, option, {
    state: index === 0 ? 'picked' : '',
  })),
});
const resultView = baseView('result', {
  estimate: 5200, interval: [4500, 5900],
  big: '≈ 5,200 词目',
  sub: '模型95%区间  4,500 – 5,900 词目',
  coverage: '已答 40 题 · 3 / 5 层至少2题 · 不认识 6 题',
  rows: [
    { label: '本地有效词目 1–1000', size: 1000, answered: 12, correct: 8, unknown: 1 },
  ],
  actions: [
    { type: 'back', payload: {}, label: '继续背单词', style: 'primary' },
    { type: 'bands', payload: {}, label: '分层详情', style: 'link' },
  ],
  chart: {
    title: '同题库、同量尺的完成测验趋势',
    points: [{ ts: 1700000000, vocab: 4200 }, { ts: 1710000000, vocab: 5200 }],
  },
  fromWelcome: false,
});
const allViews = {
  welcome: baseView('welcome', { bookCount: 52, totalWords: 41234, hasProgress: true }),
  front: frontView,
  back: backView,
  empty: emptyView,
  choice: choiceView,
  choice_back: choiceBackView,
  settings: settingsView,
  books: baseView('books', {
    rows: [
      { kind: 'main', id: 'gaokao', text: '高考' },
      { kind: 'group', id: 'gk-high', text: '高频' },
      { kind: 'book', id: 'gk-1', text: '高考核心', count: 3500 },
      { kind: 'section', text: '人教PEP版 · 3 册' },
    ],
    navLevel: 3, lead: '高频', selected: 'gk-1', order: 'seq',
    stats: { total: 3500, learned: 120 }, canStart: true,
    bookStat: '高考 · 高频 · 3,500 词',
  }),
  catalog: baseView('catalog', {
    title: '词书内容',
    book: { id: 'gk-1', name: '高考核心', path: '高考 · 高频', count: 3500 },
    categories: [
      { key: 'all', label: '全部', count: 3500 },
      { key: 'learned', label: '已学习', count: 120 },
      { key: 'unlearned', label: '待学习', count: 3380 },
    ],
    rows: [
      { key: 'abandon', caption: 'abandon', meaning: 'v. 放弃', memory: '待学习', level: 0 },
      { key: 'brave', caption: 'brave', meaning: 'adj. 勇敢的', memory: 'Lv3 · 认识', level: 3 },
    ],
    counts: { all: 3500, learned: 120, unlearned: 3380 },
    filter: 'all', query: '', sortByLevel: false, total: 2,
  }),
  history: baseView('history', {
    points: [{ ts: 1700000000, vocab: 4200 }, { ts: 1710000000, vocab: 5200 }],
    rows: [
      { index: 0, ts: 1700000000, vocab: 4200, right: 33, dontknow: 4, estimate: 4200, interval: [3800, 4600] },
      { index: 1, ts: 1710000000, vocab: 5200, right: 36, dontknow: 2, estimate: 5200, interval: [4700, 5700] },
    ],
  }),
  quiz: quizView,
  result: resultView,
  summary: baseView('summary', {
    title: '本次测试已完成',
    body: ['≈ 5,200 词目', '已答 40 题 · 答对 36 题'],
    actions: [{ type: 'settings', payload: {}, label: '知道了', style: 'primary' }],
  }),
  building: baseView('building', { percent: 42 }),
};

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------
function render(view, api) {
  return testing.renderScreen(view, api);
}
function collectElements(tree, out = []) {
  if (!tree || typeof tree !== 'object') return out;
  if (Array.isArray(tree)) {
    for (const child of tree) collectElements(child, out);
    return out;
  }
  out.push({ type: tree.type, props: tree.props || {}, children: tree.children });
  collectElements(tree.children || [], out);
  return out;
}
function findElement(tree, predicate) {
  return collectElements(tree).find(predicate) || null;
}
function findByAriaLabel(tree, label) {
  return findElement(tree, (element) => element.props['aria-label'] === label);
}
function fakeEvent(overrides) {
  return Object.assign({
    key: 'Enter',
    target: { value: 'ab' },
    preventDefault() {},
    stopPropagation() {},
  }, overrides || {});
}
function keyEvent(overrides) {
  return Object.assign({
    key: '', ctrlKey: false, altKey: false, shiftKey: false, metaKey: false,
    repeat: false, isComposing: false, keyCode: 0,
    target: null, preventDefault() {}, stopPropagation() {},
  }, overrides || {});
}
function createApiSpy(overrides) {
  const calls = {
    send: [], hide: 0, retry: 0, setOrder: [], startBook: 0,
    catalogQuery: [], commitCatalogQuery: 0, beginDrag: [],
  };
  const api = {
    send(type, payload) {
      calls.send.push({ type, payload: payload || {} });
      return Promise.resolve(true);
    },
    hide() { calls.hide += 1; },
    retry() { calls.retry += 1; },
    startBook() { calls.startBook += 1; },
    setOrder(order) { calls.setOrder.push(order); },
    catalogDraft: '',
    onCatalogQuery(value) { calls.catalogQuery.push(value); },
    commitCatalogQuery() { calls.commitCatalogQuery += 1; },
    pendingOrder: null,
    beginDrag(event) { calls.beginDrag.push(event); },
  };
  return { api: Object.assign(api, overrides || {}), calls };
}
function sentTypes(calls) {
  return calls.send.map((entry) => entry.type);
}
function invokeRenderedHandlers(tree, label) {
  let invoked = 0;
  for (const element of collectElements(tree)) {
    for (const prop of ['onClick', 'onChange', 'onKeyDown']) {
      const handler = element.props[prop];
      if (typeof handler !== 'function') continue;
      try {
        handler(fakeEvent());
        invoked += 1;
      } catch (error) {
        throw new Error(`${label}: ${prop} on <${String(element.type)}> threw: ${error && error.stack ? error.stack : error}`);
      }
    }
  }
  return invoked;
}

// Minimal hook runtime for these components (one instance per component type).
// Re-instantiate the bundle factory with this React implementation: a component
// from the static factory above would still close over the no-op React stub.
function mountWithHooks(componentName, props) {
  const stores = new Map();
  const pendingEffects = [];
  const seen = new Set();
  const pluginDisposers = [];
  let currentKey = null;
  let hookIndex = 0;
  let dirty = false;
  let mounted = true;
  let lateUpdates = 0;
  function useHooks(key) {
    currentKey = key;
    hookIndex = 0;
    seen.add(key);
    if (!stores.has(key)) stores.set(key, []);
  }
  function cleanupEffects(cells) {
    for (const cell of cells) {
      if (cell && typeof cell.cleanup === 'function') cell.cleanup();
      if (cell) cell.cleanup = null;
    }
  }
  const ReactRuntime = {
    createElement(type, properties, ...children) {
      return { type, props: properties || {}, children };
    },
    useState(initial) {
      const key = currentKey;
      const cells = stores.get(key);
      const index = hookIndex++;
      if (index >= cells.length) cells[index] = { value: typeof initial === 'function' ? initial() : initial };
      const cell = cells[index];
      return [cell.value, function set(next) {
        if (!mounted || stores.get(key) !== cells) { lateUpdates += 1; return; }
        const value = typeof next === 'function' ? next(cell.value) : next;
        if (Object.is(value, cell.value)) return;
        cell.value = value;
        dirty = true;
      }];
    },
    useRef(initial) {
      const cells = stores.get(currentKey);
      const index = hookIndex++;
      if (index >= cells.length) cells[index] = { value: { current: initial } };
      return cells[index].value;
    },
    useEffect(fn, deps) {
      const cells = stores.get(currentKey);
      const index = hookIndex++;
      if (index >= cells.length) cells[index] = { cleanup: null, lastDeps: null };
      const cell = cells[index];
      cell.fn = fn;
      cell.deps = deps;
      pendingEffects.push(cell);
    },
    useMemo(factory) { return factory(); },
  };
  const hookedModule = loaded.factory((name) => {
    if (name === 'react' || name === 'react/jsx-runtime') return ReactRuntime;
    throw new Error('unexpected runtime require: ' + name);
  });
  let component = hookedModule.__testing[componentName];
  if (componentName === 'VocabApp') {
    // Exercise the actual registered overlay without adding a product export.
    hookedModule.apply({
      effect(callback) {
        const dispose = callback();
        if (typeof dispose === 'function') pluginDisposers.push(dispose);
        return dispose;
      },
      slots: {
        inject(name, callback) { return callback(); },
        register(meta, overlay) { component = overlay; return function noopDispose() {}; },
      },
    });
  }
  assert.equal(typeof component, 'function', 'runtime component must come from the hooked factory');
  function renderTree(node) {
    if (!node || typeof node !== 'object') return node;
    if (Array.isArray(node)) return node.map(renderTree);
    if (typeof node.type === 'function') {
      useHooks(node.type);
      return renderTree(node.type(node.props || {}));
    }
    return { type: node.type, props: node.props || {}, children: (node.children || []).map(renderTree) };
  }
  function render() {
    assert.equal(mounted, true, 'cannot render an unmounted runtime');
    for (let attempt = 0; attempt < 20; attempt += 1) {
      pendingEffects.length = 0;
      seen.clear();
      dirty = false;
      const tree = renderTree(ReactRuntime.createElement(component, props));
      for (const [key, cells] of stores) {
        if (!seen.has(key)) { cleanupEffects(cells); stores.delete(key); }
      }
      for (const effect of pendingEffects) {
        const changed = !effect.deps || !effect.lastDeps
          || effect.deps.length !== effect.lastDeps.length
          || effect.deps.some((value, index) => value !== effect.lastDeps[index]);
        if (!changed) continue;
        if (typeof effect.cleanup === 'function') effect.cleanup();
        effect.lastDeps = effect.deps ? effect.deps.slice() : null;
        effect.cleanup = typeof effect.fn === 'function' ? effect.fn() : null;
      }
      if (!dirty) return tree;
    }
    throw new Error('runtime did not settle after its effect updates');
  }
  return {
    render,
    get dirty() { return dirty; },
    get lateUpdates() { return lateUpdates; },
    unmount() {
      if (!mounted) return;
      mounted = false;
      for (const cells of stores.values()) cleanupEffects(cells);
      stores.clear();
      for (const dispose of pluginDisposers.reverse()) dispose();
    },
  };
}
function assertListenerCount(types, count) {
  for (const type of types) assert.equal(windowListeners.get(type)?.size || 0, count, type + ' listener count');
}
function captureSpy() {
  const captured = [];
  const released = [];
  return {
    captured, released,
    node: {
      setPointerCapture(id) { captured.push(id); },
      releasePointerCapture(id) { released.push(id); },
    },
  };
}
function mockClientFetch(t, initialView, applyAction) {
  const requests = [];
  let view = initialView;
  let rev = 1;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    if (url === '/api/vocab-app/state') {
      assert.equal(options.method, 'GET');
      return { ok: true, json: async () => ({ rev, view }) };
    }
    assert.equal(url, '/api/vocab-app/action', 'never use a real network endpoint');
    assert.equal(options.method, 'POST');
    const request = JSON.parse(options.body);
    if (typeof applyAction === 'function') view = applyAction(request, view);
    else {
      throw new Error('Unexpected action in static client mock: ' + request.type);
    }
    rev += 1;
    return { ok: true, json: async () => ({ ok: true, rev, view }) };
  });
  return requests;
}
async function flushClient(runtime) {
  // Let the mocked fetch/json promise chain finish, without a wall-clock delay.
  await new Promise((resolve) => setImmediate(resolve));
  return runtime.render();
}
function mockTimeoutClock(t) {
  const pending = new Map();
  let now = 0;
  let sequence = 0;
  t.mock.method(globalThis, 'setTimeout', (callback, ms, ...args) => {
    const id = ++sequence;
    pending.set(id, { at: now + Number(ms || 0), run: () => callback(...args) });
    return id;
  });
  t.mock.method(globalThis, 'clearTimeout', (id) => { pending.delete(id); });
  return {
    get pending() { return pending.size; },
    get now() { return now; },
    get nextDelay() { return pending.size ? Math.min(...[...pending.values()].map((item) => item.at)) - now : null; },
    tick(ms) {
      const end = now + ms;
      while (true) {
        const next = Array.from(pending.entries()).filter(([, timer]) => timer.at <= end)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        pending.delete(next[0]);
        now = next[1].at;
        next[1].run();
      }
      now = end;
    },
  };
}

// User gesture only: full-panel tests must now explicitly open the startup
// entry. Never override the product's useState initializer in the hook runtime.
function openOverlay(runtime, clock) {
  const tree = runtime.render();
  const entry = findByAriaLabel(tree, '打开背单词浮层');
  assert.ok(entry, 'a fresh client starts as its floating entry');
  assert.equal(findByClass(tree, 'dsh-vocab-panel'), null);
  entry.props.onClick(fakeEvent());
  const opened = runtime.render();
  if (clock) clock.tick(0); // normal focus / already-due review wake timer
  return opened;
}

function mountOpenedOverlay(clock) {
  const runtime = mountWithHooks('VocabApp');
  openOverlay(runtime, clock);
  return runtime;
}

test('v0.1.10: startup stays minimized before and after GET until an explicit click', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = [];
  let resolveState;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    assert.equal(options.method, 'GET', 'startup and opening must not write personal state');
    return new Promise((resolve) => { resolveState = resolve; });
  });
  const runtime = mountWithHooks('VocabApp');
  try {
    let tree = runtime.render();
    assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
    assert.equal(findByClass(tree, 'dsh-vocab-panel'), null, 'no full-window flash while loading');
    resolveState({ ok: true, json: async () => ({ rev: 17, view: frontView }) });
    tree = await flushClient(runtime);
    assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
    assert.equal(findByClass(tree, 'dsh-vocab-panel'), null, 'successful state loading must not auto-open');
    for (const key of ['Enter', ' ', '1', 'Escape']) tree.props.onKeyDown(keyEvent({ key }));
    await flushClient(runtime);
    tree = openOverlay(runtime, clock);
    assert.equal(tree.props['data-screen'], 'front');
    assert.equal(findByClass(tree, 'dsh-vocab-panel').props.style.width, '400px');
    assert.equal(findByClass(tree, 'dsh-vocab-panel').props.style.height, '400px');
    findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
    tree = runtime.render();
    assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
    tree = openOverlay(runtime, clock);
    assert.equal(tree.props['data-screen'], 'front', 'reopen preserves the fetched view');
    assert.equal(requests.length, 1);
    assert.equal(intervals.size, 0);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
  assert.equal(runtime.lateUpdates, 0);
  assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
});

test('v0.1.10: each remount starts minimized even after the last instance was opened', async (t) => {
  const { clock } = reviewClock(t);
  const requests = mockClientFetch(t, frontView);
  for (let mount = 0; mount < 2; mount += 1) {
    const runtime = mountWithHooks('VocabApp');
    try {
      runtime.render(); const tree = await flushClient(runtime);
      assert.equal(findByClass(tree, 'dsh-vocab-panel'), null);
      assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
      assert.ok(findByClass(openOverlay(runtime, clock), 'dsh-vocab-panel'));
    } finally { runtime.unmount(); }
    assert.equal(runtime.lateUpdates, 0);
  }
  assert.equal(requests.length, 2);
  assert.equal(actionRequests(requests).length, 0);
  assert.equal(clock.pending, 0);
});

test('v0.1.10: a due review stays idle until the startup icon is opened', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = mockClientFetch(t, atEmpty(1700000002), () => frontView);
  const runtime = mountWithHooks('VocabApp');
  try {
    runtime.render(); await flushClient(runtime);
    clock.tick(60000); let tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0);
    assert.equal(clock.pending, 0);
    assert.equal(intervals.size, 0, 'hidden startup has no review polling');
    assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
    openOverlay(runtime, clock); tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 1);
    assert.equal(actionRequests(requests)[0].type, 'next');
    assert.equal(tree.props['data-screen'], 'front');
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
  assert.equal(intervals.size, 0);
});

test('v0.1.10: a locked quiz never auto-advances behind the startup icon or a closing panel', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = mockClientFetch(t, quizLockedView, (request) => {
    assert.equal(request.type, 'next'); return quizView;
  });
  const runtime = mountWithHooks('VocabApp');
  try {
    runtime.render(); await flushClient(runtime);
    clock.tick(1000); let tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0, 'no hidden startup quiz writes');
    assert.equal(clock.pending, 0);
    tree = openOverlay(runtime, clock);
    clock.tick(349); tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0);
    findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
    clock.tick(1); // hideRef must protect even before React commits the close
    tree = await flushClient(runtime);
    assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
    assert.equal(actionRequests(requests).length, 0, 'closing cancels the in-flight display timer');
    tree = openOverlay(runtime, clock);
    clock.tick(349); await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0);
    clock.tick(1); tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 1, 'visible quiz keeps its original 350ms advance');
    assert.equal(tree.props['data-screen'], 'quiz');
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
  assert.equal(intervals.size, 0);
  assert.equal(runtime.lateUpdates, 0);
});

test('v0.1.10: a failed initial GET stays minimized and opening exposes the existing retry', async (t) => {
  const { clock } = reviewClock(t);
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.method, 'GET'); calls += 1;
    if (calls === 1) throw new Error('synthetic offline');
    return { ok: true, json: async () => ({ rev: 1, view: frontView }) };
  });
  const runtime = mountWithHooks('VocabApp');
  try {
    runtime.render(); let tree = await flushClient(runtime);
    assert.ok(findByAriaLabel(tree, '打开背单词浮层'));
    assert.equal(findByClass(tree, 'dsh-vocab-panel'), null);
    tree = openOverlay(runtime, clock);
    findByAriaLabel(tree, '重新加载背单词状态').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    assert.equal(tree.props['data-screen'], 'front');
    assert.equal(calls, 2);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
  assert.equal(runtime.lateUpdates, 0);
});

// ---------------------------------------------------------------------------
// 1. Bundle shape
// ---------------------------------------------------------------------------
test('bundle parses and registers the expected module id/factory', () => {
  assert.equal(loaded.id, 'dsh-vocab-app');
  assert.equal(typeof loaded.factory, 'function');
});
test('factory exports name/inject/apply and the pure testing surface', () => {
  assert.equal(module.name, 'vocab-app');
  assert.deepEqual(module.inject, ['slots']);
  assert.equal(typeof module.apply, 'function');
  assert.equal(typeof testing.renderScreen, 'function');
  assert.equal(typeof testing.resolveStudyKey, 'function');
  assert.equal(typeof testing.ClosedEntry, 'function');
});
test('client only requires react / react/jsx-runtime', () => {
  const requires = [];
  const pattern = /require\(\s*['"]([^'"]+)['"]\s*\)/g;
  let match;
  while ((match = pattern.exec(SOURCE)) !== null) requires.push(match[1]);
  assert.deepEqual(requires, ['react']);
});
test('apply registers the shell.overlay slot through ctx.effect', () => {
  const effects = [];
  const injects = [];
  const registers = [];
  const disposers = [];
  const ctx = {
    effect(callback, label) {
      effects.push(label);
      const disposer = callback();
      if (typeof disposer === 'function') disposers.push(disposer);
      return disposer;
    },
    slots: {
      inject(name, callback) {
        injects.push(name);
        return callback();
      },
      register(meta, component) {
        registers.push({ meta, component });
        return function disposeRegistration() {};
      },
    },
  };
  module.apply(ctx);
  assert.deepEqual(effects, ['vocab-app: styles', 'vocab-app: shell overlay']);
  assert.deepEqual(injects, ['shell.overlay']);
  assert.equal(registers.length, 1);
  assert.equal(registers[0].meta.name, 'shell.overlay');
  assert.equal(registers[0].meta.id, 'vocab-app');
  assert.equal(registers[0].meta.order, 45);
  assert.equal(typeof registers[0].component, 'function');
  assert.equal(disposers.length, 2);
});
test('0.1.1 removed the compact layout, key editor and reset UI', () => {
  for (const needle of ['localStorage', 'document.body.style', 'ResizeHandles', 'beginResize', '.va-resize', 'validateBindingDraft', 'keyEditor', '恢复与清空', '刷词紧凑布局']) {
    assert.equal(SOURCE.includes(needle), false, 'client.js must not contain ' + needle);
  }
});

// ---------------------------------------------------------------------------
// 2. Themes + rendering smoke
// ---------------------------------------------------------------------------
test('themes contain every KEY for dark/light/sepia/green', () => {
  for (const name of ['dark', 'light', 'sepia', 'green']) {
    const palette = testing.THEMES[name];
    assert.ok(palette, 'missing theme ' + name);
    for (const key of testing.THEME_KEYS) assert.match(String(palette[key]), /^#[0-9a-fA-F]{6}$/, name + '.' + key);
  }
});
test('front view renders word and answer buttons with fixed key hints', () => {
  const text = testing.collectText(render(frontView, createApiSpy().api));
  assert.ok(text.includes('abandon'));
  assert.ok(text.includes('认识'));
  assert.ok(text.includes('不认识'));
  assert.ok(text.includes('Enter'));
  assert.ok(text.includes('空格'));
  assert.equal(text.includes('放弃；抛弃'), false);
});
test('every declared screen renders without throwing', () => {
  for (const screen of testing.screenNames) {
    const view = allViews[screen];
    assert.ok(view, 'fixture missing for ' + screen);
    const text = testing.collectText(render(view, createApiSpy().api));
    assert.ok(text.trim().length > 0, screen + ' rendered no text');
  }
});
test('unknown/missing/malformed views degrade instead of crashing', () => {
  assert.ok(testing.collectText(render(baseView('nope'), createApiSpy().api)).includes('未知页面'));
  assert.ok(testing.collectText(render(null, createApiSpy().api)).includes('正在加载'));
  const broken = [
    baseView('front'),
    baseView('choice', { options: 'nope' }),
    baseView('settings', { book: 'nope', quiz: null }),
    baseView('books', { rows: [null, 42, { kind: 'book' }] }),
    baseView('catalog', { rows: [null, { meaning: 3 }], counts: null, categories: null }),
    baseView('history', { points: 'nope', rows: [null, {}] }),
    baseView('quiz', { options: [null], word: null }),
    baseView('result', { rows: 'nope', actions: [null, 42], interval: 'nope' }),
    baseView('summary', { body: null }),
    baseView('building', { percent: 'x' }),
    baseView('obsolete-screen', { lines: null }),
    baseView('welcome', {}),
  ];
  for (const view of broken) assert.doesNotThrow(() => testing.collectText(render(view, createApiSpy().api)), view.screen);
});

// ---------------------------------------------------------------------------
// 3. Header title / quiz status (no duplicated learning status)
// ---------------------------------------------------------------------------
test('learning headers use studyStatus and drop the duplicate status line', () => {
  for (const view of [frontView, backView, choiceView, choiceBackView]) {
    const headerText = testing.collectText(testing.renderHeader(view, createApiSpy().api)).replace(/\s+/g, ' ').trim();
    assert.ok(headerText.includes(view.studyStatus), view.screen + ' header must show ' + view.studyStatus);
    assert.equal(testing.renderStatusBar(view), null, view.screen + ' must not render a second status line');
  }
  const frontScreenText = testing.collectText(render(frontView, createApiSpy().api));
  assert.equal(frontScreenText.includes('新词'), false, 'front body must not repeat the header status');
});
test('quiz keeps its answer-count status bar', () => {
  const statusBar = testing.renderStatusBar(quizView);
  assert.ok(statusBar);
  assert.ok(testing.collectText(statusBar).includes('词汇测试 · 已答 12 / 最多80'));
  assert.equal(testing.collectText(testing.renderHeader(quizView, createApiSpy().api)).includes('词汇测试'), false);
});

// ---------------------------------------------------------------------------
// 4. Fixed window presets (no custom border resize)
// ---------------------------------------------------------------------------
test('window preset is fixed mini and remains the default for every legacy host view', () => {
  assert.deepEqual(testing.windowPresets({}), testing.FALLBACK_WINDOW_PRESETS);
  assert.deepEqual(testing.FALLBACK_WINDOW_PRESETS, WINDOW_PRESETS);
  assert.equal(testing.currentWindowPreset({}).key, 'mini');
  for (const legacySize of ['mini', 'small', 'medium', 'large', 'unknown', null]) {
    for (const windowPresets of [undefined, [], STALE_WINDOW_PRESETS]) {
      const staleView = { windowSize: legacySize, windowPresets };
      const before = structuredClone(staleView);
      assert.deepEqual(testing.windowPresets(staleView), WINDOW_PRESETS, String(legacySize));
      assert.deepEqual(testing.currentWindowPreset(staleView), WINDOW_PRESETS[0], String(legacySize));
      assert.deepEqual(staleView, before, 'ignoring stale Host sizes must not mutate its view');
    }
  }
});
test('fixed mini geometry is clamped into the viewport', () => {
  const mini = testing.FALLBACK_WINDOW_PRESETS[0];
  assert.deepEqual(testing.initialGeometry(), { x: 982, y: 482, w: 400, h: 400 });
  assert.deepEqual(testing.fitGeometry({ x: 100, y: 100, w: 400, h: 400 }, mini), { x: 100, y: 100, w: 400, h: 400 });
  assert.deepEqual(testing.fitGeometry({ x: 9999, y: 9999, w: 999, h: 999 }, mini), { x: 992, y: 492, w: 400, h: 400 });
  bundleWindow.innerWidth = 300;
  bundleWindow.innerHeight = 320;
  try {
    assert.deepEqual(testing.fitGeometry({ x: 0, y: 0, w: 400, h: 400 }, mini), { x: 8, y: 8, w: 284, h: 304 });
  } finally {
    bundleWindow.innerWidth = 1400;
    bundleWindow.innerHeight = 900;
  }
});
test('settings has no window-size section or windowSize action, including stale Host options', () => {
  for (const legacySize of ['mini', 'small', 'medium', 'large']) {
    const spy = createApiSpy();
    const tree = render(Object.assign({}, settingsView, {
      windowSize: legacySize, windowPresets: STALE_WINDOW_PRESETS,
    }), spy.api), text = testing.collectText(tree);
    for (const removed of ['窗口', '旧迷你', '小窗', '中窗', '大窗']) {
      assert.equal(text.includes(removed), false, legacySize + ': ' + removed);
    }
    assert.ok(invokeRenderedHandlers(tree, 'settings-without-window-' + legacySize) > 0);
    assert.equal(spy.calls.send.some((entry) => entry.type === 'windowSize'), false);
    for (const preserved of ['theme', 'studyMode', 'school', 'books', 'history', 'quizStart']) {
      assert.ok(sentTypes(spy.calls).includes(preserved), 'settings keeps ' + preserved);
    }
  }
  assert.equal(SOURCE.includes('窗口大小：'), false);
  assert.equal(SOURCE.includes('va-resize'), false);
  assert.equal(SOURCE.includes('setResizing'), false);
});

// ---------------------------------------------------------------------------
// 5. Fixed learning shortcuts
// ---------------------------------------------------------------------------
test('fixed key resolver keeps front/choice/back/choice_back semantics', () => {
  const resolve = testing.resolveStudyKey;
  assert.equal(resolve(frontView, keyEvent({ key: 'Enter' })), 'remember');
  assert.equal(resolve(frontView, keyEvent({ key: ' ' })), 'forget');
  assert.equal(resolve(choiceView, keyEvent({ key: '1' })), 'choice1');
  assert.equal(resolve(choiceView, keyEvent({ key: ' ' })), 'unknown');
  assert.equal(resolve(backView, keyEvent({ key: ' ' })), 'correct');
  assert.equal(resolve(backView, keyEvent({ key: 'Enter' })), 'next');
  assert.equal(resolve(backNoCorrectView, keyEvent({ key: ' ' })), 'next');
  assert.equal(resolve(backNoCorrectView, keyEvent({ key: 'Enter' })), 'next');
  assert.equal(resolve(choiceBackView, keyEvent({ key: ' ' })), 'next');
  assert.equal(resolve(choiceBackView, keyEvent({ key: 'Enter' })), 'next');
  assert.equal(resolve(emptyView, keyEvent({ key: ' ' })), 'next');
  assert.equal(resolve(emptyView, keyEvent({ key: 'Enter' })), 'next');
  assert.equal(resolve(backView, keyEvent({ key: 'z' })), 'correct');
  assert.equal(resolve(backView, keyEvent({ key: 'z', ctrlKey: true })), 'undo');
  assert.equal(resolve(backNoCorrectView, keyEvent({ key: 'z' })), '');
  assert.equal(resolve(quizLockedView, keyEvent({ key: 'Enter' })), 'next');
  assert.equal(resolve(choiceView, keyEvent({ key: 'Escape' })), 'escape');
});
test('fixed key resolver ignores auto-repeat and editable targets', () => {
  assert.equal(testing.resolveStudyKey(frontView, keyEvent({ key: 'Enter', repeat: true })), '');
  assert.equal(testing.resolveStudyKey(frontView, keyEvent({ key: 'Enter', isComposing: true })), '');
});

// ---------------------------------------------------------------------------
// 6. Brush back layout + choice layout rules
// ---------------------------------------------------------------------------
test('brush back keeps two equal slots and sends correct (not undo)', () => {
  const { api, calls } = createApiSpy();
  const tree = render(backView, api);
  const buttons = collectElements(tree).filter((element) => element.type === 'button' && element.props.tabIndex === -1);
  assert.equal(buttons.length, 2, 'back shows exactly two action buttons');
  assert.ok(String(buttons[0].props.className).includes('va-btn-correct'));
  assert.ok(String(buttons[1].props.className).includes('va-btn-remember'));
  const text = testing.collectText(tree);
  assert.ok(text.includes('选错了'));
  assert.ok(text.includes('下一个'));
  assert.ok(text.includes('空格'));
  assert.equal(text.includes('撤销'), false);
  buttons[0].props.onClick(fakeEvent());
  buttons[1].props.onClick(fakeEvent());
  assert.ok(sentTypes(calls).includes('correct'));
  assert.ok(sentTypes(calls).includes('next'));
  assert.equal(sentTypes(calls).includes('undo'), false);
  const labelled = createApiSpy();
  render(backView, labelled.api);
  assert.deepEqual(labelled.calls.send.map((entry) => entry.type), []);
});
test('back without correction hides correction and keeps one centred Next', () => {
  const spy = createApiSpy();
  const tree = render(backNoCorrectView, spy.api);
  const buttons = collectElements(tree).filter((element) => element.type === 'button' && element.props.tabIndex === -1);
  assert.equal(buttons.length, 1);
  assert.equal(Boolean(buttons[0].props.disabled), false);
  assert.ok(String(buttons[0].props.className).includes('va-btn-centered'));
  const text = testing.collectText(tree);
  assert.equal(text.includes('选错了'), false);
  assert.ok(text.includes('下一个'));
  assert.ok(text.includes('空格 / Enter'));
  buttons[0].props.onClick(fakeEvent());
  assert.deepEqual(spy.calls.send, [{ type: 'next', payload: {} }]);
});
test('choice_back next advertises both Space and Enter', () => {
  const text = testing.collectText(render(choiceBackView, createApiSpy().api));
  assert.ok(text.includes('空格 / Enter'));
});
test('choice renders a full-width centred IPA row and never sends flip', () => {
  const { api, calls } = createApiSpy();
  const tree = render(choiceView, api);
  const ipa = findElement(tree, (element) => String(element.props.className || '').includes('va-ipa-block'));
  assert.ok(ipa, 'choice IPA container must be a full-width block');
  assert.ok(testing.collectText(ipa).includes('/əˈbændən/'));
  const text = testing.collectText(tree);
  assert.equal(text.includes('显示释义'), false);
  invokeRenderedHandlers(tree, 'choice');
  assert.equal(sentTypes(calls).includes('flip'), false);
});
test('unavailable choice screen only offers skipping, never meaning or answers', () => {
  const { api, calls } = createApiSpy();
  const tree = render(choiceUnavailableView, api);
  const text = testing.collectText(tree).replace(/\s+/g, ' ');
  assert.ok(text.includes('当前没有可用的四选一题目，可跳过'));
  assert.ok(text.includes('下一个'));
  assert.ok(text.includes('空格 / Enter'));
  assert.equal(text.includes('放弃；抛弃'), false, 'no meaning may leak');
  assert.equal(text.includes('显示释义'), false);
  invokeRenderedHandlers(tree, 'choice-unavailable');
  assert.equal(sentTypes(calls).includes('next'), true);
  for (const forbidden of ['choice', 'dontknow', 'flip', 'answer']) {
    assert.equal(sentTypes(calls).includes(forbidden), false, 'unavailable choice must not send ' + forbidden);
  }
});
test('unavailable choice keys: Space/Enter skip, numbers do nothing', () => {
  const resolve = testing.resolveStudyKey;
  assert.equal(resolve(choiceUnavailableView, keyEvent({ key: ' ' })), 'next');
  assert.equal(resolve(choiceUnavailableView, keyEvent({ key: 'Enter' })), 'next');
  for (const key of ['1', '2', '3', '4']) {
    assert.equal(resolve(choiceUnavailableView, keyEvent({ key: key })), '', 'digit ' + key);
  }
  assert.equal(resolve(choiceUnavailableView, keyEvent({ key: 'z', ctrlKey: true })), 'undo');
  const noUndo = Object.assign({}, choiceUnavailableView, { canUndo: false });
  assert.equal(resolve(noUndo, keyEvent({ key: 'z', ctrlKey: true })), '');
});
test('host no longer sends studyCaption', () => {
  assert.equal(SOURCE.includes('studyCaption'), false);
});

// ---------------------------------------------------------------------------
// 7. Settings cleanup + preserved sections
// ---------------------------------------------------------------------------
test('settings keeps the allowed sections and drops compact/key/reset/trend text', () => {
  const text = testing.collectText(render(settingsView, createApiSpy().api));
  for (const heading of ['背景', '学习模式', '已认识词汇范围', '词书', '词汇量测试']) {
    assert.ok(text.includes(heading), 'settings must show ' + heading);
  }
  for (const removed of ['窗口', '刷词紧凑布局', '键盘按键', '恢复与清空', '恢复默认设置', '清空本插件资料', '同题库、同量尺']) {
    assert.equal(text.includes(removed), false, 'settings must not show ' + removed);
  }
  assert.ok(text.includes('已学 120 / 3,500'));
  assert.ok(text.includes('V0.1.2'));
});
test('history omits trend caption for empty, single and multiple points without removing the chart or records', () => {
  for (const points of [[], allViews.history.points.slice(0, 1), allViews.history.points]) {
    const historyTree = render(Object.assign({}, allViews.history, { points }), createApiSpy().api);
    const historyText = testing.collectText(historyTree);
    assert.equal(historyText.includes('同题库、同量尺的完成测验趋势'), false);
    const chart = findByClass(historyTree, 'va-chart-wrap');
    assert.ok(chart);
    assert.ok(findByClass(chart, 'va-chart'));
    assert.equal(findElement(chart, (element) => element.type === 'p'), null, 'caption and its spacing are not rendered');
    assert.equal(collectElements(historyTree).filter((element) => element.type === 'details').length, allViews.history.rows.length);
    assert.equal(collectElements(historyTree).filter((element) => element.props.className === 'va-hist-delete').length, allViews.history.rows.length);
    if (points.length >= 2) {
      assert.ok(findByAriaLabel(chart, '完成测验词汇量趋势折线图'), 'chart retains its accessible name');
      assert.ok(findElement(chart, (element) => element.type === 'polyline'));
      assert.equal(collectElements(chart).filter((element) => element.type === 'circle').length, points.length);
    } else {
      assert.ok(testing.collectText(chart).includes(points.length ? '只有一次有效记录，暂不画趋势' : '暂无完成测验记录'));
    }
  }
});
test('result retains its default or host-provided trend caption', () => {
  for (const title of [undefined, '同题库、同量尺的完成测验趋势', '可比较的完成测验记录']) {
    const view = Object.assign({}, resultView, { chart: Object.assign({}, resultView.chart, { title }) });
    const chart = findByClass(render(view, createApiSpy().api), 'va-chart-wrap');
    const caption = findElement(chart, (element) => element.type === 'p');
    assert.ok(caption);
    assert.equal(testing.collectText(caption).trim(), title || '同题库、同量尺的完成测验趋势');
    assert.ok(findByAriaLabel(chart, '完成测验词汇量趋势折线图'));
  }
});

// ---------------------------------------------------------------------------
// 8. Real handler invocations (the class of bug that text checks miss)
// ---------------------------------------------------------------------------
test('brush front card has no reveal control, click, keyboard role or flip dispatch', () => {
  const spy = createApiSpy(), tree = render(frontView, spy.api);
  assert.equal(findByAriaLabel(tree, '显示释义'), null);
  const card = findElement(tree, (element) => element.props.className === 'va-center');
  assert.ok(card);
  for (const prop of ['onClick', 'onKeyDown', 'role', 'tabIndex']) assert.equal(card.props[prop], undefined, prop);
  invokeRenderedHandlers(tree, 'front-card');
  assert.deepEqual(spy.calls.send, [
    { type: 'answer', payload: { action: 'forget' } },
    { type: 'answer', payload: { action: 'remember' } },
  ]);
  const stale = render(Object.assign({}, frontView, { revealed: true }), createApiSpy().api);
  assert.equal(testing.collectText(stale).includes(frontView.word.meaning), false, 'legacy revealed cannot expose front meaning');
  assert.ok(testing.collectText(render(backView, createApiSpy().api)).includes(backView.word.meaning));
});
test('every screen runs its rendered handlers without free-variable errors', () => {
  for (const screen of testing.screenNames) {
    const { api } = createApiSpy();
    const invoked = invokeRenderedHandlers(render(allViews[screen], api), screen);
    if (screen !== 'building') assert.ok(invoked > 0, screen + ' should expose handlers');
  }
});
test('front/back/empty/choice handlers dispatch contract actions', () => {
  let spy = createApiSpy();
  invokeRenderedHandlers(render(frontView, spy.api), 'front');
  assert.equal(sentTypes(spy.calls).includes('flip'), false);
  assert.ok(spy.calls.send.some((entry) => entry.type === 'answer' && entry.payload.action === 'remember'));
  assert.ok(spy.calls.send.some((entry) => entry.type === 'answer' && entry.payload.action === 'forget'));
  spy = createApiSpy();
  invokeRenderedHandlers(render(backView, spy.api), 'back');
  assert.ok(sentTypes(spy.calls).includes('correct'));
  assert.ok(sentTypes(spy.calls).includes('next'));
  spy = createApiSpy();
  invokeRenderedHandlers(render(emptyView, spy.api), 'empty');
  assert.ok(sentTypes(spy.calls).includes('next'));
  spy = createApiSpy();
  invokeRenderedHandlers(render(choiceView, spy.api), 'choice');
  assert.ok(spy.calls.send.some((entry) => entry.type === 'choice' && entry.payload.index === 0));
  assert.ok(sentTypes(spy.calls).includes('dontknow'));
  assert.equal(sentTypes(spy.calls).includes('flip'), false);
});
test('settings/books/catalog/history callbacks are wired', () => {
  let spy = createApiSpy();
  invokeRenderedHandlers(render(settingsView, spy.api), 'settings');
  for (const type of ['theme', 'studyMode', 'school', 'books', 'history', 'quizStart']) {
    assert.ok(sentTypes(spy.calls).includes(type), 'settings must dispatch ' + type);
  }
  spy = createApiSpy();
  invokeRenderedHandlers(render(allViews.books, spy.api), 'books');
  assert.ok(sentTypes(spy.calls).includes('book'));
  assert.ok(sentTypes(spy.calls).includes('catalog'));
  assert.equal(spy.calls.startBook, 1);
  assert.deepEqual(spy.calls.setOrder, ['seq', 'shuffle']);
  spy = createApiSpy();
  invokeRenderedHandlers(render(allViews.catalog, spy.api), 'catalog');
  assert.ok(sentTypes(spy.calls).includes('catalogFilter'));
  assert.equal(sentTypes(spy.calls).includes('catalogSort'), false);
  assert.deepEqual(spy.calls.catalogQuery, ['ab']);
  assert.equal(spy.calls.commitCatalogQuery, 1);
  spy = createApiSpy();
  invokeRenderedHandlers(render(allViews.history, spy.api), 'history');
  const deletes = spy.calls.send.filter((entry) => entry.type === 'deleteHistory');
  assert.deepEqual(deletes.map((entry) => entry.payload.index).sort(), [0, 1]);
});
test('quiz/result/summary/welcome/header callbacks are wired', () => {
  let spy = createApiSpy();
  invokeRenderedHandlers(render(quizView, spy.api), 'quiz');
  assert.ok(spy.calls.send.some((entry) => entry.type === 'quizAnswer' && entry.payload.index === 0));
  assert.ok(sentTypes(spy.calls).includes('quizDontknow'));
  spy = createApiSpy();
  invokeRenderedHandlers(render(quizLockedView, spy.api), 'quiz-locked');
  assert.ok(sentTypes(spy.calls).includes('next'));
  spy = createApiSpy();
  invokeRenderedHandlers(render(resultView, spy.api), 'result');
  assert.ok(sentTypes(spy.calls).includes('back'));
  assert.ok(sentTypes(spy.calls).includes('bands'));
  assert.equal(sentTypes(spy.calls).includes('method'), false);
  spy = createApiSpy();
  invokeRenderedHandlers(render(allViews.summary, spy.api), 'summary');
  assert.ok(sentTypes(spy.calls).includes('settings'));
  spy = createApiSpy();
  invokeRenderedHandlers(render(allViews.welcome, spy.api), 'welcome');
  assert.ok(sentTypes(spy.calls).includes('quizStart'));
  spy = createApiSpy();
  invokeRenderedHandlers(testing.renderHeader(frontView, spy.api), 'header-front');
  assert.ok(sentTypes(spy.calls).includes('settings'));
  assert.equal(spy.calls.hide, 1);
  spy = createApiSpy();
  invokeRenderedHandlers(testing.renderHeader(settingsView, spy.api), 'header-settings');
  assert.ok(sentTypes(spy.calls).includes('back'));
  spy = createApiSpy();
  invokeRenderedHandlers(testing.renderHeader(quizView, spy.api), 'header-quiz');
  assert.ok(sentTypes(spy.calls).includes('quizPause'));
});
test('result prediction strategies and host welcome actions are click-through', () => {
  const predictionView = Object.assign({}, resultView, {
    actions: [{
      type: 'prediction', payload: { strategy: 'estimate' },
      label: '调整预测掌握', style: 'link',
      strategies: ['conservative', 'estimate', 'optimistic'],
    }],
  });
  let spy = createApiSpy();
  invokeRenderedHandlers(render(predictionView, spy.api), 'prediction');
  const strategies = spy.calls.send.filter((entry) => entry.type === 'prediction').map((entry) => entry.payload.strategy);
  assert.deepEqual(strategies.sort(), ['conservative', 'estimate', 'optimistic']);
  const welcomeWithActions = Object.assign({}, allViews.welcome, {
    title: '先测一下词汇量？', body: '结果仅供参考。', tip: '40–80 题',
    actions: [
      { type: 'quizStart', payload: { fresh: true }, label: '测试一下', style: 'primary' },
      { type: 'books', payload: { from: 'welcome' }, label: '不测了，直接开始学', style: 'secondary' },
    ],
  });
  spy = createApiSpy();
  invokeRenderedHandlers(render(welcomeWithActions, spy.api), 'welcome-actions');
  assert.ok(sentTypes(spy.calls).includes('quizStart'));
  assert.ok(sentTypes(spy.calls).includes('books'));
});

// ---------------------------------------------------------------------------
// 9. 0.1.2 controls, layout and actual hooked overlay regressions
// ---------------------------------------------------------------------------
function hasClass(element, className) {
  return String(element && element.props && element.props.className || '').split(/\s+/).includes(className);
}
function findByClass(tree, className) {
  return findElement(tree, (element) => hasClass(element, className));
}
function directElements(tree) {
  return (tree.children || []).flat(Infinity).filter((child) => child && typeof child === 'object');
}

test('quiz unknown is the fifth option row, centred without an E label, and really dispatches', () => {
  const spy = createApiSpy(), tree = render(quizView, spy.api);
  const options = findByClass(tree, 'va-options');
  const buttons = collectElements(options).filter((element) => element.type === 'button');
  assert.equal(buttons.length, 5);
  const unknown = buttons[4];
  assert.equal(hasClass(unknown, 'va-opt'), true);
  assert.equal(hasClass(unknown, 'va-opt-unknown'), true);
  assert.equal(unknown.props.disabled, false);
  assert.equal(unknown.props['aria-pressed'], 'false');
  assert.equal(findByClass(unknown, 'va-letter'), null);
  assert.equal(testing.collectText(unknown).replace(/\s+/g, ''), '不认识[空格]');
  assert.ok(findByClass(unknown, 'va-unknown-label'));
  assert.equal(findByClass(tree, 'va-quiz-actions'), null);
  unknown.props.onClick(fakeEvent());
  assert.deepEqual(spy.calls.send, [{ type: 'quizDontknow', payload: {} }]);
});

test('locked quiz keeps the fifth row and uses only Host unknownPicked, with Next outside options', () => {
  for (const picked of [true, false, undefined, 'true']) {
    const spy = createApiSpy();
    const tree = render(Object.assign({}, quizLockedView, { unknownPicked: picked }), spy.api);
    const options = findByClass(tree, 'va-options');
    const buttons = collectElements(options).filter((element) => element.type === 'button');
    assert.equal(buttons.length, 5);
    assert.ok(buttons.every((button) => button.props.disabled === true));
    const unknown = buttons[4];
    assert.equal(hasClass(unknown, 'is-picked'), picked === true);
    assert.equal(unknown.props['aria-pressed'], picked === true ? 'true' : 'false');
    for (const button of buttons) button.props.onClick(fakeEvent());
    assert.deepEqual(spy.calls.send, [], 'disabled answer handlers cannot submit again');
    assert.equal(findByAriaLabel(options, '下一个题目'), null);
    const next = findByAriaLabel(findByClass(tree, 'va-quiz-actions'), '下一个题目');
    assert.ok(next);
    assert.equal(directElements(tree).at(-1).props.className, 'va-quiz-actions');
    next.props.onClick(fakeEvent());
    assert.deepEqual(spy.calls.send, [{ type: 'next', payload: {} }]);
  }
});

test('ABCD choice and quiz show bracketed numeric keys and preserve zero-based answer indices', () => {
  for (const view of [choiceView, choiceBackView, quizView, quizLockedView]) {
    const spy = createApiSpy(), tree = render(view, spy.api);
    const rows = collectElements(findByClass(tree, 'va-options')).filter((element) => element.type === 'button' && findByClass(element, 'va-letter'));
    assert.equal(rows.length, 4);
    rows.forEach((row, index) => {
      assert.equal(testing.collectText(findByClass(row, 'va-letter')).trim(), String.fromCharCode(65 + index));
      assert.equal(testing.collectText(findByClass(row, 'va-key')).trim(), '[' + (index + 1) + ']');
      if (!view.locked) row.props.onClick(fakeEvent());
    });
    if (!view.locked) {
      assert.deepEqual(spy.calls.send, [0, 1, 2, 3].map((index) => ({
        type: view.screen === 'quiz' ? 'quizAnswer' : 'choice', payload: { index },
      })));
    }
  }
});

test('headers put study settings on the left, remove the brand, and use centred SVG nav arrows', () => {
  for (const view of [frontView, backView, emptyView, choiceView, choiceBackView]) {
    const spy = createApiSpy(), header = testing.renderHeader(view, spy.api);
    assert.equal(findByClass(header, 'va-brand'), null);
    assert.equal(findElement(header, (element) => element.type === 'svg'), null);
    const gear = findByAriaLabel(findByClass(header, 'va-head-left'), '设置');
    assert.ok(gear);
    assert.equal(findByAriaLabel(findByClass(header, 'va-head-right'), '设置'), null);
    gear.props.onClick(fakeEvent());
    assert.deepEqual(spy.calls.send, [{ type: 'settings', payload: {} }]);
  }
  for (const screen of ['settings', 'books', 'catalog', 'history']) {
    const spy = createApiSpy(), header = testing.renderHeader(allViews[screen], spy.api);
    const back = findByClass(findByClass(header, 'va-head-left'), 'va-back');
    const svg = findElement(back, (element) => element.type === 'svg');
    assert.ok(svg, screen + ' needs a font-independent back arrow');
    assert.equal(svg.props.viewBox, '0 0 24 24');
    assert.equal(svg.props['aria-hidden'], 'true');
    back.props.onClick(fakeEvent());
    assert.deepEqual(spy.calls.send, [{ type: 'back', payload: {} }]);
  }
  const entry = testing.ClosedEntry({ onOpen() {} });
  assert.equal(findElement(entry, (element) => element.type === 'svg').props.width, 24, 'closed entry retains its branded SVG');
});

test('books lead/list/stats/bottom toolbar are separate and both right controls are 36px', () => {
  const spy = createApiSpy(), tree = render(allViews.books, spy.api);
  const children = directElements(tree);
  assert.deepEqual(children.map((child) => child.props.className), [
    'va-lead va-books-lead', 'va-scroll va-books-list', 'va-muted va-books-stats', 'va-books-toolbar',
  ]);
  const list = findByClass(tree, 'va-books-list');
  assert.equal(findByClass(list, 'va-books-lead'), null);
  assert.equal(findByClass(list, 'va-books-stats'), null);
  assert.equal(findByClass(list, 'va-books-toolbar'), null);
  assert.ok(testing.collectText(findByClass(tree, 'va-books-stats')).includes('3,500'));
  const toolbar = findByClass(tree, 'va-books-toolbar');
  assert.deepEqual(directElements(toolbar).map((child) => child.props.className), ['va-books-order', 'va-books-spacer', 'va-books-actions']);
  for (const label of ['浏览当前词书内容', '用这本书开始学习']) {
    const button = findByAriaLabel(findByClass(toolbar, 'va-books-actions'), label);
    assert.equal(button.props.style.height, '36px');
    assert.equal(button.props.style.minHeight, '36px');
    assert.equal(button.props.style.minWidth, 0);
    button.props.onClick(fakeEvent());
  }
  assert.deepEqual(spy.calls.send, [{ type: 'catalog', payload: {} }]);
  assert.equal(spy.calls.startBook, 1);
  for (const label of ['词序：顺序', '词序：乱序']) findByAriaLabel(toolbar, label).props.onClick(fakeEvent());
  assert.deepEqual(spy.calls.setOrder, ['seq', 'shuffle']);
  const fallback = createApiSpy({ setOrder: undefined, startBook: undefined });
  const fallbackTree = render(allViews.books, fallback.api);
  findByAriaLabel(fallbackTree, '词序：乱序').props.onClick(fakeEvent());
  findByAriaLabel(fallbackTree, '用这本书开始学习').props.onClick(fakeEvent());
  assert.deepEqual(fallback.calls.send, [{ type: 'book', payload: { order: 'shuffle' } }, { type: 'start', payload: {} }]);
  const noSelection = render(Object.assign({}, allViews.books, { selected: '' }), createApiSpy().api);
  for (const label of ['浏览当前词书内容', '用这本书开始学习']) assert.equal(findByAriaLabel(noSelection, label).props.disabled, true);
});

test('catalog real overlay retains grade/filter/search/virtualization without count or sorting UI', async (t) => {
  const clock = mockTimeoutClock(t);
  const requests = mockClientFetch(t, Object.assign({}, allViews.catalog, { sortByLevel: true }), (request, view) => {
    assert.equal(request.type, 'catalogFilter');
    return Object.assign({}, view, { filter: request.payload.category, query: request.payload.query });
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render();
    let tree = await flushClient(runtime);
    assert.ok(testing.collectText(tree).includes('Lv3 · 认识'));
    assert.ok(findByClass(tree, 'va-vlist'));
    assert.equal(/共\s*\d+\s*条/.test(testing.collectText(tree)), false);
    assert.equal(findByAriaLabel(tree, '按记忆等级排序'), null);
    let input = findByAriaLabel(tree, '搜索单词、词组或释义');
    input.props.onChange(fakeEvent({ target: { value: 'br' } }));
    tree = runtime.render();
    input = findByAriaLabel(tree, '搜索单词、词组或释义');
    assert.equal(input.props.value, 'br');
    input.props.onKeyDown(keyEvent({ key: 'Enter' }));
    tree = await flushClient(runtime);
    const filters = collectElements(tree).filter((element) => element.type === 'button' && hasClass(element, 'va-chip'));
    assert.equal(filters.length, 3);
    filters[1].props.onClick(fakeEvent());
    await flushClient(runtime);
    const posts = requests.filter((request) => request.url.endsWith('/action')).map((request) => JSON.parse(request.options.body));
    assert.deepEqual(posts.map(({ type, payload }) => ({ type, payload })), [
      { type: 'catalogFilter', payload: { category: 'all', query: 'br' } },
      { type: 'catalogFilter', payload: { category: 'learned', query: 'br' } },
    ]);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
  assert.equal(runtime.lateUpdates, 0);
});

test('settings school section has no footnote and footer always uses the Host version', () => {
  for (const version of ['0.1.2', '9.8.7-host']) {
    const spy = createApiSpy(), tree = render(Object.assign({}, settingsView, { version }), spy.api);
    const school = findElement(tree, (element) => element.type === 'section' && element.props.key === 'school');
    assert.ok(school);
    assert.equal(findElement(school, (element) => element.type === 'p'), null);
    const schoolButtons = collectElements(school).filter((element) => element.type === 'button');
    assert.equal(schoolButtons.length, 4);
    for (const button of schoolButtons) button.props.onClick(fakeEvent());
    assert.ok(spy.calls.send.every((request) => request.type === 'school'));
    assert.ok(testing.collectText(tree).includes('V' + version));
    assert.equal(testing.collectText(tree).includes('以小学／中考／高考大纲'), false);
    assert.equal(findByAriaLabel(tree, '测评说明'), null);
  }
});

test('retired method/flip descriptors cannot reintroduce entry points while bands/settings remain valid', () => {
  const valid = ['back', 'books', 'quizStart', 'prediction', 'bands', 'settings'];
  const actions = valid.map((type) => ({ type, label: '合法:' + type, payload: type === 'prediction' ? { strategy: 'estimate' } : {} }));
  actions.push({ type: 'method', label: '旧评测入口' }, { action: 'method', label: '旧评测别名' }, { type: 'flip', label: '旧翻卡入口' });
  const spy = createApiSpy(), tree = render(Object.assign({}, resultView, { actions }), spy.api);
  for (const label of ['旧评测入口', '旧评测别名', '旧翻卡入口']) assert.equal(findByAriaLabel(tree, label), null);
  for (const type of valid) findByAriaLabel(tree, '合法:' + type).props.onClick(fakeEvent());
  assert.deepEqual(sentTypes(spy.calls), valid);
  assert.equal(testing.screenNames.includes('method'), false);
  assert.equal(Object.hasOwn(testing, 'screenMethod'), false);
  for (const fragment of ['screenMethod', 'va-method', "case 'method'", "send('method'", "send('flip'", 'va-reveal', 'va-clickable', 'canReveal', 'view.revealed', 'catalogSort', 'sort-level']) {
    assert.equal(SOURCE.includes(fragment), false, 'retired implementation: ' + fragment);
  }
});

test('real quiz overlay posts numeric/unknown intents and re-renders the fifth Host-picked row', async (t) => {
  const clock = mockTimeoutClock(t);
  const requests = mockClientFetch(t, quizView, (request, view) => {
    if (request.type === 'next') return Object.assign({}, quizView, { index: view.index });
    assert.ok(['quizAnswer', 'quizDontknow'].includes(request.type));
    return Object.assign({}, view, {
      index: view.index + 1, locked: true, unknownPicked: request.type === 'quizDontknow',
      options: quizView.options.map((option, index) => Object.assign({}, option, {
        state: request.type === 'quizAnswer' && index === request.payload.index ? 'picked' : '',
      })),
    });
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render();
    let tree = await flushClient(runtime);
    tree.props.onKeyDown(keyEvent({ key: '3' }));
    tree = await flushClient(runtime);
    assert.equal(findByClass(tree, 'va-opt-unknown').props['aria-pressed'], 'false');
    findByAriaLabel(tree, '下一个题目').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    findByClass(tree, 'va-opt-unknown').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    assert.equal(findByClass(tree, 'va-opt-unknown').props['aria-pressed'], 'true');
    assert.equal(findByClass(tree, 'va-opt-unknown').props.disabled, true);
    findByAriaLabel(tree, '下一个题目').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    tree.props.onKeyDown(keyEvent({ key: ' ' }));
    tree = await flushClient(runtime);
    assert.equal(findByClass(tree, 'va-opt-unknown').props['aria-pressed'], 'true');
    const posts = requests.filter((request) => request.url.endsWith('/action')).map((request) => JSON.parse(request.options.body));
    assert.deepEqual(posts.map(({ type, payload }) => ({ type, payload })), [
      { type: 'quizAnswer', payload: { index: 2 } }, { type: 'next', payload: {} },
      { type: 'quizDontknow', payload: {} }, { type: 'next', payload: {} }, { type: 'quizDontknow', payload: {} },
    ]);
    assert.deepEqual(posts.map((request) => request.rev), [1, 2, 3, 4, 5]);
  } finally { runtime.unmount(); }
  clock.tick(1000);
  assert.equal(clock.pending, 0);
  assert.equal(runtime.lateUpdates, 0);
});

test('all declared screens mount the mini overlay without dropping controls or scroll regions', async (t) => {
  const clock = mockTimeoutClock(t);
  for (const screen of testing.screenNames) {
    mockClientFetch(t, Object.assign({}, allViews[screen], { windowSize: 'mini' }));
    const runtime = mountOpenedOverlay(clock);
    try {
      runtime.render();
      const tree = await flushClient(runtime), panel = findElement(tree, (element) => element.type === 'section');
      assert.equal(panel.props.style.width, '400px', screen);
      assert.equal(panel.props.style.height, '400px', screen);
      assert.equal(hasClass(panel, 'va-mini'), true, screen);
      assert.ok(findByClass(tree, 'va-body'));
      if (['settings', 'books', 'history'].includes(screen)) assert.ok(findByClass(tree, 'va-scroll'), screen);
      if (screen === 'result') assert.ok(findByClass(tree, 'va-result'), screen);
      if (['choice', 'choice_back', 'quiz'].includes(screen)) assert.ok(findByClass(tree, 'va-options'), screen);
      if (screen === 'books') {
        assert.ok(findByAriaLabel(tree, '词序：顺序'));
        assert.ok(findByAriaLabel(tree, '词序：乱序'));
        assert.ok(findByAriaLabel(tree, '浏览当前词书内容'));
        assert.ok(findByAriaLabel(tree, '用这本书开始学习'));
      }
      if (screen === 'catalog') assert.ok(findByClass(tree, 'va-vlist'));
      if (screen === 'quiz') assert.ok(findByClass(tree, 'va-opt-unknown'));
    } finally { runtime.unmount(); }
    assert.equal(runtime.lateUpdates, 0, screen);
    assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
  }
  assert.equal(clock.pending, 0);
});

test('registered overlays ignore every stale Host size and preset list', async (t) => {
  const clock = mockTimeoutClock(t);
  for (const legacySize of ['mini', 'small', 'medium', 'large', 'unknown']) {
    for (const screen of ['front', 'settings', 'books', 'quiz']) {
      const label = screen + '/' + legacySize;
      const staleView = Object.assign({}, allViews[screen], {
        windowSize: legacySize, windowPresets: STALE_WINDOW_PRESETS,
      });
      const before = structuredClone(staleView);
      const requests = mockClientFetch(t, staleView);
      const runtime = mountOpenedOverlay(clock);
      try {
        runtime.render();
        const tree = await flushClient(runtime);
        const panel = findElement(tree, (element) => element.type === 'section');
        assert.equal(panel.props.style.width, '400px', label);
        assert.equal(panel.props.style.height, '400px', label);
        assert.equal(hasClass(panel, 'va-mini'), true, label);
        if (screen === 'settings') {
          assert.equal(testing.collectText(tree).includes('窗口'), false, label);
          for (const preset of STALE_WINDOW_PRESETS) {
            assert.equal(testing.collectText(tree).includes(preset.label), false, label + ': ' + preset.label);
          }
        }
        assert.deepEqual(staleView, before, 'rendering must not normalize the Host response in place');
        assert.equal(requests.length, 1, label + ': no window update or migration POST');
        assert.equal(requests[0].options.method, 'GET', label);
      } finally { runtime.unmount(); }
      assert.equal(runtime.lateUpdates, 0, label);
      assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
    }
  }
  assert.equal(clock.pending, 0);
});

test('four themed real overlays bind border/background variables and inject the non-masking control CSS', async (t) => {
  const previousDocument = globalThis.document;
  const tags = [];
  const head = {
    appendChild(tag) { tag.parentNode = head; tags.push(tag); },
    removeChild(tag) {
      const index = tags.indexOf(tag);
      if (index >= 0) tags.splice(index, 1);
      tag.parentNode = null;
    },
  };
  globalThis.document = {
    head,
    createElement(tagName) { return { tagName, id: '', textContent: '', parentNode: null, setAttribute() {} }; },
    getElementById(id) { return tags.find((tag) => tag.id === id) || null; },
  };
  try {
    for (const theme of ['dark', 'light', 'sepia', 'green']) {
      mockClientFetch(t, Object.assign({}, frontView, { theme }));
      const runtime = mountOpenedOverlay();
      try {
        runtime.render();
        const tree = await flushClient(runtime);
        assert.equal(tree.props.style['--va-border'], testing.THEMES[theme].border);
        assert.equal(tree.props.style['--va-rem-bg'], testing.THEMES[theme].rem_bg);
        assert.equal(tree.props.style['--va-fgt-bg'], testing.THEMES[theme].fgt_bg);
        const css = globalThis.document.getElementById('dsh-vocab-app:styles').textContent;
        assert.ok(css.includes('.dsh-vocab-root :where(button){'));
        assert.equal(css.includes('.dsh-vocab-root button{'), false, 'reset must not outrank control classes');
        assert.ok(css.includes('.va-btn{flex:1;min-width:0;border:1px solid var(--va-border);'));
        assert.equal(css.includes('border:1px solid transparent'), false);
        assert.equal(css.includes('border:2px solid var(--va-chip-sel-fg)'), false);
        assert.ok(css.includes('.va-opt-unknown.is-picked{background:var(--va-dk-pick);'));
        assert.ok(css.includes('.va-mini .va-thead,.va-mini .va-tr'));
        assert.ok(/\.va-result\{[^}]*overflow:auto;/.test(css), 'result itself is its scroll container');
        assert.ok(css.includes('.va-iconbtn{border:1px solid var(--va-border);width:28px;height:28px;'));
        assert.ok(css.includes('.va-linkbtn{border:1px solid var(--va-border);'));
        assert.ok(css.includes('.va-errorbar button{border:1px solid var(--va-border);'));
        assert.ok(css.includes('.va-building .va-progress-fill{transition:width .26s linear;}'));
        assert.ok(css.includes('@media (prefers-reduced-motion:reduce){.va-building .va-progress-fill{transition:none;}}'));
        assert.equal(css.includes('va-build-pending'), false, 'loading grows from the left, never bounces or loops');
      } finally { runtime.unmount(); }
      assert.equal(tags.length, 0, 'theme overlay disposes its injected style');
    }
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

// ---------------------------------------------------------------------------
// 10. In-page header drag (memory only)
// ---------------------------------------------------------------------------
test('title drag geometry keeps mini dimensions and stays inside the viewport', () => {
  const mini = { x: 800, y: 400, w: 400, h: 400 };
  assert.deepEqual(testing.movedGeometry(mini, 10, 20), { x: 810, y: 420, w: 400, h: 400 });
  assert.deepEqual(testing.movedGeometry(mini, 9999, 9999), { x: 992, y: 492, w: 400, h: 400 });
  assert.deepEqual(testing.movedGeometry(mini, -9999, -9999), { x: 8, y: 8, w: 400, h: 400 });
  // The pure helper still preserves a supplied fitted size; the overlay chooses mini.
  assert.deepEqual(testing.movedGeometry({ x: 800, y: 400, w: 520, h: 430 }, 10, 20), { x: 810, y: 420, w: 520, h: 430 });
  assert.deepEqual(testing.movedGeometry({ x: 800, y: 400, w: 520, h: 430 }, 9999, 9999), { x: 872, y: 462, w: 520, h: 430 });
  assert.deepEqual(testing.movedGeometry({ x: 800, y: 400, w: 520, h: 430 }, -9999, -9999), { x: 8, y: 8, w: 520, h: 430 });
  bundleWindow.innerWidth = 300;
  bundleWindow.innerHeight = 320;
  try {
    assert.deepEqual(testing.movedGeometry(mini, 9999, 9999), { x: 8, y: 8, w: 284, h: 304 });
    assert.deepEqual(testing.movedGeometry(mini, -9999, -9999), { x: 8, y: 8, w: 284, h: 304 });
  } finally {
    bundleWindow.innerWidth = 1400;
    bundleWindow.innerHeight = 900;
  }
});
test('header drag starts only on blank/text and forwards to beginDrag', () => {
  assert.equal(testing.shouldStartPanelDrag({ button: 0, target: { tagName: 'span', closest() { return null; } } }), true);
  assert.equal(testing.shouldStartPanelDrag({ button: 2, target: { tagName: 'span', closest() { return null; } } }), false);
  assert.equal(testing.shouldStartPanelDrag({ button: 0, target: { tagName: 'span', closest() { return { tagName: 'BUTTON' }; } } }), false);
  assert.equal(testing.shouldStartPanelDrag({ button: 0, target: { tagName: 'INPUT', closest() { return null; } } }), false);
  const { api, calls } = createApiSpy();
  const header = findElement(testing.renderHeader(frontView, api), (element) => element.type === 'header');
  assert.ok(header);
  assert.equal(typeof header.props.onPointerDown, 'function');
  header.props.onPointerDown(fakeEvent({ button: 0, target: { tagName: 'span', closest() { return null; } } }));
  assert.equal(calls.beginDrag.length, 1);
});

for (const collapsed of [false, true]) for (const side of ['default', 'left', 'right']) {
  test(`host resize restores relative placement without drift: ${collapsed ? 'entry' : 'panel'}, ${side}`, async (t) => {
    const clock = mockTimeoutClock(t);
    const requests = mockClientFetch(t, frontView);
    const original = { width: bundleWindow.innerWidth, height: bundleWindow.innerHeight };
    bundleWindow.innerWidth = 1400; bundleWindow.innerHeight = 900;
    const runtime = mountWithHooks('VocabApp');
    function resize(width, height) {
      bundleWindow.innerWidth = width; bundleWindow.innerHeight = height;
      dispatchWindow('resize', {});
      return runtime.render();
    }
    function coordinates(tree) {
      const node = findByClass(tree, collapsed ? 'dsh-vocab-reopen' : 'dsh-vocab-panel');
      return { ...node.props.style };
    }
    try {
      let tree = runtime.render(); tree = await flushClient(runtime);
      if (!collapsed) tree = openOverlay(runtime, clock);
      if (side !== 'default') {
        const node = findByClass(tree, collapsed ? 'dsh-vocab-reopen' : 'va-head');
        const before = coordinates(tree);
        const x = side === 'left' ? 70 : (collapsed ? 1220 : 866);
        const y = collapsed ? 664 : 310;
        node.props.onPointerDown(fakeEvent({ button: 0, pointerId: 31, clientX: 0, clientY: 0,
          currentTarget: captureSpy().node, target: { closest() { return null; } } }));
        dispatchWindow('pointermove', { pointerId: 31, clientX: x - parseFloat(before.left), clientY: y - parseFloat(before.top) });
        dispatchWindow('pointerup', { pointerId: 31 });
        tree = runtime.render();
        assert.equal(parseFloat(coordinates(tree).left), x);
        assert.equal(parseFloat(coordinates(tree).top), y);
      }
      const start = coordinates(tree);
      // Edge offsets, not absolute pixels, must follow the host as it grows.
      tree = resize(1600, 1100);
      assert.equal(parseFloat(coordinates(tree).left), parseFloat(start.left) + (side === 'left' ? 0 : 200));
      assert.equal(parseFloat(coordinates(tree).top), parseFloat(start.top) + 200);
      assert.deepEqual(coordinates(resize(1400, 900)), start);
      for (let cycle = 0; cycle < 3; cycle += 1) {
        // Zero/tiny intermediate sizes must not erase the preferred anchor.
        for (const [width, height] of [[800, 600], [300, 240], [0, 0], [1000, 700]]) {
          tree = resize(width, height);
          const current = coordinates(tree);
          if (width > 0) {
            const size = collapsed ? { w: 46, h: 46 }
              : { w: parseFloat(current.width), h: parseFloat(current.height) };
            assert.ok(parseFloat(current.left) >= 8 && parseFloat(current.top) >= 8);
            assert.ok(parseFloat(current.left) + size.w <= width - 8);
            assert.ok(parseFloat(current.top) + size.h <= height - 8);
          }
        }
        assert.deepEqual(coordinates(resize(1400, 900)), start, 'shrink/restore must not accumulate drift');
      }
      assert.equal(requests.length, 1, 'geometry never sends actions or reloads study state');
    } finally {
      runtime.unmount(); bundleWindow.innerWidth = original.width; bundleWindow.innerHeight = original.height;
    }
    assert.equal(runtime.lateUpdates, 0);
    assert.equal(clock.pending, 0);
    assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
  });
}

test('resize while collapsed/open preserves one corner, and a later drag replaces the preferred placement', async (t) => {
  const clock = mockTimeoutClock(t);
  const requests = mockClientFetch(t, frontView);
  const original = { width: bundleWindow.innerWidth, height: bundleWindow.innerHeight };
  bundleWindow.innerWidth = 1400; bundleWindow.innerHeight = 900;
  const runtime = mountOpenedOverlay(clock);
  function resize(width, height) {
    bundleWindow.innerWidth = width; bundleWindow.innerHeight = height;
    dispatchWindow('resize', {});
    return runtime.render();
  }
  function panelAt(tree, x, y) {
    const style = findByClass(tree, 'dsh-vocab-panel').props.style;
    assert.deepEqual(style, { left: x + 'px', top: y + 'px', width: '400px', height: '400px' });
  }
  try {
    let tree = await flushClient(runtime);
    panelAt(tree, 982, 482);
    tree = resize(300, 240);
    findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
    tree = resize(1400, 900);
    assert.deepEqual(findByAriaLabel(tree, '打开背单词浮层').props.style, { left: '1336px', top: '836px' });
    tree = resize(800, 600);
    tree = openOverlay(runtime, clock);
    panelAt(tree, 382, 182);
    panelAt(resize(1400, 900), 982, 482);
    // Drag the bubble at a smaller host size: that gesture is the new preference.
    tree = resize(800, 600);
    findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
    tree = runtime.render();
    const bubble = findByAriaLabel(tree, '打开背单词浮层');
    bubble.props.onPointerDown(fakeEvent({ button: 0, pointerId: 32, clientX: 0, clientY: 0, currentTarget: captureSpy().node }));
    dispatchWindow('pointermove', { pointerId: 32, clientX: 50 - parseFloat(bubble.props.style.left), clientY: 500 - parseFloat(bubble.props.style.top) });
    dispatchWindow('pointerup', { pointerId: 32 });
    tree = runtime.render();
    findByAriaLabel(tree, '打开背单词浮层').props.onClick(fakeEvent()); // suppress native follow-up click
    tree = resize(1400, 900);
    assert.deepEqual(findByAriaLabel(tree, '打开背单词浮层').props.style, { left: '50px', top: '800px' });
    panelAt(openOverlay(runtime, clock), 50, 446);
    panelAt(resize(800, 600), 50, 146);
    panelAt(resize(1400, 900), 50, 446);
    assert.equal(requests.length, 1);
  } finally {
    runtime.unmount(); bundleWindow.innerWidth = original.width; bundleWindow.innerHeight = original.height;
  }
  assert.equal(clock.pending, 0);
  assert.equal(runtime.lateUpdates, 0);
  assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
});

test('startup in a narrow host keeps the default edge gap when the host expands', async (t) => {
  const clock = mockTimeoutClock(t);
  mockClientFetch(t, frontView);
  const original = { width: bundleWindow.innerWidth, height: bundleWindow.innerHeight };
  bundleWindow.innerWidth = 300; bundleWindow.innerHeight = 240;
  const runtime = mountWithHooks('VocabApp');
  try {
    runtime.render(); await flushClient(runtime);
    bundleWindow.innerWidth = 1400; bundleWindow.innerHeight = 900;
    dispatchWindow('resize', {});
    const tree = runtime.render();
    assert.deepEqual(findByAriaLabel(tree, '打开背单词浮层').props.style, { left: '1336px', top: '836px' });
    const style = findByClass(openOverlay(runtime, clock), 'dsh-vocab-panel').props.style;
    assert.deepEqual(style, { left: '982px', top: '482px', width: '400px', height: '400px' });
  } finally {
    runtime.unmount(); bundleWindow.innerWidth = original.width; bundleWindow.innerHeight = original.height;
  }
  assert.equal(clock.pending, 0);
});

test('title drag restores the fixed mini preset after viewport expansion', async (t) => {
  const requests = mockClientFetch(t, Object.assign({}, frontView, {
    windowSize: 'small', windowPresets: STALE_WINDOW_PRESETS,
  }));
  bundleWindow.innerWidth = 400;
  bundleWindow.innerHeight = 400;
  const runtime = mountOpenedOverlay();
  const capture = captureSpy();
  try {
    runtime.render();
    let tree = await flushClient(runtime);
    let panel = findElement(tree, (element) => element.type === 'section');
    assert.equal(panel.props.style.width, '384px');
    assert.equal(panel.props.style.height, '384px');
    const header = findElement(tree, (element) => element.type === 'header');
    header.props.onPointerDown(fakeEvent({
      button: 0, pointerId: 21, clientX: 100, clientY: 80,
      currentTarget: capture.node,
      target: { tagName: 'span', closest() { return null; } },
    }));
    dispatchWindow('pointermove', { clientX: 130, clientY: 100 });
    assert.ok(findElement(runtime.render(), (element) => element.type === 'section').props.className.includes('va-dragging'));
    bundleWindow.innerWidth = 1400;
    bundleWindow.innerHeight = 900;
    dispatchWindow('resize', {});
    panel = findElement(runtime.render(), (element) => element.type === 'section');
    assert.equal(panel.props.style.width, '400px', 'resize restores the fixed mini preset');
    assert.equal(panel.props.style.height, '400px');
    dispatchWindow('pointermove', { clientX: 260, clientY: 210 });
    dispatchWindow('pointerup', {});
    panel = findElement(runtime.render(), (element) => element.type === 'section');
    assert.equal(panel.props.style.width, '400px', 'a later move must retain the fixed mini width');
    assert.equal(panel.props.style.height, '400px');
    assert.equal(panel.props.style.left, '168px');
    assert.equal(panel.props.style.top, '138px');
    assert.equal(panel.props.className.includes('va-dragging'), false);
    assert.deepEqual(capture.captured, [21]);
    assert.deepEqual(capture.released, [21]);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel'], 0);
    assert.equal(requests.length, 1, 'title movement never persists geometry or sends an action');
  } finally {
    runtime.unmount();
    bundleWindow.innerWidth = 1400;
    bundleWindow.innerHeight = 900;
  }
  assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
});
test('title drag keeps mini geometry before and after a stale settings response resolves', async (t) => {
  const requests = [];
  const staleSettings = Object.assign({}, settingsView, {
    windowSize: 'small', windowPresets: STALE_WINDOW_PRESETS,
  });
  let resolveState;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    assert.equal(url, '/api/vocab-app/state', 'drag must not send any action');
    assert.equal(options.method, 'GET');
    return new Promise((resolve) => { resolveState = resolve; });
  });
  const runtime = mountOpenedOverlay();
  const capture = captureSpy();
  try {
    const loading = runtime.render();
    let panel = findElement(loading, (element) => element.type === 'section');
    assert.equal(panel.props.style.width, '400px');
    assert.equal(panel.props.style.height, '400px');
    const header = findElement(loading, (element) => element.type === 'header');
    header.props.onPointerDown(fakeEvent({
      button: 0, pointerId: 22, clientX: 100, clientY: 80,
      currentTarget: capture.node,
      target: { tagName: 'span', closest() { return null; } },
    }));
    dispatchWindow('pointermove', { clientX: 90, clientY: 70 });
    panel = findElement(runtime.render(), (element) => element.type === 'section');
    assert.equal(panel.props.style.left, '972px');
    assert.equal(panel.props.style.top, '472px');
    assert.equal(hasClass(panel, 'va-dragging'), true);
    resolveState({ ok: true, json: async () => ({ rev: 1, view: staleSettings }) });
    const tree = await flushClient(runtime);
    assert.equal(tree.props['data-screen'], 'settings');
    assert.equal(testing.collectText(tree).includes('窗口'), false);
    panel = findElement(tree, (element) => element.type === 'section');
    assert.equal(panel.props.style.width, '400px', 'a stale Host response cannot select its old size');
    assert.equal(panel.props.style.height, '400px');
    assert.equal(panel.props.style.left, '972px');
    assert.equal(panel.props.style.top, '472px');
    dispatchWindow('pointermove', { clientX: 70, clientY: 50 });
    dispatchWindow('pointerup', {});
    panel = findElement(runtime.render(), (element) => element.type === 'section');
    assert.equal(panel.props.style.width, '400px', 'dragging after load must retain mini dimensions');
    assert.equal(panel.props.style.height, '400px');
    assert.equal(panel.props.style.left, '952px');
    assert.equal(panel.props.style.top, '452px');
    assert.equal(hasClass(panel, 'va-dragging'), false);
    assert.deepEqual(capture.captured, [22]);
    assert.deepEqual(capture.released, [22]);
    assert.equal(requests.length, 1, 'settings view and dragging never POST a window action');
    assert.equal(requests[0].options.method, 'GET');
  } finally {
    runtime.unmount();
  }
  assert.equal(runtime.lateUpdates, 0);
  assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
});
test('unmounting an active title drag removes listeners and releases pointer capture', async (t) => {
  mockClientFetch(t, frontView);
  const runtime = mountOpenedOverlay();
  const capture = captureSpy();
  try {
    runtime.render();
    const tree = await flushClient(runtime);
    findElement(tree, (element) => element.type === 'header').props.onPointerDown(fakeEvent({
      button: 0, pointerId: 23, clientX: 100, clientY: 80,
      currentTarget: capture.node,
      target: { tagName: 'span', closest() { return null; } },
    }));
    dispatchWindow('pointermove', { clientX: 80, clientY: 60 });
    assert.ok(findElement(runtime.render(), (element) => element.type === 'section').props.className.includes('va-dragging'));
    assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 1);
    const queuedMove = Array.from(windowListeners.get('pointermove'))[0];
    runtime.unmount();
    assertListenerCount(['resize', 'pointermove', 'pointerup', 'pointercancel'], 0);
    assert.deepEqual(capture.captured, [23]);
    assert.deepEqual(capture.released, [23]);
    queuedMove({ clientX: 500, clientY: 400 });
    dispatchWindow('pointerup', {});
    dispatchWindow('pointercancel', {});
    assert.equal(runtime.lateUpdates, 0, 'unmounted drag callbacks must not write React state');
    runtime.unmount();
    assert.deepEqual(capture.released, [23], 'unmount cleanup is idempotent');
  } finally {
    runtime.unmount();
  }
});

// ---------------------------------------------------------------------------
// 10. Closed entry: immediate drag, short click, cancellation
// ---------------------------------------------------------------------------
test('closed entry clamps to the viewport and retains only click suppression tolerance', () => {
  assert.equal(SOURCE.includes('ENTRY_LONG_PRESS_MS'), false);
  assert.equal(SOURCE.includes('setTimeout'), true, 'unrelated application timers remain in use');
  assert.deepEqual(testing.clampEntryPosition({ x: 9999, y: 9999 }), { x: 1346, y: 846 });
  bundleWindow.innerWidth = 400;
  bundleWindow.innerHeight = 300;
  try {
    assert.deepEqual(testing.clampEntryPosition({ x: -50, y: -50 }), { x: 8, y: 8 });
    assert.deepEqual(testing.clampEntryPosition({ x: 9999, y: 9999 }), { x: 346, y: 246 });
  } finally {
    bundleWindow.innerWidth = 1400;
    bundleWindow.innerHeight = 900;
  }
});
test('short click opens the panel without starting a timer', (t) => {
  const clock = mockTimeoutClock(t);
  let opened = 0;
  const runtime = mountWithHooks('ClosedEntry', {
    position: null,
    open() { opened += 1; },
    onMove() {},
  });
  try {
    const button = findByAriaLabel(runtime.render(), '打开背单词浮层');
    assert.ok(button);
    button.props.onPointerDown(fakeEvent({
      button: 0, pointerId: 3, clientX: 100, clientY: 100,
      currentTarget: { setPointerCapture() {}, releasePointerCapture() {} },
      target: { tagName: 'button', closest() { return null; } },
    }));
    assert.equal(clock.pending, 0, 'closed entry does not wait for a timer');
    dispatchWindow('pointerup', {});
    findByAriaLabel(runtime.render(), '打开背单词浮层').props.onClick(fakeEvent());
    assert.equal(opened, 1);
    assert.equal(clock.pending, 0);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 0);
  } finally {
    runtime.unmount();
  }
});
test('entry begins dragging immediately and moves even under tolerance across rerenders', (t) => {
  const clock = mockTimeoutClock(t);
  let opened = 0;
  const moves = [];
  const capture = captureSpy();
  const runtime = mountWithHooks('ClosedEntry', {
    position: null,
    open() { opened += 1; },
    onMove(x, y) { moves.push([x, y]); },
  });
  try {
    let button = findByAriaLabel(runtime.render(), '打开背单词浮层');
    button.props.onPointerDown(fakeEvent({
      button: 0, pointerId: 4, clientX: 100, clientY: 100,
      currentTarget: capture.node,
      target: { tagName: 'button', closest() { return null; } },
    }));
    assert.deepEqual(capture.captured, [4]);
    button = findByAriaLabel(runtime.render(), '打开背单词浮层');
    assert.equal(button.props.className.includes('is-dragging'), true, 'drag state starts on pointerdown');
    assert.equal(clock.pending, 0, 'drag start does not use a time threshold');
    dispatchWindow('pointermove', { clientX: 102, clientY: 102 });
    assert.deepEqual(moves[0], [1338, 838], 'even a sub-tolerance move updates the position');
    dispatchWindow('pointermove', { clientX: 140, clientY: 120 });
    assert.deepEqual(moves[1], [1346, 846], 'entry position is clamped into the viewport');
    dispatchWindow('pointerup', {});
    button = findByAriaLabel(runtime.render(), '打开背单词浮层');
    assert.equal(button.props.className.includes('is-dragging'), false);
    button.props.onClick(fakeEvent());
    assert.equal(opened, 0, 'suppression refs must survive a real rerender');
    assert.equal(clock.pending, 0);
    assert.deepEqual(capture.released, [4]);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 0);
  } finally {
    runtime.unmount();
  }
});
test('pointercancel/blur aborts the entry drag without opening', (t) => {
  const clock = mockTimeoutClock(t);
  for (const cancelEvent of ['pointercancel', 'blur']) {
    let opened = 0;
    const capture = captureSpy();
    const runtime = mountWithHooks('ClosedEntry', {
      position: null,
      open() { opened += 1; },
      onMove() {},
    });
    try {
      const button = findByAriaLabel(runtime.render(), '打开背单词浮层');
      button.props.onPointerDown(fakeEvent({
        button: 0, pointerId: 7, clientX: 100, clientY: 100,
        currentTarget: capture.node,
        target: { tagName: 'button', closest() { return null; } },
      }));
      dispatchWindow(cancelEvent, {});
      assert.equal(clock.pending, 0);
      findByAriaLabel(runtime.render(), '打开背单词浮层').props.onClick(fakeEvent());
      assert.equal(opened, 0, cancelEvent + ' must suppress the click');
      assert.equal(clock.pending, 0, cancelEvent + ' must not leave a timer pending');
      assert.deepEqual(capture.released, [7]);
      assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 0);
    } finally {
      runtime.unmount();
    }
  }
});
test('right-click does not start an entry drag', (t) => {
  const clock = mockTimeoutClock(t);
  const moves = [];
  const capture = captureSpy();
  const runtime = mountWithHooks('ClosedEntry', {
    position: null,
    open() {},
    onMove(x, y) { moves.push([x, y]); },
  });
  try {
    const button = findByAriaLabel(runtime.render(), '打开背单词浮层');
    button.props.onPointerDown(fakeEvent({
      button: 2, pointerId: 9, clientX: 100, clientY: 100,
      currentTarget: capture.node,
      target: { tagName: 'button', closest() { return null; } },
    }));
    dispatchWindow('pointermove', { clientX: 200, clientY: 200 });
    assert.deepEqual(moves, []);
    assert.deepEqual(capture.captured, []);
    assert.equal(clock.pending, 0);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 0);
  } finally {
    runtime.unmount();
  }
});
test('unmounting an immediate entry drag clears listeners and capture', (t) => {
  const clock = mockTimeoutClock(t);
  let opened = 0;
  const moves = [];
  const capture = captureSpy();
  const runtime = mountWithHooks('ClosedEntry', {
    position: null,
    open() { opened += 1; },
    onMove(x, y) { moves.push([x, y]); },
  });
  try {
    findByAriaLabel(runtime.render(), '打开背单词浮层').props.onPointerDown(fakeEvent({
      button: 0, pointerId: 24, clientX: 100, clientY: 100,
      currentTarget: capture.node,
      target: { tagName: 'button', closest() { return null; } },
    }));
    assert.equal(clock.pending, 0);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 1);
    runtime.unmount();
    assert.equal(clock.pending, 0);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 0);
    assert.deepEqual(capture.captured, [24]);
    assert.deepEqual(capture.released, [24]);
    clock.tick(1000);
    dispatchWindow('pointermove', { clientX: 200, clientY: 200 });
    dispatchWindow('pointerup', {});
    assert.deepEqual(moves, []);
    assert.equal(opened, 0);
    assert.equal(runtime.lateUpdates, 0);
  } finally {
    runtime.unmount();
  }
});
test('unmounting an immediate entry drag clears listeners and prevents late updates', (t) => {
  const clock = mockTimeoutClock(t);
  let opened = 0;
  const moves = [];
  const capture = captureSpy();
  const runtime = mountWithHooks('ClosedEntry', {
    position: { x: 80, y: 90 },
    open() { opened += 1; },
    onMove(x, y) { moves.push([x, y]); },
  });
  try {
    findByAriaLabel(runtime.render(), '打开背单词浮层').props.onPointerDown(fakeEvent({
      button: 0, pointerId: 25, clientX: 100, clientY: 100,
      currentTarget: capture.node,
      target: { tagName: 'button', closest() { return null; } },
    }));
    const button = findByAriaLabel(runtime.render(), '打开背单词浮层');
    assert.equal(button.props.className.includes('is-dragging'), true);
    dispatchWindow('pointermove', { clientX: 130, clientY: 120 });
    assert.deepEqual(moves, [[110, 110]]);
    assert.equal(clock.pending, 0);
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 1);
    runtime.unmount();
    assertListenerCount(['pointermove', 'pointerup', 'pointercancel', 'blur'], 0);
    assert.deepEqual(capture.captured, [25]);
    assert.deepEqual(capture.released, [25]);
    clock.tick(1000);
    dispatchWindow('pointermove', { clientX: 300, clientY: 200 });
    dispatchWindow('pointercancel', {});
    dispatchWindow('blur', {});
    button.props.onClick(fakeEvent());
    assert.deepEqual(moves, [[110, 110]], 'unmounted entry listeners cannot move the parent');
    assert.equal(opened, 0, 'the moved entry still suppresses its follow-up click');
    assert.equal(runtime.lateUpdates, 0);
    runtime.unmount();
    assert.deepEqual(capture.released, [25]);
  } finally {
    runtime.unmount();
  }
});

// ---------------------------------------------------------------------------
// 11. Misc: history rows, empty-screen poll, styles
// ---------------------------------------------------------------------------
test('history rows keep host title/detail and deleteHistory', () => {
  const view = baseView('history', {
    points: [],
    rows: [{
      index: 2, ts: 1700000000, tsText: '2023-11-14',
      title: '2023-11-14  ·  5,200 词',
      detail: '本次已作答 40 题，答对 36 题。\n估计认识约 5,200 个词。',
      vocab: 5200, right: 36, total: 40, dontknow: 2, available: true, interval: [4700, 5700],
    }],
  });
  const spy = createApiSpy();
  const tree = render(view, spy.api), text = testing.collectText(tree);
  assert.ok(text.includes('2023-11-14'));
  assert.ok(text.includes('本次已作答 40 题'));
  assert.equal(text.includes('删除这条记录'), false);
  const row = findByClass(tree, 'va-hist-row');
  const details = findElement(row, (element) => element.type === 'details');
  const button = findByClass(row, 'va-hist-delete');
  assert.equal(testing.collectText(button).trim(), '删除');
  assert.equal(button.type, 'button');
  assert.equal(button.props.type, 'button');
  assert.equal(button.props.className.includes('va-danger'), false, 'history delete uses the quiet record style');
  assert.equal(button.props.style?.marginTop, undefined);
  assert.equal(button.props['aria-label'], '删除这条测试记录');
  assert.equal(findElement(details, (element) => element.type === 'button'), null, 'details contains only record text');
  assert.equal(findByClass(details, 'va-hist-delete'), null, 'delete stays outside the expandable details');
  const previousConfirm = bundleWindow.confirm;
  try {
    bundleWindow.confirm = () => false;
    button.props.onClick();
    assert.equal(spy.calls.send.length, 0, 'cancel preserves history');
    bundleWindow.confirm = () => true;
    button.props.onClick();
    assert.deepEqual(spy.calls.send, [{ type: 'deleteHistory', payload: { index: 2 } }]);
  } finally { bundleWindow.confirm = previousConfirm; }
});
test('history keeps original indices, fallback details and non-deletable rows', () => {
  const spy = createApiSpy();
  const tree = render(baseView('history', { points: [], rows: [
    { index: 17, title: '2026-11-16 · 测试未完成', total: 12, right: 8 },
    { index: 4, title: '2026-11-15 · 旧版记录', detail: '旧版数值保留，未重新计算。' },
    { title: '无索引记录', total: 2 },
  ] }), spy.api);
  const rows = collectElements(tree).filter((element) => element.props.className?.split(' ').includes('va-hist-row'));
  assert.equal(rows.length, 3);
  assert.ok(testing.collectText(rows[0]).includes('答对 8 / 12 题'));
  assert.ok(testing.collectText(rows[1]).includes('旧版数值保留，未重新计算。'));
  assert.ok(testing.collectText(rows[2]).includes('已答 2 题'));
  assert.equal(findByClass(rows[2], 'va-hist-delete'), null, 'missing source index never invents a delete target');
  assert.equal(rows[2].props.className.includes('has-delete'), false);
  const previousConfirm = bundleWindow.confirm;
  try {
    bundleWindow.confirm = () => true;
    findByClass(rows[0], 'va-hist-delete').props.onClick();
    findByClass(rows[1], 'va-hist-delete').props.onClick();
    assert.deepEqual(spy.calls.send.map((entry) => entry.payload.index), [17, 4], 'display order is not a storage index');
  } finally { bundleWindow.confirm = previousConfirm; }
});
test('history delete CSS stays neutral and right-aligned without masking focus', () => {
  const row = SOURCE.match(/\.va-hist-row\{([^}]+)\}/)?.[1] || '';
  const button = SOURCE.match(/\.va-hist-delete\{([^}]+)\}/)?.[1] || '';
  assert.ok(row.includes('display:flex'));
  assert.ok(row.includes('align-items:flex-start'));
  assert.ok(SOURCE.includes('.va-hist-row>.va-hist{flex:1;min-width:0;margin:0;}'));
  assert.ok(button.includes('flex:none'));
  assert.ok(button.includes('white-space:nowrap'));
  assert.ok(button.includes('background:var(--va-opt-bg)'));
  assert.ok(button.includes('color:var(--va-opt-fg)'));
  assert.ok(SOURCE.includes('.va-hist-delete:hover{background:var(--va-opt-hover);}'));
  assert.ok(SOURCE.includes('.va-hist-delete:active{background:var(--va-btn-pressed);}'));
  assert.ok(SOURCE.includes('.dsh-vocab-root button:focus-visible'));
});
test('empty screen polls GET /state only while visible', () => {
  assert.ok(SOURCE.includes("screen !== 'empty'"));
  assert.ok(SOURCE.includes('15000'));
  assert.ok(SOURCE.includes('clearInterval(timer)'));
  assert.ok(SOURCE.includes('loadState(true)'));
});
test('installStyles injects one plugin style tag and removes it on dispose', () => {
  const appended = [];
  const head = {
    appendChild(node) { node.parentNode = head; appended.push(node); },
    removeChild(node) {
      const position = appended.indexOf(node);
      if (position >= 0) appended.splice(position, 1);
      node.parentNode = null;
    },
  };
  const previousDocument = globalThis.document;
  globalThis.document = {
    head,
    createElement(tagName) { return { tagName, id: '', textContent: '', parentNode: null, setAttribute() {} }; },
    getElementById() { return null; },
  };
  try {
    const dispose = testing.installStyles();
    assert.equal(appended.length, 1);
    const tag = appended[0];
    assert.equal(tag.id, 'dsh-vocab-app:styles');
    assert.ok(tag.textContent.includes('.dsh-vocab-panel'));
    assert.ok(tag.textContent.includes('var(--va-bg)'));
    dispose();
    assert.equal(tag.parentNode, null);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

// v0.1.3: real registered-overlay and scheduling regression additions.
function reviewClock(t) {
  const clock = mockTimeoutClock(t);
  const intervals = new Map();
  let sequence = 10000;
  t.mock.method(globalThis, 'setInterval', (fn, ms) => {
    const id = ++sequence; intervals.set(id, { fn, ms }); return id;
  });
  t.mock.method(globalThis, 'clearInterval', (id) => intervals.delete(id));
  t.mock.method(Date, 'now', () => 1700000000000 + clock.now);
  return { clock, intervals, poll() { for (const item of [...intervals.values()]) item.fn(); } };
}
function actionRequests(requests) {
  return requests.filter((item) => item.options?.method === 'POST').map((item) => JSON.parse(item.options.body));
}
function atEmpty(due) { return Object.assign({}, emptyView, { due }); }

// v0.1.8: loading feedback cannot wait for a cold quizStart response.
test('quizStart immediately shows loading before POST or response and suppresses duplicate clicks', async (t) => {
  const { clock, intervals, poll } = reviewClock(t);
  const requests = [];
  let release;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') return Promise.resolve({ ok: true, json: async () => ({ rev: 7, view: settingsView }) });
    return new Promise((resolve) => { release = () => resolve({ ok: true, json: async () => ({ ok: true, rev: 7, view: allViews.building }) }); });
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); let tree = await flushClient(runtime);
    const button = findByAriaLabel(tree, '开始新的词汇量测试');
    button.props.onClick(fakeEvent());
    tree = runtime.render();
    assert.equal(tree.props['data-screen'], 'building', 'feedback must render synchronously in the click turn');
    assert.ok(testing.collectText(tree).includes('正在加载测试'));
    assert.equal(findByAriaLabel(tree, '开始新的词汇量测试'), null);
    assert.equal(findByAriaLabel(tree, '题库构建进度').props['aria-valuenow'], 0, 'startup begins at the left edge until real progress arrives');
    assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, '0%');
    assert.equal(testing.collectText(findByClass(tree, 'va-head-left')).trim(), '', 'loading has no duplicate upper-left title');
    assert.equal(findByClass(tree, 'va-building').props['aria-busy'], 'true');
    assert.equal(testing.collectText(tree).includes('0%'), false, 'Windows-style bar does not print numerical percentages');
    assert.equal(findByClass(tree, 'is-indeterminate'), null);
    button.props.onClick(fakeEvent()); // A stale DOM callback cannot start a second test.
    await flushClient(runtime);
    poll(); await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 1);
    assert.deepEqual(actionRequests(requests)[0], { rev: 7, type: 'quizStart', payload: { fresh: true } });
    assert.equal(requests.filter((entry) => entry.options.method === 'GET').length, 1, 'do not poll over the pending POST');
    assert.equal(intervals.size, 0, 'local loading does not pretend to be host build progress');
    release(); tree = await flushClient(runtime);
    assert.equal(tree.props['data-screen'], 'building');
    assert.equal(testing.collectText(tree).includes('42%'), false);
    assert.equal(testing.collectText(findByClass(tree, 'va-head-left')).trim(), '');
    assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, '42%');
    assert.equal(findByAriaLabel(tree, '题库构建进度').props['aria-valuenow'], 42, 'only host progress supplies percentages');
    assert.equal(intervals.size, 1, 'host building response starts state polling');
  } finally { runtime.unmount(); }
  assert.equal(intervals.size, 0);
});
test('building header stays blank and the bar has only bounded left-to-right widths', () => {
  for (const percent of [-12, 0, 1, 42, 100, 180, 'bad']) {
    const view = baseView('building', { title: '正在加载测试…', percent });
    const header = testing.renderHeader(view, createApiSpy().api);
    assert.equal(testing.collectText(findByClass(header, 'va-head-left')).trim(), '');
    assert.ok(findByAriaLabel(header, '关闭浮层'), 'close/drag header stays available');
    const body = render(view, createApiSpy().api);
    const expected = typeof percent === 'number' ? Math.min(100, Math.max(0, percent)) : 0;
    assert.equal(findByClass(body, 'va-progress-fill').props.style.width, expected + '%');
    assert.equal(findByAriaLabel(body, '题库构建进度').props['aria-valuenow'], expected);
    assert.equal(findByClass(body, 'is-indeterminate'), null);
    assert.equal(testing.collectText(body).includes('%'), false);
  }
});
test('loading follows successive actual build updates and disappears only on completion or failure', async (t) => {
  const { clock, intervals, poll } = reviewClock(t);
  let hostView = settingsView, release;
  const requests = [];
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, method: options.method });
    return options.method === 'GET'
      ? Promise.resolve({ ok: true, json: async () => ({ rev: 5, view: hostView }) })
      : new Promise((resolve) => { release = () => resolve({ ok: true, json: async () => ({ ok: true, rev: 5, view: baseView('building', { percent: 0 }) }) }); });
  });
  for (const end of [quizView, settingsView]) {
    hostView = settingsView;
    const runtime = mountOpenedOverlay(clock);
    try {
      runtime.render(); let tree = await flushClient(runtime);
      findByAriaLabel(tree, '开始新的词汇量测试').props.onClick(fakeEvent());
      tree = runtime.render();
      assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, '0%');
      await flushClient(runtime); release(); await flushClient(runtime);
      assert.equal([...intervals.values()][0].ms, 100, 'real build progress is read without half-second jumps');
      for (const percent of [0, 5, 18, 37, 66, 93, 100]) {
        hostView = baseView('building', { percent }); poll(); tree = await flushClient(runtime);
        assert.equal(tree.props['data-screen'], 'building');
        assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, percent + '%');
        assert.equal(testing.collectText(findByClass(tree, 'va-head-left')).trim(), '');
      }
      hostView = end; poll(); tree = await flushClient(runtime);
      if (end.screen === 'quiz') {
        assert.equal(tree.props['data-screen'], 'building');
        assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, '100%');
        const posts = requests.filter((v) => v.method === 'POST').length;
        tree.props.onKeyDown(keyEvent({ key: '1' })); await flushClient(runtime);
        assert.equal(requests.filter((v) => v.method === 'POST').length, posts, 'filled-bar presentation must not accept quiz answers');
        assert.equal(intervals.size, 0, 'no more build reads once the host has completed');
        clock.tick(299); tree = await flushClient(runtime); assert.equal(tree.props['data-screen'], 'building');
        clock.tick(1); tree = await flushClient(runtime);
      }
      assert.equal(tree.props['data-screen'], end.screen);
      assert.equal(findByClass(tree, 'va-building'), null);
      assert.equal(intervals.size, 0);
    } finally { runtime.unmount(); }
  }
});
test('quizStart loading goes directly to quiz for a warm bank and poll completion for a cold bank', async (t) => {
  const { clock, intervals, poll } = reviewClock(t);
  let gets = 0, release;
  let hostView = settingsView;
  const requests = [];
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') { gets += 1; return Promise.resolve({ ok: true, json: async () => ({ rev: gets === 1 ? 10 : 11, view: hostView }) }); }
    return new Promise((resolve) => { release = (view) => resolve({ ok: true, json: async () => ({ ok: true, rev: 11, view }) }); });
  });
  for (const cold of [false, true]) {
    gets = 0; hostView = settingsView;
    const runtime = mountOpenedOverlay(clock);
    try {
      runtime.render(); let tree = await flushClient(runtime);
      findByAriaLabel(tree, '开始新的词汇量测试').props.onClick(fakeEvent());
      assert.equal(runtime.render().props['data-screen'], 'building');
      await flushClient(runtime);
      release(cold ? allViews.building : quizView); tree = await flushClient(runtime);
      if (cold) {
        assert.equal(tree.props['data-screen'], 'building');
        hostView = quizView; poll(); tree = await flushClient(runtime);
        assert.equal(tree.props['data-screen'], 'building');
        assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, '100%');
        clock.tick(300); tree = await flushClient(runtime);
      }
      assert.equal(tree.props['data-screen'], 'quiz');
      assert.equal(findByClass(tree, 'va-building'), null);
      assert.equal(intervals.size, 0, 'completed startup stops polling');
    } finally { runtime.unmount(); }
  }
  assert.equal(actionRequests(requests).length, 2);
});
test('unmount during the final filled bar clears its timer and never updates a disposed overlay', async (t) => {
  const { clock, intervals, poll } = reviewClock(t);
  let state = settingsView;
  t.mock.method(globalThis, 'fetch', (url, options) => Promise.resolve({ ok: true, json: async () => options.method === 'GET'
    ? { rev: 7, view: state } : { ok: true, rev: 7, view: baseView('building', { percent: 0 }) } }));
  const runtime = mountOpenedOverlay(clock);
  runtime.render(); let tree = await flushClient(runtime);
  findByAriaLabel(tree, '开始新的词汇量测试').props.onClick(fakeEvent()); await flushClient(runtime);
  state = quizView; poll(); tree = await flushClient(runtime);
  assert.equal(tree.props['data-screen'], 'building');
  assert.equal(findByClass(tree, 'va-progress-fill').props.style.width, '100%');
  assert.equal(clock.pending, 1);
  runtime.unmount(); clock.tick(500);
  assert.equal(clock.pending, 0); assert.equal(intervals.size, 0); assert.equal(runtime.lateUpdates, 0);
});
test('quizStart failure restores settings with retry; stale and invalid responses cannot strand loading', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = [];
  let outcome = 'network', release;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') return Promise.resolve({ ok: true, json: async () => ({ rev: 3, view: settingsView }) });
    return new Promise((resolve, reject) => {
      release = () => outcome === 'network' ? reject(new Error('synthetic offline'))
        : resolve({ ok: true, json: async () => outcome === 'success'
          ? { ok: true, rev: 13, view: quizView }
          : { ok: false, code: outcome, message: 'synthetic ' + outcome, rev: 12, view: settingsView } });
    });
  });
  for (const failure of ['network', 'stale', 'invalid', 'failed']) {
    outcome = failure;
    const runtime = mountOpenedOverlay(clock);
    try {
      runtime.render(); let tree = await flushClient(runtime);
      findByAriaLabel(tree, '开始新的词汇量测试').props.onClick(fakeEvent());
      assert.equal(runtime.render().props['data-screen'], 'building');
      await flushClient(runtime); release(); tree = await flushClient(runtime);
      assert.equal(tree.props['data-screen'], 'settings', failure + ' must leave a usable page');
      assert.equal(findByClass(tree, 'va-building'), null);
      assert.ok(findByAriaLabel(tree, '开始新的词汇量测试'));
      assert.equal(intervals.size, 0);
      if (failure === 'network') {
        outcome = 'success';
        findByAriaLabel(tree, '重试').props.onClick(fakeEvent());
        assert.equal(runtime.render().props['data-screen'], 'building');
        await flushClient(runtime); release(); tree = await flushClient(runtime);
        assert.equal(tree.props['data-screen'], 'quiz');
      }
    } finally { runtime.unmount(); }
  }
  assert.equal(actionRequests(requests).length, 5, 'only the explicit retry repeats quizStart');
});
test('quizStart loading handles resume and unmount without late updates or leftover polls', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = [];
  let release;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') return Promise.resolve({ ok: true, json: async () => ({ rev: 9, view: Object.assign({}, settingsView, { hasSession: true }) }) });
    return new Promise((resolve) => { release = () => resolve({ ok: true, json: async () => ({ ok: true, rev: 10, view: quizView }) }); });
  });
  const runtime = mountOpenedOverlay(clock);
  runtime.render(); const tree = await flushClient(runtime);
  findByAriaLabel(tree, '继续上次词汇量测试').props.onClick(fakeEvent());
  assert.equal(runtime.render().props['data-screen'], 'building');
  await flushClient(runtime);
  assert.deepEqual(actionRequests(requests), [{ rev: 9, type: 'quizStart', payload: { fresh: false } }]);
  runtime.unmount(); release(); await new Promise((resolve) => setImmediate(resolve));
  assert.equal(runtime.lateUpdates, 0);
  assert.equal(intervals.size, 0);
});

test('quizStart keeps loading through deferred JSON and discards it on an unreadable response', async (t) => {
  const { clock, intervals, poll } = reviewClock(t);
  const requests = [];
  let outcome, completeBody;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') return Promise.resolve({ ok: true, json: async () => ({ rev: 21, view: settingsView }) });
    return Promise.resolve({ ok: outcome === 'success', status: outcome === 'success' ? 200 : 503,
      json: () => new Promise((resolve, reject) => { completeBody = () => outcome === 'success'
        ? resolve({ ok: true, rev: 22, view: quizView }) : reject(new SyntaxError('synthetic unreadable JSON')); }),
    });
  });
  for (outcome of ['success', 'bad-json']) {
    const runtime = mountOpenedOverlay(clock);
    try {
      runtime.render(); let tree = await flushClient(runtime);
      findByAriaLabel(tree, '开始新的词汇量测试').props.onClick(fakeEvent());
      tree = await flushClient(runtime);
      assert.equal(tree.props['data-screen'], 'building', 'HTTP headers alone do not end startup feedback');
      assert.ok(testing.collectText(tree).includes('正在加载测试'));
      assert.equal(findByAriaLabel(tree, '返回上一页'), null);
      poll(); await flushClient(runtime);
      assert.equal(intervals.size, 0);
      completeBody(); tree = await flushClient(runtime);
      assert.equal(tree.props['data-screen'], outcome === 'success' ? 'quiz' : 'settings');
      assert.equal(findByClass(tree, 'va-building'), null);
      if (outcome === 'bad-json') assert.ok(findByAriaLabel(tree, '重试'));
    } finally { runtime.unmount(); }
  }
  assert.equal(actionRequests(requests).length, 2);
});
test('quizStart welcome entry and hidden pending panel preserve one request and resume the loading view', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = [];
  let release;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') return Promise.resolve({ ok: true, json: async () => ({ rev: 30, view: allViews.welcome }) });
    return new Promise((resolve) => { release = () => resolve({ ok: true, json: async () => ({ ok: true, rev: 31, view: quizView }) }); });
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); let tree = await flushClient(runtime);
    findByAriaLabel(tree, '测试一下').props.onClick(fakeEvent());
    assert.equal(runtime.render().props['data-screen'], 'building');
    tree = await flushClient(runtime);
    findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
    tree = runtime.render();
    assert.equal(findByClass(tree, 'dsh-vocab-panel'), null);
    findElement(tree, (element) => element.type === 'button').props.onClick(fakeEvent());
    tree = runtime.render();
    assert.equal(tree.props['data-screen'], 'building');
    assert.ok(testing.collectText(tree).includes('正在加载测试'));
    clock.tick(0);
    release(); tree = await flushClient(runtime);
    assert.equal(tree.props['data-screen'], 'quiz');
    assert.deepEqual(actionRequests(requests), [{ rev: 30, type: 'quizStart', payload: { fresh: true } }]);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
  assert.equal(intervals.size, 0);
  assert.equal(runtime.lateUpdates, 0);
});

test('v0.1.3: nullable due is not epoch zero, and real epoch zero stays valid', () => {
  for (const due of [null, undefined, '', 'not-a-time']) assert.equal(testing.reviewDue(atEmpty(due)), null);
  assert.equal(testing.reviewDue(atEmpty(0)), 0);
  assert.equal(testing.reviewDue(atEmpty('0')), null, 'Host due contract is numeric');
  assert.equal(testing.reviewDue(Object.assign({}, frontView, { due: 0 })), null);
});

test('v0.1.5: fixed mini shares the exact expanded/collapsed corner in narrow viewports', () => {
  const original = { width: bundleWindow.innerWidth, height: bundleWindow.innerHeight };
  try {
    for (const [width, height] of [[1400, 900], [800, 600], [300, 240]]) {
      bundleWindow.innerWidth = width; bundleWindow.innerHeight = height;
      for (const preset of WINDOW_PRESETS) for (const side of ['left', 'right']) {
        const anchor = testing.fitAnchor({ side, x: side === 'left' ? 30 : width - 30, y: height - 30 }, preset);
        const panel = testing.geometryFromAnchor(anchor, preset);
        const entry = testing.entryFromAnchor(anchor, preset);
        assert.equal(entry.y + entry.size, panel.y + panel.h);
        assert.equal(side === 'left' ? entry.x : entry.x + entry.size,
          side === 'left' ? panel.x : panel.x + panel.w);
        assert(panel.x >= 6 && panel.y >= 6);
        assert(panel.x + panel.w <= width - 6 && panel.y + panel.h <= height - 6);
        assert.deepEqual(testing.geometryFromAnchor(anchor, preset), panel);
      }
    }
  } finally { bundleWindow.innerWidth = original.width; bundleWindow.innerHeight = original.height; }
});

test('v0.1.5: dragged entry determines the fixed mini panel while preserving its corner', () => {
  const original = { width: bundleWindow.innerWidth, height: bundleWindow.innerHeight };
  bundleWindow.innerWidth = 1400; bundleWindow.innerHeight = 900;
  try {
    for (const point of [{ x: 90, y: 600 }, { x: 1270, y: 600 }]) {
      const anchor = testing.anchorFromEntry(point, WINDOW_PRESETS[0]);
      const mini = testing.geometryFromAnchor(anchor, WINDOW_PRESETS[0]);
      const bubble = testing.entryFromAnchor(anchor, WINDOW_PRESETS[0]);
      assert.equal(bubble.x, point.x); assert.equal(bubble.y, point.y);
      assert.equal(mini.w, 400); assert.equal(mini.h, 400);
      assert.equal(mini.y + mini.h, bubble.y + bubble.size);
      assert.equal(anchor.side === 'left' ? mini.x : mini.x + mini.w,
        anchor.side === 'left' ? bubble.x : bubble.x + bubble.size);
      assert.equal(anchor.side, point.x < 700 ? 'left' : 'right');
    }
  } finally { bundleWindow.innerWidth = original.width; bundleWindow.innerHeight = original.height; }
});

test('v0.1.3: actual mouse forget hides correction; remember exposes a working one-way correction', async (t) => {
  const requests = mockClientFetch(t, frontView, (request) => {
    if (request.type === 'answer') return request.payload.action === 'forget' ? backNoCorrectView : backView;
    assert(['next', 'correct'].includes(request.type));
    return Object.assign({}, frontView, { word: { w: request.type === 'correct' ? 'after-correction' : 'next-word' } });
  });
  const runtime = mountOpenedOverlay();
  try {
    runtime.render(); let tree = await flushClient(runtime);
    findByAriaLabel(tree, '不认识').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    assert.equal(findByAriaLabel(tree, '选错了'), null);
    assert(findByClass(tree, 'va-btn-centered'));
    findByAriaLabel(tree, '下一个').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    findByAriaLabel(tree, '认识').props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    const correct = findByAriaLabel(tree, '选错了');
    assert(correct && !correct.props.disabled);
    correct.props.onClick(fakeEvent());
    tree = await flushClient(runtime);
    assert(testing.collectText(tree).includes('after-correction'));
    assert.equal(findByAriaLabel(tree, '选错了'), null);
    assert.deepEqual(actionRequests(requests).map(({ type, payload }) => ({ type, payload })), [
      { type: 'answer', payload: { action: 'forget' } }, { type: 'next', payload: {} },
      { type: 'answer', payload: { action: 'remember' } }, { type: 'correct', payload: {} },
    ]);
    assert.equal(runtime.lateUpdates, 0);
  } finally { runtime.unmount(); }
});

test('v0.1.3: empty wakes at the precise five-minute boundary by POST, then stops on an unanswered card', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = mockClientFetch(t, atEmpty(1700000300), (request) => {
    assert.equal(request.type, 'next'); return frontView;
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); await flushClient(runtime);
    assert.equal(intervals.size, 1);
    clock.tick(299999); await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0);
    clock.tick(1); const tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 1);
    assert.equal(actionRequests(requests)[0].rev, 1);
    assert(testing.collectText(tree).includes('abandon'));
    assert.equal(intervals.size, 0);
    clock.tick(900000); await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 1, 'never replace an unanswered card');
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
});

test('v0.1.3: null empty due never POSTs and a thirty-day future due uses bounded timer slices', async (t) => {
  const { clock } = reviewClock(t);
  let requestView = atEmpty(null);
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    assert.equal(options.method, 'GET');
    return { ok: true, json: async () => ({ rev: 1, view: requestView }) };
  });
  let runtime = mountOpenedOverlay(clock);
  runtime.render(); await flushClient(runtime);
  clock.tick(1000000); await flushClient(runtime);
  assert.equal(actionRequests(requests).length, 0);
  runtime.unmount();
  requestView = atEmpty((Date.now() / 1000) + 30 * 86400);
  runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); await flushClient(runtime);
    assert.equal(clock.nextDelay, 60000);
    clock.tick(60000); await flushClient(runtime);
    assert.equal(clock.nextDelay, 60000);
    assert.equal(actionRequests(requests).length, 0);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
});

test('v0.1.3: stale auto-next retries with the latest revision after bounded backoff', async (t) => {
  const { clock } = reviewClock(t);
  const requests = [];
  let posted = 0;
  const view = atEmpty(1700000001);
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') return { ok: true, json: async () => ({ rev: 1, view }) };
    const action = JSON.parse(options.body); assert.equal(action.type, 'next');
    posted += 1;
    return { ok: true, json: async () => posted === 1
      ? { ok: false, code: 'stale', rev: 23, view, message: 'synthetic stale' }
      : { ok: true, rev: 24, view: frontView } };
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); await flushClient(runtime);
    clock.tick(1000); await flushClient(runtime);
    assert.equal(posted, 1);
    clock.tick(1499); await flushClient(runtime); assert.equal(posted, 1);
    clock.tick(1); await flushClient(runtime); assert.equal(posted, 2);
    assert.deepEqual(actionRequests(requests).map((entry) => entry.rev), [1, 23]);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
});

test('v0.1.3: an in-flight quiet GET defers due POST and wakes it using the returned revision', async (t) => {
  const { clock, poll } = reviewClock(t);
  const requests = [];
  let gets = 0, release;
  const view = atEmpty(1700000001);
  t.mock.method(globalThis, 'fetch', (url, options) => {
    requests.push({ url, options });
    if (options.method === 'GET') {
      gets += 1;
      const body = { ok: true, json: async () => ({ rev: gets === 1 ? 1 : 41, view }) };
      return gets === 1 ? Promise.resolve(body) : new Promise((resolve) => { release = () => resolve(body); });
    }
    return Promise.resolve({ ok: true, json: async () => ({ ok: true, rev: 42, view: frontView }) });
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); await flushClient(runtime);
    clock.tick(900); poll(); await flushClient(runtime);
    clock.tick(100); await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0, 'busy GET must serialize the action');
    release(); await flushClient(runtime);
    clock.tick(0); await flushClient(runtime);
    assert.deepEqual(actionRequests(requests).map((entry) => entry.rev), [41]);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
});

test('v0.1.3: network failure backs off and a successful still-empty response cannot spin', async (t) => {
  const { clock } = reviewClock(t);
  let posted = 0;
  const view = atEmpty(1700000001);
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (options.method === 'GET') return { ok: true, json: async () => ({ rev: 1, view }) };
    posted += 1;
    if (posted === 1) throw new Error('synthetic offline');
    return { ok: true, json: async () => ({ ok: true, rev: posted + 1, view: posted === 2 ? view : frontView }) };
  });
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); await flushClient(runtime);
    clock.tick(1000); await flushClient(runtime); assert.equal(posted, 1);
    clock.tick(1499); await flushClient(runtime); assert.equal(posted, 1);
    clock.tick(1); await flushClient(runtime); assert.equal(posted, 2);
    clock.tick(14999); await flushClient(runtime); assert.equal(posted, 2);
    clock.tick(1); await flushClient(runtime); assert.equal(posted, 3);
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
});

test('v0.1.3: unmount clears due/poll timers and late network completion cannot update React', async (t) => {
  const { clock, intervals } = reviewClock(t);
  let posted = 0, release;
  t.mock.method(globalThis, 'fetch', (url, options) => {
    if (options.method === 'GET') return Promise.resolve({ ok: true, json: async () => ({ rev: 1, view: atEmpty(1700000001) }) });
    posted += 1;
    return new Promise((resolve) => { release = () => resolve({ ok: true, json: async () => ({ ok: true, rev: 2, view: frontView }) }); });
  });
  const runtime = mountOpenedOverlay(clock);
  runtime.render(); await flushClient(runtime);
  clock.tick(1000); await flushClient(runtime);
  assert.equal(posted, 1);
  runtime.unmount(); release();
  await new Promise((resolve) => setImmediate(resolve));
  clock.tick(999999);
  assert.equal(posted, 1); assert.equal(clock.pending, 0); assert.equal(intervals.size, 0);
  assert.equal(runtime.lateUpdates, 0);
});

test('v0.1.3: neutral forget, transparent correction and centred Next CSS remain scoped in all themes', () => {
  assert(SOURCE.includes('.va-btn-forget{background:var(--va-btn-bg)'));
  assert(SOURCE.includes('.va-btn-correct{background:transparent'));
  assert(SOURCE.includes('.va-btn-correct:hover:not(:disabled){background:transparent'));
  assert(SOURCE.includes('.va-brush-actions .va-btn-centered>.va-key{margin-left:6px;}'));
  assert.equal(SOURCE.includes('.va-btn-centered>.va-key{position:absolute'), false);
  for (const theme of ['dark', 'light', 'sepia', 'green']) {
    const spy = createApiSpy();
    const front = render(Object.assign({}, frontView, { theme }), spy.api);
    assert(findByClass(front, 'va-btn-forget'));
    const wrong = render(Object.assign({}, backNoCorrectView, { theme }), spy.api);
    assert.equal(findByAriaLabel(wrong, '选错了'), null);
    assert(findByClass(wrong, 'va-btn-centered'));
    assert(findByClass(wrong, 'va-btn-label'));
    assert(findByClass(findByAriaLabel(wrong, '下一个'), 'va-key'));
    const right = render(Object.assign({}, backView, { theme }), spy.api);
    assert(findByClass(right, 'va-btn-correct'));
    const rightNext = findByAriaLabel(right, '下一个');
    assert(findByClass(rightNext, 'va-btn-centered'));
    assert(findByClass(rightNext, 'va-key'));
  }
});

test('v0.1.3: branch count/countText is gone but arrows, leaf counts and selected-book totals remain', () => {
  const spy = createApiSpy();
  const tree = render(baseView('books', {
    navLevel: 2, selected: 'leaf', bookStat: '已学 12 / 1,234 词',
    rows: [
      { id: 'main', kind: 'main', text: '主类', count: 987, countText: '987 词' },
      { id: 'group', kind: 'group', text: '子类', count: 654, countText: '654 词' },
      { id: 'leaf', kind: 'book', text: '实际词书', count: 456, countText: '456 词' },
    ],
  }), spy.api);
  for (const label of ['进入 主类', '进入 子类']) {
    const row = findByAriaLabel(tree, label);
    const text = testing.collectText(row);
    assert(text.includes('›')); assert(!/987|654/.test(text));
    row.props.onClick(fakeEvent());
  }
  assert(testing.collectText(findByAriaLabel(tree, '选择 实际词书')).includes('456 词'));
  assert(testing.collectText(findByClass(tree, 'va-books-stats')).includes('1,234'));
  assert.deepEqual(spy.calls.send, [{ type: 'book', payload: { id: 'main' } }, { type: 'book', payload: { id: 'group' } }]);
});

test('v0.1.3: hiding immediately prevents due POST, reopening the bubble wakes the empty review', async (t) => {
  const { clock, intervals } = reviewClock(t);
  const requests = mockClientFetch(t, atEmpty(1700000002), () => frontView);
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); let tree = await flushClient(runtime);
    findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
    clock.tick(2000); // before even committing the hidden React render
    tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0);
    assert.equal(intervals.size, 0); assert.equal(clock.pending, 0);
    clock.tick(60000); await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 0);
    const bubble = findElement(tree, (element) => element.type === 'button');
    bubble.props.onClick(fakeEvent());
    tree = runtime.render(); clock.tick(0); tree = await flushClient(runtime);
    assert.equal(actionRequests(requests).length, 1);
    assert(testing.collectText(tree).includes('abandon'));
  } finally { runtime.unmount(); }
  assert.equal(clock.pending, 0);
});

test('v0.1.3: actual title drag/collapse/bubble drag/reopen use one corner on both screen sides', async (t) => {
  const clock = mockTimeoutClock(t);
  const original = { width: bundleWindow.innerWidth, height: bundleWindow.innerHeight };
  bundleWindow.innerWidth = 1400; bundleWindow.innerHeight = 900;
  mockClientFetch(t, frontView);
  const runtime = mountOpenedOverlay(clock);
  try {
    runtime.render(); let tree = await flushClient(runtime);
    for (const [x, y, bubbleX, bubbleY] of [[30, 30, 90, 600], [820, 30, 1270, 600]]) {
      const before = findByClass(tree, 'dsh-vocab-panel').props.style;
      const capture = captureSpy();
      findByClass(tree, 'va-head').props.onPointerDown(fakeEvent({
        button: 0, pointerId: 71, clientX: 0, clientY: 0,
        target: { closest() { return null; } }, currentTarget: capture.node,
      }));
      dispatchWindow('pointermove', { pointerId: 71, clientX: x - parseFloat(before.left), clientY: y - parseFloat(before.top), preventDefault() {} });
      dispatchWindow('pointerup', { pointerId: 71 });
      tree = runtime.render();
      const panel = findByClass(tree, 'dsh-vocab-panel').props.style;
      assert.equal(parseFloat(panel.left), x); assert.equal(parseFloat(panel.top), y);
      const anchor = testing.anchorFromGeometry({ x, y, w: parseFloat(panel.width), h: parseFloat(panel.height) });
      const expected = testing.entryFromAnchor(anchor, WINDOW_PRESETS[0]);
      findByAriaLabel(tree, '关闭浮层').props.onClick(fakeEvent());
      tree = runtime.render();
      let button = findElement(tree, (element) => element.type === 'button');
      assert.equal(parseFloat(button.props.style.left), expected.x);
      assert.equal(parseFloat(button.props.style.top), expected.y);
      const bubbleCapture = captureSpy();
      button.props.onPointerDown(fakeEvent({ button: 0, pointerId: 72, clientX: 0, clientY: 0, currentTarget: bubbleCapture.node }));
      assert.equal(clock.pending, 0, 'closed-entry drag starts without waiting');
      dispatchWindow('pointermove', { pointerId: 72, clientX: bubbleX - expected.x, clientY: bubbleY - expected.y, preventDefault() {} });
      tree = runtime.render();
      dispatchWindow('pointerup', { pointerId: 72 });
      button = findElement(tree, (element) => element.type === 'button');
      button.props.onClick(fakeEvent()); // native follow-up click after drag is suppressed
      tree = runtime.render();
      assert.equal(findByClass(tree, 'dsh-vocab-panel'), null);
      button = findElement(tree, (element) => element.type === 'button');
      button.props.onClick(fakeEvent()); // separate short click reopens
      tree = runtime.render(); clock.tick(0); tree = await flushClient(runtime);
      const restored = findByClass(tree, 'dsh-vocab-panel').props.style;
      const movedAnchor = testing.anchorFromEntry({ x: bubbleX, y: bubbleY }, WINDOW_PRESETS[0]);
      const fitted = testing.geometryFromAnchor(movedAnchor, WINDOW_PRESETS[0]);
      assert.equal(parseFloat(restored.left), fitted.x); assert.equal(parseFloat(restored.top), fitted.y);
      assert.deepEqual(capture.released, [71]); assert.deepEqual(bubbleCapture.released, [72]);
    }
  } finally {
    runtime.unmount(); bundleWindow.innerWidth = original.width; bundleWindow.innerHeight = original.height;
  }
  assert.equal(runtime.lateUpdates, 0);
});
