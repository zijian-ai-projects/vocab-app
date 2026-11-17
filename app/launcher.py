# -*- coding: utf-8 -*-
"""启动引导：让 pythonw（没有控制台）启动失败时也能看见原因、留下日志。

只做进程级准备，不解析、不迁移、不修改任何学习记录；记录仍由 app/main.py
的 storage 层负责。三个作用：

1. 把 Anaconda 的 ``Library\\bin``（Qt5Core_conda.dll 所在目录）补到 PATH 前面。
   本机 PyQt5 的 find_qt() 只在 PATH 里找 DLL，不从 sys.prefix 主动找；用户从
   Explorer 启动时若 PATH 与终端不同，会在 ``import main`` 处直接 ImportError，
   pythonw 没有 stderr，于是表现为“双击完全没反应”。
2. 每次启动把一行开始/退出记录追加到资料目录的 ``startup.log``；异常时写入完整
   traceback，方便事后排查。
3. 任何启动期异常都用系统 MessageBoxW 弹出可见错误（即使 Qt 本身导入失败），
   并明确提示“学习记录未清空”。

成功启动后完全交给 main.main()，不接管窗口、记录或退出流程。
"""
import os
import sys
import tempfile
import time
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)
LOG_NAME = "startup.log"
MAX_LOG_BYTES = 200 * 1024
QT_DLL_NAMES = ("Qt5Core_conda.dll", "Qt5Core.dll")
FROZEN = bool(getattr(sys, "frozen", False))


def qt_dll_dirs():
    """返回可能存放 Qt5Core DLL 的目录（只读判断，不创建、不写入）。"""
    if FROZEN:
        # 冻结包里 Qt 运行库随包携带，绝不依赖开发机的 Anaconda/PATH。
        candidates = []
        try:
            sys.path.insert(0, APP_DIR)
            import paths as app_paths
            candidates.extend(app_paths.qt_dll_candidates())
        except Exception:
            candidates.append(getattr(sys, "_MEIPASS", ROOT))
        return candidates
    prefix = os.path.abspath(sys.prefix)
    site = os.path.join(prefix, "Lib", "site-packages")
    return [
        os.path.join(prefix, "Library", "bin"),      # conda（本机）
        os.path.join(site, "PyQt5", "Qt", "bin"),     # 官方 wheel
        os.path.join(site, "PyQt5", "Qt5", "bin"),
        os.path.join(site, "PySide2", "Qt", "bin"),
    ]


def find_qt_dll_dir():
    for directory in qt_dll_dirs():
        if not os.path.isdir(directory):
            continue
        for name in QT_DLL_NAMES:
            if os.path.isfile(os.path.join(directory, name)):
                return directory
    return None


def ensure_qt_on_path():
    """把 Qt DLL 目录放到 PATH 首位；返回加入的目录，找不到或已在 PATH 中返回 None。"""
    if os.name != "nt":
        return None
    directory = find_qt_dll_dir()
    if not directory:
        return None
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    normalized = {os.path.normcase(os.path.abspath(p)) for p in parts}
    added = None
    if os.path.normcase(directory) not in normalized:
        os.environ["PATH"] = os.pathsep.join([directory] + parts)
        added = directory
    if FROZEN:
        # 让 Qt 只从随包插件目录加载，避免混入系统里其它 Qt 的插件。
        try:
            import paths as app_paths
            plugins = app_paths.qt_plugin_dir()
        except Exception:
            plugins = None
        if plugins:
            os.environ["QT_PLUGIN_PATH"] = plugins
            os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    return added


def log_file():
    """日志放在资料目录；取不到资料目录时退到系统临时目录。不写记录文件。"""
    try:
        if APP_DIR not in sys.path:
            sys.path.insert(0, APP_DIR)
        import storage
        return os.path.join(storage.data_dir(None if FROZEN else ROOT), LOG_NAME)
    except Exception:
        return os.path.join(tempfile.gettempdir(), "VocabApp-" + LOG_NAME)


def _trim_log(path):
    try:
        if os.path.getsize(path) <= MAX_LOG_BYTES:
            return
        with open(path, "rb") as stream:
            stream.seek(-MAX_LOG_BYTES // 2, os.SEEK_END)
            tail = stream.read()
        with open(path, "wb") as stream:
            stream.write(b"[log truncated]\n" + tail)
    except OSError:
        pass


def write_log(text):
    """追加一行/一段日志；失败也不抛异常（不能因为日志挡住启动）。"""
    path = log_file()
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        _trim_log(path)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(text.rstrip() + "\n")
    except OSError:
        pass
    return path


def _show_message_box(title, text):
    """系统级错误框；pythonw 没有控制台时也能看见。"""
    if os.name != "nt":
        raise OSError("非 Windows 环境不使用系统对话框")
    import ctypes
    # MB_ICONERROR | MB_TOPMOST
    ctypes.windll.user32.MessageBoxW(None, str(text), str(title),
                                     0x00000010 | 0x00040000)


def alert(title, text):
    """显示启动错误；系统对话框不可用时退到 stderr。"""
    try:
        _show_message_box(title, text)
        return
    except Exception:
        pass
    stream = sys.stderr
    if stream is not None:
        try:
            stream.write("%s: %s\n" % (title, text))
            stream.flush()
        except Exception:
            pass


def _last_line(detail):
    lines = [line.strip() for line in detail.strip().splitlines() if line.strip()]
    return lines[-1][:600] if lines else "未知错误"


def trace(text):
    """仅在显式设置 VOCABAPP_TRACE 时向 stderr 写启动阶段标记（排查冻结包卡住）。"""
    if not os.environ.get("VOCABAPP_TRACE"):
        return
    try:
        stream = sys.stderr
        if stream is not None:
            stream.write("[trace] %s\n" % text)
            stream.flush()
    except Exception:
        pass


def run(argv=None):
    """启动应用并返回退出码；主流程仍由 main.main() 负责。"""
    started = time.time()
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    trace("start frozen=%s app_dir=%s sys_prefix=%s" % (FROZEN, APP_DIR, sys.prefix))
    try:
        added = ensure_qt_on_path()
        trace("qt_path=%s" % (added or "-"))
        import main as app_main
        trace("import main ok")
        version = getattr(app_main, "VERSION", "?")
        path = write_log("%s start version=%s qt_dll=%s profile=%s pid=%s"
                         % (time.strftime("%Y-%m-%d %H:%M:%S"), version,
                            added or "-", os.path.dirname(log_file()), os.getpid()))
        trace("log=%s" % path)
        result = app_main.main()
        trace("main returned %r" % (result,))
        code = 0 if result is None else result
        write_log("%s exit code=%s seconds=%.2f"
                  % (time.strftime("%Y-%m-%d %H:%M:%S"), code,
                     time.time() - started))
        return code
    except SystemExit as exc:
        code = 0 if exc.code is None else exc.code
        if not isinstance(code, int):
            code = 1
        write_log("%s exit code=%s seconds=%.2f"
                  % (time.strftime("%Y-%m-%d %H:%M:%S"), code,
                     time.time() - started))
        return code
    except BaseException:
        detail = traceback.format_exc()
        path = write_log("%s FAILED\n%s"
                         % (time.strftime("%Y-%m-%d %H:%M:%S"), detail))
        alert("背单词启动失败",
              "启动时发生错误，学习记录没有清空。\n\n"
              "详细日志：\n%s\n\n错误：\n%s" % (path, _last_line(detail)))
        return 1


if __name__ == "__main__":
    sys.exit(run())
