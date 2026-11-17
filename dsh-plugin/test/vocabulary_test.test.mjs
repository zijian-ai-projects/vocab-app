/**
 * `lib/core/vocabulary_test.js` 的差分测试。
 *
 * 基线由 `test/fixtures/gen_cat_fixtures.py` 用本机 Python 3.8.3 生成
 * （`app/vocabulary_test.py` 为权威实现）。比对策略：
 * - 词表/题库结构：size/bands/excluded_count/testable_size/identity.sources/
 *   每词干扰项池 全部与 Python 逐项比对；identity 只把 algorithm 归一为 Python
 *   版本后深比较（JS 版 ALGORITHM 按 CONTRACT 为 `vst-cat-v143-web`）。
 * - trace：Python 固定种子/答案序列产出 items+responses；JS 复用这些记录
 *   （逐条经 JS 自己的 validateRecord 校验）逐步比对 band/phase/stop_reason/
 *   theta/se/estimate/区间/全部 summary 字段。JS 选中的 item key 不要求相同
 *   （PRNG 不同），但 JS 自己的选题也断言 band/phase、选项结构与合法性。
 * - 唯一跨语言归一：`irt.b`。Python `math.log`（MSVC libm）与 JS `Math.log`
 *   （V8 fdlibm）在约 5% 的 rank 上差 1 ulp，因此复用 Python 记录时用 JS 题库
 *   重算的 a/b/c 覆盖记录里的 irt（record 的其它字段一律原样校验）。
 *
 * 运行（工作目录 dsh-plugin）：
 *   node --test test/vocabulary_test.test.mjs
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import * as vt from '../lib/core/vocabulary_test.js';

const FIXTURE_DIR = join(dirname(fileURLToPath(import.meta.url)), 'fixtures');

function loadFixture(name) {
  return JSON.parse(readFileSync(join(FIXTURE_DIR, name), 'utf8'));
}

const wordsFixture = loadFixture('cat-words.json');
const bankFixture = loadFixture('cat-bank.json');
const traceFixture = loadFixture('cat-trace.json');
const entriesFixture = loadFixture('cat-entries.json');
const primitivesFixture = loadFixture('cat-primitives.json');

const WORD_BANKS = wordsFixture.banks;
const TRACE_SCENARIOS = traceFixture.scenarios;

const RELATIVE_TOLERANCE = 1e-10;

const bankCache = new Map();

/** 固定词表 → 题库（单次进程内复用；同一词表必然同 fingerprint）。 */
function getBank(name) {
  if (!bankCache.has(name)) bankCache.set(name, new vt.FrequencyBank(WORD_BANKS[name]));
  return bankCache.get(name);
}

/** 浮点相对 1e-10；其它类型深比较。 */
function assertClose(actual, expected, label) {
  if (expected === null || typeof expected === 'string' || typeof expected === 'boolean') {
    assert.deepEqual(actual, expected, `${label}: ${String(actual)} != ${String(expected)}`);
    return;
  }
  if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', `${label}: expected number, got ${typeof actual}`);
    if (Number.isNaN(expected)) {
      assert.ok(Number.isNaN(actual), `${label}: expected NaN, got ${actual}`);
      return;
    }
    assert.ok(Number.isFinite(actual), `${label}: expected finite, got ${actual}`);
    const tolerance = RELATIVE_TOLERANCE * Math.max(1, Math.abs(expected), Math.abs(actual));
    assert.ok(Math.abs(actual - expected) <= tolerance,
      `${label}: ${actual} != ${expected} (diff ${Math.abs(actual - expected)}, tol ${tolerance})`);
    return;
  }
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${label}: expected array`);
    assert.equal(actual.length, expected.length, `${label}: length`);
    expected.forEach((value, index) => assertClose(actual[index], value, `${label}[${index}]`));
    return;
  }
  assert.ok(actual !== null && typeof actual === 'object', `${label}: expected object`);
  for (const key of Object.keys(expected)) {
    assertClose(actual[key], expected[key], `${label}.${key}`);
  }
}

/** 只取 fixture 里保存的 compact summary 字段（label/size 等常量不重复比对）。 */
function compactSummary(summary) {
  return {
    theta: summary.theta,
    se: summary.se,
    estimate: summary.estimate,
    low: summary.low,
    high: summary.high,
    answered: summary.answered,
    correct_count: summary.correct_count,
    dontknow: summary.dontknow,
    estimate_available: summary.estimate_available,
    provisional: summary.provisional,
    coverage: summary.coverage,
    survey_coverage: summary.survey_coverage,
    stop_reason: summary.stop_reason,
    boundary: summary.boundary,
    theta_low: summary.theta_low,
    theta_high: summary.theta_high,
    bands: summary.bands.map((band) => ({
      id: band.id,
      answered: band.answered,
      correct: band.correct,
      unknown: band.unknown,
      estimate: band.estimate,
      low: band.low,
      high: band.high,
      p_known: band.p_known,
    })),
  };
}

function assertSummary(bank, summary, expected, constants, label) {
  assertClose(compactSummary(summary), expected, `${label}.summary`);
  assert.equal(summary.unit, constants.unit, `${label}: unit`);
  assert.equal(summary.interval_level, constants.interval_level, `${label}: interval_level`);
  assert.equal(summary.measurement_schema, constants.measurement_schema, `${label}: schema`);
  assert.equal(summary.coverage_target, constants.coverage_target, `${label}: coverage_target`);
  assert.equal(summary.population_size, constants.population_size, `${label}: population_size`);
  assert.equal(summary.testable_size, constants.testable_size, `${label}: testable_size`);
  assert.equal(summary.untestable_count, constants.untestable_count, `${label}: untestable_count`);
  assert.equal(summary.algo, vt.ALGORITHM, `${label}: algo`);
  assert.equal(summary.bank_id, bank.fingerprint, `${label}: bank_id`);
  assert.equal(summary.bands.length, constants.coverage_target, `${label}: band count`);
  assert.equal(summary.model_only, true, `${label}: model_only`);
  assert.equal(summary.evidence_limited, summary.provisional, `${label}: evidence_limited`);
}

/**
 * 复用 Python 记录时唯一的归一：用 JS 题库重算的 irt 覆盖记录里的 irt。
 * 原因见文件头（libm log 末位差异）。其余字段保持原样交给 validateRecord 校验。
 */
function normalizeIrt(record, bank) {
  const source = Object.prototype.hasOwnProperty.call(bank.items, record.key) ? bank.items[record.key] : undefined;
  assert.ok(source, `fixture record key ${record.key} must exist in the JS bank`);
  return { ...record, irt: { a: source.a, b: source.b, c: source.c } };
}

/** 断言 nextItem 产出的 record 结构与 bank 一致（另用 summarize 触发完整 validateRecord）。 */
function assertRecordInvariants(bank, record, askedKeys, label) {
  const source = bank.items[record.key];
  assert.ok(source, `${label}: key must be in bank`);
  assert.equal(record.band, source.band, `${label}: band`);
  assert.equal(record.rank, source.rank, `${label}: rank`);
  assert.ok(record.phase === 'survey' || record.phase === 'adaptive', `${label}: phase`);
  assert.ok(!askedKeys.includes(record.key), `${label}: item must be unasked`);
  assert.ok(bank._testableByBand.get(record.band).includes(record.key), `${label}: must be testable`);
  assert.deepEqual(record.irt, { a: source.a, b: source.b, c: source.c }, `${label}: irt`);
  const item = record.item;
  assert.equal(item.item_id, record.key, `${label}: item_id`);
  assert.equal(item.word, source.word, `${label}: word`);
  assert.equal(item.options.length, 4, `${label}: four options`);
  const ids = item.options.map((option) => option.item_id);
  assert.equal(new Set(ids).size, ids.length, `${label}: option ids unique`);
  assert.equal(ids.filter((id) => id === record.key).length, 1, `${label}: exactly one target`);
  assert.equal(ids[item.correct_index], record.key, `${label}: correct slot is target`);
  assert.equal(item.correct_key, 'ABCD'[item.correct_index], `${label}: correct_key`);
  item.options.forEach((option, index) => {
    assert.equal(option.key, 'ABCD'[index], `${label}: slot ${index}`);
    assert.equal(option.text, bank.items[option.item_id].sense, `${label}: option text`);
  });
  for (let left = 0; left < ids.length; left += 1) {
    for (let right = left + 1; right < ids.length; right += 1) {
      assert.ok(bank._compatible(ids[left], ids[right]), `${label}: options must be compatible`);
    }
  }
  // 走一遍完整 validateHistory（record rank/band/phase/irt/选项文本/歧义规则）。
  assert.doesNotThrow(() => vt.summarize(bank, [record], [1]), `${label}: record must validate`);
}

/** 按 app/main.py 顺序造 session（pending 或 answered）。 */
function buildSession(bank, seed, items, responses, pending, extra = {}) {
  const answered = responses.length;
  const recordCount = pending ? answered + 1 : answered;
  const prefixRecords = items.slice(0, recordCount);
  const summary = vt.summarize(bank, prefixRecords, responses);
  const state = {
    seed,
    asked: prefixRecords.map((record) => record.key),
    theta: summary.theta,
    se: summary.se,
  };
  const index = pending ? answered : answered - 1;
  return {
    schema: vt.SESSION_SCHEMA,
    algo: vt.ALGORITHM,
    id: 'session-' + seed + '-' + answered,
    bank_id: bank.fingerprint,
    started_at: 1700000000.5,
    updated_at: 1700000123,
    from_welcome: false,
    state,
    items: prefixRecords,
    resp: responses.slice(),
    i: index,
    history_id: 'session-' + seed + '-' + answered,
    history_response_count: answered,
    ...extra,
  };
}

/** JS 自己跑一条课程：按确定性规则作答；返回 items/responses/state。 */
function simulateJs(bank, seed, answerRule, maxItems = vt.MAX_ITEMS) {
  const state = vt.newState(seed);
  const items = [];
  const responses = [];
  for (;;) {
    const record = vt.nextItem(bank, state, items, responses);
    if (record === null) break;
    items.push(record);
    state.asked.push(record.key);
    const response = answerRule(record, responses.length);
    responses.push(response);
    const summary = vt.summarize(bank, items, responses);
    state.theta = summary.theta;
    state.se = summary.se;
    if (items.length >= maxItems) break;
  }
  return { state, items, responses };
}

function keyRule(record) {
  let sum = 0;
  for (const char of record.key) sum += char.codePointAt(0);
  return sum % 3 === 0 ? 0 : (sum % 7 === 0 ? -1 : 1);
}

// ---------------------------------------------------------------------------
// 常量 / 数学原语
// ---------------------------------------------------------------------------

describe('constants', () => {
  test('契约常量与 Python 同值', () => {
    assert.equal(vt.ALGORITHM, 'vst-cat-v143-web');
    assert.equal(vt.SESSION_SCHEMA, 2);
    assert.equal(vt.MEASUREMENT_SCHEMA, 3);
    assert.equal(vt.BAND_SIZE, 1000);
    assert.equal(vt.MAX_WORDS, 20000);
    assert.equal(vt.MIN_ITEMS, 40);
    assert.equal(vt.MAX_ITEMS, 80);
    assert.equal(vt.MIN_PER_BAND, 2);
    assert.equal(vt.TARGET_SE, 0.30);
    assert.equal(vt.A, 1.4);
    assert.equal(vt.C, 0.25);
    assert.equal(vt.PRIOR_MEAN, 0.0);
    assert.equal(vt.PRIOR_SD, 2.0);
    assert.equal(vt.THETA_MIN, -5.0);
    assert.equal(vt.THETA_MAX, 7.0);
    assert.equal(vt.THETA_STEP, 0.05);
    assert.equal(vt.INTERVAL_LEVEL, 0.95);
    assert.equal(vt.UNIT, 'frequency_ranked_entries');
  });

  test('THETA_GRID 为 241 点 -5..7 step 0.05', () => {
    assert.equal(vt.THETA_GRID.length, 241);
    assert.equal(vt.THETA_GRID[0], -5.0);
    assert.equal(vt.THETA_GRID[240], 7.0);
    const expected = Array.from({ length: 241 }, (_, index) => (index - 100) / 20.0);
    assert.deepEqual([...vt.THETA_GRID], expected);
  });
});

describe('math primitives', () => {
  const ranks = primitivesFixture.ranks;
  const thetas = primitivesFixture.thetas;

  test('difficulty 与 Python 一致（相对 1e-10）', () => {
    ranks.forEach((rank, index) => {
      assertClose(vt.difficulty(rank), primitivesFixture.difficulty[index], `difficulty(${rank})`);
    });
  });

  test('pKnown / pCorrect / fisherInformation 与 Python 一致', () => {
    thetas.forEach((theta, thetaIndex) => {
      ranks.forEach((rank, rankIndex) => {
        const b = vt.difficulty(rank);
        assertClose(vt.pKnown(theta, b), primitivesFixture.p_known[thetaIndex][rankIndex],
          `pKnown(${theta}, rank=${rank})`);
        assertClose(vt.pCorrect(theta, b), primitivesFixture.p_correct[thetaIndex][rankIndex],
          `pCorrect(${theta}, rank=${rank})`);
        assertClose(vt.fisherInformation(theta, b),
          primitivesFixture.fisher_information[thetaIndex][rankIndex],
          `fisherInformation(${theta}, rank=${rank})`);
      });
    });
  });

  test('difficulty 拒绝非整数/越界', () => {
    for (const value of [0, 20001, 1.5, -1, '1', null, true, NaN, Infinity]) {
      assert.throws(() => vt.difficulty(value), /rank must be an integer between 1 and MAX_WORDS/);
    }
  });

  test('pKnown 拒绝非有限数字（含 bool）', () => {
    for (const value of ['0', null, true, NaN, Infinity, undefined]) {
      assert.throws(() => vt.pKnown(value, 0), /theta must be a finite number, not bool/);
      assert.throws(() => vt.pKnown(0, value), /b must be a finite number, not bool/);
    }
  });

  test('pyRound 为 Python 银行家舍入', () => {
    primitivesFixture.round_values.forEach((value, index) => {
      const actual = vt.pyRound(value);
      const expected = primitivesFixture.round_expected[index];
      assert.ok(actual === expected, `pyRound(${value}) = ${actual}, expected ${expected}`);
      assert.equal(Number.isInteger(actual), true, `pyRound(${value}) must be integer`);
    });
  });
});

// ---------------------------------------------------------------------------
// 题库结构（内容策略 / 干扰项池 / identity）
// ---------------------------------------------------------------------------

function assertBankAgainstFixture(name) {
  const bank = getBank(name);
  const expected = bankFixture[name];
  assert.equal(bank.size, expected.size, `${name}.size`);
  assert.equal(bank.excluded_count, expected.excluded_count, `${name}.excluded_count`);
  assert.equal(bank.testable_size, expected.testable_size, `${name}.testable_size`);
  assert.equal(bank.untestable_count, expected.untestable_count, `${name}.untestable_count`);
  assert.deepEqual(bank.bands, expected.bands, `${name}.bands`);
  assert.deepEqual(
    Object.keys(bank.items),
    expected.identity.sources.map((row) => row[0]),
    `${name}.item order must match Python sources order`,
  );
  assert.deepEqual(bank.identity.testable, expected.testable, `${name}.testable`);
  // identity：除 algorithm（版本域分隔）外必须与 Python 完全同构。
  assert.deepEqual(
    { ...bank.identity, algorithm: expected.identity.algorithm },
    expected.identity,
    `${name}.identity`,
  );
  // 每个词的干扰项池顺序也与 Python 一致（含贪心/精确回退结果）。
  const pools = Object.fromEntries(
    Object.keys(bank.items).map((key) => [key, bank._distractors.get(key)]),
  );
  assert.deepEqual(pools, expected.pools, `${name}.pools`);
  const bandTestable = Object.fromEntries(
    [...bank._testableByBand].map(([band, keys]) => [String(band), keys.length]),
  );
  assert.deepEqual(bandTestable, expected.band_testable, `${name}.band_testable`);
  // 指纹：SHOULD 与 Python 不同（ALGORITHM/规范序列化不同），但必须是稳定 sha256。
  assert.match(bank.fingerprint, /^[0-9a-f]{64}$/);
  assert.notEqual(bank.fingerprint, expected.fingerprint_py);
  return bank;
}

describe('FrequencyBank', () => {
  test('main 词表：size/bands/sources/identity/干扰项池与 Python 逐项一致', () => {
    assertBankAgainstFixture('main');
  });

  test('small 词表：单层 20 条全部可测', () => {
    const bank = assertBankAgainstFixture('small');
    assert.equal(bank.bands.length, 1);
    assert.equal(bank.size, 20);
    assert.equal(bank.testable_size, 20);
  });

  test('conflict 词表：精确回退（贪心失败→三元组）结果与 Python 一致', () => {
    const bank = assertBankAgainstFixture('conflict');
    const expected = bankFixture.conflict;
    assert.ok(expected.fallback_calls_py > 0, 'fixture 必须来自真实触发回退的 Python 词表');
    assert.equal(bank.untestable_count, 1);
    const target = Object.keys(bank.items)[0];
    assert.deepEqual(bank._distractors.get(target), ['zqbooks', 'zqjia', 'zqyi']);
  });

  test('构造第二份题库：同词表 fingerprint 稳定一致', () => {
    const first = getBank('main');
    const second = new vt.FrequencyBank(WORD_BANKS.main);
    assert.equal(second.fingerprint, first.fingerprint);
    assert.equal(second.size, first.size);
    assert.deepEqual(Object.keys(second.items), Object.keys(first.items));
  });

  test('不同词表得到不同 fingerprint', () => {
    const left = new vt.FrequencyBank([{ w: 'alpha', frq: 1, s: '甲', pos: ['n'] }]);
    const right = new vt.FrequencyBank([{ w: 'alpha', frq: 1, s: '乙', pos: ['n'] }]);
    assert.notEqual(left.fingerprint, right.fingerprint);
  });
});

// ---------------------------------------------------------------------------
// 内容策略边界词条
// ---------------------------------------------------------------------------

describe('content policy entries', () => {
  test('保留/排除集合、sources 顺序与干扰项池与 Python 一致', () => {
    const bank = new vt.FrequencyBank(entriesFixture.rows);
    const expected = entriesFixture.expected;
    assert.equal(bank.size, expected.size);
    assert.equal(bank.excluded_count, expected.excluded_count);
    assert.deepEqual(bank.bands, expected.bands);
    assert.equal(bank.testable_size, expected.testable_size);
    assert.equal(bank.untestable_count, expected.untestable_count);
    assert.deepEqual(bank.identity.sources, expected.sources);
    assert.deepEqual(bank.identity.testable, expected.testable);
    const pools = Object.fromEntries(
      Object.keys(bank.items).map((key) => [key, bank._distractors.get(key)]),
    );
    assert.deepEqual(pools, expected.pools);
  });

  test('非 JSON 可表示的非法值同样被排除', () => {
    const rows = [
      { w: 'okword', frq: 1, s: '词', pos: ['n'] },
      { w: 'nanfrq', frq: NaN, s: '词', pos: ['n'] },
      { w: 'inffrq', frq: Infinity, s: '词', pos: ['n'] },
      { w: 'boolfrq', frq: true, s: '词', pos: ['n'] },
      { w: 'zero', frq: 0, s: '词', pos: ['n'] },
      { w: 'negzero', frq: -0.0, s: '词', pos: ['n'] },
      { w: 'boolpos', frq: 2, s: '词', pos: [true] },
      { w: null, frq: 3, s: '词', pos: ['n'] },
      null,
      42,
    ];
    const bank = new vt.FrequencyBank(rows);
    assert.equal(bank.size, 1);
    assert.equal(bank.items.okword.sense, '词');
  });

  test('words 参数校验与进度回调', () => {
    assert.throws(() => new vt.FrequencyBank('not words'), /words must be an iterable of entry dictionaries/);
    assert.throws(() => new vt.FrequencyBank({ a: 1 }), /words must be iterable/);
    assert.throws(() => new vt.FrequencyBank([], 5), /progress must be callable or None/);
    const progress = [];
    const bank = new vt.FrequencyBank(
      [{ w: 'alpha', frq: 1, s: '甲', pos: ['n'] }],
      (value) => progress.push(value),
    );
    assert.equal(progress[0], 0);
    assert.equal(progress[progress.length - 1], 100);
    assert.ok(progress.every((value) => Number.isInteger(value) && value >= 0 && value <= 100));
    for (let index = 1; index < progress.length; index += 1) {
      assert.ok(progress[index] > progress[index - 1], 'progress must be strictly increasing');
    }
    assert.equal(bank.size, 1);
  });
});

// ---------------------------------------------------------------------------
// trace 差分（复用 Python 记录，逐 step 比对）
// ---------------------------------------------------------------------------

describe('trace differential', () => {
  for (const scenario of TRACE_SCENARIOS) {
    test(`${scenario.name}`, () => {
      const bank = getBank(scenario.bank);
      const records = scenario.items.map((record) => normalizeIrt(record, bank));
      const responses = scenario.responses;
      const constants = scenario.constants;

      if (scenario.kind === 'direct') {
        const summary = vt.summarize(bank, records, responses);
        assertSummary(bank, summary, scenario.summaries[0], constants, scenario.name);
        return;
      }

      const state = vt.newState(scenario.seed);
      assert.equal(scenario.expected_next.length, records.length + 1);
      const askedKeys = [];
      for (let k = 0; k < scenario.expected_next.length; k += 1) {
        const label = `${scenario.name}[k=${k}]`;
        const prefixRecords = records.slice(0, k);
        const prefixResponses = responses.slice(0, k);
        const summary = vt.summarize(bank, prefixRecords, prefixResponses);
        assertSummary(bank, summary, scenario.summaries[k], constants, label);
        const next = vt.nextItem(bank, state, prefixRecords, prefixResponses);
        const expected = scenario.expected_next[k];
        if (expected === null) {
          assert.equal(next, null, `${label}: nextItem must stop`);
          assert.notEqual(summary.stop_reason, null, `${label}: stopped summary needs stop_reason`);
        } else {
          assert.notEqual(next, null, `${label}: nextItem must return an item`);
          assert.equal(summary.stop_reason, null, `${label}: non-stopped summary has stop_reason`);
          assert.equal(next.band, expected.band, `${label}: band must match Python selection`);
          assert.equal(next.phase, expected.phase, `${label}: phase must match Python selection`);
          // Python 在同一 history 下选的词也必须是同一 band/phase（随机只决定层内哪个词）。
          assert.equal(records[k].band, expected.band, `${label}: fixture band`);
          assert.equal(records[k].phase, expected.phase, `${label}: fixture phase`);
          assertRecordInvariants(bank, next, askedKeys, label);
        }
        if (k < records.length) {
          askedKeys.push(records[k].key);
          state.asked.push(records[k].key);
          const after = vt.summarize(bank, records.slice(0, k + 1), responses.slice(0, k + 1));
          state.theta = after.theta;
          state.se = after.se;
        }
      }
    });
  }
});

// ---------------------------------------------------------------------------
// 确定性 / 自生成题目
// ---------------------------------------------------------------------------

describe('determinism', () => {
  test('同一 seed + 同一作答规则 → 完全相同的题目序列', () => {
    const bank = getBank('main');
    const first = simulateJs(bank, 12345, keyRule, 25);
    const second = simulateJs(bank, 12345, keyRule, 25);
    const projection = (run) => run.items.map((record) => ({
      key: record.key,
      band: record.band,
      phase: record.phase,
      options: record.item.options,
      correct_index: record.item.correct_index,
    }));
    assert.deepEqual(projection(second), projection(first));
    assert.deepEqual(second.responses, first.responses);
  });

  test('重建同词表题库后同 seed 序列仍一致（fingerprint 决定随机材料）', () => {
    const first = simulateJs(getBank('main'), 777, keyRule, 15);
    const rebuilt = new vt.FrequencyBank(WORD_BANKS.main);
    const second = simulateJs(rebuilt, 777, keyRule, 15);
    assert.deepEqual(second.items.map((record) => record.key), first.items.map((record) => record.key));
    assert.deepEqual(second.items.map((record) => record.item), first.items.map((record) => record.item));
  });

  test('不同 seed 的序列不同', () => {
    const bank = getBank('main');
    const first = simulateJs(bank, 1, keyRule, 10);
    const second = simulateJs(bank, 2, keyRule, 10);
    assert.notDeepEqual(first.items.map((record) => record.key), second.items.map((record) => record.key));
  });

  test('选题不重复、不越界，停止条件与 summarize 一致', () => {
    const bank = getBank('main');
    const result = simulateJs(bank, 2024, keyRule);
    assert.ok(result.items.length <= vt.MAX_ITEMS);
    const keys = result.items.map((record) => record.key);
    assert.equal(new Set(keys).size, keys.length);
    assert.deepEqual(result.state.asked, keys);
    for (const record of result.items) {
      assertRecordInvariants(bank, record, [], 'simulate');
    }
    const finalSummary = vt.summarize(bank, result.items, result.responses);
    assert.notEqual(finalSummary.stop_reason, null);
    assert.equal(vt.nextItem(bank, result.state, result.items, result.responses), null);
    if (finalSummary.stop_reason === 'max_items') assert.equal(result.items.length, vt.MAX_ITEMS);
    if (finalSummary.stop_reason === 'exhausted') {
      assert.ok(result.items.length >= bank.testable_size);
    }
  });

  test('small 词表在 testable_size 处 exhausted', () => {
    const bank = getBank('small');
    const result = simulateJs(bank, 5, (record, step) => (step % 2 === 0 ? 1 : 0));
    const finalSummary = vt.summarize(bank, result.items, result.responses);
    assert.equal(finalSummary.stop_reason, 'exhausted');
    assert.equal(result.items.length, bank.testable_size);
  });
});

// ---------------------------------------------------------------------------
// validateSession
// ---------------------------------------------------------------------------

describe('validateSession', () => {
  const scenario = TRACE_SCENARIOS.find((item) => item.name === 'main-hash-precision');
  const bank = getBank('main');
  const records = scenario.items.slice(0, 45).map((record) => normalizeIrt(record, bank));
  const pendingResponses = scenario.responses.slice(0, 44);
  const answeredResponses = scenario.responses.slice(0, 45);
  const pendingSession = buildSession(bank, scenario.seed, records, pendingResponses, true, {
    from_welcome: true,
    unknown_extension: { nested: ['原样保留', 1, null] },
  });
  const answeredSession = buildSession(bank, scenario.seed, records, answeredResponses, false);

  test('接受 Python 生成的 pending / answered 会话', () => {
    assert.equal(vt.validateSession(pendingSession, bank), true);
    assert.equal(vt.validateSession(answeredSession, bank), true);
  });

  test('未知字段被忽略且不被修改', () => {
    const snapshot = JSON.parse(JSON.stringify(pendingSession));
    assert.equal(vt.validateSession(pendingSession, bank), true);
    assert.deepEqual(pendingSession, snapshot);
  });

  test('JS 自生成会话通过 validateSession（pending + answered）', () => {
    const simulated = simulateJs(bank, 4242, keyRule, 45);
    const answered = buildSession(bank, 4242, simulated.items, simulated.responses, false);
    assert.equal(vt.validateSession(answered, bank), true);
    const pending = buildSession(bank, 4242, simulated.items, simulated.responses.slice(0, -1), true);
    assert.equal(vt.validateSession(pending, bank), true);
  });

  test('篡改/结构错误一律返回 false', () => {
    const simulated = simulateJs(bank, 4242, keyRule, 45);
    const base = buildSession(bank, 4242, simulated.items, simulated.responses, false);
    assert.equal(vt.validateSession(base, bank), true);
    const clone = () => JSON.parse(JSON.stringify(base));
    const cases = [];
    const add = (label, mutate) => {
      const session = clone();
      mutate(session);
      cases.push([label, session]);
    };

    add('schema 1', (s) => { s.schema = 1; });
    add('schema 为非整数', (s) => { s.schema = 2.5; });
    add('schema 缺失', (s) => { delete s.schema; });
    add('algo 为桌面版', (s) => { s.algo = 'vst-cat-v142'; });
    add('bank_id 不符', (s) => { s.bank_id = 'deadbeef'.repeat(8); });
    add('id 空串', (s) => { s.id = ''; });
    add('id 全空白', (s) => { s.id = '   '; });
    add('id 过长', (s) => { s.id = 'x'.repeat(257); });
    add('id 含控制字符', (s) => { s.id = 'abc\ndef'; });
    add('started_at 非有限', (s) => { s.started_at = Infinity; });
    add('started_at 是字符串', (s) => { s.started_at = '1700000000'; });
    add('i 为 -1', (s) => { s.i = -1; });
    add('i 为 MAX_ITEMS', (s) => { s.i = vt.MAX_ITEMS; });
    add('i 非整数', (s) => { s.i = 1.5; });
    add('items 少一条', (s) => { s.items.pop(); });
    add('resp 多一条', (s) => { s.resp.push(1); });
    add('resp 为 2', (s) => { s.resp[0] = 2; });
    add('resp 为 0.5', (s) => { s.resp[0] = 0.5; });
    add('重复目标 key', (s) => { s.items[1] = JSON.parse(JSON.stringify(s.items[0])); });
    add('未知 key', (s) => { s.items[0] = { ...s.items[0], key: 'notaword' }; });
    add('band 不符', (s) => { s.items[0].band += 1; });
    add('rank 不符', (s) => { s.items[0].rank += 1; });
    add('phase 非法', (s) => { s.items[0].phase = 'practice'; });
    add('irt.a 不符', (s) => { s.items[0].irt.a = 2.0; });
    add('irt 缺字段', (s) => { delete s.items[0].irt.b; });
    add('item.word 不符', (s) => { s.items[0].item.word = '其它词'; });
    add('options 只有 3 个', (s) => { s.items[0].item.options.pop(); });
    add('选项槽位顺序错', (s) => { s.items[0].item.options[0].key = 'B'; });
    add('选项文本被改', (s) => { s.items[0].item.options[0].text += 'x'; });
    add('选项 ID 不存在', (s) => { s.items[0].item.options[0].item_id = 'notaword'; });
    add('correct_index 越界', (s) => { s.items[0].item.correct_index = 4; });
    add('correct_key 不符', (s) => { s.items[0].item.correct_key = 'Z'; });
    add('正确槽不是目标', (s) => {
      const item = s.items[0].item;
      item.correct_index = (item.correct_index + 1) % 4;
      item.correct_key = 'ABCD'[item.correct_index];
      item.options[item.correct_index].item_id = s.items[0].key;
      item.options[item.correct_index].text = bank.items[s.items[0].key].sense;
    });
    add('目标出现两次', (s) => {
      const item = s.items[0].item;
      const other = (item.correct_index + 1) % 4;
      item.options[other].item_id = s.items[0].key;
      item.options[other].text = bank.items[s.items[0].key].sense;
    });
    add('survey 顺序被打乱', (s) => { s.items[0].phase = 'adaptive'; });
    add('adaptive 项被标为 survey', (s) => {
      const index = s.items.findIndex((record) => record.phase === 'adaptive');
      assert.ok(index > 0);
      s.items[index].phase = 'survey';
    });
    add('state 缺失', (s) => { s.state = null; });
    add('state.asked 少一项', (s) => { s.state.asked.pop(); });
    add('state.asked 多一项', (s) => { s.state.asked.push('extra'); });
    add('state.seed 非整数', (s) => { s.state.seed = 1.5; });
    add('state.theta 越界', (s) => { s.state.theta = 99; });
    add('state.se 为负', (s) => { s.state.se = -1; });

    for (const [label, session] of cases) {
      assert.equal(vt.validateSession(session, bank), false, `tamper should fail: ${label}`);
    }
    assert.equal(vt.validateSession(null, bank), false);
    assert.equal(vt.validateSession({}, bank), false);
    assert.equal(vt.validateSession(base, {}), false);
    assert.equal(vt.validateSession(base, null), false);
  });

  test('pending 会话的 i 与 resp 长度约束', () => {
    const simulated = simulateJs(bank, 99, keyRule, 40);
    const pending = buildSession(bank, 99, simulated.items, simulated.responses.slice(0, -1), true);
    assert.equal(vt.validateSession(pending, bank), true);
    // len(resp) === i 是合法“已呈现未作答”；变成 i+1 就是已作答，同样合法。
    const answered = JSON.parse(JSON.stringify(pending));
    answered.resp.push(1);
    answered.state = buildSession(bank, 99, simulated.items, simulated.responses, false).state;
    assert.equal(vt.validateSession(answered, bank), true);
    // 真正非法的长度关系：resp 少到最后一条之前，或 i 与 items 长度脱钩。
    const tooShort = JSON.parse(JSON.stringify(pending));
    tooShort.resp.pop();
    assert.equal(vt.validateSession(tooShort, bank), false);
    const brokenIndex = JSON.parse(JSON.stringify(pending));
    brokenIndex.i += 1;
    assert.equal(vt.validateSession(brokenIndex, bank), false);
  });
});

// ---------------------------------------------------------------------------
// 参数/历史校验（与 Python 相同的错误语义）
// ---------------------------------------------------------------------------

describe('history validation', () => {
  const bank = getBank('small');

  test('nextItem 拒绝未作答的 pending 记录', () => {
    const state = vt.newState(1);
    const record = vt.nextItem(bank, state, [], []);
    assert.ok(record);
    state.asked.push(record.key);
    assert.throws(() => vt.nextItem(bank, state, [record], []),
      /answer the pending item before requesting another/);
  });

  test('nextItem / summarize 拒绝非法 history', () => {
    const state = vt.newState(1);
    const record = vt.nextItem(bank, state, [], []);
    assert.throws(() => vt.summarize(bank, [record], [2]), /responses must be exact integers -1, 0, or 1/);
    assert.throws(() => vt.summarize(bank, [record], [1, 0]),
      /history must contain only answered items and at most one pending item/);
    assert.throws(() => vt.summarize(bank, [record, record], [1, 1]), /target keys cannot repeat/);
    assert.throws(() => vt.nextItem({}, vt.newState(1), [], []), /bank must be a FrequencyBank/);
    assert.throws(() => vt.nextItem(bank, {}, [], []),
      /state seed, asked keys, theta, or se is invalid/);
    assert.throws(() => vt.summarize(bank, 'x', []), /records and responses must be sequences/);
    const badState = { seed: 1, asked: ['wrong'], theta: 0, se: 2 };
    assert.throws(() => vt.nextItem(bank, badState, [], []),
      /state seed, asked keys, theta, or se is invalid/);
  });

  test('newState 校验 seed', () => {
    assert.deepEqual(vt.newState(7), { seed: 7, asked: [], theta: 0, se: 2 });
    for (const value of [1.5, '1', null, undefined, true, NaN, Infinity]) {
      assert.throws(() => vt.newState(value), /seed must be an integer, not bool/);
    }
  });

  test('停止后 nextItem 返回 null', () => {
    const simulated = simulateJs(bank, 5, (record, step) => (step % 2 === 0 ? 1 : 0));
    const summary = vt.summarize(bank, simulated.items, simulated.responses);
    assert.equal(summary.stop_reason, 'exhausted');
    assert.equal(vt.nextItem(bank, simulated.state, simulated.items, simulated.responses), null);
  });
});
