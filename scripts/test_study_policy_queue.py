# -*- coding: utf-8 -*-
"""Daily-policy StudyQueue tests; use only in-memory words/state/records."""
import copy
import datetime as dt
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
from study_queue import StudyQueue
from learning_policy import LearningPolicy, DAILY_NEW_FIRST, REVIEW_FIRST, local_day

NOW = dt.datetime(2026, 11, 9, 12).timestamp()
MIDNIGHT = dt.datetime(2026, 11, 10).timestamp()


def old_state(due=NOW-1):
    return {"st": "learning", "lv": 2, "due": due, "seen": 2, "lapse": 0, "extra": "keep"}


class StudyPolicyQueueTests(unittest.TestCase):
    def make(self, n=2, mode=DAILY_NEW_FIRST, keys=("a", "b", "c", "old"),
             states=None, record=None, ledger=None, known=None):
        states = states if states is not None else {"old": old_state()}
        record = record if record is not None else {}
        policy = LearningPolicy({"mode": mode, "daily_new": n}, ledger if ledger is not None else {})
        words = [{"w": key, "s": "fixture"} for key in keys]
        return StudyQueue(words, states, record, known=known, policy=policy), policy

    def assert_item(self, item, key, kind):
        self.assertIsNotNone(item)
        self.assertEqual((item["w"]["w"], item["kind"]), (key, kind))

    def test_review_first_remains_default_algorithm(self):
        q, p = self.make(mode=REVIEW_FIRST)
        self.assert_item(q.next(NOW), "old", "review")
        self.assertEqual(p.remaining(NOW), 2)
        self.assertNotIn("policy_held", q.record)

    def test_none_policy_is_legacy_compatible(self):
        q = StudyQueue([{"w": "a"}, {"w": "old"}], {"old": old_state()}, {})
        self.assert_item(q.next(NOW), "old", "review")
        self.assertNotIn("policy_held", q.record)

    def test_daily_n_new_before_due_review(self):
        q, p = self.make()
        for key in ("a", "b"):
            item = q.next(NOW)
            self.assert_item(item, key, "new")
            q.answer(item, True, NOW)
        self.assertEqual(p.remaining(NOW), 0)
        self.assert_item(q.next(NOW), "old", "review")
        self.assertEqual(q.record["new_count"], 2)

    def test_display_does_not_consume(self):
        q, p = self.make()
        before = copy.deepcopy(q.states)
        item = q.next(NOW)
        for _ in range(4):
            self.assert_item(q.next(NOW), item["w"]["w"], "new")
            self.assertEqual(p.remaining(NOW), 2)
        self.assertEqual(q.states, before)
        self.assertEqual(q.record["new_count"], 0)

    def test_zero_reviews_due_items_before_new(self):
        q, p = self.make(n=0)
        self.assert_item(q.next(NOW), "old", "review")
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "a", "new")
        self.assertEqual(q.record["new_count"], 0)

    def test_no_due_review_continues_new_after_daily_target(self):
        q, p = self.make(n=1, states={})
        q.answer(q.next(NOW), True, NOW)
        self.assertEqual(p.remaining(NOW), 0)
        self.assert_item(q.next(NOW), "b", "new")

    def test_quotas_do_not_consume_retry_or_review(self):
        q, p = self.make()
        for _ in range(2):
            q.answer(q.next(NOW), False, NOW)
        item = q.next(NOW)
        self.assert_item(item, "old", "review")
        q.answer(item, True, NOW)
        item = q.next(NOW)
        self.assert_item(item, "c", "new")
        q.answer(item, True, NOW)
        self.assert_item(q.next(NOW), "a", "retry")
        self.assertEqual(p.learned_today(NOW), 3)
        self.assertEqual(q.record["new_count"], 3)

    def test_daily_target_then_due_reviews_then_more_new(self):
        q, p = self.make(n=1, keys=("a", "b", "old"), states={"old": old_state()})
        q.answer(q.next(NOW), True, NOW)
        self.assertEqual(p.remaining(NOW), 0)
        q.states["old"]["due"] = NOW - 1
        self.assert_item(q.next(NOW), "old", "review")
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "b", "new")

    def test_saved_review_and_saved_new_are_preserved(self):
        rec = {"current": {"kind": "review", "key": "old"},
               "held_current": {"kind": "new", "key": "b"}}
        q, p = self.make(record=rec)
        self.assert_item(q.next(NOW), "b", "new")
        self.assertIn({"kind": "review", "key": "old"}, rec["policy_held"])
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "a", "new")
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "old", "review")
        q.answer(q.next(NOW), True, NOW)
        self.assertFalse(any(row["key"] == "old" for row in rec["policy_held"]))

    def test_target_reorders_new_around_due_reviews(self):
        q, p = self.make()
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "b", "new")
        p.settings["daily_new"] = 1
        self.assert_item(q.next(NOW), "old", "review")
        self.assertIn({"kind": "new", "key": "b"}, q.record["policy_held"])
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "b", "new")
        self.assertEqual(p.remaining(NOW), 0)

    def test_existing_new_item_can_be_answered_after_target_changes(self):
        q, p = self.make()
        item = q.next(NOW)
        p.settings["daily_new"] = 0
        q.answer(item, True, NOW)
        self.assertEqual(p.learned_today(NOW), 1)
        self.assertEqual(q.states["a"]["seen"], 1)

    def test_restart_preserves_global_ledger_and_saved_current(self):
        q, p = self.make(n=1, states={})
        q.answer(q.next(NOW), True, NOW)
        q2, p2 = self.make(n=1, states=q.states, record=q.record, ledger=p.ledger)
        self.assert_item(q2.next(NOW), "b", "new")
        self.assertEqual(p2.remaining(NOW), 0)
        self.assertNotIn("b", q2.states)

    def test_midnight_resumes_without_restart_and_keeps_cursor(self):
        q, p = self.make(n=1, states={})
        q.answer(q.next(NOW), True, NOW)
        cursor = q.cursor
        self.assertEqual(cursor, 1)
        self.assert_item(q.next(NOW), "b", "new")
        self.assertEqual(p.remaining(NOW), 0)
        self.assertEqual(q.cursor, cursor)

    def test_due_review_precedes_new_after_daily_target(self):
        q, p = self.make(n=1, states={})
        q.answer(q.next(NOW), True, NOW)
        q.states["a"]["due"] = NOW - 1
        self.assert_item(q.next(NOW), "a", "review")
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "b", "new")

    def test_review_due_is_next_wake(self):
        q, p = self.make(n=1, states={"old": old_state(NOW+100)})
        q.answer(q.next(NOW), True, NOW)
        self.assertEqual(q.next_due_time(NOW), NOW+100)

    def test_switch_back_restores_parked_new_after_review(self):
        q, p = self.make()
        q.answer(q.next(NOW), True, NOW)
        item = q.next(NOW)
        p.settings["daily_new"] = 1
        q.next(NOW)
        p.settings["mode"] = REVIEW_FIRST
        self.assert_item(q.next(NOW), "old", "review")
        q.answer(q.next(NOW), True, NOW)
        self.assert_item(q.next(NOW), "b", "new")
        self.assertEqual(p.learned_today(NOW), 1)

    def test_two_books_share_stable_key_count(self):
        states, ledger = {}, {}
        qa, pa = self.make(n=2, keys=("a", "b"), states=states, ledger=ledger)
        qa.answer(qa.next(NOW), True, NOW)
        qb, pb = self.make(n=2, keys=("a", "c", "d"), states=states, ledger=ledger)
        self.assert_item(qb.next(NOW), "c", "new")
        qb.answer(qb.next(NOW), True, NOW)
        self.assert_item(qa.next(NOW), "b", "new")
        self.assertEqual(pa.learned_today(NOW), 2)
        self.assertEqual(pb.learned_today(NOW), 2)

    def test_known_estimate_is_not_counted_as_new(self):
        q, p = self.make(states={}, known={"a"})
        self.assert_item(q.next(NOW), "b", "new")
        q.answer(q.next(NOW), True, NOW)
        self.assertEqual(p.ledger["days"][local_day(NOW)], ["b"])

    def test_duplicate_answer_rejected_without_extra_count(self):
        q, p = self.make()
        item = q.next(NOW)
        q.answer(item, True, NOW)
        before = copy.deepcopy((q.states, p.ledger))
        with self.assertRaises(ValueError):
            q.answer(item, True, NOW)
        self.assertEqual((q.states, p.ledger), before)

    def test_cross_midnight_amend_uses_original_intro_date(self):
        q, p = self.make(n=1, states={})
        before = copy.deepcopy((q.states, q.record, p.ledger))
        item = q.next(NOW)
        # Capture the actual pre-answer graph, including the selected current.
        before = copy.deepcopy((q.states, q.record, p.ledger))
        q.answer(item, True, NOW)
        for shared, saved in zip((q.states, q.record, p.ledger), before):
            shared.clear()
            shared.update(saved)
        q.answer(item, False, MIDNIGHT, introduced_at=NOW)
        self.assertEqual(p.learned_today(NOW), 1)
        self.assertEqual(p.learned_today(MIDNIGHT), 0)
        self.assertEqual(q.record["new_count"], 1)

    def test_invalid_policy_held_rejected_without_erasing(self):
        rec = {"policy_held": [1]}
        before = copy.deepcopy(rec)
        with self.assertRaises(TypeError):
            self.make(record=rec)
        self.assertEqual(rec, before)

    def test_restored_current_keeps_unknown_fields_same_key(self):
        unknown = {"future": {"keep": [1, True, "x"]}, "nested": {"v": 2}}
        cases = (
            ("new", "a", {}),
            ("retry", "a", {"a": {"st": "new", "lv": 0, "due": None,
                                  "seen": 1, "lapse": 1}}),
            ("review", "old", {"old": old_state()}),
        )
        for kind, key, states in cases:
            rec = {"current": dict(unknown, kind=kind, key=key)}
            q, _ = self.make(mode=REVIEW_FIRST, states=copy.deepcopy(states), record=rec)
            item = q.next(NOW)
            self.assert_item(item, key, kind)
            current = q.record["current"]
            self.assertEqual((current["kind"], current["key"]), (kind, key))
            for field, value in unknown.items():
                self.assertEqual(current[field], value,
                                 "%s current 未知字段 %s 必须恢复" % (kind, field))

    def test_policy_held_unknown_fields_restored_with_resume(self):
        unknown = {"future": {"keep": ["parked"]}, "nested": {"n": 9}}
        rec = {"current": dict(unknown, kind="new", key="a")}
        q, p = self.make(n=0, states={}, record=rec)
        self.assert_item(q.next(NOW), "a", "new")
        held = q.record.get("policy_held") or []
        self.assertFalse(held)
        for field, value in unknown.items():
            self.assertEqual(q.record["current"][field], value,
                             "当前新词未知字段 %s 必须保留" % field)
        self.assert_item(q.next(NOW), "a", "new")
        current = q.record["current"]
        self.assertEqual(current["key"], "a")
        self.assertIsNone(current.get("resume"))
        for field, value in unknown.items():
            self.assertEqual(current[field], value,
                             "恢复 policy_held 未知字段 %s 必须保留" % field)


if __name__ == "__main__":
    unittest.main(verbosity=2)
