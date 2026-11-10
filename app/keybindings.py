# -*- coding: utf-8 -*-
"""V1.3.6 键盘映射：纯配置/事件匹配，不读写文件、不依赖主程序。

对外契约（Lead 集成用）：
  DEFAULT_BINDINGS
  normalize(raw=None) -> canonical dict | ValueError
  load_bindings(raw) -> canonical dict（失败整套 defaults）
  event_action(event, bindings, phase) -> action | None
  caption(binding) -> 键位提示
"""
from collections import OrderedDict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

DEFAULT_BINDINGS = OrderedDict((
    ("remember", "Enter"),
    ("forget", "Space"),
    ("choice1", "1"),
    ("choice2", "2"),
    ("choice3", "3"),
    ("choice4", "4"),
    ("unknown", "Space"),
    ("next", "Enter"),
))

BINDING_KEYS = tuple(DEFAULT_BINDINGS)
PHASES = ("brush", "choice", "back")
PHASE_ACTIONS = {
    "brush": ("remember", "forget"),
    "choice": ("choice1", "choice2", "choice3", "choice4", "unknown"),
    "back": ("next",),
}
CONFLICT_GROUPS = (
    ("remember", "forget"),
    ("choice1", "choice2", "choice3", "choice4", "unknown"),
)
# 同屏保留命令：Z 改判、Ctrl+Z 撤销、Esc/Tab、窗口/编辑危险组合。
RESERVED = frozenset((
    "Z", "Ctrl+Z", "Ctrl+Shift+Z",
    "Esc", "Tab", "Shift+Tab", "Ctrl+Tab",
    "Ctrl+W", "Ctrl+Q", "Alt+F4", "Alt+Tab",
    "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A",
    "Ctrl+S", "Ctrl+F", "Ctrl+N", "Ctrl+O", "Ctrl+P", "Ctrl+R", "Ctrl+Y",
))
_RESERVED_CI = frozenset(item.casefold() for item in RESERVED)
_CANON_CACHE = {}


def _canonical_binding(value):
    """单 stroke、PortableText 规范化；非法返回 ""。"""
    if isinstance(value, QKeySequence):
        sequence = QKeySequence(value)
    elif isinstance(value, str):
        sequence = QKeySequence.fromString(value.strip(), QKeySequence.PortableText)
    else:
        return ""
    if sequence.isEmpty() or sequence.count() != 1:
        return ""
    text = sequence.toString(QKeySequence.PortableText)
    return "Enter" if text == "Return" else text


def canonical_binding(value):
    """公开的单项规范化（invalid -> 空串）。"""
    text = _canonical_binding(value)
    return text


def _reason(text):
    return text


def normalize(raw=None):
    """返回完整 canonical 映射；缺失补默认，非法/冲突抛 ValueError（中文理由）。"""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("按键配置必须是对象")
    unknown = [key for key in raw if key not in BINDING_KEYS]
    if unknown:
        raise ValueError("未知按键动作：" + "、".join(str(x) for x in unknown))
    result = OrderedDict()
    for key in BINDING_KEYS:
        value = raw.get(key, DEFAULT_BINDINGS[key])
        canonical = _canonical_binding(value)
        if not canonical:
            raise ValueError("%s 的按键无效：%r" % (key, value))
        if canonical.casefold() in _RESERVED_CI:
            raise ValueError("%s 使用了系统/改判保留键：%s" % (key, canonical))
        result[key] = canonical
    for group in CONFLICT_GROUPS:
        seen = {}
        for key in group:
            folded = result[key].casefold()
            if folded in seen:
                raise ValueError("%s 与 %s 不能使用同一按键：%s" %
                                 (seen[folded], key, result[key]))
            seen[folded] = key
    return dict(result)


def load_bindings(raw):
    """安全加载：任何非法配置返回完整 defaults，不抛异常。"""
    try:
        return normalize(raw)
    except (ValueError, TypeError, RuntimeError):
        return normalize(None)


def _event_binding(event):
    try:
        if event.isAutoRepeat():
            return ""
        key = int(event.key())
        if key in (int(Qt.Key_Return), int(Qt.Key_Enter)):
            return "Enter"
        sequence = QKeySequence(key | int(event.modifiers()))
        if sequence.isEmpty() or sequence.count() != 1:
            return ""
        return sequence.toString(QKeySequence.PortableText)
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return ""


def event_action(event, bindings, phase):
    """phase: brush(正反面认识/不认识) / choice(4选项+不知道) / back(下一张)。

    自动重复、保留命令、非法 phase 或未命中均返回 None。
    """
    phase = str(phase or "").casefold()
    if phase not in PHASE_ACTIONS:
        return None
    try:
        mapping = bindings if isinstance(bindings, dict) else load_bindings(bindings)
        mapping = normalize(mapping)
    except (ValueError, TypeError, RuntimeError):
        mapping = normalize(None)
    pressed = _event_binding(event)
    if not pressed:
        return None
    for action in PHASE_ACTIONS[phase]:
        if mapping[action].casefold() == pressed.casefold():
            return action
    return None


_CAPTION = {
    "Space": "空格",
    "Return": "Enter",
    "Enter": "Enter",
    "Backspace": "退格",
    "Delete": "Del",
    "Insert": "Ins",
    "Escape": "Esc",
    "Esc": "Esc",
    "Tab": "Tab",
    "Up": "↑",
    "Down": "↓",
    "Left": "←",
    "Right": "→",
}


def caption(binding):
    """返回可读键提示；无法解析时返回原文本。"""
    canonical = _canonical_binding(binding)
    if not canonical:
        return str(binding or "")
    parts = canonical.split("+")
    parts[-1] = _CAPTION.get(parts[-1], parts[-1])
    return "+".join(parts)
