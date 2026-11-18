/**
 * 背单词 DSH 版状态机：把桌面版 app/main.py 的 Card 界面状态机移植成
 * “动作 → 视图模型”的纯业务引擎。
 *
 * 设计约束（CONTRACT 第 2/4/5 节）：
 *  - 持久化文档 {schema, revision, updatedAt, progress, window}；
 *  - 一次会改记录的动作：克隆文档 → 计算 → 原子落盘（store.save）→ 递增 revision
 *    → 才替换内存状态并返回视图；落盘失败不改变内存、不推进队列；
 *  - 动作经 Promise 链串行执行；读视图不落盘；
 *  - 视图模型只描述 UI，所有文案中文并与桌面版一致。
 *
 * DSH 0.1.5：移除窗口档位设置，统一迷你（mini，400×400）。
 * 不再有紧凑布局开关/动态键位编辑/恢复默认/清空记录动作；学习键位固定用于提示。
 */
import crypto from 'node:crypto';
import packageManifest from '../../package.json' with { type: 'json' };

import { Store, StorageError } from './store.js';
import { Dataset, formatNumber, parseSeriesId, seriesLabel, bookQuantity } from './dataset.js';
import * as scheduler from '../core/scheduler.js';
import { StudyQueue } from '../core/study_queue.js';
import * as school from '../core/school_knowledge.js';
import * as pred from '../core/prediction.js';
import * as assessmentHistory from '../core/assessment_history.js';
import {
  CATEGORIES,
  isPhrase,
  meaning as entryMeaning,
  memoryInfo,
  pronunciation,
  wordCaption,
} from '../core/entries.js';

// 记录/测量基线不随插件界面版本改变。
export const APP_VERSION = '1.4.3-dsh';
export const PLUGIN_VERSION = packageManifest.version;
export const RESUME_TTL = 30 * 86400;
const TEST_RESET_MARKER = '_v142_test_reset';
const TEST_STATE_FIELDS = [
  'quiz_session', 'quiz_archives', 'history', 'last_test',
  'quiz_from_welcome', 'quiz_declined', 'theta', 'quiz_bank_id',
];
/** 0.1.0 旧偏好：仅兼容清理，不清学习/测试记录。 */
const LEGACY_PREF_FIELDS = ['keybindings', '_v136_defaults_pending'];
const LETTERS = 'ABCD';
const THEMES = {
  light: '亮色',
  dark: '暗色',
  sepia: '米黄',
  green: '护眼绿',
};
const THEME_ORDER = ['light', 'dark', 'sepia', 'green'];
const DEFAULT_THEME = 'light';
const SCREENS = [
  'welcome', 'front', 'back', 'empty', 'choice', 'choice_back', 'settings',
  'books', 'catalog', 'history', 'quiz', 'result', 'summary', 'building',
];
const STUDY_SCREENS = ['front', 'back', 'empty', 'choice', 'choice_back'];

const BINDING_KEYS = ['remember', 'forget', 'choice1', 'choice2', 'choice3', 'choice4', 'unknown', 'next'];
/** 0.1.1 固定学习键位：只用于视图提示，不再从存盘读取/编辑/校验。 */
const DEFAULT_BINDINGS = Object.freeze({
  remember: 'Enter',
  forget: 'Space',
  choice1: '1',
  choice2: '2',
  choice3: '3',
  choice4: '4',
  unknown: 'Space',
  next: 'Enter',
});
const KEY_CAPTIONS = {
  Space: '空格',
  Return: 'Enter',
  Enter: 'Enter',
  Backspace: '退格',
  Delete: 'Del',
  Insert: 'Ins',
  Escape: 'Esc',
  Esc: 'Esc',
  Tab: 'Tab',
  Up: '↑',
  Down: '↓',
  Left: '←',
  Right: '→',
  PgUp: 'PgUp',
  PgDown: 'PgDn',
};

/** 0.1.5 固定为单一迷你窗口；所有旧档位只读兼容为 mini。 */
const DEFAULT_WINDOW_SIZE = 'mini';
const WINDOW_PRESETS = Object.freeze([
  Object.freeze({ key: 'mini', label: '迷你', width: 400, height: 400 }),
]);

const ACTIONS = new Set([
  'answer', 'next', 'choice', 'dontknow', 'correct', 'undo',
  'settings', 'closeSettings', 'theme', 'studyMode', 'school',
  'books', 'book', 'nav', 'start', 'catalog', 'catalogFilter', 'catalogSort',
  'bulkLearn', 'quizStart', 'quizAnswer', 'quizDontknow', 'quizPause',
  'history', 'deleteHistory', 'prediction', 'bands', 'back',
]);

const DEFAULT_WORD_CATEGORIES = Object.freeze(CATEGORIES.map(([key, label]) => [key, label]));

export class ActionError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'ActionError';
    this.code = code;
  }
}

function invalid(message) {
  return new ActionError('invalid', message);
}

function engineClosedError() {
  return new StorageError('插件已停止，记录存储未初始化或已释放。', 'conflict');
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function intLike(value, fallback = 0) {
  try {
    if (typeof value === 'boolean') return fallback;
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.trunc(number);
  } catch {
    return fallback;
  }
}

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function localDateText(timestamp) {
  if (!finiteNumber(timestamp)) return '';
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** 固定键位展示文案（0.1.1 不再支持自定义/捕获/动态校验）。 */
export function keyCaption(binding) {
  const text = String(binding || '');
  if (!text) return '';
  const parts = text.split('+');
  const base = parts.pop();
  return [...parts, KEY_CAPTIONS[base] || base].join('+');
}

/** 固定学习键位视图对象（不读旧存盘自定义配置）。 */
function fixedBindings() {
  return { ...DEFAULT_BINDINGS };
}

function fixedKeyCaptions() {
  const captions = {};
  for (const key of BINDING_KEYS) captions[key] = keyCaption(DEFAULT_BINDINGS[key]);
  return captions;
}

function windowPresetsView() {
  return WINDOW_PRESETS.map((preset) => ({
    key: preset.key,
    label: preset.label,
    width: preset.width,
    height: preset.height,
  }));
}

function storedOrder(orders, bookId) {
  const mode = orders && orders[bookId] && orders[bookId].mode;
  return mode === 'seq' || mode === 'shuffle' ? mode : 'seq';
}

function emptyProgress() {
  return {};
}

function clone(value) {
  return structuredClone(value);
}

export class Engine {
  constructor(options = {}) {
    this.config = isPlainObject(options.config) ? options.config : {};
    this.env = options.env || process.env;
    this.dataset = options.dataset || new Dataset({
      dataDir: this.config.dataDir,
      env: this.env,
    });
    this._nowFn = typeof options.now === 'function' ? options.now : null;
    this._store = null;
    this.doc = null;
    this.ep = null;
    this._readyPromise = null;
    this._readyError = null;
    this._chain = Promise.resolve();
    this._notices = [];
    this._known = new Set();
    this._studyEngine = null;
    this._queueWords = null;
    this._queueKey = null;
    this._catalogCache = null;
    this._statsCache = null;
    this._closed = false;
  }

  // ---------- 生命周期 ----------
  get closed() {
    return this._closed;
  }

  ready() {
    if (this._closed) return Promise.reject(engineClosedError());
    if (this._readyPromise === null) this._readyPromise = this._initialize();
    return this._readyPromise;
  }

  async _initialize() {
    try {
      // 先取进程锁、再 await 数据加载：卸载发生在 await 中时 close() 能立刻
      // 释放锁；加载返回后若已关闭则中止，绝不在关闭之后补取锁。
      if (this._closed) throw engineClosedError();
      this._store = Store.open({
        namespace: this.config.dataNamespace,
        env: this.env,
        homeDir: this.config.homeDir,
      });
      try {
        if (this._closed) throw engineClosedError();
        await this.dataset.load();
        if (this._closed) throw engineClosedError();
        const doc = this._store.doc;
        // Window size is a fixed UI constant; retain legacy window bytes/fields.
        const changed = this._normalizeProgress(doc.progress);
        doc.progress = this._normalizedProgress;
        if (changed) {
          // 迁移/恢复只在启动时落盘一次，不改动 revision（还不是用户动作）。
          try {
            this._store.save(doc);
          } catch (error) {
            this._notices.push(`迁移结果暂未写入：${error.message || error}`);
          }
        }
        this.doc = doc;
        this.ep = this._freshEp();
        this._refreshRuntime();
        this._startup();
        return this;
      } catch (error) {
        const store = this._store;
        this._store = null;
        try {
          if (store) store.close();
        } catch {
          /* ignore */
        }
        throw error;
      }
    } catch (error) {
      this._readyError = error;
      throw error;
    }
  }

  async close() {
    if (this._closed) return;
    this._closed = true;
    const cancellation = typeof this.dataset.cancelQuizBankBuild === 'function'
      ? this.dataset.cancelQuizBankBuild() : null;
    const store = this._store;
    this._store = null;
    if (store) {
      try {
        store.close();
      } catch {
        /* 卸载路径不抛错；释放失败会记录在 store.notes 中 */
      }
    }
    if (cancellation) await cancellation.catch(() => {});
  }

  _now() {
    return this._nowFn ? Number(this._nowFn()) : Date.now() / 1000;
  }

  _notice(message) {
    if (message && !this._notices.includes(message)) this._notices.push(message);
  }

  storageNote() {
    const notes = [];
    if (this._store) notes.push(this._store.storageNote);
    notes.push(...this._notices);
    return notes.filter(Boolean).join('\n');
  }

  get revision() {
    return this.doc ? this.doc.revision : null;
  }

  state() {
    if (this._closed) throw engineClosedError();
    return { rev: this.doc.revision, view: this.view() };
  }

  // ---------- 动作调度（串行） ----------
  async applyAction(envelope) {
    if (this._closed) throw engineClosedError();
    if (this._readyError) throw this._readyError;
    // A request received during preparation must not wait behind the build:
    // it could otherwise run after completion and start a second fresh quiz.
    if (this.ep && this.ep.building) {
      return {
        ok: false,
        code: 'conflict',
        message: '正在构建测评题库，请稍候',
        rev: this.doc.revision,
        view: this.view(),
      };
    }
    const run = this._chain.then(() => this._applyNow(envelope));
    this._chain = run.then(
      () => undefined,
      () => undefined,
    );
    return run;
  }

  /** 等待后台任务（题库构建等）结束；测试与优雅关闭用。 */
  async idle() {
    await this._chain;
  }

  _enqueue(task) {
    const run = this._chain.then(async () => {
      // Promise microtasks alone do not let the initial building HTTP response
      // reach the browser before the synchronous FrequencyBank computation.
      // Keep the task serialized, but cross an event-loop turn before starting it.
      await new Promise((resolve) => setTimeout(resolve, 0));
      if (this._closed) return undefined; // 卸载后排队任务一律不执行（不再落盘）
      return task();
    });
    this._chain = run.then(
      () => undefined,
      (error) => {
        this._notice(`后台任务失败：${error && error.message ? error.message : error}`);
      },
    );
    return run;
  }

  async _applyNow(envelope) {
    if (this._closed || this._store === null) {
      return {
        ok: false,
        code: 'conflict',
        message: '插件已停止，记录存储已释放',
        rev: this.doc ? this.doc.revision : null,
        view: this.doc ? this.view() : null,
      };
    }
    if (!this.doc || !this.ep) {
      return {
        ok: false,
        code: 'failed',
        message: '记录尚未加载完成',
        rev: null,
        view: null,
      };
    }
    if (this.ep.building) {
      return {
        ok: false,
        code: 'conflict',
        message: '正在构建测评题库，请稍候',
        rev: this.doc.revision,
        view: this.view(),
      };
    }
    if (!Number.isInteger(envelope.rev) || envelope.rev !== this.doc.revision) {
      return {
        ok: false,
        code: 'stale',
        message: 'rev 与当前记录不一致，请刷新视图',
        rev: this.doc.revision,
        view: this.view(),
      };
    }
    if (!ACTIONS.has(envelope.type)) {
      return {
        ok: false,
        code: 'invalid',
        message: `未知的动作类型：${envelope.type}`,
        rev: this.doc.revision,
        view: this.view(),
      };
    }
    const handler = this[`_action_${envelope.type}`];
    if (typeof handler !== 'function') {
      return {
        ok: false,
        code: 'invalid',
        message: `动作暂未实现：${envelope.type}`,
        rev: this.doc.revision,
        view: this.view(),
      };
    }
    try {
      await handler.call(this, isPlainObject(envelope.payload) ? envelope.payload : {});
      return { ok: true, rev: this.doc.revision, view: this.view() };
    } catch (error) {
      if (error instanceof ActionError) {
        return {
          ok: false,
          code: error.code,
          message: error.message,
          rev: this.doc.revision,
          view: this.view(),
        };
      }
      if (error instanceof StorageError) {
        return {
          ok: false,
          code: error.code || 'failed',
          message: error.message,
          rev: this.doc.revision,
          view: this.view(),
        };
      }
      return {
        ok: false,
        code: 'failed',
        message: `操作未完成：${error && error.message ? error.message : error}`,
        rev: this.doc.revision,
        view: this.view(),
      };
    }
  }

  // ---------- 事务 ----------
  _begin(persist) {
    return {
      persist: Boolean(persist),
      draft: persist ? clone(this.doc) : null,
      ep: clone(this.ep),
    };
  }

  _commit(t, { requirePersist = false } = {}) {
    if (this._closed || this._store === null) throw engineClosedError();
    let doc = this.doc;
    if (t.persist) {
      const draft = t.draft;
      draft.updatedAt = Math.floor(this._now());
      draft.revision = this.doc.revision + 1;
      this._store.save(draft);
      doc = draft;
    } else if (requirePersist) {
      throw new ActionError('failed', '该操作必须落盘');
    }
    this.doc = doc;
    this.ep = t.ep;
    this._refreshRuntime();
    this._studyEngine = null;
  }

  /** 纯内存动作：只替换临时状态。 */
  _commitEp(ep) {
    this.ep = ep;
  }

  _refreshRuntime() {
    const p = this.doc.progress;
    this._known = this._buildKnown(p);
    this._studyEngine = null;
  }

  _buildKnown(p) {
    const known = new Set();
    const data = p.prediction_state;
    if (isPlainObject(data) && Array.isArray(data.selected)) {
      for (const key of data.selected) if (typeof key === 'string') known.add(key);
    }
    const schoolKnown = this.dataset.schoolWords(school.normalize(p.school_knowledge));
    for (const key of schoolKnown) known.add(key);
    return known;
  }

  // ---------- 进度迁移 / 校验（对齐 main.py _load_progress） ----------
  _normalizeProgress(raw) {
    const p = raw;
    this._normalizedProgress = p;
    let changed = false;
    // 0.1.0 旧偏好（自定义键位/恢复默认日志等）只做兼容清理，不动业务记录。
    for (const name of LEGACY_PREF_FIELDS) {
      if (name in p) {
        delete p[name];
        changed = true;
      }
    }
    delete p.input_mode;
    delete p.catalog_sort;
    if (p.states === undefined) p.states = {};
    if (p.study_records === undefined) {
      p.study_records = {};
      changed = true;
    }
    const resetTests = p[TEST_RESET_MARKER] !== 1;
    if (resetTests) {
      for (const name of TEST_STATE_FIELDS) delete p[name];
      p[TEST_RESET_MARKER] = 1;
      changed = true;
    }
    for (const field of ['states', 'cursors', 'orders', 'study_records']) {
      if (field in p && !isPlainObject(p[field])) {
        throw new StorageError(`记录中的 ${field} 格式异常；原文件未清空。`);
      }
    }
    if ('history' in p && !Array.isArray(p.history)) {
      throw new StorageError('词汇量测试历史格式异常；原文件未清空。');
    }
    if ('quiz_archives' in p && !Array.isArray(p.quiz_archives)) {
      throw new StorageError('旧测验归档格式异常；原文件未清空。');
    }
    for (const field of ['states', 'orders', 'study_records']) {
      const value = p[field] || {};
      if (Object.values(value).some((item) => !isPlainObject(item))) {
        throw new StorageError(`记录中的 ${field} 条目格式异常；原文件未清空。`);
      }
    }
    for (const record of Object.values(p.study_records || {})) {
      const pending = record.pending === undefined ? {} : record.pending;
      if (!isPlainObject(pending)) {
        throw new StorageError('学习队列内部格式异常；原文件未清空。');
      }
      for (const key of ['current', 'held_current']) {
        if (record[key] !== undefined && record[key] !== null && !isPlainObject(record[key])) {
          throw new StorageError('学习队列内部格式异常；原文件未清空。');
        }
      }
    }
    for (const item of p.history || []) {
      if (!isPlainObject(item) || !finiteNumber(item.ts) || !finiteNumber(item.vocab)) {
        throw new StorageError('词汇量测试历史条目异常；原文件未清空。');
      }
    }
    if ('prediction_state' in p) {
      try {
        pred.validatePredictionData(p.prediction_state);
      } catch (error) {
        throw new StorageError(`预测掌握记录格式异常；原文件未清空。${error.message || error}`);
      }
    }
    const legacy = p.memory_schema !== 2;
    p.states = scheduler.migrateStates(p.states || {}, legacy);
    p.memory_schema = 2;
    p.app_version = APP_VERSION;
    p.study_mode = p.study_mode === 'choice' ? 'choice' : 'brush';
    if (this._normalizeRetryGap(p)) changed = true;
    if (!(p.theme in THEMES)) {
      if (p.theme !== undefined) changed = true;
      p.theme = DEFAULT_THEME;
    }
    if (!('book' in p)) {
      p.book = null;
      changed = true;
    }
    if (p.cursors === undefined) p.cursors = {};
    if (p.orders === undefined) p.orders = {};
    delete p.cursor;
    const books = this.dataset.books;
    if (p.book && Object.prototype.hasOwnProperty.call(books.LEGACY, p.book)) {
      p.book = books.LEGACY[p.book];
      changed = true;
    }
    for (const [oldId, newId] of Object.entries(books.LEGACY)) {
      if (isPlainObject(p.orders[oldId]) && !(newId in p.orders)) {
        p.orders[newId] = p.orders[oldId];
        changed = true;
      }
      if (p.cursors[oldId] !== undefined && !(newId in p.cursors)) {
        p.cursors[newId] = p.cursors[oldId];
        changed = true;
      }
    }
    if (!('book_confirmed' in p)) {
      const saved = p.book;
      const oldDefaults = new Set([books.DEFAULT, 'cet6', 'cet6-all']);
      const savedMode = saved && p.orders[saved] ? p.orders[saved].mode : undefined;
      p.book_confirmed = Boolean(
        Object.keys(p.states || {}).length
        || (saved && !oldDefaults.has(saved))
        || savedMode === 'seq',
      );
      changed = true;
    }
    if (p.book_confirmed) {
      if (!p.book) {
        p.book = books.DEFAULT;
        changed = true;
      } else {
        // 兼容旧 id / 失效 id / 教材系列伪 id：运行时一律用解析后的真实词书 id，
        // 避免 states/study_records 在失效 id 上另开一份队列。
        const resolved = this.dataset.resolveSavedBook(p.book);
        if (resolved !== p.book) {
          p.book = resolved;
          changed = true;
        }
      }
    } else if (p.book !== null) {
      p.book = null;
      changed = true;
    }
    if (!('welcome_done' in p)) {
      p.welcome_done = Boolean(p.book_confirmed || (p.history || []).length);
      changed = true;
    }
    if (!('prediction_state' in p)) {
      p.prediction_state = pred.newPredictionData();
      changed = true;
    }
    return changed;
  }

  _normalizeRetryGap(p) {
    if (p.retry_gap === 4) return false;
    if (p.retry_gap === 3) {
      for (const record of Object.values(p.study_records || {})) {
        if (!isPlainObject(record) || !isPlainObject(record.pending)) continue;
        const newCount = 'new_count' in record ? record.new_count : 0;
        if (!Number.isSafeInteger(newCount) || newCount < 0) continue;
        for (const key of Object.keys(record.pending)) {
          const target = record.pending[key];
          // Ready and malformed values are opaque; never infer a deadline.
          if (Number.isSafeInteger(target) && target > newCount && target < Number.MAX_SAFE_INTEGER) {
            record.pending[key] = target + 1;
          }
        }
      }
    }
    p.retry_gap = 4;
    return true;
  }

  // ---------- 临时状态 ----------
  _freshEp() {
    return {
      screen: 'front',
      booksSrc: 'welcome',
      navLevel: 1,
      navMain: null,
      navGroup: null,
      selBook: null,
      selOrder: 'seq',
      orderExplicit: false,
      catalogSrc: 'books',
      catalog: null,
      preSettingsMode: 'front',
      settingsStudyModeStart: 'brush',
      schoolChanged: false,
      resultCtx: 'test',
      queue: [],
      qi: 0,
      // 仅当前 choice 学习会话的临时跳过集合：不落盘、不写 states/pending。
      // 并入 StudyQueue 的 excluded 后，Next 会真正推进而不是复用 current。
      skipKeys: [],
      snapshot: null,
      lastAction: null,
      corrected: false,
      choice: null,
      choiceLocked: false,
      choicePicked: null,
      quiz: null,
      result: null,
      lastTest: null,
      report: null,
      waitingDue: null,
      building: null,
      pendingQuiz: null,
    };
  }

  _startup() {
    this._startupFor(this.doc.progress, this.ep);
  }

  _startupFor(p, ep) {
    if (!p.book_confirmed) {
      this._openBooks(p, ep, 'welcome');
      return;
    }
    this._newSession(p, ep);
  }

  // ---------- 词书 / 队列 ----------
  _bookWords(bookId) {
    return this.dataset.bookWordEntries(bookId);
  }

  _seed(p, bookId) {
    if (!bookId) return 0;
    if (!isPlainObject(p.orders[bookId])) p.orders[bookId] = { mode: 'seq' };
    const record = p.orders[bookId];
    if (!Number.isInteger(record.seed)) {
      record.seed = crypto.randomInt(1, 1 << 30);
    }
    return record.seed;
  }

  _orderWords(words, mode, seed) {
    const out = words.slice();
    if (mode === 'shuffle') {
      let state = (intLike(seed, 1) >>> 0) || 1;
      const next = () => {
        state = (state + 0x6d2b79f5) >>> 0;
        let value = state;
        value = Math.imul(value ^ (value >>> 15), value | 1);
        value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
        return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
      };
      for (let index = out.length - 1; index > 0; index -= 1) {
        const swap = Math.floor(next() * (index + 1));
        const temp = out[index];
        out[index] = out[swap];
        out[swap] = temp;
      }
    } else if (mode === 'reverse') {
      out.reverse();
    }
    return out;
  }

  _queueWordsFor(p) {
    const bookId = p.book;
    if (!bookId) return [];
    const mode = storedOrder(p.orders, bookId);
    const seed = this._seed(p, bookId);
    const key = `${bookId}|${mode}|${seed}`;
    if (this._queueWords !== null && this._queueKey === key) return this._queueWords;
    this._queueWords = this._orderWords(this._bookWords(bookId), mode, seed);
    this._queueKey = key;
    return this._queueWords;
  }

  _makeEngine(p, ep) {
    const bookId = p.book;
    if (!bookId || !p.book_confirmed) {
      this._studyEngine = null;
      return null;
    }
    const record = p.study_records[bookId]
      || (p.study_records[bookId] = { cursor: intLike(p.cursors[bookId], 0) });
    this._studyEngine = new StudyQueue(
      this._queueWordsFor(p),
      p.states,
      record,
      {
        retryGap: 4,
        known: this._known,
        excluded: this._excludedFor(p, ep),
      },
    );
    return this._studyEngine;
  }

  /**
   * 学校已认识范围 + 当前 choice 会话的临时跳过词。
   * 返回新 Set：临时跳过只影响本次引擎选择，绝不写入 progress。
   */
  _excludedFor(p, ep) {
    const excluded = this.dataset.schoolWords(school.normalize(p.school_knowledge));
    if (ep && Array.isArray(ep.skipKeys)) {
      for (const key of ep.skipKeys) {
        if (typeof key === 'string' && key) excluded.add(key);
      }
    }
    return excluded;
  }

  /** 选择题无法出题时，把当前词加入临时跳过集（不判定对错、不写记录）。 */
  _skipUnavailableChoiceWord(ep) {
    const record = this._queueRecord(ep);
    if (!record) return;
    if (!Array.isArray(ep.skipKeys)) ep.skipKeys = [];
    if (!ep.skipKeys.includes(record.key)) ep.skipKeys.push(record.key);
  }

  _pullNew(p, ep) {
    if (!this._studyEngine) this._makeEngine(p, ep);
    if (!this._studyEngine) return false;
    const item = this._studyEngine.next(this._now());
    p.cursors[p.book] = this._studyEngine.cursor;
    if (item === null || item === undefined) return false;
    ep.queue.push({ kind: item.kind, key: item.w.w, idx: item.idx });
    ep.qi = ep.queue.length - 1;
    return true;
  }

  _queueRecord(ep) {
    if (!ep.queue.length) return null;
    const index = Math.min(Math.max(0, ep.qi), ep.queue.length - 1);
    return ep.queue[index];
  }

  _queueEntry(p, ep) {
    const record = this._queueRecord(ep);
    if (!record) return null;
    return this.dataset.decoratedEntry(record.key, this.dataset.bookLevel(p.book));
  }

  _itemForAnswer(p, ep) {
    const record = this._queueRecord(ep);
    if (!record) throw invalid('当前没有待回答的卡片');
    const entry = this.dataset.decoratedEntry(record.key, this.dataset.bookLevel(p.book));
    if (!entry) throw invalid('当前词条不在词库中');
    return { kind: record.kind, w: entry, st: p.states[record.key], idx: record.idx };
  }

  _captureStudy(p, ep) {
    const bookId = p.book;
    return {
      states: clone(p.states),
      record: bookId && p.study_records[bookId] ? clone(p.study_records[bookId]) : null,
      cursors: clone(p.cursors),
      qi: ep.qi,
      book: bookId,
      queue: ep.queue.slice(),
      lastAction: ep.lastAction ? { ...ep.lastAction } : null,
      corrected: ep.corrected,
    };
  }

  _restoreStudy(p, ep, snapshot) {
    if (!snapshot || snapshot.book !== p.book) return false;
    p.states = clone(snapshot.states);
    if (snapshot.record === null) delete p.study_records[snapshot.book];
    else p.study_records[snapshot.book] = clone(snapshot.record);
    p.cursors = clone(snapshot.cursors);
    ep.queue = snapshot.queue.slice();
    ep.qi = snapshot.qi;
    ep.lastAction = snapshot.lastAction ? { ...snapshot.lastAction } : null;
    ep.corrected = snapshot.corrected;
    ep.choice = null;
    ep.choiceLocked = false;
    ep.choicePicked = null;
    this._studyEngine = null;
    return true;
  }

  // ---------- 页面切换（只改临时状态） ----------
  _openBooks(p, ep, src) {
    ep.booksSrc = typeof src === 'string' && src ? src : 'welcome';
    ep.orderExplicit = false;
    ep.selBook = ep.booksSrc === 'settings' ? (p.book || null) : null;
    ep.selOrder = ep.selBook ? storedOrder(p.orders, ep.selBook) : 'seq';
    ep.navLevel = 1;
    ep.navMain = null;
    ep.navGroup = null;
    ep.screen = 'books';
  }

  _openSettings(p, ep) {
    const brushScreens = STUDY_SCREENS;
    if (brushScreens.includes(ep.screen)) {
      ep.preSettingsMode = ep.screen;
      ep.settingsStudyModeStart = p.study_mode;
      ep.schoolChanged = false;
    }
    if (!p.book_confirmed && (ep.screen === 'books' || ep.screen === 'welcome')) {
      ep.preSettingsMode = 'front';
    }
    ep.screen = 'settings';
  }

  _openCatalog(p, ep, bookId, src) {
    const mode = src === 'books' ? ep.selOrder : storedOrder(p.orders, bookId);
    ep.catalogSrc = src;
    ep.catalog = {
      book: bookId,
      src,
      filter: 'all',
      query: '',
      sortByLevel: false,
      mode,
      preserveOrder: mode === 'shuffle',
    };
    ep.screen = 'catalog';
  }

  _emptyNote(p, ep) {
    const due = ep.waitingDue;
    if (finteOrNull(due)) {
      const minutes = Math.max(1, Math.ceil((due - this._now()) / 60));
      return `下次复习约 ${minutes} 分钟后\n到期会自动出现`;
    }
    return '当前没有新词和到期词\n可在设置中查看或更换词书';
  }

  _showEmpty(p, ep) {
    ep.waitingDue = this._studyEngine ? this._studyEngine.nextDueTime(this._now()) : null;
    ep.screen = 'empty';
    ep.choice = null;
    ep.choiceLocked = false;
    ep.status = '';
  }

  _showCurrent(p, ep) {
    if (!ep.queue.length) {
      this._showEmpty(p, ep);
      return;
    }
    ep.qi = Math.min(Math.max(0, ep.qi), ep.queue.length - 1);
    ep.choice = null;
    ep.choiceLocked = false;
    ep.choicePicked = null;
    ep.corrected = false;
    if (p.study_mode === 'choice') {
      const entry = this._queueEntry(p, ep);
      if (!entry) {
        this._showEmpty(p, ep);
        return;
      }
      const question = this._buildChoiceQuestion(p, ep, entry);
      if (question === null) {
        // 选择题模式绝不回退到刷词 front（否则会暴露释义/认识按钮）：
        // 保持 choice 屏并标记不可作答，由 next 跳到下一词。
        ep.choice = null;
        ep.choiceLocked = true;
        ep.screen = 'choice';
        return;
      }
      ep.choice = question;
      ep.screen = 'choice';
    } else {
      ep.screen = 'front';
    }
  }

  _buildChoiceQuestion(p, ep, entry) {
    const stage = this.dataset.bookLevel(p.book);
    const record = this._queueRecord(ep);
    const material = `${p.book}|${record ? record.key : ''}|${ep.qi}|${p.orders[p.book] ? p.orders[p.book].seed || 0 : 0}`;
    const attempt = (pool) => {
      try {
        return this.dataset.makeOptions(entry, pool, material);
      } catch (error) {
        return null;
      }
    };
    if (stage) {
      let question = attempt(this.dataset.bookOptionPool(p.book, stage));
      if (question === null) question = attempt(this.dataset.stageOptionPool(stage));
      if (question !== null) {
        return { keys: record ? [record.key] : [], options: question.options, correct: question.correct };
      }
    }
    const key = isPhrase(entry) ? 'phrase' : 'word';
    const entries = key === 'phrase' ? this.dataset.phrases : this.dataset.bank;
    let question = attempt(this.dataset.entriesOptionPool(key, entries));
    if (question === null) {
      question = attempt(this.dataset.entriesOptionPool('all', this.dataset.allEntries));
    }
    if (question === null) {
      this._notice('当前词条无法生成四选一题目，已跳过该题。');
      return null;
    }
    return { keys: [], options: question.options, correct: question.correct };
  }

  _newSession(p, ep) {
    if (!p.book_confirmed || !p.book) {
      this._openBooks(p, ep, 'welcome');
      return false;
    }
    this._studyEngine = null;
    ep.queue = [];
    ep.qi = 0;
    ep.snapshot = null;
    ep.lastAction = null;
    ep.corrected = false;
    ep.choice = null;
    ep.choiceLocked = false;
    ep.choicePicked = null;
    this._makeEngine(p, ep);
    if (!this._pullNew(p, ep)) {
      this._showEmpty(p, ep);
      return false;
    }
    this._showCurrent(p, ep);
    return true;
  }

  _next0(p, ep) {
    this._makeEngine(p, ep);
    ep.qi += 1;
    if (!this._pullNew(p, ep)) {
      this._showEmpty(p, ep);
      return;
    }
    ep.qi = ep.queue.length - 1;
    this._showCurrent(p, ep);
  }

  _answerCurrent(p, ep, remember) {
    this._makeEngine(p, ep);
    const item = this._itemForAnswer(p, ep);
    ep.snapshot = this._captureStudy(p, ep);
    ep.corrected = false;
    this._studyEngine.answer(item, Boolean(remember), this._now());
    p.cursors[p.book] = this._studyEngine.cursor;
    ep.lastAction = { kind: item.kind, key: item.w.w, remember: Boolean(remember) };
  }

  _canCorrect(ep) {
    return (ep.screen === 'back' || ep.screen === 'choice_back')
      && Boolean(ep.lastAction && ep.lastAction.remember)
      && !ep.corrected
      && ep.snapshot !== null;
  }

  _startLearning(p, ep) {
    const selected = ep.selBook;
    if (!selected) return false;
    const newBook = selected !== p.book;
    const oldMode = isPlainObject(p.orders[selected]) && p.orders[selected].mode
      ? p.orders[selected].mode : 'seq';
    if (newBook) p.book = selected;
    const currentMode = storedOrder(p.orders, p.book);
    if (newBook || ep.selOrder !== currentMode || ep.selOrder !== oldMode) {
      if (!isPlainObject(p.orders[p.book])) p.orders[p.book] = { mode: ep.selOrder };
      const record = p.orders[p.book];
      record.mode = ep.selOrder;
      if (!Number.isInteger(record.seed)) record.seed = crypto.randomInt(1, 1 << 30);
      p.cursors[p.book] = 0;
      this._queueWords = null;
      this._queueKey = null;
      if (oldMode !== ep.selOrder && p.study_records[p.book]) {
        const saved = p.study_records[p.book];
        saved.cursor = 0;
        saved.current = null;
        saved.held_current = null;
      }
    } else {
      p.cursors[p.book] = intLike(p.cursors[p.book], 0);
    }
    p.book = p.book || selected;
    p.book_confirmed = true;
    p.welcome_done = true;
    delete p.quiz_from_welcome;
    ep.selBook = p.book;
    this._queueWords = null;
    this._queueKey = null;
    this._studyEngine = null;
    this._newSession(p, ep);
    return true;
  }

  _restoreStudyScreen(p, ep, mode) {
    if (!STUDY_SCREENS.includes(mode) && mode !== 'empty') {
      ep.screen = 'front';
      return;
    }
    if (!ep.queue.length) {
      this._newSession(p, ep);
      return;
    }
    if (mode === 'empty') {
      ep.screen = 'empty';
      this._showEmpty(p, ep);
      return;
    }
    if (mode === 'back' || mode === 'choice_back') {
      ep.screen = mode;
      return;
    }
    this._showCurrent(p, ep);
  }

  // ---------- 统计 ----------
  _bookStats(p, bookId) {
    if (!bookId) return { learned: 0, known: 0, mastered: 0, total: 0, predicted: 0 };
    const cacheKey = `${this.doc.revision}|${bookId}|${p.school_knowledge || ''}`;
    if (this._statsCache && this._statsCache.key === cacheKey) return this._statsCache.value;
    const excluded = this.dataset.schoolWords(school.normalize(p.school_knowledge));
    const words = this.dataset.bookWordStrs(bookId).filter((key) => !excluded.has(key));
    let learned = 0;
    let mastered = 0;
    let known = 0;
    let predicted = 0;
    for (const key of words) {
      const [category] = memoryInfo(key, p.states, null, this._known);
      if (category === 'mastered') {
        learned += 1;
        mastered += 1;
      } else if (category === 'predicted') {
        known += 1;
        predicted += 1;
      } else if (category === 'known') {
        known += 1;
        if (Object.prototype.hasOwnProperty.call(p.states, key)) learned += 1;
      }
    }
    const value = { learned, known, mastered, total: words.length, predicted };
    this._statsCache = { key: cacheKey, value };
    return value;
  }

  // ---------- 测验辅助 ----------
  _maxItems() {
    return this.dataset.vt ? this.dataset.vt.MAX_ITEMS : 80;
  }

  _quizRemainingDays(p, session, now = null, validateBank = true) {
    const vt = this.dataset.vt;
    if (!vt || !isPlainObject(session) || session.resume_disabled
        || session.algo !== vt.ALGORITHM) {
      return 0;
    }
    try {
      if (validateBank) {
        if (!this.dataset.quizBankBuilt) return 0;
        if (!vt.validateSession(session, this.dataset.getQuizBank())) return 0;
      }
      const stamp = now === null || now === undefined ? this._now() : Number(now);
      const started = session.started_at;
      if (!finiteNumber(stamp) || !finiteNumber(started) || started > stamp) return 0;
      return Math.min(30, Math.max(0, Math.ceil((RESUME_TTL - (stamp - started)) / 86400)));
    } catch {
      return 0;
    }
  }

  _quizGenItem(ep) {
    const vt = this.dataset.vocabularyTest;
    const bank = this.dataset.getQuizBank();
    const record = vt.nextItem(bank, ep.quiz.state, ep.quiz.items, ep.quiz.resp);
    if (record === null || record === undefined) return null;
    ep.quiz.items.push(record);
    ep.quiz.state.asked.push(record.key);
    return record;
  }

  _quizHistoryRecord(p, ep, completed = false, session = null) {
    const vt = this.dataset.vocabularyTest;
    const bank = this.dataset.getQuizBank();
    let responses;
    let items;
    let sessionId;
    let started;
    if (session !== null && session !== undefined) {
      if (!vt.validateSession(session, bank)) return null;
      responses = session.resp;
      items = session.items;
      sessionId = session.id;
      started = session.started_at;
    } else {
      responses = ep.quiz.resp;
      items = ep.quiz.items;
      sessionId = ep.quiz.sessionId;
      started = ep.quiz.startedAt;
    }
    if (!responses || !responses.length) return null;
    const measurement = vt.summarize(bank, items, responses);
    const history = Array.isArray(p.history) ? p.history : [];
    const existing = history.find((row) => row && row.id === sessionId) || null;
    const baseline = existing
      ? Boolean(existing.baseline)
      : !history.some((row) => row && assessmentHistory.isCurrent(row)
        && row.bank_id === bank.fingerprint && row.baseline);
    let timestamp = Math.floor(this._now());
    if (session !== null && session !== undefined) {
      const savedTime = session.updated_at === undefined ? started : session.updated_at;
      timestamp = finiteNumber(savedTime) ? Math.floor(savedTime) : Math.floor(started);
    }
    if (existing && existing.total === responses.length && !completed) {
      timestamp = finiteNumber(existing.ts) ? existing.ts : timestamp;
    }
    return {
      id: sessionId,
      ts: timestamp,
      started_at: started,
      algo: vt.ALGORITHM,
      measurement_schema: vt.MEASUREMENT_SCHEMA,
      bank_id: bank.fingerprint,
      unit: measurement.unit,
      population: bank.size,
      excluded_count: bank.excluded_count,
      theta: measurement.theta,
      se: measurement.se,
      vocab: Math.round(measurement.estimate),
      lo: Math.max(0, Math.round(measurement.low)),
      hi: Math.min(bank.size, Math.round(measurement.high)),
      interval_level: measurement.interval_level,
      estimate_available: measurement.estimate_available,
      provisional: measurement.provisional,
      evidence_limited: measurement.evidence_limited === undefined
        ? !measurement.estimate_available : measurement.evidence_limited,
      right: measurement.correct_count,
      dontknow: measurement.dontknow,
      total: responses.length,
      baseline,
      completed: Boolean(completed),
      coverage: measurement.coverage,
      coverage_target: measurement.coverage_target,
      bands: clone(measurement.bands),
      stop_reason: measurement.stop_reason,
      boundary: measurement.boundary === undefined ? null : measurement.boundary,
      prediction_eligible: false,
    };
  }

  _upsertQuizHistory(p, ep, completed = false, session = null) {
    const record = this._quizHistoryRecord(p, ep, completed, session);
    if (record === null) return null;
    const history = Array.isArray(p.history) ? p.history : (p.history = []);
    const existing = history.find((row) => row && row.id === record.id) || null;
    let stored = record;
    if (existing === null) history.push(record);
    else {
      Object.assign(existing, record);
      stored = existing;
    }
    ep.lastTest = { record: stored, baseline: Boolean(stored.baseline) };
    const meta = session === null || session === undefined ? p.quiz_session : session;
    if (isPlainObject(meta)) {
      meta.history_id = stored.id;
      meta.history_response_count = stored.total;
      meta.history_deleted = false;
    }
    return stored;
  }

  _saveQuizSession(p, ep) {
    const vt = this.dataset.vocabularyTest;
    const bank = this.dataset.getQuizBank();
    if (!isPlainObject(p.quiz_session)) p.quiz_session = {};
    const session = p.quiz_session;
    const previousCount = Number.isInteger(session.history_response_count)
      ? session.history_response_count : 0;
    Object.assign(session, {
      schema: vt.SESSION_SCHEMA,
      algo: vt.ALGORITHM,
      id: ep.quiz.sessionId,
      bank_id: ep.quiz.fingerprint,
      started_at: ep.quiz.startedAt,
      updated_at: Math.floor(this._now()),
      from_welcome: Boolean(ep.quiz.originWelcome),
      state: ep.quiz.state,
      items: ep.quiz.items,
      resp: ep.quiz.resp,
      i: ep.quiz.i,
    });
    if (!vt.validateSession(session, bank)) {
      throw new StorageError('测验快照与当前题库不一致，未覆盖原记录。');
    }
    p.quiz_bank_id = ep.quiz.fingerprint;
    if (ep.quiz.resp.length
        && (!session.history_deleted || ep.quiz.resp.length > previousCount)) {
      this._upsertQuizHistory(p, ep, false, session);
    }
  }

  _startQuizCore(p, ep, origin, fresh) {
    const vt = this.dataset.vocabularyTest;
    const bank = this.dataset.getQuizBank();
    ep.quizReturnToSettings = origin === 'settings'
      || (origin === 'result' && ep.resultCtx === 'history');
    delete p.quiz_declined;
    p.welcome_done = true;
    if (origin === 'welcome' || !p.book_confirmed) p.quiz_from_welcome = true;
    let session = isPlainObject(p.quiz_session) ? p.quiz_session : null;
    const resumable = session !== null
      && vt.validateSession(session, bank)
      && this._quizRemainingDays(p, session, null, false) > 0;
    if (fresh || !resumable) {
      if (session !== null) {
        assessmentHistory.archiveSession(
          p,
          Math.floor(this._now()),
          resumable ? 'new_attempt' : 'incompatible_or_expired',
        );
      }
      delete p.quiz_session;
      session = null;
    }
    if (session !== null) {
      ep.quiz = {
        state: session.state,
        items: session.items,
        resp: session.resp,
        i: session.i,
        startedAt: session.started_at,
        sessionId: session.id,
        fingerprint: session.bank_id,
        originWelcome: Boolean(session.from_welcome),
        returnToSettings: Boolean(ep.quizReturnToSettings),
        locked: false,
        picked: null,
      };
      if (ep.quiz.resp.length === ep.quiz.i + 1) {
        ep.screen = 'quiz';
        ep.quiz.locked = true;
        this._quizNextCore(p, ep, { enter: true });
        return;
      }
    } else {
      ep.quiz = {
        state: vt.newState(crypto.randomInt(1, 1 << 30)),
        items: [],
        resp: [],
        i: 0,
        startedAt: Math.floor(this._now()),
        sessionId: crypto.randomBytes(16).toString('hex'),
        fingerprint: bank.fingerprint,
        originWelcome: origin === 'welcome' || !p.book_confirmed,
        returnToSettings: Boolean(ep.quizReturnToSettings),
        locked: false,
        picked: null,
      };
    }
    if (ep.quiz.items.length <= ep.quiz.i && this._quizGenItem(ep) === null) {
      throw new StorageError('没有足够的有效词频和无重复释义来生成四选一题目；原记录未覆盖。');
    }
    this._saveQuizSession(p, ep);
    ep.screen = 'quiz';
    ep.quiz.locked = false;
    ep.quiz.picked = null;
  }

  _finishQuizCore(p, ep) {
    const fromWelcome = ep.quiz.originWelcome || !p.book_confirmed;
    const record = this._upsertQuizHistory(p, ep, true, null);
    delete p.quiz_session;
    delete p.quiz_from_welcome;
    ep.result = record;
    ep.quiz = null;
    ep.resultCtx = fromWelcome ? 'welcome_test' : 'test';
    ep.screen = fromWelcome ? 'result' : 'summary';
  }

  _quizNextCore(p, ep, options = {}) {
    const vt = this.dataset.vocabularyTest;
    if (!ep.quiz) return;
    if (ep.quiz.resp.length !== ep.quiz.i + 1) return;
    const bank = this.dataset.getQuizBank();
    const summary = vt.summarize(bank, ep.quiz.items, ep.quiz.resp);
    if (summary.stop_reason) {
      this._finishQuizCore(p, ep);
      return;
    }
    const itemCount = ep.quiz.items.length;
    if (this._quizGenItem(ep) === null) {
      this._finishQuizCore(p, ep);
      return;
    }
    ep.quiz.i = itemCount;
    this._saveQuizSession(p, ep);
    ep.quiz.locked = false;
    ep.quiz.picked = null;
    ep.screen = 'quiz';
  }

  _quizAnswerCore(p, ep, choice) {
    const vt = this.dataset.vocabularyTest;
    if (ep.quiz.locked) return false;
    if (ep.quiz.resp.length !== ep.quiz.i) return false;
    const item = ep.quiz.items[ep.quiz.i].item;
    ep.quiz.locked = true;
    ep.quiz.resp.push(choice === -1 ? -1 : Number(choice === item.correct_index));
    const summary = vt.summarize(this.dataset.getQuizBank(), ep.quiz.items, ep.quiz.resp);
    ep.quiz.state.theta = summary.theta;
    ep.quiz.state.se = summary.se;
    ep.quiz.lastAnswerAt = Math.floor(this._now());
    this._saveQuizSession(p, ep);
    ep.quiz.picked = choice;
    ep.screen = 'quiz';
    return true;
  }

  // ---------- 设置 / 键位 / 学校 ----------
  _applyPreference(p, ep, changes) {
    for (const [key, value] of Object.entries(changes)) p[key] = clone(value);
    this._refreshRuntime();
    if (Object.prototype.hasOwnProperty.call(changes, 'theme')) {
      // 主题只影响视图
    }
    if (Object.prototype.hasOwnProperty.call(changes, 'school_knowledge')) {
      this._catalogCache = null;
    }
  }

  _settingsView(p, ep) {
    const meta = p.book ? this.dataset.bookMeta(p.book) : null;
    const stats = p.book ? this._bookStats(p, p.book) : { learned: 0, total: 0 };
    const days = this._quizRemainingDays(p, p.quiz_session, null, false);
    return {
      studyMode: p.study_mode,
      school: school.normalize(p.school_knowledge),
      book: {
        id: p.book || null,
        name: p.book ? this.dataset.bookName(p.book) : '',
        num: stats.learned,
        path: p.book ? this.dataset.bookPath(p.book) : '',
        total: stats.total,
        numText: p.book ? `已学 ${formatNumber(stats.learned)} / ${formatNumber(stats.total)}` : '',
      },
      quiz: { hasSession: Boolean(p.quiz_session), remainingDays: days },
      theme: p.theme,
      themeOptions: THEME_ORDER.filter((key) => key in THEMES).map((key) => ({ key, label: THEMES[key] })),
      schoolOptions: school.LEVELS.map(([key, label]) => ({ key, label })),
      studyModeOptions: [
        { key: 'brush', label: '刷词模式' },
        { key: 'choice', label: '选择题模式' },
      ],
      version: PLUGIN_VERSION,
      title: '设置',
    };
  }

  // ---------- 视图 ----------
  _windowSize() {
    return DEFAULT_WINDOW_SIZE;
  }

  _themeKey(p) {
    return p.theme in THEMES ? p.theme : DEFAULT_THEME;
  }

  _statusText(p, ep) {
    if (ep.screen === 'quiz' && ep.quiz) {
      return `词汇测试 · 已答 ${ep.quiz.resp.length} / 最多${this._maxItems()}`;
    }
    return '';
  }

  _studyStatus(p, ep) {
    const record = this._queueRecord(ep);
    if (!record || ep.screen === 'empty') return '';
    return record.kind === 'review' ? '复习' : '新词';
  }

  _labels(ep) {
    switch (ep.screen) {
      case 'front':
        return { remember: '认识', forget: '不认识' };
      case 'back':
        return { wrong: '选错了', next: '下一个' };
      case 'empty':
        return { next: '检查复习' };
      case 'choice':
        return ep.choice ? { dontknow: '不认识' } : { next: '下一个' };
      case 'choice_back':
        return { next: '下一个' };
      case 'quiz':
        return { dontknow: '不认识', pause: '暂停并退出' };
      default:
        return {};
    }
  }

  _keyCaptions() {
    return fixedKeyCaptions();
  }

  _wordView(p, entry, reveal) {
    if (!entry) return null;
    return {
      w: wordCaption(entry),
      ipa: pronunciation(entry),
      meaning: reveal ? entryMeaning(entry) : '',
    };
  }

  _studyScreenCommon(p, ep) {
    const record = this._queueRecord(ep);
    const state = record ? (p.states[record.key] || {}) : {};
    const stats = p.book ? this._bookStats(p, p.book) : { learned: 0, total: 0 };
    return {
      kind: record ? record.kind : null,
      studyStatus: this._studyStatus(p, ep),
      canUndo: ep.snapshot !== null && STUDY_SCREENS.includes(ep.screen),
      total: stats.total,
      learned: stats.learned,
      due: finiteNumber(state.due) ? state.due : null,
      labels: this._labels(ep),
    };
  }

  view() {
    if (!this.doc || !this.ep) {
      return {
        screen: 'welcome',
        theme: DEFAULT_THEME,
        windowSize: DEFAULT_WINDOW_SIZE,
        windowPresets: windowPresetsView(),
        status: '',
        keys: fixedBindings(),
        keyCaptions: fixedKeyCaptions(),
        storageNote: this.storageNote(),
        bookCount: 0,
        totalWords: 0,
        hasProgress: false,
      };
    }
    const p = this.doc.progress;
    const ep = this.ep;
    const screen = SCREENS.includes(ep.screen) ? ep.screen : 'front';
    const base = {
      screen,
      theme: this._themeKey(p),
      windowSize: this._windowSize(),
      windowPresets: windowPresetsView(),
      status: this._statusText(p, ep),
      keys: fixedBindings(),
      keyCaptions: this._keyCaptions(),
      storageNote: this.storageNote(),
      busy: Boolean(ep.building),
    };
    const specific = this[`_view_${screen}`] ? this[`_view_${screen}`](p, ep) : this._view_front(p, ep);
    return { ...base, ...specific };
  }

  _view_welcome(p, ep) {
    return {
      bookCount: this.dataset.bookCount(),
      totalWords: this.dataset.totalWords(),
      hasProgress: Boolean(p.book_confirmed || (p.history || []).length),
      title: '先测一下词汇量？',
      body: '词频分层与自适应识别测试。结果仅供参考，不改变学习队列。',
      tip: '40–80 题 · 可暂停续测 · 参数未标定',
      actions: [
        { type: 'quizStart', payload: { fresh: true }, label: '测试一下', style: 'primary' },
        { type: 'books', payload: { from: 'welcome' }, label: '不测了，直接开始学', style: 'secondary' },
      ],
    };
  }

  _view_front(p, ep) {
    const entry = this._queueEntry(p, ep);
    const common = this._studyScreenCommon(p, ep);
    return {
      word: this._wordView(p, entry, false),
      learned: common.learned,
      total: common.total,
      due: common.due,
      studyMode: p.study_mode,
      revealed: false,
      kind: common.kind,
      studyStatus: common.studyStatus,
      canUndo: common.canUndo,
      labels: common.labels,
    };
  }

  _view_back(p, ep) {
    const entry = this._queueEntry(p, ep);
    const common = this._studyScreenCommon(p, ep);
    return {
      word: this._wordView(p, entry, true),
      learned: common.learned,
      total: common.total,
      due: common.due,
      studyMode: p.study_mode,
      revealed: true,
      kind: common.kind,
      studyStatus: common.studyStatus,
      canCorrect: this._canCorrect(ep),
      canUndo: common.canUndo,
      labels: common.labels,
    };
  }

  _view_empty(p, ep) {
    const common = this._studyScreenCommon(p, ep);
    return {
      word: {
        w: this.dataset.bookName(p.book),
        ipa: '',
        meaning: this._emptyNote(p, ep),
      },
      learned: common.learned,
      total: common.total,
      due: finteOrNull(ep.waitingDue) ? ep.waitingDue : null,
      studyMode: p.study_mode,
      revealed: true,
      kind: null,
      studyStatus: '',
      canUndo: common.canUndo,
      labels: common.labels,
    };
  }

  _choiceOptionsView(ep, options, answered, correct) {
    return options.map((text, index) => {
      let state = '';
      if (answered) {
        if (index === correct) state = 'ok';
        else if (index === ep.choicePicked) state = 'bad';
      }
      return { index, text, label: `${LETTERS[index]}  ${text}`, state };
    });
  }

  _view_choice(p, ep) {
    const entry = this._queueEntry(p, ep);
    const common = this._studyScreenCommon(p, ep);
    const available = ep.choice !== null;
    const options = available ? ep.choice.options : [];
    return {
      word: entry ? { w: wordCaption(entry), ipa: pronunciation(entry) } : null,
      options: this._choiceOptionsView(ep, options, false, -1),
      locked: ep.choiceLocked || !available,
      unavailable: !available,
      studyMode: p.study_mode,
      revealed: false,
      kind: common.kind,
      studyStatus: common.studyStatus,
      canUndo: common.canUndo,
      labels: common.labels,
    };
  }

  _view_choice_back(p, ep) {
    const entry = this._queueEntry(p, ep);
    const common = this._studyScreenCommon(p, ep);
    const options = ep.choice ? ep.choice.options : [];
    return {
      word: entry ? { w: wordCaption(entry), ipa: pronunciation(entry) } : null,
      options: this._choiceOptionsView(ep, options, true, ep.choice ? ep.choice.correct : -1),
      locked: true,
      studyMode: p.study_mode,
      revealed: true,
      correctIndex: ep.choice ? ep.choice.correct : null,
      kind: common.kind,
      studyStatus: common.studyStatus,
      canCorrect: this._canCorrect(ep),
      canUndo: common.canUndo,
      labels: common.labels,
    };
  }

  _booksRows(p, ep) {
    const books = this.dataset.books;
    if (ep.navLevel === 1) {
      return {
        lead: '选择主类',
        rows: books.mains().map((main) => ({ kind: 'main', id: main.id, text: main.name })),
      };
    }
    if (ep.navLevel === 2) {
      const main = books.mains().find((item) => item.id === ep.navMain) || null;
      if (!main) {
        ep.navLevel = 1;
        ep.navMain = null;
        return this._booksRows(p, ep);
      }
      return {
        lead: main.name,
        rows: main.groups.map((group) => ({
          kind: 'group',
          id: group.id,
          text: group.name,
          count: group.items.length,
        })),
      };
    }
    const group = books.GROUPS[ep.navGroup] || null;
    if (!group) {
      ep.navLevel = 1;
      ep.navGroup = null;
      return this._booksRows(p, ep);
    }
    const rows = [];
    const itemRow = (item) => ({
      kind: item.is_union ? 'union' : 'book',
      id: item.id,
      text: item.display || item.name,
      count: item.count,
      countText: bookQuantity(item),
    });
    if (Array.isArray(group.series) && group.series.length) {
      for (const series of group.series) {
        const items = group.items.filter((item) => (item.series || '') === series);
        rows.push({ kind: 'section', text: `${seriesLabel(series)} · ${items.length} 册` });
        for (const item of items) rows.push(itemRow(item));
      }
      for (const item of group.items) {
        if (!(item.series || '')) rows.push(itemRow(item));
      }
    } else {
      for (const item of group.items) rows.push(itemRow(item));
    }
    return { lead: group.name, rows };
  }

  _view_books(p, ep) {
    const { lead, rows } = this._booksRows(p, ep);
    const selected = ep.selBook || null;
    let stats = { total: 0, learned: 0 };
    let bookStat = '';
    if (selected) {
      const meta = this.dataset.bookMeta(selected);
      stats = {
        total: this.dataset.bookWordStrs(selected).length,
        learned: this._bookStats(p, selected).learned,
      };
      bookStat = `${this.dataset.bookPath(selected)} · ${bookQuantity(meta, stats.total)}`;
    }
    const mains = this.dataset.books.mains().map((main) => ({
      id: main.id,
      name: main.name,
      groups: main.groups.map((group) => ({
        id: group.id,
        name: group.name,
        count: group.items.length,
      })),
    }));
    return {
      mains,
      selected,
      order: ep.selOrder,
      stats,
      canStart: Boolean(selected),
      navLevel: ep.navLevel,
      navMain: ep.navMain,
      navGroup: ep.navGroup,
      lead,
      rows,
      bookStat,
      orderOptions: [
        { key: 'seq', label: '顺序' },
        { key: 'shuffle', label: '乱序' },
      ],
      title: '选择词书',
    };
  }

  _catalogData(p, ep) {
    const catalog = ep.catalog;
    if (!catalog) return null;
    const cacheKey = [
      this.doc.revision, catalog.book, catalog.mode, catalog.filter,
      catalog.query, catalog.sortByLevel ? '1' : '0',
    ].join('|');
    if (this._catalogCache && this._catalogCache.key === cacheKey) {
      return this._catalogCache.value;
    }
    const stage = this.dataset.bookLevel(catalog.book);
    const words = this._orderWords(
      this._bookWords(catalog.book),
      catalog.mode,
      this._seed(p, catalog.book),
    );
    const known = this._known;
    const categoryCounts = { all: 0, learned: 0, unlearned: 0, predicted: 0 };
    const entries = [];
    for (let order = 0; order < words.length; order += 1) {
      const entry = words[order];
      const key = entry.w;
      let category;
      let level;
      let label;
      try {
        [category, level, label] = memoryInfo(key, p.states, null, known);
      } catch {
        [category, level, label] = ['unlearned', null, '待学习'];
      }
      if (!['mastered', 'predicted', 'known', 'unlearned'].includes(category)) {
        category = 'unlearned';
      }
      const meaningText = entryMeaning(entry);
      categoryCounts.all += 1;
      if (category !== 'unlearned') categoryCounts.learned += 1;
      else categoryCounts.unlearned += 1;
      if (category === 'predicted') categoryCounts.predicted += 1;
      entries.push({
        key,
        caption: wordCaption(entry),
        meaning: meaningText,
        memory: label,
        level: Number.isFinite(level) ? level : null,
        category,
        order,
        searchWord: key.toLowerCase(),
        searchMeaning: String(meaningText || '').toLowerCase(),
      });
    }
    const query = catalog.query.trim().toLowerCase();
    let rows = entries;
    if (catalog.filter !== 'all' || query) {
      rows = entries.filter((entry) => {
        if (catalog.filter === 'learned' && entry.category === 'unlearned') return false;
        if (catalog.filter === 'unlearned' && entry.category !== 'unlearned') return false;
        if (query && !entry.searchWord.includes(query) && !entry.searchMeaning.includes(query)) {
          return false;
        }
        return true;
      });
    }
    if (catalog.sortByLevel) {
      rows = rows.slice().sort((left, right) => {
        const leftLevel = left.level === null ? -1 : left.level;
        const rightLevel = right.level === null ? -1 : right.level;
        if (leftLevel !== rightLevel) return rightLevel - leftLevel;
        return left.caption.toLowerCase() < right.caption.toLowerCase() ? -1
          : left.caption.toLowerCase() > right.caption.toLowerCase() ? 1 : 0;
      });
    } else if (catalog.preserveOrder) {
      rows = rows.slice().sort((left, right) => left.order - right.order);
    } else {
      rows = rows.slice().sort((left, right) => {
        const leftText = left.caption.toLowerCase();
        const rightText = right.caption.toLowerCase();
        return leftText < rightText ? -1 : leftText > rightText ? 1 : 0;
      });
    }
    const value = {
      entries,
      rows,
      counts: categoryCounts,
      stage,
    };
    this._catalogCache = { key: cacheKey, value };
    return value;
  }

  _view_catalog(p, ep) {
    const catalog = ep.catalog;
    if (!catalog) {
      return { book: null, rows: [], counts: { all: 0, learned: 0, unlearned: 0 }, filter: 'all', query: '', sortByLevel: false, total: 0, title: '词书内容' };
    }
    const data = this._catalogData(p, ep);
    const meta = this.dataset.bookMeta(catalog.book);
    const rows = data.rows.map((entry) => ({
      key: entry.key,
      caption: entry.caption,
      meaning: entry.meaning,
      memory: entry.memory,
      level: entry.level,
    }));
    return {
      book: {
        id: catalog.book,
        name: this.dataset.bookName(catalog.book),
        path: this.dataset.bookPath(catalog.book),
        count: Number.isFinite(meta.count) ? meta.count : 0,
      },
      rows,
      counts: data.counts,
      filter: catalog.filter,
      query: catalog.query,
      sortByLevel: catalog.sortByLevel,
      total: rows.length,
      title: '词书内容',
      categories: DEFAULT_WORD_CATEGORIES.map(([key, label]) => ({
        key,
        label,
        count: data.counts[key] || 0,
      })),
      orderMode: catalog.mode,
    };
  }

  _historyDetailText(row) {
    const total = intLike(row.total, 0);
    const right = intLike(row.right, 0);
    let text = `本次已作答 ${total} 题，答对 ${right} 题。`;
    if (!row.completed) {
      text += '\n还没测完；开始后 30 天内可以继续。';
    } else if (row.estimate_available !== true) {
      text += '\n题量不足，这次不给出词汇量估计。';
    } else {
      text += `\n估计认识约 ${formatNumber(row.vocab || 0)} 个词；`
        + `参考范围 ${formatNumber(row.lo || 0)}–${formatNumber(row.hi || 0)} 个词。`;
    }
    return text;
  }

  _historyRows(p) {
    const history = Array.isArray(p.history) ? p.history : [];
    const rows = [];
    for (let index = history.length - 1; index >= 0; index -= 1) {
      const row = history[index];
      if (!isPlainObject(row)) continue;
      const current = assessmentHistory.isCurrent(row);
      const available = current
        ? row.estimate_available === true
        : row.estimate_available !== false;
      const stamp = localDateText(row.ts);
      let title;
      if (current && !row.completed) title = `${stamp}  ·  测试未完成`;
      else if (current) title = `${stamp}  ·  ${available ? `${formatNumber(row.vocab)} 词` : '样本不足'}`;
      else title = `${stamp}  ·  旧版记录`;
      const detail = current
        ? this._historyDetailText(row)
        : `旧版记录 · 已答 ${intLike(row.total, 0)} 题；原数值保留，未重新计算。`;
      rows.push({
        index,
        id: row.id === undefined ? null : row.id,
        ts: row.ts,
        tsText: stamp,
        vocab: finiteNumber(row.vocab) ? row.vocab : 0,
        right: intLike(row.right, 0),
        dontknow: intLike(row.dontknow, 0),
        estimate: available ? row.vocab : null,
        interval: available ? [row.lo, row.hi] : null,
        title,
        detail,
        current,
        completed: Boolean(row.completed),
        available,
        baseline: Boolean(row.baseline),
        total: intLike(row.total, 0),
      });
    }
    return rows;
  }

  _historyTrend(p) {
    const history = Array.isArray(p.history) ? p.history : [];
    let bankId = null;
    if (this.dataset.quizBankBuilt) bankId = this.dataset.getQuizBank().fingerprint;
    else if (typeof p.quiz_bank_id === 'string') bankId = p.quiz_bank_id;
    if (!bankId) return [];
    try {
      return assessmentHistory.currentTrend(history, bankId)
        .map((row) => ({ ts: row.ts, vocab: row.vocab }));
    } catch {
      return [];
    }
  }

  _view_history(p, ep) {
    return {
      points: this._historyTrend(p),
      rows: this._historyRows(p),
      title: '历史记录',
    };
  }

  _view_quiz(p, ep) {
    const quiz = ep.quiz;
    if (!quiz) {
      return {
        index: 0,
        total: this._maxItems(),
        status: '',
        word: null,
        options: [],
        locked: true,
        canPause: false,
        unknownPicked: false,
        labels: this._labels(ep),
      };
    }
    const record = quiz.items[quiz.i];
    const item = record ? record.item : null;
    const answered = quiz.locked && quiz.picked !== null && quiz.picked !== undefined;
    const options = item
      ? item.options.map((option, index) => ({
        index,
        text: option.text,
        label: `${LETTERS[index]}  ${option.text}`,
        state: answered && index === quiz.picked ? 'picked' : '',
      }))
      : [];
    return {
      index: quiz.resp.length,
      total: this._maxItems(),
      status: `词汇测试 · 已答 ${quiz.resp.length} / 最多${this._maxItems()}`,
      word: item ? { w: item.word } : null,
      options,
      locked: Boolean(quiz.locked),
      canPause: true,
      unknownPicked: Boolean(answered && quiz.picked === -1),
      answered: quiz.resp.length,
      maxItems: this._maxItems(),
      labels: this._labels(ep),
    };
  }

  _resultRows(record) {
    if (!record || !Array.isArray(record.bands)) return [];
    return record.bands.map((band) => ({
      label: band.label,
      size: band.size,
      answered: band.answered,
      correct: band.correct,
      unknown: band.unknown,
    }));
  }

  _resultView(p, ep) {
    const record = ep.result;
    if (!record) {
      return {
        estimate: 0,
        interval: [0, 0],
        rows: [],
        actions: [],
        fromWelcome: false,
        big: '',
        sub: '',
        coverage: '',
        note: '',
        available: false,
        title: '',
      };
    }
    const current = assessmentHistory.isCurrent(record);
    const available = current
      ? record.estimate_available === true
      : record.estimate_available !== false;
    const fromWelcome = Boolean(p.book_confirmed ? false : true) || ep.resultCtx === 'welcome_test';
    let big;
    let sub;
    let coverage;
    let note;
    if (current) {
      const insufficient = record.completed ? '样本不足' : '采样尚未完成';
      big = available ? `≈ ${formatNumber(record.vocab)} 词目` : insufficient;
      let reason = {
        precision: '已满足模型停止条件',
        max_items: '已到80题上限',
        exhausted: '可测题目已用完',
      }[record.stop_reason] || '测试尚未完成';
      if (!record.completed) reason = '进行中的测验 · 可在有效期内继续';
      else if (available && record.provisional) reason += ' · 暂定估算';
      const interval = available
        ? `模型95%区间  ${formatNumber(record.lo)} – ${formatNumber(record.hi)} 词目`
        : '至少完成40题及分层采样后才显示估算';
      sub = `${interval}\n${reason}`;
      coverage = `已答 ${intLike(record.total, 0)} 题 · ${intLike(record.coverage, 0)} / `
        + `${intLike(record.coverage_target, 0)} 层至少2题 · 不认识 ${intLike(record.dontknow, 0)} 题`;
      note = `测量范围：本地高频有效词目 ${formatNumber(record.population || 0)} 个；`
        + '不是词族量或全部英语词汇。\n'
        + '题目参数未经实测标定；模型区间不包含全部测量偏差。\n'
        + '结果不会改变学习队列或逐词掌握状态。';
      const boundaryNote = {
        all_correct: '本次全对，能力上端信息不足，不能据此精确判断更大范围。',
        all_incorrect: '本次无正确回答，能力下端信息不足，不等于完全没有词汇知识。',
        grid_edge: '后验接近模型数值网格边界，估算与区间需谨慎解读。',
      }[record.boundary];
      if (boundaryNote) note += `\n${boundaryNote}`;
    } else {
      big = available ? `≈ ${formatNumber(record.vocab)} 词目` : '旧版样本不足';
      sub = '旧版结果 · 按原记录展示，未重新计算\n不与 V1.4.2 的新量尺比较增减';
      coverage = `原记录：答对 ${intLike(record.right, 0)} / ${intLike(record.total, 0)}`
        + ` · 不认识 ${intLike(record.dontknow, 0)} 题`;
      note = '旧版的题型、计分方法及测量范围不同。\n历史与已有学习记录均保留；新测试从独立会话开始。';
    }
    const days = this._quizRemainingDays(p, p.quiz_session, null, false);
    const rebase = !current && !record.baseline && Boolean(record.prediction_eligible);
    const actions = [{
      type: 'back',
      payload: {},
      label: fromWelcome ? '选择词书' : '继续背单词',
      style: 'primary',
    }];
    if (rebase) {
      actions.push({
        type: 'prediction',
        payload: { strategy: 'estimate' },
        label: '调整预测掌握',
        style: 'link',
        strategies: ['conservative', 'estimate', 'optimistic'],
      });
    }
    if (current) {
      actions.push({
        type: 'bands',
        payload: {},
        label: '分层采样详情',
        style: 'link',
      });
    }
    if (days > 0) {
      actions.push({
        type: 'quizStart',
        payload: { fresh: false },
        label: `继续上次测试（剩余${days}天）`,
        style: 'link',
      });
    }
    actions.push({
      type: 'quizStart',
      payload: { fresh: true },
      label: '开始新的测试',
      style: 'link',
    });
    let chart = [];
    if (current) {
      try {
        chart = assessmentHistory.comparable(Array.isArray(p.history) ? p.history : [], record)
          .map((row) => ({ ts: row.ts, vocab: row.vocab }))
          .slice(-12);
      } catch {
        chart = [];
      }
    }
    return {
      estimate: finiteNumber(record.vocab) ? record.vocab : 0,
      interval: [intLike(record.lo, 0), intLike(record.hi, 0)],
      rows: this._resultRows(record),
      actions,
      fromWelcome,
      big,
      sub,
      coverage,
      note,
      available,
      current,
      completed: Boolean(record.completed),
      chart: current ? { points: chart, title: '同题库、同量尺的完成测验趋势' } : { points: [], title: '' },
      title: '测试结果',
    };
  }

  _summaryView(p, ep) {
    const record = ep.result;
    if (ep.report) {
      return {
        title: ep.report.title,
        body: ep.report.lines.slice(),
        actions: [{ type: 'back', payload: {}, label: '返回', style: 'primary' }],
        big: '',
        note: '',
      };
    }
    let big = '';
    let note = '';
    if (record) {
      if (record.estimate_available === true) {
        big = `≈ ${formatNumber(record.vocab)} 个词`;
        note = `参考范围 ${formatNumber(record.lo)}–${formatNumber(record.hi)} 个词\n`
          + `已答 ${intLike(record.total, 0)} 题 · 答对 ${intLike(record.right, 0)} 题\n`
          + '本次测试结果已保存到历史记录。';
      } else {
        big = '样本不足';
        note = '这次没有给出词汇量估计。\n'
          + `已答 ${intLike(record.total, 0)} 题 · 答对 ${intLike(record.right, 0)} 题\n`
          + '本次测试结果已保存到历史记录。';
      }
    }
    return {
      title: '本次测试已完成',
      body: [big, ...note.split('\n')],
      actions: [{ type: 'settings', payload: {}, label: '知道了', style: 'primary' }],
      big,
      note,
    };
  }

  _view_summary(p, ep) {
    return this._summaryView(p, ep);
  }

  _view_result(p, ep) {
    return this._resultView(p, ep);
  }

  _view_building(p, ep) {
    const percent = ep.building && Number.isFinite(ep.building.percent)
      ? Math.max(0, Math.min(100, Math.round(ep.building.percent))) : 0;
    return { percent, title: '正在构建题库' };
  }

  _view_settings(p, ep) {
    return this._settingsView(p, ep);
  }

  // ---------- 动作实现 ----------
  _action_answer(payload) {
    const ep = this._begin(true);
    const p = ep.draft.progress;
    const current = this.ep;
    if (current.screen !== 'front') return;
    const action = payload.action;
    if (action !== 'remember' && action !== 'forget') {
      throw invalid('answer.action 必须是 remember 或 forget');
    }
    this._answerCurrent(p, ep.ep, action === 'remember');
    ep.ep.screen = 'back';
    this._commit(ep);
  }

  _action_next() {
    const screen = this.ep.screen;
    if (screen === 'front' || screen === 'result' || screen === 'summary') return;
    if (screen === 'choice' && this.ep.choice !== null) return;
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    if (screen === 'quiz') {
      if (!ep.quiz) return;
      this._quizNextCore(p, ep);
      this._commit(t);
      return;
    }
    if (screen === 'empty') {
      this._newSession(p, ep);
      this._commit(t);
      return;
    }
    if (screen === 'choice') {
      // 选择题无法出题（choice === null）时真正跳过当前词：加入仅本会话的
      // 临时 excluded，_next0 重建 StudyQueue 后 next() 不会复用 current。
      this._skipUnavailableChoiceWord(ep);
      this._next0(p, ep);
      this._commit(t);
      return;
    }
    if (screen === 'back' || screen === 'choice_back') {
      this._next0(p, ep);
      this._commit(t);
    }
  }

  _action_choice(payload) {
    const index = payload.index;
    if (!Number.isInteger(index) || index < -1 || index > 3) {
      throw invalid('choice.index 必须是 -1..3（-1 表示不认识）');
    }
    const current = this.ep;
    if (current.screen !== 'choice' || current.choiceLocked || !current.choice) return;
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    if (!ep.choice) return;
    const remember = index === ep.choice.correct;
    this._answerCurrent(p, ep, remember);
    ep.choiceLocked = true;
    ep.choicePicked = index;
    ep.screen = 'choice_back';
    this._commit(t);
  }

  _action_dontknow() {
    if (this.ep.screen === 'quiz') return this._action_quizAnswer({ index: -1 });
    if (this.ep.screen === 'choice') return this._action_choice({ index: -1 });
  }

  _action_correct() {
    const current = this.ep;
    if (!this._canCorrect(current)) return;
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    const snapshot = current.snapshot;
    if (!this._restoreStudy(p, ep, snapshot)) return;
    this._makeEngine(p, ep);
    const item = this._itemForAnswer(p, ep);
    this._studyEngine.answer(item, false, this._now());
    p.cursors[p.book] = this._studyEngine.cursor;
    ep.corrected = true;
    ep.lastAction = { kind: item.kind, key: item.w.w, remember: false };
    ep.qi += 1;
    const found = this._pullNew(p, ep);
    if (found) {
      ep.qi = ep.queue.length - 1;
      this._showCurrent(p, ep);
    } else {
      this._showEmpty(p, ep);
    }
    this._commit(t);
  }

  _action_undo() {
    const current = this.ep;
    if (!STUDY_SCREENS.includes(current.screen)) return;
    if (!current.snapshot) return;
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    if (!this._restoreStudy(p, ep, current.snapshot)) return;
    ep.snapshot = null;
    ep.lastAction = null;
    ep.corrected = false;
    this._showCurrent(p, ep);
    this._commit(t);
  }

  _action_settings() {
    const ep = this._begin(false);
    this._openSettings(this.doc.progress, ep.ep);
    this._commit(ep);
  }

  _action_closeSettings() {
    const current = this.ep;
    if (current.screen !== 'settings') return;
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    if (!p.book_confirmed) {
      this._openBooks(p, ep, 'welcome');
      this._commit(t);
      return;
    }
    const mode = ep.preSettingsMode;
    const changed = p.study_mode !== ep.settingsStudyModeStart;
    let persist = false;
    if (ep.schoolChanged) {
      this._studyEngine = null;
      this._makeEngine(p, ep);
      const found = this._pullNew(p, ep);
      if (found) {
        ep.qi = ep.queue.length - 1;
        this._showCurrent(p, ep);
      } else {
        this._showEmpty(p, ep);
      }
      ep.schoolChanged = false;
      persist = true;
    } else if (changed && (mode === 'back' || mode === 'choice_back')) {
      this._next0(p, ep);
      persist = true;
    } else if (changed && (mode === 'front' || mode === 'choice')) {
      this._showCurrent(p, ep);
    } else {
      this._restoreStudyScreen(p, ep, STUDY_SCREENS.includes(mode) ? mode : 'front');
    }
    ep.schoolChanged = false;
    if (persist) this._commit(t);
    else this._commitEp(ep);
  }

  _action_theme(payload) {
    if (typeof payload.key !== 'string') throw invalid('theme.key 必须是字符串');
    const key = payload.key in THEMES ? payload.key : DEFAULT_THEME;
    const t = this._begin(true);
    this._applyPreference(t.draft.progress, t.ep, { theme: key });
    this._commit(t);
  }

  _action_studyMode(payload) {
    if (payload.key !== 'brush' && payload.key !== 'choice') {
      throw invalid('studyMode.key 必须是 brush 或 choice');
    }
    const t = this._begin(true);
    if (payload.key !== this.doc.progress.study_mode) {
      // 切换学习模式即恢复临时跳过的词（刷词/以后重启都能再学到）。
      t.ep.skipKeys = [];
    }
    this._applyPreference(t.draft.progress, t.ep, { study_mode: payload.key });
    this._commit(t);
  }

  _action_school(payload) {
    if (typeof payload.level !== 'string') throw invalid('school.level 必须是字符串');
    const level = school.normalize(payload.level);
    if (level !== payload.level) throw invalid('school.level 必须是 off/primary/middle/high');
    const p = this.doc.progress;
    if (level === school.normalize(p.school_knowledge)) return;
    const t = this._begin(true);
    const draft = t.draft.progress;
    t.ep.skipKeys = []; // 学校范围变化会改变 excluded 语义：恢复临时跳过词
    for (const bookId of Object.keys(draft.study_records)) {
      draft.study_records[bookId].cursor = 0;
      draft.cursors[bookId] = 0;
    }
    this._applyPreference(draft, t.ep, { school_knowledge: level });
    t.ep.schoolChanged = true;
    this._commit(t);
  }

  _action_books(payload) {
    const from = typeof payload.from === 'string' && payload.from ? payload.from : 'welcome';
    const ep = this._begin(false);
    this._openBooks(this.doc.progress, ep.ep, from);
    this._commit(ep);
  }

  _action_book(payload) {
    if (this.ep.screen !== 'books') throw invalid('当前不在选书页面');
    const id = payload.id;
    if (id !== undefined && id !== null && typeof id !== 'string') {
      throw invalid('book.id 必须是字符串');
    }
    const order = payload.order;
    if (order !== undefined && order !== 'seq' && order !== 'shuffle') {
      throw invalid('book.order 必须是 seq 或 shuffle');
    }
    const ep = this._begin(false).ep;
    const books = this.dataset.books;
    if (typeof id === 'string' && id) {
      if (books.MAINS.some((main) => main.id === id)) {
        ep.navMain = id;
        ep.navLevel = 2;
        ep.navGroup = null;
        this._commitEp(ep);
        return;
      }
      if (books.GROUPS[id]) {
        ep.navGroup = id;
        ep.navLevel = 3;
        this._commitEp(ep);
        return;
      }
      const [gid, series] = parseSeriesId(id);
      const isRealBook = Object.prototype.hasOwnProperty.call(books.BY_ID, id);
      const isSeries = Boolean(gid && this.dataset.seriesUnionWords(gid, series).length);
      if (!isRealBook && !isSeries) throw invalid(`未知的词书 id：${id}`);
      ep.selBook = id;
      if (order) {
        ep.selOrder = order;
        ep.orderExplicit = true;
      } else if (!ep.orderExplicit) {
        ep.selOrder = storedOrder(this.doc.progress.orders, id);
      }
      this._commitEp(ep);
      return;
    }
    if (order) {
      ep.selOrder = order;
      ep.orderExplicit = true;
      this._commitEp(ep);
      return;
    }
    throw invalid('book 需要 id 或 order');
  }

  _action_nav(payload) {
    return this._action_book({ id: payload.id });
  }

  _action_start() {
    if (this.ep.screen !== 'books') throw invalid('当前不在选书页面');
    const selected = this.ep.selBook;
    if (!selected) throw invalid('请先选择一本词书');
    const t = this._begin(true);
    t.ep.skipKeys = []; // 换书/换序开始新学习会话：恢复所有临时跳过词
    this._startLearning(t.draft.progress, t.ep);
    this._commit(t);
  }

  _action_catalog() {
    const current = this.ep;
    const bookId = current.screen === 'books'
      ? current.selBook
      : (this.doc.progress.book || null);
    if (!bookId) throw invalid('还没有可浏览的词书');
    const src = current.screen === 'books' ? 'books' : 'settings';
    const mode = src === 'books' ? current.selOrder : storedOrder(this.doc.progress.orders, bookId);
    if (mode === 'shuffle' && !(isPlainObject(this.doc.progress.orders[bookId])
        && Number.isInteger(this.doc.progress.orders[bookId].seed))) {
      const t = this._begin(true);
      this._seed(t.draft.progress, bookId);
      this._catalogCache = null;
      this._openCatalog(t.draft.progress, t.ep, bookId, src);
      this._commit(t);
      return;
    }
    const ep = this._begin(false).ep;
    this._openCatalog(this.doc.progress, ep, bookId, src);
    this._commitEp(ep);
  }

  _action_catalogFilter(payload) {
    const current = this.ep;
    if (current.screen !== 'catalog' || !current.catalog) throw invalid('当前不在词表页面');
    const ep = this._begin(false).ep;
    if (payload.category !== undefined) {
      const valid = DEFAULT_WORD_CATEGORIES.map(([key]) => key);
      if (typeof payload.category !== 'string' || !valid.includes(payload.category)) {
        throw invalid('catalogFilter.category 非法');
      }
      ep.catalog.filter = payload.category;
    }
    if (payload.query !== undefined) {
      if (typeof payload.query !== 'string' || payload.query.length > 200) {
        throw invalid('catalogFilter.query 必须是不超过 200 字符的字符串');
      }
      ep.catalog.query = payload.query.trim();
    }
    this._commitEp(ep);
  }

  _action_catalogSort(payload) {
    const current = this.ep;
    if (current.screen !== 'catalog' || !current.catalog) throw invalid('当前不在词表页面');
    if (typeof payload.byLevel !== 'boolean') throw invalid('catalogSort.byLevel 必须是布尔值');
    const ep = this._begin(false).ep;
    ep.catalog.sortByLevel = payload.byLevel;
    this._commitEp(ep);
  }

  _action_bulkLearn(payload) {
    if (this.ep.screen !== 'catalog') throw invalid('当前不在词表页面');
    const keys = payload.keys;
    if (!Array.isArray(keys) || keys.length > 5000
        || keys.some((key) => typeof key !== 'string' || !key)) {
      throw invalid('bulkLearn.keys 必须是非空字符串数组（最多 5000 项）');
    }
    const t = this._begin(true);
    const p = t.draft.progress;
    const prediction = isPlainObject(p.prediction_state) ? p.prediction_state : pred.newPredictionData();
    p.prediction_state = prediction;
    for (const key of keys) {
      if (this._known.has(key)) {
        this._known.delete(key);
        if (Array.isArray(prediction.selected)) {
          prediction.selected = prediction.selected.filter((item) => item !== key);
        }
        if (Array.isArray(prediction.excluded) && !prediction.excluded.includes(key)) {
          prediction.excluded.push(key);
        }
      }
      const state = p.states[key];
      if (state && (state.st === 'mastered' || state.st === 'retired' || intLike(state.lv, 0) >= 10)) {
        state.st = 'new';
        state.lv = 0;
        state.due = null;
      }
    }
    if (isPlainObject(prediction.effective)) {
      prediction.effective.selected = Array.isArray(prediction.selected) ? prediction.selected.length : 0;
    }
    this._catalogCache = null;
    this._statsCache = null;
    this._commit(t);
  }

  _action_quizStart(payload) {
    const fresh = payload.fresh === true;
    const origin = this.ep.screen;
    const vt = this.dataset.vt;
    if (!vt) throw new ActionError('failed', this.dataset.vtError || '词汇量测评核模块不可用');
    if (this.dataset.quizBankBuilt) {
      const t = this._begin(true);
      this._startQuizCore(t.draft.progress, t.ep, origin, fresh);
      this._commit(t);
      return;
    }
    // 首次构建题库：先返回 building；后台线程计算，串行链等待，GET 可实时读取进度。
    const current = this.ep;
    current.screen = 'building';
    current.building = { percent: 0 };
    current.pendingQuiz = { origin, fresh };
    this._enqueue(async () => {
      const ep = this.ep;
      if (this._closed) {
        // 卸载发生在构建排队之后：不再构建题库，也不碰已释放的存储。
        ep.building = null;
        ep.pendingQuiz = null;
        return;
      }
      try {
        await this.dataset.prepareQuizBank((percent) => {
          if (!this._closed && this.ep === ep && ep.building) ep.building.percent = percent;
        });
        // Unload can happen while the worker is running; never commit to a released store.
        if (this._closed) return;
        const t = this._begin(true);
        const pending = ep.pendingQuiz || { origin, fresh };
        t.ep.building = null;
        t.ep.pendingQuiz = null;
        this._startQuizCore(t.draft.progress, t.ep, pending.origin, pending.fresh);
        this._commit(t);
      } catch (error) {
        if (this._closed) return;
        const failed = this.ep;
        failed.building = null;
        failed.pendingQuiz = null;
        failed.screen = origin;
        this._notice(`题库构建失败：${error && error.message ? error.message : error}`);
      }
    });
  }

  _action_quizAnswer(payload) {
    const index = payload.index;
    if (!Number.isInteger(index) || index < -1 || index > 3) {
      throw invalid('quizAnswer.index 必须是 -1..3');
    }
    const current = this.ep;
    if (current.screen !== 'quiz' || !current.quiz || current.quiz.locked) return;
    if (current.quiz.resp.length !== current.quiz.i) return;
    const t = this._begin(true);
    this._quizAnswerCore(t.draft.progress, t.ep, index);
    this._commit(t);
  }

  _action_quizDontknow() {
    return this._action_quizAnswer({ index: -1 });
  }

  _action_quizPause() {
    const current = this.ep;
    if (current.screen !== 'quiz' || !current.quiz) return;
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    this._saveQuizSession(p, ep);
    const returnToSettings = Boolean(ep.quiz && ep.quiz.returnToSettings);
    ep.quiz = null;
    if (returnToSettings) {
      this._openSettings(p, ep);
    } else {
      this._studyEngine = null;
      this._startupFor(p, ep);
    }
    this._commit(t);
  }

  _action_history() {
    const current = this.ep;
    const p = this.doc.progress;
    const vt = this.dataset.vt;
    const session = p.quiz_session;
    let persist = false;
    let t = null;
    if (vt && this.dataset.quizBankBuilt && isPlainObject(session)
        && session.algo === vt.ALGORITHM && Array.isArray(session.resp) && session.resp.length
        && !session.history_deleted && vt.validateSession(session, this.dataset.getQuizBank())
        && this._quizRemainingDays(p, session, null, false) > 0) {
      const existing = (Array.isArray(p.history) ? p.history : [])
        .find((row) => row && row.id === session.id);
      if (!existing || existing.total !== session.resp.length) {
        t = this._begin(true);
        this._upsertQuizHistory(t.draft.progress, t.ep, false, session);
        persist = true;
      }
    }
    const ep = t ? t.ep : this._begin(false).ep;
    ep.screen = 'history';
    if (persist) this._commit(t);
    else this._commitEp(ep);
  }

  _action_deleteHistory(payload) {
    if (this.ep.screen !== 'history') throw invalid('当前不在历史记录页面');
    const index = payload.index;
    const p = this.doc.progress;
    const history = Array.isArray(p.history) ? p.history : [];
    if (!Number.isInteger(index) || index < 0 || index >= history.length) {
      throw invalid('deleteHistory.index 非法');
    }
    const t = this._begin(true);
    const draft = t.draft.progress;
    const rows = Array.isArray(draft.history) ? draft.history : [];
    const latest = rows.reduce((best, row, idx) => (
      row && (best === null || intLike(row.ts, 0) >= intLike(rows[best].ts, 0)) ? idx : best
    ), null);
    const removed = rows.splice(index, 1)[0];
    const session = draft.quiz_session;
    if (index === latest && isPlainObject(session)) session.resume_disabled = true;
    if (isPlainObject(session)
        && (session.id === removed.id || session.history_id === removed.id)) {
      session.history_id = null;
      if (session.id === removed.id) {
        session.history_deleted = true;
        const responses = Array.isArray(session.resp) ? session.resp : [];
        session.history_response_count = responses.length;
      }
    }
    t.ep.lastTest = null;
    this._commit(t);
  }

  _action_prediction(payload) {
    if (this.ep.screen !== 'result') throw invalid('当前不在结果页面');
    const vt = this.dataset.vt;
    const record = this.ep.result || (this.ep.lastTest ? this.ep.lastTest.record : null);
    if (!record) throw invalid('没有可用的测试结果');
    const applicable = vt
      && record.algo !== vt.ALGORITHM
      && record.unit !== vt.UNIT
      && Boolean(record.prediction_eligible);
    if (!applicable) {
      const ep = this._begin(false).ep;
      ep.report = {
        title: '不据此预测逐词掌握',
        lines: ['新版测试只估算识别词目量，不据此跳过具体单词。已有学习和预测状态保留。'],
        returnScreen: 'result',
      };
      ep.screen = 'summary';
      this._commitEp(ep);
      return;
    }
    const strategy = payload.strategy;
    if (!pred.STRATEGIES.includes(strategy)) {
      throw invalid('prediction.strategy 必须是 conservative/estimate/optimistic');
    }
    const t = this._begin(true);
    const p = t.draft.progress;
    const ep = t.ep;
    const data = isPlainObject(p.prediction_state) ? p.prediction_state : pred.newPredictionData();
    p.prediction_state = data;
    const target = pred.applyStrategy(record.vocab, (record.hi - record.lo) / 2, strategy);
    const bands = {};
    for (const entry of this.dataset.bank) bands[entry.w] = Number(entry.lvl) || 0;
    const [selected, counts] = pred.selectPredictionCandidates(
      this.dataset.bank,
      p.states,
      target,
      {
        bands,
        rejected: data.rejected,
        excluded: data.excluded,
        seed: record.id,
      },
    );
    const previous = new Set(data.selected);
    const explicitlyReturned = new Set(data.excluded);
    data.excluded = Array.from(new Set([...explicitlyReturned, ...Array.from(previous)
      .filter((key) => !selected.has(key))])).sort();
    data.selected = Array.from(selected).sort();
    data.effective = {
      target: counts.target,
      available: counts.available,
      selected: counts.selected,
    };
    data.strategy = strategy;
    data.source_history_id = record.id;
    this._refreshRuntime();
    ep.screen = 'front';
    ep.report = null;
    this._newSession(p, ep);
    this._commit(t);
  }

  _action_bands() {
    if (this.ep.screen !== 'result') throw invalid('当前不在结果页面');
    const record = this.ep.result;
    if (!record || !assessmentHistory.isCurrent(record)) {
      throw invalid('当前结果不提供分层采样详情');
    }
    const lines = [
      '分层采样记录 · 不等于分层掌握诊断', '',
      '这里的层是本地有效词目排名，不是原始语料排名或VST词族层。',
      '每层少量样本只用于覆盖约束；不能据此认定本层已掌握或未掌握。', '',
    ];
    for (const band of record.bands || []) {
      lines.push(`${band.label}（${formatNumber(band.size)}词目）`);
      lines.push(`  已测 ${band.answered} · 答对 ${band.correct} · 不认识 ${band.unknown}`);
    }
    const ep = this._begin(false).ep;
    ep.report = { title: '分层采样详情', lines, returnScreen: 'result' };
    ep.screen = 'summary';
    this._commitEp(ep);
  }

  _action_back() {
    const screen = this.ep.screen;
    if (screen === 'settings') return this._action_closeSettings();
    if (screen === 'history') return this._action_settings();
    if (screen === 'catalog') {
      if (this.ep.catalog && this.ep.catalog.src === 'settings') return this._action_settings();
      const ep = this._begin(false).ep;
      ep.screen = 'books';
      this._commitEp(ep);
      return;
    }
    if (screen === 'books') {
      if (this.ep.navLevel > 1) {
        const ep = this._begin(false).ep;
        if (ep.navLevel === 3) {
          ep.navLevel = 2;
          ep.navGroup = null;
        } else if (ep.navLevel === 2) {
          ep.navLevel = 1;
          ep.navMain = null;
        }
        this._commitEp(ep);
        return;
      }
      if (this.ep.booksSrc === 'settings') return this._action_settings();
      return;
    }
    if (screen === 'result') {
      const ep = this._begin(false).ep;
      const p = this.doc.progress;
      if (ep.resultCtx === 'history') {
        this._openSettings(p, ep);
      } else if (ep.resultCtx === 'welcome_test') {
        this._openBooks(p, ep, 'welcome');
      } else {
        this._studyEngine = null;
        this._newSession(p, ep);
      }
      this._commitEp(ep);
      return;
    }
    if (screen === 'summary') {
      const ep = this._begin(false).ep;
      if (ep.report) {
        ep.screen = ep.report.returnScreen;
        ep.report = null;
        this._commitEp(ep);
        return;
      }
      this._openSettings(this.doc.progress, ep);
      this._commitEp(ep);
    }
  }
}

/** 仅供视图层判断可空数字；避免把 null 当成 0。 */
function finteOrNull(value) {
  return finiteNumber(value);
}

export default { Engine, ActionError, keyCaption, APP_VERSION, PLUGIN_VERSION };
