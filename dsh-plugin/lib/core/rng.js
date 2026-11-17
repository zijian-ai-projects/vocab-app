/**
 * DSH 版确定随机源：SHA-256 计数器 DRBG。
 *
 * 为什么不用 `Math.random`：测评抽题、选项洗牌、学习队列重现都需要同一种子产生
 * 同一序列，否则刷新/重连后题目会变。为什么不是 CPython `random.Random` 逐位复现：
 * 桌面版用它，但两版资料本来就独立（用户确认不共享/不导入），DSH 版只需自洽、
 * 可复现、无偏；跨实现位级一致并不改变任何心理测量结论。此处用公开、简单、
 * 可复算的构造，避免"看起来像 CPython 却对不上"的隐式风险。
 *
 * 约定（写入 identity，版本变化必须改 ALGO_TAG）：
 *   block_i = SHA-256("<tag>|<material>|<i>")，i 从 0 递增，取前 8 个 uint32（大端）。
 *   uniform()  = uint32() / 2**32
 *   randrange(n)：拒绝采样，拒绝 >= 2**32 - (2**32 mod n) 的值，保证无偏。
 */
import { createHash } from 'node:crypto';

export const RNG_CONTRACT = 'sha256-ctr-v1';

export function makeRng(material, tag = RNG_CONTRACT) {
  if (typeof material !== 'string' || !material) {
    throw new TypeError('makeRng 需要非空字符串材料');
  }
  let counter = 0;
  let words = [];

  const refill = () => {
    const digest = createHash('sha256')
      .update(`${tag}|${material}|${counter}`, 'utf8')
      .digest();
    counter += 1;
    words = new Array(8);
    for (let i = 0; i < 8; i += 1) words[i] = digest.readUInt32BE(i * 4);
  };

  const uint32 = () => {
    if (words.length === 0) refill();
    return words.shift();
  };

  const uniform = () => uint32() / 4294967296;

  const randrange = (n) => {
    if (!Number.isInteger(n) || n <= 0) throw new RangeError('randrange 需要正整数');
    if (n === 1) return 0;
    const limit = 4294967296 - (4294967296 % n);
    for (;;) {
      const value = uint32();
      if (value < limit) return value % n;
    }
  };

  const choice = (seq) => {
    if (!seq.length) throw new RangeError('Cannot choose from an empty sequence');
    return seq[randrange(seq.length)];
  };

  const sample = (seq, k) => {
    const n = seq.length;
    if (!Number.isInteger(k) || k < 0 || k > n) throw new RangeError('sample 数量越界');
    const pool = Array.from(seq);
    const out = new Array(k);
    for (let i = 0; i < k; i += 1) {
      const j = randrange(n - i);
      out[i] = pool[j];
      pool[j] = pool[n - i - 1];
    }
    return out;
  };

  const shuffle = (seq) => {
    for (let i = seq.length - 1; i > 0; i -= 1) {
      const j = randrange(i + 1);
      const tmp = seq[i];
      seq[i] = seq[j];
      seq[j] = tmp;
    }
    return seq;
  };

  return { uint32, uniform, randrange, choice, sample, shuffle };
}
