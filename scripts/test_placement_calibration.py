# -*- coding: utf-8 -*-
"""Synthetic-only early-evidence calibration and display-contract regressions.

Run: python scripts/test_placement_calibration.py
No application state, real word records, or saved measurements are read/written.
"""
import math
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import placement as pl


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = pl.build_profile([
            {"w": "synthetic_%05d" % i, "frq": i + 1} for i in range(35000)
        ])

    def test_no_correct_means_unavailable_not_a_claim_of_zero_knowledge(self):
        for responses in ([], [0], [-1], [0, -1] * 10):
            with self.subTest(responses=responses):
                result = pl.measurement_summary([-3.2] * len(responses), responses, self.bank)
                self.assertEqual(result["estimate"], 0)
                self.assertFalse(result["estimate_available"])
                self.assertIsNone(result["err"])
                self.assertTrue(result["provisional"])
                self.assertGreater(result["raw_estimate"], 0)
                self.assertLess(result["low"], result["raw_estimate"])
                self.assertGreater(result["high"], result["raw_estimate"])

    def test_first_correct_is_modest_but_uncertainty_remains_large(self):
        result = pl.measurement_summary([-3.2], [1], self.bank)
        self.assertTrue(result["estimate_available"])
        self.assertGreater(result["estimate"], 0)
        self.assertLess(result["estimate"], 5000)
        self.assertEqual(result["estimate"], result["raw_estimate"])
        self.assertTrue(result["evidence_limited"])
        self.assertTrue(result["provisional"])
        self.assertGreater(result["err"], 100)
        self.assertGreater(result["high"], 10000, "do not cap a wide model interval")
        self.assertEqual(result["unit"], "bank_entries")

    def test_unknown_is_identical_negative_evidence_in_summary(self):
        wrong = pl.measurement_summary([-3.2, -2, -1], [1, 0, 0], self.bank)
        unknown = pl.measurement_summary([-3.2, -2, -1], [1, -1, -1], self.bank)
        self.assertEqual(wrong, unknown)

    def test_summary_interval_is_raw_calibrated_posterior_not_scaled(self):
        bank = [-3.2, -2.0, -1.0, 0.0, 1.0, 2.0, 3.2]
        bs, responses = [-3.2, -2, -1, 0], [1, 0, 1, -1]
        grid, weights = pl.posterior(bs, responses, prior_sd=pl.MEASUREMENT_PRIOR_SD,
                                     prior_mean=pl.MEASUREMENT_PRIOR_MEAN, grid_min=-10)
        values = [pl.vocab_at(bank, theta) for theta in grid]
        mean = sum(value * weight for value, weight in zip(values, weights))
        result = pl.measurement_summary(bs, responses, bank)
        self.assertAlmostEqual(result["raw_estimate"], mean, places=10)
        self.assertAlmostEqual(result["estimate"], mean, places=10)
        self.assertAlmostEqual(result["low"], pl._quantile(values, weights, .025), places=10)
        self.assertAlmostEqual(result["high"], pl._quantile(values, weights, .975), places=10)
        expected_err = max(mean - result["low"], result["high"] - mean) / mean * 100
        self.assertAlmostEqual(result["err"], expected_err, places=10)
        self.assertAlmostEqual(result["interval_level"], .95)

    def test_relative_error_does_not_shrink_when_bank_size_is_multiplied(self):
        bank = [-3.2, -2, -1, 0, 1, 2, 3.2]
        small = pl.measurement_summary([-3.2], [1], bank)
        large = pl.measurement_summary([-3.2], [1], bank * 100)
        self.assertAlmostEqual(small["err"], large["err"], places=10)
        self.assertAlmostEqual(small["estimate"] * 100, large["estimate"], places=9)

    def test_positive_evidence_gradually_unlocks_higher_estimate(self):
        results = [pl.measurement_summary([-3.2] * count, [1] * count, self.bank)
                   for count in (1, 3, 10, 30)]
        estimates = [result["estimate"] for result in results]
        self.assertEqual(estimates, sorted(estimates))
        self.assertGreater(estimates[-1], 10000, "no permanent early-estimate cap")
        self.assertTrue(all(result["provisional"] for result in results[:3]))
        self.assertLess(results[-1]["err"], results[0]["err"])

    def test_repeated_adaptive_evidence_can_leave_provisional_mode(self):
        rng = random.Random(42)
        bs, responses = [], []
        theta = pl.MEASUREMENT_PRIOR_MEAN
        for _ in range(120):
            b = theta - .5
            bs.append(b)
            responses.append(int(rng.random() < pl.p_correct(-1.0, b)))
            theta = pl.measurement_summary(bs, responses, self.bank)["theta"]
        result = pl.measurement_summary(bs, responses, self.bank)
        self.assertFalse(result["evidence_limited"])
        self.assertFalse(result["provisional"])
        self.assertLess(result["err"], 50)
        self.assertTrue(result["low"] <= pl.vocab_at(self.bank, -1) <= result["high"])

    def test_summary_is_deterministic_and_reuses_bank_grid(self):
        bank = [-3.2 + .02 * i for i in range(320)]
        pl._bank_vocab_grid.cache_clear()
        pl._BANK_HIST_CACHE.clear()
        with patch.object(pl, "p_know", wraps=pl.p_know) as probability:
            first = pl.measurement_summary([-3.2, -2], [1, 0], bank)
            calls = probability.call_count
            second = pl.measurement_summary([-3.2, -2], [1, 0], bank)
            self.assertEqual(probability.call_count, calls)
        self.assertGreater(calls, 0)
        self.assertEqual(first, second)

    def test_legacy_prior_defaults_remain_compatible(self):
        grid, weights = pl.posterior([], [])
        self.assertAlmostEqual(sum(weights), 1)
        self.assertAlmostEqual(sum(t * p for t, p in zip(grid, weights)), 0, places=10)
        self.assertEqual(pl.posterior([0], [-1]), pl.posterior([0], [0]))

    def test_empty_bank_and_length_validation(self):
        result = pl.measurement_summary([-3.2], [1], [])
        self.assertEqual((result["estimate"], result["low"], result["high"]), (0, 0, 0))
        self.assertIsNone(result["err"])
        self.assertTrue(result["provisional"])
        with self.assertRaises(ValueError):
            pl.measurement_summary([], [1], self.bank)
        self.assertTrue(math.isfinite(result["theta"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
