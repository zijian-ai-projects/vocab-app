# -*- coding: utf-8 -*-
"""Pure learning-policy/ledger regression; no GUI and no profile I/O."""
import copy
import datetime as dt
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import learning_policy as lp

NOW = dt.datetime(2026, 11, 9, 12, 30).timestamp()


class LearningPolicyTests(unittest.TestCase):
    def make(self, mode=lp.DAILY_NEW_FIRST, limit=2, ledger=None):
        return lp.LearningPolicy({"mode": mode, "daily_new": limit},
                                 ledger if ledger is not None else {})

    def test_default_review_first_and_limit_20(self):
        self.assertEqual(lp.normalize_settings(), lp.DEFAULTS)
        p = self.make(lp.REVIEW_FIRST, 0)
        self.assertTrue(p.allows_new(NOW))

    def test_integer_bounds_and_safe_preferences(self):
        for value in (0, 1, 20, 999, "20"):
            self.assertEqual(lp.normalize_settings({"daily_new": value})["daily_new"], int(value))
        for value in (-1, 1000, True, False, "bad", [], {}, None, 2.5, float("inf")):
            self.assertEqual(lp.normalize_settings({"daily_new": value})["daily_new"], 20)
        self.assertEqual(lp.normalize_settings({"mode": "bad"})["mode"], lp.REVIEW_FIRST)

    def test_display_queries_do_not_create_today_or_consume(self):
        p = self.make()
        before = copy.deepcopy(p.ledger)
        for _ in range(5):
            self.assertEqual(p.remaining(NOW), 2)
            self.assertEqual(p.learned_today(NOW), 0)
            self.assertTrue(p.allows_new(NOW))
        self.assertEqual(p.ledger, before)

    def test_only_unique_stable_keys_count(self):
        p = self.make()
        self.assertTrue(p.introduce_new("alice", NOW))
        self.assertFalse(p.introduce_new("alice", NOW))
        self.assertTrue(p.introduce_new("phrase:look up", NOW))
        self.assertEqual(p.remaining(NOW), 0)
        self.assertTrue(p.allows_new(NOW))
        self.assertEqual(p.ledger["days"][lp.local_day(NOW)], ["alice", "phrase:look up"])

    def test_shared_ledger_across_books(self):
        ledger = {}
        a, b = self.make(ledger=ledger), self.make(ledger=ledger)
        a.introduce_new("a", NOW)
        self.assertEqual(b.remaining(NOW), 1)
        b.introduce_new("b", NOW)
        self.assertEqual(a.remaining(NOW), 0)
        self.assertIs(a.ledger, b.ledger)

    def test_shared_settings_change_immediately(self):
        p = self.make()
        p.introduce_new("a", NOW)
        p.settings["daily_new"] = 1
        self.assertEqual(p.remaining(NOW), 0)
        self.assertTrue(p.should_review_before_new(NOW))
        p.settings["daily_new"] = 3
        self.assertEqual(p.remaining(NOW), 2)
        self.assertFalse(p.should_review_before_new(NOW))

    def test_review_first_still_records_before_switch(self):
        p = self.make(lp.REVIEW_FIRST, 1)
        p.introduce_new("a", NOW)
        p.introduce_new("b", NOW)
        self.assertFalse(p.should_review_before_new(NOW))
        p.settings["mode"] = lp.DAILY_NEW_FIRST
        self.assertTrue(p.should_review_before_new(NOW))
        self.assertEqual(p.learned_today(NOW), 2)

    def test_zero_means_review_before_new(self):
        p = self.make(limit=0)
        self.assertEqual(p.remaining(NOW), 0)
        self.assertTrue(p.allows_new(NOW))
        self.assertTrue(p.should_review_before_new(NOW))
        self.assertTrue(p.should_review_before_new(NOW))

    def test_natural_midnight_and_not_24hours_later(self):
        p = self.make(limit=1)
        before = dt.datetime(2026, 11, 9, 23, 59, 59).timestamp()
        midnight = dt.datetime(2026, 11, 10).timestamp()
        p.introduce_new("a", before)
        self.assertEqual(p.next_day_time(before), midnight)
        self.assertEqual(p.remaining(before), 0)
        self.assertEqual(p.remaining(midnight), 1)
        self.assertGreater(p.next_day_time(midnight), midnight)

    def test_history_dates_and_unknown_fields_are_preserved(self):
        ledger = {"schema": 1, "extra": {"keep": 1}, "days": {"2026-11-08": ["old", "old"]}}
        p = self.make(ledger=ledger)
        p.introduce_new("a", NOW)
        self.assertEqual(ledger["days"]["2026-11-08"], ["old", "old"])
        self.assertEqual(ledger["extra"], {"keep": 1})
        self.assertEqual(p.learned_today(dt.datetime(2026, 11, 8, 12).timestamp()), 1)

    def test_snapshot_rollback_uses_same_shared_dict(self):
        p = self.make()
        snapshot = copy.deepcopy(p.ledger)
        p.introduce_new("a", NOW)
        shared = p.ledger
        shared.clear()
        shared.update(snapshot)
        self.assertIs(p.ledger, shared)
        self.assertEqual(p.remaining(NOW), 2)

    def test_restore_settings_does_not_clear_learning_ledger(self):
        p = self.make()
        p.introduce_new("a", NOW)
        before = copy.deepcopy(p.ledger)
        p.settings.clear()
        p.settings.update(lp.DEFAULTS)
        self.assertEqual(p.ledger, before)
        self.assertTrue(p.allows_new(NOW))

    def test_bad_ledger_is_rejected_not_erased(self):
        for ledger in ([], {"days": []}, {"days": {"bad-day": []}},
                       {"days": {"2026-11-09": {}}}, {"days": {"2026-11-09": [None]}},
                       {"days": {"2026-11-09": [""]}}):
            old = copy.deepcopy(ledger)
            with self.assertRaises(ValueError):
                self.make(ledger=ledger)
            self.assertEqual(ledger, old)

    def test_bad_key_rejected_without_mutation(self):
        p = self.make()
        before = copy.deepcopy(p.ledger)
        for key in (None, "", "   ", 42):
            with self.assertRaises(ValueError):
                p.introduce_new(key, NOW)
        self.assertEqual(p.ledger, before)

    def test_never_opens_profile_or_any_file(self):
        with patch("builtins.open", side_effect=AssertionError("Policy must not do file I/O")):
            p = self.make()
            p.introduce_new("a", NOW)
            p.remaining(NOW)
            p.next_day_time(NOW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
