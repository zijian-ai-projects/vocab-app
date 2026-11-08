# -*- coding: utf-8 -*-
"""应用图标与 Windows 任务栏身份；仅读取资源，不触碰学习记录。"""
import os
from functools import lru_cache

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
APP_ID = "VocabCard.Desktop"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_icon(size, svg_path=None):
    """直接渲染矢量词卡；小尺寸分别采样，避免任务栏图标模糊。"""
    svg_path = svg_path or os.path.join(ASSET_DIR, "vocab-card.svg")
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise ValueError("应用图标资源无效：" + svg_path)
    side = max(1, int(size))
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, side, side))
    finally:
        painter.end()
    return pixmap


@lru_cache(maxsize=1)
def application_icon():
    """优先使用多尺寸 ICO；资源未打包时以矢量源回退。"""
    icon = QIcon(os.path.join(ASSET_DIR, "vocab-card.ico"))
    if icon.isNull():
        icon = QIcon()
        for side in ICON_SIZES:
            icon.addPixmap(render_icon(side))
    return icon


def configure_application_icon(app):
    """设置窗口、任务栏、Alt-Tab 和应用对话框共用的图标。"""
    app.setApplicationDisplayName("背单词")
    app.setWindowIcon(application_icon())


def set_windows_app_id():
    """避免任务栏沿用 pythonw/PyQt 默认图标；不修改注册表或系统配置。"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_id.argtypes = [ctypes.c_wchar_p]
        set_id.restype = ctypes.c_long
        return set_id(APP_ID) == 0
    except (AttributeError, OSError):
        # 不让可选的 Shell 身份设置阻止应用安全启动。
        return False
