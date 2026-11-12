# -*- coding: utf-8 -*-
"""V1.4.1 placement regression: unknown evidence, adaptive pick, full-bank cache."""
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import placement as pl


class EvidenceTests(unittest.TestCase):
    def test_unknown_has_same_negative_likelihood_as_wrong(self):
        bs = [-1.0, 0.0, 1.0, 0.5]
        for prior in ([1, 1, 0, 0], [1, -1, 0, 1], [-1, -1, 0, 0]):
            with self.subTest(prior=prior):
                grid_a, weights_a = pl.posterior(bs[:len(prior)], prior)
                replaced = [0 if value < 0 else value for value in prior]
                grid_b, weights_b = pl.posterior(bs[:len(prior)], replaced)
                self.assertEqual(grid_a, grid_b)
                for left, right in zip(weights_a, weights_b):
                    self.assertAlmostEqual(left, right, places=12)
                mean_a, se_a = pl.estimate_theta(bs[:len(prior)], prior)
                mean_b, se_b = pl.estimate_theta(bs[:len(prior)], replaced)
                self.assertAlmostEqual(mean_a, mean_b, places=12)
                self.assertAlmostEqual(se_a, se_b, places=12)

    def test_unknown_and_wrong_share_level_staircase(self):
        for start in (0, 3, 8):
            wrong = {"level": start, "up": 0, "down": 0, "wrong_streak": 0, "fast": True}
            unknown = dict(wrong)
            pl.step(wrong, False, 1, response=0)
            pl.step(unknown, False, 1, response=-1)
            self.assertEqual(wrong, unknown)
            pl.step(wrong, False, 2, response=0)
            pl.step(unknown, False, 2, response=-1)
            self.assertEqual(wrong, unknown)
            self.assertEqual(wrong["level"], max(0, start - 1))

    def test_unknown_distinct_response_and_rigor_policy(self):
        self.assertEqual(pl.update_rigor(40.0, -1), 40.0)
        self.assertLess(pl.update_rigor(40.0, 0), 40.0)
        self.assertGreater(pl.update_rigor(40.0, 1), 40.0)
        sess = pl.new_session()
        pl.step(sess, False, 1, response=-1)
        self.assertEqual(sess["wrong_streak"], 1)


class SelectionTests(unittest.TestCase):
    def test_first_question_uses_easiest_edge_and_ignores_bands(self):
        bs = [2.0, -3.0, 1.0, -2.95, 0.0]
        lvls = [0, 14, 0, 14, 0]
        picks = {pl.pick_idx(lvls, 14, [], random.Random(seed), bs=bs, theta=0.0)
                 for seed in range(30)}
        self.assertTrue(picks)
        self.assertTrue(picks <= {1, 3}, "first pick must be easiest-edge shortlist: %r" % picks)
        self.assertNotIn(4, picks)

    def test_target_is_theta_minus_half_not_band(self):
        bs = [-4.0, -1.0, 0.48, 0.50, 0.58, 2.0]
        lvls = [0, 14, 0, 14, 0, 14]
        picks = {pl.pick_idx(lvls, 14, [0], random.Random(seed), bs=bs, theta=1.0)
                 for seed in range(40)}
        self.assertTrue(picks <= {2, 3, 4}, "target 0.5 shortlist only: %r" % picks)
        self.assertNotIn(1, picks)
        self.assertNotIn(5, picks)

    def test_shortlist_keeps_candidates_when_a_later_item_is_better(self):
        # target=0.50: earlier candidates .45/.40 must not be lost when .50 appears.
        bs = [0.45, 0.40, 0.50, 0.90]
        picks = {pl.pick_idx([0, 0, 0, 0], 0, [3], random.Random(seed),
                             bs=bs, theta=1.0) for seed in range(40)}
        self.assertEqual(picks, {0, 1, 2},
                         "all items within 0.1 of best target must remain selectable: %r" % picks)

    def test_exhaustion_and_determinism(self):
        lvls = [0, 0, 1, 1, 2]
        bs = [-1.0, -0.9, 0.0, 0.1, 1.0]
        rng = random.Random(7)
        first = pl.pick_idx(lvls, 0, [], rng, bs=bs, theta=0.0)
        second = pl.pick_idx(lvls, 0, [], random.Random(7), bs=bs, theta=0.0)
        self.assertEqual(first, second)
        picks = []
        for _ in range(len(bs)):
            picks.append(pl.pick_idx(lvls, 0, picks, rng, bs=bs, theta=0.0))
        self.assertEqual(len(set(picks)), len(bs))
        self.assertIsNone(pl.pick_idx(lvls, 0, picks, rng, bs=bs, theta=0.0))

    def test_legacy_band_path_still_works(self):
        self.assertEqual(pl.pick_idx([0, 0, 1], 0, [], random.Random(9)),
                         pl.pick_idx([0, 0, 1], 0, [], random.Random(9)))
        self.assertIsNone(pl.pick_idx([0], 0, [0], random.Random(1)))


class VocabPosteriorTests(unittest.TestCase):
    def test_full_bank_bs_matches_expanded_reference(self):
        sample_bs = [-1.0, 0.0, 1.0]
        bank_bs = [-2.0, -1.0, 0.0, 0.0, 0.5, 1.0, 2.0]
        for responses in ([1, 0, -1], [1, 1, 1], [-1, -1, -1], []):
            with self.subTest(responses=responses):
                grid, weights = pl.posterior(sample_bs[:len(responses)], responses)
                values = [sum(pl.p_know(theta, b) for b in bank_bs) for theta in grid]
                expected = (sum(value * weight for value, weight in zip(values, weights)),
                            pl._quantile(values, weights, 0.025),
                            pl._quantile(values, weights, 0.975))
                actual = pl.vocab_posterior(sample_bs, responses, bank_bs=bank_bs)
                for got, want in zip(actual, expected):
                    self.assertAlmostEqual(got, want, places=9)

    def test_bank_total_legacy_api_preserved(self):
        bs = [-1.0, 0.0, 1.0]
        for responses in ([1, 0, -1], [1, 1, 1], [-1, -1, -1], []):
            for bank_total in (None, 2, 20):
                with self.subTest(responses=responses, bank_total=bank_total):
                    total = len(bs) if bank_total is None else max(len(bs), bank_total)
                    expanded = bs + [pl.CLAMP] * (total - len(bs))
                    grid, weights = pl.posterior(bs[:len(responses)], responses)
                    values = [pl.vocab_at(expanded, theta) for theta in grid]
                    expected = (sum(value * weight for value, weight in zip(values, weights)),
                                pl._quantile(values, weights, 0.025),
                                pl._quantile(values, weights, 0.975))
                    actual = pl.vocab_posterior(bs, responses, bank_total=bank_total)
                    for got, want in zip(actual, expected):
                        self.assertAlmostEqual(got, want, places=9)

    def test_full_bank_grid_is_cached(self):
        pl._bank_vocab_grid.cache_clear()
        pl._BANK_HIST_CACHE.clear()
        bank_bs = [-3.0 + 0.02 * i for i in range(500)]
        bs = [-1.0, 0.0, 1.0]
        responses = [1, 0, -1]
        with patch.object(pl, "p_know", wraps=pl.p_know) as probability:
            pl.vocab_posterior(bs, responses, bank_bs=bank_bs)
            first = probability.call_count
            pl.vocab_posterior(bs, responses, bank_bs=bank_bs)
            second = probability.call_count - first
        self.assertGreater(first, 0)
        self.assertEqual(second, 0, "second full-bank measurement must reuse cached grid")
        self.assertIn("_bank_vocab_grid", dir(pl))

    def test_error_percent_is_absolute_over_full_bank(self):
        mean, low, high = pl.vocab_posterior([-1.0, 0.0, 1.0], [1, 0, -1],
                                             bank_bs=[-2, -1, 0, 0.5, 1, 2])
        pct = pl.vocab_error_percent(low, high, 20000)
        self.assertAlmostEqual(pct, (high - low) / 2.0 / 20000.0 * 100.0, places=12)
        self.assertGreaterEqual(pct, 0.0)
        self.assertLessEqual(low, mean)
        self.assertLessEqual(mean, high)
        self.assertGreaterEqual(high - low, 0.0)

    def test_bank_bs_total_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            pl.vocab_posterior([0.0], [1], bank_total=3, bank_bs=[0.0, 1.0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
