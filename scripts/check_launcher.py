# -*- coding: utf-8 -*-
"""真实双击路径验收：用隔离资料运行 启动背单词.vbs，检查窗口真的出现。

覆盖三种情况：
  normal      Windows 正常 PATH（等价双击）
  bare-path   PATH 只剩 System32（模拟 Explorer 环境里没有 Anaconda），
              验证 app/launcher.py 的 Qt DLL 引导仍能启动
  bad-record  隔离资料里的 states 结构损坏，必须弹出可见错误、退出码非 0，
              且不覆盖原记录

只在 .vocab-ui-tests 下创建隔离资料；开始/结束都对真实资料做字节指纹校验。
用法：python scripts/check_launcher.py --mode normal
"""
import argparse
import ctypes
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VBS = os.path.join(APP, "启动背单词.vbs")
WORKSPACE = os.path.dirname(APP)
TEST_ROOT = os.path.join(WORKSPACE, ".vocab-ui-tests")
WSCRIPT = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                       "wscript.exe")
WINDOW_TITLE = "背单词"
CARD_CLASS = "Qt5QWindowIcon"

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
k32.TerminateProcess.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]

dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
DWMWA_EXTENDED_FRAME_BOUNDS = 9

WM_CLOSE, WM_COMMAND, IDOK = 0x0010, 0x0111, 1
PROCESS_TERMINATE, PROCESS_QUERY_LIMITED = 0x0001, 0x1000
REAL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "VocabApp")
RECORD_NAMES = ("progress.json", "progress.json.bak", "_win.json", "_win.json.bak")


class Checks:
    def __init__(self):
        self.lines, self.failed = [], 0

    def ok(self, cond, message):
        self.lines.append(("  OK   " if cond else "  FAIL ") + message)
        if not cond:
            self.failed += 1
        return bool(cond)

    def note(self, message):
        self.lines.append("        " + message)

    def finish(self, path):
        self.lines.append("")
        self.lines.append("FAILS %d" % self.failed if self.failed
                          else "全部通过 ✓")
        text = "\n".join(self.lines)
        with io.open(path, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
        print(text)
        return 0 if not self.failed else 1


def related(path):
    base = os.path.abspath(path)
    names = {base, base + ".bak", base + ".tmp"}
    directory, name = os.path.dirname(base), os.path.basename(base)
    try:
        for item in os.listdir(directory):
            if item.startswith(name + ".tmp-") or item.startswith(name + ".bak.tmp-"):
                names.add(os.path.join(directory, item))
    except OSError:
        pass
    return names


def fingerprint(directory, names=RECORD_NAMES):
    result = {}
    if not os.path.isdir(directory):
        return result
    for name in names:
        for path in related(os.path.join(directory, name)):
            try:
                with open(path, "rb") as stream:
                    result[path] = stream.read()
            except OSError:
                result[path] = None
    return result


def list_windows():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindow(hwnd):
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        length = max(0, user32.GetWindowTextLengthW(hwnd))
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        found.append({"hwnd": int(hwnd), "pid": owner.value, "title": title.value,
                      "class": cls.value, "visible": bool(user32.IsWindowVisible(hwnd)),
                      "rect": [rect.left, rect.top, rect.right, rect.bottom]})
        return True

    user32.EnumWindows(callback, 0)
    return found


def dwm_frame(hwnd):
    rect = wintypes.RECT()
    result = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                          ctypes.byref(rect), ctypes.sizeof(rect))
    if result != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return [rect.left, rect.top, rect.right, rect.bottom]


def process_image(pid):
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(1024)
        if k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        k32.CloseHandle(handle)


def card_windows():
    return [w for w in list_windows() if w["title"] == WINDOW_TITLE]


def find_new_card(before):
    for window in list_windows():
        if (window["hwnd"] not in before and window["visible"]
                and window["class"] == CARD_CLASS
                and window["title"] == WINDOW_TITLE):
            return window
    return None


def close(hwnd):
    user32.PostMessageW(wintypes.HWND(hwnd), WM_COMMAND, IDOK, 0)
    user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0)


def terminate(pid):
    handle = k32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if handle:
        k32.TerminateProcess(handle, 1)
        k32.CloseHandle(handle)


def wait_for(predicate, timeout=25.0, interval=0.25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def screenshot(rect, path):
    from PIL import ImageGrab
    left, top, right, bottom = rect
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    image.save(path)
    return image.size


def prepare_profile(mode, root):
    profile = os.path.join(root, "profile")
    os.makedirs(profile)
    if mode == "bad-record":
        with io.open(os.path.join(profile, "progress.json"), "w", encoding="utf-8") as stream:
            json.dump({"states": [1, 2, 3], "history": []}, stream)
        return profile
    for name in RECORD_NAMES:
        source = os.path.join(REAL_DIR, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(profile, name))
    if mode == "stale-lock":
        # 复制真实资料目录里已终止实例留下的锁，验证下次启动能安全接管
        source = os.path.join(REAL_DIR, "vocab-app.lock")
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(profile, "vocab-app.lock"))
    return profile


def child_env(profile, bare_path):
    env = dict(os.environ)
    env["VOCABAPP_DATA_DIR"] = profile
    env.pop("PYTHONPATH", None)
    if bare_path:
        env["PATH"] = os.pathsep.join([
            os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32"),
            env.get("SystemRoot", r"C:\Windows")])
    return env


def find_card():
    return next((w for w in list_windows()
                 if w["visible"] and w["class"] == CARD_CLASS
                 and w["title"] == WINDOW_TITLE), None)


def find_dialog(title_part, before):
    """Qt 的 QMessageBox 也是 Qt5QWindowIcon 类，原生 MsgBox 才是 #32770；
    这里按标题、可见性和“启动后新出现”识别，两种都能覆盖。"""
    return next((w for w in list_windows()
                 if w["hwnd"] not in before and w["visible"]
                 and title_part in w["title"]), None)


def read_log(path):
    if not os.path.isfile(path):
        return ""
    with io.open(path, encoding="utf-8", errors="replace") as stream:
        return stream.read()


def measure_normal(checks, mode, root, profile, proc, before):
    card = wait_for(lambda: find_new_card(before), timeout=30)
    if not checks.ok(card is not None, "双击后出现可见的背单词窗口"):
        return None
    frame = dwm_frame(card["hwnd"])
    width = frame[2] - frame[0]
    height = frame[3] - frame[1]
    checks.note("窗口：%s title=%s pid=%s frame=%s" % (card["class"], card["title"],
                                                       card["pid"], frame))
    image = process_image(card["pid"])
    checks.ok(os.path.basename(image).lower() in ("pythonw.exe", "python.exe"),
              "窗口属于 Anaconda Python 进程（%s）" % image)
    checks.ok(480 <= width <= 540 and 400 <= height <= 450,
              "正常窗口尺寸约 520×430（实际 %d×%d）" % (width, height))
    checks.ok(frame[0] >= 0 and frame[1] >= 0
              and frame[2] <= 1920 and frame[3] <= 1080,
              "窗口位于可见屏幕范围内")
    screenshot(frame, os.path.join(root, "window.png"))

    log = os.path.join(profile, "startup.log")
    checks.ok(wait_for(lambda: os.path.isfile(log), timeout=5) is not None,
              "startup.log 已创建（隔离目录）")
    text = read_log(log)
    checks.ok("start version=1.3.1" in text, "日志记录了版本 1.3.1")
    checks.ok("qt_dll=" in text, "日志记录了 Qt DLL 引导结果")
    if text.strip():
        checks.note(text.strip().splitlines()[0])

    close(card["hwnd"])
    if not checks.ok(wait_for(lambda: proc.poll() is not None, timeout=25) is not None,
                     "关闭窗口后进程正常退出"):
        return None
    checks.ok(proc.poll() == 0, "正常关闭退出码为 0（%s）" % proc.poll())
    checks.ok(not os.path.exists(os.path.join(profile, "vocab-app.lock")),
              "退出后实例锁已释放")
    checks.ok("exit code=0" in read_log(log), "日志记录了正常退出")
    files = sorted(os.listdir(profile))
    checks.note("资料目录：%s" % ", ".join(files))
    checks.ok("startup.log" in files, "日志位于隔离资料目录")
    return True


def measure_bad_record(checks, root, profile, proc, before, hwnds_before):
    dialog = wait_for(lambda: find_dialog("无法安全启动", hwnds_before), timeout=40)
    if not checks.ok(dialog is not None, "损坏记录弹出可见的「无法安全启动」"):
        return None
    checks.note("对话框：%s / %s" % (dialog["title"], dialog["rect"]))
    screenshot(dialog["rect"], os.path.join(root, "dialog.png"))
    close(dialog["hwnd"])
    second = wait_for(lambda: find_dialog("背单词启动失败", hwnds_before), timeout=25)
    checks.ok(second is not None, "VBS 随后提示启动失败")
    if second:
        checks.note("对话框：%s / %s" % (second["title"], second["rect"]))
        screenshot(second["rect"], os.path.join(root, "dialog-failed.png"))
        close(second["hwnd"])
    if not checks.ok(wait_for(lambda: proc.poll() is not None, timeout=25) is not None,
                     "错误提示关闭后进程退出"):
        return None
    code = proc.poll()
    checks.ok(code not in (0, None), "退出码非 0（%s）" % code)
    checks.ok(not os.path.exists(os.path.join(profile, "vocab-app.lock")),
              "退出后没有遗留实例锁")
    after = fingerprint(profile)
    checks.ok(before == after, "损坏的隔离记录字节未被改写（拒绝启动而非清空）")
    log = os.path.join(profile, "startup.log")
    text = read_log(log)
    checks.ok("exit code=" in text, "失败退出码写入 startup.log")
    checks.note(text.strip().splitlines()[-1] if text.strip() else "无日志")
    return True


def run(mode):
    checks = Checks()
    os.makedirs(TEST_ROOT, exist_ok=True)
    root = tempfile.mkdtemp(prefix="launcher-check-%s-" % mode, dir=TEST_ROOT)
    out = os.path.join(root, "result.txt")
    real_before = fingerprint(REAL_DIR)
    proc = None
    hwnds_before = set()
    rc = 0
    try:
        checks.note("隔离目录：%s" % root)
        stale = card_windows()
        checks.ok(not stale, "启动前没有残留的背单词实例/窗口"
                  + ("" if not stale else "（残留 %d 个，会挡住启动）" % len(stale)))
        checks.ok(os.path.isfile(VBS), "启动脚本存在")
        with open(VBS, "rb") as stream:
            checks.ok(stream.read(2) == b"\xff\xfe", "启动脚本为 Unicode（中文提示不乱码）")
        profile = prepare_profile(mode, root)
        checks.ok(os.path.isdir(profile), "隔离资料已准备")
        if mode == "bad-record":
            before = fingerprint(profile)
        env = child_env(profile, bare_path=(mode == "bare-path"))
        if mode == "bare-path":
            checks.note("子进程 PATH=%s" % env["PATH"])

        hwnds_before = {window["hwnd"] for window in list_windows()}
        proc = subprocess.Popen([WSCRIPT, VBS], cwd=APP, env=env)
        if mode == "bad-record":
            result = measure_bad_record(checks, root, profile, proc, before, hwnds_before)
        else:
            result = measure_normal(checks, mode, root, profile, proc, hwnds_before)
        checks.ok(result is True, "验收场景执行完整")
    except subprocess.TimeoutExpired:
        checks.ok(False, "等待进程退出超时")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        for window in card_windows():
            if window["hwnd"] not in hwnds_before:
                terminate(window["pid"])
        checks.ok(wait_for(lambda: not card_windows(), timeout=6) is not None,
                  "退出后没有留下不可见的背单词实例")
        real_after = fingerprint(REAL_DIR)
        checks.ok(real_before == real_after,
                  "真实学习记录与实例锁字节未变（%d 个文件）" % len(real_before))
        rc = checks.finish(out)
    return rc
    return rc


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",
                        choices=("normal", "bare-path", "bad-record", "stale-lock"),
                        default="normal")
    args = parser.parse_args(argv)
    return run(args.mode)


if __name__ == "__main__":
    sys.exit(main())
