# -*- coding: utf-8 -*-
"""Freeze V134's 158 word fallbacks and original local context for V135 review."""
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
PROJECT = WORK / 'vocab-app'
DATA = PROJECT / 'data'
OUT = WORK / '.vocab-ui-tests'
EXPECTED = 'afbc132aa0627a33108816924003f669ad01fdd146ef39d245722a4dac9c931c'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


payload = DATA / 'level_meanings.json'
assert sha(payload) == EXPECTED, 'V134 origin changed; do not freeze another scope'
overlay = load(payload)
bank = {row['w']: row for row in load(DATA / 'bank.json')}
books = load(DATA / 'books.json')
scopes = {
    stage: {word: row for word, row in mapping.items()
            if word in bank and row['provenance']['rule'] == 'general_first_sense_fallback'}
    for stage, mapping in overlay['levels'].items()
}
assert len(scopes['primary']) == 47 and len(scopes['middleschool']) == 136
words = sorted(set().union(*(set(mapping) for mapping in scopes.values())))
assert len(words) == 158 and {'alice', 'matt', 'bds'} <= set(words)
contexts = {stage: {word: [] for word in mapping} for stage, mapping in scopes.items()}
for main in books['mains']:
    stage = main['id']
    if stage not in scopes:
        continue
    for group in main['groups']:
        for book in group['items']:
            members = book['words']
            positions = {word: index for index, word in enumerate(members)}
            gloss_path = DATA / 'school_gloss' / (book['id'] + '.json')
            gloss = load(gloss_path) if gloss_path.is_file() else {}
            for word in set(members) & set(scopes[stage]):
                index = positions[word]
                raw_gloss = [{'key': key, 'row': value}
                             for key, value in gloss.items() if key.casefold() == word.casefold()]
                contexts[stage][word].append({
                    'book_id': book['id'], 'book_name': book.get('name', ''),
                    'group_id': group['id'], 'group_name': group.get('name', ''),
                    'kind': book.get('kind', ''), 'series': book.get('series', ''),
                    'word_index': index,
                    'nearby_words': members[max(0, index - 4):index + 5],
                    'raw_gloss_case_matches': raw_gloss,
                })
entries = []
for word in words:
    entries.append({
        'w': word, 'bank': bank[word],
        'stages': {stage: {'old_meaning': mapping[word]['meaning'],
                           'old_provenance': mapping[word]['provenance'],
                           'books': contexts[stage][word]}
                   for stage, mapping in scopes.items() if word in mapping},
    })
origin = {
    'schema': 1, 'version': '1.3.5', 'origin_version': '1.3.4',
    'origin_overlay_sha256': EXPECTED,
    'unique_words': 158, 'stage_counts': {'primary': 47, 'middleschool': 136},
    'stage_items': 183, 'wordlist_policy': 'community_compilation',
    'original_inputs_raw_sha256': {name: sha(DATA / name) for name in
                                  ('bank.json', 'books.json', 'phrases.json', 'phrase_books.json')},
    'entries': entries,
}
targets = [(OUT / 'v135-audit-scope.json', origin)]
for stage in scopes:
    subset = dict(origin)
    subset['review_stage'] = stage
    subset['entries'] = [entry for entry in entries if stage in entry['stages']]
    targets.append((OUT / ('v135-audit-' + stage + '-input.json'), subset))
for path, _ in targets:
    assert not path.exists(), path
for path, data in targets:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('FROZEN_V135_SCOPE', len(words), 'primary', len(scopes['primary']), 'middle', len(scopes['middleschool']))
for word in ('alice', 'matt', 'bds', 'ben', 'bill', 'sam', 'mark', 'ms', 'tom', 'bund', 'steen'):
    entry = next((entry for entry in entries if entry['w'] == word), None)
    if entry:
        print('CONTEXT', word, json.dumps(entry['stages'], ensure_ascii=False))
