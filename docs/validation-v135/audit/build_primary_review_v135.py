# -*- coding: utf-8 -*-
"""Materialize the primary teammate's frozen decisions without PS-specific APIs."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / '.vocab-ui-tests'
EVIDENCE = BASE / 'v135-primary-evidence'
INPUT = BASE / 'v135-audit-primary-input.json'
ORIGIN = 'afbc132aa0627a33108816924003f669ad01fdd146ef39d245722a4dac9c931c'

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, data):
    assert not path.exists(), 'Do not overwrite an existing review artifact: ' + str(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

before = digest(INPUT)
data = load(INPUT)
decisions = load(EVIDENCE / 'review-decisions.json')
sources = load(EVIDENCE / 'source-excerpts.json')
assert data['review_stage'] == 'primary' and data['origin_overlay_sha256'] == ORIGIN
original = {entry['w']: entry for entry in data['entries']}
chosen = {entry['w']: entry for entry in decisions['items']}
assert len(original) == len(chosen) == len(decisions['items']) == 47
assert set(original) == set(chosen)
refs = {entry['id']: entry for entry in sources['accepted_sources']}
items = []
contexts = []
for word, entry in original.items():
    decision = chosen[word]
    row = entry['stages']['primary']
    text = decision['meaning']
    assert re.search('[\u3400-\u9fff]', text) and len(text) <= 32 and ';' not in text and '；' not in text
    assert re.match(r'^(n|v|adj|abbr|int)\.', text)
    if decision['category'] == 'personal_name':
        assert re.search('（[人男女]名）', text)
    references = []
    for book in row['books']:
        references.append({'kind': 'local_context', 'title': book['book_name'] + '（' + book['book_id'] + '）',
                           'quote': ' / '.join(book['nearby_words']),
                           'note': '原民间词书中已冻结的邻近词序；不是课文全文或官方词表成员认证。'})
        for match in book['raw_gloss_case_matches']:
            references.append({'kind': 'local_gloss', 'title': book['book_name'] + ' 原gloss：' + match['key'],
                               'quote': match['row'].get('tr', ''),
                               'note': '仅为原gloss字段原文；英文等式不冒称新增中文的字面来源。'})
    references.append({'kind': 'local_bank', 'title': '原通用bank字段：' + word,
                       'quote': 's: ' + entry['bank'].get('s', '') + '\nraw: ' + entry['bank'].get('raw', ''),
                       'note': decision['bank_note']})
    references.append({'kind': decision['review_kind'], 'title': '小学逐词校订：' + decision['headword'],
                       'note': decision['review_note']})
    for source_id in decision['source_ids']:
        source = refs[source_id]
        references.append({key: value for key, value in source.items() if key != 'id'})
    items.append({'w': word, 'old_meaning': row['old_meaning'], 'meaning': text,
                  'category': decision['category'], 'action': 'retain' if text == row['old_meaning'] else 'replace',
                  'headword': decision['headword'], 'reason': decision['reason'],
                  'context_books': [book['book_id'] for book in row['books']],
                  'references': references, 'status': 'reviewed'})
    contexts.append({'w': word, 'bank': entry['bank'], 'old_meaning': row['old_meaning'], 'books': row['books']})
for row in items:
    assert all(ref.get('kind') and ref.get('title') and ref.get('note') for ref in row['references'])
assert before == digest(INPUT)
output = BASE / 'v135-primary-review.json'
context_output = EVIDENCE / 'context-snapshot.json'
validation_output = EVIDENCE / 'validation.json'
for target in (output, context_output, validation_output):
    assert not target.exists(), target
save(output, {'schema': 1, 'stage': 'primary', 'scope_origin_sha256': ORIGIN, 'items': items})
save(context_output, {'schema': 1, 'stage': 'primary', 'input_sha256': before,
                      'scope_origin_sha256': ORIGIN, 'items': contexts})
retained = [row['w'] for row in items if row['action'] == 'retain']
validation = {'schema': 1, 'stage': 'primary', 'passed': True, 'items': 47,
              'replace_count': 47 - len(retained), 'retain_count': len(retained), 'retained_words': retained,
              'input_sha256_before': before, 'input_sha256_after': digest(INPUT), 'output_sha256': digest(output),
              'scope_origin_sha256': ORIGIN, 'generator': 'Lead materialization of paused teammate decisions',
              'limitations': 'Evidence separates dictionary text, local context and editorial transliteration; no official wordlist audit.'}
save(validation_output, validation)
assert len(load(output)['items']) == 47
print(json.dumps(validation, ensure_ascii=False, indent=2))
