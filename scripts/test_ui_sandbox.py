# -*- coding: utf-8 -*-
"""测试 ui_test_support.Sandbox 的隔离/指纹/退出清理本身。

覆盖：
  * legacy data 记录 + app.DEFAULT_PROGRESS_PATH/DEFAULT_WIN_PATH 稳定记录
    以及 .bak/.tmp/.tmp-*/.bak.tmp-* 的指纹；变化只报告、不恢复；
  * 指纹能发现测试期间新建的恢复文件；
  * 夹具 write_progress/write_win 会清掉自己的恢复文件；
  * Card 在 Sandbox 内构造；退出前停全部 QTimer + window_ctl、关闭 Card、drain；
  * 关闭后的迟到 save/_quiz_next/_check_due/_save_window 不写默认真实路径；
  * 报告/临时输出都在 workspace .vocab-ui-tests，不触碰真实记录。

不修改 main；如果 main 当前有错误，本测试只记录具体异常。
"""
import os
import sys
import io
import json
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
WORKSPACE = os.path.dirname(APP)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(APP, "app"))

from ui_test_support import (configure_qt, Sandbox, set_nottest, new_app,
                             TEST_ROOT, SandboxError, REAL_PROGRESS)

configure_qt("offscreen")
set_nottest(True)

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

app = new_app(sys.argv)
out = []
fails = []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def pump(n=8):
    for _ in range(n):
        app.processEvents()


def fixture():
    import books as bk
    return {
        "welcome_done": True,
        "book_confirmed": True,
        "book": bk.DEFAULT,
        "theme": "light",
        "states": {},
        "cursors": {},
        "orders": {},
        "history": [{"ts": int(time.time()) - 3600, "vocab": 5000,
                     "right": 20, "dontknow": 8, "total": 50,
                     "theta": 0.2, "se": 0.5, "baseline": True,
                     "known": 3000, "to_learn": 10000, "rigor": 90,
                     "err": 10, "lo": 4500, "hi": 5500}],
    }


# ======================================================================
# 1. 假 app：指纹覆盖 legacy/stable + bak/tmp，且只报告不恢复
# ======================================================================
def fake_app_probe():
    import tempfile
    root = tempfile.mkdtemp(prefix="fp-probe-", dir=_ensure_test_root())
    legacy = os.path.join(root, "legacy")
    stable = os.path.join(root, "stable")
    os.makedirs(legacy)
    os.makedirs(stable)
    lp = os.path.join(legacy, "progress.json")
    lw = os.path.join(legacy, "_win.json")
    sp = os.path.join(stable, "progress.json")
    sw = os.path.join(stable, "_win.json")
    for p, text in ((lp, "legacy-progress"), (lw, "legacy-win"),
                    (sp, "stable-progress"), (sw, "stable-win")):
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(text)
        with io.open(p + ".bak", "w", encoding="utf-8") as f:
            f.write(text + "-bak")
        with io.open(p + ".tmp-synthetic", "w", encoding="utf-8") as f:
            f.write(text + "-tmp")

    class FakeApp:
        DATA = legacy
        LEGACY_PROGRESS_PATH = lp
        LEGACY_WIN_PATH = lw
        LEGACY_PROGRESS_PATHS = (lp, os.path.join(root, "older", "progress.json"))
        LEGACY_WIN_PATHS = (lw, os.path.join(root, "older", "_win.json"))
        DEFAULT_PROGRESS_PATH = sp
        DEFAULT_WIN_PATH = sw
        PROGRESS_PATH = lp
        WIN_PATH = lw

    fs = Sandbox(FakeApp, "fp")
    fs.__enter__()
    check(any(p.endswith("progress.json.bak") for p in fs.watch_paths),
          "指纹包含 legacy progress.bak")
    check(any(p.endswith(".tmp-synthetic") for p in fs.watch_paths),
          "指纹包含唯一 temp 恢复文件")
    check(sp in fs.watch_paths and sw in fs.watch_paths,
          "指纹包含 stable DEFAULT_PROGRESS_PATH/DEFAULT_WIN_PATH")
    check(all(path in fs.watch_paths for path in FakeApp.LEGACY_PROGRESS_PATHS
              + FakeApp.LEGACY_WIN_PATHS), "指纹包含有序列表的全部旧资料来源")
    check(fs.verify_real(), "初始真实指纹无变化")
    # 模拟测试期间真实文件被别的进程改动（只应报错，不碰文件）
    before = open(sp, "rb").read()
    with io.open(sp, "wb") as f:
        f.write(b"changed-by-other-process")
    check(fs.verify_real() is False, "真实文件变化能被发现")
    check(any("真实记录" in e for e in fs.errors), "变化进入 errors")
    # cleanup 越界保护：mutated self.dir 不能 rmtree
    import tempfile as _tf
    outside = _tf.mkdtemp(prefix="outside-", dir=_ensure_test_root())
    fs.dir = outside
    fs._safe_rmtree(fs.dir)
    check(os.path.isdir(outside), "mutated self.dir 越界时 _safe_rmtree 拒绝删除")
    check(any("拒绝删除" in e for e in fs.errors), "越界删除进入 errors")
    import shutil
    shutil.rmtree(outside, ignore_errors=True)
    fs.dir = fs._root
    fs.__exit__(None, None, None)
    after = open(sp, "rb").read()
    check(after == b"changed-by-other-process", "Sandbox 不恢复/不覆盖真实文件")
    check(any("真实记录" in e for e in fs.errors), "退出时仍保留错误")
    import shutil as _sh
    _sh.rmtree(root, ignore_errors=True)


def _ensure_test_root():
    try:
        os.makedirs(TEST_ROOT, exist_ok=True)
    except OSError:
        pass
    return TEST_ROOT


# ======================================================================
# 2. 真 app：Sandbox 指纹包含 legacy + stable；Card 只在沙箱内构造
# ======================================================================
def real_app_probe():
    import main as app_main
    from PyQt5.QtCore import QTimer

    sb = Sandbox(app_main, "sandbox")
    sb.__enter__()
    card = None
    try:
        check(any(p == os.path.abspath(app_main.DEFAULT_PROGRESS_PATH)
                  for p in sb.watch_paths),
              "真 app 指纹包含 DEFAULT_PROGRESS_PATH")
        check(any(p == os.path.abspath(app_main.DEFAULT_WIN_PATH)
                  for p in sb.watch_paths),
              "真 app 指纹包含 DEFAULT_WIN_PATH")
        check(any(p == os.path.abspath(app_main.LEGACY_PROGRESS_PATH)
                  for p in sb.watch_paths),
              "真 app 指纹包含 legacy data/progress.json")
        check(sb.verify_real(), "进入沙箱后真实指纹不变")

        # 夹具自己的恢复文件会被清理，真实目录不受影响
        for suffix in (".bak", ".tmp", ".tmp-abc", ".bak.tmp-def"):
            p = sb.progress_path + suffix
            with io.open(p, "w", encoding="utf-8") as f:
                f.write("fixture-sidecar")
        sb.write_progress({})
        check(not any(os.path.exists(sb.progress_path + s)
                      for s in (".bak", ".tmp", ".tmp-abc", ".bak.tmp-def")),
              "write_progress 清掉夹具自己的 progress 恢复文件")
        for suffix in (".bak", ".tmp-abc"):
            p = sb.win_path + suffix
            with io.open(p, "w", encoding="utf-8") as f:
                f.write("fixture-sidecar")
        sb.write_win({})
        check(not any(os.path.exists(sb.win_path + s)
                      for s in (".bak", ".tmp-abc")),
              "write_win 清掉夹具自己的 win 恢复文件")

        # clear_fixture_sidecars 只清 sidecar；reset(None) 删除 base+sidecar
        sb.write_progress({"keep": 1})
        sb.write_win({"keep": 2})
        for p in (sb.progress_path + ".bak", sb.win_path + ".bak"):
            with io.open(p, "w", encoding="utf-8") as f:
                f.write("sidecar")
        sb.clear_fixture_sidecars()
        check(os.path.exists(sb.progress_path) and os.path.exists(sb.win_path),
              "clear_fixture_sidecars 保留 base 文件")
        check(not os.path.exists(sb.progress_path + ".bak")
              and not os.path.exists(sb.win_path + ".bak"),
              "clear_fixture_sidecars 清掉 sidecar")
        sb.reset(None, None)
        check(not os.path.exists(sb.progress_path)
              and not os.path.exists(sb.win_path),
              "reset(None,None) 删除 base + 恢复文件（不是只清 sidecar）")

        # 路径越界拒绝：mutated base 不能写/删真实记录
        saved_progress_path = sb.progress_path
        sb.progress_path = REAL_PROGRESS
        try:
            sb.write_progress({})
            check(False, "mutated progress_path 指向真实记录时 write_progress 被拒绝")
        except SandboxError:
            check(True, "mutated progress_path 越界被 SandboxError 拒绝")
        try:
            sb._clear_sidecars(REAL_PROGRESS)
            check(False, "_clear_sidecars 越界被拒绝")
        except SandboxError:
            check(True, "_clear_sidecars 越界被 SandboxError 拒绝")
        sb.progress_path = saved_progress_path
        check(sb.verify_real(), "路径越界拒绝后真实记录仍未变")

        # Card 只在 Sandbox 内构造
        card = sb.new_card(progress=fixture(), show=True)
        pump(10)
        check(card is not None and hasattr(card, "window_ctl"),
              "Sandbox 内 Card 构造成功")
        check(card._due_timer.isActive(), "Card 的 1s 到期 timer 运行中")
        check(card.window_ctl is not None, "Card 持有 window_ctl")
        # 退出会停 timer/window_ctl/关闭；这里提前 close 验证 closed 后回调
        card.close()
        pump(8)
        check(getattr(card, "_closed", False), "Card.close() 后 _closed=True")
        check(not card._due_timer.isActive(), "关闭后 _due_timer 已停")
        if card.window_ctl is not None:
            check(not card.window_ctl._hover_timer.isActive(),
                  "关闭后 window_ctl hover timer 已停")

        # 关闭后的迟到回调：必须仍写隔离路径，不写真实 DEFAULT 路径
        try:
            card.save(force=True)
        except Exception as e:
            check(False, "迟到 save(force=True) 异常：%r" % (e,))
        try:
            card._quiz_next()
        except Exception:
            pass
        try:
            card._check_due()
        except Exception:
            pass
        try:
            card._save_window(force=True)
        except Exception:
            pass
        check(sb.verify_real(), "关闭后迟到 save/_quiz_next/_check_due/_save_window 未写真实记录")
        check(os.path.abspath(sb.progress_path) == os.path.abspath(app_main.PROGRESS_PATH),
              "测试期间 main.PROGRESS_PATH 仍指向沙箱")
        check(os.path.abspath(sb.win_path) == os.path.abspath(app_main.WIN_PATH),
              "测试期间 main.WIN_PATH 仍指向沙箱")

        # 让 window save timer 挂起后再退出，验证退出前会停止/隔离
        card._window_save_timer.start(0)
        pump(4)
    except Exception:
        check(False, "真 app Sandbox/Card 场景异常：\n" + traceback.format_exc())
    finally:
        sb.__exit__(None, None, None)
        if card is not None:
            term = getattr(card, "_sandbox_terminal", {})
            check(term.get("closed") is True and term.get("closing") is False,
                  "Sandbox 退出强制 Card 终态 closed/closing")
            check(term.get("active_timers") == 0,
                  "Sandbox 退出后 Card 内 QTimer 全停（%r）" % (term.get("active_timers"),))
            check(term.get("visible") is False, "Sandbox 退出后 Card 已隐藏")
        check(os.path.abspath(app_main.PROGRESS_PATH) != os.path.abspath(sb.progress_path),
              "Sandbox 退出后 main.PROGRESS_PATH 已恢复")
        check(os.path.abspath(app_main.WIN_PATH) != os.path.abspath(sb.win_path),
              "Sandbox 退出后 main.WIN_PATH 已恢复")
        check(not sb.errors, "Sandbox 退出未发现真实记录变化：%r" % (sb.errors,))
    return sb


def ignored_close_probe():
    """注入 StorageError 让 closeEvent event.ignore，验证 Sandbox 仍强制终态。"""
    import main as app_main
    import storage
    from PyQt5.QtWidgets import QMessageBox

    sb = Sandbox(app_main, "ignored-close")
    sb.__enter__()
    card = None
    orig_critical = QMessageBox.critical
    try:
        QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
        card = sb.new_card(progress=fixture(), show=True)
        pump(10)

        def _boom(force=False):
            raise storage.StorageError("injected-save-failure")

        card.save = _boom
        card.close()
        pump(8)
        check(getattr(card, "_closed", False) is False,
              "注入 StorageError 后 close 被 event.ignore（_closed 仍 False）")
        check(card.isVisible(), "close 被忽略时窗口仍 visible（模拟真实风险）")
    except Exception:
        check(False, "ignored-close 场景异常：\n" + traceback.format_exc())
    finally:
        sb.__exit__(None, None, None)
        QMessageBox.critical = orig_critical
        term = getattr(card, "_sandbox_terminal", {}) if card is not None else {}
        check(term.get("closed") is True,
              "Sandbox 退出强制 _closed=True（即使 close 被 ignore）")
        check(term.get("closing") is False,
              "Sandbox 退出强制 _closing=False")
        check(term.get("visible") is False,
              "Sandbox 退出强制 hide 窗口（terminal visible=%r）" % (term.get("visible"),))
        check(term.get("active_timers") == 0,
              "Sandbox 退出后 Card 的 QTimer 全部停止（%r 个仍活）" %
              (term.get("active_timers"),))
        check(not sb.errors, "ignored-close 场景真实指纹未变：%r" % (sb.errors,))
    return sb


def main():
    try:
        fake_app_probe()
    except Exception:
        check(False, "假 app 指纹场景异常：\n" + traceback.format_exc())
    sb = None
    try:
        sb = real_app_probe()
    except Exception:
        check(False, "真 app 场景异常：\n" + traceback.format_exc())
    try:
        ignored_close_probe()
    except Exception:
        check(False, "ignored-close 退出场景异常：\n" + traceback.format_exc())
    # 报告写到 workspace 临时目录（不写 data/）
    root = _ensure_test_root()
    import tempfile
    outdir = tempfile.mkdtemp(prefix="sandbox-test-out-", dir=root)
    out.append("")
    if fails:
        out.append("失败 %d 项：%s" % (len(fails), " / ".join(fails)))
    else:
        out.append("全部通过 ✓")
    path = os.path.join(outdir, "test_ui_sandbox.txt")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
    print("REPORT", path)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
