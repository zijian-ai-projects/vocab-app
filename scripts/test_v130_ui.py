# -*- coding: utf-8 -*-
"""V1.3.0 综合 UI 回归与隔离示意图。

运行：D:\\software\\anaconda\\python.exe -B scripts/test_v130_ui.py
原生：同一命令加 --native。仅构造 Sandbox.new_card，不调用 main.main；
5-8 个假词、模拟时钟、真实词组只读，所有报告/截图/故障文件均在工作区
.vocab-ui-tests。Sandbox 同时指纹保护 legacy/stable 主记录与恢复文件。
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
import argparse
import json
import os
import sys
import traceback
from unittest.mock import patch

sys.dont_write_bytecode = True
ARGS = argparse.ArgumentParser(description=__doc__)
ARGS.add_argument("--native", action="store_true", help="使用原生 Qt 窗口和字体")
FLAGS = ARGS.parse_args()
# 不接受把测试输出写到 .vocab-ui-tests 以外的继承环境变量。
os.environ.pop("VOCAB_TEST_OUT", None)
from ui_test_support import configure_qt, Sandbox, set_nottest, new_app
if not FLAGS.native:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    configure_qt("offscreen")
    # Anaconda 的 offscreen 插件默认 fonts 目录为空；仅读系统已有字体。
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if font_dir.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(font_dir))
elif os.name == "nt":
    os.environ["QT_QPA_PLATFORM"] = "windows"
    configure_qt("windows")
set_nottest(True)

from PyQt5.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTimer
from PyQt5.QtGui import QFontMetrics, QMouseEvent
from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton, QLabel
from PyQt5.QtTest import QTest
import main as app_main
import books as real_books
import scheduler as sch
import storage
from catalog import LEVEL_LINES
from entries import CATEGORIES, meaning, memory_info, pronunciation
from windowing import WindowController, DOCK_ANIM_MS, DOCK_LENGTH, STRIP_THICKNESS

APP = new_app(sys.argv)
APP.setQuitOnLastWindowClosed(False)
BOOK = "fixture-word"
PHRASE_BOOK = "fixture-phrase"
KEYS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel")
MEANINGS = ("首字母", "广播频道", "人物名字", "三角形", "回声", "狐步舞", "高尔夫球", "酒店")
WORDS = [{"w": key, "s": "n." + text, "raw": "n. " + text, "pos": ["n."],
          "ipa": "test", "b": i / 10, "lvl": 0, "frq": i + 1}
         for i, (key, text) in enumerate(zip(KEYS, MEANINGS))]
PHRASES = [{"w": "take every available opportunity", "type": "phrase", "pos": [],
            "ipa": "", "s": "把握所有可以利用的机会；尽力利用一切条件实现自己的目标",
            "raw": "把握所有可以利用的机会；尽力利用一切条件实现自己的目标"}]


class FrozenBooks:
    """main 的冻结词书 API；不修改真实 books 模块，也不写真实数据。"""
    DEFAULT = BOOK
    LEGACY = {}

    def __init__(self):
        self.BY_ID = {}
        for bid, keys, label, kind in ((BOOK, list(KEYS), "隔离回归词书", "word"),
                                      (PHRASE_BOOK, [PHRASES[0]["w"]], "隔离词组词书", "phrase")):
            self.BY_ID[bid] = {"id": bid, "name": label, "display": label, "count": len(keys),
                               "words": keys, "type": kind, "kind": "fixture", "series": "",
                               "is_union": False, "group": "fixture-group", "main": "fixture-main",
                               "path": ["隔离主类", "隔离分组"]}
        group = {"id": "fixture-group", "name": "隔离分组", "main": "fixture-main",
                 "items": list(self.BY_ID.values()), "series": [], "count": 2,
                 "union": self.BY_ID[BOOK]}
        self.GROUPS = {group["id"]: group}
        self.MAINS = [{"id": "fixture-main", "name": "隔离主类", "groups": [group]}]

    def mains(self):
        return self.MAINS

    def items(self, gid):
        return self.GROUPS.get(gid, {}).get("items", [])

    def get(self, bid):
        return self.BY_ID.get(bid, self.BY_ID[BOOK])

    def words(self, bid):
        return self.get(bid)["words"]


class Clock:
    def __init__(self):
        self.value = 2000000000.0

    def __call__(self):
        return self.value


class FakeScreen:
    def __init__(self, rect):
        self.rect = QRect(rect)

    def availableGeometry(self):
        return QRect(self.rect)


class AbortCase(Exception):
    pass


def progress(**overrides):
    result = {"memory_schema": 2, "book": BOOK, "book_confirmed": True, "welcome_done": True,
              "quiz_declined": True, "theme": "light", "states": {}, "cursors": {BOOK: 0},
              "orders": {BOOK: {"mode": "seq", "seed": 42}}, "study_records": {},
              "history": [{"ts": 1999999900, "vocab": 100, "baseline": True, "theta": 0}],
              "theta": None, "custom": {"preserve": True}}
    result.update(deepcopy(overrides))
    return result


def learning(level, due):
    return {"lv": level, "st": "learning", "due": due, "seen": level, "lapse": 0, "streak": 0}


def mastered():
    return {"lv": 10, "st": "mastered", "due": None, "seen": 10, "lapse": 0, "streak": 0}


def all_mastered(**changes):
    states = {key: mastered() for key in KEYS}
    states.update(changes)
    return states


def pump(n=8):
    for _ in range(n):
        APP.processEvents()


def key_of(w):
    return w.queue[w.qi]["w"]["w"] if w.queue and 0 <= w.qi < len(w.queue) else None


def mouse(w, kind, point, button=Qt.LeftButton, buttons=Qt.LeftButton):
    local = w.mapFromGlobal(point)
    APP.sendEvent(w, QMouseEvent(kind, QPointF(local), QPointF(point), button, buttons, Qt.NoModifier))


class Suite:
    def __init__(self, sandbox):
        self.sb = sandbox
        self.clock = Clock()
        self.books = FrozenBooks()
        self.out, self.fails, self.screens = [], [], []
        self.checks = 0
        self.current = "startup"
        self.widget = None
        self.data_dir = Path(self.sb.path("fixture-data"))
        self.write_json(self.data_dir / "bank.json", WORDS)
        self.write_json(self.data_dir / "phrases.json", PHRASES)

    def write_json(self, path, data):
        path = Path(path).resolve()
        if Path(self.sb.dir).resolve() not in path.parents:
            raise AssertionError("test fixture write escaped Sandbox: " + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def check(self, condition, text, require=False):
        self.checks += 1
        label = self.current + " | " + text
        self.out.append(("OK   " if condition else "FAIL ") + label)
        if not condition:
            self.fails.append(label)
            if require:
                raise AbortCase(label)
        return condition

    def exception(self, exc_type, error, tb):
        label = self.current + " | Qt slot " + exc_type.__name__ + ": " + str(error)
        self.fails.append(label)
        self.out.append("ERROR " + label)
        self.out.extend(traceback.format_exception(exc_type, error, tb))

    def close(self, w=None, delete=True):
        w = w or self.widget
        if w is None:
            return
        try:
            for timer in w.findChildren(QTimer):
                timer.stop()
            w.close()
            if delete:
                w.deleteLater()
        except RuntimeError:
            pass
        if w is self.widget:
            self.widget = None
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        pump(2)

    @contextmanager
    def fixture_scope(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(app_main, "DATA", str(self.data_dir)))
            stack.enter_context(patch.object(app_main, "bk", self.books))
            stack.enter_context(patch.object(app_main.time, "time", self.clock))
            yield

    def card(self, data=None, win=None, restart=False):
        self.close()
        if not restart:
            self.sb.reset(progress=data if data is not None else progress(), win=win)
        w = self.sb.new_card(show=True)
        self.widget = w
        pump()
        return w

    def aliases(self, w):
        self.check(w.states is w.progress["states"] is w.study_engine.states,
                   "states/progress/engine 保持同一共享 dict")
        self.check(w.study_record is w.study_records[w.book_id]
                   is w.progress["study_records"][w.book_id] is w.study_engine.record,
                   "record/progress/engine 保持同一共享 dict")

    def submit(self, w, remember=True):
        w.act("remember" if remember else "forget")
        self.check(w.mode == "back", "刷词提交后仅翻面", require=True)

    def run(self, name, fn, fake=True):
        self.current = name
        self.out.append("\n=== " + name + " ===")
        try:
            if fake:
                with self.fixture_scope():
                    fn()
                    self.close()
            else:
                fn()
                self.close()
        except AbortCase:
            self.close()
        except Exception as error:
            self.fails.append(name + " | " + type(error).__name__ + ": " + str(error))
            self.out.append("ERROR " + self.fails[-1])
            self.out.extend(traceback.format_exc().splitlines())
            self.close()
        self.check(self.sb.verify_real(), "legacy/stable 与 bak/tmp 字节指纹不变")

    def retry_gap(self, stored_gap):
        gap = 3
        w = self.card(progress(retry_gap=stored_gap))
        self.check(w.retry_gap == w.study_engine.retry_gap == w.progress["retry_gap"] == 3,
                   "读入gap%d归一固定3且引擎共享一致" % stored_gap)
        self.check(self.sb.read_progress()["retry_gap"] == 3 and not hasattr(w, "retry_combo"),
                   "持久retry_gap恒3且不再提供重现间隔控件")
        self.check(w.study_mode == "brush" and w.mode == "front" and w.status.isHidden(),
                   "默认刷词，无选择题/学习状态HUD")
        self.check(key_of(w) == KEYS[0], "首词按源顺序")
        self.submit(w, False)
        self.check(w.states[KEYS[0]]["lv"] == 0 and w.states[KEYS[0]]["due"] is None,
                   "不认识仍 lv0，无时间 due")
        self.check(w.study_record["pending"][KEYS[0]] == 1 + gap, "pending 以其它首次新词计数")
        for idx in range(1, gap + 1):
            w._next()
            self.check(key_of(w) == KEYS[idx], "重现前第%d个其它新词" % idx, require=True)
            self.submit(w)
        w._next()
        self.check(key_of(w) == KEYS[0] and w.queue[w.qi]["kind"] == "retry", "恰好隔%d个其它新词重现" % gap)
        self.check(w.study_record["new_count"] == gap + 1, "重现不额外计首次新词")
        self.aliases(w)

    def pending_gap_migration(self, stored_gap):
        states = {}
        for key in ("alpha", "charlie", "delta"):
            states[key] = sch.new_state()
            states[key]["seen"] = 1
        states["alpha"]["future_state"] = {"keep": [8, {"unknown": True}]}
        records = {
            BOOK: {"cursor": 1, "new_count": 1, "pending": {"alpha": 6, "charlie": 0, "delta": 1},
                   "current": {"kind": "new", "key": "bravo"},
                   "held_current": {"kind": "new", "key": "echo"}, "last_retry": "alpha",
                   "future_queue": {"keep": [7, {"unknown": "word"}]}},
            PHRASE_BOOK: {"cursor": 1, "new_count": 10, "pending": {PHRASES[0]["w"]: 15},
                          "current": {"kind": "retry", "key": PHRASES[0]["w"]}, "held_current": None,
                          "last_retry": PHRASES[0]["w"], "future_queue": {"keep": [9, "phrase"]}},
        }
        data = progress(states=states, cursors={BOOK: 1, PHRASE_BOOK: 1}, study_records=records,
                        future_metadata={"keep": [0, {"scope": "gap-migration"}]})
        if stored_gap is not None:
            data["retry_gap"] = stored_gap
        expected = deepcopy(records)
        if stored_gap == 5:
            expected[BOOK]["pending"] = {"alpha": 4, "charlie": 0, "delta": 0}
            expected[PHRASE_BOOK]["pending"] = {PHRASES[0]["w"]: 13}
        w = self.card(data)
        self.check(w.retry_gap == w.study_engine.retry_gap == w.progress["retry_gap"] == 3,
                   "旧gap5/3/缺省的真实Card载入都设meta3")
        self.check(w.study_records == expected,
                   "所有书绝对pending仅旧5减2下限0，计数/游标/current/held/last_retry/未知字段完整保留")
        self.check(key_of(w) == "bravo" and w.queue[w.qi]["kind"] == "new",
                   "载入迁移保留原未答current，不被更早ready抢答或跳过")
        self.check(set(w.study_record["pending"]) == {"alpha", "charlie", "delta"}
                   and w.study_record["pending"]["charlie"] <= w.study_record["new_count"]
                   and w.study_record["pending"]["delta"] <= w.study_record["new_count"],
                   "已ready目标保持ready，不延后或丢弃")
        unaffected = ("states", "history", "custom", "cursors", "orders", "future_metadata")
        self.check(all(w.progress[field] == data[field] for field in unaffected),
                   "gap载入不改共享states/history/root未知字段/书游标/词序")
        saved = self.sb.read_progress()
        self.check(saved["retry_gap"] == 3 and saved["study_records"] == expected
                   and all(saved[field] == data[field] for field in unaffected),
                   "真实首次载入原子保存meta3和所有书目标，保留其它内容")
        w = self.card(restart=True)
        self.check(w.study_records == expected and self.sb.read_progress()["study_records"] == expected,
                   "真实重启meta3幂等，不第二次减2")
        self.check(key_of(w) == "bravo" and w.study_record["new_count"] == 1 and w.states == states,
                   "重启仍同一未答current且不额外计数/答题")
        self.aliases(w)

    def fixed_gap_fair_fallback(self):
        states = all_mastered()
        for key in ("alpha", "bravo"):
            states.pop(key)
        w = self.card(progress(states=states))
        self.submit(w, False)
        w._next()
        self.check(key_of(w) == "bravo" and w.queue[w.qi]["kind"] == "new", "先保留另一首次新词")
        self.submit(w, False)
        self.check(w.study_record["new_count"] == 2 and w.study_record["pending"] == {"alpha": 4, "bravo": 5},
                   "两个首次新词各计一次，固定3绝对目标分别4/5")
        for key in ("alpha", "bravo", "alpha"):
            w._next()
            self.check(key_of(w) == key and w.queue[w.qi]["kind"] == "retry", "书末无其它首次新词公平提前重现" + key)
            self.submit(w, False)
            self.check(w.study_record["new_count"] == 2 and w.study_record["last_retry"] == key,
                       "fallback retry不增加首次new计数且记录轮转" + key)
        self.aliases(w)

    def first_recognition(self):
        w = self.card()
        self.check(w.status.isHidden(), "刷词front学习状态HUD隐藏")
        self.submit(w)
        self.check(w.mode == "back" and w.status.isHidden(), "刷词back答题反馈不显示左上状态HUD")
        state = w.states[KEYS[0]]
        self.check(state["lv"] == 1 and state["st"] == "learning", "首认直接 lv1")
        self.check(state["due"] == self.clock() + 300 and state["seen"] == 1, "精确 5min due，seen1")
        self.check(self.sb.read_progress()["states"][KEYS[0]] == state, "提交原子持久化")
        w.act("remember")
        self.check(w.states[KEYS[0]]["seen"] == 1, "翻面期间重复刷词提交被忽略")
        self.aliases(w)

    def level_transition(self, level, remember):
        old = learning(level, self.clock() - 1)
        w = self.card(progress(states=all_mastered(alpha=old)))
        self.check(key_of(w) == "alpha" and w.queue[w.qi]["kind"] == "review", "过期旧词先出现")
        self.submit(w, remember)
        state = w.states["alpha"]
        expected = min(10, level + 1) if remember else level
        self.check(state["lv"] == expected, "记得升级/忘记留级 lv%d" % expected)
        self.check(state["due"] == (None if expected == 10 else self.clock() + sch.LEVELS[expected - 1]),
                   "按新/当前等级精确重算 due")
        self.check(state["seen"] == old["seen"] + 1 and state["lapse"] == int(not remember), "只计一次回答")
        self.check(w.study_record["new_count"] == 0, "复习不占其它新词计数")
        if expected == 10:
            w._next()
            self.check(w.mode == "empty" and w.study_engine.next_due_time(self.clock()) is None, "lv10 退休不再出现")
            self.clock.value += 100000000
            w._due_timer.timeout.emit()
            self.check(w.mode == "empty", "未来时钟也不唤醒 lv10")
            w.undo()
            self.check(key_of(w) == "alpha" and w.states["alpha"]["lv"] == 9, "退休前回答可撤销")
        self.aliases(w)

    def due_source_order(self, mode):
        states = all_mastered(alpha=learning(1, self.clock() - 1),
                              charlie=learning(2, self.clock() - 9000))
        orders = {BOOK: {"mode": mode, "seed": 42}}
        w = self.card(progress(states=states, orders=orders))
        source = [item["w"] for item in w.queue_words]
        expected = [key for key in source if key in ("alpha", "charlie")]
        if mode == "seq":
            self.check(expected == ["alpha", "charlie"], "顺序模式源词序为 alpha/charlie")
        self.check(key_of(w) == expected[0], "到期优先，使用%s源词序而非最早due" % mode)
        self.submit(w, False)
        w._next()
        self.check(key_of(w) == expected[1], "第二过期词按%s源顺序" % mode)

    def realtime_due(self):
        w = self.card(progress(states=all_mastered(alpha=learning(1, self.clock() + 2))))
        self.check(w.mode == "empty" and w._due_timer.isActive() and w.status.isHidden(),
                   "未来到期空卡有活动定时器，无学习状态HUD")
        self.check(w.word.text() == w._book_name(w.book_id), "空卡标题复用当前词书名")
        self.clock.value += 2
        w._due_timer.timeout.emit()
        self.check(w.mode == "front" and key_of(w) == "alpha", "模拟一次真实 timer tick 即显示到期词")
        self.check(w.queue[w.qi]["kind"] == "review", "实时出现的是复习而非新词")

    def current_persistence(self):
        w = self.card()
        self.submit(w, False)
        w._next()
        expected = deepcopy(w.study_record)
        self.check(expected["current"]["key"] == "bravo" and "alpha" in expected["pending"],
                   "持久记录同时含未答 current 与 pending")
        saved_states = deepcopy(w.states)
        w = self.card(restart=True)
        self.check(key_of(w) == "bravo" and w.study_record == expected, "关闭/重启不跳未答词也不丢 pending")
        self.check(w.states == saved_states, "重启不额外提交/重排 due")
        self.aliases(w)

    def correction_and_undo(self):
        w = self.card(progress(cursors={BOOK: 0, PHRASE_BOOK: 7}))
        self.submit(w)
        with patch.object(storage, "atomic_save", wraps=storage.atomic_save) as writes:
            w.correct()
        self.check(sum(call.args[0] == self.sb.progress_path for call in writes.call_args_list) == 1,
                   "纠正+推进只提交一次原子进度写")
        self.check(w.cursors is w.progress["cursors"] and w.cursors[PHRASE_BOOK] == 7,
                   "纠正保持其它词书游标与共享cursors别名")
        self.check(w.states["alpha"]["lv"] == 0 and w.states["alpha"]["seen"] == 1
                   and w.states["alpha"]["lapse"] == 1, "纠正先回滚统计再一次不认识")
        self.check("alpha" in w.study_record["pending"] and key_of(w) == "bravo", "纠正后排重现并前进")
        self.aliases(w)
        w.undo()
        self.check(key_of(w) == "alpha" and not w.states.get("alpha"), "撤销恢复首词未答，无双统计")
        self.check(w.study_record["new_count"] == 0 and w.study_record["current"]["key"] == "alpha", "撤销恢复共享 current/计数")
        self.aliases(w)

    def choices_and_keyboard(self):
        w = self.card(progress(study_mode="choice"))
        q = w.choice_question
        self.check(w.mode == "choice" and not w.compact and len(w.study_btns) == 4, "choice 正常窗四释义按钮")
        self.check(w.status.isHidden() and w.choice_hint.isHidden() and w.choice_hint.text() == "",
                   "选择题初始无左上状态HUD/1-4选义hint")
        self.check(all(isinstance(button, app_main.WrappedOptionButton) and button.content.wordWrap()
                       and button.content.text() == button.text() and button.height() >= QFontMetrics(button.content.font()).lineSpacing()
                       for button in w.study_btns), "选择题四按钮统一WrappedOptionButton/透明QLabel真实换行文字")
        self.check(len(set(q["options"])) == 4 and q["options"][q["correct"]] == meaning(w.queue[w.qi]["w"]),
                   "四真实释义且恰好一个已知答案")
        self.check("没有正确答案" not in q["options"] and "不认识" not in q["options"]
                   and w.btn_study_dk.isVisibleTo(w), "第五项独立不认识，无测试陷阱")
        self.check(all(any(meaning(row) == text for row in w.bank) for text in q["options"]), "四选项全部源自词库")
        self.check(w.choice_word.font().pixelSize() == app_main.F_WORD[0]
                   and w.choice_ipa.font().pixelSize() == app_main.F_IPA[0],
                   "选择题单词/音标字号与刷词模式一致（%d/%d）" %
                   (w.choice_word.font().pixelSize(), w.choice_ipa.font().pixelSize()))
        self.check(w.choice_body.layout().contentsMargins().top() >= 10,
                   "选择题词块整体下移（上留白 %d）" % w.choice_body.layout().contentsMargins().top())
        QTest.keyClick(w, Qt.Key_Space)
        self.check(w.mode == "choice" and not w.states.get("alpha"), "选择题 Space 不冒充答案")
        QTest.keyClick(w, Qt.Key_1 + q["correct"])
        self.check(w.mode == "choice_back" and w.choice_locked and w.states["alpha"]["lv"] == 1, "1-4键提交正确项")
        self.check(w.status.isHidden() and w.choice_hint.isHidden() and w.choice_hint.text() == "",
                   "答对后不显示“答对 · 记忆等级x”提示，学习HUD仍隐藏")
        self.check(not any(button.isEnabled() for button in w.study_btns), "一次提交后锁四按钮")
        before = deepcopy(w.states)
        w._study_answer(q["correct"])
        QTest.keyClick(w, Qt.Key_1)
        self.check(w.states == before, "重复键盘/直接提交不双答")
        QTest.keyClick(w, Qt.Key_Z, Qt.ControlModifier)
        self.check(w.mode == "choice" and not w.states.get("alpha") and not w.choice_locked, "Ctrl+Z 恢复同一未答选择题")
        self.check(w.choice_hint.isHidden() and w.choice_hint.text() == "", "撤销回未答时反馈重新清空隐藏")
        QTest.keyClick(w, Qt.Key_5)
        self.check(w.mode == "choice_back" and w.states["alpha"]["lv"] == 0, "5键不认识仍新词")
        self.check(w.choice_hint.isHidden() and w.choice_hint.text() == "", "不认识后不显示等级/隔3新词提示")
        QTest.keyClick(w, Qt.Key_Right)
        self.check(key_of(w) == "bravo" and w.mode == "choice", "Right 下一题")
        self.check(w.choice_hint.isHidden() and w.status.isHidden(), "下一题无遗留反馈或状态HUD")
        QTest.mouseClick(w.btn_study_dk, Qt.LeftButton)
        self.check(w.states["bravo"]["lv"] == 0 and w.choice_locked, "真实第五按钮提交不认识")
        QTest.keyClick(w, Qt.Key_Return)
        QTest.keyClick(w, Qt.Key_0)
        self.check(key_of(w) == "charlie" and w.states["charlie"]["lv"] == 0, "Return 下一题/0键不认识")
        self.aliases(w)

    def mode_switch(self, answered):
        w = self.card()
        if answered:
            self.submit(w)
        before = deepcopy(w.states)
        w.open_settings()
        w.study_mode_chips["choice"].click()
        w.close_settings()
        self.check(w.mode == "choice" and key_of(w) == ("bravo" if answered else "alpha"),
                   "已答切模式前进/未答保留 current")
        self.check(w.states == before, "切模式不双提交")
        w._study_answer(w.choice_question["correct"])
        current = key_of(w)
        self.check(w.states[current]["seen"] == 1, "新模式当前词只计一次")
        w.open_settings()
        w.study_mode_chips["brush"].click()
        w.close_settings()
        self.check(w.mode == "front" and key_of(w) != current, "choice_back 切刷词不重答已提交卡")
        self.check(w.states[current]["seen"] == 1, "反向模式切换也无双答")

    def simplified_books(self):
        old_orders = {BOOK: {"mode": "shuffle", "seed": 42, "future": {"keep": True}}}
        w = self.card(progress(orders=old_orders))
        original = deepcopy(w.orders)
        raw = Path(self.sb.progress_path).read_bytes()
        self.check(app_main.stored_order(w.orders, BOOK) == "shuffle" and w.orders == original,
                   "旧shuffle记录仍显示乱序且不破坏原词序/未知字段")
        w.open_settings()
        w.open_books("settings")
        w._nav_into_main("fixture-main")
        w._nav_into_group("fixture-group")
        w._pick_book(BOOK)
        pump()
        self.check(w.sel_order == "shuffle" and w.status.isHidden() and not hasattr(w, "chip_reverse"),
                   "选书页旧乱序显示乱序，无状态HUD/逆序chip")
        self.check(w.chip_seq.text() == "顺序" and w.chip_shuffle.text() == "乱序"
                   and w.btn_catalog_books.text() == "浏览词条", "选书页只有顺序/乱序与浏览词条入口")
        QTest.mouseClick(w.chip_shuffle, Qt.LeftButton)
        self.check(w.sel_order == "shuffle", "真实乱序chip选择乱序")
        w._set_order("reverse")
        self.check(w.sel_order == "shuffle", "_set_order逆序被忽略，不改变当前选择")
        QTest.mouseClick(w.chip_seq, Qt.LeftButton)
        QTest.mouseClick(w.btn_catalog_books, Qt.LeftButton)
        pump()
        self.check(w.mode == "catalog" and w.catalog_src == "books" and w.catalog.model.rowCount() == 8,
                   "选书页真实浏览词条按钮打开目录")
        QTest.keyClick(w, Qt.Key_Escape)
        self.check(w.mode == "books" and w.nav_level == 3, "浏览返回原词书级导航")
        self.check(w.orders == original and Path(self.sb.progress_path).read_bytes() == raw,
                   "只选词序/浏览不保存或重排现有学习记录")

    def viewport_background(self, w, page, key, label):
        viewport = page.viewport()
        image = w.grab().toImage()
        origin = viewport.mapTo(w, QPoint(0, 0))
        points = ((2, 2), (viewport.width() - 3, 2),
                  (2, viewport.height() - 3), (viewport.width() - 3, viewport.height() - 3),
                  (2, viewport.height() // 2), (viewport.width() - 3, viewport.height() // 2))
        colors, blank_colors, covered = [], [], []
        for x, y in points:
            color = image.pixelColor(origin.x() + x, origin.y() + y).name()
            colors.append(color)
            hit = viewport.childAt(QPoint(x, y))
            while hit is not None and hit is not viewport and not isinstance(hit, QPushButton):
                hit = hit.parentWidget()
            if isinstance(hit, QPushButton):
                covered.append((x, y, hit.text(), color))
            else:
                blank_colors.append(color)
        expected = app_main.th.get(key)["bg"].lower()
        self.out.append("THEME %s %s expected=%s viewport-corners=%s button-covered=%s" %
                        (key, label, expected, colors, covered))
        self.check(w.theme_key == key and len(blank_colors) >= 3 and all(color == expected for color in blank_colors),
                   key + " " + label + "实际grab空白视口背景匹配真主题，不回退light")

    def scroll_themes(self):
        w = self.card(progress(study_mode="choice"))
        saved = deepcopy(w.states), deepcopy(w.progress["history"]), deepcopy(w.progress["custom"])
        keys = ("light", "dark", "sepia", "green")
        self.check(set(w.theme_chips) == set(keys), "四个真正主题key为light/dark/sepia/green")
        for key in keys:
            w.open_settings()
            chip = w.theme_chips[key]
            w.settings_page.ensureWidgetVisible(chip)
            pump()
            QTest.mouseClick(chip, Qt.LeftButton)
            QTest.qWait(40)
            pump()
            self.viewport_background(w, w.settings_page, key, "设置")
            if key == "sepia":
                path = self.sb.shot("v130-settings-sepia")
                self.check(w.grab().save(path), "真实sepia设置隔离截图保存")
                self.screens.append(path)
            w.close_settings()
            QTest.qWait(40)
            pump()
            self.viewport_background(w, w.choice_page, key, "选择题")
            self.check(w.status.isHidden() and w.choice_hint.isHidden(), key + "学习仍无状态HUD或初始hint")
        self.check((w.states, w.progress["history"], w.progress["custom"]) == saved,
                   "真实主题chip切换只改设置，不改学习/历史/未知字段")

    def wrapped_height(self, w, buttons, page, label):
        QTest.qWait(60)
        pump()
        self.check(all(isinstance(button, app_main.WrappedOptionButton) and isinstance(button.content, QLabel)
                       and button.content.wordWrap() and button.content.textFormat() == Qt.PlainText
                       and button.content.text() == button.text() for button in buttons),
                   label + "四选项同一WrappedOptionButton/QLabel真文字/纯文本换行", require=True)
        samples = []
        for button in buttons:
            metrics = QFontMetrics(button.content.font())
            needed = max(metrics.lineSpacing(), button.content.heightForWidth(button.content.width()))
            samples.append((button.width(), button.height(), button.content.width(), button.content.height(), needed))
            self.check(needed > metrics.lineSpacing() and button.content.height() >= needed
                       and button.height() >= needed + 10,
                       label + "长释义按实际content宽度自动增高，完整显示未截断")
        self.out.append("WRAPPED %s samples(button_w,h,content_w,h,needed)=%s" % (label, samples))
        self.check(page.verticalScrollBar().maximum() > 0 and page.findChildren(QLabel),
                   label + "长四选项总高超视口仍可垂直滚动，不依赖普通QWidget布局")
        return [button.content.fontInfo().pixelSize() for button in buttons]

    def wrapped_long_options(self):
        long_words = deepcopy(WORDS)
        for row in long_words:
            # OptionPool 比较逗号分开的义项；每个假词的唯一长义项不能共享分句。
            row["s"] = row["raw"] = "n." + (row["w"] + "长释义完整换行不可被按钮行高或滚动条裁切") * 8
        self.close()
        self.write_json(self.data_dir / "bank.json", long_words)
        try:
            w = self.card(progress(study_mode="choice"))
            choice_fonts = self.wrapped_height(w, w.study_btns, w.choice_page, "选择题")
            data = self.quiz_fixture()
            for item in data["quiz_session"]["items"]:
                indices = [item["idx"]] + [i for i in range(len(long_words)) if i != item["idx"]][:3]
                item["opts"] = [meaning(long_words[i]) for i in indices]
            w = self.card(data)
            self.check(w.mode == "quiz" and w.status.isVisibleTo(w) and "词汇量测试" in w.status.text()
                       and "严谨度" in w.status.text(), "status仅词汇量测试显示题号/严谨度")
            quiz_fonts = self.wrapped_height(w, w.opt_btns, w.quiz_page, "词汇量测试")
            self.check(choice_fonts == quiz_fonts and len(set(quiz_fonts)) == 1,
                       "学习选择题和词汇量测试所有长项字号一致")
            path = self.sb.shot("v130-quiz-wrapped")
            self.check(w.grab().save(path), "词汇量测试长项可滚动隔离截图保存")
            self.screens.append(path)
        finally:
            self.close()
            self.write_json(self.data_dir / "bank.json", WORDS)

    def catalog(self):
        states = {"alpha": mastered(), "bravo": learning(2, self.clock() + 1800),
                  "charlie": sch.new_state(), "foxtrot": {"st": "retired", "lv": 10},
                  "golf": {"st": "known", "lv": 0}}
        states["charlie"]["seen"] = 1
        w = self.card(progress(states=states))
        w.known.update(("charlie", "delta"))
        self.check(memory_info("charlie", w.states, w.known) == ("unlearned", 0, "0 · 待学习"),
                   "task22 实际new/lv0/seen1优先测试known，不把答错新词估计为认识")
        w.open_settings()
        w.open_catalog(BOOK)
        c = w.catalog
        self.check(dict(CATEGORIES)["unlearned"] == "待学习" and c.filter_chips["unlearned"].text().startswith("待学习 "),
                   "待学习分类取代未学习，统计chip用同一文案")
        texts = {row["w"]: c.model.data(c.model.index(i, 2), Qt.DisplayRole) for i, row in enumerate(c.model.rows)}
        self.check(texts["alpha"] == texts["foxtrot"] == "10 · 已掌握"
                   and texts["charlie"] == texts["echo"] == "0 · 待学习" and texts["bravo"] == "Lv 2 · 认识",
                   "真实目录0/待重现/10退休标签精确一致，1-9保留Lv认识")
        self.check(memory_info("delta", w.states, w.known) == ("known", None, "认识 · 测试估计")
                   and memory_info("golf", w.states, w.known) == ("known", None, "认识 · 旧版已会"),
                   "测试估计和旧版已会仍无真实等级，不误标0待学习")
        self.check(c.model.counts() == {"all": 8, "mastered": 2, "known": 3, "unlearned": 3}, "目录四分类统计含测试估计")
        self.check(c.model.states is w.states and c.model.rowCount() == 8, "目录用共享 states 和模型虚拟行")
        for category, count in (("mastered", 2), ("known", 3), ("unlearned", 3), ("all", 8)):
            c.filter_chips[category].click()
            self.check(c.model.rowCount() == count, category + " 分类按钮过滤")
        c.search.setText("CHARLIE")
        self.check(c.model.rowCount() == 1 and c.model.rows[0]["w"] == "charlie", "查询不区分词大小写")
        c.search.setText("酒店")
        self.check(c.model.rowCount() == 1 and c.model.rows[0]["w"] == "hotel", "中文释义可查询")
        c.search.clear()
        saved = deepcopy(w.states)
        raw = Path(self.sb.progress_path).read_bytes()
        pump()
        header = c.table.horizontalHeader()
        self.check(c.model.headerData(2, Qt.Horizontal, Qt.DisplayRole) == "记忆等级"
                   and "点击查看记忆等级说明" not in str(c.model.data(c.model.index(0, 2), Qt.ToolTipRole)),
                   "记忆等级表头无ⓘ且等级tooltip无失效点击提示")
        self.check(not hasattr(c, "note") and not hasattr(c, "btn_levels"),
                   "目录不再有底部提示note或独立等级说明chip")
        self.check(c.table.selectionMode() == c.table.NoSelection
                   and not c.table.selectionModel().hasSelection(),
                   "目录取消行选中设计（NoSelection/无选区）")
        for column in (0, 1, 2):
            index = c.model.index(0, column)
            QTest.mouseClick(c.table.viewport(), Qt.LeftButton, pos=c.table.visualRect(index).center())
            pump()
            self.check(c.level_dialog is None and not c.table.selectionModel().hasSelection(),
                       "点击表格第%d列不打开等级说明也不留下选中" % column)
        level_foreground = c.model.data(c.model.index(0, 2), Qt.ForegroundRole)
        word_foreground = c.model.data(c.model.index(0, 0), Qt.ForegroundRole)
        expected_foreground = c.theme["fg_mean"]
        self.check(level_foreground is not None and word_foreground is not None
                   and level_foreground.name() == expected_foreground
                   and word_foreground.name() == expected_foreground,
                   "记忆等级与单词列不加分类颜色（统一普通文字色）")
        pos = QPoint(header.sectionViewportPosition(2) + header.sectionSize(2) // 2, header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.LeftButton, pos=pos)
        pump()
        self.check(c.level_dialog is not None and c.level_dialog.isVisible(),
                   "点击记忆等级表头打开主题化说明", require=True)
        badge = c.level_header.badge
        icon = c.level_header.icon_rect()
        painted = 0
        header_image = c.level_header.viewport().grab().toImage()
        muted = c.theme["muted"].lower()
        for x in range(icon.x(), icon.x() + icon.width()):
            for y in range(icon.y(), icon.y() + icon.height()):
                if 0 <= x < header_image.width() and 0 <= y < header_image.height():
                    color = header_image.pixelColor(x, y)
                    if abs(color.red() - int(muted[1:3], 16)) <= 24 and \
                            abs(color.green() - int(muted[3:5], 16)) <= 24 and \
                            abs(color.blue() - int(muted[5:7], 16)) <= 24:
                        painted += 1
        self.check(badge.isVisible() and badge.geometry() == icon and painted >= 8,
                   "记忆等级表头右上角真实绘制描边感叹号圆圈（像素 %d）" % painted)
        expected_lines = ("等级 0：新词", "等级 1：5 分钟后复习", "等级 2：30 分钟", "等级 3：12 小时",
                          "等级 4：1 天", "等级 5：2 天", "等级 6：4 天", "等级 7：7 天",
                          "等级 8：15 天", "等级 9：30 天", "等级 10：已掌握，不再出现")
        dialog = c.level_dialog
        labels = dialog.findChildren(QLabel)
        self.check(tuple(LEVEL_LINES) == expected_lines and len(labels) == 23 and labels[0].text() == "记忆等级",
                   "等级常量严格11行，QLabel为标题+11组等级/间隔，无额外规则解释", require=True)
        actual_lines = tuple(labels[i].text() + "：" + labels[i + 1].text() for i in range(1, len(labels), 2))
        self.check(actual_lines == expected_lines, "说明11行原样，等级2-9不带后复习")
        self.check(dialog.windowTitle() == "记忆等级" and c.theme["bg"] in dialog.styleSheet(),
                   "独立说明窗口有主题背景和记忆等级标题")
        close = dialog.findChild(QPushButton)
        self.check(close.text() == "知道了", "说明有明确关闭按钮")
        QTest.mouseClick(close, Qt.LeftButton)
        pump()
        self.check(not dialog.isVisible(), "真实说明关闭按钮有效")
        QTest.keyClick(w, Qt.Key_Escape)
        self.check(w.mode == "settings", "目录 Esc 返回设置")
        self.check(w.states == saved and Path(self.sb.progress_path).read_bytes() == raw, "浏览/等级说明不改学习记录")
        w.open_catalog(PHRASE_BOOK, src="settings")
        long_entry = dict(PHRASES[0])
        long_entry["s"] = long_entry["raw"] = "极长词组释义需要完整换行显示，不可以被固定行高裁掉。" * 20
        c.set_book(PHRASE_BOOK, "隔离极长词组行", [long_entry], w.states, w.known)
        self.check(c.model.data(c.model.index(0, 1), Qt.DisplayRole) == long_entry["s"],
                   "长行DisplayRole缓存与set_book输入长释义完全一致")
        samples = []
        for delay in (40, 80, 120):
            QTest.qWait(delay)
            pump()
            samples.append((c.table.rowHeight(0), c.table.columnWidth(1),
                            c.table.verticalScrollBar().isVisible(), c._measure_timer.isActive(), c.measure_calls))
        self.out.append("CATALOG long-row samples(height,meaning_width,vscroll,timer_active,calls)=" + repr(samples))
        self.check(c.table.wordWrap() and c.table.textElideMode() == Qt.ElideNone, "长词组目录完整换行而非省略")
        self.check(c.table.rowHeight(0) > 48, "极长释义目录行高自动超过48")
        self.check(not c._measure_timer.isActive(), "单超高行可视测量最终收敛，不反复复位48")
        c.set_scale(3)
        self.check(c.model.scale == 1.6, "目录缩放也封顶1.6")
        c.set_scale(0.1)
        self.check(c.model.scale == 1.0, "目录缩放不低于1")
        QTest.keyClick(w, Qt.Key_Escape)
        self.check(w.mode == "settings" and w.states == saved and Path(self.sb.progress_path).read_bytes() == raw,
                   "长行浏览/缩放返回后学习记录完全不变")

    def minimized_roundtrip(self, w, label):
        keys = ("normal_w", "normal_h", "normal_x", "normal_y", "compact_x", "compact_y",
                "x", "y", "w", "h", "compact", "dock_edge")
        expected = {key: w.window_ctl.state()[key] for key in keys}
        geometry = QRect(w.geometry())
        self.check(w.windowType() == Qt.Window, label + " 使用可任务栏恢复的Window类型")
        w.showMinimized()
        QTest.qWait(30)
        pump()
        self.check(w.isMinimized(), label + " 原生最小化状态成立")
        w._save_window()
        saved = self.sb.read_win()
        self.check({key: saved[key] for key in keys} == expected, label + " 最小化保存不丢逻辑尺寸/位置/偏好")
        w.showNormal()
        QTest.qWait(30)
        pump()
        self.check(not w.isMinimized() and w.isVisible() and w.geometry() == geometry,
                   label + " showNormal恢复原窗口状态/geometry")
        w._save_window()
        saved = self.sb.read_win()
        self.check({key: saved[key] for key in keys} == expected, label + " 恢复后持久几何完整不变")

    def geometry(self):
        screen = FakeScreen(QRect(0, 0, 1800, 1100))
        with patch.object(WindowController, "_screens", lambda _: [screen]):
            w = self.card()
            c = w.window_ctl
            c.set_normal_size(50, 60)
            self.check(w.size() == QSize(520, 430), "正常窗最小520x430")
            w.move(100, 100)
            origin = w.mapToGlobal(QPoint(w.width() - 1, w.height() - 1))
            mouse(w, QEvent.MouseButtonPress, origin)
            mouse(w, QEvent.MouseMove, origin + QPoint(80, 70), Qt.NoButton)
            mouse(w, QEvent.MouseButtonRelease, origin + QPoint(80, 70), buttons=Qt.NoButton)
            self.check(w.size() == QSize(600, 500), "Card 真实 resize 事件交给控制器")
            c.set_normal_size(1200, 820)
            pump()
            self.check(w.size() == QSize(1200, 820), "正常窗可大于1.6倍最小尺寸")
            self.check(w._ui_scale() == 1.6 and c.scale_factor == 1.6, "字体控件 scale 封顶1.6")
            w.word.ensurePolished()
            self.check(w.word.fontInfo().pixelSize() <= round(app_main.F_WORD[0] * 1.6), "Card 词字体也不超过1.6倍")
            w._save_window()
            self.check(self.sb.read_win()["normal_w"] == 1200 and self.sb.read_win()["normal_h"] == 820,
                       "窗口尺寸保存逻辑1200x820")
            if FLAGS.native:
                self.minimized_roundtrip(w, "正常窗")
                w.set_compact(True)
                w.move(700, 300)
                pump()
                self.minimized_roundtrip(w, "小窗")
                w.set_compact(False)

    def compact_edges(self):
        area = QRect(0, 0, 1400, 900)
        screen = FakeScreen(area)
        with patch.object(WindowController, "_screens", lambda _: [screen]):
            w = self.card()
            for edge, x, y in (("left", 0, 150), ("right", 1044, 150), ("top", 250, 0), ("bottom", 250, 704)):
                c = w.window_ctl
                c.restore({"compact": True, "compact_x": x, "compact_y": y,
                           "dock_edge": edge, "normal_x": 100, "normal_y": 100}, allow_compact=True)
                w._set_mode("front")
                self.check(w.size() == QSize(356, 196) and c.dock_edge == edge, edge + " 小窗固定与贴边")
                c._collapse_if_docked(force=True)
                size = QSize(STRIP_THICKNESS, DOCK_LENGTH) if edge in ("left", "right") else QSize(DOCK_LENGTH, STRIP_THICKNESS)
                self.check(c.collapsed and w.size() == size, edge + " 收成10×64短胶囊")
                self.check(not w.stage.isVisibleTo(w), edge + " 收条隐藏学习内容")
                w._save_window()
                saved = self.sb.read_win()
                self.check((saved["w"], saved["h"], saved["compact"], saved["dock_edge"]) == (356, 196, True, edge),
                           edge + " 保存展开逻辑尺寸而非条尺寸")
                APP.sendEvent(w, QEvent(QEvent.Enter))
                QTest.qWait(DOCK_ANIM_MS + 30)
                self.check(not c.collapsed and w.size() == QSize(356, 196) and w.front_bar.isVisibleTo(w), edge + " hover恢复可见控件")
            c.set_compact(False, remember=True)
            self.check(not c._collapse_if_docked(force=True) and not c.collapsed, "正常窗永不收条")

    def temporary_normal_restart(self):
        screen = FakeScreen(QRect(0, 0, 1400, 900))
        with patch.object(WindowController, "_screens", lambda _: [screen]):
            win = {"w": 356, "h": 196, "x": 0, "y": 180, "dock_edge": "left", "custom_window": True}
            w = self.card(win=win)
            self.check(w.compact and w.window_ctl.preferred_compact, "legacy仅356x196恢复小窗偏好")
            w.window_ctl._collapse_if_docked(force=True)
            w.open_settings()
            self.check(not w.compact and w.window_ctl.preferred_compact and not w.window_ctl.collapsed, "设置临时normal，不改偏好")
            w._save_window()
            saved = self.sb.read_win()
            self.check(saved["compact"] and saved["w"] == w.window_ctl.normal_size.width()
                       and saved["h"] == w.window_ctl.normal_size.height()
                       and saved["compact_x"] == 0 and saved["compact_y"] == 180 and saved["dock_edge"] == "left",
                       "临时normal保存正常逻辑尺寸及原小窗位置/贴边")
            self.check(saved["custom_window"], "窗口未知字段保留")
            w = self.card(restart=True)
            self.check(w.compact and w.pos() == QPoint(0, 180) and w.window_ctl.dock_edge == "left", "在设置关闭并重启恢复原小窗位置")
            w.open_settings()
            w.close_settings()
            self.check(w.compact and w.pos() == QPoint(0, 180), "返回学习恢复小窗而不跳位置")

    def settings_defaults(self):
        states = {"alpha": learning(3, self.clock() + 43200)}
        w = self.card(progress(states=states, study_mode="choice", retry_gap=5))
        original_states, history, custom = deepcopy(w.states), deepcopy(w.progress["history"]), deepcopy(w.progress["custom"])
        w.open_settings()
        presets = {(520, 430), (640, 520), (760, 620)}
        self.check(set(w.size_chips) == presets, "设置只有三种常用窗口尺寸chip")
        self.check(not any(hasattr(w, name) for name in ("win_w", "win_h", "win_mode", "retry_combo")),
                   "设置不再暴露尺寸数字/模式/重现间隔控件")
        labels = [label.text() for label in w.settings_body.findChildren(QLabel)]
        buttons = [button.text() for button in w.settings_body.findChildren(QPushButton)]
        self.check(not any("不认识的新词重现间隔" in text for text in labels)
                   and "应用尺寸" not in buttons, "删除旧重现间隔说明和应用尺寸按钮")
        self.check(w.lab_book_num.text() == "已学 1 / 8" and "更换" in buttons and "浏览词条" not in buttons,
                   "设置词书块只显示已学计数与更换，不含浏览词条")
        self.check(w.lab_storage.text() == "V" + app_main.VERSION and not w.lab_storage.toolTip(),
                   "设置底部只显示版本号，不显示记录位置或路径提示")
        hint_text = "".join(labels)
        self.check(all(text not in hint_text for text in
                       ("记录位置", "尺寸限于", "小窗贴边后移出收起", "4 个真实释义 + 不认识")),
                   "设置页已删除记录位置/尺寸限制/学习模式小字提示")
        self.check(not hasattr(w, "mode_note") or not w.mode_note.isVisibleTo(w),
                   "学习模式小字提示控件已移除")
        row_buttons = list(w.size_chips.values()) + [w.btn_defaults]
        centers = {round(button.pos().y() + button.height() / 2) for button in row_buttons}
        self.check(len(centers) == 1 and w.btn_defaults.isVisibleTo(w),
                   "三个尺寸chip与恢复默认在同一行：%r" % (sorted(centers),))
        book_centers = {round(widget.pos().y() + widget.height() / 2) for widget in
                        (w.lab_book, w.lab_book_num, w.btn_change_book)}
        self.check(len(book_centers) == 1,
                   "词书路径/已学计数/更换在同一行：%r" % (sorted(book_centers),))
        screen = FakeScreen(QRect(0, 0, 1600, 1000))
        with patch.object(WindowController, "_screens", lambda _: [screen]):
            for width, height in sorted(presets):
                chip = w.size_chips[(width, height)]
                w.settings_page.ensureWidgetVisible(chip)
                pump()
                QTest.mouseClick(chip, Qt.LeftButton)
                pump()
                self.check(w.window_ctl.normal_size == QSize(width, height) and w.size() == QSize(width, height),
                           "真实尺寸chip应用%d×%d" % (width, height))
            w._apply_window_size(900, 700)
            self.check(w.window_ctl.normal_size == QSize(900, 700), "尺寸入口仍交控制器限制可用工作区")
            w.settings_page.ensureWidgetVisible(w.btn_defaults)
            pump()
            QTest.mouseClick(w.btn_defaults, Qt.LeftButton)
            self.check(w.study_mode == "brush" and w.retry_gap == 3 and w.window_ctl.normal_size == QSize(520, 430),
                       "真实恢复默认按钮回刷词/固定3/520×430")
        self.check(w.states == original_states and w.progress["history"] == history and w.progress["custom"] == custom,
                   "尺寸/默认不清学习、历史或未知字段")
        self.check(self.sb.read_progress()["states"] == original_states and self.sb.read_progress()["history"] == history
                   and self.sb.read_progress()["retry_gap"] == 3, "保存的学习/历史不清空且retry_gap恒3")

    @contextmanager
    def fail_replace(self, target=None):
        target = Path(target or self.sb.progress_path).resolve()
        original = storage.os.replace
        def failing(source, destination):
            if Path(destination).resolve() == target:
                raise OSError("injected atomic replace failure")
            return original(source, destination)
        with patch.object(storage.os, "replace", failing):
            yield

    def save_failure(self, action):
        w = self.card(progress(study_mode="choice" if action == "choice_answer" else "brush"))
        if action in ("next", "correct", "undo"):
            self.submit(w)
        before = deepcopy(w._capture_study())
        raw = Path(self.sb.progress_path).read_bytes()
        mode = w.mode
        with self.fail_replace():
            if action == "answer":
                w.act("remember")
            elif action == "choice_answer":
                w._study_answer(w.choice_question["correct"])
            elif action == "next":
                w._next()
            elif action == "correct":
                w.correct()
            else:
                w.undo()
        self.check(w._capture_study() == before and w.mode == mode, action + "失败完整回滚当前状态/队列")
        self.check(Path(self.sb.progress_path).read_bytes() == raw, action + "原子失败主文件字节不变")
        self.check(w._can_act(), action + "失败后仍可操作")
        self.aliases(w)
        if action in ("answer", "choice_answer"):
            if action == "answer":
                w.act("remember")
            else:
                self.check(not w.choice_locked, "选择提交失败不锁按钮")
                w._study_answer(w.choice_question["correct"])
            self.check(w.states["alpha"]["seen"] == 1, "重试仅统计一次")

    def empty_next_failure(self, timer=False):
        states = all_mastered()
        states.pop("alpha")
        w = self.card(progress(states=states))
        self.submit(w)
        w._next()
        self.check(w.mode == "empty" and w.snapshot is not None, "空卡仍保留上一回答的撤销快照")
        w.save()
        before = deepcopy(w._capture_study())
        snapshot = deepcopy(w.snapshot)
        raw = Path(self.sb.progress_path).read_bytes()
        self.clock.value += 300
        with self.fail_replace():
            if timer:
                w._due_timer.timeout.emit()
            else:
                w._next()
        self.check(w.mode == "empty" and w._capture_study() == before, "空卡到期推进失败仍完整保留当前记录")
        self.check(w.snapshot == snapshot, "空卡保存失败保留撤销快照")
        self.check(Path(self.sb.progress_path).read_bytes() == raw, "空卡保存失败不截断记录")
        self.aliases(w)

    def quiz_fixture(self, i=0, resp=(), count=2):
        state = app_main.pl.new_session(seed=42)
        for n, answer in enumerate(resp, 1):
            app_main.pl.step(state, answer == 1, n)
        state["asked"] = list(range(count))
        items = []
        for idx in range(count):
            options = [idx] + [other for other in range(len(WORDS)) if other != idx][:2]
            items.append({"idx": idx, "opts": [meaning(WORDS[k]) for k in options]
                          + [app_main.pl.NO_ANSWER], "correct": 0, "lvl": 0})
        session = {"algo": "staircase-v1", "state": state, "i": i, "resp": list(resp),
                   "rigor": 50 + sum(1.5 if r == 1 else -3 if r == 0 else 0 for r in resp),
                   "items": items, "future_metadata": {"keep": [7, {"x": 9}]}}
        data = progress(theta=0.0, quiz_session=session)
        data["history"][0]["custom"] = {"keep": [0, {"scope": "fixture"}]}
        return data

    def quiz_model(self, w):
        names = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "rigor", "quiz_locked",
                 "theta", "known", "last_test", "mode")
        return dict({name: getattr(w, name, None) for name in names}, progress=w.progress)

    def quiz_refs(self, model):
        refs = {}
        def visit(value, path):
            if isinstance(value, (dict, list, set)):
                refs[path] = value
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, path + (key,))
            elif isinstance(value, (list, tuple)):
                for index, child in enumerate(value):
                    visit(child, path + (index,))
        for name, value in model.items():
            visit(value, (name,))
        return refs

    def quiz_snapshot(self, w):
        model = self.quiz_model(w)
        return {"values": deepcopy(model), "refs": self.quiz_refs(model),
                "raw": Path(self.sb.progress_path).read_bytes()}

    def quiz_restored(self, w, before, label):
        model = self.quiz_model(w)
        refs = self.quiz_refs(model)
        self.check(model == before["values"], label + " history/theta/session/答题模型全部回滚")
        self.check(refs.keys() == before["refs"].keys()
                   and all(refs[key] is original for key, original in before["refs"].items()),
                   label + " progress/session/state/items/resp/history嵌套原容器身份不变")
        self.check(Path(self.sb.progress_path).read_bytes() == before["raw"], label + " 已提交文件字节未变")

    def quiz_answer_failure(self):
        w = self.card(self.quiz_fixture())
        self.check(w.mode == "quiz" and w.theta == 0.0, "合法已存测试与theta0恢复", require=True)
        before = self.quiz_snapshot(w)
        with self.fail_replace(self.sb.progress_path):
            QTest.mouseClick(w.opt_btns[0], Qt.LeftButton)
        self.quiz_restored(w, before, "quiz answer失败")
        self.check(not w.quiz_locked and not w.quiz_resp and all(b.isEnabled() for b in w.opt_btns)
                   and w.btn_dontknow.isEnabled(), "answer失败恢复enabled且没有resp/计分")
        QTest.mouseClick(w.opt_btns[0], Qt.LeftButton)
        w.quiz_timer.stop()
        self.check(w.quiz_locked and w.quiz_resp == [1] and w.rigor == 51.5,
                   "answer失败后真实按钮重试仅提交/计分一次")

    def quiz_next_failure(self):
        w = self.card(self.quiz_fixture())
        QTest.mouseClick(w.opt_btns[0], Qt.LeftButton)
        w.quiz_timer.stop()
        before = self.quiz_snapshot(w)
        word = w.quiz_word.text()
        with self.fail_replace(self.sb.progress_path):
            w.quiz_timer.timeout.emit()
        self.quiz_restored(w, before, "quiz next失败")
        self.check(w.quiz_locked and not any(b.isEnabled() for b in w.opt_btns)
                   and not w.btn_dontknow.isEnabled() and w.quiz_word.text() == word,
                   "next失败保留已答locked界面，不能重答")
        self.check(w._quiz_retry_action == "next" and "重试" in w.btn_skip.text() and w.btn_skip.isEnabled(),
                   "next失败既有skip变明确保存重试入口")
        QTest.mouseClick(w.btn_skip, Qt.LeftButton)
        self.check(w.quiz_i == 1 and w.quiz_resp == [1] and not w.quiz_locked
                   and all(b.isEnabled() for b in w.opt_btns), "next重试按钮只推进一次至未答题")
        frozen = deepcopy(self.quiz_model(w))
        w.quiz_timer.timeout.emit()
        self.check(self.quiz_model(w) == frozen, "手动next后迟到timeout不跳未答题")

    def quiz_resume_answered(self):
        w = self.card(self.quiz_fixture(resp=(1,)))
        self.check(w.mode == "quiz" and w.quiz_i == 1 and w.quiz_resp == [1] and not w.quiz_locked,
                   "已答current的持久session恢复直接推进而不重答")
        self.check(w.rigor == 51.5 and w.progress["quiz_session"]["future_metadata"] == {"keep": [7, {"x": 9}]},
                   "已答恢复不重复step/严谨度且未知字段保留")
        w = self.card(restart=True)
        self.check(w.quiz_i == 1 and w.quiz_resp == [1] and w.rigor == 51.5,
                   "再重启未答下一题仍无重复resp/计分")

    def quiz_finish_failure(self):
        with patch.object(app_main, "QUIZ_N", 2):
            w = self.card(self.quiz_fixture(i=1, resp=(1,)))
            QTest.mouseClick(w.opt_btns[0], Qt.LeftButton)
            w.quiz_timer.stop()
            before = self.quiz_snapshot(w)
            history = deepcopy(w.progress["history"])
            with self.fail_replace(self.sb.progress_path):
                w.quiz_timer.timeout.emit()
            self.quiz_restored(w, before, "quiz finish失败")
            self.check(w.quiz_i == 1 and w.quiz_locked and w.quiz_resp == [1, 1]
                       and w._quiz_retry_action == "finish", "末题finish失败不增加i，保留locked与结果重试")
            QTest.mouseClick(w.btn_skip, Qt.LeftButton)
            self.check(w.mode == "result" and len(w.progress["history"]) == len(history) + 1
                       and w.progress["history"][:-1] == history and not w.progress.get("quiz_session"),
                       "finish真实重试成功仅添加一条history并清session")
            self.check(w.theta == 0.0 and w.progress["theta"] == 0.0 and not w.progress["history"][-1]["baseline"],
                       "已有基准的合法theta0在非baseline测试后仍保留")
            frozen = deepcopy(self.quiz_model(w))
            w.quiz_timer.timeout.emit()
            w.quiz_timer.timeout.emit()
            self.check(self.quiz_model(w) == frozen, "成功finish后迟到timeout不二次历史/结果")

    def quiz_start_failure(self, welcome=False):
        data = progress(theta=0.0)
        if welcome:
            data.update(welcome_done=False, book_confirmed=False)
        w = self.card(data)
        if not welcome:
            w.open_settings()
        expected_mode = "welcome" if welcome else "settings"
        self.check(w.mode == expected_mode, "测试入口实际页面=" + expected_mode, require=True)
        before = self.quiz_snapshot(w)
        button = w.btn_welcome_test if welcome else w.btn_test
        if not welcome:
            w.settings_page.ensureWidgetVisible(button)
            pump()
        clicked = []
        button.clicked.connect(lambda checked=False: clicked.append(checked))
        with self.fail_replace(self.sb.progress_path):
            QTest.mouseClick(button, Qt.LeftButton)
        self.check(len(clicked) == 1, "真实测试入口clicked恰好一次=" + expected_mode)
        self.quiz_restored(w, before, "quiz " + expected_mode + "入口失败")
        self.check(w.mode == expected_mode and not w.progress.get("quiz_session")
                   and w._quiz_retry_action == "start" and w.btn_skip.isEnabled(),
                   "真实入口首save失败flags/UI/history/theta/session不变且可重试")

    def quiz_skip_failure(self):
        w = self.card(self.quiz_fixture())
        before = self.quiz_snapshot(w)
        with self.fail_replace(self.sb.progress_path):
            QTest.mouseClick(w.btn_skip, Qt.LeftButton)
        self.quiz_restored(w, before, "quiz skip失败")
        self.check(w.mode == "quiz" and w._quiz_retry_action == "skip" and w.btn_skip.isEnabled(),
                   "skip失败保留原会话并显示明确重试")
        QTest.mouseClick(w.btn_skip, Qt.LeftButton)
        self.check(w.mode != "quiz" and not w.progress.get("quiz_session")
                   and w.progress["history"] == before["values"]["progress"]["history"] and w.theta == 0.0,
                   "明确skip重试成功才清session且history/theta0不变")

    def close_failure(self, window=False):
        state = app_main.pl.new_session(seed=42)
        state["asked"] = [0]
        session = {"algo": "staircase-v1", "state": state, "i": 0, "resp": [], "rigor": 100,
                   "items": [{"idx": 0, "opts": [meaning(WORDS[i]) for i in range(3)]
                              + [app_main.pl.NO_ANSWER], "correct": 0}]}
        w = self.card(progress(quiz_session=session))
        self.check(w.mode == "quiz", "恢复合法持久测试夹具", require=True)
        w._quiz_answer(0)
        w.quiz_timer.start(60000)
        active = [timer for timer in w.findChildren(QTimer) if timer.isActive()]
        target = self.sb.win_path if window else self.sb.progress_path
        if window:
            w._save_window()
        raw = Path(target).read_bytes()
        with self.fail_replace(target):
            closed = w.close()
        self.check(not closed and not w._closed and not w._closing and w.isVisible(), "关闭失败忽略close并恢复可操作窗口")
        self.check(w.mode == "quiz" and w.quiz_timer.isActive() and all(timer.isActive() for timer in active),
                   "关闭失败恢复quiz_timer与全部先前活动timer")
        self.check(Path(target).read_bytes() == raw, "关闭原子失败记录未截断")

    def migration_and_backup(self):
        due = self.clock() + 12345
        legacy = progress(states={"alpha": {"st": "new", "lv": 0, "due": due, "seen": 7,
                                             "lapse": 2, "retry_now": True, "custom": {"x": 1}},
                                  "bravo": {"st": "learning", "lv": 2, "due": due}})
        legacy.pop("memory_schema")
        w = self.card(legacy)
        self.check(w.states["alpha"]["lv"] == 1 and w.states["bravo"]["lv"] == 3, "UI加载一次迁移旧零基等级")
        self.check(w.states["alpha"]["due"] == due and w.states["alpha"]["seen"] == 7
                   and w.states["alpha"]["custom"] == {"x": 1} and "retry_now" not in w.states["alpha"], "迁移保留due/统计/未知字段")
        w = self.card(restart=True)
        self.check(w.states["alpha"]["lv"] == 1 and w.states["bravo"]["lv"] == 3, "重启现代schema不再重复升级")
        self.close()
        self.sb.reset(progress=progress(), win={})
        valid = progress(states={"alpha": learning(2, due)})
        self.write_json(self.sb.progress_path + ".bak", valid)
        Path(self.sb.progress_path).write_text("{invalid", encoding="utf-8")
        w = self.sb.new_card(show=True)
        self.widget = w
        self.check(w.states["alpha"]["lv"] == 2 and bool(w.storage_notices), "UI从有效备份恢复并展示通知来源")
        self.close()
        for invalid in ([1, 2], {"states": []}, {"history": {}}):
            self.sb.reset(progress=None, win={})
            self.write_json(self.sb.progress_path, invalid)
            raw = Path(self.sb.progress_path).read_bytes()
            rejected = False
            try:
                w = self.sb.new_card(show=False)
                self.widget = w
            except storage.StorageError:
                rejected = True
            self.check(rejected and Path(self.sb.progress_path).read_bytes() == raw, "拒绝非法结构，不当新用户清空：" + str(type(invalid).__name__))
        source = self.sb.path("legacy-copy.json")
        destination = self.sb.path("migrated-copy.json")
        self.write_json(source, valid)
        raw = Path(source).read_bytes()
        import warnings
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always", storage.StorageWarning)
            got = storage.load_json(destination, {}, legacy_path=source)
        self.check(got == valid and Path(source).read_bytes() == raw and bool(notices), "显式稳定迁移复制完整记录，旧夹具保留")

    def real_phrase_library(self):
        w = self.card(progress(book=real_books.DEFAULT, cursors={}, orders={}, history=[]))
        phrase_books = [book for book in real_books.all() if book.get("type") == "phrase" and not book.get("is_union")]
        self.check(len(w.phrases) == 4818 and len(phrase_books) == 8, "真实只读4818词组/8词组词书")
        self.check(all(book["count"] == len(book["words"]) and all(key in w.bank_map for key in book["words"])
                       for book in phrase_books), "8本词组书数量/词条映射完整")
        self.check(all(not pronunciation(row) for row in w.phrases), "词组不伪造IPA")
        book = phrase_books[0]
        w.open_books("settings")
        w._nav_into_main(book["main"])
        w._nav_into_group(book["group"])
        self.check(book["id"] in w.book_btns, "真实三级导航可选词组书")
        w._pick_book(book["id"])
        w._start_learning()
        self.check(w.book_id == book["id"] and all(row.get("type") == "phrase" for row in w.queue_words), "词组书进入共享学习流程")
        self.check(not w.ipa.text(), "真实词组卡没有音标")
        word_books = [item for item in real_books.all() if item.get("type") == "word" and item.get("words")]
        largest = max(word_books, key=lambda item: len(item["words"]))
        started = app_main.time.perf_counter()
        w.open_catalog(largest["id"], src="settings")
        QTest.qWait(40)
        pump(12)
        elapsed = app_main.time.perf_counter() - started
        self.out.append("PERF largest-catalog entries=%d seconds=%.3f book=%s visible_rows=%d measure_calls=%d" %
                        (len(largest["words"]), elapsed, largest["id"], w.catalog.measured_rows, w.catalog.measure_calls))
        self.check(w.catalog.model.rowCount() == len(largest["words"]), "最大真实词书完整目录行数不缺失")
        self.check(w.catalog.measured_rows <= 64 and w.catalog.measure_calls <= 8,
                   "最大目录只合并测量首屏及buffer，非全书")

    def screenshots(self):
        phrase_books = [book for book in real_books.all() if book.get("type") == "phrase" and not book.get("is_union")]
        source_words = real_books.words(real_books.DEFAULT)
        target = next((word for word in ("abandon", "ability", "benefit", "challenge") if word in source_words), source_words[0])
        data_choice = progress(book=real_books.DEFAULT, cursors={real_books.DEFAULT: source_words.index(target)},
                               orders={real_books.DEFAULT: {"mode": "seq", "seed": 42}}, history=[], study_mode="choice")
        w = self.card(data_choice)
        self.check(w.mode == "choice" and key_of(w) == target, "真实词库选择题按保存游标展示示意词")
        pump(12)
        path = self.sb.shot("v130-choice")
        self.check(w.grab().save(path), "选择题隔离截图保存")
        self.screens.append(path)
        entries = {row["w"]: row for row in w.phrases}
        choice = next(((book, i, entries[key]) for book in phrase_books for i, key in enumerate(book["words"])
                       if not entries[key].get("pos") and 30 <= len(meaning(entries[key])) <= 70), None)
        if choice is None:
            choice = next((book, i, entries[key]) for book in phrase_books for i, key in enumerate(book["words"])
                          if not entries[key].get("pos"))
        book, index, row = choice
        data = progress(book=book["id"], cursors={book["id"]: index},
                        orders={book["id"]: {"mode": "seq", "seed": 42}}, history=[])
        w = self.card(data)
        self.check(key_of(w) == row["w"], "真实词组按保存游标展示指定条目")
        w.set_compact(True)
        w.act("remember")
        w.fade.stop()
        w.answer_effect.setOpacity(1.0)
        pump(12)
        self.check(w.compact and w.size() == QSize(356, 196) and not w.ipa.text(), "词组小窗356x196、无IPA")
        self.check(w.meaning.text() == row["s"].strip(), "无pos源词组不编造词性")
        metrics = QFontMetrics(w.meaning.font())
        needed = metrics.boundingRect(QRect(0, 0, w.meaning.width(), 2000), Qt.TextWordWrap, w.meaning.text()).height()
        self.check(w.word.wordWrap() and w.meaning.wordWrap() and w.meaning.height() >= needed, "词组/释义自动换行高度足够")
        path = self.sb.shot("v130-phrase-compact")
        self.check(w.grab().save(path), "词组小窗隔离截图保存")
        self.screens.append(path)
        w.open_settings()
        w.open_catalog(book["id"])
        w.catalog.search.setText("")
        pump(12)
        self.check(w.catalog.model.rowCount() == book["count"], "真实目录模型数量完整")
        path = self.sb.shot("v130-catalog")
        self.check(w.grab().save(path), "词条浏览隔离截图保存")
        self.screens.append(path)


def run_suite():
    label = "v130-native" if FLAGS.native else "v130-offscreen"
    sb = Sandbox(app_main, label)
    suite = None
    late = None
    original_paths = (app_main.PROGRESS_PATH, app_main.WIN_PATH)
    with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok), \
            patch.dict(os.environ, {"VOCABAPP_DATA_DIR": str(Path(sb.progress_path).parent)}):
        with sb:
            suite = Suite(sb)
            suite.check(storage.paths() == (sb.progress_path, sb.win_path) and storage.legacy_dirs() == [],
                        "VOCABAPP_DATA_DIR与Sandbox globals双隔离，禁用真实迁移候选")
            suite.out.append("PLATFORM " + ("native" if FLAGS.native else "offscreen"))
            suite.out.append("Protected legacy/stable paths: " + str(len(sb.watch_paths)))
            with patch.object(sys, "excepthook", suite.exception):
                suite.run("gap3", lambda: suite.retry_gap(3))
                suite.run("fixed-gap3-legacy5", lambda: suite.retry_gap(5))
                for old_gap in (5, 3, None):
                    suite.run("stored-gap%s-pending" % (old_gap if old_gap is not None else "default"),
                              lambda gap=old_gap: suite.pending_gap_migration(gap))
                suite.run("fixed-gap3-fair-fallback", suite.fixed_gap_fair_fallback)
                suite.run("first-recognition", suite.first_recognition)
                for level in range(1, 10):
                    for remember in (True, False):
                        suite.run("level%d-%s" % (level, "remember" if remember else "forget"),
                                  lambda lv=level, yes=remember: suite.level_transition(lv, yes))
                for mode in ("seq", "shuffle"):
                    suite.run("due-" + mode, lambda order=mode: suite.due_source_order(order))
                suite.run("realtime-due", suite.realtime_due)
                suite.run("persistent-current-pending", suite.current_persistence)
                suite.run("correct-undo", suite.correction_and_undo)
                suite.run("choice-keyboard", suite.choices_and_keyboard)
                suite.run("wrapped-long-options", suite.wrapped_long_options)
                suite.run("scroll-four-themes", suite.scroll_themes)
                suite.run("simplified-books-order", suite.simplified_books)
                suite.run("switch-unanswered", lambda: suite.mode_switch(False))
                suite.run("switch-answered", lambda: suite.mode_switch(True))
                suite.run("catalog", suite.catalog)
                suite.run("normal-geometry", suite.geometry)
                suite.run("compact-four-edges", suite.compact_edges)
                suite.run("temporary-normal-restart", suite.temporary_normal_restart)
                suite.run("settings-defaults", suite.settings_defaults)
                for action in ("answer", "choice_answer", "next", "correct", "undo"):
                    suite.run("atomic-" + action, lambda act=action: suite.save_failure(act))
                suite.run("atomic-empty-next", suite.empty_next_failure)
                suite.run("atomic-due-timer", lambda: suite.empty_next_failure(True))
                suite.run("atomic-quiz-answer", suite.quiz_answer_failure)
                suite.run("atomic-quiz-next", suite.quiz_next_failure)
                suite.run("quiz-resume-answered", suite.quiz_resume_answered)
                suite.run("atomic-quiz-finish", suite.quiz_finish_failure)
                suite.run("atomic-quiz-settings-entry", suite.quiz_start_failure)
                suite.run("atomic-quiz-welcome-entry", lambda: suite.quiz_start_failure(True))
                suite.run("atomic-quiz-skip", suite.quiz_skip_failure)
                suite.run("atomic-close-progress", suite.close_failure)
                suite.run("atomic-close-window", lambda: suite.close_failure(True))
                suite.run("migration-backup-invalid", suite.migration_and_backup)
                suite.run("real-phrases-books", suite.real_phrase_library, fake=False)
                suite.run("illustrations", suite.screenshots, fake=False)
                with suite.fixture_scope():
                    late = suite.card()
                    suite.close(late, delete=False)
                    suite.widget = None
        suite.current = "closed-late-callbacks"
        suite.check((app_main.PROGRESS_PATH, app_main.WIN_PATH) == original_paths, "Sandbox 退出恢复globals")
        with patch.object(storage, "atomic_save", side_effect=AssertionError("closed callback attempted default-path write")) as save:
            late.save()
            late.mode = "quiz"
            late.quiz_i = 0
            late._quiz_next()
            suite.check(late.quiz_i == 0, "关闭后quiz模式的迟到回调也不递增题号")
            late.mode = "empty"
            late.waiting_due = 0
            frozen = deepcopy(late._capture_study())
            late._check_due()
            suite.check(late._capture_study() == frozen, "关闭后empty模式的迟到到期回调不推进队列")
            late._save_window()
            late._next()
            late.correct()
            late.undo()
            pump()
            suite.check(save.call_count == 0 and late._closed, "关闭后所有迟到回调均不写默认真实路径")
        suite.check(sb.verify_real(), "最终legacy/stable及恢复文件字节全部不变")
    suite.out.append("\nCHECKS %d; FAILS %d" % (suite.checks, len(suite.fails)))
    for path in suite.screens:
        suite.out.append("SCREENSHOT " + path)
        print("SCREENSHOT", path)
    code = sb.finish(suite.out, suite.fails, "test_v130_ui.txt")
    print("V130 CHECKS", suite.checks, "FAILS", len(suite.fails) + len(sb.errors))
    return code


if __name__ == "__main__":
    sys.exit(run_suite())
