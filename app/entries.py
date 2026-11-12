# -*- coding: utf-8 -*-
"""词条展示与记忆分类：词和词组共用数据，不编造音标或词性。"""
import re

CATEGORIES = (("all", "全部"), ("learned", "已学习"),
              ("unlearned", "待学习"))
POS_RE = re.compile(r"^(?:n|v|vt|vi|adj|adv|prep|conj|pron|det|art|num|aux|int|interj|abbr)\.")


def word_caption(entry):
    """显示拼写与稳定记忆 key 分离（如显示 I，而学习 key 仍是 i）。"""
    value = entry.get("display_w")
    return value if isinstance(value, str) and value.strip() else entry["w"]


def is_phrase(entry):
    return entry.get("type") == "phrase" or bool(re.search(r"\s", entry.get("w", "")))


def meaning(entry):
    # 学段覆盖：display_s / level_s 优先；空串/非字符串一律回退通用 s/raw。
    text = ""
    for field in ("display_s", "level_s"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            break
    if not text:
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
    # 仅采用已有且完整的音标；反斜杠是源库转义损坏，不能删掉后
    # 把残缺音节冒充为正确读音。ipa 不可用时再试已有的 ph_raw。
    for field in ("ipa", "ph_raw"):
        value = entry.get(field)
        if not isinstance(value, str):
            continue
        ipa = value.strip().strip("/").strip()
        if not ipa or "\\" in ipa or any(ord(char) < 32 for char in ipa):
            continue
        if ipa.casefold() in ("n/a", "not available", "无", "暂无", "暂无音标"):
            continue
        if not any(char.isalpha() and char not in "ˈˌːˑ" for char in ipa):
            continue
        return "/%s/" % ipa
    return ""


def _count(value, default=0):
    """与 StudyQueue._count 一致：非法/缺失计数按 0，不抛异常。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return default


def memory_info(key, states, known=None, predicted=None):
    """返回 (分类, 真实等级或None, 标签)；预测永不伪造真实等级。"""
    state = states.get(key) or {}
    status = state.get("st")
    try:
        level = max(0, min(10, int(state.get("lv", 0))))
    except (TypeError, ValueError):
        level = 0
    if status in ("mastered", "retired") or level >= 10:
        return "mastered", 10, "Lv10 · 已掌握"
    if status == "known":
        return "known", None, "认识 · 旧版已会"
    if level > 0 and status != "new":
        return "known", level, "Lv%d · 认识" % level
    # Actual answer evidence and explicit states outrank all estimates.
    if state and (_count(state.get("seen")) or _count(state.get("lapse"))):
        return "unlearned", 0, "待学习"
    if state:
        return "unlearned", 0, "待学习"
    if key in (known or ()):
        return "known", None, "认识 · 测试估计"
    if key in (predicted or ()):
        return "predicted", None, "预测 · 已掌握"
    return "unlearned", 0, "待学习"
