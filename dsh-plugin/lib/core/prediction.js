/**
 * 纯 V1.4 预测选择与分类辅助（移植 app/prediction.py）。
 *
 * 预测记录独立于 scheduler states；持久化形状由 newPredictionData 给出，
 * 边界处用 validatePredictionData 校验。
 *
 * 随机：`selectPredictionCandidates` 的 seed 与 Python `random.Random(seed)` 对应，
 * 本仓库用 `lib/core/rng.js` 的 makeRng 派生同一份确定性序列；测试可传第 8 个
 * 参数 `rng` 注入固定序列以做逐项差分。
 */
import { randomBytes } from 'node:crypto';
import { makeRng } from './rng.js';

export const SCHEMA = 1;
export const STRATEGIES = Object.freeze(['conservative', 'estimate', 'optimistic']);

export function newPredictionData() {
  return {
    schema: SCHEMA,
    selected: [],
    rejected: [],
    excluded: [],
    effective: { target: 0, available: 0, selected: 0 },
  };
}

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * 校验持久化 JSON 形状；返回原对象（不修改）。
 * @param {unknown} data
 */
export function validatePredictionData(data) {
  if (!isPlainObject(data) || data.schema !== SCHEMA) {
    throw new Error(`prediction schema must be ${SCHEMA}`);
  }
  for (const field of ['selected', 'rejected', 'excluded']) {
    const values = data[field];
    if (!Array.isArray(values)
        || values.some((key) => typeof key !== 'string' || !key)) {
      throw new Error(`prediction ${field} must be a list of non-empty keys`);
    }
    if (values.length !== new Set(values).size) {
      throw new Error(`prediction ${field} contains duplicate keys`);
    }
  }
  const effective = data.effective;
  if (!isPlainObject(effective)) {
    throw new Error('prediction effective counts must be an object');
  }
  for (const field of ['target', 'available', 'selected']) {
    const value = effective[field];
    if (typeof value === 'boolean' || !Number.isInteger(value) || value < 0) {
      throw new Error(`prediction effective.${field} must be a non-negative integer`);
    }
  }
  if (effective.selected !== data.selected.length) {
    throw new Error('prediction selected count does not match selected keys');
  }
  return data;
}

/** Python round()（银行家舍入）后取整。 */
function pyRound(value) {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff < 0.5) return floor;
  if (diff > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** Python repr（错误文案用）：字符串带单引号、None/True/False 用 Python 拼写。 */
function pyRepr(value) {
  if (typeof value === 'string') return `'${value}'`;
  if (value === null || value === undefined) return 'None';
  if (value === true) return 'True';
  if (value === false) return 'False';
  return String(value);
}

/**
 * 由估计与绝对误差余量解析目标词数。
 * @param {number} estimate
 * @param {number} error
 * @param {string} strategy
 * @returns {number}
 */
export function applyStrategy(estimate, error, strategy) {
  if (!STRATEGIES.includes(strategy)) {
    throw new Error(`unknown prediction strategy: ${pyRepr(strategy)}`);
  }
  if (typeof estimate === 'boolean' || typeof error === 'boolean'
      || typeof estimate !== 'number' || typeof error !== 'number'
      || !Number.isFinite(estimate) || !Number.isFinite(error)
      || estimate < 0 || error < 0) {
    throw new Error('estimate and error must be finite non-negative numbers');
  }
  const value = strategy === 'conservative'
    ? estimate - error
    : (strategy === 'optimistic' ? estimate + error : estimate);
  return Math.max(0, pyRound(value));
}

function entryBands(entries, bands) {
  if (bands === null || bands === undefined) {
    const out = new Map();
    for (const entry of entries) out.set(entry.w, entry.lvl === undefined ? 0 : entry.lvl);
    return out;
  }
  if (bands instanceof Map) return bands;
  if (isPlainObject(bands)) return bands;
  if (Array.isArray(bands) && bands.length === entries.length) {
    const out = new Map();
    for (let i = 0; i < entries.length; i += 1) out.set(entries[i].w, bands[i]);
    return out;
  }
  throw new Error('bands must be a key-to-level mapping or align with entries');
}

function levelLookup(levels, key) {
  if (levels instanceof Map) {
    if (!levels.has(key)) return { found: false, value: undefined };
    return { found: true, value: levels.get(key) };
  }
  if (Object.prototype.hasOwnProperty.call(levels, key)) {
    return { found: true, value: levels[key] };
  }
  return { found: false, value: undefined };
}

function membership(collection, key) {
  if (collection === null || collection === undefined) return false;
  if (collection instanceof Set) return collection.has(key);
  if (Array.isArray(collection)) return collection.includes(key);
  return false;
}

/** Python 真值语义（空 dict/list 为假）。 */
function pyTruthy(value) {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === 'number') return value !== 0 && !Number.isNaN(value);
  if (typeof value === 'string') return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

/**
 * 选出最容易的合格词；只对「部分使用的 band」洗牌。
 *
 * 任何带显式 scheduler 状态、pending 标记、rejected/excluded 的词一律略过；
 * 排除不会导致超出目标数量的额外补选。返回 [selectedKeys(Set), counts]。
 *
 * @param {Array<Record<string, unknown>>} entries
 * @param {Record<string, unknown>} states
 * @param {number} target
 * @param {object|Array<number>|null} [bands]
 * @param {Iterable<string>|null} [rejected]
 * @param {Iterable<string>|null} [excluded]
 * @param {number|string|null} [seed]
 * @param {{sample:Function}|null} [rng] 仅测试注入；默认由 seed 派生
 * @returns {[Set<string>, {target:number,available:number,selected:number,excluded:number}]}
 */
export function selectPredictionCandidates(
  entries,
  states,
  target,
  bandsOrOptions = null,
  rejected = null,
  excluded = null,
  seed = null,
  rng = null,
) {
  // 兼容两种调用形状：
  //   (entries, states, target, bands, rejected, excluded, seed)
  //   (entries, states, target, {bands, rejected, excluded, seed})
  let bands = bandsOrOptions;
  let rngOverride = rng;
  if (isPlainObject(bandsOrOptions)
      && ['bands', 'rejected', 'excluded', 'seed'].some(
        (field) => Object.prototype.hasOwnProperty.call(bandsOrOptions, field),
      )) {
    const options = bandsOrOptions;
    bands = options.bands === undefined ? null : options.bands;
    rejected = options.rejected === undefined ? null : options.rejected;
    excluded = options.excluded === undefined ? null : options.excluded;
    seed = options.seed === undefined ? null : options.seed;
    if (options.rng !== undefined) rngOverride = options.rng;
  }
  if (typeof target === 'boolean' || typeof target !== 'number'
      || !Number.isInteger(target) || target < 0) {
    throw new Error('target must be a non-negative integer');
  }
  if (!isPlainObject(states)) throw new Error('states must be an object');
  const rejectedSet = new Set(rejected || []);
  const excludedSet = new Set(excluded || []);
  const levels = entryBands(entries, bands);
  const eligible = [];
  let omitted = 0;
  for (const entry of entries) {
    const key = entry.w;
    if (typeof key !== 'string' || !key) continue;
    const looked = levelLookup(levels, key);
    if (!looked.found) continue;
    if (Object.prototype.hasOwnProperty.call(states, key)
        || rejectedSet.has(key) || excludedSet.has(key) || pyTruthy(entry.pending)) {
      omitted += 1;
      continue;
    }
    const level = looked.value;
    if (typeof level === 'boolean' || typeof level !== 'number' || !Number.isFinite(level)) {
      throw new Error('band levels must be finite numbers');
    }
    eligible.push([level, key]);
  }

  // 稳定按等级排序；完全选中的 band 内保留源顺序。
  eligible.sort((left, right) => left[0] - right[0]);
  const selected = new Set();
  let random = rngOverride;
  if (!random) {
    const material = seed === null || seed === undefined
      ? `prediction|v1|entropy|${randomBytes(16).toString('hex')}`
      : `prediction|v1|${String(seed)}`;
    random = makeRng(material);
  }
  let pos = 0;
  while (pos < eligible.length && selected.size < target) {
    const level = eligible[pos][0];
    let end = pos + 1;
    while (end < eligible.length && eligible[end][0] === level) end += 1;
    const band = eligible.slice(pos, end);
    const need = Math.min(target - selected.size, band.length);
    if (need < band.length) {
      for (const picked of random.sample(band, need)) selected.add(picked[1]);
      break;
    }
    for (const item of band) selected.add(item[1]);
    pos = end;
  }

  const counts = {
    target,
    available: eligible.length,
    selected: selected.size,
    excluded: omitted,
  };
  return [selected, counts];
}

// 兼容 Python 同名导出。
export const new_prediction_data = newPredictionData;
export const validate_prediction_data = validatePredictionData;
export const apply_strategy = applyStrategy;
export const select_prediction_candidates = selectPredictionCandidates;

export default {
  SCHEMA,
  STRATEGIES,
  newPredictionData,
  validatePredictionData,
  applyStrategy,
  selectPredictionCandidates,
};
