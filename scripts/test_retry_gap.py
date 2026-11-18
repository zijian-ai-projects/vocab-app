# -*- coding: utf-8 -*-
"""Pure retry-gap migration tests; AST extraction avoids importing Qt or user data."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import study_queue as queue

TREE = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
NODE = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
            and node.name == "normalize_retry_gap")
NAMESPACE = {"_queue_count": queue._count}
exec(compile(ast.Module(body=[NODE], type_ignores=[]), "retry_gap_subject", "exec"), NAMESPACE)
normalize = NAMESPACE["normalize_retry_gap"]


def fixture(gap=3):
    return {"retry_gap": gap,
            "study_records": {"book": {"cursor": 7, "new_count": 1,
                                        "pending": {"alpha": 6, "ready": 1, "old": 0},
                                        "current": {"kind": "new", "key": "beta"},
                                        "held_current": {"kind": "retry", "key": "held"},
                                        "last_retry": "previous", "extension": {"keep": 1}}},
            "states": {"alpha": {"st": "new", "lv": 0, "seen": 1}},
            "cursors": {"book": 7}, "orders": {"book": {"mode": "seq", "seed": 42}},
            "history": [{"ts": i, "vocab": 1000 + i} for i in range(60)],
            "daily_new_ledger": {"days": {"2026-11-17": ["untouched"]}},
            "extension": {"nested": [1, 2, 3]}}


class RetryGapTests(unittest.TestCase):
    def test_known_three_gap_migrates_future_targets_only(self):
        progress = fixture()
        before = copy.deepcopy(progress)
        record = progress["study_records"]["book"]
        pending = record["pending"]
        self.assertIs(normalize(progress), progress)
        self.assertEqual(progress["retry_gap"], 4)
        self.assertIs(record["pending"], pending)
        self.assertEqual(pending, {"alpha": 7, "ready": 1, "old": 0})
        for key in ("cursor", "new_count", "current", "held_current", "last_retry", "extension"):
            self.assertEqual(record[key], before["study_records"]["book"][key])
        for key in ("states", "cursors", "orders", "history", "daily_new_ledger", "extension"):
            self.assertEqual(progress[key], before[key])

    def test_migration_preserves_unknown_and_malformed_records(self):
        progress = fixture()
        progress["study_records"]["unknown"] = {"new_count": 0, "pending": {"x": 9}, "extension": True}
        progress["study_records"]["broken"] = None
        normalize(progress)
        self.assertEqual(progress["study_records"]["unknown"]["pending"], {"x": 10})
        self.assertEqual(progress["study_records"]["broken"], None)

    def test_malformed_counts_and_targets_are_not_inferred(self):
        progress = fixture()
        malformed = [None, True, False, "6", "bad", -1, 3.5, [], {}, 9007199254740991]
        pending = {"bad%s" % i: value for i, value in enumerate(malformed)}
        progress["study_records"]["book"]["pending"].update(copy.deepcopy(pending))
        for i, value in enumerate(malformed[:-1]):
            progress["study_records"]["bad_count%s" % i] = {"new_count": value, "pending": {"future": 8}}
        before = copy.deepcopy(progress["study_records"])
        normalize(progress)
        migrated = progress["study_records"]["book"]["pending"]
        self.assertEqual({key: migrated[key] for key in pending}, pending)
        for key in before:
            if key.startswith("bad_count"):
                self.assertEqual(progress["study_records"][key], before[key])

    def test_serialized_restart_does_not_apply_migration_twice(self):
        progress = fixture()
        normalize(progress)
        saved = json.loads(json.dumps(progress))
        before = copy.deepcopy(saved)
        normalize(saved)
        self.assertEqual(saved, before)

    def test_existing_four_preserves_deadlines(self):
        progress = fixture(4)
        before = copy.deepcopy(progress)
        normalize(progress)
        self.assertEqual(progress, before)

    def test_missing_invalid_and_unrecognized_gaps_do_not_shift_deadlines(self):
        for gap in (None, "invalid", "3", 3.9, 0, -4, True, 5):
            with self.subTest(gap=gap):
                progress = fixture(gap)
                before = copy.deepcopy(progress["study_records"])
                normalize(progress)
                self.assertEqual(progress["retry_gap"], 4)
                self.assertEqual(progress["study_records"], before)
        progress = fixture()
        progress.pop("retry_gap")
        before = copy.deepcopy(progress["study_records"])
        normalize(progress)
        self.assertEqual(progress["study_records"], before)

    def test_malformed_targets_remain_opaque_through_queue_restart(self):
        malformed = [None, True, False, "5", "bad", -1, 5.5,
                     {"opaque": ["retain"]}, [], 9007199254740992]
        for value in malformed:
            for slot in ("current", "held_current", "policy_held"):
                with self.subTest(target=value, slot=slot):
                    saved = {"kind": "retry", "key": "alpha", "custom": ["keep"]}
                    record = {"new_count": 1, "pending": {"alpha": copy.deepcopy(value)},
                              slot: [saved] if slot == "policy_held" else saved}
                    progress = {"retry_gap": 3, "study_records": {"book": record}}
                    normalize(progress)
                    states = {"alpha": {"st": "new", "lv": 0, "seen": 1}}
                    words = [{"w": key} for key in ("alpha", "fresh")]
                    engine = queue.StudyQueue(words, states, record)
                    self.assertEqual(record["pending"]["alpha"], value)
                    item = engine.next(0)
                    self.assertEqual((item["w"]["w"], item["kind"]), ("fresh", "new"))
                    engine.answer(item, True, 0)
                    states, record = json.loads(json.dumps([states, record]))
                    engine = queue.StudyQueue(words, states, record)
                    self.assertIsNone(engine.next(0))
                    self.assertEqual(record["pending"]["alpha"], value)
                    retained = record.get("policy_held", [])
                    self.assertTrue(any(entry.get("key") == "alpha" and entry.get("custom") == ["keep"]
                                        for entry in retained))

    def test_no_optional_records_are_created(self):
        progress = {"retry_gap": 3, "history": [{"ts": 1, "vocab": 123}], "extension": [1, 2]}
        normalize(progress)
        self.assertNotIn("study_records", progress)
        self.assertEqual(progress, {"retry_gap": 4, "history": [{"ts": 1, "vocab": 123}],
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
