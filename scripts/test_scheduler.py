# -*- coding: utf-8 -*-
"""固定时钟的记忆排期自测；只输出结果，不触碰真实 data 或存储模块。"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scheduler as sch


def words(*keys):
    return [{"w": key} for key in keys]


def learning(lv, due):
    return {"st": "learning", "lv": lv, "due": due, "seen": 7, "lapse": 2, "streak": 1}


class SchedulerTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(sch.MASTERED, 10)
        self.assertEqual(sch.LEVELS, [300, 1800, 43200, 86400, 172800, 345600,
                                     604800, 1296000, 2592000])
        self.assertEqual(sch.LEVEL_NAMES, ["5分钟", "30分钟", "12小时", "1天", "2天",
                                           "4天", "7天", "15天", "30天"])

    def test_new_has_no_schedule_even_at_zero(self):
        with patch.object(sch.time, "time", return_value=999):
            for now in (None, 0, 1_000_000):
                with self.subTest(now=now):
                    self.assertEqual(sch.new_state(now), {"st": "new", "lv": 0, "due": None,
                                                          "seen": 0, "lapse": 0, "streak": 0})

    def test_every_level_and_mastered_never_returns(self):
        st = sch.new_state(0)
        for lv in range(1, 11):
            before = deepcopy(st)
            source = st
            now = (lv - 1) * 100
            st = sch.on_remember(source, now)
            self.assertEqual(source, before, "input was mutated")
            self.assertIsNot(st, source)
            self.assertEqual(st["lv"], lv)
            self.assertEqual(st["seen"], lv)
            if lv < sch.MASTERED:
                self.assertEqual(st["st"], "learning")
                self.assertEqual(st["due"], now + sch.LEVELS[lv - 1])
            else:
                self.assertEqual(st["st"], "mastered")
                self.assertIsNone(st["due"])
        self.assertEqual(sch.on_remember(st, 10_000), st)
        self.assertEqual(sch.on_forget(st, 10_000), st)
        self.assertEqual(sch.on_fuzzy(st, 10_000), st)
        self.assertEqual(sch.due_queue(words("a"), {"a": st}, 10**12), [])
        self.assertIsNone(sch.next_new(words("a"), {"a": st}, 0)[0])

    def test_remember_zero_does_not_use_wall_clock(self):
        with patch.object(sch.time, "time", return_value=999):
            self.assertEqual(sch.on_remember(sch.new_state(), 0)["due"], 300)
            self.assertEqual(sch.on_remember(sch.new_state())["due"], 1299)

    def test_forget_all_learning_levels_without_demotion(self):
        for lv, interval in enumerate(sch.LEVELS, 1):
            with self.subTest(lv=lv):
                before = learning(lv, -500)
                before["retry_now"] = True
                before["custom"] = {"saved": [1, 2]}
                original = deepcopy(before)
                after = sch.on_forget(before, 0)
                self.assertEqual(before, original)
                self.assertEqual((after["st"], after["lv"], after["due"]),
                                 ("learning", lv, interval))
                self.assertEqual((after["seen"], after["lapse"]), (8, 3))
                self.assertNotIn("retry_now", after)
                self.assertEqual(after["custom"], before["custom"])
                after["custom"]["saved"].append(3)
                self.assertEqual(before["custom"]["saved"], [1, 2])
                for now in range(12):
                    after = sch.on_forget(after, now)
                    self.assertEqual(after["lv"], lv)
                    self.assertEqual(after["due"], now + interval)

    def test_forget_new_stays_new(self):
        st = sch.new_state(0)
        for attempt in range(1, 6):
            st = sch.on_forget(st, 0)
            self.assertEqual((st["st"], st["lv"], st["due"]), ("new", 0, None))
            self.assertEqual((st["seen"], st["lapse"]), (attempt, attempt))
            self.assertNotIn("retry_now", st)
            self.assertEqual(sch.due_queue(words("a"), {"a": st}, 10**12), [])
        after = sch.on_remember(st, 0)
        self.assertEqual((after["st"], after["lv"], after["due"]), ("learning", 1, 300))
        self.assertEqual(after["lapse"], 5)

    def test_fuzzy_refreshes_same_level(self):
        new = sch.on_fuzzy(sch.new_state(), 0)
        self.assertEqual((new["st"], new["lv"], new["due"]), ("new", 0, None))
        self.assertEqual(new["lapse"], 0)
        for lv, interval in enumerate(sch.LEVELS, 1):
            with self.subTest(lv=lv):
                st = sch.on_fuzzy(learning(lv, -1), 0)
                self.assertEqual((st["lv"], st["due"], st["seen"], st["lapse"]),
                                 (lv, interval, 8, 2))

    def test_retire_returns_copy_and_never_queues(self):
        before = learning(4, 0)
        after = sch.on_retire(before)
        self.assertEqual(before["st"], "learning")
        self.assertEqual((after["st"], after["lv"], after["due"]), ("retired", 4, None))
        self.assertEqual(sch.review_items(words("a"), {"a": after}, 100), [])
        self.assertIsNone(sch.next_new(words("a"), {"a": after}, 0)[0])
        self.assertEqual(sch.on_forget(after, 0), after)

    def test_due_order_is_book_order_including_reverse_and_shuffle(self):
        states = {"a": learning(1, 0), "b": learning(2, -100), "c": learning(3, -20),
                  "future": learning(1, 5), "foreign": learning(1, -10),
                  "fresh": sch.on_forget(sch.new_state(), 0),
                  "mastered": {"st": "mastered", "lv": 10, "due": -5},
                  "invalid_mastered": {"st": "learning", "lv": 10, "due": -5},
                  "retired": {"st": "retired", "lv": 4, "due": -5},
                  "known": {"st": "known", "lv": 0, "due": -5}}
        for order in (("a", "b", "c"), ("c", "b", "a"), ("b", "a", "c")):
            with self.subTest(order=order):
                book = words("fresh", *order, "future", "mastered", "invalid_mastered", "retired", "known")
                queue = sch.due_queue(book, states, 0)
                self.assertEqual([w["w"] for _, w, _ in queue], list(order))
                items = sch.review_items(book, states, 0)
                self.assertEqual([item["kind"] for item in items], ["review"] * 3)
                self.assertEqual([item["idx"] for item in items], [1, 2, 3])
                self.assertTrue(all(item["st"] is states[item["w"]["w"]] for item in items))

    def test_due_queue_is_recomputed_including_boundary_and_new_entries(self):
        book = words("a", "b", "c")
        states = {"b": learning(1, 3), "c": learning(1, 8)}
        self.assertEqual(sch.due_queue(book, states, 0), [])
        self.assertEqual([w["w"] for _, w, _ in sch.due_queue(book, states, 3)], ["b"])
        states["a"] = learning(1, 5)
        self.assertEqual([w["w"] for _, w, _ in sch.due_queue(book, states, 8)], ["a", "b", "c"])

    def test_next_new_compatibility(self):
        book = words("learning", "known", "retired", "mastered", "forgotten", "untouched")
        states = {"learning": learning(1, 999), "known": {"st": "known", "lv": 0},
                  "retired": sch.on_retire(sch.new_state()),
                  "mastered": {"st": "mastered", "lv": 10},
                  "forgotten": sch.on_forget(sch.new_state(), 0)}
        item, cursor = sch.next_new(book, states, 0)
        self.assertEqual((item["kind"], item["w"]["w"], item["idx"], cursor),
                         ("new", "forgotten", 4, 4))
        item, cursor = sch.next_new(book, states, 5)
        self.assertEqual((item["w"]["w"], cursor), ("untouched", 5))
        self.assertEqual(sch.next_new(book, states, 6), (None, 6))

    def test_legacy_learning_levels_preserve_saved_fields_and_due(self):
        for old_lv in range(9):
            with self.subTest(old_lv=old_lv):
                old = learning(old_lv, 0 if old_lv == 0 else 100 + old_lv)
                old["retry_now"] = True
                old["custom"] = {"x": [old_lv]}
                snapshot = deepcopy(old)
                modern = sch.migrate_state(old, legacy=True)
                self.assertEqual(old, snapshot)
                self.assertEqual((modern["st"], modern["lv"]), ("learning", old_lv + 1))
                self.assertEqual(modern["due"], old["due"])
                self.assertEqual((modern["seen"], modern["lapse"], modern["streak"]), (7, 2, 1))
                self.assertEqual(modern["custom"], old["custom"])
                self.assertNotIn("retry_now", modern)
                modern["custom"]["x"].append(99)
                self.assertEqual(old["custom"]["x"], [old_lv])

    def test_legacy_new_means_already_recognized_and_mastered_is_ten(self):
        old = {"st": "new", "lv": 0, "due": 0, "seen": 0, "lapse": 0, "note": "keep"}
        modern = sch.migrate_state(old, legacy=True)
        self.assertEqual((modern["st"], modern["lv"], modern["due"]), ("learning", 1, 0))
        self.assertEqual(modern["note"], "keep")
        terminal = sch.migrate_state({"st": "mastered", "lv": 9, "due": None, "seen": 33}, legacy=True)
        self.assertEqual((terminal["st"], terminal["lv"], terminal["due"], terminal["seen"]),
                         ("mastered", 10, None, 33))

    def test_modern_migration_is_idempotent_with_fresh_independent_copies(self):
        old = {"new": {"st": "new", "lv": 0, "due": 123, "seen": 0},
               "old": learning(8, 456), "mastered": {"st": "mastered", "lv": 9, "due": None}}
        migrated = sch.migrate_states(old, legacy=True)
        migrated["fresh"] = sch.on_forget(sch.new_state(), 0)
        modern = sch.migrate_states(migrated)
        self.assertEqual(modern, migrated)
        self.assertEqual(sch.migrate_states(modern), modern)
        self.assertIsNot(modern, migrated)
        for key in modern:
            self.assertIsNot(modern[key], migrated[key])
        self.assertEqual((modern["fresh"]["st"], modern["fresh"]["lv"]), ("new", 0))
        self.assertEqual(old["old"]["lv"], 8)
        self.assertEqual(modern["old"]["lv"], 9)
        with patch.object(sch.time, "time", side_effect=AssertionError("migration must not reschedule")):
            self.assertEqual(sch.migrate_states(modern), modern)


if __name__ == "__main__":
    unittest.main(verbosity=2)
