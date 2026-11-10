# -*- coding: utf-8 -*-
"""冒烟自检 v1.2：大词库 / 三级词书导航 / 全选并集 / 教材系列 / 引导 / 学习 / 设置 / 阶梯测试 / 历史。

V1.2.1：改为 ui_test_support 沙箱运行（不删/不改真实 data/progress.json、_win.json），
并补上首次选书空选择、未确认重启、标题返回槽、按钮统一、设置去掌握行等断言。
"""
import os, sys, io, json, time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], "--nottest"]

from ui_test_support import (configure_qt, Sandbox, set_nottest, new_app,
                             REAL_PROGRESS, REAL_WIN)
configure_qt("offscreen")
set_nottest(True)

from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtTest import QTest
import main as app_main
import theme as th
import books as bk
import placement as pl

app = new_app(sys.argv)
sb = Sandbox(app_main, "smoke")
sb.__enter__()
out = []
fails = []
w = sb.new_card(progress={}, show=True)


def pump(n=6):
    for _ in range(n):
        app.processEvents()


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def stop_timer(*wins):
    for x in wins:
        try:
            x.quiz_timer.stop()
        except Exception:
            pass


def series_words(group_id, series):
    """自测里独立算一遍系列并集，避免直接复用被测实现。"""
    seen, out = set(), []
    for it in bk.items(group_id):
        if (it.get("series") or "") == series:
            for word in it["words"]:
                if word not in seen:
                    seen.add(word)
                    out.append(word)
    return out


def title_pixel_size(widget):
    size = widget.fontInfo().pixelSize()
    if size < 0:
        size = widget.font().pixelSize()
    if size < 0:
        import re
        m = re.search(r"font-size:\s*(\d+)px", widget.styleSheet())
        if m:
            size = int(m.group(1))
    return size


pump()

# ---- 1. 大词库 ----
bank = w.bank
check(len(bank) >= 30000, "大词库 %s 词" % format(len(bank), ","))
check([x["w"] for x in bank] == sorted(x["w"] for x in bank), "大词库按字母序 A–Z")
check(len({x["w"] for x in bank}) == len(bank), "大词库无重复")
check(all(x.get("s") for x in bank), "每个词都有卡面释义")
lv = [0] * 15
for x in bank:
    lv[x["lvl"]] += 1
check(all(n > 0 for n in lv), "难度 15 档分布：%s" % lv)
emr = next((x for x in bank if x["w"] == "encephalomyeloradiculitis"), None)
check(emr is not None and emr["s"] == "脑脊髓神经根炎",
      "指定词释义：%s" % (emr or {}).get("s"))

# ---- 2. 三级目录数据（8 主类 / 41 分组 / 175 词书） ----
mains = bk.mains()
groups = bk.groups()
items = [it for g in groups for it in g["items"]]
bank_words = {x["w"] for x in bank}
check(len(mains) == 8, "主类 %d 个" % len(mains))
check(len(groups) == 41, "分组 %d 个" % len(groups))
check(len(items) == 183, "词书 %d 本（原175 + 8词组）" % len(items))
check(len(bk.all()) == len(groups) + len(items),
      "扁平目录 %d = %d 个并集 + %d 本词书" % (len(bk.all()), len(groups), len(items)))
check(len({b["id"] for b in bk.all()}) == len(bk.all()), "词书 id 无重复")
check(bk.DEFAULT == "cet6-dg" and bk.get("cet6")["id"] == "cet6-all",
      "旧进度兜底值 = 六级大纲；旧 id cet6 仍映射到六级并集")
check(bk.size("cet6") == bk.size("cet6-all"),
      "旧 id 兼容：cet6 -> cet6-all，%s 词" % format(bk.size("cet6"), ","))
check(bk.size("kaobo") == bk.size("kaoyan-all"),
      "旧 id 兼容：kaobo -> kaoyan-all，%s 词" % format(bk.size("kaobo"), ","))
check(bk.size("xiaoxue") == bk.size("xx-ci-all"),
      "旧 id 兼容：xiaoxue -> xx-ci-all，%s 词" % format(bk.size("xiaoxue"), ","))
check(all(b["count"] == len(b["words"]) for b in bk.all()),
      "%d 个条目 count = words 长度" % len(bk.all()))
check(all(len(b["words"]) == len(set(b["words"])) for b in bk.all()),
      "%d 个条目内无重复词" % len(bk.all()))
check(all(set(g["union"]["words"]) ==
          set().union(*(set(it["words"]) for it in g["items"])) for g in groups),
      "每个分组并集 = 各词书 words 去重并集")
check(all(g["union"]["count"] == len(set(g["union"]["words"])) for g in groups),
      "每个分组并集词数 = 去重后词数")
entry_words = {entry["w"] for entry in w.all_entries}
check(all(wd in entry_words for b in bk.all() for wd in b["words"]),
      "词书所有单词/词组都在合并词条库里")
b = bk.get("cet6-all")
check(b["path"] == ["大学", "六级"] and b["display"] == "六级词汇大全",
      "三级路径：%s" % bk.path("cet6-all"))

# ---- 3. 首次打开：Card 创建即为引导页（不再先闪学习页） ----
check(w.mode == "welcome", "首次打开 -> 引导页，实际 %s" % w.mode)
check(w.book_id is None and w.sel_book is None,
      "首次打开无默认书：book_id=%r sel_book=%r" % (w.book_id, w.sel_book))
check(w.queue == [] and w.queue_words == [],
      "首次打开不预拉词：queue=%r queue_words=%r" % (len(w.queue), len(w.queue_words)))
check(not w.progress.get("book_confirmed"), "首次打开未写 book_confirmed")
texts = [lbl.text() for lbl in w.welcome_page.findChildren(app_main.QLabel)]
check(any("测试结果会影响学习内容" in t and "自动跳过" in t for t in texts), "引导页说明")
check(any("约 5 分钟" in t and "50 题" in t for t in texts), "引导页小字：约 5 分钟 · 50 题")
check(not any(("中途可以跳过" in t) or ("之后想测" in t) for t in texts), "引导页没有多余小字")
check(th.DEFAULT == "light" and w.theme_key == "light", "默认主题为亮色")

# ---- 4. 不测了 -> 第 1 级：主类列表（空选择） ----
w.btn_welcome_skip.click()
pump(8)
check(w.mode == "books" and w.nav_level == 1,
      "不测了 -> 三级词书导航第 1 级，实际 %s/%s" % (w.mode, w.nav_level))
check(len(w.book_btns) == 8, "第 1 级列出 %d 个主类" % len(w.book_btns))
check(all(r["kind"] == "main" for r in w.nav_rows), "第 1 级每行都是主类")
check(all(m["name"] in r["text"] for m, r in zip(mains, w.nav_rows)),
      "第 1 级主类名称全部来自数据")
check(w.books_lead.text() == "选择主类", "第 1 级小字只有「选择主类」：%s" % w.books_lead.text())
check([r["text"] for r in w.nav_rows] == [m["name"] for m in mains],
      "第 1 级每行只有主类名（不显示分组数/词数）")
check(not any(("个分组" in t) or ("本词书" in t) or ("词" in t) for t in
              [r["text"] for r in w.nav_rows] + [w.books_lead.text()]),
      "第 1 级没有词书数/词数")
check(w.book_scroll.isVisible(), "第 1 级列表可滚动")
check(w.sel_book is None, "首次选书没有默认选中")
check(not any(b.property("on") == "1" for b in w.book_btns.values()),
      "首次选书没有任何行高亮")
check(not w.btn_learn.isEnabled(), "首次选书开始按钮禁用")
check(w.btn_learn.text() == "用这本开始",
      "首次选书按钮统一「用这本开始」：%r" % w.btn_learn.text())
check(w.status.text() == "", "选书页顶部不再显示已学/已会/掌握：%r" % w.status.text())
check(w.lab_book_stat.text() == "", "首次选书底部无当前书统计：%r" % w.lab_book_stat.text())
check(not w.btn_back.isVisibleTo(w), "初次主分类返回图标隐藏")
check(hasattr(w, "back_slot") and (w.back_slot.width(), w.back_slot.height()) == (22, 20),
      "返回槽保留 22×20")
check(title_pixel_size(w.page_title) == 15,
      "标题字号 15px，实际 %s" % title_pixel_size(w.page_title))
_pos = w.page_title.mapTo(w, QPoint(0, 0))
check((_pos.x(), _pos.y()) == (54, 14),
      "初始标题几何 = (54,14)，实际 %r" % ((_pos.x(), _pos.y()),))
check((w.width(), w.height()) == (520, 430),
      "窗口 520×430，实际 %r" % ((w.width(), w.height()),))
# 初次主分类的 Esc / 隐藏返回不能退出
w._page_back()
check(w.mode == "books" and w.isVisible(), "初次主分类 _page_back 不退出")
QTest.keyClick(w, Qt.Key_Escape)
check(w.mode == "books" and w.isVisible(), "初次主分类 Esc 不退出")
check(w.chip_seq.text() == "顺序" and w.chip_shuffle.text() == "乱序"
      and not hasattr(w, "chip_reverse"),
      "词序只有 顺序/乱序 两个选择（默认顺序）")

# ---- 5. 第 1 级 -> 第 2 级 -> 返回 ----
w._nav_into_main("university")
check(w.nav_level == 2 and len(w.book_btns) == len(bk.groups("university")),
      "进入大学 -> 第 2 级 %d 个分组" % len(w.book_btns))
check(w.books_lead.text() == "大学", "第 2 级小字只有主类名：%s" % w.books_lead.text())
check([r["text"] for r in w.nav_rows] == [g["name"] for g in bk.groups("university")],
      "第 2 级只显示分组名（不显示词书数/词数）")
w._nav_back()
check(w.nav_level == 1 and len(w.book_btns) == 8, "第 2 级返回键 -> 主类列表")

# ---- 6. 第 2 级 -> 第 3 级（不再有「全选」行） ----
w._nav_into_main("highschool")
check(w.nav_level == 2 and len(w.book_btns) == len(bk.groups("highschool")),
      "进入高中 -> 第 2 级列出 %d 个分组" % len(w.book_btns))
w._nav_into_group("gz-text")
gz = next(g for g in groups if g["id"] == "gz-text")
check(w.nav_level == 3 and len(w.book_btns) == len(gz["items"]),
      "教材分组第 3 级 %d 行 = %d 个分册（无全选行）" %
      (len(w.book_btns), len(gz["items"])))
check(w.books_lead.text() == "高中教材", "第 3 级小字只有分组名：%s" % w.books_lead.text())
check(w.nav_sections == ["%s · %d 册" % (app_main.series_label(s),
                                         sum(1 for it in gz["items"] if it.get("series") == s))
                         for s in gz["series"]],
      "教材分组按 series 分节：%s" % w.nav_sections)
check(gz["union"]["id"] not in w.book_btns, "第 3 级没有分组全选并集行")
check(not any("全选" in r["text"] for r in w.nav_rows), "第 3 级没有任何「全选」选项")

# ---- 7. 系列并集仍在数据/兼容层可用，但界面不展示 ----
for s in gz["series"]:
    pid = app_main.series_pseudo_id("gz-text", s)
    exp = series_words("gz-text", s)
    got = app_main.series_union_words("gz-text", s)
    check(pid not in w.book_btns and not any("本版本全选" in r["text"] for r in w.nav_rows),
          "界面不显示系列全选行：%s" % s)
    check(got == exp and len(exp) == len(set(exp)) and len(exp) > 0,
          "系列并集 %s = %d 个分册按序去重（%s 词）" %
          (s, sum(1 for it in gz["items"] if it.get("series") == s), format(len(exp), ",")))

# ---- 7b. 新大纲词书：7 本，数据正确且排在分组第一位 ----
DG = [("zhongkao", "zk-dg", "中考大纲英语词汇"),
      ("gaokao", "gk-dg", "高考大纲英语词汇"),
      ("cet4", "cet4-dg", "四级大纲英语词汇"),
      ("cet6", "cet6-dg", "六级大纲英语词汇"),
      ("kaoyan", "ky-dg", "考研大纲英语词汇"),
      ("yingzhuan", "yz-t4-dg", "专四大纲英语词汇"),
      ("yingzhuan", "yz-t8-dg", "专八大纲英语词汇")]
for gid, iid, name in DG:
    it = bk.get(iid)
    check(it["name"] == name and it["count"] == len(it["words"]) and it["count"] > 1000,
          "%s：%s 词" % (name, format(it["count"], ",")))
    g = next(g for g in groups if g["id"] == gid)
    pos = 1 if iid == "yz-t8-dg" else 0
    check(g["items"][pos]["id"] == iid, "%s 分组第 %d 本是「%s」" % (g["name"], pos + 1, name))

# ---- 7c. 小学教材命名：xx版xx（三年级起点） ----
xxg = next(g for g in groups if g["id"] == "xx-text")
check(len(xxg["items"]) == 24, "小学教材 %d 册" % len(xxg["items"]))
check(all(it["name"].endswith("（三年级起点）") for it in xxg["items"]),
      "小学教材每册都以（三年级起点）结尾")
for prefix in ("人教PEP版", "外研版", "译林版"):
    check(any(it["name"].startswith(prefix) for it in xxg["items"]),
          "小学教材有 %s 分册" % prefix)
w.open_books("welcome")
w._nav_into_main("primary")
w._nav_into_group("xx-text")
check(len(w.book_btns) == 24 and not any("全选" in r["text"] for r in w.nav_rows),
      "小学教材第 3 级 24 行、没有全选")
first_xx = w.nav_rows[0]["text"]
check("人教PEP版" in first_xx and "（三年级起点）" in first_xx and first_xx.endswith("词"),
      "小学教材首行：%s" % first_xx)

# ---- 7d. 界面点选大纲词书开始学习 ----
w.open_books("welcome")
w._nav_into_main("university")
w._nav_into_group("cet4")
rows4 = [r["text"] for r in w.nav_rows]
check(rows4[0].startswith("四级大纲英语词汇") and rows4[0].endswith("词"),
      "四级分组首行是大纲词书：%s" % rows4[0])
check("全选" not in " ".join(rows4), "四级第 3 级没有全选行")
w.book_btns["cet4-dg"].click()
check(w.sel_book == "cet4-dg", "点选四级大纲词书")
w._set_order("seq")
w._start_learning()
check(w.book_id == "cet4-dg" and len(w.queue_words) == bk.size("cet4-dg"),
      "用四级大纲开始：%s 词" % format(len(w.queue_words), ","))
check(w.queue_words[0]["w"] == bk.words("cet4-dg")[0],
      "大纲词书按源顺序从第一个词开始：%s" % w.queue_words[0]["w"])

# ---- 8. 旧并集 / 系列伪 id 仍可解析（界面不再展示，但旧进度兼容） ----
w._pick_book(gz["union"]["id"])
check(w.sel_book == gz["union"]["id"] and w.lab_book_stat.text().endswith(
      format(bk.size(gz["union"]["id"]), ",") + " 词"), "选中分组并集：%s" % w.lab_book_stat.text())
series_id = app_main.series_pseudo_id("gz-text", "人教版")
exp = series_words("gz-text", "人教版")
w._pick_book(series_id)
check(w.sel_book == series_id, "选中教材系列伪 id：%s" % series_id)
check(series_id not in bk.BY_ID, "系列并集伪 id 不写进 books.py")
check(w._book_stats(series_id)[3] == len(exp),
      "系列并集统计对象 = 当前词表（%s 词）" % format(len(exp), ","))
check(w._book_word_strs(series_id) == exp, "伪 id 解析出的词表 = 按册去重并集")
check(w._book_path(series_id) == "高中 · 高中教材 · 人教版 · 本版本全选",
      "伪 id 显示路径：%s" % w._book_path(series_id))
w._set_order("seq")
w._start_learning()
check(w.mode == "front" and w.book_id == series_id,
      "用系列并集开始学习：%s / %s" % (w.book_id, w.mode))
check(len(w.queue_words) == len(exp), "系列学习队列 %s 词" % format(len(w.queue_words), ","))
check(w.progress.get("book") == series_id, "progress[book] 保存伪 id")
check(w.queue_words[0]["w"] == exp[0], "顺序学习从系列第一个词开始：%s" % exp[0])

# ---- 9. 回到三级导航，选六级并集开始经典学习 ----
w.open_books("welcome")
check(w.nav_level == 1 and len(w.book_btns) == 8, "重新打开词书页回到第 1 级")
w._nav_into_main("university")
w._nav_into_group("cet6")
w._pick_book("cet6-all")
w._set_order("seq")
w._start_learning()
check(w.mode == "front" and w.book_id == "cet6-all" and w.order_mode == "seq",
      "顺序学习：%s / %s" % (w.book_id, w.order_mode))
check(len(w.queue_words) == bk.size("cet6-all"),
      "当前队列 %s 词" % format(len(w.queue_words), ","))
check(w.queue_words[0]["w"] == bk.words("cet6-all")[0],
      "顺序书从数据第一个词开始：%s" % w.queue_words[0]["w"])

# ---- 10. 学习：认识 / 释义 / 选错了跳下一个 ----
check(w.btn_remember.text() == w._key_caption("认识", "remember")
      and w.btn_forget.text() == w._key_caption("不认识", "forget"),
      "学习按钮是「认识 / 不认识」并附键位提示：%s / %s" % (w.btn_remember.text(), w.btn_forget.text()))
first = w.queue[w.qi]["w"]["w"]
qi0 = w.qi
w.act("remember")
check(w.mode == "back" and w.meaning.text() != "", "认识 -> 翻面有释义")
w.correct()
check(w.qi == qi0 + 1, "选错了 -> 直接跳到下一个（qi %d -> %d）" % (qi0, w.qi))
st = w.states.get(first) or {}
check(st.get("st") == "new" and st.get("lv") == 0 and st.get("lapse", 0) == 1
      and first in w.study_record["pending"],
      "新词改判仍未学习、错误计数一次并进入重现队列（lapse=%s）" % st.get("lapse"))
check(w.mode == "front", "选错了之后回到正面")

# ---- 11. 换书 + 乱序 + 持久化 ----
w.open_books("welcome")
w._nav_into_main("abroad")
w._nav_into_group("gre")
w._pick_book("gre-all")
check(w.sel_order == "seq", "选择词书默认顺序：%s" % w.sel_order)
w._set_order("shuffle")
w._start_learning()
check(w.book_id == "gre-all" and w.order_mode == "shuffle", "换到 GRE 并集 / 乱序")
check(len(w.queue_words) == bk.size("gre-all"),
      "GRE 队列 %s 词" % format(len(w.queue_words), ","))
check(sorted(x["w"] for x in w.queue_words) == sorted(bk.words("gre-all")),
      "乱序队列与词书单词集合一致（无重复/丢失）")
seed1 = (w.orders.get("gre-all") or {}).get("seed")
first_rev = w.queue_words[0]["w"]
w.save()
w2 = sb.new_card(show=True)
pump(8)
check(w2.book_id == "gre-all" and w2.order_mode == "shuffle", "重启后记住书 + 乱序")
check(w2.queue_words[0]["w"] == first_rev, "乱序首个词稳定：%s" % first_rev)
stop_timer(w, w2)

# ---- 12. 到期优先，但仅复习当前词书 ----
cel = set(bk.words("cet6-all"))
gre_only = next(x for x in bk.words("gre-all") if x not in cel)
inside = next(x for x in bk.words("cet6-all") if x != first)
w2.states[gre_only] = {"st": "learning", "lv": 2, "due": time.time() - 10,
                       "seen": 2, "lapse": 0, "streak": 0}
w2.states[inside] = {"st": "learning", "lv": 3, "due": time.time() - 5,
                     "seen": 3, "lapse": 0, "streak": 0}
w2.open_books("welcome")
w2._nav_into_main("university")
w2._nav_into_group("cet6")
w2._pick_book("cet6-all")
w2._set_order("seq")
w2._start_learning()
check(w2.queue[0]["kind"] == "review" and w2.queue[0]["w"]["w"] == inside,
      "当前书到期优先，先出 %s，不跨书出 %s" % (inside, gre_only))
check(gre_only in w2.states and all(item["w"]["w"] != gre_only for item in w2.queue),
      "外书记忆记录共享保留，但当前复习队列不纳入外书")

# ---- 13. 设置页：当前词书路径 / 数量 / 进度 ----
w2.open_settings()
check(w2.mode == "settings", "齿轮 -> 设置页")
expect_path = " · ".join(bk.get("cet6-all")["path"] + [bk.get("cet6-all")["display"]])
check(w2.lab_book.text() == expect_path, "设置页显示词书路径：%s" % w2.lab_book.text())
check("/ %s" % format(bk.size("cet6-all"), ",") in w2.lab_book_num.text(),
      "设置页已学/总：%s" % w2.lab_book_num.text())
_settings_texts = "\n".join(str(lbl.text() or "") for lbl in w2.settings_page.findChildren(QLabel))
check("已掌握" not in _settings_texts and "测试判定已会" not in _settings_texts,
      "设置页不再显示已掌握/测试判定已会")
check(hasattr(w2, "lab_progress") is False,
      "设置页已删除 lab_progress 控件")
check(getattr(w2, "size_chips", None) and len(w2.size_chips) == 3,
      "设置页提供常用窗口尺寸：%r" % sorted(getattr(w2, "size_chips", {}) or {}))
check(not hasattr(w2, "win_w") and not hasattr(w2, "win_h") and not hasattr(w2, "win_mode"),
      "设置页不再有自定义尺寸/正常小窗切换控件")
check(not hasattr(w2, "retry_combo") and w2.retry_gap == 3,
      "重现间隔固定为 3 个其它新词，不再可设置")
check(not hasattr(w2, "btn_catalog_settings"),
      "设置词书块不再放浏览词条按钮")
w2.open_books("settings")
pump(6)
check(w2.btn_catalog_books.text() == "浏览词条",
      "浏览词条入口移到词书页：%r" % w2.btn_catalog_books.text())
w2.open_settings()
pump(4)
w2.open_books("settings")
pump(6)
check(w2.mode == "books" and w2.nav_level == 1 and w2.btn_back.isVisibleTo(w2),
      "设置页「更换」-> 第 1 级，返回键可见")
check(w2.back_slot.isVisibleTo(w2) and (w2.back_slot.width(), w2.back_slot.height()) == (22, 20),
      "设置入口返回槽 22×20 仍占位")
_pos2 = w2.page_title.mapTo(w2, QPoint(0, 0))
check((_pos2.x(), _pos2.y()) == (54, 14),
      "设置入口标题几何 = (54,14)，实际 %r" % ((_pos2.x(), _pos2.y()),))
check(title_pixel_size(w2.page_title) == 15,
      "设置入口标题字号 15px，实际 %s" % title_pixel_size(w2.page_title))
check((w2.width(), w2.height()) == (520, 430),
      "设置入口窗口 520×430，实际 %r" % ((w2.width(), w2.height()),))
w2._page_back()
check(w2.mode == "settings", "第 1 级返回键（设置进入）-> 设置页")

# ---- 14. 主题切换 ----
for key, name in th.options():
    w2.set_theme(key)
    check(w2.theme_key == key and w2.progress.get("theme") == key,
          "主题 %s（%s）已应用，背景 %s" % (name, key, w2.t["bg"]))
w2.set_theme(th.DEFAULT)

# ---- 15. 词汇量测试入口 + 历史记录 ----
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
check("六级已会" in w2.res_note.text(), "结果页用分组短名：%s" % w2.res_note.text().split("\n")[-1])
w2._result_primary()
check(w2.mode == "settings", "返回设置")

# ---- 16. 阶梯测试：快速定位（2 连对升 2 档） ----
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

# ---- 17. 关掉重开：续测 ----
w3 = sb.new_card(show=True)
pump(8)
check(w3.mode == "quiz" and w3.quiz_i == 3 and len(w3.quiz_resp) == 3,
      "重开后继续未答第 %d 题且保留3条已提交答案" % (w3.quiz_i + 1))
w3.skip_test()
check(w3.progress.get("snooze_until", 0) > time.time(), "24h 内不再弹")
w3.progress.pop("snooze_until", None)

# ---- 18. 走完 50 题 -> 结果页（基准） ----
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
stop_timer(w2, w3)

# ---- 19. 周期测试：--nottest 屏蔽；去掉后满 30 天自动弹 ----
for h in w3.progress["history"]:
    h["ts"] -= 31 * 86400
w3.save()
stop_timer(w3)
w3.close()
pump(4)
set_nottest(True)
w_nt = sb.new_card(show=True)
pump(8)
check(w_nt.mode == "front", "--nottest 下周期测试被屏蔽，实际 %s" % w_nt.mode)
check(not w_nt.progress.get("quiz_session"), "--nottest 下没有生成 quiz_session")
stop_timer(w_nt)
w_nt.close()
pump(4)
set_nottest(False)
try:
    w_t = sb.new_card(show=True)
    pump(8)
    check(w_t.mode == "quiz", "去掉 --nottest 后满 30 天自动弹测试，实际 %s" % w_t.mode)
    stop_timer(w_t)
    w_t.close()
    pump(4)
finally:
    set_nottest(True)

# ---- 20. 教材系列伪 id 重启恢复（已确认用户） ----
expected_series = series_words("gz-text", "人教版")
fixture = json.loads(json.dumps(w3.progress))
fixture["book"] = series_id
fixture["book_confirmed"] = True
fixture.setdefault("cursors", {})[series_id] = 0
fixture.pop("quiz_session", None)
sb.write_progress(fixture)
w4 = sb.new_card(show=True)
pump(8)
check(w4.book_id == series_id, "重启后恢复系列并集 book id：%s" % w4.book_id)
check(len(w4.queue_words) == len(expected_series),
      "重启后系列队列 %s 词" % format(len(w4.queue_words), ","))
w4.open_settings()
check(w4.lab_book.text() == "高中 · 高中教材 · 人教版 · 本版本全选",
      "设置页显示伪 id 路径：%s" % w4.lab_book.text())
check(w4.lab_book_num.text().endswith("/ " + format(len(expected_series), ",")),
      "设置页显示伪 id 词数：%s" % w4.lab_book_num.text())
stop_timer(w4)

# ---- 21. 旧进度里的 V1.1 词书 id 自动映射（已确认用户） ----
w4.close()
fixture = sb.read_progress()
fixture["book"] = "cet6"
fixture["book_confirmed"] = True
sb.write_progress(fixture)
w5 = sb.new_card(show=True)
pump(8)
check(w5.book_id == "cet6-all", "旧 book id cet6 重启 -> cet6-all")
check(len(w5.queue_words) == bk.size("cet6-all"),
      "旧 id 映射后队列 %s 词" % format(len(w5.queue_words), ","))
w5.open_settings()
check(w5.lab_book.text() == expect_path, "旧 id 在设置页显示新路径：%s" % w5.lab_book.text())
check(w5._resolve_saved_book("kaobo") == "kaoyan-all", "旧 id kaobo 解析 -> kaoyan-all")
stop_timer(w5)

# ---- 22. 紧凑模式 356×196 / 最小化按钮不回归 ----
w5.open_books("settings")
pump(6)
w5._pick_book(w5.book_id)
w5._start_learning()
pump(6)
check(w5.mode == "front", "确认选书后继续学习 -> 正面卡片，实际 %s" % w5.mode)
w5.toggle_compact()
check(w5.compact and (w5.width(), w5.height()) == (356, 196),
      "缩小 -> %d×%d" % (w5.width(), w5.height()))
check(w5.word.isVisible() and w5.ipa.isVisible() and w5.meaning.isVisible(),
      "紧凑模式仍显示 单词/音标/释义")
check(w5.btn_min.kind == "max", "缩小后图标变成 ＋")
w5.toggle_compact()
check((not w5.compact) and (w5.width(), w5.height()) == (520, 430),
      "再点展开回 520×430")
w5._show_empty()
check(w5.word.text().startswith(w5._book_name(w5.book_id)),
      "学习页空状态显示当前词书名称：%s" % w5.word.text())

# ---- 23. 首次引导选测试：跳过 / 结束都去空选书 ----
stop_timer(w5)
w5.close()
pump(4)
sb.write_progress({})
w6 = sb.new_card(show=True)
pump(8)
check(w6.mode == "welcome", "重置隔离进度后重新进入首次引导，实际 %s" % w6.mode)
w6.btn_welcome_test.click()
pump(6)
check(w6.mode == "quiz" and w6.progress.get("quiz_from_welcome") is True,
      "引导里点测试 -> 进入测试，并记下来源")
w6.skip_test()
pump(8)
check(w6.mode == "books" and w6.nav_level == 1 and not w6.progress.get("quiz_from_welcome"),
      "跳过首次测试 -> 直接进词书选择（第 1 级）")
check(w6.sel_book is None and not w6.btn_learn.isEnabled(),
      "跳过首次测试后是空选书（无默认选择、按钮禁用）")
check(not w6.progress.get("book_confirmed"), "跳过首次测试不算确认书")
stop_timer(w6)
w6.close()
pump(4)

sb.write_progress({})
w6b = sb.new_card(show=True)
pump(8)
check(w6b.mode == "welcome", "再次重置 -> 首次引导")
w6b.btn_welcome_test.click()
pump(6)
w6b.quiz_timer.stop()
while len(w6b.quiz_resp) < app_main.QUIZ_N:
    it = w6b.quiz_items[w6b.quiz_i]
    w6b._quiz_answer(it["correct"] if it["lvl"] <= 6 else (it["correct"] + 1) % 4)
    w6b.quiz_timer.stop()
    if len(w6b.quiz_resp) < app_main.QUIZ_N:
        w6b._quiz_next()
w6b._finish_quiz()
check(w6b.mode == "result", "走完首次测试 -> 结果页")
check(w6b.btn_start.text() == "选择词书" and w6b.result_ctx == "welcome_test",
      "首次测试结果主按钮是「选择词书」")
w6b._result_primary()
pump(8)
check(w6b.mode == "books" and w6b.nav_level == 1, "首次测试结束 -> 词书选择（第 1 级）")
check(w6b.sel_book is None and not w6b.btn_learn.isEnabled(),
      "首次测试结束也是空选书（无默认选择、按钮禁用）")
check(not w6b.progress.get("book_confirmed"), "首次测试结束不算确认书")
stop_timer(w6b)
w6b.close()

# ---- 24. 主题完整性 ----
check(not th.missing(), "所有主题颜色齐全（缺 %s）" % (th.missing(),))


def _lum(hexcol):
    c = hexcol.lstrip("#")
    ch = [int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def f(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(ch[0]) + 0.7152 * f(ch[1]) + 0.0722 * f(ch[2])


g = th.get("green")
_lg, _lf = _lum(g["bg"]), _lum(g["fg_mean"])
check(_lg > 0.6, "护眼绿是浅色纸感底：%s" % g["bg"])
check((max(_lg, _lf) + 0.05) / (min(_lg, _lf) + 0.05) >= 7,
      "护眼绿正文对比度 %.1f:1（≥7）" % ((max(_lg, _lf) + 0.05) / (min(_lg, _lf) + 0.05)))
for key, t in th.THEMES.items():
    s = th.qss(t)
    check("%(" not in s and "#" in s, "主题 %s 的 QSS 渲染正常" % key)

sb.__exit__(None, None, None)
rc = sb.finish(out, fails, "smoke.txt")
sys.exit(rc)
