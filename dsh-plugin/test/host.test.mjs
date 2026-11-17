/**
 * DSH host 半测试：node --test test/host.test.mjs
 *
 * 全部使用临时目录 + 合成词库，不读取/写入真实用户记录，也不触碰
 * %USERPROFILE%\.dsh 下已有资料。
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  Store,
  StorageError,
  LockError,
  resolveStorage,
  normalizeNamespace,
} from '../lib/host/store.js';
import { Engine, keyCaption } from '../lib/host/engine.js';
import { resolveDataDir } from '../lib/host/dataset.js';
import { createHandlers, STATE_PATH, ACTION_PATH, MAX_BODY_BYTES } from '../lib/host/http.js';

const WORD_COUNT = 80;

function cjkPair(index) {
  return String.fromCharCode(0x4e00 + index) + String.fromCharCode(0x5200 + index);
}

function wordAt(index) {
  return `w${String.fromCharCode(97 + Math.floor(index / 26))}${String.fromCharCode(97 + (index % 26))}`;
}

function writeJson(file, value) {
  fs.writeFileSync(file, JSON.stringify(value));
}

/** 合成词库：80 个可测词（小写字母词 + 唯一中文义项），两本同词书。 */
function writeSyntheticData(dataDir) {
  const words = Array.from({ length: WORD_COUNT }, (_, index) => wordAt(index));
  const bank = words.map((word, index) => ({
    w: word,
    s: cjkPair(index),
    pos: ['n.'],
    frq: index + 1,
    ipa: 'wɜːd',
    raw: '',
  }));
  writeJson(path.join(dataDir, 'bank.json'), bank);
  writeJson(path.join(dataDir, 'phrases.json'), [
    { w: 'take off', type: 'phrase', s: cjkPair(200), pos: ['v.'], frq: 9999 },
  ]);
  writeJson(path.join(dataDir, 'books.json'), {
    mains: [
      {
        id: 'primary',
        name: '小学',
        groups: [
          {
            id: 'tg',
            name: '测试教材',
            union: { id: 'tg-all', count: WORD_COUNT, words },
            items: [
              { id: 'tb-1', name: '测试书一', display: '测试书一', count: WORD_COUNT, words, series: '人教 PEP' },
              { id: 'tb-2', name: '测试书二', count: WORD_COUNT, words, series: '人教 PEP' },
            ],
          },
        ],
      },
      {
        id: 'university',
        name: '大学',
        groups: [
          {
            id: 'ug',
            name: '测试大学组',
            union: { id: 'ug-all', count: WORD_COUNT, words },
            items: [{ id: 'ub-1', name: '大学书一', count: WORD_COUNT, words }],
          },
        ],
      },
    ],
  });
  writeJson(path.join(dataDir, 'phrase_books.json'), { items: [] });
  writeJson(path.join(dataDir, 'level_meanings.json'), {
    levels: {
      primary: { [words[0]]: { display_s: '小学释义甲' } },
      middleschool: {},
    },
  });
  return { words, bank };
}

function createSandbox() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'vocab-host-test-'));
  const dataDir = path.join(root, 'data');
  const storageDir = path.join(root, 'storage');
  fs.mkdirSync(dataDir);
  fs.mkdirSync(storageDir);
  const synthetic = writeSyntheticData(dataDir);
  const env = { ...process.env, DSH_VOCAB_DATA_DIR: storageDir };
  delete env.DSH_HOME;
  return {
    root,
    dataDir,
    storageDir,
    env,
    synthetic,
    storageFile: path.join(storageDir, 'vocab_app_default.json'),
    backupFile: path.join(storageDir, 'vocab_app_default.json.bak'),
    lockFile: path.join(storageDir, 'vocab_app_default.lock'),
    cleanup() {
      fs.rmSync(root, { recursive: true, force: true });
    },
  };
}

async function openEngine(sandbox, config = {}) {
  const engine = new Engine({
    config: { dataDir: sandbox.dataDir, ...config },
    env: sandbox.env,
  });
  await engine.ready();
  return engine;
}

async function withEngine(t, fn, sandbox = createSandbox(), config = {}) {
  t.after(() => {
    try {
      sandbox.cleanup();
    } catch {
      /* ignore */
    }
  });
  const engine = await openEngine(sandbox, config);
  t.after(async () => {
    await engine.close();
  });
  return fn(engine, sandbox);
}

function act(engine, type, payload = {}) {
  return engine.applyAction({ rev: engine.revision, type, payload });
}

/** 让指定词的四选一生成失败（其余词正常），用于 unavailable 跳过回归。 */
function failChoiceBuildFor(engine, keys) {
  const blocked = new Set(keys);
  const original = engine._buildChoiceQuestion.bind(engine);
  engine._buildChoiceQuestion = (p, ep, entry) => (
    blocked.has(entry.w) ? null : original(p, ep, entry)
  );
  return () => {
    engine._buildChoiceQuestion = original;
  };
}

/** 进入 choice 学习模式并关闭设置，返回关闭后的页面。 */
async function enterChoiceMode(engine) {
  await act(engine, 'settings');
  const switched = await act(engine, 'studyMode', { key: 'choice' });
  assert.equal(switched.ok, true, switched.message);
  const closed = await act(engine, 'closeSettings');
  assert.equal(closed.ok, true, closed.message);
  return engine.view();
}

function stateSnapshot(engine) {
  const p = engine.doc.progress;
  return {
    states: JSON.stringify(p.states),
    ledger: JSON.stringify(p.daily_new_ledger || null),
    history: JSON.stringify(p.history || null),
    quizSession: JSON.stringify(p.quiz_session || null),
  };
}

function assertSnapshotUnchanged(engine, snapshot, label = '') {
  const now = stateSnapshot(engine);
  assert.equal(now.states, snapshot.states, `${label} 不得判定 states`);
  assert.equal(now.ledger, snapshot.ledger, `${label} 不得改学习账本`);
  assert.equal(now.history, snapshot.history, `${label} 不得改测评历史`);
  assert.equal(now.quizSession, snapshot.quizSession, `${label} 不得改测评会话`);
}

async function navToBook(engine, { main = 'primary', group = 'tg', book = 'tb-1' } = {}) {
  assert.equal(engine.view().screen, 'books');
  let result = await act(engine, 'book', { id: main });
  assert.equal(result.ok, true, result.message);
  result = await act(engine, 'book', { id: group });
  assert.equal(result.ok, true, result.message);
  result = await act(engine, 'book', { id: book });
  assert.equal(result.ok, true, result.message);
  assert.equal(engine.view().selected, book);
}

async function answerAndNext(engine, remember = true) {
  assert.equal(engine.view().screen, 'front');
  let result = await act(engine, 'answer', { action: remember ? 'remember' : 'forget' });
  assert.equal(result.ok, true, result.message);
  assert.equal(engine.view().screen, 'back');
  result = await act(engine, 'next');
  assert.equal(result.ok, true, result.message);
}

async function runQuizToEnd(engine, { maxSteps = 120 } = {}) {
  let steps = 0;
  while (engine.view().screen === 'quiz' && steps < maxSteps) {
    const quiz = engine.ep.quiz;
    assert.ok(quiz, 'quiz 状态应存在');
    const item = quiz.items[quiz.i].item;
    const choice = quiz.resp.length % 5 === 3 ? -1 : item.correct_index;
    let result = await act(engine, 'quizAnswer', { index: choice });
    assert.equal(result.ok, true, result.message);
    result = await act(engine, 'next');
    assert.equal(result.ok, true, result.message);
    steps += 1;
  }
  assert.ok(steps < maxSteps, '测评应在题量上限内结束');
  return engine.view().screen;
}

async function beginQuiz(engine) {
  const result = await act(engine, 'quizStart', { fresh: true });
  assert.equal(result.ok, true, result.message);
  await engine.idle();
  assert.equal(engine.view().screen, 'quiz');
}

function readStorage(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

// ---------------------------------------------------------------------------
// 存储
// ---------------------------------------------------------------------------
test('存储路径解析：DSH_VOCAB_DATA_DIR 优先，其次 DSH_HOME/storages/dsh-vocab-app', () => {
  const direct = resolveStorage({
    namespace: 'vocab_app_default',
    env: { DSH_VOCAB_DATA_DIR: path.join(os.tmpdir(), 'vocab-direct'), DSH_HOME: '/ignored' },
  });
  assert.equal(direct.dir, path.resolve(os.tmpdir(), 'vocab-direct'));
  assert.equal(path.basename(direct.filePath), 'vocab_app_default.json');
  assert.equal(path.basename(direct.backupPath), 'vocab_app_default.json.bak');
  assert.equal(path.basename(direct.lockPath), 'vocab_app_default.lock');

  const home = resolveStorage({
    env: { DSH_HOME: path.join(os.tmpdir(), 'fake-dsh-home') },
  });
  assert.equal(home.namespace, 'vocab_app_default');
  assert.equal(
    home.filePath,
    path.join(os.tmpdir(), 'fake-dsh-home', 'storages', 'dsh-vocab-app', 'vocab_app_default.json'),
  );

  const custom = resolveStorage({ namespace: 'custom_ns', env: {} });
  assert.equal(custom.namespace, 'custom_ns');
  assert.match(custom.filePath, /custom_ns\.json$/);

  assert.equal(normalizeNamespace(undefined), 'vocab_app_default');
  assert.throws(() => normalizeNamespace('Bad-Name'), /dataNamespace/);
  assert.throws(() => normalizeNamespace('1abc'), /dataNamespace/);
  assert.throws(() => normalizeNamespace(42), /dataNamespace/);
});

test('存储：首次为空文档、原子保存生成 .bak、再次保存推进 revision', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const store = Store.open({ namespace: 'vocab_app_default', env: sandbox.env });
  t.after(() => store.close());
  assert.equal(store.revision, 0);
  assert.equal(fs.existsSync(sandbox.lockFile), true);

  const first = structuredClone(store.doc);
  first.revision = 1;
  first.updatedAt = 100;
  first.progress = { theme: 'dark' };
  store.save(first);
  assert.equal(store.revision, 1);
  assert.equal(fs.existsSync(sandbox.storageFile), true);
  assert.equal(readStorage(sandbox.storageFile).revision, 1);

  const second = structuredClone(store.doc);
  second.revision = 2;
  second.updatedAt = 200;
  second.progress = { theme: 'sepia' };
  store.save(second);
  assert.equal(store.revision, 2);
  // .bak 保存上一份有效原文
  assert.equal(readStorage(sandbox.backupFile).revision, 1);
  assert.equal(readStorage(sandbox.backupFile).progress.theme, 'dark');
  assert.equal(readStorage(sandbox.storageFile).progress.theme, 'sepia');

  store.close();
  assert.equal(fs.existsSync(sandbox.lockFile), false);
});

test('存储：同 namespace 只允许一个实例持有（进程级互斥）', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const first = Store.open({ env: sandbox.env });
  assert.throws(() => Store.open({ env: sandbox.env }), (error) => {
    assert.ok(error instanceof LockError);
    assert.equal(error.code, 'conflict');
    return true;
  });
  first.close();
  const reopened = Store.open({ env: sandbox.env });
  reopened.close();
});

test('存储：主文件损坏时从 .bak 原子恢复并保留备份', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const store = Store.open({ env: sandbox.env });
  const first = structuredClone(store.doc);
  first.revision = 1;
  first.updatedAt = 111;
  first.progress = { theme: 'dark' };
  store.save(first);
  const second = structuredClone(store.doc);
  second.revision = 2;
  second.updatedAt = 222;
  second.progress = { theme: 'green' };
  store.save(second);
  store.close();

  assert.equal(readStorage(sandbox.backupFile).revision, 1);
  fs.writeFileSync(sandbox.storageFile, '{ 这不是 JSON');
  const recovered = Store.open({ env: sandbox.env });
  t.after(() => recovered.close());
  assert.equal(recovered.revision, 1);
  assert.equal(recovered.doc.progress.theme, 'dark');
  assert.match(recovered.storageNote, /恢复/);
  // 恢复后的主文件必须是合法 JSON
  assert.equal(readStorage(sandbox.storageFile).revision, 1);
  // 备份仍保留
  assert.equal(readStorage(sandbox.backupFile).revision, 1);
});

test('存储：主文件与 .bak 都损坏时拒绝提供服务，不静默置空', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const store = Store.open({ env: sandbox.env });
  const doc = structuredClone(store.doc);
  doc.revision = 1;
  doc.updatedAt = 111;
  store.save(doc);
  const second = structuredClone(store.doc);
  second.revision = 2;
  second.updatedAt = 222;
  store.save(second);
  store.close();

  fs.writeFileSync(sandbox.storageFile, '{');
  fs.writeFileSync(sandbox.backupFile, '{"schema":999}');
  assert.throws(() => Store.open({ env: sandbox.env }), (error) => {
    assert.ok(error instanceof StorageError);
    assert.match(error.message, /没有可恢复的有效 JSON/);
    return true;
  });
  // 原文件未被截断
  assert.equal(fs.readFileSync(sandbox.storageFile, 'utf8'), '{');
  // 锁已释放，别处仍可处理（修复后）
  assert.equal(fs.existsSync(sandbox.lockFile), false);
});

test('数据目录：默认解析到随包/仓库 data/，提供 bank.json', () => {
  const dataDir = resolveDataDir();
  assert.equal(fs.existsSync(path.join(dataDir, 'bank.json')), true);
  assert.equal(fs.existsSync(path.join(dataDir, 'books.json')), true);
});

// ---------------------------------------------------------------------------
// 引擎：首次引导、选书、刷词
// ---------------------------------------------------------------------------
test('首次引导 → 选书 → 刷词 20 步，进度落盘且 revision 递增', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    const first = engine.view();
    assert.equal(first.screen, 'books');
    assert.equal(first.selected, null);
    assert.equal(first.canStart, false);
    assert.equal(first.navLevel, 1);
    assert.equal(engine.revision, 0);
    assert.equal(fs.existsSync(sandbox.storageFile), true);

    await navToBook(engine);
    let result = await act(engine, 'start');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'front');
    assert.equal(engine.view().word.w, engine.dataset.bookWordStrs('tb-1')[0]);
    assert.equal(engine.doc.progress.book_confirmed, true);
    assert.equal(engine.doc.progress.book, 'tb-1');

    const revs = [engine.revision];
    let shown = 0;
    for (let step = 0; step < 20; step += 1) {
      if (engine.view().screen !== 'front') break;
      const kind = engine.view().kind;
      assert.ok(kind === 'new' || kind === 'review' || kind === 'retry');
      assert.equal(engine.view().revealed, false);
      result = await act(engine, 'answer', { action: step % 4 === 3 ? 'forget' : 'remember' });
      assert.equal(result.ok, true, result.message);
      assert.equal(result.rev, engine.revision);
      assert.equal(engine.view().screen, 'back');
      assert.equal(engine.view().revealed, true);
      assert.ok(engine.view().canCorrect === (engine.ep.lastAction.remember === true));
      result = await act(engine, 'next');
      assert.equal(result.ok, true, result.message);
      revs.push(engine.revision);
      shown += 1;
    }
    assert.equal(shown, 20);
    // 每次答题都成功落盘一次（next 里可能再落盘一次）
    for (let index = 1; index < revs.length; index += 1) {
      assert.ok(revs[index] > revs[index - 1]);
    }
    const persisted = readStorage(sandbox.storageFile);
    assert.equal(persisted.revision, engine.revision);
    assert.equal(Object.keys(persisted.progress.states).length, 20);
    assert.equal(persisted.progress.study_mode, 'brush');
    assert.equal(persisted.progress.study_records['tb-1'].cursor, 20);
    const learnedKeys = Object.keys(persisted.progress.states);
    assert.equal(
      JSON.stringify(learnedKeys),
      JSON.stringify(Object.keys(engine.doc.progress.states)),
    );
  });
});

test('0.1.4 词书末级：名称不再内嵌重复数量，右侧数量/系列/选择统计保留', async (t) => {
  await withEngine(t, async (engine) => {
    await act(engine, 'book', { id: 'primary' });
    assert.equal(engine.view().navLevel, 2);
    await act(engine, 'book', { id: 'tg' });
    let view = engine.view();
    assert.equal(view.navLevel, 3);
    const books = view.rows.filter((row) => row.kind === 'book' || row.kind === 'union');
    assert(books.length >= 2);
    for (const row of books) {
      const meta = engine.dataset.bookMeta(row.id);
      assert.equal(row.text, meta.display || meta.name, 'display label contains no appended quantity');
      assert.equal(row.count, meta.count);
      assert.match(row.countText, /80\s*词/);
    }
    assert(view.rows.some((row) => row.kind === 'section' && /册/.test(row.text)));
    assert.equal((await act(engine, 'book', { id: 'tb-1' })).ok, true);
    view = engine.view();
    assert.equal(view.selected, 'tb-1');
    assert.equal(view.stats.total, WORD_COUNT);
    assert.match(view.bookStat, /80\s*词/);
    assert.equal((await act(engine, 'start')).ok, true);
    assert.equal(engine.doc.progress.book, 'tb-1');
    assert.equal(engine.view().screen, 'front');
  });
});

test('0.1.2 刷词：flip 退役，正面不揭示；答后释义与改判保留', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    const rev = engine.revision;
    const doc = structuredClone(engine.doc);
    const bytes = fs.readFileSync(sandbox.storageFile);
    assert.equal(engine.view().revealed, false);
    assert.equal(engine.view().word.meaning, '');
    for (let i = 0; i < 2; i++) {
      const result = await act(engine, 'flip');
      assert.equal(result.ok, false);
      assert.equal(result.code, 'invalid');
      assert.equal(engine.revision, rev);
      assert.deepEqual(engine.doc, doc);
      assert.deepEqual(fs.readFileSync(sandbox.storageFile), bytes);
      assert.equal(engine.view().word.meaning, '');
      assert.equal(engine.view().screen, 'front');
    }
    assert.equal('revealed' in engine.ep, false);
    assert.equal((await act(engine, 'answer', { action: 'remember' })).ok, true);
    assert.equal(engine.view().screen, 'back');
    assert.notEqual(engine.view().word.meaning, '');
    const backRev = engine.revision;
    assert.equal((await act(engine, 'flip')).code, 'invalid');
    assert.equal(engine.revision, backRev);
    assert.equal(engine.view().screen, 'back');
    assert.equal((await act(engine, 'correct')).ok, true);
    // 改判保持原业务：已推进到下一张，而不是重新揭示下一张的释义。
    assert.equal(engine.view().screen === 'front' || engine.view().screen === 'empty', true);
    if (engine.view().screen === 'front') assert.equal(engine.view().word.meaning, '');
  });
});

test('选择题：flip 必须 invalid，不泄露释义/不改状态；无法出题也不落回刷词 front', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    assert.equal((await act(engine, 'studyMode', { key: 'choice' })).ok, true);
    assert.equal((await act(engine, 'closeSettings')).ok, true);
    assert.equal(engine.view().screen, 'choice');
    assert.equal(engine.view().studyMode, 'choice');
    // 选择题页不得有 word.meaning，也不允许 flip 转成刷词页
    assert.equal('meaning' in engine.view().word, false);
    const rev = engine.revision;
    const flip = await act(engine, 'flip');
    assert.equal(flip.ok, false);
    assert.equal(flip.code, 'invalid');
    assert.equal(flip.rev, rev);
    assert.equal(engine.view().screen, 'choice');
    assert.equal(engine.view().revealed, false);
    assert.equal('meaning' in engine.view().word, false);

    // 模拟无法生成四选一：仍停在 choice（不可作答），绝不回退到刷词 front
    engine._buildChoiceQuestion = () => null;
    await act(engine, 'settings');
    assert.equal((await act(engine, 'studyMode', { key: 'brush' })).ok, true);
    assert.equal((await act(engine, 'studyMode', { key: 'choice' })).ok, true);
    const closed = await act(engine, 'closeSettings');
    assert.equal(closed.ok, true, closed.message);
    const view = engine.view();
    assert.equal(view.screen, 'choice');
    assert.equal(view.unavailable, true);
    assert.equal(view.locked, true);
    assert.equal(view.options.length, 0);
    assert.equal('meaning' in view.word, false);
    const flipAgain = await act(engine, 'flip');
    assert.equal(flipAgain.ok, false);
    assert.equal(flipAgain.code, 'invalid');
    // 不可作答页允许 next 跳过当前词，不会卡死
    const skipped = await act(engine, 'next');
    assert.equal(skipped.ok, true, skipped.message);
    assert.equal(
      engine.view().screen === 'choice' || engine.view().screen === 'empty',
      true,
    );
  });
});

test('选择题无题跳过：Next 真正推进到不同词，不判定 states/账本/测评记录', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    await act(engine, 'studyMode', { key: 'choice' });
    const first = engine.ep.queue[engine.ep.qi].key;
    failChoiceBuildFor(engine, [first]);
    await act(engine, 'closeSettings');
    assert.equal(engine.view().screen, 'choice');
    assert.equal(engine.view().unavailable, true);
    assert.equal(engine.view().word.w, first);

    const snapshot = stateSnapshot(engine);
    const pendingBefore = JSON.stringify(
      engine.doc.progress.study_records['tb-1']?.pending || {},
    );
    const result = await act(engine, 'next');
    assert.equal(result.ok, true, result.message);
    const view = engine.view();
    assert.notEqual(view.word ? view.word.w : '', first, '不可作答 Next 必须换词');
    assert.equal(view.screen === 'choice' || view.screen === 'empty', true);
    // 下一次不可作答（若新词也失败）必须继续换词，绝不复用 current
    if (view.screen === 'choice' && view.unavailable) {
      const beforeSecond = view.word.w;
      const secondNext = await act(engine, 'next');
      assert.equal(secondNext.ok, true);
      assert.notEqual(engine.view().word.w, beforeSecond);
    }
    assert.ok(engine.ep.skipKeys.includes(first));
    assertSnapshotUnchanged(engine, snapshot, 'skip-new');
    assert.equal(
      JSON.stringify(engine.doc.progress.study_records['tb-1']?.pending || {}),
      pendingBefore,
      '跳过不得改动新词 pending 元数据',
    );
    // 临时跳过不落盘（progress 里没有 skipKeys）
    const stored = readStorage(sandbox.storageFile);
    assert.equal('skipKeys' in stored.progress, false);
    assert.equal(JSON.stringify(stored.progress.states), snapshot.states);
  });
});

test('选择题 all-unavailable：有限次 Next 抵达 empty，且不产生学习判定', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    await act(engine, 'studyMode', { key: 'choice' });
    engine._buildChoiceQuestion = () => null;
    await act(engine, 'closeSettings');
    assert.equal(engine.view().screen, 'choice');
    assert.equal(engine.view().unavailable, true);
    const snapshot = stateSnapshot(engine);
    const seen = [];
    let guard = 0;
    while (engine.view().screen !== 'empty' && guard < WORD_COUNT + 10) {
      const view = engine.view();
      assert.equal(view.screen, 'choice');
      assert.equal(view.unavailable, true);
      if (view.word) seen.push(view.word.w);
      const result = await act(engine, 'next');
      assert.equal(result.ok, true, result.message);
      guard += 1;
    }
    assert.equal(engine.view().screen, 'empty', '所有词不可作答时必须有限次抵达空态');
    assert.ok(guard <= WORD_COUNT + 5, `不应无限循环（实际 ${guard} 次）`);
    assert.equal(new Set(seen).size, seen.length, '每次跳过都应换词');
    assert.ok(engine.ep.skipKeys.length >= seen.length);
    assertSnapshotUnchanged(engine, snapshot, 'all-unavailable');
    assert.equal(
      Object.keys(engine.doc.progress.study_records['tb-1'].pending || {}).length,
      0,
    );
    // 空态再 next 仍有限，不会卡回某张不可作答卡片
    const next = await act(engine, 'next');
    assert.equal(next.ok, true);
    assert.equal(engine.view().screen, 'empty');
    assert.equal('skipKeys' in readStorage(sandbox.storageFile).progress, false);
  });
});

test('选择题无题跳过：到期复习跳过后 review 状态不变，重启后仍可复习', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = await openEngine(sandbox);
  let reopened = null;
  try {
    await navToBook(engine);
    await act(engine, 'start');
    const target = sandbox.synthetic.words[1];
    engine.doc.progress.states[target] = {
      st: 'learning', lv: 3, due: Math.floor(Date.now() / 1000) - 60,
      seen: 3, lapse: 1, streak: 1,
    };
    await act(engine, 'settings');
    await act(engine, 'studyMode', { key: 'choice' });
    failChoiceBuildFor(engine, [target]);
    await act(engine, 'closeSettings');
    const targetStateBefore = JSON.stringify(engine.doc.progress.states[target]);
    let found = false;
    for (let step = 0; step < 20 && engine.view().screen !== 'empty'; step += 1) {
      const view = engine.view();
      if (view.word && view.word.w === target && view.screen === 'choice') {
        found = true;
        assert.equal(view.unavailable, true);
        break;
      }
      if (view.screen === 'choice') {
        const correct = engine.ep.choice.correct;
        await act(engine, 'choice', { index: correct });
        await act(engine, 'next');
      } else if (view.screen === 'choice_back' || view.screen === 'back') {
        await act(engine, 'next');
      } else if (view.screen === 'front') {
        await act(engine, 'answer', { action: 'remember' });
        await act(engine, 'next');
      } else {
        break;
      }
    }
    assert.equal(found, true, '应能看到到期复习词');
    const snapshot = stateSnapshot(engine);
    const targetStateBeforeSkip = JSON.stringify(engine.doc.progress.states[target]);
    const skipped = await act(engine, 'next');
    assert.equal(skipped.ok, true);
    assert.notEqual(engine.view().word ? engine.view().word.w : '', target);
    assert.equal(JSON.stringify(engine.doc.progress.states[target]), targetStateBeforeSkip);
    assert.equal(JSON.stringify(engine.doc.progress.states[target]), targetStateBefore);
    assertSnapshotUnchanged(engine, snapshot, 'skip-review');

    await engine.close();
    reopened = await openEngine(sandbox);
    assert.equal(reopened.ep.skipKeys.length, 0, '重启后临时跳过必须清空');
    let seen = false;
    for (let step = 0; step < 20 && reopened.view().screen !== 'empty'; step += 1) {
      const view = reopened.view();
      if (view.word && view.word.w === target) {
        seen = true;
        break;
      }
      if (view.screen === 'choice') {
        await act(reopened, 'choice', { index: reopened.ep.choice.correct });
        await act(reopened, 'next');
      } else if (view.screen === 'choice_back' || view.screen === 'back') {
        await act(reopened, 'next');
      } else if (view.screen === 'front') {
        await act(reopened, 'answer', { action: 'remember' });
        await act(reopened, 'next');
      } else {
        break;
      }
    }
    assert.equal(seen, true, '重启后到期复习词必须重新可学');
  } finally {
    if (reopened) await reopened.close();
    await engine.close();
  }
});

test('选择题无题跳过：ready retry 跳过后保留 pending 元数据，重启后可重现', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = await openEngine(sandbox);
  let reopened = null;
  try {
    await navToBook(engine);
    await act(engine, 'start');
    const target = sandbox.synthetic.words[0];
    const p = engine.doc.progress;
    const book = p.book;
    for (const word of sandbox.synthetic.words) {
      if (word === target) continue;
      p.states[word] = {
        st: 'mastered', lv: 10, due: null, seen: 5, lapse: 0, streak: 0,
      };
    }
    delete p.states[target];
    const record = p.study_records[book];
    delete record.current;
    delete record.held_current;
    delete record.policy_held;
    record.pending = { ...(record.pending || {}), [target]: Number(record.new_count) || 0 };
    record.cursor = sandbox.synthetic.words.length;
    await act(engine, 'settings');
    await act(engine, 'studyMode', { key: 'choice' });
    failChoiceBuildFor(engine, [target]);
    await act(engine, 'closeSettings');
    engine._studyEngine = null;
    engine._newSession(engine.doc.progress, engine.ep);
    assert.equal(engine.view().screen, 'choice');
    assert.equal(engine.view().unavailable, true);
    assert.equal(engine.view().word.w, target);
    const snapshot = stateSnapshot(engine);
    const pendingBefore = JSON.stringify(engine.doc.progress.study_records[book].pending);
    const skipped = await act(engine, 'next');
    assert.equal(skipped.ok, true);
    assert.notEqual(engine.view().word ? engine.view().word.w : '', target);
    assert.equal(
      JSON.stringify(engine.doc.progress.study_records[book].pending),
      pendingBefore,
      '跳过不得清掉原 pending 重现元数据',
    );
    assert.equal(engine.doc.progress.states[target], undefined);
    assertSnapshotUnchanged(engine, snapshot, 'skip-retry');
    const stored = readStorage(sandbox.storageFile);
    assert.equal(
      stored.progress.study_records[book].pending[target],
      pendingBefore === '{}' ? undefined : JSON.parse(pendingBefore)[target],
    );
    assert.equal('skipKeys' in stored.progress, false);

    await engine.close();
    reopened = await openEngine(sandbox);
    let seen = false;
    for (let step = 0; step < 20 && reopened.view().screen !== 'empty'; step += 1) {
      const view = reopened.view();
      if (view.word && view.word.w === target) {
        seen = true;
        break;
      }
      if (view.screen === 'choice') {
        await act(reopened, 'choice', { index: reopened.ep.choice.correct });
        await act(reopened, 'next');
      } else if (view.screen === 'choice_back' || view.screen === 'back') {
        await act(reopened, 'next');
      } else if (view.screen === 'front') {
        await act(reopened, 'answer', { action: 'remember' });
        await act(reopened, 'next');
      } else {
        break;
      }
    }
    assert.equal(seen, true, '重启后 ready retry 必须重新出现');
  } finally {
    if (reopened) await reopened.close();
    await engine.close();
  }
});

test('临时跳过：切学习模式/换书开始/学校范围变化时清理', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    // choice 下制造一次跳过
    await enterChoiceMode(engine);
    const first = engine.ep.queue[engine.ep.qi].key;
    const restoreBuild = failChoiceBuildFor(engine, [first]);
    await act(engine, 'settings');
    await act(engine, 'closeSettings');
    assert.equal(engine.view().unavailable, true);
    await act(engine, 'next');
    assert.ok(engine.ep.skipKeys.includes(first));
    // 1) 切模式清理
    await act(engine, 'settings');
    const brush = await act(engine, 'studyMode', { key: 'brush' });
    assert.equal(brush.ok, true);
    assert.deepEqual(engine.ep.skipKeys, []);
    assert.equal(
      engine._excludedFor(engine.doc.progress, engine.ep).has(first),
      false,
      '切模式后临时跳过词必须重新可学（不并入学校 excluded）',
    );
    await act(engine, 'closeSettings');
    assert.equal(engine.view().screen === 'front' || engine.view().screen === 'empty', true);
    restoreBuild();

    // 2) 学校范围变化清理
    await enterChoiceMode(engine);
    const second = engine.ep.queue[engine.ep.qi].key;
    const restoreBuild2 = failChoiceBuildFor(engine, [second]);
    await act(engine, 'settings');
    await act(engine, 'closeSettings');
    await act(engine, 'next');
    assert.ok(engine.ep.skipKeys.length > 0);
    await act(engine, 'settings');
    const school = await act(engine, 'school', { level: 'primary' });
    assert.equal(school.ok, true);
    assert.deepEqual(engine.ep.skipKeys, []);
    await act(engine, 'school', { level: 'off' });
    restoreBuild2();
    await act(engine, 'closeSettings');

    // 3) 换书/换序开始清理
    await enterChoiceMode(engine);
    const third = engine.ep.queue[engine.ep.qi].key;
    const restoreBuild3 = failChoiceBuildFor(engine, [third]);
    await act(engine, 'settings');
    await act(engine, 'closeSettings');
    await act(engine, 'next');
    assert.ok(engine.ep.skipKeys.length > 0);
    await act(engine, 'settings');
    await act(engine, 'books', { from: 'settings' });
    const currentBook = engine.view().selected;
    await act(engine, 'book', { id: currentBook });
    const started = await act(engine, 'start');
    assert.equal(started.ok, true, started.message);
    assert.deepEqual(engine.ep.skipKeys, []);
    restoreBuild3();
  });
});

test('刷词：改判 Z（correct）回滚原回答并重答为不认识', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'answer', { action: 'remember' });
    const key = engine.ep.lastAction.key;
    assert.equal(engine.view().canCorrect, true);
    const level = engine.doc.progress.states[key].lv;
    assert.equal(level, 1);
    const result = await act(engine, 'correct');
    assert.equal(result.ok, true, result.message);
    const state = engine.doc.progress.states[key];
    assert.equal(state.lv, 0);
    assert.equal(state.lapse, 1);
    assert.equal(state.st, 'new');
    assert.ok(!engine.view().canCorrect);
    assert.equal(engine.ep.lastAction.remember, false);
    // 改判后已经推进到下一张
    assert.equal(engine.view().screen === 'front' || engine.view().screen === 'empty', true);
  });
});

test('刷词：Ctrl+Z（undo）恢复上一张未答状态', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    const key = engine.view().word.w;
    const revBeforeAnswer = engine.doc.revision;
    await act(engine, 'answer', { action: 'forget' });
    assert.equal(engine.view().canUndo, true);
    assert.ok(engine.doc.progress.states[key]);
    const result = await act(engine, 'undo');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'front');
    assert.equal(engine.view().word.w, key);
    assert.equal(engine.doc.progress.states[key], undefined);
    assert.equal(engine.view().canUndo, false);
    assert.ok(engine.revision > revBeforeAnswer);
    // 撤销后可正常重答
    const again = await act(engine, 'answer', { action: 'remember' });
    assert.equal(again.ok, true);
  });
});

// ---------------------------------------------------------------------------
// 选择题模式
// ---------------------------------------------------------------------------
test('选择题模式：四选一、答错标记、作答后下一题', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    let result = await act(engine, 'studyMode', { key: 'choice' });
    assert.equal(result.ok, true);
    result = await act(engine, 'closeSettings');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'choice');
    const view = engine.view();
    assert.equal(view.options.length, 4);
    assert.equal(view.locked, false);
    assert.equal(view.revealed, false);
    assert.equal(new Set(view.options.map((option) => option.text)).size, 4);
    const correct = engine.ep.choice.correct;
    const wrong = (correct + 1) % 4;
    result = await act(engine, 'choice', { index: wrong });
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'choice_back');
    assert.equal(engine.view().locked, true);
    const states = engine.view().options.map((option) => option.state);
    assert.equal(states[correct], 'ok');
    assert.equal(states[wrong], 'bad');
    assert.equal(engine.view().revealed, true);
    assert.equal(engine.view().canUndo, true);
    // undo 返回已答前同一张
    result = await act(engine, 'undo');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'choice');
    // 重新作答并进入下一题
    result = await act(engine, 'choice', { index: 0 });
    assert.equal(result.ok, true);
    result = await act(engine, 'next');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen === 'choice' || engine.view().screen === 'empty', true);
  });
});

// ---------------------------------------------------------------------------
// 设置
// ---------------------------------------------------------------------------
test('设置：主题/学校/词书保留；0.1.5 版本默认迷你且无窗口选项', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    // 学习页：studyStatus 保留，删除重复的 studyCaption/status
    const study = engine.view();
    assert.equal(study.screen, 'front');
    assert.equal(typeof study.studyStatus, 'string');
    assert.equal('studyCaption' in study, false);
    assert.equal(study.status, '');
    assert.equal('compact' in study, false);
    assert.equal(study.windowSize, 'mini');
    assert.deepEqual(study.windowPresets, [{ key: 'mini', label: '迷你', width: 400, height: 400 }]);
    assert.equal(study.keys.remember, 'Enter');
    assert.equal(study.keyCaptions.forget, '空格');

    await act(engine, 'settings');
    const settings = engine.view();
    assert.equal(settings.screen, 'settings');
    assert.equal(settings.windowSize, 'mini');
    assert.deepEqual(settings.windowPresets, [{ key: 'mini', label: '迷你', width: 400, height: 400 }]);
    assert.equal(settings.version, '0.1.9');
    assert.equal(settings.version, JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url))).version);
    assert.equal(engine.doc.progress.app_version, '1.4.3-dsh');
    assert.equal(settings.themeOptions.length, 4);
    assert.equal(settings.schoolOptions.length, 4);
    assert.equal(settings.book.id, 'tb-1');
    assert.match(settings.book.numText, /^已学 /);
    // 0.1.1 删除的设置字段
    assert.equal('compactPreferred' in settings, false);
    assert.equal('keyBindings' in settings, false);
    assert.equal('canReset' in settings, false);
    assert.equal('compact' in settings, false);
    assert.equal('windowOptions' in settings, false);
    assert.equal((settings.actions || []).some((action) => action.type === 'windowSize'), false);

    // 主题
    let result = await act(engine, 'theme', { key: 'dark' });
    assert.equal(result.ok, true);
    assert.equal(engine.view().theme, 'dark');
    assert.equal(readStorage(sandbox.storageFile).progress.theme, 'dark');
    result = await act(engine, 'theme', { key: 'not-a-theme' });
    assert.equal(result.ok, true);
    assert.equal(engine.view().theme, 'light');

    // 学习模式非法值
    result = await act(engine, 'studyMode', { key: 'nope' });
    assert.equal(result.ok, false);
    assert.equal(result.code, 'invalid');

    // 学校范围（非法值拒绝；切换后恢复 off，避免合成词库被全部当作已认识）
    result = await act(engine, 'school', { level: 'primary' });
    assert.equal(result.ok, true);
    assert.equal(engine.doc.progress.school_knowledge, 'primary');
    result = await act(engine, 'school', { level: 'bogus' });
    assert.equal(result.ok, false);
    assert.equal(result.code, 'invalid');
    result = await act(engine, 'school', { level: 'off' });
    assert.equal(result.ok, true);
    assert.equal(engine.doc.progress.school_knowledge, 'off');

    // 设置页进入选书 / 返回
    result = await act(engine, 'books', { from: 'settings' });
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'books');
    assert.equal(engine.view().selected, 'tb-1');
    result = await act(engine, 'back');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'settings');
    const learnedBefore = Object.keys(engine.doc.progress.states).length;
    result = await act(engine, 'closeSettings');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen === 'front' || engine.view().screen === 'empty', true);
    assert.equal(Object.keys(engine.doc.progress.states).length, learnedBefore);
  });
});

// ---------------------------------------------------------------------------
// 窗口大小（0.1.5 固定迷你，不开放设置动作）
// ---------------------------------------------------------------------------
test('窗口大小固定迷你；旧windowSize动作安全拒绝且视图不产生窗口选项', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = await openEngine(sandbox);
  t.after(async () => {
    await engine.close();
  });

  const preset = { key: 'mini', label: '迷你', width: 400, height: 400 };
  const fresh = engine.view();
  assert.equal(fresh.windowSize, 'mini');
  assert.deepEqual(fresh.windowPresets, [preset]);
  await navToBook(engine);
  assert.deepEqual(engine.view().windowPresets, [preset]);
  await act(engine, 'start');
  assert.equal(engine.view().windowSize, 'mini');
  assert.deepEqual(engine.view().windowPresets, [preset]);

  const payloads = [
    ...['mini', 'small', 'medium', 'large', 'huge', 'unknown', ''].map((key) => ({ key })),
    { key: null }, { key: 0 }, { key: false },
    { size: 'mini' }, { width: 400, height: 400 }, {}, null, 'mini', 400, [],
  ];
  for (const screen of ['front', 'settings']) {
    if (screen === 'settings') assert.equal((await act(engine, 'settings')).ok, true);
    assert.equal(engine.view().screen, screen);
    assert.equal(engine.view().windowSize, 'mini');
    assert.deepEqual(engine.view().windowPresets, [preset]);
    assert.equal('windowOptions' in engine.view(), false);
    assert.equal((engine.view().actions || []).some((action) => action.type === 'windowSize'), false);
    const before = clockedSnapshot(engine, sandbox);
    for (const payload of payloads) {
      const result = await act(engine, 'windowSize', payload);
      assert.equal(result.ok, false, `${screen}: 应拒绝 ${JSON.stringify(payload)}`);
      assert.equal(result.code, 'invalid', 'windowSize 本身已退役，mini 也不能生效');
      assert.equal(result.rev, before.rev);
      assert.equal(result.view.screen, screen);
      assert.equal(result.view.windowSize, 'mini');
      assert.deepEqual(result.view.windowPresets, [preset]);
      assertClockedUnchanged(engine, sandbox, before);
    }
  }
  await engine.close();
  const reopened = await openEngine(sandbox);
  t.after(async () => {
    await reopened.close();
  });
  assert.equal(reopened.view().windowSize, 'mini');
  assert.deepEqual(reopened.view().windowPresets, [preset]);
});

// ---------------------------------------------------------------------------
// 0.1.0 旧偏好兼容
// ---------------------------------------------------------------------------
test('0.1.0 兼容：保留旧 window，仅清理 keybindings/重置日志偏好，保留学习与 CAT 记录', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const stateKey = sandbox.synthetic.words[0];
  const oldState = { st: 'learning', lv: 3, due: 1700000000, seen: 4, lapse: 1, streak: 0 };
  const oldSession = {
    schema: 2,
    algo: 'vst-cat-v143-web',
    id: 'paused-session',
    bank_id: 'bank-xyz',
    started_at: 1690000000,
    updated_at: 1690000100,
    from_welcome: false,
    i: 2,
    items: [],
    resp: [1, 0],
  };
  const oldHistory = [{ ts: 1690000200, vocab: 4321, right: 9, dontknow: 2, total: 12, id: 'h1' }];
  const doc = {
    schema: 1,
    revision: 7,
    updatedAt: 1690000300,
    progress: {
      memory_schema: 2,
      _v142_test_reset: 1,
      app_version: '0.1.0',
      study_mode: 'brush',
      theme: 'dark',
      book: 'tb-1',
      book_confirmed: true,
      welcome_done: true,
      states: { [stateKey]: oldState },
      cursors: { 'tb-1': 12 },
      orders: { 'tb-1': { mode: 'shuffle', seed: 42 } },
      study_records: { 'tb-1': { cursor: 12 } },
      history: oldHistory,
      quiz_session: oldSession,
      keybindings: { remember: 'A', forget: 'B' },
      _v136_defaults_pending: { schema: 1, preferences: {}, window: {} },
    },
    window: { version: 1, preferred_compact: true, normal_w: 520, compact: true },
  };
  fs.writeFileSync(sandbox.storageFile, JSON.stringify(doc));

  const engine = await openEngine(sandbox);
  t.after(async () => {
    await engine.close();
  });
  const p = engine.doc.progress;
  assert.equal(engine.revision, 7, '偏好清理不是用户动作，不推进 revision');
  assert.deepEqual(engine.doc.window, doc.window, '旧窗口偏好原样保留；视图只读使用mini');
  assert.equal(engine.view().windowSize, 'mini');
  assert.equal('keybindings' in p, false);
  assert.equal('_v136_defaults_pending' in p, false);
  // 业务记录原样保留（states 只补 scheduler 默认字段）
  assert.equal(p.states[stateKey].lv, 3);
  assert.equal(p.states[stateKey].st, 'learning');
  assert.equal(p.states[stateKey].due, 1700000000);
  assert.deepEqual(p.cursors, { 'tb-1': 12 });
  assert.deepEqual(p.orders, { 'tb-1': { mode: 'shuffle', seed: 42 } });
  assert.deepEqual(p.history, oldHistory);
  assert.deepEqual(p.quiz_session, oldSession);
  assert.equal(p.book, 'tb-1');
  const stored = readStorage(sandbox.storageFile);
  assert.deepEqual(stored.window, doc.window);
  assert.equal('keybindings' in stored.progress, false);
  assert.deepEqual(stored.progress.history, oldHistory);
  assert.deepEqual(stored.progress.quiz_session, oldSession);
});

// ---------------------------------------------------------------------------
// 词表（catalog）
// ---------------------------------------------------------------------------
test('词表：筛选、搜索、按等级排序、批量标记已学', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    // 从选书页浏览当前词书内容
    let result = await act(engine, 'catalog');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'catalog');
    assert.equal(engine.view().rows.length, WORD_COUNT);
    assert.equal(engine.view().counts.all, WORD_COUNT);
    assert.equal(engine.view().counts.learned, 0);
    assert.equal(engine.view().book.id, 'tb-1');
    assert.equal(engine.view().categories.length, 3);

    result = await act(engine, 'catalogSort', { byLevel: true });
    assert.equal(result.ok, true);
    assert.equal(engine.view().sortByLevel, true);
    result = await act(engine, 'catalogFilter', { category: 'learned' });
    assert.equal(result.ok, true);
    assert.equal(engine.view().rows.length, 0);
    result = await act(engine, 'catalogFilter', { category: 'all', query: 'waa' });
    assert.equal(result.ok, true);
    assert.equal(engine.view().rows.length, 1);
    assert.equal(engine.view().rows[0].key, 'waa');
    result = await act(engine, 'catalogFilter', { category: 'bogus' });
    assert.equal(result.ok, false);
    assert.equal(result.code, 'invalid');

    // 回选书页开始学习，学 3 个词后再看已学筛选
    result = await act(engine, 'back');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'books');
    await act(engine, 'start');
    for (let index = 0; index < 3; index += 1) {
      await act(engine, 'answer', { action: 'remember' });
      await act(engine, 'next');
    }
    await act(engine, 'settings');
    await act(engine, 'catalog');
    assert.equal(engine.view().screen, 'catalog');
    assert.equal(engine.view().counts.learned, 3);
    result = await act(engine, 'catalogFilter', { category: 'learned', query: '' });
    assert.equal(result.ok, true);
    assert.equal(engine.view().rows.length, 3);
    for (const row of engine.view().rows) {
      assert.equal(typeof row.caption, 'string');
      assert.equal(typeof row.meaning, 'string');
      assert.equal(typeof row.memory, 'string');
      assert.ok(row.level === null || Number.isInteger(row.level));
    }

    // 批量标记：把已学词改成新词（模拟已掌握后手动加入学习）
    const masteredKey = engine.view().rows[0].key;
    engine.doc.progress.states[masteredKey] = {
      st: 'mastered', lv: 10, due: null, seen: 12, lapse: 0, streak: 0,
    };
    engine._catalogCache = null;
    const bulk = await act(engine, 'bulkLearn', { keys: [masteredKey] });
    assert.equal(bulk.ok, true, bulk.message);
    assert.equal(engine.doc.progress.states[masteredKey].st, 'new');
    assert.equal(engine.doc.progress.states[masteredKey].lv, 0);
    assert.equal(engine.view().screen, 'catalog');
    const bad = await act(engine, 'bulkLearn', { keys: ['x', 42] });
    assert.equal(bad.ok, false);
    assert.equal(bad.code, 'invalid');
  });
});

// ---------------------------------------------------------------------------
// 词汇量测评
// ---------------------------------------------------------------------------
test('首次测评HTTP响应及GET先返回building，再启动题库线程；不提前写记录', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    const before = fs.readFileSync(sandbox.storageFile);
    const revision = engine.revision;
    let built = 0;
    const prepareBank = engine.dataset.prepareQuizBank.bind(engine.dataset);
    engine.dataset.prepareQuizBank = (progress) => {
      if (!engine.dataset.quizBankBuilt) built += 1;
      return prepareBank(progress);
    };
    const handlers = createHandlers({ engine });
    const response = await handlers.action(new Request('http://localhost' + ACTION_PATH, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ rev: revision, type: 'quizStart', payload: { fresh: true } }),
    }));
    const body = await response.json();
    assert.equal(body.ok, true);
    assert.equal(body.view.screen, 'building');
    assert.equal(body.view.percent, 0);
    assert.equal(body.rev, revision);
    assert.equal(built, 0, 'the synchronous bank build must not monopolize the HTTP response microtasks');
    const state = await (await handlers.state(new Request('http://localhost' + STATE_PATH))).json();
    assert.equal(state.view.screen, 'building');
    assert.equal(state.rev, revision);
    assert.deepEqual(fs.readFileSync(sandbox.storageFile), before);
    const duplicate = await act(engine, 'quizStart', { fresh: true });
    assert.equal(duplicate.ok, false, 'a request received during preparation cannot queue a second quiz');
    assert.equal(duplicate.code, 'conflict');
    assert.equal(duplicate.view.screen, 'building');
    await engine.idle();
    assert.equal(built, 1);
    assert.equal(engine.view().screen, 'quiz');
    assert.equal(engine.revision, revision + 1);
  });
});
test('卸载发生在building响应后时不再构建、落盘或持有锁', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    const before = fs.readFileSync(sandbox.storageFile);
    let built = false;
    engine.dataset.prepareQuizBank = () => { built = true; throw new Error('must not build after close'); };
    const result = await act(engine, 'quizStart', { fresh: true });
    assert.equal(result.view.screen, 'building');
    await engine.close();
    await engine.idle();
    assert.equal(built, false);
    assert.deepEqual(fs.readFileSync(sandbox.storageFile), before);
    assert.equal(fs.existsSync(sandbox.lockFile), false);
  });
});
test('真实worker进度期间GET及timer可响应且不写记录，完成后才提交', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine); await act(engine, 'start'); await act(engine, 'settings');
    const bytes = fs.readFileSync(sandbox.storageFile), revision = engine.revision;
    const progress = [], reads = []; let heartbeats = 0;
    const handlers = createHandlers({ engine });
    const prepare = engine.dataset.prepareQuizBank.bind(engine.dataset);
    engine.dataset.prepareQuizBank = (report) => prepare((percent) => {
      report(percent); progress.push(percent);
      if (percent > 0 && percent < 100) {
        assert.equal(engine.view().screen, 'building');
        assert.equal(engine.revision, revision);
        assert.deepEqual(fs.readFileSync(sandbox.storageFile), bytes);
        reads.push(handlers.state(new Request('http://localhost' + STATE_PATH)).then((response) => response.json()));
      }
    });
    const timer = setInterval(() => { if (engine.ep.building) heartbeats += 1; }, 1);
    try {
      const result = await act(engine, 'quizStart', { fresh: true });
      assert.equal(result.view.percent, 0);
      await engine.idle();
      assert.ok(heartbeats > 0);
      assert.equal(progress[0], 0); assert.equal(progress.at(-1), 100);
      const snapshots = await Promise.all(reads);
      assert.ok(snapshots.length > 5);
      for (const state of snapshots) {
        assert.equal(state.view.screen, 'building'); assert.equal(state.rev, revision);
        assert.ok(state.view.percent > 0 && state.view.percent < 100);
      }
      assert.equal(engine.view().screen, 'quiz'); assert.equal(engine.revision, revision + 1);
    } finally { clearInterval(timer); }
  });
});
test('worker构建中卸载即时取消，不落盘不增revision且锁释放', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    const bytes = fs.readFileSync(sandbox.storageFile), revision = engine.revision;
    const prepare = engine.dataset.prepareQuizBank.bind(engine.dataset);
    let closed, sawProgress = false;
    engine.dataset.prepareQuizBank = (report) => prepare((percent) => {
      report(percent);
      if (percent > 0 && !closed) { sawProgress = true; closed = engine.close(); }
    });
    await act(engine, 'quizStart', { fresh: true }); await engine.idle(); await closed;
    assert.equal(sawProgress, true); assert.equal(engine.closed, true);
    assert.equal(engine.dataset._quizBuild, null); assert.equal(engine.dataset.quizBankBuilt, false);
    assert.equal(engine.revision, revision); assert.deepEqual(fs.readFileSync(sandbox.storageFile), bytes);
    assert.equal(fs.existsSync(sandbox.lockFile), false);
  });
});
test('冷题库构建失败恢复设置，保留学习记录并允许再次启动', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine); await act(engine, 'start'); await act(engine, 'settings');
    const before = fs.readFileSync(sandbox.storageFile), revision = engine.revision;
    const prepareBank = engine.dataset.prepareQuizBank.bind(engine.dataset);
    engine.dataset.prepareQuizBank = async () => { throw new Error('synthetic cold build failure'); };
    assert.equal((await act(engine, 'quizStart', { fresh: true })).view.screen, 'building');
    await engine.idle();
    assert.equal(engine.view().screen, 'settings');
    assert.equal(engine.view().busy, false);
    assert.match(engine.view().storageNote, /synthetic cold build failure/);
    assert.equal(engine.revision, revision);
    assert.deepEqual(fs.readFileSync(sandbox.storageFile), before);
    engine.dataset.prepareQuizBank = prepareBank;
    await act(engine, 'quizStart', { fresh: true }); await engine.idle();
    assert.equal(engine.view().screen, 'quiz');
  });
});
test('测评：构建进度页、暂停续测、完成总结、历史与方法说明', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    const startViewRev = engine.revision;
    let result = await act(engine, 'quizStart', { fresh: true });
    assert.equal(result.ok, true, result.message);
    // 首次构建返回 building 视图（rev 不变），后台构建完成后进入 quiz
    assert.equal(result.view.screen, 'building');
    assert.equal(result.view.busy, true);
    assert.equal(result.rev, startViewRev);
    await engine.idle();
    assert.equal(engine.view().screen, 'quiz');
    assert.equal(engine.view().status.startsWith('词汇测试 · 已答 0 / 最多'), true);
    assert.equal(engine.view().options.length, 4);
    assert.equal(engine.view().locked, false);
    assert.equal(engine.view().canPause, true);

    // 暂停并退出 → 设置页；设置页显示可继续
    for (let index = 0; index < 4; index += 1) {
      const quiz = engine.ep.quiz;
      const item = quiz.items[quiz.i].item;
      result = await act(engine, 'quizAnswer', { index: item.correct_index });
      assert.equal(result.ok, true, result.message);
      assert.equal(engine.view().locked, true);
      assert.equal(engine.view().options.filter((option) => option.state === 'picked').length, 1);
      result = await act(engine, 'next');
      assert.equal(result.ok, true, result.message);
    }
    assert.equal(engine.view().index, 4);
    result = await act(engine, 'quizPause');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'settings');
    assert.equal(engine.view().quiz.hasSession, true);
    assert.equal(engine.view().quiz.remainingDays, 30);
    assert.ok(sandbox.storageFile);

    // 继续上次测试
    result = await act(engine, 'quizStart', { fresh: false });
    assert.equal(result.ok, true, result.message);
    await engine.idle();
    assert.equal(engine.view().screen, 'quiz');
    assert.equal(engine.view().index, 4);
    assert.equal(engine.view().word.w.length > 0, true);

    // 答到结束 → 非首次引导完成时显示 summary（不是 result）
    const finalScreen = await runQuizToEnd(engine);
    assert.equal(finalScreen, 'summary');
    const summary = engine.view();
    assert.equal(summary.title, '本次测试已完成');
    assert.ok(Array.isArray(summary.body) && summary.body.length >= 1);
    assert.equal(summary.actions[0].type, 'settings');
    assert.match(String(summary.big), /个词|样本不足/);

    // 知道了 → 设置；历史记录有 1 行
    result = await act(engine, 'settings');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'settings');
    result = await act(engine, 'history');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'history');
    assert.equal(engine.view().rows.length, 1);
    const row = engine.view().rows[0];
    assert.equal(row.current, true);
    assert.equal(row.completed, true);
    assert.equal(typeof row.title, 'string');
    assert.match(row.title, /词$/);
    assert.match(row.detail, /本次已作答/);
    assert.ok(Array.isArray(engine.view().points) && engine.view().points.length === 1);
    assert.equal(engine.view().points[0].vocab, row.vocab);

    // 删除历史
    result = await act(engine, 'deleteHistory', { index: row.index });
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().rows.length, 0);
    result = await act(engine, 'deleteHistory', { index: 99 });
    assert.equal(result.ok, false);

    // 说明已移到 readme，历史页不能进入已退役的 method。
    const methodRev = engine.revision;
    result = await act(engine, 'method');
    assert.equal(result.ok, false);
    assert.equal(result.code, 'invalid');
    assert.equal(engine.revision, methodRev);
    assert.equal(engine.view().screen, 'history');
  });
});

test('测评：首次引导测试结束进入 result，可看分层详情并返回选书', async (t) => {
  await withEngine(t, async (engine) => {
    // 不确认词书直接开始测评（模拟首次引导）
    assert.equal(engine.view().screen, 'books');
    await beginQuiz(engine);
    const finalScreen = await runQuizToEnd(engine);
    assert.equal(finalScreen, 'result');
    const view = engine.view();
    assert.equal(view.fromWelcome, true);
    assert.equal(typeof view.estimate, 'number');
    assert.ok(Array.isArray(view.interval) && view.interval.length === 2);
    assert.ok(Array.isArray(view.rows) && view.rows.length >= 1);
    assert.ok(Array.isArray(view.actions));
    assert.equal(view.actions[0].type, 'back');
    assert.equal(view.actions[0].label, '选择词书');
    assert.ok(view.actions.some((action) => action.type === 'quizStart' && action.payload.fresh === true));
    assert.equal(view.actions.some((action) => action.type === 'method'), false);
    assert.ok(view.actions.some((action) => action.type === 'bands'));
    assert.match(view.big, /词目|样本不足/);

    // 分层采样详情（只读报告页）
    let result = await act(engine, 'bands');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'summary');
    assert.equal(engine.view().title, '分层采样详情');
    result = await act(engine, 'back');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'result');

    // 结果说明文字/分层入口保留，method 页面和入口退役。
    const methodRev = engine.revision;
    result = await act(engine, 'method');
    assert.equal(result.ok, false);
    assert.equal(result.code, 'invalid');
    assert.equal(engine.revision, methodRev);
    assert.equal(engine.view().screen, 'result');

    // 预测策略：新版测试不据此预测逐词掌握 → 只读提示页
    result = await act(engine, 'prediction', { strategy: 'conservative' });
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'summary');
    assert.equal(engine.view().title, '不据此预测逐词掌握');
    result = await act(engine, 'back');
    assert.equal(engine.view().screen, 'result');

    // 主按钮返回选书
    result = await act(engine, 'back');
    assert.equal(result.ok, true);
    assert.equal(engine.view().screen, 'books');
    assert.equal(engine.view().selected, null);
  });
});

// ---------------------------------------------------------------------------
// 失败回滚 / rev 冲突 / 重置
// ---------------------------------------------------------------------------
test('保存失败回滚：不改变内存状态、不推进 revision、不推进队列', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    const rev = engine.revision;
    const screen = engine.view().screen;
    const word = engine.view().word.w;
    const states = JSON.stringify(engine.doc.progress.states);
    const qi = engine.ep.qi;
    engine._store.fault = (stage) => {
      if (stage === 'write') throw new Error('模拟磁盘写入失败');
    };
    const result = await act(engine, 'answer', { action: 'remember' });
    assert.equal(result.ok, false);
    assert.equal(result.code, 'failed');
    assert.equal(engine.revision, rev);
    assert.equal(engine.view().screen, screen);
    assert.equal(engine.view().word.w, word);
    assert.equal(JSON.stringify(engine.doc.progress.states), states);
    assert.equal(engine.ep.qi, qi);
    assert.equal(readStorage(sandbox.storageFile).revision, rev);

    // 故障解除后同一动作可正常提交
    engine._store.fault = null;
    const retry = await act(engine, 'answer', { action: 'remember' });
    assert.equal(retry.ok, true, retry.message);
    assert.equal(engine.view().screen, 'back');
    assert.ok(engine.revision > rev);
  });
});

test('rev 冲突返回 stale 并附当前 rev 与 view，且不改状态', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    const rev = engine.revision;
    const result = await engine.applyAction({ rev: rev - 1, type: 'settings', payload: {} });
    assert.equal(result.ok, false);
    assert.equal(result.code, 'stale');
    assert.equal(result.rev, rev);
    assert.equal(result.view.screen, 'front');
    assert.equal(engine.revision, rev);
    assert.equal(engine.view().screen, 'front');
  });
});

test('已移除动作：compact/keys/resetSettings/resetRecords 一律 invalid，不改 rev 与业务记录', async (t) => {
  await withEngine(t, async (engine, sandbox) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'answer', { action: 'remember' });
    await act(engine, 'next');
    const rev = engine.revision;
    const before = {
      states: JSON.stringify(engine.doc.progress.states),
      cursors: JSON.stringify(engine.doc.progress.cursors),
      orders: JSON.stringify(engine.doc.progress.orders),
      history: JSON.stringify(engine.doc.progress.history || null),
      quizSession: JSON.stringify(engine.doc.progress.quiz_session || null),
      book: engine.doc.progress.book,
      window: JSON.stringify(engine.doc.window),
      storedRevision: readStorage(sandbox.storageFile).revision,
    };
    const removed = [
      ['compact', { on: true }],
      ['keys', { remember: 'A', forget: 'B' }],
      ['resetSettings', {}],
      ['resetRecords', { confirm: 'CLEAR' }],
      ['resetRecords', {}],
    ];
    for (const [type, payload] of removed) {
      const result = await act(engine, type, payload);
      assert.equal(result.ok, false, `${type} 必须被拒绝`);
      assert.equal(result.code, 'invalid', `${type} 的 code 应为 invalid`);
      assert.equal(engine.revision, rev, `${type} 不得推进 revision`);
    }
    assert.equal(JSON.stringify(engine.doc.progress.states), before.states);
    assert.equal(JSON.stringify(engine.doc.progress.cursors), before.cursors);
    assert.equal(JSON.stringify(engine.doc.progress.orders), before.orders);
    assert.equal(JSON.stringify(engine.doc.progress.history || null), before.history);
    assert.equal(JSON.stringify(engine.doc.progress.quiz_session || null), before.quizSession);
    assert.equal(engine.doc.progress.book, before.book);
    assert.equal(JSON.stringify(engine.doc.window), before.window);
    assert.equal(readStorage(sandbox.storageFile).revision, before.storedRevision);
  });
});

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
function jsonRequest(url, body, { headers = {}, method = 'POST' } = {}) {
  return new Request(`http://dsh.local${url}`, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
  });
}

test('HTTP：GET state / POST action 成功与错误码', async (t) => {
  await withEngine(t, async (engine) => {
    const handlers = createHandlers({ engine });
    let response = await handlers.state(new Request(`http://dsh.local${STATE_PATH}`));
    assert.equal(response.status, 200);
    let body = await response.json();
    assert.equal(body.rev, engine.revision);
    assert.equal(body.view.screen, 'books');

    // 成功动作
    response = await handlers.action(jsonRequest(ACTION_PATH, {
      rev: engine.revision,
      type: 'book',
      payload: { id: 'primary' },
    }));
    assert.equal(response.status, 200);
    body = await response.json();
    assert.equal(body.ok, true);
    assert.equal(body.rev, engine.revision);
    assert.equal(body.view.screen, 'books');
    assert.equal(body.view.navLevel, 2);

    // stale
    response = await handlers.action(jsonRequest(ACTION_PATH, {
      rev: engine.revision + 5,
      type: 'settings',
    }));
    body = await response.json();
    assert.equal(body.ok, false);
    assert.equal(body.code, 'stale');
    assert.equal(body.rev, engine.revision);
    assert.equal(body.view.navLevel, 2);

    // 未知 type → invalid（不改状态）
    const rev = engine.revision;
    response = await handlers.action(jsonRequest(ACTION_PATH, { rev, type: 'not-real' }));
    body = await response.json();
    assert.equal(body.ok, false);
    assert.equal(body.code, 'invalid');
    assert.equal(body.rev, rev);

    // 非法字段 → 400 invalid
    response = await handlers.action(jsonRequest(ACTION_PATH, { rev: 'x', type: 'settings' }));
    assert.equal(response.status, 400);
    body = await response.json();
    assert.equal(body.code, 'invalid');
    response = await handlers.action(jsonRequest(ACTION_PATH, { rev, type: 'settings', payload: [] }));
    assert.equal(response.status, 400);

    // 非法 JSON → 400
    response = await handlers.action(jsonRequest(ACTION_PATH, '{'));
    assert.equal(response.status, 400);
    assert.equal((await response.json()).code, 'invalid');

    // Content-Type → 415
    response = await handlers.action(jsonRequest(ACTION_PATH, { rev, type: 'settings' }, {
      headers: { 'content-type': 'text/plain' },
    }));
    assert.equal(response.status, 415);

    // 请求体超过 64KiB → 413
    const huge = JSON.stringify({ rev, type: 'settings', payload: { junk: 'x'.repeat(MAX_BODY_BYTES + 100) } });
    assert.ok(Buffer.byteLength(huge) > MAX_BODY_BYTES);
    response = await handlers.action(jsonRequest(ACTION_PATH, huge));
    assert.equal(response.status, 413);

    // 方法不允许
    response = await handlers.action(new Request(`http://dsh.local${ACTION_PATH}`, { method: 'GET' }));
    assert.equal(response.status, 405);
    response = await handlers.state(new Request(`http://dsh.local${STATE_PATH}`, { method: 'POST' }));
    assert.equal(response.status, 405);

    // 响应必须是纯 JSON（无函数/undefined），可 round-trip
    response = await handlers.state(new Request(`http://dsh.local${STATE_PATH}`));
    const text = await response.text();
    assert.equal(text.includes('undefined'), false);
    JSON.parse(text);
  });
});

test('HTTP：记录双损坏时拒绝服务（503），不伪造空记录', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  let engine = await openEngine(sandbox);
  await act(engine, 'theme', { key: 'dark' });
  await engine.close();
  fs.writeFileSync(sandbox.storageFile, '{');
  fs.writeFileSync(sandbox.backupFile, '{"nope":1}');
  engine = new Engine({ config: { dataDir: sandbox.dataDir }, env: sandbox.env });
  t.after(() => engine.close());
  const handlers = createHandlers({ engine });
  let response = await handlers.state(new Request(`http://dsh.local${STATE_PATH}`));
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.ok, false);
  assert.match(body.message, /没有可恢复的有效 JSON/);
  response = await handlers.action(jsonRequest(ACTION_PATH, { rev: 0, type: 'settings' }));
  assert.equal(response.status, 503);
});

test('引擎：同 namespace 第二个实例被拒绝（冲突），关闭后释放', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const first = await openEngine(sandbox);
  const second = new Engine({ config: { dataDir: sandbox.dataDir }, env: sandbox.env });
  await assert.rejects(second.ready(), (error) => {
    assert.equal(error.code, 'conflict');
    assert.match(error.message, /占用/);
    return true;
  });
  await first.close();
  assert.equal(fs.existsSync(sandbox.lockFile), false);
  const third = await openEngine(sandbox);
  await third.close();
});

test('引擎：自定义 dataNamespace 写入对应文件', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = await openEngine(sandbox, { dataNamespace: 'custom_ns' });
  t.after(() => engine.close());
  assert.equal(fs.existsSync(path.join(sandbox.storageDir, 'custom_ns.json')), true);
  assert.equal(fs.existsSync(path.join(sandbox.storageDir, 'vocab_app_default.json')), false);
});

test('选择题模式：dontknow 等同选「不认识」并标记作答', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    await act(engine, 'settings');
    await act(engine, 'studyMode', { key: 'choice' });
    await act(engine, 'closeSettings');
    assert.equal(engine.view().screen, 'choice');
    const result = await act(engine, 'dontknow');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'choice_back');
    const correct = engine.ep.choice.correct;
    assert.equal(engine.view().options[correct].state, 'ok');
    const next = await act(engine, 'next');
    assert.equal(next.ok, true);
  });
});

test('测评：从选书页开始后暂停，回到首次引导（不是设置页）', async (t) => {
  await withEngine(t, async (engine) => {
    await beginQuiz(engine);
    const result = await act(engine, 'quizPause');
    assert.equal(result.ok, true, result.message);
    assert.equal(engine.view().screen, 'books');
    assert.equal(engine.view().rows.length > 0, true);
  });
});

test('动作字段校验：非法 payload 返回 invalid 且不改状态', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    const rev = engine.revision;
    const cases = [
      ['answer', { action: 'know' }],
      ['windowSize', { key: 'huge' }],
      ['quizAnswer', { index: 9 }],
      ['prediction', { strategy: 'bogus' }],
      ['catalogFilter', { category: 'all' }],
      ['book', { id: 42 }],
      ['deleteHistory', { index: 0 }],
    ];
    for (const [type, payload] of cases) {
      const result = await act(engine, type, payload);
      assert.equal(result.ok, false, `${type} 应被拒绝`);
      assert.equal(result.code, 'invalid', `${type} 的 code 应为 invalid`);
      assert.equal(engine.revision, rev, `${type} 不得改状态`);
    }
  });
});

test('插件入口：注册两个 exact 路由，卸载时注销并释放进程锁', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const previous = process.env.DSH_VOCAB_DATA_DIR;
  process.env.DSH_VOCAB_DATA_DIR = sandbox.storageDir;
  const routes = [];
  const cleanups = [];
  const ctx = {
    connection: {
      fetch: {
        register(route) {
          routes.push(route);
          return () => {
            route.disposed = true;
          };
        },
      },
    },
    effect(factory) {
      const cleanup = factory();
      cleanups.push(cleanup);
      return () => {
        if (typeof cleanup === 'function') cleanup();
      };
    },
  };
  try {
    const module = await import('../index.js');
    assert.equal(module.name, 'vocab-app');
    assert.deepEqual(module.inject, ['connection']);
    assert.throws(() => module.apply(ctx, { dataNamespace: 'Bad' }), /dataNamespace/);
    const engine = module.apply(ctx, { dataDir: sandbox.dataDir });
    await engine.ready();
    assert.equal(routes.length, 2);
    const stateRoute = routes.find((route) => route.path === STATE_PATH);
    const actionRoute = routes.find((route) => route.path === ACTION_PATH);
    assert.ok(stateRoute && actionRoute);
    assert.deepEqual(stateRoute.methods, ['GET']);
    assert.deepEqual(actionRoute.methods, ['POST']);
    assert.equal(stateRoute.requestBody, 'buffered');
    assert.equal(actionRoute.requestBody, 'buffered');

    let response = await stateRoute.fetch(new Request(`http://dsh.local${STATE_PATH}`));
    assert.equal(response.status, 200);
    const state = await response.json();
    assert.equal(state.view.screen, 'books');

    response = await actionRoute.fetch(new Request(`http://dsh.local${ACTION_PATH}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ rev: state.rev, type: 'settings', payload: {} }),
    }));
    assert.equal(response.status, 200);
    const action = await response.json();
    assert.equal(action.ok, true);
    assert.equal(action.view.screen, 'settings');

    for (const cleanup of cleanups) {
      if (typeof cleanup === 'function') cleanup();
    }
    assert.equal(routes.every((route) => route.disposed === true), true);
    assert.equal(fs.existsSync(sandbox.lockFile), false);
  } finally {
    if (previous === undefined) delete process.env.DSH_VOCAB_DATA_DIR;
    else process.env.DSH_VOCAB_DATA_DIR = previous;
  }
});

test('引擎：失效词书 id 在启动时解析为真实词书，避免队列分叉', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const doc = {
    schema: 1,
    revision: 3,
    updatedAt: 100,
    progress: {
      book_confirmed: true,
      book: 'no-such-book-id',
      states: {},
      cursors: {},
      orders: {},
      study_records: {},
      _v142_test_reset: 1,
      memory_schema: 2,
      study_mode: 'brush',
      theme: 'light',
    },
    window: { version: 1, preferred_compact: false },
  };
  fs.writeFileSync(sandbox.storageFile, JSON.stringify(doc));
  const engine = await openEngine(sandbox);
  t.after(() => engine.close());
  const expected = engine.dataset.defaultBookId();
  assert.equal(engine.doc.progress.book, expected);
  assert.equal(engine.view().screen === 'front' || engine.view().screen === 'empty', true);
  assert.ok(engine.doc.progress.study_records[expected], '学习队列应挂在解析后的词书 id 上');
});

test('固定学习键位：视图提供 DEFAULT_BINDINGS/keyCaptions，不读旧存盘自定义配置', async (t) => {
  await withEngine(t, async (engine) => {
    await navToBook(engine);
    await act(engine, 'start');
    const view = engine.view();
    assert.deepEqual(view.keys, {
      remember: 'Enter',
      forget: 'Space',
      choice1: '1',
      choice2: '2',
      choice3: '3',
      choice4: '4',
      unknown: 'Space',
      next: 'Enter',
    });
    assert.deepEqual(view.keyCaptions, {
      remember: 'Enter',
      forget: '空格',
      choice1: '1',
      choice2: '2',
      choice3: '3',
      choice4: '4',
      unknown: '空格',
      next: 'Enter',
    });
    // 刷词 back：左侧选错了(Space)、右侧下一个(Enter)，提示来自固定键位
    await act(engine, 'answer', { action: 'remember' });
    assert.equal(engine.view().labels.wrong, '选错了');
    assert.equal(engine.view().labels.next, '下一个');
    assert.equal(engine.view().keyCaptions.forget, '空格');
    assert.equal(engine.view().keyCaptions.next, 'Enter');
    // 设置页不再提供动态键位编辑字段
    await act(engine, 'settings');
    assert.equal('keyBindings' in engine.view(), false);
  });
});

test('keyCaption 固定展示文案', () => {
  assert.equal(keyCaption('Space'), '空格');
  assert.equal(keyCaption('Return'), 'Enter');
  assert.equal(keyCaption('Enter'), 'Enter');
  assert.equal(keyCaption(''), '');
});

// ---------------------------------------------------------------------------
// 锁协议 / 宿主生命周期（task-5）
// ---------------------------------------------------------------------------
function findDeadPid() {
  const candidates = [9999999];
  for (let index = 0; index < 40; index += 1) candidates.push(process.pid + 100000 + index);
  for (const pid of candidates) {
    if (pid === process.pid) continue;
    try {
      process.kill(pid, 0);
    } catch (error) {
      if (error && error.code === 'ESRCH') return pid;
    }
  }
  throw new Error('找不到可用的“已退出”pid');
}

function lockJson(namespace, overrides = {}) {
  return JSON.stringify({
    version: 1,
    kind: 'lock',
    namespace,
    pid: process.pid,
    host: os.hostname(),
    token: `token-${Math.random().toString(16).slice(2)}`,
    createdAt: Math.floor(Date.now() / 1000),
    ...overrides,
  });
}

function guardJson(namespace, overrides = {}) {
  return lockJson(namespace, {
    kind: 'guard',
    token: `guard-${Math.random().toString(16).slice(2)}`,
    ...overrides,
  });
}

function ageFile(file, seconds) {
  const stamp = new Date(Date.now() - seconds * 1000);
  fs.utimesSync(file, stamp, stamp);
}

function lockLeftovers(dir) {
  return fs.readdirSync(dir).filter(
    (name) => /(?:\.tmp-|\.guard$|\.guard\.|\.orphan-)/.test(name),
  );
}

test('锁：正常获取时锁内容是完整 JSON，释放后不残留临时文件/guard', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const store = Store.open({ env: sandbox.env });
  const raw = fs.readFileSync(sandbox.lockFile, 'utf8');
  const data = JSON.parse(raw);
  assert.equal(data.version, 1);
  assert.equal(data.kind, 'lock');
  assert.equal(data.namespace, 'vocab_app_default');
  assert.equal(data.pid, process.pid);
  assert.equal(data.host, os.hostname());
  assert.equal(typeof data.token, 'string');
  assert.equal(data.token.length, 32);
  assert.deepEqual(lockLeftovers(sandbox.storageDir), []);
  store.close();
  assert.equal(fs.existsSync(sandbox.lockFile), false);
  assert.deepEqual(lockLeftovers(sandbox.storageDir), []);
});

test('锁：新鲜的空锁/坏锁只拒绝，不删除（防止抢走正在写入的锁）', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  fs.writeFileSync(sandbox.lockFile, '');
  assert.throws(() => Store.open({ env: sandbox.env, guardWaitMs: 80 }), (error) => {
    assert.ok(error instanceof LockError);
    assert.equal(error.code, 'conflict');
    assert.match(error.message, /尚未写完|正在建立/);
    return true;
  });
  assert.equal(fs.readFileSync(sandbox.lockFile, 'utf8'), '');

  fs.writeFileSync(sandbox.lockFile, '这不是 JSON');
  assert.throws(() => Store.open({ env: sandbox.env, guardWaitMs: 80 }), (error) => {
    assert.ok(error instanceof LockError);
    assert.match(error.message, /尚未写完|正在建立/);
    return true;
  });
  assert.equal(fs.readFileSync(sandbox.lockFile, 'utf8'), '这不是 JSON');
});

test('锁：陈旧的空锁/坏锁也拒绝自动清理并告知手动删除路径', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  fs.writeFileSync(sandbox.lockFile, '');
  ageFile(sandbox.lockFile, 60);
  assert.throws(() => Store.open({ env: sandbox.env }), (error) => {
    assert.ok(error instanceof LockError);
    assert.match(error.message, /无法识别/);
    assert.match(error.message, /手动删除/);
    return true;
  });
  assert.equal(fs.readFileSync(sandbox.lockFile, 'utf8'), '');
});

test('锁：可证明陈旧（同主机 pid 已退出）的锁在 guard 保护下接管', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const deadPid = findDeadPid();
  fs.writeFileSync(sandbox.lockFile, lockJson('vocab_app_default', { pid: deadPid, token: 'old-token' }));
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).token, 'old-token');
  const store = Store.open({ env: sandbox.env });
  t.after(() => {
    try {
      store.close();
    } catch {
      /* ignore */
    }
  });
  const data = JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8'));
  assert.notEqual(data.token, 'old-token');
  assert.equal(data.pid, process.pid);
  assert.equal(fs.existsSync(`${sandbox.lockFile}.guard`), false);
  assert.deepEqual(lockLeftovers(sandbox.storageDir), []);
});

test('锁：另一存活实例正持 guard 接管时安全失败，不删除陈旧锁', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const deadPid = findDeadPid();
  fs.writeFileSync(sandbox.lockFile, lockJson('vocab_app_default', { pid: deadPid, token: 'old-token' }));
  fs.writeFileSync(`${sandbox.lockFile}.guard`, guardJson('vocab_app_default'));
  assert.throws(() => Store.open({ env: sandbox.env, guardWaitMs: 120 }), (error) => {
    assert.ok(error instanceof LockError);
    assert.match(error.message, /正在接管/);
    return true;
  });
  // 双方文件都被保留，绝不删除
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).token, 'old-token');
  assert.equal(fs.existsSync(`${sandbox.lockFile}.guard`), true);

  // 竞争者退出/清理后可以正常接管
  fs.unlinkSync(`${sandbox.lockFile}.guard`);
  const store = Store.open({ env: sandbox.env, guardWaitMs: 120 });
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).pid, process.pid);
  store.close();
});

test('锁：陈旧/无法确认的 guard 一律 fail-closed，保留文件并提示手动清理', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const deadPid = findDeadPid();
  fs.writeFileSync(sandbox.lockFile, lockJson('vocab_app_default', { pid: deadPid, token: 'old-token' }));
  fs.writeFileSync(
    `${sandbox.lockFile}.guard`,
    guardJson('vocab_app_default', { pid: deadPid, token: 'dead-guard' }),
  );
  assert.throws(() => Store.open({ env: sandbox.env, guardWaitMs: 120 }), (error) => {
    assert.ok(error instanceof LockError);
    assert.match(error.message, /不会自动清理 guard/);
    assert.match(error.message, /手动删除/);
    return true;
  });
  // 不自动 rename/删除任何一方：陈旧锁与 guard 原文都必须保留
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).token, 'old-token');
  assert.equal(
    JSON.parse(fs.readFileSync(`${sandbox.lockFile}.guard`, 'utf8')).token,
    'dead-guard',
  );

  // 用户确认无实例后手动删除 guard，才允许陈旧锁接管
  fs.unlinkSync(`${sandbox.lockFile}.guard`);
  const store = Store.open({ env: sandbox.env, guardWaitMs: 120 });
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).pid, process.pid);
  assert.equal(fs.existsSync(`${sandbox.lockFile}.guard`), false);
  store.close();
});

test('锁：内容无法识别的 guard 不自动清理，安全失败', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const deadPid = findDeadPid();
  fs.writeFileSync(sandbox.lockFile, lockJson('vocab_app_default', { pid: deadPid }));
  fs.writeFileSync(`${sandbox.lockFile}.guard`, '');
  assert.throws(() => Store.open({ env: sandbox.env, guardWaitMs: 100 }), (error) => {
    assert.ok(error instanceof LockError);
    assert.match(error.message, /无法确认其持有者仍在运行/);
    assert.match(error.message, /手动删除/);
    return true;
  });
  assert.equal(fs.readFileSync(`${sandbox.lockFile}.guard`, 'utf8'), '');
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).pid, deadPid);
});

test('锁：释放时 unlink 失败走 rename 兜底并可立即重新打开', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const store = Store.open({ env: sandbox.env });
  store.fault = (stage) => {
    if (stage === 'lock-unlink') {
      const error = new Error('模拟文件被占用');
      error.code = 'EBUSY';
      throw error;
    }
  };
  store.close();
  assert.equal(fs.existsSync(sandbox.lockFile), false, '兜底后锁文件名必须重新可用');
  const reopened = Store.open({ env: sandbox.env });
  assert.equal(JSON.parse(fs.readFileSync(sandbox.lockFile, 'utf8')).pid, process.pid);
  reopened.close();
});

test('引擎：数据加载期间卸载立即释放锁，之后不会补取锁', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = new Engine({ config: { dataDir: sandbox.dataDir }, env: sandbox.env });
  let releaseLoad = null;
  let markStarted = null;
  const started = new Promise((resolve) => {
    markStarted = resolve;
  });
  const originalLoad = engine.dataset.load.bind(engine.dataset);
  engine.dataset.load = async () => {
    markStarted();
    await new Promise((resolve) => {
      releaseLoad = resolve;
    });
    return originalLoad();
  };
  const readyPromise = engine.ready();
  await started;
  assert.equal(fs.existsSync(sandbox.lockFile), true, '数据加载期间应已持有锁');
  await engine.close();
  assert.equal(fs.existsSync(sandbox.lockFile), false, '卸载应立即释放锁');
  releaseLoad();
  await assert.rejects(readyPromise, (error) => {
    assert.equal(error.code, 'conflict');
    assert.match(error.message, /插件已停止/);
    return true;
  });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(fs.existsSync(sandbox.lockFile), false, '关闭后不得补取锁');
  const again = await openEngine(sandbox);
  await again.close();
});

test('引擎：卸载后 ready/state/action 一律拒绝，close 幂等', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = await openEngine(sandbox);
  await engine.close();
  await engine.close();
  assert.equal(engine.closed, true);
  assert.equal(fs.existsSync(sandbox.lockFile), false);
  await assert.rejects(engine.ready(), /插件已停止/);
  assert.throws(() => engine.state(), /插件已停止/);
  await assert.rejects(engine.applyAction({ rev: 0, type: 'settings' }), /插件已停止/);
});

test('引擎：初始化在取锁后失败会释放锁（不留半初始化锁）', async (t) => {  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const failingDataset = {
    load: async () => {
      throw new Error('模拟词库加载失败');
    },
  };
  const engine = new Engine({
    config: { dataDir: sandbox.dataDir },
    env: sandbox.env,
    dataset: failingDataset,
  });
  t.after(() => engine.close());
  await assert.rejects(engine.ready(), /模拟词库加载失败/);
  assert.equal(fs.existsSync(sandbox.lockFile), false);
  // 失败后其它实例仍可正常打开
  const again = await openEngine(sandbox);
  await again.close();
});

// ---------------------------------------------------------------------------
// 插件入口：路由注册失败/卸载 disposer 抛错时的生命周期边界
// ---------------------------------------------------------------------------
function mockPluginContext({ failOnRegister = 0, throwOnDispose = false, failOnEffect = 0 } = {}) {
  const routes = [];
  const disposed = [];
  const effects = [];
  let registerCalls = 0;
  let effectCalls = 0;
  const ctx = {
    connection: {
      fetch: {
        register(route) {
          registerCalls += 1;
          if (failOnRegister && registerCalls === failOnRegister) {
            throw new Error('模拟第二个路由注册失败');
          }
          routes.push(route);
          return () => {
            disposed.push(route.path);
            if (throwOnDispose) throw new Error('模拟 disposer 抛错');
          };
        },
      },
    },
    effect(factory, label) {
      effectCalls += 1;
      if (failOnEffect && effectCalls === failOnEffect) {
        // 模拟 cordis 在 factory 成功后仍注册失败：cleanup 被丢弃。
        factory();
        throw new Error('模拟 effect 注册失败');
      }
      const cleanup = factory();
      effects.push({ label, cleanup });
      return () => {
        if (typeof cleanup === 'function') cleanup();
      };
    },
  };
  return {
    ctx,
    routes,
    disposed,
    effects,
    registerCalls: () => registerCalls,
  };
}

async function withPluginEnv(t) {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const previous = process.env.DSH_VOCAB_DATA_DIR;
  process.env.DSH_VOCAB_DATA_DIR = sandbox.storageDir;
  return {
    sandbox,
    restore() {
      if (previous === undefined) delete process.env.DSH_VOCAB_DATA_DIR;
      else process.env.DSH_VOCAB_DATA_DIR = previous;
    },
  };
}

test('插件入口：第二个路由注册抛错时回滚已注册路由并释放记录锁', async (t) => {
  const { sandbox, restore } = await withPluginEnv(t);
  try {
    const module = await import('../index.js');
    const mock = mockPluginContext({ failOnRegister: 2 });
    assert.throws(
      () => module.apply(mock.ctx, { dataDir: sandbox.dataDir }),
      /模拟第二个路由注册失败/,
    );
    // 只成功注册了 state；action 失败后它必须被注销
    assert.equal(mock.routes.length, 1);
    assert.equal(mock.routes[0].path, STATE_PATH);
    assert.deepEqual(mock.disposed, [STATE_PATH]);
    // 引擎生命周期 effect 在路由 effect 之前独立注册（此时路由 effect 尚未建立）
    assert.equal(mock.effects.length, 1);
    assert.match(String(mock.effects[0].label), /engine lifecycle/);
    // engine.ready() 已同步取锁，注册失败路径必须立刻关闭并释放
    assert.equal(fs.existsSync(sandbox.lockFile), false);
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(fs.existsSync(sandbox.lockFile), false, '失败后不得补取锁');
    // 锁已释放，其它实例可正常打开
    const again = await openEngine(sandbox);
    await again.close();
    // 独立 engine effect 的 cleanup 幂等
    assert.doesNotThrow(() => mock.effects[0].cleanup());
  } finally {
    restore();
  }
});

test('插件入口：第一个路由注册抛错时也关闭引擎并释放锁', async (t) => {
  const { sandbox, restore } = await withPluginEnv(t);
  try {
    const module = await import('../index.js');
    const mock = mockPluginContext({ failOnRegister: 1 });
    assert.throws(
      () => module.apply(mock.ctx, { dataDir: sandbox.dataDir }),
      /模拟第二个路由注册失败/,
    );
    assert.equal(mock.routes.length, 0);
    assert.deepEqual(mock.disposed, []);
    assert.equal(fs.existsSync(sandbox.lockFile), false);
    const again = await openEngine(sandbox);
    await again.close();
  } finally {
    restore();
  }
});

test('插件入口：卸载 disposer 抛错时仍注销另一路由并关闭/释放引擎', async (t) => {
  const { sandbox, restore } = await withPluginEnv(t);
  try {
    const module = await import('../index.js');
    const mock = mockPluginContext({ throwOnDispose: true });
    const engine = module.apply(mock.ctx, { dataDir: sandbox.dataDir });
    await engine.ready();
    assert.equal(fs.existsSync(sandbox.lockFile), true);
    const routeEffect = mock.effects.find((effect) => String(effect.label).includes('/api/vocab-app'));
    assert.ok(routeEffect && typeof routeEffect.cleanup === 'function');
    // 两个 disposer 都抛错：cleanup 本身不得抛出，且必须 finally 关闭引擎
    assert.doesNotThrow(() => routeEffect.cleanup());
    assert.deepEqual(mock.disposed, [ACTION_PATH, STATE_PATH], '单个 disposer 失败不得跳过其它路由');
    assert.equal(engine.closed, true);
    assert.equal(fs.existsSync(sandbox.lockFile), false);
    // engine 生命周期 effect 的 cleanup 幂等
    const lifecycle = mock.effects.find((effect) => String(effect.label).includes('engine lifecycle'));
    assert.ok(lifecycle && typeof lifecycle.cleanup === 'function');
    assert.doesNotThrow(() => lifecycle.cleanup());
    assert.equal(engine.closed, true);
  } finally {
    restore();
  }
});

test('插件入口：ctx.effect 自身失败（路由 effect）仍注销路由、关闭引擎并释放锁', async (t) => {
  const { sandbox, restore } = await withPluginEnv(t);
  try {
    const module = await import('../index.js');
    const mock = mockPluginContext({ failOnEffect: 2 });
    assert.throws(
      () => module.apply(mock.ctx, { dataDir: sandbox.dataDir }),
      /模拟 effect 注册失败/,
    );
    // factory 已成功注册两个路由，但 ctx.effect 失败丢弃 cleanup：apply 的外层
    // catch 必须主动注销两条路由并关闭引擎。
    assert.equal(mock.routes.length, 2);
    assert.deepEqual(mock.disposed, [ACTION_PATH, STATE_PATH]);
    assert.equal(mock.effects.length, 1, '只有 engine lifecycle effect 成功建立');
    assert.equal(fs.existsSync(sandbox.lockFile), false);
    const again = await openEngine(sandbox);
    await again.close();
  } finally {
    restore();
  }
});

test('插件入口：ctx.effect 自身失败（engine lifetime effect）仍关闭引擎释放锁', async (t) => {
  const { sandbox, restore } = await withPluginEnv(t);
  try {
    const module = await import('../index.js');
    const mock = mockPluginContext({ failOnEffect: 1 });
    assert.throws(
      () => module.apply(mock.ctx, { dataDir: sandbox.dataDir }),
      /模拟 effect 注册失败/,
    );
    // engine 生命周期 effect 是第一个注册项：它失败时不应继续注册路由。
    assert.equal(mock.routes.length, 0);
    assert.deepEqual(mock.disposed, []);
    assert.equal(mock.effects.length, 0);
    assert.equal(fs.existsSync(sandbox.lockFile), false);
    const again = await openEngine(sandbox);
    await again.close();
  } finally {
    restore();
  }
});

test('引擎：卸载后排队中的动作不得继续落盘或推进 revision', async (t) => {
  const sandbox = createSandbox();
  t.after(() => sandbox.cleanup());
  const engine = await openEngine(sandbox);
  await navToBook(engine);
  await act(engine, 'start');
  const rev = engine.revision;
  const before = fs.readFileSync(sandbox.storageFile, 'utf8');
  // 先入队一个会落盘的动作，再在它真正执行前卸载插件。
  const pending = engine.applyAction({
    rev,
    type: 'answer',
    payload: { action: 'remember' },
  });
  await engine.close();
  const result = await pending;
  assert.equal(result.ok, false);
  assert.equal(result.code, 'conflict');
  assert.match(result.message, /插件已停止/);
  assert.equal(engine.revision, rev);
  assert.equal(fs.readFileSync(sandbox.storageFile, 'utf8'), before, '卸载后不得再写记录文件');
  assert.equal(fs.existsSync(sandbox.lockFile), false);
});



// 0.1.2 的未知第五行是展示改变，不是第五个猜测释义。
test('0.1.2 Quiz unknownPicked 只表示选择，不泄露对错，下一题清零', async (t) => {
  await withEngine(t, async (engine) => {
    await beginQuiz(engine);
    assert.equal(engine.view().unknownPicked, false);
    assert.equal(engine.view().options.length, 4);
    assert.equal((await act(engine, 'quizDontknow')).ok, true);
    let view = engine.view();
    assert.equal(view.locked, true);
    assert.equal(view.unknownPicked, true);
    assert.equal(view.options.length, 4);
    assert.equal(view.options.every((option) => option.state === ''), true);
    assert.equal(view.options.some((option) => 'correct' in option), false);
    assert.equal(engine.ep.quiz.picked, -1);
    // 原未知会话编码仍为-1，和答错0的后验能力证据一致，不改成五选一。
    assert.equal(engine.ep.quiz.resp.at(-1), -1);
    const vt = engine.dataset.vocabularyTest;
    assert.equal(vt.C, 0.25);
    const wrongEvidence = vt.summarize(engine.dataset.getQuizBank(), engine.ep.quiz.items, [0]);
    assert.equal(engine.ep.quiz.state.theta, wrongEvidence.theta);
    assert.equal(engine.ep.quiz.state.se, wrongEvidence.se);
    assert.equal((await act(engine, 'next')).ok, true);
    view = engine.view();
    assert.equal(view.unknownPicked, false);
    assert.equal(view.locked, false);
    assert.equal((await act(engine, 'quizAnswer', { index: 0 })).ok, true);
    view = engine.view();
    assert.equal(view.unknownPicked, false);
    assert.equal(view.options[0].state, 'picked');
    assert.equal(view.options.some((option) => option.state === 'correct' || option.state === 'wrong'), false);
    const noQuiz = engine._view_quiz(engine.doc.progress, { ...engine.ep, quiz: null });
    assert.equal(noQuiz.unknownPicked, false);
  });
});

test('0.1.5 旧窗口偏好只读显示mini：启动/GET/拒绝动作不写主档或备份，完整保留学习/测评/扩展', async (t) => {
  const cases = [
    ...['mini', 'small', 'medium', 'large'].map((size) => [size, {
      version: 2, size, w: 999, h: 888, external_future: { placement: ['left', 23] },
    }]),
    ['v1', { version: 1, preferred_compact: true, normal_w: 520, compact: true }],
    ['empty', {}],
    ['unknown', { version: 2, size: 'future-size', w: 123, h: 456, external_future: { keep: true } }],
  ];
  for (const [label, legacyWindow] of cases) {
    await t.test(label, async (st) => {
      const sandbox = createSandbox();
      st.after(() => sandbox.cleanup());
      let engine = await openEngine(sandbox);
      try {
        await navToBook(engine);
        await act(engine, 'start');
        await act(engine, 'answer', { action: 'remember' });
        await act(engine, 'next');
        await act(engine, 'settings');
        await beginQuiz(engine);
        await act(engine, 'quizDontknow');
        await act(engine, 'next');
        await act(engine, 'quizPause');
        const old = structuredClone(engine.doc);
        old.window = structuredClone(legacyWindow);
        old.progress.external_future = { untouched: true };
        await engine.close();
        fs.writeFileSync(sandbox.storageFile, JSON.stringify(old, null, 2) + '\n');
        const mainBefore = fs.readFileSync(sandbox.storageFile);
        const backupBefore = fs.existsSync(sandbox.backupFile) ? fs.readFileSync(sandbox.backupFile) : null;
        const save = st.mock.method(Store.prototype, 'save');
        engine = await openEngine(sandbox);
        assert.equal(save.mock.callCount(), 0, '仅有旧window偏好不得触发启动迁移写入');
        assert.deepEqual(engine.doc, old, '包含未知字段和时间戳的完整文档保持不变');
        assert.equal(engine.revision, old.revision);
        assert.equal(engine.view().windowSize, 'mini');
        assert.deepEqual(engine.doc.window, old.window, '窗口偏好仅在视图归一，不写回旧文档');
        assert.deepEqual(engine.view().windowPresets, [{ key: 'mini', label: '迷你', width: 400, height: 400 }]);
        assert.deepEqual(fs.readFileSync(sandbox.storageFile), mainBefore, '主档保留原始字节与格式');
        assert.deepEqual(fs.existsSync(sandbox.backupFile) ? fs.readFileSync(sandbox.backupFile) : null, backupBefore);
        const before = clockedSnapshot(engine, sandbox);
        const handlers = createHandlers({ engine });
        const response = await handlers.state(new Request(`http://dsh.local${STATE_PATH}`));
        assert.equal(response.status, 200);
        const body = await response.json();
        assert.equal(body.rev, old.revision);
        assert.equal(body.view.windowSize, 'mini');
        assert.deepEqual(body.view.windowPresets, [{ key: 'mini', label: '迷你', width: 400, height: 400 }]);
        assertClockedUnchanged(engine, sandbox, before);
        for (const payload of [{ key: 'mini' }, { key: 'small' }, { key: 'medium' }, { key: 'large' }, {}]) {
          const result = await act(engine, 'windowSize', payload);
          assert.equal(result.ok, false);
          assert.equal(result.code, 'invalid');
          assertClockedUnchanged(engine, sandbox, before);
        }
        assert.equal((await act(engine, 'method')).code, 'invalid');
        assertClockedUnchanged(engine, sandbox, before);
        assert.equal(save.mock.callCount(), 0, '只读GET与退役动作均不得调用存储保存');
        await engine.close();
        assert.deepEqual(fs.readFileSync(sandbox.storageFile), mainBefore, '关闭引擎不迁移旧窗口偏好');
        assert.deepEqual(fs.existsSync(sandbox.backupFile) ? fs.readFileSync(sandbox.backupFile) : null, backupBefore);
      } finally { await engine.close(); }
    });
  }
});

// v0.1.3 regressions: fake DSH_HOME, synthetic datasets, injected clocks only.
async function withClockedEngine(t, fn) {
  const sandbox = createSandbox();
  sandbox.env.DSH_HOME = path.join(sandbox.root, 'fake-dsh-home');
  const clock = { now: 1700000000 };
  const engines = [];
  async function reopen() {
    const engine = new Engine({
      config: { dataDir: sandbox.dataDir }, env: sandbox.env, now: () => clock.now,
    });
    engines.push(engine);
    await engine.ready();
    return engine;
  }
  t.after(async () => {
    for (const engine of engines.reverse()) await engine.close();
    sandbox.cleanup();
  });
  return fn(await reopen(), sandbox, clock, reopen);
}

function clockedSnapshot(engine, sandbox) {
  return {
    rev: engine.revision, doc: structuredClone(engine.doc), ep: structuredClone(engine.ep),
    main: fs.readFileSync(sandbox.storageFile),
    backup: fs.existsSync(sandbox.backupFile) ? fs.readFileSync(sandbox.backupFile) : null,
  };
}

function assertClockedUnchanged(engine, sandbox, before, refreshedBackup = false) {
  assert.equal(engine.revision, before.rev);
  assert.deepEqual(engine.doc, before.doc);
  assert.deepEqual(engine.ep, before.ep);
  assert.deepEqual(fs.readFileSync(sandbox.storageFile), before.main);
  assert.deepEqual(fs.existsSync(sandbox.backupFile) ? fs.readFileSync(sandbox.backupFile) : null,
    refreshedBackup ? before.main : before.backup);
}

async function clockedGet(engine, sandbox) {
  const before = clockedSnapshot(engine, sandbox);
  const response = await createHandlers({ engine }).state(new Request(`http://dsh.local${STATE_PATH}`));
  assert.equal(response.status, 200);
  const body = await response.json();
  assertClockedUnchanged(engine, sandbox, before);
  return body;
}

test('Host v0.1.3: 旧词连续三轮300秒重试优先新词，认识才恢复新等级长间隔', async (t) => {
  await withClockedEngine(t, async (engine, sandbox, clock) => {
    await navToBook(engine);
    const key = sandbox.synthetic.words[0];
    engine.doc.progress.states[key] = {
      lv: 7, st: 'learning', due: clock.now - 1, seen: 7, lapse: 2, streak: 0,
      future: { keep: ['old-word'] },
    };
    assert.equal((await act(engine, 'start')).ok, true);
    assert.equal(engine.view().word.w, key);
    assert.equal(engine.view().kind, 'review');
    const ledger = structuredClone(engine.doc.progress.daily_new_ledger);
    for (let round = 0; round < 3; round += 1) {
      const answeredAt = clock.now;
      const result = await act(engine, 'answer', { action: 'forget' });
      assert.equal(result.ok, true, result.message);
      const state = engine.doc.progress.states[key];
      assert.equal(state.lv, 7);
      assert.equal(state.st, 'learning');
      assert.equal(state.due, answeredAt + 300);
      assert.equal(state.seen, 8 + round);
      assert.equal(state.lapse, 3 + round);
      assert.equal(state.streak, 1 + round);
      assert.deepEqual(state.future, { keep: ['old-word'] });
      assert.equal(engine.view().canCorrect, false, 'forget must never permit one-way correct');
      assert.deepEqual(engine.doc.progress.daily_new_ledger, ledger);
      assert.equal(engine.doc.progress.study_records['tb-1'].new_count, 0);
      assert.deepEqual(engine.doc.progress.study_records['tb-1'].pending, {});
      clock.now = answeredAt + 299;
      assert.equal((await clockedGet(engine, sandbox)).view.screen, 'back');
      clock.now += 1;
      assert.equal((await clockedGet(engine, sandbox)).view.screen, 'back', 'GET must not replace the current card');
      assert.equal((await act(engine, 'next')).ok, true);
      assert.equal(engine.view().word.w, key, 'due old word must precede all fresh words');
      assert.equal(engine.view().kind, 'review');
    }
    const rememberedAt = clock.now;
    assert.equal((await act(engine, 'answer', { action: 'remember' })).ok, true);
    assert.equal(engine.doc.progress.states[key].lv, 8);
    assert.equal(engine.doc.progress.states[key].due, rememberedAt + 15 * 86400);
    assert.equal((await act(engine, 'next')).ok, true);
    assert.notEqual(engine.view().word.w, key);
    assert.equal(engine.view().kind, 'new');
    assert.deepEqual(engine.doc.progress.daily_new_ledger, ledger);
    assert.equal(engine.doc.progress.study_records['tb-1'].new_count, 0);
  });
});

test('Host v0.1.3: 已保存new/retry队列升级保留due/未知字段，到期held并原样恢复', async (t) => {
  for (const kind of ['new', 'retry']) {
    await t.test(kind, async (st) => {
      await withClockedEngine(st, async (first, sandbox, clock, reopen) => {
        let engine = first;
        await navToBook(engine);
        const [old, current] = sandbox.synthetic.words;
        const savedDue = clock.now + 12 * 3600;
        engine.doc.progress.states[old] = {
          lv: 3, st: 'learning', due: savedDue, seen: 5, lapse: 1, streak: 0,
          future: { from: 'saved-before-0.1.3' },
        };
        if (kind === 'retry') engine.doc.progress.states[current] = {
          lv: 0, st: 'new', due: null, seen: 2, lapse: 2, streak: 2,
        };
        engine.doc.progress.study_records['tb-1'] = {
          cursor: 1, new_count: 13, pending: kind === 'retry' ? { [current]: 15 } : {},
          current: { kind, key: current, future: { unanswered: kind } },
          held_current: null, last_retry: null,
        };
        assert.equal((await act(engine, 'start')).ok, true);
        assert.equal(engine.view().word.w, current);
        assert.equal(engine.view().kind, kind);
        const saved = structuredClone(engine.doc);
        saved.progress.external_future = { producer: 'saved-before-0.1.3' };
        saved.progress.study_records['tb-1'].current.future = { unanswered: kind };
        await engine.close();
        writeJson(sandbox.storageFile, saved);
        engine = await reopen();
        assert.equal(engine.doc.progress.states[old].due, savedDue, 'loading must not recompute saved due');
        assert.equal(engine.view().word.w, current);
        assert.deepEqual(engine.doc.progress.external_future, saved.progress.external_future);
        const ledger = structuredClone(engine.doc.progress.daily_new_ledger);
        const record = engine.doc.progress.study_records['tb-1'];
        const pending = structuredClone(record.pending);
        const cursor = record.cursor;
        clock.now = savedDue;
        const same = await clockedGet(engine, sandbox);
        assert.equal(same.view.word.w, current, 'GET/timer must never replace an unanswered new/retry');
        assert.equal(engine.doc.progress.study_records['tb-1'].held_current, null);
        await engine.close();
        engine = await reopen();
        assert.equal(engine.view().word.w, old);
        assert.equal(engine.view().kind, 'review');
        assert.equal(engine.doc.progress.states[old].due, savedDue, 'upgrade/startup must preserve existing due');
        assert.deepEqual(engine.doc.progress.study_records['tb-1'].held_current.future, { unanswered: kind });
        assert.equal((await act(engine, 'answer', { action: 'forget' })).ok, true);
        assert.equal(engine.doc.progress.states[old].due, savedDue + 300);
        assert.equal(engine.doc.progress.states[old].lv, 3);
        assert.equal((await act(engine, 'next')).ok, true);
        assert.equal(engine.view().word.w, current);
        assert.equal(engine.view().kind, kind);
        assert.deepEqual(engine.doc.progress.study_records['tb-1'].current.future, { unanswered: kind });
        assert.equal(engine.doc.progress.study_records['tb-1'].cursor, cursor);
        assert.equal(engine.doc.progress.study_records['tb-1'].new_count, 13);
        assert.deepEqual(engine.doc.progress.study_records['tb-1'].pending, pending);
        assert.deepEqual(engine.doc.progress.daily_new_ledger, ledger);
        assert.deepEqual(engine.doc.progress.external_future, saved.progress.external_future);
      });
    });
  }
});

test('Host v0.1.3: 旧词forget/undo/correct保存失败原子回滚，改判300秒且直接下一词', async (t) => {
  await withClockedEngine(t, async (engine, sandbox, clock) => {
    await navToBook(engine);
    const key = sandbox.synthetic.words[0];
    const original = {
      lv: 5, st: 'learning', due: clock.now - 1, seen: 4, lapse: 2, streak: 3,
      future: { keep: ['snapshot'] },
    };
    engine.doc.progress.states[key] = structuredClone(original);
    assert.equal((await act(engine, 'start')).ok, true);
    const ledger = structuredClone(engine.doc.progress.daily_new_ledger);
    async function failAction(type, payload = {}) {
      const before = clockedSnapshot(engine, sandbox);
      engine._store.fault = (stage) => { if (stage === 'write') throw new Error('v0.1.3 injected save failure'); };
      const result = await act(engine, type, payload);
      engine._store.fault = null;
      assert.equal(result.ok, false);
      assert.equal(result.code, 'failed');
      // The existing store refreshes .bak before its write-stage fault; it must
      // contain the last committed main, never the failed answer document.
      assertClockedUnchanged(engine, sandbox, before, true);
    }
    await failAction('answer', { action: 'forget' });
    assert.equal((await act(engine, 'answer', { action: 'forget' })).ok, true);
    assert.equal(engine.doc.progress.states[key].due, clock.now + 300);
    assert.equal(engine.view().canCorrect, false);
    await failAction('undo');
    assert.equal((await act(engine, 'undo')).ok, true);
    assert.deepEqual(engine.doc.progress.states[key], original);
    assert.equal(engine.view().word.w, key);
    assert.equal(engine.view().screen, 'front');
    assert.equal(engine.view().canUndo, false);
    clock.now += 9;
    assert.equal((await act(engine, 'answer', { action: 'remember' })).ok, true);
    assert.equal(engine.doc.progress.states[key].lv, 6);
    assert.equal(engine.doc.progress.states[key].due, clock.now + 4 * 86400);
    assert.equal(engine.view().canCorrect, true);
    clock.now += 17;
    await failAction('correct');
    assert.equal((await act(engine, 'correct')).ok, true);
    assert.deepEqual(engine.doc.progress.states[key], {
      ...original, due: clock.now + 300, seen: 5, lapse: 3, streak: 4,
    });
    assert.equal(engine.view().screen, 'front');
    assert.notEqual(engine.view().word.w, key, 'correct directly advances, never stays on meaning card');
    assert.equal(Boolean(engine.view().canCorrect), false);
    assert.deepEqual(engine.doc.progress.daily_new_ledger, ledger);
    assert.equal(engine.doc.progress.study_records['tb-1'].new_count, 0);
    assert.deepEqual(engine.doc.progress.study_records['tb-1'].pending, {});
    const beforeSecondCorrect = clockedSnapshot(engine, sandbox);
    assert.equal((await act(engine, 'correct')).ok, true);
    assertClockedUnchanged(engine, sandbox, beforeSecondCorrect);
  });
});

test('Host v0.1.3: lv9刚掌握可单向改判为同级300秒，无新词账本重计', async (t) => {
  await withClockedEngine(t, async (engine, sandbox, clock) => {
    await navToBook(engine);
    const key = sandbox.synthetic.words[0];
    engine.doc.progress.states[key] = { lv: 9, st: 'learning', due: clock.now - 1, seen: 9, lapse: 1, streak: 0 };
    assert.equal((await act(engine, 'start')).ok, true);
    const ledger = structuredClone(engine.doc.progress.daily_new_ledger);
    assert.equal((await act(engine, 'answer', { action: 'remember' })).ok, true);
    assert.equal(engine.doc.progress.states[key].lv, 10);
    assert.equal(engine.doc.progress.states[key].due, null);
    clock.now += 13;
    assert.equal((await act(engine, 'correct')).ok, true);
    assert.deepEqual(engine.doc.progress.states[key], {
      lv: 9, st: 'learning', due: clock.now + 300, seen: 10, lapse: 2, streak: 1,
    });
    assert.notEqual(engine.view().word.w, key);
    assert.deepEqual(engine.doc.progress.daily_new_ledger, ledger);
    assert.equal(engine.doc.progress.study_records['tb-1'].new_count, 0);
  });
});

test('Host v0.1.3: empty到期GET只读，正常POST next才唤醒并多轮五分钟复习', async (t) => {
  await withClockedEngine(t, async (engine, sandbox, clock) => {
    await navToBook(engine);
    const key = sandbox.synthetic.words[0];
    for (const word of sandbox.synthetic.words) engine.doc.progress.states[word] = {
      lv: 10, st: 'mastered', due: null, seen: 10, lapse: 0, streak: 0,
    };
    engine.doc.progress.states[key] = { lv: 7, st: 'learning', due: clock.now + 300, seen: 6, lapse: 0, streak: 0 };
    assert.equal((await act(engine, 'start')).ok, true);
    assert.equal(engine.view().screen, 'empty');
    const ledger = structuredClone(engine.doc.progress.daily_new_ledger);
    for (let round = 0; round < 3; round += 1) {
      clock.now += 300;
      assert.equal((await clockedGet(engine, sandbox)).view.screen, 'empty');
      const before = engine.revision;
      const response = await createHandlers({ engine }).action(new Request(`http://dsh.local${ACTION_PATH}`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ rev: before, type: 'next', payload: {} }),
      }));
      const body = await response.json();
      assert.equal(body.ok, true, body.message);
      assert.equal(body.rev, before + 1);
      assert.equal(body.view.screen, 'front');
      assert.equal(body.view.word.w, key);
      assert.equal(body.view.kind, 'review');
      assert.equal(readStorage(sandbox.storageFile).revision, body.rev);
      assert.deepEqual(readStorage(sandbox.storageFile).progress.study_records['tb-1'].current, engine.doc.progress.study_records['tb-1'].current);
      assert.equal((await act(engine, 'answer', { action: 'forget' })).ok, true);
      assert.equal(engine.doc.progress.states[key].lv, 7);
      assert.equal(engine.doc.progress.states[key].due, clock.now + 300);
      assert.equal((await act(engine, 'next')).ok, true);
      assert.equal(engine.view().screen, 'empty');
      assert.deepEqual(engine.doc.progress.daily_new_ledger, ledger);
      assert.equal(engine.doc.progress.study_records['tb-1'].new_count, 0);
      assert.deepEqual(engine.doc.progress.study_records['tb-1'].pending, {});
    }
  });
});
