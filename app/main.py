# -*- coding: utf-8 -*-
"""极简背单词卡片（PyQt5）

学习：自由节奏，先复习后新词；卡片上只有单词，点完才淡入释义。
首次打开：先推荐做词汇量测试（也可以跳过，直接选词书开始学）。
设置（⚙）：背景风格 / 词汇量测试入口与历史记录 / 词书与已学进度。
"""
import sys, os, io, json, time, copy, math, random

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QPointF
from PyQt5.QtGui import (QPainter, QColor, QPainterPath, QPen, QFont, QFontMetrics)
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,
                             QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect,
                             QScrollArea)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import scheduler as sch
import placement as pl
import theme as th
import books as bk

PROGRESS_PATH = os.path.join(DATA, "progress.json")

COMPACT_QSS = """
QPushButton { font-size: 15px; padding: 4px 12px; border-radius: 12px; }
QPushButton#bar { font-size: 13px; }
QPushButton#wrong { font-size: 14px; }
"""

CARD_W, CARD_H = 520, 430
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


def mean_h(i):
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(F_MEAN[i])
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


class Card(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("背单词")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(CARD_W, CARD_H)

        self.progress = self._load_progress()
        self.states = self.progress.setdefault("states", {})
        self.cursors = self.progress.setdefault("cursors", {})
        self.orders = self.progress.setdefault("orders", {})

        self.theme_key = self.progress.get("theme") or th.DEFAULT
        self.t = th.get(self.theme_key)
        self.book_id = self._resolve_saved_book(self.progress.get("book") or bk.DEFAULT)
        self.sel_book = self.book_id
        self.sel_order = (self.orders.get(self.book_id) or {}).get("mode", "shuffle")
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
        self.bs = [x["b"] for x in self.bank]
        self.lvls = [x["lvl"] for x in self.bank]
        self.theta = self.progress.get("theta")
        self.known = set()
        self._refresh_known()
        self.book_words = self._book_words(self.book_id)
        self.cursor = self.cursors.get(self.book_id, 0)
        self.queue_words = self._order_words(self.book_words, self.order_mode,
                                             self._seed(self.book_id))

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
        self.rigor = 100.0
        self.last_test = None
        self.quiz_timer = QTimer(self)
        self.quiz_timer.setSingleShot(True)
        self.quiz_timer.timeout.connect(self._quiz_next)

        self._build_ui()
        self._new_session()
        self.show()
        QTimer.singleShot(400, self._startup)

    # ---------- 数据 ----------
    def _load_progress(self):
        p = {}
        if os.path.exists(PROGRESS_PATH):
            try:
                with io.open(PROGRESS_PATH, encoding="utf-8") as f:
                    p = json.load(f)
            except Exception:
                p = {}
        p.setdefault("states", {})
        p.setdefault("theme", th.DEFAULT)
        p.setdefault("book", bk.DEFAULT)
        p.setdefault("cursors", {})
        p.setdefault("orders", {})
        p.pop("cursor", None)          # v1.0 的全局游标，v1.1 改为每本书一个
        # V1.1 的 11 个词书 id 已并入 V2 的分组并集：把旧游标 / 词序顺到新 id 上
        if p.get("book") in bk.LEGACY:
            p["book"] = bk.LEGACY[p["book"]]
        for old_id, new_id in bk.LEGACY.items():
            if old_id in p["orders"] and new_id not in p["orders"]:
                p["orders"][new_id] = p["orders"][old_id]
            if old_id in p["cursors"] and new_id not in p["cursors"]:
                p["cursors"][new_id] = p["cursors"][old_id]
        if "welcome_done" not in p:
            # 老用户（已经有学习记录）直接当引导已经走完
            p["welcome_done"] = bool(p.get("states") or p.get("history"))
        return p

    def save(self):
        self.progress["states"] = self.states
        self.progress["cursors"] = self.cursors
        self.progress["orders"] = self.orders
        self.progress["theta"] = self.theta
        tmp = PROGRESS_PATH + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.progress, f, ensure_ascii=False)
        # Windows 上目标文件偶尔会被杀毒/索引短暂占用，重试几次再替换
        last = None
        for i in range(6):
            try:
                os.replace(tmp, PROGRESS_PATH)
                return
            except PermissionError as e:
                last = e
                time.sleep(0.02 * (i + 1))
        try:
            with io.open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.progress, f, ensure_ascii=False)
        except Exception:
            raise last

    # ---------- 大词库 / 词书 ----------
    def _resolve_saved_book(self, saved):
        """progress 里的 book 可能来自 V1.1（旧 id）或教材系列伪 id。"""
        if saved in bk.BY_ID:
            return saved
        gid, series = parse_series_id(saved)
        if gid and series_union_words(gid, series):
            return saved
        return bk.get(saved)["id"]

    def _book_word_strs(self, book_id):
        """词书 / 并集 / 教材系列并集 -> A–Z 以外的原始词序（UI 层解析伪 id）。"""
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
        return m.get("display") or m.get("name") or book_id

    def _book_path(self, book_id):
        m = self._book_meta(book_id)
        parts = [p for p in (m.get("path") or []) if p]
        parts.append(m.get("display") or m.get("name") or book_id)
        return " · ".join(parts)

    def _book_short_name(self, book_id):
        """结果页里的一小段名字：真实书用所属分组名（六级/GRE…）。"""
        gid, series = parse_series_id(book_id)
        if gid:
            return "%s 全选" % series
        b = bk.get(book_id)
        g = bk.GROUPS.get(b.get("group"))
        return g["name"] if g else (b.get("display") or b["name"])

    def _seed(self, book_id):
        rec = self.orders.setdefault(book_id, {"mode": "shuffle"})
        if not rec.get("seed"):
            rec["seed"] = random.randrange(1, 1 << 30)
        return rec["seed"]

    def _order_words(self, words, mode, seed):
        out = list(words)
        if mode == "shuffle":
            random.Random(seed).shuffle(out)
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
        for w in words:
            st = (self.states.get(w) or {}).get("st")
            if st == "learning":
                learned += 1
            elif st == "mastered":
                learned += 1
                mastered += 1
            if w in self.known:
                known += 1
        return learned, known, mastered, len(words)

    # ---------- 学习队列：先复习（跨书），再一个个学新词（当前书） ----------
    def _new_session(self):
        self.queue = sch.review_items(self.bank, self.states, time.time())
        self.qi = 0
        if not self.queue and not self._pull_new():
            self._show_empty()
            return
        self.mode = "front"
        self._show_current()

    def _pull_new(self):
        i = self.cursor
        while i < len(self.queue_words):
            w = self.queue_words[i]
            st = self.states.get(w["w"])
            if (st and st.get("st") in sch.DONE) or w["w"] in self.known:
                i += 1
                continue
            self.cursor = i + 1
            self.cursors[self.book_id] = self.cursor
            self.queue.append({"kind": "new", "w": w, "st": None, "idx": i})
            return True
        self.cursor = i
        self.cursors[self.book_id] = i
        return False

    # ---------- 窗口 ----------
    def toggle_compact(self):
        self.set_compact(not self.compact)

    def set_compact(self, on):
        """缩小 / 展开。两档都显示 单词 + 音标 + 词性释义 + 按钮，只缩字号和留白。"""
        on = bool(on)
        self.compact = on
        i = 1 if on else 0
        self.setStyleSheet(self._base_qss + COMPACT_QSS if on else self._base_qss)
        self.root.setContentsMargins(*MARGINS[i])
        self.meaning.setFixedHeight(mean_h(i))
        self.gap_ipa.setFixedHeight(GAP_IPA[i])
        for b in (self.btn_forget, self.btn_remember, self.btn_wrong, self.btn_next):
            b.setMinimumHeight(BTN_H[i])
        self._style_text()
        self.btn_min.set_kind("max" if on else "min")
        if on:
            self.status.hide()
            self.btn_gear.hide()
            self.setFixedSize(COMPACT_W, COMPACT_H)
        else:
            self.status.show()
            self.btn_gear.show()
            self.setFixedSize(CARD_W, CARD_H)

    # ---------- UI ----------
    def reg(self, label, kind, size):
        """登记一个跟随主题 / 字号变化的文字控件。"""
        self._reg.append((label, kind, size))
        label.setStyleSheet(th.label_qss(self.t, kind, size))
        return label

    def _style_text(self):
        i = 1 if self.compact else 0
        for lbl, kind, size in self._reg:
            lbl.setStyleSheet(th.label_qss(self.t, kind, size))
        if self.mode == "empty":
            self.word.setStyleSheet(th.label_qss(self.t, "empty", 18 if self.compact else 24))
        else:
            self.word.setStyleSheet(th.label_qss(self.t, "word", F_WORD[i]))
        self.ipa.setStyleSheet(th.label_qss(self.t, "ipa", F_IPA[i]))
        self.meaning.setStyleSheet(th.label_qss(self.t, "mean", F_MEAN[i]))

    def _apply_tool_colors(self):
        for b in (self.btn_min, self.btn_gear, self.btn_back):
            b.set_colors(self.t["bar"], self.t["bar_hover"])
        self.chart.set_palette(self.t)

    def _build_ui(self):
        self._base_qss = th.qss(self.t)
        self.setStyleSheet(self._base_qss)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(*MARGINS[0])
        self.root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(4)
        self.btn_back = MiniButton("back", "返回")
        self.btn_back.clicked.connect(self._page_back)
        top.addWidget(self.btn_back)
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
        self.btn_skip.clicked.connect(self.skip_test)
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
        self._build_quiz()
        self._build_result()
        self._build_welcome()
        self._build_books()
        self._build_settings()

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
        self.btn_forget = QPushButton("不记得")
        self.btn_forget.setObjectName("forget")
        self.btn_forget.clicked.connect(lambda: self.act("forget"))
        self.btn_remember = QPushButton("记得")
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

    def _build_quiz(self):
        self.quiz_page = QWidget()
        qv = QVBoxLayout(self.quiz_page)
        qv.setContentsMargins(0, 0, 0, 0)
        qv.setSpacing(0)
        qv.addSpacing(10)
        self.quiz_word = QLabel("")
        self.quiz_word.setAlignment(Qt.AlignCenter)
        self.reg(self.quiz_word, "big", 38)
        qv.addWidget(self.quiz_word)
        qv.addSpacing(18)

        self.opt_btns = []
        for i in range(4):
            b = QPushButton("")
            b.setObjectName("opt")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(42)
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
        self.book_scroll.setFixedHeight(280)
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
        bv.addWidget(self.book_scroll)
        bv.addSpacing(4)

        self.lab_book_stat = QLabel("")
        self.reg(self.lab_book_stat, "note", 12)
        bv.addWidget(self.lab_book_stat)
        bv.addSpacing(3)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        lab_order = QLabel("词序")
        self.reg(lab_order, "note", 12)
        bottom.addWidget(lab_order)
        self.chip_seq = QPushButton("顺序")
        self.chip_shuf = QPushButton("乱序")
        for b, mode in ((self.chip_seq, "seq"), (self.chip_shuf, "shuffle")):
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(28)
            b.clicked.connect(lambda _=False, m=mode: self._set_order(m))
            bottom.addWidget(b)
        bottom.addStretch(1)
        self.btn_learn = QPushButton("开始学习")
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
        self.settings_page = QWidget()
        sv = QVBoxLayout(self.settings_page)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        sv.addSpacing(2)

        sv.addWidget(self.reg(QLabel("背景风格"), "note", 12))
        sv.addSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.theme_chips = {}
        for key, name in th.options():
            b = QPushButton(name)
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(30)
            b.clicked.connect(lambda _=False, k=key: self.set_theme(k))
            row.addWidget(b)
            self.theme_chips[key] = b
        row.addStretch(1)
        sv.addLayout(row)
        sv.addSpacing(12)

        sv.addWidget(self.reg(QLabel("词书"), "note", 12))
        sv.addSpacing(6)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.lab_book = QLabel("")
        self.reg(self.lab_book, "mean", 13)
        row2.addWidget(self.lab_book)
        row2.addStretch(1)
        self.lab_book_num = QLabel("")
        self.reg(self.lab_book_num, "note", 13)
        row2.addWidget(self.lab_book_num)
        btn_change = QPushButton("更换")
        btn_change.setObjectName("chip")
        btn_change.setCursor(Qt.PointingHandCursor)
        btn_change.setMinimumHeight(28)
        btn_change.clicked.connect(lambda: self.open_books("settings"))
        row2.addWidget(btn_change)
        sv.addLayout(row2)
        sv.addSpacing(4)
        self.lab_progress = QLabel("")
        self.reg(self.lab_progress, "note", 12)
        sv.addWidget(self.lab_progress)
        sv.addSpacing(12)

        sv.addWidget(self.reg(QLabel("词汇量测试"), "note", 12))
        sv.addSpacing(6)
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.lab_vocab = QLabel("")
        self.reg(self.lab_vocab, "mean", 14)
        row3.addWidget(self.lab_vocab)
        row3.addStretch(1)
        self.btn_test = QPushButton("开始测试")
        self.btn_test.setObjectName("chip")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.setMinimumHeight(28)
        self.btn_test.clicked.connect(self._test_from_settings)
        row3.addWidget(self.btn_test)
        sv.addLayout(row3)
        sv.addSpacing(6)
        sv.addWidget(self.reg(QLabel("历史记录（点一条看结果）"), "note", 11))
        sv.addSpacing(2)
        self.hist_box = QWidget()
        self.hist_layout = QVBoxLayout(self.hist_box)
        self.hist_layout.setContentsMargins(0, 0, 0, 0)
        self.hist_layout.setSpacing(2)
        sv.addWidget(self.hist_box)
        sv.addStretch(1)

        self.root.addWidget(self.settings_page, 1)
        self.settings_page.hide()

    # ---------- 主题 ----------
    def set_theme(self, key):
        self.theme_key = key if key in th.THEMES else th.DEFAULT
        self.t = th.get(self.theme_key)
        self.progress["theme"] = self.theme_key
        self.save()
        self._base_qss = th.qss(self.t)
        self.setStyleSheet(self._base_qss + (COMPACT_QSS if self.compact else ""))
        self._style_text()
        self._apply_tool_colors()
        self._refresh_settings()
        self.update()

    def _gear_clicked(self):
        if self.mode == "settings":
            self.close_settings()
        else:
            self.open_settings()

    def _page_back(self):
        if self.mode == "settings":
            self.close_settings()
        elif self.mode == "books":
            if self.nav_level > 1:
                self._nav_back()
            elif self.books_src == "settings":
                self.open_settings()
            else:
                self.close()          # 从引导/学习页进来：返回键 = 关闭，跟 V1.1 的 Esc 一致

    def open_settings(self):
        if self.mode in ("front", "back", "empty"):
            self.pre_settings_mode = self.mode
        self._refresh_settings()
        self._set_mode("settings")

    def close_settings(self):
        m = self.pre_settings_mode
        self._set_mode(m if m in ("front", "back", "empty") else "front")

    def _test_from_settings(self):
        self.progress.pop("quiz_declined", None)
        self.save()
        self.start_quiz()

    # ---------- 词书 / 进度 ----------
    def _stats(self):
        return self._book_stats(self.book_id)

    def _refresh_books(self):
        learned, known, mastered, total = self._book_stats(self.sel_book)
        for bid, btn in self.book_btns.items():
            btn.setProperty("on", "1" if bid == self.sel_book else "0")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.lab_book_stat.setText("%s · %s 词" %
                                   (self._book_path(self.sel_book), format(total, ",")))
        self.status.setText("已学 %s / %s · 已会 %s · 已掌握 %s" %
                            (format(learned, ","), format(total, ","),
                             format(known, ","), format(mastered, ",")))
        for chip, mode in ((self.chip_seq, "seq"), (self.chip_shuf, "shuffle")):
            chip.setProperty("on", "1" if mode == self.sel_order else "0")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        same = (self.sel_book == self.book_id and self.sel_order == self.order_mode)
        self.btn_learn.setText("开始学习" if same else "用这本开始")
        if self.nav_level == 3 and self.sel_book in self.book_btns:
            try:
                self.book_scroll.ensureWidgetVisible(self.book_btns[self.sel_book], 0, 6)
            except Exception:
                pass

    def _pick_book(self, bid):
        self.sel_book = bid
        self.sel_order = (self.orders.get(bid) or {}).get("mode", "shuffle")
        self._refresh_books()

    def _set_order(self, mode):
        self.sel_order = mode
        self._refresh_books()

    def open_books(self, src="welcome"):
        self.books_src = src
        self.sel_book = self.book_id
        self.sel_order = self.order_mode
        self.nav_level = 1
        self.nav_main = None
        self.nav_group = None
        self._build_nav_level()
        self._set_mode("books")

    def _start_learning(self):
        new_book = self.sel_book != self.book_id
        old_mode = (self.orders.get(self.sel_book) or {}).get("mode", "shuffle")
        if new_book:
            self.book_id = self.sel_book
            self.book_words = self._book_words(self.book_id)
        if new_book or self.sel_order != self.order_mode or self.sel_order != old_mode:
            self.order_mode = self.sel_order
            rec = self.orders.setdefault(self.book_id, {"mode": self.order_mode})
            rec["mode"] = self.order_mode
            if not rec.get("seed"):
                rec["seed"] = random.randrange(1, 1 << 30)
            self.queue_words = self._order_words(self.book_words, self.order_mode, rec["seed"])
            # 换了顺序就从头开始（已学的会被跳过），避免旧游标指向新序列里的别的词
            self.cursor = 0
            self.cursors[self.book_id] = 0
        else:
            self.cursor = self.cursors.get(self.book_id, 0)
        self.progress["book"] = self.book_id
        self.sel_book = self.book_id
        self.save()
        self.setFixedSize(CARD_W, CARD_H)
        self._new_session()

    # ---------- 首次引导 ----------
    def _startup(self, force=False):
        """打开应用时的入口：首次引导 / 续测 / 30 天到期测试。"""
        if "--nottest" in sys.argv and not force:
            return
        if not self.progress.get("welcome_done"):
            self.welcome()
            return
        if self.progress.get("quiz_session"):
            self.start_quiz()                     # 上次测到一半，接着来
            return
        if self.progress.get("quiz_declined") and not (self.progress.get("history") or []):
            return                                # 用户明确说了「不测了」
        if self.progress.get("snooze_until", 0) > time.time():
            return
        if self._need_test():
            self.start_quiz()

    def welcome(self):
        self._set_mode("welcome")

    def _welcome_test(self):
        self.progress["welcome_done"] = True
        self.progress.pop("quiz_declined", None)
        self.save()
        self.start_quiz()

    def _welcome_skip(self):
        self.progress["welcome_done"] = True
        self.progress["quiz_declined"] = True
        self.save()
        self.open_books("welcome")

    # ---------- 设置内容 ----------
    def _refresh_settings(self):
        learned, known, mastered, total = self._stats()
        self.lab_book.setText(self._book_path(self.book_id))
        self.lab_book.setToolTip(self._book_path(self.book_id))
        self.lab_book_num.setText("已学 %s / %s" % (format(learned, ","), format(total, ",")))
        self.lab_progress.setText("已掌握 %s · 测试判定已会 %s" %
                                  (format(mastered, ","), format(known, ",")))
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

    def _open_history(self, idx):
        hist = self.progress.get("history") or []
        if not (0 <= idx < len(hist)):
            return
        self._show_history(hist[idx], hist[:idx + 1])

    def _result_primary(self):
        if self.result_ctx == "history":
            self.open_settings()
        else:
            self._leave_result()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 18, 18)
        p.fillPath(path, QColor(self.t["bg"]))
        p.setPen(QColor(self.t["border"]))
        p.drawPath(path)

    # ---------- 拖拽 ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.drag_pos = ev.globalPos() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self.drag_pos and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPos() - self.drag_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self.drag_pos = None

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        try:
            json.dump({"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()},
                      io.open(os.path.join(DATA, "_win.json"), "w"))
        except Exception:
            pass

    # ---------- 模式 ----------
    def _set_mode(self, mode):
        self.mode = mode
        study = mode in ("front", "back", "empty")
        self.btn_min.setVisible(study)
        self.btn_gear.setVisible(study and not self.compact)
        self.btn_back.setVisible(mode == "settings" or mode == "books")
        self.page_title.setVisible(mode in ("settings", "books"))
        self.page_title.setText({"settings": "设置", "books": "选择词书"}.get(mode, ""))
        self.stage.setVisible(study)
        self.front_bar.setVisible(mode == "front")
        self.back_bar.setVisible(mode == "back")
        self.quiz_page.setVisible(mode == "quiz")
        self.result_page.setVisible(mode == "result")
        self.welcome_page.setVisible(mode == "welcome")
        self.books_page.setVisible(mode == "books")
        self.settings_page.setVisible(mode == "settings")
        self.btn_skip.setVisible(mode == "quiz")
        # 词书页：底部/顶部信息随当前选择刷新；其它页面不留词书页的统计文字
        if mode == "books":
            self._refresh_books()
        elif mode == "settings":
            self.status.setText("")
        # 所有页面都锁在固定尺寸里：避免长释义/历史结果把窗口撑大
        if mode == "quiz":
            pass                                # start_quiz 已经 setFixedSize(QUIZ_W, QUIZ_H)
        elif self.compact and mode in ("front", "back", "empty"):
            self.setFixedSize(COMPACT_W, COMPACT_H)
        else:
            self.setFixedSize(CARD_W, CARD_H)
        if mode == "front":
            self.fade.stop()               # 防止上一次淡入还在跑，把答案又淡出来
            self.answer_effect.setOpacity(0.0)

    def _show_current(self):
        item = self.queue[self.qi]
        w = item["w"]
        self.status.setText("")
        self.word.setText(w["w"])
        self.ipa.setText("/%s/" % (w.get("ipa") or w.get("ph_raw") or ""))
        self._set_mode("front")

    def _show_back(self, w, remember):
        self.meaning.setText(w.get("s") or w.get("raw") or "")
        self.btn_wrong.setVisible(remember)
        self.btn_wrong.setEnabled(True)
        self._set_mode("back")
        self.fade.stop()
        self.answer_effect.setOpacity(0.0)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()

    def _show_empty(self):
        self.status.setText("")
        self.word.setText("%s 过完了 ✓" % self._book_name(self.book_id))
        self.word.setStyleSheet(th.label_qss(self.t, "empty", 18 if self.compact else 24))
        self.ipa.setText("")
        self.answer_effect.setOpacity(0.0)
        self._set_mode("empty")
        self.back_bar.show()
        self.btn_wrong.hide()
        try:
            self.btn_next.clicked.disconnect()
        except TypeError:
            pass
        self.btn_next.setText("关闭")
        self.btn_next.clicked.connect(self.close)

    # ---------- 学习流程 ----------
    def _snapshot(self):
        self.snapshot = (copy.deepcopy(self.states), self.cursor, self.qi)

    def act(self, action):
        if self.mode != "front" or not self.queue:
            return
        self._snapshot()
        item = self.queue[self.qi]
        kind, w = item["kind"], item["w"]
        key = w["w"]
        cur = copy.deepcopy(self.states.get(key) or sch.new_state())
        now = time.time()
        self.corrected = False
        if action == "remember":
            if kind == "new":
                cur = sch.new_state(now)
            else:
                cur = sch.on_remember(cur, now)
        elif action == "fuzzy":
            if kind == "new":
                cur = sch.new_state(now)
            else:
                cur = sch.on_fuzzy(cur, now)
        elif action == "forget":
            if kind == "new":
                cur = sch.new_state(now)
            cur = sch.on_forget(cur, now)
        self.states[key] = cur
        if kind == "new":
            self.cursor = max(self.cursor, item["idx"] + 1)
            self.cursors[self.book_id] = self.cursor
        self.last_action = (kind, key)
        self.save()
        self._show_back(w, remember=(action == "remember"))

    def correct(self):
        """选错了：把刚才的「记得」改判成「不记得」，然后直接下一个。"""
        if not self.last_action or self.corrected or self.mode != "back":
            return
        _, key = self.last_action
        prev = (self.snapshot[0].get(key) if self.snapshot else None) or sch.new_state()
        cur = sch.on_forget(dict(prev), time.time())
        cur["retry_now"] = False
        self.states[key] = cur
        self.corrected = True
        self.btn_wrong.setEnabled(False)
        self.save()
        self._next()

    def _next(self):
        if self.mode != "back":
            return
        if self.last_action:
            _, key = self.last_action
            st = self.states.get(key) or {}
            if st.get("retry_now"):
                w2 = self.queue[self.qi]["w"]
                st["retry_now"] = False
                self.queue.append({"kind": "retry", "w": w2, "st": None, "idx": -1})
        self._next0()

    def _next0(self):
        self.qi += 1
        if self.qi >= len(self.queue):
            # 复习做完了：自动接新词；全书过完才收尾
            if not self._pull_new():
                self._show_empty()
                return
        self._show_current()

    def undo(self):
        if self.mode in ("quiz", "result"):
            return
        if not self.snapshot:
            return
        self.states, self.cursor, self.qi = self.snapshot
        self.cursors[self.book_id] = self.cursor
        self.snapshot = None
        self.save()
        if self.mode in ("back", "empty"):
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

    def start_quiz(self):
        self.quiz_timer.stop()
        if self.compact:
            self.set_compact(False)          # 测试固定大窗，不受缩小状态影响
        sess = self.progress.get("quiz_session")
        ok = bool(sess and sess.get("algo") == "staircase-v1"
                  and 0 <= sess.get("i", 0) < QUIZ_N
                  and len(sess.get("items") or []) > sess.get("i", 0))
        if ok:
            self.quiz_state = sess["state"]
            self.quiz_items = sess["items"]
            self.quiz_resp = sess["resp"]
            self.quiz_i = sess["i"]
            self.rigor = sess.get("rigor", 100.0)
        else:
            self.progress.pop("quiz_session", None)
            self.quiz_state = pl.new_session(seed=random.randrange(1, 1 << 30))
            self.quiz_items = []
            self.quiz_resp = []
            self.quiz_i = 0
            self.rigor = 100.0
            self._gen_item()
            self._save_quiz_session()
        self.quiz_locked = False
        self.setFixedSize(QUIZ_W, QUIZ_H)
        self._set_mode("quiz")
        self._quiz_show()

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
        self.progress["quiz_session"] = {
            "algo": "staircase-v1",
            "state": self.quiz_state,
            "items": self.quiz_items, "resp": self.quiz_resp,
            "i": self.quiz_i, "rigor": self.rigor, "ts": int(time.time()),
        }
        self.save()

    def skip_test(self):
        """跳过本次测试：丢弃当前进度，明天再说。"""
        self.quiz_timer.stop()
        self.progress.pop("quiz_session", None)
        self.progress["snooze_until"] = int(time.time()) + SKIP_SNOOZE
        self.save()
        self.setFixedSize(CARD_W, CARD_H)
        self._new_session()

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

    def _quiz_answer(self, choice):
        """choice: 0..3 选项，-1 = 不知道"""
        if self.mode != "quiz" or self.quiz_locked:
            return
        self.quiz_locked = True
        item = self.quiz_items[self.quiz_i]
        correct = item["correct"]
        good = choice >= 0 and choice == correct
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
        self._quiz_status(delta)
        # 阶梯：连对 2 升档、连错 2 降档、单个对/错留在同档
        pl.step(self.quiz_state, good, len(self.quiz_resp))
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
        self._save_quiz_session()
        self.quiz_timer.start(650)

    def _quiz_next(self):
        if self.mode != "quiz":
            return
        self.quiz_i += 1
        if self.quiz_i >= QUIZ_N:
            self._finish_quiz()
            return
        while len(self.quiz_items) <= self.quiz_i:
            self._gen_item()
        self._save_quiz_session()
        self._quiz_show()

    def _finish_quiz(self):
        items = self.quiz_items
        if not items:
            return
        resp = self.quiz_resp[:len(items)]
        if len(resp) < len(items):
            resp += [0] * (len(items) - len(resp))
        self.status.setText("词汇量测试完成")

        bs = [self.bs[it["idx"]] for it in items]
        theta, se = pl.estimate_theta(bs, resp)
        est = int(round(pl.vocab_at(self.bs, theta)))
        lo, hi = pl.error_band(self.bs, theta, se * 1.5)   # ±1.5SE ≈ 86% 覆盖

        history = self.progress.setdefault("history", [])
        is_baseline = not any(h.get("baseline") for h in history)
        rigor = int(round(self.rigor))
        # 误差带：以 θ 的 ±1SE 对应的词数区间为准（50 题的真实精度），
        # 严谨度只负责"题答得越飘、误差下限越大"。
        se_err = (hi - lo) / 2.0 / max(1, est) * 100.0
        err = max(4.0, min(40.0, max(se_err, 4 + (100 - rigor) * 0.35)))
        lo = int(round(est * (1 - err / 100.0)))
        hi = int(round(est * (1 + err / 100.0)))

        if is_baseline or not self.progress.get("theta"):
            self._set_theta(theta)             # 基准测试决定跳过哪些词
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
        self.progress["history"] = history
        self.progress.pop("quiz_session", None)
        self.progress.pop("snooze_until", None)
        self.last_test = (rec, is_baseline)
        self.save()
        self._show_result(rec, is_baseline)

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

        learned, known, mastered, total = self._book_stats(self.book_id)
        tail = "%s已会 %s / %s" % (self._book_short_name(self.book_id),
                                   format(known, ","), format(total, ","))

        if is_baseline:
            known_n = rec.get("known", len(self.known))
            to_learn = rec.get("to_learn", len(self.bank) - known_n)
            self.res_note.setText("%s\n大词库判定已会 %s 个、剩 %s 个；%s" %
                                  (line, format(known_n, ","), format(to_learn, ","), tail))
        else:
            delta = rec["vocab"] - (base["vocab"] if base else rec["vocab"])
            d2 = rec["vocab"] - (prev["vocab"] if prev else rec["vocab"])
            sign = "+" if delta >= 0 else ""
            sign2 = "+" if d2 >= 0 else ""
            self.res_note.setText("%s\n比首次 %s%s 词 · 比上次 %s%s 词 · %s" %
                                  (line, sign, format(delta, ","), sign2, format(d2, ","), tail))

        self.chart.points = [(h["ts"], h["vocab"]) for h in hist][-12:]
        self.chart.update()

    def _show_result(self, rec, is_baseline):
        self.result_ctx = "test"
        self.btn_start.setText("继续背单词")
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
        self.setFixedSize(CARD_W, CARD_H)
        self._new_session()

    # ---------- 键盘 ----------
    def keyPressEvent(self, ev):
        k = ev.key()
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
    app = QApplication(sys.argv)
    w = Card()
    center = app.primaryScreen().availableGeometry().center()
    w.move(center.x() - w.width() // 2, center.y() - w.height() // 2 - 100)
    w.show()
    w.raise_()
    w.activateWindow()

    def _auto_quiz(good=True, dk=True):
        w.quiz_timer.stop()
        if w.mode != "quiz":
            w.start_quiz()
        while len(w.quiz_resp) < QUIZ_N:
            i = len(w.quiz_resp)
            it = w.quiz_items[w.quiz_i]
            if dk and i % 7 == 3:
                w._quiz_answer(-1)
            elif good and w.bs[it["idx"]] < 0.25:
                w._quiz_answer(it["correct"])
            elif good and w.bs[it["idx"]] < 0.9:
                w._quiz_answer(it["correct"] if i % 3 else (it["correct"] + 1) % 4)
            else:
                w._quiz_answer((it["correct"] + 1) % 4)
            if len(w.quiz_resp) < QUIZ_N:
                w._quiz_next()
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
            states[wd["w"]] = {"st": st, "lv": 9 if st == "mastered" else 3,
                               "due": None if st == "mastered" else now + 3600,
                               "seen": 5, "lapse": 0, "streak": 0}
        w.states = states
        w._set_theta(0.8)
        w.progress["welcome_done"] = True
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
        json.dump({"x": w.x(), "y": w.y(), "w": w.width(), "h": w.height()},
                  io.open(os.path.join(DATA, "_win.json"), "w"))
    except Exception:
        pass
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
