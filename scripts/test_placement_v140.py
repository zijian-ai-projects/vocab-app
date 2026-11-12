# -*- coding: utf-8 -*-
"""Pure focused tests for the V1.4 placement core."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import placement as pl


class PosteriorTests(unittest.TestCase):
    def test_prior_is_symmetric_and_normalized(self):
        grid, weights = pl.posterior([], [])
        self.assertAlmostEqual(sum(weights), 1.0)
        self.assertAlmostEqual(sum(t * p for t, p in zip(grid, weights)), 0.0, places=8)

    def test_correct_increases_and_wrong_decreases_ability(self):
        correct, _ = pl.estimate_theta([0.0], [1])
        wrong, _ = pl.estimate_theta([0.0], [0])
        self.assertGreater(correct, 0.0)
        self.assertLess(wrong, 0.0)

    def test_unknown_has_no_likelihood_effect(self):
        self.assertEqual(pl.posterior([0.5], [-1]), pl.posterior([], []))

    def test_vocab_posterior_interval_contains_mean_and_uses_bank_total(self):
        mean, low, high = pl.vocab_posterior([-1.0, 0.0, 1.0], [1, 0, -1], bank_total=20)
        self.assertEqual((mean <= high, mean >= low), (True, True))
        self.assertGreaterEqual(low, 0)
        self.assertLessEqual(high, 20)


    def test_vocab_posterior_matches_expanded_reference(self):
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
                    for value, reference in zip(actual, expected):
                        self.assertAlmostEqual(value, reference, places=9)

    def test_large_word_bank_work_depends_only_on_sample_size(self):
        from unittest.mock import patch
        bs, responses = [-1.0, 0.0, 1.0], [1, 0, -1]
        grid, _ = pl.posterior(bs, responses)
        with patch.object(pl, "p_know", wraps=pl.p_know) as probability:
            mean, low, high = pl.vocab_posterior(bs, responses, bank_total=34963)
        self.assertLessEqual(probability.call_count, len(grid) * (len(bs) + 1))
        self.assertTrue(0 <= low <= mean <= high <= 34963)


class SelectionTests(unittest.TestCase):
    def test_unique_selection_and_explicit_exhaustion(self):
        lvls = [0, 0, 1, 1]
        rng = random.Random(20)
        picks = []
        for _ in range(len(lvls)):
            picks.append(pl.pick_idx(lvls, 0, picks, rng))
        self.assertEqual(len(set(picks)), len(lvls))
        self.assertIsNone(pl.pick_idx(lvls, 0, picks, rng))

    def test_deterministic_selection(self):
        self.assertEqual(pl.pick_idx([0, 0, 1], 0, [], random.Random(9)),
                         pl.pick_idx([0, 0, 1], 0, [], random.Random(9)))


class ItemTests(unittest.TestCase):
    def setUp(self):
        self.words = [
            {"w": "alpha", "pos": ["n."], "s": "首义；次义；第三义"},
            {"w": "beta", "pos": ["n."], "s": "乙义；其他"},
            {"w": "gamma", "pos": ["n."], "s": "丙义"},
            {"w": "delta", "pos": ["v."], "s": "丁义"},
            {"w": "epsilon", "pos": ["n."], "s": "戊义"},
        ]

    def test_stable_keyed_options_and_fixed_d(self):
        first = pl.make_item(self.words, 0, random.Random(5), trap_prob=0)
        second = pl.make_item(self.words, 0, random.Random(5), trap_prob=0)
        self.assertEqual(first, second)
        self.assertEqual([x["key"] for x in first["options"]], list("ABCD"))
        self.assertEqual(first["options"][3]["text"], pl.NO_ANSWER)
        self.assertNotEqual(first["correct_key"], "D")
        self.assertLessEqual(len(first["options"][0]["text"].split("；")), 2)

    def test_trap_probability_boundary_and_unknown_is_external(self):
        item = pl.make_item(self.words, 0, random.Random(3), trap_prob=1)
        self.assertTrue(item["trap"])
        self.assertEqual(item["correct_key"], "D")
        self.assertEqual(item["options"][3]["text"], pl.NO_ANSWER)
        self.assertEqual(len(item["options"]), 4)

    def test_insufficient_candidates_returns_none_without_mutation(self):
        words = [{"w": "alone", "s": "唯一"}, {"w": "same", "s": "唯一"}]
        original = [dict(row) for row in words]
        self.assertIsNone(pl.make_item(words, 0, random.Random(0)))
        self.assertEqual(words, original)

    def test_top_candidates_match_full_sorted_reference(self):
        from unittest.mock import patch
        words = [{"w": "word%d" % index, "s": "义%d；次义%d" % (index, index),
                  "pos": ["v." if index % 3 else "n."]} for index in range(80)]
        bs = [float(index % 7) / 2 for index in range(len(words))]
        reference = lambda count, rows, key: sorted(rows, key=key)[:count]
        for index in (0, 5, 79):
            for seed in (0, 7, 29):
                for probability in (0, 0.25, 1):
                    actual = pl.make_item(words, index, random.Random(seed), bs, probability)
                    with patch.object(pl, "nsmallest", side_effect=reference):
                        expected = pl.make_item(words, index, random.Random(seed), bs, probability)
                    self.assertEqual(actual, expected)

    def test_sense_cache_is_bounded_and_tracks_text_changes(self):
        from unittest.mock import patch
        pl._sense_text.cache_clear()
        word = {"s": "n. 原义；次义；第三义"}
        with patch.object(pl.re, "sub", wraps=pl.re.sub) as substitute:
            for _ in range(20):
                self.assertEqual(pl._sense(word), "原义；次义")
            self.assertEqual(substitute.call_count, 1)
        word["s"] = "v. 新义；另义"
        self.assertEqual(pl._sense(word), "新义；另义")
        self.assertEqual(pl._sense_text.cache_info().maxsize, 65536)

    def test_compatibility_options(self):
        opts, correct = pl.make_options(self.words, 0, random.Random(1), trap_prob=0)
        self.assertEqual(len(opts), 4)
        self.assertEqual(opts[3], pl.NO_ANSWER)
        self.assertNotEqual(correct, 3)


class PolicyTests(unittest.TestCase):
    def test_correct_diminishes_wrong_escalates_unknown_pauses(self):
        self.assertLess(pl.update_rigor(100, 1) - 100, pl.update_rigor(0, 1))
        self.assertLess(pl.update_rigor(40, 0) - 40, pl.update_rigor(0, 0))
        self.assertEqual(pl.update_rigor(40, -1), 40)
        self.assertEqual(pl.update_rigor(104, 1), 105)
        self.assertEqual(pl.update_rigor(3, 0), 0)

    def test_unknown_pauses_wrong_streak(self):
        sess = pl.new_session()
        pl.step(sess, False, 1)
        before = dict(sess)
        pl.step(sess, False, 2, response=-1)
        self.assertEqual(sess["wrong_streak"], before["wrong_streak"])
        for n in range(20):
            pl.step(sess, False, n + 3)
        self.assertLessEqual(sess["wrong_streak"], 12)


if __name__ == "__main__":
    unittest.main()
