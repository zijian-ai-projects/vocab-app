# -*- coding: utf-8 -*-
"""配色主题：暗色 / 亮色 / 米黄 / 护眼绿。

main.py 里不写死任何颜色：卡片背景、文字、按钮、折线图全部从这里的主题字典取。
V1.3.3：中深灰蓝 / 浅灰蓝 / 暖褐琥珀 / 鼠尾草；控件文字独立配色。
按钮/选中背景使用实色，避免半透明叠在不同父控件上改变文字对比度。
正文与可用按钮（含 hover/pressed/selected）目标 >= 4.5:1；装饰线和禁用态除外。
dock_* 供 windowing 的短胶囊使用，chip_fg 不再复用弱化提示色 muted。
新增主题 = 在 THEMES 里加一份同 key 的字典，`missing()` 会自动检查。
"""

# 一套主题必须有的颜色（缺一个就会 KeyError，自测会先查出来）
KEYS = (
    "bg", "border",
    "fg_word", "fg_ipa", "fg_mean", "fg_empty", "fg_sub", "muted",
    "bar", "bar_hover", "bar_hover_bg",
    "btn_bg", "btn_fg", "btn_hover", "btn_pressed",
    "rem_bg", "rem_hover", "rem_fg",
    "fgt_bg", "fgt_hover", "fgt_fg",
    "wrong_fg", "wrong_dis",
    "link", "close", "close_hover",
    "opt_bg", "opt_fg", "opt_hover",
    "opt_ok_bg", "opt_ok_fg", "opt_bad_bg", "opt_bad_fg",
    "dk_bg", "dk_hover", "dk_fg", "dk_pick", "dk_pick_fg",
    "chip_bg", "chip_fg", "chip_hover", "chip_sel", "chip_sel_fg",
    "dock_bg", "dock_border", "dock_fg", "dock_hover",
    "chart_bg", "chart_grid", "chart_text", "chart_date", "chart_line",
    "ok", "accent",
)

THEMES = {
    "dark": {
        # 柔和中深灰蓝，比原 #15171b 明显提亮；文字不靠高饱和荧光色。
        "bg": "#353d49", "border": "#596575",
        "fg_word": "#eef1f5", "fg_ipa": "#bec8d6", "fg_mean": "#dee5ef",
        "fg_empty": "#c0d9cc", "fg_sub": "#bdc7d5", "muted": "#b2bece",
        "bar": "#bdc7d5", "bar_hover": "#f0f3f8", "bar_hover_bg": "#495568",
        "btn_bg": "#434f5f", "btn_fg": "#e0e7f0", "btn_hover": "#4e5b6d",
        "btn_pressed": "#3c4655",
        "rem_bg": "#3e5654", "rem_hover": "#48615e", "rem_fg": "#d5e7dc",
        "fgt_bg": "#5a4954", "fgt_hover": "#65525e", "fgt_fg": "#f0dae1",
        "wrong_fg": "#bdc7d5", "wrong_dis": "#778292",
        "link": "#bdc7d5", "close": "#b2bece", "close_hover": "#e0e7f0",
        "opt_bg": "#3c4655", "opt_fg": "#dee5ef", "opt_hover": "#465365",
        "opt_ok_bg": "#425950", "opt_ok_fg": "#d5e7dc",
        "opt_bad_bg": "#604c59", "opt_bad_fg": "#f0dae1",
        "dk_bg": "#594f41", "dk_hover": "#655a49", "dk_fg": "#f0e1c4",
        "dk_pick": "#6d604d", "dk_pick_fg": "#f8edd7",
        "chip_bg": "#414d5d", "chip_fg": "#d3dce8", "chip_hover": "#4b586b",
        "chip_sel": "#52627a", "chip_sel_fg": "#edf2f8",
        "dock_bg": "#424e5f", "dock_border": "#788ba4",
        "dock_fg": "#e1e8f1", "dock_hover": "#4f5d71",
        "chart_bg": "#2f3641", "chart_grid": "#475363", "chart_text": "#acb8ca",
        "chart_date": "#bbc6d4", "chart_line": "#abbfd9",
        "ok": "#c0d9cc", "accent": "#b4c7df",
    },
    "light": {
        # 浅灰蓝纸面 + 钢蓝灰控件；正确/错误保留低饱和语义区分。
        "bg": "#f3f6fa", "border": "#cbd4df",
        "fg_word": "#293547", "fg_ipa": "#596b83", "fg_mean": "#34445b",
        "fg_empty": "#355e62", "fg_sub": "#596b83", "muted": "#586981",
        "bar": "#596b83", "bar_hover": "#293547", "bar_hover_bg": "#e0e7f0",
        "btn_bg": "#e0e7f0", "btn_fg": "#3c516d", "btn_hover": "#d4deeb",
        "btn_pressed": "#c9d5e4",
        "rem_bg": "#dbe7e9", "rem_hover": "#ccdde0", "rem_fg": "#355e62",
        "fgt_bg": "#eee0e4", "fgt_hover": "#e6d3d9", "fgt_fg": "#814d60",
        "wrong_fg": "#596b83", "wrong_dis": "#a2afbf",
        "link": "#596b83", "close": "#586981", "close_hover": "#3c516d",
        "opt_bg": "#eaf0f7", "opt_fg": "#34445b", "opt_hover": "#dce6f1",
        "opt_ok_bg": "#d5e4e3", "opt_ok_fg": "#355c5a",
        "opt_bad_bg": "#e8d7df", "opt_bad_fg": "#814d60",
        "dk_bg": "#ece4d7", "dk_hover": "#e3d7c5", "dk_fg": "#705431",
        "dk_pick": "#dcccb4", "dk_pick_fg": "#694d2c",
        "chip_bg": "#e4ebf4", "chip_fg": "#475d79", "chip_hover": "#d5e0ed",
        "chip_sel": "#cad9eb", "chip_sel_fg": "#355173",
        "dock_bg": "#dce5f0", "dock_border": "#9baec5",
        "dock_fg": "#415977", "dock_hover": "#ccd9e9",
        "chart_bg": "#f8fafd", "chart_grid": "#dbe3ed", "chart_text": "#5c6e86",
        "chart_date": "#586b84", "chart_line": "#4d6c92",
        "ok": "#355e62", "accent": "#4d6c92",
    },
    "sepia": {
        # 米黄全套暖褐/琥珀：完成、选中、折线也不再混入绿色。
        "bg": "#f3ecdf", "border": "#d8c7ac",
        "fg_word": "#45382b", "fg_ipa": "#7a654d", "fg_mean": "#554433",
        "fg_empty": "#78571f", "fg_sub": "#7a654d", "muted": "#746149",
        "bar": "#7a644c", "bar_hover": "#45382b", "bar_hover_bg": "#e9decb",
        "btn_bg": "#e9decb", "btn_fg": "#61482e", "btn_hover": "#dfd0b7",
        "btn_pressed": "#d6c5a8",
        "rem_bg": "#eaddc0", "rem_hover": "#e2d0aa", "rem_fg": "#684b22",
        "fgt_bg": "#ebd9d0", "fgt_hover": "#e1c7bb", "fgt_fg": "#7c4333",
        "wrong_fg": "#76604a", "wrong_dis": "#b6a58e",
        "link": "#74583b", "close": "#7a644c", "close_hover": "#45382b",
        "opt_bg": "#eee4d3", "opt_fg": "#624b34", "opt_hover": "#e6d8c0",
        "opt_ok_bg": "#e6d5af", "opt_ok_fg": "#684b22",
        "opt_bad_bg": "#e6cdc1", "opt_bad_fg": "#7c4333",
        "dk_bg": "#e4dacb", "dk_hover": "#dacbb6", "dk_fg": "#654d34",
        "dk_pick": "#d4bf9e", "dk_pick_fg": "#644523",
        "chip_bg": "#e9dfce", "chip_fg": "#70563a", "chip_hover": "#e1d2b9",
        "chip_sel": "#dcc49b", "chip_sel_fg": "#65471f",
        "dock_bg": "#e8dcc5", "dock_border": "#b39b77",
        "dock_fg": "#6d5030", "dock_hover": "#ddcbae",
        "chart_bg": "#faf4e9", "chart_grid": "#e0d3be", "chart_text": "#7b6549",
        "chart_date": "#7b6549", "chart_line": "#886134",
        "ok": "#78571f", "accent": "#886134",
    },
    "green": {
        # 鼠尾草浅纸面 + 灰绿控件，正常正文保持 >= 7:1。
        "bg": "#eaf0e8", "border": "#cbd9c8",
        "fg_word": "#314137", "fg_ipa": "#5b6e5e", "fg_mean": "#3d5042",
        "fg_empty": "#365c43", "fg_sub": "#5a6d5d", "muted": "#596b5c",
        "bar": "#5a6d5d", "bar_hover": "#314137", "bar_hover_bg": "#dce6db",
        "btn_bg": "#dce6db", "btn_fg": "#425b48", "btn_hover": "#cfddce",
        "btn_pressed": "#c3d3c2",
        "rem_bg": "#d5e3d7", "rem_hover": "#c5d8c9", "rem_fg": "#365c43",
        "fgt_bg": "#e9ddd6", "fgt_hover": "#dfccc1", "fgt_fg": "#754936",
        "wrong_fg": "#536858", "wrong_dis": "#a7b5a7",
        "link": "#536c59", "close": "#5b6e5e", "close_hover": "#425b48",
        "opt_bg": "#f0f4ed", "opt_fg": "#3d5042", "opt_hover": "#e1eadd",
        "opt_ok_bg": "#cfdfd1", "opt_ok_fg": "#365c43",
        "opt_bad_bg": "#e1cfc5", "opt_bad_fg": "#754936",
        "dk_bg": "#e5e2cf", "dk_hover": "#dad6be", "dk_fg": "#6a5934",
        "dk_pick": "#d1c9a8", "dk_pick_fg": "#5e4d2c",
        "chip_bg": "#dfe8dc", "chip_fg": "#49654e", "chip_hover": "#d2dfcf",
        "chip_sel": "#c7d8c6", "chip_sel_fg": "#35563f",
        "dock_bg": "#dce6d9", "dock_border": "#9fb29c",
        "dock_fg": "#415b46", "dock_hover": "#cddcca",
        "chart_bg": "#f5f8f1", "chart_grid": "#dfe8d7", "chart_text": "#5c715e",
        "chart_date": "#5b6e5e", "chart_line": "#506f59",
        "ok": "#365c43", "accent": "#506f59",
    },
}

NAMES = {"dark": "暗色", "light": "亮色", "sepia": "米黄", "green": "护眼绿"}
ORDER = ["light", "dark", "sepia", "green"]
DEFAULT = "light"


def get(key):
    return THEMES.get(key) or THEMES[DEFAULT]


def options():
    """[(key, 显示名), ...]"""
    return [(k, NAMES[k]) for k in ORDER if k in THEMES]


def missing():
    """检查每个主题是否缺颜色，返回 [(key, [缺失...])]"""
    bad = []
    for k, t in THEMES.items():
        lack = [x for x in KEYS if x not in t]
        if lack:
            bad.append((k, lack))
    return bad


QSS = """
QPushButton {
    border: none; border-radius: 18px; padding: 9px 20px;
    font-family: 'Microsoft YaHei UI'; font-size: 16px;
    background: %(btn_bg)s; color: %(btn_fg)s;
}
QPushButton:hover { background: %(btn_hover)s; }
QPushButton:pressed { background: %(btn_pressed)s; }
QPushButton#remember { background: %(rem_bg)s; color: %(rem_fg)s; }
QPushButton#remember:hover { background: %(rem_hover)s; }
QPushButton#forget { background: %(fgt_bg)s; color: %(fgt_fg)s; }
QPushButton#forget:hover { background: %(fgt_hover)s; }
QPushButton#wrong { background: transparent; color: %(wrong_fg)s; font-size: 14px; }
QPushButton#wrong:hover { background: %(btn_bg)s; color: %(fg_mean)s; }
QPushButton#wrong:disabled { color: %(wrong_dis)s; background: transparent; }
QPushButton#bar { color: %(bar)s; background: transparent; padding: 0; font-size: 13px; border-radius: 6px; }
QPushButton#bar:hover { background: %(bar_hover_bg)s; color: %(bar_hover)s; }
QPushButton#link { color: %(link)s; background: transparent; padding: 0 8px; font-size: 13px; }
QPushButton#link:hover { color: %(bar_hover)s; }
QPushButton#close { color: %(close)s; background: transparent; padding: 0; font-size: 16px; }
QPushButton#close:hover { color: %(close_hover)s; }
QPushButton#opt {
    background: %(opt_bg)s; color: %(opt_fg)s; border-radius: 12px;
    text-align: left; padding-left: 16px; font-size: 15px;
}
QPushButton#opt:hover { background: %(opt_hover)s; }
QPushButton#opt[state="correct"] { background: %(opt_ok_bg)s; color: %(opt_ok_fg)s; }
QPushButton#opt[state="wrong"] { background: %(opt_bad_bg)s; color: %(opt_bad_fg)s; }
QPushButton#dontknow {
    background: %(dk_bg)s; color: %(dk_fg)s; font-size: 15px;
    border-radius: 12px;
}
QPushButton#dontknow:hover { background: %(dk_hover)s; }
QPushButton#dontknow[state="picked"] { background: %(dk_pick)s; color: %(dk_pick_fg)s; }
QPushButton#plain {
    background: transparent; color: %(fg_sub)s; font-size: 15px;
    padding: 8px 14px; border-radius: 12px;
}
QPushButton#plain:hover { background: %(chip_bg)s; color: %(fg_word)s; }
QPushButton#chip {
    background: %(chip_bg)s; color: %(chip_fg)s; border-radius: 13px;
    padding: 6px 12px; font-size: 13px;
}
QPushButton#chip:hover { background: %(chip_hover)s; color: %(fg_word)s; }
QPushButton#chip[on="1"] { background: %(chip_sel)s; color: %(chip_sel_fg)s; }
QPushButton#row {
    background: transparent; color: %(fg_mean)s; text-align: left;
    padding: 6px 10px; font-size: 13px; border-radius: 8px;
}
QPushButton#row:hover { background: %(chip_bg)s; }
QPushButton#book {
    background: %(opt_bg)s; color: %(opt_fg)s; border-radius: 10px;
    text-align: left; padding: 4px 14px; font-size: 14px;
}
QPushButton#book:hover { background: %(opt_hover)s; }
QPushButton#book[on="1"] { background: %(chip_sel)s; color: %(chip_sel_fg)s; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
QScrollBar::handle:vertical { background: %(muted)s; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: %(bar)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def qss(t, scale=1.0):
    import re
    scale = max(1.0, min(1.6, float(scale)))
    css = QSS % t
    css += """
QLineEdit, QSpinBox, QComboBox {
    border: 1px solid %(border)s; border-radius: 7px; padding: 5px 7px;
    background: %(opt_bg)s; color: %(fg_mean)s;
    selection-background-color: %(chip_sel)s; selection-color: %(chip_sel_fg)s;
    font-family: 'Microsoft YaHei UI'; font-size: 13px;
}
QComboBox QAbstractItemView {
    background: %(bg)s; color: %(fg_mean)s;
    selection-background-color: %(chip_sel)s; selection-color: %(chip_sel_fg)s;
}
QPushButton#opt QLabel { background: transparent; color: %(opt_fg)s; font-size: 15px;
    font-family: 'Microsoft YaHei UI'; }
QPushButton#opt[state="correct"] QLabel { color: %(opt_ok_fg)s; }
QPushButton#opt[state="wrong"] QLabel { color: %(opt_bad_fg)s; }
""" % t
    if scale != 1.0:
        css = re.sub(r"(\d+)px", lambda match: "%dpx" % max(1, round(int(match.group(1)) * scale)), css)
    return css


# ---------- 文字样式 ----------
def label_qss(t, kind, size):
    fam = "'Microsoft YaHei UI'"
    if kind == "word" or kind == "big":
        return "color:%s; font-family:Georgia,'Times New Roman'; font-size:%dpx;" % (t["fg_word"], size)
    if kind == "ipa":
        return "color:%s; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:%dpx;" % (t["fg_ipa"], size)
    if kind == "mean":
        return "color:%s; font-family:%s; font-size:%dpx;" % (t["fg_mean"], fam, size)
    if kind == "empty":
        return "color:%s; font-family:%s; font-size:%dpx;" % (t["fg_empty"], fam, size)
    if kind == "sub":
        return "color:%s; font-family:%s; font-size:%dpx;" % (t["fg_sub"], fam, size)
    if kind == "title":
        return "color:%s; font-family:%s; font-size:%dpx; font-weight:600;" % (t["fg_word"], fam, size)
    if kind == "ok":
        return "color:%s; font-family:%s; font-size:%dpx;" % (t["ok"], fam, size)
    # note / hint / status
    return "color:%s; font-family:%s; font-size:%dpx;" % (t["muted"], fam, size)
