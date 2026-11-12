# -*- coding: utf-8 -*-
"""Synthetic-only UI checks for the six V1.4.1 follow-up requests."""
import copy
import time
from unittest.mock import patch
from ui_test_support import configure_qt, set_nottest, new_app, Sandbox
configure_qt('offscreen')
set_nottest(True)
from PyQt5.QtWidgets import QPushButton, QLabel
import main as m
import school_knowledge as school
import theme
import entries
app = new_app()
checks = []
def check(value, name):
    assert value, name
    checks.append(name)

def pump():
    for _ in range(6): app.processEvents()

with Sandbox(m, 'v141-optimizations') as sb:
    w = sb.new_card(show=True)
    now = time.time()
    old = {'id':'older','ts':now-100, 'vocab':200,'total':15,'err':70,'rigor':30}
    latest = {'id':'newest','ts':now, 'vocab':300,'total':20,'err':60,'rigor':40}
    w.progress['history'] = [old, latest]
    w.progress['quiz_session'] = {'id':'newest','started_at':now,'resp':[], 'history_id':'newest'}
    w._open_history_page()
    pump()
    summaries = w.history_rows.findChildren(QPushButton, 'historySummary')
    check(len(summaries)==2 and all('平均' in b.text() and '/' not in b.text() for b in summaries), 'compact date and average history')
    detail = w.history_details[1]
    check(detail.isHidden(), 'history details collapsed initially')
    summaries[0].click()
    pump()
    check(not detail.isHidden() and w.mode=='history' and all(s in detail.text() for s in ('已测词数','误差','严谨度')), 'inline detail expands without result page')
    check(detail.x() == summaries[0].x() and detail.width() == summaries[0].width()
          and detail.y() == summaries[0].y() + summaries[0].height(), 'history detail joins summary with matching edges')
    summaries[0].click()
    check(detail.isHidden(), 'history collapses again')
    with patch.object(w, 'save', side_effect=m.storage.StorageError('synthetic')), patch.object(m.QMessageBox, 'critical'):
        w._delete_history(1)
    check(len(w.progress['history'])==2 and w._quiz_remaining_days()>0, 'delete failure restores resume and history')
    w._delete_history(0)
    check(w._quiz_remaining_days()>0, 'deleting older history preserves resume')
    w._delete_history(0)
    check(w._quiz_remaining_days()==0 and w.btn_continue.isHidden(), 'deleting latest history hides resume')
    check(sb.read_progress()['quiz_session']['resume_disabled'], 'resume disabled persisted')
    w._refresh_settings()
    check(not any('记录模型' in l.text() or '记录目录' in l.text() for l in w.settings_body.findChildren(QLabel)), 'no record model or directory row')
    check([b.text() for b in w.school_chips.values()]==['关闭','小学','小初','小初高'], 'short school labels')
    labels = [l.text() for l in w.settings_body.findChildren(QLabel)]
    check('已认识词汇范围—开启后跳过对应词汇的学习' in labels, 'school note inline with heading')
    check('词汇量测试—结果仅供参考' in labels, 'measurement heading includes disclaimer')
    w.quiz_session_id = 'initial-display'
    w.quiz_resp = []
    w.rigor = 0
    w.progress['history'] = []
    w._quiz_status()
    check('词目量-' in w.status.text() and '误差100%' in w.status.text()
          and '暂估' not in w.status.text() and '尚未测得' not in w.status.text(), 'initial quiz placeholders')
    for palette in theme.THEMES.values():
        history_style = theme.history_qss(palette)
        check('QPushButton#historySummary' in history_style and 'border-radius: 0' in history_style
              and 'QPushButton#historyDelete' in history_style, 'square themed history rows')
        def contrast(fg, bg):
            def lum(value):
                channels = [int(value[i:i+2], 16)/255.0 for i in (1,3,5)]
                linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in channels]
                return sum(a*b for a,b in zip((.2126,.7152,.0722),linear))
            hi, lo = sorted((lum(palette[fg]), lum(palette[bg])), reverse=True)
            return (hi+.05)/(lo+.05)
        check(contrast('chip_fg','chip_bg') >= 4.5 and contrast('btn_fg','btn_bg') >= 4.5,
              'history detail/delete text contrast')
    check(entries.memory_info('synthetic-predicted', {}, predicted={'synthetic-predicted'})
          == ('predicted', None, '已掌握'), 'prediction status label has no prediction prefix')
    for available, provisional in ((False, True), (True, True), (True, False)):
        rec = dict(latest, estimate_available=available, provisional=provisional,
                   right=1, dontknow=0, lo=0, hi=400)
        w._fill_result(rec, [rec], False)
        check('暂估' not in w.res_big.text() and '尚未测得' not in w.res_big.text(),
              'result omits estimate qualifiers')
        if not available:
            check('-' in w.res_big.text(), 'unavailable estimate is not displayed as a measured number')
    # Select a real school book but create scheduler records only in sandbox.
    w.book_id = 'gk-dg'
    keys = w._book_word_strs(w.book_id)
    key = next(k for k in keys if k in school.words('primary'))
    w.states[key] = {'st':'learning','lv':1,'due':0,'seen':1,'lapse':0}
    w._refresh_known()
    original = w._book_stats(w.book_id)
    before = copy.deepcopy(w.states)
    check(w.set_school_knowledge('primary'), 'enable primary scope')
    remaining = w._book_stats(w.book_id)
    check(remaining[3] == len([k for k in keys if k not in school.words('primary')]) < original[3], 'denominator excludes school vocabulary')
    check(remaining[0]==0 and w.states==before, 'learned numerator excludes scoped word without erasing state')
    check(w.set_school_knowledge('off') and w._book_stats(w.book_id)==original, 'disable restores original counts')
    # The picked quiz unknown style is the same semantic pressed state as study.
    for palette in theme.THEMES.values():
        css = theme.qss(palette)
        check('QPushButton#dontknow[state="pressed"]' in css, 'shared unknown pressed style')
    check(w._measurement_error_text({'measurement_schema':2,'err':12,'evidence_limited':True})=='样本不足', 'sparse evidence never claims low error')
    check(w._measurement_error_text({'err':None})=='样本不足', 'no-correct error is unavailable')
assert not sb.errors, sb.errors
print('V1.4.1 optimizations: %d checks passed' % len(checks))
