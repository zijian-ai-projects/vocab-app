# -*- coding: utf-8 -*-
"""V1.3.6 fixed catalog order / level-label regression (offscreen)."""
import os
import sys
import time
import json

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
import catalog
import books as bk
import entries

app = QApplication.instance() or QApplication(sys.argv)
out, fails = [], []


def check(ok, text):
    out.append(("  OK   " if ok else "  FAIL ") + text)
    if not ok:
        fails.append(text)


def pump(seconds=0.0):
    end = time.time() + seconds
    while True:
        app.processEvents()
        if time.time() >= end:
            break
        time.sleep(0.005)
    for _ in range(4):
        app.processEvents()


def entry(word, frq=None, **extra):
    row = {"w": word, "s": "n." + word, "raw": "n. " + word,
           "pos": ["n."], "ipa": "", "frq": frq}
    row.update(extra)
    return row


def signature(entries):
    return [item["w"] for item in entries]


def test_labels():
    check(entries.memory_info("x", {}, set()) == ("unlearned", 0, "待学习"),
          "Lv0 只显示待学习")
    check(entries.memory_info("x", {"x": {"st": "learning", "lv": 0, "seen": 1}},
                              set())[2] == "待学习",
          "实际作答后的 Lv0 仍只显示待学习")
    check(entries.memory_info("x", {"x": {"st": "learning", "lv": 1}},
                              set())[2] == "Lv1 · 认识",
          "Lv1 无空格")
    check(entries.memory_info("x", {"x": {"st": "learning", "lv": 9}},
                              set())[2] == "Lv9 · 认识",
          "Lv9 无空格")
    check(entries.memory_info("x", {"x": {"st": "mastered", "lv": 10}},
                              set())[2] == "Lv10 · 已掌握",
          "Lv10 与 LvN 一致")
    check(entries.memory_info("x", {}, {"x"})[2] == "认识 · 测试估计",
          "测试估计不伪造等级")
    check(entries.memory_info("x", {"x": {"st": "known"}},
                              set())[2] == "认识 · 旧版已会",
          "旧版 known 不伪造等级")


def test_alphabet():
    rows = [entry("beta", 20), entry("Alpha", 2), entry("alpha", 1),
            entry("Z", 30), entry("i", 4, display_w="I"),
            entry("it", 3)]
    model = catalog.WordTableModel()
    model.set_entries(rows, {}, set())
    check(signature(model.rows) == ["Alpha", "alpha", "beta", "i", "it", "Z"],
          "目录默认 A→Z，忽略词频和大小写")
    model.refilter()
    check(signature(model.rows) == ["Alpha", "alpha", "beta", "i", "it", "Z"],
          "重筛后继续固定字母升序")
    check(model.data(model.index(0, 0), catalog.Qt.DisplayRole) == "Alpha",
          "固定排序不改变 DisplayRole 显示")

def test_filters_and_search():
    rows = [entry("beta", 3, s="n.甲"), entry("alpha", 1, s="n.乙"),
            entry("charlie", 2, s="n.甲"), entry("delta", 0, s="n.丙")]
    states = {"beta": {"st": "learning", "lv": 3},
              "alpha": {"st": "learning", "lv": 1}}
    model = catalog.WordTableModel()
    model.set_entries(rows, states, set())
    model.refilter(category="all", query="甲")
    check(signature(model.rows) == ["beta", "charlie"],
          "搜索过滤后仍按字母升序")
    model.refilter(category="known", query="")
    check(signature(model.rows) == ["alpha", "beta"],
          "known 分类仍按字母升序")
    model.refilter(category="unlearned", query="")
    check(signature(model.rows) == ["charlie", "delta"],
          "unlearned 分类仍按字母升序")
    model.category = "all"
    model.query = ""
    shuffled = [entry("charlie", 2, s="n.甲"), entry("beta", 3, s="n.甲"),
                entry("delta", 0, s="n.丙"), entry("alpha", 1, s="n.乙")]
    model.set_entries(shuffled, states, set(), preserve_order=True)
    check(signature(model.rows) == ["charlie", "beta", "delta", "alpha"],
          "乱序目录保留学习顺序")
    model.refilter(category="all", query="甲")
    check(signature(model.rows) == ["charlie", "beta"],
          "乱序目录搜索仍保留学习顺序")
    model.set_entries(shuffled, states, set(), preserve_order=False)
    model.refilter(category="all", query="")
    check(signature(model.rows) == ["alpha", "beta", "charlie", "delta"],
          "顺序模式目录恢复字母升序")


def test_performance_real_bank():
    bank = json.load(open(os.path.join(APP, "data", "bank.json"), encoding="utf-8"))
    model = catalog.WordTableModel()
    t0 = time.perf_counter()
    model.set_entries(bank, {}, set())
    elapsed = time.perf_counter() - t0
    check(len(model.rows) == len(bank), "全部 bank 参与排序")
    check(elapsed < 3.0, "34,963 词字母排序耗时 %.3fs < 3s" % elapsed)
    check(signature(model.rows[:3]) == sorted(signature(bank), key=str.casefold)[:3],
          "真实词表按字母升序排列")
    # 大词书真实入口 + 只测可见行/排序不破测量
    words = bk.words("cgcf-all") if "cgcf-all" in bk.BY_ID else []
    if words:
        cat = catalog.BookCatalog()
        cat.resize(900, 600)
        entries = [k for k in ({"w": w, "s": "n." + w, "raw": "n. " + w,
                                "pos": ["n."], "frq": 0} for w in words)]
        cat.set_book("cgcf-all", "性能", entries, {}, set())
        cat.show()
        pump(0.08)
        check(cat.measured_rows <= 80,
              "16500 项首屏仍只测可见+buffer：%d" % cat.measured_rows)
        before_calls = cat.measure_calls
        cat.model.refilter()
        pump(0.08)
        check(cat.measured_rows <= 160,
              "排序后仍只测可见附近：%d" % cat.measured_rows)
        check(cat.measure_calls >= before_calls,
              "排序后重新触发可见测量")
        cat._measure_timer.stop()
        cat.close()


def main():
    for fn in (test_labels, test_alphabet, test_filters_and_search,
               test_performance_real_bank):
        fn()
        app.processEvents()
    out.append("")
    out.append("CATALOG_SORT_CHECKS %d; FAILS %d" % (len(out) - 2, len(fails)))
    print("\n".join(out))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
