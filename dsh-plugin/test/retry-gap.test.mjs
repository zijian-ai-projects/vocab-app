/** Pure queue/migration regression tests: synthetic in-memory data, no live app. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { StudyQueue } from '../lib/core/study_queue.js';
import { Engine } from '../lib/host/engine.js';

const words = (keys) => [...keys].map((w) => ({ w }));
const forgotten = () => ({ st: 'new', lv: 0, due: null, seen: 1, lapse: 1, streak: 1 });
const learning = (due) => ({ st: 'learning', lv: 5, due, seen: 4, lapse: 0, streak: 0 });
function expectItem(item, key, kind) {
  assert.ok(item);
  assert.deepEqual([item.w.w, item.kind], [key, kind]);
  return item;
}

for (const slot of ['current', 'held_current', 'policy_held']) {
  for (const withCandidates of [false, true]) {
    test(`future saved retry cannot bypass target: ${slot}, fresh=${withCandidates}`, () => {
      const saved = { kind: 'retry', key: 'a', custom: { nested: ['keep'] } };
      let record = {
        cursor: 1, new_count: 1, pending: { a: 5 },
        [slot]: slot === 'policy_held' ? [structuredClone(saved)] : structuredClone(saved),
      };
      let states = { a: forgotten() };
      const book = words(withCandidates ? 'abcde' : 'a');
      let queue = new StudyQueue(book, states, record);
      if (!withCandidates) {
        for (const now of [0, 86400, 604800]) {
          assert.equal(queue.next(now), null);
          assert.deepEqual(record.pending, { a: 5 });
          assert.equal(record.new_count, 1);
          assert.ok(record.policy_held.some((item) => item.key === 'a' && item.custom.nested[0] === 'keep'));
          [states, record] = structuredClone([states, record]);
          queue = new StudyQueue(book, states, record);
        }
        return;
      }
      for (const key of 'bcde') {
        const item = expectItem(queue.next(0), key, 'new');
        expectItem(queue.next(0), key, 'new'); // Merely displaying is not an answer.
        queue.answer(item, true, 0);
        assert.equal(record.pending.a, 5);
        [states, record] = structuredClone([states, record]);
        queue = new StudyQueue(book, states, record);
      }
      expectItem(queue.next(0), 'a', 'retry');
      assert.equal(record.new_count, 5);
      assert.deepEqual(record.current.custom, saved.custom);
      queue.answer(queue.next(0), false, 0);
      assert.equal(record.new_count, 5);
      assert.equal(record.pending.a, 9);
      assert.equal(queue.next(0), null, 'a failed retry cannot repeat at book end');
    });
  }
}

test('four other answers count at first, middle and late positions, across days, even when others are forgotten', () => {
  for (const start of [0, 5, 40]) {
    for (const crossDay of [false, true]) {
      const book = Array.from({ length: start + 5 }, (_, i) => ({ w: `synthetic-${i}` }));
      const states = Object.fromEntries(book.slice(0, start).map(({ w }) => [w, {
        st: 'mastered', lv: 10, due: null, seen: 10,
      }]));
      const record = { cursor: start, new_count: start };
      const queue = new StudyQueue(book, states, record);
      const first = queue.next(0);
      const key = first.w.w;
      queue.answer(first, false, 0);
      assert.equal(record.pending[key], start + 5);
      const now = crossDay ? 86400 : 0;
      for (let i = 1; i <= 4; i += 1) {
        queue.answer(expectItem(queue.next(now), `synthetic-${start + i}`, 'new'), false, now);
      }
      expectItem(queue.next(now), key, 'retry');
      assert.equal(record.new_count, start + 5);
    }
  }
});

test('reviews and retries do not advance another word retry interval', () => {
  const record = { cursor: 2, new_count: 1, pending: { a: 5, b: 1 } };
  const states = { a: forgotten(), b: forgotten(), old: learning(0) };
  const queue = new StudyQueue(words(['a', 'b', 'c', 'd', 'e', 'f', 'old']), states, record);
  queue.answer(expectItem(queue.next(0), 'old', 'review'), false, 0);
  queue.answer(expectItem(queue.next(0), 'b', 'retry'), true, 0);
  assert.equal(record.new_count, 1);
  assert.equal(record.pending.a, 5);
  for (const key of 'cdef') queue.answer(expectItem(queue.next(0), key, 'new'), true, 0);
  expectItem(queue.next(0), 'a', 'retry');
});

for (const slot of ['current', 'held_current', 'policy_held']) {
  test(`saved unanswered new cannot postpone an already eligible retry: ${slot}`, () => {
    const saved = { kind: 'new', key: 'f', extension: { keep: [42] } };
    const record = {
      new_count: 5, pending: { a: 5 },
      [slot]: slot === 'policy_held' ? [structuredClone(saved)] : structuredClone(saved),
    };
    const queue = new StudyQueue(words('af'), { a: forgotten() }, record);
    queue.answer(expectItem(queue.next(0), 'a', 'retry'), true, 0);
    expectItem(queue.next(0), 'f', 'new');
    assert.deepEqual(record.current.extension, saved.extension);
  });
}

test('restoring a school-suspended new word never delays an eligible retry', () => {
  const record = {};
  const excluded = new Set();
  const queue = new StudyQueue(words('abcdex'), {}, record, { excluded });
  queue.answer(expectItem(queue.next(0), 'a', 'new'), false, 0);
  expectItem(queue.next(0), 'b', 'new');
  record.current.custom = { school: ['keep'] };
  excluded.add('b');
  for (const key of 'cdex') queue.answer(expectItem(queue.next(0), key, 'new'), true, 0);
  excluded.clear();
  expectItem(queue.next(0), 'a', 'retry');
  assert.equal(record.new_count, 5);
  queue.answer(queue.next(0), true, 0);
  expectItem(queue.next(0), 'b', 'new');
  assert.deepEqual(record.current.custom, { school: ['keep'] });
});

test('nested review interruptions preserve saved new and retry metadata across restart', () => {
  const savedNew = { kind: 'new', key: 'a', custom: { new: [1] } };
  const savedRetry = { kind: 'retry', key: 'p', custom: { retry: [2] } };
  let record = { new_count: 5, pending: { p: 5 }, current: structuredClone(savedNew), policy_held: [structuredClone(savedRetry)] };
  let states = { p: forgotten(), old: learning(10) };
  const book = words(['a', 'p', 'old']);
  let queue = new StudyQueue(book, states, record);
  expectItem(queue.next(0), 'p', 'retry');
  assert.deepEqual(record.held_current.custom, savedNew.custom);
  queue.answer(expectItem(queue.next(10), 'old', 'review'), true, 10);
  [states, record] = structuredClone([states, record]);
  queue = new StudyQueue(book, states, record);
  queue.answer(expectItem(queue.next(10), 'p', 'retry'), true, 10);
  expectItem(queue.next(10), 'a', 'new');
  assert.deepEqual(record.current.custom, savedNew.custom);
  assert.equal(record.new_count, 5);
});

for (const interrupt of ['review', 'retry']) {
  test(`interrupting current preserves an occupied held slot: ${interrupt}`, () => {
    const saved = { kind: 'new', key: 'a', custom: { keep: [1] } };
    const current = { kind: 'new', key: 'b', custom: { keep: [2] } };
    let record = { current: structuredClone(current), held_current: structuredClone(saved), new_count: 5, pending: { p: 5 } };
    let states = { p: forgotten(), ...(interrupt === 'review' ? { old: learning(0) } : {}) };
    const book = words(['a', 'b', 'p', 'old']);
    let queue = new StudyQueue(book, states, record);
    queue.answer(expectItem(queue.next(0), interrupt === 'review' ? 'old' : 'p', interrupt), true, 0);
    if (interrupt === 'review') queue.answer(expectItem(queue.next(0), 'p', 'retry'), true, 0);
    queue.answer(expectItem(queue.next(0), 'b', 'new'), true, 0);
    [states, record] = structuredClone([states, record]);
    queue = new StudyQueue(book, states, record);
    expectItem(queue.next(0), 'a', 'new');
    assert.deepEqual(record.current.custom, saved.custom);
  });
}

test('malformed targets stay opaque through migration, active selection and queue restart', () => {
  const malformed = [null, true, false, '5', 'bad', -1, 5.5, { opaque: ['retain'] }, [], Number.MAX_SAFE_INTEGER + 1];
  for (const value of malformed) {
    for (const slot of ['current', 'held_current', 'policy_held']) {
      const saved = { kind: 'retry', key: 'alpha', custom: ['keep'] };
      let record = { new_count: 1, pending: { alpha: structuredClone(value) }, [slot]: slot === 'policy_held' ? [saved] : saved };
      const progress = { retry_gap: 3, study_records: { book: record } };
      Engine.prototype._normalizeRetryGap.call({}, progress);
      let states = { alpha: forgotten() };
      const book = words(['alpha', 'fresh']);
      let queue = new StudyQueue(book, states, record);
      assert.deepEqual(record.pending.alpha, value);
      queue.answer(expectItem(queue.next(0), 'fresh', 'new'), true, 0);
      [states, record] = structuredClone([states, record]);
      queue = new StudyQueue(book, states, record);
      assert.equal(queue.next(0), null);
      assert.deepEqual(record.pending.alpha, value);
      assert.ok(record.policy_held.some((entry) => entry.key === 'alpha' && entry.custom[0] === 'keep'));
    }
  }
});

test('migration changes only valid future targets with explicit gap=3, preserving ready and unknown values', () => {
  const migrate = (p) => Engine.prototype._normalizeRetryGap.call({}, p);
  for (const marker of [undefined, null, '3', 3.9, 5, true, 4, 3]) {
    const p = {
      ...(marker === undefined ? {} : { retry_gap: marker }),
      learning_policy: ['opaque', { invalid: true }], daily_new_ledger: 'invalid but inert',
      study_records: {
        book: { new_count: 4, pending: { future: 8, ready: 4, overdue: 0, text: '8', nil: null, flag: false, fractional: 8.5, max: Number.MAX_SAFE_INTEGER }, custom: ['keep'] },
        invalidCount: { new_count: '4', pending: { future: 8 } }, malformed: null,
      },
      states: { a: forgotten() }, history: [{ ts: 1, vocab: 300 }],
    };
    const before = structuredClone(p);
    assert.equal(migrate(p), marker !== 4);
    const expected = structuredClone(before);
    expected.retry_gap = 4;
    if (marker === 3) expected.study_records.book.pending.future = 9;
    assert.deepEqual(p, expected);
    assert.equal(migrate(p), false);
    assert.deepEqual(p, expected, 'migration must be idempotent');
  }
});
