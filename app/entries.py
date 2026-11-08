# -*- coding: utf-8 -*-
"""词条展示与记忆分类：词和词组共用数据，不编造音标或词性。"""
import re

CATEGORIES = (("all", "全部"), ("mastered", "已掌握"),
              ("known", "认识"), ("unlearned", "待学习"))
POS_RE = re.compile(r"^(?:n|v|vt|vi|adj|adv|prep|conj|pron|det|art|num|aux|int|interj|abbr)\.")


def is_phrase(entry):
    return entry.get("type") == "phrase" or bool(re.search(r"\s", entry.get("w", "")))


def meaning(entry):
    text = (entry.get("s") or entry.get("raw") or "").strip()
    pos = entry.get("pos") or []
    if isinstance(pos, str):
        pos = [pos]
    if text and pos and not POS_RE.match(text):
        prefix = pos[0].strip()
        if prefix and prefix not in ("na.", "un."):
            text = prefix + " " + text
    return text


def pronunciation(entry):
    if is_phrase(entry):
        return ""
    ipa = (entry.get("ipa") or entry.get("ph_raw") or "").strip().strip("/")
    return "/%s/" % ipa if ipa else ""


def _count(value, default=0):
    """与 StudyQueue._count 一致：非法/缺失计数按 0，不抛异常。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return default


def memory_info(key, states, known=None):
    """返回 (分类, 真实记忆等级或None, 显示文字)。测试估计不是记忆等级。"""
    state = states.get(key) or {}
    status = state.get("st")
    try:
        level = max(0, min(10, int(state.get("lv", 0))))
    except (TypeError, ValueError):
        level = 0
    if status in ("mastered", "retired") or level >= 10:
        return "mastered", 10, "10 · 已掌握"
    if status == "known":
        return "known", None, "认识 · 旧版已会"
    if level > 0 and status != "new":
        return "known", level, "Lv %d · 认识" % level
    # 与 StudyQueue._has_answer 一致的实际作答证据：seen/lapse 合法计数 >0。
    # 用户实际答错/等待重现的新词不能被测试估计覆盖成「认识」。
    if state and (_count(state.get("seen")) or _count(state.get("lapse"))):
        return "unlearned", 0, "0 · 待学习"
    if key in (known or ()):
        return "known", None, "认识 · 测试估计"
    return "unlearned", 0, "0 · 待学习"
