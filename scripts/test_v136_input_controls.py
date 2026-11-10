"""Focused Qt regressions for always-on keyboard and toolbar actions."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import test_v130_ui as base
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

import test_v136_ui as v136
import main as app_main


base.configure_qt("offscreen")
base.set_nottest()
base.new_app()


def main():
    failures = []
    import test_v136_ui
    sb = base.Sandbox(app_main, "v136-input-controls")
    with sb:
        suite = test_v136_ui.V136Suite(sb)
        with suite.fixture_scope():
            w = suite.card(v136.v136_progress(), v136.win_fixture(edge_collapse=False))
            first = base.key_of(w)
            w.btn_gear.click()
            base.pump()
            if w.mode != "settings":
                failures.append("gear click did not open settings")
            if hasattr(w, "input_mode_chips"):
                failures.append("settings still exposes input mode selector")
            w.close_settings()
            base.pump()
            w.btn_min.click()
            base.pump()
            if not w.compact:
                failures.append("brush minimize click did not compact window")
            if not w.btn_min.isVisible():
                failures.append("brush minimize button hidden on brush page")
            if w.mode == "front":
                QTest.keyClick(w, Qt.Key_Space)
                base.pump()
                if w.mode != "back" or w.states[first]["seen"] != 1:
                    failures.append("Space did not score forget while buttons remain usable")
            w.btn_gear.click()
            base.pump()
            if w.mode != "settings":
                failures.append("gear stopped working after compact restore")
            w.close()

            w = suite.card(v136.v136_progress(study_mode="choice"),
                           v136.win_fixture(edge_collapse=False))
            if w.btn_min.isVisible():
                failures.append("minimize button is visible on choice page")
            w.btn_gear.click()
            base.pump()
            if w.mode != "settings":
                failures.append("choice-page gear click did not open settings")
            w.close()

    print("INPUT_CONTROLS failures=%d" % len(failures))
    for failure in failures:
        print("FAIL " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
