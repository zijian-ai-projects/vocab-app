/**
 * DSH host HTTP 路由层：只暴露两个 exact 路径。
 *   GET  /api/vocab-app/state   -> {rev, view}
 *   POST /api/vocab-app/action  -> {ok:true, rev, view} | {ok:false, code, message, rev, view}
 *
 * 请求体 ≤ 64KiB，Content-Type 必须 application/json；解析失败/字段非法/未知 type
 * 一律 4xx 或 {ok:false,code:'invalid'}，且绝不改状态。响应 JSON 会剔除函数/
 * undefined 并把非有限数字转 null，保证可序列化。
 */
export const STATE_PATH = '/api/vocab-app/state';
export const ACTION_PATH = '/api/vocab-app/action';
export const MAX_BODY_BYTES = 64 * 1024;

const JSON_HEADERS = Object.freeze({
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
});

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** 递归清洗为纯 JSON 值：剔除函数/undefined/symbol，非有限数字转 null。 */
export function toJsonSafe(value, seen = new Set()) {
  if (value === null) return null;
  const type = typeof value;
  if (type === 'string' || type === 'boolean') return value;
  if (type === 'number') return Number.isFinite(value) ? value : null;
  if (type === 'bigint') return String(value);
  if (type === 'undefined' || type === 'function' || type === 'symbol') return undefined;
  if (type !== 'object') return undefined;
  if (seen.has(value)) throw new Error('响应包含循环引用，无法序列化');
  seen.add(value);
  try {
    if (Array.isArray(value)) {
      const out = [];
      for (const item of value) {
        const safe = toJsonSafe(item, seen);
        out.push(safe === undefined ? null : safe);
      }
      return out;
    }
    if (value instanceof Map) {
      const out = {};
      for (const [key, item] of value) {
        const safe = toJsonSafe(item, seen);
        if (safe !== undefined) out[String(key)] = safe;
      }
      return out;
    }
    if (value instanceof Set) return Array.from(value, (item) => toJsonSafe(item, seen)).filter(
      (item) => item !== undefined,
    );
    const out = {};
    for (const key of Object.keys(value)) {
      const safe = toJsonSafe(value[key], seen);
      if (safe !== undefined) out[key] = safe;
    }
    return out;
  } finally {
    seen.delete(value);
  }
}

export function jsonResponse(payload, status = 200) {
  const body = JSON.stringify(toJsonSafe(payload));
  return new Response(body, { status, headers: JSON_HEADERS });
}

function methodNotAllowed(allowed) {
  return new Response('method not allowed', {
    status: 405,
    headers: { allow: allowed, 'cache-control': 'no-store' },
  });
}

async function readJsonBody(request) {
  const declared = request.headers.get('content-length');
  if (declared !== null && declared !== undefined && declared !== '') {
    const length = Number(declared);
    if (Number.isFinite(length) && length > MAX_BODY_BYTES) {
      return { ok: false, status: 413, message: `请求体超过 ${MAX_BODY_BYTES} 字节上限` };
    }
  }
  let text;
  try {
    text = await request.text();
  } catch (error) {
    return { ok: false, status: 400, message: `无法读取请求体：${error.message || error}` };
  }
  const bytes = Buffer.byteLength(text, 'utf8');
  if (bytes > MAX_BODY_BYTES) {
    return { ok: false, status: 413, message: `请求体 ${bytes} 字节超过 ${MAX_BODY_BYTES} 字节上限` };
  }
  if (!text.trim()) return { ok: false, status: 400, message: '请求体为空' };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (error) {
    return { ok: false, status: 400, message: `请求体不是有效 JSON：${error.message || error}` };
  }
}

function contentTypeIsJson(request) {
  const header = request.headers.get('content-type');
  if (!header) return false;
  return header.split(';', 1)[0].trim().toLowerCase() === 'application/json';
}

/**
 * 校验 action 请求信封：{rev:int, type:string, payload?:object}。
 * @returns {{ok:true, rev:number, type:string, payload:object}|{ok:false, message:string}}
 */
export function validateActionEnvelope(body) {
  if (!isPlainObject(body)) return { ok: false, message: '请求体必须是 JSON 对象' };
  const revision = body.rev;
  if (!Number.isInteger(revision) || revision < 0) {
    return { ok: false, message: 'rev 必须是非负整数' };
  }
  if (typeof body.type !== 'string' || !body.type.trim()) {
    return { ok: false, message: 'type 必须是非空字符串' };
  }
  let payload = body.payload;
  if (payload === undefined || payload === null) payload = {};
  if (!isPlainObject(payload)) return { ok: false, message: 'payload 必须是 JSON 对象' };
  return { ok: true, rev: revision, type: body.type.trim(), payload };
}

function failureResponse(code, message, rev, view, status = 200) {
  return jsonResponse({ ok: false, code, message, rev, view }, status);
}

/**
 * 创建两个 exact 路由的 fetch 处理器。
 * @param {{engine:object}} options engine 需提供 ready()/state()/applyAction()
 * @returns {{state:Function, action:Function}}
 */
export function createHandlers(options = {}) {
  const engine = options.engine;
  if (!engine) throw new TypeError('createHandlers 需要 engine');

  const notReadyResponse = (error) => {
    const message = error && error.message ? error.message : String(error);
    return jsonResponse(
      { ok: false, code: error && error.code === 'conflict' ? 'conflict' : 'failed', message, rev: null, view: null },
      503,
    );
  };

  async function state(request) {
    if (request.method !== 'GET') return methodNotAllowed('GET');
    let snapshot;
    try {
      await engine.ready();
      snapshot = engine.state();
    } catch (error) {
      return notReadyResponse(error);
    }
    return jsonResponse(snapshot);
  }

  async function action(request) {
    if (request.method !== 'POST') return methodNotAllowed('POST');
    if (!contentTypeIsJson(request)) {
      return jsonResponse(
        { ok: false, code: 'invalid', message: 'Content-Type 必须是 application/json' },
        415,
      );
    }
    const parsed = await readJsonBody(request);
    if (!parsed.ok) {
      return jsonResponse({ ok: false, code: 'invalid', message: parsed.message }, parsed.status);
    }
    const envelope = validateActionEnvelope(parsed.value);
    if (!envelope.ok) {
      return jsonResponse({ ok: false, code: 'invalid', message: envelope.message }, 400);
    }
    let result;
    try {
      await engine.ready();
      result = await engine.applyAction(envelope);
    } catch (error) {
      return notReadyResponse(error);
    }
    return jsonResponse(result);
  }

  return { state, action };
}

export default { createHandlers, STATE_PATH, ACTION_PATH, MAX_BODY_BYTES, toJsonSafe };
