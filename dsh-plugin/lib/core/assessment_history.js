/**
 * V1.4.2 历史边界（移植 app/assessment_history.py）：保留旧证据，绝不重算。
 *
 * 本模块无文件系统/Qt 副作用；归档由调用方在既有的 answer/session/history
 * 原子保存事务内完成。
 */
import { isDeepStrictEqual } from 'node:util';

export const ALGORITHM = 'vst-cat-v143-web';
/** 桌面版算法标识（仅用于读取/区分旧归档，不写入新记录）。 */
export const DESKTOP_ALGORITHM = 'vst-cat-v142';
export const UNIT = 'frequency_ranked_entries';
export const MEASUREMENT_SCHEMA = 3;

function isPlainObject(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** Python dict == dict 语义（深层值相等；用于归档去重）。 */
function pyEquals(left, right) {
  return isDeepStrictEqual(left, right);
}

function deepCopy(value) {
  return structuredClone(value);
}

export function isCurrent(record) {
  return isPlainObject(record) && record.algo === ALGORITHM
    && record.measurement_schema === MEASUREMENT_SCHEMA
    && record.unit === UNIT;
}

/** Python 属性名别名。 */
export const is_current = isCurrent;

/** 不同的题库/单位/测量模型就是不同量纲。 */
export function seriesKey(record) {
  const source = isPlainObject(record) ? record : {};
  return [
    source.algo === undefined ? 'legacy' : source.algo,
    source.bank_id === undefined ? 'legacy' : source.bank_id,
    source.unit === undefined ? 'legacy' : source.unit,
    source.measurement_schema === undefined ? 0 : source.measurement_schema,
  ];
}

export const series_key = seriesKey;

function seriesKeyEquals(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

export function plottable(record) {
  if (!isPlainObject(record) || record.estimate_available === false) return false;
  for (const key of ['ts', 'vocab']) {
    const value = record[key];
    if (typeof value === 'boolean' || typeof value !== 'number' || !Number.isFinite(value)) {
      return false;
    }
  }
  // 部分作答的新测试不算完成测量的趋势。
  return !isCurrent(record)
    || (record.completed === true && record.estimate_available === true);
}

export function comparable(history, reference) {
  const key = seriesKey(reference);
  return history.filter((row) => seriesKeyEquals(seriesKey(row), key) && plottable(row));
}

export const current_trend = (history, bankId) => currentTrend(history, bankId);

export function currentTrend(history, bankId) {
  return history.filter(
    (row) => isCurrent(row) && row.bank_id === bankId && plottable(row),
  );
}

/**
 * 保留精确旧快照，而不是新算的 legacy 分数；不编辑任何已有 history/session。
 * 调用方在本函数成功后替换 quiz_session；保存失败时回滚。
 * @param {Record<string, unknown>} progress 原地修改
 * @param {number} timestamp
 * @param {string} reason
 */
export function archiveSession(progress, timestamp, reason) {
  if (!isPlainObject(progress)) throw new TypeError('archiveSession 需要 progress 对象');
  const session = progress.quiz_session;
  if (session === null || session === undefined) return null;
  const archives = progress.quiz_archives === undefined ? [] : progress.quiz_archives;
  if (!Array.isArray(archives)) {
    throw new Error('quiz_archives must be a list; existing data was retained');
  }
  if (archives.some((row) => isPlainObject(row) && pyEquals(row.session, session))) {
    return null;
  }
  if (!('quiz_archives' in progress)) progress.quiz_archives = archives;
  archives.push({ archived_at: timestamp, reason, session: deepCopy(session) });
  return null;
}

export const archive_session = archiveSession;

export default {
  ALGORITHM,
  UNIT,
  MEASUREMENT_SCHEMA,
  isCurrent,
  seriesKey,
  plottable,
  comparable,
  currentTrend,
  archiveSession,
};
