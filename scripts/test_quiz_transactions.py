# -*- coding: utf-8 -*-
"""纯 AST 测验事务回归：普通对象、固定时钟、内存 JSON，不导入 Qt/Card/main。

运行：python -B scripts/test_quiz_transactions.py
只读取 main.py 的方法定义；不创建 data、临时记录、窗口或默认应用。
"""
import ast
import copy
import json
from pathlib import Path
import random
import sys
import types
import unittest

sys.dont_write_bytecode = True
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import placement as pl
from entries import word_caption


NOW = 1000000
FIELDS = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "rigor",
          "quiz_locked", "theta", "known", "last_test", "mode")
METHODS = {"_can_act", "save", "_capture_quiz", "_restore_quiz", "_set_quiz_retry",
           "_quiz_save_error", "retry_or_skip", "_welcome_test", "_test_from_settings",
           "start_quiz", "_gen_item",
           "_save_quiz_session", "skip_test", "_quiz_status", "_quiz_show",
           "_quiz_answer", "_quiz_next", "_finish_quiz", "_set_theta", "_refresh_known"}
SOURCE = (APP / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
CARD = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "Card")
NODES = [node for node in CARD.body if isinstance(node, ast.FunctionDef) and node.name in METHODS]
if {node.name for node in NODES} != METHODS:
    raise AssertionError("Missing quiz methods in AST fixture")
PLAIN = ast.ClassDef(name="QuizSubject", bases=[], keywords=[], body=NODES, decorator_list=[])
AUTO = next(node for node in ast.walk(TREE) if isinstance(node, ast.FunctionDef) and node.name == "_auto_quiz")
CODE = compile(ast.fix_missing_locations(ast.Module(body=[PLAIN, AUTO], type_ignores=[])),
               "<quiz-transactions-AST>", "exec")


def json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


class MemoryStorage:
    class StorageError(Exception):
        pass

    def __init__(self):
        self.attempts = 0
        self.fail_at = None
        self.record = None
        self.before_write = None

    def atomic_save(self, path, data):
        if path != "memory://quiz-progress":
            raise AssertionError("Unexpected storage target")
        self.attempts += 1
        if self.before_write:
            self.before_write(data)
        if self.attempts == self.fail_at:
            raise self.StorageError("injected atomic save failure")
        self.record = json_copy(data)

    def fail_next(self):
        self.fail_at = self.attempts + 1


class Widget:
    def __init__(self):
        self.text = ""
        self.enabled = True
        self.visible = True
        self.props = {}
        self.tooltip = ""

    def setText(self, value):
        self.text = value

    def setEnabled(self, value):
        self.enabled = bool(value)

    def setVisible(self, value):
        self.visible = bool(value)

    def show(self):
        self.visible = True

    def setProperty(self, key, value):
        self.props[key] = value

    def setToolTip(self, value):
        self.tooltip = value

    def style(self):
        return self

    def polish(self, widget):
        pass

    def unpolish(self, widget):
        pass


class Timer:
    def __init__(self):
        self.active = False
        self.remaining = -1
        self.starts = []

    def stop(self):
        self.active = False
        self.remaining = -1

    def start(self, delay):
        self.active = True
        self.remaining = delay
        self.starts.append(delay)

    def expire(self, callback):
        self.stop()                     # Qt single-shot 在进入 slot 前已 inactive
        return callback()


def make_subject(session=True, answered=False, index=0, count=1, history_count=100,
                 baseline=True, theta=0.75, book_confirmed=False, record=None):
    store = MemoryStorage()
    dialogs = []
    namespace = dict(copy=copy, random=random, pl=pl, word_caption=word_caption, storage=store, QUIZ_N=50,
                     LETTERS="ABCD", VERSION="1.3.0", SKIP_SNOOZE=86400,
                     PROGRESS_PATH="memory://quiz-progress",
                     time=types.SimpleNamespace(time=lambda: NOW),
                     QMessageBox=types.SimpleNamespace(critical=lambda *args: dialogs.append(args)))
    exec(CODE, namespace)
    subject = namespace["QuizSubject"]()
    namespace["w"] = subject           # AST 提取的隔离 CLI helper 也只访问这个普通对象
    subject.store, subject.dialogs, subject.namespace = store, dialogs, namespace
    subject._closed = subject._closing = False
    subject.mode = "quiz" if session else "welcome"
    subject.display_mode = subject.mode
    history = [{"ts": NOW - 10000 + i, "vocab": 1000 + i, "total": 50, "right": 30,
                "baseline": baseline and i == 0, "theta": theta,
                "future": {"n": i, "keep": [1, None, {"x": i}]}}
               for i in range(history_count)]
    subject.progress = json_copy(record) if record is not None else {
        "memory_schema": 2, "app_version": "1.3.0", "theta": theta,
        "states": {"other-word": {"st": "learning", "lv": 5, "due": NOW + 999,
                                  "seen": 8, "custom": {"keep": [1, 2]}}},
        "cursors": {"other": 17, "future-book": 8},
        "orders": {"other": {"mode": "seq", "future": [1, 2]}},
        "study_records": {"other": {"cursor": 17, "pending": {"other-word": 3},
                                    "future": {"keep": [2, 3]}}},
        "history": history, "book_confirmed": book_confirmed,
        "welcome_done": False, "quiz_from_welcome": not book_confirmed,
        "snooze_until": NOW + 100, "study_mode": "brush", "retry_gap": 3,
        "future": {"all_history": True, "keep": [1, None, {"custom": [2]}]},
    }
    subject.states, subject.cursors, subject.orders, subject.study_records = (
        subject.progress[key] for key in ("states", "cursors", "orders", "study_records"))
    subject.theta = subject.progress.get("theta")
    subject.known = set()
    subject.study_mode, subject.retry_gap = "brush", 3
    subject.bank = [{"w": "fixture-%02d" % i,
                     "s": chr(65 + i % 26) + "-meaning-%02d" % i, "pos": [], "lvl": i % 15}
                    for i in range(60)]
    subject.bs = [-3.0 + i * 0.1 for i in range(60)]
    subject.lvls = [word["lvl"] for word in subject.bank]
    subject.quiz_i, subject.quiz_items, subject.quiz_resp = 0, [], []
    subject.quiz_locked, subject._quiz_retry_action = False, None
    subject.rigor = 85.0
    rows = subject.progress.get("history", [])
    subject.last_test = (rows[-1], False) if rows else None
    subject.quiz_timer = Timer()
    subject.status, subject.quiz_word, subject.btn_dontknow, subject.btn_skip = (
        Widget(), Widget(), Widget(), Widget())
    subject.opt_btns = [Widget() for _ in range(4)]
    # 新的 _quiz_show 布局 hook 不属于事务：纯夹具仅提供无副作用 UI 接口。
    subject._ui_scale = lambda: 1.0
    subject._fit_choice_options = lambda scale: None
    subject.quiz_page = types.SimpleNamespace(
        verticalScrollBar=lambda: types.SimpleNamespace(setValue=lambda value: None))
    subject.btn_skip.text = "跳过本次测试"
    subject.btn_skip.visible = session
    subject.transitions, subject.results, subject.navigation = [], [], []

    def set_mode(mode):
        subject.mode = subject.display_mode = mode
        subject.btn_skip.setVisible(mode == "quiz")
        subject.transitions.append(mode)

    def show_result(rec, is_baseline, from_welcome=False):
        subject.results.append((rec, is_baseline, from_welcome))
        set_mode("result")

    def open_books(context):
        subject.navigation.append(("books", context))
        set_mode("books")

    def new_session():
        subject.navigation.append(("study",))
        set_mode("front")

    subject._set_mode, subject._show_result = set_mode, show_result
    subject.open_books, subject._new_session = open_books, new_session
    subject._refresh_known()
    subject.engine = types.SimpleNamespace(states=subject.states,
                                          record=subject.study_records["other"], known=subject.known)
    if session and record is None:
        subject.quiz_i = index
        shared = {"keep": [1, None, {"x": 2}]}
        subject.quiz_state = pl.new_session(seed=20261108)
        subject.quiz_state["asked"] = list(range(count))
        subject.quiz_state["future"] = shared
        subject.quiz_items = [{"idx": i, "opts": ["alpha", "beta", "gamma", "delta"],
                               "correct": 1, "lvl": i % 15, "future": shared if i == 0 else {"i": i}}
                              for i in range(count)]
        subject.quiz_resp = [1] * (index + int(answered))
        for n, response in enumerate(subject.quiz_resp, 1):
            pl.step(subject.quiz_state, response == 1, n)
        subject.progress["quiz_session"] = {"future": {"shared": shared, "keep": [9, 8]}}
        subject._save_quiz_session()
        subject._quiz_show()
        if answered:
            subject.quiz_locked = True
            for button in subject.opt_btns:
                button.setEnabled(False)
                button.setProperty("state", "correct")
            subject.btn_dontknow.setEnabled(False)
            subject.quiz_timer.start(650)
    else:
        store.record = json_copy(subject.progress)
    subject.transitions[:] = []
    return subject


def payload(subject):
    return copy.deepcopy({"progress": subject.progress,
                          "attrs": {name: getattr(subject, name) for name in FIELDS
                                    if hasattr(subject, name)}})


def references(subject):
    refs = {"progress": subject.progress, "states": subject.states, "cursors": subject.cursors,
            "orders": subject.orders, "records": subject.study_records,
            "book_record": subject.study_records["other"], "pending": subject.study_records["other"]["pending"],
            "top_future": subject.progress["future"], "known": subject.known,
            "items_attr": subject.quiz_items, "resp_attr": subject.quiz_resp,
            "last_test": subject.last_test}
    history = subject.progress.get("history")
    if history is not None:
        refs["history"] = history
        for i, row in enumerate(history):
            refs["history-%d" % i] = row
            refs["history-future-%d" % i] = row["future"]
            refs["history-keep-%d" % i] = row["future"]["keep"]
    sess = subject.progress.get("quiz_session")
    if isinstance(sess, dict):
        refs["session"] = sess
        for key in ("state", "items", "resp", "future"):
            refs["session-" + key] = sess[key]
        refs["asked"] = sess["state"]["asked"]
        for i, item in enumerate(sess["items"]):
            refs["item-%d" % i] = item
            refs["opts-%d" % i] = item["opts"]
            refs["item-future-%d" % i] = item["future"]
    if hasattr(subject, "quiz_state"):
        refs["state_attr"] = subject.quiz_state
    return refs


def ui_state(subject):
    return copy.deepcopy((subject.display_mode, subject.status.text, subject.quiz_word.text,
                          [(button.text, button.enabled, button.props) for button in subject.opt_btns],
                          subject.btn_dontknow.enabled, subject.btn_dontknow.props))


class QuizTransactionTests(unittest.TestCase):
    def assert_unchanged(self, subject, before, refs, committed):
        self.assertEqual(payload(subject), before)
        current = references(subject)
        self.assertEqual(set(current), set(refs))
        for name, original in refs.items():
            self.assertIs(current[name], original, name)
        self.assertIs(subject.progress["states"], subject.states)
        self.assertIs(subject.progress["cursors"], subject.cursors)
        self.assertIs(subject.progress["orders"], subject.orders)
        self.assertIs(subject.progress["study_records"], subject.study_records)
        self.assertIs(subject.engine.states, subject.states)
        self.assertIs(subject.engine.record, subject.study_records["other"])
        self.assertIs(subject.engine.known, subject.known)
        self.assertEqual(subject.store.record, committed)

    def fail_operation(self, subject, callback, action):
        before, refs, committed, old_ui = payload(subject), references(subject), copy.deepcopy(subject.store.record), ui_state(subject)
        attempts = subject.store.attempts
        subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), old_ui)
        subject.store.fail_next()
        self.assertFalse(callback())
        self.assertEqual(subject.store.attempts, attempts + 1)
        self.assert_unchanged(subject, before, refs, committed)
        self.assertEqual(ui_state(subject), old_ui)
        self.assertEqual(subject._quiz_retry_action, action)
        self.assertFalse(subject.quiz_timer.active)
        self.assertEqual(len(subject.dialogs), 1)
        if action:
            self.assertEqual(subject.btn_skip.text, "重试保存并继续")
            self.assertTrue(subject.btn_skip.visible)
        return before

    def test_quiz_caption_is_optional_and_never_changes_identity(self):
        subject = make_subject()
        before = payload(subject)
        bank_before = copy.deepcopy(subject.bank)
        self.assertFalse(hasattr(subject, "book_words"))
        self.assertEqual(subject.quiz_word.text, subject.bank[0]["w"])
        subject.book_words = [dict(subject.bank[0], display_w="Visible Caption")]
        subject._quiz_show()
        self.assertEqual(subject.quiz_word.text, "Visible Caption")
        subject.book_words = None
        subject._quiz_show()
        self.assertEqual(subject.quiz_word.text, subject.bank[0]["w"])
        self.assertEqual(subject.bank, bank_before)
        self.assertEqual(payload(subject), before)

    def test_school_caption_never_leaks_into_general_measurement(self):
        subject = make_subject()
        before = payload(subject)
        bank_before = copy.deepcopy(subject.bank)
        subject.book_words = [dict(subject.bank[0], display_w="School Name",
                                   display_s="n.学校人名", _school_caption=True)]
        subject._quiz_show()
        self.assertEqual(subject.quiz_word.text, subject.bank[0]["w"])
        self.assertEqual(subject.bank, bank_before)
        self.assertEqual(payload(subject), before)

    def test_plain_ast_subject_has_no_widget_constructor(self):
        subject = make_subject()
        self.assertEqual(type(subject).__bases__, (object,))
        self.assertNotIn("__init__", type(subject).__dict__)
        build = next(node for node in CARD.body if isinstance(node, ast.FunctionDef) and node.name == "_build_ui")
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr == "connect" and node.args
                            and isinstance(node.args[0], ast.Attribute)
                            and node.args[0].attr == "retry_or_skip" for node in ast.walk(build)))

    def test_snapshot_roundtrip_keeps_nested_original_refs_and_aliases(self):
        subject = make_subject()
        before, refs = payload(subject), references(subject)
        snapshot = subject._capture_quiz()
        subject.quiz_state["future"]["keep"].append("changed")
        subject.quiz_state["asked"].append(7)
        subject.quiz_resp.append(0)
        subject.quiz_items.append({"idx": 9})
        subject.progress["history"][0]["future"]["keep"].append("changed")
        subject.progress["history"].append({"ts": NOW})
        subject.progress.pop("quiz_session")
        subject.progress["new_key"] = True
        subject.known = {"new"}
        subject._restore_quiz(snapshot)
        self.assert_unchanged(subject, before, refs, subject.store.record)
        self.assertIs(subject.quiz_state["future"], subject.quiz_items[0]["future"])
        self.assertIs(subject.quiz_state["future"], subject.progress["quiz_session"]["future"]["shared"])

    def test_answer_failure_good_wrong_and_dontknow(self):
        for choice in (1, 0, -1):
            with self.subTest(choice=choice):
                subject = make_subject()
                self.fail_operation(subject, lambda: subject._quiz_answer(choice), None)
                self.assertFalse(subject.quiz_locked)
                self.assertTrue(all(button.enabled for button in subject.opt_btns))
                self.assertTrue(subject.btn_dontknow.enabled)
                self.assertEqual(subject.quiz_resp, [])

    def test_answer_success_saves_before_feedback_and_counts_once(self):
        subject = make_subject()
        original_ui = ui_state(subject)
        subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), original_ui)
        self.assertTrue(subject._quiz_answer(0))
        subject.store.before_write = None
        self.assertEqual(subject.quiz_resp, [0])
        self.assertEqual(subject.rigor, 82.0)
        self.assertEqual(subject.quiz_state["down"], 1)
        self.assertTrue(subject.quiz_locked)
        self.assertFalse(any(button.enabled for button in subject.opt_btns))
        self.assertTrue(subject.quiz_timer.active)
        self.assertEqual(subject.quiz_timer.remaining, 650)
        attempts = subject.store.attempts
        self.assertFalse(subject._quiz_answer(1))
        subject.quiz_locked = False      # 即使被外部错误解锁，已答长度也保护不重复计分
        self.assertFalse(subject._quiz_answer(1))
        self.assertEqual(subject.store.attempts, attempts)
        self.assertEqual(subject.quiz_resp, [0])

    def test_session_success_keeps_dict_and_unknown_graph_identity(self):
        subject = make_subject()
        refs = references(subject)
        future = copy.deepcopy(subject.progress["quiz_session"]["future"])
        self.assertTrue(subject._quiz_answer(1))
        self.assertIs(subject.progress["quiz_session"], refs["session"])
        self.assertIs(subject.quiz_state, refs["state_attr"])
        self.assertIs(subject.quiz_resp, refs["resp_attr"])
        self.assertEqual(subject.progress["quiz_session"]["future"], future)
        self.assertEqual(len(subject.store.record["history"]), 100)
        self.assertEqual(subject.store.record["future"], subject.progress["future"])

    def test_next_failure_keeps_answered_feedback_and_provides_retry(self):
        subject = make_subject(answered=True)
        self.fail_operation(subject, lambda: subject.quiz_timer.expire(subject._quiz_next), "next")
        self.assertTrue(subject.quiz_locked)
        self.assertFalse(any(button.enabled for button in subject.opt_btns))
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), len(subject.quiz_resp)), (0, 1, 1))
        attempts = subject.store.attempts
        self.assertFalse(subject._quiz_answer(0))
        self.assertEqual(subject.store.attempts, attempts)

    def test_next_retry_advances_once_without_answering_or_skipping(self):
        subject = make_subject(answered=True)
        self.fail_operation(subject, subject._quiz_next, "next")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), len(subject.quiz_resp)), (1, 2, 1))
        self.assertFalse(subject.quiz_locked)
        self.assertTrue(all(button.enabled for button in subject.opt_btns))
        self.assertFalse(subject.quiz_timer.active)
        self.assertEqual(subject.btn_skip.text, "跳过本次测试")
        self.assertFalse(subject.navigation)
        attempts = subject.store.attempts
        self.assertFalse(subject._quiz_next())  # 迟到 timeout 不跳过刚展示的未答题
        self.assertEqual(subject.store.attempts, attempts)

    def test_repeated_next_failures_do_not_grow_items_or_responses(self):
        subject = make_subject(answered=True)
        self.fail_operation(subject, subject._quiz_next, "next")
        subject.store.before_write = None
        before = payload(subject)
        for _ in range(3):
            subject.store.fail_next()
            self.assertFalse(subject.retry_or_skip())
            self.assertEqual(payload(subject), before)
        self.assertEqual(len(subject.quiz_items), 1)
        self.assertEqual(len(subject.quiz_resp), 1)

    def test_manual_next_stops_old_timer_and_callback_is_noop(self):
        subject = make_subject(answered=True)
        self.assertTrue(subject.quiz_timer.active)
        self.assertTrue(subject._quiz_next())
        self.assertFalse(subject.quiz_timer.active)
        before, attempts = payload(subject), subject.store.attempts
        self.assertFalse(subject._quiz_next())
        self.assertEqual(payload(subject), before)
        self.assertEqual(subject.store.attempts, attempts)

    def test_finish_failure_restores_full_history_baseline_and_keys(self):
        subject = make_subject(answered=True, index=49, count=50, baseline=False, theta=None)
        self.fail_operation(subject, subject._quiz_next, "finish")
        self.assertEqual(subject.quiz_i, 49)
        self.assertEqual(len(subject.progress["history"]), 100)
        self.assertIsNone(subject.theta)
        self.assertIn("quiz_session", subject.progress)
        self.assertIn("quiz_from_welcome", subject.progress)
        self.assertIn("snooze_until", subject.progress)
        self.assertFalse(subject.results)
        self.assertNotEqual(subject.status.text, "词汇量测试完成")

    def test_finish_failure_restores_original_absent_keys(self):
        subject = make_subject(answered=True, index=49, count=50, history_count=0, theta=None)
        for key in ("history", "theta", "quiz_from_welcome", "snooze_until", "welcome_done"):
            subject.progress.pop(key, None)
        subject.store.record = json_copy(subject.progress)
        self.fail_operation(subject, subject._finish_quiz, "finish")
        self.assertTrue(all(key not in subject.progress for key in
                            ("history", "theta", "quiz_from_welcome", "snooze_until", "welcome_done")))

    def test_finish_retry_commits_one_history_row_and_is_idempotent(self):
        subject = make_subject(answered=True, index=49, count=50, baseline=False, theta=None)
        self.fail_operation(subject, subject._quiz_next, "finish")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.quiz_i, 49)
        self.assertEqual(len(subject.progress["history"]), 101)
        self.assertTrue(subject.progress["history"][-1]["baseline"])
        self.assertIs(subject.last_test[0], subject.progress["history"][-1])
        self.assertEqual(subject.display_mode, "result")
        self.assertNotIn("quiz_session", subject.progress)
        self.assertFalse(subject.quiz_timer.active)
        attempts = subject.store.attempts
        self.assertFalse(subject._finish_quiz())
        self.assertFalse(subject._quiz_next())
        self.assertFalse(subject.retry_or_skip())
        self.assertEqual(subject.store.attempts, attempts)
        self.assertEqual(len(subject.results), 1)

    def test_repeated_finish_failures_do_not_grow_history(self):
        subject = make_subject(answered=True, index=49, count=50, baseline=False, theta=None)
        self.fail_operation(subject, subject._finish_quiz, "finish")
        subject.store.before_write = None
        before = payload(subject)
        for _ in range(3):
            subject.store.fail_next()
            self.assertFalse(subject.retry_or_skip())
            self.assertEqual(payload(subject), before)
            self.assertEqual(subject.quiz_i, 49)

    def test_finish_rejects_incomplete_nonquiz_and_already_committed_sessions(self):
        for case in ("incomplete", "nonquiz", "missing-session"):
            with self.subTest(case=case):
                subject = make_subject(answered=True, index=49, count=50)
                if case == "incomplete":
                    subject.quiz_resp.pop()
                elif case == "nonquiz":
                    subject.mode = "result"
                else:
                    subject.progress.pop("quiz_session")
                before, attempts = payload(subject), subject.store.attempts
                self.assertFalse(subject._finish_quiz())
                self.assertEqual(payload(subject), before)
                self.assertEqual(subject.store.attempts, attempts)

    def test_zero_theta_is_not_replaced_by_nonbaseline_result(self):
        subject = make_subject(answered=True, index=49, count=50, theta=0.0)
        previous_known = set(subject.known)
        previous_history = copy.deepcopy(subject.progress["history"])
        self.assertTrue(subject._finish_quiz())
        self.assertEqual(subject.theta, 0.0)
        self.assertEqual(subject.progress["theta"], 0.0)
        self.assertEqual(subject.known, previous_known)
        self.assertEqual(subject.progress["history"][:-1], previous_history)
        self.assertFalse(subject.progress["history"][-1]["baseline"])

    def test_start_failure_keeps_empty_original_attrs_and_missing_session(self):
        subject = make_subject(session=False)
        for key in ("welcome_done", "quiz_from_welcome"):
            subject.progress.pop(key)
        subject.store.record = json_copy(subject.progress)
        self.fail_operation(subject, subject.start_quiz, "start")
        self.assertFalse(hasattr(subject, "quiz_state"))
        self.assertNotIn("quiz_session", subject.progress)
        self.assertNotIn("welcome_done", subject.progress)
        self.assertNotIn("quiz_from_welcome", subject.progress)
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.display_mode, "quiz")
        self.assertEqual(subject.quiz_resp, [])
        self.assertEqual(len(subject.quiz_items), 1)
        self.assertEqual(subject.btn_skip.text, "跳过本次测试")

    def test_ui_start_wrappers_restore_flags_on_the_first_save_failure(self):
        for name in ("_welcome_test", "_test_from_settings"):
            with self.subTest(wrapper=name):
                settings = name == "_test_from_settings"
                subject = make_subject(session=False, book_confirmed=settings)
                if settings:
                    subject._set_mode("settings")
                subject.progress["quiz_declined"] = True
                subject.store.record = json_copy(subject.progress)
                self.fail_operation(subject, getattr(subject, name), "start")
                self.assertFalse(subject.progress["welcome_done"])
                self.assertTrue(subject.progress["quiz_declined"])
                self.assertNotIn("quiz_session", subject.progress)
                subject.store.before_write = None
                self.assertTrue(subject.retry_or_skip())
                self.assertTrue(subject.progress["welcome_done"])
                self.assertNotIn("quiz_declined", subject.progress)
                self.assertIn("quiz_session", subject.progress)

    def test_ui_start_wrappers_commit_flags_and_session_in_one_save(self):
        for name in ("_welcome_test", "_test_from_settings"):
            with self.subTest(wrapper=name):
                settings = name == "_test_from_settings"
                subject = make_subject(session=False, book_confirmed=settings)
                if settings:
                    subject._set_mode("settings")
                subject.progress["quiz_declined"] = True
                original_ui = ui_state(subject)

                def before_write(data):
                    self.assertEqual(ui_state(subject), original_ui)
                    self.assertTrue(data["welcome_done"])
                    self.assertNotIn("quiz_declined", data)
                    self.assertIn("quiz_session", data)
                    self.assertEqual(len(data["quiz_session"]["items"]), 1)

                subject.store.before_write = before_write
                self.assertTrue(getattr(subject, name)())
                self.assertEqual(subject.store.attempts, 1)
                self.assertEqual(subject.display_mode, "quiz")
                self.assertEqual(subject.progress["quiz_from_welcome"], not settings)

    def test_resume_unanswered_save_failure_preserves_old_session_refs(self):
        original = make_subject()
        subject = make_subject(session=False, record=original.store.record)
        self.fail_operation(subject, subject.start_quiz, "start")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, len(subject.quiz_resp)), (0, 0))
        self.assertIs(subject.quiz_state, subject.progress["quiz_session"]["state"])
        self.assertIs(subject.quiz_items, subject.progress["quiz_session"]["items"])
        self.assertIs(subject.quiz_resp, subject.progress["quiz_session"]["resp"])

    def test_resume_answered_current_advances_instead_of_answering_twice(self):
        original = make_subject(answered=True)
        subject = make_subject(session=False, record=original.store.record)
        state_before = copy.deepcopy(subject.progress["quiz_session"]["state"])
        old_ui = ui_state(subject)
        subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), old_ui)
        self.assertTrue(subject.start_quiz())
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), len(subject.quiz_resp)), (1, 2, 1))
        self.assertEqual(subject.quiz_state["up"], state_before["up"])
        self.assertEqual(subject.quiz_state["down"], state_before["down"])
        self.assertEqual(subject.quiz_state["level"], state_before["level"])
        self.assertEqual(subject.store.attempts, 1)
        self.assertEqual(subject.quiz_word.text, subject.bank[subject.quiz_items[1]["idx"]]["w"])
        self.assertFalse(subject.quiz_locked)

    def test_resume_answered_failure_restores_pre_start_attrs_and_retries_start(self):
        original = make_subject(answered=True)
        subject = make_subject(session=False, record=original.store.record)
        self.fail_operation(subject, subject.start_quiz, "start")
        self.assertEqual(subject.display_mode, "welcome")
        self.assertFalse(hasattr(subject, "quiz_state"))
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, len(subject.quiz_resp)), (1, 1))
        self.assertEqual(len(subject.quiz_items), 2)

    def test_resume_last_answer_finishes_once_at_49(self):
        original = make_subject(answered=True, index=49, count=50, theta=0.0)
        subject = make_subject(session=False, record=original.store.record)
        self.assertTrue(subject.start_quiz())
        self.assertEqual(subject.quiz_i, 49)
        self.assertEqual(subject.display_mode, "result")
        self.assertEqual(subject.progress["theta"], 0.0)
        self.assertEqual(len(subject.progress["history"]), 101)
        self.assertEqual(subject.store.attempts, 1)
        self.assertFalse(subject._finish_quiz())
        self.assertEqual(subject.store.attempts, 1)

    def test_resume_last_failure_preserves_old_graph_and_finish_retry_once(self):
        original = make_subject(answered=True, index=49, count=50, baseline=False, theta=None)
        subject = make_subject(session=False, record=original.store.record)
        self.fail_operation(subject, subject.start_quiz, "start")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.quiz_i, 49)
        self.assertEqual(len(subject.progress["history"]), 101)
        self.assertEqual(len(subject.results), 1)

    def test_invalid_resume_does_not_silently_drop_old_session(self):
        original = make_subject(answered=True)
        subject = make_subject(session=False, record=original.store.record)
        subject.progress["quiz_session"]["resp"].append(0)
        before, refs, committed = payload(subject), references(subject), copy.deepcopy(subject.store.record)
        self.assertFalse(subject.start_quiz())
        self.assert_unchanged(subject, before, refs, committed)
        self.assertEqual(subject.store.attempts, 0)
        self.assertEqual(subject._quiz_retry_action, "start")

    def test_skip_failure_preserves_session_and_successful_retry_alone_discards_it(self):
        for answered in (False, True):
            with self.subTest(answered=answered):
                subject = make_subject(answered=answered)
                self.fail_operation(subject, subject.skip_test, "skip")
                subject.store.before_write = None
                self.assertTrue(subject.retry_or_skip())
                self.assertNotIn("quiz_session", subject.progress)
                self.assertNotIn("quiz_session", subject.store.record)
                self.assertEqual(subject.progress["snooze_until"], NOW + 86400)
                self.assertEqual(len(subject.progress["history"]), 100)
                self.assertEqual(subject.navigation, [("books", "welcome")])
                self.assertEqual(subject.btn_skip.text, "跳过本次测试")
                self.assertFalse(subject.quiz_timer.active)
                attempts = subject.store.attempts
                self.assertFalse(subject.retry_or_skip())
                self.assertEqual(subject.store.attempts, attempts)

    def test_skip_retry_returns_confirmed_book_to_study(self):
        subject = make_subject(book_confirmed=True)
        self.fail_operation(subject, subject.skip_test, "skip")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.navigation, [("study",)])
        self.assertEqual(subject.display_mode, "front")

    def test_failed_skip_does_not_prevent_unanswered_question_answer(self):
        subject = make_subject()
        self.fail_operation(subject, subject.skip_test, "skip")
        subject.store.before_write = None
        self.assertTrue(subject._quiz_answer(1))
        self.assertEqual(subject._quiz_retry_action, None)
        self.assertIn("quiz_session", subject.progress)
        self.assertEqual(subject.quiz_resp, [1])
        self.assertTrue(subject.quiz_timer.active)

    def test_close_force_save_after_answer_failure_cannot_replay_answer(self):
        subject = make_subject()
        self.fail_operation(subject, lambda: subject._quiz_answer(0), None)
        subject.store.before_write = None
        subject.save(force=True)
        restarted = make_subject(session=False, record=subject.store.record)
        self.assertTrue(restarted.start_quiz())
        self.assertEqual((restarted.quiz_i, len(restarted.quiz_resp)), (0, 0))
        self.assertTrue(restarted._quiz_answer(1))
        self.assertEqual(restarted.quiz_resp, [1])

    def test_normal_close_during_feedback_resumes_next_not_same_question(self):
        subject = make_subject()
        self.assertTrue(subject._quiz_answer(1))
        subject.quiz_timer.stop()
        subject.save(force=True)
        restarted = make_subject(session=False, record=subject.store.record)
        self.assertTrue(restarted.start_quiz())
        self.assertEqual((restarted.quiz_i, len(restarted.quiz_resp)), (1, 1))
        self.assertFalse(restarted.quiz_locked)

    def test_isolated_auto_helper_stops_after_start_answer_or_next_failure(self):
        for phase in ("start", "answer", "next"):
            with self.subTest(phase=phase):
                subject = make_subject(session=phase != "start")
                before = payload(subject)
                limit = subject.store.attempts + (2 if phase == "next" else 1)
                subject.store.fail_at = limit
                subject.store.before_write = lambda data: self.assertLessEqual(subject.store.attempts, limit)
                subject.namespace["_auto_quiz"]()
                self.assertEqual(subject.store.attempts, limit)
                self.assertEqual(len(subject.dialogs), 1)
                self.assertFalse(subject.results)
                if phase == "next":
                    self.assertEqual((subject.quiz_i, len(subject.quiz_resp)), (0, 1))
                    self.assertTrue(subject.quiz_locked)
                    self.assertEqual(subject._quiz_retry_action, "next")
                else:
                    self.assertEqual(payload(subject), before)

    def test_isolated_auto_helper_advances_pending_answer_before_loop(self):
        subject = make_subject(answered=True)
        subject.namespace["_auto_quiz"]()
        self.assertEqual(subject.quiz_i, 49)
        self.assertEqual(len(subject.quiz_resp), 50)
        self.assertEqual(len(subject.quiz_items), 50)
        self.assertEqual(subject.display_mode, "result")
        self.assertEqual(len(subject.results), 1)
        self.assertFalse(subject.dialogs)

    def test_closed_and_closing_callbacks_mutate_nothing(self):
        for closing in (False, True):
            with self.subTest(closing=closing):
                subject = make_subject(answered=True, index=49, count=50)
                subject._closed, subject._closing = not closing, closing
                before, old_ui, attempts = payload(subject), ui_state(subject), subject.store.attempts
                callbacks = (lambda: subject._quiz_answer(1), subject._quiz_next,
                             subject._finish_quiz, subject.start_quiz, subject.skip_test,
                             subject._welcome_test, subject._test_from_settings,
                             subject.retry_or_skip, subject._save_quiz_session)
                for callback in callbacks:
                    self.assertFalse(callback())
                self.assertEqual(payload(subject), before)
                self.assertEqual(ui_state(subject), old_ui)
                self.assertEqual(subject.store.attempts, attempts)
                self.assertFalse(subject.dialogs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
