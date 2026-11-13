# -*- coding: utf-8 -*-
"""Pure V1.4.2 history/archival boundaries; no Qt, profile reads or writes.

Run: python -B scripts/test_assessment_history_v142.py
All examples are synthetic in-memory JSON, including legacy snapshots.
"""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import assessment_history as history


def current(**updates):
    row = {"id": "synthetic", "ts": 1805000000, "vocab": 4500,
           "algo": history.ALGORITHM, "unit": history.UNIT,
           "measurement_schema": history.MEASUREMENT_SCHEMA,
           "bank_id": "bank-a", "completed": True,
           "estimate_available": True}
    row.update(updates)
    return row


def legacy():
    return {"id": "old-fixture", "ts": 1700000000, "vocab": 7200,
            "algo": "bayes-v140", "measurement_schema": 2,
            "err": 9.3, "rigor": 102, "lo": 6500, "hi": 7850,
            "future_metadata": {"list": [1, {"keep": "原始值"}]}}


class ScaleTests(unittest.TestCase):
    def test_current_identity_requires_all_three_markers(self):
        self.assertTrue(history.is_current(current()))
        for key in ("algo", "unit", "measurement_schema"):
            row = current()
            row.pop(key)
            self.assertFalse(history.is_current(row), key)
        for row in (None, [], legacy(), current(algo="next-model"),
                    current(unit="word_families"), current(measurement_schema=2)):
            self.assertFalse(history.is_current(row))

    def test_same_scale_includes_bank_unit_algorithm_and_schema(self):
        baseline = history.series_key(current())
        for key, value in (("bank_id", "bank-b"), ("unit", "word_families"),
                           ("algo", "future-cat"), ("measurement_schema", 4)):
            self.assertNotEqual(baseline, history.series_key(current(**{key: value})))
        self.assertEqual(history.series_key({}), ("legacy", "legacy", "legacy", 0))

    def test_partial_or_unavailable_current_results_never_plot(self):
        self.assertTrue(history.plottable(current()))
        for row in (current(completed=False), current(completed=None),
                    current(completed=1), current(estimate_available=False),
                    current(estimate_available=None), current(estimate_available=1)):
            self.assertFalse(history.plottable(row), row)
        for key in ("completed", "estimate_available"):
            row = current()
            row.pop(key)
            self.assertFalse(history.plottable(row))

    def test_old_records_remain_plottable_without_new_markers(self):
        self.assertTrue(history.plottable(legacy()))
        self.assertTrue(history.plottable({"ts": 1, "vocab": 3200}))
        self.assertFalse(history.plottable(dict(legacy(), estimate_available=False)))

    def test_nonfinite_bool_missing_and_huge_values_are_rejected(self):
        for key in ("ts", "vocab"):
            for value in (None, True, False, "100", math.nan, math.inf,
                          -math.inf, 10 ** 1000):
                self.assertFalse(history.plottable(current(**{key: value})), (key, value))
            row = current()
            row.pop(key)
            self.assertFalse(history.plottable(row))
        for row in (None, [], "bad"):
            self.assertFalse(history.plottable(row))

    def test_current_trend_filters_old_other_bank_and_incomplete(self):
        first = current(id="first", ts=1)
        last = current(id="last", ts=7, vocab=5500)
        rows = [legacy(), first, current(bank_id="bank-b"),
                current(completed=False), current(estimate_available=False),
                current(unit="word_families"), last]
        before = copy.deepcopy(rows)
        result = history.current_trend(rows, "bank-a")
        self.assertEqual(result, [first, last])
        self.assertIs(result[0], first)
        self.assertIs(result[1], last)
        self.assertEqual(rows, before)

    def test_comparable_keeps_only_matching_completed_new_scale(self):
        reference = current(id="report")
        good = current(id="previous")
        rows = [legacy(), current(bank_id="other"), current(completed=False),
                current(unit="word_families"), current(measurement_schema=2),
                current(estimate_available=False), good]
        self.assertEqual(history.comparable(rows, reference), [good])
        self.assertIs(history.comparable(rows, reference)[0], good)

    def test_legacy_comparison_does_not_group_all_old_algorithms_together(self):
        old = legacy()
        another = dict(old, id="same-old-scale", ts=old["ts"] + 1)
        rows = [current(), old, dict(old, algo="staircase-v130"),
                dict(old, measurement_schema=1), another]
        self.assertEqual(history.comparable(rows, old), [old, another])
        self.assertEqual(old["vocab"], 7200)
        self.assertEqual(old["err"], 9.3)

    def test_insufficient_finished_measurement_not_fabricated_as_zero_trend(self):
        exhausted = current(vocab=0, completed=True, estimate_available=False,
                            stop_reason="exhausted", total=3)
        self.assertEqual(history.current_trend([exhausted], "bank-a"), [])


class ArchiveTests(unittest.TestCase):
    def payload(self):
        session = {"schema": 1, "algo": "bayes-v140", "id": "old-fixture",
                   "started_at": 1700000000, "resp": [1, 0, -1],
                   "state": {"seed": 2, "theta": -1.1, "level": 3,
                             "future": {"values": [None, "保留"]}},
                   "items": [{"key": "word", "item": {"options": ["a", "b"]}}]}
        return {"quiz_session": session, "history": [legacy()],
                "states": {"apple": {"st": "learning", "due": 1805000010}},
                "future": {"keep": [1, 2]}}

    def test_exact_snapshot_copied_without_mutating_old_session_or_history(self):
        progress = self.payload()
        session_ref = progress["quiz_session"]
        history_ref = progress["history"]
        row_ref = history_ref[0]
        before = copy.deepcopy(progress)
        history.archive_session(progress, 1805000000, "incompatible_or_expired")
        archive = progress["quiz_archives"][0]
        self.assertEqual(archive, {"archived_at": 1805000000,
                                   "reason": "incompatible_or_expired",
                                   "session": before["quiz_session"]})
        self.assertIs(progress["quiz_session"], session_ref)
        self.assertIs(progress["history"], history_ref)
        self.assertIs(progress["history"][0], row_ref)
        for key in before:
            self.assertEqual(progress[key], before[key])
        self.assertIsNot(archive["session"], session_ref)
        self.assertIsNot(archive["session"]["state"], session_ref["state"])
        self.assertIsNot(archive["session"]["resp"], session_ref["resp"])

    def test_archive_stays_independent_when_source_later_changes(self):
        progress = self.payload()
        old = copy.deepcopy(progress["quiz_session"])
        history.archive_session(progress, 1, "new_attempt")
        progress["quiz_session"]["resp"].append(1)
        progress["quiz_session"]["state"]["future"]["values"].append(99)
        self.assertEqual(progress["quiz_archives"][0]["session"], old)

    def test_equal_snapshot_is_idempotent_without_replacing_archive_list(self):
        progress = self.payload()
        history.archive_session(progress, 1, "first")
        archives = progress["quiz_archives"]
        first = archives[0]
        history.archive_session(progress, 2, "second")
        self.assertIs(progress["quiz_archives"], archives)
        self.assertIs(archives[0], first)
        self.assertEqual(len(archives), 1)
        self.assertEqual(first["archived_at"], 1)

    def test_same_id_but_new_evidence_keeps_both_snapshots(self):
        progress = self.payload()
        history.archive_session(progress, 1, "new_attempt")
        progress["quiz_session"]["resp"].append(0)
        history.archive_session(progress, 2, "new_attempt")
        self.assertEqual(len(progress["quiz_archives"]), 2)
        self.assertEqual(progress["quiz_archives"][0]["session"]["resp"], [1, 0, -1])
        self.assertEqual(progress["quiz_archives"][1]["session"]["resp"], [1, 0, -1, 0])

    def test_existing_archive_list_and_rows_are_retained(self):
        progress = self.payload()
        sentinel = {"future": "unknown archive shape remains"}
        archives = [sentinel]
        progress["quiz_archives"] = archives
        history.archive_session(progress, 1, "new_attempt")
        self.assertIs(progress["quiz_archives"], archives)
        self.assertIs(archives[0], sentinel)
        self.assertEqual(len(archives), 2)

    def test_malformed_archive_field_fails_closed_with_original_data(self):
        for malformed in (None, {}, "bad", 0):
            progress = self.payload()
            progress["quiz_archives"] = malformed
            before = copy.deepcopy(progress)
            with self.assertRaises(ValueError):
                history.archive_session(progress, 1, "new_attempt")
            self.assertEqual(progress, before)

    def test_missing_or_none_session_does_not_invent_archive(self):
        for progress in ({"history": [legacy()]}, {"quiz_session": None}):
            before = copy.deepcopy(progress)
            history.archive_session(progress, 1, "new_attempt")
            self.assertEqual(progress, before)
            self.assertNotIn("quiz_archives", progress)

    def test_bad_session_shapes_preserved_as_raw_snapshots(self):
        for malformed in (["old", {"future": [1]}], "old-json-string", 123):
            progress = {"quiz_session": malformed}
            history.archive_session(progress, 1, "incompatible_or_expired")
            self.assertEqual(progress["quiz_archives"][0]["session"], malformed)
            self.assertEqual(progress["quiz_session"], malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
