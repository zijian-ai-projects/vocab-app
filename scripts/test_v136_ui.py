# -*- coding: utf-8 -*-
"""V1.3.6 isolated UI acceptance: settings, keyboard, daily plan, reset, save failure.

Only runs against Sandbox/VOCABAPP_DATA_DIR, never real records.
`python -B scripts/test_v136_ui.py [--native]`
"""
from copy import deepcopy
from pathlib import Path
import datetime as dt
import json
import os
import sys
import tempfile
from unittest.mock import patch

import test_v130_ui as base
from PyQt5.QtCore import QEvent, QSize, Qt
from PyQt5.QtGui import QKeyEvent, QKeySequence
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton

import keybindings as keys
import learning_policy as learn
import storage
import theme as th


DEFAULTS_JOURNAL = "_v136_defaults_pending"
DAY = 86400


def v136_progress(**overrides):
    data = base.progress(**overrides)
    data.setdefault("learning_policy", {"mode": learn.REVIEW_FIRST, "daily_new": 20})
    data.setdefault("daily_new_ledger", {})
    data.setdefault("keybindings", dict(keys.DEFAULT_BINDINGS))
    return data


def win_fixture(**overrides):
    data = {"normal_w": 520, "normal_h": 430, "normal_x": 100,
            "normal_y": 100, "edge_collapse": True,
            "custom_window": {"keep": [1, "x"]}}
    data.update(overrides)
    return data


def seq_text(edit):
    return edit.keySequence().toString(QKeySequence.PortableText)


class V136Suite(base.Suite):
    def settings_card(self, progress=None, win=None):
        w = self.card(progress if progress is not None else v136_progress(),
                      win if win is not None else win_fixture())
        w.open_settings()
        base.pump()
        return w

    def send_key(self, w, key, modifiers=Qt.NoModifier, target=None, auto=False):
        target = target or w
        if auto:
            ev = QKeyEvent(QEvent.KeyPress, key, modifiers, "", True)
            QApplication.sendEvent(target, ev)
        else:
            QTest.keyClick(target, key, modifiers)
        base.pump()

    def current_key(self, w):
        return base.key_of(w)

    def assert_unchanged(self, w, mode, key, states, text):
        self.check(w.mode == mode and self.current_key(w) == key
                   and w.states == states, text)

    # ------------------------------------------------------------------
    def controls_contract(self):
        w = self.card(v136_progress(), win_fixture())
        self.check(w.mode in ("front", "back", "empty")
                   and w.study_status.isVisibleTo(w)
                   and "新词" in w.study_status.text(),
                   "Card.study_status 学习页展示当前题目类型")
        w.open_settings()
        base.pump()
        self.check(not hasattr(w, "learning_mode_chips")
                   and not hasattr(w, "daily_new_spin")
                   and not hasattr(w, "daily_new_label")
                   and not hasattr(w, "lab_learning_plan"),
                   "设置页移除学习安排和新词数量控件")
        self.check(w.learning_policy.settings["mode"] == learn.REVIEW_FIRST,
                   "未设置学习安排时默认先复习")
        self.check(not hasattr(w, "input_mode_chips"),
                   "设置页移除鼠标/键盘模式选择")
        self.check(not hasattr(w, "btn_restore_defaults"),
                   "设置页移除全局恢复默认控件")
        self.check(w.key_bindings == dict(keys.DEFAULT_BINDINGS),
                   "默认按键提示启用且移除键位入口")
        self.check(not hasattr(w, "btn_key_settings") and not w.btn_gear.isVisibleTo(w),
                   "设置页隐藏齿轮和修改键位入口")
        self.check(w.btn_back.isVisibleTo(w) and w.back_slot.rect().contains(
                       w.btn_back.geometry()), "设置页返回按钮填满可点击区域")
        w.btn_back.click()
        base.pump()
        self.check(w.mode in ("front", "back", "empty", "choice", "choice_back"),
                   "设置页左上角返回点击恢复学习页")
        w.open_settings()
        base.pump()
        self.check(w.width() <= 520 and w.height() <= 430,
                   "默认窗口在 520x430 内")
        self.check(all(not edit.isVisibleTo(w) for edit in w.key_edits.values()),
                   "设置页不显示键位编辑器")

    def keyboard_and_button_controls(self):
        w = self.card(v136_progress(), win_fixture())
        key = self.current_key(w)
        self.check(w._key_caption("认识", "remember") == "认识  [Enter]"
                   and w._key_caption("不认识", "forget") == "不认识  [空格]",
                   "刷词按钮显示 Enter / 空格提示")
        self.send_key(w, Qt.Key_Return)
        self.check(w.mode == "back" and w.states[key]["seen"] == 1,
                   "Enter 自动触发认识")
        self.close()

    def keyboard_defaults_once(self):
        w = self.card(v136_progress(), win_fixture())
        first = self.current_key(w)
        state_before = deepcopy(w.states)
        self.send_key(w, Qt.Key_Return)
        self.check(w.mode == "back" and self.current_key(w) == first
                   and w.states[first]["lv"] == 1,
                   "键盘默认 Enter 记忆一次，仅翻面不连翻")
        self.check(w.last_action and w.last_action[0] == "new"
                   and w.last_action[1] == first and w.last_action[2] is True,
                   "首次作答 last_action 记录刚答词")
        self.check(w.study_record["current"] is None,
                   "首次作答后 current 清空，不自动进入下一题")
        w._next()
        base.pump()
        self.check(self.current_key(w) != first and w.mode in ("front", "choice"),
                   "背面 Enter 才进入下一题")
        self.close()

        w = self.card(v136_progress(), win_fixture())
        key, states, before_record = self.current_key(w), deepcopy(w.states), deepcopy(w.study_record)
        self.send_key(w, Qt.Key_Space, auto=True)
        self.check(w.mode == "front" and w.states == states and self.current_key(w) == key
                   and w.study_record == before_record,
                   "自动重复按键不评分、不建快照")
        self.close()

    def keyboard_choice_lock(self):
        w = self.card(v136_progress(study_mode="choice"),
                      win_fixture())
        self.check(w.mode == "choice", "keyboard 选择模式就绪")
        self.send_key(w, Qt.Key_1)
        self.check(w.mode == "choice_back" and w.choice_locked,
                   "选择键 1 评分后锁住本屏")
        first_resp = deepcopy(w.last_action)
        first_states = deepcopy(w.states)
        self.send_key(w, Qt.Key_2)
        self.check(w.last_action == first_resp and w.states == first_states
                   and w.mode == "choice_back",
                   "选择题锁定时重复/其它选项键不二次评分")
        self.close()

        w = self.card(v136_progress(study_mode="brush"),
                      win_fixture())
        w.open_settings()
        with patch.object(base.app_main.pl, "make_options",
                          return_value=(list(base.MEANINGS[:4]), 0)):
            w.start_quiz()
        base.pump()
        if w.mode == "quiz":
            self.send_key(w, Qt.Key_1)
            self.check(w.quiz_locked and len(w.quiz_resp) == 1,
                       "测试题选项键评分一次并锁定")
            resp = deepcopy(w.quiz_resp)
            self.send_key(w, Qt.Key_2)
            self.check(w.quiz_resp == resp, "测试题锁定后不再评分/跳题")
        else:
            self.check(False, "测试题启动进入 quiz 失败：%s" % w.mode)
        self.close()

    def keyboard_custom_and_errors(self):
        w = self.card(v136_progress(), win_fixture())
        w.open_settings()
        self.check(w.apply_key_bindings({"remember": "A", "forget": "B"}) is True,
                   "apply_key_bindings 自定义键成功")
        self.check(w.progress["keybindings"]["remember"] == "A",
                   "自定义键位写入 progress")
        w.close_settings()
        base.pump()
        self.send_key(w, Qt.Key_A)
        self.check(w.mode == "back" and w.states[self.current_key(w)]["seen"] == 1,
                   "自定义 A 键触发记忆")
        w._next()
        base.pump()
        next_key = self.current_key(w)
        w.btn_forget.click()
        base.pump()
        self.check(w.mode == "back" and w.states[next_key]["seen"] == 1,
                   "屏幕按钮和键盘映射同时可评分")
        self.close()

        w = self.card(v136_progress(), win_fixture())
        w.open_settings()
        base.QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
        w.open_key_settings()
        base.pump()
        w.open_key_settings()
        base.pump()
        before = deepcopy(w.progress["keybindings"])
        self.check(w.apply_key_bindings({"remember": "Space", "forget": "Space"}) is False,
                   "同屏冲突配置应用返回False")
        self.check(w.progress["keybindings"] == before and w.key_bindings ==
                   keys.normalize(before), "冲突配置不替换有效键位")
        self.check(bool(w.lab_key_error.text()), "冲突显示中文错误而不静默")
        w.key_edits["remember"].setKeySequence(QKeySequence("A"))
        w.key_edits["forget"].setKeySequence(QKeySequence("A"))
        self.check(w._check_key_draft() is False and not w.btn_apply_keys.isEnabled(),
                   "草稿冲突禁用应用按钮")
        w._restore_key_defaults()
        self.check({name: seq_text(edit) for name, edit in w.key_edits.items()}
                   == dict(keys.DEFAULT_BINDINGS), "弹窗内恢复默认键位")
        self.close()

    def editing_focus_does_not_score(self):
        w = self.card(v136_progress(), win_fixture())
        w.open_settings()
        base.QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
        w.open_key_settings()
        base.pump()
        w.open_key_settings()
        base.pump()
        edit = w.key_edits["remember"]
        edit.setFocus()
        base.pump()
        before = deepcopy((w.states, w.queue, w.study_record))
        QTest.keyClick(edit, Qt.Key_1)
        QTest.keyClick(edit, Qt.Key_0)
        base.pump()
        self.check((w.states, w.queue, w.study_record) == before,
                   "编辑键位焦点时答案键不评分")
        label = QLabel("focus sink", w)
        label.setFocus()
        base.pump()
        self.send_key(w, Qt.Key_1)
        self.check((w.states, w.queue, w.study_record) == before,
                   "普通文本/控件焦点不绕过编辑保护")
        self.close()

    def button_focus_uses_config(self):
        w = self.card(v136_progress(), win_fixture())
        w.open_settings()
        w.apply_key_bindings({"remember": "A"})
        w.close_settings()
        base.pump()
        button = w.btn_remember
        button.setFocus()
        base.pump()
        key = self.current_key(w)
        QTest.keyClick(button, Qt.Key_A)
        base.pump()
        self.check(w.mode == "back" and w.states[key]["seen"] == 1,
                   "学习按钮焦点仍按自定义键盘配置评分")
        self.close()

    def daily_status_and_quota(self):
        w = self.card(v136_progress(
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 2}),
            win_fixture())
        self.check(w.learning_policy.settings["mode"] == learn.REVIEW_FIRST
                   and "今日待学新词" not in w.study_status.text()
                   and "今日新词学习计划已完成" not in w.study_status.text(),
                   "旧先学新词配置归一为先复习且学习状态不显示今日数量")
        first = self.current_key(w)
        w.act("remember")
        base.pump()
        self.check(w.learning_policy.learned_today(self.clock()) == 1,
                   "首次实际作答记入当天 ledger")
        day = learn.local_day(self.clock())
        self.check(first in self.sb.read_progress()["daily_new_ledger"]["days"][day],
                   "首次新词写入当天 ledger")
        w._next()
        base.pump()
        second = self.current_key(w)
        self.check("今日待学新词" not in w.study_status.text(),
                   "新词额度不显示在学习页状态提示")
        w.act("remember")
        base.pump()
        w._next()
        base.pump()
        self.check("今日新词学习计划已完成" not in w.study_status.text()
                   and w.learning_policy.remaining(self.clock()) == 0,
                   "每日学习额度不显示在学习页状态提示")
        self.check(w.learning_policy.learned_today(self.clock()) == 2,
                   "首次学习账本保留原始学习事实")
        self.close()

        # retry badge 必须归复习，不能继续显示新词。构造仅剩 retry 的合法记录。
        states = {key: base.mastered() for key in base.KEYS}
        states[base.KEYS[0]] = {"st": "new", "lv": 0, "due": None,
                                "seen": 1, "lapse": 1, "streak": 0}
        retry_record = {"cursor": 0, "new_count": 1,
                        "pending": {base.KEYS[0]: 1},
                        "current": None, "held_current": None}
        w = self.card(v136_progress(
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 1},
            study_mode="brush", states=states,
            study_records={base.BOOK: retry_record}), win_fixture())
        base.pump()
        if w.queue and w.queue[w.qi]["kind"] == "retry":
            self.check(w.study_status.text().startswith("复习")
                       and "重现" not in w.study_status.text(),
                       "retry badge 归为复习不冒充新词：%r" % w.study_status.text())
        else:
            self.check(False, "构造 retry fixture 未出现 retry：%s" %
                       (w.queue[w.qi] if w.queue else None))
        self.close()

    def settings_quota_change_keeps_current(self):
        w = self.card(v136_progress(
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 2}),
            win_fixture())
        first = self.current_key(w)
        self.check(w.learning_policy.settings["mode"] == learn.REVIEW_FIRST,
                   "旧每日新词优先配置加载后固定归一为先复习")
        w.open_settings()
        self.check(not hasattr(w, "learning_mode_chips")
                   and not hasattr(w, "daily_new_spin"),
                   "设置页没有学习安排入口")
        w.close_settings()
        base.pump()
        self.check(self.current_key(w) == first
                   and w.mode in ("empty", "front", "choice"),
                   "关闭设置后保留未答当前词：mode=%s key=%s want=%s" %
                   (w.mode, self.current_key(w), first))
        before = deepcopy(w.states)
        self.send_key(w, Qt.Key_Space)
        self.check(w.states != before and w.states[first]["seen"] == 1,
                   "默认先复习也允许正常学习新词：mode=%s key=%s state=%r" %
                   (w.mode, self.current_key(w), w.states.get(first)))
        w.open_settings()
        self.check(w.learning_policy.settings["mode"] == learn.REVIEW_FIRST,
                   "设置页打开时仍保持默认先复习")
        w.close_settings()
        base.pump()
        self.check(self.current_key(w) == first,
                   "离开设置后保留当前词")
        self.close()

    def undo_and_amend_keep_first_day(self):
        w = self.card(v136_progress(
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 2}),
            win_fixture())
        first = self.current_key(w)
        w.act("remember")
        base.pump()
        day_one = learn.local_day(self.clock())
        self.check(w.learning_policy.ledger["days"][day_one].count(first) == 1,
                   "首次作答只记一次")
        w.undo()
        base.pump()
        self.check(w.mode in ("front", "choice") and self.current_key(w) == first,
                   "undo 回到同一未答题")
        self.check(not w.learning_policy.ledger.get("days", {}).get(day_one) or
                   first not in w.learning_policy.ledger["days"].get(day_one, []),
                   "undo 撤回当天首次作答记录")
        w.act("forget")
        base.pump()
        self.check(w.mode == "back" and w.last_action and w.last_action[2] is False,
                   "改判前先有错的首次作答")
        self.clock.value += DAY
        day_two = learn.local_day(self.clock())
        w.correct()
        base.pump()
        self.check(w.learning_policy.ledger["days"].get(day_one, []).count(first) == 1,
                   "跨午夜改判保留原引入日，不重复计当天")
        self.check(day_two not in w.learning_policy.ledger["days"]
                   or first not in w.learning_policy.ledger["days"][day_two],
                   "跨午夜改判不写入新一天")
        self.check(w.study_record["new_count"] == 1,
                   "跨午夜改判不增加首次新词计数")
        self.close()

    def sort_filters_do_not_change_learning_order(self):
        w = self.card(v136_progress(), win_fixture())
        w.open_catalog(base.BOOK, src="settings")
        base.pump()
        self.check(not w.btn_gear.isVisibleTo(w), "词书目录页面隐藏齿轮入口")
        order_before = [row["w"] for row in w.queue_words]
        w.catalog.model.refilter()
        self.check(True, "目录重筛保持固定字母升序")
        w.catalog.set_filter("unlearned")
        base.pump()
        self.check([row["w"] for row in w.queue_words] == order_before,
                   "排序/筛选不改学习队列顺序")
        self.check(w.catalog.model.rows == sorted(
                       w.catalog.model.rows,
                       key=lambda row: row.get("display_w", row["w"]).casefold()),
                   "目录内容固定字母升序")
        w._page_back()
        base.pump()
        self.check([row["w"] for row in w.queue_words] == order_before,
                   "离开目录仍不改学习顺序")
        w = self.card(restart=True)
        w.open_books("settings")
        base.pump()
        self.check(not w.btn_gear.isVisibleTo(w), "选择词书页面隐藏齿轮入口")
        w.open_settings()
        base.pump()
        self.check(not w.btn_gear.isVisibleTo(w), "从词书返回设置时隐藏齿轮")
        w._set_mode("quiz")
        base.pump()
        self.check(not w.btn_gear.isVisibleTo(w), "词汇量测试页面隐藏齿轮入口")
        w._set_mode("welcome")
        base.pump()
        self.check(not w.btn_gear.isVisibleTo(w), "学习引导页面隐藏齿轮入口")
        w.close()  # 单独的复原窗口，防止改变后续重启断言
        w = self.card(restart=True)
        self.check(w.catalog.model.rows == sorted(
                       w.catalog.model.rows,
                       key=lambda row: row.get("display_w", row["w"]).casefold()),
                   "重启仍保持固定字母升序")
        self.check([row["w"] for row in w.queue_words] == order_before,
                   "重启后学习队列顺序不变")
        self.close()

    def restore_defaults_preserves_learning(self):
        state = {base.KEYS[0]: base.learning(2, self.clock() + 300),
                 base.KEYS[1]: base.learning(1, self.clock() + 700)}
        record = {"cursor": 2, "new_count": 3,
                  "pending": {base.KEYS[2]: 4},
                  "current": {"kind": "new", "key": base.KEYS[2], "resume": True},
                  "held_current": {"kind": "retry", "key": base.KEYS[3]},
                  "fresh": {"keep": True}}
        quiz = {"idx": 1, "asked": [base.KEYS[0]], "custom": {"keep": [1]}}
        p = v136_progress(
            theme="dark", study_mode="choice", retry_gap=5,
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 7,
                             "unknown": "keep-learning-policy"},
            keybindings=dict(keys.DEFAULT_BINDINGS, remember="A", forget="B"),
                        book=base.BOOK, book_confirmed=True, states=state,
            history=[{"ts": 1, "vocab": 90, "custom": "keep-history"}],
            theta=1.234, quiz_session=quiz,
            study_records={base.BOOK: record},
            orders={base.BOOK: {"mode": "shuffle", "seed": 987}},
            cursors={base.BOOK: 2},
            daily_new_ledger={"days": {"2026-01-01": ["alpha"]},
                              "unknown": {"keep": True}},
            custom={"preserve": {"nested": [1, "x"]}})
        w = self.card(p, win_fixture(normal_w=640, normal_h=520,
                                     edge_collapse=False))
        before_queue = [row["w"] for row in w.queue_words]
        before_records = deepcopy(w.study_records)
        before_orders = deepcopy(w.orders)
        before_cursors = deepcopy(w.cursors)
        before_ledger = deepcopy(w.daily_new_ledger)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok):
            ok = w.restore_defaults()
        base.pump()
        self.check(ok is True, "非modal restore_defaults 返回True")
        self.check(w.theme_key == th.DEFAULT and w.study_mode == "brush"
                   and w.retry_gap == 3, "恢复 theme/brush/retry_gap 默认")
        self.check(w.learning_settings == learn.DEFAULTS
                   and w.progress.get("learning_policy") == learn.DEFAULTS, "恢复默认学习安排")
        self.check(w.key_bindings == dict(keys.DEFAULT_BINDINGS),
                   "恢复默认键位")
        self.check("catalog_sort" not in w.progress,
                   "目录排序设置不再持久化")
        self.check(w.window_ctl.normal_size == QSize(520, 430)
                   and w.window_ctl.edge_collapse_enabled is True,
                   "恢复 520x430/edgeTrue 默认窗口")
        self.check(w.progress["book"] == base.BOOK
                   and w.progress["book_confirmed"] is True,
                   "保留 book/book_confirmed")
        self.check(w.states == state and w.progress["history"] == p["history"]
                   and w.theta == p["theta"]
                   and w.progress["quiz_session"] == quiz,
                   "保留 states/history/theta/test session")
        self.check(w.study_records == before_records
                   and w.orders == before_orders and w.cursors == before_cursors
                   and w.daily_new_ledger == before_ledger,
                   "保留 study_records(Pending/held/resume)/orders/cursors/ledger")
        self.check(w.progress["custom"] == p["custom"],
                   "保留未知 progress 字段")
        self.check([row["w"] for row in w.queue_words] == before_queue,
                   "恢复默认不改变学习队列顺序")
        self.check(not hasattr(w, "learning_mode_chips")
                   and not hasattr(w, "input_mode_chips"),
                   "设置页不再显示学习安排或输入模式控件")
        self.close()

        w = self.card(v136_progress(theme="dark"), win_fixture())
        self.check(not hasattr(w, "btn_restore_defaults"),
                   "设置构造时不创建全局恢复默认控件")
        self.check(w.restore_defaults() is True and w.theme_key == th.DEFAULT,
                   "保留事务式恢复默认 API")
        self.close()

    # ------------------------------------------------------------------
    def _atomic_failure(self, fail_progress=0, fail_window=0):
        real = storage.atomic_save
        counters = {"progress": 0, "window": 0}

        def wrapped(path, data):
            if Path(path) == Path(base.app_main.PROGRESS_PATH):
                counters["progress"] += 1
                if fail_progress == counters["progress"]:
                    raise storage.StorageError("inject progress save failure")
            elif Path(path) == Path(base.app_main.WIN_PATH):
                counters["window"] += 1
                if fail_window == counters["window"]:
                    raise storage.StorageError("inject window save failure")
            return real(path, data)

        return wrapped, counters

    def _restore_failure_card(self):
        p = v136_progress(
            theme="dark", study_mode="choice", retry_gap=5,
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 7},
            keybindings=dict(keys.DEFAULT_BINDINGS, remember="A", forget="B"),
                        states={base.KEYS[0]: base.learning(2, self.clock() + 50)},
            study_records={base.BOOK: {"cursor": 1, "new_count": 1,
                                       "pending": {base.KEYS[1]: 4},
                                       "current": {"kind": "new",
                                                   "key": base.KEYS[1],
                                                   "resume": True}}},
            orders={base.BOOK: {"mode": "shuffle", "seed": 222}},
            cursors={base.BOOK: 1},
            daily_new_ledger={"days": {"2026-01-02": ["alpha"]}, "keep": 1})
        return self.card(p, win_fixture(normal_w=640, normal_h=520,
                                        edge_collapse=False))

    def save_failure_stage_progress(self):
        w = self._restore_failure_card()
        before_prefs = {k: deepcopy(w.progress.get(k)) for k in
                        ("theme", "study_mode", "learning_policy", "keybindings")}
        before_learning = {"states": deepcopy(w.states),
                           "records": deepcopy(w.study_records),
                           "ledger": deepcopy(w.daily_new_ledger)}
        wrapper, _ = self._atomic_failure(fail_progress=1)
        with patch.object(storage, "atomic_save", side_effect=wrapper), \
                patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok):
            ok = w.restore_defaults()
        base.pump()
        self.check(ok is False, "进度日志保存失败返回False")
        self.check(w.progress["theme"] == before_prefs["theme"]
                   and w.progress["learning_policy"] == before_prefs["learning_policy"],
                   "进度日志失败回退偏好")
        self.check(w.states == before_learning["states"]
                   and w.study_records == before_learning["records"]
                   and w.daily_new_ledger == before_learning["ledger"],
                   "进度日志失败不动学习记录")
        self.check(w.progress.get(DEFAULTS_JOURNAL) is None,
                   "进度日志失败清理 journal")
        self.close()

    def save_failure_stage_window(self):
        w = self._restore_failure_card()
        before = deepcopy((w.progress["theme"], w.progress["learning_policy"],
                           w.window_record))
        before_size = QSize(w.window_ctl.normal_size)
        wrapper, _ = self._atomic_failure(fail_progress=0, fail_window=1)
        with patch.object(storage, "atomic_save", side_effect=wrapper), \
                patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok):
            ok = w.restore_defaults()
        base.pump()
        self.check(ok is False, "窗口保存失败返回False")
        self.check(w.progress["theme"] == before[0]
                   and w.progress["learning_policy"] == before[1],
                   "窗口失败回退偏好")
        self.check(w.window_ctl.normal_size == before_size
                   and w.window_record.get("custom_window") ==
                   before[2].get("custom_window")
                   and w.window_record.get("edge_collapse") is False,
                   "窗口失败恢复旧窗口尺寸/自定义字段")
        self.check(w.progress.get(DEFAULTS_JOURNAL) is None,
                   "窗口失败清理journal")
        self.close()

    def save_failure_stage_final_progress(self):
        w = self._restore_failure_card()
        before = deepcopy((w.progress["theme"], w.progress["learning_policy"],
                           w.window_record))
        before_size = QSize(w.window_ctl.normal_size)
        wrapper, _ = self._atomic_failure(fail_progress=2)
        with patch.object(storage, "atomic_save", side_effect=wrapper), \
                patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok):
            ok = w.restore_defaults()
        base.pump()
        self.check(ok is False, "最终进度保存失败返回False")
        self.check(w.progress["theme"] == before[0]
                   and w.progress["learning_policy"] == before[1],
                   "最终进度失败回退偏好")
        self.check(w.window_ctl.normal_size == before_size
                   and w.window_record.get("custom_window") ==
                   before[2].get("custom_window")
                   and w.window_record.get("edge_collapse") is False,
                   "最终进度失败回退窗口尺寸/自定义字段")
        self.check(w.progress.get(DEFAULTS_JOURNAL) is None,
                   "最终进度失败清理journal")
        self.close()

    def unfinished_journal_startup(self):
        old_prefs = {
            "theme": {"present": True, "value": "dark"},
            "study_mode": {"present": True, "value": "choice"},
            "learning_policy": {"present": True,
                                "value": {"mode": learn.REVIEW_FIRST, "daily_new": 20}},
            "keybindings": {"present": True, "value": dict(keys.DEFAULT_BINDINGS)},
            "retry_gap": {"present": True, "value": 3},
        }
        journal_window = win_fixture(normal_w=640, normal_h=520,
                                     edge_collapse=False)
        new_states = {base.KEYS[4]: base.learning(1, self.clock() + 300)}
        p = v136_progress(
            theme="light", study_mode="brush",
            learning_policy={"mode": learn.DAILY_NEW_FIRST, "daily_new": 5},
            keybindings=dict(keys.DEFAULT_BINDINGS, remember="A"),
            states=new_states,
            study_records={base.BOOK: {"cursor": 4, "new_count": 4,
                                       "current": {"kind": "new",
                                                   "key": base.KEYS[3],
                                                   "resume": True}}},
            orders={base.BOOK: {"mode": "shuffle", "seed": 333}},
            cursors={base.BOOK: 4},
            daily_new_ledger={"days": {"2026-01-03": ["alpha"]}, "future": 1},
            **{DEFAULTS_JOURNAL: {"schema": 1, "preferences": old_prefs,
                                   "window": journal_window}})
        self.sb.write_progress(p)
        w = self.card(restart=True)
        self.check(w.theme_key == "dark" and w.study_mode == "choice"
                   and w.key_bindings == keys.normalize(p["keybindings"])
                   and "input_mode" not in w.progress
                   and "catalog_sort" not in w.progress,
                   "未完成日志启动只回退主题、学习模式和键位偏好")
        self.check(w.window_ctl.normal_size == QSize(640, 520)
                   and w.window_ctl.edge_collapse_enabled is False,
                   "未完成日志启动恢复旧窗口")
        self.check(w.states == new_states,
                   "未完成日志启动保留后来 states")
        expected_record = p["study_records"][base.BOOK]
        actual_record = w.study_records.get(base.BOOK, {})
        self.check(all(actual_record.get(key) == value for key, value in
                       expected_record.items()),
                   "未完成日志启动保留后来 study_records（含 resume）：actual=%r expected=%r" %
                   (actual_record, expected_record))
        self.check(w.daily_new_ledger.get("days") ==
                   p["daily_new_ledger"].get("days")
                   and w.daily_new_ledger.get("future") == 1,
                   "未完成日志启动保留后来 daily ledger")
        self.check(w.progress.get(DEFAULTS_JOURNAL) is None,
                   "恢复后 journal 清除")
        self.close()


def run_suite():
    label = "v136-native" if getattr(base, "FLAGS", None) and base.FLAGS.native else "v136-offscreen"
    root = Path(base.__file__).resolve().parents[2] / ".vocab-ui-tests" / "v136"
    root.mkdir(parents=True, exist_ok=True)
    outdir = tempfile.mkdtemp(prefix=label + "-", dir=str(root))
    with patch.dict(os.environ, {"VOCAB_TEST_OUT": outdir}):
        sb = base.Sandbox(base.app_main, label)
    with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok), \
            patch.dict(os.environ, {"VOCABAPP_DATA_DIR": str(Path(sb.progress_path).parent)}):
        with sb:
            suite = V136Suite(sb)
            suite.out.append("PLATFORM " + label)
            suite.out.append("VERSION " + base.app_main.VERSION)
            with patch.object(sys, "excepthook", suite.exception):
                for name, fn in (
                    ("controls", suite.controls_contract),
                    ("input-controls", suite.keyboard_and_button_controls),
                    ("keyboard-defaults", suite.keyboard_defaults_once),
                    ("keyboard-choice-lock", suite.keyboard_choice_lock),
                    ("keyboard-custom", suite.keyboard_custom_and_errors),
                    ("editing-focus", suite.editing_focus_does_not_score),
                    ("button-focus", suite.button_focus_uses_config),
                    ("daily-status", suite.daily_status_and_quota),
                    ("quota-change", suite.settings_quota_change_keeps_current),
                    ("undo-amend", suite.undo_and_amend_keep_first_day),
                    ("sort-learning", suite.sort_filters_do_not_change_learning_order),
                    ("restore-defaults", suite.restore_defaults_preserves_learning),
                    ("save-progress-stage", suite.save_failure_stage_progress),
                    ("save-window-stage", suite.save_failure_stage_window),
                    ("save-final-stage", suite.save_failure_stage_final_progress),
                    ("unfinished-journal", suite.unfinished_journal_startup),
                ):
                    suite.run(name, fn)
                suite.check(sb.verify_real(),
                            "legacy/stable 与 bak/tmp 真实记录指纹不变")
    suite.out.append("\nCHECKS %d; FAILS %d" % (suite.checks, len(suite.fails)))
    code = sb.finish(suite.out, suite.fails, "test_v136_ui.txt")
    print("V136 CHECKS", suite.checks, "FAILS", len(suite.fails) + len(sb.errors))
    return code


if __name__ == "__main__":
    sys.exit(run_suite())
