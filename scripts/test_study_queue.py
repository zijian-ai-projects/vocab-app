# -*- coding: utf-8 -*-
"""固定时钟的学习队列自测；JSON 重启在内存模拟，不触碰真实 data。"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import scheduler as sch
import study_queue as sq
from study_queue import StudyQueue


def book(*keys):
    return [{"w": key, "s": "meaning " + key} for key in keys]


def learning(lv, due):
    return {"st": "learning", "lv": lv, "due": due, "seen": lv, "lapse": 0, "streak": 0}


def forgotten():
    return sch.on_forget(sch.new_state(), 0)


def restart(queue, words=None, retry_gap=None):
    # 等价于保存/加载 JSON，但整个测试没有文件写入。
    states = json.loads(json.dumps(queue.states, ensure_ascii=False))
    record = json.loads(json.dumps(queue.record, ensure_ascii=False))
    return StudyQueue(queue.words if words is None else words, states, record,
                      retry_gap=queue.retry_gap if retry_gap is None else retry_gap,
                      known=queue.known)


class StudyQueueTests(unittest.TestCase):
    def assert_item(self, item, key, kind, idx=None):
        self.assertIsNotNone(item)
        self.assertEqual(set(item), {"kind", "w", "st", "idx"})
        self.assertEqual((item["w"]["w"], item["kind"]), (key, kind))
        if idx is not None:
            self.assertEqual(item["idx"], idx)
        return item

    def test_default_retry_gap_is_four(self):
        queue = StudyQueue(book("a"), {}, {})
        self.assertEqual(queue.retry_gap, 4)

    def test_record_defaults_shared_identity_and_unanswered_current(self):
        states, record = {}, {}
        words = book("a", "b")
        queue = StudyQueue(words, states, record)
        self.assertIs(queue.states, states)
        self.assertIs(queue.record, record)
        self.assertEqual((queue.cursor, record["new_count"], record["pending"], record["current"]),
                         (0, 0, {}, None))
        item = self.assert_item(queue.next(0), "a", "new", 0)
        self.assertIs(item["w"], words[0])
        self.assertIsNone(item["st"])
        self.assertEqual(record["current"], {"kind": "new", "key": "a"})
        self.assertEqual(record["new_count"], 0)
        self.assertEqual(queue.next(0), item)
        queue.cursor = 1       # 即使游标变化，未答 current 也不能跳过。
        self.assert_item(queue.next(0), "a", "new", 0)
        json.dumps(record)

    def test_answer_counts_once_and_rejects_stale_item(self):
        queue = StudyQueue(book("a", "b"), {}, {})
        item = queue.next(0)
        after = queue.answer(item, True, 0)
        self.assertIs(after, queue.states["a"])
        self.assertEqual((after["lv"], after["st"], after["due"]), (1, "learning", 300))
        self.assertEqual((queue.record["new_count"], queue.cursor, queue.record["current"]), (1, 1, None))
        snapshot = deepcopy((queue.states, queue.record))
        with self.assertRaises(ValueError):
            queue.answer(item, True, 0)
        self.assertEqual((queue.states, queue.record), snapshot)
        self.assert_item(queue.next(0), "b", "new", 1)

    def test_exact_gap_three_and_five_first_new_answers(self):
        for gap in (4, 5):
            with self.subTest(gap=gap):
                keys = list("abcdefgh")[:gap + 2]
                queue = StudyQueue(book(*keys), {}, {}, retry_gap=gap)
                after = queue.answer(self.assert_item(queue.next(0), "a", "new", 0), False, 0)
                self.assertEqual((after["st"], after["lv"], after["due"]), ("new", 0, None))
                self.assertEqual(queue.record["pending"], {"a": gap + 1})
                for i in range(1, gap + 1):
                    item = self.assert_item(queue.next(0), keys[i], "new", i)
                    queue.answer(item, True, 0)
                    self.assertEqual(queue.record["new_count"], i + 1)
                item = self.assert_item(queue.next(0), "a", "retry", 0)
                self.assertEqual((item["st"]["lv"], item["st"]["due"]), (0, None))
                after = queue.answer(item, True, 0)
                self.assertEqual((after["st"], after["lv"], after["due"]), ("learning", 1, 300))
                self.assertEqual(queue.record["new_count"], gap + 1)
                self.assertNotIn("a", queue.record["pending"])
                self.assert_item(queue.next(0), keys[gap + 1], "new", gap + 1)

    def test_retry_forget_refreshes_gap_without_count_or_level_change(self):
        queue = StudyQueue(book(*"abcdefghij"), {}, {}, retry_gap=4)
        queue.answer(queue.next(0), False, 0)
        for key in "bcde":
            queue.answer(self.assert_item(queue.next(0), key, "new"), True, 0)
        after = queue.answer(self.assert_item(queue.next(0), "a", "retry"), False, 0)
        self.assertEqual((after["lv"], after["st"], after["due"], after["seen"], after["lapse"]),
                         (0, "new", None, 2, 2))
        self.assertEqual((queue.record["new_count"], queue.record["pending"]["a"]), (5, 9))
        for key in "fghi":
            queue.answer(self.assert_item(queue.next(0), key, "new"), True, 0)
        after = queue.answer(self.assert_item(queue.next(0), "a", "retry"), True, 0)
        self.assertEqual((queue.record["new_count"], after["lv"], after["seen"], after["lapse"]), (9, 1, 3, 2))

    def test_review_does_not_use_up_new_word_gap(self):
        queue = StudyQueue(book("a", "b", "c", "d", "old", "e"),
                           {"old": learning(1, 0)}, {})
        queue.answer(self.assert_item(queue.next(0), "old", "review"), False, 0)
        self.assertEqual(queue.record["new_count"], 0)
        queue.answer(self.assert_item(queue.next(0), "a", "new"), False, 0)
        for key in "bcde":
            queue.states["old"]["due"] = 0
            count = queue.record["new_count"]
            queue.answer(self.assert_item(queue.next(0), "old", "review"), True, 0)
            self.assertEqual(queue.record["new_count"], count)
            self.assertEqual(queue.record["pending"]["a"], 5)
            queue.answer(self.assert_item(queue.next(0), key, "new"), True, 0)
        self.assertEqual(queue.record["new_count"], 5)
        self.assert_item(queue.next(0), "a", "retry")

    def test_ready_retry_at_book_end_needs_no_additional_new_candidate(self):
        record = {"new_count": 5, "pending": {"a": 5}}
        queue = StudyQueue(book("a"), {"a": forgotten()}, record)
        self.assert_item(queue.next(0), "a", "retry")
        self.assertEqual(record["pending"], {"a": 5})

    def test_due_review_precedes_ready_retry(self):
        record = {"new_count": 5, "pending": {"a": 0}}
        queue = StudyQueue(book("a", "new", "old"), {"a": forgotten(), "old": learning(1, 0)}, record)
        queue.answer(self.assert_item(queue.next(0), "old", "review", 2), False, 0)
        self.assertEqual((record["new_count"], record["pending"]["a"]), (5, 0))
        self.assert_item(queue.next(0), "a", "retry", 0)

    def test_due_order_current_book_only_and_dynamic_enqueues(self):
        for order in ("abc", "cba", "bac"):
            with self.subTest(order=order):
                states = {"a": learning(1, 0), "b": learning(2, -100), "c": learning(3, -5),
                          "foreign": learning(1, -200)}
                queue = StudyQueue(book(*order, "new"), states, {})
                for idx, key in enumerate(order):
                    queue.answer(self.assert_item(queue.next(0), key, "review", idx), False, 0)
                item = self.assert_item(queue.next(0), "new", "new", 3)
                # 未答新词时，又一个旧词到期（真实 states 可被共享更新）。
                states[order[1]]["due"] = 0
                queue.answer(self.assert_item(queue.next(0), order[1], "review", 1), False, 0)
                self.assertEqual(queue.next(0), item)
                self.assertNotIn("foreign", [w["w"] for w in queue.words])

    def test_zero_clock_and_default_wall_clock(self):
        with patch.object(sq.time, "time", return_value=999):
            queue = StudyQueue(book("old", "new"), {"old": learning(1, 5)}, {})
            self.assert_item(queue.next(0), "new", "new", 1)
            self.assertEqual(queue.next_due_time(0), 5)
            self.assert_item(queue.next(), "old", "review", 0)
            self.assertEqual(queue.record["held_current"], {"kind": "new", "key": "new"})
            queue.answer(queue.next(), False)
            self.assertEqual(queue.states["old"]["due"], 1299)

    def test_unanswered_new_held_behind_all_due_reviews_then_restored(self):
        queue = StudyQueue(book("a", "b", "c", "x", "y"),
                           {"a": learning(1, 3), "b": learning(1, 1), "c": learning(1, 2)}, {})
        original = self.assert_item(queue.next(0), "x", "new", 3)
        for idx, key in enumerate("abc"):
            item = self.assert_item(queue.next(3), key, "review", idx)
            self.assertEqual(queue.record["held_current"], {"kind": "new", "key": "x"})
            self.assertEqual((queue.record["new_count"], queue.cursor), (0, 3))
            queue.answer(item, False, 3)
            json.dumps(queue.record)
        self.assertEqual(queue.next(3), original)
        self.assertIsNone(queue.record["held_current"])
        queue.answer(queue.next(3), True, 3)
        self.assertEqual((queue.record["new_count"], queue.cursor), (1, 4))
        self.assert_item(queue.next(3), "y", "new", 4)

    def test_unanswered_retry_held_without_gap_target_or_count_change(self):
        record = {"new_count": 2, "cursor": 2, "pending": {"a": 2}}
        queue = StudyQueue(book("a", "old", "fresh"), {"a": forgotten(), "old": learning(1, 5)}, record)
        self.assert_item(queue.next(0), "a", "retry", 0)
        queue.answer(self.assert_item(queue.next(5), "old", "review", 1), False, 5)
        self.assertEqual(record["held_current"], {"kind": "retry", "key": "a"})
        self.assertEqual((record["new_count"], record["pending"]["a"]), (2, 2))
        after = queue.answer(self.assert_item(queue.next(5), "a", "retry", 0), False, 5)
        self.assertEqual((record["new_count"], record["pending"]["a"], after["lv"]), (2, 6, 0))

    def test_restart_during_held_review_and_reverse_order(self):
        queue = StudyQueue(book("a", "b", "c", "d"), {"a": learning(1, 3), "b": learning(1, 2)}, {})
        self.assert_item(queue.next(0), "c", "new", 2)
        self.assert_item(queue.next(3), "a", "review", 0)
        queue = restart(queue, book("d", "c", "b", "a"))
        # 已持久化的当前复习题按 key 复用，随后按新词书顺序选题。
        queue.answer(self.assert_item(queue.next(3), "a", "review", 3), False, 3)
        queue.answer(self.assert_item(queue.next(3), "b", "review", 2), False, 3)
        queue.answer(self.assert_item(queue.next(3), "c", "new", 1), True, 3)
        self.assertEqual(queue.record["new_count"], 1)
        self.assert_item(queue.next(3), "d", "new", 0)

    def test_restart_unanswered_new_uses_key_and_never_skips_prefix(self):
        queue = StudyQueue(book("a", "b", "c", "d"), {}, {"cursor": 2})
        self.assert_item(queue.next(0), "c", "new", 2)
        queue = restart(queue, book("d", "c", "b", "a"))
        queue.answer(self.assert_item(queue.next(0), "c", "new", 1), True, 0)
        for key, idx in (("b", 2), ("a", 3), ("d", 0)):
            queue.answer(self.assert_item(queue.next(0), key, "new", idx), True, 0)
        self.assertEqual(queue.record["new_count"], 4)
        self.assertEqual(set(queue.states), set("abcd"))
        self.assertIsNone(queue.next(0))

    def test_restart_preserves_pending_and_gap_change_affects_next_forget_only(self):
        queue = StudyQueue(book(*"abcdefghi"), {}, {}, retry_gap=4)
        queue.answer(self.assert_item(queue.next(0), "a", "new"), False, 0)
        queue.answer(self.assert_item(queue.next(0), "b", "new"), True, 0)
        self.assert_item(queue.next(0), "c", "new")
        queue = restart(queue, retry_gap=6)
        self.assertEqual(queue.record["pending"]["a"], 5)
        queue.answer(self.assert_item(queue.next(0), "c", "new"), True, 0)
        queue.answer(self.assert_item(queue.next(0), "d", "new"), True, 0)
        queue.answer(self.assert_item(queue.next(0), "e", "new"), True, 0)
        queue.answer(self.assert_item(queue.next(0), "a", "retry"), False, 0)
        self.assertEqual((queue.record["new_count"], queue.record["pending"]["a"]), (5, 11))

    def test_ready_retry_ignores_legacy_daily_target_and_ledger(self):
        ledger = {"days": {"2026-11-17": ["a", "b"]}, "schema": 1}
        record = {"new_count": 4, "pending": {"a": 4}}
        queue = StudyQueue(book("a", "new"), {"a": forgotten()}, record)
        queue.answer(self.assert_item(queue.next(0), "a", "retry"), True, 0)
        self.assert_item(queue.next(0), "new", "new")
        self.assertEqual(ledger, {"days": {"2026-11-17": ["a", "b"]}, "schema": 1})

    def test_multiple_ready_retry_target_then_book_index(self):
        record = {"new_count": 10, "pending": {"a": 8, "b": 3, "c": 3}}
        queue = StudyQueue(book("c", "a", "b", "new"),
                           {key: forgotten() for key in "abc"}, record)
        for key, idx in (("c", 0), ("b", 2), ("a", 1)):
            queue.answer(self.assert_item(queue.next(0), key, "retry", idx), True, 0)
            self.assertEqual(record["new_count"], 10)
        self.assert_item(queue.next(0), "new", "new", 3)

    def test_book_end_retry_waits_for_exact_target_even_when_no_new_candidate(self):
        queue = StudyQueue(book("a", "b"), {}, {}, retry_gap=4)
        for key in "ab":
            queue.answer(self.assert_item(queue.next(0), key, "new"), False, 0)
        self.assertEqual(queue.record["pending"], {"a": 5, "b": 6})
        before = deepcopy(queue.record)
        self.assertIsNone(queue.next(0))
        self.assertEqual(queue.record["pending"], before["pending"])
        self.assertEqual(queue.record["new_count"], 2)

    def test_book_end_multiple_unknowns_do_not_early_retry_and_stay_restartable(self):
        queue = StudyQueue(book(*"abc"), {}, {}, retry_gap=4)
        for key in "abc":
            queue.answer(self.assert_item(queue.next(0), key, "new"), False, 0)
        self.assertEqual(queue.record["pending"], {"a": 5, "b": 6, "c": 7})
        for _ in range(2):
            queue = restart(queue)
            before = deepcopy(queue.record)
            self.assertIsNone(queue.next(0))
            self.assertEqual(queue.record["pending"], before["pending"])
        for key in "de":
            queue.words.append({"w": key, "s": "fixture"})
            queue._indices[key] = len(queue.words) - 1
            queue.answer(self.assert_item(queue.next(0), key, "new"), True, 0)
        self.assertEqual(queue.record["new_count"], 5)
        self.assert_item(queue.next(0), "a", "retry")

    def test_single_word_end_waits_with_no_new_or_review_deadline(self):
        queue = StudyQueue(book("a"), {}, {}, retry_gap=4)
        queue.answer(self.assert_item(queue.next(0), "a", "new"), False, 0)
        self.assertEqual(queue.record["pending"]["a"], 5)
        self.assertIsNone(queue.next(0))
        self.assertEqual(queue.record["new_count"], 1)
        self.assertIsNone(queue.next_due_time(0))
        self.assertIsNone(queue.next(300))
        self.assertEqual(queue.record["new_count"], 1)

    def test_legacy_cursor_and_reorder_do_not_lose_untouched_words(self):
        queue = StudyQueue(book(*"abcde"), {}, {"cursor": 3})
        queue.answer(self.assert_item(queue.next(0), "d", "new", 3), True, 0)
        queue = restart(queue, book("e", "c", "d", "b", "a"))
        for key, idx in (("a", 4), ("e", 0), ("c", 1), ("b", 3)):
            queue.answer(self.assert_item(queue.next(0), key, "new", idx), True, 0)
        self.assertEqual(set(queue.states), set("abcde"))
        self.assertEqual(queue.record["new_count"], 5)
        self.assertIsNone(queue.next(0))

    def test_explicit_forgotten_without_deadline_is_ready_without_new_candidate(self):
        queue = StudyQueue(book(*"abc"), {"a": forgotten()}, {"cursor": 3}, known=set("abc"))
        self.assert_item(queue.next(0), "a", "retry")
        self.assertEqual(queue.record["pending"]["a"], 0)
        self.assertEqual(queue.record["new_count"], 0)

    def test_known_skips_only_words_without_explicit_state(self):
        states = {"b": forgotten(), "c": learning(1, 100),
                  "d": {"st": "mastered", "lv": 10, "due": None},
                  "e": sch.on_retire(sch.new_state()), "f": {"st": "known", "lv": 0, "due": None},
                  "g": sch.new_state()}
        queue = StudyQueue(book(*"abcdefg"), states, {}, known=set("abcdefg"))
        self.assert_item(queue.next(0), "b", "retry", 1)
        self.assert_item(queue.next(100), "c", "review", 2)
        self.assertEqual(queue.record["held_current"], {"kind": "retry", "key": "b"})
        queue.answer(queue.next(100), True, 100)
        queue.answer(self.assert_item(queue.next(100), "b", "retry", 1), True, 100)
        queue.answer(self.assert_item(queue.next(100), "g", "new", 6), True, 100)
        self.assertEqual(queue.record["new_count"], 1)
        self.assertIsNone(queue.next(100))

    def test_memory_shared_cross_books_but_queues_are_book_local(self):
        states = {"foreign": learning(1, 0)}
        first = StudyQueue(book("a", "first_only"), states, {})
        second = StudyQueue(book("a", "second_only"), states, {}, known={"a"})
        first.answer(self.assert_item(first.next(0), "a", "new"), False, 0)
        second.answer(self.assert_item(second.next(0), "a", "retry"), True, 0)
        self.assertEqual((states["a"]["lv"], first.record["new_count"], second.record["new_count"]), (1, 1, 0))
        self.assert_item(first.next(0), "first_only", "new", 1)
        self.assertNotIn("a", first.record["pending"])
        self.assert_item(second.next(0), "second_only", "new", 1)
        self.assert_item(first.next(300), "a", "review", 0)
        self.assertEqual(states["foreign"]["due"], 0)

    def test_invalid_current_state_is_not_resurrected(self):
        queue = StudyQueue(book("a", "b"), {}, {})
        self.assert_item(queue.next(0), "a", "new")
        queue.states["a"] = {"st": "mastered", "lv": 10, "due": None}
        self.assert_item(queue.next(0), "b", "new")
        self.assertIsNone(queue.record["held_current"])
        queue.states["b"] = sch.on_retire(sch.new_state())
        self.assertIsNone(queue.next(0))
        self.assertIsNone(queue.record["current"])

    def test_foreign_pending_preserved_but_only_current_book_presented(self):
        states = {"foreign": forgotten()}
        record = {"pending": {"foreign": 0}, "new_count": 5}
        queue = StudyQueue(book("local", "other"), states, record)
        self.assert_item(queue.next(0), "local", "new")
        queue.answer(queue.next(0), True, 0)
        self.assertEqual(record["pending"], {"foreign": 0})
        queue = StudyQueue(book("foreign", "local", "other"), states, record)
        self.assert_item(queue.next(0), "foreign", "retry", 0)

    def test_next_due_time_future_only_and_current_book_only(self):
        states = {"a": learning(1, 300), "b": learning(2, 500), "past": learning(1, 0),
                  "foreign": learning(1, 1), "new": {"st": "new", "lv": 0, "due": 1},
                  "mastered": {"st": "mastered", "lv": 10, "due": 2},
                  "invalid_mastered": {"st": "learning", "lv": 10, "due": 2},
                  "retired": {"st": "retired", "lv": 2, "due": 1},
                  "known": {"st": "known", "lv": 0, "due": 2}}
        queue = StudyQueue(book("a", "b", "past", "new", "mastered", "invalid_mastered", "retired", "known"), states, {})
        with patch.object(sq.time, "time", return_value=0):
            self.assertEqual(queue.next_due_time(), 300)
        self.assertEqual(queue.next_due_time(300), 500)
        self.assertIsNone(queue.next_due_time(500))
        self.assertEqual(states["new"]["due"], 1)  # 查询不修改共享状态。

    def test_empty_book_has_no_items_or_future_due(self):
        states = {"foreign": learning(1, 20)}
        queue = StudyQueue([], states, {"cursor": 100})
        self.assertEqual(queue.cursor, 0)
        self.assertIsNone(queue.next(0))
        self.assertIsNone(queue.next_due_time(0))
        self.assertEqual(states["foreign"]["due"], 20)
        json.dumps(queue.record)

    def test_all_ten_levels_through_queue(self):
        queue = StudyQueue(book("a"), {}, {})
        queue.answer(self.assert_item(queue.next(0), "a", "new"), True, 0)
        for old_lv in range(1, 10):
            due = queue.states["a"]["due"]
            self.assertIsNone(queue.next(due - 1))
            after = queue.answer(self.assert_item(queue.next(due), "a", "review"), True, due)
            self.assertEqual(after["lv"], old_lv + 1)
            self.assertEqual(queue.record["new_count"], 1)
        self.assertEqual((queue.states["a"]["st"], queue.states["a"]["lv"], queue.states["a"]["due"]),
                         ("mastered", 10, None))
        self.assertIsNone(queue.next(10**12))
        self.assertIsNone(queue.next_due_time(0))

    def test_review_forget_preserves_grade_and_never_adds_pending(self):
        queue = StudyQueue(book("a"), {"a": learning(6, 0)}, {"new_count": 42})
        for now in (0, 345600):
            after = queue.answer(self.assert_item(queue.next(now), "a", "review"), False, now)
            self.assertEqual((after["st"], after["lv"], after["due"]), ("learning", 6, now + 300))
            self.assertEqual(queue.record["new_count"], 42)
            self.assertEqual(queue.record["pending"], {})
            self.assertIsNone(queue.next(now))

    def test_wrong_answer_snapshot_restores_counter_and_pending(self):
        states, record = {}, {}
        queue = StudyQueue(book("a", "b"), states, record)
        item = queue.next(0)
        saved_states, saved_record = deepcopy(states), deepcopy(record)
        queue.answer(item, True, 0)
        states.clear()
        states.update(saved_states)
        record.clear()
        record.update(saved_record)
        queue.answer(item, False, 0)
        self.assertEqual((record["new_count"], states["a"]["lv"], states["a"]["lapse"]), (1, 0, 1))
        self.assertEqual(record["pending"], {"a": 5})

    def test_pending_unknown_survives_reverse_then_shuffle(self):
        queue = StudyQueue(book(*"abcdefg"), {}, {})
        queue.answer(self.assert_item(queue.next(0), "a", "new"), False, 0)
        queue.answer(self.assert_item(queue.next(0), "b", "new"), False, 0)
        queue.answer(self.assert_item(queue.next(0), "c", "new"), True, 0)
        self.assert_item(queue.next(0), "d", "new", 3)
        queue = restart(queue, book(*"gfedcba"))
        self.assertEqual(queue.record["pending"], {"a": 5, "b": 6})
        queue.answer(self.assert_item(queue.next(0), "d", "new", 3), True, 0)
        queue.answer(self.assert_item(queue.next(0), "g", "new", 0), True, 0)
        self.assert_item(queue.next(0), "a", "retry", 6)
        queue = restart(queue, book(*"ebgacdf"))
        queue.answer(self.assert_item(queue.next(0), "a", "retry", 3), True, 0)
        self.assertEqual(queue.record["new_count"], 5)
        queue.answer(self.assert_item(queue.next(0), "f", "new", 6), True, 0)
        queue.answer(self.assert_item(queue.next(0), "b", "retry", 1), True, 0)
        self.assertEqual(queue.record["new_count"], 6)
        self.assertEqual(queue.record["pending"], {})
        self.assertEqual((queue.states["a"]["lv"], queue.states["b"]["lv"]), (1, 1))

    def test_restart_of_unanswered_ready_retry_keeps_current(self):
        queue = StudyQueue(book("a", "b", "c", "d", "e", "f"), {}, {})
        queue.answer(queue.next(0), False, 0)
        for key in "bcde":
            queue.answer(self.assert_item(queue.next(0), key, "new"), True, 0)
        self.assert_item(queue.next(0), "a", "retry", 0)
        queue.record["current"] = None
        queue = restart(queue)
        self.assertEqual(queue.record["pending"]["a"], 5)
        queue.answer(self.assert_item(queue.next(0), "a", "retry", 0), False, 0)
        self.assertEqual((queue.record["new_count"], queue.record["pending"]["a"]), (5, 9))

    def test_held_unknown_invalidated_when_shared_word_is_recognized(self):
        queue = StudyQueue(book("a", "old", "fresh"), {"a": forgotten(), "old": learning(1, 1)},
                           {"pending": {"a": 0}, "new_count": 4, "cursor": 2})
        self.assert_item(queue.next(0), "a", "retry")
        item = self.assert_item(queue.next(1), "old", "review")
        queue.states["a"] = learning(1, 300)
        queue.answer(item, False, 1)
        self.assertEqual(queue.record["pending"], {"a": 0})
        self.assertEqual(queue.record["held_current"], {"kind": "retry", "key": "a"})
        queue.answer(self.assert_item(queue.next(1), "fresh", "new"), True, 1)
        self.assertIsNone(queue.next(1))

    def test_legacy_full_item_current_is_canonicalized_by_key(self):
        record = {"current": {"kind": "new", "w": {"w": "a"}, "st": None, "idx": 999}}
        queue = StudyQueue(book("b", "a"), {}, record)
        queue.answer(self.assert_item(queue.next(0), "a", "new", 1), True, 0)
        self.assertEqual(record["new_count"], 1)
        self.assert_item(queue.next(0), "b", "new", 0)

    def test_nested_review_interruptions_preserve_saved_new_and_retry(self):
        saved_new = {"kind": "new", "key": "a", "custom": {"new": [1]}}
        saved_retry = {"kind": "retry", "key": "p", "custom": {"retry": [2]}}
        record = {"new_count": 5, "pending": {"p": 5},
                  "current": deepcopy(saved_new), "policy_held": [deepcopy(saved_retry)]}
        queue = StudyQueue(book("a", "p", "old"),
                           {"p": forgotten(), "old": learning(2, 10)}, record)
        self.assert_item(queue.next(0), "p", "retry")
        self.assertEqual(record["held_current"]["custom"], saved_new["custom"])
        queue.answer(self.assert_item(queue.next(10), "old", "review"), True, 10)
        queue = restart(queue)
        queue.answer(self.assert_item(queue.next(10), "p", "retry"), True, 10)
        self.assert_item(queue.next(10), "a", "new")
        self.assertEqual(queue.record["current"]["custom"], saved_new["custom"])
        self.assertEqual(queue.record["new_count"], 5)

    def test_interrupting_current_does_not_overwrite_occupied_held_slot(self):
        for interrupt in ("review", "retry"):
            with self.subTest(interrupt=interrupt):
                saved = {"kind": "new", "key": "a", "custom": {"keep": [1]}}
                current = {"kind": "new", "key": "b", "custom": {"keep": [2]}}
                record = {"current": deepcopy(current), "held_current": deepcopy(saved),
                          "new_count": 5, "pending": {"p": 5}}
                states = {"p": forgotten()}
                if interrupt == "review":
                    states["old"] = learning(2, 0)
                queue = StudyQueue(book("a", "b", "p", "old"), states, record)
                item = self.assert_item(queue.next(0), "old" if interrupt == "review" else "p", interrupt)
                queue.answer(item, True, 0)
                if interrupt == "review":
                    queue.answer(self.assert_item(queue.next(0), "p", "retry"), True, 0)
                queue.answer(self.assert_item(queue.next(0), "b", "new"), True, 0)
                queue = restart(queue)
                self.assert_item(queue.next(0), "a", "new")
                self.assertEqual(queue.record["current"]["custom"], saved["custom"])

    def test_engine_does_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("queue must be pure logic")):
            queue = StudyQueue(book("a"), {}, {})
            queue.answer(queue.next(0), False, 0)
            queue = restart(queue)
            self.assertIsNone(queue.next(0))
            self.assertEqual(queue.next_due_time(0), None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
