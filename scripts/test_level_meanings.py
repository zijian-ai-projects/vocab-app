# -*- coding: utf-8 -*-
"""Read-only integrity tests for data/level_meanings.json."""
from __future__ import print_function

import hashlib
import io
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

import build_level_meanings as builder
import level_meanings

CJK_RE = re.compile(r"[\u3400-\u9fff]")
BAD_RE = re.compile(r"(?:俚语|粗俗|人名|姓氏|\[医\]|\[计\]|\[法\]|（俚）)")


def read_json(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def digest(path):
    with open(path, "rb") as stream:
        payload = stream.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


class LevelMeaningDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_json(builder.OUT_PATH)
        cls.books = read_json(builder.BOOKS_PATH)
        cls.phrase_books = (read_json(builder.PHRASE_BOOKS_PATH)
                            if os.path.isfile(builder.PHRASE_BOOKS_PATH) else {})
        cls.bank = {row["w"]: row for row in read_json(builder.BANK_PATH)}
        if os.path.isfile(builder.PHRASES_PATH):
            cls.bank.update({row["w"]: row for row in read_json(builder.PHRASES_PATH)})

    def test_schema_and_runtime_loader(self):
        self.assertEqual(self.data["schema"], 1)
        self.assertEqual(self.data["rule_version"], builder.RULE_VERSION)
        loaded = level_meanings.load(builder.OUT_PATH)
        for stage in builder.STAGES:
            self.assertEqual(set(loaded[stage]), set(self.data["levels"][stage]))
            self.assertTrue(all(value.get("display_s") for value in loaded[stage].values()))

    def test_exact_school_membership_coverage(self):
        for stage in builder.STAGES:
            expected, book_ids = builder.ordered_stage_words(
                self.books, stage, self.phrase_books)
            actual = self.data["levels"][stage]
            self.assertEqual(set(expected), set(actual), stage)
            self.assertEqual(len(expected), len(actual), stage)
            self.assertEqual(self.data["stats"][stage]["books"], len(book_ids))
            self.assertTrue(set(actual) <= set(self.bank), stage)
            self.assertEqual(self.data["stats"][stage]["members"], len(expected))
            self.assertEqual(self.data["stats"][stage]["meanings"], len(expected))

    def test_meanings_are_short_real_chinese(self):
        for stage, maximum, groups in (("primary", 32, 1), ("middleschool", 58, 2)):
            for word, row in self.data["levels"][stage].items():
                text = row.get("meaning")
                self.assertIsInstance(text, str, (stage, word))
                self.assertTrue(text.strip() and CJK_RE.search(text), (stage, word, text))
                self.assertLessEqual(len(text), maximum, (stage, word, text))
                self.assertLessEqual(text.count("；") + 1, groups, (stage, word, text))
                self.assertEqual(text.count("（"), text.count("）"), (stage, word, text))
                self.assertEqual(text.count("("), text.count(")"), (stage, word, text))
                self.assertIsNone(BAD_RE.search(text), (stage, word, text))

    def test_every_entry_has_hashed_provenance(self):
        sources = self.data["sources"]
        self.assertTrue(sources)
        for source_id, record in sources.items():
            self.assertEqual(source_id, record["path"])
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")
            path = os.path.join(builder.ROOT, record["path"].replace("/", os.sep))
            self.assertTrue(os.path.isfile(path), source_id)
            self.assertEqual(digest(path), record["sha256"], source_id)
        for stage in builder.STAGES:
            for word, row in self.data["levels"][stage].items():
                provenance = row.get("provenance")
                self.assertIsInstance(provenance, dict, (stage, word))
                self.assertIn(provenance.get("source"), sources, (stage, word, provenance))
                for source in provenance.get("sources", [provenance.get("source")]):
                    self.assertIn(source, sources, (stage, word, source))
                self.assertNotEqual(provenance.get("rule"), "missing_real_meaning")

    def test_shipped_school_gloss_snapshot(self):
        self.assertEqual(os.path.dirname(builder.GLOSS), builder.DATA)
        index = read_json(os.path.join(builder.GLOSS, "source-index.json"))
        self.assertEqual(index["classification"], "community_compilation")
        self.assertEqual(len(index["files"]), 49)
        for record in index["files"]:
            self.assertRegex(record["original_raw_sha256"], r"^[0-9a-f]{64}$")
            snapshot = record["snapshot"]
            path = os.path.join(builder.ROOT, snapshot.replace("/", os.sep))
            self.assertEqual(os.path.dirname(path), builder.GLOSS)
            self.assertEqual(self.data["sources"][snapshot]["sha256"], digest(path))
        self.assertFalse(any(source.startswith("build/") for source in self.data["sources"]))

    def test_source_hash_ignores_checkout_newlines(self):
        from unittest.mock import patch
        results = []
        for payload in (b'{\n"word": "example"\n}\n', b'{\r\n"word": "example"\r\n}\r\n'):
            with patch("builtins.open", return_value=io.BytesIO(payload)):
                results.append(builder.sha256("fixture.json"))
        self.assertEqual(results[0], results[1])

    def test_reviewed_classroom_polysemy(self):
        checks = {
            "primary": {
                "board": ("板", "董事会"), "sick": ("病", "厌恶"),
                "open": ("开", "公开"), "subject": ("科", "主题"),
                "matter": ("事", "物质"), "practice": ("练习", "实践"),
            },
            "middleschool": {
                "term": ("学期", "术语"), "present": ("礼物", "现在"),
                "plant": ("植物", "工厂"), "letter": ("信", "标注"),
                "board": ("板", "董事会"), "sick": ("病", "厌恶"),
                "open": ("开", "公开"), "subject": ("科", "隶属"),
                "mind": ("介意", "苦恼"), "club": ("俱乐部", "棒打"),
                "paper": ("纸", "墙纸"), "even": ("甚至", "偶数"),
            },
        }
        for stage, words in checks.items():
            for word, (expected, rejected) in words.items():
                row = self.data["levels"][stage][word]
                self.assertIn(expected, row["meaning"], (stage, word))
                self.assertNotIn(rejected, row["meaning"], (stage, word))
                self.assertEqual(row["provenance"]["rule"], "verified_preferred_fragment")
        for word, second in {"present": "出席", "plant": "栽种", "letter": "字母", "right": "右边"}.items():
            row = self.data["levels"]["middleschool"][word]
            self.assertIn(second, row["meaning"], word)
            self.assertTrue(row["provenance"].get("secondary_selector"), word)

    def test_source_fragments_are_recoverable(self):
        source_rows = {}
        for source in self.data["sources"]:
            path = os.path.join(builder.ROOT, source.replace("/", os.sep))
            data = read_json(path)
            if isinstance(data, list):
                source_rows[source] = {row["w"]: row for row in data}
            elif source.startswith("data/school_gloss/"):
                source_rows[source] = data
        for stage in builder.STAGES:
            for word, row in self.data["levels"][stage].items():
                provenance = row["provenance"]
                originals = []
                for source in provenance.get("sources", [provenance["source"]]):
                    raw = source_rows[source].get(word, {})
                    for field in ("s", "raw", "tr"):
                        if raw.get(field):
                            originals.extend(builder.candidates(raw[field], source))
                emitted = builder.candidates(row["meaning"], "output")
                self.assertTrue(emitted, (stage, word, row))
                for item in emitted:
                    literal_review = provenance["rule"] == "verified_legacy_casefold_fragment"
                    self.assertTrue(any(
                        item["sense"] == original["sense"] or
                        (literal_review and item["sense"] in original["sense"])
                        for original in originals), (stage, word, item, provenance))

    def test_pos_and_parenthetical_parsing(self):
        samples = builder.candidates("adj.流行音乐的；n.流行音乐", "fixture")
        self.assertEqual([(row["pos"], row["sense"]) for row in samples],
                         [("adj", "流行音乐的"), ("n", "流行音乐")])
        samples = builder.candidates("n.(May)五月青春vt.愿意", "fixture")
        self.assertEqual(samples[0]["pos"], "n")
        self.assertEqual(samples[-1]["pos"], "vt")
        self.assertEqual(builder.split_senses("甲（乙、丙）；丁"), ["甲（乙、丙）", "丁"])

    def test_ambiguous_school_senses(self):
        primary = self.data["levels"]["primary"]
        expected = {
            "ruler": "尺", "good": "好", "bear": "熊", "bank": "银行",
            "class": "班", "book": "书", "can": "能", "will": "将",
        }
        for word, fragment in expected.items():
            if word in primary:
                self.assertIn(fragment, primary[word]["meaning"], (word, primary[word]))
        case_pairs = (
            ("march", "行军", "March", "三月"),
            ("may", "可", "May", "五月"),
            ("miss", "想念", "Miss", "小姐"),
            ("it", "它", "IT", "信息技术"),
            ("china", "瓷", "China", "中国"),
            ("us", "我们", "US", "美国"),
        )
        legacy = {"china": "中国", "march": "三月", "may": "五月", "miss": "小姐"}
        for word, fragment in legacy.items():
            if word in primary and builder.CASEFOLD_CONTEXT[word][0] not in self.bank:
                self.assertIn(fragment, primary[word]["meaning"], (word, primary[word]))
                self.assertEqual(primary[word]["provenance"]["rule"],
                                 "verified_legacy_casefold_fragment")
        for stage in builder.STAGES:
            mapping = self.data["levels"][stage]
            if "can" in mapping:
                self.assertTrue(any(fragment in mapping["can"]["meaning"]
                                    for fragment in ("能", "可以")), (stage, mapping["can"]))
            for first, first_fragment, second, second_fragment in case_pairs:
                if first in mapping and second in mapping:
                    self.assertIn(first_fragment, mapping[first]["meaning"],
                                  (stage, first, mapping[first]))
                    self.assertIn(second_fragment, mapping[second]["meaning"],
                                  (stage, second, mapping[second]))
        reviews = self.data.get("review_required") or {}
        listed = {item["word"] for rows in reviews.values() for item in rows}
        self.assertTrue({"alice", "matt", "bds"} <= listed)

    def test_levels_are_versions_not_bank_mutations(self):
        primary = self.data["levels"]["primary"]
        middle = self.data["levels"]["middleschool"]
        overlap = set(primary) & set(middle)
        self.assertGreater(len(overlap), 400)
        different = sum(primary[word]["meaning"] != middle[word]["meaning"] for word in overlap)
        self.assertGreater(different, 100)
        different_general_primary = sum(
            primary[word]["meaning"] != (self.bank[word].get("s") or self.bank[word].get("raw") or "")
            for word in primary)
        different_general_middle = sum(
            middle[word]["meaning"] != (self.bank[word].get("s") or self.bank[word].get("raw") or "")
            for word in middle)
        self.assertGreater(different_general_primary, len(primary) // 2)
        self.assertGreater(different_general_middle, len(middle) // 3)
        # The generated layer never adds display fields to the shared bank rows.
        self.assertFalse(any("display_s" in row or "level_s" in row for row in self.bank.values()))

    def test_rebuild_is_byte_identical(self):
        rebuilt = builder.build()
        self.assertEqual(builder.serialized(rebuilt), builder.serialized(self.data))
        with open(builder.OUT_PATH, "rb") as stream:
            self.assertEqual(stream.read(), builder.serialized(rebuilt))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LevelMeaningDataTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("LEVEL_MEANING_DATA tests=%d failures=%d errors=%d" %
          (result.testsRun, len(result.failures), len(result.errors)))
    sys.exit(0 if result.wasSuccessful() else 1)
