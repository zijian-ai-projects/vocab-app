# -*- coding: utf-8 -*-
"""纯逻辑选项测试；不导入 main/storage，不写真实 data 或 test_result。

默认使用内存中的 35,000 条合成词库验证缓存与性能。可加 --bank-perf
只读真实 bank.json 做一次预解析 + 1,000 题性能验证，仍只输出到 stdout。
"""
from copy import deepcopy
from pathlib import Path
import json
import random
import sys
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import study_options as so
from study_options import OptionPool, make_options


def entry(key, text, **fields):
    return {"w": key, "s": text, **fields}


def basic_entries():
    return [entry("target", "n.银行"), entry("forest", "n.森林"),
            entry("stone", "n.石头"), entry("cloud", "n.云"), entry("star", "n.星星")]


class StudyOptionsTests(unittest.TestCase):
    def assert_question(self, question, target, entries):
        self.assertEqual(set(question), {"options", "correct"})
        self.assertEqual(len(question["options"]), 4)
        self.assertEqual(len(set(question["options"])), 4)
        self.assertEqual(len({so._senses(text) for text in question["options"]}), 4)
        self.assertIn(question["correct"], range(4))
        correct = so.meaning(target)
        self.assertEqual(question["options"][question["correct"]], correct)
        self.assertEqual(question["options"].count(correct), 1)
        true_texts = {so.meaning(row) for row in entries} | {correct}
        self.assertTrue(set(question["options"]).issubset(true_texts))
        self.assertNotIn("没有正确答案", question["options"])
        self.assertNotIn("不认识", question["options"])
        target_senses = so._senses(correct)
        for idx, text in enumerate(question["options"]):
            if idx != question["correct"]:
                self.assertTrue(so._senses(text).isdisjoint(target_senses))
        return question

    def test_list_api_four_real_unique_meanings_with_known_answer(self):
        rows = basic_entries()
        self.assert_question(make_options(rows[0], rows, random.Random(7)), rows[0], rows)

    def test_target_is_always_present_and_never_a_trap(self):
        rows = basic_entries()
        pool = OptionPool(rows)
        positions = set()
        for seed in range(200):
            question = self.assert_question(make_options(rows[0], pool, random.Random(seed)), rows[0], rows)
            positions.add(question["correct"])
        self.assertEqual(positions, set(range(4)))

    def test_function_buttons_and_no_answer_are_not_distractors(self):
        rows = basic_entries() + [entry("trap", "没有正确答案"), entry("dk", "不认识"),
                                  entry("prefixed_trap", "n. 没有正确答案"),
                                  entry("prefixed_dk", "v.不认识")]
        pool = OptionPool(rows)
        for seed in range(20):
            question = self.assert_question(make_options(rows[0], pool, random.Random(seed)), rows[0], rows)
            self.assertTrue(all(so._senses(text).isdisjoint(so._RESERVED) for text in question["options"]))

    def test_reserved_target_does_not_create_a_function_or_trap_answer(self):
        rows = basic_entries()
        for text in ("没有正确答案", "不认识", "n.没有正确答案", "v.不认识"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                make_options(entry("invalid", text), OptionPool(rows), random.Random(0))

    def test_empty_or_pos_only_target_is_rejected(self):
        rows = basic_entries()
        for text in ("", "   ", "n.", "adj.；v."):
            with self.subTest(text=text), self.assertRaises(ValueError):
                make_options(entry("empty", text), rows, random.Random(0))

    def test_empty_distractors_are_ignored(self):
        rows = basic_entries() + [entry("empty", ""), entry("spaces", "  "), entry("pos_only", "n.")]
        self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(0)), rows[0], rows)

    def test_raw_fallback_and_pos_string_or_list_are_real_display_text(self):
        rows = [entry("target", "", raw="银行", pos="n."),
                entry("forest", "森林", pos=["n."]), entry("stone", "n.石头", pos=["n."]),
                entry("cloud", "云", pos=["n."])]
        question = self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(1)), rows[0], rows)
        self.assertEqual(question["options"][question["correct"]], "n. 银行")
        self.assertNotIn("n. n.石头", question["options"])

    def test_phrase_entries_have_one_known_correct_meaning(self):
        rows = [entry("take up", "从事；着手处理", type="phrase", pos=[]),
                entry("all at once", "突然；同时", type="phrase"),
                entry("as usual", "像往常一样", type="phrase"),
                entry("by the way", "顺便说一下", type="phrase"),
                entry("in vain", "徒劳地", type="phrase")]
        self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(6)), rows[0], rows)

    def test_exact_and_pos_spacing_duplicate_of_correct_are_excluded(self):
        rows = basic_entries() + [entry("alias_exact", "n.银行"), entry("alias_space", "n. 银行"),
                                  entry("alias_no_pos", "银行"), entry("alias_punctuation", "银行。")]
        pool = OptionPool(rows)
        for seed in range(20):
            question = self.assert_question(make_options(rows[0], pool, random.Random(seed)), rows[0], rows)
            self.assertNotIn("n. 银行", question["options"])
            self.assertNotIn("银行", question["options"])
            self.assertNotIn("银行。", question["options"])

    def test_duplicate_other_senses_keep_one_real_representation(self):
        rows = basic_entries()[:4] + [entry("forest_alias", "森林"), entry("forest_space", "n. 森林")]
        question = self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(2)), rows[0], rows)
        self.assertEqual(sum(so._senses(text) == {"森林"} for text in question["options"]), 1)
        self.assertIn("n.森林", question["options"])

    def test_shared_target_sense_is_excluded_instead_of_a_second_correct_answer(self):
        rows = basic_entries() + [entry("bank_and_shore", "n.银行；河岸"), entry("finance", "金融机构，银行")]
        pool = OptionPool(rows)
        for seed in range(20):
            question = self.assert_question(make_options(rows[0], pool, random.Random(seed)), rows[0], rows)
            self.assertNotIn("n.银行；河岸", question["options"])
            self.assertNotIn("金融机构，银行", question["options"])

    def test_multisense_target_excludes_each_correct_sense(self):
        rows = [entry("target", "vt.保护；n.防护"), entry("same_verb", "v.保护"),
                entry("same_noun", "n.防护"), entry("forest", "n.森林"),
                entry("stone", "n.石头"), entry("cloud", "n.云")]
        self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(10)), rows[0], rows)

    def test_insufficient_non_overlapping_distractors_raise_without_fabrication(self):
        rows = basic_entries()[:3] + [entry("partial_1", "银行；河岸"), entry("partial_2", "银行；交易")]
        with self.assertRaises(ValueError):
            make_options(rows[0], OptionPool(rows), random.Random(1))

    def test_less_than_four_entries_including_target_cannot_make_four_choices(self):
        rows = basic_entries()
        for count in range(4):
            with self.subTest(count=count), self.assertRaises(ValueError):
                make_options(rows[0], rows[:count], random.Random(0))

    def test_all_duplicate_or_empty_distractors_are_rejected(self):
        rows = [entry("target", "银行"), entry("same", "n.银行"),
                entry("empty", ""), entry("same_again", "银行"), entry("other", "森林")]
        with self.assertRaises(ValueError):
            make_options(rows[0], OptionPool(rows), random.Random(0))

    def test_same_word_alternate_meaning_is_not_a_distractor(self):
        rows = basic_entries() + [entry("target", "n.另外一个含义")]
        for seed in range(20):
            question = self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(seed)), rows[0], rows)
            self.assertNotIn("n.另外一个含义", question["options"])

    def test_source_key_union_excludes_alias_of_alternate_target_meaning(self):
        rows = basic_entries() + [entry("target", "n.另义"), entry("another_word", "另义")]
        question = self.assert_question(make_options(rows[0], OptionPool(rows), random.Random(0)), rows[0], rows)
        self.assertNotIn("n.另义", question["options"])
        self.assertNotIn("另义", question["options"])

    def test_constructor_and_len_do_not_parse_the_pool(self):
        rows = basic_entries()
        with patch.object(so, "meaning", side_effect=AssertionError("not lazy")), \
                patch.object(so, "_senses", side_effect=AssertionError("not lazy")):
            pool = OptionPool(rows)
            self.assertEqual(len(pool), len(rows))
            self.assertFalse(pool.prepared)

    def test_prepare_is_idempotent_and_questions_reuse_parsed_target(self):
        rows = basic_entries() + [entry("duplicate", "n.森林")]
        pool = OptionPool(rows)
        with patch.object(so, "meaning", wraps=so.meaning) as fmt, \
                patch.object(so, "_senses", wraps=so._senses) as parse:
            self.assertIs(pool.prepare(), pool)
            self.assertTrue(pool.prepared)
            self.assertEqual(fmt.call_count, len(rows))
            self.assertEqual(parse.call_count, 5)
            count = (fmt.call_count, parse.call_count)
            pool.prepare()
            make_options(rows[0], pool, random.Random(5))
            make_options(rows[1], pool, random.Random(6))
            self.assertEqual((fmt.call_count, parse.call_count), count)

    def test_input_entries_and_list_are_not_mutated(self):
        rows = basic_entries()
        snapshot = deepcopy(rows)
        pool = OptionPool(rows)
        make_options(rows[0], pool, random.Random(3))
        make_options(rows[1], rows, random.Random(4))
        self.assertEqual(rows, snapshot)
        self.assertEqual(tuple(rows), pool.entries)

    def test_tuple_and_generator_compatibility(self):
        rows = basic_entries()
        expected = make_options(rows[0], rows, random.Random(42))
        self.assertEqual(make_options(rows[0], tuple(rows), random.Random(42)), expected)
        self.assertEqual(make_options(rows[0], iter(rows), random.Random(42)), expected)

    def test_seeded_rng_is_deterministic_across_list_and_reused_pool(self):
        rows = basic_entries()
        pool = OptionPool(rows)
        for seed in range(20):
            expected = make_options(rows[0], rows, random.Random(seed))
            self.assertEqual(make_options(rows[0], pool, random.Random(seed)), expected)
            self.assertEqual(make_options(rows[0], pool, random.Random(seed)), expected)

    def test_random_module_is_supported_without_affecting_global_test_state(self):
        rows = basic_entries()
        saved = random.getstate()
        try:
            random.seed(42)
            question = make_options(rows[0], OptionPool(rows), random)
            self.assertEqual(question, make_options(rows[0], OptionPool(rows), random.Random(42)))
        finally:
            random.setstate(saved)

    def test_default_and_falsey_rng_are_supported(self):
        class FalseyRandom(random.Random):
            def __bool__(self):
                return False
        rows = basic_entries()
        self.assert_question(make_options(rows[0], OptionPool(rows)), rows[0], rows)
        self.assertEqual(make_options(rows[0], OptionPool(rows), FalseyRandom(17)),
                         make_options(rows[0], OptionPool(rows), random.Random(17)))

    def test_legacy_shuffle_only_rng_is_compatible(self):
        class ShuffleOnly:
            def shuffle(self, values):
                values.reverse()
        rows = basic_entries()
        question = make_options(rows[0], OptionPool(rows), ShuffleOnly())
        self.assert_question(question, rows[0], rows)
        self.assertEqual(question, make_options(rows[0], rows, ShuffleOnly()))

    def test_external_target_can_use_three_real_pool_distractors(self):
        target = entry("outside", "prep.在外面")
        rows = basic_entries()[1:4]
        self.assert_question(make_options(target, OptionPool(rows), random.Random(0)), target, rows)

    def test_external_target_normalized_alias_is_not_another_correct_option(self):
        target = entry("outside", "n. 银行")
        rows = basic_entries()[:4]
        self.assert_question(make_options(target, OptionPool(rows), random.Random(0)), target, rows)

    def test_current_entry_changes_refresh_only_that_real_answer(self):
        rows = basic_entries()
        pool = OptionPool(rows).prepare()
        rows[0]["s"] = "n.最新目标释义"
        with patch.object(so, "meaning", wraps=so.meaning) as fmt:
            question = make_options(rows[0], pool, random.Random(0))
            self.assertEqual(fmt.call_count, 1)
            self.assertEqual(question["options"][question["correct"]], "n.最新目标释义")
            make_options(rows[0], pool, random.Random(1))
            self.assertEqual(fmt.call_count, 1)
        self.assertNotIn("n.银行", question["options"])

    def test_normalization_handles_pos_case_punctuation_and_escaped_newline(self):
        self.assertEqual(so._senses("n.银行\\nvt.储存； n. 金融机构。"),
                         {"银行", "储存", "金融机构"})
        self.assertEqual(so._senses("N. Bank ; V. KEEP"), {"bank", "keep"})
        self.assertEqual(so._senses("adj.快乐/高兴、愉快"), {"快乐", "高兴", "愉快"})

    def test_sample_miss_falls_back_to_cached_meanings_without_regex(self):
        class FirstIndicesRandom(random.Random):
            def sample(self, population, k):
                return list(range(k))
        rows = [entry("target", "目标")] + [entry("overlap%d" % i, "目标；重复%d" % i) for i in range(20)]
        rows += [entry("forest", "森林"), entry("stone", "石头"), entry("cloud", "云")]
        pool = OptionPool(rows).prepare()
        with patch.object(so, "meaning", side_effect=AssertionError("format cache missed")), \
                patch.object(so, "_senses", side_effect=AssertionError("sense cache missed")):
            question = make_options(rows[0], pool, FirstIndicesRandom(0))
        self.assert_question(question, rows[0], rows)

    def test_sampling_is_bounded_and_only_four_options_are_shuffled(self):
        class CountingRandom(random.Random):
            def __init__(self, seed):
                super().__init__(seed)
                self.sample_calls = []
                self.shuffle_lengths = []
            def sample(self, population, k):
                self.sample_calls.append((type(population), len(population), k))
                return super().sample(population, k)
            def shuffle(self, values):
                self.shuffle_lengths.append(len(values))
                return super().shuffle(values)
        rows = [entry("w%d" % i, "n.释义%d" % i) for i in range(1000)]
        pool, rng = OptionPool(rows), CountingRandom(1)
        question = make_options(rows[0], pool, rng)
        self.assertEqual(rng.sample_calls, [(range, 1000, so._SAMPLE_SIZE)])
        self.assertEqual(rng.shuffle_lengths, [4])
        self.assert_question(question, rows[0], rows)

    def test_35000_entry_pool_parses_once_then_1000_questions_are_fast(self):
        rows = [entry("w%d" % i, "n.合成释义%d" % i) for i in range(35000)]
        pool = OptionPool(rows)
        counts = {"meaning": 0, "senses": 0}
        original_meaning, original_senses = so.meaning, so._senses
        def counted_meaning(row):
            counts["meaning"] += 1
            return original_meaning(row)
        def counted_senses(text):
            counts["senses"] += 1
            return original_senses(text)
        rng = random.Random(2026)
        with patch.object(so, "meaning", new=counted_meaning), \
                patch.object(so, "_senses", new=counted_senses):
            started = time.perf_counter()
            pool.prepare()
            prepared_seconds = time.perf_counter() - started
            self.assertEqual(counts, {"meaning": 35000, "senses": 35000})
            started = time.perf_counter()
            for idx in rng.sample(range(len(rows)), 1000):
                question = make_options(rows[idx], pool, rng)
                self.assertEqual(question["options"][question["correct"]], rows[idx]["s"])
                self.assertEqual(len(set(question["options"])), 4)
            question_seconds = time.perf_counter() - started
            self.assertEqual(counts, {"meaning": 35000, "senses": 35000}, "per-question full parsing regressed")
        self.assertLess(question_seconds, 3.0, "1,000 cached questions took unexpectedly long")
        print("PERF synthetic entries=35000 prepare=%.3fs questions=1000 total=%.3fs avg=%.3fms" %
              (prepared_seconds, question_seconds, question_seconds))

    def test_engine_performs_no_file_access(self):
        rows = basic_entries()
        with patch("builtins.open", side_effect=AssertionError("option generator must not open files")):
            pool = OptionPool(rows)
            question = make_options(rows[0], pool, random.Random(0))
        self.assert_question(question, rows[0], rows)


def bank_performance():
    """显式 --bank-perf 才读 bank；绝不打开记录文件或写任何数据。"""
    with (ROOT / "data" / "bank.json").open("r", encoding="utf-8-sig") as stream:
        rows = json.load(stream)
    pool = OptionPool(rows)
    started = time.perf_counter()
    pool.prepare()
    prepare_seconds = time.perf_counter() - started
    rng, done, skipped = random.Random(2026), 0, 0
    started = time.perf_counter()
    for idx in rng.sample(range(len(rows)), min(len(rows), 2000)):
        try:
            question = make_options(rows[idx], pool, rng)
        except ValueError:
            skipped += 1
            continue
        assert len(set(question["options"])) == 4
        assert question["options"][question["correct"]] == so.meaning(rows[idx])
        assert "没有正确答案" not in question["options"] and "不认识" not in question["options"]
        done += 1
        if done == 1000:
            break
    seconds = time.perf_counter() - started
    assert done == min(len(rows), 1000), "real bank could not produce enough valid questions"
    print("PERF bank entries=%d prepare=%.3fs questions=%d skipped=%d total=%.3fs avg=%.3fms" %
          (len(rows), prepare_seconds, done, skipped, seconds, seconds * 1000 / max(done, 1)))


if __name__ == "__main__":
    if "--bank-perf" in sys.argv:
        sys.argv.remove("--bank-perf")
        bank_performance()
    unittest.main(verbosity=2)
