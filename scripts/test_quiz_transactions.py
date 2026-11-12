# -*- coding: utf-8 -*-
"""纯 AST 测验事务回归：普通对象、固定时钟、内存 JSON，不导入 Qt/Card/main。

运行：python -B scripts/test_quiz_transactions.py
只读取 main.py 的方法定义；不创建 data、临时记录、窗口或默认应用。
"""
import ast
import copy
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import types
import unittest

sys.dont_write_bytecode = True
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import placement as pl
from entries import word_caption


NOW = 1000000
RESUME_TTL = 30 * 86400
BANK_SIZE = 60
FIELDS = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "rigor",
          "quiz_locked", "theta", "known", "last_test", "mode",
          "quiz_started_at", "quiz_last_answer_at", "quiz_session_id",
          "quiz_origin_welcome", "quiz_bank_fingerprint", "quiz_vocab_grid",
          "quiz_item_indices", "quiz_result", "quiz_return_to_settings", "quiz_status_values")
METHODS = {"_can_act", "save", "_capture_quiz", "_restore_quiz", "_set_quiz_retry",
           "_quiz_save_error", "retry_or_skip", "_welcome_test", "_test_from_settings",
           "_confirm_new_quiz", "_startup", "start_quiz", "_gen_item",
           "_save_quiz_session", "skip_test", "_test_bank_exhausted", "_quiz_status", "_quiz_show",
           "_quiz_answer", "_quiz_next", "_finish_quiz", "_set_theta", "_refresh_known",
           "_quiz_remaining_days", "_quiz_history_record", "_upsert_quiz_history"}
SOURCE = (APP / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
CARD = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "Card")
NODES = [node for node in CARD.body if isinstance(node, ast.FunctionDef) and node.name in METHODS]
if {node.name for node in NODES} != METHODS:
    raise AssertionError("Missing quiz methods in AST fixture: " + ", ".join(sorted(METHODS - {node.name for node in NODES})))
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
                 baseline=True, theta=0.75, book_confirmed=False, record=None,
                 existing_history_index=None):
    store = MemoryStorage()
    dialogs = []
    questions, notices = [], []

    def question(*args):
        questions.append(args)
        return namespace["question_answer"]

    def no_prediction(*args, **kwargs):
        raise AssertionError("Quiz transactions must not implicitly apply prediction")

    namespace = dict(copy=copy, random=random, math=math, os=os, pl=pl,
                     word_caption=word_caption, storage=store,
                     LETTERS="ABCD", VERSION="1.4.0", RESUME_TTL=RESUME_TTL,
                     PREDICTION_MIN_N=50, PREDICTION_MIN_RIGOR=60,
                     pred=types.SimpleNamespace(apply_strategy=no_prediction,
                                                select_prediction_candidates=no_prediction),
                     PROGRESS_PATH="memory://quiz-progress", question_answer=1,
                     time=types.SimpleNamespace(time=lambda: NOW),
                     QMessageBox=types.SimpleNamespace(
                         Yes=1, Cancel=2, question=question,
                         critical=lambda *args: dialogs.append(args),
                         information=lambda *args: notices.append(args)))
    exec(CODE, namespace)
    subject = namespace["QuizSubject"]()
    namespace["w"] = subject           # AST 提取的隔离 CLI helper 也只访问这个普通对象
    subject.store, subject.dialogs, subject.namespace = store, dialogs, namespace
    subject.questions, subject.notices = questions, notices
    subject._closed = subject._closing = False
    subject.mode = "quiz" if session else "welcome"
    subject.display_mode = subject.mode
    history = [{"ts": NOW - 10000 + i, "vocab": 1000 + i, "total": 50, "right": 30,
                "baseline": baseline and i == 0, "theta": theta,
                "future": {"n": i, "keep": [1, None, {"x": i}]}}
               for i in range(history_count)]
    subject.progress = json_copy(record) if record is not None else {
        "memory_schema": 2, "app_version": "1.4.0", "theta": theta,
        "prediction_state": {"schema": 1, "selected": ["fixture-55"],
                             "rejected": [], "excluded": ["fixture-54"],
                             "effective": {"target": 1, "available": 60, "selected": 1}},
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
    subject.prediction_data = subject.progress["prediction_state"]
    subject.known = set()
    subject.study_mode, subject.retry_gap = "brush", 3
    subject.bank = [{"w": "fixture-%02d" % i,
                     "s": chr(65 + i % 26) + "-meaning-%02d" % i, "pos": [], "lvl": i % 15}
                    for i in range(BANK_SIZE)]
    subject.bs = [-3.0 + i * 0.1 for i in range(BANK_SIZE)]
    subject.lvls = [word["lvl"] for word in subject.bank]
    subject.bank_fingerprint = "fixture-bank-v140"
    subject.quiz_i, subject.quiz_items, subject.quiz_resp = 0, [], []
    subject.quiz_locked, subject._quiz_retry_action = False, None
    subject.quiz_return_to_settings = False
    subject.quiz_status_values = None
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
    subject._refresh_key_hints = lambda: None  # 视觉键位提示由 test_v136_ui 覆盖
    subject.quiz_page = types.SimpleNamespace(
        verticalScrollBar=lambda: types.SimpleNamespace(setValue=lambda value: None))
    subject.btn_skip.text = "结束本次测试"
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

    def open_settings():
        subject.navigation.append(("settings",))
        set_mode("settings")

    subject._set_mode, subject._show_result = set_mode, show_result
    subject.open_books, subject._new_session = open_books, new_session
    subject.open_settings = open_settings
    subject.welcome = lambda: set_mode("welcome")
    subject._refresh_known()
    subject.engine = types.SimpleNamespace(states=subject.states,
                                          record=subject.study_records["other"], known=subject.known)
    if session and record is None:
        if count != index + 1 or count > BANK_SIZE:
            raise AssertionError("Fixture must use a legal current-item index")
        subject.quiz_i = index
        shared = {"keep": [1, None, {"x": 2}]}
        subject.quiz_state = pl.new_session(seed=20261108)
        subject.quiz_state["theta"] = 0.0
        subject.quiz_state["asked"] = [entry["w"] for entry in subject.bank[:count]]
        subject.quiz_state["future"] = shared
        subject.quiz_item_indices = {entry["w"]: i for i, entry in enumerate(subject.bank)}
        subject.quiz_vocab_grid = pl.build_profile(subject.bank)
        subject.quiz_bank_fingerprint = subject.bank_fingerprint
        subject.quiz_started_at = NOW - 123
        subject.quiz_session_id = "fixture-existing-session"
        if existing_history_index is not None:
            subject.progress["history"][existing_history_index].update(
                id=subject.quiz_session_id, baseline=True)
        subject.quiz_origin_welcome = not book_confirmed
        subject.quiz_items = [
            {"key": subject.bank[i]["w"], "lvl": i % 15,
             "item": {"item_id": "item-%02d" % i, "word": subject.bank[i]["w"],
                      "options": [{"key": key, "text": text, "item_id": "option-" + key}
                                  for key, text in zip("ABCD", ("alpha", "beta", "gamma", pl.NO_ANSWER))],
                      "correct_index": 1, "correct_key": "B", "trap": False},
             "future": shared if i == 0 else {"i": i}}
            for i in range(count)]
        subject.quiz_resp = [1] * (index + int(answered))
        for n, response in enumerate(subject.quiz_resp, 1):
            pl.step(subject.quiz_state, response == 1, n, response)
        if subject.quiz_resp:
            subject.quiz_state["theta"], _ = pl.estimate_theta(
                subject.bs[:len(subject.quiz_resp)], subject.quiz_resp)
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
            "last_test": subject.last_test, "prediction_data": subject.prediction_data}
    if isinstance(subject.progress.get("quiz_session"), dict):
        refs["session"] = subject.progress["quiz_session"]
    if hasattr(subject, "quiz_state"):
        refs["state_attr"] = subject.quiz_state

    def collect(value, path, ancestors=()):
        if not isinstance(value, (dict, list, set, tuple)):
            return
        refs[path] = value
        if id(value) in ancestors:
            return
        ancestors += (id(value),)
        if isinstance(value, dict):
            for key, child in value.items():
                collect(child, path + "/" + str(key), ancestors)
        elif isinstance(value, (list, tuple)):
            for i, child in enumerate(value):
                collect(child, path + "/" + str(i), ancestors)

    collect(subject.progress, "graph/progress")
    for name in FIELDS:
        if hasattr(subject, name):
            collect(getattr(subject, name), "graph/" + name)
    return refs


def ui_state(subject):
    return copy.deepcopy((subject.display_mode, subject.status.text, subject.quiz_word.text,
                          [(button.text, button.enabled, button.props) for button in subject.opt_btns],
                          subject.btn_dontknow.enabled, subject.btn_dontknow.props))


class QuizTransactionTests(unittest.TestCase):
    def assert_quiz_status(self, value):
        plain = re.sub(r"<[^>]*>", "", value).replace("&nbsp;", " ")
        parts = [part.strip() for part in plain.split("·")]
        self.assertEqual(len(parts), 4, plain)
        self.assertEqual(parts[0], "词汇量测试")
        self.assertRegex(parts[1], r"^词目量\s*[\d,]+$")
        self.assertRegex(parts[2], r"^误差\s*\d+(?:\.\d+)?%$")
        self.assertRegex(parts[3], r"^严谨度\s*(?:\d+(?:\.\d+)?|max)$")

    def assert_no_implicit_mastery(self, subject, before, known):
        self.assertEqual(subject.theta, before["theta"])
        self.assertEqual(subject.progress["theta"], before["theta"])
        self.assertIs(subject.known, known)
        self.assertEqual(subject.states, before["states"])
        self.assertEqual(subject.prediction_data, before["prediction_state"])

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
        subject.quiz_state["asked"].append("transient-key")
        subject.quiz_resp.append(0)
        subject.quiz_items.append({"key": "transient-key"})
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
        self.assertEqual(subject.rigor, 74.0)
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
        self.assertEqual(len(subject.store.record["history"]), 101)
        self.assertEqual(subject.store.record["history"][-1]["total"], 1)
        self.assertFalse(subject.store.record["history"][-1]["completed"])
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
        scored = copy.deepcopy(subject.quiz_state)
        rigor, item, responses = subject.rigor, subject.quiz_items[0], list(subject.quiz_resp)
        self.fail_operation(subject, subject._quiz_next, "next")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), len(subject.quiz_resp)), (1, 2, 1))
        self.assertEqual(subject.quiz_resp, responses)
        self.assertIs(subject.quiz_items[0], item)
        self.assertEqual(subject.rigor, rigor)
        self.assertEqual({key: value for key, value in subject.quiz_state.items() if key != "asked"},
                         {key: value for key, value in scored.items() if key != "asked"})
        self.assertEqual(subject.quiz_state["asked"][:-1], scored["asked"])
        self.assertFalse(subject.quiz_locked)
        self.assertTrue(all(button.enabled for button in subject.opt_btns))
        self.assertFalse(subject.quiz_timer.active)
        self.assertEqual(subject.btn_skip.text, "结束本次测试")
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
        subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, baseline=False, theta=None)
        self.fail_operation(subject, subject._quiz_next, "finish")
        self.assertEqual(subject.quiz_i, BANK_SIZE - 1)
        self.assertEqual(len(subject.progress["history"]), 101)
        self.assertIsNone(subject.theta)
        self.assertIn("quiz_session", subject.progress)
        self.assertIn("quiz_from_welcome", subject.progress)
        self.assertIn("snooze_until", subject.progress)
        self.assertFalse(subject.results)
        self.assertNotEqual(subject.status.text, "词汇量测试完成")

    def test_finish_failure_restores_original_absent_keys(self):
        subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, history_count=0, theta=None)
        for key in ("history", "theta", "quiz_from_welcome", "snooze_until", "welcome_done"):
            subject.progress.pop(key, None)
        subject.store.record = json_copy(subject.progress)
        self.fail_operation(subject, subject._finish_quiz, "finish")
        self.assertTrue(all(key not in subject.progress for key in
                            ("history", "theta", "quiz_from_welcome", "snooze_until", "welcome_done")))

    def test_finish_retry_commits_one_history_row_and_is_idempotent(self):
        subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, baseline=False, theta=None)
        old_states = copy.deepcopy(subject.states)
        old_prediction, known = copy.deepcopy(subject.prediction_data), subject.known
        self.fail_operation(subject, subject._quiz_next, "finish")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertIsNone(subject.theta)
        self.assertIsNone(subject.progress["theta"])
        self.assertIs(subject.known, known)
        self.assertEqual(subject.states, old_states)
        self.assertEqual(subject.prediction_data, old_prediction)
        self.assertEqual(subject.quiz_i, BANK_SIZE - 1)
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
        subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, baseline=False, theta=None)
        self.fail_operation(subject, subject._finish_quiz, "finish")
        subject.store.before_write = None
        before = payload(subject)
        for _ in range(3):
            subject.store.fail_next()
            self.assertFalse(subject.retry_or_skip())
            self.assertEqual(payload(subject), before)
            self.assertEqual(subject.quiz_i, BANK_SIZE - 1)

    def test_finish_rejects_incomplete_nonquiz_and_already_committed_sessions(self):
        for case in ("incomplete", "nonquiz", "missing-session"):
            with self.subTest(case=case):
                subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE)
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
        subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, theta=0.0)
        previous_known = set(subject.known)
        previous_history = copy.deepcopy(subject.progress["history"])
        self.assertTrue(subject._finish_quiz())
        self.assertEqual(subject.theta, 0.0)
        self.assertEqual(subject.progress["theta"], 0.0)
        self.assertEqual(subject.known, previous_known)
        self.assertEqual(subject.progress["history"][:-1], previous_history[:-1])
        self.assertEqual(len(subject.progress["history"]), len(previous_history))
        self.assertTrue(subject.progress["history"][-1]["completed"])
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
        self.assertEqual(subject.btn_skip.text, "结束本次测试")

    def test_ui_start_wrappers_restore_flags_on_the_first_save_failure(self):
        for name in ("_welcome_test", "_test_from_settings"):
            with self.subTest(wrapper=name):
                settings = name == "_test_from_settings"
                subject = make_subject(session=False, book_confirmed=settings)
                if settings:
                    subject._set_mode("settings")
                subject.progress["quiz_declined"] = True
                subject.store.record = json_copy(subject.progress)
                self.fail_operation(subject, getattr(subject, name), "start_new" if settings else "start")
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
                self.assertEqual(subject.progress["quiz_session"]["from_welcome"], not settings)
                self.assertFalse(subject.questions)

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
        key = subject.quiz_items[1]["key"]
        self.assertEqual(subject.quiz_word.text, subject.bank[subject.quiz_item_indices[key]]["w"])
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

    def test_resume_last_answer_finishes_once_at_bank_exhaustion(self):
        original = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, theta=0.0)
        subject = make_subject(session=False, record=original.store.record)
        self.assertTrue(subject.start_quiz())
        self.assertEqual(subject.quiz_i, BANK_SIZE - 1)
        self.assertEqual(subject.display_mode, "result")
        self.assertEqual(subject.progress["theta"], 0.0)
        self.assertEqual(len(subject.progress["history"]), 101)
        self.assertEqual(subject.store.attempts, 1)
        self.assertFalse(subject._finish_quiz())
        self.assertEqual(subject.store.attempts, 1)

    def test_resume_last_failure_preserves_old_graph_and_finish_retry_once(self):
        original = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE, baseline=False, theta=None)
        subject = make_subject(session=False, record=original.store.record)
        self.fail_operation(subject, subject.start_quiz, "start")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.quiz_i, BANK_SIZE - 1)
        self.assertEqual(len(subject.progress["history"]), 101)
        self.assertEqual(len(subject.results), 1)

    def test_invalid_resume_replaced_only_after_successful_save(self):
        original = make_subject(answered=True)
        subject = make_subject(session=False, record=original.store.record)
        subject.progress["quiz_session"]["resp"].append(0)
        subject.store.record = json_copy(subject.progress)
        old_session = subject.progress["quiz_session"]
        self.fail_operation(subject, subject.start_quiz, "start")
        self.assertIs(subject.progress["quiz_session"], old_session)
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertIsNot(subject.progress["quiz_session"], old_session)
        self.assertNotEqual(subject.quiz_session_id, old_session["id"])
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), subject.quiz_resp), (0, 1, []))
        self.assertEqual(subject.store.record, json_copy(subject.progress))

    def test_skip_failure_and_retry_preserve_30_day_resumable_session(self):
        for answered in (False, True):
            with self.subTest(answered=answered):
                subject = make_subject(answered=answered)
                session = subject.progress["quiz_session"]
                before_session = json_copy(session)
                history = copy.deepcopy(subject.progress["history"])
                snooze = subject.progress["snooze_until"]
                self.fail_operation(subject, subject.skip_test, "skip")
                subject.store.before_write = None
                self.assertTrue(subject.retry_or_skip())
                self.assertIs(subject.progress["quiz_session"], session)
                self.assertEqual(subject.store.record["quiz_session"], before_session)
                self.assertEqual(subject.progress["history"], history)
                self.assertEqual(subject.progress["snooze_until"], snooze)
                self.assertEqual(subject.navigation, [("study",)])
                self.assertEqual(subject.btn_skip.text, "结束本次测试")
                self.assertFalse(subject.quiz_timer.active)
                attempts = subject.store.attempts
                self.assertFalse(subject.retry_or_skip())
                self.assertEqual(subject.store.attempts, attempts)
                # A cold restart within the retention window keeps every committed answer.
                restarted = make_subject(session=False, record=subject.store.record)
                restarted.namespace["time"] = types.SimpleNamespace(time=lambda: NOW + RESUME_TTL - 124)
                self.assertTrue(restarted.start_quiz())
                self.assertEqual(restarted.quiz_session_id, session["id"])
                self.assertEqual(restarted.quiz_resp, before_session["resp"])
                self.assertEqual(restarted.quiz_i, int(answered))

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
        self.assertEqual(subject.quiz_i, BANK_SIZE - 1)
        self.assertEqual(len(subject.quiz_resp), BANK_SIZE)
        self.assertEqual(len(subject.quiz_items), BANK_SIZE)
        self.assertEqual(subject.display_mode, "result")
        self.assertEqual(len(subject.results), 1)
        self.assertFalse(subject.dialogs)

    def test_fresh_settings_replaces_answered_session_in_one_save_without_dialog(self):
        for answered in (False, True):
            with self.subTest(answered=answered):
                subject = make_subject(answered=answered, book_confirmed=True)
                subject._set_mode("settings")
                old_session = subject.progress["quiz_session"]
                old_history = copy.deepcopy(subject.progress["history"])
                refs = references(subject)
                attempts, old_ui = subject.store.attempts, ui_state(subject)
                subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), old_ui)
                self.assertTrue(subject._test_from_settings())
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertFalse(subject.questions)
                self.assertIsNot(subject.progress["quiz_session"], old_session)
                self.assertNotEqual(subject.quiz_session_id, old_session["id"])
                self.assertEqual((subject.quiz_i, len(subject.quiz_items), subject.quiz_resp), (0, 1, []))
                self.assertEqual(subject.rigor, 100.0)
                self.assertEqual(subject.progress["history"], old_history)
                current = references(subject)
                for name, original in refs.items():
                    if (name in ("progress", "states", "cursors", "orders", "records", "book_record",
                                 "pending", "top_future", "known", "last_test", "prediction_data")
                            or name.startswith("graph/progress/")
                            and not name.startswith("graph/progress/quiz_session")):
                        self.assertIs(current[name], original, name)
                self.assertEqual(subject.store.record, json_copy(subject.progress))

    def test_forced_fresh_failure_restores_old_session_and_retry_remains_new_start(self):
        for origin in ("quiz", "settings", "result"):
            with self.subTest(origin=origin):
                subject = make_subject(answered=True, book_confirmed=True)
                subject._set_mode(origin)
                old_session = subject.progress["quiz_session"]
                old_id, old_resp = subject.quiz_session_id, list(subject.quiz_resp)
                self.fail_operation(subject, lambda: subject.start_quiz(fresh=True), "start_new")
                self.assertIs(subject.progress["quiz_session"], old_session)
                self.assertEqual(subject.quiz_resp, old_resp)
                subject.store.before_write = None
                before, refs, committed = payload(subject), references(subject), json_copy(subject.store.record)
                subject.store.fail_next()
                self.assertFalse(subject.retry_or_skip())
                self.assert_unchanged(subject, before, refs, committed)
                self.assertEqual(subject._quiz_retry_action, "start_new")
                attempts = subject.store.attempts
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertNotEqual(subject.quiz_session_id, old_id)
                self.assertEqual((subject.quiz_i, len(subject.quiz_items), subject.quiz_resp), (0, 1, []))
                self.assertEqual(len(subject.progress["history"]), 101)
                self.assertIsNot(subject.progress["quiz_session"], old_session)

    def test_result_new_quiz_confirmation_cancels_or_uses_fresh_transaction(self):
        subject = make_subject(answered=True, book_confirmed=True)
        subject._set_mode("result")
        before, refs, committed = payload(subject), references(subject), json_copy(subject.store.record)
        subject.namespace["question_answer"] = subject.namespace["QMessageBox"].Cancel
        attempts = subject.store.attempts
        self.assertFalse(subject._confirm_new_quiz())
        self.assert_unchanged(subject, before, refs, committed)
        self.assertEqual(subject.store.attempts, attempts)
        self.assertEqual(len(subject.questions), 1)
        subject.namespace["question_answer"] = subject.namespace["QMessageBox"].Yes
        self.fail_operation(subject, subject._confirm_new_quiz, "start_new")
        self.assertEqual(len(subject.questions), 2)
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(len(subject.questions), 2)  # retry never asks again or resumes old answers
        self.assertEqual(subject.quiz_resp, [])
        self.assertNotEqual(subject.quiz_session_id, committed["quiz_session"]["id"])

    def test_welcome_wrapper_resumes_existing_answers_without_forcing_fresh(self):
        original = make_subject(answered=True)
        subject = make_subject(session=False, record=original.store.record)
        old_id = subject.progress["quiz_session"]["id"]
        self.assertTrue(subject._welcome_test())
        self.assertEqual(subject.quiz_session_id, old_id)
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), subject.quiz_resp), (1, 2, [1]))
        self.assertFalse(subject.questions)
        self.assertEqual(subject.store.attempts, 1)

    def test_cold_resume_builds_stable_mapping_before_validating_reordered_bank(self):
        original = make_subject(index=2, count=3)
        subject = make_subject(session=False, record=original.store.record)
        subject.bank.reverse()
        subject.bs.reverse()
        subject.lvls.reverse()
        self.assertFalse(hasattr(subject, "quiz_item_indices"))
        session = subject.progress["quiz_session"]
        expected_state, expected_items, expected_resp = (copy.deepcopy(session[key])
                                                       for key in ("state", "items", "resp"))
        self.assertTrue(subject.start_quiz())
        self.assertIs(subject.progress["quiz_session"], session)
        self.assertIs(subject.quiz_state, session["state"])
        self.assertIs(subject.quiz_items, session["items"])
        self.assertIs(subject.quiz_resp, session["resp"])
        self.assertEqual(subject.quiz_state, expected_state)
        self.assertEqual(subject.quiz_items, expected_items)
        self.assertEqual(subject.quiz_resp, expected_resp)
        key = subject.quiz_items[2]["key"]
        self.assertEqual(subject.quiz_item_indices[key], BANK_SIZE - 3)
        self.assertEqual(subject.quiz_word.text, key)
        self.assertEqual(subject.store.attempts, 1)

    def test_50th_answer_advances_until_bank_exhaustion(self):
        subject = make_subject(answered=True, index=49, count=50)
        history = copy.deepcopy(subject.progress["history"])
        self.assertFalse(subject._test_bank_exhausted())
        self.assertTrue(subject._quiz_next())
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), len(subject.quiz_resp)), (50, 51, 50))
        self.assertEqual(subject.progress["history"], history)
        self.assertEqual(subject.display_mode, "quiz")
        self.assertFalse(subject.results)
        self.assertIn("quiz_session", subject.store.record)
        self.assert_quiz_status(subject.status.text)

    def test_generation_is_deterministic_unique_and_finite_including_unusable_entries(self):
        left, right = make_subject(), make_subject()
        for _ in range(BANK_SIZE):
            left_item, right_item = left._gen_item(), right._gen_item()
            self.assertEqual(left_item, right_item)
            if left_item is None:
                break
        else:
            self.fail("Generation did not terminate within the finite bank")
        self.assertEqual(len(left.quiz_items), BANK_SIZE)
        keys = [item["key"] for item in left.quiz_items]
        self.assertEqual(len(set(keys)), BANK_SIZE)
        self.assertTrue(all(isinstance(key, str) for key in left.quiz_state["asked"]))
        before = payload(left)
        self.assertIsNone(left._gen_item())
        self.assertEqual(payload(left), before)
        unusable = make_subject()
        for entry in unusable.bank:
            entry["s"] = ""
        self.assertIsNone(unusable._gen_item())
        self.assertEqual(len(unusable.quiz_items), 1)
        self.assertTrue(unusable._test_bank_exhausted())
        self.assertEqual(len(set(unusable.quiz_state["asked"])), BANK_SIZE)

    def test_invalid_snapshots_preserve_every_old_reference_until_fresh_save(self):
        mutations = {
            "legacy-algo": lambda s: s.update(algo="legacy"),
            "wrong-bank": lambda s: s.update(bank_id="other-bank"),
            "missing-id": lambda s: s.pop("id"),
            "empty-id": lambda s: s.update(id=""),
            "expired": lambda s: s.update(started_at=NOW - RESUME_TTL - 1),
            "exact-expiry": lambda s: s.update(started_at=NOW - RESUME_TTL),
            "nan-time": lambda s: s.update(started_at=float("nan")),
            "boolean-time": lambda s: s.update(started_at=True),
            "bad-rigor": lambda s: s.update(rigor=106),
            "boolean-index": lambda s: s.update(i=True),
            "lost-current-item": lambda s: s["items"].clear(),
            "extra-response": lambda s: s["resp"].extend([1, 0]),
            "bad-response": lambda s: s["resp"].append(True),
            "legacy-asked": lambda s: s["state"].update(asked=[0]),
            "unknown-key": lambda s: s["items"][0].update(key="not-in-bank"),
            "duplicate-asked": lambda s: s["state"]["asked"].append(s["state"]["asked"][0]),
            "bad-level": lambda s: s["state"].update(level=-1),
            "boolean-seed": lambda s: s["state"].update(seed=True),
            "bad-counter": lambda s: s["state"].update(up="invalid"),
            "bad-fast": lambda s: s["state"].update(fast=1),
            "missing-option": lambda s: s["items"][0]["item"]["options"].pop(),
            "bad-option-text": lambda s: s["items"][0]["item"]["options"][0].update(text=4),
            "bad-correct": lambda s: s["items"][0]["item"].update(correct_index=4),
        }
        original = make_subject()
        for case, mutate in mutations.items():
            with self.subTest(case=case):
                subject = make_subject(session=False, record=original.store.record)
                old_session = subject.progress["quiz_session"]
                mutate(old_session)
                self.fail_operation(subject, subject.start_quiz, "start")
                self.assertIs(subject.progress["quiz_session"], old_session)
                subject.store.before_write = None
                self.assertTrue(subject.retry_or_skip())
                self.assertIsNot(subject.progress["quiz_session"], old_session)
                self.assertNotEqual(subject.quiz_session_id, original.quiz_session_id)
                self.assertEqual(subject.quiz_resp, [])
                self.assertEqual((subject.quiz_i, len(subject.quiz_items)), (0, 1))
                self.assertEqual(subject.store.record["quiz_session"]["algo"], "bayes-v140")

    def test_finish_failure_and_retry_upsert_existing_id_without_duplicate_or_hidden_mastery(self):
        subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE,
                               baseline=False, theta=None, existing_history_index=12)
        existing = subject.progress["history"][12]
        subject.last_test = (existing, True)
        subject.store.record = json_copy(subject.progress)
        history_refs = list(subject.progress["history"])
        old_states, old_prediction = copy.deepcopy(subject.states), copy.deepcopy(subject.prediction_data)
        known, old_history = subject.known, copy.deepcopy(subject.progress["history"])
        self.fail_operation(subject, subject._finish_quiz, "finish")
        self.assertEqual(subject.progress["history"], old_history)
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(len(subject.progress["history"]), 100)
        self.assertEqual(sum(row.get("id") == subject.quiz_session_id
                             for row in subject.progress["history"]), 1)
        for i, original in enumerate(history_refs):
            self.assertIs(subject.progress["history"][i], original)
            if i != 12:
                self.assertEqual(original, old_history[i])
        self.assertIs(subject.last_test[0], existing)
        self.assertIs(subject.quiz_result, existing)
        self.assertTrue(existing["baseline"])
        self.assertEqual(existing["total"], BANK_SIZE)
        self.assertEqual(existing["algo"], "bayes-v140")
        self.assertTrue(existing["prediction_eligible"])
        self.assertTrue(existing["completed"])
        self.assertEqual(existing["future"], old_history[12]["future"])
        self.assertIsNone(subject.theta)
        self.assertIsNone(subject.progress["theta"])
        self.assertIs(subject.known, known)
        self.assertEqual(subject.states, old_states)
        self.assertEqual(subject.prediction_data, old_prediction)
        self.assertEqual(subject.store.record["prediction_state"], old_prediction)
        attempts = subject.store.attempts
        self.assertFalse(subject._finish_quiz())
        self.assertEqual(subject.store.attempts, attempts)

    def test_no_correct_answers_save_history_without_implicit_prediction(self):
        for response in (0, -1):
            with self.subTest(response=response):
                subject = make_subject()
                choice = -1 if response < 0 else 0
                self.assertTrue(subject._quiz_answer(choice))
                subject.quiz_timer.stop()
                history = copy.deepcopy(subject.progress["history"])
                row = subject.progress["history"][-1]
                self.assertEqual(len(history), 101)
                self.assertEqual(row["right"], 0)
                self.assertFalse(row["completed"])
                self.assertFalse(row["prediction_eligible"])
                before, known = copy.deepcopy(subject.progress), subject.known
                self.fail_operation(subject, subject._finish_quiz, "finish")
                subject.store.before_write = None
                attempts = subject.store.attempts
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertEqual(len(subject.progress["history"]), 101)
                self.assertEqual(subject.progress["history"][:-1], history[:-1])
                self.assertIs(subject.progress["history"][-1], row)
                self.assertEqual(row["total"], 1)
                self.assertEqual(row["right"], 0)
                self.assertEqual(row["dontknow"], int(response < 0))
                self.assertTrue(row["completed"])
                self.assertFalse(row["prediction_eligible"])
                self.assert_no_implicit_mastery(subject, before, known)
                self.assertNotIn("quiz_session", subject.store.record)
                self.assertEqual(subject.store.record["history"][-1], row)
                self.assertEqual(len(subject.results), 1)
                self.assertFalse(subject.notices)

    def test_first_answer_immediately_commits_session_and_history_once(self):
        for choice, response in ((1, 1), (0, 0), (-1, -1)):
            with self.subTest(choice=choice):
                subject = make_subject(history_count=140, theta=None, baseline=False)
                before, known = copy.deepcopy(subject.progress), subject.known
                history, rows = subject.progress["history"], list(subject.progress["history"])
                old_ui, attempts = ui_state(subject), subject.store.attempts
                self.assertEqual(len(history), 140)
                self.assertNotIn("history_id", subject.progress["quiz_session"])

                def before_write(data):
                    self.assertEqual(ui_state(subject), old_ui)
                    self.assertEqual(len(data["history"]), 141)
                    self.assertEqual(data["quiz_session"]["resp"], [response])
                    self.assertEqual(data["quiz_session"]["history_id"], subject.quiz_session_id)
                    self.assertEqual(data["history"][-1]["id"], subject.quiz_session_id)
                    self.assertEqual(data["history"][-1]["total"], 1)
                    self.assertFalse(data["history"][-1]["completed"])

                subject.store.before_write = before_write
                self.assertTrue(subject._quiz_answer(choice))
                subject.store.before_write = None
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertIs(subject.progress["history"], history)
                self.assertEqual(history[:-1], before["history"])
                for current, original in zip(history[:-1], rows):
                    self.assertIs(current, original)
                self.assert_no_implicit_mastery(subject, before, known)
                self.assert_quiz_status(subject.status.text)
                attempts = subject.store.attempts
                self.assertFalse(subject._quiz_answer(choice))
                self.assertEqual(subject.store.attempts, attempts)
                self.assertEqual(len(history), 141)

    def test_zero_answer_skip_never_creates_history(self):
        subject = make_subject(history_count=0)
        self.assertEqual(subject.progress["history"], [])
        self.assertTrue(subject.skip_test())
        self.assertEqual(subject.store.record["history"], [])
        self.assertFalse(subject.store.record["quiz_session"].get("history_id"))

    def test_in_progress_upsert_preserves_all_unknown_fields_and_shared_aliases(self):
        subject = make_subject(answered=True, history_count=140)
        row = subject.progress["history"][-1]
        shared = subject.quiz_state["future"]
        row["future"] = shared
        row["custom"] = {"keep": [7, None, {"next_schema": True}]}
        custom = row["custom"]
        subject.quiz_status_values["unknown"] = shared
        self.assertTrue(subject._quiz_next())
        history = subject.progress["history"]
        previous, row_refs = copy.deepcopy(history), list(history)
        subject.namespace["time"] = types.SimpleNamespace(time=lambda: NOW + 33)
        self.fail_operation(subject, lambda: subject._quiz_answer(-1), None)
        subject.store.before_write = None
        attempts = subject.store.attempts
        self.assertTrue(subject._quiz_answer(-1))
        self.assertEqual(subject.store.attempts, attempts + 1)
        self.assertEqual(len(history), 141)
        self.assertEqual(history[:-1], previous[:-1])
        for original, current in zip(row_refs, history):
            self.assertIs(current, original)
        self.assertIs(row["future"], shared)
        self.assertIs(row["custom"], custom)
        self.assertIs(subject.progress["quiz_session"]["future"]["shared"], shared)
        self.assertEqual(row["custom"], previous[-1]["custom"])
        self.assertEqual(row["total"], 2)
        self.assertFalse(row["completed"])
        self.assertEqual(subject.store.record["history"][-1], row)

    def test_capture_restores_return_flag_and_status_cache_unknown_aliases(self):
        subject = make_subject(answered=True)
        subject.quiz_return_to_settings = True
        shared = subject.quiz_state["future"]
        subject.quiz_status_values["future"] = shared
        subject.progress["history"][-1]["future"] = shared
        before, refs = payload(subject), references(subject)
        snapshot = subject._capture_quiz()
        subject.quiz_return_to_settings = False
        subject.quiz_status_values["future"]["keep"].append("transient")
        subject.quiz_status_values = {"replacement": []}
        subject._restore_quiz(snapshot)
        self.assert_unchanged(subject, before, refs, subject.store.record)
        self.assertIs(subject.quiz_status_values["future"], shared)
        self.assertIs(subject.progress["history"][-1]["future"], shared)

    def test_remaining_days_ceil_boundary_and_expired_session(self):
        subject = make_subject()
        for seconds, days in ((RESUME_TTL, 30), (86401, 2), (86400, 1),
                              (86399, 1), (1, 1), (0.1, 1), (0, 0), (-1, 0)):
            with self.subTest(seconds=seconds):
                session = {"started_at": NOW + seconds - RESUME_TTL,
                           "updated_at": NOW + RESUME_TTL}
                self.assertEqual(subject._quiz_remaining_days(session, now=NOW), days)
        for started_at in (None, True, float("nan"), float("inf"), "yesterday"):
            with self.subTest(started_at=started_at):
                self.assertEqual(subject._quiz_remaining_days({"started_at": started_at}, now=NOW), 0)
        self.assertEqual(subject._quiz_remaining_days({}, now=NOW), 0)
        self.assertEqual(subject._quiz_remaining_days(now=NOW), 30)

    def test_resume_and_skip_do_not_refresh_started_at_but_fresh_resets_30_days(self):
        original = make_subject(answered=True)
        subject = make_subject(session=False, record=original.store.record, book_confirmed=True)
        started_at, sid = original.quiz_started_at, original.quiz_session_id
        later = started_at + RESUME_TTL - 86401
        subject.namespace["time"] = types.SimpleNamespace(time=lambda: later)
        subject._set_mode("settings")
        self.assertTrue(subject.start_quiz())
        self.assertEqual(subject.quiz_started_at, started_at)
        self.assertEqual(subject._quiz_remaining_days(), 2)
        self.assertTrue(subject.skip_test())
        self.assertEqual(subject.store.record["quiz_session"]["started_at"], started_at)
        self.assertEqual(subject.store.record["quiz_session"]["updated_at"], later)
        self.assertEqual(subject.store.record["quiz_session"]["id"], sid)
        subject._set_mode("settings")
        old_history = copy.deepcopy(subject.progress["history"])
        self.assertTrue(subject._test_from_settings())
        self.assertNotEqual(subject.quiz_session_id, sid)
        self.assertEqual(subject.quiz_started_at, later)
        self.assertEqual(subject._quiz_remaining_days(), 30)
        self.assertEqual(subject.progress["history"], old_history)
        # The most recent updated_at cannot extend the original attempt at expiry.
        expired = make_subject(session=False, record=original.store.record)
        expired.progress["quiz_session"]["updated_at"] = started_at + RESUME_TTL
        expired.namespace["time"] = types.SimpleNamespace(time=lambda: started_at + RESUME_TTL)
        self.assertTrue(expired.start_quiz())
        self.assertNotEqual(expired.quiz_session_id, sid)
        self.assertEqual(expired.quiz_started_at, started_at + RESUME_TTL)

    def test_settings_new_and_resume_skip_return_through_settings_not_startup(self):
        for fresh in (False, True):
            with self.subTest(fresh=fresh):
                subject = make_subject(answered=True, book_confirmed=True)
                subject._set_mode("settings")
                start = subject._test_from_settings if fresh else subject.start_quiz
                self.assertTrue(start())
                self.assertTrue(subject.quiz_return_to_settings)
                subject.namespace["time"] = types.SimpleNamespace(time=lambda: NOW + 17)
                self.fail_operation(subject, subject.skip_test, "skip")
                self.assertTrue(subject.quiz_return_to_settings)
                subject.store.before_write = None
                attempts = subject.store.attempts
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertEqual(subject.display_mode, "settings")
                self.assertEqual(subject.navigation, [("settings",)])
                self.assertFalse(subject.results)

    def test_nonsettings_skip_keeps_startup_even_after_settings_attempt(self):
        subject = make_subject(book_confirmed=True)
        subject._set_mode("settings")
        self.assertTrue(subject._test_from_settings())
        self.assertTrue(subject.skip_test())
        subject._set_mode("front")
        self.assertTrue(subject.start_quiz())
        self.assertFalse(subject.quiz_return_to_settings)
        subject.navigation[:] = []
        self.assertTrue(subject.skip_test())
        self.assertEqual(subject.navigation, [("study",)])
        self.assertEqual(subject.display_mode, "front")

    def test_skip_failure_with_advanced_clock_restores_original_history_graph(self):
        subject = make_subject(answered=True)
        subject.progress["history"][-1]["future"] = subject.quiz_state["future"]
        subject.namespace["time"] = types.SimpleNamespace(time=lambda: NOW + 77)
        self.fail_operation(subject, subject.skip_test, "skip")
        subject.store.before_write = None
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.progress["quiz_session"]["started_at"], NOW - 123)
        self.assertEqual(subject.progress["quiz_session"]["updated_at"], NOW + 77)
        self.assertEqual(len(subject.progress["history"]), 101)

    def test_zero_right_50_answer_history_is_never_prediction_eligible(self):
        for response in (0, -1):
            with self.subTest(response=response):
                subject = make_subject(index=49, count=50, history_count=0)
                subject.quiz_resp[:] = [response] * 50
                subject.rigor = 100.0  # Threshold alone must not make all-unknown eligible.
                self.assertTrue(subject._save_quiz_session())
                self.assertEqual(len(subject.progress["history"]), 1)
                row = subject.progress["history"][0]
                self.assertEqual(row["total"], 50)
                self.assertEqual(row["right"], 0)
                self.assertFalse(row["prediction_eligible"])
                self.assertTrue(subject._finish_quiz())
                self.assertIs(subject.progress["history"][0], row)
                self.assertTrue(row["completed"])
                self.assertFalse(row["prediction_eligible"])

    def test_fresh_and_expired_legacy_answers_archive_in_same_new_session_commit(self):
        original = make_subject(answered=True)
        legacy = json_copy(original.store.record)
        # A pre-change fixture has committed answers but no same-id history yet.
        legacy["history"] = legacy["history"][:-1]
        for key in ("history_id", "history_response_count", "history_deleted"):
            legacy["quiz_session"].pop(key, None)
        for fresh in (False, True):
            with self.subTest(fresh=fresh):
                subject = make_subject(session=False, record=legacy)
                old_session = subject.progress["quiz_session"]
                if not fresh:
                    old_session["started_at"] = NOW - RESUME_TTL
                    old_session["updated_at"] = NOW
                subject.store.record = json_copy(subject.progress)
                old_history = copy.deepcopy(subject.progress["history"])
                self.fail_operation(subject, lambda: subject.start_quiz(fresh=fresh),
                                    "start_new" if fresh else "start")
                subject.store.before_write = None
                attempts = subject.store.attempts
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertEqual(len(subject.progress["history"]), 101)
                self.assertEqual(subject.progress["history"][:-1], old_history)
                archived = subject.progress["history"][-1]
                self.assertEqual(archived["id"], old_session["id"])
                self.assertEqual(archived["total"], 1)
                self.assertFalse(archived["completed"])
                self.assertNotEqual(subject.quiz_session_id, old_session["id"])
                self.assertEqual(subject.quiz_resp, [])
                self.assertEqual(subject._quiz_remaining_days(), 30)
                self.assertEqual(subject.store.record["history"][-1], archived)

    def test_quiz_status_colors_only_changed_numbers_and_keeps_max_without_delta(self):
        subject = make_subject(answered=True)
        subject.theme_key = "dark"
        row = subject.progress["history"][-1]
        cache = subject.quiz_status_values
        old = copy.deepcopy(cache)
        row["vocab"] = old["vocab"] + 20
        row["err"] = old["err"] + 1
        subject.rigor = 104.5
        attempts = subject.store.attempts
        subject._quiz_status(delta=999)
        self.assert_quiz_status(subject.status.text)
        self.assertNotIn("999", re.sub(r"<[^>]*>", "", subject.status.text))
        self.assertIn("#79e0ac", subject.status.text)
        spans = re.findall(r"<span[^>]*>(.*?)</span>", subject.status.text)
        self.assertTrue(spans)
        for number in spans:
            self.assertRegex(number, r"^(?:\d+(?:\.\d+)?|max)$")
        self.assertIs(subject.quiz_status_values, cache)
        row["vocab"] -= 10
        row["err"] -= 2
        subject.rigor = 70
        subject._quiz_status(delta=-999)
        self.assert_quiz_status(subject.status.text)
        self.assertIn("#ef9cad", subject.status.text)
        subject.rigor = 105
        subject._quiz_status()
        self.assert_quiz_status(subject.status.text)
        self.assertTrue(re.sub(r"<[^>]*>", "", subject.status.text).endswith("严谨度max"))
        self.assertEqual(subject.store.attempts, attempts)

    def test_closed_and_closing_callbacks_mutate_nothing(self):
        for closing in (False, True):
            with self.subTest(closing=closing):
                subject = make_subject(answered=True, index=BANK_SIZE - 1, count=BANK_SIZE)
                subject._closed, subject._closing = not closing, closing
                before, old_ui, attempts = payload(subject), ui_state(subject), subject.store.attempts
                callbacks = (lambda: subject._quiz_answer(1), subject._quiz_next,
                             subject._finish_quiz, subject.start_quiz, subject.skip_test,
                             subject._welcome_test, subject._test_from_settings,
                             subject._confirm_new_quiz, lambda: subject.start_quiz(fresh=True),
                             subject.retry_or_skip, subject._save_quiz_session)
                for callback in callbacks:
                    self.assertFalse(callback())
                self.assertEqual(payload(subject), before)
                self.assertEqual(ui_state(subject), old_ui)
                self.assertEqual(subject.store.attempts, attempts)
                self.assertFalse(subject.dialogs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
