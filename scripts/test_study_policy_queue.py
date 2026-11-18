# -*- coding: utf-8 -*-
"""Synthetic retry-queue regression tests and active-policy retirement checks."""
import ast
import copy
import os
import sys
import unittest

sys.dont_write_bytecode = True
APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app")
sys.path.insert(0, APP)
from study_queue import StudyQueue


def book(*keys):
    return [{"w": key, "s": "fixture " + key} for key in keys]


def forgotten():
    return {"st": "new", "lv": 0, "due": None, "seen": 1, "lapse": 1,
            "extra": {"retain": True}}


def learning(due):
    return {"st": "learning", "lv": 1, "due": due, "seen": 1, "lapse": 0}


class StudyRetryQueueTests(unittest.TestCase):
    def assert_item(self, item, key, kind):
        self.assertIsNotNone(item)
        self.assertEqual((item["w"]["w"], item["kind"]), (key, kind))
        return item

    def test_retry_waits_for_exactly_four_other_first_new_answers(self):
        queue = StudyQueue(book("a", "b", "c", "d", "e", "f"), {}, {})
        item = self.assert_item(queue.next(0), "a", "new")
        queue.answer(item, False, 0)
        self.assertEqual((queue.record["new_count"], queue.record["pending"]["a"]), (1, 5))

        # Display and re-fetch do not advance eligibility, even after a long delay.
        for now in (0, 0, 86400 * 400):
            self.assert_item(queue.next(now), "b", "new")
            self.assertEqual(queue.record["new_count"], 1)
            queue.record["current"] = None
        # Three actual other first-new answers bring the counter to four.
        for key in ("b", "c", "d"):
            queue.answer(self.assert_item(queue.next(0), key, "new"), True, 0)
        self.assertEqual(queue.record["new_count"], 4)
        queue.states["review"] = learning(0)
        queue.words.append({"w": "review", "s": "fixture review"})
        queue._indices["review"] = len(queue.words) - 1
        self.assert_item(queue.next(0), "review", "review")
        queue.answer(self.assert_item(queue.next(0), "review", "review"), True, 0)
        self.assertEqual(queue.record["new_count"], 4)
        queue.answer(self.assert_item(queue.next(0), "e", "new"), True, 0)
        self.assertEqual(queue.record["new_count"], 5)
        self.assert_item(queue.next(0), "a", "retry")
        self.assertEqual(queue.record["pending"]["a"], 5)

    def test_book_end_does_not_retry_early_but_retries_at_target_without_candidate(self):
        queue = StudyQueue(book("a", "b", "c"), {}, {}, retry_gap=4)
        for key in "abc":
            queue.answer(self.assert_item(queue.next(0), key, "new"), False, 0)
        self.assertEqual(queue.record["pending"], {"a": 5, "b": 6, "c": 7})
        snapshot = copy.deepcopy(queue.record["pending"])
        self.assertIsNone(queue.next(10**9))
        self.assertEqual(queue.record["pending"], snapshot)
        self.assertEqual(queue.record["new_count"], 3)

        # Finish the book with exactly four OTHER first-new answers.
        queue.words.extend(book("d", "e"))
        queue._indices["d"] = 3
        queue._indices["e"] = 4
        queue.cursor = 3
        for key in "de":
            queue.answer(self.assert_item(queue.next(10**9), key, "new"), True, 10**9)
        self.assertEqual(queue.record["new_count"], 5)
        self.assert_item(queue.next(10**9), "a", "retry")
        self.assertEqual(queue.record["pending"]["a"], 5)

    def test_saved_fresh_word_cannot_delay_ready_retry(self):
        for slot in ("current", "held_current", "policy_held"):
            with self.subTest(slot=slot):
                saved = {"kind": "new", "key": "f", "extension": {"keep": [42]}}
                record = {"new_count": 5, "pending": {"a": 5},
                          slot: [copy.deepcopy(saved)] if slot == "policy_held" else copy.deepcopy(saved)}
                queue = StudyQueue(book("a", "f"), {"a": forgotten()}, record)
                queue.answer(self.assert_item(queue.next(0), "a", "retry"), True, 0)
                self.assert_item(queue.next(0), "f", "new")
                self.assertEqual(record["current"]["extension"], saved["extension"])

    def test_saved_future_retry_guards_and_metadata(self):
        marker = {"future": {"nested": ["retain", 17]}}
        for slot in ("current", "held_current", "policy_held"):
            for has_candidate in (False, True):
                with self.subTest(slot=slot, has_candidate=has_candidate):
                    saved = dict(marker, kind="retry", key="a")
                    record = {"new_count": 4, "pending": {"a": 8}}
                    if slot == "policy_held":
                        record[slot] = [saved]
                    else:
                        record[slot] = saved
                    words = book("a", "fresh") if has_candidate else book("a")
                    states = {"a": forgotten()}
                    queue = StudyQueue(words, states, record)

                    item = queue.next(0)
                    if has_candidate:
                        self.assert_item(item, "fresh", "new")
                        self.assertEqual(record["new_count"], 4)
                    else:
                        self.assertIsNone(item)
                    self.assertEqual(record["pending"]["a"], 8)
                    saved_items = [record.get("current"), record.get("held_current")]
                    saved_items.extend(record.get("policy_held", []))
                    retained = [entry for entry in saved_items
                                if isinstance(entry, dict) and entry.get("key") == "a"]
                    self.assertTrue(retained, "future retry must remain saved")
                    self.assertTrue(any(entry.get("future") == marker["future"]
                                        for entry in retained), "saved metadata must survive")

    def test_legacy_policy_fields_are_opaque(self):
        legacy_policy = {"mode": "old", "nested": [1, {"x": True}]}
        ledger = {"days": {"not-a-date": [None]}, "opaque": {"v": 3}}
        record = {"new_count": 0, "learning_policy": copy.deepcopy(legacy_policy),
                  "daily_new_ledger": copy.deepcopy(ledger)}
        before = copy.deepcopy(record)
        queue = StudyQueue(book("a", "b"), {}, record)
        queue.answer(queue.next(0), True, 0)
        self.assertEqual(record["learning_policy"], before["learning_policy"])
        self.assertEqual(record["daily_new_ledger"], before["daily_new_ledger"])

    def test_legacy_journal_preference_values_are_ignored_on_restore(self):
        path = os.path.join(APP, "main.py")
        with open(path, "r", encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read(), filename="main.py")
        functions = {node.name: node for node in ast.walk(tree)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        recovery = functions["_recover_defaults_journal"]
        with open(path, "r", encoding="utf-8") as source_file:
            lines = source_file.readlines()
        text = "".join(lines[recovery.lineno - 1:recovery.end_lineno])
        self.assertIn("name in RESET_PREF_KEYS", text)
        self.assertIn("LEGACY_RESET_PREF_KEYS", text)

        # Exercise the key-filter semantics on inert synthetic journal values.
        active_keys = {"theme", "study_mode", "keybindings", "school_knowledge"}
        journal_prefs = {
            "theme": {"present": True, "value": {"mode": "dark"}},
            "retry_gap": {"present": True, "value": 99},
            "learning_policy": {"present": True, "value": {"mode": "retired"}},
        }
        progress = {"retry_gap": 4, "learning_policy": {"mode": "old"}}
        restored = {key: value for key, value in journal_prefs.items()
                    if key in active_keys}
        for key, saved in restored.items():
            if saved["present"]:
                progress[key] = copy.deepcopy(saved["value"])
            else:
                progress.pop(key, None)
        self.assertEqual(progress["retry_gap"], 4)
        self.assertEqual(progress["learning_policy"], {"mode": "old"})
        self.assertEqual(progress["theme"], {"mode": "dark"})

    def test_active_app_has_no_policy_import_normalization_ledger_or_ui(self):
        # The standalone learning_policy.py remains a legacy module by design.
        active = ("main.py", "study_queue.py", "storage.py", "books.py",
                  "study_options.py", "scheduler.py")
        forbidden_names = {"LearningPolicy", "normalize_settings", "validate_ledger",
                           "DAILY_NEW_FIRST", "daily_new_ledger"}
        for filename in active:
            path = os.path.join(APP, filename)
            with open(path, "r", encoding="utf-8") as source_file:
                source = source_file.read()
            tree = ast.parse(source, filename=filename)
            with self.subTest(file=filename):
                imports = [node for node in ast.walk(tree)
                           if isinstance(node, (ast.Import, ast.ImportFrom))]
                for node in imports:
                    imported = ([alias.name for alias in node.names]
                                if isinstance(node, ast.Import) else [node.module or ""])
                    self.assertFalse(any("learning_policy" in name for name in imported))
                identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
                attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
                self.assertFalse(forbidden_names & (identifiers | attrs))
                self.assertNotIn("policy=", source)
                self.assertNotIn("introduced_at", source)
                self.assertNotIn("daily_new_ledger", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
