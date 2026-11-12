# -*- coding: utf-8 -*-
"""极简背单词卡片（PyQt5）

学习：自由节奏，先复习后新词；卡片上只有单词，点完才淡入释义。
首次打开：先推荐做词汇量测试（也可以跳过，直接选词书开始学）。
设置（⚙）：背景 / 词汇量测试入口与历史记录 / 词书与已学进度。
"""
import sys, os, io, json, time, copy, math, random, warnings, traceback

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QRect, QLockFile, QEvent
from PyQt5.QtGui import (QPainter, QColor, QPainterPath, QPen, QFont, QFontMetrics, QKeySequence)
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                             QHBoxLayout, QVBoxLayout, QButtonGroup, QGraphicsOpacityEffect,
                             QScrollArea, QSizePolicy, QLayout,
                             QMessageBox, QStyle, QStyleOptionButton,
                             QKeySequenceEdit, QLineEdit, QAbstractSpinBox,
                             QTextEdit, QPlainTextEdit, QDialog)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import scheduler as sch
import placement as pl
import prediction as pred
import theme as th
import books as bk
import storage
from study_queue import StudyQueue, _count as _queue_count
import learning_policy as learn
import keybindings as keys
from windowing import WindowController
from catalog import BookCatalog
from entries import is_phrase, meaning as entry_meaning, pronunciation, memory_info, word_caption
import level_meanings
import study_options
import school_knowledge as school
from app_icon import application_icon, configure_application_icon, set_windows_app_id

DEFAULT_PROGRESS_PATH, DEFAULT_WIN_PATH = storage.paths(ROOT)
PROGRESS_PATH, WIN_PATH = DEFAULT_PROGRESS_PATH, DEFAULT_WIN_PATH
LEGACY_PROGRESS_PATH = os.path.join(DATA, "progress.json")
LEGACY_WIN_PATH = os.path.join(DATA, "_win.json")
# 单路径常量保留给旧隔离脚本；实际迁移覆盖所有旧稳定资料目录。
LEGACY_PROGRESS_PATHS = tuple(os.path.join(directory, "progress.json")
                              for directory in storage.legacy_dirs(ROOT))
LEGACY_WIN_PATHS = tuple(os.path.join(directory, "_win.json")
                         for directory in storage.legacy_dirs(ROOT))
VERSION = "1.4.1"
DEFAULTS_JOURNAL = "_v136_defaults_pending"
RESET_PREF_KEYS = ("theme", "study_mode", "retry_gap", "learning_policy",
                   "keybindings", "school_knowledge")

COMPACT_QSS = """
QPushButton { font-size: 15px; padding: 4px 12px; border-radius: 12px; }
QPushButton#bar { font-size: 13px; }
QPushButton#wrong { font-size: 14px; }
"""

CARD_W, CARD_H = 520, 430
# 设置只显示常用窗口名称；内部几何尺寸仍受当前屏幕工作区限制。
WINDOW_PRESETS = ((520, 430, "小窗"), (640, 520, "标准"), (760, 620, "大窗"))
QUIZ_W, QUIZ_H = 520, 430
COMPACT_W, COMPACT_H = 356, 196
# 字号 / 留白：(大窗, 小窗)
F_WORD = (38, 26)
F_IPA = (18, 18)
F_MEAN = (20, 17)
GAP_IPA = (16, 6)
BTN_H = (46, 36)
MARGINS = ((22, 14, 22, 16), (14, 8, 14, 10))
# 释义最多占 2 行（5556 词实测：大窗 476px 宽、小窗 312px 宽，都只到 2 行）。
# 按行高留固定高度：翻面不跳位，长释义也不会被截掉。
MEAN_LINES = 2


def book_quantity(meta, total=None):
    """所有民间词书统一显示实际成员数，不推算任何机构的词目配额。"""
    total = meta.get("count", 0) if total is None else total
    return "%s 词" % format(total, ",")


def mean_h(i, scale=1.0):
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(round(F_MEAN[i] * scale))
    return QFontMetrics(f).lineSpacing() * MEAN_LINES
ONBOARDING_PROMPT_N = 50
PREDICTION_MIN_N = 50
PREDICTION_MIN_RIGOR = 60
RESUME_TTL = 30 * 86400
LETTERS = "ABCD"

# 教材「某个版本全选」是 UI 层现算的并集，books.py 里没有对应 id，
# 这里用伪 id 存进 progress（book / cursors / orders），重启时再解析回词表。
SERIES_PREFIX = "series:"


def series_pseudo_id(group_id, series):
    return "%s%s:%s" % (SERIES_PREFIX, group_id, series)


def parse_series_id(book_id):
    """伪 id -> (group_id, series)；真实词书返回 (None, None)。"""
    if not isinstance(book_id, str) or not book_id.startswith(SERIES_PREFIX):
        return None, None
    parts = book_id.split(":", 2)
    if len(parts) == 3 and parts[1] and parts[2]:
        return parts[1], parts[2]
    return None, None


def series_union_words(group_id, series):
    """某版本各分册按册序拼接后去重（保留首次出现的顺序）。"""
    seen, out = set(), []
    for b in bk.items(group_id):
        if (b.get("series") or "") != series:
            continue
        for w in b["words"]:
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out


def series_label(series):
    """教材版本在界面上的写法（数据里人教 PEP 统一显示成人教PEP版）。"""
    return "人教PEP版" if series == "人教 PEP" else series


def stored_order(orders, book_id):
    """选择词书时的词序：顺序或乱序。

    旧版保存的逆序/乱序记录仍原样留在 progress 里（不影响已学内容），但界面
    只提供顺序/乱序；旧逆序记录显示为顺序。
    """
    mode = (orders.get(book_id) or {}).get("mode")
    return mode if mode in ("seq", "shuffle") else "seq"


def normalize_retry_gap(progress):
    """把旧五词间隔的存量 retry 一次归一到三词；不丢队列或学习计数。"""
    if _queue_count(progress.get("retry_gap", 3), 3) == 5:
        for record in progress.get("study_records", {}).values():
            pending = record.get("pending", {})
            for key, target in list(pending.items()):
                # pending 是绝对首次新词计数；旧 5 改成 3 只需整体提前 2。
                # 已 ready 的词保持 ready，不延后；未知词和其它书记录均保留。
                pending[key] = max(0, _queue_count(target) - 2)
    progress["retry_gap"] = 3       # 保存后再次加载不再调整 deadline。
    return progress


class ChartCanvas(QWidget):
    """词汇量历史折线图。points: [(timestamp, vocab), ...]"""

    def __init__(self, points, parent=None, integrated=False):
        super().__init__(parent)
        self.integrated = integrated
        self.points = points
        self.setMinimumHeight(168)
        self.set_palette(th.get(th.DEFAULT))

    def set_palette(self, t):
        self.c = dict(bg=t["bg"] if self.integrated else t["chart_bg"],
                      grid=t["chart_grid"], text=t["chart_text"],
                      date=t["chart_date"], line=t["chart_line"])
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pl_, pr, pt, pb = 56, 20, 14, 24
        c = self.c
        p.fillRect(self.rect(), QColor(c["bg"]))

        pts = self.points
        if not pts:
            p.setPen(QColor(c["text"]))
            p.drawText(self.rect(), Qt.AlignCenter, "暂无记录")
            return

        vals = [v for _, v in pts]
        vmin, vmax = min(vals), max(vals)
        span = max(200, vmax - vmin)
        lo, hi = vmin - span * 0.25, vmax + span * 0.25
        n = len(pts)
        x0, x1 = pl_, w - pr
        y0, y1 = pt, h - pb

        def px(i):
            return x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)

        def py(v):
            return y1 - (v - lo) / (hi - lo) * (y1 - y0)

        # 网格
        p.setPen(QPen(QColor(c["grid"]), 1))
        for k in range(3):
            v = lo + (hi - lo) * k / 2
            y = py(v)
            p.drawLine(int(x0), int(y), int(x1), int(y))
            p.setPen(QColor(c["text"]))
            p.drawText(2, int(y) - 7, pl_ - 10, 14, Qt.AlignRight | Qt.AlignVCenter,
                       format(int(v), ","))
            p.setPen(QPen(QColor(c["grid"]), 1))

        # 折线
        path = QPainterPath()
        for i, (_, v) in enumerate(pts):
            pt_ = QPointF(px(i), py(v))
            if i == 0:
                path.moveTo(pt_)
            else:
                path.lineTo(pt_)
        p.setPen(QPen(QColor(c["line"]), 2))
        p.drawPath(path)

        # 点 + 日期
        for i, (ts, v) in enumerate(pts):
            x, y = px(i), py(v)
            p.setBrush(QColor(c["line"]))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, y), 3.2, 3.2)
            if n <= 8:
                p.setPen(QColor(c["date"]))
                rx = min(max(0, int(x) - 26), w - 52)
                p.drawText(rx, int(y1) + 5, 52, 16, Qt.AlignCenter,
                           time.strftime("%m-%d", time.localtime(ts)))


class MiniButton(QPushButton):
    """左上角小图标：内部透明，只描边，线条颜色与粗细统一。

    kind: "min"（横线）/ "max"（加号）/ "gear"（空心齿轮）/ "back"（返回箭头）
    """

    def __init__(self, kind, tip="", parent=None):
        super().__init__("", parent)
        self.kind = kind
        self.setObjectName("bar")
        self.setFixedSize(22, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tip)
        self._hover = False
        self.fg = "#7d8592"
        self.hi = "#e6e9ee"

    def set_colors(self, fg, hi):
        self.fg, self.hi = fg, hi
        self.update()

    def set_kind(self, kind):
        self.kind = kind
        self.update()

    def enterEvent(self, ev):
        self._hover = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self.update()
        super().leaveEvent(ev)

    def paintEvent(self, ev):
        super().paintEvent(ev)                     # 背景（透明 / hover）交给样式表
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(self.hi if self._hover else self.fg), 1.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        # 落在像素中间，避免整条线变淡（否则跟齿轮描边颜色对不上）
        mx, my = math.floor(cx) + 0.5, math.floor(cy) + 0.5
        if self.kind == "min":
            p.drawLine(QPointF(cx - 5.5, my), QPointF(cx + 5.5, my))
        elif self.kind == "max":
            p.drawLine(QPointF(cx - 5.5, my), QPointF(cx + 5.5, my))
            p.drawLine(QPointF(mx, cy - 5.5), QPointF(mx, cy + 5.5))
        elif self.kind == "back":
            p.drawLine(QPointF(cx + 5.0, my), QPointF(cx - 4.5, my))
            p.drawPath(self._chevron(cx - 4.5, my, 4.0))
        else:
            self._paint_gear(p, cx, cy)

    @staticmethod
    def _chevron(x, y, size):
        path = QPainterPath()
        path.moveTo(QPointF(x + size * 0.62, y - size * 0.62))
        path.lineTo(QPointF(x, y))
        path.lineTo(QPointF(x + size * 0.62, y + size * 0.62))
        return path

    @staticmethod
    def _paint_gear(p, cx, cy):
        """8 齿空心齿轮：外轮廓多边形 + 中心小圆孔，不填色。"""
        r_tip, r_base, hole, teeth = 6.2, 4.5, 1.7, 8
        step = 360.0 / teeth
        path = QPainterPath()
        first = True
        for i in range(teeth):
            a = i * step
            for ang, r in ((a - 9.0, r_tip), (a + 9.0, r_tip),
                           (a + 15.0, r_base), (a + step - 15.0, r_base)):
                rad = math.radians(ang - 90.0)
                pt = QPointF(cx + r * math.cos(rad), cy + r * math.sin(rad))
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(QPointF(cx, cy), hole, hole)


class WrappedOptionButton(QPushButton):
    """学习选择题和词汇量测试共用的可换行选项，行高随实际宽度变化。"""
    def __init__(self, parent=None, base_height=36):
        super().__init__(parent)
        self._base_height = base_height
        self._base_fixed = False
        self._fit_scale = 1.0
        self.content = QLabel(self)
        self.content.setWordWrap(True)
        self.content.setTextFormat(Qt.PlainText)
        self.content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.content.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 5, 13, 5)
        layout.addWidget(self.content)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(base_height)

    def setText(self, text):
        super().setText(text)
        self.content.setText(text)
        self.setToolTip(text)
        self.fit_height(self._fit_scale)

    def fit_height(self, scale, available_width=None):
        self._fit_scale = scale
        padding_x, padding_y = round(13 * scale), round(5 * scale)
        self.layout().setContentsMargins(padding_x, padding_y, padding_x, padding_y)
        outer_width = self.width() if available_width is None else available_width
        width = max(40, outer_width - 2 * padding_x)
        self.content.ensurePolished()
        metrics = QFontMetrics(self.content.font())
        height = max(metrics.lineSpacing(), self.content.heightForWidth(width))
        self.setMinimumHeight(max(round(self._base_height * scale), height + 2 * padding_y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 滚动条出现会缩窄视口；不能仅按窗口总宽度测高。
        self.fit_height(self._fit_scale)

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(0)
        size.setHeight(self.minimumHeight())
        return size

    def sizeHint(self):
        size = super().sizeHint()
        size.setWidth(0)
        size.setHeight(self.minimumHeight())
        return size

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QPainter(self)
        self.style().drawControl(QStyle.CE_PushButton, option, painter, self)


class Card(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("背单词")
        configure_application_icon(QApplication.instance())
        self.setWindowIcon(application_icon())
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(CARD_W, CARD_H)

        self._closed = False
        self._closing = False
        self._ready_for_close = False
        self._applying_scale = False
        self.storage_notices = []
        self.progress = self._load_progress()
        self.states = self.progress.setdefault("states", {})
        self.cursors = self.progress.setdefault("cursors", {})
        self.orders = self.progress.setdefault("orders", {})
        self.study_records = self.progress.setdefault("study_records", {})
        self.study_record = None
        self.study_engine = None
        self.study_mode = self.progress.get("study_mode", "brush")
        self.learning_settings = learn.normalize_settings(self.progress.get("learning_policy"))
        self.learning_settings["mode"] = learn.REVIEW_FIRST
        self.progress["learning_policy"] = self.learning_settings
        self.daily_new_ledger = self.progress["daily_new_ledger"]
        self.learning_policy = learn.LearningPolicy(self.learning_settings, self.daily_new_ledger)
        self.key_bindings = dict(keys.DEFAULT_BINDINGS)
        self.progress["keybindings"] = dict(self.key_bindings)
        self._last_answer_time = None
        self._policy_changed_in_settings = False
        self.retry_gap = 3            # 固定隔 3 个其它新词重现，不再提供设置
        self.settings_study_mode_start = self.study_mode
        self.catalog_src = "books"
        self.choice_question = None
        self._study_option_pools = {}
        self.choice_locked = False

        self.theme_key = self.progress.get("theme") or th.DEFAULT
        self.t = th.get(self.theme_key)
        self.book_id = self._resolve_saved_book(self.progress.get("book"))
        self.sel_book = None
        self.sel_order = stored_order(self.orders, self.book_id)
        self._order_selection_explicit = False
        self.order_mode = self.sel_order
        self.books_src = "welcome"
        self.pre_settings_mode = "front"
        self.result_ctx = "test"
        self.nav_level = 1
        self.nav_main = None
        self.nav_group = None
        self.nav_rows = []
        self.nav_sections = []
        self._nav_labels = []
        self.book_btns = {}
        self._reg = []

        # 大词库（A–Z，唯一一份词条）+ 当前词书的 A–Z 单词列表
        self.bank = json.load(io.open(os.path.join(DATA, "bank.json"), encoding="utf-8"))
        self.bank_map = {x["w"]: x for x in self.bank}
        phrase_path = os.path.join(DATA, "phrases.json")
        self.phrases = json.load(io.open(phrase_path, encoding="utf-8")) if os.path.exists(phrase_path) else []
        self.bank_map.update({x["w"]: x for x in self.phrases})
        self.all_entries = self.bank + self.phrases
        self.level_meanings = level_meanings.load()
        self.bs = [x["b"] for x in self.bank]
        self.lvls = [x["lvl"] for x in self.bank]
        self.bank_fingerprint = __import__("hashlib").sha256(
            "\n".join(word["w"] for word in self.bank).encode("utf-8")).hexdigest()
        self.theta = self.progress.get("theta")
        self.prediction_data = self.progress.get("prediction_state")
        if self.prediction_data is None:
            self.prediction_data = pred.new_prediction_data()
            self.progress["prediction_state"] = self.prediction_data
        try:
            pred.validate_prediction_data(self.prediction_data)
        except ValueError as error:
            raise storage.StorageError("预测掌握记录格式异常；原文件未清空。" + str(error))
        self._refresh_known()
        self.book_words = self._book_words(self.book_id)
        self.cursor = self.cursors.get(self.book_id, 0)
        self.queue_words = self._order_words(self.book_words, self.order_mode,
                                             self._seed(self.book_id) if self.book_id else None)

        self.queue = []
        self.qi = 0
        self.mode = "front"
        self.last_action = None
        self.corrected = False
        self.snapshot = None
        self.drag_pos = None
        self.compact = False

        self.quiz_items = []
        self.quiz_i = 0
        self.quiz_resp = []
        self.quiz_locked = False
        self._quiz_retry_action = None
        self.rigor = 100.0
        self.quiz_started_at = None
        self.quiz_last_answer_at = None
        self.quiz_session_id = None
        self.quiz_prompt_shown = False
        self.quiz_result = None
        self.quiz_vocab_grid = None
        self.quiz_bank_fingerprint = None
        self.quiz_origin_welcome = False
        self.quiz_return_to_settings = False
        self.quiz_status_values = None
        self.quiz_item_indices = {entry.get("w"): index for index, entry in enumerate(self.bank)}
        self.last_test = None
        self.quiz_timer = QTimer(self)
        self.quiz_timer.setSingleShot(True)
        self.quiz_timer.timeout.connect(self._quiz_next)

        self._window_save_timer = QTimer(self)
        self._window_save_timer.setSingleShot(True)
        self._window_save_timer.timeout.connect(self._flush_window)
        self._due_timer = QTimer(self)
        self._due_timer.setInterval(1000)
        self._due_timer.timeout.connect(self._check_due)
        self._build_ui()
        self.window_ctl = WindowController(self)
        self.window_ctl.update_palette(self.t)
        self.window_ctl.changed.connect(self._window_changed)
        legacy_win = (LEGACY_WIN_PATHS if WIN_PATH == DEFAULT_WIN_PATH
                      and not os.environ.get("VOCABAPP_DATA_DIR") else None)
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always", storage.StorageWarning)
            saved_window = storage.load_json(WIN_PATH, {}, legacy_path=legacy_win)
        self.storage_notices.extend(str(notice.message) for notice in notices)
        self.window_record = dict(saved_window)
        self.window_ctl.restore(saved_window, allow_compact=False)
        self._refresh_window_controls()
        self._startup()                   # 首屏与尺寸都先确定，不闪默认学习卡片
        self._ready_for_close = True
        self._apply_scaling()
        self._due_timer.start()
        self.show()

    # ---------- 数据 ----------
    def _load_progress(self):
        legacy = (LEGACY_PROGRESS_PATHS if PROGRESS_PATH == DEFAULT_PROGRESS_PATH
                  and not os.environ.get("VOCABAPP_DATA_DIR") else None)
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always", storage.StorageWarning)
            p = storage.load_json(PROGRESS_PATH, {}, legacy_path=legacy)
        self.storage_notices.extend(str(notice.message) for notice in notices)
        if DEFAULTS_JOURNAL in p:
            self._recover_defaults_journal(p)
        p["learning_policy"] = learn.normalize_settings(p.get("learning_policy"))
        p["learning_policy"]["mode"] = learn.REVIEW_FIRST
        p.setdefault("daily_new_ledger", {})
        try:
            learn.validate_ledger(p["daily_new_ledger"])
        except ValueError as error:
            raise storage.StorageError("每日新词账本异常；原文件未清空。" + str(error))
        p.pop("input_mode", None)
        p.pop("catalog_sort", None)
        try:
            p["keybindings"] = keys.normalize(p.get("keybindings"))
        except ValueError as error:
            p["keybindings"] = dict(keys.DEFAULT_BINDINGS)
            self.storage_notices.append("键位配置异常，已安全使用默认键位：" + str(error))
        p.setdefault("states", {})
        for field in ("states", "cursors", "orders", "study_records"):
            if field in p and not isinstance(p[field], dict):
                raise storage.StorageError("记录中的 %s 格式异常；原文件未清空。" % field)
        if "history" in p and not isinstance(p["history"], list):
            raise storage.StorageError("词汇量测试历史格式异常；原文件未清空。")
        for field in ("states", "orders", "study_records"):
            if any(not isinstance(value, dict) for value in p.get(field, {}).values()):
                raise storage.StorageError("记录中的 %s 条目格式异常；原文件未清空。" % field)
        for record in p.get("study_records", {}).values():
            if not isinstance(record.get("pending", {}), dict) or any(
                    record.get(key) is not None and not isinstance(record[key], dict)
                    for key in ("current", "held_current")):
                raise storage.StorageError("学习队列内部格式异常；原文件未清空。")
        if any(not isinstance(item, dict) or not isinstance(item.get("ts"), (int, float))
               or not isinstance(item.get("vocab"), (int, float)) for item in p.get("history", [])):
            raise storage.StorageError("词汇量测试历史条目异常；原文件未清空。")
        if "prediction_state" in p:
            try:
                pred.validate_prediction_data(p["prediction_state"])
            except ValueError as error:
                raise storage.StorageError("预测掌握记录格式异常；原文件未清空。" + str(error))
        p["states"] = sch.migrate_states(p["states"], legacy=p.get("memory_schema") != 2)
        p["memory_schema"] = 2
        p["app_version"] = VERSION
        p["study_mode"] = p.get("study_mode") if p.get("study_mode") in ("brush", "choice") else "brush"
        normalize_retry_gap(p)
        p.setdefault("theme", th.DEFAULT)
        p.setdefault("book", None)
        p.setdefault("cursors", {})
        p.setdefault("orders", {})
        p.pop("cursor", None)          # v1.0 的全局游标，v1.1 改为每本书一个
        # V1.1 的 11 个词书 id 已并入三级目录的分组并集：保留旧游标 / 词序
        if p.get("book") in bk.LEGACY:
            p["book"] = bk.LEGACY[p["book"]]
        for old_id, new_id in bk.LEGACY.items():
            if old_id in p["orders"] and new_id not in p["orders"]:
                p["orders"][new_id] = p["orders"][old_id]
            if old_id in p["cursors"] and new_id not in p["cursors"]:
                p["cursors"][new_id] = p["cursors"][old_id]
        if "book_confirmed" not in p:
            # 旧版打开就填默认六级、生成 seed / 游标；这些不是选书完成的证据。
            # 学习记录、已保存的其它词书或明确保存的顺序模式才证明真正用书开始过。
            saved = p.get("book")
            old_defaults = {bk.DEFAULT, "cet6", "cet6-all"}
            saved_mode = (p["orders"].get(saved) or {}).get("mode")
            p["book_confirmed"] = bool(
                p["states"] or (saved and saved not in old_defaults) or saved_mode == "seq")
        if p["book_confirmed"]:
            p["book"] = p.get("book") or bk.DEFAULT  # 无 book 字段的 v1.0 学习记录兜底
        else:
            p["book"] = None             # 不把旧版默认占位当作新用户的选择
        if "welcome_done" not in p:
            p["welcome_done"] = bool(p["book_confirmed"] or p.get("history"))
        return p

    def _can_act(self):
        return not getattr(self, "_closed", False) and not getattr(self, "_closing", False)

    def save(self, force=False):
        if not force and not self._can_act():
            return False
        self.progress["states"] = self.states
        self.progress["cursors"] = self.cursors
        self.progress["orders"] = self.orders
        self.progress["study_records"] = self.study_records
        self.progress["theta"] = self.theta
        self.progress["memory_schema"] = 2
        self.progress["app_version"] = VERSION
        self.progress["study_mode"] = self.study_mode
        self.progress["retry_gap"] = 3
        self.progress["prediction_state"] = self.prediction_data
        storage.atomic_save(PROGRESS_PATH, self.progress)

    # ---------- 大词库 / 词书 ----------
    def _resolve_saved_book(self, saved):
        """恢复已确认的词书（兼容旧 id / 教材系列伪 id）；未选书不兜底。"""
        if not saved:
            return None
        if saved in bk.BY_ID:
            return saved
        gid, series = parse_series_id(saved)
        if gid and series_union_words(gid, series):
            return saved
        return bk.get(saved)["id"]

    def _book_word_strs(self, book_id):
        """词书 / 并集 / 教材系列并集 -> A–Z 以外的原始词序（UI 层解析伪 id）。"""
        if not book_id:
            return []
        gid, series = parse_series_id(book_id)
        if gid:
            if gid not in bk.GROUPS:
                return bk.words(bk.DEFAULT)
            words = series_union_words(gid, series)
            return words or bk.words(gid)      # 系列失效时退回分组并集
        return bk.words(book_id)

    def _book_level(self, book_id):
        """按词书 / 分组 union / 教材系列伪 ID 的主分类返回学段。"""
        if not book_id:
            return None
        gid, _series = parse_series_id(book_id)
        if gid:
            group = bk.GROUPS.get(gid) or {}
            main = group.get("main")
        else:
            try:
                main = bk.get(book_id).get("main")
            except (KeyError, TypeError):
                main = None
        return level_meanings.stage_for_main(main)

    def _book_words(self, book_id):
        """返回浅拷贝词条并附加学段释义；bank_map/稳定 w/学习状态绝不修改。"""
        stage = self._book_level(book_id)
        mapping = self.level_meanings.get(stage, {}) if stage else {}
        return [level_meanings.decorate(self.bank_map[key], mapping)
                for key in self._book_word_strs(book_id) if key in self.bank_map]

    def _level_pool_entries(self, stage):
        """该主分类（primary/middleschool）所有唯一成员的已适配词条。"""
        mapping = self.level_meanings.get(stage, {})
        seen = set()
        entries = []
        for group in bk.groups(stage):
            for item in bk.items(group["id"]):
                for key in bk.words(item["id"]):
                    if key in seen or key not in self.bank_map:
                        continue
                    seen.add(key)
                    entries.append(level_meanings.decorate(self.bank_map[key], mapping))
        return entries

    def _book_level_option_pool(self, book_id, stage):
        """当前词书的学段释义池；不足时由调用方回退到同学段全分类池。"""
        key = "__level_book__%s:%s" % (stage, book_id)
        if key not in self._study_option_pools:
            self._study_option_pools[key] = study_options.OptionPool(
                self._book_words(book_id))
        return self._study_option_pools[key]

    def _level_option_pool(self, stage):
        key = "__level__" + stage
        if key not in self._study_option_pools:
            self._study_option_pools[key] = study_options.OptionPool(
                self._level_pool_entries(stage))
        return self._study_option_pools[key]

    def _book_meta(self, book_id):
        """统一的词书显示信息：伪 id 不写进 books.py，显示名 / 路径在这里现算。"""
        if not book_id:
            return {"id": None, "name": "", "display": "", "count": 0, "path": []}
        gid, series = parse_series_id(book_id)
        if gid:
            g = bk.GROUPS.get(gid)
            if g:
                main = next((m for m in bk.mains() if m["id"] == g["main"]), None)
                name = "%s · 本版本全选" % series
                return {"id": book_id, "name": name, "display": name,
                        "count": len(series_union_words(gid, series)),
                        "path": [main["name"] if main else "", g["name"]],
                        "group": gid, "series": series, "main": g["main"],
                        "source_status": "community_compilation", "source_version": "community",
                        "source_note": "词表由民间整理；教材系列全选按现有成员首次出现去重。",
                        "is_union": False, "is_series": True}
        b = dict(bk.get(book_id))
        b["is_series"] = False
        return b

    def _book_name(self, book_id):
        m = self._book_meta(book_id)
        return m.get("display") or m.get("name") or book_id or ""

    def _book_path(self, book_id):
        m = self._book_meta(book_id)
        parts = [p for p in (m.get("path") or []) if p]
        label = m.get("display") or m.get("name") or book_id
        if label:
            parts.append(label)
        return " · ".join(parts)

    def _book_short_name(self, book_id):
        """结果页里的一小段名字：真实书用所属分组名（六级/GRE…）。"""
        if not book_id:
            return ""
        gid, series = parse_series_id(book_id)
        if gid:
            return "%s 全选" % series
        b = bk.get(book_id)
        g = bk.GROUPS.get(b.get("group"))
        return g["name"] if g else (b.get("display") or b["name"])

    def _seed(self, book_id):
        rec = self.orders.setdefault(book_id, {"mode": "seq"})
        if rec.get("seed") is None:
            rec["seed"] = random.randrange(1, 1 << 30)
        return rec["seed"]

    def _order_words(self, words, mode, seed):
        out = list(words)
        if mode == "shuffle":
            random.Random(seed).shuffle(out)
        elif mode == "reverse":
            out.reverse()
        return out

    def _refresh_known(self):
        """仅使用用户明确接受的预测词；历史 theta 不自动改变学习队列。"""
        self.theta = self.progress.get("theta")
        data = self.progress.get("prediction_state")
        keys = data.get("selected", []) if isinstance(data, dict) else []
        selected = {key for key in keys if isinstance(key, str)} if isinstance(keys, list) else set()
        self.school_known = school.words(school.normalize(self.progress.get("school_knowledge")))
        selected.update(self.school_known)
        # Preserve the set shared with StudyQueue when preferences change.
        if hasattr(self, "known"):
            self.known.clear()
            self.known.update(selected)
        else:
            self.known = selected

    def _book_stats(self, book_id):
        learned = mastered = known = predicted = 0
        excluded = school.words(school.normalize(self.progress.get("school_knowledge")))
        words = [key for key in self._book_word_strs(book_id) if key not in excluded]
        for key in words:
            category, _, _ = memory_info(key, self.states, None, self.known)
            if category == "mastered":
                learned += 1
                mastered += 1
            elif category == "predicted":
                known += 1
                predicted += 1
            elif category == "known":
                known += 1
                if key in self.states:
                    learned += 1
        return learned, known, mastered, len(words), predicted

    # ---------- 当前词书实时队列；记忆状态在不同词书间共享 ----------
    def _make_engine(self):
        self.study_record = self.study_records.setdefault(
            self.book_id, {"cursor": self.cursors.get(self.book_id, 0)})
        self.learning_policy = learn.LearningPolicy(self.learning_settings, self.daily_new_ledger)
        self.study_engine = StudyQueue(self.queue_words, self.states, self.study_record,
                                      retry_gap=self.retry_gap, known=self.known,
                                      policy=self.learning_policy,
                                      excluded=school.words(school.normalize(self.progress.get("school_knowledge"))))
        self.cursor = self.study_engine.cursor

    def _new_session(self):
        if not self._can_act():
            return
        if not self.progress.get("book_confirmed") or not self.book_id:
            self.open_books("welcome")
            return
        self._make_engine()
        self.queue = []
        self.qi = 0
        self.snapshot = None
        self.last_action = None
        if not self._pull_new():
            self._show_empty()
            return
        self._show_current()

    def _pull_new(self, persist=True):
        if self.study_engine is None:
            self._make_engine()
        item = self.study_engine.next(time.time())
        self.cursor = self.study_engine.cursor
        self.cursors[self.book_id] = self.cursor
        if item is not None:
            self.queue.append(item)
            if persist:
                self.save()             # 未答 current 也持久化，关闭或重启不跳词
        return item is not None

    def _check_due(self):
        if not self._can_act():
            return
        now = time.time()
        self._refresh_learning_status(now)
        if self.mode != "empty" or not self.study_engine:
            return
        if self.window_ctl.collapsed:
            return
        waiting = self.study_engine.next_due_time(now)
        old_waiting = getattr(self, "waiting_due", None)
        # A quota midnight becomes eligible immediately, even after changing the clock/day.
        ready = old_waiting is not None and now >= old_waiting
        self.waiting_due = waiting
        if not ready and (waiting is None or now < waiting):
            self._empty_note()
            return
        before = self._capture_study()
        try:
            found = self._pull_new()
        except storage.StorageError as error:
            self._due_timer.stop()
            self._study_save_error(error, before)
            return
        if found:
            self.qi = len(self.queue) - 1
            self._show_current()
        else:
            self.waiting_due = self.study_engine.next_due_time()
            self._empty_note()

    # ---------- 窗口 ----------
    def toggle_compact(self):
        if self.study_mode == "brush" and self.mode in ("front", "back", "empty"):
            self.set_compact(not self.compact)

    def set_compact(self, on):
        on = bool(on) and self.study_mode == "brush"
        self.window_ctl.set_compact(on, remember=True)
        self.compact = self.window_ctl.compact
        self._set_mode(self.mode)
        self._flush_window()

    def _ui_scale(self):
        if self.compact:
            return 1.0
        return max(1.0, min(self.width() / CARD_W, self.height() / CARD_H, 1.6))

    def _window_changed(self):
        if not self._can_act() or not hasattr(self, "window_ctl"):
            return
        if not self.window_ctl.can_persist_geometry:
            return
        self.compact = self.window_ctl.compact
        self._apply_scaling()
        self._window_save_timer.start(400)

    def _save_window(self, force=False):
        if not hasattr(self, "window_ctl") or (not self._can_act() and not force):
            return
        if not self.window_ctl.can_persist_geometry:
            return
        record = dict(getattr(self, "window_record", {}))
        record.update(self.window_ctl.state())
        storage.atomic_save(WIN_PATH, record)
        self.window_record = record

    def _flush_window(self):
        if not self._can_act():
            return
        try:
            self._save_window()
            self._last_window_error = None
        except storage.StorageError as error:
            notice = "窗口设置暂未保存：" + str(error)
            if notice != getattr(self, "_last_window_error", None):
                self.storage_notices.append(notice)
                self._last_window_error = notice
                self.btn_gear.setToolTip(notice)
                if self.mode == "settings":
                    self._refresh_settings()

    def _apply_scaling(self, force=False):
        if self._applying_scale or not hasattr(self, "root"):
            return
        if hasattr(self, "window_ctl") and (self.window_ctl.collapsed or self.window_ctl.animating):
            return
        scale = self._ui_scale()
        signature = (scale, self.width(), self.height(), self.compact, self.mode,
                     self.theme_key, self.word.text(), self.meaning.text())
        if not force and getattr(self, "_scale_signature", None) == signature:
            return
        self._applying_scale = True
        try:
            self._scale_signature = signature
            i = 1 if self.compact else 0
            self._base_qss = th.qss(self.t, scale)
            action_qss = ('QPushButton[bookAction="1"] { font-size: %dpx; padding: 4px %dpx; }'
                          % (round(13 * scale), round(12 * scale)))
            self.setStyleSheet(self._base_qss + (COMPACT_QSS if self.compact else "") + action_qss
                               + th.history_qss(self.t, scale))
            self.root.setContentsMargins(*(round(value * scale) for value in MARGINS[i]))
            for button in self.findChildren(QPushButton):
                if isinstance(button, MiniButton) or button is self.btn_close:
                    continue
                if not hasattr(button, "_base_height"):
                    button._base_height = button.minimumHeight()
                    button._base_fixed = button.minimumHeight() == button.maximumHeight()
                height = round(button._base_height * scale)
                if button._base_fixed:
                    button.setFixedHeight(height)
                else:
                    button.setMinimumHeight(height)
            for button in (self.btn_forget, self.btn_remember, self.btn_wrong, self.btn_next):
                button.setMinimumHeight(round(BTN_H[i] * scale))
            for button in (self.btn_min, self.btn_gear, self.btn_back):
                button.setFixedSize(round(22 * scale), round(20 * scale))
                button.raise_()
            self.back_slot.setFixedSize(round(22 * scale), round(20 * scale))
            self.btn_close.setFixedSize(round(24 * scale), round(24 * scale))
            self.btn_min.set_kind("max" if self.compact else "min")
            self.gap_ipa.setFixedHeight(round(GAP_IPA[i] * scale))
            self.meaning.setFixedHeight(mean_h(i, scale))
            self._style_text()
            self._fit_study_text()
            self.catalog.set_scale(scale)
            self._apply_tool_colors()
            for area in self.findChildren(QScrollArea):
                try:
                    area.viewport().setAutoFillBackground(False)
                except AttributeError:
                    pass
            self._fit_choice_options(scale)
            self.update()
        finally:
            self._applying_scale = False

    def _fit_study_text(self):
        i, scale = (1 if self.compact else 0), self._ui_scale()
        margins = self.root.contentsMargins()
        width = max(40, self.width() - margins.left() - margins.right())
        self.word.ensurePolished()
        size = round((18 if self.compact else 24) * scale) if self.mode == "empty" else round(F_WORD[i] * scale)
        minimum = round((14 if self.compact else 22) * scale)
        limit = 2 if self.compact else 3
        while True:
            self.word.setStyleSheet(th.label_qss(self.t, "empty" if self.mode == "empty" else "word", size))
            self.word.ensurePolished()
            metrics = QFontMetrics(self.word.font())
            height = metrics.boundingRect(QRect(0, 0, width, 2000), Qt.TextWordWrap, self.word.text()).height()
            if height <= metrics.lineSpacing() * limit or size <= minimum:
                break
            size -= 1
        word_height = max(metrics.lineSpacing(), height)
        self.word.setFixedHeight(word_height)
        visible_ipa = bool(self.ipa.text()) and self.mode != "empty"
        self.ipa.setVisible(visible_ipa)
        self.gap_ipa.setVisible(visible_ipa or bool(self.meaning.text()))
        available = (self.height() - margins.top() - margins.bottom()
                     - round((20 + BTN_H[i] + 8) * scale) - word_height)
        if visible_ipa:
            available -= self.ipa.sizeHint().height() + round(GAP_IPA[i] * scale)
        mean_size = round(F_MEAN[i] * scale)
        while True:
            self.meaning.setStyleSheet(th.label_qss(self.t, "mean", mean_size))
            self.meaning.ensurePolished()
            metrics = QFontMetrics(self.meaning.font())
            needed = metrics.boundingRect(QRect(0, 0, width, 2000), Qt.TextWordWrap,
                                          self.meaning.text()).height()
            if not self.compact or needed <= max(32, available) or mean_size <= 14:
                break
            mean_size -= 1
        self.meaning.setFixedHeight(max(metrics.lineSpacing() * MEAN_LINES, needed))

    def _fit_choice_options(self, scale):
        """两个选择题页都按可用视口测高；超长内容可滚动，不拉大窗口。"""
        if not hasattr(self, "study_btns"):
            return
        margins = self.root.contentsMargins()
        width = max(80, self.width() - margins.left() - margins.right() - round(6 * scale))
        for label in (self.choice_word, self.quiz_word):
            label.ensurePolished()
            metrics = QFontMetrics(label.font())
            height = metrics.boundingRect(QRect(0, 0, width, 2000), Qt.TextWordWrap,
                                          label.text()).height()
            label.setFixedHeight(max(metrics.lineSpacing(), height))
        for button in self.study_btns + self.opt_btns:
            button.fit_height(scale, width)

    # ---------- UI ----------
    def reg(self, label, kind, size):
        self._reg.append((label, kind, size))
        label.setStyleSheet(th.label_qss(self.t, kind, round(size * self._ui_scale())))
        return label

    def _style_text(self):
        i, scale = (1 if self.compact else 0), self._ui_scale()
        for label, kind, size in self._reg:
            label.setStyleSheet(th.label_qss(self.t, kind, round(size * scale)))
        kind, size = ("empty", 18 if self.compact else 24) if self.mode == "empty" else ("word", F_WORD[i])
        self.word.setStyleSheet(th.label_qss(self.t, kind, round(size * scale)))
        self.ipa.setStyleSheet(th.label_qss(self.t, "ipa", round(F_IPA[i] * scale)))
        self.meaning.setStyleSheet(th.label_qss(self.t, "mean", round(F_MEAN[i] * scale)))

    def _apply_tool_colors(self):
        for b in (self.btn_min, self.btn_gear, self.btn_back):
            b.set_colors(self.t["bar"], self.t["bar_hover"])
        self.chart.set_palette(self.t)
        self.history_chart.set_palette(self.t)

    def _build_ui(self):
        self._base_qss = th.qss(self.t)
        self.setStyleSheet(self._base_qss)

        self.root = QVBoxLayout(self)
        self.root.setSizeConstraint(QLayout.SetNoConstraint)
        self.root.setContentsMargins(*MARGINS[0])
        self.root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(4)
        self.back_slot = QWidget()
        self.back_slot.setFixedSize(22, 20)
        self.btn_back = MiniButton("back", "返回", self.back_slot)
        self.btn_back.setGeometry(self.back_slot.rect())
        self.btn_back.clicked.connect(self._page_back)
        top.addWidget(self.back_slot)
        self.btn_min = MiniButton("min", "缩小 / 展开")
        self.btn_min.clicked.connect(self.toggle_compact)
        top.addWidget(self.btn_min)
        self.btn_gear = MiniButton("gear", "设置")
        self.btn_gear.clicked.connect(self._gear_clicked)
        top.addWidget(self.btn_gear)
        top.addSpacing(6)
        self.page_title = QLabel("")
        top.addWidget(self.page_title)
        self.status = QLabel("")
        self.status.setTextFormat(Qt.RichText)
        top.addWidget(self.status)
        self.study_status = QLabel("")
        self.study_status.setTextFormat(Qt.PlainText)
        self.study_status.setToolTip("新词：首次学习；复习：到期词。")
        top.addWidget(self.study_status)
        top.addStretch(1)
        self.btn_skip = QPushButton("结束本次测试")
        self.btn_skip.setObjectName("link")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.clicked.connect(self.retry_or_skip)
        top.addWidget(self.btn_skip)
        self.btn_skip.hide()
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("close")
        self.btn_close.setToolTip("关闭")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_close)
        self.root.addLayout(top)

        self.reg(self.page_title, "title", 15)
        self.reg(self.status, "note", 12)
        self.reg(self.study_status, "note", 11)

        self._build_study()
        self._build_choice()
        self._build_quiz()
        self._build_result()
        self._build_welcome()
        self._build_books()
        self._build_settings()
        self.catalog = BookCatalog(self)
        self.root.addWidget(self.catalog, 1)
        self.catalog.hide()
        self.history_page = QWidget()
        hv = QVBoxLayout(self.history_page)
        hv.setContentsMargins(0, 0, 0, 0)
        self.history_chart = ChartCanvas([], integrated=True)
        hv.addWidget(self.history_chart)
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_rows = QWidget()
        self.history_rows_layout = QVBoxLayout(self.history_rows)
        self.history_rows_layout.addStretch(1)
        self.history_scroll.setWidget(self.history_rows)
        hv.addWidget(self.history_scroll, 1)
        self.history_page.hide()
        self.root.addWidget(self.history_page, 1)
        self._learning_buttons = ([self.btn_forget, self.btn_remember, self.btn_wrong, self.btn_next,
                                  self.btn_study_dk, self.btn_study_next, self.btn_dontknow, self.btn_skip]
                                 + self.study_btns + self.opt_btns)
        self._window_buttons = [self.btn_min, self.btn_gear, self.btn_back, self.btn_close]
        for button in self._learning_buttons + self._window_buttons:
            button.setFocusPolicy(Qt.NoFocus)
            button.installEventFilter(self)
        self.setFocusPolicy(Qt.StrongFocus)

        self.btn_back.hide()
        self.page_title.hide()
        self._apply_tool_colors()
        self._style_text()

    def _build_study(self):
        """单词 + 音标 + 释义整块居中；翻面只做淡入，位置不动。"""
        self.stage = QWidget()
        sv = QVBoxLayout(self.stage)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        sv.addStretch(1)

        self.word = QLabel("")
        self.word.setTextFormat(Qt.PlainText)
        self.word.setWordWrap(True)
        self.word.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.word.setAlignment(Qt.AlignCenter)
        sv.addWidget(self.word)

        self.ipa = QLabel("")
        self.ipa.setAlignment(Qt.AlignCenter)
        sv.addWidget(self.ipa)

        self.gap_ipa = QWidget()
        self.gap_ipa.setFixedHeight(GAP_IPA[0])
        sv.addWidget(self.gap_ipa)

        self.answer = QWidget()
        av = QVBoxLayout(self.answer)
        av.setContentsMargins(0, 0, 0, 0)
        self.meaning = QLabel("")
        self.meaning.setAlignment(Qt.AlignCenter)
        self.meaning.setWordWrap(True)
        self.meaning.setFixedHeight(mean_h(0))
        av.addWidget(self.meaning)
        sv.addWidget(self.answer)
        sv.addStretch(1)

        self.answer_effect = QGraphicsOpacityEffect(self.answer)
        self.answer.setGraphicsEffect(self.answer_effect)
        self.answer_effect.setOpacity(0.0)
        self.fade = QPropertyAnimation(self.answer_effect, b"opacity", self)
        self.fade.setDuration(190)
        self.fade.setEasingCurve(QEasingCurve.OutCubic)

        self.root.addWidget(self.stage, 1)

        self.front_bar = QWidget()
        fb = QHBoxLayout(self.front_bar)
        fb.setContentsMargins(0, 0, 0, 0)
        fb.setSpacing(10)
        self.btn_forget = QPushButton("不认识")
        self.btn_forget.setObjectName("dontknow")
        self.btn_forget.clicked.connect(lambda: self.act("forget"))
        self.btn_remember = QPushButton("认识")
        self.btn_remember.setObjectName("remember")
        self.btn_remember.clicked.connect(lambda: self.act("remember"))
        for b in (self.btn_forget, self.btn_remember):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(46)
        fb.addWidget(self.btn_forget, 1)
        fb.addWidget(self.btn_remember, 1)
        self.root.addWidget(self.front_bar)

        self.back_bar = QWidget()
        bb = QHBoxLayout(self.back_bar)
        bb.setContentsMargins(0, 0, 0, 0)
        bb.setSpacing(10)
        self.btn_wrong = QPushButton("选错了")
        self.btn_wrong.setObjectName("wrong")
        self.btn_wrong.setCursor(Qt.PointingHandCursor)
        self.btn_wrong.setMinimumHeight(46)
        self.btn_wrong.clicked.connect(self.correct)
        self.btn_next = QPushButton("下一个")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setMinimumHeight(46)
        self.btn_next.clicked.connect(self._next)
        bb.addWidget(self.btn_wrong, 2)
        bb.addWidget(self.btn_next, 3)
        self.root.addWidget(self.back_bar)
        self.back_bar.hide()

    def _build_choice(self):
        self.choice_page = QScrollArea()
        self.choice_page.setWidgetResizable(True)
        self.choice_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.choice_body = QWidget()
        layout = QVBoxLayout(self.choice_body)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(4)
        self.choice_word = QLabel("")
        self.choice_word.setWordWrap(True)
        self.choice_word.setTextFormat(Qt.PlainText)
        self.choice_word.setAlignment(Qt.AlignCenter)
        self.choice_word.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.reg(self.choice_word, "word", F_WORD[0]))
        self.choice_ipa = QLabel("")
        self.choice_ipa.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.reg(self.choice_ipa, "ipa", F_IPA[0]))
        layout.addStretch(1)
        self.study_btns = []
        for index in range(4):
            button = WrappedOptionButton()
            button.setObjectName("opt")
            button.setMinimumHeight(36)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _, i=index: self._study_answer(i))
            self.study_btns.append(button)
            layout.addWidget(button)
        self.choice_hint = QLabel("")
        self.choice_hint.setAlignment(Qt.AlignCenter)
        self.choice_hint.hide()
        layout.addWidget(self.reg(self.choice_hint, "note", 12))
        self.choice_actions = QWidget()
        actions = QHBoxLayout(self.choice_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        self.btn_study_dk = QPushButton("不认识")
        self.btn_study_dk.setObjectName("dontknow")
        self.btn_study_dk.setMinimumHeight(34)
        self.btn_study_dk.clicked.connect(lambda: self._study_answer(-1))
        self.btn_study_next = QPushButton("下一个")
        self.btn_study_next.setObjectName("remember")
        self.btn_study_next.setMinimumHeight(34)
        self.btn_study_next.clicked.connect(self._next)
        self.btn_study_next.hide()
        actions.addWidget(self.btn_study_dk)
        actions.addWidget(self.btn_study_next)
        layout.addWidget(self.choice_actions)
        layout.addStretch(1)
        self.choice_page.setWidget(self.choice_body)
        self.root.addWidget(self.choice_page, 1)
        self.choice_page.hide()

    def _build_quiz(self):
        self.quiz_page = QScrollArea()
        self.quiz_page.setWidgetResizable(True)
        self.quiz_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.quiz_body = QWidget()
        qv = QVBoxLayout(self.quiz_body)
        qv.setContentsMargins(0, 0, 0, 0)
        qv.setSpacing(0)
        qv.addSpacing(10)
        self.quiz_word = QLabel("")
        self.quiz_word.setAlignment(Qt.AlignCenter)
        self.quiz_word.setWordWrap(True)
        self.quiz_word.setTextFormat(Qt.PlainText)
        self.quiz_word.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.reg(self.quiz_word, "big", 38)
        qv.addWidget(self.quiz_word)
        qv.addStretch(1)

        self.opt_btns = []
        for i in range(4):
            b = WrappedOptionButton(base_height=42)
            b.setObjectName("opt")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, idx=i: self._quiz_answer(idx))
            qv.addWidget(b)
            qv.addSpacing(8)
            self.opt_btns.append(b)

        qv.addSpacing(2)
        self.quiz_actions = QWidget()
        actions = QHBoxLayout(self.quiz_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        self.btn_dontknow = QPushButton("不认识")
        self.btn_dontknow.setObjectName("dontknow")
        self.btn_dontknow.setMinimumHeight(self.btn_study_dk.minimumHeight())
        self.btn_dontknow.setSizePolicy(self.btn_study_dk.sizePolicy())
        self.btn_dontknow.clicked.connect(lambda: self._quiz_answer(-1))
        actions.addWidget(self.btn_dontknow)
        qv.addWidget(self.quiz_actions)
        qv.addStretch(1)

        self.quiz_page.setWidget(self.quiz_body)
        self.root.addWidget(self.quiz_page, 1)
        self.quiz_page.hide()

    def _build_result(self):
        self.result_page = QWidget()
        rv = QVBoxLayout(self.result_page)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addSpacing(6)
        self.res_big = QLabel("")
        self.res_big.setAlignment(Qt.AlignCenter)
        self.reg(self.res_big, "big", 38)
        rv.addWidget(self.res_big)
        rv.addSpacing(2)
        self.res_sub = QLabel("")
        self.res_sub.setAlignment(Qt.AlignCenter)
        self.reg(self.res_sub, "sub", 13)
        rv.addWidget(self.res_sub)
        rv.addSpacing(10)
        self.chart_holder = QWidget()
        ch = QVBoxLayout(self.chart_holder)
        ch.setContentsMargins(0, 0, 0, 0)
        self.chart = ChartCanvas([])
        ch.addWidget(self.chart)
        rv.addWidget(self.chart_holder)
        rv.addSpacing(8)
        self.res_note = QLabel("")
        self.res_note.setAlignment(Qt.AlignCenter)
        self.res_note.setWordWrap(True)
        self.reg(self.res_note, "note", 12)
        rv.addWidget(self.res_note)
        rv.addSpacing(4)
        links = QHBoxLayout()
        links.setSpacing(4)
        self.btn_rebase = QPushButton("调整预测掌握")
        self.btn_rebase.setObjectName("link")
        self.btn_rebase.setCursor(Qt.PointingHandCursor)
        self.btn_rebase.clicked.connect(self._apply_prediction)
        self.btn_retest = QPushButton("开始新的测试")
        self.btn_retest.setObjectName("link")
        self.btn_retest.setCursor(Qt.PointingHandCursor)
        self.btn_retest.clicked.connect(self._confirm_new_quiz)
        self.btn_continue_quiz = QPushButton("继续上次测试")
        self.btn_continue_quiz.setObjectName("link")
        self.btn_continue_quiz.clicked.connect(self.start_quiz)
        links.addStretch(1)
        links.addWidget(self.btn_rebase)
        links.addWidget(self.btn_continue_quiz)
        links.addWidget(self.btn_retest)
        links.addStretch(1)
        rv.addLayout(links)
        rv.addStretch(1)

        self.btn_start = QPushButton("继续背单词")
        self.btn_start.setObjectName("remember")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self._result_primary)
        rv.addWidget(self.btn_start)
        self.root.addWidget(self.result_page, 1)
        self.result_page.hide()

    # ---------- 首次引导 / 词书 / 设置 ----------
    def _build_welcome(self):
        self.welcome_page = QWidget()
        wv = QVBoxLayout(self.welcome_page)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(0)
        wv.addStretch(1)

        title = QLabel("先测一下词汇量？")
        title.setAlignment(Qt.AlignCenter)
        self.reg(title, "title", 20)
        wv.addWidget(title)
        wv.addSpacing(10)

        body = QLabel("测试结果会影响学习内容，熟悉的词自动跳过。")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        self.reg(body, "note", 13)
        wv.addWidget(body)
        wv.addSpacing(6)

        tip = QLabel("约 5 分钟 · 50 题")
        tip.setAlignment(Qt.AlignCenter)
        self.reg(tip, "note", 12)
        wv.addWidget(tip)
        wv.addSpacing(24)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_welcome_test = QPushButton("测试一下")
        self.btn_welcome_test.setObjectName("remember")
        self.btn_welcome_test.setCursor(Qt.PointingHandCursor)
        self.btn_welcome_test.setMinimumHeight(46)
        self.btn_welcome_test.clicked.connect(self._welcome_test)
        self.btn_welcome_skip = QPushButton("不测了，直接开始学")
        self.btn_welcome_skip.setObjectName("plain")
        self.btn_welcome_skip.setCursor(Qt.PointingHandCursor)
        self.btn_welcome_skip.setMinimumHeight(46)
        self.btn_welcome_skip.clicked.connect(self._welcome_skip)
        row.addWidget(self.btn_welcome_test, 1)
        row.addWidget(self.btn_welcome_skip, 1)
        wv.addLayout(row)
        wv.addStretch(1)

        self.root.addWidget(self.welcome_page, 1)
        self.welcome_page.hide()

    def _build_books(self):
        """三级导航：主类 → 分组 → 词书（分组全选 / 教材按版本全选）。"""
        self.books_page = QWidget()
        bv = QVBoxLayout(self.books_page)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(0)
        bv.addSpacing(2)

        self.books_lead = QLabel("")
        self.reg(self.books_lead, "note", 12)
        bv.addWidget(self.books_lead)
        bv.addSpacing(5)

        self.book_scroll = QScrollArea()
        self.book_scroll.setWidgetResizable(True)
        self.book_scroll.setMinimumHeight(120)
        self.book_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.book_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.book_scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QWidget#booklist{background:transparent;}")
        holder = QWidget()
        holder.setObjectName("booklist")
        self.book_list_layout = QVBoxLayout(holder)
        self.book_list_layout.setContentsMargins(0, 0, 6, 0)
        self.book_list_layout.setSpacing(3)
        self.book_list_layout.addStretch(1)
        self.book_scroll.setWidget(holder)
        bv.addWidget(self.book_scroll, 1)
        bv.addSpacing(4)

        self.lab_book_stat = QLabel("")
        self.lab_book_stat.setWordWrap(True)
        self.lab_book_stat.setTextFormat(Qt.PlainText)
        self.reg(self.lab_book_stat, "note", 12)
        bv.addWidget(self.lab_book_stat)
        bv.addSpacing(3)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        lab_order = QLabel("词序")
        self.reg(lab_order, "note", 12)
        bottom.addWidget(lab_order)
        self.chip_seq = QPushButton("顺序")
        self.chip_seq.setObjectName("chip")
        self.chip_seq.clicked.connect(lambda: self._set_order("seq"))
        self.chip_shuffle = QPushButton("乱序")
        self.chip_shuffle.setObjectName("chip")
        self.chip_shuffle.clicked.connect(lambda: self._set_order("shuffle"))
        for b in (self.chip_seq, self.chip_shuffle):
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(28)
            bottom.addWidget(b)
        bottom.addStretch(1)
        self.btn_catalog_books = QPushButton("浏览词条")
        self.btn_catalog_books.setObjectName("chip")
        self.btn_catalog_books.setEnabled(False)
        self.btn_catalog_books.clicked.connect(lambda: self.open_catalog(self.sel_book, "books"))
        bottom.addWidget(self.btn_catalog_books)
        self.btn_learn = QPushButton("用这本书开始")
        self.btn_learn.setEnabled(False)
        self.btn_learn.setObjectName("remember")
        self.btn_learn.setCursor(Qt.PointingHandCursor)
        for button in (self.btn_catalog_books, self.btn_learn):
            button.setProperty("bookAction", "1")
            button.setFixedHeight(36)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.btn_learn.clicked.connect(self._start_learning)
        bottom.addWidget(self.btn_learn)
        bv.addLayout(bottom)
        bv.addSpacing(2)

        self.root.addWidget(self.books_page, 1)
        self.books_page.hide()

    # ---------- 三级词书导航 ----------
    def _clear_book_rows(self):
        # 分节标题登记过主题样式，重建前要从登记表里摘掉，避免主题切换时碰到已删除控件
        if self._nav_labels:
            dead = {id(x) for x in self._nav_labels}
            self._reg = [it for it in self._reg if id(it[0]) not in dead]
            self._nav_labels = []
        while self.book_list_layout.count():
            it = self.book_list_layout.takeAt(0)
            wgt = it.widget()
            if wgt is not None:
                wgt.hide()                 # deleteLater 要等事件循环；先立刻从界面移除
                wgt.setParent(None)
                wgt.deleteLater()
        self.book_btns = {}
        self.nav_rows = []
        self.nav_sections = []

    def _add_nav_row(self, text, key, slot, kind):
        btn = QPushButton(text)
        btn.setObjectName("book")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(32)
        btn.setToolTip(text)
        btn.clicked.connect(slot)
        self.book_list_layout.addWidget(btn)
        self.book_btns[key] = btn
        self.nav_rows.append({"kind": kind, "id": key, "text": text})
        return btn

    def _add_nav_section(self, text):
        lbl = QLabel(text)
        lbl.setContentsMargins(6, 5, 0, 0)
        self.reg(lbl, "note", 11)
        self.book_list_layout.addWidget(lbl)
        self.nav_sections.append(text)
        self._nav_labels.append(lbl)

    def _add_nav_item_row(self, it):
        text = "%s　%s" % (it.get("display") or it["name"], book_quantity(it))
        button = self._add_nav_row(text, it["id"],
                                   lambda _=False, bid=it["id"]: self._pick_book(bid), "book")
        note = it.get("source_note")
        if isinstance(note, str) and note:
            button.setToolTip(text + "\n" + note)

    def _build_nav_level(self):
        """按当前层级重建列表：1 主类 / 2 分组 / 3 词书 + 并集。"""
        self._clear_book_rows()
        if self.nav_level == 1:
            mains = bk.mains()
            self.books_lead.setText("选择主类")
            for m in mains:
                self._add_nav_row(m["name"], m["id"],
                                  lambda _=False, mid=m["id"]: self._nav_into_main(mid),
                                  "main")
        elif self.nav_level == 2:
            main = next((m for m in bk.mains() if m["id"] == self.nav_main), None)
            if not main:
                self.nav_level = 1
                return self._build_nav_level()
            self.books_lead.setText(main["name"])
            for g in main["groups"]:
                self._add_nav_row(g["name"], g["id"],
                                  lambda _=False, gid=g["id"]: self._nav_into_group(gid),
                                  "group")
        else:
            g = bk.GROUPS.get(self.nav_group)
            if not g:
                self.nav_level = 1
                return self._build_nav_level()
            self.books_lead.setText(g["name"])

            # 教材类分组：按版本分节（只列具体分册，不再提供「全选」）
            if g.get("series"):
                for s in g["series"]:
                    items = [it for it in g["items"] if (it.get("series") or "") == s]
                    self._add_nav_section("%s · %d 册" % (series_label(s), len(items)))
                    for it in items:
                        self._add_nav_item_row(it)
                for it in g["items"]:
                    if not (it.get("series") or ""):
                        self._add_nav_item_row(it)
            else:
                for it in g["items"]:
                    self._add_nav_item_row(it)
        self.book_list_layout.addStretch(1)

    def _nav_into_main(self, main_id):
        self.nav_main = main_id
        self.nav_level = 2
        self._build_nav_level()
        self._refresh_books()
        self.book_scroll.verticalScrollBar().setValue(0)

    def _nav_into_group(self, group_id):
        self.nav_group = group_id
        self.nav_level = 3
        self._build_nav_level()
        self._refresh_books()
        self.book_scroll.verticalScrollBar().setValue(0)

    def _nav_back(self):
        if self.nav_level == 3:
            self.nav_level = 2
            self.nav_group = None
            self._build_nav_level()
            self._refresh_books()
        elif self.nav_level == 2:
            self.nav_level = 1
            self.nav_main = None
            self._build_nav_level()
            self._refresh_books()
        else:
            self._page_back()
        try:
            self.book_scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass

    def _build_settings(self):
        self.settings_page = QScrollArea()
        self.settings_page.setWidgetResizable(True)
        self.settings_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_body = QWidget()
        layout = QVBoxLayout(self.settings_body)
        layout.setContentsMargins(0, 2, 2, 6)
        layout.setSpacing(6)

        layout.addWidget(self.reg(QLabel("背景"), "note", 12))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.theme_chips = {}
        for key, name in th.options():
            button = QPushButton(name)
            button.setObjectName("chip")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(30)
            button.clicked.connect(lambda _, k=key: self.set_theme(k))
            row.addWidget(button)
            self.theme_chips[key] = button
        row.addStretch(1)
        layout.addLayout(row)
        layout.addSpacing(6)

        layout.addWidget(self.reg(QLabel("窗口"), "note", 12))
        sizes = QHBoxLayout()
        sizes.setSpacing(6)
        self.size_chips = {}
        for width, height, name in WINDOW_PRESETS:
            button = QPushButton(name)
            button.setObjectName("chip")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(30)
            button.clicked.connect(lambda _=False, w=width, h=height:
                                   self._apply_window_size(w, h))
            sizes.addWidget(button)
            self.size_chips[(width, height)] = button
        sizes.addSpacing(10)
        self.btn_edge_collapse = QPushButton("小窗贴边收起：开")
        self.btn_edge_collapse.setObjectName("chip")
        self.btn_edge_collapse.setCheckable(True)
        self.btn_edge_collapse.setChecked(True)
        self.btn_edge_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_edge_collapse.setMinimumHeight(30)
        self.btn_edge_collapse.setToolTip(
            "开启后，小窗和刷词小窗靠边并移开鼠标时收起，悬停展开；关闭后不自动收起。")
        self.btn_edge_collapse.clicked.connect(self._set_edge_collapse)
        sizes.addWidget(self.btn_edge_collapse)
        sizes.addStretch(1)
        layout.addLayout(sizes)
        layout.addSpacing(6)

        layout.addWidget(self.reg(QLabel("学习模式"), "note", 12))
        modes = QHBoxLayout()
        self.study_mode_chips = {}
        for key, text in (("brush", "刷词模式"), ("choice", "选择题模式")):
            button = QPushButton(text)
            button.setObjectName("chip")
            button.setMinimumHeight(30)
            button.clicked.connect(lambda _, k=key: self.set_study_mode(k))
            self.study_mode_chips[key] = button
            modes.addWidget(button)
        modes.addStretch(1)
        layout.addLayout(modes)
        layout.addSpacing(6)

        scope_heading = self.reg(QLabel("已认识词汇范围—开启后跳过对应词汇的学习"), "note", 12)
        scope_heading.setWordWrap(True)
        scope_heading.setToolTip("以小学／中考／高考大纲英语词汇三本词书为准；包括已学词的复现。关闭后恢复原记录与排期。")
        layout.addWidget(scope_heading)
        school_row = QHBoxLayout()
        school_row.setSpacing(4)
        self.school_chips = {}
        for key, caption in school.LEVELS:
            button = QPushButton(caption)
            button.setObjectName("chip")
            button.setMinimumHeight(30)
            button.clicked.connect(lambda _, value=key: self.set_school_knowledge(value))
            self.school_chips[key] = button
            school_row.addWidget(button)
        school_row.addStretch(1)
        layout.addLayout(school_row)
        layout.addSpacing(6)

        self.key_edits = {}
        self.btn_apply_keys = None
        self.key_dialog = None
        for _title, actions in (("刷词答案", (("remember", "认识"), ("forget", "不认识"))),
                                ("选择题答案", (("choice1", "选项 A"), ("choice2", "选项 B"),
                                                ("choice3", "选项 C"), ("choice4", "选项 D"),
                                                ("unknown", "不认识"))),
                                ("翻到下一张", (("next", "下一个"),))):
            for action, text in actions:
                editor = QKeySequenceEdit(QKeySequence(self.key_bindings[action]), self)
                editor.hide()
                editor.setProperty("action_label", text)
                editor.keySequenceChanged.connect(self._check_key_draft)
                self.key_edits[action] = editor
        self.lab_key_error = QLabel("", self)
        self.lab_key_error.hide()

        layout.addWidget(self.reg(QLabel("词书"), "note", 12))
        book_row = QHBoxLayout()
        book_row.setSpacing(8)
        self.lab_book = QLabel("")
        self.lab_book.setWordWrap(True)
        self.lab_book.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        book_row.addWidget(self.reg(self.lab_book, "mean", 13), 1)
        self.lab_book_num = QLabel("")
        book_row.addWidget(self.reg(self.lab_book_num, "note", 13))
        change = QPushButton("更换")
        change.setObjectName("chip")
        change.setCursor(Qt.PointingHandCursor)
        change.setMinimumHeight(28)
        change.clicked.connect(lambda: self.open_books("settings"))
        book_row.addWidget(change)
        self.btn_change_book = change
        layout.addLayout(book_row)
        layout.addSpacing(6)

        layout.addWidget(self.reg(QLabel("词汇量测试—结果仅供参考"), "note", 12))
        test_row = QHBoxLayout()
        self.btn_history = QPushButton("历史记录")
        self.btn_history.clicked.connect(self._open_history_page)
        test_row.addWidget(self.btn_history)
        self.btn_continue = QPushButton("继续上次测试")
        self.btn_continue.clicked.connect(self.start_quiz)
        test_row.addWidget(self.btn_continue)
        self.btn_test = QPushButton("开始新的测试")
        self.btn_test.clicked.connect(self._test_from_settings)
        test_row.addWidget(self.btn_test)
        for button in (self.btn_history, self.btn_continue, self.btn_test):
            button.setObjectName("chip")
            button.setMinimumHeight(30)
        test_row.addStretch(1)
        layout.addLayout(test_row)
        layout.addSpacing(6)
        self.lab_storage = QLabel("")
        self.lab_storage.setWordWrap(True)
        self.lab_storage.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.reg(self.lab_storage, "note", 11))
        layout.addStretch(1)
        self.settings_page.setWidget(self.settings_body)
        self.root.addWidget(self.settings_page, 1)
        self.settings_page.hide()

    def _refresh_window_controls(self):
        if not hasattr(self, "window_ctl"):
            return
        size = self.window_ctl.normal_size
        current = (size.width(), size.height())
        for key, chip in self.size_chips.items():
            chip.setProperty("on", "1" if key == current else "0")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        enabled = self.window_ctl.edge_collapse_enabled
        self.btn_edge_collapse.setChecked(enabled)
        self.btn_edge_collapse.setText("小窗贴边收起：开" if enabled else "小窗贴边收起：关")
        self.btn_edge_collapse.setProperty("on", "1" if enabled else "0")
        self.btn_edge_collapse.style().unpolish(self.btn_edge_collapse)
        self.btn_edge_collapse.style().polish(self.btn_edge_collapse)

    def _set_edge_collapse(self, enabled):
        if not self._can_act():
            self._refresh_window_controls()
            return
        self.window_ctl.set_edge_collapse_enabled(bool(enabled))
        self._flush_window()
        self._refresh_window_controls()

    def _apply_window_size(self, width, height):
        self.window_ctl.set_normal_size(width, height)
        self._flush_window()
        self._refresh_settings()

    def _pref_snapshot(self, progress=None, names=RESET_PREF_KEYS):
        progress = self.progress if progress is None else progress
        return {name: {"present": name in progress,
                       "value": copy.deepcopy(progress.get(name))} for name in names}

    @staticmethod
    def _restore_pref_fields(progress, snapshot):
        for name, saved in snapshot.items():
            if saved["present"]:
                progress[name] = copy.deepcopy(saved["value"])
            else:
                progress.pop(name, None)

    def _recover_defaults_journal(self, progress):
        """A crash journal contains preferences only, never old learning records."""
        journal = progress.get(DEFAULTS_JOURNAL)
        if (not isinstance(journal, dict) or journal.get("schema") != 1
                or not isinstance(journal.get("window"), dict)
                or not isinstance(journal.get("preferences"), dict)):
            raise storage.StorageError("未完成的设置重置日志格式异常；学习记录未清空。")
        prefs = journal["preferences"]
        if any(name not in RESET_PREF_KEYS or not isinstance(value, dict)
               or not isinstance(value.get("present"), bool)
               or (value.get("present") and "value" not in value) for name, value in prefs.items()):
            raise storage.StorageError("设置重置日志的偏好格式异常；学习记录未清空。")
        storage.atomic_save(WIN_PATH, journal["window"])
        self._restore_pref_fields(progress, prefs)
        progress.pop(DEFAULTS_JOURNAL, None)
        try:
            storage.atomic_save(PROGRESS_PATH, progress)
        except storage.StorageError:
            progress[DEFAULTS_JOURNAL] = journal
            raise
        self.storage_notices.append("已恢复上次未完成的设置重置；学习与测试记录未回退。")

    def _sync_preference_attrs(self):
        self.study_mode = self.progress.get("study_mode", "brush")
        self.retry_gap = 3
        self.learning_settings = learn.normalize_settings(self.progress.get("learning_policy"))
        self.learning_settings["mode"] = learn.REVIEW_FIRST
        self.progress["learning_policy"] = self.learning_settings
        self.learning_policy = learn.LearningPolicy(self.learning_settings, self.daily_new_ledger)
        self.key_bindings = keys.load_bindings(self.progress.get("keybindings"))
        self.progress["keybindings"] = dict(self.key_bindings)
        self.theme_key = self.progress.get("theme") if self.progress.get("theme") in th.THEMES else th.DEFAULT
        self.t = th.get(self.theme_key)
        if self.study_engine is not None:
            self.study_engine.policy = self.learning_policy
            self.study_engine.retry_gap = 3

    def _apply_preference_ui(self):
        self._refresh_known()
        self._apply_scaling(force=True)
        self.catalog.set_palette(self.t)
        self.window_ctl.update_palette(self.t)
        self._refresh_key_hints()
        self._refresh_learning_status()
        self.catalog.set_metadata(self.states, known=None, predicted=self.known)
        self._refresh_settings()
        self.update()

    def _commit_preferences(self, changes):
        if not self._can_act():
            return False
        if DEFAULTS_JOURNAL in self.progress:
            try:
                self._recover_defaults_journal(self.progress)
            except storage.StorageError as error:
                QMessageBox.critical(self, "设置暂未保存", str(error))
                return False
        before = self._pref_snapshot(names=tuple(changes))
        for name, value in changes.items():
            self.progress[name] = copy.deepcopy(value)
        if "study_mode" in changes:
            self.study_mode = changes["study_mode"]
        try:
            self.save()
        except storage.StorageError as error:
            self._restore_pref_fields(self.progress, before)
            self._sync_preference_attrs()
            self._apply_preference_ui()
            QMessageBox.critical(self, "设置保存失败", "设置未改变，学习记录未清空。\n" + str(error))
            return False
        self._sync_preference_attrs()
        self._apply_preference_ui()
        return True

    def set_school_knowledge(self, level):
        if level != school.normalize(level):
            return False
        if level == school.normalize(self.progress.get("school_knowledge")):
            return True
        # A previously skipped word may be behind the cursor. Re-scan without
        # changing scheduler records, pending retries, or daily learning counts.
        old_records, old_cursors = copy.deepcopy(self.study_records), dict(self.cursors)
        for book_id, record in self.study_records.items():
            record["cursor"] = 0
            self.cursors[book_id] = 0
        if not self._commit_preferences({"school_knowledge": level}):
            for book_id, saved in old_records.items():
                self.study_records[book_id].clear()
                self.study_records[book_id].update(saved)
            self.cursors.clear()
            self.cursors.update(old_cursors)
            return False
        self._policy_changed_in_settings = True
        self._school_changed_in_settings = True
        return True

    def set_study_mode(self, mode):
        if mode not in ("brush", "choice"):
            return False
        return self._commit_preferences({"study_mode": mode})

    def set_learning_plan(self, mode=None, daily_new=None):
        candidate = dict(self.learning_settings)
        candidate["mode"] = learn.REVIEW_FIRST
        if mode == learn.DAILY_NEW_FIRST or daily_new is not None:
            candidate["daily_new"] = learn.DEFAULTS["daily_new"]
        if candidate == self.learning_settings:
            return True
        if self._commit_preferences({"learning_policy": candidate}):
            self._policy_changed_in_settings = True
            return True
        return False

    def apply_key_bindings(self, raw):
        try:
            normalized = keys.normalize(raw)
        except ValueError as error:
            self.lab_key_error.setText(str(error))
            return False
        if not self._commit_preferences({"keybindings": normalized}):
            self.lab_key_error.setText("键位未保存，原配置仍有效；可重试。")
            return False
        self._reset_key_draft()
        return True

    def open_key_settings(self):
        if self.key_dialog is not None and self.key_dialog.isVisible():
            self.key_dialog.raise_()
            self.key_dialog.activateWindow()
            return
        self._reset_key_draft()
        dialog = QDialog(self)
        dialog.setWindowTitle("键盘按键设置")
        dialog.setModal(True)
        dialog.setMinimumWidth(440)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(8)
        sections = (("刷词", (("remember", "认识"), ("forget", "不认识"))),
                    ("选择题", (("choice1", "选项 A"), ("choice2", "选项 B"),
                                  ("choice3", "选项 C"), ("choice4", "选项 D"),
                                  ("unknown", "不认识"))),
                    ("翻页", (("next", "下一张"),)))
        for title, actions in sections:
            heading = self.reg(QLabel(title), "note", 12)
            outer.addWidget(heading)
            for action, text in actions:
                row = QHBoxLayout()
                label = self.reg(QLabel(text), "note", 12)
                label.setMinimumWidth(100)
                row.addWidget(label)
                editor = self.key_edits[action]
                editor.setMinimumWidth(180)
                row.addWidget(editor, 1)
                outer.addLayout(row)
        note = self.reg(QLabel("点按输入框后按下新键位。同屏答案键不能重复；下一张可复用答案键。\n"
                               "Z 改判、Ctrl+Z 撤销、Esc / Tab 与窗口和编辑命令保留。"), "note", 11)
        note.setWordWrap(True)
        outer.addWidget(note)
        self.lab_key_error.setStyleSheet(th.label_qss(self.t, "note", 11))
        self.lab_key_error.setParent(dialog)
        self.lab_key_error.show()
        outer.addWidget(self.lab_key_error)
        buttons = QHBoxLayout()
        self.btn_restore_key_defaults = QPushButton("恢复默认键位")
        self.btn_restore_key_defaults.setObjectName("chip")
        self.btn_restore_key_defaults.setMinimumHeight(32)
        self.btn_restore_key_defaults.clicked.connect(self._restore_key_defaults)
        buttons.addWidget(self.btn_restore_key_defaults)
        buttons.addStretch(1)
        self.btn_cancel_keys = QPushButton("取消")
        self.btn_cancel_keys.setObjectName("chip")
        self.btn_cancel_keys.setMinimumHeight(32)
        self.btn_cancel_keys.clicked.connect(self._reset_key_draft)
        self.btn_cancel_keys.clicked.connect(dialog.reject)
        buttons.addWidget(self.btn_cancel_keys)
        self.btn_apply_keys = QPushButton("保存键位")
        self.btn_apply_keys.setObjectName("remember")
        self.btn_apply_keys.setMinimumHeight(32)
        self.btn_apply_keys.clicked.connect(self._apply_key_bindings)
        buttons.addWidget(self.btn_apply_keys)
        outer.addLayout(buttons)
        dialog.setStyleSheet(th.qss(self.t, getattr(self, "scale_factor", 1.0)))
        dialog.finished.connect(self._key_dialog_finished)
        self.key_dialog = dialog
        self._check_key_draft()
        for edit in self.key_edits.values():
            edit.setParent(dialog)
            edit.show()
        dialog.exec_()
        for edit in self.key_edits.values():
            edit.setParent(self)
            edit.hide()
        self.lab_key_error.setParent(self)
        self.lab_key_error.hide()

    def _key_dialog_finished(self, _result):
        self._reset_key_draft()
        self.btn_apply_keys = None
        self.key_dialog = None

    def _restore_key_defaults(self):
        for name, edit in self.key_edits.items():
            edit.blockSignals(True)
            edit.setKeySequence(QKeySequence(keys.DEFAULT_BINDINGS[name]))
            edit.blockSignals(False)
        self._check_key_draft()

    def _apply_key_bindings(self):
        ok = self.apply_key_bindings({name: edit.keySequence().toString(QKeySequence.PortableText)
                                      for name, edit in self.key_edits.items()})
        if ok and self.key_dialog is not None:
            self.key_dialog.accept()
        return ok

    def _check_key_draft(self, *_):
        draft = {name: edit.keySequence().toString(QKeySequence.PortableText)
                 for name, edit in self.key_edits.items()}
        try:
            keys.normalize(draft)
        except ValueError as error:
            self.lab_key_error.setText(str(error))
            if self.btn_apply_keys is not None:
                self.btn_apply_keys.setEnabled(False)
            return False
        self.lab_key_error.clear()
        if self.btn_apply_keys is not None:
            self.btn_apply_keys.setEnabled(True)
        return True

    def _reset_key_draft(self):
        for name, edit in self.key_edits.items():
            edit.blockSignals(True)
            edit.setKeySequence(QKeySequence(self.key_bindings[name]))
            edit.blockSignals(False)
        self._check_key_draft()

    def _confirm_restore_defaults(self):
        answer = QMessageBox.question(
            self, "恢复全部默认设置",
            "恢复背景、窗口、学习模式/安排及键位。\n"
            "不改变所选词书、学习状态/队列/词序游标/今日计数、词汇量测试记录。\n继续吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.restore_defaults()

    def restore_defaults(self):
        if not self._can_act():
            return False
        if DEFAULTS_JOURNAL in self.progress:
            try:
                self._recover_defaults_journal(self.progress)
            except storage.StorageError as error:
                QMessageBox.critical(self, "恢复默认未完成", str(error))
                return False
        before = self._pref_snapshot()
        old_window = copy.deepcopy(self.window_record)
        old_state = self.window_ctl.state()
        old_window.update(old_state)
        old_compact = self.window_ctl.compact
        journal = {"schema": 1, "preferences": before, "window": old_window}
        defaults = {"theme": th.DEFAULT, "study_mode": "brush", "retry_gap": 3,
                    "learning_policy": dict(learn.DEFAULTS),
                    "keybindings": dict(keys.DEFAULT_BINDINGS), "school_knowledge": "off"}
        self._window_save_timer.stop()
        self.progress[DEFAULTS_JOURNAL] = journal
        window_written = False
        try:
            self.save()                       # durable old-preference journal first
            self.window_ctl.restore({}, allow_compact=False)
            self._window_save_timer.stop()
            self._save_window()               # then the separate window file
            window_written = True
            self.progress.update(copy.deepcopy(defaults))
            self.progress.pop(DEFAULTS_JOURNAL, None)
            self._sync_preference_attrs()
            self.save()                       # committing new prefs clears journal atomically
        except storage.StorageError as error:
            self._restore_pref_fields(self.progress, before)
            self._sync_preference_attrs()
            self.window_ctl.restore(old_state, allow_compact=old_compact)
            self._window_save_timer.stop()
            self.window_record = old_window
            rollback_errors = []
            if window_written:
                try:
                    storage.atomic_save(WIN_PATH, old_window)
                except storage.StorageError as rollback:
                    rollback_errors.append(str(rollback))
            if rollback_errors:
                self.progress[DEFAULTS_JOURNAL] = journal
            else:
                self.progress.pop(DEFAULTS_JOURNAL, None)
            try:
                self.save()
            except storage.StorageError as rollback:
                self.progress[DEFAULTS_JOURNAL] = journal
                rollback_errors.append(str(rollback))
            self._apply_preference_ui()
            message = "恢复默认未完成，学习与测试记录未改变。\n" + str(error)
            if rollback_errors:
                message += "\n偏好回退尚待完成，下次启动会恢复；记录不会回退。\n" + "\n".join(rollback_errors)
            QMessageBox.critical(self, "恢复默认未完成", message)
            return False
        self._window_save_timer.stop()
        self._policy_changed_in_settings = True
        self._apply_preference_ui()
        self._reset_key_draft()
        return True

    # ---------- 主题 ----------
    def set_theme(self, key):
        return self._commit_preferences({"theme": key if key in th.THEMES else th.DEFAULT})

    def _gear_clicked(self):
        self.open_settings()

    def _refresh_back_control(self):
        self.back_slot.setVisible(self.mode in ("settings", "books", "catalog", "history"))
        self.btn_back.setVisible(
            self.mode in ("settings", "catalog", "history") or
            (self.mode == "books" and (self.books_src == "settings" or self.nav_level > 1)))

    def _page_back(self):
        if self.mode == "settings":
            self.close_settings()
        elif self.mode == "history":
            self.open_settings()
        elif self.mode == "catalog":
            if self.catalog.level_dialog is not None:
                self.catalog.level_dialog.close()
            self.open_settings() if self.catalog_src == "settings" else self._set_mode("books")
        elif self.mode == "books":
            if self.nav_level > 1:
                self._nav_back()
            elif self.books_src == "settings":
                self.open_settings()

    def open_catalog(self, book_id, src="settings"):
        if not self._can_act() or not book_id:
            return
        self.catalog_src = src
        mode = self.sel_order if src == "books" else stored_order(self.orders, book_id)
        words = self._order_words(self._book_words(book_id), mode, self._seed(book_id))
        self._refresh_known()
        self.catalog.set_palette(self.t)
        self.catalog.set_book(book_id, self._book_path(book_id), words, self.states,
                              None, preserve_order=(mode == "shuffle"),
                              predicted=self.known)
        self._set_mode("catalog")

    def open_settings(self):
        if not self._can_act():
            return
        if self.mode in ("front", "back", "empty", "choice", "choice_back"):
            self.pre_settings_mode = self.mode
            self.settings_study_mode_start = self.study_mode
            self._policy_changed_in_settings = False
        self._refresh_settings()
        if not self.progress.get("book_confirmed") and self.mode in ("books", "welcome"):
            self.pre_settings_mode = "front"
        self._set_mode("settings")

    def close_settings(self):
        if not self._can_act():
            return

        self._reset_key_draft()
        if not self.progress.get("book_confirmed"):
            self.open_books("welcome")
            return
        if self.mode == "settings" and not hasattr(self, "study_engine"):
            self.open_books("welcome")
            return
        mode = self.pre_settings_mode
        changed = self.study_mode != self.settings_study_mode_start
        school_changed = getattr(self, "_school_changed_in_settings", False)
        if self._policy_changed_in_settings and (mode in ("front", "choice", "empty") or school_changed):
            before = self._capture_study()
            try:
                self._make_engine()
                found = self._pull_new(persist=False)
                self.save()
            except storage.StorageError as error:
                self._study_save_error(error, before)
                return
            self._policy_changed_in_settings = False
            if found:
                self.qi = len(self.queue) - 1
                self._show_current()
            else:
                self._show_empty(persist=False)
        elif changed and mode in ("back", "choice_back"):
            self._next0()               # 这张卡已经提交，不能在另一模式再答一次
        elif changed and mode in ("front", "choice"):
            self._show_current()
        else:
            self._set_mode(mode if mode in ("front", "back", "empty", "choice", "choice_back") else "front")
        self._policy_changed_in_settings = False
        self._school_changed_in_settings = False

    def _test_from_settings(self):
        return self.start_quiz(fresh=True)

    def _confirm_new_quiz(self):
        if not self._can_act():
            return False
        answer = QMessageBox.question(
            self, "开始新的测试", "开始新测试会替换当前可续测会话，不会删除已保存历史。继续吗？",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return False
        return self.start_quiz(fresh=True)

    # ---------- 词书 / 进度 ----------
    def _stats(self):
        return self._book_stats(self.book_id)

    def _refresh_books(self):
        for bid, btn in self.book_btns.items():
            btn.setProperty("on", "1" if bid == self.sel_book else "0")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if self.sel_book:
            total = len(self._book_word_strs(self.sel_book))
            self.lab_book_stat.setText("%s · %s" %
                                       (self._book_path(self.sel_book), book_quantity(self._book_meta(self.sel_book), total)))
        else:
            self.lab_book_stat.clear()
        if self.mode == "books":
            self.status.clear()
            self.status.hide()
        self._refresh_back_control()
        for chip, mode in ((self.chip_seq, "seq"), (self.chip_shuffle, "shuffle")):
            chip.setProperty("on", "1" if mode == self.sel_order else "0")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self.btn_learn.setText("用这本书开始")
        self.btn_learn.setEnabled(bool(self.sel_book))
        self.btn_catalog_books.setEnabled(bool(self.sel_book))
        if self.btn_learn is not None:
            self.btn_learn.adjustSize()
        self.btn_catalog_books.adjustSize()
        if self.nav_level == 3 and self.sel_book in self.book_btns:
            try:
                self.book_scroll.ensureWidgetVisible(self.book_btns[self.sel_book], 0, 6)
            except Exception:
                pass

    def _pick_book(self, bid):
        self.sel_book = bid
        if not self._order_selection_explicit:
            self.sel_order = stored_order(self.orders, bid)
        self._refresh_books()

    def _set_order(self, mode):
        if mode not in ("seq", "shuffle"):
            return
        self.sel_order = mode
        self._order_selection_explicit = True
        self._refresh_books()

    def open_books(self, src="welcome"):
        self.books_src = src
        self._order_selection_explicit = False
        self.sel_book = self.book_id if src == "settings" else None
        self.sel_order = (self.order_mode if self.order_mode in ("seq", "shuffle")
                          else "seq") if self.sel_book else "seq"
        self.nav_level = 1
        self.nav_main = None
        self.nav_group = None
        self._build_nav_level()
        self._set_mode("books")

    def _start_learning(self):
        if not self.sel_book:
            return
        new_book = self.sel_book != self.book_id
        old_mode = (self.orders.get(self.sel_book) or {}).get("mode", "seq")
        if new_book:
            self.book_id = self.sel_book
            self.book_words = self._book_words(self.book_id)
        if new_book or self.sel_order != self.order_mode or self.sel_order != old_mode:
            self.order_mode = self.sel_order
            rec = self.orders.setdefault(self.book_id, {"mode": self.order_mode})
            rec["mode"] = self.order_mode
            if rec.get("seed") is None:
                rec["seed"] = random.randrange(1, 1 << 30)
            self.queue_words = self._order_words(self.book_words, self.order_mode, rec["seed"])
            self.cursor = 0
            self.cursors[self.book_id] = 0
            if old_mode != self.sel_order and self.book_id in self.study_records:
                record = self.study_records[self.book_id]
                record.update(cursor=0, current=None, held_current=None)
        else:
            self.cursor = self.cursors.get(self.book_id, 0)
        self.progress["book"] = self.book_id
        self.progress["book_confirmed"] = True
        self.progress["welcome_done"] = True
        self.progress.pop("quiz_from_welcome", None)
        self.sel_book = self.book_id
        self.save()
        self._new_session()

    # ---------- 首次引导 ----------
    def _startup(self, force=False):
        """Show onboarding or study; resumable sessions are explicit in settings."""
        session = self.progress.get("quiz_session")
        # Expiry disables continuation; retain its answers for history migration
        # or transactional archival when the user explicitly starts a new test.
        if self._quiz_remaining_days(session):
            self._new_session()
            return
        if not self.progress.get("book_confirmed"):
            self.open_books("welcome")            # 是否测试不等于已经确认词书
            return
        self._new_session()

    def welcome(self):
        # Kept for old progress paths; new installs open book selection directly.
        self._set_mode("welcome")

    def _welcome_test(self):
        return self.start_quiz()

    def _welcome_skip(self):
        self.progress["welcome_done"] = True
        self.progress["quiz_declined"] = True
        self.save()
        self.open_books("welcome")

    # ---------- 设置内容 ----------
    def _refresh_settings(self):
        self._refresh_window_controls()
        for key, button in self.study_mode_chips.items():
            button.setProperty("on", "1" if key == self.study_mode else "0")
            button.style().unpolish(button)
            button.style().polish(button)
        selected_school = school.normalize(self.progress.get("school_knowledge"))
        for key, button in self.school_chips.items():
            button.setProperty("on", "1" if key == selected_school else "0")
            button.style().unpolish(button)
            button.style().polish(button)
        self.lab_storage.setText("V%s" % VERSION)
        self.lab_storage.setToolTip("\n".join(self.storage_notices))
        learned, _, _, total, predicted = self._stats()
        path = self._book_path(self.book_id)
        self.lab_book.setText(path or "未选择词书")
        meta = self._book_meta(self.book_id) if self.book_id else {}
        note = meta.get("source_note")
        tooltip = [path, book_quantity(meta, total)] if self.book_id else []
        if isinstance(note, str) and note:
            tooltip.append(note)
        self.lab_book.setToolTip("\n".join(tooltip))
        self.lab_book_num.setText("已学 %s / %s" % (format(learned, ","), format(total, ","))
                                  if self.book_id else "")
        days = self._quiz_remaining_days()
        self.btn_continue.setText("继续上次测试（剩余%d天）" % days if days else "继续上次测试")
        self.btn_continue.setVisible(bool(days))
        if self.progress.get("quiz_session", {}).get("resume_disabled"):
            self.btn_continue.setVisible(False)
        for k, chip in self.theme_chips.items():
            chip.setProperty("on", "1" if k == self.theme_key else "0")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self._apply_scaling(force=True)

    def _open_history_page(self):
        if not self._can_act():
            return False
        session = self.progress.get("quiz_session")
        if (isinstance(session, dict) and isinstance(session.get("resp"), list)
                and session["resp"] and not session.get("history_deleted")):
            existing = next((row for row in self.progress.get("history", [])
                             if row.get("id") == session.get("id")), None)
            if existing is None or existing.get("total") != len(session["resp"]):
                before = self._capture_quiz()
                try:
                    if self._upsert_quiz_history(session=session) is not None:
                        self.save()      # Migrate a legacy answered snapshot atomically.
                except storage.StorageError as error:
                    self._restore_quiz(before)
                    QMessageBox.critical(self, "测试历史保存失败", str(error))
                    return False
        history = self.progress.get("history") or []
        self.history_chart.points = [(row["ts"], row["vocab"]) for row in history]
        self.history_chart.update()
        session = self.progress.get("quiz_session")
        if (isinstance(session, dict) and session.get("resume_disabled")
                and self._quiz_remaining_days(session) == 0):
            self.btn_continue.setVisible(False)
            self.btn_continue.setToolTip("最新测试记录已删除，不能继续上次测试")
        else:
            self.btn_continue.setToolTip("")

        def clear_rows(layout):
            while layout.count():
                item = layout.takeAt(0)
                widget, child = item.widget(), item.layout()
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
                elif child is not None:
                    clear_rows(child)
                    child.deleteLater()

        clear_rows(self.history_rows_layout)
        self.history_details = {}
        for idx, row in reversed(list(enumerate(history))):
            block = QVBoxLayout()
            block.setContentsMargins(0, 0, 0, 0)
            block.setSpacing(0)
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(0)
            summary_column = QVBoxLayout()
            summary_column.setContentsMargins(0, 0, 0, 0)
            summary_column.setSpacing(0)
            view = QPushButton("%s  平均 %s" % (
                time.strftime("%Y-%m-%d", time.localtime(row["ts"])), format(row["vocab"], ",")))
            view.setCheckable(True)
            view.setObjectName("historySummary")
            view.setFixedHeight(round(34 * self._ui_scale()))
            view._base_height, view._base_fixed = 34, True
            detail = QLabel("已测词数 %d · 误差 %s · 严谨度 %s" % (
                row.get("total", 0), self._measurement_error_text(row), row.get("rigor", 0)))
            detail.setWordWrap(True)
            detail.setObjectName("historyDetail")
            detail.hide()
            self.history_details[idx] = detail
            view.toggled.connect(detail.setVisible)
            summary_column.addWidget(view)
            summary_column.addWidget(detail)
            line.addLayout(summary_column, 1)
            delete = QPushButton("删除")
            delete.setObjectName("historyDelete")
            delete.setFixedHeight(round(34 * self._ui_scale()))
            delete._base_height, delete._base_fixed = 34, True
            delete.clicked.connect(lambda _=False, i=idx: self._delete_history(i))
            line.addWidget(delete, 0, Qt.AlignTop)
            block.addLayout(line)
            self.history_rows_layout.addLayout(block)
        self.history_rows_layout.addStretch(1)
        self._set_mode("history")

    def _delete_history(self, index):
        if not self._can_act():
            return
        history = self.progress.get("history") or []
        if not (0 <= index < len(history)):
            return
        before = self._capture_quiz()
        latest = max(range(len(history)), key=lambda i: (history[i].get("ts", 0), i))
        removed = history.pop(index)
        session = self.progress.get("quiz_session")
        if index == latest and isinstance(session, dict):
            session["resume_disabled"] = True
        if isinstance(session, dict) and (session.get("id") == removed.get("id")
                                         or session.get("history_id") == removed.get("id")):
            session["history_id"] = None
            if session.get("id") == removed.get("id"):
                session["history_deleted"] = True
                responses = session.get("resp", [])
                session["history_response_count"] = len(responses) if isinstance(responses, list) else 0
        try:
            self.save()
        except storage.StorageError as error:
            self._restore_quiz(before)
            QMessageBox.critical(self, "无法删除记录", str(error))
            return
        self.last_test = None
        self._refresh_settings()
        self._open_history_page()

    def _open_history(self, idx):
        hist = self.progress.get("history") or []
        if not (0 <= idx < len(hist)):
            return
        detail = getattr(self, "history_details", {}).get(idx)
        if detail is not None:
            detail.setVisible(detail.isHidden())

    def _result_primary(self):
        if self.result_ctx == "history":
            self.open_settings()
        elif self.result_ctx == "welcome_test":
            self.open_books("welcome")       # 首次引导的测试结束后先选词书
        else:
            self._leave_result()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if hasattr(self, "window_ctl") and self.window_ctl.paint_dock(painter):
            return
        path = QPainterPath()
        radius = min(18 * self._ui_scale(), self.width() / 2, self.height() / 2)
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, radius, radius)
        painter.fillPath(path, QColor(self.t["bg"]))
        painter.setPen(QColor(self.t["border"]))
        painter.drawPath(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "window_ctl"):
            self._window_changed()

    def closeEvent(self, event):
        if self._closed or not getattr(self, "_ready_for_close", True) or not hasattr(self, "_window_save_timer"):
            self._closed = True
            self._closing = False
            for timer in self.findChildren(QTimer):
                timer.stop()
            if hasattr(self, "window_ctl"):
                self.window_ctl.stop_timers()
            if hasattr(self, "fade"):
                self.fade.stop()
            event.accept()
            return
        self._closing = True
        active = [(timer, max(1, timer.remainingTime()))
                  for timer in self.findChildren(QTimer) if timer.isActive()]
        fade_running = self.fade.state() == self.fade.Running
        if fade_running:
            self.fade.pause()
        if hasattr(self, "window_ctl"):
            self.window_ctl.stop_timers()
        for timer, _ in active:
            timer.stop()
        try:
            self.save(force=True)
            self._save_window(force=True)
        except storage.StorageError as error:
            QMessageBox.critical(self, "记录保存失败", "请检查记录目录后重试。\n" + str(error))
            self._closing = False
            for timer, remaining in active:
                if timer.isSingleShot():
                    timer.start(remaining)
                else:
                    timer.start()
            if fade_running:
                self.fade.resume()
            event.ignore()
            return
        self._closed = True
        self._closing = False
        self.fade.stop()
        if self.catalog.level_dialog is not None:
            self.catalog.level_dialog.close()
        self.window_ctl.stop_timers()
        event.accept()

    # ---------- 模式 ----------
    def _set_mode(self, mode):
        if not self._can_act():
            return
        if hasattr(self, "window_ctl"):
            self.window_ctl.reveal()
        self.mode = mode
        brush = mode in ("front", "back", "empty")
        choices = mode in ("choice", "choice_back")
        study = brush or choices
        if hasattr(self, "window_ctl"):
            small = brush and self.study_mode == "brush" and self.window_ctl.preferred_compact
            self.window_ctl.set_compact(small, remember=False)
            self.compact = self.window_ctl.compact
        self.btn_min.setVisible(brush and self.study_mode == "brush")
        self.btn_gear.setVisible(mode not in ("settings", "books", "catalog", "history", "quiz", "result", "welcome")
                                  and not self.compact)
        self._refresh_back_control()
        # 学习页面（刷词/选择题）不显示左上角的状态文字；测试页保留进度与严谨度。
        self.status.setVisible(mode == "quiz" and not self.compact)
        self.page_title.setVisible(mode in ("settings", "books", "catalog", "history"))
        self.page_title.setText({"settings": "设置", "books": "选择词书", "catalog": "词书内容", "history": "历史记录"}.get(mode, ""))
        self.stage.setVisible(brush)
        self.front_bar.setVisible(mode == "front")
        self.back_bar.setVisible(mode in ("back", "empty"))
        self.choice_page.setVisible(choices)
        self.quiz_page.setVisible(mode == "quiz")
        self.result_page.setVisible(mode == "result")
        self.welcome_page.setVisible(mode == "welcome")
        self.books_page.setVisible(mode == "books")
        self.settings_page.setVisible(mode == "settings")
        self.catalog.setVisible(mode == "catalog")
        self.history_page.setVisible(mode == "history")
        self.btn_skip.setVisible(mode == "quiz")
        if mode == "books":
            self._refresh_books()
        elif mode in ("settings", "welcome", "catalog"):
            self.status.clear()
        if mode == "front":
            self.fade.stop()
            self.answer_effect.setOpacity(0.0)
        self._refresh_learning_status()
        self._refresh_key_hints()
        self._apply_scaling(force=True)

    def _show_current(self):
        item = self.queue[self.qi]
        word = item["w"]
        state = self.states.get(word["w"]) or {}
        try:
            level = int(state.get("lv", 0))
        except (TypeError, ValueError):
            level = 0
        caption = "复习 · 记忆等级 %d" % level if item["kind"] == "review" else "新词" + (" · 重现" if item["kind"] == "retry" else "")
        self.status.setText(caption)
        self.word.setText(word_caption(word))
        self.ipa.setText(pronunciation(word))
        self.meaning.setText(entry_meaning(word))
        self.meaning.setTextFormat(Qt.PlainText)
        self.btn_next.setText("下一个")
        self.corrected = False
        if self.study_mode == "choice":
            stage = self._book_level(self.book_id)
            if stage:
                try:
                    self.choice_question = study_options.make_options(
                        word, self._book_level_option_pool(self.book_id, stage), random)
                except ValueError:
                    # 当前书不足时只合并同一学段全部词书；绝不混入通用高级释义。
                    self.choice_question = study_options.make_options(
                        word, self._level_option_pool(stage), random)
            else:
                key = "phrase" if is_phrase(word) else "word"
                if key not in self._study_option_pools:
                    self._study_option_pools[key] = study_options.OptionPool(
                        self.phrases if key == "phrase" else self.bank)
                try:
                    self.choice_question = study_options.make_options(
                        word, self._study_option_pools[key], random)
                except ValueError:
                    if "all" not in self._study_option_pools:
                        self._study_option_pools["all"] = study_options.OptionPool(
                            self.all_entries)
                    self.choice_question = study_options.make_options(
                        word, self._study_option_pools["all"], random)
            self.choice_locked = False
            self.choice_word.setText(word_caption(word))
            self.choice_ipa.setText(pronunciation(word))
            self.choice_ipa.setVisible(bool(self.choice_ipa.text()))
            for index, button in enumerate(self.study_btns):
                caption = "%s  %s" % ("ABCD"[index], self.choice_question["options"][index])
                button.setProperty("_study_caption", caption)
                button.setText(caption)
                button.setProperty("state", "")
                button.setEnabled(True)
                button.style().unpolish(button)
                button.style().polish(button)
            self._refresh_key_hints()
            self.choice_hint.clear()
            self.choice_hint.hide()
            self.btn_study_dk.show()
            self.btn_study_next.hide()
            self._set_mode("choice")
            self.choice_page.verticalScrollBar().setValue(0)
        else:
            self._set_mode("front")

    def _show_back(self, word, remember):
        self.meaning.setText(entry_meaning(word))
        self.btn_wrong.setVisible(remember)
        self.btn_wrong.setEnabled(True)
        self._set_mode("back")
        self.fade.stop()
        self.answer_effect.setOpacity(0.0)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()

    def _empty_note(self):
        due = getattr(self, "waiting_due", None)
        now = time.time()
        if due is not None:
            minutes = max(1, math.ceil((due - now) / 60))
            text = "下次复习约 %d 分钟后\n到期会自动出现" % minutes
        else:
            text = "当前没有新词和到期词\n可在设置中查看或更换词书"
        if self.meaning.text() != text:
            self.meaning.setText(text)
            self._apply_scaling(force=True)

    def _show_empty(self, persist=True):
        if persist:
            self.save()
        self.waiting_due = self.study_engine.next_due_time() if self.study_engine else None
        self._due_timer.start()
        self.fade.stop()
        self.status.clear()
        self.word.setText(self._book_name(self.book_id))
        self.ipa.clear()
        self._set_mode("empty")
        self._empty_note()
        self.answer_effect.setOpacity(1.0)
        self.btn_wrong.hide()
        self.btn_next.setText(self._key_caption("检查复习", "next"))

    # ---------- 学习流程 ----------
    def _capture_study(self):
        return {"states": copy.deepcopy(self.states),
                "record": copy.deepcopy(self.study_record),
                "cursor": self.cursor, "cursors": copy.deepcopy(self.cursors),
                "qi": self.qi, "book": self.book_id,
                "queue": list(self.queue), "last_action": self.last_action,
                "corrected": self.corrected,
                "daily_new_ledger": copy.deepcopy(self.daily_new_ledger),
                "last_answer_time": self._last_answer_time}

    def _snapshot(self):
        self.snapshot = self._capture_study()

    def _restore_snapshot(self, snapshot=None, transient=False):
        snapshot = snapshot if snapshot is not None else self.snapshot
        if not snapshot or snapshot["book"] != self.book_id:
            return False
        self.states.clear()
        self.states.update(copy.deepcopy(snapshot["states"]))
        self.study_record.clear()
        self.study_record.update(copy.deepcopy(snapshot["record"]))
        if "daily_new_ledger" in snapshot:
            self.daily_new_ledger.clear()
            self.daily_new_ledger.update(copy.deepcopy(snapshot["daily_new_ledger"]))
        self._last_answer_time = snapshot.get("last_answer_time")
        self.cursor, self.qi = snapshot["cursor"], snapshot["qi"]
        if "cursors" in snapshot:
            self.cursors.clear()
            self.cursors.update(copy.deepcopy(snapshot["cursors"]))
        else:
            self.cursors[self.book_id] = self.cursor
        self.queue = list(snapshot["queue"])
        if transient:
            self.last_action = snapshot["last_action"]
            self.corrected = snapshot["corrected"]
        self._make_engine()
        return True

    def _study_save_error(self, error, before):
        self._restore_snapshot(before, transient=True)
        QMessageBox.critical(self, "记录保存失败", "未推进这张卡片，原记录未清空。\n" + str(error))

    def _answer_current(self, remember):
        if not self._can_act():
            return False
        previous_snapshot = self.snapshot
        self._snapshot()
        item = self.queue[self.qi]
        self.corrected = False
        try:
            answered_at = time.time()
            self.study_engine.answer(item, remember, answered_at)
            self._last_answer_time = answered_at
            self.cursor = self.study_engine.cursor
            self.cursors[self.book_id] = self.cursor
            self.last_action = (item["kind"], item["w"]["w"], remember)
            self.save()
        except (storage.StorageError, ValueError) as error:
            self._study_save_error(error, self.snapshot)
            self.snapshot = previous_snapshot
            return False
        return True

    def act(self, action):
        if self.mode != "front" or not self.queue:
            return
        remember = action == "remember"
        if action not in ("remember", "forget", "fuzzy"):
            return
        if self._answer_current(remember):
            self._show_back(self.queue[self.qi]["w"], remember)

    def _study_answer(self, chosen):
        if self.mode != "choice" or self.choice_locked or not self.choice_question:
            return
        if chosen not in (-1, 0, 1, 2, 3):
            return
        correct = self.choice_question["correct"]
        remember = chosen == correct
        if not self._answer_current(remember):
            return
        self.choice_locked = True
        for index, button in enumerate(self.study_btns):
            button.setEnabled(False)
            button.setProperty("state", "correct" if index == correct else
                               "wrong" if index == chosen else "")
            button.style().unpolish(button)
            button.style().polish(button)
        # 正误由选项状态体现；不另显示等级或重现规则，也不保留提示占位。
        self.choice_hint.clear()
        self.choice_hint.hide()
        self.btn_study_dk.hide()
        self.btn_study_next.show()
        self._set_mode("choice_back")

    def correct(self):
        """把刚才的认识改为不认识，回滚原回答计数后重答。"""
        if (not self._can_act() or not self.last_action or not self.last_action[2]
                or self.corrected or self.mode not in ("back", "choice_back") or not self.snapshot):
            return
        before = self._capture_study()
        introduced_at = self._last_answer_time
        if not self._restore_snapshot():
            return
        item = self.queue[self.qi]
        try:
            self.study_engine.answer(item, False, time.time(), introduced_at=introduced_at)
            self._last_answer_time = introduced_at
            self.cursor = self.study_engine.cursor
            self.cursors[self.book_id] = self.cursor
            self.corrected = True
            self.last_action = (item["kind"], item["w"]["w"], False)
            self.qi += 1
            found = self._pull_new(persist=False)
            self.save()
        except storage.StorageError as error:
            self._study_save_error(error, before)
            return
        self.btn_wrong.setEnabled(False)
        if found:
            self.qi = len(self.queue) - 1
            self._show_current()
        else:
            self._show_empty(persist=False)

    def _next(self):
        if not self._can_act():
            return
        if self.mode == "empty":
            before = self._capture_study()
            previous_snapshot = self.snapshot
            try:
                self._new_session()
            except storage.StorageError as error:
                self.snapshot = previous_snapshot
                self._study_save_error(error, before)
        elif self.mode in ("back", "choice_back"):
            self._next0()

    def _next0(self):
        if not self._can_act():
            return
        before = self._capture_study()
        try:
            self.qi += 1
            if not self._pull_new():
                self._show_empty()
                return
        except storage.StorageError as error:
            self._study_save_error(error, before)
            return
        self.qi = len(self.queue) - 1
        self._show_current()

    def undo(self):
        if not self._can_act() or self.mode not in ("front", "back", "choice", "choice_back", "empty"):
            return
        before = self._capture_study()
        if not self._restore_snapshot():
            return
        try:
            self.save()
        except storage.StorageError as error:
            self._study_save_error(error, before)
            return
        self.snapshot = None
        self.last_action = None
        self._show_current()

    # ---------- 词汇量测试 ----------
    def _need_test(self):
        if self.progress.get("quiz_session"):
            return True
        hist = self.progress.get("history") or []
        return False

    def _maybe_start_test(self):
        """兼容旧调用：等价于启动引导流程。"""
        self._startup()

    def _capture_quiz(self):
        """只复制测验可变图，保留原容器引用；不复制其它学习记录。"""
        names = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "rigor",
                 "quiz_locked", "theta", "known", "last_test", "mode",
                 "_quiz_retry_action", "quiz_started_at", "quiz_last_answer_at", "quiz_session_id",
                 "quiz_origin_welcome", "quiz_bank_fingerprint", "quiz_vocab_grid",
                 "quiz_item_indices", "quiz_result", "quiz_return_to_settings", "quiz_status_values")
        attrs = {name: getattr(self, name) for name in names if hasattr(self, name)}
        progress_refs = dict(self.progress)
        keys = ("quiz_session", "history", "theta", "quiz_from_welcome",
                "snooze_until", "welcome_done")
        graph = {"attrs": attrs,
                 "progress": {key: self.progress[key] for key in keys if key in self.progress}}
        originals = {}

        def collect(value):
            if not isinstance(value, (dict, list, set, tuple)) or id(value) in originals:
                return
            originals[id(value)] = value
            values = list(value.keys()) + list(value.values()) if isinstance(value, dict) else value
            for child in values:
                collect(child)

        collect(graph)
        memo = {}
        copy.deepcopy(graph, memo)       # 同一次复制保留 session/state/items/resp 的共享关系
        return {"names": names, "attrs": attrs, "progress_ref": self.progress,
                "progress_refs": progress_refs,
                "containers": [(value, memo.get(id(value), value))
                               for value in originals.values()]}

    def _restore_quiz(self, before):
        # 把快照的子节点重新接到原容器，而不是用深拷贝替换整份 progress。
        links = {id(saved): original for original, saved in before["containers"]}

        def original_value(value):
            return links.get(id(value), value)

        for original, saved in before["containers"]:
            if isinstance(original, dict):
                original.clear()
                original.update((original_value(key), original_value(value))
                                for key, value in saved.items())
            elif isinstance(original, list):
                original[:] = [original_value(value) for value in saved]
            elif isinstance(original, set):
                original.clear()
                original.update(original_value(value) for value in saved)
        self.progress = before["progress_ref"]
        self.progress.clear()
        self.progress.update(before["progress_refs"])
        for name in before["names"]:
            if name in before["attrs"]:
                setattr(self, name, before["attrs"][name])
            elif hasattr(self, name):
                delattr(self, name)

    def _set_quiz_retry(self, action):
        self._quiz_retry_action = action
        self.btn_skip.setText("重试保存并继续" if action else "结束本次测试")
        tips = {"next": "只重试保存下一题，不会重复计算已提交的答案。",
                "finish": "只重试保存本次结果，不会重复添加测试历史。",
                "start": "重试开始或恢复本次测试，原进度仍然保留。",
                "start_new": "重试开始新的测试；保存成功前保留原会话和历史。",
                "skip": "重试保存并结束本次测试。"}
        self.btn_skip.setToolTip(tips.get(action, "结束本次测试；未答题目不会计入结果。"))
        if action:
            self.btn_skip.setEnabled(True)
            self.btn_skip.show()

    def _quiz_save_error(self, error, before, retry_action):
        self._restore_quiz(before)
        self.quiz_timer.stop()          # 明确重试；不能让残留回调再次推进
        if retry_action in ("next", "finish"):
            self.quiz_locked = True    # 上题已经提交，只能重试推进，不能重答
        self._set_quiz_retry(retry_action)
        QMessageBox.critical(self, "测试记录保存失败",
                             "本次操作未提交，原答题与历史记录已恢复。\n" + str(error))

    def retry_or_skip(self, checked=False):
        if not self._can_act():
            return False
        action = getattr(self, "_quiz_retry_action", None)
        if action == "start":
            return self.start_quiz()
        if action == "start_new":
            return self.start_quiz(fresh=True)
        if action == "next":
            return self._quiz_next()
        if action == "finish":
            return self._finish_quiz()
        if action == "skip":
            return self.skip_test()
        if self.mode == "quiz":
            return self.skip_test()
        return False

    def start_quiz(self, checked=False, *, fresh=False):
        if not self._can_act():
            return False
        before = self._capture_quiz()
        self.quiz_timer.stop()
        retry_action = "start_new" if fresh else "start"
        item_indices = {entry.get("w"): idx for idx, entry in enumerate(self.bank)}

        def number(value):
            try:
                return (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and math.isfinite(value))
            except (TypeError, ValueError, OverflowError):
                return False

        def valid_session(session, allow_expired=False):
            if (not isinstance(session, dict) or session.get("algo") != "bayes-v140"
                    or session.get("bank_id") != self.bank_fingerprint
                    or not isinstance(session.get("id"), str) or not session["id"]
                    or not number(session.get("started_at"))
                    or (not allow_expired and not self._quiz_remaining_days(session))
                    or not number(session.get("rigor")) or not 0 <= session["rigor"] <= 105):
                return False
            state, items, responses, index = (session.get(key) for key in ("state", "items", "resp", "i"))
            if (not isinstance(state, dict) or not isinstance(items, list)
                    or not isinstance(responses, list) or type(index) is not int
                    or index < 0 or len(items) != index + 1
                    or len(responses) not in (index, index + 1)):
                return False
            # Both snapshots are legal: the current question is unanswered, or
            # its answer was committed before the 650ms advancement timer ran.
            if (type(state.get("level")) is not int or not 0 <= state["level"] <= pl.TOP_LEVEL
                    or type(state.get("seed")) is not int or not number(state.get("theta", 0.0))
                    or any(type(state.get(key, 0)) is not int or not 0 <= state.get(key, 0) <= limit
                           for key, limit in (("up", 105), ("down", 105), ("wrong_streak", 12)))
                    or type(state.get("fast", False)) is not bool
                    or not isinstance(state.get("asked"), list)
                    or any(not isinstance(key, str) or key not in item_indices for key in state["asked"])
                    or len(state["asked"]) != len(set(state["asked"]))
                    or any(type(response) is not int or response not in (-1, 0, 1) for response in responses)):
                return False
            keys = set()
            asked = set(state["asked"])
            for record in items:
                if not isinstance(record, dict):
                    return False
                key, item = record.get("key"), record.get("item")
                if (not isinstance(key, str) or key not in item_indices or key not in asked
                        or key in keys or not isinstance(item, dict)):
                    return False
                options, correct = item.get("options"), item.get("correct_index")
                if (not isinstance(options, list) or len(options) != 4 or type(correct) is not int
                        or not 0 <= correct < 4
                        or any(not isinstance(option, dict) or not isinstance(option.get("text"), str)
                               for option in options)):
                    return False
                keys.add(key)
            return True

        try:
            self.quiz_return_to_settings = (self.mode == "settings" or
                                            (self.mode == "result" and getattr(self, "result_ctx", None) == "history"))
            self.progress.pop("quiz_declined", None)
            self.progress["welcome_done"] = True
            if self.mode == "welcome" or not self.progress.get("book_confirmed"):
                self.progress["quiz_from_welcome"] = True
            sess = self.progress.get("quiz_session")
            self.quiz_item_indices = item_indices
            resumable = valid_session(sess)
            if fresh or not resumable:
                # Archive a valid answered legacy snapshot before replacing it.
                # This is part of the same commit as the new first question.
                if (valid_session(sess, allow_expired=True) and sess["resp"]
                        and not sess.get("history_deleted")):
                    old_row = next((row for row in self.progress.get("history", [])
                                    if row.get("id") == sess["id"]), None)
                    if old_row is None or old_row.get("total") != len(sess["resp"]):
                        self._upsert_quiz_history(session=sess)
                self.progress.pop("quiz_session", None)
                sess = None
            if sess:
                self.quiz_state = sess["state"]
                self.quiz_items = sess["items"]
                self.quiz_resp = sess["resp"]
                self.quiz_i = sess["i"]
                self.rigor = sess["rigor"]
                self.quiz_started_at = sess["started_at"]
                self.quiz_session_id = sess["id"]
                self.quiz_bank_fingerprint = sess["bank_id"]
                self.quiz_vocab_grid = pl.build_profile(self.bank)
                self.quiz_origin_welcome = bool(sess.get("from_welcome"))
                if len(self.quiz_resp) == self.quiz_i + 1:
                    self.mode = "quiz"
                    self.quiz_locked = True
                    return self._quiz_next(before=before, retry_action=retry_action)
            else:
                self.quiz_state = pl.new_session(seed=random.randrange(1, 1 << 30))
                self.quiz_state["theta"] = 0.0
                self.quiz_items = []
                self.quiz_resp = []
                self.quiz_i = 0
                self.rigor = 100.0
                self.quiz_started_at = int(time.time())
                self.quiz_session_id = os.urandom(16).hex()
                self.quiz_origin_welcome = self.mode == "welcome" or not self.progress.get("book_confirmed")
                self.quiz_vocab_grid = pl.build_profile(self.bank)
                self.quiz_bank_fingerprint = self.bank_fingerprint
            if len(self.quiz_items) <= self.quiz_i and self._gen_item() is None:
                raise storage.StorageError("词库无法生成无歧义选项，无法开始测试。")
            self._save_quiz_session()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, retry_action)
            return False
        self._set_quiz_retry(None)
        self._set_mode("quiz")
        self._quiz_show()
        return True

    def _gen_item(self):
        """Select a unique stable-key item; skip entries lacking unambiguous options."""
        asked = {self.quiz_item_indices[key] for key in self.quiz_state["asked"]
                 if key in self.quiz_item_indices}
        while True:
            rng = random.Random(self.quiz_state["seed"] * 1000003 + len(asked))
            idx = pl.pick_idx(self.lvls, self.quiz_state["level"], asked, rng, self.bs,
                              self.quiz_state.get("theta", 0.0))
            if idx is None:
                return None
            item = pl.make_item(self.bank, idx, rng, self.bs)
            key = self.bank[idx]["w"]
            asked.add(idx)
            self.quiz_item_indices[key] = idx
            if item is None:
                self.quiz_state["asked"].append(key)
                continue
            record = {"key": key, "item": item, "lvl": self.quiz_state["level"]}
            self.quiz_items.append(record)
            self.quiz_state["asked"].append(key)
            return record

    def _quiz_remaining_days(self, session=None, now=None):
        """Days left in this attempt; resuming never renews started_at."""
        session = self.progress.get("quiz_session") if session is None else session
        if not isinstance(session, dict) or session.get("resume_disabled"):
            return 0
        started = session.get("started_at")
        try:
            if (not isinstance(started, (int, float)) or isinstance(started, bool)
                    or not math.isfinite(started)):
                return 0
            now = time.time() if now is None else now
            if not math.isfinite(now):
                return 0
            seconds = RESUME_TTL - (now - started)
            return min(30, max(0, int(math.ceil(seconds / 86400))))
        except (TypeError, ValueError, OverflowError):
            return 0

    def _quiz_history_record(self, completed=False, session=None):
        """A measurement for every answered attempt, without adopting mastery."""
        if session is not None:
            # Older answered snapshots can be archived without entering quiz mode.
            if (not isinstance(session, dict) or session.get("algo") != "bayes-v140"
                    or session.get("bank_id") != self.bank_fingerprint
                    or not isinstance(session.get("id"), str) or not session["id"]
                    or not isinstance(session.get("resp"), list)
                    or not isinstance(session.get("items"), list)
                    or len(session["items"]) < len(session["resp"])
                    or any(type(response) is not int or response not in (-1, 0, 1)
                           for response in session["resp"])):
                return None
            try:
                if any(not isinstance(session.get(key), (int, float)) or isinstance(session[key], bool)
                       or not math.isfinite(session[key]) for key in ("started_at", "rigor")):
                    return None
                if not 0 <= session["rigor"] <= 105:
                    return None
            except (TypeError, ValueError, OverflowError):
                return None
            measured = session["items"][:len(session["resp"])]
            if any(not isinstance(item, dict) or not isinstance(item.get("key"), str)
                   or item["key"] not in self.quiz_item_indices for item in measured):
                return None
            if len({item["key"] for item in measured}) != len(measured):
                return None
        responses = self.quiz_resp if session is None else session["resp"]
        if not responses:
            return None
        items = self.quiz_items if session is None else session["items"]
        rigor = int(round(self.rigor if session is None else session["rigor"]))
        session_id = self.quiz_session_id if session is None else session["id"]
        started = self.quiz_started_at if session is None else session["started_at"]
        bs = [self.bs[self.quiz_item_indices[item["key"]]] for item in items[:len(responses)]]
        measurement = pl.measurement_summary(bs, responses, self.bs)
        estimate, low, high = (measurement[key] for key in ("estimate", "low", "high"))
        theta, se = measurement["theta"], measurement["se"]
        history = self.progress.get("history") or []
        existing = next((row for row in history if row.get("id") == session_id), None)
        baseline = bool(existing.get("baseline")) if existing else not any(row.get("baseline") for row in history)
        timestamp = int(time.time())
        if session is not None:
            saved_time = session.get("updated_at", started)
            try:
                timestamp = int(saved_time) if isinstance(saved_time, (int, float)) and not isinstance(saved_time, bool) else int(started)
            except (TypeError, ValueError, OverflowError):
                timestamp = int(started)
        if existing and existing.get("total") == len(responses) and not completed:
            timestamp = existing.get("ts", timestamp)
        right = sum(response == 1 for response in responses)
        return {
            "id": session_id, "ts": timestamp, "started_at": started,
            "algo": "bayes-v140", "theta": round(theta, 4), "se": round(se, 4),
            "vocab": int(round(estimate)), "rigor": rigor,
            "lo": max(0, int(round(low))), "hi": int(round(high)),
            "err": round(measurement["err"], 1) if measurement["err"] is not None else None,
            "measurement_schema": 2, "provisional": measurement["provisional"],
            "evidence_limited": measurement["evidence_limited"],
            "estimate_available": measurement["estimate_available"],
            "right": right, "dontknow": sum(response < 0 for response in responses),
            "total": len(responses), "baseline": baseline, "completed": bool(completed),
            "prediction_eligible": right > 0 and len(responses) >= PREDICTION_MIN_N and rigor >= PREDICTION_MIN_RIGOR,
        }

    def _upsert_quiz_history(self, completed=False, session=None):
        if not self._can_act():
            return None
        record = self._quiz_history_record(completed=completed, session=session)
        if record is None:
            return None
        history = self.progress.setdefault("history", [])
        existing = next((row for row in history if row.get("id") == record["id"]), None)
        if existing is None:
            history.append(record)
        else:
            existing.update(record)       # Preserve the row and unrecognized metadata.
            record = existing
        self.last_test = (record, bool(record["baseline"]))
        meta = self.progress.get("quiz_session") if session is None else session
        if isinstance(meta, dict):
            meta["history_id"] = record["id"]
            meta["history_response_count"] = record["total"]
            meta["history_deleted"] = False
        return record

    def _save_quiz_session(self):
        if not self._can_act():
            return False
        sess = self.progress.get("quiz_session")
        if not isinstance(sess, dict):
            sess = {}
            self.progress["quiz_session"] = sess
        previous_count = sess.get("history_response_count", 0)
        if type(previous_count) is not int:
            previous_count = 0
        sess.update({
            "schema": 1, "algo": "bayes-v140", "id": self.quiz_session_id,
            "bank_id": self.quiz_bank_fingerprint,
            "started_at": self.quiz_started_at, "updated_at": int(time.time()),
            "from_welcome": self.quiz_origin_welcome,
            "state": self.quiz_state, "items": self.quiz_items,
            "resp": self.quiz_resp, "i": self.quiz_i, "rigor": self.rigor,
        })
        if self.quiz_resp and (not sess.get("history_deleted") or len(self.quiz_resp) > previous_count):
            self._upsert_quiz_history()
        self.save()                      # Answer, session and history commit together.
        return True

    def skip_test(self):
        """Pause for later; settings entry returns to settings, not study."""
        if not self._can_act() or self.mode != "quiz":
            return False
        before = self._capture_quiz()
        self.quiz_timer.stop()
        try:
            self._save_quiz_session()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, "skip")
            return False
        self._set_quiz_retry(None)
        if getattr(self, "quiz_return_to_settings", False):
            self.open_settings()
        else:
            self._startup()
        return True

    def _test_bank_exhausted(self):
        return len(self.quiz_state.get("asked", [])) >= len(self.bank)

    @staticmethod
    def _measurement_error_text(record):
        if not record or record.get("err") is None:
            return "样本不足"
        if record.get("measurement_schema") == 2 and record.get("evidence_limited"):
            return "样本不足"
        return "±%s%%" % (("%.1f" % record["err"]).rstrip("0").rstrip("."))

    def _quiz_status(self, delta=None):
        """Four fragments; the score becomes literal 'max' at 105, not '/105'."""
        initial = not self.quiz_resp
        record = next((row for row in self.progress.get("history", [])
                       if row.get("id") == self.quiz_session_id and row.get("total") == len(self.quiz_resp)), None)
        if initial:
            record = None
        elif record is None:
            record = self._quiz_history_record()  # A deleted history row must not erase the live measurement.
        values = {"id": self.quiz_session_id, "vocab": record["vocab"] if record else None,
                  "err": 100 if initial else (record.get("err") if record else None),
                  "rigor": float(self.rigor)}
        previous = getattr(self, "quiz_status_values", None)
        comparable = isinstance(previous, dict) and previous.get("id") == self.quiz_session_id
        green, red = (("#79e0ac", "#ef9cad") if getattr(self, "theme_key", None) == "dark"
                      else ("#177245", "#b82c3c"))

        def colored(key, text):
            old = previous.get(key) if comparable else None
            if old is not None and values[key] is not None and values[key] != old:
                improved = values[key] < old if key == "err" else values[key] > old
                color = green if improved else red
                return "<span style='color:%s'>%s</span>" % (color, text)
            return text

        rigor = "max" if values["rigor"] >= 105 else ("%.1f" % values["rigor"]).rstrip("0").rstrip(".")
        error_text = "100%" if initial else self._measurement_error_text(record)
        if error_text == "样本不足":
            values["err"] = None
        shown = "-" if values["vocab"] is None or (record and record.get("estimate_available") is False) else str(values["vocab"])
        self.status.setText("词汇量测试 · 词目量%s · 误差%s · 严谨度%s" % (
            colored("vocab", shown),
            colored("err", error_text), colored("rigor", rigor)))
        self.status.setToolTip("按词库独立词条估计，不额外乘以时态、复数等变形数；词库已有的变形词条可能单独计入。\n"
                               "暂估依赖保守先验与词频难度假设，未经标准化校准；少量回答不能证明掌握总量。\n"
                               "误差为模型95%区间相对估计值的最大偏差，不是答题错误率或准确率保证。")
        if isinstance(previous, dict):
            previous.update(values)
        else:
            self.quiz_status_values = values

    def _quiz_show(self):
        record = self.quiz_items[self.quiz_i]
        item = record["item"]
        w = self.bank[self.quiz_item_indices[record["key"]]]
        if not w.get("display_w"):
            # 显示拼写可能来自当前词书的浅拷贝（通用 bank 仍保留稳定 w）。
            for candidate in (getattr(self, "book_words", ()) or ()):
                if (candidate.get("w") == w.get("w") and candidate.get("display_w")
                        and not candidate.get("_school_caption")):
                    w = candidate
                    break
        self.quiz_word.setText(word_caption(w))
        self._quiz_status()
        for i, b in enumerate(self.opt_btns):
            caption = "%s  %s" % (LETTERS[i], item["options"][i]["text"])
            b.setProperty("_quiz_caption", caption)
            b.setText(caption)
            b.setEnabled(True)
            b.setProperty("state", "")
            b.style().unpolish(b)
            b.style().polish(b)
        self.btn_dontknow.setEnabled(True)
        self.btn_dontknow.setProperty("state", "")
        self.btn_dontknow.style().unpolish(self.btn_dontknow)
        self.btn_dontknow.style().polish(self.btn_dontknow)
        self.quiz_locked = False
        self._refresh_key_hints()
        self._fit_choice_options(self._ui_scale())
        self.quiz_page.verticalScrollBar().setValue(0)

    def _quiz_answer(self, choice):
        """choice: 0..3 选项，-1 = 不知道；保存成功后才显示反馈。"""
        if (not self._can_act() or self.mode != "quiz" or self.quiz_locked
                or len(self.quiz_resp) != self.quiz_i):
            return False
        before = self._capture_quiz()
        self.quiz_timer.stop()
        item = self.quiz_items[self.quiz_i]["item"]
        correct = item["correct_index"]
        good = choice >= 0 and choice == correct
        try:
            self.quiz_locked = True
            if choice < 0:
                self.quiz_resp.append(-1)
                delta = -1.0
            elif good:
                self.quiz_resp.append(1)
                delta = 1.5
            else:
                self.quiz_resp.append(0)
                delta = -3.0
            old = self.rigor
            self.rigor = pl.update_rigor(self.rigor, self.quiz_resp[-1])
            delta = self.rigor - old
            pl.step(self.quiz_state, good, len(self.quiz_resp), self.quiz_resp[-1])
            bs = [self.bs[self.quiz_item_indices[entry["key"]]]
                  for entry in self.quiz_items[:len(self.quiz_resp)]]
            self.quiz_state["theta"] = pl.measurement_summary(bs, self.quiz_resp, self.bs)["theta"]
            self.quiz_last_answer_at = int(time.time())
            self._save_quiz_session()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, before["attrs"].get("_quiz_retry_action"))
            return False
        self._set_quiz_retry(None)
        self._quiz_status(delta)
        for i, b in enumerate(self.opt_btns):
            b.setEnabled(False)
            state = ""
            if i == correct:
                state = "correct"
            elif i == choice:
                state = "wrong"
            b.setProperty("state", state)
            b.style().unpolish(b)
            b.style().polish(b)
        self.btn_dontknow.setEnabled(False)
        self.btn_dontknow.setProperty("state", "pressed" if choice < 0 else "")
        self.btn_dontknow.style().unpolish(self.btn_dontknow)
        self.btn_dontknow.style().polish(self.btn_dontknow)
        self.quiz_timer.start(650)
        return True

    def _quiz_next(self, before=None, retry_action="next"):
        if not self._can_act() or self.mode != "quiz":
            return False
        self.quiz_timer.stop()          # 手动推进/重试后，旧 single-shot 不能再推进一次
        if len(self.quiz_resp) != self.quiz_i + 1:
            return False               # 仅推进已答题；迟到回调不能跳过未答题
        before = before if before is not None else self._capture_quiz()
        finish_action = retry_action if retry_action in ("start", "start_new") else "finish"
        if self._test_bank_exhausted():
            return self._finish_quiz(before=before, retry_action=finish_action)
        try:
            item_count = len(self.quiz_items)
            item = self._gen_item()
            if item is None:
                return self._finish_quiz(before=before, retry_action=finish_action)
            self.quiz_i = item_count
            self._save_quiz_session()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, retry_action)
            return False
        self._set_quiz_retry(None)
        # Normal advancement stays on the quiz page; avoid repolishing the
        # entire application on every question. A cold resume still switches
        # pages after its next-question snapshot has committed successfully.
        if before["attrs"].get("mode") != "quiz":
            self._set_mode("quiz")
        self._quiz_show()
        return True

    def _finish_quiz(self, before=None, retry_action="finish"):
        if (not self._can_act() or self.mode != "quiz" or not self.quiz_items
                or len(self.quiz_items) != len(self.quiz_resp) or not self.progress.get("quiz_session")):
            return False
        self.quiz_timer.stop()
        before = before if before is not None else self._capture_quiz()
        try:
            rec = self._upsert_quiz_history(completed=True)
            self.progress.pop("quiz_session", None)
            self.progress.pop("quiz_from_welcome", None)
            self.save()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, retry_action)
            return False
        self._set_quiz_retry(None)
        self.quiz_result = rec
        self._show_result(rec, bool(rec["baseline"]), self.quiz_origin_welcome)
        return True

    def _set_theta(self, theta):
        """记下决定「测试判定已会」的 θ（基准测试 / 手排时用）。"""
        self.theta = float(theta)
        self.progress["theta"] = self.theta
        self._refresh_known()

    def _fill_result(self, rec, hist, is_baseline):
        base = next((h for h in hist if h.get("baseline")), None)
        prevs = [h for h in hist if h is not rec]
        prev = prevs[-1] if prevs else None

        vocab_text = "-" if rec.get("estimate_available") is False else format(rec["vocab"], ",")
        self.res_big.setText("≈ %s 词目" % vocab_text)
        self.res_sub.setText("严谨度 %d  ·  误差 %s\n模型95%%区间 %s – %s 词目（非准确率保证）" % (
            rec.get("rigor", 100), self._measurement_error_text(rec),
            format(rec.get("lo", rec["vocab"]), ","),
            format(rec.get("hi", rec["vocab"]), ",")))
        line = "答对 %d/%d" % (rec["right"], rec["total"])
        if rec.get("dontknow"):
            line += "  ·  不认识 %d 题" % rec["dontknow"]

        tail = ""
        if self.book_id:
            _, known, _, total, predicted = self._book_stats(self.book_id)
            tail = "%s已会 %s / %s" % (self._book_short_name(self.book_id),
                                       format(known, ","), format(total, ","))

        if is_baseline:
            known_n = rec.get("known", len(self.known))
            to_learn = rec.get("to_learn", len(self.bank) - known_n)
            self.res_note.setText("%s\n大词库判定已会 %s 个、剩 %s 个%s" %
                                  (line, format(known_n, ","), format(to_learn, ","),
                                   "；" + tail if tail else ""))
        else:
            delta = rec["vocab"] - (base["vocab"] if base else rec["vocab"])
            d2 = rec["vocab"] - (prev["vocab"] if prev else rec["vocab"])
            sign = "+" if delta >= 0 else ""
            sign2 = "+" if d2 >= 0 else ""
            self.res_note.setText("%s\n比首次 %s%s 词 · 比上次 %s%s 词%s" %
                                  (line, sign, format(delta, ","), sign2, format(d2, ","),
                                   " · " + tail if tail else ""))

        self.chart.points = [(h["ts"], h["vocab"]) for h in hist][-12:]
        self.chart.update()

    def _show_result(self, rec, is_baseline, from_welcome=False):
        from_welcome = from_welcome or not self.progress.get("book_confirmed")
        self.quiz_result = rec
        self.result_ctx = "welcome_test" if from_welcome else "test"
        self.btn_start.setText("选择词书" if from_welcome else "继续背单词")
        self.btn_rebase.setVisible(not is_baseline and bool(rec.get("prediction_eligible")))
        days = self._quiz_remaining_days()
        self.btn_continue_quiz.setText("继续上次测试（剩余%d天）" % days if days else "继续上次测试")
        self.btn_continue_quiz.setVisible(bool(days))
        self._fill_result(rec, self.progress.get("history", []), is_baseline)
        self._set_mode("result")

    def _show_history(self, rec, upto):
        self.result_ctx = "history"
        self.quiz_result = rec
        self.btn_start.setText("返回设置")
        self.btn_rebase.hide()
        days = self._quiz_remaining_days()
        self.btn_continue_quiz.setText("继续上次测试（剩余%d天）" % days if days else "继续上次测试")
        self.btn_continue_quiz.setVisible(bool(days))
        self._fill_result(rec, upto, bool(rec.get("baseline")))
        self._set_mode("result")

    def _apply_prediction(self):
        """Apply one of the explicit predicted-mastery strategies to eligible words."""
        rec = self.quiz_result or (self.last_test[0] if self.last_test else None)
        if not rec or not rec.get("prediction_eligible"):
            QMessageBox.information(self, "暂不可预测", "需要至少 50 个回答，且严谨度达到 60。")
            return False
        dialog = QDialog(self)
        dialog.setWindowTitle("预测掌握范围")
        layout = QVBoxLayout(dialog)
        mode = QPushButton("保守 · 估计减误差")
        median = QPushButton("按估计")
        high = QPushButton("宽松 · 估计加误差")
        strategy_group = QButtonGroup(dialog)
        strategy_group.setExclusive(True)
        for button in (mode, median, high):
            button.setCheckable(True)
            strategy_group.addButton(button)
            layout.addWidget(button)
        mode.setChecked(True)
        controls = QHBoxLayout()
        confirm = QPushButton("应用")
        cancel = QPushButton("取消")
        controls.addStretch(1)
        controls.addWidget(cancel)
        controls.addWidget(confirm)
        layout.addLayout(controls)
        chosen = []
        mode.clicked.connect(lambda: chosen.__setitem__(slice(None), ["conservative"]))
        median.clicked.connect(lambda: chosen.__setitem__(slice(None), ["estimate"]))
        high.clicked.connect(lambda: chosen.__setitem__(slice(None), ["optimistic"]))
        confirm.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        if not dialog.exec_() or not chosen:
            return False
        strategy = chosen[0]
        target = pred.apply_strategy(rec["vocab"], (rec["hi"] - rec["lo"]) / 2, strategy)
        selected, counts = pred.select_prediction_candidates(
            self.bank, self.states, target, bands={entry["w"]: entry["lvl"] for entry in self.bank},
            rejected=self.prediction_data["rejected"], excluded=self.prediction_data["excluded"], seed=rec["id"])
        prior = copy.deepcopy(self.prediction_data)
        previous = set(self.prediction_data["selected"])
        explicitly_returned = set(self.prediction_data["excluded"])
        self.prediction_data["excluded"] = sorted(explicitly_returned | (previous - selected))
        self.prediction_data["selected"] = sorted(selected)
        self.prediction_data["effective"] = {key: counts[key] for key in ("target", "available", "selected")}
        self.prediction_data["strategy"] = strategy
        self.prediction_data["source_history_id"] = rec["id"]
        try:
            self.save()
        except storage.StorageError as error:
            self.prediction_data.clear()
            self.prediction_data.update(prior)
            QMessageBox.critical(self, "预测未保存", str(error))
            return False
        self._refresh_known()
        self.catalog.set_metadata(self.states, known=set(), predicted=self.known)
        self._new_session()
        return True

    def _bulk_learn_selected(self, keys_to_learn):
        if not self._can_act():
            return False
        states_before = copy.deepcopy(self.states)
        pred_before = copy.deepcopy(self.prediction_data)
        for key in keys_to_learn:
            if key in self.known:
                self.known.discard(key)
                if key in self.prediction_data["selected"]:
                    self.prediction_data["selected"].remove(key)
                if key not in self.prediction_data["excluded"]:
                    self.prediction_data["excluded"].append(key)
            state = self.states.get(key)
            if state and (state.get("st") in ("mastered", "retired") or int(state.get("lv", 0)) >= 10):
                state["st"] = "new"
                state["lv"] = 0
                state["due"] = None
        self.prediction_data["effective"]["selected"] = len(self.prediction_data["selected"])
        try:
            self.save()
        except storage.StorageError as error:
            self.states.clear()
            self.states.update(states_before)
            self.prediction_data.clear()
            self.prediction_data.update(pred_before)
            self._refresh_known()
            QMessageBox.critical(self, "未加入学习", str(error))
            return False
        self.catalog.set_metadata(self.states, known=set(), predicted=self.known)
        return True

    def _rebase(self):
        return self._apply_prediction()

    def _leave_result(self):
        self._new_session()

    # ---------- 键盘 ----------
    def _refresh_learning_status(self, now=None):
        if not hasattr(self, "study_status"):
            return
        parts = []
        study = self.mode in ("front", "back", "empty", "choice", "choice_back")
        if study and self.mode != "empty" and self.queue and 0 <= self.qi < len(self.queue):
            kind = self.queue[self.qi]["kind"]
            parts.append("新词" if kind == "new" else "复习")
        self.study_status.setText(" · ".join(parts))
        if not hasattr(self, "window_ctl") or not (self.window_ctl.collapsed or self.window_ctl.animating):
            self.study_status.setVisible(study and bool(parts))

    def _brush_correction_page(self):
        return self.mode == "back" and bool(self.last_action and self.last_action[2])

    def _key_caption(self, text, action):
        if action == "next":
            hint = "enter" if self._brush_correction_page() else "空格/enter"
            binding = self.key_bindings[action]
            if binding not in ("Space", "Enter"):
                hint += "/" + keys.caption(binding)
            return text + " [%s]" % hint
        return text + "  [%s]" % keys.caption(self.key_bindings[action])

    def _refresh_key_hints(self):
        if not hasattr(self, "btn_remember"):
            return
        self.btn_remember.setText(self._key_caption("认识", "remember"))
        self.btn_forget.setText(self._key_caption("不认识", "forget"))
        self.btn_wrong.setText(self._key_caption("选错了", "forget"))
        self.btn_next.setText(self._key_caption("再看看" if self.mode == "empty" else "下一个", "next"))
        self.btn_study_next.setText(self._key_caption("下一个", "next"))
        self.btn_study_dk.setText(self._key_caption("不认识", "unknown"))
        self.btn_dontknow.setText(self._key_caption("不认识", "unknown"))
        for group, prop in ((self.study_btns, "_study_caption"), (self.opt_btns, "_quiz_caption")):
            for index, button in enumerate(group):
                base = button.property(prop)
                if isinstance(base, str):
                    button.setText(self._key_caption(base, "choice%d" % (index + 1)))
                button.setShortcut(QKeySequence())

    @staticmethod
    def _editor_has_focus():
        widget = QApplication.focusWidget()
        while widget is not None:
            if isinstance(widget, (QLineEdit, QAbstractSpinBox, QKeySequenceEdit, QTextEdit, QPlainTextEdit)):
                return True
            widget = widget.parentWidget()
        return False

    def _dispatch_study_key(self, ev):
        if not self._can_act() or ev.isAutoRepeat() or self._editor_has_focus():
            return
        k, mods = ev.key(), ev.modifiers()
        if k == Qt.Key_Escape and mods == Qt.NoModifier:
            self.close()
            return
        if k == Qt.Key_Z and mods == Qt.ControlModifier and self.mode != "quiz":
            self.undo()
            return
        if k == Qt.Key_Z and mods == Qt.NoModifier:
            self.correct()
            return
        phase = ("brush" if self.mode == "front" else "choice" if self.mode in ("choice", "quiz")
                 else "back" if self.mode in ("back", "empty", "choice_back") else None)
        if self._brush_correction_page():
            # 认识后的反面保留“不认识/选错了”键，不能被下一词别名抢占。
            if keys.event_action(ev, self.key_bindings, "brush") == "forget":
                self.correct()
                return
            if k == Qt.Key_Space:
                return
        action = keys.event_action(ev, self.key_bindings, phase)
        if action in ("remember", "forget"):
            self.act(action)
        elif action == "next":
            self._next()
        elif action == "unknown" or (action and action.startswith("choice")):
            selected = -1 if action == "unknown" else int(action[-1]) - 1
            if self.mode == "quiz":
                self._quiz_answer(selected)
            else:
                self._study_answer(selected)

    def eventFilter(self, watched, event):
        if watched in getattr(self, "_window_buttons", ()) and not self._editor_has_focus():
            if event.type() == QEvent.KeyPress:
                self.keyPressEvent(event)
                event.accept()
                return True
            if event.type() == QEvent.KeyRelease and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                event.accept()
                return True
        if (watched in getattr(self, "_learning_buttons", ())
                and self.mode in ("front", "back", "empty", "choice", "choice_back", "quiz")
                and not self._editor_has_focus()):
            if event.type() == QEvent.KeyPress:
                self._dispatch_study_key(event)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, ev):
        if not self._can_act():
            return
        if self.mode in ("front", "back", "empty", "choice", "choice_back", "quiz"):
            self._dispatch_study_key(ev)
            ev.accept()
            return
        k = ev.key()
        if self._editor_has_focus():
            super().keyPressEvent(ev)
            return
        if self.mode in ("catalog", "history"):
            if k == Qt.Key_Escape:
                self._page_back()
            return
        if self.mode == "result":
            if k in (Qt.Key_Space, Qt.Key_Return):
                self._result_primary()
            elif k == Qt.Key_Escape:
                self.close()
            return
        if self.mode == "settings":
            if k == Qt.Key_Escape:
                self.close_settings()
            return
        if self.mode == "books":
            if k == Qt.Key_Escape:
                self._nav_back()
            return
        if self.mode == "welcome":
            if k == Qt.Key_Escape:
                self.close()
            return
        super().keyPressEvent(ev)


def main():
    set_windows_app_id()
    app = QApplication(sys.argv)
    configure_application_icon(app)
    destructive_debug = {"--seed", "--history", "--chart", "--result", "--back"}
    if destructive_debug.intersection(sys.argv) and not os.environ.get("VOCABAPP_DATA_DIR"):
        QMessageBox.critical(None, "调试需隔离资料", "造数据和自动答题只能在显式设置 VOCABAPP_DATA_DIR 的隔离目录中运行。\n默认学习记录未读取或修改。")
        sys.exit(1)
    directory = storage.data_dir(ROOT)
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as error:
        QMessageBox.critical(None, "无法访问记录目录", str(error))
        sys.exit(1)
    instance_lock = QLockFile(os.path.join(directory, "vocab-app.lock"))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        if instance_lock.error() == QLockFile.LockFailedError:
            QMessageBox.information(None, "背单词已在运行", "同一记录目录只能打开一个窗口。\n请检查现有窗口或屏幕边缘的小条。")
            sys.exit(0)
        QMessageBox.critical(None, "无法锁定记录目录", "请检查目录权限：\n" + directory)
        sys.exit(1)
    try:
        w = Card()
    except Exception as error:
        traceback.print_exc()
        QMessageBox.critical(None, "无法安全启动", "原记录没有清空，请先备份并检查记录文件。\n" + str(error))
        instance_lock.unlock()
        sys.exit(1)

    def report_error(exc_type, error, tb):
        traceback.print_exception(exc_type, error, tb)
        QMessageBox.critical(w, "操作未完成", "原记录未清空。\n" + str(error))
    sys.excepthook = report_error
    w.show()
    w.raise_()
    w.activateWindow()

    def _auto_quiz(good=True, dk=True):
        w.quiz_timer.stop()
        if w.mode != "quiz" and not w.start_quiz():
            return
        if len(w.quiz_resp) == w.quiz_i + 1:
            if not w._quiz_next():
                return
        while w.mode == "quiz":
            i = len(w.quiz_resp)
            if i >= len(w.quiz_items):
                return
            record = w.quiz_items[w.quiz_i]
            it = record["item"]
            b = w.bs[w.quiz_item_indices[record["key"]]]
            correct = it["correct_index"]
            if dk and i % 7 == 3:
                choice = -1
            elif good and b < 0.25:
                choice = correct
            elif good and b < 0.9:
                choice = correct if i % 3 else (correct + 1) % 4
            else:
                choice = (correct + 1) % 4
            if not w._quiz_answer(choice):
                return
            if w._test_bank_exhausted():
                w._finish_quiz()
                return
            if not w._quiz_next():
                return

    def _seed():
        """调试用：造点历史记录和学习进度，方便截设置页。"""
        now = int(time.time())
        w.progress["history"] = [
            {"ts": now - 90 * 86400, "vocab": 5200, "right": 18, "dontknow": 9,
             "total": 50, "theta": 0.1, "se": 0.5, "baseline": True,
             "known": 3200, "to_learn": 12012, "rigor": 88, "err": 9.0,
             "lo": 4732, "hi": 5668},
            {"ts": now - 60 * 86400, "vocab": 7100, "right": 22, "dontknow": 7,
             "total": 50, "theta": 0.4, "se": 0.5, "baseline": False,
             "rigor": 92, "err": 8.0, "lo": 6532, "hi": 7668},
            {"ts": now - 30 * 86400, "vocab": 8600, "right": 25, "dontknow": 6,
             "total": 50, "theta": 0.8, "se": 0.5, "baseline": False,
             "rigor": 94, "err": 7.0, "lo": 7998, "hi": 9202},
        ]
        states = w.progress["states"]
        for i, wd in enumerate(w.bank[:160]):
            st = "mastered" if i < 40 else "learning"
            states[wd["w"]] = {"st": st, "lv": 10 if st == "mastered" else 3,
                               "due": None if st == "mastered" else now + 3600,
                               "seen": 5, "lapse": 0, "streak": 0}
        w.states = states
        w._set_theta(0.8)
        w.progress["welcome_done"] = True
        if not w.book_id:
            w._pick_book(bk.DEFAULT)
            w._start_learning()
        w.save()

    for _a in list(sys.argv):
        if _a.startswith("--theme="):
            _k = _a.split("=", 1)[1]
            QTimer.singleShot(900, lambda k=_k: w.set_theme(k))

    if "--seed" in sys.argv:
        QTimer.singleShot(250, _seed)
    if "--welcome" in sys.argv:
        def _show_welcome():
            w.progress["welcome_done"] = False
            w.welcome()
        QTimer.singleShot(900, _show_welcome)
    if "--books" in sys.argv:
        QTimer.singleShot(900, lambda: w.open_books("welcome"))
    if "--settings" in sys.argv:
        QTimer.singleShot(900, w.open_settings)
    if "--history" in sys.argv:
        def _show_history():
            _seed()
            w._open_history(1)
        QTimer.singleShot(900, _show_history)

    if "--compact" in sys.argv:
        QTimer.singleShot(900, w.toggle_compact)
    if "--back" in sys.argv:
        QTimer.singleShot(900, lambda: w.act("remember"))
    if "--quiz" in sys.argv:
        QTimer.singleShot(900, w.start_quiz)
    if "--result" in sys.argv:
        QTimer.singleShot(900, lambda: _auto_quiz(True, True))
    if "--chart" in sys.argv:
        def _seed_then_quiz():
            _seed()
            _auto_quiz(True, False)
        QTimer.singleShot(900, _seed_then_quiz)
    try:
        result = app.exec_()
    finally:
        instance_lock.unlock()
    sys.exit(result)


if __name__ == "__main__":
    main()
