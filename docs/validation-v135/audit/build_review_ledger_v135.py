# -*- coding: utf-8 -*-
"""Create the complete 158-word public decision ledger from the shipped source."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'vocab-app'
source = ROOT / 'data' / 'school_meaning_reviews.json'
blob = source.read_text(encoding='utf-8')
data = json.loads(blob)
positions = {}
for index, line in enumerate(blob.splitlines(), 1):
    match = re.match(r'^\s*"w":\s*(".*"),$', line)
    if match:
        word = json.loads(match.group(1))
        assert word not in positions
        positions[word] = index
assert len(positions) == len(data['entries']) == 158


def cell(text):
    return text.replace('|', '&#124;').replace('\n', '<br>')


def stage_text(row):
    if not row:
        return '—'
    if row['action'] == 'retain':
        return cell(row['old_meaning']) + '（保留）'
    return cell(row['old_meaning']) + ' → **' + cell(row['meaning']) + '**'

lines = [
    '# V1.3.5 · 158词逐词释义对照', '',
    '本台账逐项列出固定审核池的稳定key、原短义、新短义和判定理由；完整字段与可携带短引用见 [已散列校订源](<../data/school_meaning_reviews.json>)。学校卡片、目录和学习四选项读取 [显示覆盖](<../data/level_meanings.json>)。', '',
    '## 结果与范围', '',
    '| 口径 | 小学 | 初中 | 合计 |', '|---|---:|---:|---:|',
    '| 已逐项审核 | 47 | 136 | 183学段项 / 158词 |',
    '| 新短义不同（replace） | 39 | 64 | 103学段项 |',
    '| 原短义保留（retain） | 8 | 72 | 80学段项 |', '',
    '**按不同词计：89词至少一个学段短义变化；69词在所属全部学段保留原短义。** 158是原V1.3.4来源规则回退池，不是158个已证明错误；replace包括补词性/身份、修复残缺、补完整常用义或必要译写，不等于每条原译全错。25个共享词的人名/地名中文字面一致，姓名括注/义组可按学段不同；DVD的“数字化视频光盘/数字视频光盘”同义。', '',
    '未改原34,963 bank key、书籍ID、成员或顺序，不重置进度、排期、历史。其它5,302学段行（包含773初中词组）值与原来源元数据完全不变；773词组不属于本次逐词审核。高中/通用词汇量测量继续使用原通用义。', '',
    '## 证据说明', '',
    '- 原bank中文字、原词书成员位置/邻词、已有gloss和外部短引用分开保存。人物段支持名字用法，不冒称完整教材人物全文；无人物依据不推断具体角色或性别。',
    '- 新译写/词性/标签明确是编辑校订；不能把新译名伪装为旧gloss原文。历史本地引用附原路径、SHA和行范围并嵌入校订源，外部字典/教材/机构材料只作含义旁证，不是官方词表审计。',
    '- 全部词表仍由民间整理。审核是限定范围的AI逐词审查与Lead合并/交叉核验，不等同于人类专家或出版机构认证，也不保证范围外全部语义。',
    '- “—”表示该词不在本次该学段47/136集合，不能据此认定该学段没收录。保留释义时仍可规范仅显示的大小写；稳定key保持原文。', '',
    '## 全部158词', '',
    '| # | 稳定key / 显示词形 | 小学：旧 → 新 | 初中：旧 → 新 | 逐词判定与记录 |',
    '|---:|---|---|---|---|',
]
for number, entry in enumerate(data['entries'], 1):
    word, values = entry['w'], entry['levels']
    headwords = list(dict.fromkeys(row['headword'] for row in values.values()))
    key = '`' + word + '`'
    if any(value != word for value in headwords):
        key += ' / ' + ', '.join(headwords)
    reasons = []
    for stage, label in (('primary', '小学'), ('middleschool', '初中')):
        if stage in values:
            reasons.append(label + '：' + values[stage]['reason'])
    link = '[逐词记录](<../data/school_meaning_reviews.json#L%d>)' % positions[word]
    lines.append('| %d | %s | %s | %s | %s<br>%s |' % (
        number, key, stage_text(values.get('primary')), stage_text(values.get('middleschool')),
        cell('<br>'.join(reasons)), link))
lines.extend(['', '## 使用与验证', '',
              '生成器严格固定158/183集合和四原始输入指纹；只有明确 `--write` 才生成覆盖。校订行的来源指向本校订表，未校订行仍按原片段回查。完整实现说明和回归命令见 [覆盖层说明](<level-meanings.md>)；本轮独立隔离/原生验收见 [V1.3.5验收记录](<acceptance-v135.md>)。', ''])
output = ROOT / 'docs' / 'school-meanings-review-v135.md'
assert not output.exists(), 'Do not overwrite an unread published ledger'
output.write_text('\n'.join(lines), encoding='utf-8')
print('V135_LEDGER_WRITTEN', len(data['entries']), 'words', len(lines), 'lines')
