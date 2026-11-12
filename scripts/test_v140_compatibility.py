# -*- coding: utf-8 -*-
"""Real UI compatibility: matched unknown controls and legacy answered sessions."""
import copy
import os
import re
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

configure_qt("offscreen")
set_nottest(True)
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox, QPushButton, QStyle, QStyleOptionButton
import main as app_main
import theme as th

app = new_app(sys.argv)
out, fails, exceptions = [], [], []


def check(value, message):
    line = ("OK " if value else "FAIL ") + message
    print(line, flush=True)
    out.append(line)
    if not value:
        fails.append(message)


def new_card(sb, progress=None):
    card = sb.new_card(progress={} if progress is None else progress, show=True)
    card._due_timer.stop()
    card._window_save_timer.stop()
    QTest.qWait(20)
    return card


def click(button):
    QTest.mouseClick(button, Qt.LeftButton)
    QTest.qWait(20)


def signature(button):
    button.ensurePolished()
    return (button.objectName(), button.minimumHeight(), button.maximumHeight(),
            button.sizePolicy().horizontalPolicy(), button.sizePolicy().verticalPolicy(),
            button.cursor().shape(), button.fontInfo().pixelSize(), button.sizeHint().height())


def test_styles(sb):
    card = new_card(sb)
    card.open_settings()
    click(card.btn_test)
    for width, height, name in app_main.WINDOW_PRESETS:
        card.resize(width, height)
        for key in th.THEMES:
            card.set_theme(key)
            QTest.qWait(20)
            left, right = card.btn_study_dk, card.btn_dontknow
            context = "%s/%s" % (name, key)
            check(signature(left) == signature(right), "unknown control style/sizing matches: " + context)
            ll, rl = left.parentWidget().layout(), right.parentWidget().layout()
            check(type(ll) is type(rl) and ll.contentsMargins() == rl.contentsMargins()
                  and ll.spacing() == rl.spacing(), "unknown control action frame matches: " + context)
            card.open_settings()
            card.settings_page.ensureWidgetVisible(card.btn_continue)
            QTest.qWait(20)
            button = card.btn_continue
            opt = QStyleOptionButton()
            opt.initFrom(button)
            opt.text = button.text()
            text_rect = button.style().subElementRect(QStyle.SE_PushButtonContents, opt, button)
            check(text_rect.width() >= button.fontMetrics().horizontalAdvance(button.text()),
                  "remaining-days caption is not clipped: " + context)
            click(button)
    card.close()
    QTest.qWait(20)


def test_legacy_history(sb):
    original = new_card(sb)
    original.open_settings()
    click(original.btn_test)
    correct = original.quiz_items[0]["item"]["correct_index"]
    click(original.opt_btns[correct])
    original.close()                    # Keep the real answered-current cold snapshot.
    QTest.qWait(20)
    legacy = copy.deepcopy(sb.read_progress())
    legacy["history"] = []              # A record made by the pre-fix implementation.
    session = legacy["quiz_session"]
    for key in ("history_id", "history_response_count", "history_deleted"):
        session.pop(key, None)
    session["started_at"] -= 31 * 86400
    session["updated_at"] = session["started_at"] + 60
    session["future"] = {"nested": [1, 2, 3]}
    card = new_card(sb, legacy)
    sid = session["id"]
    check(card.progress.get("quiz_session", {}).get("id") == sid,
          "startup keeps expired legacy answers for history rather than silently deleting them")
    card.open_settings()
    check(not card.btn_continue.isVisible(), "expired legacy test cannot be continued")
    history_ref = card.progress["history"]
    session_ref = card.progress["quiz_session"]
    future_ref = session_ref["future"]["nested"]
    durable = sb.read_progress()
    theta, known = card.theta, set(card.known)
    with patch.object(card, "save", side_effect=app_main.storage.StorageError("injected migration failure")), \
            patch.object(QMessageBox, "critical") as errors:
        click(card.btn_history)
    check(errors.call_count == 1 and card.mode == "settings", "failed migration reports error without navigation")
    check(card.progress["history"] is history_ref and not history_ref
          and card.progress["quiz_session"] is session_ref
          and session_ref["future"]["nested"] is future_ref
          and sb.read_progress() == durable, "failed history migration restores original references and file")
    click(card.btn_history)
    row = card.progress["history"][0]
    check(card.mode == "history" and row["id"] == sid and row["total"] == 1 and row["right"] == 1,
          "opening history migrates the previous one-answer test even after resume expiry")
    check(card.progress["history"] is history_ref and session_ref["started_at"] == session["started_at"]
          and session_ref["future"]["nested"] is future_ref,
          "history migration preserves original deadline, container and unknown metadata")
    check(card.theta == theta and set(card.known) == known and not row["prediction_eligible"],
          "legacy partial history does not adopt theta, mastery or prediction")
    check(sb.read_progress()["history"][0]["id"] == sid, "legacy measurement is durably committed")
    for number in range(4):
        click(card.btn_back)
        click(card.btn_history)
        host = card.history_rows_layout.parentWidget()
        visible = [button for button in host.findChildren(QPushButton) if button.isVisibleTo(host)]
        check(len(visible) == 2, "history reopening has no old overlapping row controls: %d" % number)
    delete = card.history_rows_layout.itemAt(0).layout().itemAt(1).widget()
    durable = sb.read_progress()
    with patch.object(card, "save", side_effect=app_main.storage.StorageError("injected deletion failure")), \
            patch.object(QMessageBox, "critical") as errors:
        click(delete)
    check(errors.call_count == 1 and card.progress["history"][0] is row
          and session_ref["history_id"] == sid and not session_ref["history_deleted"]
          and sb.read_progress() == durable, "failed deletion restores the row and session history link")
    click(delete)
    check(not card.progress["history"] and session_ref["history_deleted"]
          and session_ref["history_id"] is None, "explicit deletion leaves a resumable-session tombstone")
    # Make an independent valid-age fixture from the deleted measurement.
    deleted = copy.deepcopy(sb.read_progress())
    deleted["quiz_session"]["started_at"] = int(app_main.time.time()) - 2 * 86400
    expected_vocab = row["vocab"]
    card.close()
    QTest.qWait(20)
    resumed = new_card(sb, deleted)
    resumed.open_settings()
    click(resumed.btn_continue)
    check(resumed.mode == "quiz" and resumed.quiz_resp == [1] and not resumed.progress["history"],
          "merely resuming a deleted measurement does not resurrect its history")
    plain = re.sub(r"<[^>]*>", "", resumed.status.text())
    check("词目量%d" % expected_vocab in plain, "history deletion does not zero the live quiz measurement")
    correct = resumed.quiz_items[resumed.quiz_i]["item"]["correct_index"]
    click(resumed.opt_btns[correct])
    check(len(resumed.progress["history"]) == 1 and resumed.progress["history"][0]["id"] == sid
          and resumed.progress["history"][0]["total"] == 2,
          "a newly committed answer creates exactly one updated measurement after explicit deletion")
    click(resumed.btn_skip)
    check(resumed.mode == "settings", "resumed legacy test exits back to its settings entry")


def main():
    old_hook = sys.excepthook
    sys.excepthook = lambda *args: exceptions.append(str(args[1]))
    try:
        with Sandbox(app_main, "v140-compatibility") as sb:
            for name, test in (("styles", test_styles), ("legacy", test_legacy_history)):
                try:
                    test(sb)
                except Exception as error:
                    check(False, "%s raised %r" % (name, error))
                finally:
                    for card in sb.cards:
                        sb._stop_card(card)
                        card.close()
                    QTest.qWait(20)
            check(not exceptions, "Qt callbacks have no unhandled exceptions: %s" % exceptions)
            check(sb.verify_real(), "user's original records remain unchanged")
    finally:
        sys.excepthook = old_hook
    return sb.finish(out, fails, "test_v140_compatibility.txt")


if __name__ == "__main__":
    sys.exit(main())
