# -*- coding: utf-8 -*-
"""Regression for new-word retries in the Windows learning header.

Execute the actual Card methods extracted from main.py, with the real pure
StudyQueue/scheduler and invented in-memory records. No Qt, profile imports,
record files, or real learning data are needed.
"""
import ast
from copy import deepcopy
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import learning_policy as learn
import scheduler as sch
from study_queue import StudyQueue

METHODS = {
    "_can_act", "_capture_study", "_snapshot", "_restore_snapshot",
    "_answer_current", "act", "correct", "undo", "_make_engine",
    "_pull_new", "_next0", "_refresh_learning_status",
}
source = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
card = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "Card")
selected = [n for n in card.body if isinstance(n, ast.FunctionDef) and n.name in METHODS]
assert {n.name for n in selected} == METHODS
subject = ast.ClassDef(name="CardLogic", bases=[], keywords=[], body=selected, decorator_list=[])
module = ast.fix_missing_locations(ast.Module(body=[subject], type_ignores=[]))


class SaveError(RuntimeError):
    pass


namespace = {
    "copy": copy, "time": SimpleNamespace(time=lambda: 1000.0),
    "StudyQueue": StudyQueue, "learn": learn,
    "school": SimpleNamespace(normalize=lambda value: value, words=lambda value: set()),
    "storage": SimpleNamespace(StorageError=SaveError),
}
exec(compile(module, str(ROOT / "app" / "main.py"), "exec"), namespace)


class Label:
    def __init__(self):
        self.text = ""
        self.visible = True

    def setText(self, text):
        self.text = text

    def setVisible(self, visible):
        self.visible = visible

    def setEnabled(self, enabled):
        self.enabled = enabled


class Harness(namespace["CardLogic"]):
    def __init__(self, keys=("alpha", "beta", "gamma", "delta", "tail"),
                 states=None, record=None, ledger=None, daily_new=20):
        self.queue_words = [{"w": key, "s": "synthetic meaning " + key} for key in keys]
        self.states = deepcopy(states or {})
        self.book_id = "synthetic-book"
        self.study_records = {self.book_id: deepcopy(record or {})}
        self.cursors = {self.book_id: 0, "other-book": 17}
        self.daily_new_ledger = deepcopy(ledger or {})
        self.learning_settings = {"mode": learn.REVIEW_FIRST, "daily_new": daily_new}
        self.known = set()
        self.retry_gap = 3
        self.progress = {
            "states": self.states, "study_records": self.study_records,
            "cursors": self.cursors, "daily_new_ledger": self.daily_new_ledger,
            "extension": {"keep": [1, 2]}, "history": [{"synthetic": True}],
        }
        self.queue = []
        self.qi = 0
        self.cursor = 0
        self.snapshot = None
        self.last_action = None
        self.corrected = False
        self._last_answer_time = None
        self._closed = self._closing = False
        self.study_status = Label()
        self.btn_wrong = Label()
        self.window_ctl = SimpleNamespace(collapsed=False, animating=False)
        self.saved = None
        self.writes = 0
        self.fail_save = False
        self.mode = "empty"
        self._make_engine()
        if self._pull_new(persist=False):
            self._show_current()
        else:
            self._show_empty(persist=False)

    def save(self):
        if self.fail_save:
            raise SaveError("synthetic failure")
        self.writes += 1
        self.saved = json.loads(json.dumps(self.progress))

    def _show_current(self):
        self.mode = "front"
        self.corrected = False
        self._refresh_learning_status()

    def _show_back(self, word, remember):
        self.mode = "back"
        self._refresh_learning_status()

    def _show_empty(self, persist=True):
        self.mode = "empty"
        self._refresh_learning_status()
        if persist:
            self.save()

    def _study_save_error(self, error, before):
        self._restore_snapshot(before, transient=True)

    def current(self):
        if self.mode == "empty":
            return None
        item = self.queue[self.qi]
        return item["w"]["w"], item["kind"]


class LearningStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        namespace["time"].time = lambda: self.now

    def assert_aliases(self, w):
        self.assertIs(w.states, w.progress["states"])
        self.assertIs(w.states, w.study_engine.states)
        self.assertIs(w.study_record, w.study_records[w.book_id])
        self.assertIs(w.study_record, w.study_engine.record)
        self.assertIs(w.daily_new_ledger, w.learning_policy.ledger)
        self.assertEqual(w.cursors["other-book"], 17)

    def test_every_learning_phase_distinguishes_new_retry_and_review(self):
        w = Harness(keys=("alpha",))
        for mode in ("front", "back", "choice", "choice_back"):
            for kind, expected in (("new", "新词"), ("retry", "新词"), ("review", "复习")):
                with self.subTest(mode=mode, kind=kind):
                    w.mode = mode
                    w.queue[w.qi]["kind"] = kind
                    before = deepcopy(w._capture_study())
                    writes = w.writes
                    w._refresh_learning_status(now=10**12)
                    self.assertEqual(w.study_status.text, expected)
                    self.assertTrue(w.study_status.visible)
                    self.assertEqual(w._capture_study(), before)
                    self.assertEqual(w.writes, writes)

    def test_remember_then_correct_stays_new_and_reappears_after_three_new_answers(self):
        # The existing daily-new policy defers ready retries until its quota;
        # use a quota of four so three other first answers make alpha eligible.
        w = Harness(daily_new=4)
        self.assertEqual(w.current(), ("alpha", "new"))
        w.act("remember")
        self.assertEqual((w.states["alpha"]["lv"], w.states["alpha"]["due"]), (1, 1300))
        self.now = 1005
        writes = w.writes
        w.correct()
        self.assertEqual(w.writes, writes + 1)
        state = w.states["alpha"]
        self.assertEqual((state["st"], state["lv"], state["due"]), ("new", 0, None))
        self.assertEqual((state["seen"], state["lapse"], state["streak"]), (1, 1, 1))
        self.assertEqual(w.study_record["pending"], {"alpha": 4})
        self.assertEqual(w.learning_policy.learned_today(1000), 1)
        for key in ("beta", "gamma", "delta"):
            self.assertEqual(w.current(), (key, "new"))
            w.act("remember")
            w._next0()
        self.assertEqual(w.current(), ("alpha", "retry"))
        self.assertEqual(w.study_status.text, "新词")
        self.assertEqual(w.study_record["new_count"], 4)
        self.assertEqual(w.learning_policy.learned_today(1000), 4)
        self.assertIsNone(w.states["alpha"]["due"])
        self.assertEqual(sch.review_items(w.queue_words, w.states, 10**12)[0]["w"]["w"], "beta")
        self.assertNotIn("alpha", [item["w"]["w"] for item in sch.review_items(w.queue_words, w.states, 10**12)])
        self.assert_aliases(w)

    def test_book_end_early_retry_after_correction_is_new_not_review(self):
        w = Harness(keys=("alpha",))
        w.act("remember")
        w.correct()
        self.assertEqual(w.current(), ("alpha", "retry"))
        self.assertEqual(w.study_status.text, "新词")
        self.assertEqual(w.study_record["new_count"], 1)
        self.assertEqual(sch.review_items(w.queue_words, w.states, 10**12), [])
        self.assert_aliases(w)

    def test_direct_forget_repeated_retry_and_remember_have_matching_labels(self):
        w = Harness(keys=("alpha",))
        for _ in range(3):
            w.act("forget")
            self.assertEqual(w.study_status.text, "新词")
            w._next0()
            self.assertEqual(w.current(), ("alpha", "retry"))
            self.assertEqual(w.study_status.text, "新词")
        self.assertEqual(w.study_record["new_count"], 1)
        self.assertEqual(w.learning_policy.learned_today(1000), 1)
        w.act("remember")
        w._next0()
        self.assertEqual(w.mode, "empty")
        self.now += 300
        self.assertTrue(w._pull_new(persist=False))
        w.qi = len(w.queue) - 1
        w._show_current()
        self.assertEqual(w.current(), ("alpha", "review"))
        self.assertEqual(w.study_status.text, "复习")

    def test_serialized_restart_keeps_retry_label_and_records_unchanged(self):
        w = Harness(keys=("alpha",))
        w.act("remember")
        w.correct()
        saved = json.loads(json.dumps(w.progress))
        restarted = Harness(keys=("alpha",), states=saved["states"],
                            record=saved["study_records"][w.book_id],
                            ledger=saved["daily_new_ledger"])
        self.assertEqual(restarted.current(), ("alpha", "retry"))
        self.assertEqual(restarted.study_status.text, "新词")
        self.assertEqual(restarted.states, saved["states"])
        self.assertEqual(restarted.study_record, saved["study_records"][w.book_id])
        self.assertEqual(restarted.daily_new_ledger, saved["daily_new_ledger"])
        self.assert_aliases(restarted)

    def test_old_review_correction_keeps_original_level_and_five_minute_due(self):
        for level in range(1, 10):
            with self.subTest(level=level):
                original = {"lv": level, "st": "learning", "due": self.now,
                            "seen": 7, "lapse": 2, "streak": 1,
                            "extension": {"keep": [level]}}
                w = Harness(keys=("alpha",), states={"alpha": original})
                self.assertEqual(w.study_status.text, "复习")
                w.act("remember")
                w.correct()
                state = w.states["alpha"]
                self.assertEqual((state["st"], state["lv"], state["due"]),
                                 ("learning", level, self.now + 300))
                self.assertEqual((state["seen"], state["lapse"], state["streak"]), (8, 3, 2))
                self.assertEqual(state["extension"], original["extension"])
                self.assertEqual(w.study_record["new_count"], 0)
                self.assertEqual(w.daily_new_ledger.get("days", {}), {})
                self.now += 300
                self.assertTrue(w._pull_new(persist=False))
                w.qi = len(w.queue) - 1
                w._show_current()
                self.assertEqual(w.current(), ("alpha", "review"))
                self.assertEqual(w.study_status.text, "复习")
                self.assert_aliases(w)

    def test_undo_and_failed_correction_do_not_mutate_saved_learning(self):
        w = Harness(keys=("alpha",))
        w.act("remember")
        before = deepcopy(w._capture_study())
        saved = deepcopy(w.saved)
        w.fail_save = True
        w.correct()
        self.assertEqual(w._capture_study(), before)
        self.assertEqual(w.saved, saved)
        self.assertEqual(w.mode, "back")
        self.assert_aliases(w)
        w.fail_save = False
        w.undo()
        self.assertEqual(w.current(), ("alpha", "new"))
        self.assertEqual(w.study_status.text, "新词")
        self.assertEqual(w.states, {})
        self.assertEqual(w.study_record["new_count"], 0)

    def test_empty_and_nonlearning_headers_are_blank(self):
        w = Harness(keys=("alpha",))
        for mode in ("empty", "settings", "books", "history", "quiz", "welcome"):
            with self.subTest(mode=mode):
                w.mode = mode
                before = deepcopy(w._capture_study())
                w._refresh_learning_status()
                self.assertEqual(w.study_status.text, "")
                self.assertFalse(w.study_status.visible)
                self.assertEqual(w._capture_study(), before)

    def test_collapsed_or_animating_windows_keep_existing_visibility(self):
        w = Harness(keys=("alpha",))
        w.queue[w.qi]["kind"] = "retry"
        for collapsed, animating in ((True, False), (False, True), (True, True)):
            with self.subTest(collapsed=collapsed, animating=animating):
                w.window_ctl.collapsed = collapsed
                w.window_ctl.animating = animating
                w.study_status.visible = False
                w._refresh_learning_status()
                self.assertEqual(w.study_status.text, "新词")
                self.assertFalse(w.study_status.visible)


if __name__ == "__main__":
    unittest.main()
