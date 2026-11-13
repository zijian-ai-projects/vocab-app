# -*- coding: utf-8 -*-
"""V1.4.2 independent engine regression and READ-ONLY real-bank smoke tests.

Run from any directory:
    python -B scripts/test_vocabulary_test_v142.py

All numerical fixtures are synthetic Chinese-sense banks, not empirical
population calibration.  The optional real dictionary is only read; no user
records, legacy engine, GUI, installation, or data writes are involved.
"""
import ast
import copy
import hashlib
import json
import math
import random
import sys
import time
import unittest
from collections import Counter
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import vocabulary_test as vt

_BUILD_TIMES = {}


def spelling(number):
    letters = []
    for _ in range(5):
        number, digit = divmod(number, 26)
        letters.append(chr(97 + digit))
    return "entry" + "".join(reversed(letters))


def synthetic(size):
    # Deliberately unique two-Han-character synthetic sense tokens.  A shared
    # boilerplate such as "测试释义..." would correctly trigger ambiguity
    # rejection and would not be a useful numerical fixture.
    return [{"w": spelling(index), "s": "n." + chr(0x4E00 + index // 200)
             + chr(0x5300 + index % 200), "pos": ["n."], "frq": 100 + index * 7,
             "raw": "", "b": float("nan"), "lvl": index % 15}
            for index in range(size)]


@lru_cache(maxsize=10)
def bank(size):
    started = time.perf_counter()
    result = vt.FrequencyBank(synthetic(size))
    _BUILD_TIMES[size] = time.perf_counter() - started
    return result


def record_for(source, key, phase="adaptive"):
    item = source.items[key]
    options = [key] + list(source._distractors[key][:3])
    if len(options) != 4:
        raise ValueError("fixture target is not testable")
    return {"key": key, "band": item["band"], "rank": item["rank"], "phase": phase,
            "irt": {name: item[name] for name in ("a", "b", "c")},
            "item": {"item_id": key, "word": item["word"], "correct_index": 0,
                     "correct_key": "A",
                     "options": [{"key": "ABCD"[index], "item_id": option,
                                  "text": source.items[option]["sense"]}
                                 for index, option in enumerate(options)]}}


def fixed_records(source, count, start=0):
    keys = list(source.items)[start:start + count]
    return [record_for(source, key, "survey" if index == 0 else "adaptive")
            for index, key in enumerate(keys)]


def append_draw(source, state, records, responses, response):
    record = vt.next_item(source, state, records, responses)
    if record is not None:
        records.append(record)
        state["asked"].append(record["key"])
        responses.append(response)
    return record


def attempt(source, policy, seed=17):
    state, records, responses = vt.new_state(seed), [], []
    while len(records) <= vt.MAX_ITEMS:
        response = policy(len(records))
        if append_draw(source, state, records, responses, response) is None:
            return state, records, responses, vt.summarize(source, records, responses)
    raise AssertionError("attempt exceeded MAX_ITEMS")


def session_fixture(source=None, count=5, answered_last=False):
    source = source or bank(3000)
    state, records, responses = vt.new_state(987), [], []
    for index in range(count):
        record = vt.next_item(source, state, records, responses)
        if record is None:
            raise AssertionError("fixture unexpectedly stopped")
        records.append(record)
        state["asked"].append(record["key"])
        if index < count - 1 or answered_last:
            responses.append((1, 0, -1)[index % 3])
    return {"schema": vt.SESSION_SCHEMA, "algo": vt.ALGORITHM,
            "bank_id": source.fingerprint, "id": "fixture-session-1",
            "started_at": 1.0, "state": state, "items": records,
            "resp": responses, "i": len(records) - 1}


def independent_posterior(records, responses):
    grid = [index / 20.0 for index in range(-100, 141)]
    logs = []
    for theta in grid:
        value = -0.5 * (theta / 2.0) ** 2
        for record, response in zip(records, responses):
            b = math.log((record["rank"] + 100) / 1000.0)
            q = 1.0 / (1.0 + math.exp(-1.4 * (theta - b)))
            p = 0.25 + 0.75 * q
            value += math.log(p if response == 1 else 1.0 - p)
        logs.append(value)
    scale = max(logs)
    weights = [math.exp(value - scale) for value in logs]
    total = math.fsum(weights)
    weights = [weight / total for weight in weights]
    mean = math.fsum(theta * weight for theta, weight in zip(grid, weights))
    se = math.sqrt(math.fsum(weight * (theta - mean) ** 2
                             for theta, weight in zip(grid, weights)))
    return grid, weights, mean, se


def reference_quantile(values, weights, probability):
    cumulative = 0.0
    for value, weight in zip(values, weights):
        cumulative += weight
        if cumulative >= probability:
            return value
    return values[-1]


def set_path(value, path, replacement):
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = replacement


class BankContractTests(unittest.TestCase):
    def test_constants_and_python38_stdlib_independence(self):
        expected = {"ALGORITHM": "vst-cat-v142", "SESSION_SCHEMA": 2,
                    "MEASUREMENT_SCHEMA": 3, "BAND_SIZE": 1000,
                    "MAX_WORDS": 20000, "MIN_ITEMS": 40, "MAX_ITEMS": 80,
                    "MIN_PER_BAND": 2, "TARGET_SE": 0.30, "A": 1.4, "C": 0.25}
        for name, value in expected.items():
            self.assertEqual(getattr(vt, name), value)
        tree = ast.parse((ROOT / "app" / "vocabulary_test.py").read_text(encoding="utf-8"),
                         feature_version=8)
        allowed = {"hashlib", "json", "math", "random", "re", "unicodedata", "functools"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(alias.name in allowed for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
        self.assertEqual(len(vt.THETA_GRID), 241)
        self.assertEqual((vt.THETA_GRID[0], vt.THETA_GRID[-1]), (-5.0, 7.0))

    def test_build_progress_is_monotonic_zero_to_100_and_identity_neutral(self):
        words = synthetic(400)
        values = []
        source = vt.FrequencyBank(words, progress=values.append)
        baseline = vt.FrequencyBank(words)
        self.assertEqual((values[0], values[-1]), (0, 100))
        self.assertEqual(values, sorted(set(values)))
        self.assertGreater(len(values), 10)
        self.assertEqual(source.fingerprint, baseline.fingerprint)
        self.assertEqual(list(source.items), list(baseline.items))
        with self.assertRaisesRegex(ValueError, "progress"):
            vt.FrequencyBank(words, progress="not-callable")

    def test_local_ranks_not_source_ranks_or_school_fields(self):
        class NoSchoolFields(dict):
            def get(self, key, default=None):
                if key in ("b", "lvl", "l"):
                    raise AssertionError("legacy/school field was read")
                return super().get(key, default)

            def __getitem__(self, key):
                if key in ("b", "lvl", "l"):
                    raise AssertionError("legacy/school field was read")
                return super().__getitem__(key)

        words = [NoSchoolFields(row) for row in synthetic(2053)]
        words.reverse()
        source = vt.FrequencyBank(words)
        self.assertEqual(source.size, 2053)
        self.assertEqual(source.excluded_count, 0)
        self.assertEqual([part["size"] for part in source.bands], [1000, 1000, 53])
        self.assertEqual([part["id"] for part in source.bands], [1, 2, 3])
        for rank, item in enumerate(source.items.values(), 1):
            self.assertEqual(item["rank"], rank)
            self.assertEqual(item["band"], (rank - 1) // 1000 + 1)
            self.assertEqual(item["a"], 1.4)
            self.assertEqual(item["c"], 0.25)
            self.assertAlmostEqual(item["b"], math.log((rank + 100) / 1000.0), places=15)
        for band_id, part in enumerate(source.bands, 1):
            self.assertEqual(part["start"], (band_id - 1) * 1000 + 1)
            self.assertEqual(part["end"] - part["start"] + 1, part["size"])
            self.assertIn("本地有效词目", part["label"])

    def test_invalid_frequency_senses_entities_and_nonwords_are_excluded(self):
        valid = synthetic(8)
        bad = []
        for index, frq in enumerate((0, -1, "7", None, True, False, float("nan"), float("inf"))):
            row = synthetic(1)[0]
            row.update(w="bad" + spelling(index), frq=frq)
            bad.append(row)
        for index, sense in enumerate(("", "...", "n/a", "未知释义", "乱码", "= another",
                                       "word的过去式", "以上皆非", "n.人名；艾丽丝", "n.伦敦")):
            bad.append({"w": "sense" + spelling(index), "s": sense, "pos": [], "frq": 500})
        bad.extend([{"w": "NASA", "s": "国家航空机构", "frq": 4},
                    {"w": "Alice", "s": "艾丽丝", "frq": 5},
                    {"w": "shortform", "s": "国家航空机构", "raw": "abbr.缩略形式", "frq": 6},
                    {"w": "new york", "s": "城市", "frq": 7},
                    {"w": "fixture-0001", "s": "实例", "frq": 8},
                    {"w": "china", "s": "n.中国；adj.中国的", "frq": 9},
                    {"w": "invalidpos", "s": "n.火焰", "pos": [7], "frq": 10},
                    {"w": "control", "s": "n.火\x00焰", "frq": 11},
                    None, "not an entry"])
        source = vt.FrequencyBank(valid + bad)
        self.assertEqual(source.size, len(valid))
        self.assertEqual(source.excluded_count, len(bad))
        self.assertEqual(list(source.items), [row["w"] for row in valid])
        abbreviation = {"w": "abbreviation", "s": "n.缩写形式", "pos": ["n."], "frq": 50}
        self.assertIn("abbreviation", vt.FrequencyBank(valid + [abbreviation]).items)

    def test_unlabelled_abbreviations_do_not_blacklist_short_ordinary_words(self):
        names = ("etc", "mrs", "pm", "mr", "ms", "dr", "vs", "ltd", "inc",
                 "jr", "sr", "eg", "ie", "aka", "asap", "st")
        ordinary = ("am", "as", "in", "no", "us", "ad", "fig", "mar", "etcetera",
                    "abbreviation", "acronym", "abbreviate", "department", "professional")
        good = synthetic(len(ordinary))
        for row, word in zip(good, ordinary):
            row["w"] = word
        bad = [{"w": word, "s": "n.太太，夫人" if word == "mrs" else "及其他，等等",
                "pos": ["n."] if word == "mrs" else [], "raw": "", "frq": 1}
               for word in names]
        snapshot = copy.deepcopy(good + bad)
        source = vt.FrequencyBank(good + bad)
        self.assertEqual(set(source.items), set(ordinary))
        self.assertEqual(source.excluded_count, len(bad))
        self.assertEqual(good + bad, snapshot)
        self.assertEqual(source.fingerprint, vt.FrequencyBank(list(reversed(good + bad))).fingerprint)

    def test_only_inflection_pointers_not_ordinary_lexical_readings(self):
        pointers = ("word的复数", "v.go 的过去式和过去分词", "(be的过去分词)",
                    "n.‘word’ 的复数形式。", "go的过去式；go的过去分词",
                    "go的过去式、过去分词", "be的单数第一人称",
                    "be的过去式\\nbe的过去分词")
        bad = [{"w": "pointer" + spelling(index), "s": sense, "frq": index + 1}
               for index, sense in enumerate(pointers)]
        senses = (("form", "n.词形"), ("past", "n.过去"), ("plural", "adj.复数的"),
                  ("saw", "n.锯子；see的过去式"), ("left", "adj.左边的；leave的过去式"),
                  ("better", "adj.更好的；good的比较级"),
                  ("children", "n.孩子（child的复数）"))
        good = [{"w": word, "s": sense, "frq": index + 100,
                 "raw": "see的过去式" if word == "saw" else ""}
                for index, (word, sense) in enumerate(senses)]
        source = vt.FrequencyBank(bad + good)
        self.assertEqual(set(source.items), {word for word, _ in senses})
        self.assertEqual(source.excluded_count, len(bad))

    def test_conservative_entity_metadata_not_ordinary_gloss_substrings(self):
        bad = [{"w": "namedperson", "s": "n.人名；艾丽丝", "frq": 1},
               {"w": "namedplace", "s": "n.地名；某城市", "frq": 2},
               {"w": "rawname", "s": "n.黄铜", "raw": "n.黄铜\\nn.人名；艾丽丝", "frq": 3},
               {"w": "labelled", "s": "n.黄铜", "raw": "[姓氏]某姓", "frq": 4},
               {"w": "namedcity", "s": "n.伦敦", "frq": 5}]
        good = [{"w": word, "s": sense, "frq": index + 20}
                for index, (word, sense) in enumerate((
                    ("china", "n.瓷器"), ("history", "n.研究中国历史"),
                    ("surname", "n.姓，姓氏"), ("name", "n.名字，名称"),
                    ("country", "n.国家"), ("abbreviation", "n.缩写形式"),
                    ("acronym", "n.首字母缩略词"), ("proper", "adj.适当的")))]
        good.append({"w": "I", "s": "pron.我", "pos": ["pron."], "frq": 10})
        source = vt.FrequencyBank(bad + good)
        self.assertEqual(set(source.items), {row["w"].casefold() for row in good})
        self.assertEqual(source.items["i"]["word"], "I")
        self.assertEqual(source.excluded_count, len(bad))

    def test_sort_deduplicate_cap_and_stable_fingerprint(self):
        words = synthetic(60)
        original = copy.deepcopy(words)
        duplicated = copy.deepcopy(words[10])
        duplicated.update(frq=1, s="n.苹果")
        words.extend([duplicated, copy.deepcopy(duplicated)])
        source = vt.FrequencyBank(words)
        reverse = vt.FrequencyBank(list(reversed(words)))
        self.assertEqual(source.size, 60)
        self.assertEqual(source.excluded_count, 2)
        self.assertEqual(source.fingerprint, reverse.fingerprint)
        self.assertEqual(next(iter(source.items)), duplicated["w"])
        self.assertEqual(source.items[duplicated["w"]]["source_frq"], 1)
        self.assertEqual(words[:60], original)
        large = vt.FrequencyBank(synthetic(20003))
        self.assertEqual(large.size, 20000)
        self.assertEqual(large.excluded_count, 3)
        self.assertEqual(large.bands[-1]["end"], 20000)

    def test_population_summary_steps_are_bounded_exact_and_read_only(self):
        words = synthetic(301)
        words.extend([copy.deepcopy(words[17]), {"w": "invalid", "frq": 0}, None])
        before = copy.deepcopy(words)
        selected, input_count = vt._select_entries(words)
        expected = {"size": len(selected), "excluded_count": input_count - len(selected),
                    "bands": (len(selected) + vt.BAND_SIZE - 1) // vt.BAND_SIZE}
        batches = list(vt.population_summary_steps(iter(words), batch_size=37))
        self.assertEqual(batches[:-1], [None] * (len(words) // 37))
        self.assertEqual(batches[-1], expected)
        self.assertEqual(vt.population_summary(iter(words)), expected)
        self.assertEqual(words, before)
        with patch.object(vt, "MAX_WORDS", 23):
            capped, _ = vt._select_entries(words)
            self.assertEqual(vt.population_summary(words), {
                "size": len(capped), "excluded_count": len(words) - len(capped), "bands": 1})
        self.assertEqual(list(vt.population_summary_steps([])), [
            {"size": 0, "excluded_count": 0, "bands": 0}])
        for invalid in (None, "not entries", {}, 5):
            with self.subTest(words=invalid), self.assertRaises(ValueError):
                list(vt.population_summary_steps(invalid))
        for invalid in (0, -1, True, 1.5):
            with self.subTest(batch_size=invalid), self.assertRaises(ValueError):
                list(vt.population_summary_steps(words, batch_size=invalid))

    def test_fingerprint_covers_every_target_and_distractor_source(self):
        original = synthetic(100)
        baseline = vt.FrequencyBank(original).fingerprint
        for field, new_value in (("s", "n.橙色"), ("raw", "n.橙色；柑橘"),
                                 ("frq", 100000), ("pos", ["adj."])):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[99][field] = new_value
                self.assertNotEqual(vt.FrequencyBank(changed).fingerprint, baseline)
        changed = copy.deepcopy(original)
        for row in changed:
            row["b"], row["lvl"] = 99, -200
        self.assertEqual(vt.FrequencyBank(changed).fingerprint, baseline)
        with patch.object(vt, "MEASUREMENT_SCHEMA", 4):
            self.assertNotEqual(vt.FrequencyBank(original).fingerprint, baseline)
        with patch.object(vt, "_CONTENT_POLICY", "changed-content-policy"):
            self.assertNotEqual(vt.FrequencyBank(original).fingerprint, baseline)
        with patch.object(vt, "_DISTRACTOR_POOL", 7):
            self.assertNotEqual(vt.FrequencyBank(original).fingerprint, baseline)
        with patch.object(vt, "_ABBREVIATION_KEYS", vt._ABBREVIATION_KEYS | {"unusedkey"}):
            self.assertNotEqual(vt.FrequencyBank(original).fingerprint, baseline)
        changed = copy.deepcopy(original)
        changed[-1]["display_w"] = "changedcaption"
        self.assertNotEqual(vt.FrequencyBank(changed).fingerprint, baseline)

    def test_empty_and_ambiguous_populations_never_invent_options(self):
        empty = vt.FrequencyBank([])
        self.assertEqual(empty.size, 0)
        self.assertIsNone(vt.next_item(empty, vt.new_state(1), [], []))
        result = vt.summarize(empty, [], [])
        self.assertEqual(result["stop_reason"], "exhausted")
        self.assertFalse(result["estimate_available"])
        self.assertEqual((result["estimate"], result["low"], result["high"]), (0, 0, 0))
        words = [{"w": spelling(index), "s": sense, "frq": index + 1, "pos": ["n."]}
                 for index, sense in enumerate(("n.苹果", "n.苹果果实", "n.红色苹果", "n.苹果属植物"))]
        ambiguous = vt.FrequencyBank(words)
        self.assertEqual(ambiguous.size, 4)
        self.assertEqual(ambiguous.testable_size, 0)
        self.assertIsNone(vt.next_item(ambiguous, vt.new_state(2), [], []))
        self.assertEqual(vt.summarize(ambiguous, [], [])["stop_reason"], "exhausted")

    def test_same_pos_band_preference_and_real_other_pos_fallback(self):
        source = bank(3000)
        for seed in range(8):
            record = vt.next_item(source, vt.new_state(seed), [], [])
            ids = [option["item_id"] for option in record["item"]["options"]]
            self.assertTrue(all(source.items[key]["band"] == 1 for key in ids))
            self.assertTrue(all(source.items[key]["pos"] == ["n."] for key in ids))
        words = [{"w": word, "s": sense, "pos": [pos], "frq": index + 1}
                 for index, (word, sense, pos) in enumerate((
                     ("stone", "n.石头", "n."), ("swim", "v.游泳", "v."),
                     ("blue", "adj.蓝色", "adj."), ("quickly", "adv.迅速地", "adv.")))]
        fallback = vt.FrequencyBank(words)
        self.assertEqual(fallback.testable_size, 4)
        item = vt.next_item(fallback, vt.new_state(5), [], [])["item"]
        self.assertEqual(len({slot["item_id"] for slot in item["options"]}), 4)
        for slot in item["options"]:
            self.assertEqual(slot["text"], fallback.items[slot["item_id"]]["sense"])

    def test_key_fragment_and_raw_alternate_sense_conflicts(self):
        words = [{"w": spelling(index), "s": sense, "raw": raw, "frq": index + 1}
                 for index, (sense, raw) in enumerate((
                     ("v.使害怕", ""), ("adj.感到害怕的", ""),
                     ("n.光线", "n.明亮"), ("adj.明亮的", ""),
                     ("n.苹果", ""), ("n.河流", ""), ("n.石头", ""), ("n.火焰", "")))]
        source = vt.FrequencyBank(words)
        self.assertFalse(source._compatible(spelling(0), spelling(1)))
        self.assertFalse(source._compatible(spelling(2), spelling(3)))
        for key, pool in source._distractors.items():
            for index, left in enumerate((key,) + pool):
                for right in ((key,) + pool)[index + 1:]:
                    self.assertTrue(source._compatible(left, right))

    def test_normalized_and_alternate_gloss_conflicts_remain_conservative(self):
        cases = (("v.使害怕", "", "adj.感到害怕的", "", True),
                 ("n.灯光", "n.光明", "adj.光明的", "", True),
                 ("n.岩石", "n.water", "n.江河", "n.water", True),
                 ("n.水", "", "n.火焰", "n.水源", True),
                 ("n.ＡＢＣ苹果", "", "n.abc苹果", "", True),
                 ("n.石头", "", "n.森林", "", False))
        for first, first_raw, second, second_raw, conflict in cases:
            with self.subTest(first=first, second=second):
                left = vt._semantic_profile(first, first_raw)
                right = vt._semantic_profile(second, second_raw)
                self.assertEqual(vt._profiles_conflict(left, right), conflict)
                self.assertEqual(vt._profiles_conflict(right, left), conflict)


class NumericalTests(unittest.TestCase):
    def test_new_state_is_exact_json_and_rejects_noninteger_seed(self):
        self.assertEqual(vt.new_state(4), {"seed": 4, "asked": [], "theta": 0, "se": 2})
        self.assertIsNot(vt.new_state(4)["asked"], vt.new_state(4)["asked"])
        json.dumps(vt.new_state(-5), allow_nan=False)
        for value in (True, 1.0, "7", None, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vt.new_state(value)

    def test_guessing_fixed_3pl_and_saturation_stability(self):
        self.assertEqual(vt.p_known(0, 0), 0.5)
        self.assertEqual(vt.p_correct(0, 0), 0.625)
        self.assertAlmostEqual(vt.p_correct(-1000, 0), 0.25, places=15)
        self.assertEqual(vt.p_correct(1000, 0), 1.0)
        self.assertEqual(vt.p_correct(1e308, -1e308), 1.0)
        self.assertEqual(vt.fisher_information(1e308, -1e308), 0.0)
        for theta in (-5.0, -2.0, 0.0, 2.0, 7.0):
            q = vt.p_known(theta, 0.3)
            p = 0.25 + 0.75 * q
            derivative = 1.4 * 0.75 * q * (1 - q)
            reference = derivative ** 2 / (p * (1 - p))
            self.assertAlmostEqual(vt.fisher_information(theta, 0.3), reference, places=12)
        for bad in (True, None, "1", float("inf"), float("nan")):
            for function in (vt.p_known, vt.p_correct, vt.fisher_information):
                with self.subTest(value=bad, function=function.__name__), self.assertRaises(ValueError):
                    function(bad, 0)

    def test_posterior_matches_independent_fixed_3pl_reference(self):
        source = bank(1000)
        records = fixed_records(source, 40, 300)
        responses = ([1, -1, 1, 0, 1] * 8)
        grid, weights, theta, se = independent_posterior(records, responses)
        actual_grid, actual_weights = vt.posterior(source, records, responses)
        self.assertEqual(tuple(grid), actual_grid)
        for left, right in zip(weights, actual_weights):
            self.assertAlmostEqual(left, right, places=13)
        result = vt.summarize(source, records, responses)
        self.assertAlmostEqual(result["theta"], theta, places=12)
        self.assertAlmostEqual(result["se"], se, places=12)
        self.assertEqual(result["theta_low"], reference_quantile(grid, weights, 0.025))
        self.assertEqual(result["theta_high"], reference_quantile(grid, weights, 0.975))
        self.assertAlmostEqual(math.fsum(actual_weights), 1.0, places=14)

    def test_wrong_and_unknown_identical_measurement_not_distinct_penalties(self):
        source = bank(3000)
        records = fixed_records(source, 80, 1000)
        wrong = vt.summarize(source, records, [0] * 80)
        unknown = vt.summarize(source, records, [-1] * 80)
        for key in ("theta", "se", "estimate", "low", "high", "boundary",
                    "stop_reason", "estimate_available", "provisional"):
            self.assertEqual(wrong[key], unknown[key], key)
        self.assertEqual(wrong["dontknow"], 0)
        self.assertEqual(unknown["dontknow"], 80)
        self.assertEqual(wrong["boundary"], "all_incorrect")
        self.assertEqual(wrong["correct_count"], 0)
        self.assertTrue(wrong["provisional"])
        for part in unknown["bands"]:
            self.assertEqual(part["unknown"], part["answered"])

    def test_boundary_cases_are_finite_and_explicit(self):
        source = bank(1000)
        records = fixed_records(source, 80)
        for answer, boundary in ((1, "all_correct"), (0, "all_incorrect"), (-1, "all_incorrect")):
            with self.subTest(answer=answer):
                result = vt.summarize(source, records, [answer] * 80)
                self.assertEqual(result["boundary"], boundary)
                self.assertTrue(result["provisional"])
                self.assertGreater(result["se"], 0)
                self.assertEqual(result["stop_reason"], "max_items")
                json.dumps(result, allow_nan=False)
                for key in ("theta", "se", "estimate", "low", "high"):
                    self.assertTrue(math.isfinite(result[key]))
                self.assertGreater(result["high"], result["low"])
                self.assertGreater(result["low"], 0)
                self.assertLess(result["high"], source.size)

    def test_monotone_evidence_without_modified_eap(self):
        source = bank(1000)
        records = fixed_records(source, 40, 500)
        previous_theta = previous_estimate = -float("inf")
        for successes in range(41):
            result = vt.summarize(source, records, [1] * successes + [0] * (40 - successes))
            self.assertGreater(result["theta"], previous_theta)
            self.assertGreater(result["estimate"], previous_estimate)
            previous_theta, previous_estimate = result["theta"], result["estimate"]

    def test_band_counts_exact_population_integral_and_equal_tail_intervals(self):
        source = bank(2053)
        records = [record_for(source, list(source.items)[index], "survey")
                   for index in (0, 500, 1000, 1050, 2000, 2001)]
        responses = [1, 1, 0, -1, 1, 0]
        grid, weights, _, _ = independent_posterior(records, responses)
        totals = [0.0] * len(grid)
        result = vt.summarize(source, records, responses)
        for info, actual in zip(source.bands, result["bands"]):
            curve = []
            for index, theta in enumerate(grid):
                value = math.fsum(1.0 / (1.0 + math.exp(-1.4 *
                                      (theta - math.log((rank + 100) / 1000.0))))
                                  for rank in range(info["start"], info["end"] + 1))
                curve.append(value)
                totals[index] += value
                self.assertLess(abs(value - source._population[info["id"]][index]), 1e-8)
            expected = math.fsum(value * weight for value, weight in zip(curve, weights))
            self.assertAlmostEqual(actual["estimate"], expected, places=9)
            self.assertAlmostEqual(actual["low"], reference_quantile(curve, weights, .025), places=9)
            self.assertAlmostEqual(actual["high"], reference_quantile(curve, weights, .975), places=9)
            self.assertAlmostEqual(actual["p_known"], actual["estimate"] / info["size"], places=14)
        self.assertAlmostEqual(result["estimate"], math.fsum(x * w for x, w in zip(totals, weights)), places=9)
        self.assertAlmostEqual(result["low"], reference_quantile(totals, weights, .025), places=9)
        self.assertAlmostEqual(result["high"], reference_quantile(totals, weights, .975), places=9)
        self.assertEqual(result["coverage"], 3)
        self.assertEqual(result["survey_coverage"], 3)
        self.assertEqual(result["coverage_target"], 3)
        self.assertEqual([part["answered"] for part in result["bands"]], [2, 2, 2])
        self.assertEqual([part["correct"] for part in result["bands"]], [2, 0, 1])
        self.assertEqual([part["unknown"] for part in result["bands"]], [0, 1, 0])
        self.assertFalse(result["estimate_available"], "coverage alone is not 40 answers")
        self.assertEqual(result["unit"], "frequency_ranked_entries")
        self.assertEqual(result["interval_level"], .95)

    def test_invalid_inputs_raise_valueerror_not_nan(self):
        source = bank(50)
        record = fixed_records(source, 1)[0]
        for value in (True, False, 1.0, "1", 2, -2, float("nan"), float("inf"), None):
            with self.subTest(response=value), self.assertRaises(ValueError):
                vt.summarize(source, [record], [value])
        for name, value in (("a", float("nan")), ("b", float("inf")), ("c", 0), ("a", True)):
            changed = copy.deepcopy(record)
            changed["irt"][name] = value
            with self.subTest(parameter=name), self.assertRaises(ValueError):
                vt.summarize(source, [changed], [1])
        for records, responses in (([], [1]), ([record] * 2, [1, 0]),
                                   ([record] * 81, [1] * 81), ("bad", []), ([], "bad")):
            with self.assertRaises(ValueError):
                vt.summarize(source, records, responses)
        state = vt.new_state(1)
        with self.assertRaises(ValueError):
            vt.next_item(source, state, [record], [])


class SelectionTests(unittest.TestCase):
    def test_ordered_survey_then_two_per_band_before_free_adaptation(self):
        source = bank(20000)
        state, records, responses = vt.new_state(99), [], []
        for index in range(20):
            record = append_draw(source, state, records, responses, (1, 0, -1)[index % 3])
            self.assertEqual(record["band"], index + 1)
            self.assertEqual(record["phase"], "survey")
        for _ in range(20):
            before = Counter(record["band"] for record in records)
            record = append_draw(source, state, records, responses, 1)
            self.assertIsNotNone(record)
            self.assertEqual(record["phase"], "adaptive")
            self.assertEqual(before[record["band"]], 1, "third visit before every band has two")
        self.assertEqual(set(Counter(record["band"] for record in records).values()), {2})
        self.assertTrue(vt.summarize(source, records, responses)["estimate_available"])

    def test_expected_fisher_layer_choice_over_remaining_uniform_targets(self):
        source = bank(3000)
        state, records, responses = vt.new_state(19), [], []
        for response in (1, 1, 0):
            append_draw(source, state, records, responses, response)
        grid, weights = vt.posterior(source, records, responses)
        asked = set(state["asked"])
        scores = {}
        for band_id in (1, 2, 3):
            ranks = [source.items[key]["rank"] for key in source._testable_by_band[band_id]
                     if key not in asked]
            expectations = []
            for theta, weight in zip(grid, weights):
                information = []
                for rank in ranks:
                    b = math.log((rank + 100) / 1000.0)
                    q = 1 / (1 + math.exp(-1.4 * (theta - b)))
                    information.append(1.4 ** 2 * .75 * q ** 2 * (1 - q) / (.25 + .75 * q))
                expectations.append(weight * math.fsum(information) / len(ranks))
            scores[band_id] = math.fsum(expectations)
            self.assertAlmostEqual(vt._expected_information(source, band_id, weights, records),
                                   scores[band_id], places=12)
        expected = max(scores, key=lambda band_id: (scores[band_id], -band_id))
        chosen = vt.next_item(source, state, records, responses)
        self.assertEqual(chosen["band"], expected)
        wrong_hint = copy.deepcopy(state)
        wrong_hint.update(theta=7, se=0.001)
        self.assertEqual(vt.next_item(source, wrong_hint, records, responses), chosen)

    def test_uniform_within_band_not_information_maximum_or_easy_edge(self):
        source = bank(1000)
        ranks = [vt.next_item(source, vt.new_state(seed), [], [])["rank"] for seed in range(400)]
        self.assertGreater(len(set(ranks)), 270)
        self.assertLess(min(ranks), 70)
        self.assertGreater(max(ranks), 930)
        deciles = Counter((rank - 1) // 100 for rank in ranks)
        self.assertEqual(len(deciles), 10)
        self.assertTrue(all(10 <= count <= 75 for count in deciles.values()), deciles)

    def test_seed_reproducibility_no_target_repeat_and_no_mutation(self):
        source = bank(1000)
        first = attempt(source, lambda n: (1, 0, 1)[n % 3], 45)
        second = attempt(source, lambda n: (1, 0, 1)[n % 3], 45)
        self.assertEqual(first, second)
        self.assertEqual(len({record["key"] for record in first[1]}), len(first[1]))
        for record in first[1]:
            options = record["item"]["options"]
            self.assertEqual([option["key"] for option in options], list("ABCD"))
            self.assertEqual(len({option["item_id"] for option in options}), 4)
            self.assertEqual(len({option["text"] for option in options}), 4)
            self.assertEqual(sum(option["item_id"] == record["key"] for option in options), 1)
        state, records, responses = vt.new_state(78), [], []
        snapshot = copy.deepcopy((state, records, responses, source.items, source.bands))
        rng_state = random.getstate()
        vt.next_item(source, state, records, responses)
        vt.summarize(source, records, responses)
        self.assertEqual((state, records, responses, source.items, source.bands), snapshot)
        self.assertEqual(random.getstate(), rng_state)

    def test_unknown_and_wrong_produce_identical_next_question(self):
        source = bank(3000)
        state, records, responses = vt.new_state(31), [], []
        for _ in range(9):
            append_draw(source, state, records, responses, -1)
        wrong = [0] * len(responses)
        self.assertEqual(vt.next_item(source, state, records, responses),
                         vt.next_item(source, state, records, wrong))

    def test_precision_stop_requires_minimum_and_coverage(self):
        source = bank(1000)
        records = fixed_records(source, 40, 400)
        responses = ([1, 1, 0] * 14)[:40]
        result = vt.summarize(source, records, responses)
        self.assertLessEqual(result["se"], .30)
        self.assertEqual(result["stop_reason"], "precision")
        self.assertTrue(result["estimate_available"])
        state = vt.new_state(5)
        state["asked"] = [record["key"] for record in records]
        self.assertIsNone(vt.next_item(source, state, records, responses))
        early = vt.summarize(source, records[:39], responses[:39])
        self.assertIsNone(early["stop_reason"])
        self.assertFalse(early["estimate_available"])
        self.assertTrue(early["provisional"])

    def test_eighty_item_hard_stop_and_boundary_flag(self):
        source = bank(20000)
        _, records, responses, result = attempt(source, lambda _: 1, 29)
        self.assertEqual(len(records), 80)
        self.assertEqual(len(responses), 80)
        self.assertEqual(result["stop_reason"], "max_items")
        self.assertEqual(result["boundary"], "all_correct")
        self.assertTrue(result["provisional"])
        self.assertEqual(result["coverage"], 20)

    def test_small_bank_exhaustion_pending_item_and_unfillable_band(self):
        source = bank(4)
        state, records, responses = vt.new_state(51), [], []
        for _ in range(3):
            self.assertIsNotNone(append_draw(source, state, records, responses, 0))
        last = vt.next_item(source, state, records, responses)
        records.append(last)
        state["asked"].append(last["key"])
        self.assertIsNone(vt.summarize(source, records, responses)["stop_reason"])
        responses.append(-1)
        result = vt.summarize(source, records, responses)
        self.assertEqual(result["stop_reason"], "exhausted")
        self.assertFalse(result["estimate_available"])
        self.assertIsNone(vt.next_item(source, state, records, responses))
        _, _, _, partial = attempt(bank(1001), lambda _: 0, 8)
        self.assertEqual(partial["answered"], 80)
        self.assertEqual(partial["coverage_target"], 2)
        self.assertEqual(partial["coverage"], 1)
        self.assertFalse(partial["estimate_available"], "one-entry last band cannot count as two")
        _, _, _, too_small = attempt(bank(39), lambda _: 1, 8)
        self.assertEqual(too_small["answered"], 39)
        self.assertEqual(too_small["stop_reason"], "exhausted")
        self.assertFalse(too_small["estimate_available"])

    def test_cached_hot_path_reuses_precomputed_senses_and_curves(self):
        source = bank(20000)
        with patch.object(vt, "_semantic_profile", side_effect=AssertionError("rescanned senses")), \
             patch.object(source, "_build_distractors", side_effect=AssertionError("rebuilt options")), \
             patch.object(vt, "_population_curve", side_effect=AssertionError("rebuilt population")), \
             patch.object(vt, "_information_curve", side_effect=AssertionError("rebuilt band information")):
            started = time.perf_counter()
            _, records, _, result = attempt(source, lambda _: 1, 112)
            elapsed = time.perf_counter() - started
        self.assertEqual(len(records), 80)
        self.assertEqual(result["stop_reason"], "max_items")
        # Timings are diagnostics only: cache-use assertions above are stable
        # structural regression checks, independent of machine load/speed.
        print("PERF synthetic20k: build=%.3fs; full80=%.3fs" % (_BUILD_TIMES[20000], elapsed))


class SessionValidationTests(unittest.TestCase):
    def test_pending_and_feedback_snapshots_and_extensions_no_ttl(self):
        source = bank(3000)
        self.assertFalse(vt.validate_session(None, source))
        self.assertFalse(vt.validate_session({}, source))
        for answered in (False, True):
            session = session_fixture(source, answered_last=answered)
            session["future_extension"] = {"version": 19, "tags": ["keep", "me"]}
            session["state"]["extra"] = [1, 2, 3]
            session["items"][0]["item"]["options"][0]["annotation"] = "keep"
            snapshot = copy.deepcopy(session)
            self.assertTrue(vt.validate_session(session, source))
            self.assertEqual(session, snapshot)
            self.assertTrue(vt.validate_session(json.loads(json.dumps(session)), source))
        # started_at=1 is decades old; expiration belongs to UI, not engine.
        self.assertTrue(vt.validate_session(session_fixture(source), source))

    def test_tamper_rejected_every_identity_numeric_option_and_response_axis(self):
        source = bank(3000)
        original = session_fixture(source)
        other_key = next(key for key in source.items if key not in original["state"]["asked"])
        corruptions = [
            (("schema",), 1), (("schema",), True), (("algo",), "bayes-old"),
            (("bank_id",), "different"), (("id",), ""), (("id",), float("nan")),
            (("started_at",), float("nan")), (("started_at",), float("inf")),
            (("started_at",), True), (("state", "seed"), True), (("state", "seed"), 1.0),
            (("state", "theta"), float("nan")), (("state", "se"), -1),
            (("state", "asked", 0), other_key), (("state", "asked"), []),
            (("i",), original["i"] - 1), (("i",), True),
            (("items", 0, "key"), other_key), (("items", 0, "rank"), 0),
            (("items", 0, "rank"), True), (("items", 0, "band"), 2),
            (("items", 0, "phase"), "adaptive"), (("items", 3, "phase"), "survey"),
            (("items", 0, "irt", "a"), 1), (("items", 0, "irt", "b"), float("nan")),
            (("items", 0, "irt", "c"), 0), (("items", 0, "item", "item_id"), other_key),
            (("items", 0, "item", "word"), "tampered"),
            (("items", 0, "item", "correct_index"), True),
            (("items", 0, "item", "correct_index"), 4),
            (("items", 0, "item", "correct_key"), "Z"),
            (("items", 0, "item", "options", 0, "key"), "X"),
            (("items", 0, "item", "options", 0, "text"), "伪造释义"),
            (("items", 0, "item", "options", 0, "item_id"), "not-a-bank-key"),
            (("resp", 0), True), (("resp", 0), 1.0), (("resp", 0), "1"),
            (("resp", 0), 2), (("resp", 0), float("nan")),
        ]
        for path, value in corruptions:
            with self.subTest(path=path, value=value):
                corrupted = copy.deepcopy(original)
                set_path(corrupted, path, value)
                snapshot = copy.deepcopy(corrupted)
                self.assertFalse(vt.validate_session(corrupted, source))
                # NaN cannot be compared by equality; a stable repr confirms
                # even invalid inputs were not normalized or edited in place.
                self.assertEqual(repr(corrupted), repr(snapshot))
        duplicate = copy.deepcopy(original)
        duplicate["state"]["asked"][1] = duplicate["state"]["asked"][0]
        self.assertFalse(vt.validate_session(duplicate, source))
        duplicate = copy.deepcopy(original)
        options = duplicate["items"][0]["item"]["options"]
        options[1] = dict(options[0], key="B")
        self.assertFalse(vt.validate_session(duplicate, source))
        extra_responses = copy.deepcopy(original)
        extra_responses["resp"] += [0, 0]
        self.assertFalse(vt.validate_session(extra_responses, source))
        excessive = copy.deepcopy(original)
        excessive["items"] = excessive["items"] * 17
        excessive["i"] = len(excessive["items"]) - 1
        excessive["resp"] = [0] * excessive["i"]
        self.assertFalse(vt.validate_session(excessive, source))

    def test_swapped_correct_slot_and_exact_parameter_tamper(self):
        source = bank(3000)
        session = session_fixture(source)
        changed = copy.deepcopy(session)
        item = changed["items"][0]["item"]
        item["correct_index"] = (item["correct_index"] + 1) % 4
        item["correct_key"] = "ABCD"[item["correct_index"]]
        self.assertFalse(vt.validate_session(changed, source))
        changed = copy.deepcopy(session)
        changed["items"][0]["irt"]["b"] += 1e-12
        self.assertFalse(vt.validate_session(changed, source))
        changed = copy.deepcopy(session)
        changed["items"][0]["item"]["options"].reverse()
        self.assertFalse(vt.validate_session(changed, source))

    def test_sense_change_prevents_silent_resume_even_unasked_source(self):
        source = bank(100)
        session = session_fixture(source)
        changed_rows = synthetic(100)
        changed_rows[-1]["s"] = "n.橙子"
        changed_bank = vt.FrequencyBank(changed_rows)
        self.assertNotEqual(source.fingerprint, changed_bank.fingerprint)
        self.assertFalse(vt.validate_session(session, changed_bank))


class RealBankSmokeTests(unittest.TestCase):
    def test_existing_bank_is_read_only_and_measurable(self):
        path = ROOT / "data" / "bank.json"
        if not path.is_file():
            self.skipTest("optional real dictionary is absent")
        before = path.read_bytes()
        digest = hashlib.sha256(before).hexdigest()
        words = json.loads(before.decode("utf-8"))
        started = time.perf_counter()
        source = vt.FrequencyBank(words)
        build_elapsed = time.perf_counter() - started
        self.assertGreater(source.size, 1000)
        self.assertLessEqual(source.size, 20000)
        self.assertGreaterEqual(source.testable_size, 40)
        self.assertEqual(len(source.bands), (source.size + 999) // 1000)
        state, records, responses = vt.new_state(2026), [], []
        for index in range(min(2 * len(source.bands), 40)):
            record = append_draw(source, state, records, responses, (1, 0, 1)[index % 3])
            self.assertIsNotNone(record)
            item = record["item"]
            self.assertEqual(item["options"][item["correct_index"]]["item_id"], record["key"])
        result = vt.summarize(source, records, responses)
        self.assertEqual(result["coverage"], len(source.bands))
        self.assertTrue(result["estimate_available"])
        session = {"schema": 2, "algo": vt.ALGORITHM, "id": "read-only-smoke", "started_at": 0,
                   "bank_id": source.fingerprint, "state": state, "items": records,
                   "resp": responses, "i": len(records) - 1}
        self.assertTrue(vt.validate_session(session, source))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        json.dumps(result, ensure_ascii=True, allow_nan=False)
        print("SMOKE real bank: size=%d testable=%d bands=%d excluded=%d build=%.3fs SHA256 unchanged" %
              (source.size, source.testable_size, len(source.bands), source.excluded_count, build_elapsed))


if __name__ == "__main__":
    unittest.main(verbosity=2)
