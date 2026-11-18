/**
 * 当前词书的可持久化学习队列（移植 app/study_queue.py）；不读写任何文件。
 *
 * words 已由调用方排好顺序，states 是跨书共享的记忆状态，record 是当前词书的
 * 队列记录。两个 dict 均原地更新，调用方负责原子保存：
 *   {cursor, new_count, pending, current, held_current, last_retry, policy_held?}
 * pending 将词 key 映射到再次出现时所需的首次新词回答总数；current 只存
 * {kind, key}，因此重启或词书换序后仍能找到未回答的词。
 *
 * 随机：本队列完全确定性，不使用 rng；时钟由调用方传入（now=0 是合法固定时钟）。
 */
import * as sch from './scheduler.js';
import { isDeepStrictEqual } from 'node:util';

const KINDS = new Set(['new', 'retry', 'review']);

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
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

/** Python int()：非法值抛异常（调用方决定回退）。 */
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

/** 与 entries._count 一致：非法/缺失计数按 0，不抛异常。 */
export function count(value, fallback = 0) {
  try {
    return Math.max(0, pyInt(value));
  } catch {
    return fallback;
  }
}

export const _count = count;

function validTarget(value) {
  // Unknown persisted values are not deadlines; never coerce them into ready 0.
  return Number.isSafeInteger(value) && value >= 0;
}

function hasAnswer(st) {
  return pyTruthy(st) && Boolean(count(st.seen) || count(st.lapse));
}

function membership(collection, key) {
  if (collection === null || collection === undefined) return false;
  if (collection instanceof Set) return collection.has(key);
  if (Array.isArray(collection)) return collection.includes(key);
  if (typeof collection === 'object') return Object.prototype.hasOwnProperty.call(collection, key);
  return false;
}

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

/**
 * 兼容调用方过去保存过完整 item 的 current：只取稳定 key。
 * @param {unknown} current
 * @returns {string|null}
 */
function currentKey(current) {
  if (!isPlainObject(current)) return null;
  let key = current.key;
  if (key === undefined || key === null) {
    if (isPlainObject(current.w)) key = current.w.w;
  }
  return key === undefined ? null : key;
}

function nowValue(now) {
  return now === null || now === undefined ? Date.now() / 1000 : now;
}

export class StudyQueue {
  /**
   * @param {Array<{w:string}>} words 已排好序的词条
   * @param {Record<string, object|null>} states 跨书共享状态（原地更新）
   * @param {Record<string, unknown>} record 当前词书队列记录（原地更新）
   * @param {{retryGap?:number, known?:Set<string>|null,
   *   excluded?:Set<string>|null}} [options]
   */
  constructor(words, states, record, options = {}) {
    if (!isPlainObject(states) || !isPlainObject(record)) {
      throw new TypeError('states and record must be shared dictionaries');
    }
    const opts = isPlainObject(options) ? options : {};
    let gap;
    try {
      gap = pyInt(opts.retryGap === undefined ? 4 : opts.retryGap);
    } catch {
      throw new TypeError('retry_gap must be an integer');
    }
    if (gap <= 0) throw new Error('retry_gap must be positive');
    this.words = Array.from(words);
    this.states = states;
    this.record = record;
    this.retryGap = gap;
    this.known = opts.known !== undefined && opts.known !== null ? opts.known : new Set();
    // 显式学校排除优先于所有队列路径；保留传入集合引用，暂停后恢复。
    this.excluded = opts.excluded !== undefined && opts.excluded !== null
      ? opts.excluded
      : new Set();
    // Python 只在调用方已提供 policy_held 时校验；缺失时不写入 record（保持记录形状）。
    if (hasOwn(record, 'policy_held')) {
      const policyHeld = record.policy_held;
      if (!Array.isArray(policyHeld) || policyHeld.some((item) => !isPlainObject(item))) {
        throw new TypeError('record.policy_held must be a list of saved items');
      }
    }
    this._indices = new Map();
    for (let idx = 0; idx < this.words.length; idx += 1) {
      const key = this.words[idx].w;
      if (!this._indices.has(key)) this._indices.set(key, idx);
    }

    this.cursor = hasOwn(record, 'cursor') ? record.cursor : 0;
    record.new_count = count(hasOwn(record, 'new_count') ? record.new_count : 0);
    if (!hasOwn(record, 'pending')) record.pending = {};
    if (!isPlainObject(record.pending)) {
      throw new TypeError('record.pending must be a dictionary');
    }
    if (!hasOwn(record, 'current')) record.current = null;
    if (!hasOwn(record, 'held_current')) record.held_current = null;
    if (!hasOwn(record, 'last_retry')) record.last_retry = null;
  }

  get cursor() {
    return this.record.cursor;
  }

  set cursor(value) {
    this.record.cursor = Math.min(this.words.length, count(value));
  }

  /** 读取 record.policy_held；缺失时返回空数组（不写入记录）。 */
  _policyHeld(readOnly = false) {
    if (!hasOwn(this.record, 'policy_held')) {
      if (readOnly) return [];
      this.record.policy_held = [];
    }
    const held = this.record.policy_held;
    if (!Array.isArray(held)) throw new TypeError('record.policy_held must be a list');
    return held;
  }

  _skipKnown(key, st) {
    // 预测是显式 opt-in，绝不覆盖 scheduler 记录。
    return membership(this.known, key) && !pyTruthy(st) && !hasOwn(this.record.pending, key);
  }

  _syncPending() {
    const pending = this.record.pending;
    for (const key of Object.keys(pending)) {
      if (membership(this.excluded, key)) continue; // 暂停不得擦除 retry 目标
      const st = this.states[key];
      if (pyTruthy(st) && !sch.isNew(st)) {
        // 同一词在其它词书中已认识/出库，旧 retry 就失效。
        delete pending[key];
      }
    }
    for (const key of this._indices.keys()) {
      if (membership(this.excluded, key)) continue;
      const st = this.states[key];
      if (sch.isNew(st) && hasAnswer(st)) {
        // 旧游标/换书/换序不得丢掉显式忘记而未认识的词；没有间隔记录时直接 ready。
        if (!hasOwn(pending, key)) pending[key] = this.record.new_count;
      }
    }
  }

  _item(key, kind) {
    const idx = this._indices.get(key);
    const st = this.states[key];
    return { kind, w: this.words[idx], st: st === undefined ? null : st, idx };
  }

  _select(key, kind, resume = false, saved = null) {
    // 被到期复习挂起的未答词可能先被 scheduler 找到；恢复其额外字段而不是覆盖。
    if (saved === null || saved === undefined) {
      const held = this.record.held_current;
      if (currentKey(held) === key) {
        saved = held;
        this.record.held_current = null;
      } else {
        const parked = this._policyHeld(true);
        for (const entry of parked) {
          if (currentKey(entry) === key) {
            saved = entry;
            parked.splice(parked.indexOf(entry), 1);
            break;
          }
        }
      }
    }
    // 恢复同 key 的合法 current/policy_held 时保留原字典的未知字段；
    // 规范内部字段才覆盖，不同 key 绝不串字段。
    const current = isPlainObject(saved) && currentKey(saved) === key ? { ...saved } : {};
    current.kind = kind;
    current.key = key;
    if (kind === 'new') {
      if (resume) current.resume = true;
      else delete current.resume;
    } else {
      delete current.resume;
    }
    this.record.current = current;
    return this._item(key, kind);
  }

  static _currentKey(current) {
    return currentKey(current);
  }

  _reuseCurrent(now) {
    const current = this.record.current;
    const key = currentKey(current);
    const kind = isPlainObject(current) ? current.kind : null;
    if (membership(this.excluded, key)) {
      this._parkPolicyCurrent();
      return null;
    }
    if (!this._indices.has(key) || !KINDS.has(kind)) {
      this.record.current = null;
      return null;
    }
    const st = this.states[key];
    if (kind === 'review') {
      if (sch.isLearning(st) && st.due !== null && st.due !== undefined && st.due <= now) {
        return this._select(key, kind, false, current);
      }
    } else if (sch.isNew(st) && !this._skipKnown(key, st)) {
      let effectiveKind = kind;
      if (kind === 'retry' || hasOwn(this.record.pending, key) || hasAnswer(st)) {
        if (!hasOwn(this.record.pending, key)) {
          this.record.pending[key] = this.record.new_count;
        }
        effectiveKind = 'retry';
        const target = this.record.pending[key];
        if (!validTarget(target) || target > this.record.new_count) {
          // Unknown deadlines and saved items cannot bypass the target.
          this._parkPolicyCurrent();
          return null;
        }
      }
      return this._select(
        key,
        effectiveKind,
        effectiveKind === 'new' ? Boolean(current.resume) : false,
        current,
      );
    }
    this.record.current = null;
    return null;
  }

  _pendingOrder() {
    // key 不在当前词书中时保留记录，但绝不加入本书队列。
    const entries = [];
    for (const key of Object.keys(this.record.pending)) {
      const target = this.record.pending[key];
      if (!this._indices.has(key) || membership(this.excluded, key)
          || !validTarget(target) || !sch.isNew(this.states[key])) {
        continue;
      }
      entries.push([target, this._indices.get(key), key]);
    }
    entries.sort((left, right) => {
      if (left[0] !== right[0]) return left[0] - right[0];
      if (left[1] !== right[1]) return left[1] - right[1];
      if (left[2] === right[2]) return 0;
      return left[2] < right[2] ? -1 : 1;
    });
    return entries;
  }

  _nextNew() {
    const n = this.words.length;
    const start = this.cursor;
    // 优先旧 cursor 之后的词；尾部耗尽后补扫前缀，换序也不丢未学词。
    for (const [from, to] of [[start, n], [0, start]]) {
      for (let idx = from; idx < to; idx += 1) {
        const w = this.words[idx];
        const key = w.w;
        const st = this.states[key];
        if (!membership(this.excluded, key) && sch.isNew(st)
            && !hasOwn(this.record.pending, key) && !this._skipKnown(key, st)) {
          return [key, idx];
        }
      }
    }
    return null;
  }

  /** 额外的保存列表，避免覆盖 existing held_current 槽位。 */
  _parkPolicyCurrent() {
    const current = this.record.current;
    if (isPlainObject(current)) {
      const held = this._policyHeld();
      const copy = { ...current };
      if (!held.some((entry) => isDeepStrictEqual(entry, copy))) held.push(copy);
    }
    this.record.current = null;
  }

  _holdCurrent() {
    // Suspending another item must not overwrite an earlier interruption.
    const current = this.record.current;
    if (!isPlainObject(current)) return;
    const held = this.record.held_current;
    if (isPlainObject(held) && !isDeepStrictEqual(held, current)) {
      const saved = this._policyHeld();
      if (!saved.some((entry) => isDeepStrictEqual(entry, held))) saved.push({ ...held });
    }
    this.record.held_current = { ...current };
    this.record.current = null;
  }

  _takePolicyHeld(now) {
    const held = this._policyHeld(true);
    for (const entry of [...held]) {
      const key = currentKey(entry);
      if (!this._indices.has(key) || membership(this.excluded, key)) {
        continue; // 保留外来与被暂停的保存项
      }
      this.record.current = { ...entry };
      const current = this._reuseCurrent(now);
      if (current !== null) {
        if (current.kind === 'new') this.record.current.resume = true;
        const idx = held.indexOf(entry);
        if (idx >= 0) held.splice(idx, 1);
        return current;
      }
    }
    this.record.current = null;
    return null;
  }

  _reviews(now) {
    return sch.reviewItems(this.words, this.states, now)
      .filter((item) => !membership(this.excluded, item.w.w));
  }

  /**
   * 取一题并保存 current；到期旧词优先，新词重试严格按计数间隔。
   * @param {number|null} [now]
   */
  next(now = null) {
    const time = nowValue(now);
    const held = this.record.held_current;
    if (isPlainObject(held) && membership(this.excluded, currentKey(held))) {
      // 释放唯一的复习中断槽位但保留其元数据。
      const saved = this._policyHeld();
      if (!saved.some((entry) => isDeepStrictEqual(entry, held))) saved.push({ ...held });
      this.record.held_current = null;
    }
    this._syncPending();
    let current = this._reuseCurrent(time);
    if (current !== null && current.kind === 'review') return current;

    const reviews = this._reviews(time);
    if (reviews.length) {
      if (current !== null) {
        // next/startup 会优先复习；不前移 cursor、不增加 new_count，
        // 挂起的 new/retry 在所有到期旧词答完后继续原题。
        this._holdCurrent();
      }
      return this._select(reviews[0].w.w, 'review');
    }

    if (current !== null && current.kind === 'retry') return current;
    // Ready retries also beat saved fresh items; suspend rather than lose them.
    const pending = this._pendingOrder();
    if (pending.length && pending[0][0] <= this.record.new_count) {
      if (current !== null) this._holdCurrent();
      return this._select(pending[0][2], 'retry');
    }
    if (current !== null) return current;
    const heldCurrent = this.record.held_current;
    this.record.held_current = null;
    if (heldCurrent !== null && heldCurrent !== undefined) {
      this.record.current = heldCurrent;
      current = this._reuseCurrent(time);
      if (current !== null) return current;
    }
    // A restored school-new item cannot delay an already eligible retry.
    current = this._takePolicyHeld(time);
    if (current !== null) return current;

    const candidate = this._nextNew();
    if (candidate !== null) {
      const [key, idx] = candidate;
      this.cursor = idx;
      return this._select(key, 'new');
    }

    this.cursor = this.words.length;
    return null;
  }

  /**
   * 回答 next 返回的当前词，写 states，清 current，返回新状态。
   * 拒绝已回答或其它题的 stale item，避免重复计数。
   * @param {{kind:string, w:{w:string}}} item
   * @param {boolean} remember
   * @param {number|null} [now]
   */
  answer(item, remember, now = null) {
    const time = nowValue(now);
    if (!isPlainObject(item) || !isPlainObject(item.w)) {
      throw new TypeError('answer 需要 next() 返回的 item');
    }
    const key = item.w.w;
    const kind = item.kind;
    const current = this.record.current;
    if (!this._indices.has(key) || membership(this.excluded, key) || !KINDS.has(kind)
        || currentKey(current) !== key || !isPlainObject(current) || current.kind !== kind) {
      throw new Error('answer must match the unanswered current item');
    }

    const resume = Boolean(isPlainObject(current) && current.resume);
    let before = this.states[key];
    const firstNew = kind === 'new' && sch.isNew(before) && !hasAnswer(before)
      && !hasOwn(this.record.pending, key);
    if (!pyTruthy(before)) before = sch.newState(time);
    const after = remember ? sch.onRemember(before, time) : sch.onForget(before, time);
    this.states[key] = after;

    if (firstNew) this.record.new_count += 1;
    if (sch.isNew(after)) {
      this.record.pending[key] = this.record.new_count + this.retryGap;
    } else {
      delete this.record.pending[key];
    }
    if (kind === 'new' && !resume) {
      this.cursor = this._indices.get(key) + 1;
    } else if (kind === 'retry') {
      this.record.last_retry = key;
    }
    if (hasOwn(this.record, 'policy_held')) {
      const held = this._policyHeld(true);
      const kept = held.filter((saved) => currentKey(saved) !== key);
      held.splice(0, held.length, ...kept);
    }
    this.record.current = null;
    return after;
  }

  /** 当前词书最近的未来旧词 due；没有则 null。now 仅供固定时钟测试。 */
  nextDueTime(now = null) {
    const time = nowValue(now);
    let best = null;
    for (const key of this._indices.keys()) {
      if (membership(this.excluded, key)) continue;
      const st = this.states[key];
      if (sch.isLearning(st) && st.due !== null && st.due !== undefined && st.due > time) {
        if (best === null || st.due < best) best = st.due;
      }
    }
    return best;
  }

  /**
   * 队列摘要（JS 侧新增；Python StudyQueue 无此方法，供 host 组装视图）。
   * @param {number|null} [now]
   * @returns {{cursor:number,total:number,due:number,unseen:number,learned:number,
   *   pending:number,newCount:number,currentKey:string|null,nextDue:number|null}}
   */
  stats(now = null) {
    const time = nowValue(now);
    let due = 0;
    let unseen = 0;
    let learned = 0;
    for (const key of this._indices.keys()) {
      if (membership(this.excluded, key)) continue;
      const st = this.states[key];
      if (sch.isNew(st)) {
        unseen += 1;
      } else {
        learned += 1;
        if (sch.isLearning(st) && st.due !== null && st.due !== undefined && st.due <= time) {
          due += 1;
        }
      }
    }
    let pending = 0;
    for (const key of Object.keys(this.record.pending)) {
      if (this._indices.has(key) && !membership(this.excluded, key)) pending += 1;
    }
    return {
      cursor: this.cursor,
      total: this.words.length,
      due,
      unseen,
      learned,
      pending,
      newCount: this.record.new_count,
      currentKey: currentKey(this.record.current),
      nextDue: this.nextDueTime(time),
    };
  }
}

// 兼容 Python 属性名别名。
StudyQueue.prototype.next_due_time = StudyQueue.prototype.nextDueTime;

export default { StudyQueue, count };
