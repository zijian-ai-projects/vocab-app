# -*- coding: utf-8 -*-
"""词书内容浏览：模型表格避免给数千词条创建按钮，记忆说明不修改记录。

V1.3.0 性能约束：
  * 垂直表头 Fixed，默认行高 48*scale；不再对全表 ResizeToContents；
  * 只为可见行 + BUFFER_ROWS 行用 QFontMetrics 测高（按实际列宽减 cell padding），
    结果缓存（word + widths + scale + display text，容量 1024）；
  * 滚动 / viewport Show,Resize / 列宽变化 / model reset / layoutChanged 用 16ms
    singleShot QTimer 合并，不在 setBook / refilter 时同步测量全书；
  * ElideNone + WordWrap；ScrollPerPixel 允许长词组行高于视口并完整换行；
  * Model 一次缓存 meaning，搜索 / DisplayRole 不反复 format。
"""
import time
from collections import OrderedDict

from PyQt5.QtCore import (QEvent, QModelIndex, QPoint, QRect, QSize, Qt, QTimer,
                          QAbstractTableModel, pyqtSignal)
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTableView, QHeaderView, QDialog,
                             QAbstractItemView, QStyledItemDelegate, QLayout,
                             QSizePolicy, QButtonGroup,
                             QStyle, QStyleOptionViewItem)
import theme as th
from entries import CATEGORIES, meaning, memory_info, word_caption

LEVEL_LINES = (
    "等级 0：新词",
    "等级 1：5 分钟后复习",
    "等级 2：30 分钟",
    "等级 3：12 小时",
    "等级 4：1 天",
    "等级 5：2 天",
    "等级 6：4 天",
    "等级 7：7 天",
    "等级 8：15 天",
    "等级 9：30 天",
    "等级 10：已掌握，不再出现",
)
LEVEL_TEXT = "\n".join(LEVEL_LINES)


def level_lines():
    """说明窗口/测试共用的 11 行等级文案。"""
    return LEVEL_LINES

# 行高测量参数：与视图 delegate 的单元格内边距保持一致（见 TextWrapDelegate）
CELL_PAD_X = 6
CELL_PAD_Y = 6
BUFFER_ROWS = 4
DEFAULT_ROW = 48
HEIGHT_CACHE_LIMIT = 1024
MEASURE_DELAY_MS = 16


class LevelBadge(QWidget):
    """记忆等级表头右上角的描边感叹号圆圈（透明底、只画线条）。"""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#8a929c")
        self._scale = 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

    def set_style(self, color, scale, side):
        self._color = QColor(color)
        self._scale = max(1.0, min(1.6, float(scale)))
        self.resize(side, side)
        self.update()

    def paintEvent(self, ev):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(self._color)
            pen.setWidthF(max(1.0, 1.2 * self._scale))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRect(0, 0, self.width(), self.height()).adjusted(0, 0, -1, -1))
            font = QFont(self.font())
            font.setPixelSize(max(7, round(self.height() * 0.72)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "!")
        finally:
            painter.end()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.pos()):
            self.clicked.emit()
        else:
            super().mouseReleaseEvent(ev)


class LevelHeader(QHeaderView):
    """记忆等级表头：在文字右上方显示透明底、描边的感叹号圆圈。"""

    level_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._icon_scale = 1.0
        self._icon_color = QColor("#8a929c")
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.badge = LevelBadge(self.viewport())
        self.badge.clicked.connect(self.level_clicked.emit)
        self.badge.hide()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if ev.button() == Qt.LeftButton and self.logicalIndexAt(ev.pos()) == 2:
            self.level_clicked.emit()

    def set_icon_style(self, color, scale):
        self._icon_color = QColor(color)
        self._icon_scale = max(1.0, min(1.6, float(scale)))
        self.refresh_badge()
        self.update()

    def icon_color(self):
        return QColor(self._icon_color)

    def icon_rect(self):
        """测试/无障碍用：当前图标的 header 局部矩形；无该列时为空。"""
        if self.count() <= 2:
            return QRect()
        x = self.sectionViewportPosition(2)
        w = self.sectionSize(2)
        if w <= 0:
            return QRect()
        d = max(10, round(14 * self._icon_scale))
        margin = max(2, round(3 * self._icon_scale))
        right = x + w - margin
        top = margin
        return QRect(right - d, top, d, d)

    def refresh_badge(self):
        rect = self.icon_rect()
        if rect.isEmpty() or self.width() <= 0:
            self.badge.hide()
            return
        side = rect.width()
        self.badge.set_style(self._icon_color, self._icon_scale, side)
        self.badge.move(rect.x(), rect.y())
        self.badge.show()
        self.badge.raise_()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.refresh_badge()

    def showEvent(self, ev):
        super().showEvent(ev)
        self.refresh_badge()

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)


class NoSelectTableView(QTableView):
    """目录只读浏览：点击行不留下 current/selection 蓝色态。"""

    def _clear_current(self, *_args):
        self.clearSelection()
        self.setCurrentIndex(QModelIndex())

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        self._clear_current()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self._clear_current()

    def mouseDoubleClickEvent(self, ev):
        super().mouseDoubleClickEvent(ev)
        self._clear_current()


class TextWrapDelegate(QStyledItemDelegate):
    """完整换行，并屏蔽只读目录的原生 focus/selection 绘制态。"""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # NoSelection 仍允许 currentIndex（表头点击/键盘/focus proxy 都会设置它）。
        # 必须在 delegate 层清除 State_HasFocus，否则 Qt 会在单元格下画虚线框；
        # 清除 Selected 也保证程序化 current/selection 不覆盖统一正文色。
        option.state = QStyle.State(int(option.state) & ~int(
            QStyle.State_HasFocus | QStyle.State_Selected))
        option.features |= QStyleOptionViewItem.WrapText
        option.textElideMode = Qt.ElideNone


class WordTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries, self.rows = [], []
        self.states, self.known, self.predicted = {}, set(), set()
        self.category, self.query = "all", ""
        self.selection_mode = False
        self.selected_keys = set()
        self.order_index = None
        self.palette = th.get(th.DEFAULT)
        self.scale = 1.0
        self._font = QFont("Microsoft YaHei UI")
        self._font.setPixelSize(13)
        self._meanings = []          # 与 entries 对齐的 meaning，只 format 一次
        self._search = []            # (word_casefold, meaning_casefold)
        self._meta = []              # [(category, label)]，与 entries 对齐
        self._levels = []            # 与 entries 对齐的真实记忆等级/None
        self._pos_by_id = {}         # id(entry) -> entries 索引，避免 O(n) 查找
        self._counts = {key: 0 for key, _ in CATEGORIES}
        self._counts["all"] = 0
        self._row_meta = []          # 与 rows 对齐，None 表示未构建
        self._row_meta_dirty = True

    # ---------- 数据缓存 ----------
    def set_entries(self, entries, states, known=None, preserve_order=False,
                    predicted=None):
        self.order_index = ({entry.get("w", ""): index
                             for index, entry in enumerate(entries)}
                            if preserve_order else None)
        self.entries = list(entries)
        entry_keys = {entry["w"] for entry in self.entries}
        self.selected_keys.intersection_update(entry_keys)
        self.states = states
        self.known = known or set()
        self.predicted = set(predicted or ())
        self._pos_by_id = {id(entry): pos for pos, entry in enumerate(self.entries)}
        self._meanings = [meaning(entry) for entry in self.entries]
        self._search = [(entry["w"].casefold(), text.casefold())
                        for entry, text in zip(self.entries, self._meanings)]
        self._meta = []
        self._levels = []
        self._counts = {key: 0 for key, _ in CATEGORIES}
        self._counts.update(learned=0, predicted=0)
        self._counts["all"] = len(self.entries)
        for entry in self.entries:
            key = entry["w"]
            try:
                category, level, label = memory_info(
                    key, self.states, self.known, self.predicted)
            except TypeError:
                # Retain compatibility with older entries.py providers.
                category, level, label = memory_info(key, self.states, self.known)
            if category not in ("mastered", "predicted", "known", "unlearned"):
                category = "unlearned"
            if category == "predicted":
                self._counts["mastered"] = self._counts.get("mastered", 0) + 1
            self._meta.append((category, label))
            self._levels.append(level)
            self._counts[category] = self._counts.get(category, 0) + 1
            if category != "unlearned":
                self._counts["learned"] = self._counts.get("learned", 0) + 1
            if key in self.predicted:
                self._counts["predicted"] = self._counts.get("predicted", 0) + 1
        self._counts.setdefault("learned", 0)
        self._counts.setdefault("predicted", 0)
        self._row_meta_dirty = True
        self.refilter()

    def _entry_level(self, entry):
        pos = self._pos_by_id.get(id(entry))
        if pos is None or pos >= len(self._levels):
            return None
        return self._levels[pos]

    def _sort_rows(self, rows):
        if self.order_index is not None:
            return sorted(rows, key=lambda entry: self.order_index.get(
                entry.get("w", ""), len(self.order_index)))
        return sorted(rows, key=lambda entry: word_caption(entry).casefold())

    def set_order(self, entries, preserve_order=False):
        self.order_index = ({entry.get("w", ""): index
                             for index, entry in enumerate(entries)}
                            if preserve_order else None)
        self.refilter()

    def set_scale(self, scale):
        scale = max(1.0, min(1.6, float(scale)))
        if scale == self.scale:
            return
        self.scale = scale
        self._font = QFont("Microsoft YaHei UI")
        self._font.setPixelSize(round(13 * scale))
        self.dataChanged.emit(self.index(0, 0),
                              self.index(max(0, len(self.rows) - 1), 2),
                              [Qt.FontRole])

    def meaning(self, entry):
        """入口缓存索引：按 entries 原始位置找一次，找不到才 format。"""
        pos = self._pos_by_id.get(id(entry))
        if pos is None:
            return meaning(entry)
        return self._meanings[pos] if pos < len(self._meanings) else meaning(entry)

    def meaning_for_row(self, row):
        if 0 <= row < len(self.rows):
            entry = self.rows[row]
            pos = self._pos_by_id.get(id(entry))
            if pos is None:
                return meaning(entry)
            return self._meanings[pos] if pos < len(self._meanings) else meaning(entry)
        return ""

    def _build_row_meta(self):
        self._row_meta = [
            self._meta[self._pos_by_id[id(entry)]]
            if id(entry) in self._pos_by_id else ("unlearned", "")
            for entry in self.rows
        ]
        self._row_meta_dirty = False

    def label_for_row(self, row):
        if 0 <= row < len(self.rows):
            if self._row_meta_dirty:
                self._build_row_meta()
            return self._row_meta[row][1]
        return ""

    def meta_for_row(self, row):
        if 0 <= row < len(self.rows):
            if self._row_meta_dirty:
                self._build_row_meta()
            return self._row_meta[row]
        return ("unlearned", "")

    def refilter(self, category=None, query=None):
        if category is not None:
            self.category = category
        if query is not None:
            self.query = query.strip().casefold()
        self.beginResetModel()
        cat = self.category
        query = self.query
        if cat == "all" and not query:
            self.rows = list(self.entries)
        else:
            rows = []
            for entry, (word_ci, meaning_ci), (entry_cat, _) in zip(
                    self.entries, self._search, self._meta):
                key = entry["w"]
                if cat == "predicted" and key not in self.predicted:
                    continue
                if cat == "learned" and entry_cat == "unlearned":
                    continue
                if cat not in ("all", "predicted", "learned") and entry_cat != cat:
                    continue
                if query and query not in word_ci and query not in meaning_ci:
                    continue
                rows.append(entry)
            self.rows = rows
        self.rows = self._sort_rows(self.rows)
        self._row_meta_dirty = True
        self.endResetModel()

    def counts(self):
        return dict(self._counts)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def flags(self, index):
        flags = super().flags(index)
        if (index.isValid() and index.column() == 0 and self.selection_mode):
            flags |= Qt.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if (not index.isValid() or index.column() != 0
                or role != Qt.CheckStateRole or not self.selection_mode):
            return False
        key = self.rows[index.row()]["w"]
        if value == Qt.Checked:
            self.selected_keys.add(key)
        else:
            self.selected_keys.discard(key)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ("单词 / 词组", "释义", "记忆等级")[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        row = index.row()
        entry = self.rows[row]
        if role == Qt.CheckStateRole and index.column() == 0 and self.selection_mode:
            return Qt.Checked if entry["w"] in self.selected_keys else Qt.Unchecked
        if role == Qt.DisplayRole:
            if index.column() == 0:
                return word_caption(entry)
            if index.column() == 1:
                return self.meaning_for_row(row)
            return self.label_for_row(row)
        category, label = self.meta_for_row(row)
        if role == Qt.ToolTipRole:
            if index.column() == 2:
                state = self.states.get(entry["w"]) or {}
                due = state.get("due")
                stamp = ("\n下次复习：" + time.strftime("%Y-%m-%d %H:%M", time.localtime(due))) \
                    if isinstance(due, (int, float)) else ""
                return label + stamp
            has_overlay = any(isinstance(entry.get(field), str) and entry[field].strip()
                              for field in ("display_s", "level_s"))
            detail = self.meaning_for_row(row) if has_overlay else (entry.get("raw") or self.meaning_for_row(row))
            return word_caption(entry) + "\n" + detail
        if role == Qt.ForegroundRole:
            # 单词列/释义/等级列统一普通文字色，不再按记忆分类染色。
            return QColor(self.palette["fg_mean"])
        if role == Qt.FontRole:
            return QFont(self._font)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignVCenter | (Qt.AlignCenter if index.column() == 2 else Qt.AlignLeft))
        return None


class ControlFlowLayout(QLayout):
    """Keep complete button labels; wrap only the small toolbar, never table rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Horizontal)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def minimumSize(self):
        # A flow group needs one full button, not the sum of all button widths.
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect, apply):
        x, y, row_height = rect.x(), rect.y(), 0
        spacing = self.spacing()
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint().expandedTo(item.minimumSize())
            if row_height and x + size.width() > rect.x() + rect.width():
                x, y, row_height = rect.x(), y + row_height + spacing, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + spacing
            row_height = max(row_height, size.height())
        return y + row_height - rect.y()


class BookCatalog(QWidget):
    bulk_learn_requested = pyqtSignal(object)
    toggle_select_mode = pyqtSignal(bool)
    refresh_metadata = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("catalog")
        self.theme = th.get(th.DEFAULT)
        self.book_id = None
        self.level_dialog = None
        self._scale = 1.0
        self._height_cache = OrderedDict()
        self._measured_rows = set()
        self._measure_calls = 0
        self._columns_dirty = False
        self._measure_timer = QTimer(self)
        self._measure_timer.setSingleShot(True)
        self._measure_timer.setInterval(MEASURE_DELAY_MS)
        self._measure_timer.timeout.connect(self._measure_visible)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.path_label)
        self.path_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.filter_controls = QWidget(self)
        self.filter_layout = ControlFlowLayout(self.filter_controls)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_chips = {}
        # entries providers may already expose learned/predicted. Never create two
        # widgets for the same key: a dict would orphan the first widget's state.
        self._category_labels = []
        seen_categories = set()
        for key, label in list(CATEGORIES) + [
                ("learned", "已学习"), ("predicted", "预测掌握")]:
            if key in seen_categories:
                continue
            seen_categories.add(key)
            self._category_labels.append((key, label))
            button = QPushButton(label)
            button.setObjectName("chip")
            button.setProperty("catalogControl", "filter")
            button.setProperty("on", "0")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _, k=key: self.set_filter(k))
            self.filter_group.addButton(button)
            self.filter_layout.addWidget(button)
            self.filter_chips[key] = button
        layout.addWidget(self.filter_controls)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索单词、词组或释义")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._search_changed)
        layout.addWidget(self.search)
        self.selection_controls = QWidget(self)
        self.selection_layout = ControlFlowLayout(self.selection_controls)
        self.select_mode_button = QPushButton("选择")
        self.select_mode_button.setObjectName("chip")
        self.select_mode_button.setProperty("catalogControl", "selection")
        self.select_mode_button.setProperty("on", "0")
        self.select_mode_button.setCheckable(True)
        self.select_mode_button.toggled.connect(self._selection_mode_changed)
        self.selection_layout.addWidget(self.select_mode_button)
        self.select_filtered_button = QPushButton("选择当前筛选")
        self.select_filtered_button.clicked.connect(self.select_filtered)
        self.select_filtered_button.hide()
        self.selection_layout.addWidget(self.select_filtered_button)
        self.bulk_learn_button = QPushButton("加入学习")
        self.bulk_learn_button.clicked.connect(self._request_bulk_learn)
        self.bulk_learn_button.hide()
        self.selection_layout.addWidget(self.bulk_learn_button)
        for button in (self.select_filtered_button, self.bulk_learn_button):
            button.setObjectName("chip")
            button.setProperty("catalogControl", "action")
        for button in (self.select_mode_button, self.select_filtered_button,
                       self.bulk_learn_button):
            button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.selection_controls)
        self.selection_hint = QLabel(
            "勾选词条或选择当前筛选，再加入学习；切换筛选保留已选词。")
        self.selection_hint.setWordWrap(True)
        self.selection_hint.setTextFormat(Qt.PlainText)
        self.selection_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.selection_hint.hide()
        layout.addWidget(self.selection_hint)
        self.model = WordTableModel(self)
        self.table = NoSelectTableView()
        self.table.setModel(self.model)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setItemDelegate(TextWrapDelegate(self.table))
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setMinimumSectionSize(DEFAULT_ROW)
        self.table.verticalHeader().setDefaultSectionSize(DEFAULT_ROW)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.level_header = LevelHeader(self.table)
        self.table.setHorizontalHeader(self.level_header)
        header = self.level_header
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)   # 不再 ResizeToContents
        self.table.setColumnWidth(0, 142)
        self.table.setColumnWidth(2, 96)
        header.level_clicked.connect(self.show_levels)
        # QTableView 内部已连接 sectionPressed -> selectColumn；即使 NoSelection
        # 也会建立 (0, column) current。随后清理，不禁用表格键盘/滚动能力。
        header.sectionPressed.connect(self.table._clear_current)
        header.sectionClicked.connect(self.table._clear_current)
        header.sectionDoubleClicked.connect(self.table._clear_current)
        header.sectionResized.connect(self._columns_resized)
        # The badge is a viewport child, not painted section content. Keep it
        # aligned with its level column when narrow/high-font tables scroll.
        self.table.horizontalScrollBar().valueChanged.connect(header.refresh_badge)
        self.table.verticalScrollBar().valueChanged.connect(self._schedule_measure)
        self.table.viewport().installEventFilter(self)
        self.model.modelReset.connect(self._schedule_measure)
        self.model.layoutChanged.connect(self._schedule_measure)
        layout.addWidget(self.table, 1)
        self.set_palette(self.theme)

    # ------------------------------------------------------------------
    # 行高测量（只测 visible + buffer）
    # ------------------------------------------------------------------
    @property
    def measured_rows(self):
        return len(self._measured_rows)

    @property
    def measure_calls(self):
        return self._measure_calls

    def _schedule_measure(self, *_args):
        if not hasattr(self, "_measure_timer"):
            return
        self._measure_timer.start()          # 16ms coalesce

    def eventFilter(self, obj, ev):
        if obj is self.table.viewport() and ev.type() in (
                QEvent.Resize, QEvent.Show, QEvent.Polish):
            self._schedule_measure()
        return super().eventFilter(obj, ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._schedule_measure()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._schedule_measure()

    def _default_row(self):
        return max(1, round(DEFAULT_ROW * self._scale))

    def _text_width(self, column):
        # 不用固定 40 下限：用户可把 word 列拖到 header 最小宽度；
        # 实际 delegate 文本宽只有 max(1, columnWidth - 2*CELL_PAD_X)。
        width = self.table.columnWidth(column)
        return max(1, width - 2 * CELL_PAD_X)

    def _font(self):
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(round(13 * self._scale))
        return font

    def _cache_get(self, key):
        value = self._height_cache.get(key)
        if value is not None:
            self._height_cache.move_to_end(key)
        return value

    def _cache_put(self, key, value):
        self._height_cache[key] = value
        self._height_cache.move_to_end(key)
        while len(self._height_cache) > HEIGHT_CACHE_LIMIT:
            self._height_cache.popitem(last=False)

    def measure_height(self, text, width, word="", widths=None):
        """单列文本高度；cache key 含 word + widths + 实际文本宽 + scale + text。"""
        key = (str(word), tuple(widths or ()), int(width),
               round(self._scale, 3), str(text))
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        fm = QFontMetrics(self._font())
        rect = fm.boundingRect(0, 0, max(1, int(width)), 0,
                               Qt.TextWordWrap | Qt.AlignLeft, str(text))
        height = max(self._default_row(), rect.height() + 2 * CELL_PAD_Y)
        self._cache_put(key, height)
        return height

    def _row_height(self, row):
        if not (0 <= row < self.model.rowCount()):
            return self._default_row()
        entry = self.model.rows[row]
        widths = (self.table.columnWidth(0), self.table.columnWidth(1),
                  self.table.columnWidth(2))
        word = entry["w"]
        heights = [
            self.measure_height(word_caption(entry), self._text_width(0), word, widths),
            self.measure_height(self.model.meaning_for_row(row),
                                self._text_width(1), word, widths),
            self.measure_height(self.model.label_for_row(row),
                                self._text_width(2), word, widths),
        ]
        return max(self._default_row(), max(heights))

    def _measure_visible(self):
        if not hasattr(self, "table") or self.model.rowCount() == 0:
            return
        viewport = self.table.viewport()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return
        self._measure_calls += 1
        count = self.model.rowCount()
        first = self.table.rowAt(0)
        last = self.table.rowAt(max(0, viewport.height() - 1))
        if first < 0:
            first = 0
        if last < 0:
            last = min(count - 1, first + 2 * BUFFER_ROWS)
        first = max(0, first - BUFFER_ROWS)
        last = min(count - 1, last + BUFFER_ROWS)
        vh = self.table.verticalHeader()
        for row in range(first, last + 1):
            height = self._row_height(row)
            self._measured_rows.add(row)
            if vh.sectionSize(row) != height:
                vh.resizeSection(row, height)

    def _invalidate_rows(self):
        """清缓存/已测标记，但不把当前已测行高重置成 48。

        关键：长行测量后会出现/改变垂直滚动条，Stretch 列宽随之变化并触发
        sectionResized；如果这里把行高重置为 48，会再次隐藏滚动条，形成
        “48 -> 长行 -> 滚动条 -> 48” 的自触发循环。保持当前行高直到下一次
        可见行重新测量即可，行数仍只限可见+buffer。
        """
        self._measured_rows.clear()
        self._height_cache.clear()
        self._columns_dirty = False
        self._schedule_measure()

    def _columns_resized(self, *_args):
        if getattr(self, "_applying_columns", False):
            return
        # 列宽变化只重新测量可见行；不清/不重置已测行高（避免滚动条循环）。
        self._schedule_measure()
        if hasattr(self, "level_header"):
            self.level_header.refresh_badge()

    # ------------------------------------------------------------------
    def set_book(self, book_id, path, entries, states, known=None, preserve_order=False,
                 predicted=None):
        self.book_id = book_id
        self.path_label.setText(path)
        self.search.clear()
        self.model.category = "all"
        self.model.set_entries(entries, states, known, preserve_order=preserve_order,
                               predicted=predicted)
        self.set_filter("all")
        self.table.scrollToTop()
        self._invalidate_rows()
        if hasattr(self, "level_header"):
            self.level_header.refresh_badge()

    def _search_changed(self, query):
        self.model.refilter(query=query)
        self._schedule_measure()

    def set_metadata(self, states=None, known=None, predicted=None):
        """Refresh memory/prediction classification without replacing book entries."""
        self.model.set_entries(
            self.model.entries,
            self.model.states if states is None else states,
            self.model.known if known is None else known,
            preserve_order=self.model.order_index is not None,
            predicted=self.model.predicted if predicted is None else predicted)
        self.set_filter(self.model.category)
        self.refresh_metadata.emit()

    def _selection_mode_changed(self, enabled):
        self.set_selection_mode(enabled)

    def set_selection_mode(self, enabled):
        enabled = bool(enabled)
        self.select_mode_button.blockSignals(True)
        self.select_mode_button.setChecked(enabled)
        self.select_mode_button.blockSignals(False)
        self.select_mode_button.setProperty("on", "1" if enabled else "0")
        self.select_mode_button.style().unpolish(self.select_mode_button)
        self.select_mode_button.style().polish(self.select_mode_button)
        self.select_mode_button.update()
        self.model.selection_mode = enabled
        self.table.setEditTriggers(
            QAbstractItemView.AllEditTriggers if enabled
            else QAbstractItemView.NoEditTriggers)
        self.select_filtered_button.setVisible(enabled)
        self.bulk_learn_button.setVisible(enabled)
        self.selection_hint.setVisible(enabled)
        self.selection_layout.invalidate()
        self.selection_controls.updateGeometry()
        if self.model.rowCount():
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(self.model.rowCount() - 1, 0),
                [Qt.CheckStateRole])
        self.toggle_select_mode.emit(enabled)

    def select_filtered(self):
        self.model.selected_keys.update(entry["w"] for entry in self.model.rows)
        if self.model.rowCount():
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(self.model.rowCount() - 1, 0),
                [Qt.CheckStateRole])

    def _request_bulk_learn(self):
        keys = sorted(self.model.selected_keys, key=str.casefold)
        if keys:
            self.bulk_learn_requested.emit(keys)

    def set_filter(self, category):
        if category not in self.filter_chips:
            category = "all"
        self.model.refilter(category=category)
        counts = self.model.counts()
        self.filter_chips[category].setChecked(True)
        for key, label in self._category_labels:
            button = self.filter_chips[key]
            button.setText("%s %s" % (label, format(counts.get(key, 0), ",")))
            button.setProperty("on", "1" if key == category else "0")
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self.filter_layout.invalidate()
        self.filter_controls.updateGeometry()
        self._invalidate_rows()

    def _level_header_clicked(self, section):
        if section == 2:
            self.show_levels()

    def show_levels(self, index=None):
        """由「记忆等级」表头文字或透明徽标打开；表格行不弹说明。"""
        if self.level_dialog is not None:
            self.level_dialog.close()
        dialog = QDialog(self.window())
        dialog.setWindowTitle("记忆等级")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        dialog.resize(420, 520)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(7)
        title = QLabel("记忆等级")
        title.setStyleSheet(th.label_qss(self.theme, "title", 18))
        outer.addWidget(title)
        outer.addSpacing(6)
        for line in LEVEL_LINES:
            level_text, _, detail = line.partition("：")
            row = QHBoxLayout()
            row.setSpacing(10)
            left = QLabel(level_text)
            left.setStyleSheet(th.label_qss(self.theme, "title", 14))
            left.setFixedWidth(max(72, round(76 * self._scale)))
            row.addWidget(left)
            right = QLabel(detail)
            right.setWordWrap(True)
            right.setStyleSheet(th.label_qss(self.theme, "mean", 14))
            row.addWidget(right, 1)
            outer.addLayout(row)
        outer.addStretch(1)
        close = QPushButton("知道了")
        close.setObjectName("remember")
        close.setCursor(Qt.PointingHandCursor)
        close.setMinimumHeight(36)
        close.clicked.connect(dialog.close)
        outer.addWidget(close)
        dialog.setStyleSheet(th.qss(self.theme) +
                            "QDialog{background:%s;}" % self.theme["bg"])
        self.level_dialog = dialog
        dialog.show()

    def set_palette(self, palette):
        had_dialog = (self.level_dialog is not None
                      and not self.level_dialog.isHidden())
        self.theme = palette
        self.model.palette = palette
        self.set_scale(self._scale)
        if had_dialog:
            # 说明窗口若正开着，主题切换后按新主题重建
            self.show_levels()

    def set_scale(self, scale):
        scale = max(1.0, min(1.6, float(scale)))
        self._scale = scale
        self.model.set_scale(scale)
        # Local QSS also styles standalone catalogs. Focus is a border, hover is
        # transient; only semantic `on` paints the persistent selected fill.
        self.setStyleSheet(th.qss(self.theme, scale) + (
            'QPushButton#chip[catalogControl]{border:1px solid transparent;'
            'padding:%(pad_y)dpx %(pad_x)dpx;outline:0;}'
            'QPushButton#chip[catalogControl]:focus{border-color:%(accent)s;}'
            'QPushButton#chip[catalogControl]:pressed{background:%(btn_pressed)s;'
            'color:%(chip_fg)s;}'
            'QPushButton#chip[catalogControl][on="1"]{background:%(chip_sel)s;'
            'color:%(chip_sel_fg)s;}'
            % dict(self.theme, pad_y=round(5 * scale), pad_x=round(10 * scale))))
        self.filter_layout.setSpacing(round(6 * scale))
        self.selection_layout.setSpacing(round(6 * scale))
        self.filter_layout.invalidate()
        self.selection_layout.invalidate()
        self.filter_controls.updateGeometry()
        self.selection_controls.updateGeometry()
        self.selection_hint.setStyleSheet(
            th.label_qss(self.theme, "note", round(12 * scale)))
        self.path_label.setStyleSheet(th.label_qss(self.theme, "mean", round(13 * scale)))
        self.table.setStyleSheet(
            "QTableView{border:none;background:%(bg)s;color:%(fg_mean)s;outline:0;"
            "selection-background-color:%(bg)s;selection-color:%(fg_mean)s;}"
            "QTableView::item:selected,QTableView::item:focus{"
            "background:%(bg)s;color:%(fg_mean)s;border:none;outline:0;}"
            "QHeaderView{border:none;outline:0;}"
            "QHeaderView::section{background:%(bg)s;color:%(muted)s;border:none;"
            "padding:%(header_pad)dpx;font-size:%(header_size)dpx;}"
            "QHeaderView::section:checked,QHeaderView::section:pressed{"
            "background:%(bg)s;color:%(muted)s;}"
            % dict(self.theme, header_pad=round(7 * scale), header_size=round(12 * scale)))
        self._applying_columns = True
        try:
            self.table.setColumnWidth(0, round(142 * scale))
            self.table.setColumnWidth(2, round(96 * scale))
        finally:
            self._applying_columns = False
        self.table.verticalHeader().setMinimumSectionSize(self._default_row())
        self.table.verticalHeader().setDefaultSectionSize(self._default_row())
        if hasattr(self, "level_header"):
            self.level_header.set_icon_style(self.theme["muted"], scale)
        self._invalidate_rows()
