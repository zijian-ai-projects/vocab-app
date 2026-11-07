# -*- coding: utf-8 -*-
"""配色主题：暗色 / 亮色 / 米黄 / 护眼绿。

main.py 里不写死任何颜色：卡片背景、文字、按钮、折线图全部从这里的主题字典取。
新增主题 = 在 THEMES 里加一份同 key 的字典，`data/_theme_keys` 的检查会自动覆盖到。
"""

# 一套主题必须有的颜色（缺一个就会 KeyError，check_ui.py 会先查出来）
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
    "chip_bg", "chip_hover", "chip_sel", "chip_sel_fg",
    "chart_bg", "chart_grid", "chart_text", "chart_date", "chart_line",
    "ok", "accent",
)

THEMES = {
    "dark": {
        "bg": "#15171b", "border": "#2a2e35",
        "fg_word": "#eceef2", "fg_ipa": "#8b93a1", "fg_mean": "#d2d9e3",
        "fg_empty": "#5fd39a", "fg_sub": "#9aa3b2", "muted": "#5f6672",
        "bar": "#7d8592", "bar_hover": "#e6e9ee", "bar_hover_bg": "#23272b",
        "btn_bg": "#23272f", "btn_fg": "#c9ced6", "btn_hover": "#2b303a",
        "btn_pressed": "#1d2128",
        "rem_bg": "rgba(95,211,154,0.14)", "rem_hover": "rgba(95,211,154,0.24)",
        "rem_fg": "#79e0ac",
        "fgt_bg": "rgba(229,134,154,0.12)", "fgt_hover": "rgba(229,134,154,0.22)",
        "fgt_fg": "#ef9cad",
        "wrong_fg": "#8b93a1", "wrong_dis": "#464c56",
        "link": "#8f98a6", "close": "#5b616c", "close_hover": "#c9ced6",
        "opt_bg": "#1e222a", "opt_fg": "#cfd6e0", "opt_hover": "#262b34",
        "opt_ok_bg": "rgba(95,211,154,0.22)", "opt_ok_fg": "#9be8c2",
        "opt_bad_bg": "rgba(229,134,154,0.20)", "opt_bad_fg": "#f0a9b8",
        "dk_bg": "rgba(240,180,106,0.10)", "dk_hover": "rgba(240,180,106,0.20)",
        "dk_fg": "#f0b46a", "dk_pick": "rgba(240,180,106,0.28)",
        "dk_pick_fg": "#ffd9a8",
        "chip_bg": "#1e222a", "chip_hover": "#262b34",
        "chip_sel": "rgba(127,180,232,0.18)", "chip_sel_fg": "#a8c8ee",
        "chart_bg": "#111316", "chart_grid": "#24272e", "chart_text": "#5f6672",
        "chart_date": "#6f7784", "chart_line": "#7fb4e8",
        "ok": "#5fd39a", "accent": "#7fb4e8",
    },
    "light": {
        "bg": "#f7f8fa", "border": "#e2e5ea",
        "fg_word": "#1b1f24", "fg_ipa": "#6a7480", "fg_mean": "#2b3138",
        "fg_empty": "#178a53", "fg_sub": "#6a7480", "muted": "#8a929c",
        "bar": "#6e7884", "bar_hover": "#1b1f24", "bar_hover_bg": "#e7eaef",
        "btn_bg": "#e9ecf0", "btn_fg": "#3a424c", "btn_hover": "#dfe4ea",
        "btn_pressed": "#d6dce3",
        "rem_bg": "rgba(31,158,99,0.12)", "rem_hover": "rgba(31,158,99,0.20)",
        "rem_fg": "#178a53",
        "fgt_bg": "rgba(198,62,84,0.10)", "fgt_hover": "rgba(198,62,84,0.18)",
        "fgt_fg": "#c33f55",
        "wrong_fg": "#5f6873", "wrong_dis": "#b8bfc8",
        "link": "#6a7480", "close": "#98a1ac", "close_hover": "#3a424c",
        "opt_bg": "#eef1f5", "opt_fg": "#2b3138", "opt_hover": "#e6eaef",
        "opt_ok_bg": "rgba(31,158,99,0.18)", "opt_ok_fg": "#178a53",
        "opt_bad_bg": "rgba(198,62,84,0.16)", "opt_bad_fg": "#c33f55",
        "dk_bg": "rgba(176,120,31,0.12)", "dk_hover": "rgba(176,120,31,0.20)",
        "dk_fg": "#a06a15", "dk_pick": "rgba(176,120,31,0.26)",
        "dk_pick_fg": "#8a5a10",
        "chip_bg": "#eef1f5", "chip_hover": "#e6eaef",
        "chip_sel": "rgba(59,130,246,0.16)", "chip_sel_fg": "#2b6cb0",
        "chart_bg": "#ffffff", "chart_grid": "#e9edf2", "chart_text": "#9aa3ad",
        "chart_date": "#b0b7c0", "chart_line": "#3b82f6",
        "ok": "#178a53", "accent": "#3b82f6",
    },
    "sepia": {
        "bg": "#f4ecdf", "border": "#ded1bb",
        "fg_word": "#3a2f24", "fg_ipa": "#8b7c66", "fg_mean": "#4a3d2e",
        "fg_empty": "#3f7d52", "fg_sub": "#7d6c55", "muted": "#9a8a72",
        "bar": "#8b7c66", "bar_hover": "#3a2f24", "bar_hover_bg": "#e8ddca",
        "btn_bg": "#eae1d1", "btn_fg": "#4a3d2e", "btn_hover": "#e2d7c4",
        "btn_pressed": "#dccfba",
        "rem_bg": "rgba(63,125,82,0.12)", "rem_hover": "rgba(63,125,82,0.20)",
        "rem_fg": "#3f7d52",
        "fgt_bg": "rgba(168,78,58,0.10)", "fgt_hover": "rgba(168,78,58,0.18)",
        "fgt_fg": "#a4513c",
        "wrong_fg": "#7d6c55", "wrong_dis": "#c0b39c",
        "link": "#7d6c55", "close": "#b0a48d", "close_hover": "#3a2f24",
        "opt_bg": "#efe7d9", "opt_fg": "#4a3d2e", "opt_hover": "#e7ddcc",
        "opt_ok_bg": "rgba(63,125,82,0.16)", "opt_ok_fg": "#3f7d52",
        "opt_bad_bg": "rgba(168,78,58,0.14)", "opt_bad_fg": "#a4513c",
        "dk_bg": "rgba(160,110,30,0.12)", "dk_hover": "rgba(160,110,30,0.20)",
        "dk_fg": "#8a6414", "dk_pick": "rgba(160,110,30,0.26)",
        "dk_pick_fg": "#77540d",
        "chip_bg": "#efe7d9", "chip_hover": "#e7ddcc",
        "chip_sel": "rgba(63,125,82,0.16)", "chip_sel_fg": "#3f7d52",
        "chart_bg": "#faf5ec", "chart_grid": "#e5dbc9", "chart_text": "#a08f74",
        "chart_date": "#ab9c80", "chart_line": "#6a9c7a",
        "ok": "#3f7d52", "accent": "#6a9c7a",
    },
    "green": {
        # 低饱和浅绿（纸感），不是深色绿；文字统一深绿灰，对比度按正文 ≥ 7:1 配
        "bg": "#e8efe2", "border": "#d3ddc8",
        "fg_word": "#24301f", "fg_ipa": "#6b7a60", "fg_mean": "#2f3b28",
        "fg_empty": "#2f7d4f", "fg_sub": "#667456", "muted": "#6d7b62",
        "bar": "#6f7d63", "bar_hover": "#24301f", "bar_hover_bg": "#dbe5d2",
        "btn_bg": "#dde7d4", "btn_fg": "#3a4732", "btn_hover": "#d4dfc9",
        "btn_pressed": "#c9d6bd",
        "rem_bg": "rgba(47,125,79,0.14)", "rem_hover": "rgba(47,125,79,0.22)",
        "rem_fg": "#2c7a4c",
        "fgt_bg": "rgba(176,68,58,0.10)", "fgt_hover": "rgba(176,68,58,0.18)",
        "fgt_fg": "#a4483c",
        "wrong_fg": "#5f6b53", "wrong_dis": "#b6c1ab",
        "link": "#6b7a60", "close": "#9aa88d", "close_hover": "#3a4732",
        "opt_bg": "#eff4ea", "opt_fg": "#2f3b28", "opt_hover": "#e5ecdd",
        "opt_ok_bg": "rgba(47,125,79,0.18)", "opt_ok_fg": "#2c7a4c",
        "opt_bad_bg": "rgba(176,68,58,0.16)", "opt_bad_fg": "#a4483c",
        "dk_bg": "rgba(150,110,30,0.12)", "dk_hover": "rgba(150,110,30,0.20)",
        "dk_fg": "#8a6516", "dk_pick": "rgba(150,110,30,0.26)",
        "dk_pick_fg": "#78560f",
        "chip_bg": "#e5ecdd", "chip_hover": "#dce6d3",
        "chip_sel": "rgba(47,125,79,0.16)", "chip_sel_fg": "#2c6e45",
        "chart_bg": "#f7faf4", "chart_grid": "#dfe8d7", "chart_text": "#8b9781",
        "chart_date": "#a3ad97", "chart_line": "#4e8f68",
        "ok": "#2c7a4c", "accent": "#4e8f68",
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
    background: %(chip_bg)s; color: %(muted)s; border-radius: 13px;
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
QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
QScrollBar::handle:vertical { background: %(muted)s; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: %(bar)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def qss(t):
    return QSS % t


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
