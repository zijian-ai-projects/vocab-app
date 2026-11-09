# -*- coding: utf-8 -*-
"""Read-only V135 review, provenance, fixed-scope and stable-identity regressions."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'app'))
import build_level_meanings as builder
import level_meanings
from entries import meaning, word_caption


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


class SchoolReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = load(builder.REVIEW_PATH)
        cls.data = load(builder.OUT_PATH)
        cls.bank = {row['w']: row for row in load(builder.BANK_PATH)}
        cls.bank.update({row['w']: row for row in load(builder.PHRASES_PATH)})
        cls.books = load(builder.BOOKS_PATH)
        cls.phrase_books = load(builder.PHRASE_BOOKS_PATH)
        cls.rows = builder.read_school_reviews(cls.bank)
        cls.runtime = level_meanings.load(builder.OUT_PATH)
        cls.legacy = {}
        for stage in builder.STAGES:
            words, ids = builder.ordered_stage_words(cls.books, stage, cls.phrase_books)
            glosses = builder.gloss_index(ids, {})
            result = {}
            for word in words:
                context = builder.CASEFOLD_CONTEXT.get(word)
                selectors = context[1].get(stage) if context and context[0] not in cls.bank else None
                text, provenance = builder.select_meaning(stage, word, cls.bank[word],
                                                         glosses.get(word, []), selectors)
                result[word] = {'meaning': text, 'provenance': provenance}
            cls.legacy[stage] = result

    def test_exact_158_183_scope_and_truthful_actions(self):
        self.assertEqual(len(self.review['entries']), 158)
        self.assertEqual({s: len(v) for s, v in self.rows.items()}, {'primary': 47, 'middleschool': 136})
        self.assertEqual(len(set(self.rows['primary']) & set(self.rows['middleschool'])), 25)
        self.assertEqual(len(set(self.rows['primary']) | set(self.rows['middleschool'])), 158)
        actions = Counter(row['action'] for values in self.rows.values() for row in values.values())
        self.assertEqual(actions, Counter(replace=103, retain=80))
        changed = {w for values in self.rows.values() for w, row in values.items() if row['action'] == 'replace'}
        self.assertEqual(len(changed), 89)
        self.assertEqual(self.review['summary']['retained_unique_words'], 69)
        for stage, values in self.rows.items():
            self.assertEqual(builder.review_scope_digest(values), builder.REVIEW_SCOPE_HASHES[stage])
            for word, row in values.items():
                self.assertEqual(row['action'], 'retain' if row['meaning'] == row['old_meaning'] else 'replace')

    def test_every_old_meaning_matches_unchanged_legacy_algorithm(self):
        for stage, values in self.rows.items():
            for word, row in values.items():
                self.assertEqual(row['old_meaning'], self.legacy[stage][word]['meaning'], (stage, word))
                self.assertEqual(self.legacy[stage][word]['provenance']['rule'], 'general_first_sense_fallback')

    def test_all_5302_outside_rows_are_identical_to_legacy(self):
        count = 0
        for stage, values in self.data['levels'].items():
            for word, row in values.items():
                if word not in self.rows[stage]:
                    self.assertEqual(row, self.legacy[stage][word], (stage, word))
                    count += 1
        self.assertEqual(count, 5302)

    def test_773_phrases_remain_outside_word_review(self):
        book = next(row for row in self.phrase_books['items'] if row['id'] == 'zk-phrases')
        self.assertEqual(len(book['words']), 773)
        self.assertTrue(set(book['words']).isdisjoint(self.rows['middleschool']))
        for word in book['words']:
            self.assertEqual(self.data['levels']['middleschool'][word], self.legacy['middleschool'][word])
        self.assertEqual(self.data['stats']['middleschool']['rules']['general_first_sense_fallback'], 773)
        self.assertNotIn('general_first_sense_fallback', self.data['stats']['primary']['rules'])

    def test_every_correction_has_honest_review_provenance(self):
        source = builder.relpath(builder.REVIEW_PATH)
        self.assertEqual(len(self.data['sources']), 55)
        self.assertEqual(self.data['sources'][source], builder.source_record(builder.REVIEW_PATH))
        for stage, values in self.rows.items():
            for word, reviewed in values.items():
                out = self.data['levels'][stage][word]
                self.assertEqual(out['meaning'], reviewed['meaning'])
                self.assertEqual(out['provenance']['source'], source)
                self.assertEqual(out['provenance']['sources'], [source])
                self.assertEqual(out['provenance']['rule'], builder.REVIEW_RULE)
                self.assertEqual(out['provenance']['category'], reviewed['category'])
                self.assertEqual(out['provenance']['review_word'], word)
                self.assertEqual(out['provenance']['review_stage'], stage)
                self.assertTrue(reviewed['references'] and reviewed['reason'] and reviewed['context_books'])
        self.assertEqual(self.data['review_required'], {'primary': [], 'middleschool': []})

    def test_named_collisions_are_real_names_not_technical_or_slang(self):
        for stage in builder.STAGES:
            for word, name in {'alice': '爱丽丝', 'matt': '马特', 'sam': '萨姆',
                               'ben': '本', 'peter': '彼得', 'tom': '汤姆',
                               'sally': '萨莉', 'nick': '尼克', 'sue': '苏'}.items():
                row = self.rows[stage][word]
                self.assertTrue(row['meaning'].startswith('n.'))
                self.assertIn(name, row['meaning'])
                self.assertIn(row['category'], ('personal_name', 'person_name'))
                self.assertEqual(row['headword'], word.capitalize())
        for word, expected in {'john': '约翰', 'mike': '迈克', 'sato': '佐藤', 'ruby': '鲁比',
                               'steen': '斯蒂恩', 'griffin': '格里芬', 'hayes': '海斯'}.items():
            self.assertIn(expected, self.rows['middleschool'][word]['meaning'])
        for values in self.rows.values():
            for row in values.values():
                if row['category'] in ('personal_name', 'person_name', 'surname'):
                    self.assertNotRegex(row['meaning'], r'接口|帐户|账户|监狱|厕所|暗淡|无光泽|偷懒|〈|\[计\]')

    def test_common_words_abbreviations_and_holidays_are_not_guessed(self):
        expected = {'app': '应用程序', 'word': '单词', 'thanksgiving': '感恩节', 'august': '八月', 'ms': '女士'}
        for stage in builder.STAGES:
            for word, text in expected.items():
                self.assertIn(text, self.rows[stage][word]['meaning'])
        self.assertIn('北斗卫星导航系统', self.rows['primary']['bds']['meaning'])
        self.assertIn('呃', self.rows['primary']['er']['meaning'])
        self.assertIn('here is', self.rows['primary']["here's"]['meaning'])
        self.assertIn('它们', self.rows['primary']["they're"]['meaning'])
        self.assertIn('第一人称单数', self.rows['middleschool']['am']['meaning'])
        self.assertNotIn('上午', self.rows['middleschool']['am']['meaning'])
        self.assertIn('X射线', self.rows['middleschool']['x-ray']['meaning'])
        self.assertIn('世界自然基金会', self.rows['middleschool']['wwf']['meaning'])
        self.assertIn('铅笔芯', self.rows['middleschool']['hb']['meaning'])

    def test_shared_names_have_consistent_chinese_spellings(self):
        def core(text):
            return re.sub(r'（[^）]*）|\([^)]*\)', '', re.sub(r'^[a-z]+\.', '', text)).strip()
        for word in set(self.rows['primary']) & set(self.rows['middleschool']):
            p, m = self.rows['primary'][word], self.rows['middleschool'][word]
            if p['category'] in ('personal_name', 'person_name', 'place_name'):
                self.assertEqual(core(p['meaning']), core(m['meaning']).split('；')[0], word)

    def test_four_original_inputs_have_exact_normalized_audit_hashes(self):
        values = self.review['scope']['original_inputs_normalized_sha256']
        self.assertEqual(set(values), {'bank.json', 'books.json', 'phrases.json', 'phrase_books.json'})
        for name, expected in values.items():
            self.assertEqual(hashlib.sha256((ROOT / 'data' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest(), expected)

    def test_display_aliases_are_school_only_and_preserve_all_original_fields(self):
        before = deepcopy(self.bank)
        aliases = 0
        for stage, values in self.rows.items():
            for word, reviewed in values.items():
                original = self.bank[word]
                school = level_meanings.decorate(original, self.runtime[stage])
                self.assertEqual(meaning(school), reviewed['meaning'])
                self.assertEqual(word_caption(school), reviewed['headword'])
                for field, value in original.items():
                    self.assertEqual(school[field], value, (stage, word, field))
                if reviewed['headword'] != word:
                    self.assertTrue(school['_school_caption'])
                    aliases += 1
                self.assertEqual(level_meanings.decorate(original, {}), original)
        self.assertGreater(aliases, 100)
        self.assertEqual(self.bank, before)
        self.assertEqual(self.bank['alice']['s'], '应用语言接口转换与扩充')
        self.assertEqual(level_meanings.stage_for_main('highschool'), None)
        self.assertEqual(level_meanings.stage_for_main('university'), None)
        self.assertEqual(word_caption(self.bank['bund']), 'bund')
        self.assertEqual(word_caption(level_meanings.decorate(self.bank['bund'], self.runtime['primary'])), 'the Bund')

    def test_tampered_missing_duplicate_or_unsuitable_review_records_are_rejected(self):
        variants = []
        for field, value in [('status', 'pending'), ('meaning', 'English only'), ('meaning', 'n.俚语'),
                             ('meaning', 'n.名\n字'), ('meaning', 'n.名;字'), ('meaning', 'n.' + '长' * 65),
                             ('meaning', 'n.人名'), ('category', ''), ('context_books', []),
                             ('references', []), ('headword', ''), ('action', 'unknown')]:
            data = deepcopy(self.review)
            row = next(iter(data['entries'][0]['levels'].values()))
            row[field] = value
            if field == 'meaning' and value == 'n.人名':
                row['category'] = 'common_word'
            variants.append(data)
        data = deepcopy(self.review); data['entries'].pop(); variants.append(data)
        data = deepcopy(self.review); data['scope']['original_inputs_normalized_sha256']['bank.json'] = '0' * 64; variants.append(data)
        data = deepcopy(self.review); data['entries'][1]['w'] = data['entries'][0]['w']; variants.append(data)
        original_read = builder.read_json
        for index, data in enumerate(variants):
            with self.subTest(variant=index):
                with patch.object(builder, 'read_json', side_effect=lambda p, value=data: value if p == builder.REVIEW_PATH else original_read(p)):
                    with self.assertRaises(ValueError):
                        builder.read_school_reviews(self.bank)

    def test_loader_requires_valid_meaning_before_accepting_caption(self):
        self.assertEqual(level_meanings._normalise({'display_w': 'Alice'}), {})
        self.assertEqual(level_meanings._normalise({'meaning': '', 'display_w': 'Alice'}), {})
        for invalid in (None, 5, [], {}, ' '):
            value = level_meanings._normalise({'meaning': 'n.爱丽丝（人名）', 'display_w': invalid})
            self.assertNotIn('display_w', value)
        value = level_meanings._normalise({'meaning': 'n.外滩（上海地名）', 'display_w': 'the Bund'})
        self.assertEqual(value['display_w'], 'the Bund')
        self.assertEqual(value['display_s'], 'n.外滩（上海地名）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
