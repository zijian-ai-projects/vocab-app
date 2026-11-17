/**
 * 可选的累计学段词汇假设（移植 app/school_knowledge.py）：
 * 与记忆记录完全分离，只把某学段词书里的词当作「已认识」的预测。
 *
 * Python 用 lru_cache(maxsize=4) 缓存 frozenset；这里返回 Set 的新副本，
 * 调用方可以安全修改（等价于 frozenset 不可变）。
 */
import { load as loadBooks } from './books.js';

export const LEVELS = Object.freeze([
  Object.freeze(['off', '关闭']),
  Object.freeze(['primary', '小学']),
  Object.freeze(['middle', '小初']),
  Object.freeze(['high', '小初高']),
]);

export const BOOKS = Object.freeze(['xx-dg', 'zk-dg', 'gk-dg']);

const LEVEL_INDEX = new Map(LEVELS.map(([key], index) => [key, index]));
const CACHE = new Map(); // level -> Set（局部缓存，仅默认 books 句柄）
const HANDLE_CACHE = new WeakMap(); // books handle -> Map(level -> Set)

export function normalize(value) {
  return typeof value === 'string' && LEVEL_INDEX.has(value) ? value : 'off';
}

function compute(level, handle) {
  const index = LEVEL_INDEX.get(level);
  const words = new Set();
  for (const bookId of BOOKS.slice(0, index)) {
    for (const word of handle.words(bookId)) words.add(word);
  }
  return words;
}

/**
 * 某学段累计应认识词集合（Set<string> 新副本）。
 * @param {string} level 'off'|'primary'|'middle'|'high'（非法值按 'off'）
 * @param {ReturnType<typeof loadBooks>|null} [handle] 默认为 `books.load()`（只读 data/）
 * @returns {Set<string>}
 */
export function words(level, handle = null) {
  const normalized = normalize(level);
  if (handle) {
    let perHandle = HANDLE_CACHE.get(handle);
    if (!perHandle) {
      perHandle = new Map();
      HANDLE_CACHE.set(handle, perHandle);
    }
    if (!perHandle.has(normalized)) perHandle.set(normalized, compute(normalized, handle));
    return new Set(perHandle.get(normalized));
  }
  if (!CACHE.has(normalized)) CACHE.set(normalized, compute(normalized, loadBooks()));
  return new Set(CACHE.get(normalized));
}

/** 清空缓存（测试用；替代 Python lru_cache.cache_clear）。 */
export function clearCache() {
  CACHE.clear();
}

export default { LEVELS, BOOKS, normalize, words, clearCache };
