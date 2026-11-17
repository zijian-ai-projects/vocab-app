# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配方：一个安装目录里放 GUI 主程序与清空记录工具。

构建入口是 release/build_windows.py；本文件只描述布局，不自己执行。
运行资产按白名单逐个复制到 `_internal/data`、`_internal/assets`，绝不整目录
打包（源 `data/` 目录里还有个人记录、恢复文件与测试资料）。
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))
APP = os.path.join(ROOT, "app")

RUNTIME_DATA = (
    "bank.json",
    "books.json",
    "phrases.json",
    "phrase_books.json",
    "level_meanings.json",
)
RUNTIME_ASSETS = ("vocab-card.svg", "vocab-card.ico")

datas = [(os.path.join(ROOT, "data", name), "data") for name in RUNTIME_DATA]
datas += [(os.path.join(ROOT, "assets", name), "assets") for name in RUNTIME_ASSETS]

HIDDEN = ["main", "paths", "storage", "books", "level_meanings", "app_icon", "windowing", "catalog"]
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3",
    "numpy", "pandas", "matplotlib", "scipy", "PIL",
    "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtQml",
    "PyQt5.QtQuick", "PyQt5.QtMultimedia", "PyQt5.QtBluetooth", "PyQt5.QtNetwork",
    "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.QtTest", "PyQt5.QtXmlPatterns",
]

gui = Analysis(
    [os.path.join(APP, "launcher.py")],
    pathex=[APP],
    binaries=[],
    datas=datas,
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

reset = Analysis(
    [os.path.join(ROOT, "scripts", "reset_records.py")],
    pathex=[APP],
    binaries=[],
    datas=datas,
    hiddenimports=["paths", "storage"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

gui_pyz = PYZ(gui.pure, gui.zipped_data)
reset_pyz = PYZ(reset.pure, reset.zipped_data)

gui_exe = EXE(
    gui_pyz,
    gui.scripts,
    [],
    exclude_binaries=True,
    name="VocabApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    icon=os.path.join(ROOT, "assets", "vocab-card.ico"),
)

reset_exe = EXE(
    reset_pyz,
    reset.scripts,
    [],
    exclude_binaries=True,
    name="ResetRecords",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

# 只在本地排查启动崩溃时使用：VOCAB_BUILD_DEBUG_EXE=1 会额外产出一个带控制台的
# 同名主程序，正常构建不生成、也不会进入发行包。
_extras = []
if os.environ.get("VOCAB_BUILD_DEBUG_EXE") == "1":
    _extras.append(EXE(
        gui_pyz,
        gui.scripts,
        [],
        exclude_binaries=True,
        name="VocabAppDebug",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
    ))

coll = COLLECT(
    gui_exe,
    gui.binaries,
    gui.datas,
    reset_exe,
    reset.binaries,
    reset.datas,
    *_extras,
    strip=False,
    upx=False,
    name="VocabApp",
)
