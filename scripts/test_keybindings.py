# -*- coding: utf-8 -*-
"""V1.3.6 keyboard bindings contract tests (pure config, no I/O)."""
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication
import keybindings as kb

app = QApplication.instance() or QApplication([])
out, fails = [], []


def check(ok, text):
    out.append(("  OK   " if ok else "  FAIL ") + text)
    if not ok:
        fails.append(text)


def raises(fn, text):
    try:
        fn()
    except ValueError:
        check(True, text)
    except Exception as error:  # noqa: BLE001
        check(False, text + "：异常类型 %r" % error)
    else:
        check(False, text + "：未抛 ValueError")


def event(key, modifiers=Qt.NoModifier, auto=False):
    return QKeyEvent(QEvent.KeyPress, key, modifiers, "", auto)


def action(key, modifiers=Qt.NoModifier, phase="brush", auto=False, bindings=None):
    return kb.event_action(event(key, modifiers, auto),
                           bindings if bindings is not None else kb.DEFAULT_BINDINGS,
                           phase)


def test_defaults():
    expected = {"remember": "Enter", "forget": "Space", "choice1": "1",
                "choice2": "2", "choice3": "3", "choice4": "4",
                "unknown": "Space", "next": "Enter"}
    check(kb.normalize() == expected, "默认映射为 Enter/空格/1..4")
    check(kb.normalize(None) is not kb.DEFAULT_BINDINGS,
          "normalize 返回独立映射")
    check(tuple(kb.DEFAULT_BINDINGS) == ("remember", "forget", "choice1", "choice2",
                                         "choice3", "choice4", "unknown", "next"),
          "DEFAULT_BINDINGS 键顺序/动作名精确")
    check(kb.caption("Space") == "空格" and kb.caption("1") == "1",
          "caption 空格/数字提示")
    check(kb.caption("Ctrl+Z") == "Ctrl+Z", "caption 组合键提示")


def test_normalize_and_invalid():
    check(kb.normalize({"remember": "a"})["remember"] == "A",
          "字母大小写归一")
    check(kb.normalize({"remember": "space", "forget": "1"})["remember"] == "Space",
          "Space 名称归一")
    check(kb.normalize({"remember": "Ctrl+k"})["remember"] == "Ctrl+K",
          "组合键 PortableText 归一")
    check(kb.normalize({"remember": "A", "next": "A"})["next"] == "A",
          "next 可复用答题键")
    check(kb.normalize({"remember": "Space", "forget": "1",
                        "choice1": "1"})["choice1"] == "1",
          "不同模式组可复用同一键")
    raises(lambda: kb.normalize({"unknown_action": "A"}), "未知动作拒绝")
    raises(lambda: kb.normalize({"remember": ""}), "空键拒绝")
    raises(lambda: kb.normalize({"remember": "Ctrl+K, Ctrl+C"}),
           "多 stroke 拒绝")
    raises(lambda: kb.normalize({"remember": "Ctrl"}), "纯修饰键拒绝")
    raises(lambda: kb.normalize({"remember": "Z"}), "Z 改判保留键拒绝")
    raises(lambda: kb.normalize({"remember": "ctrl+z"}),
           "Ctrl+Z 撤销保留键大小写归一后拒绝")
    raises(lambda: kb.normalize({"remember": "Esc"}), "Esc 保留键拒绝")
    raises(lambda: kb.normalize({"remember": "Tab"}), "Tab 保留键拒绝")
    raises(lambda: kb.normalize({"remember": "Ctrl+W"}), "窗口快捷键拒绝")
    raises(lambda: kb.normalize({"remember": "Ctrl+C"}), "编辑快捷键拒绝")
    raises(lambda: kb.normalize({"remember": "Space", "forget": "Space"}),
           "remember/forget 同键拒绝")
    raises(lambda: kb.normalize({"choice1": "2", "choice2": "2"}),
           "4 choice + unknown 组内重键拒绝")
    raises(lambda: kb.normalize({"choice4": "Space"}),
           "choice4 与 unknown 默认同键拒绝")
    raises(lambda: kb.normalize("not a mapping"), "非对象配置拒绝")


def test_safe_load():
    valid = kb.normalize({"remember": "A"})
    check(kb.load_bindings({"remember": "A"}) == valid,
          "load_bindings 保留有效配置")
    bad = {"remember": "Space", "forget": "Space"}
    check(kb.load_bindings(bad) == kb.normalize(None),
          "冲突配置整套安全回退默认")
    check(kb.load_bindings({"remember": "Ctrl+Z"}) == kb.normalize(None),
          "保留键配置整套安全回退默认")
    check(kb.load_bindings(None) == kb.normalize(None),
          "load_bindings(None) 默认")


def test_events():
    check(action(Qt.Key_Return, phase="brush") == "remember",
          "brush Enter -> remember")
    check(action(Qt.Key_Space, phase="brush") == "forget",
          "brush Space -> forget")
    check(action(Qt.Key_1, phase="choice") == "choice1",
          "choice 1 -> choice1（跨模式复用）")
    check(action(Qt.Key_Space, phase="choice") == "unknown",
          "choice Space -> unknown")
    check(action(Qt.Key_Return, phase="back") == "next",
          "back Enter -> next")
    check(action(Qt.Key_0, phase="brush") is None,
          "非当前 phase 动作不触发")
    check(action(Qt.Key_Space, phase="brush", auto=True) is None,
          "自动重复事件不评分")
    check(action(Qt.Key_Z, Qt.ControlModifier, phase="brush") is None,
          "Ctrl+Z 保留命令不触发动作")
    check(action(Qt.Key_Z, Qt.NoModifier, phase="choice") is None,
          "Z 改判保留命令不触发动作")
    check(action(Qt.Key_Escape, phase="brush") is None,
          "Esc 不触发动作")
    check(action(Qt.Key_Tab, phase="choice") is None,
          "Tab 不触发动作")
    check(action(Qt.Key_F1, phase="brush") is None,
          "未绑定键返回 None")
    check(kb.event_action(event(Qt.Key_Space), kb.DEFAULT_BINDINGS, "nope") is None,
          "非法 phase 返回 None")
    custom = kb.normalize({"remember": "a", "forget": "b",
                           "choice1": "1", "choice2": "2",
                           "choice3": "3", "choice4": "4",
                           "unknown": "0", "next": "Space"})
    check(kb.event_action(event(Qt.Key_A), custom, "brush") == "remember",
          "自定义小写 binding 匹配大写事件")
    check(kb.event_action(event(Qt.Key_K, Qt.ControlModifier), custom, "brush")
          is None, "未绑定组合键返回 None")
    combo = kb.normalize({"remember": "Ctrl+K"})
    check(kb.event_action(event(Qt.Key_K, Qt.ControlModifier), combo, "brush")
          == "remember", "自定义组合键匹配")
    check(kb.event_action(event(Qt.Key_K, Qt.ControlModifier | Qt.ShiftModifier),
                          combo, "brush") is None,
          "修饰键不完全一致不匹配")


def main():
    for fn in (test_defaults, test_normalize_and_invalid, test_safe_load,
               test_events):
        fn()
    out.append("")
    out.append("KEYBINDINGS_CHECKS %d; FAILS %d" % (len(out) - 2, len(fails)))
    print("\n".join(out))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
