# -*- coding: utf-8 -*-
"""统一解析只读资源与可写资料位置，供源码运行与冻结发行共用。

设计（不改动任何既有源码路径语义）：

* 源码运行（未冻结）：``resource_root()`` 就是项目根（``app/`` 的父目录），
  ``data/``、``assets/`` 在其下，行为与 V1.4.3 完全一致。
* 冻结发行（PyInstaller onedir）：只读资源在 ``sys._MEIPASS``（即 ``_internal/``）
  内；可写资料默认在可执行文件旁的 ``userdata/``，只读安装时回退到用户目录。
* DSH 插件版是独立的 Node 实现，不 import 本模块。

本模块只做路径计算，不创建目录、不读文件内容。
"""
import os
import sys


def is_frozen():
    """是否运行在 PyInstaller 冻结包内。"""
    return bool(getattr(sys, "frozen", False))


def _bundle_dir():
    """只读资源根：冻结包内为 ``_internal``，源码运行为项目根。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.abspath(meipass)
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _install_dir():
    """安装根：冻结包为 exe 所在目录，源码运行为项目根。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_root():
    return _bundle_dir()


def install_root():
    return _install_dir()


def app_root():
    """Python 模块目录（源码运行是 ``app/``；冻结后模块已编译进包）。"""
    if is_frozen():
        return _bundle_dir()
    return os.path.join(_install_dir(), "app")


def data_root():
    """只读词库目录。"""
    return os.path.join(_bundle_dir(), "data")


def assets_root():
    """只读图标等资源目录。"""
    return os.path.join(_bundle_dir(), "assets")


def portable_data_dir():
    """冻结发行的默认可写资料目录（安装目录旁，便于整包搬移）。"""
    return os.path.join(_install_dir(), "userdata")


def qt_dll_candidates():
    """冻结时 Qt 运行库可能所在的目录（只计算，不校验存在性）。"""
    if not is_frozen():
        return []
    bundle = _bundle_dir()
    return [
        bundle,
        os.path.join(bundle, "PyQt5", "Qt5", "bin"),
        os.path.join(bundle, "PyQt5", "Qt", "bin"),
        os.path.join(bundle, "Library", "bin"),
    ]


def qt_plugin_dir():
    """冻结时 Qt 插件目录（platforms/imageformats/svg），可能不存在。"""
    if not is_frozen():
        return None
    for name in ("Qt5", "Qt"):
        candidate = os.path.join(_bundle_dir(), "PyQt5", name, "plugins")
        if os.path.isdir(candidate):
            return candidate
    return None
