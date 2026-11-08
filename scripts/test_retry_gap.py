# -*- coding: utf-8 -*-
"""纯测试：旧五词 retry 绝对计数迁移至三词；AST 只抽取纯函数，不导入 Qt/资料。"""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import scheduler as sch
import study_queue as queue

TREE = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
NODE = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
            and node.name == "normalize_retry_gap")
NAMESPACE = {"_queue_count": queue._count}
exec(compile(ast.Module(body=[NODE], type_ignores=[]), "retry_gap_subject", "exec"), NAMESPACE)
normalize = NAMESPACE["normalize_retry_gap"]


def fixture(gap=5):
    return {"retry_gap": gap,
            "study_records": {"book": {"cursor": 7, "new_count": 1,
                                       "pending": {"alpha": 6, "ready": 1, "old": 0},
                                       "current": {"kind": "new", "key": "beta"},
                                       "held_current": {"kind": "retry", "key": "held"},
                                       "last_retry": "previous", "extension": {"keep": 1}}},
            "states": {"alpha": {"st": "new", "lv": 0, "seen": 1}},
            "cursors": {"book": 7}, "orders": {"book": {"mode": "seq", "seed": 42}},
            "history": [{"ts": i, "vocab": 1000 + i} for i in range(60)],
            "extension": {"nested": [1, 2, 3]}}


class RetryGapTests(unittest.TestCase):
    def test_old_five_is_three_without_losing_state_or_queue(self):
        progress = fixture()
        before = copy.deepcopy(progress)
        record = progress["study_records"]["book"]
        pending = record["pending"]
        self.assertIs(normalize(progress), progress)
        self.assertEqual(progress["retry_gap"], 3)
        self.assertIs(record["pending"], pending)
        self.assertEqual(pending, {"alpha": 4, "ready": 0, "old": 0})
        for key in ("cursor", "new_count", "current", "held_current", "last_retry", "extension"):
            self.assertEqual(record[key], before["study_records"]["book"][key])
        for key in ("states", "cursors", "orders", "history", "extension"):
            self.assertEqual(progress[key], before[key])

    def test_migrated_retry_waits_exactly_three_other_new_answers(self):
        words = [{"w": key, "s": key} for key in ("alpha", "beta", "gamma", "delta", "epsilon")]
        state = sch.new_state()
        state["seen"] = 1
        states = {"alpha": state}
        record = {"cursor": 1, "new_count": 1, "pending": {"alpha": 6}}
        progress = {"retry_gap": 5, "study_records": {"book": record}}
        normalize(progress)
        self.assertEqual(record["pending"]["alpha"], 4)
        engine = queue.StudyQueue(words, states, record, retry_gap=3)
        for key in ("beta", "gamma", "delta"):
            item = engine.next(now=1700000000)
            self.assertEqual((item["kind"], item["w"]["w"]), ("new", key))
            engine.answer(item, True, now=1700000000)
        self.assertEqual(record["new_count"], 4)
        item = engine.next(now=1700000000)
        self.assertEqual((item["kind"], item["w"]["w"]), ("retry", "alpha"))

    def test_other_books_and_orphan_keys_are_migrated_and_retained(self):
        progress = fixture()
        progress["study_records"]["other"] = {"new_count": 10, "cursor": 99,
                                                "pending": {"second": 15, "orphan": 2},
                                                "extension": {"not_current_book": True}}
        normalize(progress)
        other = progress["study_records"]["other"]
        self.assertEqual(other["pending"], {"second": 13, "orphan": 0})
        self.assertEqual((other["new_count"], other["cursor"]), (10, 99))
        self.assertEqual(other["extension"], {"not_current_book": True})

    def test_ready_retry_stays_ready(self):
        state = sch.new_state()
        state["seen"] = 1
        record = {"cursor": 1, "new_count": 10, "pending": {"alpha": 3}}
        progress = {"retry_gap": 5, "study_records": {"book": record}}
        normalize(progress)
        self.assertEqual(record["pending"]["alpha"], 1)
        engine = queue.StudyQueue([{"w": "alpha"}, {"w": "beta"}], {"alpha": state}, record)
        item = engine.next(now=1700000000)
        self.assertEqual((item["kind"], item["w"]["w"]), ("retry", "alpha"))

    def test_serialized_restart_does_not_apply_migration_twice(self):
        progress = fixture()
        normalize(progress)
        saved = json.loads(json.dumps(progress))
        before = copy.deepcopy(saved)
        normalize(saved)
        self.assertEqual(saved, before)
        self.assertEqual(saved["study_records"]["book"]["pending"]["alpha"], 4)

    def test_existing_three_preserves_all_deadlines(self):
        progress = fixture(3)
        before = copy.deepcopy(progress)
        normalize(progress)
        self.assertEqual(progress, before)

    def test_missing_or_invalid_gap_does_not_shift_deadlines(self):
        for gap in (None, "invalid", 0, -4, True):
            with self.subTest(gap=gap):
                progress = fixture(gap)
                before = copy.deepcopy(progress["study_records"])
                normalize(progress)
                self.assertEqual(progress["retry_gap"], 3)
                self.assertEqual(progress["study_records"], before)
        progress = fixture()
        progress.pop("retry_gap")
        before = copy.deepcopy(progress["study_records"])
        normalize(progress)
        self.assertEqual(progress["study_records"], before)

    def test_string_five_and_queue_count_conversion_are_compatible(self):
        progress = {"retry_gap": "5", "study_records": {"book": {
            "new_count": "1", "pending": {"alpha": "6", "ready": None}, "extension": True}}}
        normalize(progress)
        record = progress["study_records"]["book"]
        self.assertEqual(record["pending"], {"alpha": 4, "ready": 0})
        self.assertEqual(record["new_count"], "1")
        self.assertTrue(record["extension"])

    def test_no_optional_records_are_created(self):
        progress = {"retry_gap": 5, "history": [{"ts": 1, "vocab": 123}], "extension": [1, 2]}
        normalize(progress)
        self.assertNotIn("study_records", progress)
        self.assertEqual(progress, {"retry_gap": 3, "history": [{"ts": 1, "vocab": 123}],
                                    "extension": [1, 2]})

    def test_main_load_progress_calls_pure_normalization(self):
        card = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "Card")
        loader = next(node for node in card.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_load_progress")
        calls = [node for node in ast.walk(loader) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "normalize_retry_gap"]
        self.assertEqual(len(calls), 1)
        self.assertEqual([node.id for node in calls[0].args if isinstance(node, ast.Name)], ["p"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
