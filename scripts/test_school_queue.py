# -*- coding: utf-8 -*-
"""Pure school-exclusion regressions: fixed clock, synthetic in-memory records only."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scheduler as sch
from study_queue import StudyQueue


NOW = 1000


def book(*keys):
    return [{"w": key, "s": "fixture"} for key in keys]


def learned(due=NOW):
    return {"st": "learning", "lv": 2, "due": due, "seen": 2,
            "lapse": 0, "custom": {"keep": [1, 2]}}


def forgotten():
    return sch.on_forget(sch.new_state(), NOW)


class SchoolQueueTests(unittest.TestCase):
    def assert_item(self, item, key, kind):
        self.assertIsNotNone(item)
        self.assertEqual((item["w"]["w"], item["kind"]), (key, kind))
        return item

    def test_learned_an_due_is_suspended_not_deleted(self):
        states = {"an": learned(), "old": learned()}
        original = deepcopy(states)
        excluded = {"an"}
        q = StudyQueue(book("an", "old", "fresh"), states, {}, excluded=excluded)
        q.answer(self.assert_item(q.next(NOW), "old", "review"), True, NOW)
        q.answer(self.assert_item(q.next(NOW), "fresh", "new"), True, NOW)
        self.assertIsNone(q.next(NOW))
        self.assertEqual(states["an"], original["an"])
        excluded.clear()
        self.assert_item(q.next(NOW), "an", "review")

    def test_new_exclusions_and_prediction_are_separate(self):
        q = StudyQueue(book("an", "predicted", "explicit", "fresh", "x", "y", "z", "w", "v"),
                       {"explicit": forgotten()}, {"pending": {"explicit": 0}, "new_count": 4},
                       known={"predicted", "explicit"}, excluded={"an"})
        q.answer(self.assert_item(q.next(NOW), "explicit", "retry"), True, NOW)
        self.assert_item(q.next(NOW), "fresh", "new")
        self.assertNotIn("an", q.states)
        q.excluded = set()
        q.answer(self.assert_item(q.next(NOW), "fresh", "new"), True, NOW)
        for key in "xyzwv":
            q.answer(self.assert_item(q.next(NOW), key, "new"), True, NOW)
        self.assert_item(q.next(NOW), "an", "new")

    def test_school_resume_preserves_ready_and_future_retry_targets(self):
        for target in (0, 999):
            with self.subTest(target=target):
                states = {"an": forgotten()}
                record = {"pending": {"an": target}, "new_count": 4}
                q = StudyQueue(book("an", "other"), states, record, excluded={"an"})
                q.answer(self.assert_item(q.next(NOW), "other", "new"), True, NOW)
                self.assertIsNone(q.next(NOW))
                self.assertEqual(record["pending"], {"an": target})
                q.excluded.clear()
                if target <= record["new_count"]:
                    self.assert_item(q.next(NOW), "an", "retry")
                else:
                    self.assertIsNone(q.next(NOW))
                self.assertEqual(record["pending"]["an"], target)

    def test_excluded_pending_not_cleaned_even_if_shared_state_learned(self):
        state = learned()
        q = StudyQueue(book("an"), {"an": state}, {"pending": {"an": 42}}, excluded={"an"})
        self.assertIsNone(q.next(NOW))
        self.assertEqual(q.record["pending"], {"an": 42})
        self.assertEqual(q.states["an"], state)
        q.excluded.clear()
        self.assert_item(q.next(NOW), "an", "review")
        self.assertEqual(q.record["pending"], {})  # Normal reconciliation resumes.

    def test_excluded_ready_retry_resumes_at_book_end(self):
        q = StudyQueue(book("an", "other"), {"an": forgotten()},
                       {"pending": {"an": 0}, "new_count": 4}, excluded={"an"})
        self.assert_item(q.next(NOW), "other", "new")
        q.answer(q.next(NOW), True, NOW)
        self.assertIsNone(q.next(NOW))
        self.assertEqual(q.record["pending"]["an"], 0)
        q.excluded.clear()
        self.assert_item(q.next(NOW), "an", "retry")

    def test_current_all_kinds_suspend_and_restore_unknown_fields_after_restart(self):
        for kind in ("new", "retry", "review"):
            with self.subTest(kind=kind):
                states = {} if kind == "new" else {"an": forgotten() if kind == "retry" else learned()}
                saved = {"key": "an", "kind": kind, "future": {"keep": [True]}}
                record = {"current": deepcopy(saved)}
                if kind == "retry":
                    record["pending"] = {"an": 77}
                    record["new_count"] = 77
                    record["cursor"] = 1
                q = StudyQueue(book("an", "fresh"), states, record, excluded={"an"})
                q.answer(self.assert_item(q.next(NOW), "fresh", "new"), True, NOW)
                self.assertIsNone(q.next(NOW))
                self.assertIn(saved, record["policy_held"])
                states, record = json.loads(json.dumps([states, record]))
                q = StudyQueue(book("an", "fresh"), states, record)
                self.assert_item(q.next(NOW), "an", kind)
                self.assertEqual(record["current"]["future"], saved["future"])
                if kind == "retry":
                    self.assertEqual(record["pending"]["an"], 77)

    def test_held_and_school_suspended_all_kinds_skip_and_restore(self):
        for slot in ("held_current", "policy_held"):
            for kind in ("new", "retry", "review"):
                with self.subTest(slot=slot, kind=kind):
                    saved = {"key": "an", "kind": kind, "extra": ["unchanged"]}
                    record = {slot: [deepcopy(saved)] if slot == "policy_held" else deepcopy(saved)}
                    states = {} if kind == "new" else {"an": forgotten() if kind == "retry" else learned()}
                    if kind == "retry":
                        record["pending"] = {"an": 12}
                        record["new_count"] = 12
                    q = StudyQueue(book("an", "fresh"), states, record, excluded={"an"})
                    self.assert_item(q.next(NOW), "fresh", "new")
                    q.answer(q.next(NOW), True, NOW)
                    self.assertIsNone(q.next(NOW))
                    self.assertIn(saved, record["policy_held"])
                    q.excluded.clear()
                    self.assert_item(q.next(NOW), "an", kind)
                    if kind == "retry":
                        self.assertEqual(record["pending"]["an"], 12)
                    self.assertEqual(record["current"]["extra"], ["unchanged"])

    def test_excluded_held_survives_other_current_review_interruption(self):
        record = {"held_current": {"kind": "new", "key": "an", "marker": 7},
                  "current": {"kind": "new", "key": "fresh"}}
        q = StudyQueue(book("an", "fresh", "old"), {"old": learned()}, record, excluded={"an"})
        q.answer(self.assert_item(q.next(NOW), "old", "review"), True, NOW)
        q.answer(self.assert_item(q.next(NOW), "fresh", "new"), True, NOW)
        self.assertIsNone(q.next(NOW))
        q.excluded.clear()
        self.assert_item(q.next(NOW), "an", "new")
        self.assertEqual(record["current"]["marker"], 7)

    def test_excluded_review_does_not_interrupt_valid_new(self):
        record = {"current": {"kind": "new", "key": "fresh", "marker": 9}}
        q = StudyQueue(book("an", "fresh"), {"an": learned()}, record, excluded={"an"})
        self.assert_item(q.next(NOW), "fresh", "new")
        self.assertEqual(record["current"], {"kind": "new", "key": "fresh", "marker": 9})
        self.assertNotIn("policy_held", record)

    def test_future_wake_excludes_school_and_resumes(self):
        q = StudyQueue(book("an", "later"), {"an": learned(NOW + 1), "later": learned(NOW + 50)}, {}, excluded={"an"})
        self.assertEqual(q.next_due_time(NOW), NOW + 50)
        q.excluded.clear()
        self.assertEqual(q.next_due_time(NOW), NOW + 1)

    def test_enabling_exclusion_rejects_old_answer_without_any_mutation(self):
        for kind in ("new", "retry", "review"):
            with self.subTest(kind=kind):
                states = {} if kind == "new" else {"an": forgotten() if kind == "retry" else learned()}
                q = StudyQueue(book("an", "more"), states, {"new_count": 4} if kind == "retry" else {})
                item = self.assert_item(q.next(NOW), "an", kind)
                q.excluded.add("an")
                before = deepcopy((states, q.record))
                with self.assertRaises(ValueError):
                    q.answer(item, True, NOW)
                self.assertEqual((states, q.record), before)

    def test_engine_and_regressions_never_open_records(self):
        with patch("builtins.open", side_effect=AssertionError("pure queue test")):
            q = StudyQueue(book("an"), {"an": learned()}, {}, excluded={"an"})
            self.assertIsNone(q.next(NOW))
            q.excluded.clear()
            q.answer(self.assert_item(q.next(NOW), "an", "review"), True, NOW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
