// Public synthetic words only; no profile, storage, or private learning inputs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { setImmediate as immediate } from 'node:timers/promises';
import { Dataset } from '../lib/host/dataset.js';
import * as vt from '../lib/core/vocabulary_test.js';

function words(count = 80) {
  return Array.from({ length: count }, (_, i) => ({
    w: 'word' + String.fromCharCode(97 + Math.floor(i / 26)) + String.fromCharCode(97 + i % 26),
    frq: i + 1, pos: ['n.'], s: String.fromCharCode(0x4e00 + i) + String.fromCharCode(0x5200 + i), raw: '',
  }));
}
function dataset() { const d = new Dataset(); d.vt = vt; d.bank = words(); return d; }

test('worker bank retains exact synchronous fingerprint, maps, seeded questions, and summaries', async () => {
  const d = dataset(), progress = [];
  const expected = d.getQuizBank();
  d._quizBank = null;
  const bank = await d.prepareQuizBank((value) => progress.push(value));
  assert.ok(bank instanceof vt.FrequencyBank);
  assert.equal(bank.items.constructor, undefined, 'null-prototype item dictionary is restored');
  assert.deepEqual(bank, expected);
  assert.equal(bank.fingerprint, expected.fingerprint);
  assert.equal(progress[0], 0); assert.equal(progress.at(-1), 100);
  assert.ok(progress.length > 8);
  assert.ok(progress.every((value, index) => Number.isInteger(value) && value >= 0 && value <= 100 && (!index || value > progress[index - 1])));
  let left = vt.newState(128), right = vt.newState(128);
  const records = [], responses = [];
  for (let i = 0; i < 5; i++) {
    const a = vt.nextItem(expected, left, records, responses), b = vt.nextItem(bank, right, records, responses);
    assert.deepEqual(b, a); left.asked.push(a.key); right.asked.push(b.key);
    records.push(a); responses.push(i % 2 ? -1 : 1);
    const summary = vt.summarize(expected, records, responses);
    left.theta = right.theta = summary.theta; left.se = right.se = summary.se;
  }
  assert.deepEqual(vt.summarize(bank, records, responses), vt.summarize(expected, records, responses));
  assert.equal(d.getQuizBank(), bank);
});
test('cold preparation shares one worker and yields main-thread turns, then uses the warm cache', async () => {
  const d = dataset(), first = [], second = [];
  const a = d.prepareQuizBank((p) => first.push(p));
  const b = d.prepareQuizBank((p) => second.push(p));
  assert.equal(a, b);
  assert.throws(() => d.getQuizBank(), /构建中/);
  let done = false; a.then(() => { done = true; });
  await immediate(); assert.equal(done, false, 'worker startup/build cannot block this event-loop turn');
  const bank = await a;
  assert.deepEqual(first, second);
  assert.equal(d._quizBuild, null);
  assert.equal(await d.prepareQuizBank(), bank);
  assert.equal(d._quizBuild, null);
});
test('worker input failures do not cache a bank and permit a clean retry', async () => {
  const d = dataset(); d.bank = null;
  await assert.rejects(d.prepareQuizBank(), /words must/);
  assert.equal(d.quizBankBuilt, false); assert.equal(d._quizBuild, null);
  d.bank = words(); assert.ok(await d.prepareQuizBank() instanceof vt.FrequencyBank);
});
test('premature worker exit rejects all waiting callers without caching and can retry', async () => {
  const d = dataset(), promise = d.prepareQuizBank();
  const rejected = assert.rejects(promise, /意外退出/);
  await d._quizBuild.worker.terminate(); await rejected;
  assert.equal(d._quizBuild, null); assert.equal(d.quizBankBuilt, false);
  assert.ok(await d.prepareQuizBank() instanceof vt.FrequencyBank);
});
test('uncloneable public input fails cleanly at worker startup and can retry', async () => {
  const d = dataset(); d.bank = [() => {}];
  await assert.rejects(d.prepareQuizBank(), { name: 'DataCloneError' });
  assert.equal(d._quizBuild, null); assert.equal(d.quizBankBuilt, false);
  d.bank = words(); assert.ok(await d.prepareQuizBank() instanceof vt.FrequencyBank);
});
test('worker cancellation settles pending callers and supports retry without late cache mutation', async () => {
  const d = dataset();
  const promise = d.prepareQuizBank();
  const cancelled = assert.rejects(promise, { name: 'AbortError' });
  await d.cancelQuizBankBuild(); await cancelled;
  assert.equal(d._quizBuild, null); assert.equal(d.quizBankBuilt, false);
  await immediate(); assert.equal(d.quizBankBuilt, false);
  assert.ok(await d.prepareQuizBank() instanceof vt.FrequencyBank);
});
test('a failing progress consumer cancels its worker and does not strand retry', async () => {
  const d = dataset();
  await assert.rejects(d.prepareQuizBank((p) => { if (p > 0) throw new Error('synthetic progress failure'); }), /synthetic progress failure/);
  assert.equal(d._quizBuild, null); assert.equal(d.quizBankBuilt, false);
  assert.ok(await d.prepareQuizBank() instanceof vt.FrequencyBank);
});
