# -*- coding: utf-8 -*-
"""极简背单词卡片（PyQt5）

学习：自由节奏，先复习后新词；卡片上只有单词，点完才淡入释义。
首次打开：先推荐做词汇量测试（也可以跳过，直接选词书开始学）。
设置（⚙）：背景风格 / 词汇量测试入口与历史记录 / 词书与已学进度。
"""
import sys, os, io, json, time, copy, math, random, warnings, traceback

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QRect, QLockFile
from PyQt5.QtGui import (QPainter, QColor, QPainterPath, QPen, QFont, QFontMetrics)
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                             QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect,
                             QScrollArea, QSizePolicy, QLayout,
                             QMessageBox, QStyle, QStyleOptionButton)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import scheduler as sch
import placement as pl
import theme as th
import books as bk
import storage
from study_queue import StudyQueue, _count as _queue_count
from windowing import WindowController
from catalog import BookCatalog
from entries import is_phrase, meaning as entry_meaning, pronunciation, memory_info
import study_options
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
VERSION = "1.3.3"

COMPACT_QSS = """
QPushButton { font-size: 15px; padding: 4px 12px; border-radius: 12px; }
QPushButton#bar { font-size: 13px; }
QPushButton#wrong { font-size: 14px; }
"""

CARD_W, CARD_H = 520, 430
# 设置里的常用窗口尺寸；恢复默认回到 520×430，仍受当前屏幕工作区限制。
WINDOW_PRESETS = ((520, 430, "小巧"), (640, 520, "标准"), (760, 620, "大窗"))
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


def mean_h(i, scale=1.0):
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(round(F_MEAN[i] * scale))
    return QFontMetrics(f).lineSpacing() * MEAN_LINES
QUIZ_N = 50
THRESHOLD = pl.KNOWN_THRESHOLD
TEST_INTERVAL = 30 * 86400        # 每满 30 天再测一次
SKIP_SNOOZE = 86400               # 跳过本次：明天再问
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

    def __init__(self, points, parent=None):
        super().__init__(parent)
        self.points = points
        self.setMinimumHeight(168)
        self.set_palette(th.get(th.DEFAULT))

    def set_palette(self, t):
        self.c = dict(bg=t["chart_bg"], grid=t["chart_grid"], text=t["chart_text"],
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
        self.bs = [x["b"] for x in self.bank]
        self.lvls = [x["lvl"] for x in self.bank]
        self.theta = self.progress.get("theta")
        self.known = set()
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

    def _book_words(self, book_id):
        return [self.bank_map[w] for w in self._book_word_strs(book_id) if w in self.bank_map]

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
                        "group": gid, "series": series,
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
        """用最近一次测试的 θ 算「测试判定已会」的词（跨书共享）。"""
        theta = self.progress.get("theta")
        self.theta = theta
        if theta is None:
            self.known = set()
            return
        self.known = {w["w"] for w, b in zip(self.bank, self.bs)
                      if pl.p_know(theta, b) >= pl.KNOWN_THRESHOLD}

    def _book_stats(self, book_id):
        learned = mastered = known = 0
        words = self._book_word_strs(book_id)
        for key in words:
            category, _, _ = memory_info(key, self.states, self.known)
            if category == "mastered":
                learned += 1
                mastered += 1
            elif category == "known":
                known += 1
                if key in self.states:
                    learned += 1
        return learned, known, mastered, len(words)

    # ---------- 当前词书实时队列；记忆状态在不同词书间共享 ----------
    def _make_engine(self):
        self.study_record = self.study_records.setdefault(
            self.book_id, {"cursor": self.cursors.get(self.book_id, 0)})
        self.study_engine = StudyQueue(self.queue_words, self.states, self.study_record,
                                      retry_gap=self.retry_gap, known=self.known)
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
        if not self._can_act() or self.mode != "empty" or not self.study_engine:
            return
        if self.window_ctl.collapsed:
            return
        waiting = getattr(self, "waiting_due", None)
        if waiting is None or time.time() < waiting:
            if waiting is not None:
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
        self._save_window()

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
            self.setStyleSheet(self._base_qss + (COMPACT_QSS if self.compact else ""))
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
            self.back_slot.setFixedSize(round(22 * scale), round(20 * scale))
            self.btn_close.setFixedSize(round(20 * scale), round(20 * scale))
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
        top.addStretch(1)
        self.btn_skip = QPushButton("跳过本次测试")
        self.btn_skip.setObjectName("link")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.clicked.connect(self.retry_or_skip)
        top.addWidget(self.btn_skip)
        self.btn_skip.hide()
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("close")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_close)
        self.root.addLayout(top)

        self.reg(self.page_title, "title", 15)
        self.reg(self.status, "note", 12)

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
        self.btn_forget.setObjectName("forget")
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
        self.btn_next = QPushButton("下一个  →")
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
        self.btn_study_next = QPushButton("下一个  →")
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
        self.btn_dontknow = QPushButton("不认识")
        self.btn_dontknow.setObjectName("dontknow")
        self.btn_dontknow.setCursor(Qt.PointingHandCursor)
        self.btn_dontknow.setMinimumHeight(38)
        self.btn_dontknow.clicked.connect(lambda: self._quiz_answer(-1))
        qv.addWidget(self.btn_dontknow)
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
        self.btn_rebase = QPushButton("以这次结果重排学习队列")
        self.btn_rebase.setObjectName("link")
        self.btn_rebase.setCursor(Qt.PointingHandCursor)
        self.btn_rebase.clicked.connect(self._rebase)
        self.btn_retest = QPushButton("重新测试")
        self.btn_retest.setObjectName("link")
        self.btn_retest.setCursor(Qt.PointingHandCursor)
        self.btn_retest.clicked.connect(self.start_quiz)
        links.addStretch(1)
        links.addWidget(self.btn_rebase)
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
        self.btn_learn = QPushButton("用这本开始")
        self.btn_learn.setEnabled(False)
        self.btn_learn.setObjectName("remember")
        self.btn_learn.setCursor(Qt.PointingHandCursor)
        self.btn_learn.setMinimumHeight(40)
        self.btn_learn.setMinimumWidth(132)
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
        text = "%s　%s 词" % (it.get("display") or it["name"], format(it["count"], ","))
        self._add_nav_row(text, it["id"],
                          lambda _=False, bid=it["id"]: self._pick_book(bid), "book")

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

        layout.addWidget(self.reg(QLabel("背景风格"), "note", 12))
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
            button = QPushButton("%s %d×%d" % (name, width, height))
            button.setObjectName("chip")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(30)
            button.clicked.connect(lambda _=False, w=width, h=height:
                                   self._apply_window_size(w, h))
            sizes.addWidget(button)
            self.size_chips[(width, height)] = button
        self.btn_defaults = QPushButton("恢复默认")
        self.btn_defaults.setObjectName("chip")
        self.btn_defaults.setCursor(Qt.PointingHandCursor)
        self.btn_defaults.setMinimumHeight(30)
        self.btn_defaults.setToolTip("恢复窗口尺寸、主题和学习模式；不清空学习记录和测试历史")
        self.btn_defaults.clicked.connect(self.restore_defaults)
        sizes.addWidget(self.btn_defaults)
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

        layout.addWidget(self.reg(QLabel("词汇量测试"), "note", 12))
        test_row = QHBoxLayout()
        self.lab_vocab = QLabel("")
        test_row.addWidget(self.reg(self.lab_vocab, "mean", 14))
        test_row.addStretch(1)
        self.btn_test = QPushButton("开始测试")
        self.btn_test.setObjectName("chip")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.setMinimumHeight(28)
        self.btn_test.clicked.connect(self._test_from_settings)
        test_row.addWidget(self.btn_test)
        layout.addLayout(test_row)
        layout.addWidget(self.reg(QLabel("历史记录（点一条看结果，完整历史保留）"), "note", 11))
        self.hist_box = QWidget()
        self.hist_layout = QVBoxLayout(self.hist_box)
        self.hist_layout.setContentsMargins(0, 0, 0, 0)
        self.hist_layout.setSpacing(2)
        layout.addWidget(self.hist_box)
        layout.addSpacing(6)
        self.lab_storage = QLabel("")
        self.lab_storage.setWordWrap(True)
        self.lab_storage.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.reg(self.lab_storage, "note", 11))
        layout.addStretch(1)
        self.settings_page.setWidget(self.settings_body)
        self.root.addWidget(self.settings_page, 1)
        self.settings_page.hide()

    def _apply_window_size(self, width, height):
        self.window_ctl.set_normal_size(width, height)
        self._save_window()
        self._refresh_settings()

    def set_study_mode(self, mode):
        if mode not in ("brush", "choice"):
            return
        self.study_mode = mode
        self.save()
        self._refresh_settings()

    def restore_defaults(self):
        self.study_mode = "brush"
        self.retry_gap = 3
        if self.study_engine is not None:
            self.study_engine.retry_gap = 3
        self.window_ctl.restore({}, allow_compact=False)
        self.set_theme(th.DEFAULT)
        self._save_window()
        self._refresh_settings()

    # ---------- 主题 ----------
    def set_theme(self, key):
        self.theme_key = key if key in th.THEMES else th.DEFAULT
        self.t = th.get(self.theme_key)
        self.progress["theme"] = self.theme_key
        self.save()
        self._apply_scaling(force=True)
        self.catalog.set_palette(self.t)
        self.window_ctl.update_palette(self.t)
        self._refresh_settings()
        self.update()

    def _gear_clicked(self):
        if self.mode == "settings":
            self.close_settings()
        else:
            self.open_settings()

    def _refresh_back_control(self):
        self.back_slot.setVisible(self.mode in ("settings", "books", "catalog"))
        self.btn_back.setVisible(
            self.mode in ("settings", "catalog") or
            (self.mode == "books" and (self.books_src == "settings" or self.nav_level > 1)))

    def _page_back(self):
        if self.mode == "settings":
            self.close_settings()
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
        self.catalog.set_palette(self.t)
        self.catalog.set_book(book_id, self._book_path(book_id), words, self.states, self.known)
        self._set_mode("catalog")

    def open_settings(self):
        if not self._can_act():
            return
        if self.mode in ("front", "back", "empty", "choice", "choice_back"):
            self.pre_settings_mode = self.mode
            self.settings_study_mode_start = self.study_mode
        self._refresh_settings()
        self._set_mode("settings")

    def close_settings(self):
        if not self._can_act():
            return
        if not self.progress.get("book_confirmed"):
            self.open_books("welcome")
            return
        mode = self.pre_settings_mode
        changed = self.study_mode != self.settings_study_mode_start
        if changed and mode in ("back", "choice_back"):
            self._next0()               # 这张卡已经提交，不能在另一模式再答一次
        elif changed and mode in ("front", "choice"):
            self._show_current()       # 未回答时仍是同一个 current
        else:
            self._set_mode(mode if mode in ("front", "back", "empty", "choice", "choice_back") else "front")

    def _test_from_settings(self):
        return self.start_quiz()

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
            self.lab_book_stat.setText("%s · %s 词" %
                                       (self._book_path(self.sel_book), format(total, ",")))
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
        self.btn_learn.setText("用这本开始")
        self.btn_learn.setEnabled(bool(self.sel_book))
        self.btn_catalog_books.setEnabled(bool(self.sel_book))
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
        """显示窗口前决定入口：续测 / 首次引导 / 待选书 / 到期测试 / 学习。"""
        if self.progress.get("quiz_session"):
            self.start_quiz()                     # 上次测到一半，直接接着来
            return
        if not self.progress.get("welcome_done"):
            self.welcome()
            return
        if not self.progress.get("book_confirmed"):
            self.open_books("welcome")            # 是否测试不等于已经确认词书
            return
        allow_test = force or "--nottest" not in sys.argv
        declined = self.progress.get("quiz_declined") and not self.progress.get("history")
        snoozed = self.progress.get("snooze_until", 0) > time.time()
        if allow_test and not declined and not snoozed and self._need_test():
            self.start_quiz()
            return
        self._new_session()

    def welcome(self):
        self._set_mode("welcome")

    def _welcome_test(self):
        return self.start_quiz()        # 引导标记和题目必须在同一个事务里保存

    def _welcome_skip(self):
        self.progress["welcome_done"] = True
        self.progress["quiz_declined"] = True
        self.save()
        self.open_books("welcome")

    # ---------- 设置内容 ----------
    def _refresh_settings(self):
        if hasattr(self, "window_ctl"):
            size = self.window_ctl.normal_size
            current = (size.width(), size.height())
            for key, chip in self.size_chips.items():
                chip.setProperty("on", "1" if key == current else "0")
                chip.style().unpolish(chip)
                chip.style().polish(chip)
        for key, button in self.study_mode_chips.items():
            button.setProperty("on", "1" if key == self.study_mode else "0")
            button.style().unpolish(button)
            button.style().polish(button)
        location = "V%s" % VERSION
        if self.storage_notices:
            location += "\n" + "\n".join(self.storage_notices)
        self.lab_storage.setText(location)
        learned, _, _, total = self._stats()
        path = self._book_path(self.book_id)
        self.lab_book.setText(path or "未选择词书")
        self.lab_book.setToolTip(path)
        self.lab_book_num.setText("已学 %s / %s" % (format(learned, ","), format(total, ","))
                                  if self.book_id else "")
        hist = self.progress.get("history") or []
        if hist:
            last = hist[-1]
            self.lab_vocab.setText("上次 ≈ %s 词（%s）" %
                                   (format(last["vocab"], ","),
                                    time.strftime("%Y-%m-%d", time.localtime(last["ts"]))))
        else:
            self.lab_vocab.setText("还没测过")
        self.btn_test.setText("重新测试" if hist else "开始测试")
        for k, chip in self.theme_chips.items():
            chip.setProperty("on", "1" if k == self.theme_key else "0")
            chip.style().unpolish(chip)
            chip.style().polish(chip)

        while self.hist_layout.count():
            it = self.hist_layout.takeAt(0)
            wgt = it.widget()
            if wgt is not None:
                wgt.deleteLater()
        rows = list(enumerate(hist))[-5:][::-1]
        if not rows:
            lbl = QLabel("暂无记录")
            lbl.setStyleSheet(th.label_qss(self.t, "note", 12))
            self.hist_layout.addWidget(lbl)
        for idx, h in rows:
            b2 = QPushButton("%s　　≈ %s 词　›" %
                             (time.strftime("%Y-%m-%d", time.localtime(h["ts"])),
                              format(h["vocab"], ",")))
            b2.setObjectName("row")
            b2.setCursor(Qt.PointingHandCursor)
            b2.setMinimumHeight(26)
            b2.clicked.connect(lambda _=False, i=idx: self._open_history(i))
            self.hist_layout.addWidget(b2)
        self._apply_scaling(force=True)

    def _open_history(self, idx):
        hist = self.progress.get("history") or []
        if not (0 <= idx < len(hist)):
            return
        self._show_history(hist[idx], hist[:idx + 1])

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
        self.btn_gear.setVisible(study and not self.compact)
        self._refresh_back_control()
        # 学习页面（刷词/选择题）不显示左上角的状态文字；测试页保留进度与严谨度。
        self.status.setVisible(mode == "quiz" and not self.compact)
        self.page_title.setVisible(mode in ("settings", "books", "catalog"))
        self.page_title.setText({"settings": "设置", "books": "选择词书", "catalog": "词书内容"}.get(mode, ""))
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
        self.btn_skip.setVisible(mode == "quiz")
        if mode == "books":
            self._refresh_books()
        elif mode in ("settings", "welcome", "catalog"):
            self.status.clear()
        if mode == "front":
            self.fade.stop()
            self.answer_effect.setOpacity(0.0)
        self._apply_scaling(force=True)

    def _show_current(self):
        item = self.queue[self.qi]
        word = item["w"]
        _, level, _ = memory_info(word["w"], self.states, self.known)
        caption = "复习 · 记忆等级 %d" % level if item["kind"] == "review" else "新词" + (" · 重现" if item["kind"] == "retry" else "")
        self.status.setText(caption)
        self.word.setText(word["w"])
        self.ipa.setText(pronunciation(word))
        self.meaning.setText(entry_meaning(word))
        self.meaning.setTextFormat(Qt.PlainText)
        self.btn_next.setText("下一个  →")
        self.corrected = False
        if self.study_mode == "choice":
            key = "phrase" if is_phrase(word) else "word"
            if key not in self._study_option_pools:
                self._study_option_pools[key] = study_options.OptionPool(self.phrases if key == "phrase" else self.bank)
            try:
                self.choice_question = study_options.make_options(word, self._study_option_pools[key], random)
            except ValueError:
                if "all" not in self._study_option_pools:
                    self._study_option_pools["all"] = study_options.OptionPool(self.all_entries)
                self.choice_question = study_options.make_options(word, self._study_option_pools["all"], random)
            self.choice_locked = False
            self.choice_word.setText(word["w"])
            self.choice_ipa.setText(pronunciation(word))
            self.choice_ipa.setVisible(bool(self.choice_ipa.text()))
            for index, button in enumerate(self.study_btns):
                button.setText("%s  %s" % ("ABCD"[index], self.choice_question["options"][index]))
                button.setProperty("state", "")
                button.setEnabled(True)
                button.style().unpolish(button)
                button.style().polish(button)
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
        if due is not None:
            minutes = max(1, math.ceil((due - time.time()) / 60))
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
        self.btn_next.setText("检查复习")

    # ---------- 学习流程 ----------
    def _capture_study(self):
        return {"states": copy.deepcopy(self.states),
                "record": copy.deepcopy(self.study_record),
                "cursor": self.cursor, "cursors": copy.deepcopy(self.cursors),
                "qi": self.qi, "book": self.book_id,
                "queue": list(self.queue), "last_action": self.last_action,
                "corrected": self.corrected}

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
            self.study_engine.answer(item, remember, time.time())
            self.cursor = self.study_engine.cursor
            self.cursors[self.book_id] = self.cursor
            self.last_action = (item["kind"], item["w"]["w"], remember)
            self.save()
        except storage.StorageError as error:
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
        if not self._restore_snapshot():
            return
        item = self.queue[self.qi]
        try:
            self.study_engine.answer(item, False, time.time())
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
        if not hist:
            return True
        last = max(h["ts"] for h in hist)
        if time.time() - last >= TEST_INTERVAL:
            return True
        return False

    def _maybe_start_test(self):
        """兼容旧调用：等价于启动引导流程。"""
        self._startup()

    def _capture_quiz(self):
        """只复制测验可变图，保留原容器引用；不复制其它学习记录。"""
        names = ("quiz_state", "quiz_items", "quiz_resp", "quiz_i", "rigor",
                 "quiz_locked", "theta", "known", "last_test", "mode",
                 "_quiz_retry_action")
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
        self.btn_skip.setText("重试保存并继续" if action else "跳过本次测试")
        tips = {"next": "只重试保存下一题，不会重复计算已提交的答案。",
                "finish": "只重试保存本次结果，不会重复添加测试历史。",
                "start": "重试开始或恢复本次测试，原进度仍然保留。",
                "skip": "重试跳过本次测试；保存成功前不会丢弃本次答案。"}
        self.btn_skip.setToolTip(tips.get(action, "跳过本次测试，稍后再测。"))
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
        if action == "next":
            return self._quiz_next()
        if action == "finish":
            return self._finish_quiz()
        if action == "skip":
            return self.skip_test()
        if self.mode == "quiz":
            return self.skip_test()
        return False

    def start_quiz(self):
        if not self._can_act():
            return False
        before = self._capture_quiz()
        self.quiz_timer.stop()
        try:
            self.progress.pop("quiz_declined", None)
            self.progress["welcome_done"] = True
            if self.mode == "welcome" or not self.progress.get("book_confirmed"):
                self.progress["quiz_from_welcome"] = True
            sess = self.progress.get("quiz_session")
            if sess:
                ok = (isinstance(sess, dict) and sess.get("algo") == "staircase-v1"
                      and isinstance(sess.get("i"), int) and 0 <= sess["i"] < QUIZ_N
                      and isinstance(sess.get("state"), dict)
                      and isinstance(sess.get("items"), list)
                      and isinstance(sess.get("resp"), list)
                      and sess["i"] < len(sess["items"]) <= QUIZ_N
                      and len(sess["resp"]) in (sess["i"], sess["i"] + 1))
                if not ok:
                    raise storage.StorageError("测试进度格式异常；请先备份检查，或明确跳过本次测试。")
                self.quiz_state = sess["state"]
                self.quiz_items = sess["items"]
                self.quiz_resp = sess["resp"]
                self.quiz_i = sess["i"]
                self.rigor = sess.get("rigor", 100.0)
                if len(self.quiz_resp) == self.quiz_i + 1:
                    # 仅设置逻辑模式，不切换页面；推进/完成保存成功后才显示新 UI。
                    self.mode = "quiz"
                    self.quiz_locked = True
                    return self._quiz_next(before=before, retry_action="start")
            else:
                self.quiz_state = pl.new_session(seed=random.randrange(1, 1 << 30))
                self.quiz_items = []
                self.quiz_resp = []
                self.quiz_i = 0
                self.rigor = 100.0
            if not self.quiz_items:
                self._gen_item()
            self._save_quiz_session()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, "start")
            return False
        self._set_quiz_retry(None)
        self._set_mode("quiz")
        self._quiz_show()
        return True

    def _gen_item(self):
        """按当前档位随机抽一个没做过的词，生成 4 选 1。"""
        rng = random.Random(self.quiz_state["seed"] * 1000003 + len(self.quiz_state["asked"]))
        idx = pl.pick_idx(self.lvls, self.quiz_state["level"], self.quiz_state["asked"], rng)
        opts, correct = pl.make_options(self.bank, idx, rng, self.bs)
        item = {"idx": idx, "opts": opts, "correct": correct, "lvl": self.quiz_state["level"]}
        self.quiz_items.append(item)
        self.quiz_state["asked"].append(idx)
        return item

    def _save_quiz_session(self):
        if not self._can_act():
            return False
        sess = self.progress.get("quiz_session")
        if not isinstance(sess, dict):
            sess = {}
            self.progress["quiz_session"] = sess
        sess.update({
            "algo": "staircase-v1",
            "state": self.quiz_state,
            "items": self.quiz_items, "resp": self.quiz_resp,
            "i": self.quiz_i, "rigor": self.rigor, "ts": int(time.time()),
        })                              # 保留 session 的未知字段和原字典身份
        self.save()
        return True

    def skip_test(self):
        """只有明确跳过且保存成功，才丢弃本次测试；失败仍保留原 session。"""
        if not self._can_act():
            return False
        before = self._capture_quiz()
        self.quiz_timer.stop()
        try:
            self.progress.pop("quiz_session", None)
            self.progress["snooze_until"] = int(time.time()) + SKIP_SNOOZE
            from_welcome = bool(self.progress.pop("quiz_from_welcome", False) or
                                not self.progress.get("book_confirmed"))
            self.save()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, "skip")
            return False
        self._set_quiz_retry(None)
        if from_welcome:
            self.open_books("welcome")
        else:
            self._new_session()
        return True

    def _quiz_status(self, delta=None):
        txt = "词汇量测试 %d/%d   ·   严谨度 %d" % (
            self.quiz_i + 1, QUIZ_N, int(round(self.rigor)))
        if delta:
            col = "#79e0ac" if delta > 0 else "#ef9cad"
            txt += "  <span style='color:%s'>%+.1f</span>" % (col, delta)
        self.status.setText(txt)

    def _quiz_show(self):
        item = self.quiz_items[self.quiz_i]
        w = self.bank[item["idx"]]
        self.quiz_word.setText(w["w"])
        self._quiz_status()
        for i, b in enumerate(self.opt_btns):
            b.setText("%s  %s" % (LETTERS[i], item["opts"][i]))
            b.setEnabled(True)
            b.setProperty("state", "")
            b.style().unpolish(b)
            b.style().polish(b)
        self.btn_dontknow.setEnabled(True)
        self.btn_dontknow.setProperty("state", "")
        self.btn_dontknow.style().unpolish(self.btn_dontknow)
        self.btn_dontknow.style().polish(self.btn_dontknow)
        self.quiz_locked = False
        self._fit_choice_options(self._ui_scale())
        self.quiz_page.verticalScrollBar().setValue(0)

    def _quiz_answer(self, choice):
        """choice: 0..3 选项，-1 = 不知道；保存成功后才显示反馈。"""
        if (not self._can_act() or self.mode != "quiz" or self.quiz_locked
                or len(self.quiz_resp) != self.quiz_i):
            return False
        before = self._capture_quiz()
        self.quiz_timer.stop()
        item = self.quiz_items[self.quiz_i]
        correct = item["correct"]
        good = choice >= 0 and choice == correct
        try:
            self.quiz_locked = True
            if choice < 0:
                self.quiz_resp.append(-1)
                delta = 0.0
            elif good:
                self.quiz_resp.append(1)
                delta = 1.5
            else:
                self.quiz_resp.append(0)
                delta = -3.0
            old = self.rigor
            self.rigor = max(0.0, min(100.0, self.rigor + delta))
            delta = self.rigor - old
            pl.step(self.quiz_state, good, len(self.quiz_resp))
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
        self.btn_dontknow.setProperty("state", "picked" if choice < 0 else "")
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
        if len(self.quiz_resp) == QUIZ_N:
            action = "start" if retry_action == "start" else "finish"
            return self._finish_quiz(before=before, retry_action=action)
        try:
            self.quiz_i += 1
            while len(self.quiz_items) <= self.quiz_i:
                self._gen_item()
            self._save_quiz_session()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, retry_action)
            return False
        self._set_quiz_retry(None)
        self._set_mode("quiz")
        self._quiz_show()
        return True

    def _finish_quiz(self, before=None, retry_action="finish"):
        if (not self._can_act() or self.mode != "quiz" or len(self.quiz_resp) != QUIZ_N
                or len(self.quiz_items) != QUIZ_N or not self.progress.get("quiz_session")):
            return False               # 不补零造结果；已完成/迟到的调用也不重复提交
        self.quiz_timer.stop()
        before = before if before is not None else self._capture_quiz()
        items, resp = self.quiz_items, self.quiz_resp
        bs = [self.bs[it["idx"]] for it in items]
        theta, se = pl.estimate_theta(bs, resp)
        est = int(round(pl.vocab_at(self.bs, theta)))
        lo, hi = pl.error_band(self.bs, theta, se * 1.5)
        rigor = int(round(self.rigor))
        se_err = (hi - lo) / 2.0 / max(1, est) * 100.0
        err = max(4.0, min(40.0, max(se_err, 4 + (100 - rigor) * 0.35)))
        lo = int(round(est * (1 - err / 100.0)))
        hi = int(round(est * (1 + err / 100.0)))
        try:
            history = self.progress.setdefault("history", [])
            is_baseline = not any(h.get("baseline") for h in history)
            if is_baseline or self.progress.get("theta") is None:
                self._set_theta(theta)  # 0.0 也是合法基准，不可误判成尚未设置
            elif self.last_test is None:
                self._refresh_known()
            rec = {
                "ts": int(time.time()),
                "algo": "staircase-v1",
                "theta": round(theta, 3), "se": round(se, 3),
                "vocab": est, "rigor": rigor, "err": round(err, 1),
                "lo": max(0, lo), "hi": hi,
                "right": sum(1 for r in resp if r == 1),
                "dontknow": sum(1 for r in resp if r < 0),
                "total": QUIZ_N,
                "known": len(self.known),
                "to_learn": len(self.bank) - len(self.known),
                "baseline": is_baseline,
            }
            history.append(rec)
            from_welcome = bool(self.progress.pop("quiz_from_welcome", False) or
                                not self.progress.get("book_confirmed"))
            self.progress.pop("quiz_session", None)
            self.progress.pop("snooze_until", None)
            self.last_test = (rec, is_baseline)
            self.save()
        except storage.StorageError as error:
            self._quiz_save_error(error, before, retry_action)
            return False
        self._set_quiz_retry(None)
        self.status.setText("词汇量测试完成")
        self._show_result(rec, is_baseline, from_welcome)
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

        self.res_big.setText("≈ %s 词" % format(rec["vocab"], ","))
        self.res_sub.setText("严谨度 %d  ·  误差 ±%d%%  ·  %s – %s 词" % (
            rec.get("rigor", 100), int(round(rec.get("err", 0))),
            format(rec.get("lo", rec["vocab"]), ","),
            format(rec.get("hi", rec["vocab"]), ",")))
        line = "答对 %d/%d" % (rec["right"], rec["total"])
        if rec.get("dontknow"):
            line += "  ·  不认识 %d 题" % rec["dontknow"]

        tail = ""
        if self.book_id:
            _, known, _, total = self._book_stats(self.book_id)
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
        self.result_ctx = "welcome_test" if from_welcome else "test"
        self.btn_start.setText("选择词书" if from_welcome else "继续背单词")
        self.btn_rebase.setVisible(not is_baseline)
        self._fill_result(rec, self.progress.get("history", []), is_baseline)
        self._set_mode("result")

    def _show_history(self, rec, upto):
        self.result_ctx = "history"
        self.btn_start.setText("返回设置")
        self.btn_rebase.hide()
        self._fill_result(rec, upto, bool(rec.get("baseline")))
        self._set_mode("result")

    def _rebase(self):
        """用最近这次测试的结果重排学习队列。"""
        if not self.last_test:
            return
        rec, _ = self.last_test
        self._set_theta(rec.get("theta", 0.0))
        for h in self.progress.get("history", []):
            h["baseline"] = (h is rec)
        rec["known"] = len(self.known)
        rec["to_learn"] = len(self.bank) - len(self.known)
        self.save()
        self._show_result(rec, True)

    def _leave_result(self):
        self._new_session()

    # ---------- 键盘 ----------
    def keyPressEvent(self, ev):
        if not self._can_act():
            return
        k = ev.key()
        if self.mode in ("choice", "choice_back"):
            if k == Qt.Key_Z and ev.modifiers() & Qt.ControlModifier:
                self.undo()
            elif k == Qt.Key_Escape:
                self.close()
            elif self.mode == "choice":
                if Qt.Key_1 <= k <= Qt.Key_4:
                    self._study_answer(k - Qt.Key_1)
                elif k in (Qt.Key_0, Qt.Key_5):
                    self._study_answer(-1)
            elif k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Right):
                self._next()
            elif k == Qt.Key_Z:
                self.correct()
            return
        if self.mode == "catalog":
            if k == Qt.Key_Escape:
                self._page_back()
            return
        if self.mode == "quiz":
            if Qt.Key_1 <= k <= Qt.Key_4:
                self._quiz_answer(k - Qt.Key_1)
            elif k in (Qt.Key_0, Qt.Key_Space):
                self._quiz_answer(-1)
            elif k == Qt.Key_Escape:
                self.close()          # 直接退出，进度留着
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
        if k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Right):
            if self.mode in ("back", "empty"):
                self._next()
            else:
                self.act("remember")
        elif k in (Qt.Key_Left, Qt.Key_1):
            self.act("forget")

        elif k == Qt.Key_Z and not (ev.modifiers() & Qt.ControlModifier) and self.mode == "back":
            self.correct()
        elif k == Qt.Key_Z and ev.modifiers() & Qt.ControlModifier:
            self.undo()
        elif k == Qt.Key_Escape:
            self.close()
        else:
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
        if len(w.quiz_resp) == w.quiz_i + 1 and len(w.quiz_resp) < QUIZ_N:
            if not w._quiz_next():
                return
        while len(w.quiz_resp) < QUIZ_N:
            i = len(w.quiz_resp)
            it = w.quiz_items[w.quiz_i]
            if dk and i % 7 == 3:
                choice = -1
            elif good and w.bs[it["idx"]] < 0.25:
                choice = it["correct"]
            elif good and w.bs[it["idx"]] < 0.9:
                choice = it["correct"] if i % 3 else (it["correct"] + 1) % 4
            else:
                choice = (it["correct"] + 1) % 4
            if not w._quiz_answer(choice):
                return                 # 失败留给明确重试，不在调试循环里反复弹错
            if len(w.quiz_resp) < QUIZ_N and not w._quiz_next():
                return
        w._finish_quiz()

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
