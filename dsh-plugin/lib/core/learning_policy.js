/**
 * 学习安排与全局自然日新词账本（移植 app/learning_policy.py）。
 *
 * 只操作调用方共享的 settings / ledger 对象，不读写文件。一次首次实际作答
 * 即引入新词，认识/不认识都计入；展示、重试与复习不计。
 */

export const REVIEW_FIRST = 'review_first';
export const DAILY_NEW_FIRST = 'daily_new_first';
export const DEFAULTS = Object.freeze({ mode: REVIEW_FIRST, daily_new: 20 });
export const MAX_DAILY_NEW = 999;

const MODES = new Set([REVIEW_FIRST, DAILY_NEW_FIRST]);

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Python int() 语义的严格转换；失败抛异常。
 * 只实现 settings/ledger 实际需要的分支。
 */
function pythonInt(value) {
  if (typeof value === 'boolean') throw new TypeError('boolean is not a word limit');
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new RangeError('cannot convert to integer');
    return Math.trunc(value);
  }
  if (typeof value === 'string') {
    const text = value.trim();
    const match = /^([+-]?)(\d+)$/.exec(text);
    if (!match) throw new TypeError('invalid literal for int()');
    // Python: int("020") === 20，随后由调用方按字符串相等性判断是否规范。
    return Number(`${match[1]}${match[2]}`);
  }
  throw new TypeError('int() argument must be a number or string');
}

/**
 * 安全读取每日上限：非法值回退 DEFAULTS.daily_new。
 * @param {unknown} value
 * @returns {number}
 */
function normalizeDailyNew(value) {
  try {
    if (typeof value === 'boolean') throw new TypeError('boolean is not a word limit');
    const number = pythonInt(value);
    // 对应 Python: `if number != value and not (isinstance(value, str) and str(number) == value.strip())`
    const sameAsNumber = !(typeof value === 'string') && number === value;
    const sameAsCanonicalString = typeof value === 'string' && String(number) === value.trim();
    if (!sameAsNumber && !sameAsCanonicalString) {
      throw new TypeError('not an integer');
    }
    if (!(number >= 0 && number <= MAX_DAILY_NEW)) {
      throw new RangeError('out of range');
    }
    return number;
  } catch {
    return DEFAULTS.daily_new;
  }
}

/**
 * 规范化设置副本；未知字段保留，非法 mode/daily_new 回退默认。
 * @param {Record<string, unknown>|null|undefined} raw
 * @returns {Record<string, unknown>}
 */
export function normalizeSettings(raw = null) {
  const out = isPlainObject(raw) ? { ...raw } : {};
  if (!MODES.has(out.mode)) out.mode = REVIEW_FIRST;
  out.daily_new = normalizeDailyNew(
    out.daily_new === undefined ? DEFAULTS.daily_new : out.daily_new,
  );
  return out;
}

function isIsoDateKey(day) {
  if (typeof day !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const date = Number(match[3]);
  if (year < 1 || year > 9999) return false;
  if (month < 1 || month > 12) return false;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (date < 1 || date > days[month - 1]) return false;
  // Python date.fromisoformat(day).isoformat() == day：年份必须四位。
  return true;
}

/**
 * 校验日账本结构；不合法抛 Error（对应 Python ValueError）。
 * @param {unknown} ledger
 * @returns {true}
 */
export function validateLedger(ledger) {
  if (!isPlainObject(ledger)) {
    throw new Error('daily_new_ledger must be a dictionary');
  }
  const days = ledger.days === undefined ? {} : ledger.days;
  if (!isPlainObject(days)) {
    throw new Error('daily_new_ledger.days must be a dictionary');
  }
  for (const day of Object.keys(days)) {
    if (!isIsoDateKey(day)) {
      throw new Error('daily_new_ledger contains an invalid local date');
    }
    const words = days[day];
    if (!Array.isArray(words)
        || words.some((word) => typeof word !== 'string' || !word.trim())) {
      throw new Error('daily_new_ledger words must be stable nonempty string keys');
    }
  }
  return true;
}

function timestamp(now) {
  return now === null || now === undefined ? Date.now() / 1000 : Number(now);
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function localDate(now) {
  const date = new Date(timestamp(now) * 1000);
  if (Number.isNaN(date.getTime())) throw new RangeError('invalid timestamp');
  return {
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate(),
    date,
  };
}

/** 本地自然日 YYYY-MM-DD。 */
export function localDay(now = null) {
  const { year, month, day } = localDate(now);
  return `${String(year).padStart(4, '0')}-${pad2(month)}-${pad2(day)}`;
}

export class LearningPolicy {
  /**
   * @param {Record<string, unknown>} settings
   * @param {{schema?:number, days?:Record<string, string[]>}} ledger
   */
  constructor(settings, ledger) {
    if (!isPlainObject(settings)) {
      throw new TypeError('settings must be a dictionary');
    }
    validateLedger(ledger);
    this.settings = settings;
    this.ledger = ledger;
    // 缺失容器会创建，但已有日期/未知字段绝不擦除。
    if (!('schema' in ledger)) ledger.schema = 1;
    if (!('days' in ledger)) ledger.days = {};
  }

  get dailyNewFirst() {
    return this.settings.mode === DAILY_NEW_FIRST;
  }

  /** Python 属性名别名。 */
  get daily_new_first() {
    return this.dailyNewFirst;
  }

  get limit() {
    return normalizeSettings(this.settings).daily_new;
  }

  learnedToday(now = null) {
    const words = this.ledger.days[localDay(now)];
    return new Set(words || []).size;
  }

  /** Python 属性名别名。 */
  learned_today(now = null) {
    return this.learnedToday(now);
  }

  remaining(now = null) {
    return Math.max(0, this.limit - this.learnedToday(now));
  }

  allowsNew(now = null) {
    void now;
    return true;
  }

  allows_new(now = null) {
    return this.allowsNew(now);
  }

  shouldReviewBeforeNew(now = null) {
    return this.dailyNewFirst && this.remaining(now) <= 0;
  }

  should_review_before_new(now = null) {
    return this.shouldReviewBeforeNew(now);
  }

  introduceNew(key, now = null) {
    if (typeof key !== 'string' || !key.trim()) {
      throw new Error('A stable nonempty word key is required');
    }
    const day = localDay(now);
    if (!(day in this.ledger.days)) this.ledger.days[day] = [];
    const words = this.ledger.days[day];
    if (!Array.isArray(words)) {
      throw new Error('daily_new_ledger words must be stable nonempty string keys');
    }
    if (words.includes(key)) return false;
    words.push(key);
    return true;
  }

  introduce_new(key, now = null) {
    return this.introduceNew(key, now);
  }

  nextDayTime(now = null) {
    const { year, month, day } = localDate(now);
    // 构造次日本地午夜，而不是 now+24h；自然日跨 DST 也成立。
    const midnight = new Date(year, month - 1, day + 1, 0, 0, 0, 0);
    return midnight.getTime() / 1000;
  }

  next_day_time(now = null) {
    return this.nextDayTime(now);
  }
}

export default {
  REVIEW_FIRST,
  DAILY_NEW_FIRST,
  DEFAULTS,
  MAX_DAILY_NEW,
  normalizeSettings,
  validateLedger,
  localDay,
  LearningPolicy,
};
