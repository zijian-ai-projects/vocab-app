/**
 * 本仓库自有的规范 JSON 序列化 + 指纹。
 *
 * 目的：给测评 identity / 记录附指纹时，只要求「同输入必然同输出、跨进程稳定」，
 * 不要求与 Python `json.dumps(sort_keys=True)` 逐字节相同。规则：
 * - 对象键按 JS 默认字符串序（UTF-16 code unit）排序，无空格；
 * - 字符串只转义 JSON 必须转义的字符（" \ 和控制字符），非 ASCII 原样输出；
 * - 数字用 Number#toString（整数不带小数点，-0 输出 "0"）；
 * - 数组保持顺序；undefined/函数/Symbol 属性按 JSON.stringify 语义处理
 *   （对象属性省略、数组元素变 null），BigInt/循环引用/非有限数直接报错。
 */
import { createHash } from 'node:crypto';

const CONTROL_ESCAPES = {
  0x08: '\\b',
  0x09: '\\t',
  0x0a: '\\n',
  0x0c: '\\f',
  0x0d: '\\r',
};

function escapeString(text) {
  let out = '"';
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    const char = text[i];
    if (char === '"') {
      out += '\\"';
    } else if (char === '\\') {
      out += '\\\\';
    } else if (code < 0x20) {
      out += CONTROL_ESCAPES[code] || `\\u${code.toString(16).padStart(4, '0')}`;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      // 代理对保留原字符；落单的高位代理转义，保证输出仍是合法 JSON。
      const next = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        out += char + text[i + 1];
        i += 1;
      } else {
        out += `\\u${code.toString(16).padStart(4, '0')}`;
      }
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      out += `\\u${code.toString(16).padStart(4, '0')}`;
    } else {
      out += char;
    }
  }
  return `${out}"`;
}

function isPlainObject(value) {
  if (value === null || typeof value !== 'object') return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function rejectUnsupported(value, path) {
  if (typeof value === 'bigint') {
    throw new TypeError(`canonicalJson: BigInt 不可序列化（${path}）`);
  }
  if (typeof value === 'function' || typeof value === 'symbol') {
    return undefined;
  }
  if (typeof value === 'object' && value !== null && !Array.isArray(value) && !isPlainObject(value)) {
    throw new TypeError(`canonicalJson: 不支持的对象类型（${path}）`);
  }
  return value;
}

function write(value, path, stack) {
  const checked = rejectUnsupported(value, path);
  if (checked === undefined || checked === null) return 'null';
  const type = typeof checked;
  if (type === 'boolean') return checked ? 'true' : 'false';
  if (type === 'number') {
    if (!Number.isFinite(checked)) {
      throw new TypeError(`canonicalJson: 非有限数字不可序列化（${path}）`);
    }
    return String(checked);
  }
  if (type === 'string') return escapeString(checked);
  if (type !== 'object') {
    throw new TypeError(`canonicalJson: 未知类型 ${type}（${path}）`);
  }
  if (stack.has(checked)) {
    throw new TypeError(`canonicalJson: 循环引用（${path}）`);
  }
  stack.add(checked);
  let out;
  if (Array.isArray(checked)) {
    const parts = new Array(checked.length);
    for (let i = 0; i < checked.length; i += 1) {
      const item = checked[i];
      const itemChecked = rejectUnsupported(item, `${path}[${i}]`);
      parts[i] = itemChecked === undefined ? 'null' : write(itemChecked, `${path}[${i}]`, stack);
    }
    out = `[${parts.join(',')}]`;
  } else {
    const keys = Object.keys(checked).sort();
    const parts = [];
    for (const key of keys) {
      const item = rejectUnsupported(checked[key], `${path}.${key}`);
      if (item === undefined) continue;
      parts.push(`${escapeString(key)}:${write(item, `${path}.${key}`, stack)}`);
    }
    out = `{${parts.join(',')}}`;
  }
  stack.delete(checked);
  return out;
}

/**
 * 规范序列化：键排序、无空格、非 ASCII 原样、数字用 Number#toString。
 * @param {unknown} value
 * @returns {string}
 */
export function canonicalJson(value) {
  return write(value, '$', new Set());
}

/**
 * canonicalJson 的 SHA-256 十六进制指纹。
 * @param {unknown} value
 * @returns {string}
 */
export function fingerprintOf(value) {
  return createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex');
}

export default canonicalJson;
