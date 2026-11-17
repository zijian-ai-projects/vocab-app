/**
 * 只读数据层：读 data/{bank,phrases,books,phrase_books,level_meanings}.json，
 * 构建 books 句柄 / A–Z 词库索引 / 学段释义覆盖 / 学习选项池，并懒构建
 * FrequencyBank（题库构建进度通过回调上报）。
 *
 * 目录解析：DSH_VOCAB_APP_DATA_DIR → 插件包内 data/ → 仓库根 data/（源码运行）。
 * 绝不写 data/，也绝不读写桌面版 progress.json / _win.json。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';

import * as booksModule from '../core/books.js';
import * as levelMeaningsModule from '../core/level_meanings.js';
import { stageForMain } from '../core/level_meanings.js';
import { OptionPool, makeOptions } from '../core/study_options.js';
import * as school from '../core/school_knowledge.js';
import { makeRng } from '../core/rng.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const PLUGIN_ROOT = path.resolve(HERE, '..', '..');
export const REPO_ROOT = path.resolve(PLUGIN_ROOT, '..');

export const SERIES_PREFIX = 'series:';
export const DATA_FILE_NAMES = Object.freeze([
  'bank.json', 'phrases.json', 'books.json', 'phrase_books.json', 'level_meanings.json',
]);

export function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '0';
  return String(Math.trunc(number)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 所有词书统一显示实际成员数。 */
export function bookQuantity(meta, total = null) {
  const count = total === null || total === undefined
    ? (meta && Number.isFinite(meta.count) ? meta.count : 0)
    : total;
  return `${formatNumber(count)} 词`;
}

export function seriesLabel(series) {
  return series === '人教 PEP' ? '人教PEP版' : series;
}

/** 教材系列伪 id -> [group_id, series]；真实词书 -> [null, null]。 */
export function parseSeriesId(bookId) {
  if (typeof bookId !== 'string' || !bookId.startsWith(SERIES_PREFIX)) return [null, null];
  const parts = bookId.split(':');
  if (parts.length === 3 && parts[1] && parts[2]) return [parts[1], parts[2]];
  return [null, null];
}

function isDirectoryWithData(directory) {
  if (!directory || typeof directory !== 'string') return false;
  try {
    if (!fs.statSync(directory).isDirectory()) return false;
    return fs.existsSync(path.join(directory, 'bank.json'))
      && fs.existsSync(path.join(directory, 'books.json'));
  } catch {
    return false;
  }
}

/**
 * 解析只读数据目录。config.dataDir 仅测试注入；生产按 env/包内/仓库回退。
 * @param {{dataDir?:string, env?:Record<string,string|undefined>}} [options]
 */
export function resolveDataDir(options = {}) {
  const env = options.env || process.env;
  const candidates = [];
  if (typeof env.DSH_VOCAB_APP_DATA_DIR === 'string' && env.DSH_VOCAB_APP_DATA_DIR.trim()) {
    candidates.push(path.resolve(env.DSH_VOCAB_APP_DATA_DIR.trim()));
  }
  if (options.dataDir) candidates.push(path.resolve(options.dataDir));
  candidates.push(path.join(PLUGIN_ROOT, 'data'));
  candidates.push(path.join(REPO_ROOT, 'data'));
  for (const candidate of candidates) {
    if (isDirectoryWithData(candidate)) return candidate;
  }
  throw new Error(
    '找不到背单词词库数据目录（需要 bank.json 与 books.json）。已尝试：'
    + candidates.join('、')
    + '。请把 data/ 随插件发布，或设置 DSH_VOCAB_APP_DATA_DIR。',
  );
}

function readJsonArray(filePath) {
  let text;
  try {
    text = fs.readFileSync(filePath, 'utf8');
  } catch (error) {
    if (error && error.code === 'ENOENT') return [];
    throw new Error(`无法读取词库文件 ${filePath}：${error.message || error}`);
  }
  let data;
  try {
    data = JSON.parse(text.replace(/^\uFEFF/, ''));
  } catch (error) {
    throw new Error(`词库文件不是有效 JSON：${filePath}（${error.message || error}）`);
  }
  if (!Array.isArray(data)) throw new Error(`词库文件顶层必须是数组：${filePath}`);
  return data;
}

export class Dataset {
  constructor(options = {}) {
    this.config = options;
    this.dataDir = null;
    this.bank = [];
    this.phrases = [];
    this.bankMap = new Map();
    this.allEntries = [];
    this.books = null;
    this.levelMeanings = { primary: {}, middleschool: {} };
    this.vt = null;
    this.vtError = null;
    this._optionPools = new Map();
    this._quizBank = null;
    this._quizBuild = null;
    this._loaded = null;
  }

  get loaded() {
    return this._loaded !== null;
  }

  async load() {
    if (this._loaded !== null) return this._loaded;
    this._loaded = (async () => {
      const dataDir = resolveDataDir(this.config);
      this.dataDir = dataDir;
      this.bank = readJsonArray(path.join(dataDir, 'bank.json'));
      const phrasePath = path.join(dataDir, 'phrases.json');
      this.phrases = fs.existsSync(phrasePath) ? readJsonArray(phrasePath) : [];
      this.bankMap = new Map();
      for (const entry of this.bank) {
        if (entry && typeof entry.w === 'string' && !this.bankMap.has(entry.w)) {
          this.bankMap.set(entry.w, entry);
        }
      }
      for (const entry of this.phrases) {
        if (entry && typeof entry.w === 'string') this.bankMap.set(entry.w, entry);
      }
      this.allEntries = this.bank.concat(this.phrases);
      this.books = booksModule.load(dataDir);
      this.levelMeanings = levelMeaningsModule.load(dataDir);
      try {
        this.vt = await import('../core/vocabulary_test.js');
      } catch (error) {
        this.vt = null;
        this.vtError = `词汇量测评核模块（lib/core/vocabulary_test.js）不可用：${error.message || error}`;
      }
      return this;
    })();
    try {
      return await this._loaded;
    } catch (error) {
      this._loaded = null;
      throw error;
    }
  }

  // ---------- 词条 ----------
  entry(key) {
    return this.bankMap.get(key) || null;
  }

  /** 词书 / 分组并集 / 教材系列并集 -> 原始词序（UI 层解析伪 id）。 */
  bookWordStrs(bookId) {
    if (!bookId) return [];
    const [gid, series] = parseSeriesId(bookId);
    if (gid) {
      if (!this.books.GROUPS[gid]) return this.books.words(this.books.DEFAULT);
      const words = this.seriesUnionWords(gid, series);
      return words.length ? words : this.books.words(gid);
    }
    return this.books.words(bookId);
  }

  /** 某版本各分册按册序拼接后去重（保留首次出现顺序）。 */
  seriesUnionWords(groupId, series) {
    const group = this.books.GROUPS[groupId];
    if (!group) return [];
    const seen = new Set();
    const out = [];
    for (const item of group.items) {
      if ((item.series || '') !== series) continue;
      for (const word of item.words || []) {
        if (seen.has(word)) continue;
        seen.add(word);
        out.push(word);
      }
    }
    return out;
  }

  bookLevel(bookId) {
    if (!bookId) return null;
    const [gid] = parseSeriesId(bookId);
    let main = null;
    if (gid) {
      const group = this.books.GROUPS[gid];
      main = group ? group.main : null;
    } else {
      try {
        main = this.books.get(bookId).main;
      } catch {
        main = null;
      }
    }
    return stageForMain(main);
  }

  levelMapping(stage) {
    if (!stage) return {};
    return this.levelMeanings[stage] || {};
  }

  decoratedEntry(key, stage = null) {
    const entry = this.entry(key);
    if (!entry) return null;
    const mapping = stage === null ? null : this.levelMapping(stage);
    return mapping ? levelMeaningsModule.decorate(entry, mapping) : entry;
  }

  /** 返回浅拷贝词条并附加学段释义；共享词条绝不修改。 */
  bookWordEntries(bookId) {
    const stage = this.bookLevel(bookId);
    const mapping = stage ? this.levelMapping(stage) : null;
    const out = [];
    for (const key of this.bookWordStrs(bookId)) {
      const entry = this.entry(key);
      if (!entry) continue;
      out.push(mapping ? levelMeaningsModule.decorate(entry, mapping) : entry);
    }
    return out;
  }

  /** 该主分类（primary/middleschool）所有唯一成员词条。 */
  levelPoolEntries(stage) {
    if (!stage) return [];
    const mapping = this.levelMapping(stage);
    const seen = new Set();
    const out = [];
    for (const group of this.books.groups(stage)) {
      for (const item of this.books.items(group.id)) {
        for (const key of this.books.words(item.id)) {
          if (seen.has(key) || !this.bankMap.has(key)) continue;
          seen.add(key);
          out.push(levelMeaningsModule.decorate(this.bankMap.get(key), mapping));
        }
      }
    }
    return out;
  }

  // ---------- 词书元数据 ----------
  defaultBookId() {
    return this.books ? this.books.DEFAULT : null;
  }

  /** 统一的词书显示信息：伪 id 不写进 books，显示名/路径现算。 */
  bookMeta(bookId) {
    if (!bookId) return { id: null, name: '', display: '', count: 0, path: [] };
    const [gid, series] = parseSeriesId(bookId);
    if (gid) {
      const group = this.books.GROUPS[gid];
      if (group) {
        const main = this.books.mains().find((item) => item.id === group.main) || null;
        const name = `${series} · 本版本全选`;
        return {
          id: bookId,
          name,
          display: name,
          count: this.seriesUnionWords(gid, series).length,
          path: [main ? main.name : '', group.name],
          group: gid,
          series,
          main: group.main,
          source_status: 'community_compilation',
          source_version: 'community',
          source_note: '词表由民间整理；教材系列全选按现有成员首次出现去重。',
          is_union: false,
          is_series: true,
        };
      }
    }
    const book = { ...this.books.get(bookId) };
    book.is_series = false;
    return book;
  }

  bookName(bookId) {
    const meta = this.bookMeta(bookId);
    return meta.display || meta.name || bookId || '';
  }

  bookPath(bookId) {
    const meta = this.bookMeta(bookId);
    const parts = (meta.path || []).filter((part) => Boolean(part));
    const label = meta.display || meta.name || bookId;
    if (label) parts.push(label);
    return parts.join(' · ');
  }

  /** 结果/目录里的一小段名字：真实书用所属分组名。 */
  bookShortName(bookId) {
    if (!bookId) return '';
    const [gid, series] = parseSeriesId(bookId);
    if (gid) return `${series} 全选`;
    try {
      const book = this.books.get(bookId);
      const group = this.books.GROUPS[book.group];
      return group ? group.name : (book.display || book.name);
    } catch {
      return '';
    }
  }

  /** 恢复已确认的词书（兼容旧 id / 教材系列伪 id）；未选书不兜底。 */
  resolveSavedBook(saved) {
    if (!saved) return null;
    if (saved in this.books.BY_ID) return saved;
    const [gid, series] = parseSeriesId(saved);
    if (gid && this.seriesUnionWords(gid, series).length) return saved;
    try {
      return this.books.get(saved).id;
    } catch {
      return this.books.DEFAULT;
    }
  }

  bookCount() {
    return this.books.all().length;
  }

  totalWords() {
    let total = 0;
    for (const book of this.books.all()) total += Number(book.count) || 0;
    return total;
  }

  // ---------- 学习选项池 ----------
  optionPool(key, entries) {
    if (!this._optionPools.has(key)) this._optionPools.set(key, new OptionPool(entries));
    return this._optionPools.get(key);
  }

  bookOptionPool(bookId, stage) {
    return this.optionPool(`__level_book__${stage}:${bookId}`, this.bookWordEntries(bookId));
  }

  stageOptionPool(stage) {
    return this.optionPool(`__level__${stage}`, this.levelPoolEntries(stage));
  }

  entriesOptionPool(key, entries) {
    return this.optionPool(key, entries);
  }

  /**
   * 生成学习用四选一。material 决定确定性；同词同池同 material 必然同题。
   * @param {object} entry
   * @param {OptionPool} pool
   * @param {string} material
   */
  makeOptions(entry, pool, material) {
    const rng = makeRng(`study-options|v1|${material}`);
    return makeOptions(entry, pool, rng);
  }

  // ---------- 学校已认识范围 ----------
  schoolWords(level) {
    return school.words(school.normalize(level), this.books);
  }

  // ---------- 测评题库（懒构建） ----------
  get quizBankBuilt() {
    return this._quizBank !== null;
  }

  /**
   * 构建/复用 FrequencyBank。构建是同步重计算，onProgress(0..100)。
   * @param {(percent:number)=>void} [onProgress]
   */
  getQuizBank(onProgress = null) {
    if (this._quizBank !== null) {
      if (onProgress) onProgress(100);
      return this._quizBank;
    }
    if (this._quizBuild) throw new Error('测评题库构建中，请等待 prepareQuizBank');
    if (!this.vt) throw new Error(this.vtError || '词汇量测评核模块不可用');
    this._quizBank = new this.vt.FrequencyBank(this.bank, onProgress || undefined);
    return this._quizBank;
  }

  /** Cold construction runs off-thread; only public word data crosses the boundary. */
  prepareQuizBank(onProgress = null) {
    if (onProgress !== null && typeof onProgress !== 'function') return Promise.reject(new TypeError('onProgress must be callable'));
    if (this._quizBank !== null) {
      if (onProgress) onProgress(100);
      return Promise.resolve(this._quizBank);
    }
    if (this._quizBuild) {
      if (onProgress) {
        this._quizBuild.listeners.add(onProgress);
        onProgress(this._quizBuild.percent);
      }
      return this._quizBuild.promise;
    }
    if (!this.vt) return Promise.reject(new Error(this.vtError || '词汇量测评核模块不可用'));
    let resolveBuild, rejectBuild;
    const promise = new Promise((resolve, reject) => { resolveBuild = resolve; rejectBuild = reject; });
    const build = { promise, worker: null, percent: 0, listeners: new Set(onProgress ? [onProgress] : []), settled: false, cancel: null };
    this._quizBuild = build;
    const finish = (error, bank) => {
      if (build.settled) return;
      build.settled = true;
      if (this._quizBuild === build) this._quizBuild = null;
      build.listeners.clear();
      if (build.worker) {
        build.worker.removeAllListeners('message');
        // Keep error/exit handlers installed until the isolated thread exits.
        void build.worker.terminate().catch(() => {});
      }
      if (error) rejectBuild(error);
      else { this._quizBank = bank; resolveBuild(bank); }
    };
    build.cancel = () => {
      const error = new Error('测评题库构建已取消'); error.name = 'AbortError'; finish(error);
      return build.worker ? build.worker.terminate().catch(() => {}) : Promise.resolve();
    };
    try {
      if (onProgress) onProgress(0);
      build.worker = new Worker(new URL('./quiz-bank-worker.js', import.meta.url), { workerData: { words: this.bank }, env: {} });
      build.worker.on('message', (message) => {
        if (build.settled || this._quizBuild !== build) return;
        try {
          if (message && message.type === 'progress') {
            const value = message.percent;
            if (Number.isInteger(value) && value > build.percent && value <= 100) {
              build.percent = value;
              for (const listener of build.listeners) listener(value);
            }
          } else if (message && message.type === 'ready') {
            const value = message.bank;
            if (!value || typeof value.fingerprint !== 'string' || !(value._population instanceof Map) || !(value._profiles instanceof Map)) {
              throw new Error('测评题库线程返回格式异常');
            }
            // Structured cloning retains Maps/Sets, but not the class or null prototype.
            Object.setPrototypeOf(value.items, null);
            finish(null, Object.assign(Object.create(this.vt.FrequencyBank.prototype), value));
          } else if (message && message.type === 'failed') {
            throw new Error(message.message || '测评题库线程构建失败');
          } else throw new Error('测评题库线程返回未知消息');
        } catch (error) { finish(error); }
      });
      build.worker.once('error', (error) => finish(error));
      build.worker.once('exit', (code) => {
        if (!build.settled) finish(new Error(`测评题库线程意外退出（${code}）`));
      });
    } catch (error) { finish(error); }
    return promise;
  }

  cancelQuizBankBuild() {
    return this._quizBuild ? this._quizBuild.cancel() : Promise.resolve();
  }

  get vocabularyTest() {
    if (!this.vt) throw new Error(this.vtError || '词汇量测评核模块不可用');
    return this.vt;
  }
}

export default { Dataset, resolveDataDir, parseSeriesId, seriesLabel, bookQuantity, formatNumber };
