/**
 * 小学/初中学段释义覆盖（移植 app/level_meanings.py）：
 * 安全加载 data/level_meanings.json，不修改通用 bank。
 *
 * 文件格式兼容两种（数据 owner 可任选）：
 *   {"primary": {"word": "小学释义"}, "middleschool": {...}}
 *   {"levels": {"primary": {...}, "middleschool": {...}}}
 * 值可为字符串，或含 display_s/level_s（也接受 s/meaning/text/gloss）的对象；
 * 有效释义对象可附 display_w，学校词形与稳定 key 分离。
 * 任何缺失/损坏/非法字段都安全回退为空覆盖，不抛异常。
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
export const DEFAULT_PATH = path.join(DATA, 'level_meanings.json');
export const STAGES = Object.freeze(['primary', 'middleschool']);

const STAGE_ALIASES = [
  ['primary', 'primary'],
  ['middleschool', 'middleschool'],
  ['middle_school', 'middleschool'],
  ['middle', 'middleschool'],
];
const STAGE_BY_MAIN = Object.freeze({ primary: 'primary', middleschool: 'middleschool' });

let CACHE = null;
let CACHE_PATH = null;
let CACHE_MTIME = null;

/** 默认数据目录：包内 `data/`，可用环境变量 DSH_VOCAB_APP_DATA_DIR 覆盖。 */
export function defaultDataDir() {
  const override = process.env.DSH_VOCAB_APP_DATA_DIR;
  return override ? path.resolve(override) : DATA;
}

export function defaultPath() {
  return path.join(defaultDataDir(), 'level_meanings.json');
}

export function stageForMain(main) {
  return Object.prototype.hasOwnProperty.call(STAGE_BY_MAIN, main) ? STAGE_BY_MAIN[main] : null;
}

/** Python 属性名别名。 */
export const stage_for_main = stageForMain;

function textOf(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function normalise(value) {
  if (typeof value === 'string') {
    const text = textOf(value);
    if (!text) return {};
    // 文件是纯字符串时，同时提供两个兼容字段，entries.meaning 取首个有效值。
    return { display_s: text, level_s: text };
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return {};
  const out = {};
  for (const field of ['display_s', 'level_s']) {
    const text = textOf(value[field]);
    if (text) out[field] = text;
  }
  if (Object.keys(out).length === 0) {
    for (const field of ['s', 'meaning', 'text', 'gloss']) {
      const text = textOf(value[field]);
      if (text) {
        out.display_s = text;
        out.level_s = text;
        break;
      }
    }
  }
  if (Object.keys(out).length) {
    const displayWord = textOf(value.display_w);
    if (displayWord) out.display_w = displayWord;
  }
  return out;
}

function stageMapping(source, stage) {
  let raw = source[stage];
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    for (const [alias, canonical] of STAGE_ALIASES) {
      if (canonical !== stage) continue;
      const value = source[alias];
      if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
        raw = value;
        break;
      }
    }
  }
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const result = {};
  for (const word of Object.keys(raw)) {
    if (!word) continue;
    const normalised = normalise(raw[word]);
    if (Object.keys(normalised).length) result[word] = normalised;
  }
  return result;
}

function emptyResult() {
  const out = {};
  for (const stage of STAGES) out[stage] = {};
  return out;
}

/**
 * 返回 {primary: {word: {display_s/level_s}}, middleschool: {...}}。
 * @param {string|null} [dataDir] 默认 `dsh-plugin/data`；显式传入时不缓存（对齐 Python path 参数）
 */
export function load(dataDir = null) {
  const explicit = dataDir !== null && dataDir !== undefined;
  let filename;
  if (explicit) {
    if (typeof dataDir !== 'string' || !dataDir) {
      throw new TypeError('level_meanings.load 需要 data 目录路径字符串');
    }
    filename = path.join(path.resolve(dataDir), 'level_meanings.json');
  } else {
    filename = defaultPath();
  }
  const cached = !explicit && CACHE !== null && CACHE_PATH === filename;
  if (cached) {
    let mtime = null;
    try {
      mtime = fs.existsSync(filename) ? fs.statSync(filename).mtimeMs : null;
    } catch {
      mtime = null;
    }
    if (mtime === CACHE_MTIME) return CACHE;
  }
  let result;
  try {
    if (!fs.existsSync(filename)) {
      result = emptyResult();
    } else {
      const data = JSON.parse(fs.readFileSync(filename, 'utf8'));
      if (data === null || typeof data !== 'object' || Array.isArray(data)) {
        result = emptyResult();
      } else {
        const levels = data.levels;
        const source = levels !== null && typeof levels === 'object' && !Array.isArray(levels)
          ? levels
          : data;
        result = {};
        for (const stage of STAGES) result[stage] = stageMapping(source, stage);
        // levels 不完整时也兼容顶层同名字段
        for (const stage of STAGES) {
          if (Object.keys(result[stage]).length === 0) {
            result[stage] = stageMapping(data, stage);
          }
        }
      }
    }
  } catch {
    result = emptyResult();
  }
  if (!explicit) {
    let mtime = null;
    try {
      mtime = fs.existsSync(filename) ? fs.statSync(filename).mtimeMs : null;
    } catch {
      mtime = null;
    }
    CACHE = result;
    CACHE_PATH = filename;
    CACHE_MTIME = mtime;
  }
  return result;
}

export function clearCache() {
  CACHE = null;
  CACHE_PATH = null;
  CACHE_MTIME = null;
}

/**
 * @param {string} stage
 * @param {string|null} [dataDir] 显式数据目录（可选；默认走包内 data/）
 */
export function mappingFor(stage, dataDir = null) {
  if (!STAGES.includes(stage)) return {};
  const mapping = dataDir ? load(dataDir) : load();
  return mapping[stage] || {};
}

export const mapping_for = mappingFor;

/**
 * 浅拷贝有效显示义/可选学校词形；标记学校 caption 但绝不改原 entry。
 * @param {Record<string, unknown>} entry
 * @param {Record<string, object>|null} [mapping]
 */
export function decorate(entry, mapping = null) {
  if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
    throw new TypeError('decorate 需要词条对象');
  }
  const copy = { ...entry };
  if (mapping && Object.keys(mapping).length) {
    const override = mapping[copy.w];
    if (override && Object.keys(override).length) {
      for (const field of ['display_s', 'level_s', 'display_w']) {
        const text = override[field];
        if (text) copy[field] = text;
      }
      if (textOf(override.display_w)) copy._school_caption = true;
    }
  }
  return copy;
}

export default {
  STAGES,
  load,
  clearCache,
  mappingFor,
  decorate,
  stageForMain,
  DEFAULT_PATH,
};
