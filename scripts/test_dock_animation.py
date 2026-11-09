# -*- coding: utf-8 -*-
"""V1.3.3 侧边胶囊绘制与平滑收/展动画的隔离回归（纯 Qt offscreen，不启动真实 app）。"""
import os
import sys
import io
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(APP)
sys.path.insert(0, os.path.join(APP, "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QEvent
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

import windowing as wd

app = QApplication.instance() or QApplication(sys.argv)
out = []
fails = []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def render_dock(ctl):
    pix = QPixmap(ctl.widget.size())
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    try:
        painted = ctl.paint_dock(painter)
    finally:
        painter.end()
    return pix, painted


def pump(seconds=0.0, events=6):
    for _ in range(events):
        app.processEvents()
    if seconds > 0:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.008)
    for _ in range(events):
        app.processEvents()


def wait_anim(ctl, timeout=1.2):
    end = time.time() + timeout
    while ctl.animating and time.time() < end:
        pump(0.02)
    pump(0.02)


class Dummy(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(*wd.NORMAL_MIN)
        lay = QVBoxLayout(self)
        self.a = QLabel("A")
        self.b = QLabel("B")
        lay.addWidget(self.a)
        lay.addWidget(self.b)


def new_ctl(size=None):
    w = Dummy()
    if size:
        w.resize(*size)
    w.move(100, 100)
    w.show()
    pump()
    return w, wd.WindowController(w)


def dock_small(c, edge="left"):
    avail = app.primaryScreen().availableGeometry()
    c.restore({"normal_w": 520, "normal_h": 430, "dock_edge": edge,
               "normal_x": avail.left() + 100, "normal_y": avail.top() + 100,
               "x": avail.left() + 100, "y": avail.top() + 100})
    pump()


def theme():
    return {"bg": "#f7f8fa", "border": "#e2e5ea", "fg_mean": "#2b3138",
            "muted": "#8a929c", "chip_bg": "#eef1f5", "chip_hover": "#e6eaef",
            "dock_bg": "#112233", "dock_border": "#445566",
            "dock_fg": "#aabbcc", "dock_hover": "#223344"}


# 1. 胶囊绘制/主题/尺寸/逻辑状态
w, c = new_ctl()
dock_small(c, "left")
c.update_palette(theme())
# paint_dock 在展开状态应 no-op
check(render_dock(c)[1] is False,
      "展开状态 paint_dock 返回 False")
check(c._collapse_if_docked(force=True, immediate=False), "启动平滑收起")
pump(0.03)
overlay = c._dock_overlay
check(overlay is not None and overlay.isVisibleTo(w),
      "收起动画中快照 overlay 实际可见")
check(overlay is not None and overlay.pixmap() is not None
      and not overlay.pixmap().isNull(),
      "快照 overlay 有非空 pixmap")
if overlay is not None and overlay.pixmap() is not None:
    snap_img = overlay.pixmap().toImage()
    visible_px = 0
    for x in range(0, max(1, snap_img.width()), 16):
        for y in range(0, max(1, snap_img.height()), 16):
            if snap_img.pixelColor(x, y).alpha() > 0:
                visible_px += 1
    check(visible_px > 0, "快照 overlay pixmap 有可见像素：%d" % visible_px)
check(overlay is not None
      and all(pair[0] is not overlay for pair in c._hidden_children),
      "快照 overlay 不混入 hidden_children")
check(c.animating and not c.can_persist_geometry,
      "动画中 animating=True / can_persist_geometry=False")
wait_anim(c)
check(not c.animating and c.can_persist_geometry,
      "动画结束 animating=False / can_persist_geometry=True")
check(c.collapsed and c._dock_edge == "left", "平滑收起后 collapsed/edge 正确")
check(w.size().width() == wd.STRIP_THICKNESS
      and w.size().height() == min(wd.DOCK_LENGTH, 430),
      "短圆角胶囊尺寸 %r" % (w.size(),))
st = c.state()
check(st["normal_w"] == 520 and st["normal_h"] == 430
      and st["w"] == 520 and st["h"] == 430,
      "收起不写入动画中间值/逻辑尺寸仍 520×430：%r" % (st,))
check(c._dock_overlay is None, "收起结束移除快照 overlay")
pix = QPixmap(w.size())
pix.fill(Qt.transparent)
p = QPainter(pix)
painted = c.paint_dock(p)
p.end()
check(painted is True, "collapsed paint_dock 返回 True")
img = pix.toImage()
bg = QColor(theme()["dock_bg"]).rgb()
found_bg = any(img.pixelColor(x, y).rgb() == bg
               for x in range(w.width()) for y in range(w.height()))
check(found_bg, "paint_dock 使用 theme.dock_bg 绘制胶囊")
check(img.pixelColor(w.width() // 2, 8).rgb() != 0,
      "胶囊中部存在可见绘制像素")
w.close()

# 2. 平滑展开/悬停
w, c = new_ctl()
dock_small(c, "right")
c.update_palette(theme())
check(c._collapse_if_docked(force=True, immediate=False), "展开前先收起")
wait_anim(c)
check(c.collapsed, "已收起")
c.reveal(immediate=False)
check(c.animating, "展开动画进行中")
wait_anim(c)
check(not c.animating and not c.collapsed, "展开动画完成")
check(w.size() == QSize(520, 430), "展开恢复 520×430")
check(c._dock_overlay is None, "展开结束移除 overlay")
check(w.a.isVisibleTo(w) and w.b.isVisibleTo(w), "展开恢复直接子控件")
st = c.state()
check(st["dock_edge"] == "right" and st["w"] == 520 and st["h"] == 430,
      "展开后 dock_edge/state 正确：%r" % (st,))
w.close()

# 3. 快速 enter/leave 反向，不能卡死或错误收回
w, c = new_ctl()
dock_small(c, "left")
c.update_palette(theme())
c._cursor_inside = lambda: False
c._collapse_if_docked(force=True, immediate=False)
pump(0.03)
c._on_hover_enter()                      # 收起中途反向展开
check(c.animating or not c.collapsed, "收起中途 hover enter 反向")
wait_anim(c)
check(not c.collapsed and w.size() == QSize(520, 430),
      "快速反向结束后正常展开 520×430")
check(c._dock_overlay is None and not c.animating,
      "快速反向结束无 overlay/动画残留")
c._on_hover_enter()
check(not c.collapsed, "已展开时 hover enter 幂等")
w.close()

# 3b. 真正 Enter/Leave 事件：收条动画中 enter 反向，expand 中 leave 再收
w, c = new_ctl()
dock_small(c, "left")
c.update_palette(theme())
c._cursor_inside = lambda: False
QApplication.sendEvent(w, QEvent(QEvent.Leave))
pump(0.30)
check(c.animating or c.collapsed, "真实 Leave 事件触发收条动画")
QApplication.sendEvent(w, QEvent(QEvent.Enter))
wait_anim(c)
check(not c.collapsed and w.size() == QSize(520, 430),
      "收条动画中真实 Enter 事件反向展开")
QApplication.sendEvent(w, QEvent(QEvent.Leave))
pump(0.50)
wait_anim(c)
check(c.collapsed, "展开后真实 Leave 事件再次自动收条")
w.close()

# 3c. immediate reveal 遇到正在 expand 的 target 也必须真正落定
w, c = new_ctl()
dock_small(c, "right")
c.update_palette(theme())
c._cursor_inside = lambda: False
c._collapse_if_docked(force=True, immediate=False)
wait_anim(c)
c._on_hover_enter()
pump(0.03)
c.reveal(immediate=True)
check(not c.animating and not c.collapsed,
      "immediate reveal 在 expand target 中仍立即落定")
check(w.size() == QSize(520, 430), "immediate reveal 后尺寸 520×430")
check(c._dock_overlay is None, "immediate reveal 后无 overlay")
w.close()

# 4. restore/set_compact/update_palette 中断动画
w, c = new_ctl()
dock_small(c, "top")
c.update_palette(theme())
c._collapse_if_docked(force=True, immediate=False)
pump(0.03)
c.restore({"normal_w": 640, "normal_h": 520, "x": 120, "y": 80})
check(not c.animating and c.can_persist_geometry, "restore 中断动画并落定")
check(w.size() == QSize(640, 520), "restore 后尺寸 640×520")
check(c._dock_overlay is None, "restore 中断后无 overlay")
w.close()

w, c = new_ctl()
dock_small(c, "bottom")
c.update_palette(theme())
c._collapse_if_docked(force=True, immediate=False)
pump(0.03)
c.set_compact(True, remember=True)
check(not c.animating, "set_compact 中断动画")
check(c.compact and w.size() == QSize(*wd.COMPACT_SIZE),
      "set_compact 后实际小窗 356×196")
w.close()

w, c = new_ctl()
dock_small(c, "left")
c.update_palette(theme())
c._collapse_if_docked(force=True, immediate=False)
pump(0.03)
new_theme = theme()
new_theme["dock_bg"] = "#334455"
c.update_palette(new_theme)
wait_anim(c)
check(not c.animating and c.collapsed, "update_palette 中断动画并落定")
check(c.theme["dock_bg"] == "#334455", "update_palette 记录新主题")
w.close()

# 4b. 收/展动画中关闭 edge_collapse → 立即完整展开、释放 overlay/hover
w, c = new_ctl()
dock_small(c, "left")
c.update_palette(theme())
c._collapse_if_docked(force=True, immediate=False)
pump(0.03)
c.set_edge_collapse_enabled(False)
check(not c.animating and c.can_persist_geometry,
      "收起动画中关闭 edge_collapse 立即落定")
check(not c.collapsed and w.size() == QSize(520, 430),
      "收起动画中关闭后完整展开 520×430")
check(c._dock_overlay is None and not c._hover_timer.isActive(),
      "关闭后 overlay 释放、hover timer 停止")
check(c.state()["edge_collapse"] is False, "state edge_collapse=False")
w.close()

w, c = new_ctl()
dock_small(c, "right")
c.update_palette(theme())
c._collapse_if_docked(force=True, immediate=False)
wait_anim(c)
c.reveal(immediate=False)
pump(0.03)
c.set_edge_collapse_enabled(False)
check(not c.animating and not c.collapsed,
      "展开动画中关闭 edge_collapse 立即完整展开")
check(w.size() == QSize(520, 430), "展开动画中关闭后尺寸 520×430")
check(c._dock_overlay is None, "展开动画中关闭后无 overlay")
w.close()

# 5. close/stop_timers 中断；paint fallback；640/760 不自动收
w, c = new_ctl()
dock_small(c, "left")
c.update_palette({})
c._collapse_if_docked(force=True, immediate=False)
pump(0.03)
c.stop_timers()
check(not c.animating and c.collapsed, "stop_timers 中断动画并落定")
check(c._dock_overlay is None, "stop_timers 后无 overlay")
check(render_dock(c)[1] is True,
      "无 dock_* 主题时 paint_dock fallback 可绘制")
w.close()

for other in ((640, 520), (760, 620)):
    w, c = new_ctl(size=other)
    c.set_normal_size(*other)
    pump()
    avail = app.primaryScreen().availableGeometry()
    w.move(avail.left(), avail.top() + 100)
    pump()
    check(not c._auto_hide_enabled(), "%d×%d 不启用自动收条" % other)
    check(c._collapse_if_docked(force=True, immediate=False) is False,
          "%d×%d _collapse_if_docked 无动作" % other)
    check(not c.animating and not c.collapsed,
          "%d×%d 不产生动画/collapsed" % other)
    w.close()

# 6. 胶囊 grip/方向提示像素（非背景像素在中心附近）
w, c = new_ctl()
dock_small(c, "left")
c.update_palette(theme())
c._collapse_if_docked(force=True, immediate=False)
wait_anim(c)
pix = QPixmap(w.size())
pix.fill(Qt.transparent)
p = QPainter(pix)
c.paint_dock(p)
p.end()
img = pix.toImage()
bg = QColor(theme()["dock_bg"]).rgb()
fg = QColor(theme()["dock_fg"]).rgb()
non_bg = sum(1 for x in range(w.width()) for y in range(w.height())
             if img.pixelColor(x, y).rgb() not in (0, bg))
check(non_bg >= 4, "胶囊有握柄/方向提示可见像素：%d" % non_bg)
w.close()

out.append("")
out.append("失败 %d 项：%s" % (len(fails), " / ".join(fails)) if fails else "全部通过 ✓")
root = os.path.join(WORKSPACE, ".vocab-ui-tests")
os.makedirs(root, exist_ok=True)
path = os.path.join(root, "dock-animation-%d.txt" % int(time.time()))
with io.open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
print("REPORT", path)
sys.exit(1 if fails else 0)
