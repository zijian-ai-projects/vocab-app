# -*- coding: utf-8 -*-
"""WindowController 隔离测试（纯 Qt geometry / offscreen，不实例化 main，不碰真实数据）。

运行：
  D:\\software\\anaconda\\python.exe scripts\\test_windowing.py
默认 offscreen；如需原生窗口可设 VOCAB_TEST_PLATFORM=windows；
VOCAB_TEST_PLATFORM=native 表示不改 QT_QPA_PLATFORM、用系统默认平台。

覆盖：
  * 常量 / 只读属性 / changed 信号 / state JSON；
  * 正常窗最小 520×430、最大 1.6×、set_normal_size clamp 工作区；
  * 四边 resize（直接 QMouseEvent，避免 QTest.mouseMove 不出窗口）；
  * Move 自动夹紧、clamp_position、掉线屏幕恢复；
  * 小窗固定 356×196、不可 resize、临时 remember=False 不改偏好；
  * 四边吸附/8px 收条/悬停展开/正常窗不自动收条；
  * 收条隐藏直接子控件、展开恢复；hide 时 timer 不残留 hidden 状态；
  * restore/state 正常/小窗逻辑位置、allow_compact、负坐标假屏幕。
"""
import os
import sys
import io
import json
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(APP)
sys.path.insert(0, os.path.join(APP, "app"))

# 必须在 import PyQt5 之前决定平台；默认 offscreen。
# VOCAB_TEST_PLATFORM=native 表示不设置平台，用系统默认（Windows=windows）。
_plat = os.environ.get("VOCAB_TEST_PLATFORM", "")
if _plat and _plat.lower() not in ("native", "default"):
    os.environ["QT_QPA_PLATFORM"] = _plat
elif not _plat:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import (QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer)
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import (QApplication, QDialog, QLabel, QVBoxLayout, QWidget)

import windowing as wd

app = QApplication.instance() or QApplication(sys.argv)
out = []
fails = []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def pump(seconds=0.0, events=6):
    for _ in range(events):
        app.processEvents()
    if seconds > 0:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)
    for _ in range(events):
        app.processEvents()


class Dummy(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(*wd.NORMAL_MIN)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 14, 22, 16)
        self.a = QLabel("A")
        self.b = QLabel("B")
        self.c = QWidget()
        lay.addWidget(self.a)
        lay.addWidget(self.b)
        lay.addWidget(self.c)


def new_ctl(pos=(100, 100), size=None):
    w = Dummy()
    if size is not None:
        w.resize(size[0], size[1])
    w.move(*pos)
    w.show()
    pump()
    return w, wd.WindowController(w)


def send_mouse(widget, etype, global_pos, button=Qt.LeftButton,
               buttons=Qt.LeftButton):
    local = widget.mapFromGlobal(global_pos)
    # Qt5 QMouseEvent(type, localPos, globalPos, button, buttons, modifiers)
    ev = QMouseEvent(etype, local, QPoint(global_pos), button, buttons,
                     Qt.NoModifier)
    QApplication.sendEvent(widget, ev)
    app.processEvents()


def fake_screen(rect):
    class FakeScreen:
        def __init__(self, r):
            self._r = QRect(r)

        def availableGeometry(self):
            return QRect(self._r)

        def geometry(self):
            return QRect(self._r)
    return FakeScreen(rect)


def primary_avail():
    return app.primaryScreen().availableGeometry()


def all_screens():
    return [s for s in app.screens() if s is not None]


def normalize_size(w, h, avail):
    # 正常窗本身最大 = 当前屏幕可用工作区；MAX_SCALE 只作用于 scale_factor
    lo_w = min(wd.NORMAL_MIN[0], avail.width())
    lo_h = min(wd.NORMAL_MIN[1], avail.height())
    hi_w = max(lo_w, avail.width())
    hi_h = max(lo_h, avail.height())
    return (min(max(w, lo_w), hi_w), min(max(h, lo_h), hi_h))


# ======================================================================
# 1. 常量 / API
# ======================================================================
check(wd.NORMAL_MIN == (520, 430), "NORMAL_MIN == (520,430)")
check(wd.COMPACT_SIZE == (356, 196), "COMPACT_SIZE == (356,196)")
check(abs(wd.MAX_SCALE - 1.6) < 1e-9, "MAX_SCALE == 1.6")

w, c = new_ctl()
check(isinstance(c, QObject), "WindowController 是 QObject")
check(isinstance(c.normal_size, QSize) and c.normal_size == QSize(520, 430),
      "normal_size 是 QSize(520,430)：%r" % (c.normal_size,))
check(c.compact is False and c.preferred_compact is False,
      "初始 compact/preferred_compact = False")
check(c.collapsed is False and c.dock_edge is None,
      "初始 collapsed=False / dock_edge=None")
st = c.state()
check(isinstance(st, dict) and st.get("version") == 1, "state 带 version=1")
for key in ("normal_w", "normal_h", "normal_x", "normal_y", "compact_x",
            "compact_y", "x", "y", "w", "h", "compact", "dock_edge"):
    check(key in st, "state 包含键 %s" % key)
check(st["w"] == 520 and st["h"] == 430 and st["compact"] is False,
      "初始 state w/h=520×430、compact=False")
check(len(json.dumps(st)) > 0, "state 可 JSON 序列化")
w.close()

# ======================================================================
# 1b. eventFilter 被当 app/全局 filter 时，非 QWidget QObject 必须安全放行
# ======================================================================
w, c = new_ctl()
qobj = QObject()
timer = QTimer(w)
layout = w.layout()
try:
    check(c.eventFilter(qobj, QEvent(QEvent.User)) is False,
          "eventFilter(QObject) 安全返回 False，不调用 isAncestorOf")
    check(c.eventFilter(timer, QEvent(QEvent.Timer)) is False,
          "eventFilter(QTimer) 安全返回 False")
    check(c.eventFilter(layout, QEvent(QEvent.LayoutRequest)) is False,
          "eventFilter(QLayout) 安全返回 False")
    app.installEventFilter(c)
    try:
        QApplication.sendEvent(qobj, QEvent(QEvent.User))
        QApplication.sendEvent(timer, QEvent(QEvent.Timer))
        QApplication.sendEvent(layout, QEvent(QEvent.LayoutRequest))
        check(True, "安装为 application 级 event filter 后非 widget 事件不崩")
    finally:
        app.removeEventFilter(c)
except TypeError as e:
    check(False, "非 QWidget event 触发 TypeError：%r" % (e,))
w.close()

# ======================================================================
# 2. 正常窗尺寸约束 / 用户尺寸
# ======================================================================
w, c = new_ctl()
avail = primary_avail()
c.set_normal_size(300, 200)
check(c.normal_size == QSize(520, 430), "set_normal_size 低于最小 -> 520×430：%r" % c.normal_size)
check(w.size() == QSize(520, 430), "窗口实际也钳到 520×430：%r" % w.size())
c.set_normal_size(2000, 2000)
exp_w, exp_h = normalize_size(2000, 2000, avail)
check((c.normal_size.width(), c.normal_size.height()) == (exp_w, exp_h),
      "超大尺寸按工作区 clamp（不是 1.6×）：%r（期望 %r）" % (c.normal_size, (exp_w, exp_h)))
check(w.size() == c.normal_size, "实际窗口尺寸 = normal_size")
check(w.geometry().left() >= avail.left() and w.geometry().top() >= avail.top()
      and w.geometry().right() <= avail.right()
      and w.geometry().bottom() <= avail.bottom(),
      "正常窗完整在工作区内：%r / %r" % (w.geometry(), avail))
# 外部 resize 被 controller 收回到合法范围
w.resize(100, 100)
pump()
check(c.normal_size == QSize(520, 430), "外部缩到 100×100 被钳回 520×430：%r" % c.normal_size)
check(w.size() == QSize(520, 430), "外部 resize 后实际尺寸 520×430")
w.close()

# ======================================================================
# 2b. 大屏：正常窗可超过 832×688（上限=工作区），字体 scale 仍 cap 1.6
# ======================================================================
fake_big = fake_screen(QRect(0, 0, 1400, 900))
w, c = new_ctl(pos=(0, 0))
c._screens = lambda: [fake_big]
c.set_normal_size(1400, 900)
check(c.normal_size == QSize(1400, 900),
      "大屏正常窗可 1400×900（不再被 832×688 限制）：%r" % c.normal_size)
check(w.size() == QSize(1400, 900), "大屏实际窗口 1400×900")
check(abs(c.scale_factor - wd.MAX_SCALE) < 1e-9,
      "大窗字体/控件 scale 仍 cap 1.6：%.3f" % c.scale_factor)
st_big = c.state()
check((st_big["normal_w"], st_big["normal_h"]) == (1400, 900),
      "大窗 state 保存 1400×900")
check(st_big["w"] == 1400 and st_big["h"] == 900, "大窗 state w/h 逻辑尺寸")
w.close()

# 拖拽 resize 也可超过 832×688，直到工作区
w, c = new_ctl(pos=(20, 20))
c._screens = lambda: [fake_big]
g0 = w.mapToGlobal(QPoint(w.width() - 1, w.height() - 1))
send_mouse(w, QEvent.MouseButtonPress, g0)
g1 = w.mapToGlobal(QPoint(1200, 800))
send_mouse(w, QEvent.MouseMove, g1, button=Qt.NoButton, buttons=Qt.LeftButton)
send_mouse(w, QEvent.MouseButtonRelease, g1, button=Qt.LeftButton, buttons=Qt.NoButton)
check(w.width() > 832 and w.height() > 688,
      "拖拽 resize 可超过 832×688：%r" % w.size())
check(w.width() <= 1400 and w.height() <= 900, "拖拽 resize 不超过工作区")
check(abs(c.scale_factor - wd.MAX_SCALE) < 1e-9,
      "超过 832×688 后 scale_factor 仍 1.6")
w.close()

# restore 大尺寸也按工作区保留
w, c = new_ctl(pos=(10, 10))
c._screens = lambda: [fake_big]
c.restore({"normal_w": 1200, "normal_h": 820, "x": 100, "y": 50})
check(c.normal_size == QSize(1200, 820), "restore 1200×820 保留：%r" % c.normal_size)
check(w.size() == QSize(1200, 820), "restore 大尺寸实际尺寸")
check(abs(c.scale_factor - wd.MAX_SCALE) < 1e-9, "restore 大尺寸 scale=1.6")
w.close()

# ======================================================================
# 3. 正常窗四边拖拽 resize / 最小限制
# ======================================================================
w, c = new_ctl()
avail = primary_avail()
start = QRect(w.geometry())
g0 = w.mapToGlobal(QPoint(1, 1))
send_mouse(w, QEvent.MouseButtonPress, g0)
check(c._resizing is not None, "左上角按下进入 resize")
check(set(c._resizing["edges"]) == {"left", "top"}, "左上角识别 left+top")
# 左上向外拖（global 变小）=> 变大、左上角外移
g1 = g0 - QPoint(60, 50)
send_mouse(w, QEvent.MouseMove, g1, button=Qt.NoButton, buttons=Qt.LeftButton)
check(w.width() == start.width() + 60 and w.height() == start.height() + 50,
      "左上拖拽改宽高：%r -> %r" % (start.size(), w.size()))
check(w.pos() == QPoint(start.x() - 60, start.y() - 50),
      "左上拖拽同时移动左上角：%r" % (w.pos(),))
send_mouse(w, QEvent.MouseButtonRelease, g1, button=Qt.LeftButton, buttons=Qt.NoButton)
check(c._resizing is None, "释放结束 resize")
check(c.normal_size == w.size(), "resize 后 normal_size 同步：%r" % c.normal_size)

# 右下角往内拖到很小 -> 不低于 520×430
w2, c2 = new_ctl(pos=(120, 100))
p0 = w2.mapToGlobal(QPoint(w2.width() - 1, w2.height() - 1))
send_mouse(w2, QEvent.MouseButtonPress, p0)
p1 = w2.mapToGlobal(QPoint(50, 50))
send_mouse(w2, QEvent.MouseMove, p1, button=Qt.NoButton, buttons=Qt.LeftButton)
send_mouse(w2, QEvent.MouseButtonRelease, p1, button=Qt.LeftButton, buttons=Qt.NoButton)
check(w2.width() >= wd.NORMAL_MIN[0] and w2.height() >= wd.NORMAL_MIN[1],
      "右下缩到最小仍 >=520×430：%r" % w2.size())
check(c2.normal_size.width() >= wd.NORMAL_MIN[0]
      and c2.normal_size.height() >= wd.NORMAL_MIN[1],
      "normal_size 最小限制")
w.close()
w2.close()

# ======================================================================
# 4. Move 夹紧 / clamp_position
# ======================================================================
w, c = new_ctl()
avail = primary_avail()
w.move(avail.right() + 500, avail.bottom() + 500)
pump()
check(avail.contains(w.geometry()), "Move 到屏幕外被自动夹回工作区：%r" % w.geometry())
pt = c.clamp_position(QPoint(avail.right() + 9999, avail.bottom() + 9999))
check(QPoint(pt.x(), pt.y()) == w.pos(), "clamp_position 右下极值 = 当前合法位置")
pt2 = c.clamp_position(QPoint(avail.left() - 9999, avail.top() - 9999))
check(pt2 == QPoint(avail.left(), avail.top()),
      "clamp_position 左上极值 = 工作区左上：%r" % (pt2,))
check(avail.contains(QRect(pt2, c.normal_size)), "clamp 后窗口完整可见")
w.close()

# ======================================================================
# 4b. 背景拖拽（Card 旧拖拽移除后由 controller 接管）
# ======================================================================
w, c = new_ctl(pos=(100, 100))
start = w.pos()
g0 = w.mapToGlobal(QPoint(260, 215))
send_mouse(w, QEvent.MouseButtonPress, g0)
check(c._dragging is not None, "背景中部按下进入拖拽")
check(c._resizing is None, "背景中部按下不进入 resize")
g1 = g0 + QPoint(60, 30)
send_mouse(w, QEvent.MouseMove, g1, button=Qt.NoButton, buttons=Qt.LeftButton)
check(w.pos() == start + QPoint(60, 30),
      "背景拖拽移动窗口：%r -> %r" % (start, w.pos()))
send_mouse(w, QEvent.MouseButtonRelease, g1, button=Qt.LeftButton, buttons=Qt.NoButton)
check(c._dragging is None, "释放结束背景拖拽")
check(c.state()["normal_x"] == w.x() and c.state()["normal_y"] == w.y(),
      "拖拽后 state 正常位置同步")
w.close()

# ======================================================================
# 5. 小窗固定尺寸 / 临时 remember=False 不改偏好 / 不可 resize
# ======================================================================
w, c = new_ctl()
c.set_compact(True, remember=True)
check(c.compact is True and c.preferred_compact is True, "set_compact(True) 改实际+偏好")
check(w.size() == QSize(*wd.COMPACT_SIZE), "小窗实际 356×196：%r" % w.size())
check(c.state()["w"] == 356 and c.state()["h"] == 196, "小窗 state w/h=356×196")
w.resize(500, 400)
pump()
check(w.size() == QSize(*wd.COMPACT_SIZE), "小窗外 resize 被改回 356×196")
c.set_compact(False, remember=False)
check(c.compact is False and c.preferred_compact is True,
      "remember=False 关小窗不改偏好")
check(w.size() == QSize(520, 430), "关小窗恢复正常尺寸")
c.set_compact(True, remember=False)
check(c.compact is True and c.preferred_compact is True,
      "remember=False 开小窗不改偏好")
c.set_compact(False, remember=True)
check(c.preferred_compact is False, "remember=True 关小窗更新偏好")
w.close()

# (0,0) 是合法位置，不能因 QPoint 真值判断被 compact 位置覆盖
w, c = new_ctl(pos=(0, 0))
c.set_compact(True, remember=True)
st = c.state()
check((st["normal_x"], st["normal_y"]) == (0, 0),
      "正常位置 (0,0) 在收小窗后仍保存为 (0,0)：%r" % ((st["normal_x"], st["normal_y"]),))
w.close()

# ======================================================================
# 6. 四边吸附 / 8px 收条 / 悬停展开
# ======================================================================
for edge in ("left", "right", "top", "bottom"):
    w, c = new_ctl()
    avail = primary_avail()
    c.restore({"compact": True, "dock_edge": edge,
               "normal_w": 520, "normal_h": 430,
               "compact_x": avail.left() + 150, "compact_y": avail.top() + 150,
               "x": avail.left() + 150, "y": avail.top() + 150})
    check(c.compact and c.dock_edge == edge,
          "%s：restore 后 compact/dock_edge 正确（%r）" % (edge, c.dock_edge))
    check(w.size() == QSize(*wd.COMPACT_SIZE), "%s：展开小窗 356×196" % edge)
    if edge == "left":
        check(w.x() == avail.left(), "left：贴左边缘 x=%d" % w.x())
    elif edge == "right":
        check(w.geometry().right() == avail.right(), "right：贴右边缘")
    elif edge == "top":
        check(w.y() == avail.top(), "top：贴上边缘")
    else:
        check(w.geometry().bottom() == avail.bottom(), "bottom：贴下边缘")
    if c._collapse_if_docked(force=True):
        check(c.collapsed, "%s：鼠标离开 -> 收条" % edge)
        size = w.size()
        if edge in ("left", "right"):
            check(size.width() == wd.STRIP_THICKNESS
                  and size.height() == min(wd.DOCK_LENGTH, 196),
                  "%s：竖胶囊 %d×%d，实际 %r" %
                  (edge, wd.STRIP_THICKNESS, wd.DOCK_LENGTH, size))
        else:
            check(size.height() == wd.STRIP_THICKNESS
                  and size.width() == min(wd.DOCK_LENGTH, 356),
                  "%s：横胶囊 %d×%d，实际 %r" %
                  (edge, wd.DOCK_LENGTH, wd.STRIP_THICKNESS, size))
        check(not w.a.isVisibleTo(w) and not w.b.isVisibleTo(w),
              "%s：收条隐藏直接子控件" % edge)
        st = c.state()
        check(st["w"] == 356 and st["h"] == 196
              and st["x"] == c._compact_logical_rect.x()
              and st["y"] == c._compact_logical_rect.y(),
              "%s：state 保存逻辑尺寸/位置，不存 8px：%r" % (edge, st))
        check(st["x"] == c._compact_logical_rect.x(),
              "%s：state x 是展开小窗逻辑 x" % edge)
        c.reveal()
        check(not c.collapsed and w.size() == QSize(*wd.COMPACT_SIZE),
              "%s：reveal 展开回 356×196" % edge)
        check(w.a.isVisibleTo(w) and w.b.isVisibleTo(w),
              "%s：reveal 恢复直接子控件" % edge)
        # 再收起，用进入事件展开
        c._collapse_if_docked(force=True)
        check(c.collapsed, "%s：再次收条" % edge)
        c._on_hover_enter()
        pump(0.30)
        check(not c.collapsed and w.size() == QSize(*wd.COMPACT_SIZE),
              "%s：hover enter 展开" % edge)
    else:
        check(False, "%s：没有进入收条" % edge)
    w.close()

# ======================================================================
# 6b. 收条隐藏直接子控件，但不隐藏 isWindow() 的 QDialog
# ======================================================================
w, c = new_ctl()
avail = primary_avail()
dlg = QDialog(w)
dlg.setWindowTitle("catalog")
dlg.show()
pump()
c.restore({"compact": True, "dock_edge": "left",
           "compact_x": avail.left(), "compact_y": avail.top() + 100,
           "x": avail.left(), "y": avail.top() + 100})
check(c._collapse_if_docked(force=True) and c.collapsed, "有 QDialog 时仍能收条")
check(dlg.isWindow(), "QDialog isWindow()=True")
check(dlg.isVisible(), "收条不隐藏 isWindow() 的 QDialog")
# 收条期间页面若尝试 show 直接子页：暂时压住，展开时恢复
w.a.show()
pump()
check(not w.a.isVisibleTo(w), "收条期间页面 show 被压住（小条内不露出页面）")
c.reveal()
check(w.a.isVisibleTo(w), "展开后页面恢复可见")
check(dlg.isVisible(), "展开后 QDialog 仍可见")
dlg.close()
w.close()

# ======================================================================
# 7. 其它正常尺寸（640×520/760×620）永不自动收条
# ======================================================================
for other_size in ((640, 520), (760, 620)):
    w, c = new_ctl()
    c.set_normal_size(*other_size)
    pump()
    avail = primary_avail()
    w.move(avail.left(), avail.top() + 100)
    pump()
    check(c.collapsed is False,
          "%d×%d 正常窗贴边不 collapsed" % other_size)
    check(c._collapse_if_docked(force=True) is False,
          "%d×%d 正常窗 _collapse_if_docked 无动作" % other_size)
    c._cursor_inside = lambda: False
    c._on_hover_leave()
    pump(0.40)
    check(c.collapsed is False,
          "%d×%d 正常窗 hover leave 也不收条" % other_size)
    w.close()

# ======================================================================
# 7b. 520×430 小巧正常窗也支持四边 8px 收条 / 悬停展开
# ======================================================================
for edge in ("left", "right", "top", "bottom"):
    w, c = new_ctl()
    avail = primary_avail()
    c.restore({"normal_w": 520, "normal_h": 430,
               "dock_edge": edge,
               "normal_x": avail.left() + 100, "normal_y": avail.top() + 100,
               "x": avail.left() + 100, "y": avail.top() + 100})
    check(c.normal_size == QSize(520, 430) and not c.compact,
          "%s：520×430 仍是正常窗" % edge)
    check(c._docked_small and c.dock_edge == edge,
          "%s：520×430 restore 后可贴边收起（edge=%r）" % (edge, c.dock_edge))
    check(w.size() == QSize(520, 430),
          "%s：520×430 展开尺寸不变" % edge)
    if edge == "left":
        check(w.x() == avail.left(), "left：520×430 贴左")
    elif edge == "right":
        check(w.geometry().right() == avail.right(), "right：520×430 贴右")
    elif edge == "top":
        check(w.y() == avail.top(), "top：520×430 贴上")
    else:
        check(w.geometry().bottom() == avail.bottom(), "bottom：520×430 贴下")
    check(c._collapse_if_docked(force=True), "%s：520×430 进入收条" % edge)
    check(c.collapsed and w.size() in (
              QSize(wd.STRIP_THICKNESS, min(wd.DOCK_LENGTH, 430)),
              QSize(min(wd.DOCK_LENGTH, 520), wd.STRIP_THICKNESS)),
          "%s：520×430 收成短圆角胶囊（%r）" % (edge, w.size()))
    check(not w.a.isVisibleTo(w) and not w.b.isVisibleTo(w),
          "%s：520×430 收条隐藏直接子控件" % edge)
    st = c.state()
    check(st["normal_w"] == 520 and st["normal_h"] == 430
          and st["w"] == 520 and st["h"] == 430,
          "%s：520×430 收条不写入 8px 逻辑尺寸：%r" % (edge, st))
    check((st["x"], st["y"]) == (c._small_logical_rect.x(),
                                 c._small_logical_rect.y()),
          "%s：520×430 state 位置来自展开逻辑 rect" % edge)
    c.reveal()
    check(not c.collapsed and w.size() == QSize(520, 430),
          "%s：520×430 hover/reveal 展开回 520×430" % edge)
    check(w.a.isVisibleTo(w) and w.b.isVisibleTo(w),
          "%s：520×430 reveal 恢复子控件" % edge)
    c._collapse_if_docked(force=True)
    c._on_hover_enter()
    pump(0.30)
    check(not c.collapsed and w.size() == QSize(520, 430),
          "%s：520×430 hover enter 展开" % edge)
    w.close()

# 拖到边缘自动吸附 + 保存/还原仍保持贴边与 520×430
w, c = new_ctl()
avail = primary_avail()
w.move(avail.left(), avail.top() + 120)
pump()
check(c._docked_small and c.dock_edge == "left",
      "520×430 直接 move 到左边 8px 阈值 -> 自动贴边")
check(c._collapse_if_docked(force=True) and c.collapsed,
      "520×430 拖到边缘后鼠标离开可收条")
c._on_hover_enter()
pump(0.30)
check(not c.collapsed and w.size() == QSize(520, 430),
      "520×430 拖到边缘后 hover 展开仍是 520×430")
c._cursor_inside = lambda: False
c._on_hover_leave()
pump(0.40)
check(c.collapsed and w.size() in (
          QSize(wd.STRIP_THICKNESS, min(wd.DOCK_LENGTH, 430)),
          QSize(min(wd.DOCK_LENGTH, 520), wd.STRIP_THICKNESS)),
      "520×430 hover leave 延迟后自动收成短胶囊")
c._on_hover_enter()
pump(0.30)
check(not c.collapsed and w.size() == QSize(520, 430),
      "520×430 hover enter 从 8px 展开回 520×430")
saved = c.state()
check(saved["normal_w"] == 520 and saved["normal_h"] == 430
      and saved["compact"] is False and saved["dock_edge"] == "left",
      "520×430 贴边状态保存 normal 尺寸 + dock_edge：%r" % (saved,))
w.close()
w2, c2 = new_ctl()
c2.restore(saved)
check(c2.normal_size == QSize(520, 430) and not c2.compact
      and c2._docked_small and c2.dock_edge == "left",
      "520×430 贴边状态 restart 恢复逻辑尺寸/贴边")
check(w2.size() == QSize(520, 430), "520×430 restart 展开尺寸 520×430")
w2.close()

w, c = new_ctl()
avail = primary_avail()
c.restore({"compact": True, "dock_edge": "left",
           "compact_x": avail.left(), "compact_y": avail.top() + 100,
           "x": avail.left(), "y": avail.top() + 100})
c._cursor_inside = lambda: False
c._on_hover_leave()
pump(0.40)
check(c.collapsed, "hover leave + 延迟后自动收条")
c._on_hover_enter()
pump(0.30)
check(not c.collapsed, "hover enter 自动展开")
# 展开状态 hide -> timer 停止；show 后子控件不被残留 hidden
c._cursor_inside = lambda: False
c._on_hover_leave()
w.hide()
pump(0.40)
check(not c.collapsed, "hide 后 timer 不把窗口收条")
w.show()
pump()
check(w.a.isVisibleTo(w) and w.b.isVisibleTo(w),
      "hide/show 后直接子控件仍可见（无残留 hidden）")
w.close()

# ======================================================================
# 9. state/restore：正常窗 / 小窗 / allow_compact / 掉线屏幕
# ======================================================================
w, c = new_ctl(pos=(140, 120))
avail = primary_avail()
c.set_normal_size(600, 500)
w.move(150, 130)
pump()
expect_pos = c.clamp_position(QPoint(150, 130))
st = c.state()
check((st["normal_w"], st["normal_h"]) == (600, 500), "state 正常尺寸 600×500")
check((st["x"], st["y"]) == (expect_pos.x(), expect_pos.y()),
      "state 正常位置夹紧后 %r" % ((st["x"], st["y"]),))
check(st["compact"] is False and st["w"] == 600 and st["h"] == 500,
      "state 正常窗 w/h=正常尺寸")

w2, c2 = new_ctl(pos=(10, 10))
c2.restore(st)
check(c2.normal_size == QSize(600, 500), "restore normal_size 600×500")
check(w2.pos() == expect_pos,
      "restore 正常位置 %r：%r" % (expect_pos, w2.pos()))
check(c2.compact is False and c2.preferred_compact is False, "restore 正常偏好")
w.close()
w2.close()

# 小窗状态往返
w, c = new_ctl()
avail = primary_avail()
c.restore({"compact": True, "dock_edge": "left",
           "compact_x": avail.left(), "compact_y": avail.top() + 120,
           "normal_w": 640, "normal_h": 520, "normal_x": 80, "normal_y": 90,
           "x": avail.left(), "y": avail.top() + 120})
st = c.state()
check(st["compact"] is True and st["dock_edge"] == "left", "小窗 state 保存偏好/edge")
check(st["w"] == 356 and st["h"] == 196, "小窗 state w/h=356×196")
w2, c2 = new_ctl(pos=(0, 0))
c2.restore(st)
check(c2.compact is True and c2.preferred_compact is True, "restore 小窗偏好")
check(w2.size() == QSize(*wd.COMPACT_SIZE), "restore 小窗尺寸 356×196")
check(c2.dock_edge == "left", "restore 小窗 dock_edge=left")
check(c2.state()["w"] == 356 and c2.state()["h"] == 196, "restore 后 state 仍逻辑尺寸")
# allow_compact=False：实际正常窗，但偏好仍恢复（不擅自丢用户设置）
w3, c3 = new_ctl(pos=(10, 10))
c3.restore(st, allow_compact=False)
check(c3.compact is False, "allow_compact=False 实际保持正常窗")
check(c3.preferred_compact is True, "allow_compact=False 仍恢复用户偏好")
check(w3.size() == QSize(640, 520), "allow_compact=False 使用 normal_size 640×520")
w.close()
w2.close()
w3.close()

# 掉线屏幕坐标 -> 恢复到可见屏幕
w, c = new_ctl()
avail = primary_avail()
c.restore({"normal_w": 600, "normal_h": 500, "x": 99999, "y": 99999})
st = c.state()
check(avail.contains(QRect(QPoint(st["x"], st["y"]), c.normal_size)),
      "restore 屏幕外坐标被夹回当前工作区：%r" % ((st["x"], st["y"]),))
w.close()

# 旧 _win.json 只有 x/y/w/h：也能恢复正常尺寸（normal_w/h 缺省时兜底 w/h）
w, c = new_ctl(pos=(10, 10))
c.restore({"x": 80, "y": 70, "w": 600, "h": 500})
check(c.normal_size == QSize(600, 500), "旧 save 的 w/h 作为正常尺寸兜底")
check(w.pos() == QPoint(80, 70), "旧 save 的 x/y 恢复：%r" % w.pos())
w.close()

# 负坐标多屏（假 QScreen）
w, c = new_ctl()
fake = fake_screen(QRect(-1920, 0, 1920, 1080))
c._screens = lambda: [fake]
c.restore({"normal_w": 600, "normal_h": 500, "x": -1000, "y": 100})
st = c.state()
fake_avail = fake.availableGeometry()
check(fake_avail.contains(QRect(QPoint(st["x"], st["y"]), c.normal_size)),
      "负坐标多屏：restore 后窗口在假屏幕工作区内：%r" % ((st["x"], st["y"]),))
check(st["x"] < 0, "负坐标被保留（不强行挪到 0）：%d" % st["x"])
pt = c.clamp_position(QPoint(-5000, 100))
check(fake_avail.contains(QRect(pt, c.normal_size)),
      "负坐标 clamp_position 不越界：%r" % (pt,))
check(pt.x() < 0, "负坐标 clamp_position 允许负 x：%d" % pt.x())
# 屏幕掉线（恢复真实屏幕）：state 不再写负坐标/屏幕外
del c._screens
st2 = c.state()
real_avail = primary_avail()
check(real_avail.contains(QRect(QPoint(st2["x"], st2["y"]), c.normal_size)),
      "屏幕掉线后 state 夹回真实可见屏幕：%r" % ((st2["x"], st2["y"]),))
w.close()

# ======================================================================
# 9b. legacy 356×196 无 compact 字段 -> 恢复小窗偏好
# ======================================================================
w, c = new_ctl(pos=(100, 100))
c.restore({"x": 120, "y": 90, "w": 356, "h": 196}, allow_compact=False)
check(c.preferred_compact is True,
      "legacy 356×196 无 compact 字段 -> preferred_compact=True")
check(c.compact is False, "allow_compact=False 时实际仍正常窗")
check(c.state()["compact"] is True, "legacy 小窗偏好进入 state.compact")
c.set_compact(True, remember=False)
check(c.compact is True and w.size() == QSize(*wd.COMPACT_SIZE),
      "legacy 偏好随后 set_compact(True, remember=False) 能恢复小窗")
check((w.pos().x(), w.pos().y()) == (120, 90),
      "legacy 小窗位置沿用 x/y：%r" % (w.pos(),))
w.close()

# allow_compact=True 时 legacy 小窗偏好直接以小窗启动
w, c = new_ctl(pos=(100, 100))
c.restore({"x": 120, "y": 90, "w": 356, "h": 196})
check(c.compact is True and c.preferred_compact is True,
      "legacy 小窗偏好 allow_compact=True 直接进小窗")
check(w.size() == QSize(*wd.COMPACT_SIZE), "legacy 直接小窗尺寸 356×196")
w.close()

# ======================================================================
# 9c. temporary normal (remember=False) 后 save/restart 保留小窗位置/贴边
# ======================================================================
w, c = new_ctl(pos=(0, 0))
avail = primary_avail()
compact_pos = (avail.left(), avail.top() + 120)
c.restore({"compact": True, "dock_edge": "left",
           "compact_x": compact_pos[0], "compact_y": compact_pos[1],
           "normal_w": 600, "normal_h": 500,
           "normal_x": 140, "normal_y": 100,
           "x": compact_pos[0], "y": compact_pos[1]})
check(c.compact and c.dock_edge == "left", "前置：小窗贴左边")
c.set_compact(False, remember=False)   # 临时页面 normal，不改偏好
check(c.compact is False and c.preferred_compact is True,
      "temporary normal：实际 normal、偏好仍 small")
st_temp = c.state()
check(st_temp["compact"] is True, "temporary normal state.compact 仍 True")
check(st_temp["dock_edge"] == "left", "temporary normal state.dock_edge 仍 left")
check((st_temp["compact_x"], st_temp["compact_y"]) == compact_pos,
      "temporary normal state 保留小窗逻辑位置：%r" %
      ((st_temp["compact_x"], st_temp["compact_y"]),))
w2, c2 = new_ctl(pos=(10, 10))
c2.restore(st_temp)
check(c2.compact is True and c2.preferred_compact is True,
      "temporary normal 保存后重启恢复小窗偏好")
check(c2.dock_edge == "left", "重启后 dock_edge 仍 left")
check(w2.size() == QSize(*wd.COMPACT_SIZE), "重启后小窗尺寸 356×196")
check((w2.x(), w2.y()) == compact_pos,
      "重启后小窗位置保持：%r" % ((w2.x(), w2.y()),))
w.close()
w2.close()

# ======================================================================
# 10. changed 信号 / 防递归 / scale_factor / update_palette
# ======================================================================
w, c = new_ctl()
check(abs(c.scale_factor - 1.0) < 1e-9, "520×430 -> scale_factor 1.0")
c.set_normal_size(650, 550)
check(abs(c.scale_factor - min(650 / 520.0, 550 / 430.0, 1.6)) < 1e-9,
      "scale_factor = min(w/520,h/430,1.6)：%.3f" % c.scale_factor)
calls = []


def _recurse():
    calls.append(1)
    if len(calls) < 6:
        c.set_normal_size(600, 500)


c.changed.connect(_recurse)
c.set_normal_size(610, 510)
check(len(calls) == 1, "changed 回调内再改布局不递归（calls=%d）" % len(calls))
c.changed.disconnect(_recurse)

# main 设置页会直接写 controller.preferred_compact；必须有 setter 且发 changed
pref_hits = []
c.changed.connect(lambda: pref_hits.append(1))
c.preferred_compact = True
check(c.preferred_compact is True and len(pref_hits) >= 1,
      "preferred_compact setter 可写且发 changed")
c.preferred_compact = False
check(c.preferred_compact is False, "preferred_compact setter 可设回 False")
c.changed.disconnect()

hits = []
c.changed.connect(lambda: hits.append(1))
c.set_normal_size(600, 500)
check(len(hits) > 0, "set_normal_size 触发 changed")
# 贴左边缘再进小窗，确保有 dock_edge 可收条
avail = primary_avail()
w.move(avail.left(), avail.top() + 100)
pump()
before = len(hits)
c.set_compact(True, remember=True)
check(len(hits) > before, "set_compact 触发 changed")
before = len(hits)
c._collapse_if_docked(force=True)
check(c.collapsed and len(hits) > before, "收条触发 changed")
before = len(hits)
c.reveal()
check(len(hits) > before, "reveal 触发 changed")
c.update_palette({"bg": "#fff", "fg": "#111"})
check(c.theme.get("bg") == "#fff", "update_palette 记录 theme")
st = c.state()
check(st["w"] == 356 and st["h"] == 196,
      "收条后 state 逻辑尺寸仍为 356×196（不是 8px）")
check(st["x"] == c._compact_logical_rect.x()
      and st["y"] == c._compact_logical_rect.y(),
      "收条后 state 使用展开小窗逻辑位置")
w.close()

# ======================================================================
# 报告
# ======================================================================
out.append("")
if fails:
    out.append("失败 %d 项：%s" % (len(fails), " / ".join(fails)))
else:
    out.append("全部通过 ✓")

root = os.path.join(WORKSPACE, ".vocab-ui-tests")
try:
    os.makedirs(root, exist_ok=True)
except OSError:
    pass
path = os.path.join(root, "windowing-%d.txt" % int(time.time()))
with io.open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
print("REPORT", path)
sys.exit(1 if fails else 0)
