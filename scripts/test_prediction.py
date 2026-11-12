# -*- coding: utf-8 -*-
"""Pure prediction selection and classification tests; no Qt or profile I/O."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import entries
import prediction


class PredictionTests(unittest.TestCase):
    def test_prediction_schema_is_separate_and_validated(self):
        data = prediction.new_prediction_data()
        self.assertEqual(data, {"schema": 1, "selected": [], "rejected": [],
                                "excluded": [], "effective": {
                                    "target": 0, "available": 0, "selected": 0}})
        self.assertIs(prediction.validate_prediction_data(data), data)
        invalid = copy.deepcopy(data)
        invalid["selected"] = ["x"]
        with self.assertRaises(ValueError):
            prediction.validate_prediction_data(invalid)
        for malformed in (None, [], {"schema": 2},
                          dict(data, rejected=["x", "x"])):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                prediction.validate_prediction_data(malformed)

    def test_strategy_target_and_validation(self):
        self.assertEqual(prediction.apply_strategy(100, 15, "conservative"), 85)
        self.assertEqual(prediction.apply_strategy(100, 15, "estimate"), 100)
        self.assertEqual(prediction.apply_strategy(100, 15, "optimistic"), 115)
        self.assertEqual(prediction.apply_strategy(10, 20, "conservative"), 0)
        for estimate, error, strategy in ((1, -1, "estimate"), (float("nan"), 1, "estimate"),
                                          (1, 1, "unknown"), (True, 1, "estimate")):
            with self.subTest(estimate=estimate, error=error, strategy=strategy):
                with self.assertRaises(ValueError):
                    prediction.apply_strategy(estimate, error, strategy)

    def test_selects_easiest_bands_and_only_randomizes_cutoff(self):
        words = [{"w": "a"}, {"w": "b"}, {"w": "c"}, {"w": "d"}, {"w": "e"}]
        bands = {"a": 0, "b": 0, "c": 1, "d": 1, "e": 2}
        first, counts = prediction.select_prediction_candidates(
            words, {}, 3, bands=bands, seed=23)
        second, _ = prediction.select_prediction_candidates(
            words, {}, 3, bands=bands, seed=23)
        self.assertEqual(first, second)
        self.assertEqual(first.intersection({"a", "b"}), {"a", "b"})
        self.assertEqual(len(first.intersection({"c", "d"})), 1)
        self.assertNotIn("e", first)
        self.assertEqual(counts, {"target": 3, "available": 5,
                                  "selected": 3, "excluded": 0})

    def test_exclusions_and_states_do_not_backfill_target(self):
        words = [{"w": key} for key in "abcdef"]
        bands = dict(zip("abcdef", range(6)))
        states = {"a": {"st": "new"}, "b": {"st": "learning"}}
        selected, counts = prediction.select_prediction_candidates(
            words, states, 4, bands, rejected={"c"}, excluded={"d"}, seed=1)
        self.assertEqual(selected, {"e", "f"})
        self.assertEqual(counts, {"target": 4, "available": 2,
                                  "selected": 2, "excluded": 4})

    def test_pending_entries_are_excluded(self):
        words = [{"w": "a", "pending": True}, {"w": "b"}]
        selected, counts = prediction.select_prediction_candidates(words, {}, 2, seed=0)
        self.assertEqual(selected, {"b"})
        self.assertEqual(counts["excluded"], 1)

    def test_classifier_precedence_and_real_mastery(self):
        states = {
            "master": {"st": "mastered", "lv": 10},
            "learn": {"st": "learning", "lv": 4},
            "evidence": {"st": "new", "seen": 1},
            "explicit": {"st": "new", "lv": 0},
        }
        predicted = {"master", "learn", "evidence", "explicit", "guess"}
        self.assertEqual(entries.memory_info("master", states, predicted=predicted),
                         ("mastered", 10, "Lv10 · 已掌握"))
        self.assertEqual(entries.memory_info("learn", states, predicted=predicted),
                         ("known", 4, "Lv4 · 认识"))
        self.assertEqual(entries.memory_info("evidence", states, predicted=predicted),
                         ("unlearned", 0, "待学习"))
        self.assertEqual(entries.memory_info("explicit", states, predicted=predicted),
                         ("unlearned", 0, "待学习"))
        self.assertEqual(entries.memory_info("guess", {}, predicted=predicted),
                         ("predicted", None, "已掌握"))

    def test_legacy_known_wins_over_prediction(self):
        self.assertEqual(entries.memory_info("x", {}, known={"x"}, predicted={"x"}),
                         ("known", None, "认识 · 测试估计"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
