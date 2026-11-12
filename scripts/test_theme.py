# -*- coding: utf-8 -*-
r"""V1.3.4 四主题回归：更清晰的 DK 填充、三处不认识一致性、原配色/API。

运行：D:\software\anaconda\python.exe -B scripts\test_theme.py
主程序尚在集成时：同命令追加 --palette-only（不构造 Card，明确延期三处实际控件验证）。
默认 offscreen + Sandbox；可显式设 VOCAB_TEST_PLATFORM=windows 做隔离原生截图。
报告/四主题与 DK 旧新版预览写 .vocab-ui-tests，不写真实记录或 data。
装饰边线、网格、禁用 wrong_dis 不属于 4.5:1 正文/可用按钮检查。
DK 填充:bg 的 >=1.5:1 是本次视觉分离目标，不是声称通过 WCAG 非文字 3:1。
"""
import hashlib
import json
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(APP, "app")]

from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

PALETTE_ONLY = "--palette-only" in sys.argv
_test_platform = os.environ.get("VOCAB_TEST_PLATFORM", "offscreen")
if _test_platform not in ("native", "default"):
    os.environ["QT_QPA_PLATFORM"] = _test_platform
configure_qt(None if _test_platform in ("native", "default") else _test_platform)
_font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
if os.name == "nt" and os.path.isdir(_font_dir):
    os.environ.setdefault("QT_QPA_FONTDIR", _font_dir)
set_nottest(True)

from PyQt5.QtCore import Qt, QSize, QT_VERSION_STR, PYQT_VERSION_STR
from PyQt5.QtGui import QColor, QPalette, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox,
                             QStyle, QStyleOptionButton)
import theme as th

app = new_app(sys.argv)
out, fails = [], []
MIN_CONTRAST = 4.5
MIN_DK_FILL_CONTRAST = 1.5
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
DOCK_KEYS = ("dock_bg", "dock_border", "dock_fg", "dock_hover")
DK_SURFACES = ("dk_bg", "dk_hover", "dk_pressed")
DK_CHANGED_KEYS = frozenset(DK_SURFACES + ("dk_fg",))
DK_PRESSED_RULE = "QPushButton#dontknow:pressed { background: %(dk_pressed)s; }\n"
DK_STATES = (
    ("normal", QStyle.State_None, "dk_bg"),
    ("hover", QStyle.State_MouseOver, "dk_hover"),
    ("pressed", QStyle.State_Sunken, "dk_pressed"),
    ("pressed+hover", QStyle.State(int(QStyle.State_MouseOver) | int(QStyle.State_Sunken)), "dk_pressed"),
)
DK_CONTEXTS = ("刷词", "学习选择题", "词汇量测试")

# v1.3.3 / a50eeaa：只允许 DK normal/hover/pressed/fg 改色；picked 与其他全部保留。
# 摘要采用 sorted-key 紧凑 JSON / UTF-8，测试不需要 git 或外部进程。
V133_STABLE_HASHES = {
    "light": "c8e3d1b65ee79c10eefcd8ad64bc26073c13ac817eb9f3d3c5dbdd0697652385",
    "dark": "b0090a81b60fc3ef35cfe4f1e733780840ff237c36f2ae4c3891371a427fc177",
    "sepia": "8218c84f6bb83a82046721221ccb660ba8024b225af285ab36c69c41ef33687e",
    "green": "f2ccbdb09f8e42f03662bbdffd119d3ba9bc31401e480cf64fa005852b1fdedf",
}
# QSS baseline from committed V1.3.6 (1967ecc); unlike the palette hashes,
# the older V1.3.3 QSS digest predates the current close-button rules.
V136_QSS_HASH = "cb5762c930089186167f7f75d0f9c40867583255ae5d757b4b2ac6d6cf0aa1a0"
V133_DK = {
    "light": {"dk_bg": "#ece4d7", "dk_hover": "#e3d7c5", "dk_fg": "#705431",
              "dk_pick": "#dcccb4", "dk_pick_fg": "#694d2c"},
    "dark": {"dk_bg": "#594f41", "dk_hover": "#655a49", "dk_fg": "#f0e1c4",
             "dk_pick": "#6d604d", "dk_pick_fg": "#f8edd7"},
    "sepia": {"dk_bg": "#e4dacb", "dk_hover": "#dacbb6", "dk_fg": "#654d34",
              "dk_pick": "#d4bf9e", "dk_pick_fg": "#644523"},
    "green": {"dk_bg": "#e5e2cf", "dk_hover": "#dad6be", "dk_fg": "#6a5934",
              "dk_pick": "#d1c9a8", "dk_pick_fg": "#5e4d2c"},
}

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
    ("dk_fg", "dk_bg"), ("dk_fg", "dk_hover"), ("dk_fg", "dk_pressed"),
    ("dk_pick_fg", "dk_pick"),
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


def button_image(button, state=QStyle.State_None, size=None, text=True, enabled=True):
    """绘制实际 widget 的 QStyle/QSS；显式状态不依赖鼠标位置，尺寸可归一化。"""
    image = QImage(QSize(*size) if size else button.size(), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    option = QStyleOptionButton()
    option.initFrom(button)
    option.rect = image.rect()
    option.text = button.text() if text else ""
    clean_state = int(option.state) & ~int(
        QStyle.State_MouseOver | QStyle.State_Sunken | QStyle.State_HasFocus | QStyle.State_Enabled)
    option.state = QStyle.State(clean_state | int(state) |
                               (int(QStyle.State_Enabled) if enabled else 0))
    painter = QPainter(image)
    try:
        button.style().drawControl(QStyle.CE_PushButton, option, painter, button)
    finally:
        painter.end()
    return image


def button_fill(button, state=QStyle.State_None, enabled=True):
    image = button_image(button, state, text=False, enabled=enabled)
    return image.pixelColor(image.width() // 2, image.height() // 2)


def set_feedback(button, state):
    button.setProperty("state", state)
    button.style().unpolish(button)
    button.style().polish(button)
    button.ensurePolished()


def stable_hash(palette):
    stable = {key: value for key, value in palette.items() if key not in DK_CHANGED_KEYS}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
            (th.NAMES[theme_key] + " · V1.3.4", "title", 17, "fg_word"),
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
            ("忘记", "forget", "fgt_fg", "fgt_bg", "fgt_hover"),
            ("不认识", "dontknow", "dk_fg", "dk_bg", "dk_hover")):
        button = QPushButton(text, panel)
        button.setObjectName(name)
        buttons.addWidget(button)
        probes.append((button, QPalette.ButtonText, fg))
        fills.extend(((button, QStyle.State_None, bg),
                      (button, QStyle.State_MouseOver, hover)))
        if not name:
            fills.append((button, QStyle.State_Sunken, "btn_pressed"))
        elif name == "dontknow":
            fills.extend((button, state, key) for _, state, key in DK_STATES[2:])
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

    unknown = QPushButton("不认识 · 已选择（反馈原色）", panel)
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


def PaletteOptionProbe(parent=None):
    """palette-only 的独立父按钮/子标签探针；不导入 main 或任何词书资源。"""
    button = QPushButton(parent)
    button.content = QLabel(button)
    button.content.setWordWrap(True)
    button.content.setAttribute(Qt.WA_TransparentForMouseEvents)
    layout = QHBoxLayout(button)
    layout.setContentsMargins(16, 9, 16, 9)
    layout.addWidget(button.content)
    button.setText = button.content.setText
    return button


def palette_sandbox_module():
    # 与 main 一样守护 stable/legacy/recovery 路径，但不加载 main/books/bank。
    from types import SimpleNamespace
    import storage
    progress, win = storage.paths(APP)
    legacy_dirs = storage.legacy_dirs(APP)
    return SimpleNamespace(
        PROGRESS_PATH=progress, WIN_PATH=win,
        DEFAULT_PROGRESS_PATH=progress, DEFAULT_WIN_PATH=win,
        LEGACY_PROGRESS_PATH=os.path.join(APP, "data", "progress.json"),
        LEGACY_WIN_PATH=os.path.join(APP, "data", "_win.json"),
        LEGACY_PROGRESS_PATHS=tuple(os.path.join(path, "progress.json") for path in legacy_dirs),
        LEGACY_WIN_PATHS=tuple(os.path.join(path, "_win.json") for path in legacy_dirs))


def import_fixture_main(sb):
    """真实 Card/UI 工厂，数据全部来自 Sandbox；main/books 首次 import 也不读实库。"""
    import io
    from unittest.mock import patch
    if "main" in sys.modules or "books" in sys.modules:
        raise RuntimeError("Card 主题回归须在全新 Python 进程运行，避免已缓存的真实词书")
    fixture_dir = sb.path("fake-data")
    os.makedirs(fixture_dir, exist_ok=True)
    bank = [{"w": word, "p": "/%s/" % word, "s": "n. 隔离主题词条", "raw": "n. 隔离主题词条",
             "b": -1.0 + index * 0.25, "lvl": index}
            for index, word in enumerate(("gentle", "clear", "paper", "memory", "river", "warm", "study", "word"))]
    words = [entry["w"] for entry in bank]
    books = {"schema": 2, "mains": [{"id": "theme-fixture-main", "name": "隔离主题",
              "groups": [{"id": "theme-fixture-group", "name": "主题夹具",
                          "union": {"id": "theme-fixture-all", "count": len(words), "words": words},
                          "items": [{"id": "theme-fixture-book", "name": "主题词书", "display": "主题词书",
                                     "kind": "fixture", "count": len(words), "words": words}]}]}]}
    originals = {}
    original_open = io.open
    for name, content in (("bank.json", bank), ("books.json", books), ("phrases.json", []),
                          ("phrase_books.json", {"items": []})):
        target = os.path.join(fixture_dir, name)
        with original_open(target, "w", encoding="utf-8") as stream:
            json.dump(content, stream, ensure_ascii=False)
        originals[os.path.normcase(os.path.abspath(os.path.join(APP, "data", name)))] = target

    def fixture_open(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            key = os.path.normcase(os.path.abspath(os.fsdecode(path)))
            if key in originals:
                mode = args[0] if args else kwargs.get("mode", "r")
                if any(flag in mode for flag in ("w", "a", "+", "x")):
                    raise RuntimeError("主题回归禁止写实资源路径：%s" % path)
                path = originals[key]
        return original_open(path, *args, **kwargs)

    with patch("io.open", fixture_open), patch("builtins.open", fixture_open):
        import main as app_main
    old_data, old_books_data = app_main.DATA, app_main.bk.DATA
    app_main.DATA = app_main.bk.DATA = fixture_dir
    app_main.PROGRESS_PATH, app_main.WIN_PATH = sb.progress_path, sb.win_path
    # Sandbox 进入时的 stub 与 main 同守护路径；退出时停止真 Card 再恢复其全局记录路径。
    sb.app = app_main
    out.append("FAKE_RESOURCES bank/books/phrases=%s entries=%d book=theme-fixture-book" %
               (fixture_dir, len(bank)))
    return app_main, (old_data, old_books_data)


def is_unknown_caption(text):
    return re.fullmatch(r"不认识(?:  \[[^\]\r\n]+\])?", text) is not None


def check_dk_group(buttons, palette, label):
    """验证三个实际或独立控件的全部状态；不点击，不改变答题/进度。"""
    saved = [(button, button.property("state"), button.isEnabled()) for _, button in buttons]
    normal_images = []
    try:
        for _, button in buttons:
            button.setEnabled(True)
            set_feedback(button, "")
        check(all(button.objectName() == "dontknow" for _, button in buttons),
              "%s 三处 objectName 同为 dontknow：%r" %
              (label, [(context, button.objectName()) for context, button in buttons]))
        check(all(is_unknown_caption(button.text()) for _, button in buttons),
              "%s 三处基础文字同为不认识，热键提示格式合法" % label)
        check(all(button.palette().color(QPalette.Active, QPalette.ButtonText) == QColor(palette["dk_fg"])
                  for _, button in buttons), "%s 三处 normal 前景同为 dk_fg" % label)
        scale = max(1.0, min(1.6, buttons[0][1].font().pixelSize() / 15.0))
        size = (round(220 * scale), round(44 * scale))
        for state_name, state, key in DK_STATES:
            colors = [button_fill(button, state) for _, button in buttons]
            check(all(color == QColor(palette[key]) for color in colors),
                  "%s %s 三处填充同为 %s：%r" %
                  (label, state_name, key, [color.name() for color in colors]))
            images = [button_image(button, state, size=size) for _, button in buttons]
            check(all(image == images[0] for image in images[1:]),
                  "%s %s 三处归一化实际绘制逐像素相同" % (label, state_name))
            if state_name == "normal":
                normal_images = [(context, image) for (context, _), image in zip(buttons, images)]
        for _, button in buttons:
            set_feedback(button, "picked")
        for state_name, state, _ in DK_STATES:
            check(all(button_fill(button, state) == QColor(palette["dk_pick"])
                      for _, button in buttons),
                  "%s picked 优先于 %s，保留原反馈填充" % (label, state_name))
        for _, button in buttons:
            button.setEnabled(False)
        check(all(button.palette().color(QPalette.Disabled, QPalette.ButtonText) == QColor(palette["dk_pick_fg"])
                  for _, button in buttons), "%s disabled picked 前景仍为原 dk_pick_fg" % label)
        check(all(button_fill(button, enabled=False) == QColor(palette["dk_pick"])
                  for _, button in buttons), "%s disabled picked 填充仍为原 dk_pick" % label)
    finally:
        for button, state, enabled in saved:
            button.setEnabled(enabled)
            set_feedback(button, state)
    return normal_images


def check_dk_widgets(theme_key, scale):
    palette = th.get(theme_key)
    panel = QWidget()
    panel.setObjectName("dk_probe")
    panel.setStyleSheet(th.qss(palette, scale) + "QWidget#dk_probe{background:%s;}" % palette["bg"])
    buttons = []
    try:
        for context in DK_CONTEXTS:
            button = QPushButton("不认识", panel)
            button.setObjectName("dontknow")
            button.resize(round(220 * scale), round(44 * scale))
            button.ensurePolished()
            buttons.append((context, button))
        check_dk_group(buttons, palette, "WIDGET %s/scale%.1f" % (theme_key, scale))
        check(all(button.font().pixelSize() == round(15 * scale) for _, button in buttons),
              "%s/scale%.1f DK 原字号/scaling 不变" % (theme_key, scale))
    finally:
        panel.close()
        panel.deleteLater()


def add_caption(layout, text, palette):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(th.label_qss(palette, "note", 12))
    layout.addWidget(label)


def add_button_image(layout, image):
    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    label.setPixmap(QPixmap.fromImage(image))
    layout.addWidget(label)


def build_dk_comparison():
    gallery = QWidget()
    gallery.setObjectName("dk_comparison_gallery")
    gallery.setStyleSheet("QWidget#dk_comparison_gallery{background:#eef1f5;}")
    grid = QGridLayout(gallery)
    grid.setContentsMargins(8, 8, 8, 8)
    grid.setSpacing(8)
    for column, theme_key in enumerate(th.ORDER):
        palette = th.get(theme_key)
        panel = QWidget(gallery)
        panel.setObjectName("dk_comparison_panel")
        panel.setStyleSheet("QWidget#dk_comparison_panel{background:%s;border:1px solid %s;}" %
                            (palette["bg"], palette["border"]))
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        title = QLabel(th.NAMES[theme_key] + " · 不认识")
        title.setStyleSheet(th.label_qss(palette, "title", 17))
        layout.addWidget(title)
        old_palette = dict(palette)
        old_palette.update(V133_DK[theme_key])
        old_palette["dk_pressed"] = old_palette["dk_hover"]
        button = QPushButton("不认识", panel)
        button.setObjectName("dontknow")
        button.resize(300, 44)
        button.setStyleSheet(th.qss(old_palette))
        button.ensurePolished()
        add_caption(layout, "V1.3.3 · 原正常填充", palette)
        add_button_image(layout, button_image(button, size=(300, 44)))
        button.setStyleSheet(th.qss(palette))
        button.ensurePolished()
        for caption, state in (("V1.3.4 · 正常", QStyle.State_None),
                               ("悬停 · hover", QStyle.State_MouseOver),
                               ("按下 · pressed + hover", DK_STATES[-1][1])):
            add_caption(layout, caption, palette)
            add_button_image(layout, button_image(button, state, size=(300, 44)))
        set_feedback(button, "picked")
        add_caption(layout, "选中反馈 · picked（原色保留）", palette)
        add_button_image(layout, button_image(button, size=(300, 44)))
        add_caption(layout, "页面 %s\n文字 %s\n填充:bg %.3f -> %.3f\nDK 状态文字最低 %.3f:1" %
                    (palette["bg"], palette["dk_fg"],
                     contrast(V133_DK[theme_key]["dk_bg"], palette["bg"]),
                     contrast(palette["dk_bg"], palette["bg"]),
                     min(contrast(palette["dk_fg"], palette[key]) for key in DK_SURFACES)), palette)
        layout.addStretch(1)
        button.hide()
        grid.addWidget(panel, 0, column)
        grid.setColumnStretch(column, 1)
    gallery.resize(1480, 640)
    return gallery


def build_card_dk_gallery(samples):
    gallery = QWidget()
    grid = QGridLayout(gallery)
    grid.setContentsMargins(8, 8, 8, 8)
    grid.setSpacing(8)
    for column, (theme_key, images) in enumerate(samples):
        palette = th.get(theme_key)
        panel = QWidget(gallery)
        panel.setObjectName("actual_dk_panel")
        panel.setStyleSheet("QWidget#actual_dk_panel{background:%s;border:1px solid %s;}" %
                            (palette["bg"], palette["border"]))
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel(th.NAMES[theme_key] + " · 实际 Card")
        title.setStyleSheet(th.label_qss(palette, "title", 16))
        layout.addWidget(title)
        for context, image in images:
            add_caption(layout, context + " · #dontknow", palette)
            add_button_image(layout, image)
        layout.addStretch(1)
        grid.addWidget(panel, 0, column)
    gallery.resize(1150, 320)
    return gallery


def main():
    app_main = palette_sandbox_module()
    old_data = None
    out.append("PYTHON %s QT %s PYQT %s PLATFORM %s" %
               (sys.version.split()[0], QT_VERSION_STR, PYQT_VERSION_STR,
                os.environ.get("QT_QPA_PLATFORM")))
    out.append("MODE " + ("palette-only" if PALETTE_ONLY else "card-integrated"))
    sb = Sandbox(app_main, "theme-v134-palette" if PALETTE_ONLY else "theme-v134-card")
    gallery = comparison = card_gallery = None
    try:
        with sb:
            if PALETTE_ONLY:
                option_class = PaletteOptionProbe
            else:
                app_main, old_data = import_fixture_main(sb)
                option_class = app_main.WrappedOptionButton
            out.append("OPTION_CLASS " + option_class.__name__)
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
            check(all(key in th.KEYS for key in DK_SURFACES), "DK normal/hover/pressed 四套 required keys 齐全")
            check(th.QSS.count(DK_PRESSED_RULE) == 1 and "QPushButton#dk" not in th.QSS,
                  "三处只共用既有 #dontknow；pressed 一条规则，不新造 #dk CSS")
            base_qss = th.QSS.replace(DK_PRESSED_RULE, "")
            check(hashlib.sha256(base_qss.encode("utf-8")).hexdigest() == V136_QSS_HASH,
                  "去除 DK pressed 规则后 QSS 与已提交 V136 基线完全相同（字号/留白/反馈/其他控件）")

            for theme_key in th.ORDER:
                palette = th.get(theme_key)
                check(set(palette) == set(th.KEYS), "%s key 集合与 KEYS 一致" % theme_key)
                check(all(HEX_COLOR.fullmatch(color) for color in palette.values()),
                      "%s 全部实色合法，避免父背景透明叠色影响对比度" % theme_key)
                check(stable_hash(palette) == V133_STABLE_HASHES[theme_key],
                      "%s V133 非DK配色（含picked反馈）摘要完全不变" % theme_key)
                check(len({palette[key] for key in DK_SURFACES}) == 3,
                      "%s DK normal/hover/pressed 三态填充各自可辨" % theme_key)
                old_fill = contrast(V133_DK[theme_key]["dk_bg"], palette["bg"])
                new_fill = contrast(palette["dk_bg"], palette["bg"])
                check(new_fill >= old_fill + 0.25,
                      "%s DK 正常填充:bg 明显增强 %.3f -> %.3f" % (theme_key, old_fill, new_fill))
                for key in DK_SURFACES:
                    check(contrast(palette[key], palette["bg"]) >= MIN_DK_FILL_CONTRAST,
                          "%s %s:bg %.3f >= %.1f 视觉分离目标" %
                          (theme_key, key, contrast(palette[key], palette["bg"]), MIN_DK_FILL_CONTRAST))
                check(all(max(rgb(palette[key])) - min(rgb(palette[key])) <= 55
                          for key in DK_SURFACES + ("dk_fg",)), "%s DK 全部新色通道跨度<=55，低饱和" % theme_key)
                out.append("DK_PALETTE %s fg=%s normal=%s hover=%s pressed=%s old_fill=%.3f new_fill=%.3f text_min=%.3f fill_min=%.3f" %
                           (theme_key, palette["dk_fg"], palette["dk_bg"], palette["dk_hover"], palette["dk_pressed"],
                            old_fill, new_fill,
                            min(contrast(palette["dk_fg"], palette[key]) for key in DK_SURFACES),
                            min(contrast(palette[key], palette["bg"]) for key in DK_SURFACES)))
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
                            "opt_hover", "chip_bg", "chip_hover", "dock_bg", "dock_hover") + DK_SURFACES
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
                    check_dk_widgets(theme_key, scale)
                check(th.qss(palette, 0.8) == th.qss(palette, 1.0)
                      and th.qss(palette, 2.0) == th.qss(palette, 1.6),
                      "%s scale 仍限于 1.0-1.6" % theme_key)

            sepia = th.get("sepia")
            check(all(r >= g >= b for r, g, b in map(rgb, sepia.values())),
                  "米黄所有控件/文字/selected/正确/chart 都是暖褐琥珀，不含绿色")
            for key in ("btn_fg", "chip_fg", "chip_sel_fg", "dock_fg", "dk_fg"):
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
                panel, probes, fills = build_panel(theme_key, option_class)
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
            comparison = build_dk_comparison()
            comparison.show()
            pump(0.05)
            compare_path = sb.shot("dk_v133_v134_comparison.png")
            check(comparison.grab().save(compare_path), "DK 四主题旧新版/hover/pressed/picked 对比图保存")
            out.append("DK_COMPARISON " + compare_path)

            if PALETTE_ONLY:
                out.append("DEFERRED actual Card / WrappedOptionButton（palette-only 完全不导入主程序/词书）")
                out.append("SOURCE theme=%s" % os.path.abspath(th.__file__))
            else:
                card = sb.new_card(progress={
                    "welcome_done": True, "book_confirmed": True, "book": "theme-fixture-book",
                    "theme": "light", "states": {}, "cursors": {}, "orders": {}, "history": [],
                }, show=True)
                card.move(70, 70)
                samples = []
                for theme_key in th.ORDER:
                    card.set_theme(theme_key)
                    pump(0.03)
                    palette = th.get(theme_key)
                    check(card.t is palette and card.theme_key == theme_key,
                          "%s 实际 Card 消费主题，不是另一套 demo 配色" % theme_key)
                    check(all(card.window_ctl.theme[key] == palette[key] for key in DOCK_KEYS),
                          "%s Card -> WindowController dock_* API 完整传递" % theme_key)
                    check(card.btn_remember.palette().color(QPalette.ButtonText) == QColor(palette["rem_fg"])
                          and card.btn_next.palette().color(QPalette.ButtonText) == QColor(palette["btn_fg"]),
                          "%s 实际 Card 正常/认识按钮原配色保持" % theme_key)
                    buttons = tuple(zip(DK_CONTEXTS, (card.btn_forget, card.btn_study_dk, card.btn_dontknow)))
                    found = [button for button in card.findChildren(QPushButton)
                             if is_unknown_caption(button.text())]
                    check(set(found) == {button for _, button in buttons},
                          "%s 全 Card 的不认识入口恰为已确认三处，无漏用其他颜色入口" % theme_key)
                    expected = ["不认识  [%s]" % app_main.keys.caption(card.key_bindings[action])
                                for action in ("forget", "unknown", "unknown")]
                    check([button.text() for _, button in buttons] == expected,
                          "%s 三处热键提示精确对应实际配置" % theme_key)
                    samples.append((theme_key, check_dk_group(buttons, palette, "CARD " + theme_key)))
                    check(card.catalog.theme is palette and card.catalog.model.palette is palette,
                          "%s Card -> catalog 主题 API 保持同步" % theme_key)
                    check(os.path.realpath(app_main.PROGRESS_PATH) == os.path.realpath(sb.progress_path)
                          and os.path.realpath(app_main.WIN_PATH) == os.path.realpath(sb.win_path),
                          "%s Card 进度/窗口保存始终隔离在 Sandbox" % theme_key)
                card_gallery = build_card_dk_gallery(samples)
                card_gallery.show()
                pump(0.05)
                actual_path = sb.shot("dk_actual_card_buttons.png")
                check(card_gallery.grab().save(actual_path), "实际 Card 三处不认识四主题图保存")
                out.append("DK_ACTUAL_CARD " + actual_path)
                out.append("SOURCE theme=%s main=%s catalog=%s" %
                           (os.path.abspath(th.__file__), os.path.abspath(app_main.__file__),
                            os.path.abspath(sys.modules[app_main.BookCatalog.__module__].__file__)))
    except Exception:
        check(False, "theme 测试异常：\n" + traceback.format_exc())
    finally:
        if old_data is not None:
            app_main.DATA, app_main.bk.DATA = old_data
        for view in (gallery, comparison, card_gallery):
            if view is not None:
                view.close()
                view.deleteLater()
        pump()
    check(not sb.errors, "Sandbox 真实记录/备份指纹未变：%r" % sb.errors)
    out.append("FINGERPRINT protected=%d unchanged=%s" % (len(sb.watch_paths), not sb.errors))
    return sb.finish(out, fails, "test_theme.txt")


if __name__ == "__main__":
    sys.exit(main())
