# -*- coding: utf-8 -*-
"""冒烟自检：首次引导 / 测试 / 学习 / 选错了 / 设置 / 主题 / 历史 / 词书。"""
import os, sys, io, json, time, re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
sys.argv = [sys.argv[0], "--nottest"]

from PyQt5.QtWidgets import QApplication
import main as app_main
import theme as th
import books as bk
import scheduler as sch
import placement as pl

prog = os.path.join(app_main.DATA, "progress.json")
if os.path.exists(prog):
    os.remove(prog)

app = QApplication(sys.argv)
w = app_main.Card()
out = []
fails = []


def pump(n=6):
    for _ in range(n):
        app.processEvents()


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


pump()

# ---- 1. 首次打开：先推荐测试 ----
w._startup(force=True)
check(w.mode == "welcome", "首次打开 -> 引导页，实际 %s" % w.mode)
check(w.btn_welcome_test.text() == "测试一下", "按钮：测试一下")
check(w.btn_welcome_skip.text() == "不测了，直接开始学", "按钮：不测了，直接开始学")
check(w.welcome_page.isVisible(), "引导页可见")
_texts = [lbl.text() for lbl in w.welcome_page.findChildren(app_main.QLabel)]
check(any("测试结果会影响学习内容" in t and "自动跳过" in t for t in _texts),
      "引导页说明：测试结果会影响学习内容，熟悉的词自动跳过")
check(any("约 5 分钟" in t and "50 题" in t for t in _texts), "引导页小字：约 5 分钟 · 50 题")
check(not any(("中途可以跳过" in t) or ("之后想测" in t) for t in _texts), "引导页没有多余小字")
check(th.DEFAULT == "light" and w.theme_key == "light"
      and w.t["bg"] == th.THEMES["light"]["bg"],
      "默认主题为亮色（%s）" % w.theme_key)

# ---- 2. 不测了 -> 词书页 ----
w._welcome_skip()
check(w.mode == "books", "不测了 -> 词书页，实际 %s" % w.mode)
check(w.progress.get("welcome_done") is True, "记下 welcome_done")
check(w.progress.get("quiz_declined") is True, "记下 quiz_declined")
check(len(bk.all()) == 1 and w.sel_book == "cet6",
      "词书列表 %d 本，选中 %s" % (len(bk.all()), w.sel_book))
out.append("词书行：%s" % w.lab_book_stat.text())
check("/" in w.lab_book_stat.text(), "显示 已学/总 数量")

# ---- 3. 开始学习 ----
w._start_learning()
check(w.mode == "front", "开始学习 -> 学习页，实际 %s" % w.mode)
check(w.progress.get("book") == "cet6", "记下词书")

# ---- 4. 记得 -> 翻面；选错了 -> 直接下一个 ----
first_word = w.queue[w.qi]["w"]["w"]
qi0 = w.qi
w.act("remember")
check(w.mode == "back" and w.meaning.text() != "", "记得 -> 翻面有释义")
w.correct()
check(w.qi == qi0 + 1, "选错了 -> 直接跳到下一个（qi %d -> %d）" % (qi0, w.qi))
st = w.states.get(first_word) or {}
check(st.get("st") == "learning" and st.get("lapse", 0) >= 1,
      "选错了把状态改成不记得（lapse=%s）" % st.get("lapse"))
check(w.mode == "front", "选错了之后回到正面")

# ---- 5. 设置页 ----
w.open_settings()
check(w.mode == "settings", "齿轮 -> 设置页")
check(w.lab_book.text() == bk.get("cet6")["name"], "设置页显示当前词书：%s" % w.lab_book.text())
learned, known, mastered, total = w._stats()
out.append("进度：已学 %d / %d · 已掌握 %d · 测试跳过 %d" % (learned, total, mastered, known))
check(total == len(w.words), "总数与词表一致")
check("已学" in w.lab_book_num.text(), "显示已学/总：%s" % w.lab_book_num.text())

# ---- 6. 主题切换 ----
for key, name in th.options():
    w.set_theme(key)
    check(w.theme_key == key and w.progress.get("theme") == key,
          "主题 %s（%s）已应用，背景 %s" % (name, key, w.t["bg"]))
w.set_theme(th.DEFAULT)

# ---- 7. 词汇量测试入口 + 历史记录 ----
check(w.btn_test.isVisible() and w.btn_test.text() in ("开始测试", "重新测试"),
      "设置页有测试入口：%s" % w.btn_test.text())
w.progress["history"] = [
    {"ts": int(time.time()) - 90 * 86400, "vocab": 2180, "right": 18, "dontknow": 9,
     "total": 50, "theta": 0.1, "se": 0.5, "baseline": True, "known": 1400, "to_learn": 4156},
    {"ts": int(time.time()) - 30 * 86400, "vocab": 3120, "right": 25, "dontknow": 6,
     "total": 50, "theta": 0.6, "se": 0.5, "baseline": False},
]
w.save()
w._refresh_settings()
check(w.hist_layout.count() == 2, "历史记录列出 %d 条" % w.hist_layout.count())
pump()
check(w.hist_box.mapTo(w.settings_page, w.hist_box.rect().bottomLeft()).y() <= w.settings_page.height(),
      "设置页内容没超出窗口")
w._open_history(1)
check(w.mode == "result", "点历史记录 -> 结果页，实际 %s" % w.mode)
check(w.btn_start.text() == "返回设置", "历史结果的主按钮是「返回设置」")
check(not w.btn_rebase.isVisible(), "历史结果不显示重排按钮")
check(len(w.chart.points) == 2, "折线图有 %d 个点（到所选记录为止）" % len(w.chart.points))
w._result_primary()
check(w.mode == "settings", "返回设置，实际 %s" % w.mode)

# ---- 8. 测试流程 ----
w._test_from_settings()
check(w.mode == "quiz", "开始测试 -> 测试页")
check(len(w.quiz_items) == 50, "50 题")
dup = [o for it in w.quiz_items for o in it["opts"] if re.search(r"[a-z]{1,6}\.[a-z]{1,6}\.", o)]
check(not dup, "选项里没有重复词性前缀（%d 个）" % len(dup))
for i in range(3):
    w._quiz_answer(w.quiz_items[i]["correct"])
    if i < 2:
        w._quiz_next()
w.quiz_timer.stop()
w2 = app_main.Card()          # 重开 = 续测
w2._startup(force=True)
check(w2.mode == "quiz" and w2.quiz_i == 2,
      "重开后继续第 %d 题" % (w2.quiz_i + 1))
w2.skip_test()
check(w2.mode == "front", "跳过本次 -> 回学习页")
check(w2.progress.get("snooze_until", 0) > time.time(), "24h 内不再弹")
w2.progress.pop("snooze_until", None)

# ---- 9. 走完一次测试 -> 结果页 ----
w2.start_quiz()
w2.quiz_timer.stop()
for i in range(len(w2.quiz_items)):
    it = w2.quiz_items[i]
    w2._quiz_answer(it["correct"] if w2.bs[it["idx"]] < 0.2 else (it["correct"] + 1) % 4)
    if i < len(w2.quiz_items) - 1:
        w2._quiz_next()
w2._finish_quiz()
check(w2.mode == "result", "测完 -> 结果页")
check(w2.btn_start.text() == "继续背单词", "测试结果主按钮是「继续背单词」")
check(w2.progress.get("quiz_declined") is None, "测过之后不再算「不测了」")
check("严谨度" in w2.res_sub.text(), "结果页有严谨度")
w2._result_primary()
check(w2.mode == "front", "继续背单词 -> 学习页")

# ---- 10. 满 30 天再弹测试 ----
for h in w2.progress["history"]:
    h["ts"] -= 31 * 86400
w2.save()
w2._startup(force=True)
check(w2.mode == "quiz", "超过 30 天 -> 再次弹测试，实际 %s" % w2.mode)

# ---- 11. 主题完整性 ----
check(not th.missing(), "所有主题颜色齐全（缺 %s）" % (th.missing(),))
for key, t in th.THEMES.items():
    s = th.qss(t)
    check("%(" not in s and "#" in s, "主题 %s 的 QSS 渲染正常" % key)

out.append("")
out.append("全部通过 ✓" if not fails else "失败 %d 项：%s" % (len(fails), " / ".join(fails)))
io.open(os.path.join(app_main.DATA, "smoke.txt"), "w", encoding="utf-8").write("\n".join(out))
print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
