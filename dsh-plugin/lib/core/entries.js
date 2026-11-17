/**
 * 词条展示与记忆分类（移植 app/entries.py）。
 *
 * 词和词组共用数据；不编造音标或词性。所有函数纯读取传入词条，不修改它。
 */

export const CATEGORIES = Object.freeze([
  Object.freeze(['all', '全部']),
  Object.freeze(['learned', '已学习']),
  Object.freeze(['unlearned', '待学习']),
]);

const POS_RE = /^(?:n|v|vt|vi|adj|adv|prep|conj|pron|det|art|num|aux|int|interj|abbr)\./;

/** Python 真值语义（空 dict/空 list 为假）。 */
export function pyTruthy(value) {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === 'number') return value !== 0 && !Number.isNaN(value);
  if (typeof value === 'string') return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

/** Python int(value)：拒绝非整数浮点/非数字字符串，None/对象抛错。 */
export function pyInt(value) {
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new RangeError('cannot convert to integer');
    return Math.trunc(value);
  }
  if (typeof value === 'string') {
    const text = value.trim();
    const match = /^[+-]?\d+$/.exec(text);
    if (!match) throw new TypeError('invalid literal for int()');
    const number = Number(text);
    if (!Number.isFinite(number)) throw new RangeError('integer too large');
    return Math.trunc(number);
  }
  throw new TypeError('int() argument must be a number or string');
}

/** 与 StudyQueue._count 一致：非法/缺失计数按 0，不抛异常。 */
export function countOf(value, fallback = 0) {
  try {
    return Math.max(0, pyInt(value));
  } catch {
    return fallback;
  }
}

function requireObject(entry, purpose) {
  if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
    throw new TypeError(`${purpose} 需要词条对象`);
  }
  return entry;
}

/**
 * 显示拼写与稳定记忆 key 分离（如显示 I，而学习 key 仍是 i）。
 * @param {Record<string, unknown>} entry
 */
export function wordCaption(entry) {
  requireObject(entry, 'wordCaption');
  const value = entry.display_w;
  if (typeof value === 'string' && value.trim()) return value;
  if (!Object.prototype.hasOwnProperty.call(entry, 'w')) {
    throw new TypeError('词条缺少稳定 key（w）');
  }
  return entry.w;
}

/** @param {Record<string, unknown>} entry */
export function isPhrase(entry) {
  requireObject(entry, 'isPhrase');
  if (entry.type === 'phrase') return true;
  const word = entry.w === undefined || entry.w === null ? '' : entry.w;
  if (typeof word !== 'string') throw new TypeError('词条的 w 必须是字符串');
  return /\s/.test(word);
}

/**
 * 学段覆盖优先：display_s / level_s；空串/非字符串回退通用 s/raw。
 * @param {Record<string, unknown>} entry
 */
export function meaning(entry) {
  requireObject(entry, 'meaning');
  let text = '';
  for (const field of ['display_s', 'level_s']) {
    const value = entry[field];
    if (typeof value === 'string' && value.trim()) {
      text = value.trim();
      break;
    }
  }
  if (!text) {
    const fallback = pyTruthy(entry.s) ? entry.s : (pyTruthy(entry.raw) ? entry.raw : '');
    if (fallback && typeof fallback !== 'string') {
      throw new TypeError('词条的 s/raw 必须是字符串');
    }
    text = fallback.trim();
  }
  let pos = entry.pos;
  if (typeof pos === 'string') pos = [pos];
  if (!pyTruthy(pos)) pos = [];
  if (!Array.isArray(pos)) throw new TypeError('词条的 pos 必须是字符串或数组');
  if (text && pos.length && !POS_RE.test(text)) {
    if (typeof pos[0] !== 'string') throw new TypeError('词条的 pos[0] 必须是字符串');
    const prefix = pos[0].trim();
    if (prefix && prefix !== 'na.' && prefix !== 'un.') text = `${prefix} ${text}`;
  }
  return text;
}

/** 仅采用已有且完整的音标；词组没有音标。 */
export function pronunciation(entry) {
  requireObject(entry, 'pronunciation');
  if (isPhrase(entry)) return '';
  for (const field of ['ipa', 'ph_raw']) {
    const value = entry[field];
    if (typeof value !== 'string') continue;
    let ipa = value.trim();
    ipa = ipa.replace(/^\/+/, '').replace(/\/+$/, '').trim();
    if (!ipa || ipa.includes('\\')) continue;
    let hasControl = false;
    for (let i = 0; i < ipa.length; i += 1) {
      if (ipa.charCodeAt(i) < 32) {
        hasControl = true;
        break;
      }
    }
    if (hasControl) continue;
    const folded = ipa.toLowerCase();
    if (['n/a', 'not available', '无', '暂无', '暂无音标'].includes(folded)) continue;
    const blocked = new Set(['ˈ', 'ˌ', 'ː', 'ˑ']);
    let hasLetter = false;
    for (const char of Array.from(ipa)) {
      if (!blocked.has(char) && /\p{L}/u.test(char)) {
        hasLetter = true;
        break;
      }
    }
    if (!hasLetter) continue;
    return `/${ipa}/`;
  }
  return '';
}

function hasMembership(collection, key) {
  if (collection === null || collection === undefined) return false;
  if (collection instanceof Set) return collection.has(key);
  if (Array.isArray(collection)) return collection.includes(key);
  if (typeof collection === 'object') return Object.prototype.hasOwnProperty.call(collection, key);
  return false;
}

/**
 * 返回 [分类, 真实等级或 null, 标签]；预测永不伪造真实等级。
 * @param {string} key
 * @param {Record<string, object|null|undefined>} states
 * @param {Iterable<string>|Array<string>|null} [known]
 * @param {Iterable<string>|Array<string>|null} [predicted]
 * @returns {[string, number|null, string]}
 */
export function memoryInfo(key, states, known = null, predicted = null) {
  if (states === null || typeof states !== 'object') {
    throw new TypeError('memoryInfo 需要 states 对象');
  }
  const raw = states[key];
  const state = pyTruthy(raw) ? raw : {};
  const status = state.st;
  let level = 0;
  try {
    level = Math.max(0, Math.min(10, pyInt(state.lv === undefined ? 0 : state.lv)));
  } catch {
    level = 0;
  }
  if (status === 'mastered' || status === 'retired' || level >= 10) {
    return ['mastered', 10, 'Lv10 · 已掌握'];
  }
  if (status === 'known') return ['known', null, '认识 · 旧版已会'];
  if (level > 0 && status !== 'new') return ['known', level, `Lv${level} · 认识`];
  // 真实作答证据与显式状态优先于一切估计。
  if (pyTruthy(state) && (countOf(state.seen) || countOf(state.lapse))) {
    return ['unlearned', 0, '待学习'];
  }
  if (pyTruthy(state)) return ['unlearned', 0, '待学习'];
  if (hasMembership(known, key)) return ['known', null, '认识 · 测试估计'];
  if (hasMembership(predicted, key)) return ['predicted', null, '已掌握'];
  return ['unlearned', 0, '待学习'];
}

export default {
  CATEGORIES,
  wordCaption,
  isPhrase,
  meaning,
  pronunciation,
  memoryInfo,
};
