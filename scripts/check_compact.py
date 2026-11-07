# -*- coding: utf-8 -*-
"""布局自检：缩小/展开两档的字号、留白、控件是否够放、齿轮图标是否画出来。

结果写到 data/_layout.txt（控制台是 GBK，别直接 print 中文）。
"""
import os, sys, io, json, time, re

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
sys.argv = [sys.argv[0], "--nottest"]          # main 里读的是 sys.argv

from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontMetrics
import main as app_main

prog = os.path.join(app_main.DATA, "progress.json")
if os.path.exists(prog):
    os.remove(prog)

app = QApplication(sys.argv)
w = app_main.Card()
w.show()
pump = lambda n=6: [app.processEvents() for _ in range(n)]
pump()

words = json.load(io.open(os.path.join(app_main.DATA, "words.json"), encoding="utf-8"))

out, fails = [], []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def load(word):
    w.queue = [{"kind": "new", "w": word, "st": None, "idx": 0}]
    w.qi = 0
    w._show_current()
    pump(4)


def longest_meaning():
    """按实际宽度算：谁的释义折行后最高。"""
    best, best_h = words[0], 0
    for x in words:
        lab = QLabel(x.get("s") or "")
        lab.setFont(w.meaning.font())
        lab.setWordWrap(True)
        h = lab.heightForWidth(text_width())
        if h > best_h:
            best, best_h = x, h
    return best, best_h


def text_width():
    i = 1 if w.compact else 0
    return (app_main.COMPACT_W if w.compact else app_main.CARD_W) - 2 * app_main.MARGINS[i][0]


for compact, tag in ((True, "缩小"), (False, "展开")):
    w.set_compact(compact)
    pump()
    exp_w, exp_h = (app_main.COMPACT_W, app_main.COMPACT_H) if compact \
        else (app_main.CARD_W, app_main.CARD_H)
    out.append("[%s] 窗口 %d×%d（期望 %d×%d）" % (tag, w.width(), w.height(), exp_w, exp_h))
    check((w.width(), w.height()) == (exp_w, exp_h), "窗口尺寸")

    # 最长的释义（按折行后的高度挑）
    long_word, need = longest_meaning()
    load(long_word)
    w.act("remember")                        # 翻面：释义可见
    for _ in range(120):                     # 等淡入动画（190ms）走完
        app.processEvents()
        if w.answer_effect.opacity() > 0.99:
            break
        time.sleep(0.01)
    pump(2)
    check(w.ipa.isVisible() and w.ipa.text() != "", "音标可见：%s" % w.ipa.text())
    check(w.meaning.isVisible() and w.meaning.text() != "",
          "释义可见：%s（折行需要 %dpx）" % (w.meaning.text(), need))
    check(need <= w.meaning.height(),
          "释义不被截：需要 %dpx / 实际 %dpx" % (need, w.meaning.height()))
    check(need <= app_main.mean_h(1 if compact else 0),
          "预留行高够用：需要 %dpx / 预留 %dpx" % (need, app_main.mean_h(1 if compact else 0)))

    bar_top = w.front_bar.mapTo(w, w.front_bar.rect().topLeft()).y()
    mean_bot = w.meaning.mapTo(w, w.meaning.rect().bottomLeft()).y()
    check(mean_bot < bar_top, "释义底 %d < 按钮顶 %d" % (mean_bot, bar_top))
    w.grab().save(os.path.join(app_main.DATA, "_layout_%s_longmean.png"
                               % ("compact" if compact else "normal")))

    if compact:
        check(not w.btn_gear.isVisible(), "小窗隐藏齿轮")
        check(w.btn_min.kind == "max", "小窗图标为 ＋")
    else:
        check(w.btn_gear.isVisible(), "大窗显示齿轮")
        check(w.btn_min.kind == "min", "大窗图标为 —")

    # 长单词不超出窗口
    load(max(words, key=lambda x: len(x["w"])))
    pump(4)
    check(w.word.width() <= w.width(), "长词宽度 %d ≤ 窗口 %d" % (w.word.width(), w.width()))
    out.append("       长词：%s" % w.word.text())
    tag_f = "compact" if compact else "normal"
    w.grab().save(os.path.join(app_main.DATA, "_layout_%s_front.png" % tag_f))

    # 正面 → 翻面：位置不能动，答案要淡入到全不透明
    top_before = w.meaning.mapTo(w, w.meaning.rect().topLeft()).y()
    w.act("remember")
    for _ in range(120):                       # 等淡入动画（190ms）走完
        app.processEvents()
        if w.answer_effect.opacity() > 0.99:
            break
        time.sleep(0.01)
    pump(2)
    w.grab().save(os.path.join(app_main.DATA, "_layout_%s_back.png" % tag_f))
    y_back = w.meaning.mapTo(w, w.meaning.rect().topLeft()).y()
    check(y_back == top_before, "翻面 位置一致（%d vs %d）" % (y_back, top_before))
    check(abs(w.answer_effect.opacity() - 1.0) < 0.01,
          "答案淡入到不透明（%.2f）" % w.answer_effect.opacity())
    check(w.front_bar.height() == w.back_bar.height(),
          "两个按钮条等高 %d / %d" % (w.front_bar.height(), w.back_bar.height()))
    w._show_current()
    pump(4)
    y_front = w.meaning.mapTo(w, w.meaning.rect().topLeft()).y()
    check(y_front == top_before, "回到正面 位置一致（%d vs %d）" % (y_front, top_before))
    check(w.answer_effect.opacity() < 0.01,
          "回到正面答案已隐藏（%.2f）" % w.answer_effect.opacity())
    out.append("")

# ---------- 释义条数：一条卡面最多 2 个释义；2 个词性时每个词性只 1 个 ----------
POS_RE = re.compile(r"(?:^|[；，、\s])(n|v|vt|vi|adj|adv|prep|pron|conj|num|art|int|aux|abbr|det|modal)\.")
out.append("[释义] 共 %d 词" % len(words))
n_bad = n_two_pos = 0
longest = max(words, key=lambda x: len(x.get("s") or ""))
for x in words:
    s = x.get("s") or ""
    parts = [p for p in s.split("；") if p.strip()]
    if ";" in s or len(parts) > 2:
        n_bad += 1
        if n_bad <= 5:
            out.append("   超 2 个：%s | %s" % (x["w"], s))
    if len(POS_RE.findall(s)) >= 2:
        n_two_pos += 1
        if len(parts) > 2:
            n_bad += 1
out.append("  含半角 ; 或多于 2 个释义的词：%d" % n_bad)
out.append("  两个词性的词：%d（每个 1 个释义）" % n_two_pos)
out.append("  最长释义：%s | %s" % (longest["w"], longest["s"]))
check(n_bad == 0, "每条卡面最多 2 个释义（违规 %d 词）" % n_bad)

# ---------- 图标：横线 / 加号 / 齿轮，同一条笔，内部透明 ----------
w.set_compact(False)
pump()
img = w.grab().toImage()
bg = img.pixelColor(4, w.height() // 2).getRgb()[:3]
out.append("卡片底色 rgb=%s" % (bg,))


def ink(btn):
    tl = btn.mapTo(w, btn.rect().topLeft())
    darkest, n = None, 0
    for y in range(btn.height()):
        for x in range(btn.width()):
            r, g, b = img.pixelColor(tl.x() + x, tl.y() + y).getRgb()[:3]
            d = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            if d > 40:
                n += 1
                if darkest is None or d > darkest[0]:
                    darkest = (d, (r, g, b), x, y)
    return n, (darkest[1] if darkest else None), tl


n_min, col_min, tl_min = ink(w.btn_min)
n_gear, col_gear, tl_gear = ink(w.btn_gear)
gcx, gcy = tl_gear.x() + w.btn_gear.width() / 2, tl_gear.y() + w.btn_gear.height() / 2


def dist(fx, fy):
    r, g, b = img.pixelColor(int(round(fx)), int(round(fy))).getRgb()[:3]
    return max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2])), (r, g, b)


body_d, body = dist(gcx + 3, gcy)      # 齿盘内圈（有齿也没关系，这里是空的）
hole_d, hole = dist(gcx, gcy)          # 中心孔
out.append("「—」描边像素 %d 个，最深颜色 %s" % (n_min, col_min))
out.append("齿轮描边像素 %d 个，最深颜色 %s" % (n_gear, col_gear))
out.append("齿轮内部：中心 %s ／ 齿盘内圈 %s（跟底色差 %d / %d）" % (hole, body, hole_d, body_d))
check(n_min > 5 and n_gear > 5, "两个图标都画出了线条")
check(col_min == col_gear, "描边颜色完全一致：%s" % (col_min,))
check(body_d <= 40 and hole_d <= 60, "齿轮内部透明（不填色）")
solid = (w.btn_gear.width() * w.btn_gear.height()) * 0.4
check(n_gear < solid, "齿轮是空心线框而不是实心块（描边像素 %d < %.0f）" % (n_gear, solid))

for name, btn in (("min", w.btn_min), ("gear", w.btn_gear)):
    tl = btn.mapTo(w, btn.rect().topLeft())
    w.grab().copy(tl.x() - 3, tl.y() - 3, btn.width() + 6, btn.height() + 6).scaled(
        (btn.width() + 6) * 8, (btn.height() + 6) * 8,
        Qt.KeepAspectRatio, Qt.SmoothTransformation).save(
        os.path.join(app_main.DATA, "_layout_icon_%s.png" % name))
out.append("放大图：_layout_icon_min.png / _layout_icon_gear.png（8 倍）")

out.append("")
out.append("全部通过 ✓" if not fails else "失败 %d 项：%s" % (len(fails), " / ".join(fails)))
io.open(os.path.join(app_main.DATA, "_layout.txt"), "w", encoding="utf-8").write("\n".join(out))
print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
