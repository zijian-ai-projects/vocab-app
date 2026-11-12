# -*- coding: utf-8 -*-
"""V1.4.0 real-click quiz regression; all records stay in Sandbox.

No replacements for quiz rendering, mode transitions, answers or QTimer callbacks.
Set VOCAB_TEST_CASE to one scenario name for a focused reproduction.
"""
import copy
import os
import sys
import time
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

configure_qt("offscreen")
set_nottest(True)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox
import main as app_main
import theme as th

app = new_app(sys.argv)
out = []
fails = []


def check(condition, message):
    line = ("OK " if condition else "FAIL ") + message
    print(line, flush=True)
    out.append(line)
    if not condition:
        fails.append(message)


def history_record():
    return {"id": "saved-history", "ts": int(time.time()) - 86400,
            "vocab": 4500, "right": 15, "total": 20, "dontknow": 2,
            "lo": 3200, "hi": 6000, "rigor": 90, "err": 30,
            "theta": 0.5, "se": 0.4, "baseline": True}


def new_card(sb, progress=None):
    card = sb.new_card(progress={} if progress is None else progress, show=True)
    QTest.qWait(20)
    # The due/window timers are not the subject of these scenarios. The quiz
    # timer and all production UI/answer methods remain untouched.
    card._due_timer.stop()
    card._window_save_timer.stop()
    return card


def click(button):
    QTest.mouseClick(button, Qt.LeftButton)


def test_settings(sb):
    saved_history = [history_record()]
    card = new_card(sb, {"history": saved_history})
    check(card.mode == "books", "unconfirmed user starts at book selection")
    card.start_quiz()
    old_id = card.quiz_session_id
    card.skip_test()
    card.open_settings()
    history_ref = card.progress["history"]
    saved_history = copy.deepcopy(history_ref)
    QTest.qWait(20)
    actions = (card.btn_history, card.btn_continue, card.btn_test)
    modes = tuple(card.study_mode_chips.values())
    check([button.text() for button in actions] ==
          ["历史记录", "继续上次测试（剩余30天）", "开始新的测试"], "three requested action labels include remaining days")
    check(all(button.isVisible() for button in actions), "valid session makes all three actions visible")
    for width, height, name in app_main.WINDOW_PRESETS:
        card.resize(width, height)
        for key in th.THEMES:
            card.set_theme(key)
            QTest.qWait(20)
            for button in actions + modes:
                button.ensurePolished()
            context = "%s / %s" % (name, key)
            check(all(button.objectName() == modes[0].objectName() == "chip"
                      and button.minimumHeight() == modes[0].minimumHeight()
                      and button.maximumHeight() == modes[0].maximumHeight()
                      and button.sizePolicy().horizontalPolicy() == modes[0].sizePolicy().horizontalPolicy()
                      and button.sizePolicy().verticalPolicy() == modes[0].sizePolicy().verticalPolicy()
                      and button.fontInfo().pixelSize() == modes[0].fontInfo().pixelSize()
                      and button.cursor().shape() == modes[0].cursor().shape()
                      for button in actions), "action style and sizing match learning modes: " + context)
            check(all(button.height() == modes[0].height() for button in actions)
                  and card.btn_history.width() < card.btn_test.width(),
                  "actual heights match and action widths follow text: " + context)
    card.resize(520, 430)
    QTest.qWait(30)
    card.settings_page.ensureWidgetVisible(card.btn_test)
    QTest.qWait(20)
    check(card.btn_test.isVisible() and card.settings_page.viewport().rect().contains(
          card.btn_test.mapTo(card.settings_page.viewport(), card.btn_test.rect().center())),
          "new-test button is exposed after resizing back to the small window")
    dialogs = []
    with patch.object(QMessageBox, "question", side_effect=lambda *a, **k: dialogs.append(a) or QMessageBox.Yes):
        click(card.btn_test)
    check(not dialogs and card.mode == "quiz", "settings new-test click starts quiz without a popup")
    check(card.quiz_session_id != old_id and card.quiz_i == 0 and card.quiz_resp == []
          and not card.quiz_locked and all(button.isEnabled() for button in card.opt_btns),
          "new test replaces the old attempt with an answerable first question")
    check(card.progress["history"] is history_ref and card.progress["history"] == saved_history,
          "new test preserves exact saved history and its container")


def test_history(sb):
    card = new_card(sb, {"history": [history_record()]})
    card.open_settings()
    click(card.btn_history)
    QTest.qWait(20)
    check(card.mode == "history" and card.page_title.text() == "历史记录", "history button opens history list")
    check(card.back_slot.isVisible() and card.btn_back.isVisible() and not card.btn_gear.isVisible(),
          "history list shows top-left back rather than gear")
    click(card.btn_back)
    check(card.mode == "settings", "history top-left back returns to settings")
    click(card.btn_history)
    QTest.keyClick(card, Qt.Key_Escape)
    check(card.mode == "settings", "history Escape returns to settings")


def test_answers(sb):
    card = new_card(sb)
    card.open_settings()
    # Only suppress the old confirmation while reproducing the answer stall.
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        click(card.btn_test)
    check(card.mode == "quiz" and bool(card.quiz_word.text()), "real quiz rendering presents first word")
    heartbeat = []
    timer = QTimer(card)
    timer.setInterval(25)
    timer.timeout.connect(lambda: heartbeat.append(time.perf_counter()))
    timer.start()
    # Exercise all four options and the separate unknown button through signals.
    options = (0, 1, 2, 3, -1)
    for option in options[:int(os.environ.get("VOCAB_TEST_ANSWERS", len(options)))]:
        before_count = len(card.quiz_resp)
        old_key = card.quiz_items[card.quiz_i]["key"]
        correct = card.quiz_items[card.quiz_i]["item"]["correct_index"]
        expected = -1 if option < 0 else int(option == correct)
        started = time.perf_counter()
        click(card.btn_dontknow if option < 0 else card.opt_btns[option])
        elapsed = time.perf_counter() - started
        check(elapsed < 1.5, "answer %s returns promptly (%.3fs)" % (option, elapsed))
        check(len(card.quiz_resp) == before_count + 1 and card.quiz_resp[-1] == expected,
              "answer %s records exactly one response" % option)
        check(card.quiz_locked and card.quiz_timer.isActive()
              and not any(button.isEnabled() for button in card.opt_btns),
              "answer %s locks feedback and schedules real timer" % option)
        # A second click during feedback must not score the question again.
        click(card.opt_btns[0])
        check(len(card.quiz_resp) == before_count + 1, "feedback double-click does not score again")
        heartbeat_before = len(heartbeat)
        started = time.perf_counter()
        QTest.qWait(900)
        wait_elapsed = time.perf_counter() - started
        check(wait_elapsed < 1.5 and len(heartbeat) - heartbeat_before >= 15,
              "event loop stays responsive while advancing (%.3fs)" % wait_elapsed)
        check(card.mode == "quiz" and card.quiz_i == len(card.quiz_resp)
              and card.quiz_items[card.quiz_i]["key"] != old_key
              and not card.quiz_locked and not card.quiz_timer.isActive()
              and all(button.isEnabled() for button in card.opt_btns)
              and card.btn_dontknow.isEnabled(), "real timer advances to an unlocked new question")
        session = sb.read_progress().get("quiz_session", {})
        check(session.get("i") == card.quiz_i and session.get("resp") == card.quiz_resp,
              "advanced question and responses are persisted")
    timer.stop()
    keys = [record["key"] for record in card.quiz_items]
    check(len(keys) == len(set(keys)), "real-click questions have unique stable keys")


def test_resume(sb):
    card = new_card(sb)
    card.start_quiz()
    sid = card.quiz_session_id
    key = card.quiz_items[0]["key"]
    card.close()
    QTest.qWait(20)
    restarted = new_card(sb, sb.read_progress())
    check(restarted.mode == "books", "restart does not fake its startup mode")
    restarted.open_settings()
    click(restarted.btn_continue)
    check(restarted.quiz_session_id == sid and restarted.quiz_i == 0
          and restarted.quiz_resp == [] and restarted.quiz_items[0]["key"] == key
          and not restarted.quiz_locked and all(b.isEnabled() for b in restarted.opt_btns),
          "fresh window resumes the same unanswered first item")
    correct = restarted.quiz_items[0]["item"]["correct_index"]
    click(restarted.opt_btns[correct])
    check(restarted.quiz_resp == [1] and restarted.quiz_timer.isActive(), "answer saved before feedback close")
    rigor = restarted.rigor
    state = copy.deepcopy(restarted.quiz_state)
    restarted.close()  # Real close cancels the 650ms timer, leaving answered-current state.
    QTest.qWait(20)
    persisted = sb.read_progress()
    check(persisted["quiz_session"]["i"] == 0 and persisted["quiz_session"]["resp"] == [1],
          "feedback-close fixture really contains an answered-current snapshot")
    resumed = new_card(sb, persisted)
    resumed.open_settings()
    click(resumed.btn_continue)
    check(resumed.quiz_session_id == sid and resumed.quiz_resp == [1] and resumed.quiz_i == 1
          and resumed.quiz_items[1]["key"] != key and resumed.rigor == rigor,
          "fresh window advances answered-current snapshot without resetting or rescoring")
    check(resumed.quiz_state["up"] == state["up"] and resumed.quiz_state["down"] == state["down"]
          and resumed.quiz_state["level"] == state["level"] and not resumed.quiz_locked,
          "resume preserves score/streak and unlocks the next real question")
    click(resumed.opt_btns[0])
    QTest.qWait(900)
    check(len(resumed.quiz_resp) == 2 and resumed.quiz_i == 2 and not resumed.quiz_locked,
          "resumed quiz remains playable through its real timer")


def test_fresh_failure(sb):
    card = new_card(sb, {"history": [history_record()]})
    card.start_quiz()
    card.open_settings()
    old_id = card.quiz_session_id
    refs = (card.progress, card.progress["quiz_session"], card.quiz_state,
            card.quiz_items, card.quiz_resp, card.progress["history"])
    saved = copy.deepcopy(card.progress)
    persisted = sb.read_progress()
    with patch.object(card, "save", side_effect=app_main.storage.StorageError("injected failure")) as save, \
            patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as error:
        click(card.btn_test)
    check(save.call_count == 1 and error.call_count == 1, "new-test failure makes only one commit attempt")
    restored = (card.progress, card.progress["quiz_session"], card.quiz_state,
                card.quiz_items, card.quiz_resp, card.progress["history"])
    check(all(original is current for original, current in zip(refs, restored))
          and card.progress == saved and sb.read_progress() == persisted,
          "failed new start preserves original containers and all durable records")
    check(card.mode == "settings" and card._quiz_retry_action == "start_new"
          and card.btn_skip.isVisible() and not card.quiz_timer.isActive(),
          "failed fresh start stays on settings with an explicit fresh retry")
    with patch.object(card, "save", wraps=card.save) as save:
        click(card.btn_skip)
    check(save.call_count == 1 and card.mode == "quiz" and card.quiz_session_id != old_id
          and card.quiz_i == 0 and card.quiz_resp == [] and not card.quiz_locked,
          "retry creates and commits one fresh attempt, not a resume of the old attempt")
    check(card.progress["history"] is refs[-1] and card.progress["history"] == saved["history"],
          "fresh retry preserves exact prior history")


def main():
    sb = Sandbox(app_main, "v140-flow")
    exceptions = []
    old_hook = sys.excepthook
    sys.excepthook = lambda typ, value, tb: exceptions.append(repr(value))
    selected = os.environ.get("VOCAB_TEST_CASE")
    scenarios = (("settings", test_settings), ("history", test_history),
                 ("answers", test_answers), ("resume", test_resume),
                 ("fresh", test_fresh_failure))
    try:
        with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as errors, sb:
            for name, scenario in scenarios:
                if selected and selected != name:
                    continue
                try:
                    scenario(sb)
                except Exception as error:
                    check(False, "%s raised %r" % (name, error))
                finally:
                    for card in sb.cards:
                        sb._stop_card(card)
                        card.close()
                    QTest.qWait(20)
            check(not exceptions, "Qt signal callbacks have no unhandled exceptions: %s" % exceptions)
            check(errors.call_count == 0, "normal clicks trigger no storage/error dialogs")
            check(sb.verify_real(), "user's real records remain unchanged")
    finally:
        sys.excepthook = old_hook
    return sb.finish(out, fails, "test_v140_quiz_flow.txt")


if __name__ == "__main__":
    sys.exit(main())
