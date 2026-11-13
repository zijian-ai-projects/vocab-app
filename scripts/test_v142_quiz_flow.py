# -*- coding: utf-8 -*-
"""V1.4.2 integration regression, Python 3.8; no legacy fixture import.

Default: python -B scripts/test_v142_quiz_flow.py
    Extract production Card methods with AST; use only synthetic words, plain
    objects, a fixed clock and an in-memory atomic store. No Qt/main import,
    user-record reads, application launch, or filesystem writes are needed.

Optional: python -B scripts/test_v142_quiz_flow.py --all --out <test-directory>
    Add offscreen Qt checks using ui_test_support.Sandbox ONLY. Output paths
    must be inside the workspace's .vocab-ui-tests. The Sandbox's real-record
    fingerprints are read-only guards, never fixtures loaded into a Card.
    Only synthetic progress / Sandbox.read_progress() enter tested Cards.

The legacy test_quiz_transactions.py intentionally remains untouched. Its
placement/rigor/650ms assumptions are not the V1.4.2 contract.
"""
import argparse
import ast
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import traceback
import types
import unittest
from contextlib import ExitStack
from functools import lru_cache
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TEST_ROOT = ROOT.parent / ".vocab-ui-tests"
sys.path.insert(0, str(APP))
import vocabulary_test as vt
import assessment_history as assessment_history

NOW = 1805000000
RESUME_TTL = 30 * 86400
PROTECTED = ("states", "cursors", "orders", "study_records", "prediction_state",
             "book", "daily_new_ledger", "school_knowledge", "theta", "future",
             "keybindings", "learning_policy")
FIELDS = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "quiz_locked",
          "theta", "known", "last_test", "mode", "_quiz_retry_action",
          "quiz_started_at", "quiz_last_answer_at", "quiz_session_id",
          "quiz_origin_welcome", "quiz_bank_fingerprint", "quiz_item_indices",
          "quiz_result", "quiz_return_to_settings", "quiz_status_values")
METHODS = {
    "_can_act", "save", "_capture_quiz", "_restore_quiz", "_set_quiz_retry",
    "_quiz_save_error", "retry_or_skip", "_assessment_bank", "start_quiz",
    "_gen_item", "_quiz_remaining_days", "_quiz_history_record",
    "_upsert_quiz_history", "_save_quiz_session", "skip_test",
    "_test_bank_exhausted", "_quiz_status", "_quiz_show", "_quiz_answer",
    "_quiz_next", "_finish_quiz", "_startup", "_quiz_build_begin",
    "_quiz_build_progress", "_quiz_build_end",
    "_welcome_test", "_test_from_settings", "_delete_history",
    "_open_history_page", "_fill_result", "_show_result", "_history_detail_text",
    "_fill_summary", "_show_summary", "_summary_done",
    "_show_assessment_method", "_assessment_method_text", "_show_band_profile",
    "_apply_prediction",
}
SOURCE = (APP / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(APP / "main.py"))
CARD = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "Card")
NODES = [node for node in CARD.body if isinstance(node, ast.FunctionDef) and node.name in METHODS]
missing = METHODS - {node.name for node in NODES}
if missing:
    raise AssertionError("V1.4.2 AST contract changed; missing: " + ", ".join(sorted(missing)))
PLAIN = ast.ClassDef(name="QuizSubject", bases=[], keywords=[], body=NODES, decorator_list=[])
CODE = compile(ast.fix_missing_locations(ast.Module(body=[PLAIN], type_ignores=[])),
               "<v142-quiz-flow-production-AST>", "exec")


def json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def word_key(index):
    chars = []
    for _ in range(5):
        chars.append(chr(97 + index % 26))
        index //= 26
    return "fixture" + "".join(reversed(chars))


@lru_cache(maxsize=6)
def raw_bank(size=2000):
    # Independent two-CJK-character meanings avoid the engine's conservative
    # shared-bigram distractor rejection. Digits in word keys are not allowed.
    return [{"w": word_key(i), "s": "n." + chr(0x4e00 + i // 200) + chr(0x5300 + i % 200),
             "frq": i + 1, "pos": ["n."], "lvl": i % 15, "b": -99.0}
            for i in range(size)]


@lru_cache(maxsize=6)
def prepared_bank(size=2000):
    # Shared only as an immutable-in-use fixture; production _assessment_bank
    # still performs its own first construction in tests of that contract.
    return vt.FrequencyBank(raw_bank(size))


def legacy_history(count=3):
    return [{"id": "legacy-%d" % i, "ts": NOW - 5000 + i, "vocab": 1234 + i,
             "right": 23, "dontknow": 7, "total": 51, "baseline": i == 0,
             "theta": -0.5, "se": 0.75, "lo": 800, "hi": 2400,
             "rigor": 73.125, "err": 41.125,
             "future": {"keep": [None, {"version": i}, [1, 2, 3]]}}
            for i in range(count)]


def legacy_session():
    return {"schema": 1, "algo": "legacy-staircase", "id": "untouched-old-attempt",
            "started_at": NOW - 500, "updated_at": NOW - 50, "i": 1,
            "state": {"up": 2, "down": 1, "level": 7, "rigor": 81.25},
            "resp": [0, -1], "items": [{"key": "historical-word", "old": True}],
            "future": {"nested": [False, None, {"raw": [1, "x"]}]}}


def progress_fixture(history_count=3):
    return {
        "memory_schema": 2, "app_version": "1.4.2", "theta": 0.75,
        "states": {"other-word": {"st": "learning", "lv": 5, "due": NOW + 999,
                                    "seen": 8, "custom": {"keep": [1, 2]}}},
        "cursors": {"other": 17, "future-book": 8},
        "orders": {"other": {"mode": "seq", "future": [1, 2]}},
        "study_records": {"other": {"cursor": 17, "pending": {"other-word": 3},
                                    "future": {"keep": [2, 3]}}},
        "prediction_state": {"schema": 1, "selected": [word_key(9)], "rejected": [],
                             "excluded": [word_key(10)], "effective": {
                                 "target": 1, "available": 2000, "selected": 1}},
        "history": legacy_history(history_count), "book_confirmed": True,
        "book": "cet4-all", "school_knowledge": "off",
        "daily_new_ledger": {"schema": 1, "days": {"2026-09-01": ["other-word", word_key(9)]},
                             "future": {"keep": [3, None, {"ledger": True}]}},
        "learning_policy": {"mode": "review_first", "daily_new": 17,
                            "future": {"keep": [4, 5]}},
        "keybindings": {"remember": "R", "forget": "F", "choice1": "A", "choice2": "S",
                        "choice3": "D", "choice4": "G", "unknown": "H", "next": "N"},
        "welcome_done": False, "quiz_declined": True, "quiz_from_welcome": False,
        "snooze_until": NOW + 100, "study_mode": "brush", "retry_gap": 3,
        "future": {"all_history": True, "keep": [1, None, {"custom": [2]}]},
        "quiz_archives": [{"archived_at": NOW - 6000, "reason": "fixture",
                           "session": {"id": "prior-archive", "future": [1, {"x": 2}]}}],
    }


class MemoryStorage:
    class StorageError(Exception):
        pass

    def __init__(self):
        self.attempts = self.commits = 0
        self.fail_at = None
        self.record = None
        self.before_write = None

    def atomic_save(self, path, data):
        if path != "memory://v142-progress":
            raise AssertionError("AST regression attempted non-memory storage: " + str(path))
        self.attempts += 1
        if self.before_write:
            self.before_write(data)
        if self.attempts == self.fail_at:
            raise self.StorageError("injected atomic-save failure")
        encoded = json_copy(data)
        self.record = encoded
        self.commits += 1

    def fail_next(self):
        self.fail_at = self.attempts + 1


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class Widget:
    """Only the interface used by extracted methods; never a Qt object."""
    def __init__(self, text="", *args):
        self.text, self.enabled, self.visible = text, True, True
        self.props, self.tooltip, self.value, self.points = {}, "", 0, []
        self.clicked, self.toggled = Signal(), Signal()

    def setText(self, value): self.text = value
    def setEnabled(self, value): self.enabled = bool(value)
    def setVisible(self, value): self.visible = bool(value)
    def show(self): self.visible = True
    def hide(self): self.visible = False
    def isHidden(self): return not self.visible
    def setProperty(self, key, value): self.props[key] = value
    def property(self, key): return self.props.get(key)
    def setToolTip(self, value): self.tooltip = value
    def setValue(self, value): self.value = value
    def setRange(self, minimum, maximum): self.minimum, self.maximum = minimum, maximum
    def repaint(self): pass
    def setWordWrap(self, value): pass
    def setTextFormat(self, value): pass
    def setObjectName(self, value): pass
    def setCheckable(self, value): pass
    def setFixedHeight(self, value): pass
    def verticalScrollBar(self): return self
    def style(self): return self
    def polish(self, widget): pass
    def unpolish(self, widget): pass
    def update(self): pass
    def deleteLater(self): pass


class Layout:
    def __init__(self): self.children = []
    def setContentsMargins(self, *args): pass
    def setSpacing(self, *args): pass
    def addWidget(self, widget, *args): self.children.append((widget, None))
    def addLayout(self, layout, *args): self.children.append((None, layout))
    def addStretch(self, *args): self.children.append((None, None))
    def count(self): return len(self.children)
    def takeAt(self, index):
        widget, layout = self.children.pop(index)
        return types.SimpleNamespace(widget=lambda: widget, layout=lambda: layout)
    def deleteLater(self): pass


class Timer:
    def __init__(self): self.active, self.remaining, self.starts = False, -1, []
    def stop(self): self.active, self.remaining = False, -1
    def start(self, delay):
        self.active, self.remaining = True, delay
        self.starts.append(delay)
    def expire(self, callback):
        self.stop()
        return callback()


class Clock:
    # Bind module helpers before the fixed-clock method shadows the class name.
    strftime = staticmethod(time.strftime)
    localtime = staticmethod(time.localtime)

    def __init__(self): self.now = NOW
    def time(self): return self.now


def make_subject(record=None, size=2000, mode="settings", history_count=3, cached=True):
    store, clock = MemoryStorage(), Clock()
    errors, notices, questions, reports = [], [], [], []

    def no_prediction(*args, **kwargs):
        raise AssertionError("new quiz must not apply prediction or per-word mastery")

    api = types.SimpleNamespace(**{name: getattr(vt, name) for name in (
        "ALGORITHM", "UNIT", "SESSION_SCHEMA", "MEASUREMENT_SCHEMA", "MIN_ITEMS",
        "MAX_ITEMS", "MIN_PER_BAND", "MAX_WORDS", "BAND_SIZE", "FrequencyBank",
        "population_summary", "population_summary_steps", "new_state",
        "next_item", "validate_session", "summarize")})
    namespace = dict(copy=copy, random=random.Random(142), math=math, os=os,
                     vt=api, assessment_history=assessment_history, storage=store,
                     time=clock, LETTERS="ABCD", RESUME_TTL=RESUME_TTL, VERSION="1.4.2",
                     PROGRESS_PATH="memory://v142-progress", question_answer=1,
                     pred=types.SimpleNamespace(apply_strategy=no_prediction,
                         select_prediction_candidates=no_prediction),
                     QVBoxLayout=Layout, QHBoxLayout=Layout, QLabel=Widget, QPushButton=Widget,
                     Qt=types.SimpleNamespace(PlainText=0, AlignTop=1),
                     QTimer=types.SimpleNamespace(singleShot=lambda _delay, callback: callback()),
                     QCoreApplication=types.SimpleNamespace(processEvents=lambda *args: None),
                     QEventLoop=types.SimpleNamespace(ExcludeUserInputEvents=1))

    def question(*args):
        questions.append(args)
        return namespace["question_answer"]

    namespace["QMessageBox"] = types.SimpleNamespace(
        Yes=1, Cancel=2, question=question,
        critical=lambda *args: errors.append(args),
        information=lambda *args: notices.append(args))
    exec(CODE, namespace)
    subject = namespace["QuizSubject"]()
    subject.store, subject.clock, subject.api, subject.namespace = store, clock, api, namespace
    subject.dialogs, subject.notices, subject.questions, subject.reports = errors, notices, questions, reports
    subject._closed = subject._closing = False
    subject.mode = subject.display_mode = mode
    subject.progress = json_copy(record) if record is not None else progress_fixture(history_count)
    for name in ("states", "cursors", "orders", "study_records"):
        setattr(subject, name, subject.progress[name])
    subject.theta = subject.progress.get("theta")
    subject.prediction_data = subject.progress["prediction_state"]
    subject.known = {word_key(9)}
    subject.study_mode, subject.retry_gap = "brush", 3
    subject.bank = raw_bank(size)
    if cached:
        subject._test_bank, subject._test_bank_source = prepared_bank(size), subject.bank
    subject.quiz_items, subject.quiz_resp, subject.quiz_i = [], [], 0
    subject.quiz_locked, subject._quiz_retry_action = False, None
    subject.quiz_result, subject.quiz_status_values = None, None
    subject.quiz_return_to_settings = False
    subject.result_ctx = "test"
    rows = subject.progress.get("history", [])
    subject.last_test = (rows[-1], False) if rows else None
    subject.quiz_timer = Timer()
    for name in ("status", "quiz_word", "quiz_progress", "btn_dontknow",
                 "btn_skip", "btn_band_profile", "res_big", "res_sub", "res_coverage",
                 "res_note", "chart", "chart_holder", "btn_start", "btn_rebase",
                 "btn_continue_quiz", "history_chart", "build_progress",
                 "summary_big", "summary_note", "method_text", "method_page"):
        setattr(subject, name, Widget())
    subject.opt_btns = [Widget() for _ in range(4)]
    subject.history_rows_layout = Layout()
    subject._ui_scale = lambda: 1.0
    subject._fit_choice_options = lambda scale: None
    subject._refresh_key_hints = lambda: None
    subject._refresh_settings = lambda: None
    subject.quiz_page = types.SimpleNamespace(verticalScrollBar=lambda: Widget())
    subject.method_scroll = Widget()
    subject.method_page = types.SimpleNamespace(verticalScrollBar=lambda: subject.method_scroll)
    subject.navigation, subject.transitions = [], []

    def set_mode(value):
        subject.mode = subject.display_mode = value
        subject.btn_skip.setVisible(value == "quiz")
        subject.transitions.append(value)

    def navigate(value):
        subject.navigation.append(value)
        set_mode(value)

    subject._set_mode = set_mode
    subject.open_settings = lambda: navigate("settings")
    subject.open_books = lambda context: navigate("books")
    subject._new_session = lambda: navigate("front")
    subject._read_only_report = lambda title, text: reports.append((title, text))
    subject.engine = types.SimpleNamespace(states=subject.states,
        record=subject.study_records["other"], known=subject.known)
    subject.queue, subject.qi = [{"key": "other-word", "kind": "review"}], 0
    store.record = json_copy(subject.progress)
    return subject


def start_subject(**kwargs):
    subject = make_subject(**kwargs)
    if not subject.start_quiz():
        raise AssertionError("fixture could not start: %r" % subject.dialogs)
    return subject


def choice_for(subject, response=1):
    correct = subject.quiz_items[subject.quiz_i]["item"]["correct_index"]
    return -1 if response == -1 else correct if response == 1 else (correct + 1) % 4


def add_aliases(subject):
    shared = {"keep": [1, None, {"nested": ["untouched"]}]}
    subject.quiz_state["future"] = shared
    subject.quiz_items[0]["future"] = shared
    subject.quiz_items[0]["item"]["options"][0]["future"] = shared
    subject.progress["quiz_session"]["future"] = {"shared": shared, "keep": [9, 8]}
    subject.store.record = json_copy(subject.progress)
    return shared


def snapshot_attempt(subject, count=80, answered=True):
    """A valid serialized snapshot with chosen unique items, NOT an RNG replay.

    This isolates the 80th-answer/finish boundary from early precision stops.
    The public validator checks every ID/meaning/IRT/phase before it is used.
    """
    bank = subject._assessment_bank()
    keys = list(bank.items)
    band_keys = {band["id"]: [key for key in keys if bank.items[key]["band"] == band["id"]]
                 for band in bank.bands}
    ordered = [band_keys[band["id"]][round_index]
               for round_index in range(count)
               for band in bank.bands if round_index < len(band_keys[band["id"]])][:count]
    items = []
    for index, key in enumerate(ordered):
        source = bank.items[key]
        key_index = keys.index(key)
        ids = [key] + [keys[(key_index + offset) % len(keys)] for offset in (1, 2, 3)]
        item = {"item_id": key, "word": source["word"], "correct_index": 0, "correct_key": "A",
                "options": [{"key": "ABCD"[i], "item_id": option, "text": bank.items[option]["sense"]}
                            for i, option in enumerate(ids)]}
        items.append({"key": key, "band": source["band"], "rank": source["rank"],
                      "phase": "survey" if index < len(bank.bands) else "adaptive",
                      "item": item, "irt": {name: source[name] for name in ("a", "b", "c")}})
    responses = [1 if i % 3 else -1 for i in range(count - int(not answered))]
    measurement = vt.summarize(bank, items, responses)
    state = vt.new_state(142)
    state.update(asked=ordered, theta=measurement["theta"], se=measurement["se"])
    sess = {"schema": 2, "algo": vt.ALGORITHM, "id": "synthetic-saved-attempt",
            "bank_id": bank.fingerprint, "started_at": NOW - 123, "updated_at": NOW - 3,
            "from_welcome": False, "state": state, "items": items, "resp": responses,
            "i": count - 1}
    if not vt.validate_session(sess, bank):
        raise AssertionError("invalid serialized boundary fixture")
    subject.progress["quiz_session"] = sess
    subject.quiz_state, subject.quiz_items, subject.quiz_resp = state, items, responses
    subject.quiz_i, subject.quiz_session_id = sess["i"], sess["id"]
    subject.quiz_started_at, subject.quiz_bank_fingerprint = sess["started_at"], sess["bank_id"]
    subject.quiz_origin_welcome = False
    subject.quiz_item_indices = {entry["w"]: i for i, entry in enumerate(subject.bank)}
    subject._set_mode("quiz")
    if responses:
        subject._upsert_quiz_history()
    subject._quiz_show()
    if answered:
        subject.quiz_locked = True
        for button in subject.opt_btns:
            button.setEnabled(False)
        subject.opt_btns[0].setProperty("state", "selected")
        subject.btn_dontknow.setEnabled(False)
        subject._quiz_status()
        subject.quiz_timer.start(350)
    subject.store.record = json_copy(subject.progress)
    return sess


def payload(subject):
    return copy.deepcopy({"progress": subject.progress,
                          "attrs": {name: getattr(subject, name) for name in FIELDS if hasattr(subject, name)}})


def references(subject):
    refs = {"engine/states": subject.engine.states, "engine/record": subject.engine.record,
            "engine/known": subject.engine.known, "study/queue": subject.queue}

    def collect(value, path, ancestors=()):
        if not isinstance(value, (dict, list, set, tuple)):
            return
        refs[path] = value
        if id(value) in ancestors:
            return
        ancestors += (id(value),)
        children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, (list, tuple)) else []
        for key, child in children:
            collect(child, path + "/" + str(key), ancestors)

    collect(subject.progress, "progress")
    for name in FIELDS + ("states", "cursors", "orders", "study_records", "prediction_data"):
        if hasattr(subject, name):
            collect(getattr(subject, name), "attr/" + name)
    return refs


def ui_state(subject):
    return copy.deepcopy((subject.display_mode, subject.status.text,
        subject.quiz_progress.value, subject.quiz_word.text,
        [(button.text, button.enabled, button.props) for button in subject.opt_btns],
        subject.btn_dontknow.enabled, subject.btn_dontknow.props))


def protected_state(subject):
    return copy.deepcopy(({key: subject.progress[key] for key in PROTECTED},
                          subject.theta, subject.known, subject.queue, subject.qi))


class V142FlowTests(unittest.TestCase):
    def assert_saved(self, subject):
        self.assertEqual(subject.store.record, json_copy(subject.progress))

    def assert_unchanged(self, subject, before, refs, committed, action=None):
        expected = copy.deepcopy(before)
        expected["attrs"]["_quiz_retry_action"] = action
        if action in ("next", "finish"):
            expected["attrs"]["quiz_locked"] = True
        self.assertEqual(payload(subject), expected)
        current = references(subject)
        self.assertEqual(set(current), set(refs))
        for name, original in refs.items():
            self.assertIs(current[name], original, name)
        self.assertEqual(subject.store.record, committed)
        self.assertIs(subject.engine.states, subject.states)
        self.assertIs(subject.engine.known, subject.known)
        self.assertIs(subject.engine.record, subject.study_records["other"])

    def fail_save(self, subject, callback, action):
        before, refs, committed = payload(subject), references(subject), json_copy(subject.store.record)
        old_ui, attempts, errors = ui_state(subject), subject.store.attempts, len(subject.dialogs)
        subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), old_ui)
        subject.store.fail_next()
        self.assertFalse(callback())
        subject.store.before_write = None
        self.assertEqual(subject.store.attempts, attempts + 1)
        self.assert_unchanged(subject, before, refs, committed, action)
        self.assertEqual(ui_state(subject), old_ui)
        self.assertEqual(len(subject.dialogs), errors + 1)
        self.assertFalse(subject.quiz_timer.active)
        if action:
            self.assertTrue(subject.btn_skip.enabled and subject.btn_skip.visible)
            self.assertEqual(subject.btn_skip.text, "重试保存并继续")

    def fail_model(self, subject, callback, action, method="summarize", call=1):
        before, refs, committed = payload(subject), references(subject), json_copy(subject.store.record)
        old_ui, attempts, errors = ui_state(subject), subject.store.attempts, len(subject.dialogs)
        original, calls = getattr(subject.api, method), []

        def fail(*args, **kwargs):
            calls.append(1)
            if len(calls) == call:
                raise ValueError("injected model failure")
            return original(*args, **kwargs)

        with patch.object(subject.api, method, side_effect=fail):
            self.assertFalse(callback())
        self.assertEqual(len(calls), call)
        self.assertEqual(subject.store.attempts, attempts)
        self.assert_unchanged(subject, before, refs, committed, action)
        self.assertEqual(ui_state(subject), old_ui)
        self.assertEqual(len(subject.dialogs), errors + 1)
        self.assertFalse(subject.quiz_timer.active)

    def test_ast_is_plain_and_main_no_longer_imports_placement(self):
        subject = make_subject()
        self.assertEqual(type(subject).__bases__, (object,))
        self.assertNotIn("__init__", type(subject).__dict__)
        imports = [alias.name for node in TREE.body if isinstance(node, ast.Import) for alias in node.names]
        self.assertNotIn("placement", imports)
        self.assertIn("vocabulary_test", imports)
        self.assertNotIn("main", sys.modules)
        self.assertNotIn("test_quiz_transactions", sys.modules)
        self.assertFalse(hasattr(subject, "rigor"))
        timer_source = ast.get_source_segment(SOURCE, next(node for node in CARD.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"))
        self.assertIn("self.quiz_timer.setSingleShot(True)", timer_source)
        self.assertIn("self.quiz_timer.timeout.connect(self._quiz_next)", timer_source)

    def test_assessment_bank_is_lazy_and_cached_by_list_identity(self):
        subject = make_subject(cached=False)
        self.assertFalse(hasattr(subject, "_test_bank"))
        values = []
        with patch.object(subject.api, "FrequencyBank", wraps=vt.FrequencyBank) as constructor:
            first = subject._assessment_bank(values.append)
            self.assertEqual((values[0], values[-1]), (0, 100))
            self.assertEqual(values, sorted(set(values)))
            self.assertGreater(len(values), 10)
            self.assertIs(subject._assessment_bank(lambda value: self.fail("cached bank reported progress")), first)
            self.assertEqual(constructor.call_count, 1)
            subject.bank = list(subject.bank)
            second = subject._assessment_bank()
            self.assertIsNot(second, first)
            self.assertEqual(second.fingerprint, first.fingerprint)
            self.assertEqual(constructor.call_count, 2)

    def test_cold_build_stays_visible_through_first_item_and_commit_for_all_origins(self):
        baseline = prepared_bank(2000)
        for mode, context in (("settings", "test"), ("welcome", "test"),
                              ("front", "test"), ("result", "history"), ("result", "test")):
            with self.subTest(mode=mode, context=context):
                subject = make_subject(mode=mode, cached=False)
                subject.result_ctx = context
                before = protected_state(subject)

                def ready_bank(words, progress=None):
                    progress(0)
                    progress(100)
                    return baseline

                original_show = subject._quiz_show

                def ready_question():
                    self.assertEqual(subject.display_mode, "building")
                    self.assertEqual(subject.build_progress.value, 100)
                    original_show()

                subject.store.before_write = lambda data: self.assertEqual(subject.display_mode, "building")
                with patch.object(subject.api, "FrequencyBank", side_effect=ready_bank), \
                        patch.object(subject, "_quiz_show", side_effect=ready_question):
                    self.assertTrue(subject.start_quiz(fresh=True))
                self.assertEqual(subject.transitions, ["building", "quiz"])
                self.assertEqual(subject.quiz_return_to_settings,
                                 mode == "settings" or (mode == "result" and context == "history"))
                self.assertEqual(subject.quiz_origin_welcome, mode == "welcome")
                self.assertEqual(protected_state(subject), before)
                self.assertFalse(hasattr(subject, "_build_prior_mode"))
                self.assert_saved(subject)

    def test_cold_build_failures_restore_visible_page_and_transaction(self):
        baseline = prepared_bank(2000)
        for mode in ("settings", "welcome", "front"):
            for fault in ("bank", "validation", "generation", "save", "unexpected"):
                with self.subTest(mode=mode, fault=fault):
                    subject = make_subject(mode=mode, cached=False)
                    before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
                    old_ui = ui_state(subject)

                    def ready_bank(words, progress=None):
                        progress(0)
                        progress(100)
                        if fault == "bank":
                            raise ValueError("injected cold bank failure")
                        return baseline

                    with ExitStack() as stack:
                        stack.enter_context(patch.object(subject.api, "FrequencyBank", side_effect=ready_bank))
                        if fault == "validation":
                            stack.enter_context(patch.object(subject.api, "validate_session",
                                                             side_effect=ValueError("injected validation failure")))
                        elif fault in ("generation", "unexpected"):
                            error = RuntimeError("unexpected generation failure") if fault == "unexpected" else ValueError("injected generation failure")
                            stack.enter_context(patch.object(subject.api, "next_item", side_effect=error))
                        elif fault == "save":
                            subject.store.fail_next()
                        if fault == "unexpected":
                            with self.assertRaisesRegex(RuntimeError, "unexpected generation failure"):
                                subject.start_quiz(fresh=True)
                        else:
                            self.assertFalse(subject.start_quiz(fresh=True))
                    self.assert_unchanged(subject, before, refs, disk,
                                          None if fault == "unexpected" else "start_new")
                    self.assertEqual(ui_state(subject), old_ui)
                    self.assertFalse(hasattr(subject, "_build_prior_mode"))

    def test_cold_answered_resume_enters_visible_quiz_even_from_quiz_origin(self):
        baseline = prepared_bank(2000)
        source = start_subject(history_count=0)
        self.assertTrue(source._quiz_answer(-1))
        subject = make_subject(record=source.store.record, mode="quiz", cached=False)

        def ready_bank(words, progress=None):
            progress(0)
            progress(100)
            return baseline

        subject.store.before_write = lambda data: self.assertEqual(subject.display_mode, "building")
        with patch.object(subject.api, "FrequencyBank", side_effect=ready_bank):
            self.assertTrue(subject.start_quiz())
        self.assertEqual(subject.transitions, ["building", "quiz"])
        self.assertEqual((subject.quiz_i, len(subject.quiz_resp)), (1, 1))
        self.assertEqual(subject.progress["history"][0]["total"], 1)
        self.assert_saved(subject)

    def test_method_text_is_immediate_without_counting_or_building(self):
        subject = make_subject(cached=False)
        before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
        with patch.object(subject.api, "population_summary",
                          side_effect=AssertionError("method page counted the population")), \
                patch.object(subject.api, "population_summary_steps",
                             side_effect=AssertionError("method page scheduled population batches")), \
                patch.object(subject.api, "FrequencyBank",
                             side_effect=AssertionError("method page built the test bank")):
            self.assertTrue(subject._show_assessment_method())
        self.assertEqual(subject.display_mode, "method")
        self.assertNotIn("正在准备", subject.method_text.text)
        self.assertIn("最多保留 20,000 个词目", subject.method_text.text)
        self.assertIn("每 1,000 个有效词目一层，最多20层", subject.method_text.text)
        self.assertFalse(hasattr(subject, "_test_bank"))
        self.assertFalse(hasattr(subject, "_method_summary_pending_source"))
        subject.open_settings()
        self.assertTrue(subject._show_assessment_method())
        self.assertIn("方法与限制", subject.method_text.text)
        subject.open_settings()
        self.assert_unchanged(subject, before, refs, disk)

    def test_local_frequency_population_is_capped_and_ranked_not_legacy_difficulty(self):
        words = copy.deepcopy(raw_bank(20003))
        words.extend([{"w": "invalidfrequency", "frq": 0, "s": "n.无效"},
                      {"w": "invalidmeaning", "frq": 0.1, "s": ""}])
        words.reverse()
        before = copy.deepcopy(words)
        bank = vt.FrequencyBank(words)
        self.assertEqual((bank.size, bank.excluded_count, len(bank.bands)), (20000, 5, 20))
        self.assertEqual([band["size"] for band in bank.bands], [1000] * 20)
        self.assertEqual(bank.items[word_key(0)]["rank"], 1)
        self.assertEqual(bank.items[word_key(19999)]["rank"], 20000)
        self.assertNotIn(word_key(20000), bank.items)
        self.assertAlmostEqual(bank.items[word_key(0)]["b"], math.log(101 / 1000.0))
        self.assertEqual(words, before)
        self.assertEqual((vt.MIN_ITEMS, vt.MAX_ITEMS, vt.MIN_PER_BAND), (40, 80, 2))
        summary = vt.population_summary(words)
        self.assertEqual((summary["size"], summary["excluded_count"], summary["bands"]),
                         (bank.size, bank.excluded_count, len(bank.bands)))

    def test_fresh_start_one_atomic_save_with_no_unanswered_history(self):
        subject = make_subject(history_count=0)
        before, old_ui = protected_state(subject), ui_state(subject)
        subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), old_ui)
        self.assertTrue(subject.start_quiz(fresh=True))
        self.assertEqual((subject.store.attempts, subject.store.commits), (1, 1))
        self.assertEqual(subject.progress["history"], [])
        session = subject.progress["quiz_session"]
        self.assertEqual((session["schema"], session["algo"], session["i"], session["resp"]),
                         (2, "vst-cat-v142", 0, []))
        self.assertEqual(len(session["items"]), 1)
        self.assertTrue({"key", "band", "rank", "phase", "item", "irt"}.issubset(session["items"][0]))
        self.assertTrue(vt.validate_session(session, subject._assessment_bank()))
        self.assertEqual(protected_state(subject), before)
        self.assertFalse(subject.quiz_locked or subject.quiz_timer.active)
        self.assert_saved(subject)

    def test_start_failure_restores_absent_attributes_and_welcome_flags(self):
        subject = make_subject(mode="welcome")
        for key in ("welcome_done", "quiz_from_welcome", "quiz_archives"):
            subject.progress.pop(key)
        subject.store.record = json_copy(subject.progress)
        self.fail_save(subject, subject.start_quiz, "start")
        self.assertFalse(hasattr(subject, "quiz_state"))
        self.assertNotIn("quiz_session", subject.progress)
        self.assertTrue(subject.progress["quiz_declined"])
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.quiz_resp, [])
        self.assertTrue(subject.quiz_origin_welcome)

    def test_entry_wrappers_start_directly_without_confirmation_dialog(self):
        for name in ("_welcome_test", "_test_from_settings"):
            with self.subTest(wrapper=name):
                subject = make_subject()
                self.assertFalse(hasattr(subject, "_confirm_new_quiz"))
                questions = len(subject.questions)
                self.fail_save(subject, getattr(subject, name), "start_new")
                self.assertEqual(len(subject.questions), questions,
                                 "starting a test must not show a confirmation dialog")
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.quiz_resp, [])
                self.assertEqual(subject.store.commits, 1)

    def test_legacy_session_archived_exactly_without_rescoring_old_history(self):
        for fresh in (False, True):
            with self.subTest(fresh=fresh):
                subject = make_subject()
                old = legacy_session()
                subject.progress["quiz_session"] = old
                old_saved, history = copy.deepcopy(old), copy.deepcopy(subject.progress["history"])
                old_refs = references(subject)
                with patch.object(subject.api, "summarize", side_effect=AssertionError("legacy must never be rescored")):
                    self.assertTrue(subject.start_quiz(fresh=fresh))
                archived = subject.progress["quiz_archives"][-1]["session"]
                self.assertEqual(archived, old_saved)
                self.assertIsNot(archived, old)
                self.assertIsNot(archived["future"], old["future"])
                self.assertEqual(old, old_saved)
                self.assertEqual(subject.progress["history"], history)
                self.assertIs(subject.progress["history"], old_refs["progress/history"])
                self.assertIs(subject.progress["quiz_archives"], old_refs["progress/quiz_archives"])
                self.assertIs(subject.progress["history"][0], old_refs["progress/history/0"])
                self.assertEqual(subject.store.attempts, 1)
                self.assert_saved(subject)

    def test_fresh_archive_save_failure_preserves_every_existing_reference(self):
        subject = start_subject()
        self.assertTrue(subject._quiz_answer(choice_for(subject, 0)))
        add_aliases(subject)
        old_session = subject.progress["quiz_session"]
        old_history = copy.deepcopy(subject.progress["history"])
        self.fail_save(subject, lambda: subject.start_quiz(fresh=True), "start_new")
        for _ in range(2):
            self.fail_save(subject, subject.retry_or_skip, "start_new")
        self.assertTrue(subject.retry_or_skip())
        self.assertIsNot(subject.progress["quiz_session"], old_session)
        self.assertEqual(subject.progress["quiz_archives"][-1]["session"], old_session)
        self.assertEqual(subject.progress["history"], old_history)
        self.assertEqual(subject.quiz_resp, [])

    def test_malformed_archive_container_is_not_overwritten(self):
        subject = make_subject()
        subject.progress["quiz_session"] = legacy_session()
        subject.progress["quiz_archives"] = {"future": [1, 2]}
        subject.store.record = json_copy(subject.progress)
        before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
        self.assertFalse(subject.start_quiz(fresh=True))
        self.assert_unchanged(subject, before, refs, disk, "start_new")
        self.assertEqual(subject.store.attempts, 0)

    def test_no_response_creates_no_history_on_pause_or_history_open(self):
        subject = start_subject(history_count=0)
        self.assertIsNone(subject._quiz_history_record())
        self.assertTrue(subject.skip_test())
        self.assertEqual(subject.progress["history"], [])
        attempts = subject.store.attempts
        self.assertTrue(subject._open_history_page())
        self.assertEqual(subject.progress["history"], [])
        self.assertEqual(subject.store.attempts, attempts)

    def test_answer_commit_is_atomic_and_feedback_never_reveals_correctness(self):
        for response in (1, 0, -1):
            with self.subTest(response=response):
                subject = start_subject()
                add_aliases(subject)
                previous, before = ui_state(subject), protected_state(subject)
                old_history = copy.deepcopy(subject.progress["history"])
                attempts = subject.store.attempts
                subject.store.before_write = lambda data: self.assertEqual(ui_state(subject), previous)
                choice = choice_for(subject, response)
                self.assertTrue(subject._quiz_answer(choice))
                self.assertEqual(subject.store.attempts, attempts + 1)
                self.assertEqual(subject.quiz_resp, [response])
                self.assertEqual(len(subject.progress["history"]), len(old_history) + 1)
                self.assertEqual(subject.progress["history"][:-1], old_history)
                self.assertEqual(subject.progress["history"][-1]["total"], 1)
                self.assertEqual(subject.progress["history"][-1]["dontknow"], int(response == -1))
                self.assertNotIn("rigor", subject.progress["history"][-1])
                self.assertNotIn("err", subject.progress["history"][-1])
                self.assertFalse(hasattr(subject, "rigor"))
                self.assertTrue(subject.quiz_locked)
                self.assertEqual(subject.quiz_timer.starts[-1], 350)
                self.assertTrue(subject.quiz_timer.active)
                self.assertEqual([button.props["state"] for button in subject.opt_btns],
                                 ["picked" if i == choice else "" for i in range(4)])
                self.assertEqual(subject.btn_dontknow.props["state"],
                                 "picked" if response == -1 else "")
                self.assertFalse(any(button.enabled for button in subject.opt_btns))
                self.assertFalse(subject.btn_dontknow.enabled)
                captions = [row[0] for row in previous[4]]
                self.assertEqual([button.text for button in subject.opt_btns], captions)
                self.assertEqual([button.props["_quiz_caption"] for button in subject.opt_btns], captions)
                self.assertEqual(subject.status.text, "词汇测试 · 已答 1 / 最多80")
                self.assertNotRegex(subject.status.text, "准备下一题|严谨度|误差|正确答案|None")
                self.assertFalse(hasattr(subject, "quiz_phase"))
                self.assertEqual(protected_state(subject), before)
                self.assert_saved(subject)

    def test_wrong_and_dontknow_have_identical_posterior_without_rigor_rewards(self):
        original = start_subject()
        wrong = make_subject(record=original.store.record)
        unknown = make_subject(record=original.store.record)
        self.assertTrue(wrong.start_quiz() and unknown.start_quiz())
        self.assertTrue(wrong._quiz_answer(choice_for(wrong, 0)))
        self.assertTrue(unknown._quiz_answer(-1))
        for key in ("theta", "se", "vocab", "lo", "hi"):
            self.assertEqual(wrong.progress["history"][-1][key], unknown.progress["history"][-1][key])
        self.assertEqual((wrong.quiz_resp, unknown.quiz_resp), ([0], [-1]))
        self.assertEqual(len(wrong.progress["history"]), len(unknown.progress["history"]))

    def test_duplicate_and_illegal_choices_are_noops(self):
        subject = start_subject()
        for choice in (None, True, False, "0", 0.0, 1.0, -2, 4, 999, [], {}):
            before, attempts = payload(subject), subject.store.attempts
            self.assertFalse(subject._quiz_answer(choice), repr(choice))
            self.assertEqual(payload(subject), before)
            self.assertEqual(subject.store.attempts, attempts)
        self.assertTrue(subject._quiz_answer(choice_for(subject)))
        attempts = subject.store.attempts
        self.assertFalse(subject._quiz_answer(-1))
        subject.quiz_locked = False
        self.assertFalse(subject._quiz_answer(-1))
        self.assertEqual(subject.quiz_resp, [1])
        self.assertEqual(subject.store.attempts, attempts)

    def test_answer_save_failure_restores_nested_aliases_for_every_response(self):
        for response in (1, 0, -1):
            with self.subTest(response=response):
                subject = start_subject()
                shared = add_aliases(subject)
                self.fail_save(subject, lambda: subject._quiz_answer(choice_for(subject, response)), None)
                self.assertIs(subject.quiz_state["future"], shared)
                self.assertIs(subject.quiz_items[0]["future"], shared)
                self.assertIs(subject.progress["quiz_session"]["future"]["shared"], shared)
                self.assertFalse(subject.quiz_locked)
                subject.save(force=True)
                cold = make_subject(record=subject.store.record)
                self.assertTrue(cold.start_quiz())
                self.assertEqual(cold.quiz_resp, [])

    def test_model_failure_before_and_after_theta_update_restores_answer(self):
        for call in (1, 2):
            with self.subTest(summarize_call=call):
                subject = start_subject()
                add_aliases(subject)
                self.fail_model(subject, lambda: subject._quiz_answer(choice_for(subject)), None, call=call)
                self.assertFalse(hasattr(subject, "quiz_last_answer_at"))
                self.assertEqual(subject.quiz_resp, [])
                self.assertTrue(subject._quiz_answer(choice_for(subject)))

    def test_snapshot_roundtrip_restores_all_mutable_quiz_and_archive_objects(self):
        subject = start_subject()
        add_aliases(subject)
        before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
        snapshot = subject._capture_quiz()
        subject.quiz_state["future"]["keep"].append("changed")
        subject.quiz_items[0]["item"]["options"][0]["text"] = "changed"
        subject.quiz_items.append({"key": "transient"})
        subject.quiz_resp.append(1)
        subject.progress["history"][0]["future"]["keep"].append("changed")
        subject.progress["quiz_archives"][0]["session"]["future"].append("changed")
        subject.progress["quiz_archives"].append({"new": True})
        subject.progress.pop("quiz_session")
        subject.progress["new_key"] = True
        subject.known = {"changed"}
        subject._restore_quiz(snapshot)
        self.assert_unchanged(subject, before, refs, disk)

    def test_success_preserves_existing_session_history_and_unknown_extensions(self):
        subject = start_subject()
        add_aliases(subject)
        session, state, items, responses = subject.progress["quiz_session"], subject.quiz_state, subject.quiz_items, subject.quiz_resp
        self.assertTrue(subject._quiz_answer(choice_for(subject)))
        row = subject.progress["history"][-1]
        row["future_v200"] = {"do_not_drop": [1, None]}
        extra = row["future_v200"]
        self.assertTrue(subject._quiz_next())
        self.assertTrue(subject._quiz_answer(-1))
        self.assertIs(subject.progress["quiz_session"], session)
        self.assertIs(subject.quiz_state, state)
        self.assertIs(subject.quiz_items, items)
        self.assertIs(subject.quiz_resp, responses)
        self.assertIs(subject.progress["history"][-1], row)
        self.assertIs(row["future_v200"], extra)
        self.assertEqual(row["total"], 2)
        self.assertEqual(subject.progress["quiz_session"]["history_response_count"], 2)
        self.assert_saved(subject)

    def test_next_save_failures_only_retry_advancement_not_scoring(self):
        subject = start_subject()
        self.assertTrue(subject._quiz_answer(choice_for(subject, 0)))
        add_aliases(subject)
        state, item = copy.deepcopy(subject.quiz_state), subject.quiz_items[0]
        row = subject.progress["history"][-1]
        for _ in range(3):
            self.fail_save(subject, subject._quiz_next if not subject._quiz_retry_action else subject.retry_or_skip, "next")
            self.assertFalse(subject._quiz_answer(-1))
            self.assertEqual((len(subject.quiz_items), subject.quiz_resp), (1, [0]))
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), subject.quiz_resp), (1, 2, [0]))
        self.assertIs(subject.quiz_items[0], item)
        self.assertIs(subject.progress["history"][-1], row)
        self.assertEqual(row["total"], 1)
        self.assertEqual(subject.quiz_state["theta"], state["theta"])
        self.assertEqual(subject.quiz_state["se"], state["se"])
        self.assertFalse(subject.quiz_locked or subject.quiz_timer.active)
        before, attempts = payload(subject), subject.store.attempts
        self.assertFalse(subject._quiz_next())
        self.assertEqual(payload(subject), before)
        self.assertEqual(subject.store.attempts, attempts)

    def test_next_model_and_generation_failures_restore_pending_transition(self):
        for method in ("summarize", "next_item"):
            with self.subTest(method=method):
                subject = start_subject()
                self.assertTrue(subject._quiz_answer(-1))
                self.fail_model(subject, subject._quiz_next, "next", method=method)
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.quiz_resp, [-1])
                self.assertEqual(subject.quiz_i, 1)

    def test_finish_save_failure_retry_commits_one_result_without_rescoring(self):
        subject = make_subject()
        snapshot_attempt(subject)
        add_aliases(subject)
        protected, row = protected_state(subject), subject.progress["history"][-1]
        for _ in range(3):
            self.fail_save(subject, subject._quiz_next if not subject._quiz_retry_action else subject.retry_or_skip, "finish")
            self.assertIs(subject.progress["history"][-1], row)
            self.assertFalse(row["completed"])
            self.assertEqual(len(subject.quiz_resp), 80)
        attempts = subject.store.attempts
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.store.attempts, attempts + 1)
        self.assertEqual(subject.mode, "summary")
        self.assertEqual((row["total"], row["stop_reason"], row["completed"]), (80, "max_items", True))
        self.assertIs(subject.quiz_result, row)
        self.assertNotIn("quiz_session", subject.progress)
        self.assertEqual(protected_state(subject), protected)
        attempts = subject.store.attempts
        self.assertFalse(subject._finish_quiz())
        self.assertFalse(subject._quiz_next())
        self.assertFalse(subject.retry_or_skip())
        self.assertEqual(subject.store.attempts, attempts)
        self.assert_saved(subject)

    def test_finish_model_failure_rolls_back_and_remains_retryable(self):
        subject = make_subject()
        snapshot_attempt(subject)
        self.fail_model(subject, subject._finish_quiz, "finish")
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.mode, "summary")
        self.assertEqual(subject.progress["history"][-1]["total"], 80)

    def test_finish_rejects_incomplete_nonquiz_or_already_committed_snapshots(self):
        for case in ("incomplete", "nonquiz", "missing-session"):
            with self.subTest(case=case):
                subject = make_subject()
                snapshot_attempt(subject, count=2, answered=case != "incomplete")
                if case == "nonquiz": subject.mode = "settings"
                if case == "missing-session": subject.progress.pop("quiz_session")
                before, attempts = payload(subject), subject.store.attempts
                self.assertFalse(subject._finish_quiz())
                self.assertEqual(payload(subject), before)
                self.assertEqual(subject.store.attempts, attempts)

    def test_pause_save_and_model_failures_restore_then_return_to_settings(self):
        for answered in (False, True):
            with self.subTest(answered=answered):
                subject = start_subject()
                if answered: self.assertTrue(subject._quiz_answer(-1))
                self.fail_save(subject, subject.skip_test, "skip")
                if answered:
                    self.fail_model(subject, subject.retry_or_skip, "skip")
                old_responses = list(subject.quiz_resp)
                self.assertTrue(subject.retry_or_skip())
                self.assertEqual(subject.mode, "settings")
                self.assertEqual(subject.progress["quiz_session"]["resp"], old_responses)
                self.assertFalse(subject.quiz_timer.active)

    def test_pending_resume_preserves_item_option_order_and_original_references(self):
        source = start_subject()
        add_aliases(source)
        subject = make_subject(record=source.store.record)
        session = subject.progress["quiz_session"]
        items, state, responses = session["items"], session["state"], session["resp"]
        saved = copy.deepcopy(session)
        with patch.object(subject.api, "next_item", side_effect=AssertionError("pending item must not regenerate")):
            self.assertTrue(subject.start_quiz())
        self.assertIs(subject.progress["quiz_session"], session)
        self.assertIs(subject.quiz_items, items)
        self.assertIs(subject.quiz_state, state)
        self.assertIs(subject.quiz_resp, responses)
        self.assertEqual(session, saved)
        self.assertEqual(subject.quiz_i, 0)
        self.assertTrue(all(button.enabled for button in subject.opt_btns))
        self.assertEqual(subject.store.attempts, 1)

    def test_pending_resume_failure_restores_pre_start_objects(self):
        source = start_subject()
        subject = make_subject(record=source.store.record)
        self.fail_save(subject, subject.start_quiz, "start")
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, subject.quiz_resp), (0, []))

    def test_answered_feedback_resume_only_advances_once(self):
        source = start_subject()
        self.assertTrue(source._quiz_answer(choice_for(source, 0)))
        source.save(force=True)
        subject = make_subject(record=source.store.record)
        session = subject.progress["quiz_session"]
        item, state = session["items"][0], copy.deepcopy(session["state"])
        with patch.object(subject, "_quiz_answer", side_effect=AssertionError("resume must not answer again")):
            self.assertTrue(subject.start_quiz())
        self.assertEqual((subject.quiz_i, len(subject.quiz_items), subject.quiz_resp), (1, 2, [0]))
        self.assertIs(subject.quiz_items[0], item)
        self.assertEqual(subject.quiz_state["theta"], state["theta"])
        self.assertEqual(subject.quiz_state["se"], state["se"])
        self.assertEqual(subject.progress["history"][-1]["total"], 1)
        self.assertEqual(subject.store.attempts, 1)

    def test_answered_resume_failure_retries_start_not_answer_or_partial_next(self):
        source = start_subject()
        self.assertTrue(source._quiz_answer(-1))
        subject = make_subject(record=source.store.record)
        self.fail_save(subject, subject.start_quiz, "start")
        self.assertEqual(subject.mode, "settings")
        self.assertFalse(hasattr(subject, "quiz_state"))
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual((subject.quiz_i, subject.quiz_resp), (1, [-1]))

    def test_30_day_ttl_is_from_start_not_last_save_and_invalid_clocks_fail_closed(self):
        subject = start_subject()
        session = subject.progress["quiz_session"]
        started = session["started_at"]
        cases = ((started, 30), (started + 86400, 29),
                 (started + RESUME_TTL - 1, 1), (started + RESUME_TTL, 0),
                 (started - 1, 0), (True, 0), (float("nan"), 0), (float("inf"), 0))
        for now, expected in cases:
            self.assertEqual(subject._quiz_remaining_days(session, now=now), expected, repr(now))
        cold = make_subject(record=subject.store.record)
        cold.clock.now = started + 29 * 86400
        self.assertTrue(cold.start_quiz())
        self.assertEqual(cold.quiz_started_at, started)
        self.assertEqual(cold._quiz_remaining_days(), 1)

    def test_cold_resumable_startup_defers_bank_build_until_continue(self):
        source = start_subject()
        cold = make_subject(record=source.store.record, cached=False)
        self.assertIsNone(getattr(cold, "_test_bank", None))
        self.assertGreater(cold._quiz_remaining_days(validate_bank=False), 0)
        self.assertIsNone(getattr(cold, "_test_bank", None))
        cold._startup()
        self.assertIsNone(getattr(cold, "_test_bank", None))
        self.assertTrue(cold.start_quiz())
        self.assertIsNotNone(getattr(cold, "_test_bank", None))
        self.assertEqual(cold.quiz_session_id, source.quiz_session_id)

    def test_expired_changed_meaning_old_algorithm_and_disabled_attempts_do_not_resume(self):
        for reason in ("expired", "meaning", "algorithm", "resume_disabled"):
            with self.subTest(reason=reason):
                source = start_subject()
                self.assertTrue(source._quiz_answer(-1))
                subject = make_subject(record=source.store.record)
                session = subject.progress["quiz_session"]
                if reason == "expired": subject.clock.now = session["started_at"] + RESUME_TTL
                elif reason == "meaning":
                    subject.bank = copy.deepcopy(subject.bank)
                    subject.bank[0]["s"] = "n.另义"
                elif reason == "algorithm": session["algo"] = "legacy-other-algorithm"
                else: session["resume_disabled"] = True
                old_session, old_history = copy.deepcopy(session), copy.deepcopy(subject.progress["history"])
                self.assertEqual(subject._quiz_remaining_days(), 0)
                self.assertTrue(subject.start_quiz())
                self.assertNotEqual(subject.quiz_session_id, old_session["id"])
                self.assertEqual(subject.quiz_resp, [])
                self.assertEqual(subject.progress["quiz_archives"][-1]["session"], old_session)
                self.assertEqual(subject.progress["history"], old_history)

    def test_reordered_same_bank_resumes_but_meaning_change_changes_fingerprint(self):
        source = start_subject()
        subject = make_subject(record=source.store.record)
        subject.bank = list(reversed(subject.bank))
        self.assertTrue(subject.start_quiz())
        self.assertEqual(subject.quiz_session_id, source.quiz_session_id)
        self.assertEqual(subject.quiz_items, source.quiz_items)
        self.assertEqual(subject.quiz_word.text, subject.quiz_items[0]["item"]["word"])
        subject.book_words = [{"w": subject.quiz_word.text, "display_w": "school caption", "_school_caption": True}]
        subject._quiz_show()
        self.assertEqual(subject.quiz_word.text, subject.quiz_items[0]["item"]["word"])

    def test_new_history_schema_unit_interval_bands_and_no_prediction(self):
        subject = make_subject()
        snapshot_attempt(subject, count=40)
        row = subject.progress["history"][-1]
        self.assertEqual((row["algo"], row["measurement_schema"], row["unit"]),
                         ("vst-cat-v142", 3, "frequency_ranked_entries"))
        self.assertEqual(row["bank_id"], subject._assessment_bank().fingerprint)
        self.assertEqual(row["interval_level"], 0.95)
        self.assertTrue(0 <= row["lo"] <= row["vocab"] <= row["hi"] <= row["population"])
        self.assertTrue(row["estimate_available"])
        self.assertEqual(row["coverage"], row["coverage_target"])
        self.assertEqual(sum(band["answered"] for band in row["bands"]), 40)
        self.assertTrue(all(band["answered"] >= 2 for band in row["bands"]))
        self.assertFalse(row["prediction_eligible"])
        self.assertNotIn("rigor", row)
        self.assertNotIn("err", row)
        partial = start_subject()
        self.assertTrue(partial._quiz_answer(-1))
        self.assertFalse(partial.progress["history"][-1]["estimate_available"])

    def test_delete_latest_disables_resume_and_failure_restores_all_references(self):
        subject = start_subject()
        self.assertTrue(subject._quiz_answer(-1))
        index = len(subject.progress["history"]) - 1
        before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
        subject.store.fail_next()
        subject._delete_history(index)
        self.assert_unchanged(subject, before, refs, disk)
        subject._delete_history(index)
        sess = subject.progress["quiz_session"]
        self.assertTrue(sess["resume_disabled"] and sess["history_deleted"])
        self.assertEqual(sess["history_response_count"], 1)
        self.assertEqual(subject._quiz_remaining_days(), 0)
        attempts = subject.store.attempts
        self.assertTrue(subject._open_history_page())
        self.assertEqual(subject.store.attempts, attempts)

    def test_deleted_nonlatest_history_stays_deleted_until_one_new_response(self):
        subject = start_subject()
        self.assertTrue(subject._quiz_answer(-1))
        own_index = len(subject.progress["history"]) - 1
        newer = dict(legacy_history(1)[0], id="newer-independent", ts=NOW + 1)
        subject.progress["history"].append(newer)
        subject._delete_history(own_index)
        sess = subject.progress["quiz_session"]
        self.assertTrue(sess["history_deleted"])
        self.assertFalse(sess.get("resume_disabled", False))
        self.assertEqual(subject._quiz_remaining_days(), 30)
        subject._set_mode("quiz")
        self.assertTrue(subject._quiz_next())
        self.assertFalse(any(row.get("id") == sess["id"] for row in subject.progress["history"]))
        self.assertTrue(subject._quiz_answer(-1))
        own = [row for row in subject.progress["history"] if row.get("id") == sess["id"]]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["total"], 2)
        self.assertFalse(sess["history_deleted"])

    def test_history_repairs_only_valid_current_bank_and_preserves_old_records(self):
        for kind in ("current", "expired", "legacy", "different-bank", "deleted", "unanswered"):
            with self.subTest(kind=kind):
                subject = start_subject(history_count=0)
                if kind != "unanswered": self.assertTrue(subject._quiz_answer(-1))
                subject.progress["history"][:] = legacy_history(3)
                sess = subject.progress["quiz_session"]
                if kind == "expired": subject.clock.now = sess["started_at"] + RESUME_TTL
                elif kind == "legacy": sess["algo"] = "legacy-staircase"
                elif kind == "different-bank": sess["bank_id"] = "different"
                elif kind == "deleted": sess["history_deleted"] = True
                old = copy.deepcopy(subject.progress["history"])
                attempts = subject.store.attempts
                self.assertTrue(subject._open_history_page())
                self.assertEqual(subject.progress["history"][:3], old)
                self.assertEqual(len(subject.progress["history"]), 4 if kind == "current" else 3)
                self.assertEqual(subject.store.attempts - attempts, int(kind == "current"))

    def test_history_repair_model_and_save_failure_do_not_mutate_any_graph(self):
        for failure in ("model", "save"):
            with self.subTest(failure=failure):
                subject = start_subject()
                self.assertTrue(subject._quiz_answer(-1))
                subject.progress["history"].pop()
                subject.store.record = json_copy(subject.progress)
                before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
                if failure == "save": subject.store.fail_next()
                context = patch.object(subject.api, "summarize", side_effect=ValueError("model failure")) if failure == "model" else patch.object(subject.api, "summarize", wraps=vt.summarize)
                with context:
                    self.assertFalse(subject._open_history_page())
                self.assert_unchanged(subject, before, refs, disk)

    def test_history_and_result_charts_do_not_mix_model_bank_unit_or_partial_rows(self):
        subject = make_subject()
        snapshot_attempt(subject, count=40)
        template = copy.deepcopy(subject.progress["history"][-1])
        template.update(completed=True, estimate_available=True, id="same-scale", ts=NOW)
        variants = [dict(template, id="old", algo="legacy-staircase"),
                    dict(template, id="bank", bank_id="different"),
                    dict(template, id="unit", unit="word_families"),
                    dict(template, id="schema", measurement_schema=2),
                    dict(template, id="partial", completed=False),
                    dict(template, id="unavailable", estimate_available=False)]
        history = legacy_history(2) + variants + [template]
        subject.progress.pop("quiz_session")
        subject.progress["history"] = history
        before = copy.deepcopy(history)
        self.assertTrue(subject._open_history_page())
        expected = [(template["ts"], template["vocab"])]
        self.assertEqual(subject.history_chart.points, expected)
        subject._show_result(template, True)
        self.assertEqual(subject.chart.points, expected)
        self.assertFalse(subject.btn_rebase.visible)
        subject._show_result(history[0], True)
        self.assertEqual(subject.chart.points, [])
        self.assertFalse(subject.chart_holder.visible or subject.btn_band_profile.visible)
        self.assertNotIn("95%", subject.res_sub.text)
        self.assertIn("未重新计算", subject.res_sub.text)
        self.assertEqual(history, before)

    def test_reports_are_read_only_and_new_result_cannot_apply_prediction(self):
        subject = make_subject()
        snapshot_attempt(subject, count=40)
        subject.quiz_result = subject.progress["history"][-1]
        before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
        self.assertTrue(subject._show_assessment_method())
        self.assertEqual(subject.mode, "method")
        self.assertEqual(subject.method_return_mode, "settings")
        method = subject.method_text.text
        subject._set_mode(before["attrs"]["mode"])
        subject._show_band_profile()
        self.assertEqual(len(subject.reports), 1)
        detail = subject._history_detail_text(subject.quiz_result)
        self.assertIn("本次已作答 40 题，答对 %d 题。" % subject.quiz_result["right"], detail)
        self.assertNotIn("题目分布在", detail)
        self.assertNotIn("考生校准", detail)
        bands = subject.reports[0][1]
        for text in ("至少40题", "最多80题", "每层至少2题", "未经实测标定", "不测", "高亮"):
            self.assertIn(text, method)
        self.assertIn("不等于分层掌握诊断", bands)
        self.assertIn("不是原始语料排名或VST词族层", bands)
        self.assertFalse(subject._apply_prediction())
        self.assertEqual(len(subject.notices), 1)
        self.assert_unchanged(subject, before, refs, disk)

    def test_80th_answer_finishes_automatically_without_requesting_item_81(self):
        subject = make_subject(size=20000)
        snapshot_attempt(subject, count=80, answered=False)
        before = protected_state(subject)
        self.assertTrue(subject._quiz_answer(choice_for(subject)))
        self.assertEqual(len(subject.quiz_resp), 80)
        with patch.object(subject.api, "next_item", side_effect=AssertionError("must never ask item 81")):
            self.assertTrue(subject.quiz_timer.expire(subject._quiz_next))
        self.assertEqual(subject.mode, "summary")
        self.assertIn("已答 80 题 · 答对 %d 题" % subject.quiz_result["right"],
                      subject.summary_note.text)
        self.assertIn("本次测试结果已保存到历史记录。", subject.summary_note.text)
        self.assertNotIn("本次成绩", subject.summary_note.text)
        self.assertNotIn("不认识", subject.summary_note.text)
        self.assertEqual(subject.quiz_result["stop_reason"], "max_items")
        self.assertEqual(subject.quiz_result["total"], 80)
        self.assertEqual(subject.quiz_result["coverage"], 20)
        self.assertEqual(len(subject.quiz_items), 80)
        self.assertEqual(protected_state(subject), before)
        self.assertNotIn("quiz_session", subject.progress)

    def test_completed_feedback_resume_finishes_once_and_failure_retries_start(self):
        source = make_subject(size=2000)
        snapshot_attempt(source)
        subject = make_subject(record=source.store.record)
        self.fail_save(subject, subject.start_quiz, "start")
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.mode, "summary")
        self.assertEqual(subject.quiz_result["total"], 80)
        self.assertEqual(len([row for row in subject.progress["history"] if row.get("id") == subject.quiz_result["id"]]), 1)
        self.assertEqual(subject.store.commits, 1)

    def test_extreme_responses_are_bounded_and_keep_learning_state_untouched(self):
        for response in (1, 0, -1):
            with self.subTest(response=response):
                subject = start_subject(size=20000, history_count=0)
                before = protected_state(subject)
                for _ in range(81):
                    if subject.mode == "summary": break
                    self.assertLess(len(subject.quiz_resp), 80)
                    self.assertTrue(subject._quiz_answer(choice_for(subject, response)))
                    self.assertTrue(subject.quiz_timer.expire(subject._quiz_next))
                self.assertEqual(subject.mode, "summary")
                self.assertTrue(40 <= len(subject.quiz_resp) <= 80)
                self.assertEqual(len(subject.quiz_items), len(subject.quiz_resp))
                self.assertEqual(len({item["key"] for item in subject.quiz_items}), len(subject.quiz_items))
                self.assertEqual(len(subject.progress["history"]), 1)
                self.assertEqual(subject.quiz_result["total"], len(subject.quiz_resp))
                self.assertTrue(subject.quiz_result["completed"])
                self.assertTrue(all(band["answered"] >= 2 for band in subject.quiz_result["bands"]))
                self.assertEqual(protected_state(subject), before)
                self.assertEqual(subject.progress["theta"], 0.75)
                self.assertFalse(subject.quiz_timer.active)
                self.assert_saved(subject)

    def test_current_abandoned_snapshot_is_archived_raw_without_history_repair(self):
        for reason in ("new_attempt", "expired"):
            for history_state in ("missing", "stale"):
                with self.subTest(reason=reason, history_state=history_state):
                    subject = start_subject()
                    self.assertTrue(subject._quiz_answer(-1))
                    session = subject.progress["quiz_session"]
                    for name in ("history_id", "history_response_count", "history_deleted"):
                        session.pop(name, None)
                    if history_state == "missing":
                        subject.progress["history"].pop()
                    else:
                        subject.progress["history"][-1]["total"] = 777
                    if reason == "expired":
                        subject.clock.now = session["started_at"] + RESUME_TTL
                    raw, history = copy.deepcopy(session), copy.deepcopy(subject.progress["history"])
                    history_refs = references(subject)
                    with patch.object(subject.api, "summarize", side_effect=AssertionError(
                            "abandoned snapshot/history must not be rescored during archival")):
                        self.assertTrue(subject.start_quiz(fresh=reason == "new_attempt"))
                    self.assertEqual(subject.progress["quiz_archives"][-1]["session"], raw)
                    self.assertEqual(session, raw)
                    self.assertEqual(subject.progress["history"], history)
                    self.assertIs(subject.progress["history"], history_refs["progress/history"])
                    self.assertEqual(subject.quiz_resp, [])
                    self.assert_saved(subject)

    def test_malformed_archives_fail_closed_without_any_previous_session(self):
        for archives in (None, "retained-raw", {"future": [1, 2]}, False, 0):
            with self.subTest(archives=archives):
                subject = make_subject()
                subject.progress["quiz_archives"] = archives
                subject.store.record = json_copy(subject.progress)
                before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
                self.assertFalse(subject.start_quiz(fresh=True))
                self.assert_unchanged(subject, before, refs, disk, "start_new")
                self.assertEqual(subject.store.attempts, 0)

    def test_non_dict_old_sessions_never_resume_and_are_archived_without_get_crashes(self):
        for old in ([{"raw": [1, None]}], "legacy-raw", False, 0, None):
            with self.subTest(old=old):
                subject = make_subject()
                subject.progress["quiz_session"] = copy.deepcopy(old)
                raw, history = copy.deepcopy(old), copy.deepcopy(subject.progress["history"])
                archive_count = len(subject.progress["quiz_archives"])
                self.assertEqual(subject._quiz_remaining_days(), 0)
                subject._startup()
                subject.open_settings()
                self.assertTrue(subject.start_quiz())
                self.assertEqual(subject.progress["history"], history)
                if old is None:
                    self.assertEqual(len(subject.progress["quiz_archives"]), archive_count)
                else:
                    self.assertEqual(subject.progress["quiz_archives"][-1]["session"], raw)
                    self.assertEqual(len(subject.progress["quiz_archives"]), archive_count + 1)
                self.assert_saved(subject)

    def test_new_attempt_generation_failure_rolls_back_raw_archives_and_history(self):
        subject = make_subject()
        subject.progress["quiz_session"] = legacy_session()
        subject.store.record = json_copy(subject.progress)
        self.fail_model(subject, lambda: subject.start_quiz(fresh=True), "start_new", method="next_item")
        self.assertTrue(subject.retry_or_skip())
        self.assertEqual(subject.progress["quiz_archives"][-1]["session"], legacy_session())
        self.assert_saved(subject)

    def test_new_algo_or_unit_refuses_prediction_even_with_eligibility_tampering(self):
        for tag in ("algorithm", "unit", "both"):
            for source in ("result", "last_test"):
                with self.subTest(tag=tag, source=source):
                    subject = make_subject()
                    record = dict(legacy_history(1)[0], prediction_eligible=True)
                    if tag in ("algorithm", "both"):
                        record["algo"] = vt.ALGORITHM
                    if tag in ("unit", "both"):
                        record["unit"] = vt.UNIT
                    if source == "result":
                        subject.quiz_result = record
                    else:
                        subject.last_test = (record, False)
                    before, refs, disk = payload(subject), references(subject), json_copy(subject.store.record)
                    self.assertFalse(subject._apply_prediction())
                    self.assertEqual(len(subject.notices), 1)
                    self.assertEqual(subject.store.attempts, 0)
                    self.assert_unchanged(subject, before, refs, disk)

    def test_closed_and_closing_cards_reject_all_quiz_actions(self):
        for flag in ("_closed", "_closing"):
            subject = start_subject()
            self.assertTrue(subject._quiz_answer(-1))
            setattr(subject, flag, True)
            before, attempts = payload(subject), subject.store.attempts
            for callback in (subject.start_quiz, lambda: subject._quiz_answer(0),
                             subject._quiz_next, subject._finish_quiz,
                             subject.skip_test, subject.retry_or_skip, subject.save):
                self.assertFalse(callback())
            self.assertEqual(payload(subject), before)
            self.assertEqual(subject.store.attempts, attempts)


def output_directory(value=None):
    target = Path(value).resolve() if value else TEST_ROOT / ("v142-flow-%s-%d" % (time.strftime("%Y%m%d-%H%M%S"), os.getpid()))
    root = TEST_ROOT.resolve()
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise ValueError("test outputs must stay inside workspace .vocab-ui-tests")
    if not relative.parts:
        raise ValueError("use a dedicated subdirectory of .vocab-ui-tests")
    target.mkdir(parents=True, exist_ok=True)
    return target


def run_ast(outdir=None, pattern=None):
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(V142FlowTests)
    if pattern:
        suite = unittest.TestSuite(test for test in suite if pattern in test.id())
        if suite.countTestCases() == 0:
            raise ValueError("no AST tests match " + pattern)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    print(text, end="", flush=True)
    if outdir is not None:
        (outdir / "ast-report.txt").write_text(text, encoding="utf-8")
    return result.wasSuccessful()


def run_ui(outdir):
    # Import Qt/main only after an explicit --ui/--all choice. Do not run
    # app/main.py, construct a non-Sandbox Card, or point at real progress.
    sys.path.insert(0, str(ROOT / "scripts"))
    from ui_test_support import configure_qt, Sandbox, set_nottest, new_app
    configure_qt("offscreen")
    set_nottest(True)
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QMessageBox, QLabel, QPushButton, QSizePolicy
    import main as app_main
    import theme as themes
    qt_app = new_app(["v142-isolated-regression"])
    out, failures, callback_errors, reports = [], [], [], []

    def check(condition, message):
        line = ("OK " if condition else "FAIL ") + message
        out.append(line)
        print(line, flush=True)
        if not condition:
            failures.append(message)
            raise AssertionError(message)

    def visible_text(card):
        return "\n".join(widget.text() for widget in card.findChildren((QLabel, QPushButton))
                         if widget.isVisible())

    def protected_snapshot(progress):
        # 出厂状态没有测试能力值(theta)，因此同时记录“是否存在”。
        return {name: (name in progress, copy.deepcopy(progress.get(name)))
                for name in PROTECTED}

    def new_card(sb, progress=None):
        # The argument is always synthetic, or read back from this Sandbox.
        seed_progress = progress_fixture(history_count=0) if progress is None else progress
        card = sb.new_card(progress=seed_progress, show=True)
        card._due_timer.stop()
        card._window_save_timer.stop()
        card.bank = raw_bank()
        QTest.qWait(25)
        card.open_settings()
        return card

    def active_card(sb):
        card = new_card(sb)
        check(card.start_quiz(fresh=True), "isolated Card starts a V1.4.2 attempt")
        card.resize(520, 430)
        QTest.qWait(25)
        return card

    def click(card, button):
        if card.mode == "quiz": card.quiz_page.ensureWidgetVisible(button)
        elif card.mode == "result": card.result_page.ensureWidgetVisible(button)
        elif card.mode == "settings": card.settings_page.ensureWidgetVisible(button)
        QTest.qWait(5)
        QTest.mouseClick(button, Qt.LeftButton)

    def cursor_shape():
        cursor = app_main.QApplication.overrideCursor()
        return None if cursor is None else cursor.shape()

    def scenario_startup_guards(sb):
        expected = progress_fixture(history_count=0)["keybindings"]
        card = new_card(sb)
        check(card.key_bindings == expected and card.progress["keybindings"] == expected,
              "cold Card preserves every valid custom keybinding")
        settings_text = visible_text(card)
        check("词汇量测试 · V1.4.2" not in settings_text and "40–80题" not in settings_text,
              "settings test header has no version and no 40-80 tip")
        check(card.btn_assessment_method.objectName() == "chip"
              and card.btn_history.objectName() == "chip"
              and card.btn_assessment_method.geometry().x() < card.btn_history.geometry().x(),
              "assessment notes are a chip control left of the history button")
        check(card.grab().save(str(outdir / "settings.png")), "settings screenshot saved")
        with patch.object(app_main.vt, "population_summary",
                          side_effect=AssertionError("method page counted population")), \
                patch.object(app_main.vt, "population_summary_steps",
                             side_effect=AssertionError("method page queued population batches")), \
                patch.object(app_main.vt, "FrequencyBank",
                             side_effect=AssertionError("method page built the assessment bank")):
            card._show_assessment_method()
        check(card.mode == "method" and card.method_page.isVisible()
              and card.page_title.text() == "评测说明"
              and "词汇量测试 · 方法与限制" in card.method_text.text()
              and "最多保留 20,000 个词目" in card.method_text.text()
              and "正在准备" not in card.method_text.text()
              and not hasattr(card, "_method_summary_pending_source")
              and not hasattr(card, "_test_bank"),
              "assessment notes show full text immediately without counting or building")
        check(card.grab().save(str(outdir / "assessment-method.png")),
              "assessment method page screenshot saved")
        click(card, card.btn_back)
        QTest.qWait(10)
        check(card.mode == "settings", "assessment method back control returns to settings")
        next_study_mode = "choice" if card.study_mode == "brush" else "brush"
        with patch.object(card, "_apply_scaling", wraps=card._apply_scaling) as scaling:
            click(card, card.study_mode_chips[next_study_mode])
        check(card.study_mode == next_study_mode and scaling.call_count == 0,
              "simple settings chips respond without a full stylesheet/layout pass")
        card._quiz_build_begin()
        QTest.qWait(25)
        check(card.mode == "building" and card.build_page.isVisible()
              and card.build_progress.minimum() == 0 and card.build_progress.maximum() == 100
              and card.build_progress.value() == 0,
              "building page is visible with determinate progress starting at zero")
        bar_center_y = card.build_progress.mapTo(card, card.build_progress.rect().center()).y()
        bar_top_y = card.build_progress.mapTo(card, card.build_progress.rect().topLeft()).y()
        title_bottom_y = card.build_title.mapTo(card, card.build_title.rect().bottomLeft()).y()
        check(abs(bar_center_y - card.rect().center().y()) <= 1
              and title_bottom_y < bar_top_y,
              "build progress is vertically centered on the card with its title above")
        check(card.grab().save(str(outdir / "building-0.png")), "zero-progress building page screenshot saved")
        card._quiz_build_end()
        QTest.qWait(10)
        progress_values, progress_modes, mode_transitions, ready_stages = [], [], [], []
        original_progress = card._quiz_build_progress
        original_set_mode = card._set_mode
        original_gen_item, original_save_session = card._gen_item, card._save_quiz_session

        def ready_stage(name, callback):
            ready_stages.append((name, card.mode, card.build_progress.value(), card.build_page.isVisible()))
            return callback()

        def tracked_progress(value):
            progress_values.append(value)
            progress_modes.append(card.mode)
            original_progress(value)

        def tracked_mode(mode):
            mode_transitions.append(mode)
            return original_set_mode(mode)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel) as ask, \
                patch.object(card, "_quiz_build_progress", side_effect=tracked_progress), \
                patch.object(card, "_set_mode", side_effect=tracked_mode), \
                patch.object(card, "_gen_item", side_effect=lambda: ready_stage("item", original_gen_item)), \
                patch.object(card, "_save_quiz_session", side_effect=lambda: ready_stage("save", original_save_session)):
            check(card._test_from_settings() and card.mode == "quiz",
                  "new-test button starts immediately")
        check(ask.call_count == 0, "starting a test shows no confirmation dialog")
        check(progress_values[0] == 0 and progress_values[-1] == 100
              and progress_values == sorted(set(progress_values)) and len(progress_values) > 10
              and all(mode == "building" for mode in progress_modes)
              and card.build_progress.value() == 100,
              "first test advances real build progress monotonically from zero to completion")
        check(mode_transitions == ["building", "quiz"],
              "successful cold build stays visible through setup and never restores the entry page")
        check(ready_stages == [("item", "building", 100, True), ("save", "building", 100, True)],
              "100-percent build page remains visible during first-item generation and persistence")
        quiz_word_gap = card.quiz_word.geometry().top() - card.quiz_progress.geometry().bottom()
        check(quiz_word_gap >= 16,
              "quiz word has a modestly larger gap below the progress bar")
        check(card.grab().save(str(outdir / "quiz-word-position.png")),
              "lowered quiz-word layout screenshot saved")
        card.close()
        QTest.qWait(20)
        card = new_card(sb)
        check(not hasattr(card, "_test_bank") and not hasattr(card, "_test_bank_source"),
              "assessment bank remains lazy before the first test")
        before_cursor, raised = cursor_shape(), False
        with patch.object(app_main.vt, "FrequencyBank", side_effect=ValueError("injected bank failure")):
            try:
                card._assessment_bank()
            except ValueError:
                raised = True
        check(raised and cursor_shape() == before_cursor and not hasattr(card, "_test_bank"),
              "failed cold bank construction restores the busy cursor and leaves no partial cache")
        bank = card._assessment_bank()
        check(bank.size == len(raw_bank()) and cursor_shape() == before_cursor,
              "bank construction retries cleanly after a cold-build failure")
        check(all(app_main.ChartCanvas.chart_bounds(points)[0] >= 0
                  for points in ([(0, 10)], [(0, 100), (1, 120)], [(0, 0), (1, 0)])),
              "chart y axis never starts below zero")
        check(card.start_quiz(fresh=True)
              and all(button.text().endswith("[%s]" % hint) for button, hint in zip(
                  card.opt_btns, ("A", "S", "D", "G")))
              and card.btn_dontknow.text().endswith("[H]"),
              "quiz captions use the preserved custom bindings after cold start")

    def scenario_cold_build_edges(sb):
        baseline = prepared_bank(2000)
        for origin in ("settings", "front", "welcome"):
            for fail in (False, True):
                card = new_card(sb)
                if origin == "front":
                    card.set_study_mode("brush")
                    card.window_ctl.set_compact(True, remember=True)
                card._set_mode(origin)
                QTest.qWait(20)
                before, disk = copy.deepcopy(card.progress), sb.read_progress()
                prior_size, prior_compact = card.size(), card.window_ctl.compact
                transitions, compact_requests = [], []
                original_mode, original_compact = card._set_mode, card.window_ctl.set_compact

                def ready_bank(progress=None):
                    if progress is not None:
                        progress(0)
                        progress(100)
                    card._test_bank, card._test_bank_source = baseline, card.bank
                    return baseline

                def tracked_mode(mode):
                    transitions.append(mode)
                    return original_mode(mode)

                def tracked_compact(enabled, *args, **kwargs):
                    compact_requests.append(bool(enabled))
                    return original_compact(enabled, *args, **kwargs)

                with ExitStack() as stack:
                    stack.enter_context(patch.object(card, "_assessment_bank", side_effect=ready_bank))
                    stack.enter_context(patch.object(card, "_set_mode", side_effect=tracked_mode))
                    stack.enter_context(patch.object(card.window_ctl, "set_compact", side_effect=tracked_compact))
                    if fail:
                        stack.enter_context(patch.object(card, "save", side_effect=app_main.storage.StorageError("injected cold-start save failure")))
                        errors = stack.enter_context(patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok))
                    result = card.start_quiz(fresh=True)
                QTest.qWait(20)
                case = "%s %s" % (origin, "rollback" if fail else "success")
                if fail:
                    expected_page = {"settings": card.settings_page, "front": card.stage,
                                     "welcome": card.welcome_page}[origin]
                    check(not result and errors.call_count == 1 and card.mode == origin
                          and expected_page.isVisible() and not card.build_page.isVisible(),
                          case + ": failed first save restores the actual entry page")
                    check(card.progress == before and sb.read_progress() == disk
                          and card.window_ctl.compact == prior_compact and card.size() == prior_size,
                          case + ": progress, disk and compact geometry roll back together")
                else:
                    check(result and transitions == ["building", "quiz"] and card.quiz_page.isVisible(),
                          case + ": build enters the ready quiz without a prior-page transition")
                    check(compact_requests and not any(compact_requests),
                          case + ": successful build never briefly restores compact study geometry")
                    check(card.quiz_origin_welcome == (origin == "welcome")
                          and card.quiz_return_to_settings == (origin == "settings"),
                          case + ": logical entry flags survive the continuous build page")
                check(not hasattr(card, "_build_prior_mode"), case + ": build bookkeeping is cleaned up")
                card.close()
                QTest.qWait(10)

    def scenario_settings_refresh(sb):
        card = new_card(sb)
        next_mode = "choice" if card.study_mode == "brush" else "brush"
        with patch.object(card, "_apply_scaling", wraps=card._apply_scaling) as scaling, \
                patch.object(card, "_refresh_known", wraps=card._refresh_known) as known, \
                patch.object(card.catalog, "set_metadata", wraps=card.catalog.set_metadata) as metadata:
            click(card, card.study_mode_chips[next_mode])
        check(card.study_mode == next_mode and scaling.call_count == known.call_count == metadata.call_count == 0,
              "study-mode click updates preferences without rescaling or rebuilding word metadata")
        level = next(value for value in card.school_chips if value != card.progress.get("school_knowledge"))
        with patch.object(card, "_apply_scaling", wraps=card._apply_scaling) as scaling, \
                patch.object(card, "_refresh_known", wraps=card._refresh_known) as known, \
                patch.object(card.catalog, "set_metadata", wraps=card.catalog.set_metadata) as metadata:
            click(card, card.school_chips[level])
        check(card.progress["school_knowledge"] == level and scaling.call_count == 0
              and known.call_count == metadata.call_count == 1,
              "school-level click refreshes known words once but does not run full scaling")
        before, disk, known_before = copy.deepcopy(card.progress), sb.read_progress(), set(card.known)
        with patch.object(card, "save", side_effect=app_main.storage.StorageError("injected settings save failure")), \
                patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as errors, \
                patch.object(card, "_apply_scaling", wraps=card._apply_scaling) as scaling:
            check(not card.set_school_knowledge("off"), "school-level save failure remains explicit and retryable")
        check(errors.call_count == 1 and scaling.call_count == 0 and card.progress == before
              and sb.read_progress() == disk and card.known == known_before
              and card.school_chips[level].property("on") == "1",
              "targeted settings rollback restores records, known words and selected chip without rescaling")
        bindings = dict(card.key_bindings, forget="T")
        with patch.object(card, "_apply_scaling", wraps=card._apply_scaling) as scaling:
            changed = card.apply_key_bindings(bindings)
        check(changed and card.key_bindings == bindings and card.btn_forget.text().endswith("[T]")
              and scaling.call_count == 0,
              "keybinding changes refresh captions without a stylesheet/layout pass")
        theme = next(value for value in card.theme_chips if value != card.theme_key)
        with patch.object(card, "_apply_scaling", wraps=card._apply_scaling) as scaling:
            click(card, card.theme_chips[theme])
        check(card.theme_key == theme and scaling.call_count == 1,
              "theme click performs one necessary full palette/scaling pass, not two")

    def scenario_method_response(sb):
        card = new_card(sb)
        card.bank = raw_bank(20000)
        before, disk = copy.deepcopy(card.progress), sb.read_progress()
        started = time.perf_counter()
        with patch.object(app_main.vt, "population_summary",
                          side_effect=AssertionError("method page counted population")), \
                patch.object(app_main.vt, "population_summary_steps",
                             side_effect=AssertionError("method page queued population batches")), \
                patch.object(app_main.vt, "FrequencyBank",
                             side_effect=AssertionError("method page built the assessment bank")):
            card._show_assessment_method()
        elapsed = (time.perf_counter() - started) * 1000
        check(card.mode == "method" and "词汇量测试 · 方法与限制" in card.method_text.text()
              and "最多保留 20,000 个词目" in card.method_text.text()
              and "正在准备" not in card.method_text.text()
              and not hasattr(card, "_method_summary_pending_source"),
              "method text is complete on the first return without a loading state")
        check(not hasattr(card, "_test_bank") and card.progress == before and sb.read_progress() == disk,
              "opening method text neither builds a bank nor saves progress")
        out.append("METHOD_OPEN_ELAPSED_MS %.1f" % elapsed)
        click(card, card.btn_back)
        QTest.qWait(20)
        check(card.mode == "settings", "immediate method page keeps the real Back control responsive")
        card._show_assessment_method()
        check("方法与限制" in card.method_text.text()
              and not hasattr(card, "_method_summary_pending_source"),
              "reopening method notes remains immediate")

    def scenario_factory_reset(sb):
        seeded = progress_fixture(history_count=2)
        seeded["quiz_session"] = {"schema": 1, "algo": "legacy-staircase", "id": "old"}
        seeded["quiz_archives"] = [{"archived_at": 1, "session": {"id": "old-archive"}}]
        seeded["theta"] = 1.25
        sb.write_progress(seeded)
        card = sb.new_card(show=False)
        try:
            saved = sb.read_progress()
            for name in ("history", "quiz_session", "quiz_archives", "theta"):
                check(name not in card.progress and name not in saved,
                      "factory reset removes old test field: %s" % name)
            for name in ("cursors", "orders", "study_records"):
                kept = card.progress.get(name) or {}
                check(all(kept.get(key) == value for key, value in seeded[name].items()),
                      "factory reset keeps saved entries in: %s" % name)
            for name in ("prediction_state", "book", "school_knowledge",
                         "keybindings", "learning_policy"):
                check(card.progress.get(name) == seeded.get(name),
                      "factory reset keeps non-test field: %s" % name)
            check("other-word" in card.progress["states"]
                  and card.progress["states"]["other-word"].get("custom") == {"keep": [1, 2]},
                  "factory reset keeps learning states")
            check(saved.get(app_main.TEST_RESET_MARKER) == 1,
                  "factory reset marker is persisted, so later tests are kept")
        finally:
            card.close()
            QTest.qWait(20)

    def scenario_summary(sb):
        card = active_card(sb)
        model = make_subject()
        snapshot_attempt(model, count=80)
        row = copy.deepcopy(model.progress["history"][-1])
        row.update(completed=True)
        card._show_summary(row)
        QTest.qWait(20)
        text = visible_text(card)
        labels = (card.summary_title, card.summary_big, card.summary_note)
        page_center = card.summary_page.rect().center().x()
        check(card.mode == "summary" and "本次测试已完成" in text and "知道了" in text
              and "≈" in card.summary_big.text()
              and "已答 80 题 · 答对 %d 题" % row["right"] in card.summary_note.text()
              and "本次测试结果已保存到历史记录。" in card.summary_note.text()
              and "本次成绩" not in card.summary_note.text()
              and "不认识" not in card.summary_note.text(),
              "finished test shows the requested result wording and answer counts")
        check(all(label.alignment() & Qt.AlignHCenter for label in labels)
              and all(label.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding for label in labels)
              and all(abs(label.geometry().center().x() - page_center) <= 1 for label in labels),
              "every completion-page text row expands across and centers on the page")
        check(card.btn_summary_ok.width() < card.summary_page.width() // 2
              and card.btn_summary_ok.width() >= card.btn_summary_ok.sizeHint().width(),
              "summary acknowledgement fits its text and is less than half-page width")
        summary_rule = "QPushButton#summaryOk { background: %s; color: %s; }" % (
            card.t["chip_bg"], card.t["chip_fg"])
        check(card.btn_summary_ok.objectName() == "summaryOk"
              and summary_rule in card.styleSheet()
              and card.btn_summary_ok.objectName() != "remember",
              "summary acknowledgement uses the settings-control theme colours")
        for width, height, name in app_main.WINDOW_PRESETS:
            card._apply_window_size(width, height)
            QTest.qWait(35)
            center = card.summary_page.rect().center().x()
            check(all(label.alignment() & Qt.AlignHCenter for label in labels)
                  and all(abs(label.geometry().center().x() - center) <= 1 for label in labels)
                  and card.summary_note.textFormat() == Qt.PlainText,
                  "summary rows remain centered at preset %s (%dx%d)" % (name, width, height))
            check(card.grab().save(str(outdir / ("summary-%dx%d.png" % (width, height)))),
                  "summary preset screenshot saved: %dx%d" % (width, height))
        card._apply_window_size(520, 430)
        QTest.qWait(20)
        check(card.grab().save(str(outdir / "summary.png")), "summary screenshot saved")
        card._fill_summary({"estimate_available": False, "total": 12, "right": 7})
        check("本次测试结果已保存到历史记录。" in card.summary_note.text()
              and "本次记录" not in card.summary_note.text(),
              "insufficient-sample summary uses the same requested result wording")
        click(card, card.btn_summary_ok)
        QTest.qWait(20)
        check(card.mode == "settings", "summary acknowledgement returns to settings")

    def scenario_answers(sb):
        card = active_card(sb)
        intro = visible_text(card)
        check("选择最贴近" not in intro and "第一阶段" not in intro and "第二阶段" not in intro,
              "quiz page hides the instruction and phase captions")
        protected = protected_snapshot(card.progress)
        for choice in (0, 1, 2, 3, -1):
            n, old_key = len(card.quiz_resp), card.quiz_items[card.quiz_i]["key"]
            captions = [button.text() for button in card.opt_btns]
            correct = card.quiz_items[card.quiz_i]["item"]["correct_index"]
            click(card, card.btn_dontknow if choice == -1 else card.opt_btns[choice])
            check(card.quiz_resp[-1] == (-1 if choice == -1 else int(choice == correct))
                  and len(card.quiz_resp) == n + 1, "real click stores one response: %s" % choice)
            check(card.quiz_timer.isSingleShot() and card.quiz_timer.interval() == 350 and card.quiz_timer.isActive(),
                  "real single-shot timer is 350ms")
            check([button.property("state") for button in card.opt_btns] ==
                  ["picked" if i == choice else "" for i in range(4)]
                  and card.btn_dontknow.property("state") == ("picked" if choice == -1 else ""),
                  "feedback marks only the chosen control, never correct/wrong")
            check([button.text() for button in card.opt_btns] == captions
                  and card.status.text() == "词汇测试 · 已答 %d / 最多80" % (n + 1)
                  and "正在准备下一题" not in card.status.text(),
                  "feedback keeps the saved-answer count without preparing text")
            check(card.grab().save(str(outdir / ("feedback-%s.png" % choice))),
                  "feedback screenshot saved: %s" % choice)
            check(not card._quiz_answer(-1) and len(card.quiz_resp) == n + 1, "duplicate answer is ignored")
            disk = sb.read_progress()
            check(len(disk["quiz_session"]["resp"]) == n + 1 and disk["history"][-1]["total"] == n + 1,
                  "answer and its one history row are durable before auto-next")
            QTest.qWait(600)
            check(card.mode == "quiz" and card.quiz_i == n + 1 and len(card.quiz_resp) == n + 1
                  and card.quiz_items[card.quiz_i]["key"] != old_key and not card.quiz_locked,
                  "production timeout advances exactly one pending item")
        check(protected_snapshot(card.progress) == protected,
              "real answer/timer flow leaves learning and prediction records unchanged")

    def scenario_resume(sb):
        card = active_card(sb)
        session_id, pending = card.quiz_session_id, copy.deepcopy(card.quiz_items[0])
        card.close()
        QTest.qWait(20)
        resumed = new_card(sb, sb.read_progress())
        check(not hasattr(resumed, "_test_bank"),
              "cold resumable startup defers bank construction until explicit continue")
        resumed.open_settings()
        QTest.qWait(10)
        check(resumed.mode == "settings" and resumed.btn_continue.isVisible()
              and not hasattr(resumed, "_test_bank"),
              "opening settings exposes Continue without a hidden cold bank build")
        progress_values, progress_modes = [], []
        original_progress = resumed._quiz_build_progress

        def tracked_resume_progress(value):
            progress_values.append(value)
            progress_modes.append(resumed.mode)
            original_progress(value)

        with patch.object(resumed, "_quiz_build_progress", side_effect=tracked_resume_progress):
            click(resumed, resumed.btn_continue)
            check(resumed.mode == "quiz" and resumed.quiz_session_id == session_id
                  and resumed.quiz_items[0] == pending and resumed.quiz_resp == [],
                  "cold Qt resume preserves unanswered options and stable session ID")
        check(progress_values[0] == 0 and progress_values[-1] == 100
              and progress_values == sorted(set(progress_values))
              and all(mode == "building" for mode in progress_modes),
              "cold Qt resume shows the real determinate first-build progress page")
        check(resumed._quiz_answer(-1), "answer before real close commits")
        resumed.close()
        QTest.qWait(20)
        saved = sb.read_progress()
        check(saved["quiz_session"]["i"] == 0 and saved["quiz_session"]["resp"] == [-1],
              "feedback close leaves the answered-current durable snapshot")
        next_card = new_card(sb, saved)
        check(next_card.start_quiz() and next_card.quiz_i == 1 and next_card.quiz_resp == [-1]
              and next_card.quiz_session_id == session_id, "Qt feedback resume only advances, never rescores")

    def scenario_save_failure(sb):
        card = active_card(sb)
        before, disk = copy.deepcopy(card.progress), sb.read_progress()
        refs = (card.progress, card.progress["quiz_session"], card.quiz_items, card.quiz_resp,
                card.quiz_state, card.progress.get("history"))
        with patch.object(card, "save", side_effect=app_main.storage.StorageError("injected save failure")), \
                patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as error:
            check(not card._quiz_answer(-1), "real Card rejects failed answer save")
            check(error.call_count == 1, "failure is shown once without a blocking dialog")
        current = (card.progress, card.progress["quiz_session"], card.quiz_items, card.quiz_resp,
                   card.quiz_state, card.progress.get("history"))
        check(all(left is right for left, right in zip(refs, current))
              and card.progress == before and sb.read_progress() == disk,
              "Qt failure restores session/state/history original containers and disk")
        check(not card.quiz_locked and not card.quiz_timer.isActive()
              and all(button.isEnabled() for button in card.opt_btns), "failed answer is immediately answerable again")

    def scenario_theme(sb, key):
        card = active_card(sb)
        card.set_theme(key)
        card.resize(520, 430)
        QTest.qWait(35)
        check((card.width(), card.height()) == (520, 430), key + ": requested minimum window is retained")
        check(len(card.opt_btns) == 4 and all(button.content.wordWrap() for button in card.opt_btns),
              key + ": four production option labels support wrapping")
        check("严谨度" not in visible_text(card) and "误差" not in visible_text(card)
              and "None" not in visible_text(card), key + ": no old rigor/error or None score placeholders")
        check(all(option["item_id"] in card._assessment_bank().items for option in card.quiz_items[0]["item"]["options"]),
              key + ": every option is a real bank meaning; no none-of-the-above trap")
        check(card.grab().save(str(outdir / ("quiz-%s.png" % key))), key + ": normal quiz screenshot saved")
        # UI-only copied items stress arbitrary legitimate-length glosses. Never
        # overwrite a persisted bank meaning; restore before any answer/save.
        original = card.quiz_items
        try:
            card.quiz_items = copy.deepcopy(original)
            for i, option in enumerate(card.quiz_items[0]["item"]["options"]):
                option["text"] = ("n.用于检查长释义完整换行的隔离样本文本；包含多个义项、解释以及补充说明。" * (4 + i))
            card._quiz_show()
            QTest.qWait(35)
            card._fit_choice_options(card._ui_scale())
            QTest.qWait(35)
            check(card.width() == 520 and card.height() == 430, key + ": long definitions do not enlarge window")
            check(card.quiz_page.verticalScrollBar().maximum() > 0, key + ": long meanings have vertical scrolling")
            for button in card.opt_btns:
                check(button.content.wordWrap() and button.content.height() >=
                      button.content.heightForWidth(button.content.width()), key + ": long option text is not clipped")
            check(card.grab().save(str(outdir / ("quiz-long-%s.png" % key))), key + ": long-meaning screenshot saved")
            card.quiz_page.ensureWidgetVisible(card.btn_dontknow)
            QTest.qWait(25)
            center = card.btn_dontknow.mapTo(card.quiz_page.viewport(), card.btn_dontknow.rect().center())
            check(card.quiz_page.viewport().rect().contains(center), key + ": DK remains reachable by scrolling")
            check(card.grab().save(str(outdir / ("quiz-scroll-%s.png" % key))), key + ": scroll-bottom screenshot saved")
        finally:
            card.quiz_items = original
            card._quiz_show()
        model = make_subject()
        snapshot_attempt(model, count=80)
        row = copy.deepcopy(model.progress["history"][-1])
        row.update(completed=True)
        history = [dict(row, id="other-bank", bank_id="other-bank"),
                   dict(row, id="partial", completed=False), legacy_history(1)[0], row]
        card.progress["history"] = history
        card._show_result(row, True)
        QTest.qWait(35)
        check(card.btn_band_profile.isVisible() and not card.btn_rebase.isVisible(),
              key + ": result exposes band profile, hides prediction application")
        check(card.chart.points == [(row["ts"], row["vocab"])], key + ": result chart contains only same-scale completed estimate")
        before = protected_snapshot(card.progress)
        with patch.object(card, "_read_only_report", side_effect=lambda title, text: reports.append((title, text))):
            click(card, card.btn_band_profile)
            click(card, card.btn_result_method)
        check(reports and "不等于分层掌握诊断" in reports[-1][1]
              and card.mode == "method" and card.page_title.text() == "评测说明"
              and "未经实测标定" in card.method_text.text(),
              key + ": band detail stays read-only and method opens as embedded page")
        click(card, card.btn_back)
        QTest.qWait(10)
        check(card.mode == "result", key + ": method-page back control returns to result")
        with patch.object(QMessageBox, "information", return_value=QMessageBox.Ok) as info:
            check(not card._apply_prediction() and info.call_count == 1, key + ": direct prediction request is refused")
        check(protected_snapshot(card.progress) == before, key + ": result/report actions leave learning unchanged")
        check("None" not in visible_text(card) and "严谨度" not in visible_text(card)
              and "误差" not in visible_text(card), key + ": result has no legacy score placeholders")
        card.result_page.verticalScrollBar().setValue(0)
        QTest.qWait(20)
        check(card.grab().save(str(outdir / ("result-%s.png" % key))), key + ": result screenshot saved")
        card._open_history_page()
        QTest.qWait(25)
        buttons = [button.text() for button in card.history_rows.findChildren(QPushButton)]
        check("报告" not in buttons, key + ": history rows no longer expose a report button")
        check(any("测试未完成" in text for text in buttons),
              key + ": incomplete history row says the test is unfinished")
        check("趋势只连接" not in visible_text(card), key + ": trend note is removed")
        summary = card.history_rows.findChildren(QPushButton, "historySummary")[0]
        summary.setChecked(True)
        QTest.qWait(20)
        details = [label.text() for label in card.history_rows.findChildren(QLabel, "historyDetail")
                   if label.isVisible()]
        expected_detail = "本次已作答 %d 题，答对 %d 题。" % (row["total"], row["right"])
        check(bool(details) and expected_detail in details[0]
              and "词频区间" not in details[0] and "题目分布在" not in details[0]
              and "模型95%" not in details[0] and "参数未标定" not in details[0]
              and "考生校准" not in details[0],
              key + ": expanded history shows answered/correct counts without interval wording")
        check(card.grab().save(str(outdir / ("history-%s.png" % key))),
              key + ": expanded history screenshot saved")

    old_hook = sys.excepthook
    sys.excepthook = lambda typ, value, tb: callback_errors.append("".join(traceback.format_exception(typ, value, tb)))
    try:
        with patch.dict(os.environ, {"VOCAB_TEST_OUT": str(outdir)}):
            sb = Sandbox(app_main, "v142-flow")
            scenarios = [("factory-reset", scenario_factory_reset),
                         ("startup-guards", scenario_startup_guards),
                         ("cold-build-edges", scenario_cold_build_edges),
                         ("settings-refresh", scenario_settings_refresh),
                         ("method-response", scenario_method_response),
                         ("answers", scenario_answers), ("resume", scenario_resume),
                         ("save-failure", scenario_save_failure),
                         ("summary", scenario_summary)]
            scenarios.extend(("theme-" + key, lambda sandbox, theme=key: scenario_theme(sandbox, theme))
                             for key in ("light", "dark", "sepia", "green"))
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                    patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as unexpected_errors, sb:
                for name, scenario in scenarios:
                    try:
                        scenario(sb)
                    except Exception:
                        failures.append(name + " raised")
                        out.append(traceback.format_exc())
                    finally:
                        for card in sb.cards:
                            sb._stop_card(card)
                            card.close()
                        QTest.qWait(20)
                try:
                    check(not callback_errors, "Qt slots have no uncaught callback exceptions")
                    check(unexpected_errors.call_count == 0, "normal scenarios show no unexpected critical dialogs")
                    check(sb.verify_real(), "read-only fingerprint guard: real user records/recovery files unchanged")
                except AssertionError:
                    pass
            out.extend(callback_errors)
            if sb.errors:
                out.extend(sb.errors)
            (outdir / "read-only-reports.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
            return sb.finish(out, failures, "ui-report.txt") == 0
    finally:
        sys.excepthook = old_hook
        # Keep the QApplication alive until all Sandbox teardown is complete.
        qt_app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ui", action="store_true", help="offscreen Sandbox Qt tests only")
    mode.add_argument("--all", action="store_true", help="AST plus offscreen Sandbox Qt tests")
    parser.add_argument("--out", help="optional report directory within workspace .vocab-ui-tests")
    parser.add_argument("--pattern", help="run AST test names containing this text")
    args = parser.parse_args()
    outdir = output_directory(args.out) if args.out or args.ui or args.all else None
    success = True
    if not args.ui:
        success = run_ast(outdir, args.pattern)
    if args.ui or args.all:
        success = run_ui(outdir) and success
    if outdir:
        print("REPORTS", outdir, flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
