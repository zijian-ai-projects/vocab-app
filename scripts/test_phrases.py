# -*- coding: utf-8 -*-
"""只读词组库/来源校验及纯展示助手测试，不构造Card或访问使用记录。"""
import copy
import json
from pathlib import Path
import random
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
import books
import entries
import study_options
import build_phrases as build

PHRASES = json.loads((ROOT / "data" / "phrases.json").read_text(encoding="utf-8"))
SUPPLEMENT = json.loads((ROOT / "data" / "phrase_books.json").read_text(encoding="utf-8"))["items"]
EXPECTED = {"cet4-phrases": 1652, "cet6-phrases": 1652, "zk-phrases": 773,
            "gk-phrases": 914, "ky-phrases": 1769, "ielts-phrases": 998,
            "toefl-phrases": 951, "gre-phrases": 328}


class PhraseTests(unittest.TestCase):
    def test_library_real_meanings_unique_sorted_no_fake_phonetics(self):
        self.assertEqual(len(PHRASES), 4818)
        keys = [entry["w"] for entry in PHRASES]
        self.assertEqual(keys, sorted(set(keys)))
        for entry in PHRASES:
            self.assertTrue(entries.is_phrase(entry))
            self.assertTrue(re.search(r"[\u4e00-\u9fff]", entry["s"]))
            self.assertEqual(entries.pronunciation(entry), "")
            self.assertNotIn("na.", entry["pos"])
            self.assertNotIn("un.", entry["pos"])
            self.assertFalse(entries.meaning(entry).startswith(("na.", "un.")))

    def test_eight_books_attached_counts_memberships_union_and_source_order(self):
        self.assertEqual({book["id"]: book["count"] for book in SUPPLEMENT}, EXPECTED)
        all_keys = {entry["w"] for entry in PHRASES}
        used = set()
        sources = {book_id: name for book_id, _, _, name in build.SOURCES}
        for book in SUPPLEMENT:
            self.assertEqual(len(book["words"]), len(set(book["words"])))
            self.assertEqual(book["count"], len(book["words"]))
            self.assertTrue(set(book["words"]) <= all_keys)
            self.assertEqual(books.get(book["id"])["type"], "phrase")
            self.assertEqual(books.words(book["id"]), book["words"])
            self.assertIn(book["id"], [item["id"] for item in books.items(book["group"])])
            self.assertTrue(set(book["words"]) <= set(books.GROUPS[book["group"]]["union"]["words"]))
            path = Path(build.SOURCE) / "word" / (sources[book["id"]] + ".txt")
            seen, source_order = set(), []
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                word = build.key(line)
                if word in all_keys and word not in seen:
                    source_order.append(word)
                    seen.add(word)
            self.assertEqual(book["words"], source_order)
            used.update(book["words"])
        self.assertEqual(used, all_keys)
        self.assertEqual(len(books.mains()), 8)
        self.assertEqual(len(books.groups()), 41)
        self.assertEqual(sum(len(group["items"]) for group in books.groups()), 183)

    def test_original_union_prefixes_preserve_old_cursor_positions(self):
        original = json.loads((ROOT / "data" / "books.json").read_text(encoding="utf-8"))
        for main in original["mains"]:
            for group in main["groups"]:
                before = group["union"]["words"]
                self.assertEqual(books.words(group["union"]["id"])[:len(before)], before)

    def test_normalization_and_missing_pos_pronunciation(self):
        self.assertEqual(build.key("  TAKE\tＳＴＨ  Into Account  "), "take sth into account")
        self.assertIsNone(build.make_entry("by chance", "no translation available"))
        self.assertIsNone(build.make_entry("by chance", ""))
        entry = build.make_entry("by chance", "na. 偶然；碰巧")
        self.assertEqual(entry["pos"], [])
        self.assertEqual(entries.meaning(entry), "偶然；碰巧")
        typed = build.make_entry("take into account", "v. 将…考虑在内")
        self.assertEqual(typed["pos"], ["v."])
        self.assertEqual(entries.meaning(typed), "v. 将…考虑在内")
        self.assertEqual(entries.pronunciation({"w": "on the way", "ipa": "fake", "ph_raw": "fake"}), "")
        self.assertEqual(entries.pronunciation({"w": "word", "ipa": "wɜːd"}), "/wɜːd/")
        self.assertEqual(entries.pronunciation({"w": "word", "ipa": "", "ph_raw": ""}), "")
        self.assertEqual(entries.pronunciation({"w": "word", "ipa": " / / ", "ph_raw": ""}), "")
        self.assertEqual(entries.pronunciation({"w": "word", "ipa": "p\\\\:sən", "ph_raw": ""}), "")
        self.assertEqual(entries.pronunciation({"w": "word", "ipa": "\\\\", "ph_raw": " /wɜːd/ "}), "/wɜːd/")
        self.assertEqual(entries.meaning({"w": "an", "s": "art.一", "pos": ["art."]}), "art.一")

    def test_real_word_pos_prefixes_never_duplicate(self):
        bank = json.loads((ROOT / "data" / "bank.json").read_text(encoding="utf-8"))
        tags = {tag for entry in bank for tag in entry.get("pos", [])}
        self.assertIn("art.", tags)
        self.assertIn("abbr.", tags)
        for tag in tags:
            self.assertIsNotNone(entries.POS_RE.match(tag + "释义"), tag)
        for entry in bank:
            text = entry.get("s", "")
            if text and entries.POS_RE.match(text):
                self.assertEqual(entries.meaning(entry), text, entry["w"])
        ceo = next(entry for entry in bank if entry["w"] == "ceo")
        self.assertEqual(entries.meaning(ceo), "abbr.首席执行官；执行总裁")

    def test_memory_categories_are_real_not_estimated_mastery(self):
        states = {"a": {"st": "mastered", "lv": 10}, "b": {"st": "learning", "lv": 1},
                  "c": {"st": "new", "lv": 0, "seen": 1}, "d": {"st": "known", "lv": 0}}
        before = copy.deepcopy(states)
        self.assertEqual(entries.memory_info("a", states)[:2], ("mastered", 10))
        self.assertEqual(entries.memory_info("b", states)[:2], ("known", 1))
        self.assertEqual(entries.memory_info("c", states, {"c"})[:2], ("unlearned", 0))
        self.assertEqual(entries.memory_info("d", states)[:2], ("known", None))
        self.assertEqual(entries.memory_info("e", states, {"e"})[:2], ("known", None))
        self.assertEqual(entries.memory_info("f", states)[:2], ("unlearned", 0))
        self.assertEqual(states, before)

    def test_real_phrase_options_unique_correct_no_quiz_trap(self):
        pool = study_options.OptionPool(PHRASES)
        for target in PHRASES[::97]:
            result = study_options.make_options(target, pool, random.Random(target["w"]))
            options = result["options"]
            self.assertEqual(len(options), 4)
            self.assertEqual(len(set(options)), 4)
            self.assertEqual(options[result["correct"]], entries.meaning(target))
            self.assertNotIn("没有正确答案", options)
            self.assertNotIn("不认识", options)


if __name__ == "__main__":
    unittest.main(verbosity=2)
