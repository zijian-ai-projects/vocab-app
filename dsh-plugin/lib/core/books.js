/**
 * 词书 V2（移植 app/books.py）：三级目录 主类 → 分组 → 词书
 * （+ 分组全选并集 / 教材分册）。
 *
 * 数据来自冻结的 data/books.json（schema 2，保持现有目录与成员顺序）：
 *   mains[] → groups[] → union{id,count,words} + items[{id,name,display,series,count,words}]
 * phrase_books.json 若存在，会把其中的词组书并入对应分组，并同步扩充分组并集
 * （按首次出现去重、保持顺序、重算 count）。
 *
 * 对上层保持简单接口：get/words/size/name/path/all/默认书；三级目录另给
 * mains()/groups()/items()。旧 V1.1 的 10 个词书 id 用 LEGACY 映射到对应分组
 * 的「全选」并集，保证旧进度能落到同一批词上。
 *
 * `load(dataDir)` 是纯读取：只读 `books.json` / `phrase_books.json`，绝不写文件。
 * 不传参时读包目录下的 `data/`（`dsh-plugin/data`）并缓存。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const DATA = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
  '..',
  'data',
);

/** 旧 V1.1 词书 id → V2 分组并集 id。 */
export const LEGACY = Object.freeze({
  xiaoxue: 'xx-ci-all',
  chuzhong: 'zhongkao-all',
  gaokao: 'gaokao-all',
  cet4: 'cet4-all',
  cet6: 'cet6-all',
  kaoyan: 'kaoyan-all',
  kaobo: 'kaoyan-all',
  ielts: 'ielts-all',
  toefl: 'toefl-all',
  gre: 'gre-all',
});

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readJson(filename) {
  let text;
  try {
    text = fs.readFileSync(filename, 'utf8');
  } catch (error) {
    throw new Error(`无法读取词库文件：${filename}（${error.code || error.message}）`);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`词库文件不是合法 JSON：${filename}（${error.message}）`);
  }
}

function requireArray(value, label) {
  if (!Array.isArray(value)) throw new TypeError(`${label} 必须是数组`);
  return value;
}

/**
 * 读取并合并 books.json + phrase_books.json（对应 Python `_load`）。
 * @param {string} dataDir
 * @returns {object} 原始 data 对象（已合并 supplement）
 */
function loadRaw(dataDir) {
  const filename = path.join(dataDir, 'books.json');
  const data = readJson(filename);
  if (!isPlainObject(data)) throw new TypeError('books.json 顶层必须是对象');
  const supplement = path.join(dataDir, 'phrase_books.json');
  if (fs.existsSync(supplement)) {
    const extra = readJson(supplement);
    if (!isPlainObject(extra)) throw new TypeError('phrase_books.json 顶层必须是对象');
    const items = extra.items === undefined ? [] : requireArray(extra.items, 'phrase_books.items');
    const groups = new Map();
    for (const main of requireArray(data.mains === undefined ? [] : data.mains, 'books.mains')) {
      for (const group of requireArray(
        main.groups === undefined ? [] : main.groups,
        'books.mains[].groups',
      )) {
        groups.set(group.id, group);
      }
    }
    for (const item of items) {
      if (!isPlainObject(item)) throw new TypeError('phrase_books.items[] 必须是对象');
      const group = groups.get(item.group);
      if (!group) continue;
      const existing = requireArray(group.items === undefined ? [] : group.items, 'group.items');
      if (existing.some((old) => old.id === item.id)) continue;
      existing.push(item);
      const union = group.union;
      if (!isPlainObject(union)) throw new TypeError('分组缺少 union 对象');
      const words = requireArray(union.words, 'union.words');
      const seen = new Set(words);
      for (const word of requireArray(item.words, 'phrase item.words')) {
        if (!seen.has(word)) {
          words.push(word);
          seen.add(word);
        }
      }
      union.count = words.length;
    }
  }
  return data;
}

/**
 * 由原始 data 建立目录结构（对应 Python `_build`）。
 * @param {object} data
 */
function build(data) {
  /** @type {Object<string, object>} */
  const books = Object.create(null);
  const mains = [];
  /** @type {Object<string, object>} */
  const groups = Object.create(null);
  for (const m of requireArray(data.mains === undefined ? [] : data.mains, 'books.mains')) {
    const mainEntry = { id: m.id, name: m.name, groups: [] };
    for (const g of requireArray(m.groups === undefined ? [] : m.groups, 'main.groups')) {
      const u = g.union;
      if (!isPlainObject(u)) throw new TypeError('分组缺少 union 对象');
      const gid = g.id;
      const unionName = g.union_name || `${g.name}（全选）`;
      const unionBook = {
        id: u.id,
        name: unionName,
        display: unionName,
        count: u.count,
        words: u.words,
        kind: 'union',
        type: 'word',
        series: '',
        is_union: true,
        group: gid,
        main: m.id,
        path: [m.name, g.name],
        source_status: 'community_compilation',
        source_version: 'community',
        count_rule: 'ordered_unique_first_occurrence_union',
        official_entry_count: null,
        source_note: '词表由民间整理；分组全选按现有成员首次出现去重。',
      };
      books[unionBook.id] = unionBook;
      const items = [];
      for (const it of requireArray(g.items === undefined ? [] : g.items, 'group.items')) {
        const b = {
          id: it.id,
          name: it.name,
          display: it.display || it.name,
          count: it.count,
          words: it.words,
          kind: it.kind || '',
          type: it.type || 'word',
          series: it.series || '',
          is_union: false,
          group: gid,
          main: m.id,
          path: [m.name, g.name],
        };
        Object.assign(b, {
          source_status: 'community_compilation',
          source_version: 'community',
          count_rule: 'existing_ordered_membership',
          official_entry_count: null,
          source_note: '词表由民间整理；保留原始成员与顺序。',
        });
        books[b.id] = b;
        items.push(b);
      }
      const series = [];
      for (const it of items) {
        const s = it.series || '';
        if (s && !series.includes(s)) series.push(s);
      }
      const gg = {
        id: gid,
        name: g.name,
        main: m.id,
        union: unionBook,
        items,
        series,
        count: items.length,
      };
      groups[gid] = gg;
      mainEntry.groups.push(gg);
    }
    mains.push(mainEntry);
  }
  return { books, mains, groups };
}

function callableList(fn, getList) {
  return new Proxy(fn, {
    get(target, prop, receiver) {
      const list = getList();
      if (prop === 'length') return list.length;
      if (prop === Symbol.iterator) return list[Symbol.iterator].bind(list);
      if (typeof prop === 'string' && /^\d+$/.test(prop)) return list[Number(prop)];
      if (prop in target) return Reflect.get(target, prop, receiver);
      const value = list[prop];
      return typeof value === 'function' ? value.bind(list) : value;
    },
  });
}

function createHandle(dataDir) {
  const data = loadRaw(dataDir);
  const { books, mains, groups } = build(data);
  const mainIds = Object.keys(books);
  const DEFAULT = Object.prototype.hasOwnProperty.call(books, 'cet6-dg')
    ? 'cet6-dg'
    : (mainIds.length ? mainIds[0] : null);

  const mainsFn = () => mains;
  const groupsFn = (mainId = null) => {
    if (mainId === null || mainId === undefined) {
      const out = [];
      for (const m of mains) out.push(...m.groups);
      return out;
    }
    const main = mains.find((m) => m.id === mainId);
    return main ? main.groups : [];
  };
  const itemsFn = (groupId) => {
    const group = groups[groupId];
    return group ? group.items : [];
  };
  const allFn = () => {
    const out = [];
    for (const m of mains) {
      for (const g of m.groups) {
        out.push(g.union);
        out.push(...g.items);
      }
    }
    return out;
  };

  const handle = {
    data,
    mains: callableList(mainsFn, mainsFn),
    groups: callableList(groupsFn, () => groupsFn()),
    items: itemsFn,
    all: callableList(allFn, allFn),
    resolve(bookId) {
      if (bookId !== null && bookId !== undefined
          && Object.prototype.hasOwnProperty.call(books, bookId)) {
        return bookId;
      }
      if (bookId !== null && bookId !== undefined
          && Object.prototype.hasOwnProperty.call(LEGACY, bookId)) {
        return LEGACY[bookId];
      }
      return DEFAULT;
    },
    get(bookId) {
      const id = handle.resolve(bookId);
      if (id === null || !Object.prototype.hasOwnProperty.call(books, id)) {
        throw new Error(`词库中没有可用的默认词书（请求 ${String(bookId)}）`);
      }
      return books[id];
    },
    words(bookId) {
      return handle.get(bookId).words;
    },
    size(bookId) {
      return handle.get(bookId).count;
    },
    name(bookId) {
      const book = handle.get(bookId);
      return book.display || book.name;
    },
    path(bookId) {
      const book = handle.get(bookId);
      return [...book.path, book.display].join(' · ');
    },
    sourceInfo(bookId) {
      const book = handle.get(bookId);
      return {
        status: 'community_compilation',
        version: 'community',
        study_count: book.count,
        official_entry_count: null,
        count_basis: book.is_union
          ? 'ordered_unique_first_occurrence_union'
          : 'existing_ordered_membership',
        source_ids: [],
        sources: [],
        note: book.source_note || '词表由民间整理。',
      };
    },
    sourceRows(bookId) {
      handle.get(bookId); // 保持无效 id 行为与其它 helper 一致
      return [];
    },
    DEFAULT,
    BY_ID: books,
    MAINS: mains,
    GROUPS: groups,
    LEGACY,
    DATA: dataDir,
  };
  // Python 别名（snake_case）。
  handle.source_info = handle.sourceInfo;
  handle.source_rows = handle.sourceRows;
  return handle;
}

let defaultHandle = null;
let defaultHandleDir = null;

/** 默认 data 目录：包内 `data/`，可用环境变量 DSH_VOCAB_APP_DATA_DIR 覆盖。 */
export function defaultDataDir() {
  const override = process.env.DSH_VOCAB_APP_DATA_DIR;
  return override ? path.resolve(override) : DATA;
}

/**
 * 读取真实 data 目录，返回词书目录句柄（只读）。
 * @param {string|null} [dataDir] 默认 `dsh-plugin/data`（可被 DSH_VOCAB_APP_DATA_DIR 覆盖）
 * @returns {{mains:Function,groups:Function,items:Function,all:Function,
 *   resolve:Function,get:Function,words:Function,size:Function,name:Function,
 *   path:Function,sourceInfo:Function,sourceRows:Function,DEFAULT:string,
 *   BY_ID:object,MAINS:Array,GROUPS:object,LEGACY:object,DATA:string}}
 */
export function load(dataDir = null) {
  if (dataDir === null || dataDir === undefined) {
    const directory = defaultDataDir();
    if (defaultHandle === null || defaultHandleDir !== directory) {
      defaultHandle = createHandle(directory);
      defaultHandleDir = directory;
    }
    return defaultHandle;
  }
  if (typeof dataDir !== 'string' || !dataDir) {
    throw new TypeError('books.load 需要 data 目录路径字符串');
  }
  return createHandle(path.resolve(dataDir));
}

/** 清空默认目录缓存（测试用）。 */
export function clearCache() {
  defaultHandle = null;
  defaultHandleDir = null;
}

export default { load, clearCache, defaultDataDir, LEGACY, DATA };
