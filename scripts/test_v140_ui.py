# -*- coding: utf-8 -*-
"""V1.4 quiz/history regression checks in the isolated UI sandbox.

Production rendering, mode transitions and the 650ms quiz timer remain real.
Only storage failures/dialogs are intercepted; real record fingerprints are verified.
Run with python -B scripts/test_v140_ui.py (offscreen).
"""
import copy
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

configure_qt("offscreen")
set_nottest(True)
import main as app_main
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox
from unittest.mock import patch

app = new_app(sys.argv)
out = []
fails = []


def check(condition, label):
    line = ("OK " if condition else "FAIL ") + label
    out.append(line)
    print(line, flush=True)
    if not condition:
        fails.append(label)


FIELDS = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "rigor", "quiz_locked",
          "theta", "known", "last_test", "mode", "quiz_started_at", "quiz_last_answer_at",
          "quiz_session_id", "quiz_origin_welcome", "quiz_bank_fingerprint", "quiz_vocab_grid",
          "quiz_item_indices", "quiz_result", "quiz_return_to_settings", "quiz_status_values")


def snapshot(w):
    return copy.deepcopy({"progress": w.progress,
                          "attrs": {name: getattr(w, name) for name in FIELDS if hasattr(w, name)}})


def references(w):
    refs = {}

    def collect(value, path, ancestors=()):
        if not isinstance(value, (dict, list, tuple, set)):
            return
        refs[path] = value
        if id(value) in ancestors:
            return
        ancestors += (id(value),)
        if isinstance(value, dict):
            for key, child in value.items():
                collect(child, path + "/" + str(key), ancestors)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                collect(child, path + "/" + str(index), ancestors)

    collect(w.progress, "progress")
    for name in FIELDS:
        if hasattr(w, name):
            collect(getattr(w, name), name)
    return refs


def ui_state(w):
    return (w.mode, w.status.text(), w.quiz_word.text(),
            tuple((button.text(), button.isEnabled(), button.property("state")) for button in w.opt_btns),
            w.btn_dontknow.isEnabled(), w.btn_dontknow.property("state"))


def status_valid(w):
    text = re.sub(r"<[^>]*>", "", w.status.text()).replace("&nbsp;", " ")
    parts = [part.strip() for part in text.split("·")]
    return (len(parts) == 4 and parts[0] == "词汇量测试"
            and re.fullmatch(r"词目量\s*[\d,]+", parts[1]) is not None
            and re.fullmatch(r"误差\s*\d+(?:\.\d+)?%", parts[2]) is not None
            and re.fullmatch(r"严谨度\s*(?:\d+(?:\.\d+)?|max)", parts[3]) is not None)


def history_rows(count=120):
    return [{"id": "old-history-%d" % i, "ts": int(time.time()) - 10000 + i,
             "vocab": 1000 + i, "right": 30, "total": 50, "dontknow": 0,
             "theta": 0.5, "se": 0.4, "rigor": 90, "lo": 800, "hi": 1300,
             "err": 25, "baseline": i == 0,
             "future": {"keep": [i, None, {"next_schema": True}]}} for i in range(count)]


def new_card(sb, progress=None):
    w = sb.new_card(progress={"history": history_rows()} if progress is None else progress, show=True)
    QTest.qWait(20)
    w._due_timer.stop()
    w._window_save_timer.stop()
    return w


def click(button):
    QTest.mouseClick(button, Qt.LeftButton)


def answer_to(w, count):
    """Drive production answers/advancement without mocking rendering or unlocking."""
    for _ in range(count):
        if w.mode != "quiz" or w.quiz_i != len(w.quiz_resp):
            break
        item = w.quiz_items[w.quiz_i]["item"]
        if not w._quiz_answer(item["correct_index"]):
            break
        w.quiz_timer.stop()
        if not w._quiz_next():
            break
    return len(w.quiz_resp)


def mastery_unchanged(w, before, known):
    return (w.theta == before["theta"] and w.progress["theta"] == before["theta"]
            and w.known is known and w.states == before["states"]
            and w.prediction_data == before["prediction_state"])


def fail_transaction(sb, w, callback, action, label):
    before, refs, durable, old_ui = snapshot(w), references(w), sb.read_progress(), ui_state(w)
    real_save = app_main.storage.atomic_save
    writes = []

    def fail_save(path, data):
        if os.path.abspath(path) == os.path.abspath(sb.progress_path):
            writes.append(path)
            if ui_state(w) != old_ui:
                raise AssertionError("UI feedback changed before durable commit")
            raise app_main.storage.StorageError("injected transaction failure")
        return real_save(path, data)

    with patch.object(app_main.storage, "atomic_save", side_effect=fail_save), \
            patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok) as errors:
        result = callback()
    restored = references(w)
    check(result is False and len(writes) == 1 and errors.call_count == 1, label + " attempts one failed commit")
    check(snapshot(w) == before and set(refs) == set(restored)
          and all(restored[name] is value for name, value in refs.items())
          and sb.read_progress() == durable and ui_state(w) == old_ui,
          label + " restores original graph, containers, aliases and durable/UI state")
    check(w._quiz_retry_action == action and not w.quiz_timer.isActive(), label + " stops callbacks and exposes correct retry")


def commit_once(sb, w, callback, label, inspect=None):
    old_ui, real_save, writes = ui_state(w), app_main.storage.atomic_save, []

    def save(path, data):
        if os.path.abspath(path) == os.path.abspath(sb.progress_path):
            writes.append(path)
            if ui_state(w) != old_ui:
                raise AssertionError("UI feedback changed before durable commit")
            if inspect is not None:
                inspect(data)
        return real_save(path, data)

    with patch.object(app_main.storage, "atomic_save", side_effect=save):
        result = callback()
    check(result is True and len(writes) == 1, label + " commits once before UI feedback")
    return result


def test_settings_and_resume(sb):
    card = new_card(sb, {})
    card.open_settings()
    actions = (card.btn_history, card.btn_continue, card.btn_test)
    check(not hasattr(card, "lab_vocab") and all(button.minimumHeight() == 30
          and button.objectName() == "chip" for button in actions),
          "settings shows only equal-height vocabulary test action controls")
    check(card.btn_history.text() == "历史记录" and card.btn_test.text() == "开始新的测试"
          and card.btn_continue.isHidden(), "settings labels are exact and zero-session continue is hidden")
    card.welcome()
    with patch.object(QMessageBox, "question", side_effect=AssertionError("welcome must not show a prompt")):
        check(card._welcome_test() is True, "welcome test starts directly without a 50-question prompt")
    with patch.object(card, "_startup", wraps=card._startup) as startup:
        check(card.skip_test() is True and startup.call_count == 1,
              "non-settings end keeps the production startup route")
    card.open_settings()
    check(card.btn_continue.text() == "继续上次测试（剩余30天）" and card.btn_continue.isVisible(),
          "settings continue shows ceil remaining days")
    with patch.object(QMessageBox, "question", side_effect=AssertionError("new test must start directly")):
        click(card.btn_test)
    check(card.mode == "quiz" and not card.quiz_locked and bool(card.quiz_word.text())
          and all(button.isEnabled() for button in card.opt_btns), "new Bayesian quiz renders answerable UI")
    check(card.quiz_bank_fingerprint == card.bank_fingerprint, "session binds stable bank identity")
    card.progress["quiz_session"] = {"algo": "bayes-v140", "bank_id": card.bank_fingerprint,
                                     "state": {}, "items": [], "resp": [], "i": 0}
    check(card.start_quiz() is True and card.mode == "quiz"
          and card.progress["quiz_session"].get("id"),
          "damaged empty resume session is replaced with a playable fresh quiz")
    got = answer_to(card, 3)
    keys = [item["key"] for item in card.quiz_items]
    check(got == 3, "three responses were recorded: %d" % got)
    check(len(keys) == len(set(keys)) and len(card.quiz_resp) == 3,
          "question keys stay unique and all three responses persist")
    sid = card.quiz_session_id
    check(card.skip_test() is True, "ending quiz saves current attempt")
    session = card.progress.get("quiz_session")
    check(session and session["id"] == sid and len(session["resp"]) == 3,
          "ending retains same resumable session and answers")
    card.open_settings()
    click(card.btn_continue)
    check(card.mode == "quiz" and card.quiz_session_id == sid and len(card.quiz_resp) == 3
          and not card.quiz_locked, "resume restores stable session id and playable answers")
    with patch.object(card, "open_settings", wraps=card.open_settings) as settings, \
            patch.object(card, "_startup", wraps=card._startup) as startup:
        check(card.skip_test() is True and card.mode == "settings"
              and settings.call_count == 1 and startup.call_count == 0,
              "settings resume then end returns through production open_settings")
    old_history, old_id = copy.deepcopy(card.progress["history"]), card.quiz_session_id
    click(card.btn_test)
    check(card.quiz_session_id != old_id and card.quiz_resp == []
          and card.progress["history"] == old_history and card._quiz_remaining_days() == 30,
          "explicit new test resets 30 days without deleting saved history")
    with patch.object(card, "open_settings", wraps=card.open_settings) as settings, \
            patch.object(card, "_startup", wraps=card._startup) as startup:
        check(card.skip_test() is True and card.mode == "settings"
              and settings.call_count == 1 and startup.call_count == 0,
              "settings new test then end also returns to settings")
    QTest.qWait(20)
    card._due_timer.stop()
    card._window_save_timer.stop()
    now, session = int(time.time()), card.progress["quiz_session"]
    for seconds, days in ((86401, 2), (86400, 1), (1, 1), (0, 0), (-1, 0)):
        session["started_at"] = now + seconds - app_main.RESUME_TTL
        session["updated_at"] = now
        with patch.object(app_main.time, "time", return_value=now):
            card._refresh_settings()
            check(card._quiz_remaining_days() == days and card.btn_continue.isHidden() == (days == 0)
                  and (days == 0 or card.btn_continue.text() == "继续上次测试（剩余%d天）" % days),
                  "remaining-day ceil/visibility boundary: %d seconds" % seconds)
    expired_id = card.quiz_session_id
    with patch.object(app_main.time, "time", return_value=now):
        check(card.start_quiz() is True and card.quiz_session_id != expired_id,
              "sessions beyond 30 days expire despite recent updated_at")
    check(card.progress["quiz_session"]["id"] == card.quiz_session_id,
          "fresh attempt is persisted with a new identity")
    card.quiz_timer.stop()


def test_immediate_history_and_finish(sb):
    for unknown in (False, True):
        card = new_card(sb)
        card.open_settings()
        click(card.btn_test)
        before, known = copy.deepcopy(card.progress), card.known
        history, rows = card.progress["history"], list(card.progress["history"])
        sid = card.quiz_session_id
        correct = card.quiz_items[0]["item"]["correct_index"]
        choice = -1 if unknown else (correct + 1) % 4
        response = -1 if unknown else 0
        check(len(history) == 120 and not card.progress["quiz_session"].get("history_id"),
              "zero answers never create a history row")

        def inspect(data):
            assert len(data["history"]) == 121 and data["quiz_session"]["resp"] == [response]
            assert data["quiz_session"]["history_id"] == sid and data["history"][-1]["id"] == sid
            assert data["history"][-1]["total"] == 1 and data["history"][-1]["completed"] is False

        commit_once(sb, card, lambda: card._quiz_answer(choice), "first unknown/wrong answer", inspect)
        row = history[-1]
        check(sb.read_progress()["history"][-1] == row and row["right"] == 0
              and not row["prediction_eligible"] and not row["completed"],
              "at least one wrong/unknown answer is immediately durable in history without prediction")
        check(card.quiz_locked and card.quiz_timer.isActive() and status_valid(card)
              and not any(button.isEnabled() for button in card.opt_btns),
              "real answer feedback locks buttons and shows exactly four status fragments")
        spans = re.findall(r"<span[^>]*>(.*?)</span>", card.status.text())
        check(bool(spans) and all(re.fullmatch(r"(?:\d+(?:\.\d+)?|max)", number) for number in spans),
              "status colors changed numeric values only, never labels or an extra delta")
        with patch.object(app_main.storage, "atomic_save", wraps=app_main.storage.atomic_save) as writes:
            click(card.opt_btns[correct])
            duplicate = card._quiz_answer(correct)
        check(duplicate is False and writes.call_count == 0 and len(card.quiz_resp) == 1
              and len(history) == 121, "duplicate feedback callbacks cannot score or save again")
        shared = card.quiz_state.setdefault("future", {"keep": [1, None, {"schema": 9}]})
        card.quiz_items[0]["future"] = shared
        card.progress["quiz_session"]["future"] = shared
        row["future"] = shared
        custom = row["custom"] = {"retain": [8, 9]}
        card.quiz_timer.stop()
        commit_once(sb, card, card._finish_quiz, "zero-right finish")
        check(len(history) == 121 and history[-1] is row and row["id"] == sid
              and row["total"] == 1 and row["right"] == 0 and row["completed"]
              and not row["prediction_eligible"], "finish upserts one same-id history row even with zero correct")
        check(history[:-1] == before["history"] and all(current is original for current, original in zip(history[:-1], rows))
              and row["future"] is shared and row["custom"] is custom
              and sb.read_progress()["history"][-1]["custom"] == {"retain": [8, 9]},
              "finish does not truncate old history or remove unknown fields and their aliases")
        check(mastery_unchanged(card, before, known), "saving/finishing never sets theta, mastery or prediction implicitly")
        with patch.object(app_main.storage, "atomic_save", wraps=app_main.storage.atomic_save) as writes:
            result = card._finish_quiz()
        check(result is False and writes.call_count == 0 and len(history) == 121,
              "completed-session callback cannot append or commit again")
        card.open_settings()
        click(card.btn_history)
        check(card.mode == "history" and len(card.history_chart.points) == 121,
              "history page displays every preserved row including wrong/unknown attempt")
        card._delete_history(120)
        check(len(card.progress["history"]) == 120 and card.progress["history"] == before["history"],
              "history row can be deleted without altering other rows")
        card._due_timer.stop()
        card._window_save_timer.stop()


def test_failures_and_real_timer(sb):
    card = new_card(sb)
    card.open_settings()
    click(card.btn_test)
    for choice in (card.quiz_items[0]["item"]["correct_index"],
                   (card.quiz_items[0]["item"]["correct_index"] + 1) % 4, -1):
        fail_transaction(sb, card, lambda: card._quiz_answer(choice), None, "answer %d" % choice)
    correct = card.quiz_items[0]["item"]["correct_index"]
    commit_once(sb, card, lambda: card._quiz_answer(correct), "answer retry")
    shared = card.quiz_state.setdefault("future", {"keep": [1, {"next_schema": True}]})
    card.quiz_items[0]["future"] = shared
    card.progress["quiz_session"]["future"] = shared
    card.progress["history"][-1]["future"] = shared
    card.quiz_status_values["future"] = shared
    card.quiz_timer.stop()
    fail_transaction(sb, card, card._quiz_next, "next", "next")
    commit_once(sb, card, card.retry_or_skip, "next retry")
    check(card.quiz_i == 1 and card.quiz_resp == [1] and not card.quiz_locked
          and all(button.isEnabled() for button in card.opt_btns),
          "next retry renders unlocked next question without rescoring")
    commit_once(sb, card, lambda: card._quiz_answer(-1), "second answer")
    # The genuine production QTimer, never replaced or forced unlocked, advances.
    QTest.qWait(900)
    check(card.quiz_i == 2 and card.quiz_resp == [1, -1] and not card.quiz_locked
          and not card.quiz_timer.isActive() and all(button.isEnabled() for button in card.opt_btns)
          and card.btn_dontknow.isEnabled() and status_valid(card),
          "real 650ms timer advances and refreshes answerable UI without extra status numbers")
    stable = snapshot(card)
    with patch.object(app_main.storage, "atomic_save", wraps=app_main.storage.atomic_save) as writes:
        late = card._quiz_next()
    check(late is False and writes.call_count == 0 and snapshot(card) == stable,
          "late timeout cannot skip an unanswered question")
    future_time = int(time.time()) + 77
    with patch.object(app_main.time, "time", return_value=future_time):
        fail_transaction(sb, card, card.skip_test, "skip", "skip with changed updated_at/history timestamp")
        commit_once(sb, card, card.retry_or_skip, "skip retry")
    check(card.mode == "settings" and len(card.progress["history"]) == 121,
          "skip retry retains one history row and returns settings")
    card._due_timer.stop()
    card._window_save_timer.stop()
    click(card.btn_continue)
    correct = card.quiz_items[card.quiz_i]["item"]["correct_index"]
    commit_once(sb, card, lambda: card._quiz_answer(correct), "finish preparation")
    card.quiz_timer.stop()
    fail_transaction(sb, card, card._finish_quiz, "finish", "finish")
    commit_once(sb, card, card.retry_or_skip, "finish retry")
    check(len(card.progress["history"]) == 121 and card.progress["history"][-1]["completed"],
          "finish retry completes existing history instead of adding a duplicate")


def test_close_and_history_detach(sb):
    card = new_card(sb)
    card.open_settings()
    click(card.btn_test)
    correct = card.quiz_items[0]["item"]["correct_index"]
    card._quiz_answer(correct)
    sid = card.quiz_session_id
    check(card.close() is True, "real feedback close saves and cancels timers")
    persisted = sb.read_progress()
    check(persisted["quiz_session"]["resp"] == [1] and len(persisted["history"]) == 121,
          "feedback close retains immediately saved session and history")
    before = snapshot(card)
    with patch.object(app_main.storage, "atomic_save", side_effect=AssertionError("closed callback wrote")):
        results = (card._quiz_answer(correct), card._quiz_next(), card.skip_test(),
                   card.start_quiz(), card._finish_quiz(), card.retry_or_skip(), card._save_quiz_session())
    check(not any(results) and snapshot(card) == before, "closed callbacks mutate no graph and make no writes")
    resumed = new_card(sb, persisted)
    resumed.open_settings()
    click(resumed.btn_continue)
    check(resumed.quiz_session_id == sid and resumed.quiz_i == 1 and resumed.quiz_resp == [1]
          and not resumed.quiz_locked, "cold resume advances answered-current without repeated score")
    resumed.quiz_timer.stop()
    resumed._closing = True
    before = snapshot(resumed)
    with patch.object(app_main.storage, "atomic_save", side_effect=AssertionError("closing callback wrote")):
        results = (resumed._quiz_answer(-1), resumed._quiz_next(), resumed.skip_test(),
                   resumed.start_quiz(), resumed._finish_quiz(), resumed.retry_or_skip())
    check(not any(results) and snapshot(resumed) == before, "closing callbacks are terminal no-ops")
    resumed._closing = False
    resumed.skip_test()
    resumed._delete_history(120)
    check(len(resumed.progress["history"]) == 120, "history row can be deleted")
    check(resumed.progress["quiz_session"]["history_id"] is None,
          "deleting history detaches resumable session reference")
    resumed._due_timer.stop()
    resumed._window_save_timer.stop()


def main():
    sb = Sandbox(app_main, "v140")
    exceptions = []
    old_hook = sys.excepthook
    sys.excepthook = lambda typ, value, tb: exceptions.append(repr(value))
    try:
        with patch.object(QMessageBox, "critical", return_value=QMessageBox.Ok), \
                patch.object(QMessageBox, "information", return_value=QMessageBox.Ok), \
                patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), sb:
            scenarios = (("settings/resume", test_settings_and_resume),
                         ("immediate history", test_immediate_history_and_finish),
                         ("rollback/timer", test_failures_and_real_timer),
                         ("close/history detach", test_close_and_history_detach))
            for name, scenario in scenarios:
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
            check(sb.verify_real(), "real records remain unchanged")
    finally:
        sys.excepthook = old_hook
    return sb.finish(out, fails, "test_v140_ui.txt")


if __name__ == "__main__":
    sys.exit(main())
