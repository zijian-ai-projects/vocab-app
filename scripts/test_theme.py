# -*- coding: utf-8 -*-
r"""V1.3.3 四主题回归：正文/可用按钮对比度、独立文字、状态与 dock API。

运行：D:\software\anaconda\python.exe -B scripts\test_theme.py
仅 offscreen + Sandbox；报告/四主题预览写 .vocab-ui-tests，不写真实记录或 data。
装饰边线、网格、禁用 wrong_dis 不属于 4.5:1 正文/可用按钮检查。
"""
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(APP, "app")]

from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

os.environ["QT_QPA_PLATFORM"] = "offscreen"
configure_qt("offscreen")
_font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
if os.name == "nt" and os.path.isdir(_font_dir):
    os.environ.setdefault("QT_QPA_FONTDIR", _font_dir)
set_nottest(True)

from PyQt5.QtCore import Qt, QT_VERSION_STR, PYQT_VERSION_STR
from PyQt5.QtGui import QColor, QPalette, QImage, QPainter
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
                             QStyle, QStyleOptionButton)
import theme as th

app = new_app(sys.argv)
out, fails = [], []
MIN_CONTRAST = 4.5
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
DOCK_KEYS = ("dock_bg", "dock_border", "dock_fg", "dock_hover")

# 穷举 QSS/label_qss 的可用文字状态；同一文字若用于不同背景，则分别检查。
TEXT_PAIRS = (
    ("fg_word", "bg"), ("fg_ipa", "bg"), ("fg_mean", "bg"),
    ("fg_empty", "bg"), ("fg_sub", "bg"), ("muted", "bg"),
    ("bar", "bg"), ("bar_hover", "bar_hover_bg"), ("bar_hover", "bg"),
    ("btn_fg", "btn_bg"), ("btn_fg", "btn_hover"), ("btn_fg", "btn_pressed"),
    ("rem_fg", "rem_bg"), ("rem_fg", "rem_hover"),
    ("fgt_fg", "fgt_bg"), ("fgt_fg", "fgt_hover"),
    ("wrong_fg", "bg"), ("fg_mean", "btn_bg"),
    ("link", "bg"), ("close", "bg"), ("close_hover", "bg"),
    ("opt_fg", "opt_bg"), ("opt_fg", "opt_hover"),
    ("opt_ok_fg", "opt_ok_bg"), ("opt_bad_fg", "opt_bad_bg"),
    ("dk_fg", "dk_bg"), ("dk_fg", "dk_hover"), ("dk_pick_fg", "dk_pick"),
    ("chip_fg", "chip_bg"), ("fg_word", "chip_bg"), ("fg_word", "chip_hover"),
    ("chip_sel_fg", "chip_sel"), ("fg_mean", "chip_bg"),
    ("fg_mean", "opt_bg"),
    ("chart_text", "chart_bg"), ("chart_date", "chart_bg"),
    ("chart_line", "chart_bg"), ("ok", "bg"), ("accent", "bg"),
    ("dock_fg", "dock_bg"), ("dock_fg", "dock_hover"),
)


def check(condition, message):
    out.append(("  OK   " if condition else "  FAIL ") + message)
    if not condition:
        fails.append(message)


def pump(seconds=0.0):
    end = time.monotonic() + seconds
    for _ in range(8):
        app.processEvents()
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
    for _ in range(8):
        app.processEvents()


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def luminance(color):
    channels = [channel / 255.0 for channel in rgb(color)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
              for v in channels]
    return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear))


def contrast(foreground, background):
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def button_fill(button, state=QStyle.State_None):
    """通过真实 QStyle/QSS 强制绘制 hover/pressed，避免依赖原生鼠标位置。"""
    image = QImage(button.size(), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    option = QStyleOptionButton()
    option.initFrom(button)
    option.rect = image.rect()
    option.text = ""
    clean_state = int(option.state) & ~int(
        QStyle.State_MouseOver | QStyle.State_Sunken | QStyle.State_HasFocus)
    option.state = QStyle.State(clean_state | int(QStyle.State_Enabled) | int(state))
    painter = QPainter(image)
    try:
        button.style().drawControl(QStyle.CE_PushButton, option, painter, button)
    finally:
        painter.end()
    return image.pixelColor(image.width() // 2, image.height() // 2)


def build_panel(theme_key, option_class):
    palette = th.get(theme_key)
    panel = QWidget()
    panel.setObjectName("theme_panel")
    panel.setStyleSheet(th.qss(palette) +
                       "QWidget#theme_panel{background:%s;border:1px solid %s;}" %
                       (palette["bg"], palette["border"]))
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(8)
    probes, fills = [], []

    for text, kind, size, key in (
            (th.NAMES[theme_key] + " · V1.3.3", "title", 17, "fg_word"),
            ("gentle / 柔和可读", "word", 25, "fg_word"),
            ("/ˈdʒentl/  independent controls", "ipa", 13, "fg_ipa"),
            ("低饱和纸面；控件、选中与状态各自搭配文字", "mean", 14, "fg_mean"),
            ("正文及可用按钮所有状态 ≥ 4.5:1", "note", 12, "muted")):
        label = QLabel(text, panel)
        label.setStyleSheet(th.label_qss(palette, kind, size))
        layout.addWidget(label)
        probes.append((label, QPalette.WindowText, key))

    buttons = QHBoxLayout()
    for text, name, fg, bg, hover in (
            ("继续学习", "", "btn_fg", "btn_bg", "btn_hover"),
            ("认识", "remember", "rem_fg", "rem_bg", "rem_hover"),
            ("不认识", "forget", "fgt_fg", "fgt_bg", "fgt_hover")):
        button = QPushButton(text, panel)
        button.setObjectName(name)
        buttons.addWidget(button)
        probes.append((button, QPalette.ButtonText, fg))
        fills.extend(((button, QStyle.State_None, bg),
                      (button, QStyle.State_MouseOver, hover)))
        if not name:
            fills.append((button, QStyle.State_Sunken, "btn_pressed"))
    layout.addLayout(buttons)

    chips = QHBoxLayout()
    for text, selected in (("待学习 12", False), ("认识 8 · 已选", True)):
        button = QPushButton(text, panel)
        button.setObjectName("chip")
        button.setProperty("on", "1" if selected else "0")
        chips.addWidget(button)
        probes.append((button, QPalette.ButtonText, "chip_sel_fg" if selected else "chip_fg"))
        fills.append((button, QStyle.State_MouseOver, "chip_sel" if selected else "chip_hover"))
    chips.addStretch(1)
    layout.addLayout(chips)

    for text, state, fg, bg in (
            ("A  正确 · 主题化反馈", "correct", "opt_ok_fg", "opt_ok_bg"),
            ("B  错误 · 文字仍清晰", "wrong", "opt_bad_fg", "opt_bad_bg")):
        button = option_class(panel)
        button.setObjectName("opt")
        button.setText(text)
        button.setProperty("state", state)
        layout.addWidget(button)
        probes.append((button, QPalette.ButtonText, fg))
        probes.append((button.content, QPalette.WindowText, fg))
        fills.append((button, QStyle.State_MouseOver, bg))

    unknown = QPushButton("不确定 · 已选择", panel)
    unknown.setObjectName("dontknow")
    unknown.setProperty("state", "picked")
    layout.addWidget(unknown)
    probes.append((unknown, QPalette.ButtonText, "dk_pick_fg"))
    fills.append((unknown, QStyle.State_MouseOver, "dk_pick"))

    fields = QHBoxLayout()
    edit = QLineEdit("搜索词条 / warm text", panel)
    combo = QComboBox(panel)
    combo.addItems(["控件选中跟随主题", "selected"])
    spin = QSpinBox(panel)
    spin.setValue(12)
    spin.setMaximumWidth(65)
    for widget in (edit, combo, spin):
        fields.addWidget(widget)
        probes.append((widget, QPalette.Text, "fg_mean"))
    probes.extend(((edit, QPalette.Highlight, "chip_sel"),
                   (edit, QPalette.HighlightedText, "chip_sel_fg"),
                   (combo.view(), QPalette.Text, "fg_mean"),
                   (combo.view(), QPalette.Highlight, "chip_sel"),
                   (combo.view(), QPalette.HighlightedText, "chip_sel_fg")))
    layout.addLayout(fields)
    layout.addStretch(1)
    return panel, probes, fills


def main():
    import main as app_main

    out.append("PYTHON %s QT %s PYQT %s PLATFORM %s" %
               (sys.version.split()[0], QT_VERSION_STR, PYQT_VERSION_STR,
                os.environ.get("QT_QPA_PLATFORM")))
    sb = Sandbox(app_main, "theme")
    gallery = None
    try:
        with sb:
            check(not th.missing(), "四主题 required keys 齐全：%r" % th.missing())
            check(set(th.ORDER) == {"light", "dark", "sepia", "green"}
                  and len(th.ORDER) == 4, "四主题名称/顺序 API 保持完整")
            check(th.DEFAULT == "light" and th.get("unknown") is th.get(th.DEFAULT),
                  "默认亮色与未知主题 fallback API 不变")
            check(th.options() == [(key, th.NAMES[key]) for key in th.ORDER],
                  "options() 保持主题名称 API")
            check(len(th.KEYS) == len(set(th.KEYS)), "required keys 无重复")
            check(all(key in th.KEYS for key in DOCK_KEYS + ("chip_fg",)),
                  "dock_* / chip_fg 纳入 required keys，不只是可选临时色")

            for theme_key in th.ORDER:
                palette = th.get(theme_key)
                check(set(palette) == set(th.KEYS), "%s key 集合与 KEYS 一致" % theme_key)
                check(all(HEX_COLOR.fullmatch(color) for color in palette.values()),
                      "%s 全部实色合法，避免父背景透明叠色影响对比度" % theme_key)
                values = []
                for fg, bg in TEXT_PAIRS:
                    ratio = contrast(palette[fg], palette[bg])
                    values.append((ratio, fg, bg))
                    check(ratio >= MIN_CONTRAST,
                          "%s %s/%s %.3f:1 >= %.1f" % (theme_key, fg, bg, ratio, MIN_CONTRAST))
                worst = min(values)
                out.append("SUMMARY %s body=%.3f button_worst=%.3f dock_worst=%.3f min=%.3f (%s/%s) pairs=%d" %
                           (theme_key, contrast(palette["fg_mean"], palette["bg"]),
                            min(contrast(palette["btn_fg"], palette[key])
                                for key in ("btn_bg", "btn_hover", "btn_pressed")),
                            min(contrast(palette["dock_fg"], palette[key])
                                for key in ("dock_bg", "dock_hover")),
                            worst[0], worst[1], worst[2], len(values)))
                surfaces = ("bg", "btn_bg", "btn_hover", "btn_pressed", "opt_bg",
                            "opt_hover", "chip_bg", "chip_hover", "dock_bg", "dock_hover")
                check(all(max(rgb(palette[key])) - min(rgb(palette[key])) <= 56 for key in surfaces),
                      "%s 主面板/控件 RGB 通道跨度 <=56，保持柔和灰调" % theme_key)
                check(palette["opt_ok_bg"] != palette["opt_bad_bg"]
                      and palette["opt_ok_fg"] != palette["opt_bad_fg"],
                      "%s 正确/错误状态保持协调但可区分" % theme_key)
                for scale in (1.0, 1.6):
                    css = th.qss(palette, scale)
                    check("%(" not in css and "color: %s;" % palette["chip_fg"] in css,
                          "%s/scale%.1f QSS 完整且 chip 使用独立 chip_fg" % (theme_key, scale))
                    check("selection-background-color: %s;" % palette["chip_sel"] in css
                          and "selection-color: %s;" % palette["chip_sel_fg"] in css,
                          "%s/scale%.1f 输入框/下拉选中颜色主题化" % (theme_key, scale))
                check(th.qss(palette, 0.8) == th.qss(palette, 1.0)
                      and th.qss(palette, 2.0) == th.qss(palette, 1.6),
                      "%s scale 仍限于 1.0-1.6" % theme_key)

            sepia = th.get("sepia")
            check(all(r >= g >= b for r, g, b in map(rgb, sepia.values())),
                  "米黄所有控件/文字/selected/正确/chart 都是暖褐琥珀，不含绿色")
            for key in ("btn_fg", "chip_fg", "chip_sel_fg", "dock_fg"):
                check(len({th.get(name)[key] for name in th.ORDER}) == 4,
                      "%s 四主题文字颜色互不复用" % key)
                check(all(rgb(th.get(name)[key])[2] >= rgb(th.get(name)[key])[1]
                          >= rgb(th.get(name)[key])[0] for name in ("light", "dark")),
                      "%s 亮色/暗色控件是独立柔和灰蓝" % key)
                r, g, b = rgb(th.get("green")[key])
                check(g >= r and g >= b, "%s 护眼绿控件为鼠尾草灰绿" % key)
            old_dark = luminance("#15171b")
            new_dark = luminance(th.get("dark")["bg"])
            check(new_dark > old_dark * 3 and new_dark < 0.10,
                  "暗色明显提亮但仍为中深灰蓝：L %.5f -> %.5f (%.2fx)" %
                  (old_dark, new_dark, new_dark / old_dark))
            check(luminance(th.get("green")["bg"]) > 0.6
                  and contrast(th.get("green")["fg_mean"], th.get("green")["bg"]) >= 7,
                  "护眼绿保持浅纸面/正文 >=7:1")

            gallery = QWidget()
            grid = QGridLayout(gallery)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(8)
            all_probes = []
            for position, theme_key in enumerate(th.ORDER):
                panel, probes, fills = build_panel(theme_key, app_main.WrappedOptionButton)
                grid.addWidget(panel, position // 2, position % 2)
                all_probes.append((theme_key, probes, fills))
            gallery.resize(1140, 960)
            gallery.show()
            pump(0.08)
            for theme_key, probes, fills in all_probes:
                palette = th.get(theme_key)
                for widget, role, key in probes:
                    widget.ensurePolished()
                    actual = widget.palette().color(role)
                    check(actual == QColor(palette[key]),
                          "%s 实际 Qt %s palette role%d -> %s (%s)" %
                          (theme_key, type(widget).__name__, role, key, actual.name()))
                for button, state, key in fills:
                    actual = button_fill(button, state)
                    check(actual == QColor(palette[key]),
                          "%s 实际 QStyle %s state%d 背景 -> %s (%s)" %
                          (theme_key, button.objectName() or "default", int(state), key, actual.name()))
            preview = sb.shot("theme_four_palette.png")
            check(gallery.grab().save(preview), "原生 Qt 四主题预览保存到隔离输出目录")
            out.append("PREVIEW " + preview)

            card = sb.new_card(progress={
                "welcome_done": True, "book_confirmed": True, "book": "cet4-dg",
                "theme": "light", "states": {}, "cursors": {}, "orders": {}, "history": [],
            }, show=True)
            for theme_key in th.ORDER:
                card.set_theme(theme_key)
                pump(0.03)
                palette = th.get(theme_key)
                check(card.t is palette and card.theme_key == theme_key,
                      "%s 实际 Card 消费主题，不是另一套 demo 配色" % theme_key)
                check(all(card.window_ctl.theme[key] == palette[key] for key in DOCK_KEYS),
                      "%s Card -> WindowController dock_* API 完整传递" % theme_key)
                check(card.btn_remember.palette().color(QPalette.ButtonText) == QColor(palette["rem_fg"])
                      and card.btn_forget.palette().color(QPalette.ButtonText) == QColor(palette["fgt_fg"])
                      and card.btn_next.palette().color(QPalette.ButtonText) == QColor(palette["btn_fg"]),
                      "%s 实际 Card 正常/认识/不认识按钮文字使用独立主题色" % theme_key)
                check(card.catalog.theme is palette and card.catalog.model.palette is palette,
                      "%s Card -> catalog 主题 API 保持同步" % theme_key)
                check(os.path.realpath(app_main.PROGRESS_PATH) == os.path.realpath(sb.progress_path)
                      and os.path.realpath(app_main.WIN_PATH) == os.path.realpath(sb.win_path),
                      "%s Card 进度/窗口保存始终隔离在 Sandbox" % theme_key)
            out.append("SOURCE theme=%s catalog=%s" %
                       (os.path.abspath(th.__file__),
                        os.path.abspath(sys.modules[app_main.BookCatalog.__module__].__file__)))
    except Exception:
        check(False, "theme 测试异常：\n" + traceback.format_exc())
    finally:
        if gallery is not None:
            gallery.close()
            gallery.deleteLater()
            pump()
    check(not sb.errors, "Sandbox 真实记录/备份指纹未变：%r" % sb.errors)
    out.append("FINGERPRINT protected=%d unchanged=%s" % (len(sb.watch_paths), not sb.errors))
    return sb.finish(out, fails, "test_theme.txt")


if __name__ == "__main__":
    sys.exit(main())
