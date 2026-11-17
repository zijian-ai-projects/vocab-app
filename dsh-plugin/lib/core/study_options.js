/**
 * 学习用四选一：四个真实释义、一个正确答案，没有测试陷阱或功能按钮。
 * 移植 app/study_options.py。
 *
 * 大量词条请复用 OptionPool(entries)。构造只冻结词条顺序，首次出题才预解析；
 * 后续只抽样少量已缓存释义，不在每题遍历全库、解析正则或洗牌万词列表。
 * 随机调用顺序与 Python 完全一致：先 `rng.sample(indices, min(count,12))`，
 * 最后 `rng.shuffle(options)`；没有可用 sample 时退回 shuffle 小批索引。
 */
import { meaning } from './entries.js';

const POS_RE = /\b[a-z]{1,7}\.\s*/gi;
const SPLIT_RE = /[；;，,\n\r、/]|\\n/g;
const RESERVED = new Set(['没有正确答案', '不认识']);
export const SAMPLE_SIZE = 12;

const STRIP_CHARS = /^[ .。!?？！:：]+|[ .。!?？！:：]+$/g;

function normalizeWhitespace(part) {
  return part.split(/\s+/).filter(Boolean).join(' ');
}

/** 只用于比较的义项规范化；展示文本仍完整取自真实词条。 */
function sensesOf(text) {
  const prepared = text.replace(/\\n/g, '\n').toLowerCase().replace(POS_RE, '');
  const out = new Set();
  for (const part of prepared.split(SPLIT_RE)) {
    const normalized = normalizeWhitespace(part).replace(STRIP_CHARS, '');
    if (normalized) out.add(normalized);
  }
  return out;
}

function senseGroupKey(senses) {
  return Array.from(senses).sort().join('\u0000');
}

function signature(entry) {
  const rawPos = entry.pos ? entry.pos : null;
  let firstPos = null;
  if (typeof rawPos === 'string') firstPos = rawPos;
  else if (Array.isArray(rawPos) && rawPos.length) firstPos = rawPos[0];
  return [
    entry.w === undefined ? null : entry.w,
    entry.s === undefined ? null : entry.s,
    entry.raw === undefined ? null : entry.raw,
    firstPos === undefined ? null : firstPos,
    entry.display_s === undefined ? null : entry.display_s,
    entry.level_s === undefined ? null : entry.level_s,
  ];
}

function signatureEquals(left, right) {
  if (left === right) return true;
  if (!left || !right || left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

function usable(parsed) {
  if (!parsed.text || parsed.senses.size === 0) return false;
  for (const item of parsed.senses) if (RESERVED.has(item)) return false;
  return true;
}

export class OptionPool {
  /** @param {Iterable<Record<string, unknown>>} entries */
  constructor(entries) {
    this.entries = Array.from(entries);
    this._choices = null;
    this._byEntry = new Map();
    this._senseCache = new Map();
  }

  get length() {
    return this.entries.length;
  }

  /** 兼容 Python `len(pool)`。 */
  get size() {
    return this.entries.length;
  }

  get prepared() {
    return this._choices !== null;
  }

  _parse(entry) {
    const text = meaning(entry);
    let senses = this._senseCache.get(text);
    if (senses === undefined) {
      senses = sensesOf(text);
      this._senseCache.set(text, senses);
    }
    return { key: entry.w === undefined ? null : entry.w, text, senses };
  }

  /**
   * 每池只预解析一次；返回 this，方便显式预热/性能测量。
   */
  prepare() {
    if (this.prepared) return this;
    const groups = new Map();
    const byEntry = new Map();
    for (const entry of this.entries) {
      const parsed = this._parse(entry);
      byEntry.set(entry, { signature: signature(entry), parsed });
      if (!usable(parsed)) continue;
      const groupKey = senseGroupKey(parsed.senses);
      let group = groups.get(groupKey);
      if (!group) {
        group = { text: parsed.text, senses: parsed.senses, keys: new Set() };
        groups.set(groupKey, group);
      }
      group.keys.add(parsed.key);
    }
    this._byEntry = byEntry;
    this._choices = Array.from(groups.values()).map((group) => ({
      text: group.text,
      senses: group.senses,
      keys: group.keys,
    }));
    return this;
  }

  _target(entry) {
    this.prepare();
    const sig = signature(entry);
    const cached = this._byEntry.get(entry);
    if (cached !== undefined && signatureEquals(cached.signature, sig)) {
      return cached.parsed;
    }
    const parsed = this._parse(entry);
    if (cached !== undefined) {
      // 只刷新当题 entry；完整词库变更需重新构池，不能逐题全库检查。
      this._byEntry.set(entry, { signature: sig, parsed });
    }
    return parsed;
  }

  /** 兼容 Python 私有名 `_target` 的公开别名。 */
  target(entry) {
    return this._target(entry);
  }

  static _eligible(choice, target) {
    if (choice.text === target.text) return false;
    if (target.key !== null && choice.keys.has(target.key)) return false;
    for (const sense of target.senses) if (choice.senses.has(sense)) return false;
    return true;
  }

  _distractors(target, rng) {
    const count = this._choices.length;
    if (count < 3) throw new Error('需要至少三个不同的其它释义');
    const indices = Array.from({ length: count }, (_, index) => index);
    let sampled;
    if (rng && typeof rng.sample === 'function') {
      sampled = rng.sample(indices, Math.min(count, SAMPLE_SIZE));
    } else {
      // 旧 API 只要求 shuffle；兼容这种固定测试 RNG，也只洗牌小批索引。
      sampled = indices.slice(0, Math.min(count, SAMPLE_SIZE));
      rng.shuffle(sampled);
    }
    const candidates = [];
    for (const index of sampled) {
      const choice = this._choices[index];
      if (OptionPool._eligible(choice, target)) {
        candidates.push(choice.text);
        if (candidates.length === 3) return candidates;
      }
    }
    // 很小/大量同义的池可能抽样不足；只扫已解析缓存，绝不回退同义「正确」干扰项。
    const sampledSet = new Set(sampled);
    for (let index = 0; index < this._choices.length; index += 1) {
      if (sampledSet.has(index)) continue;
      const choice = this._choices[index];
      if (OptionPool._eligible(choice, target)) {
        candidates.push(choice.text);
        if (candidates.length === 3) return candidates;
      }
    }
    throw new Error('需要至少三个不同且不与正确义项重复的其它释义');
  }
}

/**
 * 返回 {options: 四个真实释义, correct: 0..3}；不认识由 UI 的第五项提供。
 * list/其它 iterable 保持兼容，会临时构池；每题复用 OptionPool 才是大词库性能路径。
 * @param {Record<string, unknown>} entry
 * @param {OptionPool|Iterable<Record<string, unknown>>} pool
 * @param {{sample?:Function, shuffle:Function}} rng 必须注入（本仓库 rng.js 的 makeRng）
 * @returns {{options: string[], correct: number}}
 */
export function makeOptions(entry, pool, rng) {
  if (!rng || typeof rng.shuffle !== 'function') {
    throw new TypeError('makeOptions 需要通过参数注入 rng（不要用全局 Math.random）');
  }
  const optionPool = pool instanceof OptionPool ? pool : new OptionPool(pool);
  const target = optionPool._target(entry);
  if (!usable(target)) {
    throw new Error('词条缺少可用真实释义，不能生成学习选择题');
  }
  const options = optionPool._distractors(target, rng).concat([target.text]);
  rng.shuffle(options);
  return { options, correct: options.indexOf(target.text) };
}

// 兼容 Python 同名导出。
export const make_options = makeOptions;

export default { OptionPool, makeOptions, SAMPLE_SIZE };
