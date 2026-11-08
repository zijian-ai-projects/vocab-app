# -*- coding: utf-8 -*-
"""学习用四选一：四个真实释义、一个正确答案，没有测试陷阱或功能按钮。

大量词条请复用 OptionPool(entries)。构造只冻结词条顺序，首次出题才预解析；
以后只抽样少量已缓存释义，不在每题遍历全库、解析正则或洗牌万词列表。
词库释义发生变化时应新建池；当题的 entry 改变则仍使用其最新真实释义。
"""
from collections import namedtuple
import random
import re

try:
    from .entries import meaning
except ImportError:
    from entries import meaning


_POS_RE = re.compile(r"\b[a-z]{1,7}\.\s*", re.IGNORECASE)
_SPLIT_RE = re.compile(r"[；;，,\n\r、/]|\\n")
_RESERVED = frozenset(("没有正确答案", "不认识"))
_Parsed = namedtuple("_Parsed", "key text senses")
_Choice = namedtuple("_Choice", "text senses keys")
_SAMPLE_SIZE = 12


def _senses(text):
    """只用于比较的义项规范化；展示文本仍完整取自真实词条。"""
    # 原始释义可能保存字面量 \\n；先转换，避免把 \\nvt. 误识别为 nvt. 词性。
    text = _POS_RE.sub("", text.replace("\\n", "\n").casefold())
    return frozenset(normalized for part in _SPLIT_RE.split(text)
                     for normalized in [" ".join(part.split()).strip(" .。!?？！:：")]
                     if normalized)


def _signature(entry):
    pos = entry.get("pos") or ()
    first_pos = pos if isinstance(pos, str) else (pos[0] if pos else None)
    return entry.get("w"), entry.get("s"), entry.get("raw"), first_pos


def _usable(parsed):
    return bool(parsed.text and parsed.senses and parsed.senses.isdisjoint(_RESERVED))


class OptionPool:
    """惰性的真实释义池，兼容 make_options(entry, pool, rng=None)。

    可提前 prepare()，也可在首题自动准备。prepared 和 len(pool) 可读，
    len 返回原词条数且不触发解析。规范义项相同的释义只保留一个真实展示
    文本，记录所有来源词 key；空释义及「没有正确答案/不认识」均不入池。
    """

    def __init__(self, entries):
        self.entries = tuple(entries)
        self._choices = None
        self._by_id = {}
        self._sense_cache = {}

    def __len__(self):
        return len(self.entries)

    @property
    def prepared(self):
        return self._choices is not None

    def _parse(self, entry):
        text = meaning(entry)
        if text not in self._sense_cache:
            self._sense_cache[text] = _senses(text)
        return _Parsed(entry.get("w"), text, self._sense_cache[text])

    def prepare(self):
        """每池只预解析一次；返回 self，方便显式预热/性能测量。"""
        if self.prepared:
            return self
        groups, by_id = {}, {}
        for entry in self.entries:
            parsed = self._parse(entry)
            by_id[id(entry)] = (_signature(entry), parsed)
            if not _usable(parsed):
                continue
            if parsed.senses not in groups:
                groups[parsed.senses] = [parsed.text, set()]
            groups[parsed.senses][1].add(parsed.key)
        self._by_id = by_id
        self._choices = tuple(_Choice(text, senses, frozenset(keys))
                              for senses, (text, keys) in groups.items())
        return self

    def _target(self, entry):
        self.prepare()
        signature = _signature(entry)
        cached = self._by_id.get(id(entry))
        if cached is not None and cached[0] == signature:
            return cached[1]
        parsed = self._parse(entry)
        if cached is not None:
            # 只刷新当题 entry；完整词库变更需重新构池，不能逐题全库检查。
            self._by_id[id(entry)] = (signature, parsed)
        return parsed

    @staticmethod
    def _eligible(choice, target):
        return (choice.text != target.text
                and (target.key is None or target.key not in choice.keys)
                and choice.senses.isdisjoint(target.senses))

    def _distractors(self, target, rng):
        count = len(self._choices)
        if count < 3:
            raise ValueError("需要至少三个不同的其它释义")

        sampler = getattr(rng, "sample", None)
        if callable(sampler):
            indices = sampler(range(count), min(count, _SAMPLE_SIZE))
        else:
            # 旧 API 只要求 shuffle；兼容这种固定测试 RNG，也只洗牌小批索引。
            indices = list(range(min(count, _SAMPLE_SIZE)))
            rng.shuffle(indices)
        candidates = []
        for idx in indices:
            choice = self._choices[idx]
            if self._eligible(choice, target):
                candidates.append(choice.text)
                if len(candidates) == 3:
                    return candidates

        # 很小/大量同义的池可能抽样不足；只扫已解析缓存，绝不回退同义
        # 「正确」干扰项。调用方可在 ValueError 时用更大的真实词池重试。
        sampled = set(indices)
        for idx, choice in enumerate(self._choices):
            if idx not in sampled and self._eligible(choice, target):
                candidates.append(choice.text)
                if len(candidates) == 3:
                    return candidates
        raise ValueError("需要至少三个不同且不与正确义项重复的其它释义")


def make_options(entry, pool, rng=None):
    """返回 {options: 四个真实释义, correct: 0..3}，不认识由 UI 的第五项提供。

    list/其它 iterable 保持兼容，会临时构池；每题复用 OptionPool 才是
    大词库性能路径。传入 random.Random 或 random 模块均可固定随机结果。
    """
    rng = random.Random() if rng is None else rng
    pool = pool if isinstance(pool, OptionPool) else OptionPool(pool)
    target = pool._target(entry)
    if not _usable(target):
        raise ValueError("词条缺少可用真实释义，不能生成学习选择题")
    options = pool._distractors(target, rng) + [target.text]
    rng.shuffle(options)
    return {"options": options, "correct": options.index(target.text)}
