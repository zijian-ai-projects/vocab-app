# -*- coding: utf-8 -*-
"""V1.3.4 设置、贴边偏好、词表修订兼容与三处不认识控件验收。

python -B scripts/test_v134_ui.py [--native]
只在 Sandbox / VOCABAPP_DATA_DIR 运行；不调用 main.main、不写真实记录。
VOCAB_V134_SKIP_IMAGES=1 可在数据整理期间跳过真实词库示意图。
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import sys
import tempfile
from unittest.mock import patch

import test_v130_ui as base
from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLabel, QMessageBox, QPushButton

import books as real_books
import theme as th
from windowing import DOCK_ANIM_MS


class V134Suite(base.Suite):
    def shot(self, widget, name):
        base.pump(12)
        path = self.sb.shot(name)
        self.check(widget.grab().save(path), "保存隔离截图 " + name)
        self.screens.append(path)
        return path

    def settings_contract(self, key):
        win = {"normal_w": 640, "normal_h": 520, "normal_x": 100,
               "normal_y": 100, "edge_collapse": False, "future": {"keep": [1, 2]}}
        states = {base.KEYS[1]: base.learning(2, self.clock() + 3600)}
        w = self.card(base.progress(theme=key, study_mode="choice", states=states), win)
        w.open_settings()
        self.check(w.btn_edge_collapse.isCheckable() and not w.btn_edge_collapse.isChecked(),
                   key + "保存的关闭偏好与可勾选设置立即同步")
        self.check(w.btn_edge_collapse.text() == "小窗贴边收起：关", "开关明确显示关闭状态")
        labels = [x.text() for x in w.settings_body.findChildren(QLabel)]
        buttons = [x.text() for x in w.settings_body.findChildren(QPushButton)]
        self.check("背景" in labels and "背景风格" not in labels, "标题为背景")
        self.check("恢复默认" not in buttons and not hasattr(w, "btn_defaults"),
                   "恢复默认控件不存在而非仅隐藏")
        self.check([x.text() for x in w.size_chips.values()] == ["小窗", "标准", "大窗"],
                   "窗口预设只显示名称")
        self.check(not any(re.search(r"\d+\s*[×x]\s*\d+", x.text() + x.toolTip())
                           for x in list(w.size_chips.values()) + [w.btn_edge_collapse]),
                   "窗口控件文字与提示不暴露尺寸数字")
        row = list(w.size_chips.values()) + [w.btn_edge_collapse]
        centers = {round(x.y() + x.height() / 2) for x in row}
        self.check(len(centers) == 1, "三个预设与贴边开关在同一行")
        self.check(all(x.x() >= 0 and x.x() + x.width() <= w.settings_body.width() for x in row),
                   "窗口行没有横向截断")
        before = Path(self.sb.progress_path).read_bytes()
        QTest.mouseClick(w.btn_edge_collapse, Qt.LeftButton)
        base.pump()
        self.check(w.window_ctl.edge_collapse_enabled and w.btn_edge_collapse.isChecked()
                   and w.btn_edge_collapse.property("on") == "1", "鼠标点击开启并刷新chip状态")
        self.check(self.sb.read_win().get("edge_collapse") is True
                   and self.sb.read_win()["future"] == win["future"], "保存开关并保留未知窗口字段")
        self.check(Path(self.sb.progress_path).read_bytes() == before and w.states == states
                   and w.study_mode == "choice", "开关不改学习进度、历史、模式或记录字节")
        w.btn_edge_collapse.setFocus()
        QTest.keyClick(w.btn_edge_collapse, Qt.Key_Space)
        base.pump()
        self.check(not w.window_ctl.edge_collapse_enabled and not w.btn_edge_collapse.isChecked(),
                   "空格键也可关闭开关")
        self.aliases(w)

    def preference_restart(self, enabled):
        win = {"normal_w": 640, "normal_h": 520, "normal_x": 130, "normal_y": 130,
               "edge_collapse": enabled, "future": {"nested": [True, "keep"]}}
        w = self.card(win=win)
        self.check(w.window_ctl.edge_collapse_enabled is enabled
                   and w.btn_edge_collapse.isChecked() is enabled,
                   "首次show前同步已保存偏好%s" % enabled)
        w._set_edge_collapse(not enabled)
        saved = deepcopy(self.sb.read_win())
        self.check(saved.get("edge_collapse") is (not enabled), "显式变更保存bool而非字符串")
        w = self.card(restart=True)
        self.check(w.window_ctl.edge_collapse_enabled is (not enabled)
                   and w.btn_edge_collapse.isChecked() is (not enabled), "重启恢复变更后的偏好")
        self.check(w.window_record["future"] == win["future"], "重启不丢未知字段")
        self.check(w.window_ctl.normal_size == QSize(640, 520), "偏好切换不修改正常尺寸")

    def legacy_preference(self):
        for value in ("missing", None, "false", 0, 1, [], {}):
            win = {"normal_w": 640, "normal_h": 520, "normal_x": 100, "normal_y": 100}
            if value != "missing":
                win["edge_collapse"] = value
            w = self.card(win=win)
            self.check(w.window_ctl.edge_collapse_enabled is True
                       and w.btn_edge_collapse.isChecked(), "旧记录/非法类型保守保留开启：%r" % value)
            w._save_window()
            self.check(self.sb.read_win().get("edge_collapse") is True,
                       "保存时修正为实际bool：%r" % value)

    def animation_toggle(self, compact, phase, edge):
        original_cursor = QCursor.pos()
        try:
            self._animation_toggle_with_cursor(compact, phase, edge)
        finally:
            QCursor.setPos(original_cursor)

    def _animation_toggle_with_cursor(self, compact, phase, edge):
        area = base.APP.primaryScreen().availableGeometry()
        win = {"normal_w": 520, "normal_h": 430, "normal_x": area.left() + 100,
               "normal_y": area.top() + 100, "dock_edge": edge, "edge_collapse": True}
        w = self.card(win=win)
        if compact:
            w.set_compact(True)
        c = w.window_ctl
        QTest.qWait(20)
        QCursor.setPos(area.bottomRight() - QPoint(20, 20))
        QTest.qWait(20)
        c.stop_timers()
        c._hover_inside = False
        w._window_save_timer.stop()
        logical = deepcopy(c.state())
        progress_before = Path(self.sb.progress_path).read_bytes()
        pointer = QCursor.pos()
        self.out.append("POINTER compact=%s phase=%s edge=%s cursor=%s frame=%s" %
                        (compact, phase, edge, (pointer.x(), pointer.y()),
                         w.frameGeometry().getRect()))
        self.check(not c._cursor_inside() and c._collapse_if_docked(force=True, immediate=False),
                   "真实鼠标停在窗外并启动收起动画", require=True)
        if phase == "expand":
            QTest.qWait(DOCK_ANIM_MS + 25)
            c._hover_inside = True
            c.reveal(immediate=False)
        QTest.qWait(25)
        self.check(c.animating and not c.can_persist_geometry, "中间帧锁定几何保存")
        w._set_edge_collapse(False)
        base.pump()
        expected = QSize(356, 196) if compact else QSize(520, 430)
        self.check(not c.animating and not c.collapsed and w.size() == expected,
                   "关闭偏好立即完整展开并停止动画")
        self.check(c.can_persist_geometry and c._dock_overlay is None and not c._hover_timer.isActive(),
                   "解除保存锁、释放快照并停止hover计时")
        logical["edge_collapse"] = False
        self.check(c.state() == logical and self.sb.read_win().get("edge_collapse") is False,
                   "保存实际逻辑几何与false偏好，不写中间帧")
        self.check(not c._collapse_if_docked(force=True, immediate=False), "force也不能绕过关闭设置")
        self.check(Path(self.sb.progress_path).read_bytes() == progress_before,
                   "动画中关闭偏好不修改任何学习记录字节")
        c._hover_inside = True
        w._set_edge_collapse(True)
        c._hover_inside = False
        self.check(c._collapse_if_docked(force=True, immediate=True), "重新开启后仍支持正常靠边收起")
        c.reveal(immediate=True)
        c.stop_timers()

    def dontknow_contract(self, key):
        w = self.card(base.progress(theme=key))
        palette = th.get(key)
        for b in (w.btn_forget, w.btn_study_dk, w.btn_dontknow):
            b.ensurePolished()
            self.check(b.objectName() == "dontknow" and b.text() == "不认识",
                       key + "三处控件共用同一语义样式")
            self.check(b.palette().color(QPalette.ButtonText) == QColor(palette["dk_fg"]),
                       key + "三处文字使用相同DK前景色")
        self.check(palette["dk_bg"] != palette["bg"], "不认识背景与页面背景不同")
        self.check(all(name in palette for name in ("dk_bg", "dk_hover", "dk_pressed", "dk_fg")),
                   "DK包含正常、悬停、按下及文字色")

    def display_identity(self):
        self.check(base.app_main.word_caption({"w": "i", "display_w": "I"}) == "I",
                   "显示拼写与稳定记忆key可分离")
        for invalid in (None, 0, [], "", " "):
            self.check(base.app_main.word_caption({"w": "it", "display_w": invalid}) == "it",
                       "无效display字段安全退回原key")
        w = self.card(base.progress(study_mode="choice"))
        row = w.queue[w.qi]["w"]
        row["display_w"] = "ALPHA"
        before = deepcopy(w.study_record["current"])
        w._show_current()
        self.check(w.word.text() == w.choice_word.text() == "ALPHA"
                   and w.study_record["current"] == before,
                   "刷词/选择题呈现大小写不改current记忆key")
        w.open_settings()
        # 此用例只验证显示拼写；8词fixture不保证真实自适应算法有4个近难度选项。
        with patch.object(base.app_main.pl, "make_options", return_value=(list(base.MEANINGS[:4]), 0)):
            w.start_quiz()
        base.pump()
        w.quiz_items[w.quiz_i]["idx"] = 0
        w._quiz_show()
        self.check(w.quiz_word.text() == "ALPHA", "词汇量测试也使用正确显示拼写")
        w.catalog.set_book(base.BOOK, "显示拼写测试", [row], w.states, set())
        index = w.catalog.model.index(0, 0)
        self.check(w.catalog.model.data(index, Qt.DisplayRole) == "ALPHA"
                   and w.catalog.model.data(index, Qt.ToolTipRole).startswith("ALPHA\n"),
                   "内容浏览单词列与Tooltip共享正确显示拼写")
        w.catalog.model.refilter("all", "alpha")
        self.check(w.catalog.model.rowCount() == 1 and w.catalog.model.rows[0]["w"] == "alpha",
                   "目录搜索与记忆key保持原始词形")
        row["display_w"] = "OFFICIAL DISPLAY SPELLING " * 8
        with patch.object(w.catalog, "measure_height", wraps=w.catalog.measure_height) as measurements:
            height = w.catalog._row_height(0)
        first_args = measurements.call_args_list[0][0]
        self.check(first_args[0] == row["display_w"] and first_args[2] == "alpha"
                   and height > w.catalog._default_row(),
                   "宽显示拼写参与目录行高测量，缓存身份仍是稳定原key")
        self.check(any(key[0] == "alpha" and key[-1] == row["display_w"]
                       for key in w.catalog._height_cache),
                   "显示文本是行高缓存维度，变化后不会误用旧raw短词高度")

    def window_save_failure(self):
        w = self.card(base.progress(study_mode="choice"), win={"custom": {"keep": "window"}})
        w.open_settings()
        w._set_edge_collapse(True)
        saved, progress_before = self.sb.read_win(), self.sb.read_progress()
        actual_save = base.storage.atomic_save

        def failing_window(path, value):
            if os.path.abspath(path) == os.path.abspath(base.app_main.WIN_PATH):
                raise base.storage.StorageError("fixture window disk unavailable")
            return actual_save(path, value)

        with patch.object(base.storage, "atomic_save", side_effect=failing_window):
            w._set_edge_collapse(False)
            self.check(not w.window_ctl.edge_collapse_enabled and not w.btn_edge_collapse.isChecked()
                       and w.btn_edge_collapse.text() == "小窗贴边收起：关"
                       and w.btn_edge_collapse.property("on") == "0",
                       "窗口保存失败不抛Qt槽异常，偏好与按钮仍同步当前关闭状态")
            self.check("窗口设置暂未保存" in w.lab_storage.text()
                       and "fixture window disk unavailable" in w.btn_gear.toolTip(),
                       "窗口设置保存失败有明确提示而非静默成功")
            self.check(self.sb.read_win() == saved and self.sb.read_progress() == progress_before,
                       "失败不覆盖旧有效窗口记录或学习数据")
            # offscreen默认800×600工作区；标准预设能完整容纳，不把620高的屏幕夹紧当失败。
            w._apply_window_size(640, 520)
            self.check(w.window_ctl.normal_size == QSize(640, 520)
                       and w.size_chips[(640, 520)].property("on") == "1"
                       and not w.btn_edge_collapse.isChecked(),
                       "preset保存失败仍更新实际尺寸且保留当前关闭偏好")
        w._flush_window()
        persisted = self.sb.read_win()
        self.check(persisted["edge_collapse"] is False and persisted["custom"] == {"keep": "window"}
                   and persisted["w"] == 640 and persisted["h"] == 520
                   and w._last_window_error is None,
                   "故障解除后安全保存当前窗口/偏好及未知字段")
        self.check(self.sb.read_progress() == progress_before, "窗口重试保存不改学习记录")
        with patch.object(w, "_can_act", return_value=False):
            w.btn_edge_collapse.setChecked(True)
            w._set_edge_collapse(True)
            self.check(not w.window_ctl.edge_collapse_enabled and not w.btn_edge_collapse.isChecked(),
                       "动作被安全guard拒绝时按钮恢复controller实际偏好")

    def compact_save_failure(self):
        w = self.card(base.progress(study_mode="brush"), win={"custom": {"retain": 7}})
        w._flush_window()
        saved, progress_before = self.sb.read_win(), self.sb.read_progress()
        with patch.object(w, "_save_window", side_effect=base.storage.StorageError("fixture compact disk unavailable")):
            w.toggle_compact()
            self.check(w.compact and w.window_ctl.compact,
                       "小窗按钮保存失败不抛Qt槽异常，当前实际小窗完整生效")
            self.check("fixture compact disk unavailable" in w.btn_gear.toolTip()
                       and w._last_window_error is not None,
                       "小窗保存故障使用统一窗口设置错误提示")
            self.check(self.sb.read_win() == saved and self.sb.read_progress() == progress_before,
                       "小窗保存失败不覆盖旧有效窗口配置或学习记录")
            w.toggle_compact()
            self.check(not w.compact and not w.window_ctl.compact,
                       "故障期间仍能安全从小窗切回正常窗")
        w.toggle_compact()
        persisted = self.sb.read_win()
        self.check(persisted["compact"] is True and persisted["custom"] == {"retain": 7}
                   and persisted["w"] == 356 and persisted["h"] == 196
                   and w._last_window_error is None,
                   "故障解除后小窗切换能持久化真实逻辑几何和未知字段")
        self.check(self.sb.read_progress() == progress_before, "小窗故障/恢复不改学习状态与历史")

    def source_count_display(self):
        quantity = base.app_main.book_quantity
        self.check(quantity({"count": 8}) == "8 词",
                   "民间词表按实际学习卡数显示")
        self.check(quantity({"count": 8, "source_status": "community_compilation"}) == "8 词",
                   "community 来源只展示实际成员数")
        item = self.books.BY_ID[base.BOOK]
        original = deepcopy(item)
        note = "fixture: 民间整理；保留原始成员与顺序。"
        item.update(source_note=note)
        try:
            w = self.card()
            w.open_settings()
            self.check("8 词" in w.lab_book.toolTip()
                       and note in w.lab_book.toolTip()
                       and w.lab_book_num.text().endswith("/ 8"),
                       "设置来源Tooltip展示民间注记/实际卡数")
            w.sel_book = base.BOOK
            w._refresh_books()
            self.check("8 词" in w.lab_book_stat.text(), "选书说明显示实际卡数")
            w._nav_into_main(item["main"])
            w._nav_into_group(item["group"])
            button = w.book_btns[base.BOOK]
            self.check("8 词" in button.text() and note in button.toolTip(),
                       "具体词书条目数量与民间来源Tooltip一致")
        finally:
            self.close()
            item.clear()
            item.update(original)

    def composition_revision(self):
        item = self.books.BY_ID[base.BOOK]
        old = deepcopy(item)
        added = dict(base.WORDS[0], w="india", s="n.新增测试词", raw="n. 新增测试词", ipa="")
        new_keys = ["india"] + [key for key in base.KEYS if key != "bravo"]
        item["words"], item["count"] = new_keys, len(new_keys)
        self.write_json(self.data_dir / "bank.json", base.WORDS + [added])
        forgotten = base.sch.new_state()
        forgotten.update(seen=1, custom={"history": "retain"})
        states = {key: base.mastered() for key in base.KEYS if key not in ("alpha", "bravo", "charlie")}
        states.update(bravo=forgotten, charlie=base.learning(3, self.clock() - 1))
        record = {"cursor": len(base.KEYS), "new_count": 7, "pending": {"bravo": 10},
                  "current": {"kind": "review", "key": "charlie"},
                  "held_current": {"kind": "new", "key": "alpha"}, "custom": {"keep": True}}
        p = base.progress(states=states, cursors={base.BOOK: len(base.KEYS)},
                          study_records={base.BOOK: record})
        try:
            w = self.card(p)
            self.check(base.key_of(w) == "charlie" and w.queue[w.qi]["kind"] == "review",
                       "词表换版仍先恢复本书到期复习")
            self.check(w.study_record["new_count"] == 7 and w.states["bravo"] == forgotten,
                       "换版不伪造新词次数、不删除移出本书的历史词状态")
            self.submit(w)
            w._next()
            self.check(base.key_of(w) == "alpha", "到期复习后恢复保留的held_current")
            self.submit(w)
            w._next()
            self.check(base.key_of(w) == "india", "旧cursor即使在书末也补扫新增前缀，不永久跳新词")
            self.check(w.study_record["pending"]["bravo"] == 10,
                       "移出本书的pending保留但不进入本书队列")
            self.submit(w)
            w._next()
            self.check(w.mode == "empty", "新增词学习完成后正常结束，不跳词或循环")
            self.check(w.states["bravo"] == forgotten and w.progress["history"] == p["history"]
                       and w.study_record["custom"] == {"keep": True}, "历史及未知队列字段完整保留")
            removed = deepcopy(p)
            removed["study_records"][base.BOOK]["current"] = {"kind": "new", "key": "bravo"}
            w = self.card(removed)
            self.check(base.key_of(w) != "bravo" and w.states["bravo"] == forgotten,
                       "已移出的current不重现，但历史状态不抹掉")
        finally:
            self.close()
            item.clear()
            item.update(old)
            self.write_json(self.data_dir / "bank.json", base.WORDS)

    def real_source_contract(self):
        bid = "xx-dg"
        words = real_books.words(bid)
        meta = real_books.get(bid)
        self.check(len(words) == 525 and meta.get("count") == 525
                   and words[0] == "an" and words[-1] == "zoo",
                   "真实2022小学词表保持 V1.3.3 原 525 成员/顺序", require=True)
        self.check(meta.get("official_entry_count") is None
                   and meta.get("source_status") == "community_compilation"
                   and isinstance(meta.get("source_note"), str)
                   and bool(meta["source_note"].strip()),
                   "真实词表来源为民间整理，不冒充官方词目数", require=True)
        source = real_books.source_info(bid)
        self.check(source.get("status") == "community_compilation"
                   and source.get("official_entry_count") is None
                   and source.get("study_count") == len(words)
                   and real_books.source_rows(bid) == [],
                   "民间来源API不返回官方审计行，卡数=实际成员数")

        target = words[0]
        record = {"cursor": 0, "new_count": 0, "pending": {},
                  "current": {"kind": "new", "key": target}, "held_current": None}
        w = self.card(base.progress(book=bid, history=[], study_mode="choice", states={},
                                   orders={bid: {"mode": "seq", "seed": 42}},
                                   cursors={bid: 0}, study_records={bid: record}))
        self.check(base.key_of(w) == target
                   and w.word.text() == w.choice_word.text() == target,
                   "真实民间词书刷词/选择显示原成员，current保持稳定key")
        w.catalog.set_book(bid, "真实民间来源检查", w._book_words(bid), w.states, set())
        index = next(i for i, entry in enumerate(w.catalog.model.rows)
                     if entry["w"] == target)
        index = w.catalog.model.index(index, 0)
        self.check(w.catalog.model.data(index, Qt.DisplayRole) == target,
                   "真实词表内容浏览显示原成员")
        w.open_settings()
        self.check(meta["source_note"] in w.lab_book.toolTip()
                   and base.app_main.book_quantity(meta, len(words)) in w.lab_book.toolTip(),
                   "真实设置词书Tooltip民间来源/数量与运行时meta一致")
        self.check(w.lab_book_num.text().endswith("/ %d" % len(words)),
                   "真实选书进度分母仍是实际学习卡数")
        w.start_quiz()
        base.pump()
        w.quiz_items[w.quiz_i]["idx"] = next(
            i for i, entry in enumerate(w.bank) if entry["w"] == target)
        w._quiz_show()
        self.check(w.quiz_word.text() == target,
                   "真实民间词库测试页显示原成员")
        self.check(w.study_record["current"]["key"] == target,
                   "测试页面展示不改未答学习current的稳定key")

    def illustrations(self):
        bid = real_books.DEFAULT
        words = real_books.words(bid)
        target = next((key for key in ("abandon", "ability", "challenge") if key in words), words[0])
        for key in th.ORDER:
            w = self.card(base.progress(book=bid, history=[], theme=key, study_mode="choice", states={},
                                       cursors={bid: words.index(target)},
                                       orders={bid: {"mode": "seq", "seed": 42}}))
            w.window_ctl.set_normal_size(640, 520)
            self.shot(w, "v134-choice-" + key)
            self.shot(w.btn_study_dk, "v134-dk-choice-" + key)
            w.open_settings()
            self.shot(w, "v134-settings-on-" + key)
            QTest.mouseClick(w.btn_edge_collapse, Qt.LeftButton)
            self.shot(w, "v134-settings-off-" + key)
            QTest.mouseClick(w.study_mode_chips["brush"], Qt.LeftButton)
            w.close_settings()
            self.shot(w, "v134-brush-" + key)
            self.shot(w.btn_forget, "v134-dk-brush-" + key)
            w.set_compact(True)
            self.shot(w, "v134-compact-" + key)
            w.open_settings()
            w.start_quiz()
            base.pump()
            self.shot(w, "v134-quiz-" + key)
            self.shot(w.btn_dontknow, "v134-dk-quiz-" + key)
        self.dk_overview()

    def dk_overview(self):
        cell_w, row_h, head_h, side_w = 620, 82, 52, 100
        image = QImage(side_w + cell_w * 3, head_h + row_h * 4, QImage.Format_ARGB32)
        image.fill(QColor("#e9edf2"))
        painter = QPainter(image)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(18)
        painter.setFont(font)
        painter.setPen(QColor("#26364a"))
        for col, label in enumerate(("刷词", "选择题", "词汇量测试")):
            painter.drawText(QRect(side_w + col * cell_w, 0, cell_w, head_h), Qt.AlignCenter, label)
        names = dict(th.options())
        for row, key in enumerate(th.ORDER):
            palette = th.get(key)
            y = head_h + row * row_h
            painter.fillRect(QRect(0, y, image.width(), row_h), QColor(palette["bg"]))
            painter.setPen(QColor(palette["fg_word"]))
            painter.drawText(QRect(0, y, side_w, row_h), Qt.AlignCenter, names[key])
            for col, mode in enumerate(("brush", "choice", "quiz")):
                original = QImage(self.sb.shot("v134-dk-%s-%s" % (mode, key)))
                self.check(not original.isNull() and original.width() <= cell_w,
                           key + "原生控件图像可完整放入对比图（不缩放/拉伸）")
                painter.drawImage(side_w + col * cell_w + (cell_w - original.width()) // 2,
                                  y + (row_h - original.height()) // 2, original)
        painter.end()
        path = self.sb.shot("v134-native-dontknow-overview" if base.FLAGS.native else "v134-dontknow-overview")
        self.check(image.save(path), "保存四主题三入口对比图")
        self.screens.append(path)


def run_suite():
    label = "v134-native" if base.FLAGS.native else "v134-offscreen"
    root = Path(base.__file__).resolve().parents[2] / ".vocab-ui-tests" / "v134-integration"
    root.mkdir(parents=True, exist_ok=True)
    outdir = tempfile.mkdtemp(prefix=label + "-", dir=str(root))
    with patch.dict(os.environ, {"VOCAB_TEST_OUT": outdir}):
        sb = base.Sandbox(base.app_main, label)
    with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok), \
            patch.dict(os.environ, {"VOCABAPP_DATA_DIR": str(Path(sb.progress_path).parent)}):
        with sb:
            suite = V134Suite(sb)
            suite.out.append("PLATFORM " + ("native" if base.FLAGS.native else "offscreen"))
            suite.out.append("VERSION " + base.app_main.VERSION)
            with patch.object(sys, "excepthook", suite.exception):
                for key in th.ORDER:
                    suite.run("settings-" + key, lambda k=key: suite.settings_contract(k))
                    suite.run("dontknow-" + key, lambda k=key: suite.dontknow_contract(k))
                for enabled in (False, True):
                    suite.run("preference-restart-%s" % enabled, lambda on=enabled: suite.preference_restart(on))
                suite.run("legacy-preference", suite.legacy_preference)
                for compact in (False, True):
                    for phase in ("collapse", "expand"):
                        for edge in ("left", "right", "top", "bottom"):
                            suite.run("toggle-%s-%s-%s" % (compact, phase, edge),
                                      lambda cp=compact, ph=phase, ed=edge: suite.animation_toggle(cp, ph, ed))
                suite.run("display-identity", suite.display_identity)
                suite.run("window-save-failure", suite.window_save_failure)
                suite.run("compact-save-failure", suite.compact_save_failure)
                suite.run("source-count-display", suite.source_count_display)
                suite.run("book-composition-revision", suite.composition_revision)
                if os.environ.get("VOCAB_V134_SKIP_IMAGES") != "1":
                    suite.run("real-source-contract", suite.real_source_contract, fake=False)
                    suite.run("illustrations", suite.illustrations, fake=False)
                suite.check(sb.verify_real(), "最终真实progress/window/bak/tmp字节均未改变")
    suite.out.append("\nCHECKS %d; FAILS %d" % (suite.checks, len(suite.fails)))
    for path in suite.screens:
        suite.out.append("SCREENSHOT " + path)
    code = sb.finish(suite.out, suite.fails, "test_v134_ui.txt")
    print("V134 CHECKS", suite.checks, "FAILS", len(suite.fails) + len(sb.errors))
    return code


if __name__ == "__main__":
    sys.exit(run_suite())
