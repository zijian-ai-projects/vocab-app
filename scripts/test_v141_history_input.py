"""Synthetic-only history theme and window-button focus regressions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')
from unittest.mock import patch
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QPushButton
import test_v130_ui as base
import test_v136_ui as v136
import main as m
import theme

base.configure_qt('offscreen')
base.set_nottest()
base.new_app()
checks = []
def check(ok, name):
    assert ok, name
    checks.append(name)
def focused_key(w, key):
    QTest.keyClick(QApplication.focusWidget() or w, key)
    base.pump()

with base.Sandbox(m, 'v141-history-input') as sb:
    suite = v136.V136Suite(sb)
    with suite.fixture_scope():
        w = suite.card(v136.v136_progress(), v136.win_fixture(edge_collapse=False))
        w.activateWindow()
        w.setFocus()
        base.pump()
        first = base.key_of(w)
        QTest.mouseClick(w.btn_min, Qt.LeftButton)
        base.pump()
        compact = w.compact
        check(compact, 'mouse click compacts brush window')
        check(QApplication.focusWidget() is not w.btn_min, 'compact control does not retain mouse focus')
        focused_key(w, Qt.Key_Space)
        check(w.compact == compact and w.mode == 'back' and w.states[first]['seen'] == 1,
              'focused Space scores word rather than resizing')
        for _ in range(4):
            focused_key(w, Qt.Key_Space)
            check(w.compact == compact, 'repeated Space never toggles window size')
        QTest.mouseClick(w.btn_gear, Qt.LeftButton)
        base.pump()
        check(w.mode == 'settings', 'mouse gear opens settings')
        with patch.object(w, 'close', wraps=w.close) as close:
            for _ in range(3):
                focused_key(w, Qt.Key_Space)
            check(w.isVisible() and w.mode == 'settings' and not close.called,
                  'settings Space never closes window')
            for button in w._window_buttons:
                button.setFocus()
                QTest.keyClick(button, Qt.Key_Space)
                QTest.keyClick(button, Qt.Key_Return)
                base.pump()
            check(w.isVisible() and w.mode == 'settings' and not close.called,
                  'forced toolbar focus cannot activate close/back/resize by Space or Enter')
        # Real settings controls keep keyboard accessibility.
        edge = w.btn_edge_collapse
        old_edge = edge.isChecked()
        edge.setFocus()
        QTest.keyClick(edge, Qt.Key_Space)
        base.pump()
        check(edge.isChecked() != old_edge, 'settings option still accepts Space')
        now = 1700000000
        w.progress['history'] = [dict(ts=now, vocab=200, total=10, err=20, rigor=80)]
        palettes = []
        for name in theme.ORDER:
            w.set_theme(name)
            w._open_history_page()
            base.pump()
            t = theme.get(name)
            chart = w.history_chart
            check(chart.c == dict(bg=t['bg'], grid=t['chart_grid'], text=t['chart_text'],
                                  date=t['chart_date'], line=t['chart_line']), name + ' history chart consumes active theme')
            palettes.append(tuple(chart.c.values()))
            check(chart.grab().toImage().pixelColor(0, 0) == QColor(t['bg']), name + ' chart canvas blends with page')
            summary = w.history_rows.findChild(QPushButton, 'historySummary')
            delete = w.history_rows.findChild(QPushButton, 'historyDelete')
            check(summary.height() == delete.height() and summary.y() == delete.y(), name + ' row heights and top alignment')
            check(summary.palette().color(summary.foregroundRole()) == delete.palette().color(delete.foregroundRole()),
                  name + ' row text colors agree')
            # Blank pixels inside the borders verify rendered QSS backgrounds.
            def fill(button):
                return button.grab().toImage().pixelColor(3, 3)
            check(fill(summary) == fill(delete) == QColor(t['opt_bg']), name + ' matching rendered row backgrounds')
            summary.click()
            base.pump()
            check(summary.height() == delete.height() and summary.y() == delete.y(), name + ' expanded row keeps delete top-aligned')
            check(fill(summary) == fill(delete), name + ' expanded row retains matching base colors')
        check(len(set(palettes)) == 4, 'all four chart themes are distinct')
        w.close()
    check(not sb.errors, 'sandbox protection remains intact')
print('V1.4.1 history/input: %d checks passed' % len(checks))
