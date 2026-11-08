# -*- coding: utf-8 -*-
"""V1.3.0 独立窗口控制器（不依赖 main.py / 真实数据）。

WindowController 负责一个 frameless 顶层 QWidget 的实际窗口几何：
  * 正常窗：可四边鼠标拖拽缩放，最小 520×430；正常窗本身可放大到当前屏幕
    可用工作区（不是 1.6×；MAX_SCALE 只用于字体/控件 scale_factor），并限制在可见工作区；
  * 小窗：固定 356×196，不可 resize；靠近可用工作区任一边（8px 阈值）时吸附，
    鼠标离开后缩成 8px 小条，悬停小条再展开；正常窗永不自动收条；
  * 支持多屏负坐标（用 QScreen.availableGeometry），窗口不会被拖到屏幕外；
  * restore/state 保存正常窗尺寸/位置、小窗展开的逻辑位置、用户小窗偏好；
    collapsed 小条尺寸与屏幕外坐标永远不会写进 state。

API（给 Lead 接入用）
--------------------
WindowController(widget: QWidget, parent: QObject | None = None)
    QObject，changed = pyqtSignal()。

只读属性
    normal_size      -> QSize     正常窗逻辑尺寸（最小 520×430，最大 = 当前屏幕可用工作区）
    compact          -> bool      当前实际是否处于小窗（临时页面也可能为 True）
    preferred_compact-> bool      用户选择的小窗偏好（remember=False 不改变它）
    collapsed        -> bool      当前是否缩成贴边小条
    dock_edge        -> str|None  "left"/"right"/"top"/"bottom"/None
    scale_factor     -> float     字体/控件缩放 min(normal_w/520, normal_h/430, 1.6)

方法
    restore(saved: dict, allow_compact=True)
        saved 缺省时：正常窗 520×430、小窗 356×196；恢复 x/y、normal_w/normal_h
        以及用户 compact 偏好。allow_compact=False 时只恢复偏好、本次保持正常窗。
    set_compact(on: bool, remember=True)
        remember=False 用于「临时页面」：只改实际窗口，不改用户偏好。
    set_normal_size(width, height)
        正常窗最小 520×430，最大为当前屏幕可用工作区；1.6×仅限制字体/控件；
        小窗期间只更新记忆中的正常尺寸。
    state() -> dict
        JSON 可序列化。键：version / normal_w / normal_h / normal_x / normal_y /
        compact_x / compact_y / x / y / w / h / compact / dock_edge。
        其中 w/h 是「逻辑尺寸」：小窗永远 356×196，收条时也绝不写 8px；
        x/y 是当前逻辑左上角；compact 是用户偏好，不是临时页面状态。
    reveal()
        收条 -> 展开回 356×196；未收条时 no-op。
    clamp_position(point: QPoint) -> QPoint
        供主窗口背景拖拽用：把逻辑左上角限制在当前屏幕可用工作区。
    update_palette(theme: dict)
        可选：只记录/刷新，不负责重排布局（布局缩放由 Lead 的 UI 层处理）。

事件
    * controller 用 eventFilter 处理四边 resize、Move/Resize 夹紧、hover 收/展；
    * 不接管背景拖拽：主窗口拖拽时调用 clamp_position()，或直接 move 后由 Move
      事件自动夹紧；若以后要完全接管，再加 drag 逻辑即可。
    * 收条时只隐藏 widget 的直接子控件（排除 isWindow() 的 QDialog/弹出窗口），
      展开时恢复它们原来的可见性，不把窗口移到屏幕外，也不改 child 的 hidden 状态来源；
    * 接管正常/展开小窗的「背景拖拽」（只处理发到顶层 widget 本身的鼠标事件，
      子控件/按钮事件不拦截；Lead 可以移除 Card 旧 background drag）。
"""
from PyQt5.QtCore import (QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer,
                          pyqtSignal)
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QWidget

NORMAL_MIN = (520, 430)
COMPACT_SIZE = (356, 196)
MAX_SCALE = 1.6

STRIP_THICKNESS = 8          # 收条后的厚度（~8px）
SNAP_DISTANCE = 8            # 贴边吸附阈值
EDGE_RESIZE_MARGIN = 6       # 正常窗四边可拖拽的像素宽度
HOVER_DELAY_MS = 120         # 鼠标离开后延迟收条，避免 child 间移动误触发


def _safe_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(default)


class WindowController(QObject):
    changed = pyqtSignal()

    SNAP_DISTANCE = SNAP_DISTANCE
    STRIP_THICKNESS = STRIP_THICKNESS
    EDGE_RESIZE_MARGIN = EDGE_RESIZE_MARGIN

    def __init__(self, widget, parent=None):
        super().__init__(parent if parent is not None else widget)
        if not isinstance(widget, QWidget):
            raise TypeError("WindowController(widget) 需要 QWidget")
        self.widget = widget
        self.theme = {}

        self._normal_size = QSize(*NORMAL_MIN)
        self._normal_pos = widget.pos()

        self._compact = False
        self._preferred_compact = False
        self._collapsed = False
        self._dock_edge = None
        self._preferred_dock_edge = None      # 临时 normal 时仍保留“下次小窗贴哪边”
        self._compact_logical_rect = None      # 小窗展开时的逻辑 rect（收条也不丢）
        self._docked_small = False             # 520×430 小巧正常窗也支持贴边隐藏
        self._small_logical_rect = None        # 520×430 展开时的逻辑 rect（收条不丢）

        self._hidden_children = []             # [[child, was_visible], ...]
        self._updating_children = False
        self._resizing = None                  # dict
        self._dragging = None                  # dict
        self._adjusting = False
        self._suppress_changed = False
        self._emitting_changed = False
        self._hover_inside = False

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._on_hover_timeout)

        self.widget.installEventFilter(self)
        self.widget.setMouseTracking(True)
        self._install_child_filters()

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------
    @property
    def normal_size(self):
        """正常窗逻辑尺寸（QSize）。"""
        return QSize(self._normal_size)

    @property
    def compact(self):
        return bool(self._compact)

    @property
    def preferred_compact(self):
        return bool(self._preferred_compact)

    @preferred_compact.setter
    def preferred_compact(self, value):
        value = bool(value)
        if value == self._preferred_compact:
            return
        self._preferred_compact = value
        if not value:
            self._preferred_dock_edge = None
        self._emit_changed()

    @property
    def collapsed(self):
        return bool(self._collapsed)

    @property
    def dock_edge(self):
        return self._dock_edge

    @property
    def actual_size(self):
        """当前实际窗口尺寸（收条时是 8px 小条；外部一般不用它做保存）。"""
        return QSize(self.widget.size())

    @property
    def scale_factor(self):
        """正常尺寸 UI 缩放：min(width/520, height/430, MAX_SCALE)。"""
        n = self._normal_size
        return min(n.width() / float(NORMAL_MIN[0]),
                   n.height() / float(NORMAL_MIN[1]),
                   MAX_SCALE)

    # ------------------------------------------------------------------
    # 屏幕 / 几何工具
    # ------------------------------------------------------------------
    def _screens(self):
        """可被测试替换的屏幕列表（假屏幕也可）。"""
        return QApplication.screens() or [QApplication.primaryScreen()]

    def _work_area_for(self, point=None):
        screens = [s for s in self._screens() if s is not None]
        if not screens:
            return QRect(0, 0, 800, 600)
        if point is not None:
            for s in screens:
                g = s.availableGeometry()
                if g.contains(QPoint(int(point.x()), int(point.y()))):
                    return QRect(g)
        # 离哪个屏幕最近就用哪个（支持负坐标多屏）
        if point is None:
            return QRect(screens[0].availableGeometry())
        p = QPoint(int(point.x()), int(point.y()))
        best, best_d = None, None
        for s in screens:
            g = s.availableGeometry()
            dx = max(g.left() - p.x(), 0, p.x() - g.right())
            dy = max(g.top() - p.y(), 0, p.y() - g.bottom())
            d = dx * dx + dy * dy
            if best_d is None or d < best_d:
                best, best_d = QRect(g), d
        return best or QRect(0, 0, 800, 600)

    @staticmethod
    def _clamp_value(v, lo, hi):
        return min(max(v, lo), hi)

    def _max_normal(self, geo):
        # 正常窗本身不按 1.6× 限制：最大就是当前屏幕可用工作区。
        # MAX_SCALE 只用于字体/控件 scale_factor。
        lo_w = min(NORMAL_MIN[0], geo.width())
        lo_h = min(NORMAL_MIN[1], geo.height())
        hi_w = max(lo_w, geo.width())
        hi_h = max(lo_h, geo.height())
        return lo_w, lo_h, hi_w, hi_h

    def _clamp_normal_size(self, size, geo):
        lo_w, lo_h, hi_w, hi_h = self._max_normal(geo)
        w = self._clamp_value(int(size.width()), lo_w, hi_w)
        h = self._clamp_value(int(size.height()), lo_h, hi_h)
        return QSize(w, h)

    def _clamp_pos_for(self, point, size, geo):
        w = min(int(size.width()), geo.width())
        h = min(int(size.height()), geo.height())
        x = self._clamp_value(int(point.x()), geo.left(),
                              geo.left() + geo.width() - w)
        y = self._clamp_value(int(point.y()), geo.top(),
                              geo.top() + geo.height() - h)
        return QPoint(x, y)

    def clamp_position(self, point):
        """把逻辑左上角限制在当前屏幕可用工作区（窗口完整可见）。"""
        size = self._logical_size()
        geo = self._work_area_for(point)
        return self._clamp_pos_for(point, size, geo)

    # ------------------------------------------------------------------
    # 逻辑尺寸 / 位置
    # ------------------------------------------------------------------
    def _logical_size(self):
        if self._compact:
            return QSize(*COMPACT_SIZE)
        return QSize(self._normal_size)

    def _is_small_normal(self):
        """520×430 的普通窗：尺寸仍算正常窗，但支持与 compact 相同的贴边收起。"""
        return (not self._compact and
                self._normal_size == QSize(*NORMAL_MIN))

    def _auto_hide_enabled(self):
        return bool(self._compact or self._is_small_normal())

    def _logical_pos(self):
        if self._compact:
            if self._compact_logical_rect is not None:
                return self._compact_logical_rect.topLeft()
            return QPoint(self.widget.pos())
        return QPoint(self._normal_pos if self._normal_pos is not None
                      else self.widget.pos())

    def _set_normal_geometry(self):
        """把 widget 调回正常窗尺寸/位置（使用当前 _normal_size/_normal_pos）。"""
        if self._normal_pos is None:
            self._normal_pos = QPoint(self.widget.pos())
        geo = self._work_area_for(self._normal_pos)
        self._normal_size = self._clamp_normal_size(self._normal_size, geo)
        self._normal_pos = self._clamp_pos_for(self._normal_pos, self._normal_size, geo)
        lo_w, lo_h, hi_w, hi_h = self._max_normal(geo)
        self._adjusting = True
        try:
            self.widget.setMinimumSize(lo_w, lo_h)
            self.widget.setMaximumSize(hi_w, hi_h)
            self.widget.setGeometry(self._normal_pos.x(), self._normal_pos.y(),
                                    self._normal_size.width(),
                                    self._normal_size.height())
        finally:
            self._adjusting = False

    def _set_compact_geometry(self, pos, edge=None):
        """展开的小窗：356×196，按需贴边。"""
        size = QSize(*COMPACT_SIZE)
        geo = self._work_area_for(QPoint(pos) + QPoint(size.width() // 2, size.height() // 2))
        pos = self._clamp_pos_for(QPoint(pos), size, geo)
        if edge in ("left", "right", "top", "bottom"):
            pos = self._snap_pos(pos, size, edge, geo)
        else:
            edge = self._detect_dock_edge(QRect(pos, size), geo)
            if edge:
                pos = self._snap_pos(pos, size, edge, geo)
        self._dock_edge = edge
        if edge:
            self._preferred_dock_edge = edge
        self._compact_logical_rect = QRect(QPoint(pos), size)
        self._adjusting = True
        try:
            self.widget.setMinimumSize(COMPACT_SIZE[0], COMPACT_SIZE[1])
            self.widget.setMaximumSize(COMPACT_SIZE[0], COMPACT_SIZE[1])
            self.widget.setGeometry(pos.x(), pos.y(), COMPACT_SIZE[0], COMPACT_SIZE[1])
        finally:
            self._adjusting = False

    def _set_strip_geometry(self):
        """收条：按 dock_edge 缩成 8px 小条，逻辑尺寸保持不变。

        compact 保持 356×196；520×430 小巧正常窗保持 520×430。
        """
        logical = self._logical_size()
        if self._compact:
            if self._compact_logical_rect is None:
                self._compact_logical_rect = QRect(QPoint(self.widget.pos()), logical)
            rect = QRect(self._compact_logical_rect)
        else:
            if self._small_logical_rect is None:
                pos = (self._normal_pos if self._normal_pos is not None
                       else QPoint(self.widget.pos()))
                self._small_logical_rect = QRect(pos, logical)
            rect = QRect(self._small_logical_rect)
        rect.setSize(logical)
        geo = self._work_area_for(rect.center())
        rect = QRect(self._clamp_pos_for(rect.topLeft(), rect.size(), geo), rect.size())
        if self._compact:
            self._compact_logical_rect = rect
        else:
            self._small_logical_rect = rect
            self._normal_pos = rect.topLeft()
        edge = self._dock_edge or self._detect_dock_edge(rect, geo)
        if not edge:
            return False
        self._dock_edge = edge
        self._preferred_dock_edge = edge
        if edge == "left":
            strip = QRect(geo.left(), rect.top(), STRIP_THICKNESS,
                          min(rect.height(), geo.height()))
        elif edge == "right":
            strip = QRect(geo.left() + geo.width() - STRIP_THICKNESS, rect.top(),
                          STRIP_THICKNESS, min(rect.height(), geo.height()))
        elif edge == "top":
            strip = QRect(rect.left(), geo.top(),
                          min(rect.width(), geo.width()), STRIP_THICKNESS)
        else:
            strip = QRect(rect.left(), geo.top() + geo.height() - STRIP_THICKNESS,
                          min(rect.width(), geo.width()), STRIP_THICKNESS)
        strip = QRect(self._clamp_pos_for(strip.topLeft(), strip.size(), geo),
                      strip.size())
        self._adjusting = True
        try:
            self.widget.setMinimumSize(strip.width(), strip.height())
            self.widget.setMaximumSize(strip.width(), strip.height())
            self.widget.setGeometry(strip)
        finally:
            self._adjusting = False
        self._collapsed = True
        return True

    def _snap_pos(self, pos, size, edge, geo):
        x, y = int(pos.x()), int(pos.y())
        if edge == "left":
            x = geo.left()
        elif edge == "right":
            x = geo.left() + geo.width() - int(size.width())
        elif edge == "top":
            y = geo.top()
        elif edge == "bottom":
            y = geo.top() + geo.height() - int(size.height())
        return self._clamp_pos_for(QPoint(x, y), size, geo)

    def _detect_dock_edge(self, rect, geo):
        deltas = (
            ("left", rect.left() - geo.left()),
            ("right", geo.left() + geo.width() - 1 - rect.right()),
            ("top", rect.top() - geo.top()),
            ("bottom", geo.top() + geo.height() - 1 - rect.bottom()),
        )
        best = None
        for idx, (edge, delta) in enumerate(deltas):
            if delta <= SNAP_DISTANCE:
                key = (max(delta, 0), idx)
                if best is None or key < best[0]:
                    best = (key, edge)
        return best[1] if best else None

    # ------------------------------------------------------------------
    # 公开状态控制
    # ------------------------------------------------------------------
    def restore(self, saved, allow_compact=True):
        """恢复窗口状态。saved 缺省/缺键时用 520×430 / 356×196。"""
        saved = saved or {}
        self._hover_timer.stop()
        self._resizing = None
        self._suppress_changed = True
        try:
            if self._collapsed or self._hidden_children:
                self._restore_children()
            self._collapsed = False
            self._dock_edge = None
            self._preferred_dock_edge = None
            self._compact = False

            nw = _safe_int(saved.get("normal_w", saved.get("w", NORMAL_MIN[0])),
                           NORMAL_MIN[0])
            nh = _safe_int(saved.get("normal_h", saved.get("h", NORMAL_MIN[1])),
                           NORMAL_MIN[1])
            geo = self._work_area_for(QPoint(
                _safe_int(saved.get("x", 0), 0), _safe_int(saved.get("y", 0), 0)))
            self._normal_size = self._clamp_normal_size(QSize(nw, nh), geo)

            pref = bool(saved.get("compact", False))
            if "compact" not in saved:
                # 旧版 _win.json 只有 w/h：356×196 说明用户上次用的是小窗
                sw = _safe_int(saved.get("w", -1), -1)
                sh = _safe_int(saved.get("h", -1), -1)
                if (sw, sh) == COMPACT_SIZE:
                    pref = True
            self._preferred_compact = pref
            saved_edge = saved.get("dock_edge")
            if saved_edge in ("left", "right", "top", "bottom") and pref:
                self._preferred_dock_edge = saved_edge
            small_edge = (saved_edge
                          if (not pref
                              and self._normal_size == QSize(*NORMAL_MIN)
                              and saved_edge in ("left", "right", "top", "bottom"))
                          else None)

            # 正常窗位置：normal_x/y 优先，否则 x/y，否则居中
            normal_pos = self._saved_pos(saved, "normal_x", "normal_y",
                                         "x", "y", geo, self._normal_size)
            # 小窗逻辑位置：compact_x/y 优先，否则 x/y，否则正常窗位置
            compact_pos = self._saved_pos(saved, "compact_x", "compact_y",
                                          "x", "y", geo, QSize(*COMPACT_SIZE))
            self._normal_pos = self._clamp_pos_for(normal_pos, self._normal_size, geo)
            self._compact_logical_rect = QRect(
                self._clamp_pos_for(compact_pos, QSize(*COMPACT_SIZE), geo),
                QSize(*COMPACT_SIZE))

            if pref and allow_compact:
                self._compact = True
                edge = saved.get("dock_edge")
                if edge not in ("left", "right", "top", "bottom"):
                    edge = None
                self._set_compact_geometry(self._compact_logical_rect.topLeft(), edge)
                self._docked_small = False
            else:
                self._compact = False
                self._docked_small = bool(small_edge)
                if small_edge:
                    self._dock_edge = small_edge
                    self._preferred_dock_edge = small_edge
                    self._normal_pos = self._snap_pos(
                        self._normal_pos, self._normal_size, small_edge, geo)
                    self._small_logical_rect = QRect(
                        self._normal_pos, QSize(self._normal_size))
                self._set_normal_geometry()
        finally:
            self._suppress_changed = False
        self._emit_changed()

    def _saved_pos(self, saved, kx, ky, fx, fy, geo, size):
        if kx in saved and ky in saved:
            return QPoint(_safe_int(saved.get(kx), geo.left()),
                          _safe_int(saved.get(ky), geo.top()))
        if fx in saved and fy in saved:
            return QPoint(_safe_int(saved.get(fx), geo.left()),
                          _safe_int(saved.get(fy), geo.top()))
        # 缺省居中
        return QPoint(geo.left() + (geo.width() - size.width()) // 2,
                      geo.top() + (geo.height() - size.height()) // 2)

    def set_compact(self, on, remember=True):
        on = bool(on)
        if remember:
            self._preferred_compact = on
        if on == self._compact:
            if remember:
                self._emit_changed()
            return
        self._hover_timer.stop()
        if on:
            # 从正常窗进入小窗：记下正常位置，展开位置用上次小窗位置
            if not self._collapsed:
                self._normal_pos = QPoint(self.widget.pos())
            self._docked_small = False
            self._small_logical_rect = None
            self._restore_children()
            self._collapsed = False
            self._compact = True
            if remember:
                # 用户主动收小窗：留在当前正常窗位置，避免跳回旧小窗位置
                pos = (self._normal_pos if self._normal_pos is not None
                       else QPoint(self.widget.pos()))
            else:
                # 临时页面恢复：优先回到此前的展开小窗逻辑位置/贴边
                pos = (self._compact_logical_rect.topLeft()
                       if self._compact_logical_rect is not None
                       else (self._normal_pos if self._normal_pos is not None
                             else QPoint(self.widget.pos())))
            self._set_compact_geometry(pos, self._preferred_dock_edge)
        else:
            if self._compact and not self._collapsed:
                self._compact_logical_rect = QRect(QPoint(self.widget.pos()),
                                                   QSize(*COMPACT_SIZE))
            self._restore_children()
            self._collapsed = False
            self._compact = False
            self._dock_edge = None
            self._docked_small = False
            self._small_logical_rect = None
            if remember:
                self._preferred_dock_edge = None
            self._set_normal_geometry()
        self._emit_changed()

    def set_normal_size(self, width, height):
        geo = self._work_area_for(self._logical_pos())
        size = self._clamp_normal_size(QSize(_safe_int(width, NORMAL_MIN[0]),
                                             _safe_int(height, NORMAL_MIN[1])), geo)
        self._normal_size = size
        if (not self._compact and
                self._normal_size != QSize(*NORMAL_MIN) and self._docked_small):
            self._docked_small = False
            self._dock_edge = None
            self._preferred_dock_edge = None
            self._small_logical_rect = None
        if not self._compact:
            self._normal_pos = self._clamp_pos_for(self._logical_pos(), size, geo)
            self._set_normal_geometry()
        self._emit_changed()

    def reveal(self):
        if not self._collapsed:
            return
        is_compact = self._compact
        self._restore_children()
        self._collapsed = False
        if is_compact:
            rect = (self._compact_logical_rect
                    or QRect(QPoint(self.widget.pos()), QSize(*COMPACT_SIZE)))
            self._set_compact_geometry(rect.topLeft(), self._dock_edge)
        else:
            rect = (self._small_logical_rect
                    or QRect(QPoint(self.widget.pos()), QSize(self._normal_size)))
            self._normal_pos = rect.topLeft()
            self._set_normal_geometry()
        self._emit_changed()

    def state(self):
        """返回可 JSON 序列化的状态；小条尺寸/屏幕外坐标不会出现在这里。"""
        normal_pos = (self._normal_pos if self._normal_pos is not None
                      else QPoint(self.widget.pos()))
        # 正常窗与小窗可能在不同屏幕：各自按自己的屏幕夹紧，避免互相带偏
        normal_geo = self._work_area_for(normal_pos)
        normal_pos = self._clamp_pos_for(normal_pos, self._normal_size, normal_geo)
        compact_pos = (self._compact_logical_rect.topLeft()
                       if self._compact_logical_rect is not None
                       else (QPoint(self.widget.pos()) if self._compact else normal_pos))
        compact_geo = self._work_area_for(compact_pos)
        compact_pos = self._clamp_pos_for(compact_pos, QSize(*COMPACT_SIZE),
                                          compact_geo)
        cur_pos = compact_pos if self._compact else normal_pos
        cur_size = QSize(*COMPACT_SIZE) if self._compact else QSize(self._normal_size)
        return {
            "version": 1,
            "normal_w": int(self._normal_size.width()),
            "normal_h": int(self._normal_size.height()),
            "normal_x": int(normal_pos.x()),
            "normal_y": int(normal_pos.y()),
            "compact_x": int(compact_pos.x()),
            "compact_y": int(compact_pos.y()),
            "x": int(cur_pos.x()),
            "y": int(cur_pos.y()),
            "w": int(cur_size.width()),
            "h": int(cur_size.height()),
            "compact": bool(self._preferred_compact),
            "dock_edge": (self._dock_edge if self._compact
                          else ((self._dock_edge or self._preferred_dock_edge)
                                if self._is_small_normal()
                                else (self._preferred_dock_edge
                                      if self._preferred_compact else None))),
        }

    def update_palette(self, theme):
        """可选：记录主题并请求重绘；布局缩放由 UI 层处理。"""
        self.theme = dict(theme or {})
        self.widget.update()

    # ------------------------------------------------------------------
    # hover / 收条
    # ------------------------------------------------------------------
    def _cursor_inside(self):
        try:
            if not self.widget.isVisible():
                return False
            return self.widget.frameGeometry().contains(QCursor.pos())
        except Exception:
            return False

    def _on_hover_enter(self):
        self._hover_timer.stop()
        self._hover_inside = True
        if self._collapsed:
            self.reveal()

    def _on_hover_leave(self):
        self._hover_inside = False
        if self._auto_hide_enabled() and self._dock_edge and not self._collapsed:
            self._hover_timer.start()

    def _on_hover_timeout(self):
        if (not self._auto_hide_enabled() or self._collapsed
                or not self._dock_edge):
            return
        if self._cursor_inside():
            return
        self._collapse_if_docked(force=True)

    def _collapse_if_docked(self, force=False):
        if (not self._auto_hide_enabled() or self._collapsed
                or not self._dock_edge):
            return False
        if not force and self._cursor_inside():
            return False
        self._hover_timer.stop()
        if not self._collapsed:
            logical = self._logical_size()
            pos = QPoint(self.widget.pos())
            if self._compact:
                self._compact_logical_rect = QRect(pos, logical)
            else:
                self._small_logical_rect = QRect(pos, logical)
                self._normal_pos = pos
        self._hide_children()
        if not self._set_strip_geometry():
            self._restore_children()
            return False
        self._emit_changed()
        return True

    def _hide_children(self):
        self._restore_children()
        self._hidden_children = []
        self._updating_children = True
        try:
            for child in self.widget.findChildren(QWidget,
                                                  options=Qt.FindDirectChildrenOnly):
                if child.isWindow():
                    continue          # QDialog/弹出窗口不是页面，不参与收条
                if child.isVisible():
                    self._hidden_children.append([child, True])
                    child.hide()
        finally:
            self._updating_children = False
        self.widget.update()

    def _restore_children(self):
        pairs = self._hidden_children
        self._hidden_children = []
        self._updating_children = True
        try:
            for child, was_visible in pairs:
                try:
                    if was_visible:
                        child.show()
                except RuntimeError:
                    pass
        finally:
            self._updating_children = False
        try:
            lay = self.widget.layout()
            if lay is not None:
                lay.activate()
        except Exception:
            pass

    def _track_child_visibility(self, child, visible):
        """收条期间如果页面代码切换了直接子控件可见性，记录最新状态供展开恢复。"""
        try:
            if child.isWindow():
                return
        except RuntimeError:
            return
        for pair in self._hidden_children:
            if pair[0] is child:
                pair[1] = bool(visible)
                return
        if visible:
            self._hidden_children.append([child, True])

    def _emit_changed(self):
        if self._suppress_changed:
            return
        # changed 回调可能改 font/layout 并再次触发 resize/move：内部防递归，递归期间丢弃
        if self._emitting_changed:
            return
        self._emitting_changed = True
        try:
            self.changed.emit()
        finally:
            self._emitting_changed = False

    # ------------------------------------------------------------------
    # 事件过滤
    # ------------------------------------------------------------------
    def _install_child_filters(self):
        for child in self.widget.findChildren(QWidget):
            try:
                child.installEventFilter(self)
                child.setMouseTracking(True)
            except RuntimeError:
                pass

    def _watch_child(self, child):
        if not isinstance(child, QWidget):
            return
        try:
            child.installEventFilter(self)
            child.setMouseTracking(True)
        except RuntimeError:
            pass
        self._install_child_filters_for(child)

    def _install_child_filters_for(self, parent):
        for child in parent.findChildren(QWidget):
            try:
                child.installEventFilter(self)
                child.setMouseTracking(True)
            except RuntimeError:
                pass

    def _edges_at(self, local):
        if self._compact or self._collapsed:
            return ()
        r = self.widget.rect()
        m = self.EDGE_RESIZE_MARGIN
        x, y = local.x(), local.y()
        edges = []
        if x <= m:
            edges.append("left")
        if x >= r.width() - m - 1:
            edges.append("right")
        if y <= m:
            edges.append("top")
        if y >= r.height() - m - 1:
            edges.append("bottom")
        return tuple(edges)

    def _cursor_shape(self, edges):
        left, right = "left" in edges, "right" in edges
        top, bottom = "top" in edges, "bottom" in edges
        if (left and top) or (right and bottom):
            return Qt.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.SizeBDiagCursor
        if left or right:
            return Qt.SizeHorCursor
        if top or bottom:
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _update_cursor(self, obj, ev):
        if self._compact or self._collapsed:
            try:
                self.widget.setCursor(Qt.ArrowCursor)
            except RuntimeError:
                pass
            return
        try:
            local = self.widget.mapFromGlobal(ev.globalPos())
            edges = self._edges_at(local)
            self.widget.setCursor(self._cursor_shape(edges))
        except Exception:
            pass

    def _try_start_resize(self, obj, ev):
        if self._compact or self._collapsed:
            return False
        try:
            local = self.widget.mapFromGlobal(ev.globalPos())
        except Exception:
            return False
        edges = self._edges_at(local)
        if not edges:
            return False
        self._resizing = {
            "edges": edges,
            "start_global": QPoint(ev.globalPos()),
            "start_geo": QRect(self.widget.geometry()),
        }
        self.widget.setCursor(self._cursor_shape(edges))
        return True

    def _do_resize(self, ev):
        info = self._resizing
        if not info:
            return
        edges = info["edges"]
        start = info["start_geo"]
        delta = ev.globalPos() - info["start_global"]
        geo = self._work_area_for(ev.globalPos())
        lo_w, lo_h, hi_w, hi_h = self._max_normal(geo)

        x, y, w, h = start.x(), start.y(), start.width(), start.height()
        if "left" in edges:
            x = start.x() + delta.x()
            w = start.width() - delta.x()
        if "right" in edges:
            w = start.width() + delta.x()
        if "top" in edges:
            y = start.y() + delta.y()
            h = start.height() - delta.y()
        if "bottom" in edges:
            h = start.height() + delta.y()

        w = self._clamp_value(w, lo_w, hi_w)
        h = self._clamp_value(h, lo_h, hi_h)
        if "left" in edges:
            x = start.x() + start.width() - w
        if "top" in edges:
            y = start.y() + start.height() - h
        rect = QRect(x, y, w, h)
        rect = QRect(self._clamp_pos_for(rect.topLeft(), rect.size(), geo), rect.size())
        self._adjusting = True
        try:
            self.widget.setGeometry(rect)
        finally:
            self._adjusting = False

    def _end_resize(self):
        self._resizing = None
        self._normal_size = QSize(self.widget.size())
        self._normal_pos = QPoint(self.widget.pos())
        self.widget.setCursor(Qt.ArrowCursor)
        self._emit_changed()

    # ---------- 背景拖拽（只接管发到顶层 widget 本身的事件） ----------
    def _try_start_drag(self, obj, ev):
        if obj is not self.widget or self._collapsed:
            return False
        if self._resizing:
            return False
        # 边缘区域优先 resize；中部区域才拖拽
        try:
            local = self.widget.mapFromGlobal(ev.globalPos())
        except Exception:
            return False
        if self._edges_at(local):
            return False
        self._dragging = {"start_global": QPoint(ev.globalPos()),
                          "start_pos": QPoint(self.widget.pos())}
        return True

    def _do_drag(self, ev):
        info = self._dragging
        if not info:
            return
        delta = ev.globalPos() - info["start_global"]
        target = info["start_pos"] + delta
        target = self.clamp_position(target)
        if self._compact:
            size = QSize(*COMPACT_SIZE)
            geo = self._work_area_for(target)
            edge = self._detect_dock_edge(QRect(target, size), geo)
            if edge:
                target = self._snap_pos(target, size, edge, geo)
        elif self._is_small_normal():
            size = QSize(self._normal_size)
            geo = self._work_area_for(target)
            edge = self._detect_dock_edge(QRect(target, size), geo)
            if edge:
                target = self._snap_pos(target, size, edge, geo)
        self._adjusting = True
        try:
            self.widget.move(target)
        finally:
            self._adjusting = False
        if self._compact:
            self._compact_logical_rect = QRect(target, QSize(*COMPACT_SIZE))
            self._dock_edge = self._detect_dock_edge(self._compact_logical_rect,
                                                     self._work_area_for(target))
            self._preferred_dock_edge = self._dock_edge
        elif self._is_small_normal():
            rect = QRect(target, QSize(self._normal_size))
            edge = self._detect_dock_edge(rect, self._work_area_for(target))
            self._dock_edge = edge
            self._preferred_dock_edge = edge
            self._docked_small = bool(edge)
            self._small_logical_rect = rect
            self._normal_pos = QPoint(target)
        else:
            self._normal_pos = QPoint(target)
        self._emit_changed()

    def _end_drag(self):
        self._dragging = None
        if self._compact:
            self._compact_logical_rect = QRect(QPoint(self.widget.pos()),
                                               QSize(*COMPACT_SIZE))
        elif self._is_small_normal():
            self._normal_pos = QPoint(self.widget.pos())
            self._small_logical_rect = QRect(self._normal_pos,
                                             QSize(self._normal_size))
        else:
            self._normal_pos = QPoint(self.widget.pos())
        self._emit_changed()

    def stop_timers(self):
        """closeEvent 用：停掉 hover 定时器与进行中的拖拽/resize。"""
        self._hover_timer.stop()
        self._resizing = None
        self._dragging = None

    def _on_widget_move(self):
        if self._adjusting:
            return False
        if self._collapsed:
            return False
        pos = QPoint(self.widget.pos())
        if self._compact:
            self._compact_logical_rect = QRect(pos, QSize(*COMPACT_SIZE))
            edge = self._detect_dock_edge(self._compact_logical_rect,
                                          self._work_area_for(pos))
            if edge:
                target = self._snap_pos(pos, QSize(*COMPACT_SIZE), edge,
                                        self._work_area_for(pos))
                if target != pos:
                    self._adjusting = True
                    try:
                        self.widget.move(target)
                    finally:
                        self._adjusting = False
                    pos = target
                self._dock_edge = edge
                self._preferred_dock_edge = edge
                self._compact_logical_rect = QRect(pos, QSize(*COMPACT_SIZE))
            else:
                self._dock_edge = None
                self._preferred_dock_edge = None
        elif self._is_small_normal():
            target = self.clamp_position(pos)
            geo = self._work_area_for(target)
            edge = self._detect_dock_edge(QRect(target, QSize(self._normal_size)),
                                          geo)
            if edge:
                target = self._snap_pos(target, QSize(self._normal_size),
                                        edge, geo)
            if target != pos:
                self._adjusting = True
                try:
                    self.widget.move(target)
                finally:
                    self._adjusting = False
                pos = target
            self._normal_pos = pos
            self._dock_edge = edge
            self._preferred_dock_edge = edge
            self._docked_small = bool(edge)
            self._small_logical_rect = QRect(pos, QSize(self._normal_size))
        else:
            self._docked_small = False
            self._dock_edge = None
            self._preferred_dock_edge = None
            self._small_logical_rect = None
            target = self.clamp_position(pos)
            if target != pos:
                self._adjusting = True
                try:
                    self.widget.move(target)
                finally:
                    self._adjusting = False
                pos = target
            self._normal_pos = pos
        self._emit_changed()
        return False

    def _on_widget_resize(self, ev):
        if self._adjusting or self._resizing:
            return False
        if self._compact:
            # 小窗/小条尺寸由 controller 固定；外部 resize 一律纠正
            if self._collapsed:
                self._adjusting = True
                try:
                    self._set_strip_geometry()
                finally:
                    self._adjusting = False
            else:
                self._adjusting = True
                try:
                    self._set_compact_geometry(self._logical_pos(), self._dock_edge)
                finally:
                    self._adjusting = False
            return False
        geo = self._work_area_for(self.widget.pos())
        size = self._clamp_normal_size(QSize(self.widget.size()), geo)
        if size != self.widget.size():
            self._adjusting = True
            try:
                self.widget.resize(size)
            finally:
                self._adjusting = False
        self._normal_size = QSize(size)
        self._normal_pos = QPoint(self.widget.pos())
        if not self._is_small_normal():
            self._docked_small = False
            self._dock_edge = None
            self._preferred_dock_edge = None
            self._small_logical_rect = None
        else:
            self._small_logical_rect = QRect(self._normal_pos,
                                             QSize(self._normal_size))
        self._emit_changed()
        return False

    def eventFilter(self, obj, ev):
        try:
            # 可能被安装为 app/全局 filter：非 QWidget 的 QObject（layout/QTimer/
            # QAction 等）事件直接放行，绝不对其调用 isAncestorOf/window/hide。
            if not isinstance(obj, QWidget):
                return False
            if ev.type() == QEvent.ChildAdded:
                self._watch_child(ev.child())
                return False
            if obj is not self.widget:
                try:
                    if not self.widget.isAncestorOf(obj):
                        return False
                    # QDialog / 弹出窗口的鼠标事件不参与主窗口 hover/resize/drag
                    if obj.window() is not self.widget:
                        return False
                except RuntimeError:
                    return False

            et = ev.type()
            # 收条期间页面切换可见性：记录最新状态，并暂时压住（小条里不该有页面）
            if (et in (QEvent.Show, QEvent.Hide) and obj is not self.widget
                    and self._collapsed and not self._updating_children):
                try:
                    if obj.parent() is self.widget and not obj.isWindow():
                        self._track_child_visibility(obj, et == QEvent.Show)
                        if et == QEvent.Show:
                            self._updating_children = True
                            try:
                                obj.hide()
                            finally:
                                self._updating_children = False
                except RuntimeError:
                    pass
                return False
            if et == QEvent.Enter:
                self._on_hover_enter()
                return False
            if et == QEvent.Leave:
                self._on_hover_leave()
                return False
            if et == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                if self._try_start_resize(obj, ev):
                    return True
                if self._try_start_drag(obj, ev):
                    return True
                return False
            if et == QEvent.MouseMove:
                if self._resizing:
                    self._do_resize(ev)
                    return True
                if self._dragging:
                    self._do_drag(ev)
                    return True
                self._update_cursor(obj, ev)
                return False
            if et == QEvent.MouseButtonRelease:
                if self._resizing:
                    self._end_resize()
                    return True
                if self._dragging:
                    self._end_drag()
                    return True
                return False
            if et == QEvent.Show and obj is self.widget:
                self._install_child_filters()
                self._hover_timer.stop()
                return False
            if et == QEvent.Hide and obj is self.widget:
                self._hover_timer.stop()
                return False
            if et == QEvent.Move and obj is self.widget:
                return self._on_widget_move()
            if et == QEvent.Resize and obj is self.widget:
                return self._on_widget_resize(ev)
        except RuntimeError:
            return False
        return False
