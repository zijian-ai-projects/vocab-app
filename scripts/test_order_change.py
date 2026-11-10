# -*- coding: utf-8 -*-
"""V1.3.3 真实Card词序回归；只在Sandbox写资料，绝不运行默认main。"""
import copy
import io
import json
import os
from pathlib import Path
import random
import sys
import time
import unittest
from contextlib import ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
from ui_test_support import Sandbox, configure_qt, new_app, set_nottest
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"))
configure_qt("offscreen")
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox
import main as app_main
import books as real_books
import scheduler as sch
import storage
from study_queue import StudyQueue

APP = new_app([])
APP.setQuitOnLastWindowClosed(False)
REAL_TIME = time.time
A, B = "fixture-order-a", "fixture-order-b"
KEYS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel")
WORDS = [{"w": key, "ipa": "tɛst", "s": "n.隔离释义" + key,
          "raw": "n.隔离释义" + key, "pos": ["n."], "b": i / 10,
          "lvl": 0, "frq": i + 1} for i, key in enumerate(KEYS)]


class TinyBooks:
    DEFAULT = A
    LEGACY = {}

    def __init__(self):
        self.BY_ID = {}
        for bid, keys in ((A, KEYS), (B, KEYS[4:] + KEYS[:4])):
            self.BY_ID[bid] = {"id": bid, "name": bid, "display": bid,
                              "words": list(keys), "count": len(keys), "type": "word",
                              "kind": "fixture", "series": "", "is_union": False,
                              "group": "fixture-group", "main": "fixture-main",
                              "path": ["隔离主类", "隔离分组"]}
        group = {"id": "fixture-group", "name": "隔离分组", "main": "fixture-main",
                 "items": list(self.BY_ID.values()), "series": [], "count": 2,
                 "union": self.BY_ID[A]}
        self.GROUPS = {group["id"]: group}
        self.MAINS = [{"id": "fixture-main", "name": "隔离主类", "groups": [group]}]

    def mains(self):
        return self.MAINS

    def items(self, gid):
        return self.GROUPS.get(gid, {}).get("items", [])

    def get(self, bid):
        return self.BY_ID.get(bid, self.BY_ID[A])

    def words(self, bid):
        return self.get(bid)["words"]


def fixture(**overrides):
    data = {"memory_schema": 2, "book": A, "book_confirmed": True,
            "welcome_done": True, "quiz_declined": True, "theme": "light",
            "states": {}, "cursors": {A: 0, B: 0}, "orders": {
                A: {"mode": "seq", "seed": 42}, B: {"mode": "shuffle", "seed": 52}},
            "study_records": {}, "retry_gap": 3, "study_mode": "brush", "theta": None,
            "history": [{"ts": 1999999900, "vocab": 100, "theta": 0, "baseline": True}],
            "future_metadata": {"keep": [7, {"unknown": True}]}}
    data.update(copy.deepcopy(overrides))
    return data


def current(w):
    item = w.queue[w.qi]
    return item["kind"], item["w"]["w"]


def shuffled(keys, seed):
    keys = list(keys)
    random.Random(seed).shuffle(keys)
    return keys


class OrderChangeTests(unittest.TestCase):
    def setUp(self):
        set_nottest(True)
        self.stack = ExitStack()
        self.sb = Sandbox(app_main, "order-change")
        self.clock = [2000000000.0]
        self.books = TinyBooks()
        self.stack.enter_context(patch.dict(os.environ, {"VOCABAPP_DATA_DIR": self.sb.dir}))
        self.stack.enter_context(patch.object(app_main, "DATA", self.sb.dir))
        self.stack.enter_context(patch.object(app_main, "bk", self.books))
        self.stack.enter_context(patch.object(app_main.time, "time", lambda: self.clock[0]))
        self.stack.enter_context(patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok))
        self.stack.enter_context(self.sb)
        self.write_bank(WORDS)
        self.addCleanup(self.finish_sandbox)

    def finish_sandbox(self):
        self.stack.close()
        self.assertFalse(self.sb.errors, "真实记录shield: " + " / ".join(self.sb.errors))
        print("REAL_GUARD", self._testMethodName, "PATHS", len(self.sb.watch_paths), "UNCHANGED", True)

    def write_bank(self, entries):
        # 只在已确定的原始Sandbox目录创建/替换夹具，不写真实bank。
        with io.open(self.sb.path("bank.json"), "w", encoding="utf-8") as stream:
            json.dump(entries, stream, ensure_ascii=False)
        with io.open(self.sb.path("phrases.json"), "w", encoding="utf-8") as stream:
            json.dump([], stream)

    def card(self, data=None):
        if data is not None:
            self.sb.reset(data, {"mode": "normal", "w": 520, "h": 430})
        w = self.sb.new_card(show=True)
        self.sb.pump(APP)
        self.assertEqual(storage.paths(), (self.sb.progress_path, self.sb.win_path))
        self.assertEqual(storage.legacy_dirs(), [])
        return w

    def click(self, button):
        self.assertTrue(button.isVisible(), button.text() + " 必须实际可见")
        QTest.mouseClick(button, Qt.LeftButton)
        self.sb.pump(APP)

    def books_page(self, w, src="settings"):
        w.open_books(src)
        w._nav_into_main("fixture-main")
        w._nav_into_group("fixture-group")
        self.sb.pump(APP)
        self.assertEqual(w.nav_level, 3)
        self.assertTrue(w.chip_shuffle.isVisible())

    def row(self, w, bid):
        self.click(w.book_btns[bid])

    def confirm(self, w):
        self.click(w.btn_learn)
        self.assertIs(w.study_engine.record, w.study_records[w.book_id])
        self.assertEqual([x["w"] for x in w.study_engine.words], [x["w"] for x in w.queue_words])

    def trace(self, name, w):
        print("UI_TRACE", name, json.dumps({"book": w.book_id, "sel_book": w.sel_book,
              "sel_order": w.sel_order, "order_mode": w.order_mode,
              "current": current(w) if w.queue else None,
              "record": copy.deepcopy(w.study_records.get(w.book_id)),
              "queue_words": [x["w"] for x in w.queue_words],
              "orders": w.orders}, ensure_ascii=False))

    def check_explicit_then_row(self, w, mode, bid, src):
        self.books_page(w, src)
        self.click(w.chip_shuffle if mode == "shuffle" else w.chip_seq)
        self.assertEqual(w.sel_order, mode)
        self.row(w, bid)
        selected = w.sel_order
        self.confirm(w)
        self.trace("explicit-%s-before-row-%s" % (mode, bid), w)
        with self.subTest(stage="book-row-keeps-explicit-mode"):
            self.assertEqual(selected, mode, "_pick_book不得覆盖用户已显式选择的词序")
        with self.subTest(stage="confirm-commits-explicit-mode"):
            self.assertEqual(w.orders[bid]["mode"], mode)
        with self.subTest(stage="engine-rebuilt-with-explicit-mode"):
            expected = self.books.words(bid)
            if mode == "shuffle":
                expected = shuffled(expected, w.orders[bid]["seed"])
            self.assertEqual([x["w"] for x in w.queue_words], expected)
        w.close()
        restarted = self.card()
        with self.subTest(stage="restart-persists-explicit-mode"):
            self.assertEqual(restarted.order_mode, mode)
            self.assertEqual(current(restarted), current(w))

    def test_shuffle_before_first_book_row_is_not_silently_discarded(self):
        w = self.card(fixture(book_confirmed=False))
        self.check_explicit_then_row(w, "shuffle", A, "welcome")

    def test_shuffle_before_same_book_row_is_not_silently_discarded(self):
        w = self.card(fixture())
        self.check_explicit_then_row(w, "shuffle", A, "settings")

    def test_seq_before_book_with_saved_shuffle_is_not_silently_discarded(self):
        w = self.card(fixture())
        self.check_explicit_then_row(w, "seq", B, "settings")

    def test_saved_book_mode_is_restored_when_no_explicit_selection(self):
        w = self.card(fixture())
        self.books_page(w, "welcome")
        self.row(w, B)
        self.assertEqual(w.sel_order, "shuffle")
        self.assertEqual(w.chip_shuffle.property("on"), "1")
        self.confirm(w)
        self.assertEqual(w.order_mode, "shuffle")
        self.assertEqual(current(w), ("new", shuffled(self.books.words(B), 52)[0]))

    def test_explicit_change_after_row_rebuilds_pointers_and_preserves_records(self):
        alpha = sch.new_state()
        alpha["seen"] = 1
        record = {"cursor": 1, "new_count": 1, "pending": {"alpha": 4},
                  "current": {"kind": "new", "key": "bravo"},
                  "held_current": {"kind": "new", "key": "charlie"}, "last_retry": "alpha",
                  "unknown": {"keep": [7, "queue"]}}
        data = fixture(states={"alpha": alpha}, cursors={A: 1, B: 0}, study_records={A: record})
        w = self.card(data)
        self.assertEqual(current(w), ("new", "bravo"))
        self.books_page(w)
        self.row(w, A)
        self.click(w.chip_shuffle)
        self.confirm(w)
        self.trace("row-before-shuffle", w)
        expected = shuffled(KEYS, 42)
        self.assertEqual([x["w"] for x in w.queue_words], expected)
        self.assertEqual(current(w), ("new", expected[0]))
        self.assertEqual(w.study_record["cursor"], 0)
        self.assertIsNone(w.study_record["held_current"])
        self.assertEqual(w.study_record["new_count"], 1)
        self.assertEqual(w.study_record["pending"], {"alpha": 4})
        self.assertEqual(w.study_record["unknown"], record["unknown"])
        for field in ("states", "history", "future_metadata"):
            self.assertEqual(w.progress[field], data[field])
        saved = self.sb.read_progress()
        w.close()
        restarted = self.card()
        self.assertEqual(restarted.study_record, saved["study_records"][A])
        self.assertEqual(current(restarted), ("new", expected[0]))
        self.assertEqual(restarted.orders[A]["seed"], 42)

    def test_same_shuffle_start_and_restart_preserve_unanswered_current(self):
        record = {"cursor": 3, "new_count": 0, "pending": {},
                  "current": {"kind": "new", "key": "hotel"},
                  "held_current": None, "last_retry": None, "unknown": {"keep": True}}
        data = fixture(orders={A: {"mode": "shuffle", "seed": 42}},
                       cursors={A: 3}, study_records={A: record})
        w = self.card(data)
        self.assertEqual(current(w), ("new", "hotel"))
        self.books_page(w)
        self.assertEqual(w.sel_book, A)
        self.assertEqual(w.sel_order, "shuffle")
        self.assertEqual(w.chip_shuffle.property("on"), "1")
        self.row(w, A)
        self.click(w.chip_shuffle)
        self.confirm(w)
        self.assertEqual(w.study_record, record)
        self.assertEqual(current(w), ("new", "hotel"))
        w.close()
        restarted = self.card()
        self.assertEqual(restarted.study_record, record)
        self.assertEqual(restarted.orders[A]["seed"], 42)

    def test_due_filter_uses_shuffled_book_order_not_due_timestamp(self):
        states = {"alpha": {"lv": 1, "st": "learning", "due": self.clock[0] - 900,
                            "seen": 1, "lapse": 0, "streak": 0},
                  "delta": {"lv": 1, "st": "learning", "due": self.clock[0] - 1,
                            "seen": 1, "lapse": 0, "streak": 0}}
        w = self.card(fixture(states=states, orders={A: {"mode": "shuffle", "seed": 42}}))
        self.assertEqual(current(w), ("review", "delta"))
        self.assertLess(states["alpha"]["due"], states["delta"]["due"])
        w.act("remember")
        w._next()
        self.assertEqual(current(w), ("review", "alpha"))
        self.assertEqual(w.study_record["new_count"], 0)
        self.assertEqual(w.study_record["cursor"], 0)

    def test_new_book_same_mode_resumes_its_saved_current_and_shared_states(self):
        record_a = {"cursor": 3, "new_count": 0, "pending": {},
                    "current": {"kind": "new", "key": "hotel"},
                    "held_current": None, "last_retry": None}
        record_b = {"cursor": 6, "new_count": 9, "pending": {},
                    "current": {"kind": "new", "key": "echo"},
                    "held_current": None, "last_retry": None, "unknown": {"keep": [9]}}
        w = self.card(fixture(orders={A: {"mode": "shuffle", "seed": 42},
                                     B: {"mode": "shuffle", "seed": 52}},
                              cursors={A: 3, B: 6}, study_records={A: record_a, B: record_b}))
        self.books_page(w)
        self.row(w, B)
        self.confirm(w)
        self.assertEqual(current(w), ("new", "echo"))
        self.assertEqual(w.study_records[A], record_a)
        self.assertEqual(w.study_records[B], record_b)
        self.assertIs(w.states, w.study_engine.states)
        w.close()
        restarted = self.card()
        self.assertEqual(restarted.book_id, B)
        self.assertEqual(current(restarted), ("new", "echo"))
        self.assertEqual(restarted.study_record, record_b)

    def test_catalog_order_and_refilter_are_stable_without_committing_selection(self):
        w = self.card(fixture())
        queue_before = [x["w"] for x in w.queue_words]
        self.books_page(w)
        self.row(w, A)
        self.click(w.chip_shuffle)
        before = self.sb.read_progress()
        self.click(w.btn_catalog_books)
        expected = shuffled(KEYS, 42)
        self.assertEqual([x["w"] for x in w.catalog.model.entries], expected)
        ranks = {row["w"]: row.get("frq", 0) for row in WORDS}
        catalog_expected = sorted(expected, key=lambda key: ranks[key])
        w.catalog.model.refilter(category="unlearned", query="")
        self.assertEqual([x["w"] for x in w.catalog.model.rows], catalog_expected)
        w.catalog.model.refilter(category="all", query="a")
        self.assertEqual([x["w"] for x in w.catalog.model.rows],
                         [k for k in catalog_expected if "a" in k])
        self.assertEqual([x["w"] for x in w.queue_words], queue_before,
                         "目录频率排序/筛选不能改未确认前的学习队列")
        self.assertEqual(self.sb.read_progress(), before)

    def test_cursor_tail_then_prefix_scan_never_loses_or_repeats_new_words(self):
        ordered = [next(x for x in WORDS if x["w"] == k) for k in shuffled(KEYS, 42)]
        record = {"cursor": 3, "new_count": 0, "pending": {}, "current": None}
        engine = StudyQueue(ordered, {}, record, 3)
        trace = []
        for _ in range(8):
            item = engine.next(self.clock[0])
            self.assertEqual(item["kind"], "new")
            trace.append(item["w"]["w"])
            engine.answer(item, True, self.clock[0])
        self.assertEqual(trace, [x["w"] for x in ordered[3:] + ordered[:3]])
        self.assertEqual(len(set(trace)), 8)
        self.assertEqual(record["new_count"], 8)
        self.assertIsNone(engine.next(self.clock[0]))

    def test_readonly_real_book_copy_ui_matches_review_current_then_shuffle_trace(self):
        # 只读真实资料，随后只将副本写入Sandbox；默认app.main从不调用。
        original = json.loads((ROOT / "data" / "progress.json").read_text(encoding="utf-8"))
        bank = json.loads((ROOT / "data" / "bank.json").read_text(encoding="utf-8"))
        data = copy.deepcopy(original)
        data.update(book_confirmed=True, welcome_done=True, quiz_declined=True, study_mode="brush")
        self.clock[0] = REAL_TIME()
        self.write_bank(bank)
        self.stack.enter_context(patch.object(app_main, "bk", real_books))
        bid = data["book"]
        wm = {x["w"]: x for x in bank}
        expected = [wm[k] for k in real_books.words(bid) if k in wm]
        mode = data["orders"][bid]["mode"]
        if mode == "shuffle":
            random.Random(data["orders"][bid]["seed"]).shuffle(expected)
        reference = StudyQueue(expected, copy.deepcopy(data["states"]),
                               copy.deepcopy(data["study_records"][bid]), 3)
        w = self.card(data)
        self.assertEqual([x["w"] for x in w.queue_words], [x["w"] for x in expected])
        trace = []
        for _ in range(15):
            item = reference.next(self.clock[0])
            self.assertIsNotNone(item)
            self.assertEqual(current(w), (item["kind"], item["w"]["w"]))
            trace.append((item["kind"], item["w"]["w"], item["idx"],
                          w.study_record["cursor"], w.study_record["new_count"]))
            reference.answer(item, True, self.clock[0])
            w.act("remember")
            w._next()
            reference.next(self.clock[0])
            self.assertEqual(w.states, reference.states)
            self.assertEqual(w.study_record, reference.record)
        print("READONLY_REAL_UI_TRACE", json.dumps(trace, ensure_ascii=False))
        saved = self.sb.read_progress()
        key = current(w)
        w.close()
        restarted = self.card()
        self.assertEqual(current(restarted), key)
        self.assertEqual(restarted.study_record, saved["study_records"][bid])


if __name__ == "__main__":
    from contextlib import redirect_stdout
    import tempfile
    from ui_test_support import TEST_ROOT
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(OrderChangeTests))
    outdir = Path(tempfile.mkdtemp(prefix="order-change-out-", dir=TEST_ROOT))
    report = outdir / "test_order_change.txt"
    report.write_text(buffer.getvalue(), encoding="utf-8")
    print(buffer.getvalue())
    print("REPORT", str(report))
    print("ORDER_TESTS", result.testsRun, "FAILS", len(result.failures), "ERRORS", len(result.errors))
    sys.exit(0 if result.wasSuccessful() else 1)
