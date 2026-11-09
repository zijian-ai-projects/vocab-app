# -*- coding: utf-8 -*-
"""Reconcile the two completed scoped reviews into one shipped V135 source."""
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'vocab-app'
DATA = APP / 'data'
BASE = ROOT / '.vocab-ui-tests'

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

scope = load(BASE / 'v135-audit-scope.json')
origin = scope['origin_overlay_sha256']
files = {'primary': BASE / 'v135-primary-review.json', 'middleschool': BASE / 'v135-middle-review.json'}
reviews = {}
for stage, path in files.items():
    payload = load(path)
    assert payload['stage'] == stage and payload['scope_origin_sha256'] == origin
    rows = {row['w']: row for row in payload['items']}
    expected = {row['w']: row['stages'][stage] for row in scope['entries'] if stage in row['stages']}
    assert len(rows) == len(payload['items']) == len(expected)
    assert set(rows) == set(expected)
    for word, row in rows.items():
        assert row['status'] == 'reviewed'
        assert row['old_meaning'] == expected[word]['old_meaning']
        assert row['action'] == ('retain' if row['meaning'] == row['old_meaning'] else 'replace')
        assert row['context_books'] == [book['book_id'] for book in expected[word]['books']]
        assert row['references'] and row['reason'] and row['headword']
    reviews[stage] = rows
assert len(reviews['primary']) == 47 and len(reviews['middleschool']) == 136
assert len(set(reviews['primary']) & set(reviews['middleschool'])) == 25
for name, original in scope['original_inputs_raw_sha256'].items():
    assert digest(DATA / name) == original, 'Original source changed: ' + name
entries = []
for frozen in scope['entries']:
    word = frozen['w']
    levels = {}
    for stage in ('primary', 'middleschool'):
        if word in reviews[stage]:
            row = deepcopy(reviews[stage][word])
            row.pop('w')
            # This was an AI-assisted editorial review, not human-expert certification.
            for ref in row['references']:
                if ref.get('kind') == 'editorial_transliteration':
                    ref['title'] = ref['title'].replace('人工校订', '逐词编辑校订')
                if word == 'alice' and ref.get('kind') == 'user_instruction':
                    ref['quote'] = 'Alice在小学中明显是人名爱丽丝'
            levels[stage] = row
    entries.append({'w': word, 'levels': levels})
assert len(entries) == 158
summary = {stage: dict(Counter(row['action'] for row in values.values())) for stage, values in reviews.items()}
changed = sorted({word for values in reviews.values() for word, row in values.items() if row['action'] == 'replace'})
unchanged = sorted({row['w'] for row in entries} - set(changed))
payload = {
    'schema': 1, 'version': '1.3.5',
    'description': '固定158词的逐词适龄释义校订表；依据原词书上下文、已有中文、用户确认与列出的补充材料，不改原词库或成员。',
    'review_method': 'AI-assisted wordwise contextual/evidence review by two scoped reviewers, reconciled by Lead; not an official wordlist audit or human-expert certification.',
    'source_classification': 'community_compilation_and_editorial_corrections',
    'scope': {
        'origin_version': '1.3.4', 'origin_overlay_sha256': origin,
        'rule': 'general_first_sense_fallback words in the original primary/middleschool layer; excludes 773 phrase entries',
        'unique_words': 158, 'stage_items': 183, 'stage_counts': {'primary': 47, 'middleschool': 136},
        'overlap_words': 25,
        'original_inputs_raw_sha256': scope['original_inputs_raw_sha256'],
        'original_inputs_normalized_sha256': {name: hashlib.sha256((DATA / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                             for name in scope['original_inputs_raw_sha256']},
        'completed_review_sha256': {stage: digest(path) for stage, path in files.items()},
    },
    'summary': {'stage_decisions': summary, 'replace_stage_items': sum(values.get('replace', 0) for values in summary.values()),
                'retain_stage_items': sum(values.get('retain', 0) for values in summary.values()),
                'changed_unique_words': len(changed), 'retained_unique_words': len(unchanged)},
    'limitations': [
        '158是固定来源回退池，不代表158个错误；retain保留经逐项检查已合适的原短义。replace也包括补词性/身份说明，不等于每项旧译全错。',
        '人名用法据原词书连续人物段及所列材料复核；无完整人物课文者不推断具体角色或性别。原中文缺失/异译明确为编辑译写，不冒称历史gloss原文。',
        '外部教材片段、字典、机构介绍只作本词含义旁证，不做任何官方词表成员或完整性审计。',
        '本表仅小学47项与初中136项；未逐词认证其它学校成员或773词组，也不改变高中/通用词汇量测验释义。',
    ],
    'entries': entries,
}
output = DATA / 'school_meaning_reviews.json'
assert not output.exists(), 'Refuse to overwrite a shipped review without reading it'
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('V135_REVIEW_MERGED', json.dumps(payload['summary'], ensure_ascii=False), 'sha256', digest(output))
print('UNCHANGED_UNIQUE', ' '.join(unchanged))
