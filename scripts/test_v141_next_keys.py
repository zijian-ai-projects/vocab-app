"""Isolated dual next-key checks in brush and choice study modes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')
from unittest.mock import patch
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
import test_v130_ui as base
import test_v136_ui as v136
import main as m
base.configure_qt('offscreen')
base.set_nottest()
base.new_app()
checks = 0
with base.Sandbox(m, 'v141-next-keys') as sb:
    suite = v136.V136Suite(sb)
    with suite.fixture_scope():
        for mode, phase in (('brush', 'back'), ('choice', 'choice_back')):
            w = suite.card(v136.v136_progress(study_mode=mode), v136.win_fixture(edge_collapse=False))
            w._set_mode(phase)
            button = w.btn_next if mode == 'brush' else w.btn_study_next
            assert button.text() == '下一个 [空格/enter]', button.text()
            checks += 1
            for target in (w, button, w.btn_min):
                for key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                    with patch.object(w, '_next') as next_word:
                        QTest.keyClick(target, key)
                        assert next_word.call_count == 1, (mode, key, next_word.call_count)
                    checks += 1
            w.close()
        w = suite.card(v136.v136_progress(), v136.win_fixture(edge_collapse=False))
        w.act('remember')
        assert w.mode == 'back' and w.btn_next.text() == '下一个 [enter]', w.btn_next.text()
        checks += 1
        for target in (w, w.btn_next, w.btn_wrong, w.btn_min):
            with patch.object(w, 'correct') as correct, patch.object(w, '_next') as next_word:
                QTest.keyClick(target, Qt.Key_Space)
                assert correct.call_count == 1 and next_word.call_count == 0
                checks += 1
            for key in (Qt.Key_Return, Qt.Key_Enter):
                with patch.object(w, 'correct') as correct, patch.object(w, '_next') as next_word:
                    QTest.keyClick(target, key)
                    assert next_word.call_count == 1 and correct.call_count == 0
                    checks += 1
        w.close()
    assert not sb.errors, sb.errors
print('V1.4.1 next keys: %d checks passed' % checks)
