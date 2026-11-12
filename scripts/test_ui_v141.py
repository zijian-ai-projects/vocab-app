# -*- coding: utf-8 -*-
"""Isolated V1.4.1 UI and preference regression checks."""
import copy
import sys
from unittest.mock import patch
from ui_test_support import configure_qt, set_nottest, new_app, Sandbox
configure_qt('offscreen')
set_nottest(True)
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt
import main as m
import school_knowledge as school
import prediction
app = new_app()
checks = []
def check(value, name):
    assert value, name
    checks.append(name)
with Sandbox(m, 'v141') as sb:
    w = sb.new_card(show=True)
    app.processEvents()
    check(w.mode == 'books' and w._test_first_show_mode == 'books', 'direct book startup')
    check(w.sel_book is None and not w.btn_learn.isEnabled(), 'no implicit book selection')
    check(not w.known and school.normalize(w.progress.get('school_knowledge')) == 'off', 'school default off')
    check(not school.words('off') and school.words('primary') < school.words('middle') < school.words('high'), 'cumulative school sets')
    states = copy.deepcopy(w.states)
    for level in ('primary', 'middle', 'high', 'off'):
        check(w.set_school_knowledge(level), 'save school ' + level)
        check(set(w.known) == set(school.words(level)), 'known set ' + level)
        check(w.states == states, 'scheduler records untouched ' + level)
        check(sb.read_progress()['school_knowledge'] == level, 'persist school ' + level)
    with patch.object(w, 'save', side_effect=m.storage.StorageError('synthetic')), patch.object(m.QMessageBox, 'critical'):
        check(not w.set_school_knowledge('high') and not w.known, 'failed preference rollback')
    check(tuple(w.catalog.filter_chips) == ('all', 'learned', 'unlearned'), 'three catalog categories')
    check(not any(b.text() in ('选择', '选择当前筛选', '加入学习') for b in w.catalog.findChildren(QPushButton)), 'no selection actions')
    w.open_books('welcome')
    app.processEvents()
    check(w.btn_catalog_books.height() == w.btn_learn.height(), 'equal button heights')
    check(w.btn_catalog_books.font().pixelSize() == w.btn_learn.font().pixelSize(), 'equal button font sizes')
    w.quiz_session_id = 'synthetic'
    w.quiz_resp = [1]
    w.rigor = 10
    w.progress['history'] = [{'id':'synthetic','total':1,'vocab':100,'err':10}]
    w.quiz_status_values = {'id':'synthetic','vocab':120,'err':15,'rigor':10}
    w._quiz_status()
    check("#177245'>±10" in w.status.text(), 'decreasing error green')
    w.progress['history'][0]['err'] = 20
    w._quiz_status()
    check("#b82c3c'>±20" in w.status.text(), 'increasing error red')
    # Legacy direct callers cannot leave a mismatched persisted prediction count.
    w.prediction_data['selected'] = ['synthetic']
    w.prediction_data['effective']['selected'] = 1
    w.known.add('synthetic')
    check(w._bulk_learn_selected(['synthetic']), 'legacy bulk compatibility')
    prediction.validate_prediction_data(sb.read_progress()['prediction_state'])
    check(True, 'prediction count persists consistently')
with Sandbox(m, 'v141-queue') as queue_sb:
    w = queue_sb.new_card(show=False)
    school_key = next(iter(school.words('primary')))
    w.book_id = 'synthetic-school'
    w.progress.update(book_confirmed=True, book=w.book_id)
    w.queue_words = [{'w': school_key, 's': 'school'}, {'w': 'zz-test-outside-school', 's': 'outside'}]
    w.book_words = w.queue_words
    w._make_engine()
    w.open_settings()
    check(w.set_school_knowledge('primary'), 'enable queue assumption')
    w._make_engine()
    check(w.study_engine.next()['w']['w'] == 'zz-test-outside-school', 'school vocabulary skipped')
    check(w.set_school_knowledge('off'), 'disable queue assumption')
    # Keep the currently unanswered outside word; after answering it the
    # reset cursor must make previously skipped school vocabulary available.
    item = w.study_engine.next()
    w.study_engine.answer(item, True)
    w._make_engine()
    check(w.study_engine.next()['w']['w'] == school_key, 'disabled school vocabulary returns behind cursor')
assert not queue_sb.errors, queue_sb.errors
assert not sb.errors, sb.errors
print('V1.4.1 UI: %d checks passed' % len(checks))
