# -*- coding: utf-8 -*-
"""catalog.py 性能回归：16331 词大词书只测可见行 + 长行完整换行。

运行：
  D:\software\anaconda\python.exe scripts\test_catalog.py
默认 offscreen；真实 Sandbox（只读 bank/books，不写真实 records）。
"""
import os
import sys
import io
import copy
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
WORKSPACE = os.path.dirname(APP)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(APP, "app"))

from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

configure_qt("offscreen")
set_nottest(True)

from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QFontMetrics, QColor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (QApplication, QDialog, QHeaderView, QLabel,
                             QPushButton, QAbstractItemView)

app = new_app(sys.argv)
out = []
fails = []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def pump(seconds=0.0, n=12):
    for _ in range(n):
        app.processEvents()
    if seconds:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.008)
    for _ in range(n):
        app.processEvents()


def wait_measure(catalog_widget, timeout=2.0):
    end = time.time() + timeout
    while catalog_widget._measure_timer.isActive() and time.time() < end:
        pump(0.02)
    pump(0.10)


def main():
    import main as app_main
    import catalog
    import books as bk
    import entries as entry_mod

    sb = Sandbox(app_main, "catalog")
    sb.__enter__()
    catalog_widget = None
    card = None
    try:
        bank = json.load(io.open(os.path.join(app_main.DATA, "bank.json"),
                                 encoding="utf-8"))
        bank_map = {entry["w"]: entry for entry in bank}
        words = bk.words("cgcf-all")
        entries = [bank_map[word] for word in words if word in bank_map]
        check(len(entries) == 16331, "真实最大词书 cgcf-all = %d 词" % len(entries))

        # entries 文案：待学习 / 0 · 待学习 / 10 · 已掌握 / 1-9 保留 Lv n · 认识
        check(dict(entry_mod.CATEGORIES).get("unlearned") == "待学习",
              "CATEGORIES unlearned 显示「待学习」")
        check(entry_mod.memory_info("x", {}, set()) == ("unlearned", 0, "0 · 待学习"),
              "未学习 -> 0 · 待学习")
        check(entry_mod.memory_info("x", {"x": {"st": "learning", "lv": 0, "seen": 2}},
                                    set())[2] == "0 · 待学习",
              "待重现 -> 0 · 待学习")
        check(entry_mod.memory_info("x", {"x": {"st": "learning", "lv": 3}},
                                    set()) == ("known", 3, "Lv 3 · 认识"),
              "等级1-9 -> Lv n · 认识")
        check(entry_mod.memory_info("x", {"x": {"st": "mastered", "lv": 10}},
                                    set()) == ("mastered", 10, "10 · 已掌握"),
              "等级10 -> 10 · 已掌握")
        check(entry_mod.memory_info("x", {}, {"x"}) == ("known", None, "认识 · 测试估计"),
              "测试估计仍是认识、不是真实等级")

        # 实际作答证据必须压过测试估计（与 StudyQueue._has_answer/_count 一致）
        evidence_states = {
            "seen1": {"st": "new", "lv": 0, "seen": 1},
            "lapse1": {"st": "new", "lv": 0, "lapse": 1},
            "seen0": {"st": "new", "lv": 0, "seen": 0},
            "bad": {"st": "new", "lv": 0, "seen": "x", "lapse": None},
        }
        states_before = copy.deepcopy(evidence_states)
        known_before = {"seen1", "lapse1", "seen0", "bad", "estimate"}
        known_copy = set(known_before)
        check(entry_mod.memory_info("seen1", evidence_states, known_copy)
              == ("unlearned", 0, "0 · 待学习"),
              "seen1 新词 + 测试估计 -> 0 · 待学习（估计不覆盖实际作答）")
        check(entry_mod.memory_info("lapse1", evidence_states, known_copy)
              == ("unlearned", 0, "0 · 待学习"),
              "lapse1 新词 + 测试估计 -> 0 · 待学习")
        check(entry_mod.memory_info("seen0", evidence_states, known_copy)
              == ("known", None, "认识 · 测试估计"),
              "seen0 未作答 + 测试估计 -> known,None（不伪造等级）")
        check(entry_mod.memory_info("seen0", evidence_states, set())
              == ("unlearned", 0, "0 · 待学习"),
              "seen0 未作答且无估计 -> 0 · 待学习")
        check(entry_mod.memory_info("bad", evidence_states, known_copy)
              == ("known", None, "认识 · 测试估计"),
              "seen/lapse 非法计数安全按 0 处理，不崩")
        check(evidence_states == states_before and known_copy == known_before,
              "memory_info 纯只读，不修改 states/known")
        check(len(catalog.LEVEL_LINES) == 11 and catalog.level_lines() is catalog.LEVEL_LINES,
              "等级说明只有 11 行常量")
        expect_levels = (
            "等级 0：新词",
            "等级 1：5 分钟后复习",
            "等级 2：30 分钟",
            "等级 3：12 小时",
            "等级 4：1 天",
            "等级 5：2 天",
            "等级 6：4 天",
            "等级 7：7 天",
            "等级 8：15 天",
            "等级 9：30 天",
            "等级 10：已掌握，不再出现",
        )
        check(catalog.LEVEL_LINES == expect_levels,
              "等级说明逐字对齐用户要求（2-9 不带「后复习」）")
        check(catalog.LEVEL_LINES[0] == "等级 0：新词"
              and catalog.LEVEL_LINES[-1] == "等级 10：已掌握，不再出现",
              "等级说明首尾文案正确")
        check(("旧词" not in catalog.LEVEL_TEXT) and ("不记得" not in catalog.LEVEL_TEXT),
              "等级说明不再写升降级规则长文")

        catalog_widget = catalog.BookCatalog()
        catalog_widget.resize(900, 600)
        catalog_widget.show()
        pump(0.05)

        # Model meaning 只 format 一次（搜索/DisplayRole 不再调用 meaning）
        calls = []

        def _count_meaning(entry):
            calls.append(entry["w"])
            return "缓存释义：" + entry["w"]

        old_meaning = catalog.meaning
        catalog.meaning = _count_meaning
        try:
            t0 = time.perf_counter()
            catalog_widget.set_book("cgcf-all", "实用 · 词根词缀 · 英语词汇的奥秘",
                                    entries, {}, set())
            set_book_s = time.perf_counter() - t0
        finally:
            catalog.meaning = old_meaning
        pump(0.10)
        check(set_book_s < 2.0, "16331 项 set_book %.3fs < 2s" % set_book_s)
        check(len(calls) == len(entries),
              "set_entries 对 %d 项各 format meaning 一次（实际 %d）" %
              (len(entries), len(calls)))
        check(catalog_widget.model.rowCount() == len(entries),
              "model rowCount = %d" % catalog_widget.model.rowCount())
        check(catalog_widget.table.verticalHeader().sectionResizeMode(0) == QHeaderView.Fixed,
              "垂直表头 Fixed（不再 ResizeToContents）")
        check(catalog_widget.table.horizontalHeader().sectionResizeMode(2) == QHeaderView.Fixed,
              "记忆等级列 Fixed（不再 ResizeToContents）")
        check(catalog_widget.table.verticalHeader().defaultSectionSize() == 48,
              "默认行高 48：%d" % catalog_widget.table.verticalHeader().defaultSectionSize())
        check(catalog_widget.table.verticalHeader().minimumSectionSize() == 48,
              "最小行高 48：%d" % catalog_widget.table.verticalHeader().minimumSectionSize())
        check(catalog_widget.table.textElideMode() == Qt.ElideNone, "ElideNone 保留完整换行")
        check(catalog_widget.table.verticalScrollMode() == QAbstractItemView.ScrollPerPixel,
              "垂直滚动 ScrollPerPixel（允许长行超视口）")

        initial_calls = catalog_widget.measure_calls
        initial_measured = catalog_widget.measured_rows
        check(initial_calls <= 3, "setBook 后仅合并测量 %d 次（不是全书）" % initial_calls)
        check(initial_measured <= 64,
              "首屏仅测可见+buffer %d 行（book 16331）" % initial_measured)
        check(initial_calls < len(entries),
              "没有遍历全书测量：measure_calls %d << %d" % (initial_calls, len(entries)))

        # 表头/等级 Tooltip 不再暗示可点击弹窗
        check(catalog_widget.model.headerData(2, Qt.Horizontal, Qt.DisplayRole)
              == "记忆等级",
              "表头为纯「记忆等级」且无 ⓘ")
        tip = catalog_widget.model.data(catalog_widget.model.index(0, 2),
                                        Qt.ToolTipRole) or ""
        check("点击查看记忆等级说明" not in tip,
              "等级列 tooltip 不再包含失效点击提示：%r" % tip)
        check("记忆等级" in tip or "待学习" in tip or "已掌握" in tip or "认识" in tip,
              "等级列 tooltip 仍保留当前等级文字：%r" % tip)

        # 表头图标/点击打开说明；独立 chip 删除；行点击不弹窗也不选中
        check(not hasattr(catalog_widget, "btn_levels"),
              "工具栏独立「等级说明」chip 已删除")
        header = catalog_widget.level_header
        icon_rect = header.icon_rect()
        check(not icon_rect.isEmpty() and icon_rect.intersects(
                  header.rect().adjusted(
                      header.sectionViewportPosition(2), 0, 0, 0)),
              "表头「记忆等级」右上角有感叹号圆圈图标 %r" % (icon_rect,))
        check(catalog_widget.level_header.icon_color()
              == QColor(catalog_widget.theme["muted"]),
              "表头图标颜色等于表头主题文字色（非硬编码）")
        check(not hasattr(catalog_widget, "note"),
              "底部提示 note 已删除")

        # 行点击：不弹说明、不留下 selection/current
        catalog_widget.table.selectionModel().clearSelection()
        catalog_widget.table.setCurrentIndex(catalog_widget.model.index(-1, -1))
        QTest.mouseClick(catalog_widget.table.viewport(), Qt.LeftButton,
                         Qt.NoModifier, QPoint(12, 12))
        pump(0.03)
        check(catalog_widget.level_dialog is None,
              "点击行不再弹出等级说明")
        check(not catalog_widget.table.currentIndex().isValid(),
              "点击行不再留下 current row")
        check(catalog_widget.table.selectionModel().selectedRows() == [],
              "点击行不再出现选中态")

        # 图标点击 / 表头文字点击都能打开
        QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier,
                         icon_rect.center())
        pump(0.05)
        check(isinstance(catalog_widget.level_dialog, QDialog)
              and catalog_widget.level_dialog.isVisible(),
              "点击表头感叹号图标打开等级说明")
        catalog_widget.level_dialog.close()
        pump(0.03)
        text_pos = QPoint(header.sectionViewportPosition(2) + 16,
                          header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, text_pos)
        pump(0.05)
        dialog = catalog_widget.level_dialog
        check(isinstance(dialog, QDialog) and dialog.isVisible(),
              "点击「记忆等级」表头文字打开等级说明")
        check(dialog.windowTitle() == "记忆等级", "说明窗口标题「记忆等级」")
        labels = dialog.findChildren(QLabel)
        level_labels = [label for label in labels
                        if label.text().startswith("等级 ")]
        detail_texts = [label.text() for label in labels]
        check([label.text() for label in level_labels] ==
              [line.partition("：")[0] for line in catalog.LEVEL_LINES],
              "说明窗口 11 行等级齐全")
        check("新词" in detail_texts and "5 分钟后复习" in detail_texts
              and "已掌握，不再出现" in detail_texts,
              "说明窗口等级/时间/已掌握文案齐全")
        check(catalog_widget.theme["bg"] in dialog.styleSheet(),
              "说明窗口使用当前主题背景")
        close_buttons = [button for button in dialog.findChildren(QPushButton)
                         if button.text() == "知道了"]
        check(len(close_buttons) == 1, "说明窗口有关闭按钮")
        close_buttons[0].click()
        pump(0.03)
        check(not dialog.isVisible(), "说明窗口可关闭")
        dialog = None

        # 等级列/单词列文字只用主题普通文字色，不再按分类染色
        ordinary = QColor(catalog_widget.theme["fg_mean"])
        check(catalog_widget.model.data(catalog_widget.model.index(0, 0),
                                        Qt.ForegroundRole) == ordinary,
              "单词列 ForegroundRole == theme.fg_mean")
        check(catalog_widget.model.data(catalog_widget.model.index(0, 2),
                                        Qt.ForegroundRole) == ordinary,
              "等级列 ForegroundRole == theme.fg_mean")
        color_model = catalog.WordTableModel()
        color_model.set_entries(
            [{"w": "mastered-word", "s": "掌握释义"},
             {"w": "known-word", "s": "认识释义"}],
            {"mastered-word": {"st": "mastered", "lv": 10},
             "known-word": {"st": "learning", "lv": 1}}, set())
        for row in range(2):
            for col in (0, 2):
                check(color_model.data(color_model.index(row, col),
                                       Qt.ForegroundRole) == ordinary,
                      "分类行 %d 列 %d 仍为普通文字色" % (row, col))

        # 滚动到中部 / 底部：只增加可见附近行，不遍历全书
        bar = catalog_widget.table.verticalScrollBar()
        bar.setValue(max(0, bar.maximum() // 2))
        pump(0.08)
        mid_measured = catalog_widget.measured_rows
        mid_calls = catalog_widget.measure_calls
        check(mid_measured <= 160,
              "滚动中部后累计测量 %d 行（16331 项中仍很小）" % mid_measured)
        check(mid_calls <= initial_calls + 5,
              "滚动中部只新增合并测量 %d 次（总计 %d）" % (mid_calls - initial_calls, mid_calls))

        # 视口/列宽 resize：coalesce 后仍只测可见附近
        resize_calls = catalog_widget.measure_calls
        catalog_widget.resize(650, 400)
        pump(0.05)
        catalog_widget.table.setColumnWidth(0, 180)
        pump(0.05)
        check(catalog_widget.measured_rows <= 220,
              "resize/列宽变化后累计测量仍限可见附近：%d" % catalog_widget.measured_rows)
        check(catalog_widget.measure_calls <= resize_calls + 8,
              "resize/列宽变化只合并测量少量次数：%d -> %d" %
              (resize_calls, catalog_widget.measure_calls))

        # 搜索/筛选也不做全书测量
        catalog_widget.search.setText("a")
        pump(0.05)
        check(catalog_widget.model.rowCount() > 0, "搜索后仍有结果：%d" %
              catalog_widget.model.rowCount())
        check(catalog_widget.measured_rows <= 180,
              "搜索后累计测量仍限可见附近：%d" % catalog_widget.measured_rows)
        catalog_widget.set_filter("mastered")
        pump(0.05)
        check(catalog_widget.measured_rows <= 200,
              "筛选后累计测量仍限可见附近：%d" % catalog_widget.measured_rows)

        # 极长行：行高 > 视口，且完整换行（>= FontMetrics 计算高度）
        long_word = "pneumonoultramicroscopicsilicovolcanoconiosis"
        long_meaning = ("very long meaning with complete wrapping " * 80).strip()
        long_entry = dict(entries[0])
        long_entry["w"] = long_word
        long_entry["s"] = long_meaning
        long_entry["raw"] = long_meaning
        long_entries = entries + [long_entry]
        catalog_widget.set_book("long", "长行测试", long_entries, {}, set())
        pump(0.05)
        catalog_widget.set_filter("all")
        pump(0.05)
        bar = catalog_widget.table.verticalScrollBar()
        bar.setValue(bar.maximum())
        pump(0.10)
        long_row = catalog_widget.model.rowCount() - 1
        row_h = catalog_widget.table.rowHeight(long_row)
        width = catalog_widget._text_width(1)
        fm = QFontMetrics(catalog_widget._font())
        needed = fm.boundingRect(0, 0, width, 0,
                                 Qt.TextWordWrap | Qt.AlignLeft, long_meaning).height()
        check(row_h > catalog_widget.table.viewport().height(),
              "极长行高 %d > 视口 %d（ScrollPerPixel 可滚动）" %
              (row_h, catalog_widget.table.viewport().height()))
        check(row_h >= needed + 2 * catalog.CELL_PAD_Y,
              "极长行高 %d >= FontMetrics 完整换行 %d + padding" %
              (row_h, needed))
        check(catalog_widget.measure_calls < len(long_entries),
              "长行仍只测可见附近：measure_calls=%d" % catalog_widget.measure_calls)

        # 真实短语 + 极窄 word 列：必须按实际文本宽（columnWidth-12，不再有 40 下限）
        phrases = json.load(io.open(os.path.join(app_main.DATA, "phrases.json"),
                                    encoding="utf-8"))
        phrase = next(entry for entry in phrases if entry.get("w") == "on the part of")

        # 单条极长行（真实 phrase 复制 + 长 s/raw）：不能因滚动条/stretch 列
        # 自触发 _invalidate_rows 把行高反复重置成 48。
        single = dict(phrase)
        single["s"] = ("very long meaning with complete wrapping " * 300).strip()
        single["raw"] = single["s"]
        catalog_widget.resize(520, 430)
        catalog_widget.set_book("single-long", "单条长行", [single], {}, set())
        end = time.time() + 1.5
        while catalog_widget._measure_timer.isActive() and time.time() < end:
            pump(0.03)
        h1 = catalog_widget.table.rowHeight(0)
        calls1 = catalog_widget.measure_calls
        pump(0.12)
        check(h1 > catalog_widget.table.verticalHeader().defaultSectionSize(),
              "单条极长行行高 %d > 默认 48（不再被反复重置）" % h1)
        check(h1 > catalog_widget.table.viewport().height(),
              "单条极长行 %d > 视口 %d，ScrollPerPixel 可滚动" %
              (h1, catalog_widget.table.viewport().height()))
        check(catalog_widget.table.verticalScrollBar().isVisible(),
              "单条极长行出现垂直滚动条")
        check(not catalog_widget._measure_timer.isActive(),
              "单条长行测量收敛，timer 已停止")
        check(catalog_widget.measure_calls == calls1,
              "收敛后 measure_calls 不再增长（%d）" % calls1)
        catalog_widget.resize(900, 600)
        pump(0.08)

        catalog_widget.set_book("phrase", "词组 · on the part of", [phrase], {}, set())
        catalog_widget.set_filter("all")
        pump(0.05)
        catalog_widget.table.setColumnWidth(0, 38)
        pump(0.10)
        cw = catalog_widget.table.columnWidth(0)
        actual_text_width = max(1, cw - 2 * catalog.CELL_PAD_X)
        check(actual_text_width < 40,
              "窄 word 列实际文本宽 %d < 40（columnWidth=%d）" %
              (actual_text_width, cw))
        fm = QFontMetrics(catalog_widget._font())
        phrase_needed = fm.boundingRect(
            0, 0, actual_text_width, 0,
            Qt.TextWordWrap | Qt.AlignLeft, phrase["w"]).height()
        phrase_row_h = catalog_widget.table.rowHeight(0)
        check(phrase_needed + 2 * catalog.CELL_PAD_Y > catalog_widget.table.verticalHeader().defaultSectionSize(),
              "短语 on the part of 在窄列需要 %dpx + padding > 默认 48" % phrase_needed)
        check(phrase_row_h >= phrase_needed + 2 * catalog.CELL_PAD_Y,
              "窄列完整换行：行高 %d >= 需要 %d + padding" %
              (phrase_row_h, phrase_needed))
        catalog_widget._height_cache.clear()
        catalog_widget.measure_height("on the part of", 40,
                                      word="on the part of",
                                      widths=(cw, 648, 96))
        assert_after_wide = len(catalog_widget._height_cache)
        catalog_widget.measure_height("on the part of", actual_text_width,
                                      word="on the part of",
                                      widths=(cw, 648, 96))
        check(len(catalog_widget._height_cache) == 2,
              "行高缓存 key 区分实际文本宽（40px/26px 各一条缓存，%d -> %d）" %
              (assert_after_wide, len(catalog_widget._height_cache)))

        # 行高缓存 key 含 display text/widths/scale，容量有界
        before = len(catalog_widget._height_cache)
        for i in range(1200):
            catalog_widget.measure_height("unique-text-%d" % i, 100,
                                          word="w%d" % i, widths=(142, 648, 96))
        check(len(catalog_widget._height_cache) <= 1024,
              "行高缓存容量 <=1024：%d" % len(catalog_widget._height_cache))
        check(len(catalog_widget._height_cache) < 1200,
              "行高缓存有界（%d < 1200 插入）" % len(catalog_widget._height_cache))

        # scale 1.0 / 1.6：默认 48*s、字体 13*s，且不触发全书测量
        catalog_widget.set_scale(1.0)
        pump(0.05)
        check(catalog_widget.table.verticalHeader().defaultSectionSize() == 48,
              "scale=1.0 默认行高 48")
        check(catalog_widget.model.data(catalog_widget.model.index(0, 0),
                                        Qt.FontRole).pixelSize() == 13,
              "scale=1.0 字体 13px")
        catalog_widget.set_scale(1.6)
        pump(0.05)
        check(catalog_widget.table.verticalHeader().defaultSectionSize()
              == round(48 * 1.6),
              "scale=1.6 默认行高 %d" % catalog_widget.table.verticalHeader().defaultSectionSize())
        check(catalog_widget.level_header.icon_color()
              == QColor(catalog_widget.theme["muted"]),
              "scale 变化后表头图标颜色仍等于主题文字色")
        check(catalog_widget.level_header.icon_rect().width() >= 14,
              "scale 变化后表头图标尺寸随 scale 更新：%d" %
              catalog_widget.level_header.icon_rect().width())
        old_theme = catalog_widget.theme
        catalog_widget.set_palette(catalog.th.get("dark"))
        pump(0.03)
        check(catalog_widget.level_header.icon_color()
              == QColor(catalog_widget.theme["muted"]),
              "set_palette(dark) 后表头图标颜色跟随主题")
        catalog_widget.set_palette(old_theme)
        pump(0.03)
        check(catalog_widget.model.data(catalog_widget.model.index(0, 0),
                                        Qt.FontRole).pixelSize() == round(13 * 1.6),
              "scale=1.6 字体 %dpx" %
              catalog_widget.model.data(catalog_widget.model.index(0, 0),
                                        Qt.FontRole).pixelSize())
        check(catalog_widget.measured_rows <= 220,
              "scale 变化后累计测量仍限可见附近：%d" % catalog_widget.measured_rows)
        check(catalog_widget.measure_calls < len(long_entries),
              "scale 变化没有遍历全书测量：%d" % catalog_widget.measure_calls)
        check(catalog_widget.table.verticalHeader().minimumSectionSize()
              == round(48 * 1.6),
              "scale=1.6 最小行高 %d" % catalog_widget.table.verticalHeader().minimumSectionSize())

        # 主题样式仍保留（表头 QSS/背景）
        catalog_widget.set_palette(catalog_widget.theme)
        pump(0.03)
        qss = catalog_widget.table.styleSheet()
        check("QHeaderView::section" in qss and "padding:" in qss,
              "主题表头 QSS 仍保留")
        check(catalog_widget.theme["bg"] in qss, "主题背景仍写入表头 QSS")

        # 真实 Card 主题样式（不是独立 widget）：单条极长中文/英文 + search 仅一条
        # 复现 memory-engine 的 CatalogCard 场景，验证不再 48/long 自触发振荡。
        card = sb.new_card(progress={
            "welcome_done": True, "book_confirmed": True, "book": "cet4-dg",
            "theme": "light", "states": {}, "cursors": {}, "orders": {},
            "history": [],
        }, show=True)
        pump(0.08)
        card.catalog.set_palette(card.t)
        card._set_mode("catalog")
        pump(0.05)
        single_card = dict(phrase)
        single_card["s"] = ("极长中文释义" * 500) + " " + \
                           ("very long english meaning " * 300)
        single_card["raw"] = single_card["s"]
        for theme_key, scale in (("light", 1.0), ("dark", 1.6)):
            card.set_theme(theme_key)
            card.catalog.set_palette(card.t)
            card.catalog.set_scale(scale)
            card.catalog.search.clear()
            card.catalog.set_book("real-card-single", "真实 Card 单条",
                                  [single_card], {}, set())
            card.catalog.setVisible(True)
            card.catalog.search.setText("on the part of")
            wait_measure(card.catalog)
            c = card.catalog
            calls = c.measure_calls
            pump(0.15)
            check(c.model.rowCount() == 1,
                  "%s/scale%.1f Card 搜索只留 1 条" % (theme_key, scale))
            check(not c._measure_timer.isActive(),
                  "%s/scale%.1f 真实 Card 单条长行测量 timer 已停" % (theme_key, scale))
            check(c.table.rowHeight(0) > c.table.viewport().height(),
                  "%s/scale%.1f 真实 Card 行高 %d > 视口 %d" %
                  (theme_key, scale, c.table.rowHeight(0), c.table.viewport().height()))
            check(c.table.verticalScrollBar().isVisible(),
                  "%s/scale%.1f 真实 Card 长行垂直滚动条可见" % (theme_key, scale))
            check(c.measure_calls == calls,
                  "%s/scale%.1f 收敛后 measure_calls 不再增长（%d）" %
                  (theme_key, scale, calls))
            out.append("      CARD %s scale=%.1f height=%d viewport=%d calls=%d" %
                       (theme_key, scale, c.table.rowHeight(0),
                        c.table.viewport().height(), calls))
        card.close()
        card = None
        pump(0.05)
        source_line = "SOURCE catalog=%s data=%s" % (
            os.path.abspath(catalog.__file__),
            os.path.abspath(os.path.join(app_main.DATA, "bank.json")))
        out.append("      " + source_line)
        out.append("      TIMING set_book=%.3fs measure_calls=%d measured_rows=%d" %
                   (set_book_s, catalog_widget.measure_calls,
                    catalog_widget.measured_rows))

    except Exception:
        import traceback
        check(False, "catalog 测试异常：\n" + traceback.format_exc())
    finally:
        if card is not None:
            try:
                for timer in card.findChildren(QTimer):
                    timer.stop()
                card.close()
            except Exception:
                pass
        if catalog_widget is not None:
            try:
                catalog_widget._measure_timer.stop()
                catalog_widget.close()
            except Exception:
                pass
        sb.__exit__(None, None, None)
        check(not sb.errors, "Sandbox 真实 records 指纹未变：%r" % (sb.errors,))
        out.append("      FINGERPRINT protected=%d unchanged=%s" %
                   (len(sb.watch_paths), not sb.errors))

    out.append("")
    if fails:
        out.append("失败 %d 项：%s" % (len(fails), " / ".join(fails)))
    else:
        out.append("全部通过 ✓")
    path = sb.out("test_catalog.txt")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
    print("REPORT", path)
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
