/**
 * V1.3 纯逻辑记忆排期（移植 app/scheduler.py）。
 *
 * lv=0 是尚未认识的新词，没有时间排期。认识后进入 lv=1，随后每次记得升一级；
 * lv=1..9 记得后按新等级在 5min..30d 后复习，不认识则同级 5min 后重试；lv=10 出库。
 * 迁移只改变等级表示，不重新计算已保存的时间。所有状态操作返回副本，绝不修改传入状态。
 */

export const MIN = 60;
export const HOUR = 3600;
export const DAY = 86400;

export const LEVELS = Object.freeze([
  5 * MIN,
  30 * MIN,
  12 * HOUR,
  DAY,
  2 * DAY,
  4 * DAY,
  7 * DAY,
  15 * DAY,
  30 * DAY,
]);

export const LEVEL_NAMES = Object.freeze([
  '5分钟',
  '30分钟',
  '12小时',
  '1天',
  '2天',
  '4天',
  '7天',
  '15天',
  '30天',
]);

export const MASTERED = 10;
/** Python 里语义为「已完成/不需再学」的状态集合。 */
export const DONE = Object.freeze(['retired', 'mastered', 'learning', 'known']);
const TERMINAL = new Set(['retired', 'mastered', 'known']);

function nowValue(now) {
  // 0 是合法的固定时钟，不能用 `now || Date.now()/1000`。
  return now === null || now === undefined ? Date.now() / 1000 : now;
}

/** Python 真值语义（空对象为假）。 */
function pyTruthy(value) {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === 'number') return value !== 0 && !Number.isNaN(value);
  if (typeof value === 'string') return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

/** Python int()：非法值抛出异常，由调用方决定回退。 */
function pyInt(value) {
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new RangeError('cannot convert to integer');
    return Math.trunc(value);
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (!/^[+-]?\d+$/.test(text)) throw new TypeError('invalid literal for int()');
    const number = Number(text);
    if (!Number.isFinite(number)) throw new RangeError('integer too large');
    return Math.trunc(number);
  }
  throw new TypeError('int() argument must be a number or string');
}

function copyState(state) {
  // 状态是 JSON 安全的普通对象；structuredClone 深拷贝并保留未知字段。
  return structuredClone(state);
}

/**
 * Python 数值加法语义：数值/布尔可以相加，字符串会抛 TypeError（不会拼接）。
 */
function addNumbers(left, right, label) {
  const toNumber = (value) => {
    if (typeof value === 'number') return value;
    if (typeof value === 'boolean') return value ? 1 : 0;
    throw new TypeError(`${label} 必须是数字`);
  };
  return toNumber(left) + toNumber(right);
}

function assertStateObject(st, purpose) {
  if (st === null || st === undefined) return null;
  if (typeof st !== 'object' || Array.isArray(st)) {
    throw new TypeError(`${purpose} 需要状态对象`);
  }
  return st;
}

/** 0..10 的等级；非法 lv 按 0。 */
export function levelOf(st) {
  const state = assertStateObject(st, 'levelOf');
  if (!pyTruthy(state)) return 0;
  try {
    return Math.max(0, Math.min(MASTERED, pyInt(state.lv === undefined ? 0 : state.lv)));
  } catch {
    return 0;
  }
}

export function isNew(st) {
  const state = assertStateObject(st, 'isNew');
  if (!pyTruthy(state)) return true;
  const status = state.st === undefined ? 'new' : state.st;
  return status === 'new' && levelOf(state) === 0;
}

export function isLearning(st) {
  const state = assertStateObject(st, 'isLearning');
  if (!pyTruthy(state)) return false;
  return state.st === 'learning' && levelOf(state) >= 1 && levelOf(state) < MASTERED;
}

/** @returns {{lv:number,due:null,seen:number,lapse:number,streak:number,st:string}} */
export function newState(now = null) {
  void now; // 兼容旧调用的占位参数。
  return { lv: 0, due: null, seen: 0, lapse: 0, streak: 0, st: 'new' };
}

/**
 * 返回独立副本，把旧 0 基等级转换为 V1.3 的 1 基学习等级。
 * legacy 必须由调用方 memory_schema != 2 决定；现代状态幂等。
 */
export function migrateState(st, legacy = false) {
  const source = assertStateObject(st, 'migrateState');
  const out = pyTruthy(source) ? copyState(source) : newState();
  if ('retry_now' in out) delete out.retry_now;
  let lv = levelOf(out);
  let status = pyTruthy(out.st) ? out.st : (lv ? 'learning' : 'new');

  if (legacy) {
    if (status === 'new') {
      lv = 1;
      status = 'learning';
    } else if (status === 'learning') {
      lv = Math.min(MASTERED, lv + 1);
    } else if (status === 'mastered') {
      lv = MASTERED;
    }
  }

  if (status === 'mastered' || (lv === MASTERED && status !== 'retired' && status !== 'known')) {
    lv = MASTERED;
    status = 'mastered';
  } else if (status === 'new' || status === 'learning') {
    status = lv ? 'learning' : 'new';
  }

  out.lv = lv;
  out.st = status;
  if (!('due' in out)) out.due = null;
  if (TERMINAL.has(status) || (status === 'new' && lv === 0)) out.due = null;
  if (!('seen' in out)) out.seen = 0;
  if (!('lapse' in out)) out.lapse = 0;
  if (!('streak' in out)) out.streak = 0;
  return out;
}

/** 逐词迁移；原 states 和其中的状态均不修改。 */
export function migrateStates(states, legacy = false) {
  if (states === null || typeof states !== 'object' || Array.isArray(states)) {
    throw new TypeError('migrateStates 需要 states 对象');
  }
  const out = {};
  for (const key of Object.keys(states)) {
    out[key] = migrateState(states[key], legacy);
  }
  return out;
}

/** 认识新词进入 1 级；记得旧词升一级，10 级永久出库。 */
export function onRemember(st, now = null) {
  const out = migrateState(st);
  if (TERMINAL.has(out.st)) return out;
  out.seen = addNumbers(out.seen, 1, 'seen');
  out.streak = 0;
  const lv = Math.min(MASTERED, out.lv + 1);
  out.lv = lv;
  out.st = lv === MASTERED ? 'mastered' : 'learning';
  out.due = lv === MASTERED ? null : addNumbers(nowValue(now), LEVELS[lv - 1], 'due');
  return out;
}

/** 忘记不退级：旧词固定 5 分钟后重试，新词仍然是无 due 的新词。 */
export function onForget(st, now = null) {
  const out = migrateState(st);
  if (TERMINAL.has(out.st)) return out;
  out.seen = addNumbers(out.seen, 1, 'seen');
  out.lapse = addNumbers(out.lapse, 1, 'lapse');
  out.streak = addNumbers(out.streak, 1, 'streak');
  const lv = out.lv;
  out.st = lv ? 'learning' : 'new';
  out.due = lv ? addNumbers(nowValue(now), 5 * MIN, 'due') : null;
  return out;
}

/** 兼容旧的模糊按钮：同级刷新，不升降级，不增加 lapse。 */
export function onFuzzy(st, now = null) {
  const out = migrateState(st);
  if (TERMINAL.has(out.st)) return out;
  out.seen = addNumbers(out.seen, 1, 'seen');
  out.streak = 0;
  const lv = out.lv;
  out.st = lv ? 'learning' : 'new';
  out.due = lv ? addNumbers(nowValue(now), LEVELS[lv - 1], 'due') : null;
  return out;
}

/** 保留旧 API 的主动出库；不会再被新词或复习队列选中。 */
export function onRetire(st) {
  const out = migrateState(st);
  out.st = 'retired';
  out.due = null;
  return out;
}

function* dueEntries(words, states, now) {
  for (let idx = 0; idx < words.length; idx += 1) {
    const w = words[idx];
    const key = w && w.w;
    const st = states[key];
    if (isLearning(st) && st.due !== null && st.due !== undefined && st.due <= now) {
      yield { idx, w, st };
    }
  }
}

/**
 * 保留旧 (due, word, state) 结构，按传入词书顺序而不是 due 排序。
 * @returns {Array<[number, object, object]>}
 */
export function dueQueue(words, states, now = null) {
  const time = nowValue(now);
  const out = [];
  for (const { w, st } of dueEntries(words, states, time)) out.push([st.due, w, st]);
  return out;
}

/** 当前词书此刻的到期旧词；idx 是传入 words 的真实索引。 */
export function reviewItems(words, states, now = null) {
  const time = nowValue(now);
  const out = [];
  for (const { idx, w, st } of dueEntries(words, states, time)) {
    out.push({ kind: 'review', w, st, idx });
  }
  return out;
}

/**
 * 兼容旧的单步新词 API，返回 [item, cursor]，不修改 states。
 * 此 API 不管理重试间隔；完整学习流程使用 StudyQueue。
 * @returns {[object, number]}
 */
export function nextNew(words, states, cursor) {
  // Python int(cursor) 对非法输入抛错，不静默变 0；负游标按 0 处理。
  let i = Math.max(0, pyInt(cursor));
  if (!Number.isFinite(i)) i = 0;
  while (i < words.length) {
    const w = words[i];
    const key = w && w.w;
    const st = states[key];
    if (isNew(st)) {
      return [{ kind: 'new', w, st: st === undefined ? null : st, idx: i }, i];
    }
    i += 1;
  }
  return [null, i];
}

// 兼容 Python 同名导出（host 层优先使用 camelCase）。
export const new_state = newState;
export const migrate_state = migrateState;
export const migrate_states = migrateStates;
export const on_remember = onRemember;
export const on_forget = onForget;
export const on_fuzzy = onFuzzy;
export const on_retire = onRetire;
export const due_queue = dueQueue;
export const review_items = reviewItems;
export const next_new = nextNew;

export default {
  MIN,
  HOUR,
  DAY,
  LEVELS,
  LEVEL_NAMES,
  MASTERED,
  DONE,
  newState,
  migrateState,
  migrateStates,
  onRemember,
  onForget,
  onFuzzy,
  onRetire,
  dueQueue,
  reviewItems,
  nextNew,
};
