# -*- coding: utf-8 -*-
"""构建 Windows x64 便携发行包（开发工具，不随发行物发布）。

用法（必须用隔离构建环境的解释器）：
    .build\\venv\\Scripts\\python.exe -B release\\build_windows.py

产物：
    vocab-app-releases\\v1.4.3\\VocabApp-1.4.3-windows-x64\\   目录式安装包
    vocab-app-releases\\v1.4.3\\VocabApp-1.4.3-windows-x64.zip
    vocab-app-releases\\v1.4.3\\SHA256SUMS.txt

约束：
* 运行资产只按白名单复制，绝不整目录打包；个人记录、恢复文件、日志、
  测试/开发材料一律不进包。
* 不修改源码树的任何非构建产物；不删除已有发行目录之外的用户文件。
"""
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1.4.3"
RELEASE_ROOT = os.path.join(ROOT, "vocab-app-releases", "v" + VERSION)
DIST_NAME = "VocabApp-%s-windows-x64" % VERSION
BUILD = os.path.join(ROOT, ".build")
DIST = os.path.join(BUILD, "win-dist")
WORK = os.path.join(BUILD, "win-work")
SPEC = os.path.join(ROOT, "release", "vocab_app.spec")

REQUIRED = (
    "VocabApp.exe",
    "ResetRecords.exe",
    os.path.join("_internal", "data", "bank.json"),
    os.path.join("_internal", "data", "books.json"),
    os.path.join("_internal", "data", "phrases.json"),
    os.path.join("_internal", "data", "phrase_books.json"),
    os.path.join("_internal", "data", "level_meanings.json"),
    os.path.join("_internal", "assets", "vocab-card.ico"),
    os.path.join("_internal", "assets", "vocab-card.svg"),
)

FORBIDDEN_SUFFIXES = (
    ".py", ".pyc", ".pyo", ".spec", ".md", ".bak", ".tmp", ".log", ".lock",
    ".vbs", ".bat", ".lnk", ".zip", ".gz", ".tgz",
)
FORBIDDEN_NAMES = {
    "progress.json", "_win.json", "vocab-app.lock", "startup.log", "debug.log",
    "vocab-card.png",
}

USAGE = """背单词 V{version}（Windows x64 便携版）

怎么用
  1. 把整个文件夹解压到任意位置（可以有中文或空格）。
  2. 双击 VocabApp.exe 打开。无需安装 Python、Anaconda 或任何运行库。
  3. 学习记录保存在同一文件夹的 userdata\\ 内；换电脑时连文件夹一起复制即可。
     如果放在只读目录（例如 Program Files），记录会自动改存到
     %LOCALAPPDATA%\\VocabAppWindows\\。

清空记录
  先关闭 VocabApp，再双击 ResetRecords.exe。它会先列出将要删除的文件，
  输入 CLEAR 回车才会删除，输入其它任何内容即取消；词库不会被删除。
  清空不可撤销：中途失败时可能已删掉部分文件，请以它打印的结果为准。

注意
  * 同一记录目录只允许开一个窗口；重复双击会提示"已在运行"。
  * 本程序未做代码签名，Windows 可能显示 SmartScreen 提示。
  * 本包不含任何学习记录；userdata\\ 是首次运行时新建的。

文件说明
  VocabApp.exe      主程序
  ResetRecords.exe  清空使用记录（控制台）
  _internal\\        运行库与词库（请勿删除或改名）
  userdata\\         你的学习记录（首次运行后出现）
"""

NOTICE = """第三方组件与许可提醒（请务必阅读）

本发行包内含以下第三方运行库，它们各自保留原有许可：
  * Python 3.8.3            PSF License
  * PyQt5 5.12.3            GNU GPL v3（或 Riverbank 商业许可）
  * Qt 5.12.10              GNU LGPL v3 / GPL v3（随 PyQt5 分发）
  * PyInstaller 6.11.1      GPL v2 + bootloader 例外条款

因为 PyQt5 采用 GPL v3，本程序若对外**公开发布**（不再只是自己在本机使用），
需要同时满足 GPL v3 的源码提供义务，或取得 Riverbank 的商业许可。
本仓库当前未声明开源许可；发布前请自行确认。

词库数据（data/ 下的 JSON）来自公开词表与词典整理，其再分发条件
尚未逐项核实；公开发布前必须单独确认，不能默认沿用本程序代码的许可。

本程序不联网、不上传学习记录，记录只存在本机。
"""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message):
    sys.stderr.write("构建失败：" + message + "\n")
    raise SystemExit(1)


def check_environment():
    if "venv" not in sys.executable.replace("\\", "/"):
        fail("请使用 .build\\venv\\Scripts\\python.exe 运行本脚本，避免污染现有 Anaconda。")
    try:
        import PyInstaller  # noqa: F401
        from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
    except Exception as error:  # pragma: no cover - 构建期诊断
        fail("构建环境缺少 PyInstaller/PyQt5：%s" % error)
    print("构建环境：Python %s / PyQt5 %s / Qt %s / PyInstaller %s"
          % (sys.version.split()[0], PYQT_VERSION_STR, QT_VERSION_STR,
             __import__("PyInstaller").__version__))
    for name in ("bank.json", "books.json", "phrases.json", "phrase_books.json",
                 "level_meanings.json"):
        path = os.path.join(ROOT, "data", name)
        if not os.path.isfile(path):
            fail("缺少运行资产：%s" % path)
    for name in ("vocab-card.svg", "vocab-card.ico"):
        if not os.path.isfile(os.path.join(ROOT, "assets", name)):
            fail("缺少图标资源：%s" % name)


def run_pyinstaller():
    for path in (DIST, WORK):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(DIST, exist_ok=True)
    command = [
        sys.executable, "-B", "-m", "PyInstaller",
        "--noconfirm", "--clean", "--log-level", "WARN",
        "--distpath", DIST, "--workpath", WORK,
        SPEC,
    ]
    print("执行：" + " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        fail("PyInstaller 返回 %d" % result.returncode)


def check_layout(source):
    for relative in REQUIRED:
        if not os.path.isfile(os.path.join(source, relative)):
            fail("构建产物缺少：" + relative)
    problems = []
    # 顶层只允许两个 exe、_internal 与两份说明文本；源码/脚本/文档/记录一律不许出现。
    top_level_exe = {"VocabApp.exe", "ResetRecords.exe"}
    for name in sorted(os.listdir(source)):
        full = os.path.join(source, name)
        lower = name.casefold()
        if os.path.isdir(full):
            if name != "_internal":
                problems.append(name + "（多余目录）")
            continue
        if name in top_level_exe:
            continue
        if name in {"使用说明.txt", "第三方组件与许可.txt"}:
            continue
        problems.append(name + "（多余文件）")
    # 编译运行库必须保留；只例外允许 Python 的 base_library.zip。
    forbidden_dirs = {"docs", "scripts", "test", "tests", ".git", "__pycache__", "node_modules"}
    for base, dirs, files in os.walk(source):
        for name in dirs:
            full = os.path.join(base, name)
            if name.casefold() in forbidden_dirs or os.path.islink(full):
                problems.append(os.path.relpath(full, source))
        for name in files:
            full = os.path.join(base, name)
            relative = os.path.relpath(full, source)
            lower = name.casefold()
            bootstrap = relative.replace("\\", "/") == "_internal/base_library.zip"
            record = (lower in FORBIDDEN_NAMES or lower.startswith(("progress.json.", "_win.json.", "vocab-v140-")))
            forbidden = lower.endswith(FORBIDDEN_SUFFIXES) and not bootstrap
            if record or forbidden or os.path.islink(full):
                problems.append(relative)
    for folder, allowed in (("data", {os.path.basename(p) for p in REQUIRED if os.path.dirname(p) == os.path.join("_internal", "data")}),
                            ("assets", {"vocab-card.svg", "vocab-card.ico"})):
        actual = set(os.listdir(os.path.join(source, "_internal", folder)))
        if actual != allowed:
            problems.append("_internal/%s（资产白名单不匹配）" % folder)
    if problems:
        fail("发行目录出现不该发布的文件：\n  " + "\n  ".join(sorted(problems)[:20]))


def stage_release():
    target = os.path.join(RELEASE_ROOT, DIST_NAME)
    if os.path.exists(target):
        # 只替换仍是干净发行物的目录；一旦运行产生 userdata，必须先由用户另存。
        check_layout(target)
        if os.path.islink(target):
            fail("发行目标是目录链接，拒绝替换：" + target)
        shutil.rmtree(target)
    os.makedirs(RELEASE_ROOT, exist_ok=True)
    shutil.copytree(os.path.join(DIST, "VocabApp"), target)
    with open(os.path.join(target, "使用说明.txt"), "w", encoding="utf-8", newline="\r\n") as stream:
        stream.write(USAGE.format(version=VERSION))
    with open(os.path.join(target, "第三方组件与许可.txt"), "w", encoding="utf-8", newline="\r\n") as stream:
        stream.write(NOTICE)
    return target


def zip_release(source):
    archive = os.path.join(RELEASE_ROOT, DIST_NAME + ".zip")
    if os.path.exists(archive):
        os.remove(archive)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for base, dirs, files in os.walk(source):
            dirs.sort()
            for name in sorted(files):
                full = os.path.join(base, name)
                relative = os.path.relpath(full, os.path.dirname(source))
                package.write(full, relative.replace(os.sep, "/"))
    return archive


def write_sums(archive):
    path = os.path.join(RELEASE_ROOT, "SHA256SUMS.txt")
    line = "%s  %s\n" % (sha256_file(archive), os.path.basename(archive))
    previous = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as stream:
            previous = stream.read()
    basename = os.path.basename(archive)
    retained = [item for item in previous.splitlines()
                if len(item.split()) == 2 and item.split()[1] != basename]
    with open(path, "w", encoding="utf-8", newline="\r\n") as stream:
        for item in retained:
            stream.write(item + "\n")
        stream.write(line)
    print("SHA-256：" + line.strip())


def main():
    check_environment()
    run_pyinstaller()
    built = os.path.join(DIST, "VocabApp")
    check_layout(built)
    target = stage_release()
    archive = zip_release(target)
    write_sums(archive)
    size = os.path.getsize(archive) / (1024.0 * 1024.0)
    print("完成：%s（%.1f MiB）" % (archive, size))


if __name__ == "__main__":
    main()
