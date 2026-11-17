/**
 * 背单词 DSH 版状态文档存储（单文件 JSON，原子写 + .bak + 进程级互斥锁）。
 *
 * 路径解析顺序（硬要求，不得改）：
 *   1. process.env.DSH_VOCAB_DATA_DIR —— 直接作为记录目录（测试/隔离用）
 *   2. process.env.DSH_HOME（缺省 ~/.dsh）下 storages/dsh-vocab-app/
 * 文件名：<dataNamespace>.json；同名 .bak 保存上一份有效原文；同名 .lock 是
 * 进程级互斥锁，<name>.lock.guard 是“陈旧锁判定/删除/重取”的短命独占 guard。
 *
 * 锁协议（安全失败优先）：
 *  - 锁文件先在同目录临时文件里写完整内容并 fsync，再用 link(2) 原子出现在
 *    <name>.lock；正常路径下任何竞争者都不可能看到空/半写锁。
 *  - 锁内容无法识别（空/坏 JSON/namespace 不符）时**绝不自动删除**：
 *    新文件（<10s）视为“可能正在写入”，直接拒绝并提示稍后重试；更旧的视为
 *    崩溃残留，拒绝并告知手动删除路径。否则可能抢走存活实例的锁。
 *  - 只有“内容有效且可证明陈旧”（同主机 pid 已死；跨主机 mtime 超过 24h）的锁才
 *    允许接管，且必须在 .lock.guard 独占保护下重新读锁、再次确认陈旧、删除、
 *    再创建。guard 只会被创建它的实例主动释放；任何现存的 guard（包括 pid 已退出
 *    的陈旧 guard 或内容无法识别的 guard）都 fail-closed：绝不自动 rename/回收，
 *    以免 A/B 同时读到陈旧 guard 后互相搬走对方新建的 live guard（双 guard 竞态）。
 *    提示用户确认无实例后手动删除 guard 再重试——guard 只存活极短同步窗口，
 *    崩溃残留时安全拒绝比自动清理更安全。
 *  - 释放顺序：先关闭可能持有的 fd（Windows 允许删除的前提），再按 token 校验
 *    后 unlink；unlink 失败做有限重试并以 rename→unlink 兜底，失败信息写入
 *    storageNote，绝不静默吞掉。
 *
 * 写入顺序：同目录唯一临时文件 → fsync → rename；写前把上一份有效内容原子写成
 * <name>.bak。读取顺序：主文件 → .bak；两者都坏则抛 StorageError 并拒绝提供服务，
 * 绝不静默置空。本模块不做业务 schema 迁移（engine 的职责），只校验文档外壳。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

export const DOCUMENT_SCHEMA = 1;
export const DEFAULT_NAMESPACE = 'vocab_app_default';
export const NAMESPACE_PATTERN = /^[a-z][a-z0-9_]*$/;
export const LOCK_STALE_MS = 24 * 60 * 60 * 1000;
/** 竞争 guard 的最长等待时间（只等待“已确认存活”的竞争者自行释放）。 */
export const GUARD_WAIT_MS = 2000;
export const GUARD_RETRY_MS = 50;
/** 新出现但内容无法识别的锁/guard：在此窗口内只拒绝，绝不删除。 */
export const UNKNOWN_LOCK_GRACE_MS = 10 * 1000;
export const LOCK_VERSION = 1;

/** 记录无法安全加载/保存；调用方不得把它当作新用户空记录。 */
export class StorageError extends Error {
  constructor(message, code = 'failed') {
    super(message);
    this.name = 'StorageError';
    this.code = code;
  }
}

/** 同一 namespace 已被另一个实例持有（或锁状态无法安全判定）。 */
export class LockError extends StorageError {
  constructor(message) {
    super(message, 'conflict');
    this.name = 'LockError';
  }
}

/** 校验并返回 dataNamespace（默认 vocab_app_default）。 */
export function normalizeNamespace(value) {
  if (value === undefined || value === null || value === '') return DEFAULT_NAMESPACE;
  if (typeof value !== 'string' || !NAMESPACE_PATTERN.test(value)) {
    throw new StorageError(
      `dataNamespace 必须匹配 ^[a-z][a-z0-9_]*$（收到 ${JSON.stringify(value)}）`,
      'invalid',
    );
  }
  return value;
}

/**
 * 解析记录目录与文件名（不创建目录、不读文件）。
 * @param {{namespace?:string, env?:Record<string,string|undefined>, homeDir?:string}} [options]
 * @returns {{namespace:string, dir:string, filePath:string, backupPath:string,
 *   lockPath:string, guardPath:string, source:string}}
 */
export function resolveStorage(options = {}) {
  const namespace = normalizeNamespace(options.namespace);
  const env = options.env || process.env;
  let dir;
  let source;
  const override = typeof env.DSH_VOCAB_DATA_DIR === 'string' ? env.DSH_VOCAB_DATA_DIR.trim() : '';
  if (override) {
    dir = path.resolve(override);
    source = 'DSH_VOCAB_DATA_DIR';
  } else {
    const configuredHome = typeof env.DSH_HOME === 'string' ? env.DSH_HOME.trim() : '';
    let home;
    if (configuredHome) {
      home = path.resolve(configuredHome);
    } else if (options.homeDir) {
      home = path.resolve(options.homeDir);
    } else {
      home = path.join(os.homedir(), '.dsh');
    }
    dir = path.join(home, 'storages', 'dsh-vocab-app');
    source = 'DSH_HOME';
  }
  const filePath = path.join(dir, `${namespace}.json`);
  const lockPath = path.join(dir, `${namespace}.lock`);
  return {
    namespace,
    dir,
    filePath,
    backupPath: `${filePath}.bak`,
    lockPath,
    guardPath: `${lockPath}.guard`,
    source,
  };
}

/** 全新文档外壳。 */
export function emptyDocument(now = null) {
  return {
    schema: DOCUMENT_SCHEMA,
    revision: 0,
    updatedAt: now === null || now === undefined ? Math.floor(Date.now() / 1000) : now,
    progress: {},
    window: {},
  };
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

/** 同步短睡：取锁/接管都在启动路径，避免引入异步状态机。 */
function sleepSync(milliseconds) {
  const ms = Math.max(0, Number(milliseconds) || 0);
  try {
    const buffer = new Int32Array(new SharedArrayBuffer(4));
    Atomics.wait(buffer, 0, 0, ms);
  } catch {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      /* 极少数环境不支持 Atomics.wait，退化为短忙等 */
    }
  }
}

/** 文档外壳校验：不合格返回原因字符串，合格返回 null。 */
export function documentProblem(doc) {
  if (!isPlainObject(doc)) return '顶层必须是对象';
  if (doc.schema !== DOCUMENT_SCHEMA) {
    return `schema 必须为 ${DOCUMENT_SCHEMA}（收到 ${JSON.stringify(doc.schema)}）`;
  }
  if (!Number.isInteger(doc.revision) || doc.revision < 0) return 'revision 必须是非负整数';
  if (!isFiniteNumber(doc.updatedAt)) return 'updatedAt 必须是有限数字';
  if (!isPlainObject(doc.progress)) return 'progress 必须是对象';
  if (!isPlainObject(doc.window)) return 'window 必须是对象';
  return null;
}

class ReadResult {
  constructor(status, doc = null, raw = null, problem = null) {
    this.status = status; // 'ok' | 'missing' | 'invalid'
    this.doc = doc;
    this.raw = raw;
    this.problem = problem;
  }
}

/** 读取并解析一个 JSON 文档文件；区分缺失与损坏。 */
function readDocument(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath);
  } catch (error) {
    if (error && error.code === 'ENOENT') return new ReadResult('missing');
    return new ReadResult('invalid', null, null, `无法读取：${error.message || error}`);
  }
  let doc;
  try {
    const text = raw.toString('utf8').replace(/^\uFEFF/, '');
    doc = JSON.parse(text);
  } catch (error) {
    return new ReadResult('invalid', null, null, `不是有效 JSON：${error.message || error}`);
  }
  const problem = documentProblem(doc);
  if (problem) return new ReadResult('invalid', null, null, problem);
  return new ReadResult('ok', doc, raw);
}

function writeStageFile(target, bytes) {
  const dir = path.dirname(target);
  const temp = path.join(
    dir,
    `.${path.basename(target)}.tmp-${process.pid}-${crypto.randomBytes(6).toString('hex')}`,
  );
  let fd = null;
  try {
    fd = fs.openSync(temp, 'wx', 0o600);
    fs.writeFileSync(fd, bytes);
    fs.fsyncSync(fd);
  } catch (error) {
    try {
      if (fd !== null) fs.closeSync(fd);
    } catch {
      /* 关闭失败不影响原错误 */
    }
    fd = null;
    try {
      fs.unlinkSync(temp);
    } catch {
      /* 临时文件可能未建立 */
    }
    throw error;
  } finally {
    if (fd !== null) {
      try {
        fs.closeSync(fd);
      } catch {
        /* fsync 已成功，close 失败可忽略 */
      }
    }
  }
  return temp;
}

function replaceFile(source, target) {
  // 仅对短暂的 Windows 占用做有限重试；绝不退化成非原子覆写。
  let lastError = null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      fs.renameSync(source, target);
      return;
    } catch (error) {
      lastError = error;
      const busy = error && (
        error.code === 'EPERM' || error.code === 'EBUSY' || error.code === 'EACCES'
        || error.winerror === 5 || error.winerror === 32 || error.winerror === 33
      );
      if (!busy) throw error;
      sleepSync(20 * (attempt + 1));
    }
  }
  throw lastError;
}

function atomicWriteSync(target, bytes) {
  const stage = writeStageFile(target, bytes);
  try {
    replaceFile(stage, target);
  } catch (error) {
    try {
      fs.unlinkSync(stage);
    } catch {
      /* 保留 stage 也不影响恢复，这里尽力清理 */
    }
    throw error;
  }
}

function serializeDocument(doc, label = '状态文档') {
  let text;
  try {
    text = JSON.stringify(doc, null, 2);
  } catch (error) {
    throw new StorageError(`保存失败：${label}无法序列化为 JSON：${error.message || error}`);
  }
  if (typeof text !== 'string') throw new StorageError(`保存失败：${label}序列化结果为空`);
  return Buffer.from(`${text}\n`, 'utf8');
}

function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    // EPERM 表示进程存在但无权限发信号：仍视为存活。
    return Boolean(error && error.code === 'EPERM');
  }
}

function lockPayload(namespace, token) {
  return JSON.stringify({
    version: LOCK_VERSION,
    kind: 'lock',
    namespace,
    pid: process.pid,
    host: os.hostname(),
    token,
    createdAt: nowSeconds(),
  });
}

function guardPayload(namespace, token) {
  return JSON.stringify({
    version: LOCK_VERSION,
    kind: 'guard',
    namespace,
    pid: process.pid,
    host: os.hostname(),
    token,
    createdAt: nowSeconds(),
  });
}

/**
 * 读取并校验锁/guard 文件。
 * @returns {{exists:boolean, stat:object|null, data:object|null, problem:string|null}}
 */
function inspectLockFile(filePath, namespace, expectedKind = null) {
  let stat;
  try {
    stat = fs.statSync(filePath);
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return { exists: false, stat: null, data: null, problem: null };
    }
    return { exists: true, stat: null, data: null, problem: `stat 失败：${error.message || error}` };
  }
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf8');
  } catch (error) {
    return { exists: true, stat, data: null, problem: `读取失败：${error.message || error}` };
  }
  let data;
  try {
    data = JSON.parse(raw.replace(/^\uFEFF/, ''));
  } catch (error) {
    return { exists: true, stat, data: null, problem: '不是有效 JSON' };
  }
  if (!isPlainObject(data)
      || data.version !== LOCK_VERSION
      || data.namespace !== namespace
      || (expectedKind !== null && data.kind !== expectedKind)
      || !Number.isInteger(data.pid) || data.pid <= 0
      || typeof data.host !== 'string' || !data.host
      || typeof data.token !== 'string' || !data.token
      || !isFiniteNumber(data.createdAt)) {
    return { exists: true, stat, data: null, problem: '内容字段不完整或不属于本 namespace' };
  }
  return { exists: true, stat, data, problem: null };
}

/**
 * 原子创建“内容完整”的独占文件：临时文件写完 + fsync + link 到目标。
 * link 不支持的文件系统回退到 open('wx')+write（存在极短空窗；竞争者靠
 * “新鲜但不可识别 → 拒绝”来避免抢锁）。返回 'exists' 表示目标已存在。
 * @returns {'linked'|{mode:'fallback', fd:number}|'exists'}
 */
function createExclusiveFile(target, payload) {
  const dir = path.dirname(target);
  const token = crypto.randomBytes(6).toString('hex');
  const temp = path.join(dir, `.${path.basename(target)}.tmp-${process.pid}-${token}`);
  let tempReady = false;
  try {
    const fd = fs.openSync(temp, 'wx', 0o600);
    tempReady = true;
    try {
      fs.writeFileSync(fd, payload);
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    try {
      fs.linkSync(temp, target);
      return 'linked';
    } catch (error) {
      if (error && error.code === 'EEXIST') return 'exists';
      const unsupported = error && [
        'EPERM', 'ENOSYS', 'EXDEV', 'EACCES', 'ENOTSUP', 'EOPNOTSUPP', 'EINVAL',
      ].includes(error.code);
      if (!unsupported) throw error;
    }
  } finally {
    if (tempReady) {
      try {
        fs.unlinkSync(temp);
      } catch {
        /* 临时文件可能已被清理 */
      }
    }
  }
  // 回退路径：独占打开后立刻写入完整内容（只有崩溃才会留下空文件）。
  try {
    const fd = fs.openSync(target, 'wx', 0o600);
    try {
      fs.writeFileSync(fd, payload);
      fs.fsyncSync(fd);
    } catch (error) {
      try {
        fs.closeSync(fd);
      } catch {
        /* ignore */
      }
      try {
        fs.unlinkSync(target);
      } catch {
        /* ignore */
      }
      throw error;
    }
    return { mode: 'fallback', fd };
  } catch (error) {
    if (error && error.code === 'EEXIST') return 'exists';
    throw error;
  }
}

/**
 * 带重试地删除文件；unlink 失败时以 rename→unlink 兜底（Windows 上先关闭
 * fd 后一般可直接删除；rename 兜底处理短暂占用）。失败抛 LockError。
 */
function removeFileWithRetry(filePath, fault = null) {
  let lastError = null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      if (fault) fault('lock-unlink');
      fs.unlinkSync(filePath);
      return true;
    } catch (error) {
      if (error && error.code === 'ENOENT') return true;
      lastError = error;
      sleepSync(20 * (attempt + 1));
    }
  }
  // rename 兜底：让锁文件名重新可用；遗留 orphan 不影响互斥判定。
  const orphan = `${filePath}.orphan-${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
  try {
    fs.renameSync(filePath, orphan);
  } catch (error) {
    if (error && error.code === 'ENOENT') return true;
    throw new LockError(
      `无法安全删除锁文件 ${filePath}：${(lastError && lastError.message) || error.message || error}。`
      + '请确认没有其它背单词实例后手动删除。',
    );
  }
  try {
    fs.unlinkSync(orphan);
  } catch {
    /* orphan 不参与互斥，删除失败可忽略 */
  }
  return true;
}

const ownedLocks = new Set();

process.once('exit', () => {
  for (const store of Array.from(ownedLocks)) {
    try {
      store.releaseLock();
    } catch {
      /* 进程退出阶段尽力而为 */
    }
  }
});

/** 单 namespace 状态存储。构造请使用 Store.open（同时加载文档并取锁）。 */
export class Store {
  constructor(paths, doc, raw, notes) {
    this.namespace = paths.namespace;
    this.dir = paths.dir;
    this.filePath = paths.filePath;
    this.backupPath = paths.backupPath;
    this.lockPath = paths.lockPath;
    this.guardPath = paths.guardPath;
    this.source = paths.source;
    this.doc = doc;
    this.raw = raw;
    this.notes = notes;
    this.lockToken = null;
    this.lockFd = null;
    this.closed = false;
    /** 竞争 guard 的最长等待（测试可缩短）。 */
    this.guardWaitMs = GUARD_WAIT_MS;
    /** 测试注入：fault(stage) 抛错即模拟该阶段失败。 */
    this.fault = null;
  }

  /**
   * 打开（或首次创建）状态文档。
   * @param {{namespace?:string, env?:object, homeDir?:string, guardWaitMs?:number}} [options]
   * @returns {Store}
   */
  static open(options = {}) {
    const paths = resolveStorage(options);
    try {
      fs.mkdirSync(paths.dir, { recursive: true });
    } catch (error) {
      throw new StorageError(`无法创建记录目录 ${paths.dir}：${error.message || error}`);
    }
    const store = new Store(paths, emptyDocument(), null, []);
    if (Number.isFinite(options.guardWaitMs) && options.guardWaitMs >= 0) {
      store.guardWaitMs = Number(options.guardWaitMs);
    }
    store.acquireLock();
    try {
      store.load();
    } catch (error) {
      store.releaseLock();
      throw error;
    }
    return store;
  }

  get revision() {
    return this.doc.revision;
  }

  get storageNote() {
    return this.notes.join('\n');
  }

  /** 锁持有者状态：'alive' 不可清理；'stale' 可证明陈旧；'unknown-*' 拒绝清理。 */
  _ownerState(info) {
    if (!info.exists) return 'missing';
    if (!info.data || info.problem) {
      const age = info.stat ? Date.now() - info.stat.mtimeMs : 0;
      return age < UNKNOWN_LOCK_GRACE_MS ? 'unknown-fresh' : 'unknown-old';
    }
    if (info.data.host === os.hostname()) {
      return processAlive(info.data.pid) ? 'alive' : 'stale';
    }
    const age = info.stat ? Date.now() - info.stat.mtimeMs : 0;
    return age > LOCK_STALE_MS ? 'stale' : 'alive';
  }

  _describeOwner(info) {
    if (!info || !info.data) return '未知持有者';
    return `pid=${info.data.pid} host=${info.data.host}`;
  }

  acquireLock() {
    const token = crypto.randomBytes(16).toString('hex');
    const payload = lockPayload(this.namespace, token);
    for (let attempt = 0; attempt < 4; attempt += 1) {
      let created;
      try {
        created = createExclusiveFile(this.lockPath, payload);
      } catch (error) {
        throw new LockError(`无法创建记录锁 ${this.lockPath}：${error.message || error}`);
      }
      if (created !== 'exists') {
        this.lockToken = token;
        this.lockFd = created && created.mode === 'fallback' ? created.fd : null;
        ownedLocks.add(this);
        return;
      }
      const info = inspectLockFile(this.lockPath, this.namespace, 'lock');
      const state = this._ownerState(info);
      if (state === 'missing') continue; // 竞争者刚释放，重试创建
      if (state === 'alive') {
        throw new LockError(
          `记录目录已被另一个背单词实例占用（${this._describeOwner(info)}）：${this.lockPath}。`
          + '同一 dataNamespace 同时只允许一个实例持有。',
        );
      }
      if (state === 'unknown-fresh') {
        throw new LockError(
          `记录锁正在建立或内容尚未写完：${this.lockPath}。`
          + '为避免抢走其它实例的锁，本次启动已拒绝；请稍后重试。',
        );
      }
      if (state === 'unknown-old') {
        throw new LockError(
          `记录锁内容无法识别：${this.lockPath}（${info.problem || '未知原因'}）。`
          + '可能仍有实例存活或上一实例异常退出；出于安全考虑不会自动清理。'
          + '请确认没有其它背单词实例后，手动删除该锁文件再启动。',
        );
      }
      // 可证明陈旧：在短命 guard 保护下重新判定并清理，然后重试创建。
      this._takeoverStaleLock();
    }
    throw new LockError(`无法获取记录锁 ${this.lockPath}，请稍后重试。`);
  }

  /** 独占短命 guard 下完成“重新判定陈旧 → 删除 → 由调用方重取”。 */
  _takeoverStaleLock() {
    const guard = this._acquireGuard();
    try {
      const info = inspectLockFile(this.lockPath, this.namespace, 'lock');
      const state = this._ownerState(info);
      if (state === 'missing') return; // 已被其它实例清理/释放
      if (state !== 'stale') {
        throw new LockError(
          `记录锁在接管期间仍被持有或状态不明（${this._describeOwner(info)}）：${this.lockPath}。`
          + '出于安全考虑已停止接管；请稍后重试。',
        );
      }
      removeFileWithRetry(this.lockPath, this.fault);
    } finally {
      this._releaseGuard(guard);
    }
  }

  _acquireGuard() {
    const token = crypto.randomBytes(16).toString('hex');
    const payload = guardPayload(this.namespace, token);
    const deadline = Date.now() + this.guardWaitMs;
    for (;;) {
      let created;
      try {
        created = createExclusiveFile(this.guardPath, payload);
      } catch (error) {
        throw new LockError(`无法创建锁接管 guard ${this.guardPath}：${error.message || error}`);
      }
      if (created !== 'exists') {
        return {
          path: this.guardPath,
          token,
          fd: created && created.mode === 'fallback' ? created.fd : null,
        };
      }
      const info = inspectLockFile(this.guardPath, this.namespace, 'guard');
      if (!info.exists) continue; // 竞争者刚释放，重试创建
      const holderAlive = Boolean(
        info.data && info.data.host === os.hostname() && processAlive(info.data.pid),
      );
      if (holderAlive) {
        // 正常竞争者正在极短时间内完成接管：只短暂等待，绝不清理其 guard。
        if (Date.now() >= deadline) {
          throw new LockError(
            `另一个背单词实例正在接管记录锁（${this._describeOwner(info)}）：${this.guardPath}。`
            + '请稍后重试。',
          );
        }
        sleepSync(GUARD_RETRY_MS);
        continue;
      }
      // 任何无法确认“持有者仍存活且会自行释放”的 guard（pid 已退出、跨主机、
      // 空/坏内容）一律 fail-closed：不 rename、不删除、不回收，避免 A/B 同时
      // 读到陈旧 guard 后互相搬走对方新建的 live guard 形成双 guard 竞态。
      throw new LockError(
        `锁接管 guard 已存在且无法确认其持有者仍在运行：${this.guardPath}`
        + (info.data ? `（${this._describeOwner(info)}）` : `（${info.problem || '内容无法识别'}）`)
        + '。为安全起见不会自动清理 guard；请确认没有其它背单词实例后，'
        + '手动删除该 guard 文件再重试。',
      );
    }
  }

  _releaseGuard(guard) {
    if (!guard) return;
    if (guard.fd !== null && guard.fd !== undefined) {
      try {
        fs.closeSync(guard.fd);
      } catch {
        /* ignore */
      }
      guard.fd = null;
    }
    const info = inspectLockFile(guard.path, this.namespace, 'guard');
    if (!info.exists) return;
    if (info.data && info.data.token === guard.token) {
      try {
        removeFileWithRetry(guard.path, this.fault);
      } catch (error) {
        this.notes.push(`锁接管 guard 未能清理：${error.message || error}`);
      }
    }
  }

  releaseLock() {
    if (this.lockToken !== null) {
      // 先关闭 fd：Windows 上“打开中的文件”常被拒绝删除。
      if (this.lockFd !== null) {
        try {
          fs.closeSync(this.lockFd);
        } catch {
          /* close 失败仍继续尝试删除 */
        }
        this.lockFd = null;
      }
      const info = inspectLockFile(this.lockPath, this.namespace, 'lock');
      if (info.exists) {
        if (info.data && info.data.token === this.lockToken) {
          try {
            removeFileWithRetry(this.lockPath, this.fault);
          } catch (error) {
            this.notes.push(`记录锁未能清理：${error.message || error}`);
          }
        } else if (info.problem) {
          this.notes.push(
            `记录锁内容异常，未自动清理：${this.lockPath}（${info.problem}）。`,
          );
        }
      }
      this.lockToken = null;
    } else if (this.lockFd !== null) {
      try {
        fs.closeSync(this.lockFd);
      } catch {
        /* ignore */
      }
      this.lockFd = null;
    }
    ownedLocks.delete(this);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.releaseLock();
  }

  load() {
    const main = readDocument(this.filePath);
    const backup = readDocument(this.backupPath);
    if (main.status === 'ok') {
      this.doc = main.doc;
      this.raw = main.raw;
      return;
    }
    if (backup.status === 'ok') {
      const restored = documentProblem(backup.doc) === null ? backup.doc : null;
      if (restored === null) throw new StorageError(`无法恢复 ${this.filePath}：备份文档外壳无效`);
      restoreFromBackup(this, restored);
      this.notes.push(
        `主记录${main.status === 'missing' ? '缺失' : '损坏'}，已从 ${this.backupPath} 恢复；`
        + '备份保留，原主文件未被截断。',
      );
      return;
    }
    const bothMissing = main.status === 'missing' && backup.status === 'missing';
    if (bothMissing) {
      this.doc = emptyDocument();
      this.raw = null;
      return;
    }
    const problems = [];
    if (main.status === 'invalid') problems.push(`${this.filePath}：${main.problem}`);
    if (backup.status === 'invalid') problems.push(`${this.backupPath}：${backup.problem}`);
    throw new StorageError(
      `无法加载 ${this.filePath}：没有可恢复的有效 JSON；记录未清空、原文件未改写。`
      + (problems.length ? `（${problems.join('；')}）` : ''),
    );
  }

  /**
   * 原子提交新文档（调用方负责先递增 revision/updatedAt）。
   * 失败抛 StorageError，且内存中的 doc/raw 保持原值（不推进 revision）。
   * @param {object} doc
   */
  save(doc) {
    if (this.closed) throw new StorageError('记录存储已关闭');
    if (doc !== this.doc) {
      const problem = documentProblem(doc);
      if (problem) throw new StorageError(`保存失败：状态文档外壳无效（${problem}）`);
    }
    const nextRaw = serializeDocument(doc);
    try {
      if (this.fault) this.fault('serialize');
      if (this.raw !== null) {
        if (this.fault) this.fault('backup');
        atomicWriteSync(this.backupPath, this.raw);
      }
      if (this.fault) this.fault('write');
      atomicWriteSync(this.filePath, nextRaw);
      if (this.fault) this.fault('rename');
    } catch (error) {
      if (error instanceof StorageError) throw error;
      throw new StorageError(`无法原子保存 ${this.filePath}：${error.message || error}（未使用非原子覆写）`);
    }
    this.doc = doc;
    this.raw = nextRaw;
    return doc;
  }
}

function restoreFromBackup(store, doc) {
  let bytes;
  try {
    bytes = serializeDocument(doc, '备份文档');
    atomicWriteSync(store.filePath, bytes);
  } catch (error) {
    throw new StorageError(
      `无法从备份恢复 ${store.filePath}：${error.message || error}（备份未改写）`,
    );
  }
  store.doc = doc;
  // 恢复后的主文件就是这份规范序列化字节；.bak 仍保留原备份原文。
  store.raw = bytes;
}

export default {
  Store,
  StorageError,
  LockError,
  resolveStorage,
  normalizeNamespace,
  emptyDocument,
  LOCK_STALE_MS,
  GUARD_WAIT_MS,
  UNKNOWN_LOCK_GRACE_MS,
};
