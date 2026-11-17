/**
 * core 差分测试（node:test，无第三方依赖）。
 *
 * fixture 由 test/fixtures/gen_core_fixtures.py 从真实 app/*.py + data/ 只读文件
 * 生成；这里用固定时钟 / 注入 ScriptRng 复算，逐项比对。运行：
 *   node --test test/
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

import { exactSum, sumProducts } from '../lib/core/exactsum.js';
import { canonicalJson, fingerprintOf } from '../lib/core/canonical.js';
import * as entries from '../lib/core/entries.js';
import * as books from '../lib/core/books.js';
import * as levelMeanings from '../lib/core/level_meanings.js';
import * as scheduler from '../lib/core/scheduler.js';
import * as learningPolicy from '../lib/core/learning_policy.js';
import * as studyOptions from '../lib/core/study_options.js';
import * as school from '../lib/core/school_knowledge.js';
import * as prediction from '../lib/core/prediction.js';
import * as history from '../lib/core/assessment_history.js';
import { StudyQueue, count as queueCount } from '../lib/core/study_queue.js';
import { makeRng } from '../lib/core/rng.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, 'fixtures');
const DATA_DIR = path.resolve(HERE, '..', '..', 'data');

/** 与 gen_core_fixtures.py 的 ScriptRng 完全相同的确定性 PRNG。 */
class ScriptRng {
  static MODULUS = 2147483647;

  static MULTIPLIER = 48271;

  constructor(seed = 12345) {
    const value = Number(seed) % ScriptRng.MODULUS;
    this.state = value || 1;
    this.calls = [];
  }

  _next() {
    this.state = (this.state * ScriptRng.MULTIPLIER) % ScriptRng.MODULUS;
    return this.state;
  }

  randrange(n) {
    if (n <= 0) throw new RangeError('randrange need positive');
    if (n === 1) return 0;
    const limit = ScriptRng.MODULUS - (ScriptRng.MODULUS % n);
    for (;;) {
      const value = this._next();
      if (value < limit) return value % n;
    }
  }

  sample(seq, k) {
    const pool = Array.from(seq);
    const record = {
      op: 'sample',
      n: pool.length,
      k,
      seq: pool.length <= 40 ? pool.slice() : null,
    };
    this.calls.push(record);
    const out = [];
    for (let index = 0; index < k; index += 1) {
      const picked = this.randrange(pool.length - index);
      out.push(pool[picked]);
      pool[picked] = pool[pool.length - index - 1];
    }
    record.out = out.slice();
    return out;
  }

  shuffle(seq) {
    const values = Array.from(seq);
    const record = {
      op: 'shuffle',
      n: values.length,
      seq: values.length <= 40 ? values.map((item) => JSON.parse(JSON.stringify(item))) : null,
    };
    this.calls.push(record);
    for (let index = values.length - 1; index > 0; index -= 1) {
      const picked = this.randrange(index + 1);
      const tmp = values[index];
      values[index] = values[picked];
      values[picked] = tmp;
    }
    record.out = values.map((item) => JSON.parse(JSON.stringify(item)));
    return values;
  }
}

function fixture(name) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), 'utf8'));
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function tempDataDir(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vocab-core-'));
  for (const [name, payload] of Object.entries(files)) {
    if (payload === null || payload === undefined) continue;
    fs.writeFileSync(
      path.join(dir, name),
      typeof payload === 'string' ? payload : JSON.stringify(payload),
      'utf8',
    );
  }
  return dir;
}

function cleanupDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

// --------------------------------------------------------------------------- //
// books
// --------------------------------------------------------------------------- //
function bookSummary(book) {
  const words = book.words;
  return {
    id: book.id,
    name: book.name,
    display: book.display,
    count: book.count,
    kind: book.kind,
    type: book.type,
    series: book.series,
    is_union: book.is_union,
    group: book.group,
    main: book.main,
    path: book.path,
    source_status: book.source_status,
    source_version: book.source_version,
    count_rule: book.count_rule,
    official_entry_count: book.official_entry_count,
    source_note: book.source_note,
    word_count: words.length,
    word_sha: sha256(words.map((word) => String(word)).join('\n')),
    first_words: words.slice(0, 3),
    last_words: words.slice(-3),
  };
}

function sha256(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function catalogueSnapshot(handle) {
  const mains = handle.MAINS.map((main) => ({
    id: main.id,
    name: main.name,
    groups: main.groups.map((group) => ({
      id: group.id,
      name: group.name,
      main: group.main,
      count: group.count,
      series: group.series,
      union: bookSummary(group.union),
      item_ids: group.items.map((item) => item.id),
    })),
  }));
  const allIds = handle.all().map((book) => book.id);
  const resolveInputs = [
    ...Object.keys(handle.BY_ID),
    ...Object.keys(handle.LEGACY),
    'does-not-exist', null, '', 0,
  ];
  const byId = {};
  for (const id of Object.keys(handle.BY_ID)) byId[id] = bookSummary(handle.BY_ID[id]);
  const sizes = {};
  const names = {};
  const paths = {};
  for (const id of allIds) {
    sizes[id] = handle.size(id);
    names[id] = handle.name(id);
    paths[id] = handle.path(id);
  }
  const sourceInfo = {};
  for (const id of [...allIds.slice(0, 5), handle.DEFAULT]) sourceInfo[id] = handle.sourceInfo(id);
  const sourceRows = {};
  for (const id of [...allIds.slice(0, 3), handle.DEFAULT]) sourceRows[id] = handle.sourceRows(id);
  const groupsByMain = {};
  const itemsByGroup = {};
  for (const main of handle.MAINS) {
    groupsByMain[main.id] = main.groups.map((group) => group.id);
    for (const group of main.groups) {
      itemsByGroup[group.id] = group.items.map((item) => item.id);
    }
  }
  return {
    default: handle.DEFAULT,
    legacy: { ...handle.LEGACY },
    mains,
    all_ids: allIds,
    by_id: byId,
    sizes,
    names,
    paths,
    resolve: resolveInputs.map((input) => ({ input, output: handle.resolve(input) })),
    source_info: sourceInfo,
    source_rows: sourceRows,
    groups_no_arg_ids: handle.groups().map((group) => group.id),
    groups_by_main: groupsByMain,
    items_by_group: itemsByGroup,
  };
}

test('books: 真实 data 目录的结构/顺序/resolve/path/sourceInfo', () => {
  const data = fixture('core-books.json');
  const handle = books.load(DATA_DIR);
  assert.deepEqual(catalogueSnapshot(handle), data.real);
});

test('books: phrase_books 合并、LEGACY、DEFAULT 回退（合成目录）', () => {
  const data = fixture('core-books.json');
  for (const variant of data.synthetic) {
    const dir = tempDataDir({
      'books.json': variant.books_json,
      'phrase_books.json': variant.phrase_books_json,
    });
    try {
      const handle = books.load(dir);
      assert.deepEqual(catalogueSnapshot(handle), variant.expected, variant.name);
    } finally {
      cleanupDir(dir);
    }
  }
});

test('books: 默认目录支持 DSH_VOCAB_APP_DATA_DIR', () => {
  const previous = process.env.DSH_VOCAB_APP_DATA_DIR;
  process.env.DSH_VOCAB_APP_DATA_DIR = DATA_DIR;
  books.clearCache();
  try {
    const handle = books.load();
    assert.equal(handle.DATA, DATA_DIR);
    assert.equal(handle.size(handle.DEFAULT), books.load(DATA_DIR).size(handle.DEFAULT));
  } finally {
    if (previous === undefined) delete process.env.DSH_VOCAB_APP_DATA_DIR;
    else process.env.DSH_VOCAB_APP_DATA_DIR = previous;
    books.clearCache();
  }
});

// --------------------------------------------------------------------------- //
// level_meanings
// --------------------------------------------------------------------------- //
test('level_meanings: 真实覆盖规则与 decorate', () => {
  const data = fixture('core-level-meanings.json');
  assert.deepEqual([...levelMeanings.STAGES], data.stages);
  const mapping = levelMeanings.load(DATA_DIR);
  for (const stage of data.stages) {
    assert.equal(Object.keys(mapping[stage]).length, data.real.counts[stage], stage);
    assert.equal(canonicalJson(mapping[stage]), canonicalJson(mapping[stage]));
    assert.equal(sha256(canonicalJson(mapping[stage])), data.real.sha[stage], stage);
    for (const [word, expected] of Object.entries(data.real.samples[stage])) {
      assert.deepEqual(mapping[stage][word], expected, `${stage}/${word}`);
    }
  }
  for (const item of data.decorate) {
    assert.deepEqual(levelMeanings.decorate(item.entry, mapping[item.stage]), item.output);
  }
  for (const item of data.stage_for_main) {
    assert.deepEqual(levelMeanings.stageForMain(item.input), item.output);
  }
});

test('level_meanings: 合成文件/别名字段/损坏回退', () => {
  const data = fixture('core-level-meanings.json');
  for (const variant of data.synthetic) {
    const dir = tempDataDir({ 'level_meanings.json': variant.content });
    try {
      assert.deepEqual(levelMeanings.load(dir), variant.expected, variant.name);
    } finally {
      cleanupDir(dir);
    }
  }
});

test('level_meanings: 默认目录支持 DSH_VOCAB_APP_DATA_DIR 并安全回退', () => {
  const previous = process.env.DSH_VOCAB_APP_DATA_DIR;
  const missing = tempDataDir({});
  try {
    process.env.DSH_VOCAB_APP_DATA_DIR = DATA_DIR;
    levelMeanings.clearCache();
    const mapping = levelMeanings.load();
    const explicit = levelMeanings.load(DATA_DIR);
    assert.deepEqual(mapping, explicit);
    assert.ok(Object.keys(levelMeanings.mappingFor('primary')).length > 0);

    process.env.DSH_VOCAB_APP_DATA_DIR = missing;
    levelMeanings.clearCache();
    assert.deepEqual(levelMeanings.load().primary, {});
    assert.equal(levelMeanings.mappingFor('middleschool').constructor, Object);
  } finally {
    if (previous === undefined) delete process.env.DSH_VOCAB_APP_DATA_DIR;
    else process.env.DSH_VOCAB_APP_DATA_DIR = previous;
    levelMeanings.clearCache();
    cleanupDir(missing);
  }
});

// --------------------------------------------------------------------------- //
// entries
// --------------------------------------------------------------------------- //
test('entries: 展示/释义/音标/词组判定（真实词条切片）', () => {
  const data = fixture('core-entries.json');
  assert.deepEqual(entries.CATEGORIES.map((item) => [...item]), data.categories);
  for (const item of data.display) {
    assert.equal(entries.wordCaption(item.entry), item.word_caption);
    assert.equal(entries.isPhrase(item.entry), item.is_phrase);
    assert.equal(entries.meaning(item.entry), item.meaning);
    assert.equal(entries.pronunciation(item.entry), item.pronunciation);
  }
});

test('entries: memoryInfo 分类/等级/标签', () => {
  const data = fixture('core-entries.json');
  for (const item of data.memory) {
    assert.deepEqual(
      entries.memoryInfo(item.key, item.states, new Set(item.known), new Set(item.predicted)),
      item.output,
      item.key,
    );
  }
  assert.equal(entries.memoryInfo('missing', {}, new Set(), new Set())[0], 'unlearned');
});

// --------------------------------------------------------------------------- //
// study_options
// --------------------------------------------------------------------------- //
function choicesDigest(pool) {
  pool.prepare();
  return pool._choices.map((choice) => ({
    text: choice.text,
    senses: [...choice.senses].sort(),
    keys: [...choice.keys].filter((key) => key !== null).sort(),
    has_null_key: choice.keys.has(null),
  }));
}

test('study_options: 池预解析/选项集合/正确项/随机调用顺序', () => {
  const data = fixture('core-study-options.json');
  const pool = new studyOptions.OptionPool(data.entries);
  assert.equal(pool.length, data.pool_size);
  assert.deepEqual(choicesDigest(pool), data.prepared_choices);
  for (const item of data.cases) {
    const entry = data.entries.find((candidate) => candidate.w === item.target)
      || { w: 'empty', s: '' };
    const rng = new ScriptRng(item.target === 'empty' ? 7 : 20260101);
    if (item.error === null) {
      const result = studyOptions.makeOptions(entry, pool, rng);
      assert.deepEqual(result.options, item.options, item.target);
      assert.equal(result.correct, item.correct, item.target);
    } else {
      assert.throws(() => studyOptions.makeOptions(entry, pool, rng), {
        message: item.error,
      }, item.target);
    }
    assert.deepEqual(rng.calls, item.calls, `${item.target} calls`);
  }
});

test('study_options: 池不足三个释义时报错；真实词库切片选项', () => {
  const data = fixture('core-study-options.json');
  const tiny = new studyOptions.OptionPool(data.tiny.entries);
  const rng = new ScriptRng(8);
  assert.throws(() => studyOptions.makeOptions(
    { w: 'a', s: '甲' }, tiny, rng,
  ), { message: data.tiny.error });
  assert.deepEqual(rng.calls, data.tiny.calls);

  const realPool = new studyOptions.OptionPool(data.real_entries);
  assert.equal(realPool.length, data.real_pool_size);
  assert.deepEqual(choicesDigest(realPool), data.real_choices);
  for (const item of data.real_cases) {
    const entry = data.real_entries.find((candidate) => candidate.w === item.target);
    const caseRng = new ScriptRng(424242);
    const result = studyOptions.makeOptions(entry, realPool, caseRng);
    assert.deepEqual(result.options, item.options, item.target);
    assert.equal(result.correct, item.correct, item.target);
    assert.deepEqual(caseRng.calls, item.calls, `${item.target} calls`);
  }
});

test('study_options: makeOptions 必须注入 rng', () => {
  const pool = new studyOptions.OptionPool([
    { w: 'a', s: '甲' }, { w: 'b', s: '乙' }, { w: 'c', s: '丙' },
    { w: 'd', s: '丁' },
  ]);
  assert.throws(() => studyOptions.makeOptions({ w: 'a', s: '甲' }, pool), TypeError);
  const rng = makeRng('study-options|test');
  const result = studyOptions.makeOptions({ w: 'a', s: '甲' }, pool, rng);
  assert.equal(result.options[result.correct], '甲');
  assert.equal(result.options.length, 4);
});

// --------------------------------------------------------------------------- //
// scheduler
// --------------------------------------------------------------------------- //
test('scheduler: 常量与逐条状态转换（含 legacy 迁移）', () => {
  const data = fixture('core-scheduler.json');
  assert.deepEqual({
    MIN: scheduler.MIN,
    HOUR: scheduler.HOUR,
    DAY: scheduler.DAY,
    LEVELS: [...scheduler.LEVELS],
    LEVEL_NAMES: [...scheduler.LEVEL_NAMES],
    MASTERED: scheduler.MASTERED,
    DONE: [...scheduler.DONE],
  }, data.constants);
  for (const item of data.cases) {
    let actual;
    if (item.op === 'migrate') {
      actual = scheduler.migrateState(clone(item.state), item.legacy);
    } else if (item.op === 'newState') {
      actual = scheduler.newState(item.now);
    } else {
      const fn = {
        remember: scheduler.onRemember,
        forget: scheduler.onForget,
        fuzzy: scheduler.onFuzzy,
        retire: scheduler.onRetire,
      }[item.op];
      actual = fn(clone(item.state), item.now);
    }
    // Frozen Python fixtures keep every historical assertion except the one
    // v0.1.3 intentional rule change: old-word forget schedules now + 300.
    const expected = clone(item.expected);
    if (item.op === 'forget' && expected.st === 'learning'
        && expected.lv >= 1 && expected.lv <= 9) {
      expected.due = item.now + 300;
    }
    assert.deepEqual(actual, expected, `${item.op} ${JSON.stringify(item.state)}`);
  }
});

test('scheduler: dueQueue/reviewItems/nextNew/migrateStates', () => {
  const data = fixture('core-scheduler.json').batch;
  const states = clone(data.states);
  assert.deepEqual(scheduler.migrateStates(clone(states), false), data.migrate_modern);
  assert.deepEqual(scheduler.migrateStates(clone(states), true), data.migrate_legacy);
  assert.deepEqual(scheduler.dueQueue(clone(data.words), clone(states), data.now),
    data.due_queue);
  assert.deepEqual(scheduler.reviewItems(clone(data.words), clone(states), data.now),
    data.review_items);
  const cursors = [0, 1, 3, 6, -2, '2'];
  const nextNew = cursors.map((cursor) => scheduler.nextNew(
    clone(data.words), clone(states), cursor,
  ));
  assert.deepEqual(nextNew, data.next_new);
});

// --------------------------------------------------------------------------- //
// learning_policy
// --------------------------------------------------------------------------- //
test('learning_policy: 常量/normalizeSettings/validateLedger', () => {
  const data = fixture('core-learning-policy.json');
  assert.deepEqual({
    REVIEW_FIRST: learningPolicy.REVIEW_FIRST,
    DAILY_NEW_FIRST: learningPolicy.DAILY_NEW_FIRST,
    DEFAULTS: { ...learningPolicy.DEFAULTS },
    MAX_DAILY_NEW: learningPolicy.MAX_DAILY_NEW,
  }, data.constants);
  for (const item of data.normalize) {
    assert.deepEqual(learningPolicy.normalizeSettings(item.raw), item.output);
  }
  for (const item of data.ledger) {
    if (item.ok) {
      assert.equal(learningPolicy.validateLedger(clone(item.ledger)), true);
    } else {
      assert.throws(() => learningPolicy.validateLedger(clone(item.ledger)), {
        message: item.error,
      });
    }
  }
});

test('learning_policy: 每日配额/跨日/账本原地更新/次日零点', () => {
  const data = fixture('core-learning-policy.json');
  for (const item of data.behavior) {
    const ledger = clone(item.ledger_before);
    const policy = new learningPolicy.LearningPolicy(clone(item.settings), ledger);
    assert.equal(policy.dailyNewFirst, item.daily_new_first);
    assert.equal(policy.limit, item.limit);
    assert.equal(policy.learnedToday(item.now), item.learned_today);
    assert.equal(policy.remaining(item.now), item.remaining);
    assert.equal(policy.allowsNew(item.now), item.allows_new);
    assert.equal(policy.shouldReviewBeforeNew(item.now), item.should_review_before_new);
    assert.equal(policy.nextDayTime(item.now), item.next_day_time);
    assert.equal(learningPolicy.localDay(item.now), item.local_day);
    for (const action of item.introduce) {
      if (action.error !== undefined) {
        assert.throws(() => policy.introduceNew(action.key, action.now), {
          message: action.error,
        });
      } else {
        assert.equal(policy.introduceNew(action.key, action.now), action.added);
      }
    }
    assert.deepEqual(ledger, item.ledger_after);
  }
  const clockInputs = [
    0, 1, 86399, 86400, 1700000000.0,
    new Date(2024, 1, 29, 12, 0, 0).getTime() / 1000,
    new Date(2024, 2, 1, 12, 0, 0).getTime() / 1000,
    new Date(2024, 11, 31, 23, 59, 0).getTime() / 1000,
  ];
  assert.deepEqual(clockInputs.map((now) => learningPolicy.localDay(now)), data.clock);
  const policy = new learningPolicy.LearningPolicy(
    { mode: learningPolicy.REVIEW_FIRST, daily_new: 20 }, {},
  );
  const localTimes = [
    new Date(2024, 1, 29, 12, 0, 0).getTime() / 1000,
    new Date(2024, 2, 31, 12, 0, 0).getTime() / 1000,
    new Date(2024, 11, 31, 23, 59, 0).getTime() / 1000,
  ];
  assert.deepEqual(localTimes.map((now) => policy.nextDayTime(now)),
    data.next_day_time);
});

// --------------------------------------------------------------------------- //
// school_knowledge
// --------------------------------------------------------------------------- //
test('school_knowledge: normalize 与累计词集合（真实 books）', () => {
  const data = fixture('core-school-knowledge.json');
  assert.deepEqual(school.LEVELS.map((item) => [...item]), data.levels);
  assert.deepEqual([...school.BOOKS], data.books);
  for (const item of data.normalize) {
    assert.equal(school.normalize(item.input), item.output);
  }
  const handle = books.load(DATA_DIR);
  for (const [level, expected] of Object.entries(data.words)) {
    const values = [...school.words(level, handle)].sort();
    assert.equal(values.length, expected.count, level);
    assert.equal(sha256(values.join('\n')), expected.sha, level);
    assert.deepEqual(values.slice(0, 20), expected.first, level);
    assert.deepEqual(values.slice(-20), expected.last, level);
  }
  // 返回副本：修改结果不影响缓存
  const first = school.words('primary', handle);
  first.clear();
  assert.ok(school.words('primary', handle).size > 0);
});

// --------------------------------------------------------------------------- //
// prediction
// --------------------------------------------------------------------------- //
test('prediction: 常量/文档校验/策略解析', () => {
  const data = fixture('core-prediction.json');
  assert.deepEqual({ SCHEMA: prediction.SCHEMA, STRATEGIES: [...prediction.STRATEGIES] },
    data.constants);
  assert.deepEqual(prediction.newPredictionData(), data.new_data);
  for (const item of data.validate) {
    if (item.ok) {
      const result = prediction.validatePredictionData(clone(item.document));
      assert.deepEqual(result, item.document);
    } else {
      assert.throws(() => prediction.validatePredictionData(clone(item.document)), {
        message: item.error,
      });
    }
  }
  for (const item of data.strategy) {
    if (item.value_error === null || item.value_error === undefined) {
      assert.equal(prediction.applyStrategy(item.estimate, item.error, item.strategy),
        item.output);
    } else {
      assert.throws(
        () => prediction.applyStrategy(item.estimate, item.error, item.strategy),
        { message: item.value_error },
      );
    }
  }
});

test('prediction: 候选选择（同 rng 序列逐项一致）', () => {
  const data = fixture('core-prediction.json');
  for (const item of data.selection) {
    const rng = new ScriptRng(item.seed);
    const [selected, counts] = prediction.selectPredictionCandidates(
      clone(data.entries), clone(data.states), item.target,
      {
        bands: item.bands === null ? null : clone(item.bands),
        rejected: item.rejected,
        excluded: item.excluded,
        seed: item.seed,
        rng,
      },
    );
    assert.deepEqual([...selected].sort(), item.selected, item.name);
    assert.deepEqual(counts, item.counts, item.name);
  }
  const errorCalls = {
    bad_target: () => prediction.selectPredictionCandidates(
      clone(data.entries), clone(data.states), -1),
    bad_target_bool: () => prediction.selectPredictionCandidates(
      clone(data.entries), clone(data.states), true),
    bad_states: () => prediction.selectPredictionCandidates(
      clone(data.entries), [], 1),
    bad_bands: () => prediction.selectPredictionCandidates(
      clone(data.entries), clone(data.states), 1, [1, 2]),
    bad_level: () => prediction.selectPredictionCandidates(
      clone(data.entries), clone(data.states), 1,
      { w01: 'one', w02: 2 }),
    bad_level_bool: () => prediction.selectPredictionCandidates(
      clone(data.entries), clone(data.states), 1,
      { w01: true, w02: 2 }),
  };
  for (const item of data.selection_errors) {
    assert.throws(errorCalls[item.name], { message: item.error }, item.name);
  }
});

// --------------------------------------------------------------------------- //
// assessment_history
// --------------------------------------------------------------------------- //
test('assessment_history: 常量/分类/系列/趋势/归档边界', () => {
  const data = fixture('core-assessment-history.json');
  assert.deepEqual({
    ALGORITHM: history.ALGORITHM,
    UNIT: history.UNIT,
    MEASUREMENT_SCHEMA: history.MEASUREMENT_SCHEMA,
  }, data.constants);
  for (const item of data.is_current) {
    assert.equal(history.isCurrent(item.record), item.output);
  }
  for (const item of data.series_key) {
    assert.deepEqual(history.seriesKey(item.record), item.output);
  }
  for (const item of data.plottable) {
    assert.equal(history.plottable(item.record), item.output);
  }
  assert.deepEqual(history.comparable(data.history, data.comparable_reference),
    data.comparable_output);
  assert.deepEqual(history.currentTrend(data.history, data.trend_bank),
    data.trend_output);
  for (const item of data.archives) {
    const progress = clone(item.input);
    if (item.error !== null) {
      assert.throws(
        () => history.archiveSession(progress, item.timestamp, item.reason),
        { message: item.error },
        item.name,
      );
    } else {
      assert.equal(
        history.archiveSession(progress, item.timestamp, item.reason),
        null,
        item.name,
      );
      assert.deepEqual(progress, item.progress, item.name);
    }
  }
});

// --------------------------------------------------------------------------- //
// study_queue
// --------------------------------------------------------------------------- //
function makeScenarioQueue(scenario) {
  const policy = new learningPolicy.LearningPolicy(
    clone(scenario.settings), clone(scenario.ledger),
  );
  const queue = new StudyQueue(
    clone(scenario.words),
    clone(scenario.states),
    clone(scenario.record),
    {
      retryGap: scenario.retry_gap,
      known: new Set(scenario.known),
      policy,
      excluded: new Set(scenario.excluded),
    },
  );
  return queue;
}

function queueItemSnapshot(item) {
  if (item === null) return null;
  return {
    kind: item.kind,
    key: item.w.w,
    w: item.w,
    st: item.st,
    idx: item.idx,
  };
}

test('study_queue: 固定时钟轨迹（含掉队重现/daily_new/排除/损坏 record）', () => {
  const data = fixture('core-queue.json');
  for (const scenario of data.scenarios) {
    const queue = makeScenarioQueue(scenario);
    assert.deepEqual(queue.record, scenario.record_after_init, `${scenario.name} init record`);
    assert.equal(queue.cursor, scenario.cursor_after_init, `${scenario.name} init cursor`);
    let pendingItem = null;
    for (let index = 0; index < scenario.steps.length; index += 1) {
      const step = scenario.steps[index];
      const expected = scenario.trace[index];
      let actual;
      if (step.op === 'next') {
        pendingItem = queue.next(step.now);
        actual = {
          op: 'next',
          now: step.now,
          item: queueItemSnapshot(pendingItem),
          cursor: queue.cursor,
          next_due: queue.nextDueTime(step.now),
          record: clone(queue.record),
          states: clone(queue.states),
        };
      } else {
        const after = queue.answer(pendingItem, step.remember, step.now,
          step.introduced_at === undefined ? null : step.introduced_at);
        pendingItem = null;
        actual = {
          op: 'answer',
          now: step.now,
          remember: step.remember,
          state: clone(after),
          cursor: queue.cursor,
          next_due: queue.nextDueTime(step.now),
          record: clone(queue.record),
          states: clone(queue.states),
        };
      }
      assert.deepEqual(actual, expected, `${scenario.name} step ${index}`);
    }
  }
});

test('study_queue: 构造期校验与 answer stale 保护', () => {
  const data = fixture('core-queue.json');
  const words = [{ w: 'a' }];
  for (const item of data.construction_errors) {
    let options;
    switch (item.name) {
      case 'states_not_dict': options = { states: [], record: {} }; break;
      case 'record_not_dict': options = { states: {}, record: [] }; break;
      case 'pending_not_dict': options = { states: {}, record: { pending: [] } }; break;
      case 'policy_held_not_list': options = { states: {}, record: { policy_held: 'x' } }; break;
      case 'policy_held_item_not_dict': options = { states: {}, record: { policy_held: [1] } }; break;
      case 'retry_gap_zero': options = { states: {}, record: {}, retryGap: 0 }; break;
      case 'retry_gap_negative': options = { states: {}, record: {}, retryGap: -2 }; break;
      default: options = { states: {}, record: {}, retryGap: 'abc' };
    }
    if (item.exact) {
      assert.throws(() => new StudyQueue(clone(words), clone(options.states),
        clone(options.record), { retryGap: options.retryGap }), {
        message: item.error,
      }, item.name);
    } else {
      assert.throws(() => new StudyQueue(clone(words), clone(options.states),
        clone(options.record), { retryGap: options.retryGap }));
    }
  }
  // answer 的 stale/错配保护
  const states = {};
  const record = {};
  const queue = new StudyQueue([{ w: 'a' }, { w: 'b' }], states, record, {
    retryGap: 3,
    known: new Set(),
    policy: new learningPolicy.LearningPolicy(
      { mode: learningPolicy.REVIEW_FIRST, daily_new: 20 }, {},
    ),
    excluded: new Set(),
  });
  const first = queue.next(1700000000);
  queue.answer(first, true, 1700000001);
  const attempts = [
    ['double_answer', clone(first)],
    ['wrong_kind', { kind: 'review', w: { w: 'a' }, st: null, idx: 0 }],
    ['missing_key', { kind: 'new', w: { w: 'zzz' }, st: null, idx: 0 }],
  ];
  for (let index = 0; index < attempts.length; index += 1) {
    const [name, item] = attempts[index];
    assert.throws(() => queue.answer(item, true, 1700000002),
      { message: data.answer_errors[index].error }, name);
  }
});

test('study_queue: stats 摘要形状（JS 侧新增）', () => {
  const states = {};
  const record = {};
  const queue = new StudyQueue(
    [{ w: 'a' }, { w: 'b' }, { w: 'c' }],
    states,
    record,
    {
      retryGap: 3,
      policy: new learningPolicy.LearningPolicy(
        { mode: learningPolicy.REVIEW_FIRST, daily_new: 20 }, {},
      ),
    },
  );
  const item = queue.next(1000);
  assert.equal(item.kind, 'new');
  queue.answer(item, true, 1001);
  const stats = queue.stats(1001);
  assert.deepEqual(stats, {
    cursor: 1,
    total: 3,
    due: 0,
    unseen: 2,
    learned: 1,
    pending: 0,
    newCount: 1,
    currentKey: null,
    nextDue: 1301,
  });
  assert.equal(queueCount('7'), 7);
  assert.equal(queueCount('bad'), 0);
  assert.equal(queueCount(-5), 0);
});

// --------------------------------------------------------------------------- //
// exactSum
// --------------------------------------------------------------------------- //
test('exactSum: 与 math.fsum 逐例一致', () => {
  const data = fixture('core-sum.json');
  for (const item of data.cases) {
    assert.equal(exactSum(item.values), item.output,
      `exactSum(${JSON.stringify(item.values).slice(0, 60)})`);
  }
  assert.ok(Number.isNaN(exactSum([NaN, 1])));
  assert.equal(exactSum([Infinity]), Infinity);
  assert.equal(exactSum([-Infinity]), -Infinity);
  assert.throws(() => exactSum([Infinity, -Infinity]), RangeError);
  assert.throws(() => exactSum([1e308, 1e308]), RangeError);
  assert.equal(exactSum([1, true, false]), 2);
  assert.equal(sumProducts([2, 3], [0.5, 0.25]), 1.75);
  assert.equal(sumProducts([4, 6], [0.25, 0.5]), 4);
  assert.throws(() => sumProducts([1, 2], [1]), TypeError);
});

// --------------------------------------------------------------------------- //
// canonicalJson / fingerprint
// --------------------------------------------------------------------------- //
test('canonicalJson: 键排序/非 ASCII 原样/整数无小数点/稳定指纹', () => {
  assert.equal(canonicalJson({ b: 1, a: [1, 2] }), '{"a":[1,2],"b":1}');
  assert.equal(canonicalJson({ 中文: '汉字' }), '{"中文":"汉字"}');
  assert.equal(canonicalJson(1.0), '1');
  assert.equal(canonicalJson(-0), '0');
  assert.equal(canonicalJson('a"b\\c\n'), '"a\\"b\\\\c\\n"');
  assert.equal(canonicalJson({ x: undefined, y: 1 }), '{"y":1}');
  assert.equal(canonicalJson([undefined, 1]), '[null,1]');
  assert.equal(canonicalJson(null), 'null');
  assert.throws(() => canonicalJson(10n), TypeError);
  const cycle = {};
  cycle.self = cycle;
  assert.throws(() => canonicalJson(cycle), TypeError);
  assert.equal(fingerprintOf({ a: 1 }), fingerprintOf({ a: 1 }));
  assert.notEqual(fingerprintOf({ a: 1 }), fingerprintOf({ a: 2 }));
  assert.match(fingerprintOf({ a: 1 }), /^[0-9a-f]{64}$/);
  const stable = fingerprintOf({ words: ['b', 'a'], n: 2 });
  assert.equal(stable, fingerprintOf({ n: 2, words: ['b', 'a'] }));
});

// v0.1.3: only old-word forget changes; the historical fixture files stay frozen.
test('scheduler v0.1.3: lv1..9 首次/重复忘记固定300秒，认识仍按新等级排期', async (t) => {
  for (let lv = 1; lv <= 9; lv += 1) {
    await t.test(`lv${lv}`, () => {
      const input = {
        lv, st: 'learning', due: 987654321, seen: 7, lapse: 2, streak: 3,
        future: { nested: [{ values: ['preserve', lv] }] },
      };
      const original = clone(input);
      const first = scheduler.onForget(input, 0);
      assert.deepEqual(first, { ...original, due: 300, seen: 8, lapse: 3, streak: 4 });
      const repeatAt = 1234.25;
      const again = scheduler.onForget(first, repeatAt);
      assert.deepEqual(again, { ...original, due: repeatAt + 300, seen: 9, lapse: 4, streak: 5 });
      const rememberAt = 1600.5;
      const remembered = scheduler.onRemember(again, rememberAt);
      assert.deepEqual(remembered, {
        ...original,
        lv: lv + 1,
        st: lv === 9 ? 'mastered' : 'learning',
        due: lv === 9 ? null : rememberAt + scheduler.LEVELS[lv],
        seen: 10, lapse: 4, streak: 0,
      });
      assert.deepEqual(input, original, 'caller state must not be changed');
      assert.deepEqual(Object.keys(first).sort(), Object.keys(original).sort(), 'no retry/migration flag');
      assert.notEqual(first.future, input.future);
      assert.notEqual(again.future.nested, first.future.nested);
      assert.notEqual(remembered.future.nested[0].values, again.future.nested[0].values);
      first.future.nested[0].values.push('only the returned copy');
      assert.deepEqual(input, original);
      assert.deepEqual(again.future, original.future);
      assert.deepEqual(remembered.future, original.future);
    });
  }
});

test('scheduler v0.1.3: lv0/terminal/fuzzy/now=0/null/undefined 保持各自语义', (t) => {
  const fixedNow = 1701234567.25;
  t.mock.method(Date, 'now', () => fixedNow * 1000);
  const old = { lv: 6, st: 'learning', due: 123, seen: 4, lapse: 2, streak: 3, extra: { x: ['keep'] } };
  assert.equal(scheduler.onForget(old, 0).due, 300);
  assert.equal(scheduler.onForget(old, null).due, fixedNow + 300);
  assert.equal(scheduler.onForget(old, undefined).due, fixedNow + 300);
  const fresh = { ...scheduler.newState(), extra: { keep: [1, 2] } };
  for (const now of [0, null, undefined]) {
    assert.deepEqual(scheduler.onForget(fresh, now), {
      ...fresh, seen: 1, lapse: 1, streak: 1, due: null,
    });
  }
  const firstRemember = scheduler.onRemember(scheduler.onForget(fresh, 0), 10);
  assert.equal(firstRemember.lv, 1);
  assert.equal(firstRemember.due, 310);
  for (const [st, lv] of [['mastered', 10], ['known', 7], ['retired', 4]]) {
    const terminal = { lv, st, due: null, seen: 9, lapse: 3, streak: 2, extra: { nested: [st] } };
    for (const action of [scheduler.onForget, scheduler.onRemember, scheduler.onFuzzy]) {
      const result = action(terminal, 0);
      assert.deepEqual(result, terminal);
      assert.notEqual(result, terminal);
      assert.notEqual(result.extra.nested, terminal.extra.nested);
    }
  }
  for (let lv = 1; lv <= 9; lv += 1) {
    const fuzzy = scheduler.onFuzzy({ ...old, lv }, 0);
    assert.equal(fuzzy.lv, lv);
    assert.equal(fuzzy.due, scheduler.LEVELS[lv - 1], 'legacy fuzzy still uses same-grade LEVELS');
    assert.equal(fuzzy.seen, old.seen + 1);
    assert.equal(fuzzy.lapse, old.lapse);
    assert.equal(fuzzy.streak, 0);
  }
});

test('scheduler v0.1.3: modern/legacy 迁移不重算已有due且保持深拷贝', () => {
  const saved = {
    lv: 3, st: 'learning', due: 1799999999.125, seen: 8, lapse: 2, streak: 1,
    extra: { savedQueue: [{ producer: 'before-0.1.3' }] },
  };
  const original = clone(saved);
  const modern = scheduler.migrateState(saved, false);
  assert.deepEqual(modern, saved);
  const legacy = scheduler.migrateState(saved, true);
  assert.deepEqual(legacy, { ...original, lv: 4 });
  const migrated = scheduler.migrateStates({ old: saved }, true);
  assert.equal(migrated.old.due, saved.due);
  assert.deepEqual(Object.keys(migrated.old).sort(), Object.keys(saved).sort());
  legacy.extra.savedQueue[0].producer = 'returned copy';
  migrated.old.extra.savedQueue.push({ another: true });
  assert.deepEqual(saved, original);
  assert.deepEqual(modern, original);
});

test('study_queue v0.1.3: 到期旧词多轮五分钟优先，held new/retry 与账本/pending 不被污染', () => {
  for (const kind of ['new', 'retry']) {
    const states = {
      old: { lv: 5, st: 'learning', due: 1300, seen: 4, lapse: 1, streak: 0, custom: { old: true } },
    };
    if (kind === 'retry') states.current = { lv: 0, st: 'new', due: null, seen: 2, lapse: 2, streak: 2 };
    const record = {
      cursor: 1, new_count: 13, pending: kind === 'retry' ? { current: 15 } : {},
      current: { kind, key: 'current', custom: { originalUnanswered: kind } },
      held_current: null, last_retry: null,
    };
    const ledger = { schema: 1, days: {}, custom: { preserve: ['ledger'] } };
    const policy = new learningPolicy.LearningPolicy({ ...learningPolicy.DEFAULTS }, ledger);
    const queue = new StudyQueue([{ w: 'old' }, { w: 'current' }, { w: 'tail' }], states, record, { policy, retryGap: 3 });
    const pendingBefore = clone(record.pending);
    const ledgerBefore = clone(ledger);
    assert.equal(queue.next(1000).w.w, 'current');
    assert.equal(queue.next(1299).w.w, 'current');
    for (const at of [1300, 1600]) {
      const old = queue.next(at);
      assert.equal(old.kind, 'review');
      assert.equal(old.w.w, 'old');
      assert.deepEqual(record.held_current.custom, { originalUnanswered: kind });
      const after = queue.answer(old, false, at);
      assert.equal(after.lv, 5);
      assert.equal(after.due, at + 300);
      assert.equal(record.new_count, 13);
      assert.deepEqual(record.pending, pendingBefore);
      assert.deepEqual(ledger, ledgerBefore);
      const resumed = queue.next(at);
      assert.equal(resumed.kind, kind);
      assert.equal(resumed.w.w, 'current');
      assert.deepEqual(record.current.custom, { originalUnanswered: kind });
      assert.equal(record.cursor, 1);
    }
    const old = queue.next(1900);
    queue.answer(old, true, 1900);
    assert.equal(states.old.lv, 6);
    assert.equal(states.old.due, 1900 + scheduler.LEVELS[5]);
    assert.equal(queue.next(1900).w.w, 'current');
    assert.equal(record.new_count, 13);
    assert.deepEqual(record.pending, pendingBefore);
    assert.deepEqual(ledger, ledgerBefore);
    assert.equal(states.old.seen, 7);
    assert.equal(states.old.lapse, 3);
    assert.equal(states.old.streak, 0);
  }
});

test('study_queue v0.1.3: lv0无due、pending3与每日残留20门槛均保持不变', () => {
  const states = {};
  const record = {};
  const ledger = {};
  const policy = new learningPolicy.LearningPolicy({ ...learningPolicy.DEFAULTS }, ledger);
  const queue = new StudyQueue(Array.from({ length: 30 }, (_, i) => ({ w: `synthetic${i}` })), states, record, { policy, retryGap: 3 });
  const now = 1700000000;
  for (let i = 0; i < 4; i += 1) queue.answer(queue.next(now + i), i !== 0, now + i);
  assert.equal(states.synthetic0.lv, 0);
  assert.equal(states.synthetic0.due, null);
  assert.equal(record.pending.synthetic0, 4);
  assert.equal(record.new_count, 4);
  assert.equal(policy.learnedToday(now), 4);
  assert.equal(queue.next(now + 4).w.w, 'synthetic4', 'ready retry still has the saved daily_new gate');
  for (let i = 4; i < 20; i += 1) queue.answer(queue.next(now + i), true, now + i);
  const retry = queue.next(now + 20);
  assert.equal(retry.kind, 'retry');
  assert.equal(retry.w.w, 'synthetic0');
  queue.answer(retry, false, now + 20);
  assert.equal(states.synthetic0.lv, 0);
  assert.equal(states.synthetic0.due, null);
  assert.equal(record.pending.synthetic0, 23);
  assert.equal(record.new_count, 20);
  assert.equal(policy.learnedToday(now), 20);
});
