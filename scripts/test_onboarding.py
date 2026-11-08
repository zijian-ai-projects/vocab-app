# -*- coding: utf-8 -*-
"""V1.2.1 首次引导 / 选书 / 启动流程回归测试（隔离沙箱）。

覆盖 Lead 的需求：
  1. Card 创建（show 前）初始模式正确，不先闪学习页，也不预拉新词；
  2. 首次选书 sel_book=None、开始按钮禁用、无选中行；初次主分类无返回且 Esc/返回不能退出；
     子层有返回；设置入口的主分类有返回；标题 15px 与 22×20 返回槽保留；
  3. 选书页顶部不再显示 已学/已会/已掌握；
  4. 选中书按钮统一「用这本开始」；
  5. 未点「用这本开始」关闭重启仍停在选书页；点过才算 book_confirmed；
  6. 首测中断优先续测；首测完成/跳过进空选书；
  7. 设置页不再有「已掌握 / 测试判定已会」；
  8. 老 progress 迁移：有学习证据的保留；纯历史/默认六级占位记录仍进待选书；
  9. --nottest 只屏蔽周期测试，不跳过首次引导。

真实 data/progress.json、data/_win.json 由 ui_test_support.Sandbox 保护，不会被删/改。
"""
import os
import sys
import io
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from ui_test_support import (configure_qt, Sandbox, set_nottest, new_app,
                             REAL_PROGRESS, REAL_WIN)

configure_qt("offscreen")
set_nottest(True)

from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtTest import QTest

import main as app_main
import books as bk
import theme as th

app = new_app(sys.argv)
out = []
fails = []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def pump(n=10):
    for _ in range(n):
        app.processEvents()


def stop(w):
    try:
        w.quiz_timer.stop()
    except Exception:
        pass


def close_card(w):
    stop(w)
    try:
        w.close()
    except Exception:
        pass


def close_cards(sb):
    for w in list(sb.cards):
        close_card(w)
    sb.cards = []
    pump(4)


def scenario(sb, name, fn):
    """单个场景出错不拖垮整套测试；失败信息写进报告。"""
    try:
        fn(sb)
    except Exception as e:
        check(False, "%s：异常 %r" % (name, e))
    finally:
        close_cards(sb)


def recent_history():
    return [{"ts": int(time.time()) - 86400, "vocab": 5000, "right": 20, "dontknow": 8,
             "total": 50, "theta": 0.2, "se": 0.5, "baseline": True,
             "known": 3000, "to_learn": 10000, "rigor": 90, "err": 10,
             "lo": 4500, "hi": 5500}]


def confirmed_progress(book="cet4-dg", confirmed=True, evidence=True):
    """一个“已有用户”的进度：默认带学习证据；confirmed=False 用于迁移测试。"""
    p = {
        "welcome_done": True,
        "book": book,
        "states": {},
        "cursors": {book: 1},
        "orders": {book: {"mode": "seq", "seed": 12345}},
        "history": recent_history(),
        "theme": "light",
    }
    if evidence:
        p["states"] = {"survey": {"st": "learning", "lv": 1,
                                  "due": time.time() + 3600, "seen": 1,
                                  "lapse": 0, "streak": 1}}
    if confirmed:
        p["book_confirmed"] = True
    return p


def find_book(group_id, book_id):
    for it in bk.items(group_id):
        if it["id"] == book_id:
            return True
    return False


def pick_book_via_ui(w, book_id):
    """通过真实按钮点击从第 1 级走到目标词书并选中它。"""
    if w.mode != "books":
        w.open_books("welcome")
        pump(4)
    target = None
    for m in bk.mains():
        for g in m["groups"]:
            for it in g["items"]:
                if it["id"] == book_id:
                    target = (m["id"], g["id"])
                    break
            if target:
                break
        if target:
            break
    if not target:
        raise AssertionError("找不到词书 %s" % book_id)
    w.book_btns[target[0]].click()
    pump(4)
    w.book_btns[target[1]].click()
    pump(4)
    w.book_btns[book_id].click()
    pump(4)
    return w


def label_texts(widget):
    return [str(lbl.text() or "") for lbl in widget.findChildren(QLabel)]


def title_pixel_size(widget):
    """QSS font-size 在 polish 之前 fontInfo() 可能返回 -1，兼容读样式表。"""
    size = widget.fontInfo().pixelSize()
    if size < 0:
        size = widget.font().pixelSize()
    if size < 0:
        import re
        m = re.search(r"font-size:\s*(\d+)px", widget.styleSheet())
        if m:
            size = int(m.group(1))
    return size


def first_item(group_id):
    its = bk.items(group_id)
    if not its:
        raise AssertionError("分组 %s 没有词书" % group_id)
    return its[0]["id"]


def no_forbidden_settings(w):
    texts = label_texts(w.settings_page)
    joined = "\n".join(texts)
    has = ("已掌握" in joined) or ("测试判定已会" in joined)
    check(not has, "设置页不存在「已掌握 / 测试判定已会」：%s" % joined.replace("\n", " | "))


# ======================================================================
# 1. Card 创建（show 前）初始状态：welcome、不预拉词、无书
# ======================================================================
def t_fresh_start(sb):
    w = sb.new_card(progress={}, show=False)
    check(w.mode == "welcome", "fresh Card 创建后即为 welcome（未先闪学习页），实际 %s" % w.mode)
    check(getattr(w, "book_id", "MISSING") is None,
          "fresh book_id is None，实际 %r" % getattr(w, "book_id", "MISSING"))
    check(getattr(w, "sel_book", "MISSING") is None,
          "fresh sel_book is None，实际 %r" % getattr(w, "sel_book", "MISSING"))
    check(getattr(w, "queue", None) == [], "show 前 queue 未被预拉：%r" % getattr(w, "queue", None))
    check(getattr(w, "queue_words", None) == [],
          "show 前 queue_words 为空：%r" % getattr(w, "queue_words", None))
    check(getattr(w, "book_words", None) == [],
          "fresh book_words 为空：%r" % getattr(w, "book_words", None))
    check(not w.progress.get("book"), "fresh progress 里没有 book：%r" % w.progress.get("book"))
    check(not w.progress.get("book_confirmed"), "fresh progress 里没有 book_confirmed")
    check(w.progress.get("welcome_done") in (None, False),
          "fresh welcome_done 未提前写成 True：%r" % w.progress.get("welcome_done"))
    check(w._test_show_deferred, "首次创建用 show 拦截，检查的是 show 前状态")
    check(w._test_first_show_mode == "welcome",
          "第一次 show 的瞬间就是 welcome，实际 %r" % w._test_first_show_mode)
    check(w._test_first_show_book is None,
          "第一次 show 时 book_id=None，实际 %r" % (w._test_first_show_book,))
    check(w._test_first_show_queue_len == 0,
          "第一次 show 时 queue 长度 0，实际 %d" % w._test_first_show_queue_len)
    check(w._test_first_show_queue_words_len == 0,
          "第一次 show 时 queue_words 长度 0，实际 %d" % w._test_first_show_queue_words_len)
    check(not w.stage.isVisibleTo(w), "show 前学习区不可见")
    check(w.word.text() == "", "show 前没有预填单词：%r" % w.word.text())
    check(w.welcome_page.isVisibleTo(w), "show 前欢迎页已设为当前页")
    sb.show(w)
    pump(8)
    check(w.mode == "welcome", "show 后仍停在欢迎页，实际 %s" % w.mode)


# ======================================================================
# 2. 首次选书：空选择 / 禁用 / 无顶部统计 / 标题与返回槽
# ======================================================================
def t_first_books(sb):
    w = sb.new_card(progress={}, show=True)
    pump(8)
    w.btn_welcome_skip.click()
    pump(8)
    check(w.mode == "books" and w.nav_level == 1,
          "不测了 -> books 第 1 级，实际 %s/%s" % (w.mode, w.nav_level))
    check(w.sel_book is None, "首次选书 sel_book is None，实际 %r" % w.sel_book)
    check(not w.btn_learn.isEnabled(), "首次选书「开始」按钮禁用")
    check(w.btn_learn.text() == "用这本开始",
          "首次选书按钮文案统一「用这本开始」：%r" % w.btn_learn.text())
    check(w.status.text() == "", "选书页顶部不再显示统计：%r" % w.status.text())
    check(not any(b.property("on") == "1" for b in w.book_btns.values()),
          "首次选书没有任何行处于选中态")
    check(hasattr(w, "back_slot") and w.back_slot.width() == 22 and w.back_slot.height() == 20,
          "返回槽固定 22×20：%r" % ((getattr(w, "back_slot", None) and
                                     (w.back_slot.width(), w.back_slot.height())),))
    check(not w.btn_back.isVisibleTo(w), "初次主分类返回图标隐藏")
    check(title_pixel_size(w.page_title) == 15,
          "标题字号 15px，实际 %s" % title_pixel_size(w.page_title))
    pos = w.page_title.mapTo(w, QPoint(0, 0))
    check((pos.x(), pos.y()) == (54, 14),
          "初始标题几何 = (54,14)，实际 %r" % ((pos.x(), pos.y()),))
    check((w.width(), w.height()) == (520, 430),
          "窗口 520×430，实际 %r" % ((w.width(), w.height()),))

    # 禁用状态下点开始：不能进学习，不能写 book_confirmed
    w.btn_learn.click()
    pump(4)
    check(w.mode == "books" and not w.progress.get("book_confirmed"),
          "无选择时点开始不进入学习、不写 book_confirmed")

    # Esc / 隐藏返回 / _page_back 都不能退出初次主分类
    w._page_back()
    pump(4)
    check(w.mode == "books" and w.isVisible(), "初次主分类 _page_back 不退出")
    QTest.keyClick(w, Qt.Key_Escape)
    pump(4)
    check(w.mode == "books" and w.isVisible(), "初次主分类 Esc 不退出")
    w.btn_back.click()
    pump(4)
    check(w.mode == "books" and w.isVisible(), "初次主分类点隐藏返回槽不退出")

    # 子层有返回
    w._nav_into_main("university")
    pump(4)
    check(w.nav_level == 2 and w.btn_back.isVisibleTo(w), "第 2 级有返回图标")
    w._nav_back()
    pump(4)
    check(w.nav_level == 1 and not w.btn_back.isVisibleTo(w),
          "回到初次主分类后返回图标再次隐藏")


def t_settings_entry_geometry(sb):
    """设置入口进入选书页：返回图标可见，标题几何与初次主分类完全一致。"""
    prog = confirmed_progress("cet4-dg", confirmed=True)
    w = sb.new_card(progress=prog, show=True)
    pump(8)
    w.open_settings()
    pump(6)
    w.open_books("settings")
    pump(8)
    check(w.mode == "books" and w.nav_level == 1, "settings 入口 -> books 第 1 级")
    check(w.btn_back.isVisibleTo(w), "settings 入口主分类返回图标可见")
    check(w.back_slot.isVisibleTo(w) and (w.back_slot.width(), w.back_slot.height()) == (22, 20),
          "settings 入口返回槽 22×20 仍占位")
    pos = w.page_title.mapTo(w, QPoint(0, 0))
    check((pos.x(), pos.y()) == (54, 14),
          "settings 入口标题几何 = (54,14)，实际 %r" % ((pos.x(), pos.y()),))
    check(title_pixel_size(w.page_title) == 15,
          "settings 入口标题仍 15px，实际 %s" % title_pixel_size(w.page_title))
    check((w.width(), w.height()) == (520, 430),
          "settings 入口窗口 520×430，实际 %r" % ((w.width(), w.height()),))
    w._page_back()
    pump(6)
    check(w.mode == "settings", "settings 入口主分类返回 -> 设置页，实际 %s" % w.mode)


# ======================================================================
# 3. 选择但未点「用这本开始」：不算确认；重启仍在选书页
# ======================================================================
def t_unconfirmed_restart(sb):
    w = sb.new_card(progress={}, show=True)
    pump(6)
    w.btn_welcome_skip.click()
    pump(6)
    target = first_item("cet4")
    pick_book_via_ui(w, target)
    check(w.sel_book == target, "点选词书：%s" % target)
    check(w.btn_learn.isEnabled(), "选中后开始按钮启用")
    check(w.btn_learn.text() == "用这本开始",
          "选中后按钮仍统一「用这本开始」：%r" % w.btn_learn.text())
    check(sum(1 for b in w.book_btns.values() if b.property("on") == "1") == 1,
          "选中行恰好一个高亮")
    check(not w.progress.get("book_confirmed"), "只点选不写 book_confirmed")
    check(not w.progress.get("book"), "只点选不写 progress[book]：%r" % w.progress.get("book"))
    w.close()
    pump(4)

    w2 = sb.new_card(show=True)
    pump(8)
    check(w2.mode == "books" and w2.nav_level == 1,
          "未确认关闭重启 -> 选书页第 1 级，实际 %s/%s" % (w2.mode, w2.nav_level))
    check(w2.sel_book is None, "重启后仍没有默认选中")
    check(not w2.btn_learn.isEnabled(), "重启后开始按钮仍禁用")
    check(not w2.progress.get("book_confirmed"), "重启后仍无 book_confirmed")


# ======================================================================
# 4. 点「用这本开始」：book_confirmed 写入；重启进学习
# ======================================================================
def t_confirm_and_restart(sb):
    w = sb.new_card(progress={}, show=True)
    pump(6)
    w.btn_welcome_skip.click()
    pump(6)
    target = first_item("cet4")
    pick_book_via_ui(w, target)
    w.btn_learn.click()
    pump(8)
    check(w.mode == "front", "点「用这本开始」-> 学习页，实际 %s" % w.mode)
    check(w.book_id == target, "确认后 book_id = %s，实际 %r" % (target, w.book_id))
    check(w.progress.get("book_confirmed") is True, "确认后 progress[book_confirmed]=True")
    check(w.progress.get("book") == target,
          "确认后 progress[book]=%s，实际 %r" % (target, w.progress.get("book")))
    check(bool(w.queue) or w.word.text() != "", "确认后学习队列/当前词已就绪")
    w.close()
    pump(4)

    w2 = sb.new_card(show=True)
    pump(8)
    check(w2.mode == "front", "已确认用户重启直接进学习页，实际 %s" % w2.mode)
    check(w2.book_id == target, "已确认用户重启保留上次书：%r" % w2.book_id)
    check(w2.progress.get("book_confirmed") is True, "重启后 book_confirmed 保留")


# ======================================================================
# 5. 首测中断 -> 重启优先续测；跳过 -> 空选书
# ======================================================================
def t_quiz_resume_and_skip(sb):
    w = sb.new_card(progress={}, show=True)
    pump(6)
    w.btn_welcome_test.click()
    pump(6)
    check(w.mode == "quiz", "首次引导点测试 -> quiz，实际 %s" % w.mode)
    for i in range(3):
        it = w.quiz_items[w.quiz_i]
        w._quiz_answer(it["correct"])
        w.quiz_timer.stop()
        if i < 2:
            w._quiz_next()
    w.save()
    check(w.progress.get("quiz_session") is not None, "中断时保存 quiz_session")
    w.close()
    pump(4)

    w2 = sb.new_card(show=True)
    pump(8)
    check(w2.mode == "quiz", "重启后优先续测，实际 %s" % w2.mode)
    check(w2.quiz_i == 2, "续测题号保持：%d" % w2.quiz_i)
    check(w2.book_id is None, "续测时仍无已确认书")
    w2.skip_test()
    pump(8)
    check(w2.mode == "books" and w2.nav_level == 1,
          "首测跳过 -> 空选书页第 1 级，实际 %s/%s" % (w2.mode, w2.nav_level))
    check(w2.sel_book is None, "首测跳过后不默认选书")
    check(not w2.progress.get("book_confirmed"), "首测跳过后未确认书")
    w2.close()
    pump(4)
    w3 = sb.new_card(show=True)
    pump(8)
    check(w3.mode == "books", "首测跳过关闭重启 -> 仍在选书页，实际 %s" % w3.mode)


# ======================================================================
# 6. 首测完成 -> 结果页 -> 空选书
# ======================================================================
def t_quiz_complete_to_books(sb):
    w = sb.new_card(progress={}, show=True)
    pump(6)
    w.btn_welcome_test.click()
    pump(6)
    w.quiz_timer.stop()
    while len(w.quiz_resp) < app_main.QUIZ_N:
        it = w.quiz_items[w.quiz_i]
        w._quiz_answer(it["correct"] if it["lvl"] <= 6 else (it["correct"] + 1) % 4)
        w.quiz_timer.stop()
        if len(w.quiz_resp) < app_main.QUIZ_N:
            w._quiz_next()
    w._finish_quiz()
    check(w.mode == "result", "首测完成 -> 结果页，实际 %s" % w.mode)
    w._result_primary()
    pump(8)
    check(w.mode == "books" and w.nav_level == 1,
          "首测完成继续 -> 空选书页，实际 %s/%s" % (w.mode, w.nav_level))
    check(w.sel_book is None, "首测完成后不默认选书")
    check(not w.progress.get("book_confirmed"), "首测完成不写 book_confirmed")
    w.close()
    pump(4)
    w2 = sb.new_card(show=True)
    pump(8)
    check(w2.mode == "books", "首测完成重启 -> 选书页，实际 %s" % w2.mode)


# ======================================================================
# 7. 设置页：去掌握/测试判定行；老用户保留路径与已学；空书显示未选择
# ======================================================================
def t_settings(sb):
    prog = confirmed_progress("cet4-dg", confirmed=True)
    w = sb.new_card(progress=prog, show=True)
    pump(8)
    w.open_settings()
    pump(6)
    check(w.mode == "settings", "已确认用户可进设置")
    no_forbidden_settings(w)
    check("/ %s" % format(bk.size("cet4-dg"), ",") in w.lab_book_num.text(),
          "设置页保留已学/总：%s" % w.lab_book_num.text())
    expect_path = " · ".join(bk.get("cet4-dg")["path"] + [bk.get("cet4-dg")["display"]])
    check(w.lab_book.text() == expect_path, "老用户设置页保留上次书路径：%s" % w.lab_book.text())
    w.close()
    pump(4)

    # 首次无书：真实打开设置（gear 在 books 页不可用，直接调 open_settings 验证兜底）
    w2 = sb.new_card(progress={}, show=True)
    pump(6)
    w2.open_settings()
    pump(6)
    check(w2.lab_book.text() == "未选择词书",
          "首次无书设置页显示「未选择词书」：%r" % w2.lab_book.text())
    check(w2.lab_book_num.text() == "", "首次无书设置页词数行留空：%r" % w2.lab_book_num.text())
    no_forbidden_settings(w2)


# ======================================================================
# 7b. 空书设置 + 主题刷新（_book_path(None) 回归）
# ======================================================================
def t_fresh_settings(sb):
    w = sb.new_card(progress={}, show=True)
    pump(6)
    w.open_settings()
    pump(6)
    check(w.mode == "settings", "fresh 无书也能打开设置页，实际 %s" % w.mode)
    check(w._book_path(None) == "", "空书 _book_path(None) 返回空串")
    check(w.lab_book.text() == "未选择词书",
          "空书设置页显示「未选择词书」：%r" % w.lab_book.text())
    check(w.lab_book_num.text() == "", "空书设置页已学/总留空：%r" % w.lab_book_num.text())
    for key, name in th.options():
        try:
            w.set_theme(key)
            pump(3)
            ok = (w.theme_key == key and w.lab_book.text() == "未选择词书"
                  and w.lab_book_num.text() == "")
            check(ok, "空书主题刷新（%s）不报错且保持空态" % name)
        except Exception as e:
            check(False, "空书主题刷新（%s）异常 %r" % (name, e))
    w.set_theme(th.DEFAULT)
    check(w.mode == "settings", "空书主题刷新后仍在设置页")


# ======================================================================
# 8. 选书页统一「用这本开始」/ 无顶部统计（已确认用户）
# ======================================================================
def t_books_unified_label(sb):
    prog = confirmed_progress("cet4-dg", confirmed=True)
    w = sb.new_card(progress=prog, show=True)
    pump(8)
    w.open_books("settings")
    pump(8)
    check(w.mode == "books", "设置入口进入选书页")
    check(w.status.text() == "", "已确认用户选书页顶部也无统计：%r" % w.status.text())
    check(w.btn_back.isVisibleTo(w), "设置入口主分类返回可见")
    # 选中当前书 / 换一本，文案都统一
    check(w.btn_learn.text() == "用这本开始",
          "进入选书页按钮就是「用这本开始」：%r" % w.btn_learn.text())
    other = first_item("cet6")
    pick_book_via_ui(w, other)
    check(w.btn_learn.text() == "用这本开始",
          "换选另一本后仍是「用这本开始」：%r" % w.btn_learn.text())
    check(w.btn_learn.isEnabled(), "换选后开始按钮可用")


# ======================================================================
# 9. 老 progress 迁移
# ======================================================================
def t_migration(sb):
    # 9a. v1.1 旧 id + 学习证据（states） -> 迁移为已确认，进学习页
    p = {"welcome_done": True, "book": "cet6",
         "states": {"survey": {"st": "learning", "lv": 1, "due": time.time() + 3600,
                               "seen": 1, "lapse": 0, "streak": 1}},
         "cursors": {"cet6": 2}, "orders": {"cet6": {"mode": "seq", "seed": 1}},
         "history": recent_history()}
    w = sb.new_card(progress=p, show=True)
    pump(8)
    check(w.mode == "front", "v1.1 有 states 的旧进度迁移 -> 学习页，实际 %s" % w.mode)
    check(w.book_id == "cet6-all", "旧 book cet6 -> cet6-all，实际 %r" % w.book_id)
    check(w.progress.get("book_confirmed") is True, "有证据旧进度迁移为 book_confirmed=True")
    w.open_settings()
    pump(4)
    no_forbidden_settings(w)
    w.close()
    pump(4)

    # 9b. 纯“历史/默认六级占位”记录（无 states、默认 book） -> 仍进待选书
    p = {"welcome_done": True, "book": "cet6-all", "states": {},
         "cursors": {}, "orders": {}, "history": recent_history()}
    w = sb.new_card(progress=p, show=True)
    pump(8)
    check(w.mode == "books",
          "纯历史/默认六级占位旧记录 -> 待选书（不误迁移），实际 %s" % w.mode)
    check(w.sel_book is None and not w.btn_learn.isEnabled(),
          "占位旧记录进选书页后无默认选择、按钮禁用")
    check(not w.progress.get("book_confirmed"), "占位旧记录不写 book_confirmed")
    w.close()
    pump(4)

    # 9b2. v1.2.0 真实占位 fixture：默认 cet6-dg + 游标 + shuffle seed
    for hist in ([], recent_history()):
        p = {"welcome_done": True, "book": "cet6-dg", "states": {},
             "cursors": {"cet6-dg": 1},
             "orders": {"cet6-dg": {"mode": "shuffle", "seed": 123}},
             "history": hist}
        w = sb.new_card(progress=p, show=True)
        pump(8)
        check(w.mode == "books",
              "cet6-dg 占位（history=%d 条）-> 待选书，实际 %s" %
              (len(hist), w.mode))
        check(w.book_id is None, "cet6-dg 占位迁移后 book_id=None，实际 %r" % w.book_id)
        check(w.sel_book is None and not w.btn_learn.isEnabled(),
              "cet6-dg 占位进选书页后空选择、按钮禁用")
        check(not w.progress.get("book_confirmed") and not w.progress.get("book"),
              "cet6-dg 占位不写 book/book_confirmed")
        w.close()
        pump(4)

    # 9c. 非默认已保存书（无 states） -> 视为已有选择/学习记录
    p = {"welcome_done": True, "book": "cet4-dg", "states": {},
         "cursors": {}, "orders": {}, "history": recent_history()}
    w = sb.new_card(progress=p, show=True)
    pump(8)
    check(w.mode == "front", "非默认已保存书的旧进度 -> 学习页，实际 %s" % w.mode)
    check(w.book_id == "cet4-dg", "非默认旧书保留：%r" % w.book_id)
    w.close()
    pump(4)

    # 9d. 系列伪 id + 明确 book_confirmed -> 保留
    p = {"welcome_done": True, "book": "series:gz-text:人教版",
         "book_confirmed": True, "states": {}, "cursors": {},
         "orders": {}, "history": recent_history()}
    w = sb.new_card(progress=p, show=True)
    pump(8)
    check(w.mode == "front", "系列伪 id 已确认进度 -> 学习页，实际 %s" % w.mode)
    check(w.book_id == "series:gz-text:人教版", "系列伪 id 保留：%r" % w.book_id)
    w.open_settings()
    pump(4)
    check(w.lab_book.text() == "高中 · 高中教材 · 人教版 · 本版本全选",
          "系列伪 id 设置页路径：%s" % w.lab_book.text())
    w.close()
    pump(4)

    # 9e. 很老的进度（无 welcome_done）+ states -> 迁移
    p = {"book": "cet4-dg",
         "states": {"survey": {"st": "learning", "lv": 1, "due": time.time() + 3600,
                               "seen": 1, "lapse": 0, "streak": 1}},
         "cursors": {"cet4-dg": 1}, "orders": {"cet4-dg": {"mode": "seq", "seed": 2}},
         "history": recent_history()}
    w = sb.new_card(progress=p, show=True)
    pump(8)
    check(w.mode == "front", "无 welcome_done 但有 states 的旧进度 -> 学习页，实际 %s" % w.mode)
    check(w.progress.get("welcome_done") is True, "迁移补 welcome_done=True")
    check(w.progress.get("book_confirmed") is True, "迁移补 book_confirmed=True")


# ======================================================================
# 10. --nottest 只屏蔽周期测试，不跳过首次引导
# ======================================================================
def t_nottest(sb):
    # 首次引导：带 --nottest 也必须 welcome
    w = sb.new_card(progress={}, show=True)
    pump(6)
    check(w.mode == "welcome", "--nottest 下首次打开仍进欢迎页，实际 %s" % w.mode)
    w.close()
    pump(4)

    # 已确认用户 + 31 天前历史 + --nottest：不自动弹周期测试
    p = confirmed_progress("cet4-dg", confirmed=True)
    old = recent_history()
    old[0]["ts"] -= 31 * 86400
    p["history"] = old
    set_nottest(True)
    w = sb.new_card(progress=p, show=True)
    pump(8)
    check(w.mode == "front", "--nottest 下已确认用户不自动弹周期测试，实际 %s" % w.mode)
    w.close()
    pump(4)

    # 去掉 --nottest：超过 30 天应自动弹测试
    set_nottest(False)
    try:
        w2 = sb.new_card(progress=None, show=True)   # 沿用上一条 p（已保存）
        pump(8)
        check(w2.mode == "quiz", "去掉 --nottest 后超过 30 天自动弹测试，实际 %s" % w2.mode)
    finally:
        set_nottest(True)


# ======================================================================
# 11. 标题/返回槽细节（首次与设置入口一致）
# ======================================================================
def t_title_slot(sb):
    w = sb.new_card(progress={}, show=True)
    pump(6)
    w.btn_welcome_skip.click()
    pump(6)
    x1 = w.page_title.mapTo(w, QPoint(0, 0)).x()
    fs1 = title_pixel_size(w.page_title)
    slot = getattr(w, "back_slot", None)
    check(slot is not None, "存在 back_slot 返回槽属性")
    if slot is not None:
        check((slot.width(), slot.height()) == (22, 20),
              "back_slot 尺寸 22×20：%r" % ((slot.width(), slot.height()),))
        check(slot.isVisibleTo(w), "初次主分类返回槽本身仍占位可见")
    check(fs1 == 15, "标题字号 15px：%s" % fs1)
    # 进入第 2 级再返回，标题 x 不能跳
    w._nav_into_main("university")
    pump(4)
    x2 = w.page_title.mapTo(w, QPoint(0, 0)).x()
    check(x2 == x1, "第 1/2 级标题 x 一致：%d vs %d" % (x1, x2))
    check(w.btn_back.isVisibleTo(w), "第 2 级返回图标可见")


# ======================================================================
# 主流程
# ======================================================================
def main():
    with Sandbox(app_main, "onboarding") as sb:
        before = (os.path.exists(REAL_PROGRESS), os.path.exists(REAL_WIN))
        scenario(sb, "fresh-start", t_fresh_start)
        scenario(sb, "first-books", t_first_books)
        scenario(sb, "settings-entry-geometry", t_settings_entry_geometry)
        scenario(sb, "unconfirmed-restart", t_unconfirmed_restart)
        scenario(sb, "confirm-and-restart", t_confirm_and_restart)
        scenario(sb, "quiz-resume-skip", t_quiz_resume_and_skip)
        scenario(sb, "quiz-complete-books", t_quiz_complete_to_books)
        scenario(sb, "settings", t_settings)
        scenario(sb, "fresh-settings-theme", t_fresh_settings)
        scenario(sb, "books-unified-label", t_books_unified_label)
        scenario(sb, "migration", t_migration)
        scenario(sb, "nottest", t_nottest)
        scenario(sb, "title-slot", t_title_slot)

        check((os.path.exists(REAL_PROGRESS), os.path.exists(REAL_WIN)) == before,
              "真实 data/progress.json 与 _win.json 存在性未变")
    # __exit__ 之后 errors 才齐全，再写报告
    return sb.finish(out, fails, "test_onboarding.txt")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
