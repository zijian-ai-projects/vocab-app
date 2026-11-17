/**
 * 精确浮点求和：对齐 CPython `math.fsum` 的语义。
 *
 * 普通 `+=` 会把每一次中间结果四舍五入到 double，累加几千个计数或概率时会
 * 产生可见误差。这里把每个 double 精确拆成「整数尾数 × 2^指数」，用 BigInt
 * 求和后再做一次正确舍入（round-half-to-even），因此与 `math.fsum` 一样只有
 * 一次舍入。
 *
 * 与 Python 的差异（均为异常类型）：
 * - `fsum([inf, -inf])` 在 Python 抛 ValueError；这里抛 RangeError。
 * - 有限项之和溢出 double 时 Python 抛 OverflowError；这里抛 RangeError。
 * 正常输入（有限、结果为有限 double）逐位一致。
 */

const _buffer = new ArrayBuffer(8);
const _view = new DataView(_buffer);

const TWO_53 = 1n << 53n;

/** 把有限非零 double 拆成 {m, e}，满足 value === m * 2^e（m 为 BigInt）。 */
function decompose(value) {
  _view.setFloat64(0, value, false);
  const hi = _view.getUint32(0, false);
  const lo = _view.getUint32(4, false);
  const negative = hi >>> 31 === 1;
  const exponentBits = (hi >>> 20) & 0x7ff;
  const fraction = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  let mantissa;
  let exponent;
  if (exponentBits === 0) {
    mantissa = fraction;
    exponent = -1074;
  } else {
    mantissa = (1n << 52n) | fraction;
    exponent = exponentBits - 1075;
  }
  if (negative) mantissa = -mantissa;
  return { m: mantissa, e: exponent };
}

/** 把精确值 total * 2^exp 正确舍入成 double。 */
function roundToNumber(total, exp) {
  if (total === 0n) return 0;
  const negative = total < 0n;
  let mantissa = negative ? -total : total;
  let shift = 0;
  let bits = mantissa.toString(2).length;
  if (bits > 53) {
    shift = bits - 53;
    const dropped = BigInt(shift);
    let kept = mantissa >> dropped;
    const remainder = mantissa - (kept << dropped);
    const half = 1n << (dropped - 1n);
    if (remainder > half || (remainder === half && (kept & 1n) === 1n)) kept += 1n;
    mantissa = kept;
    if (mantissa === TWO_53) {
      mantissa >>= 1n;
      shift += 1;
    }
  }
  let exponent = exp + shift;
  if (exponent < -1074) {
    const extra = BigInt(-1074 - exponent);
    let kept = mantissa >> extra;
    const remainder = mantissa - (kept << extra);
    const half = 1n << (extra - 1n);
    if (remainder > half || (remainder === half && (kept & 1n) === 1n)) kept += 1n;
    mantissa = kept;
    exponent = -1074;
    if (mantissa === 0n) return negative ? -0 : 0;
  }
  const valueBits = mantissa.toString(2).length;
  if (exponent + valueBits - 1 > 1023) {
    throw new RangeError('exactSum: 中间结果溢出 double');
  }
  // mantissa < 2^53 必然可被 Number 精确表示；乘 2^exponent 只移动指数，
  // 在正常数范围内同样是精确的（次正规数由上面的 -1074 分支保证）。
  const value = Number(mantissa) * Math.pow(2, exponent);
  if (!Number.isFinite(value)) {
    throw new RangeError('exactSum: 中间结果溢出 double');
  }
  return negative ? -value : value;
}

function accumulate(pairs) {
  let minimumExponent = Infinity;
  for (const pair of pairs) {
    if (pair.m === 0n) continue;
    if (pair.e < minimumExponent) minimumExponent = pair.e;
  }
  if (minimumExponent === Infinity) return 0;
  let total = 0n;
  for (const pair of pairs) {
    if (pair.m === 0n) continue;
    total += pair.m << BigInt(pair.e - minimumExponent);
  }
  return roundToNumber(total, minimumExponent);
}

/**
 * math.fsum 语义的精确求和。
 * @param {Iterable<number|boolean>} values
 * @returns {number}
 */
export function exactSum(values) {
  if (values == null || typeof values[Symbol.iterator] !== 'function') {
    throw new TypeError('exactSum 需要一个数值可迭代对象');
  }
  const pairs = [];
  let hasNaN = false;
  let hasPositiveInfinity = false;
  let hasNegativeInfinity = false;
  for (const raw of values) {
    let value;
    if (typeof raw === 'boolean') value = raw ? 1 : 0;
    else if (typeof raw === 'number') value = raw;
    else throw new TypeError('exactSum 只接受 number/boolean 项');
    if (Number.isNaN(value)) {
      hasNaN = true;
      continue;
    }
    if (value === Infinity) {
      hasPositiveInfinity = true;
      continue;
    }
    if (value === -Infinity) {
      hasNegativeInfinity = true;
      continue;
    }
    if (value === 0) continue;
    pairs.push(decompose(value));
  }
  if (hasNaN) return NaN;
  // math.fsum([inf, -inf]) 抛 ValueError；这里抛 RangeError。
  if (hasPositiveInfinity && hasNegativeInfinity) {
    throw new RangeError('-inf + inf in exactSum');
  }
  if (hasPositiveInfinity) return Infinity;
  if (hasNegativeInfinity) return -Infinity;
  return accumulate(pairs);
}

/**
 * 精确计算 Σ values[i] * weights[i]（乘积本身不提前舍入）。
 * 仅用于有限数值；非有限项交给 exactSum 的规则处理（乘积为 NaN 时返回 NaN）。
 * @param {Iterable<number>} values
 * @param {Iterable<number>} weights
 * @returns {number}
 */
export function sumProducts(values, weights) {
  const left = Array.from(values);
  const right = Array.from(weights);
  if (left.length !== right.length) {
    throw new TypeError('sumProducts 需要等长的 values 与 weights');
  }
  const pairs = [];
  let hasNaN = false;
  let hasPositiveInfinity = false;
  let hasNegativeInfinity = false;
  for (let i = 0; i < left.length; i += 1) {
    const a = left[i];
    const b = right[i];
    if (typeof a !== 'number' || typeof b !== 'number') {
      throw new TypeError('sumProducts 只接受 number 项');
    }
    if (!Number.isFinite(a) || !Number.isFinite(b) || a === 0 || b === 0) {
      const product = a * b;
      if (Number.isNaN(product)) {
        hasNaN = true;
        continue;
      }
      if (product === Infinity) {
        hasPositiveInfinity = true;
        continue;
      }
      if (product === -Infinity) {
        hasNegativeInfinity = true;
        continue;
      }
      continue; // 有限 0：乘积精确为 0。
    }
    const da = decompose(a);
    const db = decompose(b);
    pairs.push({ m: da.m * db.m, e: da.e + db.e });
  }
  if (hasNaN) return NaN;
  if (hasPositiveInfinity && hasNegativeInfinity) {
    throw new RangeError('-inf + inf in sumProducts');
  }
  if (hasPositiveInfinity) return Infinity;
  if (hasNegativeInfinity) return -Infinity;
  return accumulate(pairs);
}

export default exactSum;
