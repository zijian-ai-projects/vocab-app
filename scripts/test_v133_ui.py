# -*- coding: utf-8 -*-
"""V1.3.3 新界面回归：提示、音标、图标、表头焦点和四主题侧边动画。

python -B scripts/test_v133_ui.py [--native]
复用 V1.3.0 的冻结 8 词 fixture / Sandbox；不启动默认资料的 main.main。
真实词库仅用于隔离示意图。所有输出保留在 .vocab-ui-tests。
"""
from copy import deepcopy
from pathlib import Path
import os
import struct
import sys
from unittest.mock import patch

import test_v130_ui as base
from PyQt5.QtCore import QEvent, QPoint, QSize, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox

import app_icon
import books as real_books
import theme as th
from windowing import DOCK_ANIM_MS, DOCK_LENGTH, STRIP_THICKNESS


class V133Suite(base.Suite):
    def shot(self, widget, name):
        base.pump(12)
        path = self.sb.shot(name)
        self.check(widget.grab().save(path), "保存隔离截图 " + name)
        self.screens.append(path)

    def hint_free(self, level, unknown):
        states = {base.KEYS[0]: base.learning(level, self.clock() - 1)} if level else {}
        w = self.card(base.progress(study_mode="choice", states=states))
        q = w.choice_question
        self.check(w.mode == "choice", "真实选择题窗口已显示", require=True)
        if unknown:
            QTest.mouseClick(w.btn_study_dk, Qt.LeftButton)
        else:
            QTest.mouseClick(w.study_btns[(q["correct"] + 1) % 4], Qt.LeftButton)
        base.pump()
        self.check(w.mode == "choice_back" and w.choice_locked, "回答后锁定题目并展示下一题")
        self.check(w.choice_hint.isHidden() and w.choice_hint.text() == "", "答错/不认识提示清空且隐藏，无等级/重现规则占位")
        self.check(w.status.isHidden(), "学习状态HUD继续隐藏")
        self.check(w.states[base.KEYS[0]]["lv"] == level, "移除提示不改变记忆等级")
        self.check(w.btn_study_next.isVisibleTo(w) and not w.btn_study_dk.isVisibleTo(w), "下一题可操作、不认识按钮不残留")
        self.check(w.study_btns[q["correct"]].property("state") == "correct", "正确释义仍有选项反馈")
        if not unknown:
            self.check(w.study_btns[(q["correct"] + 1) % 4].property("state") == "wrong", "错误选项仍有反馈")
        QTest.keyClick(w, Qt.Key_Z, Qt.ControlModifier)
        self.check(w.mode == "choice" and w.choice_hint.isHidden() and w.choice_hint.text() == "", "撤销返回原题仍无提示")
        self.check(w.states == states, "撤销完整恢复作答前状态")
        self.aliases(w)

    def ipa_ui(self, mode):
        w = self.card(base.progress(study_mode=mode))
        row = w.queue[w.qi]["w"]
        for value in ("", "\\", "\\\\", "/", " /\\/ ", "æ\\:s"):
            row["ipa"] = value
            row["ph_raw"] = ""
            w._show_current()
            base.pump()
            self.check(w.ipa.text() == w.choice_ipa.text() == "", "缺失/占位/损坏音标不渲染：%r" % value)
            target = w.choice_ipa if mode == "choice" else w.ipa
            self.check(target.isHidden(), "空音标不保留斜线或可见标签")
        row["ipa"] = "əˈbɪləti"
        w._show_current()
        target = w.choice_ipa if mode == "choice" else w.ipa
        self.check(target.text() == "/əˈbɪləti/" and not target.isHidden(), "合法音标在当前模式按原文显示一对斜线")

    def icon_ui(self):
        w = self.card()
        icon = app_icon.application_icon()
        self.check(not icon.isNull() and not w.windowIcon().isNull() and not base.APP.windowIcon().isNull(), "应用与窗口均有原创图标")
        sizes = {s.width() for s in icon.availableSizes()}
        self.check(set(app_icon.ICON_SIZES).issubset(sizes), "ICO包含16–256全部9种独立尺寸：%r" % sorted(sizes))
        data = (Path(app_icon.ASSET_DIR) / "vocab-card.ico").read_bytes()
        self.check(struct.unpack_from("<HHH", data) == (0, 1, len(app_icon.ICON_SIZES)), "Windows ICO目录头与帧数有效")
        png = QImage(str(Path(app_icon.ASSET_DIR) / "vocab-card.png"))
        self.check(png.size() == QSize(512, 512) and png.hasAlphaChannel(), "PNG为512px透明图标资源")
        rendered = app_icon.render_icon(256).toImage()
        self.check(rendered.pixelColor(168, 59) == QColor("#d4a666"), "词卡书签保留暖金品牌色")
        self.check(rendered.pixelColor(0, 0).alpha() == 0, "图标四角透明")
        self.check(base.APP.applicationDisplayName() == "背单词", "应用中文显示名保持不变")
        original = w.windowIcon().cacheKey()
        w.set_theme("sepia")
        self.check(w.windowIcon().cacheKey() == original, "主题切换不换回默认图标")
        if os.name == "nt":
            self.check(app_icon.set_windows_app_id(), "独立Windows任务栏身份可设置，不修改注册表")
            if base.FLAGS.native:
                import ctypes
                from ctypes import wintypes
                send = ctypes.windll.user32.SendMessageW
                send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                send.restype = ctypes.c_ssize_t
                self.check(bool(send(int(w.winId()), 0x007F, 1, 0)), "Windows WM_GETICON大图标句柄存在")
                self.check(bool(send(int(w.winId()), 0x007F, 0, 0)), "Windows WM_GETICON小图标句柄存在")

    def header_ui(self):
        w = self.card()
        w.open_settings()
        w.open_catalog(base.BOOK)
        c = w.catalog
        header = c.level_header
        base.pump(12)
        for col in range(3):
            x = header.sectionViewportPosition(col) + header.sectionSize(col) // 2
            QTest.mouseClick(header.viewport(), Qt.LeftButton, pos=QPoint(x, header.height() // 2))
            base.pump()
            self.check(not c.table.currentIndex().isValid(), "点击表头%d不设置首行current焦点虚线" % col)
            self.check(not c.table.selectionModel().selectedIndexes(), "点击表头%d仍无选中行" % col)
            if col == 2:
                self.check(c.level_dialog is not None and c.level_dialog.isVisible(), "记忆等级表头仍打开说明")
                c.level_dialog.close()
                base.pump()
        QTest.mouseClick(header.badge, Qt.LeftButton)
        base.pump()
        self.check(c.level_dialog is not None and c.level_dialog.isVisible(), "透明描边感叹号徽标仍打开说明")
        c.level_dialog.close()

    def order_ui(self):
        import random
        expected = list(base.KEYS)
        random.Random(42).shuffle(expected)
        w = self.card()
        before = Path(self.sb.progress_path).read_bytes()
        w.open_books("settings")
        w._nav_into_main("fixture-main")
        w._nav_into_group("fixture-group")
        QTest.mouseClick(w.chip_shuffle, Qt.LeftButton)
        QTest.mouseClick(w.book_btns[base.BOOK], Qt.LeftButton)
        self.check(w.sel_order == "shuffle" and w.chip_shuffle.property("on") == "1", "先乱序再点词书仍明确选中乱序")
        QTest.mouseClick(w.btn_catalog_books, Qt.LeftButton)
        base.pump()
        self.check([row["w"] for row in w.catalog.model.rows] == expected, "确认前浏览目录已按所选稳定乱序展示")
        self.check(Path(self.sb.progress_path).read_bytes() == before, "未确认前不改原学习进度")
        QTest.keyClick(w, Qt.Key_Escape)
        QTest.mouseClick(w.btn_learn, Qt.LeftButton)
        base.pump()
        self.check(w.order_mode == "shuffle" and [row["w"] for row in w.queue_words] == expected, "真实确认按钮重建乱序学习队列")
        self.check(base.key_of(w) == expected[0] and w.study_record["cursor"] == 0, "模式变更不沿用旧顺序的未答词或游标")
        saved = self.sb.read_progress()
        self.check(saved["orders"][base.BOOK] == {"mode": "shuffle", "seed": 42}, "确认保存词序，随机seed保持稳定")
        w = self.card(restart=True)
        self.check(w.order_mode == "shuffle" and base.key_of(w) == expected[0], "重启仍乱序并续上同一未答词")
        w.open_books("settings")
        w._nav_into_main("fixture-main")
        w._nav_into_group("fixture-group")
        QTest.mouseClick(w.chip_seq, Qt.LeftButton)
        QTest.mouseClick(w.book_btns[base.BOOK], Qt.LeftButton)
        self.check(w.sel_order == "seq" and w.chip_seq.property("on") == "1", "反向先顺序再点已存乱序的书也不覆盖")
        QTest.mouseClick(w.btn_learn, Qt.LeftButton)
        self.check(w.order_mode == "seq" and [row["w"] for row in w.queue_words] == list(base.KEYS), "确认恢复原书顺序")
        self.check(base.key_of(w) == base.KEYS[0], "乱序改顺序重新选取排序后的首个未学词")
        w = self.card(restart=True)
        self.check(w.order_mode == "seq" and base.key_of(w) == base.KEYS[0], "反向变更重启保持顺序与未答词")
        self.check(w.states == {} and w.orders[base.BOOK]["seed"] == 42, "两次改序不伪造记忆状态、不重新洗牌")

    def dock_ui(self):
        w = self.card()
        c = w.window_ctl
        area = base.APP.primaryScreen().availableGeometry()
        for theme_key in th.ORDER:
            w.set_theme(theme_key)
            for edge in ("left", "right", "top", "bottom"):
                c.restore({"normal_w": 520, "normal_h": 430, "normal_x": area.left() + 100,
                           "normal_y": area.top() + 100, "dock_edge": edge})
                w._set_mode("front")
                c.stop_timers()
                c._hover_inside = False
                w._window_save_timer.stop()
                before = deepcopy(c.state())
                sig = w._scale_signature
                self.check(c.theme == w.t, theme_key + "启动/切换后controller主题一致")
                self.check(c._collapse_if_docked(force=True, immediate=False), edge + "启动缓动收起")
                QTest.qWait(30)
                self.check(c.animating and not c.can_persist_geometry, edge + "中间帧仍在动画中")
                self.check(c._dock_overlay is not None and c._dock_overlay.isVisibleTo(w), edge + "快照overlay实际可见，而非被collapsed过滤器隐藏")
                with patch.object(base.storage, "atomic_save", wraps=base.storage.atomic_save) as save:
                    w._save_window()
                    w._flush_window()
                    w._apply_scaling(force=True)
                    self.check(save.call_count == 0 and w._scale_signature == sig, edge + "动画中不保存/不字体重排")
                QTest.qWait(DOCK_ANIM_MS + 25)
                c._hover_timer.stop()
                self.check(c.collapsed and not c.animating, edge + "收起完成并解除动画锁")
                expected = QSize(STRIP_THICKNESS, DOCK_LENGTH) if edge in ("left", "right") else QSize(DOCK_LENGTH, STRIP_THICKNESS)
                self.check(w.size() == expected and not w.stage.isVisibleTo(w), edge + "10×64短胶囊且学习内容隐藏")
                self.check(c.state() == before, edge + "收起不改变逻辑尺寸/坐标/偏好")
                if edge == "left":
                    self.shot(w, "v133-dock-" + theme_key)
                c._hover_inside = True
                c.reveal(immediate=False)
                QTest.qWait(30)
                self.check(c.animating and c._dock_overlay is not None and c._dock_overlay.isVisibleTo(w), edge + "展开动画快照实际可见")
                QTest.qWait(DOCK_ANIM_MS + 25)
                c._hover_timer.stop()
                self.check(not c.animating and not c.collapsed and w.size() == QSize(520, 430), edge + "展开落定520×430")
                self.check(w.stage.isVisibleTo(w) and c._dock_overlay is None, edge + "展开后恢复真实控件且释放overlay")
                self.check(c.state() == before, edge + "完整收/展逻辑状态保持一致")
        # 外部切页必须立即落定正在展开的动画，不让压缩的几何进入设置页。
        c._hover_inside = False
        c._collapse_if_docked(force=True, immediate=False)
        QTest.qWait(DOCK_ANIM_MS + 20)
        c.reveal(immediate=False)
        QTest.qWait(20)
        c.reveal(immediate=True)
        self.check(not c.animating and not c.collapsed and w.size() == QSize(520, 430), "外部immediate reveal终止展开中动画")
        c.stop_timers()

    def illustrations(self):
        book = real_books.DEFAULT
        words = real_books.words(book)
        target = next((word for word in ("ability", "abandon", "challenge") if word in words), words[0])
        w = self.card(base.progress(book=book, history=[], study_mode="choice", states={},
                                   cursors={book: words.index(target)}, orders={book: {"mode": "seq", "seed": 42}}))
        w.window_ctl.set_normal_size(640, 520)
        for key in th.ORDER:
            w.set_theme(key)
            self.check(w.window_ctl.theme == th.get(key), key + "真实词库示意图与侧边调色一致")
            self.shot(w, "v133-choice-" + key)
            w.open_settings()
            self.shot(w, "v133-settings-" + key)
            w.close_settings()


def run_suite():
    label = "v133-native" if base.FLAGS.native else "v133-offscreen"
    sb = base.Sandbox(base.app_main, label)
    suite = None
    with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok), \
            patch.dict(os.environ, {"VOCABAPP_DATA_DIR": str(Path(sb.progress_path).parent)}):
        with sb:
            suite = V133Suite(sb)
            suite.out.append("PLATFORM " + ("native" if base.FLAGS.native else "offscreen"))
            suite.out.append("Protected legacy/stable paths: %d" % len(sb.watch_paths))
            with patch.object(sys, "excepthook", suite.exception):
                for level in (0, 4):
                    for unknown in (False, True):
                        suite.run("hint-lv%d-%s" % (level, "unknown" if unknown else "wrong"),
                                  lambda lv=level, dk=unknown: suite.hint_free(lv, dk))
                for mode in ("brush", "choice"):
                    suite.run("ipa-" + mode, lambda key=mode: suite.ipa_ui(key))
                suite.run("app-icon", suite.icon_ui)
                suite.run("header-no-focus", suite.header_ui)
                suite.run("order-confirm-and-restart", suite.order_ui)
                suite.run("four-theme-dock-animation", suite.dock_ui)
                suite.run("illustrations", suite.illustrations, fake=False)
            suite.check(sb.verify_real(), "最终真实progress/window/bak/tmp全部字节不变")
    suite.out.append("\nCHECKS %d; FAILS %d" % (suite.checks, len(suite.fails)))
    for path in suite.screens:
        suite.out.append("SCREENSHOT " + path)
        print("SCREENSHOT", path)
    code = sb.finish(suite.out, suite.fails, "test_v133_ui.txt")
    print("V133 CHECKS", suite.checks, "FAILS", len(suite.fails) + len(sb.errors))
    return code


if __name__ == "__main__":
    sys.exit(run_suite())
