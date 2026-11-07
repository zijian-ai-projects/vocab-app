# -*- coding: utf-8 -*-
"""冒烟自检 v1.1：大词库 / 11 本词书 / 顺序乱序 / 引导 / 学习 / 设置 / 阶梯测试 / 历史。"""
import os, sys, io, json, time, re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
sys.argv = [sys.argv[0], "--nottest"]

from PyQt5.QtWidgets import QApplication
import main as app_main
import theme as th
import books as bk
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


def stop_timer():
    for x in (w,):
        try:
            x.quiz_timer.stop()
        except Exception:
            pass


pump()

# ---- 1. 大词库 ----
bank = w.bank
check(len(bank) >= 15000, "大词库 %d 词" % len(bank))
check([x["w"] for x in bank] == sorted(x["w"] for x in bank), "大词库按字母序 A–Z")
check(len({x["w"] for x in bank}) == len(bank), "大词库无重复")
check(all(x.get("s") for x in bank), "每个词都有卡面释义")
lv = [0] * 15
for x in bank:
    lv[x["lvl"]] += 1
check(min(lv) > 0 and max(lv) - min(lv) <= 20, "难度 15 档分布：%s" % lv)

# ---- 2. 11 本词书 ----
check(len(bk.all()) == 11, "词书 %d 本" % len(bk.all()))
check(bk.size("cet6") == 5406, "六级 %d 词" % bk.size("cet6"))
check(bk.size("kaobo") == 10556, "考博 %d 词" % bk.size("kaobo"))
check(all(x in w.bank_map for x in bk.words("cet6")), "六级每个词都在大词库里")
check(bk.words("cet6") == sorted(bk.words("cet6")), "词书数据存的是 A–Z 顺序")

# ---- 3. 首次打开：引导页 ----
w._startup(force=True)
check(w.mode == "welcome", "首次打开 -> 引导页，实际 %s" % w.mode)
texts = [lbl.text() for lbl in w.welcome_page.findChildren(app_main.QLabel)]
check(any("测试结果会影响学习内容" in t and "自动跳过" in t for t in texts), "引导页说明")
check(any("约 5 分钟" in t and "50 题" in t for t in texts), "引导页小字：约 5 分钟 · 50 题")
check(not any(("中途可以跳过" in t) or ("之后想测" in t) for t in texts), "引导页没有多余小字")
check(th.DEFAULT == "light" and w.theme_key == "light", "默认主题为亮色")

# ---- 4. 不测了 -> 词书页；选书 + 选顺序 ----
w._welcome_skip()
check(w.mode == "books", "不测了 -> 词书页，实际 %s" % w.mode)
check(len(w.book_btns) == 11, "词书页列出 %d 本" % len(w.book_btns))
check(w.book_scroll.isVisible(), "词书列表可滚动")
check(w.chip_seq.text() == "顺序" and w.chip_shuf.text() == "乱序", "有 顺序/乱序 两个选择")
check(w.sel_book == "cet6" and w.sel_order in ("seq", "shuffle"),
      "默认选中 %s / %s" % (w.sel_book, w.sel_order))
check("已学 0 / 5,406" in w.lab_book_stat.text(), "词书显示已学/总：%s" % w.lab_book_stat.text())

w._pick_book("cet6")
w._set_order("seq")
w._start_learning()
check(w.mode == "front" and w.book_id == "cet6" and w.order_mode == "seq",
      "顺序学习：%s / %s" % (w.book_id, w.order_mode))
check(len(w.queue_words) == 5406, "当前队列 %d 词" % len(w.queue_words))
check(w.queue_words[0]["w"] == sorted(bk.words("cet6"))[0],
      "顺序书从 A 开头的词开始：%s" % w.queue_words[0]["w"])

# ---- 5. 学习：记得 / 释义 / 选错了跳下一个 ----
first = w.queue[w.qi]["w"]["w"]
qi0 = w.qi
w.act("remember")
check(w.mode == "back" and w.meaning.text() != "", "记得 -> 翻面有释义")
w.correct()
check(w.qi == qi0 + 1, "选错了 -> 直接跳到下一个（qi %d -> %d）" % (qi0, w.qi))
st = w.states.get(first) or {}
check(st.get("st") == "learning" and st.get("lapse", 0) >= 1,
      "选错了把状态改成不记得（lapse=%s）" % st.get("lapse"))
check(w.mode == "front", "选错了之后回到正面")

# ---- 6. 换书 + 乱序 + seed 持久化 ----
w.open_books("welcome")
w._pick_book("gre")
w._set_order("shuffle")
w._start_learning()
check(w.book_id == "gre" and w.order_mode == "shuffle", "换到 GRE / 乱序")
check(len(w.queue_words) == 7504, "GRE 队列 %d 词" % len(w.queue_words))
seed1 = (w.orders.get("gre") or {}).get("seed")
first_shuf = w.queue_words[0]["w"]
w.save()
w2 = app_main.Card()
w2._startup(force=True)
check(w2.book_id == "gre" and w2.order_mode == "shuffle", "重启后记住书 + 乱序")
check(w2.queue_words[0]["w"] == first_shuf, "乱序 seed 稳定：%s" % first_shuf)
stop_timer()

# ---- 7. 复习跨书 ----
cel = set(bk.words("cet6"))
gre_only = next(x for x in bk.words("gre") if x not in cel)
w2.states[gre_only] = {"st": "learning", "lv": 2, "due": time.time() - 10,
                       "seen": 2, "lapse": 0, "streak": 0}
w2.open_books("welcome")
w2._pick_book("cet6")
w2._set_order("seq")
w2._start_learning()
check(w2.queue[0]["kind"] == "review" and w2.queue[0]["w"]["w"] == gre_only,
      "复习跨书：先出 %s" % gre_only)

# ---- 8. 设置页：当前词书 / 数量 ----
w2.open_settings()
check(w2.mode == "settings", "齿轮 -> 设置页")
check(w2.lab_book.text() == bk.get("cet6")["name"], "设置页显示当前词书：%s" % w2.lab_book.text())
check("/ 5,406" in w2.lab_book_num.text(), "设置页已学/总：%s" % w2.lab_book_num.text())
check("已掌握" in w2.lab_progress.text() and "测试判定已会" in w2.lab_progress.text(),
      "设置页进度行：%s" % w2.lab_progress.text())

# ---- 9. 主题切换 ----
for key, name in th.options():
    w2.set_theme(key)
    check(w2.theme_key == key and w2.progress.get("theme") == key,
          "主题 %s（%s）已应用，背景 %s" % (name, key, w2.t["bg"]))
w2.set_theme(th.DEFAULT)

# ---- 10. 词汇量测试入口 + 历史记录 ----
w2.progress["history"] = [
    {"ts": int(time.time()) - 90 * 86400, "vocab": 5200, "right": 18, "dontknow": 9,
     "total": 50, "theta": 0.1, "se": 0.5, "baseline": True, "known": 3200, "to_learn": 12012},
    {"ts": int(time.time()) - 30 * 86400, "vocab": 7100, "right": 25, "dontknow": 6,
     "total": 50, "theta": 0.6, "se": 0.5, "baseline": False},
]
w2.save()
w2._refresh_settings()
check(w2.btn_test.isVisible() and w2.btn_test.text() in ("开始测试", "重新测试"),
      "设置页有测试入口：%s" % w2.btn_test.text())
check(w2.hist_layout.count() == 2, "历史记录列出 %d 条" % w2.hist_layout.count())
w2._open_history(1)
check(w2.mode == "result", "点历史记录 -> 结果页")
check(w2.btn_start.text() == "返回设置", "历史结果主按钮是「返回设置」")
check(len(w2.chart.points) == 2, "折线图有 %d 个点" % len(w2.chart.points))
w2._result_primary()
check(w2.mode == "settings", "返回设置")

# ---- 11. 阶梯测试：快速定位（2 连对升 2 档） ----
w2.progress["history"] = []
w2.progress.pop("theta", None)
w2.save()
w2._test_from_settings()
check(w2.mode == "quiz" and w2.quiz_state["level"] == 0, "测试从第 0 档开始")
check(len(w2.quiz_items) == 1, "逐题生成（当前 %d 题）" % len(w2.quiz_items))
for i in range(3):
    it = w2.quiz_items[w2.quiz_i]
    w2._quiz_answer(it["correct"])
    w2.quiz_timer.stop()
    if i < 2:
        w2._quiz_next()
check(w2.quiz_state["level"] == 2, "2 连对（前 8 题）-> 升 2 档，实际 %d" % w2.quiz_state["level"])
check(w2.quiz_i == 2 and len(w2.quiz_resp) == 3, "已答 %d 题" % len(w2.quiz_resp))
w2.save()

# ---- 12. 关掉重开：续测 ----
w3 = app_main.Card()
w3._startup(force=True)
check(w3.mode == "quiz" and w3.quiz_i == 2, "重开后继续第 %d 题" % (w3.quiz_i + 1))
w3.skip_test()
check(w3.progress.get("snooze_until", 0) > time.time(), "24h 内不再弹")
w3.progress.pop("snooze_until", None)

# ---- 13. 走完 50 题 -> 结果页（基准） ----
w3.progress["history"] = []
w3.progress.pop("theta", None)
w3.save()
w3.start_quiz()
w3.quiz_timer.stop()
while len(w3.quiz_resp) < app_main.QUIZ_N:
    it = w3.quiz_items[w3.quiz_i]
    if it["lvl"] <= 6:
        w3._quiz_answer(it["correct"])
    else:
        w3._quiz_answer((it["correct"] + 1) % 4)
    w3.quiz_timer.stop()
    if len(w3.quiz_resp) < app_main.QUIZ_N:
        w3._quiz_next()
w3._finish_quiz()
check(w3.mode == "result", "测完 -> 结果页")
check(w3.btn_start.text() == "继续背单词", "测试结果主按钮是「继续背单词」")
check(w3.last_test and w3.last_test[0].get("algo") == "staircase-v1", "记录测试算法版本")
check(0 < w3.last_test[0]["vocab"] <= len(w3.bank),
      "估值 %s 在 0~%s 之间" % (format(w3.last_test[0]["vocab"], ","), format(len(w3.bank), ",")))
check(w3.progress.get("theta") is not None, "基准测试写入 theta")
check(len(w3.known) > 0, "测试判定已会 %d 词" % len(w3.known))
check(w3.last_test[0]["known"] == len(w3.known), "结果页已会数与 θ 一致")
learned, known, mastered, total = w3._book_stats(w3.book_id)
check(known <= total, "词书已会 %s / %s" % (format(known, ","), format(total, ",")))
check("严谨度" in w3.res_sub.text(), "结果页有严谨度")

# ---- 14. 满 30 天再弹测试 ----
for h in w3.progress["history"]:
    h["ts"] -= 31 * 86400
w3.save()
w3._startup(force=True)
check(w3.mode == "quiz", "超过 30 天 -> 再次弹测试，实际 %s" % w3.mode)

# ---- 15. 主题完整性 ----
check(not th.missing(), "所有主题颜色齐全（缺 %s）" % (th.missing(),))
for key, t in th.THEMES.items():
    s = th.qss(t)
    check("%(" not in s and "#" in s, "主题 %s 的 QSS 渲染正常" % key)

out.append("")
out.append("全部通过 ✓" if not fails else "失败 %d 项：%s" % (len(fails), " / ".join(fails)))
io.open(os.path.join(app_main.DATA, "smoke.txt"), "w", encoding="utf-8").write("\n".join(out))
print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
