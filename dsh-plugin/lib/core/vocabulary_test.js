/**
 * DSH 版词汇量测评（frequency-entry CAT）。
 *
 * 本文件是 `app/vocabulary_test.py`（V1.4.2，859 行）的逐条移植：常量、内容策略
 * 正则、干扰项池构建（贪心 + 精确回退）、band 期望信息量、EAP 后验、停止规则、
 * survey/adaptive 顺序、`summarize` 全部字段、`validateSession` 全部结构校验都与
 * Python 一一对应。唯一被有意替换的是随机源：由 CPython `random.Random(int)` 改为
 * 本仓库 `lib/core/rng.js` 的 SHA-256 计数器 DRBG（CONTRACT §6）；PRNG 不同不改变
 * 任何测量量，只改变“同一条记录序列下选中哪个词/选项顺序”。
 *
 * 数值移植约定：
 * - `_range_curves`/`_total_population`/`_dot`/`_theta_stats` 里的 `math.fsum`
 *   语义用 `lib/core/exactsum.js` 的 `exactSum`（BigInt 精确累加 + 一次正确舍入）。
 * - Python `str.strip` / `str.casefold` / `unicodedata.normalize("NFKC")` /
 *   `re.fullmatch` 与 JS 默认行为不同处均有显式辅助函数（pyStrip/pyCasefold/fullmatch）。
 * - 区间使用 Python 常量 1.959963984540054 的等价形式（95% 等尾分位）。
 *
 * 随机材料（与 CONTRACT §6 一致）：
 *   makeRng(`${ALGORITHM}|${bank.fingerprint}|${state.seed}|${records.length}`)
 *
 * @module lib/core/vocabulary_test
 */
import { createHash } from 'node:crypto';
import { makeRng } from './rng.js';
import { fingerprintOf } from './canonical.js';
import { exactSum } from './exactsum.js';

// ---------------------------------------------------------------------------
// 常量（数值、顺序与 app/vocabulary_test.py 顶部一致）
// ---------------------------------------------------------------------------
export const ALGORITHM = 'vst-cat-v143-web';
export const SESSION_SCHEMA = 2;
export const MEASUREMENT_SCHEMA = 3;
export const BAND_SIZE = 1000;
export const MAX_WORDS = 20000;
export const MIN_ITEMS = 40;
export const MAX_ITEMS = 80;
export const MIN_PER_BAND = 2;
export const TARGET_SE = 0.30;
export const A = 1.4;
export const C = 0.25;
export const PRIOR_MEAN = 0.0;
export const PRIOR_SD = 2.0;
export const THETA_MIN = -5.0;
export const THETA_MAX = 7.0;
export const THETA_STEP = 0.05;
export const INTERVAL_LEVEL = 0.95;
export const UNIT = 'frequency_ranked_entries';
/** Python: tuple(index / 20.0 for index in range(-100, 141))，-5.00 .. 7.00 step 0.05。 */
export const THETA_GRID = Object.freeze(Array.from({ length: 241 }, (_, index) => (index - 100) / 20.0));

// 改动内容/选题规则必须让旧会话失效（与 Python 同值）。
const CONTENT_POLICY = 'single-entries-zh-lexical-conflict-v2';
const DISTRACTOR_POOL = 6;
// 显式缩写键：绝不从“短”推断缩写（am/as/in/no/us、fig、mar、ad 等仍是普通词）。
const ABBREVIATION_KEYS = new Set([
  'etc', 'mr', 'mrs', 'ms', 'dr', 'vs', 'ltd', 'inc', 'jr', 'sr', 'pm',
  'eg', 'ie', 'aka', 'asap', 'st',
]);
const SLOTS = 'ABCD';
const ENGLISH_STOP = new Set(['a', 'an', 'the', 'of', 'to', 'and', 'or', 'in']);

// 规范序列化/指纹与精确求和统一走 core-port 提供的公共模块（CONTRACT §6）：
//   canonical.js  -> identity 的规范 JSON 与 SHA-256 指纹
//   exactsum.js   -> math.fsum 语义的精确求和（不是普通 += 累加）
// 本文件只保留读 double 位模式的小工具（pyRound 的十进制舍入用）。
// ---------------------------------------------------------------------------

const _BITS_VIEW = new DataView(new ArrayBuffer(8));

// ---------------------------------------------------------------------------
// Python 语义辅助：strip / casefold / fullmatch / 比较
// ---------------------------------------------------------------------------

// Python str.isspace() 覆盖的字符集（JS trim 的集合略有不同，逐字符显式判断）。
const PY_WHITESPACE = new Set([
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f,
  0x20, 0x85, 0xa0, 0x1680,
  0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007,
  0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
]);

/** Python `str.strip()`（无参数）。 */
export function pyStrip(text) {
  let start = 0;
  let end = text.length;
  while (start < end && PY_WHITESPACE.has(text.charCodeAt(start))) start += 1;
  while (end > start && PY_WHITESPACE.has(text.charCodeAt(end - 1))) end -= 1;
  return text.slice(start, end);
}

/** Python `str.strip(chars)` 的指定字符版本。 */
function stripChars(text, chars) {
  let start = 0;
  let end = text.length;
  while (start < end && chars.has(text[start])) start += 1;
  while (end > start && chars.has(text[end - 1])) end -= 1;
  return text.slice(start, end);
}

// Python 3.8（Unicode 12.1）`str.casefold()` 与 JS `toLowerCase()` 的差异表。
// 生成方法：对每个 NFKC 稳定的码位比较 Python casefold 与 lower，共 103 条
// （Cherokee 由下面的规则式处理）。覆盖 ß/ẞ→ss、ς/ϲ→σ、希腊多调符展开、
// Cyrillic 变体、数学字母等。
const CASEFOLD_EXTRA = new Map([
  [0xdf, 'ss'], [0x1f0, 'j\u030c'], [0x345, '\u03b9'], [0x390, '\u03b9\u0308\u0301'],
  [0x3b0, '\u03c5\u0308\u0301'], [0x3c2, '\u03c3'], [0x13f8, '\u13f0'], [0x13f9, '\u13f1'],
  [0x13fa, '\u13f2'], [0x13fb, '\u13f3'], [0x13fc, '\u13f4'], [0x13fd, '\u13f5'],
  [0x1c80, '\u0432'], [0x1c81, '\u0434'], [0x1c82, '\u043e'], [0x1c83, '\u0441'],
  [0x1c84, '\u0442'], [0x1c85, '\u0442'], [0x1c86, '\u044a'], [0x1c87, '\u0463'],
  [0x1c88, '\ua64b'], [0x1e96, 'h\u0331'], [0x1e97, 't\u0308'], [0x1e98, 'w\u030a'],
  [0x1e99, 'y\u030a'], [0x1e9e, 'ss'], [0x1f50, '\u03c5\u0313'], [0x1f52, '\u03c5\u0313\u0300'],
  [0x1f54, '\u03c5\u0313\u0301'], [0x1f56, '\u03c5\u0313\u0342'], [0x1f80, '\u1f00\u03b9'],
  [0x1f81, '\u1f01\u03b9'], [0x1f82, '\u1f02\u03b9'], [0x1f83, '\u1f03\u03b9'],
  [0x1f84, '\u1f04\u03b9'], [0x1f85, '\u1f05\u03b9'], [0x1f86, '\u1f06\u03b9'],
  [0x1f87, '\u1f07\u03b9'], [0x1f88, '\u1f00\u03b9'], [0x1f89, '\u1f01\u03b9'],
  [0x1f8a, '\u1f02\u03b9'], [0x1f8b, '\u1f03\u03b9'], [0x1f8c, '\u1f04\u03b9'],
  [0x1f8d, '\u1f05\u03b9'], [0x1f8e, '\u1f06\u03b9'], [0x1f8f, '\u1f07\u03b9'],
  [0x1f90, '\u1f20\u03b9'], [0x1f91, '\u1f21\u03b9'], [0x1f92, '\u1f22\u03b9'],
  [0x1f93, '\u1f23\u03b9'], [0x1f94, '\u1f24\u03b9'], [0x1f95, '\u1f25\u03b9'],
  [0x1f96, '\u1f26\u03b9'], [0x1f97, '\u1f27\u03b9'], [0x1f98, '\u1f20\u03b9'],
  [0x1f99, '\u1f21\u03b9'], [0x1f9a, '\u1f22\u03b9'], [0x1f9b, '\u1f23\u03b9'],
  [0x1f9c, '\u1f24\u03b9'], [0x1f9d, '\u1f25\u03b9'], [0x1f9e, '\u1f26\u03b9'],
  [0x1f9f, '\u1f27\u03b9'], [0x1fa0, '\u1f60\u03b9'], [0x1fa1, '\u1f61\u03b9'],
  [0x1fa2, '\u1f62\u03b9'], [0x1fa3, '\u1f63\u03b9'], [0x1fa4, '\u1f64\u03b9'],
  [0x1fa5, '\u1f65\u03b9'], [0x1fa6, '\u1f66\u03b9'], [0x1fa7, '\u1f67\u03b9'],
  [0x1fa8, '\u1f60\u03b9'], [0x1fa9, '\u1f61\u03b9'], [0x1faa, '\u1f62\u03b9'],
  [0x1fab, '\u1f63\u03b9'], [0x1fac, '\u1f64\u03b9'], [0x1fad, '\u1f65\u03b9'],
  [0x1fae, '\u1f66\u03b9'], [0x1faf, '\u1f67\u03b9'], [0x1fb2, '\u1f70\u03b9'],
  [0x1fb3, '\u03b1\u03b9'], [0x1fb4, '\u03ac\u03b9'], [0x1fb6, '\u03b1\u0342'],
  [0x1fb7, '\u03b1\u0342\u03b9'], [0x1fbc, '\u03b1\u03b9'], [0x1fc2, '\u1f74\u03b9'],
  [0x1fc3, '\u03b7\u03b9'], [0x1fc4, '\u03ae\u03b9'], [0x1fc6, '\u03b7\u0342'],
  [0x1fc7, '\u03b7\u0342\u03b9'], [0x1fcc, '\u03b7\u03b9'], [0x1fd2, '\u03b9\u0308\u0300'],
  [0x1fd6, '\u03b9\u0342'], [0x1fd7, '\u03b9\u0308\u0342'], [0x1fe2, '\u03c5\u0308\u0300'],
  [0x1fe4, '\u03c1\u0313'], [0x1fe6, '\u03c5\u0342'], [0x1fe7, '\u03c5\u0308\u0342'],
  [0x1ff2, '\u1f7c\u03b9'], [0x1ff3, '\u03c9\u03b9'], [0x1ff4, '\u03ce\u03b9'],
  [0x1ff6, '\u03c9\u0342'], [0x1ff7, '\u03c9\u0342\u03b9'], [0x1ffc, '\u03c9\u03b9'],
]);

/** Python `unicodedata.normalize("NFKC", text).casefold()`。 */
export function pyCasefold(text) {
  const normalized = text.normalize('NFKC');
  let out = '';
  for (const char of normalized) {
    const cp = char.codePointAt(0);
    // Cherokee 的 casefold 目标是大写音节（Unicode 稳定性策略），与 JS lower 相反。
    if (cp >= 0x13a0 && cp <= 0x13f5) { out += char; continue; }
    if (cp >= 0xab70 && cp <= 0xabbf) { out += String.fromCodePoint(cp - 0xa9d0); continue; }
    const mapped = CASEFOLD_EXTRA.get(cp);
    out += mapped === undefined ? char.toLowerCase() : mapped;
  }
  return out;
}

/** Python `re.fullmatch(pattern, text)` 的判定（match 必须覆盖整个字符串）。 */
function fullmatch(regex, text) {
  const match = regex.exec(text);
  return match !== null && match[0] === text;
}

/** Python 字符串比较按 Unicode 码点；JS `<` 按 UTF-16 码元（astral 区不同）。 */
function compareCodePoints(left, right) {
  const leftIterator = left[Symbol.iterator]();
  const rightIterator = right[Symbol.iterator]();
  for (;;) {
    const a = leftIterator.next();
    const b = rightIterator.next();
    if (a.done || b.done) {
      if (a.done && b.done) return 0;
      return a.done ? -1 : 1;
    }
    const ac = a.value.codePointAt(0);
    const bc = b.value.codePointAt(0);
    if (ac !== bc) return ac < bc ? -1 : 1;
  }
}

/** Python tuple 比较：逐元素，短序列在等前缀时更小。 */
function compareStringArrays(left, right) {
  const length = Math.min(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const order = compareCodePoints(left[index], right[index]);
    if (order !== 0) return order;
  }
  if (left.length === right.length) return 0;
  return left.length < right.length ? -1 : 1;
}

/** Python `round(value)`（银行家舍入）。插件只用整数舍入；ndigits≠0 为近似实现。 */
export function pyRound(value, ndigits = 0) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TypeError('pyRound 需要有限数字');
  }
  if (ndigits === 0) {
    const floor = Math.floor(value);
    const difference = value - floor;
    if (difference > 0.5) return floor + 1;
    if (difference < 0.5) return floor;
    return floor % 2 === 0 ? floor : floor + 1;
  }
  if (!Number.isInteger(ndigits)) throw new TypeError('pyRound ndigits 需要整数');
  // 非整数位：先精确放大到整数再四舍六入五成双（q 可能超出 2^53，双舍入概率极低）。
  const negative = value < 0;
  const magnitude = Math.abs(value);
  _BITS_VIEW.setFloat64(0, magnitude);
  const bits = _BITS_VIEW.getBigUint64(0);
  const exponentBits = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & 0xfffffffffffffn;
  let mantissa;
  let exponent;
  if (exponentBits === 0) {
    mantissa = fraction;
    exponent = -1074;
  } else {
    mantissa = fraction | (1n << 52n);
    exponent = exponentBits - 1075;
  }
  const scale = 10n ** BigInt(ndigits);
  let scaled = mantissa * scale;
  let rounded;
  if (exponent >= 0) {
    rounded = scaled << BigInt(exponent);
  } else {
    const divisor = 1n << BigInt(-exponent);
    rounded = scaled / divisor;
    const remainder = scaled % divisor;
    const twice = remainder * 2n;
    if (twice > divisor || (twice === divisor && rounded % 2n === 1n)) rounded += 1n;
  }
  const result = Number(rounded) / 10 ** ndigits;
  return negative ? -result : result;
}

// ---------------------------------------------------------------------------
// 内容策略正则（与 Python 逐条对应；`u` 标志 + 显式 Unicode 语义）
// ---------------------------------------------------------------------------

/** Python `_WORD = re.compile(r"[a-z]+(?:[-'][a-z]+)*\Z", re.ASCII)`。 */
const WORD_RE = /[a-z]+(?:[-'][a-z]+)*/u;
/** `_CJK`（仅 search）。 */
const CJK_RE = /[\u3400-\u4dbf\u4e00-\u9fff]/u;
/** `_CJK_RUN`（findall，故用 g）。 */
const CJK_RUN_RE = /[\u3400-\u4dbf\u4e00-\u9fff]+/gu;
/**
 * `_POS`（re.I，sub 时全局）：注意 Python 顺序 n|v|vt|vi|adj|a|adv|ad|...
 * 与 JS 交替顺序一致。
 */
const POS_RE = /(?<![a-z])(?:n|v|vt|vi|adj|a|adv|ad|prep|conj|pron|det|art|num|aux|int|interj|abbr|un|na)\./giu;
/** `_NON_MEANING`。 */
const NON_MEANING_RE = /(?:暂无(?:释义|解释|翻译)?|释义缺失|未收录|无释义|未知释义|待补充|翻译错误|乱码|见词条|参见词条|同上|以上皆非|以上都不|以上全部|均不正确)/u;
/**
 * `_META_ENTITY`（re.I）。Python 的 `\b` 是 Unicode 词边界（CJK 也算 \w），
 * 这里用 `(?<![\p{L}\p{N}_])` / `(?![\p{L}\p{N}_])` 等价替换，避免 JS ASCII `\b` 误判。
 */
const META_ENTITY_RE = new RegExp(
  '(?:(?<![\\p{L}\\p{N}_])(?:abbr|abbrev|acronym|propn|proper\\s+noun)(?![\\p{L}\\p{N}_])'
  + '|[\\[（(【]\\s*(?:人名|地名|姓氏|男子名|女子名|男名|女名|国名|城市名|省名|缩写|略语)'
  + '|(?:^|[；;\\n])\\s*(?:(?:n|un|na)\\.\\s*)?(?:人名|地名|姓氏|男子名|女子名)(?:\\s*$|[，,；;：:（(])'
  + '|(?:的|之)(?:缩写|缩略形式|简称))',
  'iu',
);
/** `_INFLECTION_FORM`。 */
const INFLECTION_FORM = '(?:复数|过去式|过去分词|现在分词|第三人称单数|比较级|最高级|单数(?:第一|第二|第三)人称|(?:第一|第二)人称单数)';
/** `_INFLECTION_ONLY`（无 re.I；与 Python 同串拼接）。 */
const INFLECTION_ONLY_RE = new RegExp(
  "^[\"'“‘]?[a-z]+(?:[-'][a-z]+)*[\"'”’]?\\s*的\\s*" + INFLECTION_FORM
  + '(?:\\s*(?:和|及|与|或|、|[，,])\\s*' + INFLECTION_FORM + ')*'
  + '(?:形式)?[。.!！]?$',
  'u',
);
/** `_PLACE_GLOSS`（match 即从串首）。 */
const PLACE_GLOSS_RE = /^(?:中国|美国|英国|法国|德国|日本|加拿大|澳大利亚|印度|俄罗斯|意大利|西班牙|葡萄牙|巴西|墨西哥|埃及|希腊|瑞典|瑞士|挪威|芬兰|丹麦|荷兰|比利时|奥地利|波兰|乌克兰|新西兰|南非|韩国|朝鲜|越南|泰国|新加坡|马来西亚|印度尼西亚|菲律宾|土耳其|伊朗|伊拉克|爱尔兰|伦敦|巴黎|东京|北京|上海|纽约|华盛顿|罗马|柏林|悉尼|莫斯科|亚洲|欧洲|非洲|美洲|大洋洲|南极洲)(?=$|[；;，,（(])/u;
/** `re.match(r"\s*(?:=|参见|见\s*[a-z])", body, re.I)`。 */
const SENSE_START_RE = /^\s*(?:=|参见|见\s*[a-z])/iu;
/** `re.match(r"\s*([a-z]+)(?:\.|\b)", source, re.I)`。 */
const PRIMARY_POS_RE = /^\s*([a-z]+)(?:\.|(?![\p{L}\p{N}_]))/iu;
/** `re.findall(r"[a-z0-9\u3400-\u4dbf\u4e00-\u9fff]", primary)` 的字符类。 */
const PROFILE_CHAR_RE = /[a-z0-9\u3400-\u4dbf\u4e00-\u9fff]/gu;
/** `re.findall(r"[a-z]{3,}", combined)`。 */
const ENGLISH_WORD_RE = /[a-z]{3,}/gu;

const LOG_ONE_MINUS_C = Math.log1p(-C);
const PRIOR_LOG = Object.freeze(THETA_GRID.map((theta) => -0.5 * ((theta - PRIOR_MEAN) / PRIOR_SD) ** 2));
const THETA_EXP = Object.freeze(THETA_GRID.map((theta) => Math.exp(A * theta)));

// ---------------------------------------------------------------------------
// 基础数学
// ---------------------------------------------------------------------------

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function requireNumber(value, name) {
  if (!finiteNumber(value)) throw new Error(`${name} must be a finite number, not bool`);
  return value;
}

/** `_sigmoid`：正负分支分别避免 exp 溢出。 */
function sigmoid(value) {
  if (value >= 0.0) return 1.0 / (1.0 + Math.exp(-value));
  const exponential = Math.exp(value);
  return exponential / (1.0 + exponential);
}

/** 固定本地排名启发式；绝不读取来源 b/lvl。 */
export function difficulty(rank) {
  if (!Number.isInteger(rank) || rank < 1 || rank > MAX_WORDS) {
    throw new Error('rank must be an integer between 1 and MAX_WORDS');
  }
  return Math.log((rank + 100) / 1000.0);
}

/** 识别概率（无猜测成分）。 */
export function pKnown(theta, b) {
  const t = requireNumber(theta, 'theta');
  const difficultyValue = requireNumber(b, 'b');
  return sigmoid(A * (t - difficultyValue));
}

/** 固定 3PL 作答概率：.25 + .75 * sigmoid(1.4*(theta-b))。 */
export function pCorrect(theta, b) {
  return C + (1.0 - C) * pKnown(theta, b);
}

/** 3PL Fisher 信息量；在饱和概率下也稳定。 */
export function fisherInformation(theta, b) {
  const known = pKnown(theta, b);
  return (A * A * (1.0 - C) * known * known * (1.0 - known)
    / (C + (1.0 - C) * known));
}

// ---------------------------------------------------------------------------
// 内容策略
// ---------------------------------------------------------------------------

function posValues(value) {
  let values;
  if (typeof value === 'string') values = [value];
  else if (Array.isArray(value)) values = value;
  else if (value === null || value === undefined) values = [];
  else return null;
  if (values.some((part) => typeof part !== 'string')) return null;
  return values.map((part) => pyStrip(part)).filter((part) => part.length > 0);
}

function primaryPos(values, sense) {
  const source = values.length > 0 ? values[0] : sense;
  const match = PRIMARY_POS_RE.exec(source);
  const value = match ? match[1].toLowerCase() : 'other';
  return ({ vt: 'v', vi: 'v', a: 'adj', ad: 'adv', interj: 'int' })[value] ?? value;
}

/** `_sense_body`：NFKC + casefold + 去掉词性标记。 */
function senseBody(text) {
  return pyCasefold(text).replace(POS_RE, '');
}

function isDisjoint(left, right) {
  const [small, large] = left.size <= right.size ? [left, right] : [right, left];
  for (const value of small) if (large.has(value)) return false;
  return true;
}

function anyCharIn(chars, text) {
  for (const char of chars) if (text.includes(char)) return true;
  return false;
}

/**
 * 保守语义档案（可哈希），绝不虚构/翻译释义。两字中文重叠覆盖 使害怕/感到害怕
 * 之类碎片；单字整释义也受保护。raw 只作为歧义证据，绝不作为答案文本。
 * @returns {{canonical:string, grams:Set<string>, singles:Set<string>, english:Set<string>, runs:string, id:string}}
 */
function semanticProfile(sense, raw = '') {
  const primary = senseBody(sense);
  const combined = `${primary};${senseBody(raw.split('\\n').join(';'))}`;
  const canonical = (primary.match(PROFILE_CHAR_RE) || []).join('');
  const grams = new Set();
  const singles = new Set();
  const runs = combined.match(CJK_RUN_RE) || [];
  for (const run of runs) {
    const characters = [...run];
    if (characters.length === 1) {
      singles.add(run);
    } else {
      for (let index = 0; index < characters.length - 1; index += 1) {
        grams.add(characters[index] + characters[index + 1]);
      }
    }
  }
  const english = new Set((combined.match(ENGLISH_WORD_RE) || []).filter((word) => !ENGLISH_STOP.has(word)));
  const id = JSON.stringify([
    canonical,
    [...grams].sort(),
    [...singles].sort(),
    [...english].sort(),
    runs.join(''),
  ]);
  return { canonical, grams, singles, english, runs: runs.join(''), id };
}

/** 拒绝整条形态指向，而不是“释义里提到某个变形”的普通义项。 */
function onlyInflections(body) {
  if (!body.includes('的')) return false;
  const stripSet = new Set([' ', '\t', '\r', '\n', '(', ')', '[', ']', '【', '】']);
  const parts = body.replace(/\\n/g, '\n').split(/[;；\n]+/)
    .map((part) => stripChars(part, stripSet))
    .filter((part) => part.length > 0);
  return parts.length > 0 && parts.every((part) => fullmatch(INFLECTION_ONLY_RE, part));
}

/** `_profiles_conflict`：逐条照抄（含单字规则的方向性）。 */
function profilesConflict(left, right) {
  if (left.canonical.includes(right.canonical) || right.canonical.includes(left.canonical)) return true;
  if (!isDisjoint(left.grams, right.grams) || !isDisjoint(left.english, right.english)) return true;
  if (left.singles.size > 0 && anyCharIn(left.singles, right.runs)) return true;
  return right.singles.size > 0 && anyCharIn(right.singles, left.runs);
}

/**
 * `_prepare_entry`：只读取这些字段，绝不读来源 b/lvl 或学校成员关系；不修改调用方数据。
 * @returns {object|null}
 */
function prepareEntry(row) {
  if (row === null || typeof row !== 'object' || Array.isArray(row)) return null;
  const word = row.w;
  const frq = row.frq;
  const sense = row.s;
  let raw = row.raw === undefined ? '' : row.raw;
  const pos = posValues(row.pos);
  let caption = row.display_w === undefined ? word : row.display_w;
  if (typeof word !== 'string' || word !== pyStrip(word)
    || !finiteNumber(frq) || frq <= 0
    || typeof sense !== 'string' || pos === null) {
    return null;
  }
  const key = pyCasefold(word);
  if (!fullmatch(WORD_RE, key) || ABBREVIATION_KEYS.has(key) || row.type === 'phrase') {
    return null;
  }
  // 只保留代词 I，不保留任意大写专名或缩写。
  if (word !== key && !(word === 'I' && primaryPos(pos, sense) === 'pron')) {
    return null;
  }
  if (typeof caption !== 'string' || caption.trim().length === 0) caption = word;
  caption = pyStrip(caption);
  if (caption !== pyCasefold(caption) && !(caption === 'I' && key === 'i')) {
    return null;
  }
  const trimmedSense = pyStrip(sense);
  raw = typeof raw === 'string' ? pyStrip(raw) : '';
  const body = pyStrip(senseBody(trimmedSense));
  if (!CJK_RE.test(body)
    || trimmedSense.includes('\ufffd')
    || [...trimmedSense].some((char) => char.codePointAt(0) < 32 && !'\n\t\r'.includes(char))
    || NON_MEANING_RE.test(body)
    || onlyInflections(body)
    || SENSE_START_RE.test(body)
    || META_ENTITY_RE.test(`${pos.join(';')};${trimmedSense};${raw}`.replace(/\\n/g, ';'))
    || PLACE_GLOSS_RE.test(body)) {
    return null;
  }
  const frequency = frq;
  return {
    key,
    word: caption,
    sense: trimmedSense,
    pos: pos.slice(),
    source_frq: frequency,
    source_raw: raw,
  };
}

/** 共享选择框架：词频序、每键唯一、容量上限。 */
function selectEntries(words) {
  if (typeof words === 'string' || words instanceof Uint8Array) {
    throw new Error('words must be an iterable of entry dictionaries');
  }
  if (words === null || words === undefined || typeof words[Symbol.iterator] !== 'function') {
    throw new Error('words must be iterable');
  }
  const prepared = [];
  let inputCount = 0;
  for (const row of words) {
    inputCount += 1;
    const entry = prepareEntry(row);
    if (entry !== null) prepared.push(entry);
  }
  // 末尾的 tie-breaker 让重复词目消解与来源迭代顺序无关，同时不改变主 (frq, w) 次序。
  prepared.sort(comparePreparedEntries);
  const selected = [];
  const seen = new Set();
  for (const item of prepared) {
    if (!seen.has(item.key)) {
      seen.add(item.key);
      selected.push(item);
      if (selected.length === MAX_WORDS) break;
    }
  }
  return { selected, inputCount };
}

function comparePreparedEntries(left, right) {
  if (left.source_frq !== right.source_frq) return left.source_frq < right.source_frq ? -1 : 1;
  let order = compareCodePoints(left.key, right.key);
  if (order !== 0) return order;
  order = compareCodePoints(left.sense, right.sense);
  if (order !== 0) return order;
  order = compareStringArrays(left.pos, right.pos);
  if (order !== 0) return order;
  order = compareCodePoints(left.source_raw, right.source_raw);
  if (order !== 0) return order;
  return compareCodePoints(left.word, right.word);
}

// ---------------------------------------------------------------------------
// 缓存曲线（Python lru_cache 的等价物；结果只依赖 rank/区间）
// ---------------------------------------------------------------------------

const rankScaleCache = new Map();
const itemCurvesCache = new Map();
const rangeCurvesCache = new Map();

function rankScale(rank) {
  let scale = rankScaleCache.get(rank);
  if (scale === undefined) {
    scale = Math.exp(A * difficulty(rank));
    rankScaleCache.set(rank, scale);
  }
  return scale;
}

/** 对数似然与 Fisher 信息（不出现不稳定的 log(1-p)）。 */
function itemCurves(rank) {
  let curves = itemCurvesCache.get(rank);
  if (curves !== undefined) return curves;
  const scale = rankScale(rank);
  const logScale = Math.log(scale);
  const correct = new Array(THETA_GRID.length);
  const failure = new Array(THETA_GRID.length);
  const information = new Array(THETA_GRID.length);
  for (let index = 0; index < THETA_GRID.length; index += 1) {
    const exponential = THETA_EXP[index];
    const denominator = exponential + scale;
    const known = exponential / denominator;
    correct[index] = Math.log((exponential + C * scale) / denominator);
    failure[index] = LOG_ONE_MINUS_C + logScale - Math.log(denominator);
    information[index] = A * A * (1.0 - C) * known * known * (1.0 - known)
      / (C + (1.0 - C) * known);
  }
  curves = { correct, failure, information };
  itemCurvesCache.set(rank, curves);
  return curves;
}

/** 精确人口/信息量和（共用概率计算）。 */
function rangeCurves(start, end) {
  const cacheKey = `${start}:${end}`;
  const cached = rangeCurvesCache.get(cacheKey);
  if (cached !== undefined) return cached;
  const scales = new Array(end - start + 1);
  for (let rank = start; rank <= end; rank += 1) scales[rank - start] = rankScale(rank);
  const population = new Array(THETA_GRID.length);
  const information = new Array(THETA_GRID.length);
  const factor = A * A * (1.0 - C);
  const oneMinusC = 1.0 - C;
  for (let index = 0; index < THETA_GRID.length; index += 1) {
    const exponential = THETA_EXP[index];
    const known = scales.map((scale) => exponential / (exponential + scale));
    population[index] = exactSum(known);
    information[index] = exactSum(known.map((q) => factor * q * q * (1.0 - q) / (C + oneMinusC * q)));
  }
  const result = { population, information };
  rangeCurvesCache.set(cacheKey, result);
  return result;
}

/** 对每个保留的本地 rank 精确求和，而不是取层中点。 */
function populationCurve(start, end) {
  return rangeCurves(start, end).population;
}

function informationCurve(ranks) {
  if (ranks.length > 0 && ranks[ranks.length - 1] - ranks[0] + 1 === ranks.length) {
    return rangeCurves(ranks[0], ranks[ranks.length - 1]).information;
  }
  const scales = ranks.map((rank) => rankScale(rank));
  const result = new Array(THETA_GRID.length);
  const factor = A * A * (1.0 - C);
  const oneMinusC = 1.0 - C;
  for (let index = 0; index < THETA_GRID.length; index += 1) {
    const exponential = THETA_EXP[index];
    const known = scales.map((scale) => exponential / (exponential + scale));
    result[index] = exactSum(known.map((q) => factor * q * q * (1.0 - q) / (C + oneMinusC * q)));
  }
  return result;
}

// ---------------------------------------------------------------------------
// 频率分档题库
// ---------------------------------------------------------------------------

/**
 * 使用中的不可变本地测量总体与缓存的选项池。
 *
 * `size` 包含被保留的频率词目——即便保守内容检查对其中一些词目无法构造题目；
 * `testable_size` / `untestable_count` 明确区分。这样的词目永远不会被抽到；
 * 无法填充的层绝不会被悄悄当成已覆盖。
 */
export class FrequencyBank {
  /**
   * @param {Iterable<object>} words 词条数组（含 w/frq/s/pos/raw/display_w/type 等）
   * @param {((percent:number)=>void)|null} [progress] 0..100 单调进度回调
   */
  constructor(words, progress = null) {
    if (progress !== null && progress !== undefined && typeof progress !== 'function') {
      throw new Error('progress must be callable or None');
    }
    (progress ?? null);
    let lastProgress = -1;
    const report = (value) => {
      const clamped = Math.max(0, Math.min(100, Math.trunc(value)));
      if (clamped <= lastProgress) return;
      lastProgress = clamped;
      if (progress !== null && progress !== undefined) progress(clamped);
    };

    report(0);
    const { selected, inputCount } = selectEntries(words);
    report(10);
    this.size = selected.length;
    this.excluded_count = inputCount - this.size;
    this.bands = [];
    this.items = Object.create(null);
    const profiles = new Map();
    const primary = new Map();
    const byBand = new Map();
    const byBandPos = new Map();
    const sourceRows = [];
    for (let start = 1; start <= this.size; start += BAND_SIZE) {
      const end = Math.min(start + BAND_SIZE - 1, this.size);
      const band = Math.trunc((start - 1) / BAND_SIZE) + 1;
      this.bands.push({ id: band, label: `本地有效词目 ${start}–${end}`, size: end - start + 1, start, end });
      byBand.set(band, []);
    }
    const itemTotal = Math.max(1, selected.length);
    const itemTick = Math.max(1, Math.trunc(itemTotal / 50));
    for (let index = 0; index < selected.length; index += 1) {
      const source = selected[index];
      const rank = index + 1;
      const key = source.key;
      const band = Math.trunc((rank - 1) / BAND_SIZE) + 1;
      const item = {
        key,
        word: source.word,
        sense: source.sense,
        source_frq: source.source_frq,
        pos: source.pos.slice(),
        rank,
        band,
        a: A,
        b: difficulty(rank),
        c: C,
      };
      this.items[key] = item;
      profiles.set(key, semanticProfile(item.sense, source.source_raw));
      const primaryValue = primaryPos(item.pos, item.sense);
      primary.set(key, primaryValue);
      byBand.get(band).push(key);
      const posKey = `${band}\u0000${primaryValue}`;
      if (!byBandPos.has(posKey)) byBandPos.set(posKey, []);
      byBandPos.get(posKey).push(key);
      sourceRows.push([key, item.word, item.sense, item.pos, item.source_frq, source.source_raw]);
      if (rank === selected.length || rank % itemTick === 0) {
        report(10 + Math.trunc((20 * rank) / itemTotal));
      }
    }
    report(30);
    // 干扰项构建（_buildDistractors）需要读取这些索引，先挂到实例上（Python 在
    // 同一 __init__ 中同样是先填属性再建池）。
    this._profiles = profiles;
    this._primary = primary;
    this._byBand = byBand;
    this._byBandPos = byBandPos;

    // 重名同义项共享构建工作；候选池本身两两相容，因此任意抽出的三元组都安全，
    // nextItem 无需扫描整个题库找干扰项。
    const templates = new Map();
    const distractors = new Map();
    const testableByBand = new Map();
    for (const band of this.bands) testableByBand.set(band.id, []);
    const distractorTotal = Math.max(1, Object.keys(this.items).length);
    const distractorTick = Math.max(1, Math.trunc(distractorTotal / 100));
    let itemNumber = 0;
    for (const key of Object.keys(this.items)) {
      itemNumber += 1;
      const item = this.items[key];
      const signature = `${item.band}\u0000${primary.get(key)}\u0000${profiles.get(key).id}`;
      let pool = templates.get(signature);
      if (pool === undefined) {
        pool = this._buildDistractors(key);
        templates.set(signature, pool);
      }
      distractors.set(key, pool);
      if (pool.length >= 3) testableByBand.get(item.band).push(key);
      if (itemNumber === distractorTotal || itemNumber % distractorTick === 0) {
        report(30 + Math.trunc((45 * itemNumber) / distractorTotal));
      }
    }
    report(75);

    this._distractors = distractors;
    this._testableByBand = testableByBand;
    let testableSize = 0;
    for (const keys of testableByBand.values()) testableSize += keys.length;
    this.testable_size = testableSize;
    this.untestable_count = this.size - this.testable_size;

    this._population = new Map();
    const bandTotal = Math.max(1, this.bands.length);
    for (let index = 0; index < this.bands.length; index += 1) {
      const band = this.bands[index];
      this._population.set(band.id, populationCurve(band.start, band.end));
      report(75 + Math.trunc((10 * (index + 1)) / bandTotal));
    }
    report(85);
    this._information = new Map();
    const informationTotal = Math.max(1, this._testableByBand.size);
    let bandNumber = 0;
    for (const [bandId, keys] of this._testableByBand) {
      bandNumber += 1;
      this._information.set(bandId, informationCurve(keys.map((key) => this.items[key].rank)));
      report(85 + Math.trunc((8 * bandNumber) / informationTotal));
    }
    report(93);
    this._totalPopulation = new Array(THETA_GRID.length);
    for (let index = 0; index < THETA_GRID.length; index += 1) {
      const column = [];
      for (const curve of this._population.values()) column.push(curve[index]);
      this._totalPopulation[index] = exactSum(column);
    }
    report(95);

    const testable = Object.keys(this.items).filter((key) => this._distractors.get(key).length >= 3);
    const identity = {
      algorithm: ALGORITHM,
      session_schema: SESSION_SCHEMA,
      measurement_schema: MEASUREMENT_SCHEMA,
      unit: UNIT,
      scope: {
        size: this.size,
        max_words: MAX_WORDS,
        band_size: BAND_SIZE,
        local_rank: true,
        bands: this.bands,
      },
      model: {
        a: A,
        c: C,
        b: 'ln((local_rank+100)/1000)',
        theta_grid: [THETA_MIN, THETA_MAX, THETA_STEP],
        prior: [PRIOR_MEAN, PRIOR_SD],
        interval_level: INTERVAL_LEVEL,
      },
      test: {
        min_items: MIN_ITEMS,
        max_items: MAX_ITEMS,
        min_per_band: MIN_PER_BAND,
        target_se: TARGET_SE,
        content_policy: CONTENT_POLICY,
        distractor_pool: DISTRACTOR_POOL,
        abbreviation_keys: [...ABBREVIATION_KEYS].sort(),
      },
      sources: sourceRows,
      testable,
    };
    this.identity = identity;
    this.fingerprint = fingerprintOf(identity);
    report(100);
  }

  /** 同层同词性优先，再邻近层的该词性，最后才用其它词性的真实释义。 */
  *_candidateGroups(key) {
    const item = this.items[key];
    const band = item.band;
    const primaryValue = this._primary.get(key);
    const nearest = [...this._byBand.keys()].sort((left, right) => {
      const distance = Math.abs(left - band) - Math.abs(right - band);
      return distance !== 0 ? distance : left - right;
    });
    for (const number of nearest) {
      yield this._byBandPos.get(`${number}\u0000${primaryValue}`) ?? [];
    }
    for (const number of nearest) {
      yield this._byBand.get(number);
    }
  }

  _buildDistractors(key) {
    const offset = createHash('sha256').update(key, 'utf8').digest().readBigUInt64BE(0);
    const visited = new Set();
    const seenProfiles = new Set();
    const compatible = [];
    const pool = [];
    const poolProfiles = [];
    const targetProfile = this._profiles.get(key);
    for (const group of this._candidateGroups(key)) {
      const length = group.length;
      if (length === 0) continue;
      const start = Number(offset % BigInt(length));
      for (let index = 0; index < length; index += 1) {
        const candidate = group[(start + index) % length];
        if (visited.has(candidate)) continue;
        visited.add(candidate);
        const profile = this._profiles.get(candidate);
        if (seenProfiles.has(profile.id) || profilesConflict(targetProfile, profile)) continue;
        seenProfiles.add(profile.id);
        compatible.push(candidate);
        if (poolProfiles.every((other) => !profilesConflict(profile, other))) {
          pool.push(candidate);
          poolProfiles.push(profile);
          if (pool.length === DISTRACTOR_POOL) return pool;
        }
      }
      // 不要仅为扩大已可用的同组干扰项而引入更低优先级的频率/词性组。
      if (pool.length >= 3) return pool;
    }
    if (pool.length >= 3) return pool;
    // 贪心首选可能挡住本可成立的三元组；这种小/歧义情形精确求解。
    for (let firstIndex = 0; firstIndex < compatible.length; firstIndex += 1) {
      const first = compatible[firstIndex];
      const neighbors = compatible.slice(firstIndex + 1).filter((second) => this._compatible(first, second));
      for (let secondIndex = 0; secondIndex < neighbors.length; secondIndex += 1) {
        const second = neighbors[secondIndex];
        for (const third of neighbors.slice(secondIndex + 1)) {
          if (this._compatible(second, third)) return [first, second, third];
        }
      }
    }
    return [];
  }

  _compatible(left, right) {
    return left !== right && !profilesConflict(this._profiles.get(left), this._profiles.get(right));
  }

  /** Python `bank.items[key]` 的显式访问器（items 为普通对象，这里仅作便利）。 */
  getItem(key) {
    return Object.prototype.hasOwnProperty.call(this.items, key) ? this.items[key] : undefined;
  }
}

// ---------------------------------------------------------------------------
// 会话状态
// ---------------------------------------------------------------------------

export function newState(seed) {
  if (typeof seed !== 'number' || !Number.isInteger(seed)) {
    throw new Error('seed must be an integer, not bool');
  }
  return { seed, asked: [], theta: 0.0, se: 2.0 };
}

function requireBank(bank) {
  if (!(bank instanceof FrequencyBank)) throw new Error('bank must be a FrequencyBank');
}

function isSlotIndex(value) {
  return typeof value === 'number' && Number.isInteger(value);
}

function validateRecord(bank, record) {
  if (record === null || typeof record !== 'object' || Array.isArray(record)) {
    throw new Error('record must be a dictionary');
  }
  const key = record.key;
  if (typeof key !== 'string' || !(key in bank.items)) {
    throw new Error('record has an unknown key');
  }
  const source = bank.items[key];
  if (!isSlotIndex(record.band) || record.band !== source.band
    || !isSlotIndex(record.rank) || record.rank !== source.rank
    || (record.phase !== 'survey' && record.phase !== 'adaptive')) {
    throw new Error('record rank, band, or phase is invalid');
  }
  const irt = record.irt;
  if (irt === null || typeof irt !== 'object' || Array.isArray(irt)
    || ['a', 'b', 'c'].some((name) => !finiteNumber(irt[name]) || irt[name] !== source[name])) {
    throw new Error('record IRT parameters do not match the fixed bank');
  }
  const item = record.item;
  if (item === null || typeof item !== 'object' || Array.isArray(item)
    || item.item_id !== key || item.word !== source.word) {
    throw new Error('record target ID or display word does not match');
  }
  const options = item.options;
  const correct = item.correct_index;
  if (!Array.isArray(options) || options.length !== 4
    || !isSlotIndex(correct) || correct < 0 || correct >= 4
    || item.correct_key !== SLOTS[correct]) {
    throw new Error('item needs four slots and a valid correct slot');
  }
  const optionKeys = [];
  for (let index = 0; index < options.length; index += 1) {
    const option = options[index];
    if (option === null || typeof option !== 'object' || Array.isArray(option)
      || option.key !== SLOTS[index]) {
      throw new Error('option slot keys must be ordered A, B, C, D');
    }
    const optionId = option.item_id;
    if (typeof optionId !== 'string' || !(optionId in bank.items)
      || option.text !== bank.items[optionId].sense) {
      throw new Error('option text and stable ID must match the bank');
    }
    if (optionKeys.some((previous) => !bank._compatible(optionId, previous))) {
      throw new Error('duplicate or conflicting option meanings');
    }
    optionKeys.push(optionId);
  }
  if (optionKeys[correct] !== key || optionKeys.filter((optionId) => optionId === key).length !== 1) {
    throw new Error('exactly one option must be the target sense');
  }
  return key;
}

function validateHistory(bank, records, responses) {
  requireBank(bank);
  if (!Array.isArray(records) || !Array.isArray(responses)) {
    throw new Error('records and responses must be sequences');
  }
  if (records.length > MAX_ITEMS || responses.length > MAX_ITEMS
    || [0, 1].indexOf(records.length - responses.length) === -1) {
    throw new Error('history must contain only answered items and at most one pending item');
  }
  if (responses.some((response) => !isSlotIndex(response) || (response !== -1 && response !== 0 && response !== 1))) {
    throw new Error('responses must be exact integers -1, 0, or 1');
  }
  const keys = [];
  for (const record of records) {
    const key = validateRecord(bank, record);
    if (keys.includes(key)) throw new Error('target keys cannot repeat');
    keys.push(key);
  }
  return keys;
}

function sameStringArray(left, right) {
  if (!Array.isArray(left) || left.length !== right.length) return false;
  for (let index = 0; index < right.length; index += 1) {
    if (left[index] !== right[index]) return false;
  }
  return true;
}

function validateState(state, keys) {
  if (state === null || typeof state !== 'object' || Array.isArray(state)
    || typeof state.seed !== 'number' || !Number.isInteger(state.seed)
    || !Array.isArray(state.asked)
    || !sameStringArray(state.asked, keys)
    || !finiteNumber(state.theta)
    || state.theta < THETA_MIN || state.theta > THETA_MAX
    || !finiteNumber(state.se) || state.se < 0 || state.se > 6.0) {
    throw new Error('state seed, asked keys, theta, or se is invalid');
  }
}

// ---------------------------------------------------------------------------
// 后验 / 统计
// ---------------------------------------------------------------------------

const posteriorCache = new Map();

function posterior(evidence) {
  const cacheKey = evidence.map(([rank, response]) => `${rank}:${response}`).join(',');
  const cached = posteriorCache.get(cacheKey);
  if (cached !== undefined) return cached;
  let logWeights = PRIOR_LOG.slice();
  for (const [rank, response] of evidence) {
    const curve = response === 1 ? itemCurves(rank).correct : itemCurves(rank).failure;
    const next = new Array(THETA_GRID.length);
    for (let index = 0; index < THETA_GRID.length; index += 1) next[index] = logWeights[index] + curve[index];
    logWeights = next;
  }
  let maximum = logWeights[0];
  for (const value of logWeights) if (value > maximum) maximum = value;
  const unnormalized = logWeights.map((value) => Math.exp(value - maximum));
  const normalizer = exactSum(unnormalized);
  const weights = unnormalized.map((value) => value / normalizer);
  posteriorCache.set(cacheKey, weights);
  return weights;
}

function weightsOf(records, responses) {
  // 不认识与答错故意产生相同缓存键与相同似然；没有严谨度奖惩。
  const evidence = [];
  const length = Math.min(records.length, responses.length);
  for (let index = 0; index < length; index += 1) {
    evidence.push([records[index].rank, responses[index] === 1 ? 1 : 0]);
  }
  return posterior(evidence);
}

function dot(left, right) {
  const products = new Array(Math.min(left.length, right.length));
  for (let index = 0; index < products.length; index += 1) products[index] = left[index] * right[index];
  return exactSum(products);
}

function thetaStats(weights) {
  const mean = dot(THETA_GRID, weights);
  const deviations = new Array(THETA_GRID.length);
  for (let index = 0; index < THETA_GRID.length; index += 1) {
    const difference = THETA_GRID[index] - mean;
    deviations[index] = weights[index] * difference ** 2;
  }
  const variance = exactSum(deviations);
  return [mean, Math.sqrt(variance)];
}

function quantileIndex(weights, probability) {
  let cumulative = 0.0;
  for (let index = 0; index < weights.length; index += 1) {
    cumulative += weights[index];
    if (cumulative >= probability) return index;
  }
  return weights.length - 1;
}

function countsOf(bank, records, responses) {
  const counts = new Map();
  for (const band of bank.bands) counts.set(band.id, [0, 0, 0]);
  const length = Math.min(records.length, responses.length);
  for (let index = 0; index < length; index += 1) {
    const record = records[index];
    const response = responses[index];
    const value = counts.get(record.band);
    value[0] += 1;
    value[1] += response === 1 ? 1 : 0;
    value[2] += response === -1 ? 1 : 0;
  }
  return counts;
}

function stopReason(bank, records, responses, se, coverage) {
  const answered = responses.length;
  if (answered >= MAX_ITEMS) return 'max_items';
  if (answered >= MIN_ITEMS && coverage === bank.bands.length && se <= TARGET_SE) return 'precision';
  // 最后一道已呈现但未作答的题仍是可用证据。
  if (records.length === answered && records.length >= bank.testable_size) return 'exhausted';
  return null;
}

// ---------------------------------------------------------------------------
// 公开 API
// ---------------------------------------------------------------------------

/**
 * 未修改的 EAP 计数与变换后的 95% 等尾模型区间。
 *
 * 层估计先对该层全部 rank 求和识别概率，再对后验积分；猜测不当作识别。
 * 不做观测分缩放、最小宽度截断或端点调整。可用性要求 40 题且每层至少 2 题。
 */
export function summarize(bank, records, responses) {
  validateHistory(bank, records, responses);
  const weights = weightsOf(records, responses);
  const [theta, se] = thetaStats(weights);
  const lower = quantileIndex(weights, (1.0 - INTERVAL_LEVEL) / 2.0);
  const upper = quantileIndex(weights, 1.0 - (1.0 - INTERVAL_LEVEL) / 2.0);
  const counts = countsOf(bank, records, responses);
  const bands = [];
  for (const source of bank.bands) {
    const band = source.id;
    const [answered, correct, unknown] = counts.get(band);
    const curve = bank._population.get(band);
    const estimate = dot(curve, weights);
    bands.push({
      id: band,
      label: source.label,
      size: source.size,
      answered,
      correct,
      unknown,
      estimate,
      low: curve[lower],
      high: curve[upper],
      p_known: estimate / source.size,
    });
  }
  const answered = responses.length;
  let correct = 0;
  let dontknow = 0;
  for (const response of responses) {
    if (response === 1) correct += 1;
    else if (response === -1) dontknow += 1;
  }
  let coverage = 0;
  for (const value of counts.values()) if (value[0] >= MIN_PER_BAND) coverage += 1;
  const available = answered >= MIN_ITEMS && coverage === bank.bands.length;
  let boundary = null;
  if (answered > 0 && correct === answered) boundary = 'all_correct';
  else if (answered > 0 && correct === 0) boundary = 'all_incorrect';
  else if (weights[0] + weights[weights.length - 1] >= 0.01) boundary = 'grid_edge';
  const provisional = !available || se > TARGET_SE || boundary !== null;
  const population = bank._totalPopulation;
  let surveyCoverage = 0;
  for (const value of counts.values()) if (value[0] >= 1) surveyCoverage += 1;
  return {
    theta,
    se,
    estimate: dot(population, weights),
    low: population[lower],
    high: population[upper],
    answered,
    correct_count: correct,
    dontknow,
    estimate_available: available,
    provisional,
    bands,
    coverage,
    coverage_target: bank.bands.length,
    survey_coverage: surveyCoverage,
    stop_reason: stopReason(bank, records, responses, se, coverage),
    unit: UNIT,
    interval_level: INTERVAL_LEVEL,
    boundary,
    theta_low: THETA_GRID[lower],
    theta_high: THETA_GRID[upper],
    evidence_limited: provisional,
    model_only: true,
    measurement_schema: MEASUREMENT_SCHEMA,
    algo: ALGORITHM,
    bank_id: bank.fingerprint,
    population_size: bank.size,
    testable_size: bank.testable_size,
    untestable_count: bank.untestable_count,
  };
}

/** 均匀“剩余层内抽取”的期望 Fisher 信息量。 */
function expectedInformation(bank, band, weights, records) {
  const asked = records.filter((record) => record.band === band);
  const remaining = bank._testableByBand.get(band).length - asked.length;
  if (remaining <= 0) throw new Error('cannot score an exhausted band');
  const total = dot(bank._information.get(band), weights);
  const used = exactSum(asked.map((record) => dot(itemCurves(record.rank).information, weights)));
  return (total - used) / remaining;
}

/**
 * 纯选题：有序 survey、覆盖约束下的信息量 CAT。
 *
 * 层由后验期望 3PL Fisher 信息量选择；层内未问目标为种子化均匀抽取，
 * 绝不是信息量最大、易端短名单或对错连续阶梯。
 */
export function nextItem(bank, state, records, responses) {
  const keys = validateHistory(bank, records, responses);
  validateState(state, keys);
  if (records.length !== responses.length) {
    throw new Error('answer the pending item before requesting another');
  }
  const weights = weightsOf(records, responses);
  const [, se] = thetaStats(weights);
  const counts = countsOf(bank, records, responses);
  let coverage = 0;
  for (const value of counts.values()) if (value[0] >= MIN_PER_BAND) coverage += 1;
  if (stopReason(bank, records, responses, se, coverage) !== null) return null;
  const asked = new Set(keys);
  const available = bank.bands
    .map((band) => band.id)
    .filter((bandId) => bank._testableByBand.get(bandId).length > counts.get(bandId)[0]);
  if (available.length === 0) return null;
  let band;
  let phase;
  const survey = available.filter((bandId) => counts.get(bandId)[0] === 0);
  if (survey.length > 0) {
    band = survey[0];
    phase = 'survey';
  } else {
    const undercovered = available.filter((bandId) => counts.get(bandId)[0] < MIN_PER_BAND);
    const candidates = undercovered.length > 0 ? undercovered : available;
    let best = null;
    let bestInformation = -Infinity;
    for (const number of candidates) {
      const information = expectedInformation(bank, number, weights, records);
      if (best === null || information > bestInformation
        || (information === bestInformation && number < best)) {
        best = number;
        bestInformation = information;
      }
    }
    band = best;
    phase = 'adaptive';
  }
  const material = `${ALGORITHM}|${bank.fingerprint}|${formatInteger(state.seed)}|${records.length}`;
  const rng = makeRng(material);
  const unasked = bank._testableByBand.get(band).filter((key) => !asked.has(key));
  const key = unasked[rng.randrange(unasked.length)];
  const source = bank.items[key];
  const optionIds = [key, ...rng.sample(bank._distractors.get(key), 3)];
  rng.shuffle(optionIds);
  const correct = optionIds.indexOf(key);
  const item = {
    item_id: key,
    word: source.word,
    options: optionIds.map((optionId, index) => ({
      key: SLOTS[index],
      text: bank.items[optionId].sense,
      item_id: optionId,
    })),
    correct_index: correct,
    correct_key: SLOTS[correct],
  };
  return {
    key,
    band,
    rank: source.rank,
    phase,
    item,
    irt: { a: source.a, b: source.b, c: source.c },
  };
}

/** Python `%d` 对 int 的十进制文本（JS number 仅在安全范围内保持一致）。 */
function formatInteger(value) {
  if (Number.isSafeInteger(value)) return String(value);
  return BigInt(value).toString();
}

/**
 * 校验当前/待答或刚答完的 JSON 会话快照，无 TTL。
 *
 * 未知扩展字段被忽略并保留。校验来源身份、固定参数、精确选项 ID/文本与内容歧义；
 * 这是校验，不是“用户从未改过作答”的密码学声明。绝不写入 session/bank/state。
 */
export function validateSession(session, bank) {
  try {
    requireBank(bank);
    if (session === null || typeof session !== 'object' || Array.isArray(session)
      || typeof session.schema !== 'number' || !Number.isInteger(session.schema)
      || session.schema !== SESSION_SCHEMA || session.algo !== ALGORITHM
      || session.bank_id !== bank.fingerprint) {
      return false;
    }
    const identifier = session.id;
    if (typeof identifier !== 'string' || pyStrip(identifier).length === 0 || identifier.length > 256
      || [...identifier].some((char) => char.codePointAt(0) < 32)
      || !finiteNumber(session.started_at)) {
      return false;
    }
    const items = session.items;
    const responses = session.resp;
    const index = session.i;
    if (!Array.isArray(items) || !Array.isArray(responses)
      || typeof index !== 'number' || !Number.isInteger(index) || index < 0 || index >= MAX_ITEMS
      || items.length !== index + 1 || (responses.length !== index && responses.length !== index + 1)) {
      return false;
    }
    const keys = validateHistory(bank, items, responses);
    validateState(session.state, keys);
    // 强制 survey 顺序/phase，不重采样、不信任已保存的 theta/se。
    // adaptive 题目 ID 无需重新生成即可校验。
    const counts = new Map();
    for (const band of bank.bands) counts.set(band.id, 0);
    for (const record of items) {
      const unseen = bank.bands
        .map((band) => band.id)
        .filter((bandId) => counts.get(bandId) === 0 && bank._testableByBand.get(bandId).length > 0);
      if (unseen.length > 0) {
        if (record.phase !== 'survey' || record.band !== unseen[0]) return false;
      } else if (record.phase !== 'adaptive') {
        return false;
      }
      counts.set(record.band, counts.get(record.band) + 1);
    }
    return true;
  } catch (error) {
    return false;
  }
}
