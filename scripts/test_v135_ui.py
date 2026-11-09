# -*- coding: utf-8 -*-
"""V135: all 183 real reviewed stage entries, plus native/Qt learning flows.

Only Sandbox profiles are written. Run with -B; add --native for Windows Qt.
No fake bank/books/meaning loader is used in these cases.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import random
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import test_v130_ui as base
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
import level_meanings
import study_options
from entries import meaning, word_caption

ROOT = Path(__file__).resolve().parent.parent
REVIEW = json.loads((ROOT / 'data' / 'school_meaning_reviews.json').read_text(encoding='utf-8'))
ROWS = {stage: {entry['w']: entry['levels'][stage] for entry in REVIEW['entries'] if stage in entry['levels']}
        for stage in ('primary', 'middleschool')}
SAMPLES = [('primary', 'alice'), ('middleschool', 'alice'), ('primary', 'matt'),
           ('middleschool', 'matt'), ('primary', 'bds'), ('primary', 'bund'),
           ('primary', 'er'), ('primary', 'ms'), ('primary', 'app'),
           ('middleschool', 'am'), ('middleschool', 'x-ray'), ('middleschool', 'sato'),
           ('middleschool', 'ruby'), ('middleschool', 'wwf'), ('middleschool', 'thanksgiving')]


class ReviewSuite(base.Suite):
    def reviewed_card(self, stage, word, mode):
        bid = ROWS[stage][word]['context_books'][0]
        words = base.app_main.bk.words(bid)
        pos = words.index(word)
        data = base.progress(book=bid, study_mode=mode, history=[], states={},
                             cursors={bid: pos}, orders={bid: {'mode': 'seq', 'seed': 42}})
        return self.card(data)

    def shot(self, window, name):
        if not base.FLAGS.native:
            return
        base.pump(4)
        QTest.qWait(180)
        path = os.path.join(self.sb.outdir, name + '.png')
        self.check(window.grab().save(path), '原生隔离截图：' + name)
        self.screens.append(path)

    def all_reviewed_entries(self):
        w = self.reviewed_card('primary', 'alice', 'brush')
        before = deepcopy(w.bank_map)
        original_states, original_history = deepcopy(w.states), deepcopy(w.progress['history'])
        count = 0
        for stage, values in ROWS.items():
            allowed = {value['display_s'] for value in w.level_meanings[stage].values()}
            stage_pool = w._level_option_pool(stage).prepare()
            book_cache = {}
            for word, reviewed in values.items():
                bid = reviewed['context_books'][0]
                if bid not in book_cache:
                    book_cache[bid] = w._book_words(bid)
                entries = book_cache[bid]
                entry = next(item for item in entries if item['w'] == word)
                self.check(w._book_level(bid) == stage and meaning(entry) == reviewed['meaning']
                           and word_caption(entry) == reviewed['headword'],
                           stage + '/' + word + ' 真实书短义/规范显示一致')
                self.check(entry is not w.bank_map[word] and all(entry[k] == v for k, v in before[word].items()),
                           stage + '/' + word + ' 原全部字段及稳定key不变')
                try:
                    question = study_options.make_options(entry, w._book_level_option_pool(bid, stage), random.Random(count))
                except ValueError:
                    question = study_options.make_options(entry, stage_pool, random.Random(count))
                self.check(len(question['options']) == len(set(question['options'])) == 4
                           and question['options'][question['correct']] == reviewed['meaning']
                           and all(text in allowed for text in question['options']),
                           stage + '/' + word + ' 正确项与3干扰项同学段且不重复')
                w.catalog.set_book(bid, 'V135真实书逐词检查', entries, w.states, set())
                row_index = next(i for i, item in enumerate(w.catalog.model.rows) if item['w'] == word)
                self.check(w.catalog.model.data(w.catalog.model.index(row_index, 0), Qt.DisplayRole) == reviewed['headword']
                           and w.catalog.model.data(w.catalog.model.index(row_index, 1), Qt.DisplayRole) == reviewed['meaning'],
                           stage + '/' + word + ' 原生目录词形与释义')
                self.check(w.catalog.model.data(w.catalog.model.index(row_index, 1), Qt.ToolTipRole)
                           == reviewed['headword'] + '\n' + reviewed['meaning'],
                           stage + '/' + word + ' 悬停提示同一校订')
                count += 1
        self.check(count == 183, '183学段项全部进入真实运行时、目录和四选项链路')
        self.check(w.bank_map == before and w.states == original_states and w.progress['history'] == original_history,
                   '全量查看/出题不污染通用bank、真实词书身份、states或history')

    def brush_and_choice(self, stage, word):
        reviewed = ROWS[stage][word]
        for mode in ('brush', 'choice'):
            w = self.reviewed_card(stage, word, mode)
            current = w.queue[w.qi]['w']
            self.check(current['w'] == word, stage + '/' + word + ' 实际原书游标选中目标', require=True)
            self.check(meaning(current) == reviewed['meaning'] and word_caption(current) == reviewed['headword'],
                       stage + '/' + word + ' 实际当前词使用校订')
            self.check(word not in w.states and w.progress['history'] == [], '隔离资料原空状态/空历史')
            if mode == 'brush':
                self.check(w.mode == 'front' and w.word.text() == reviewed['headword']
                           and w.meaning.text() == reviewed['meaning'], '刷词真实正面词形/待显示义')
                QTest.mouseClick(w.btn_remember, Qt.LeftButton)
                base.pump(3)
                self.check(w.mode == 'back' and w.meaning.text() == reviewed['meaning'], '实际认识按钮翻面仍为校订义')
                if (stage, word) in (('primary', 'alice'), ('primary', 'bds'), ('middleschool', 'ruby')):
                    self.shot(w, stage + '-' + word + '-brush')
            else:
                question = w.choice_question
                allowed = {value['display_s'] for value in w.level_meanings[stage].values()}
                self.check(w.mode == 'choice' and w.choice_word.text() == reviewed['headword']
                           and question['options'][question['correct']] == reviewed['meaning']
                           and all(text in allowed for text in question['options']), '真实选择题四项同学段')
                self.check(all(button.text() == '%s  %s' % ('ABCD'[i], question['options'][i])
                               for i, button in enumerate(w.study_btns)), 'A-D实际按钮显示完整校订短义')
                if (stage, word) in (('middleschool', 'alice'), ('primary', 'bund')):
                    self.shot(w, stage + '-' + word + '-choice')
                QTest.mouseClick(w.study_btns[question['correct']], Qt.LeftButton)
                base.pump(3)
                self.check(w.mode == 'choice_back' and w.choice_locked, '实际选择按钮完成作答反馈')
            self.check(set(w.states) == {word} and w.states[word]['lv'] == 1,
                       '首次实际作答只写原稳定key并进入Lv1')
            self.check(reviewed['headword'] == word or reviewed['headword'] not in w.states,
                       '显示大小写/别名不创建新记忆key')
            self.check(w.progress['history'] == [] and not w.bank_map[word].get('_school_caption'),
                       '不写测试历史，不污染原bank或学校标记')

    def general_measurement_caption(self):
        w = self.reviewed_card('primary', 'alice', 'brush')
        original = deepcopy(w.bank_map['alice'])
        w.start_quiz()
        idx = next(i for i, entry in enumerate(w.bank) if entry['w'] == 'alice')
        # Render a deterministic generic-bank question; do not alter sampling code.
        options = [meaning(w.bank[idx])] + [meaning(w.bank[i]) for i in (0, 1, 2)]
        w.quiz_items = [{'idx': idx, 'opts': options, 'correct': 0}]
        w.quiz_i = 0
        w._quiz_show()
        self.check(w.quiz_word.text() == 'alice', '通用测量不借用学校Alice别名')
        self.check(w.opt_btns[0].text() == 'A  ' + original['s'], '通用测量正确项保留原bank来源')
        self.check(w.bank_map['alice'] == original and w.progress['history'] == [], '只渲染不改通用词条或测量历史')


def main():
    label = 'v135-native' if base.FLAGS.native else 'v135-offscreen'
    sb = base.Sandbox(base.app_main, label)
    suite = ReviewSuite(sb)
    with patch.dict(os.environ, {'VOCABAPP_DATA_DIR': sb.dir}):
        with sb:
            with patch.object(sys, 'excepthook', suite.exception):
                suite.run('all-reviewed-183', suite.all_reviewed_entries, fake=False)
                for stage, word in SAMPLES:
                    suite.run(stage + '-' + word, lambda s=stage, k=word: suite.brush_and_choice(s, k), fake=False)
                suite.run('general-measurement', suite.general_measurement_caption, fake=False)
                suite.check(sb.verify_real(), '真实进度/窗口/备份/临时路径指纹未变')
    for path in suite.screens:
        suite.out.append('SCREENSHOT ' + path)
        print('SCREENSHOT', path)
    code = sb.finish(suite.out, suite.fails, 'test_v135_ui.txt')
    print('V135 CHECKS', suite.checks, 'FAILS', len(suite.fails) + len(sb.errors))
    return code


if __name__ == '__main__':
    sys.exit(main())
