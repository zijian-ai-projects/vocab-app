# -*- coding: utf-8 -*-
"""UI 测试沙箱（V1.2.1）。

所有 UI 自测都通过这里拿“隔离运行环境”：
  * progress.json / _win.json 写到临时目录，绝不碰用户真实的 data/ 文件；
  * 测试结果 / 截图写到独立的临时输出目录，打印路径，不写 data/；
  * 进入沙箱时读取真实 progress/_win 的快照仅供校验；发现变化报错，绝不覆盖或回滚；
  * 退出码：调用 finish 的脚本失败时 exit 非 0。

用法（必须在 import PyQt5 之前调用 configure_qt）：
    from ui_test_support import configure_qt, Sandbox, set_nottest, new_app
    configure_qt("offscreen")          # 逻辑测试；check_compact 不调用 = 原生窗口（真实字体）
    from PyQt5.QtWidgets import QApplication
    import main as app_main
    with Sandbox(app_main, "smoke") as sb:
        w = sb.new_card(show=True)
        ...
    sys.exit(sb.finish(out, fails))    # 先退出沙箱完成校验，再写报告 / 设置退出码
"""
import os
import sys
import io
import json
import shutil
import tempfile

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(APP_ROOT)
if os.path.join(APP_ROOT, "app") not in sys.path:
    sys.path.insert(0, os.path.join(APP_ROOT, "app"))

# 工作区内的测试临时根目录：不写 vocab-app/data，也不往用户 temp 目录外扩
TEST_ROOT = os.path.join(WORKSPACE, ".vocab-ui-tests")


# 这些是用户真实数据，任何测试都不能删/改
REAL_PROGRESS = os.path.join(APP_ROOT, "data", "progress.json")
REAL_WIN = os.path.join(APP_ROOT, "data", "_win.json")


def configure_qt(platform=None):
    """设置 Qt 平台。逻辑测试用 offscreen（不弹窗）；check_compact 不调用（要真实字体）。"""
    if platform:
        os.environ.setdefault("QT_QPA_PLATFORM", platform)


def set_nottest(on=True):
    """只控制 main.py 的周期测试屏蔽（--nottest）；不影响首次引导。"""
    has = "--nottest" in sys.argv
    if on and not has:
        sys.argv.append("--nottest")
    elif not on and has:
        sys.argv.remove("--nottest")


def new_app(argv=None):
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    return app


class SandboxError(RuntimeError):
    pass


def _snapshot(path):
    try:
        with io.open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise SandboxError("无法读取 %s：%r" % (path, e))


class Sandbox:
    def __init__(self, app_main, label="ui"):
        self.app = app_main
        self.label = label
        keep = os.environ.get("VOCAB_TEST_KEEP", "") == "1"
        self.keep = keep
        try:
            os.makedirs(TEST_ROOT, exist_ok=True)
        except OSError:
            pass
        self.dir = tempfile.mkdtemp(prefix="%s-sandbox-" % label, dir=TEST_ROOT)
        out_env = os.environ.get("VOCAB_TEST_OUT")
        if out_env:
            self.outdir = out_env
        else:
            self.outdir = tempfile.mkdtemp(prefix="%s-out-" % label, dir=TEST_ROOT)
        try:
            os.makedirs(self.outdir, exist_ok=True)
        except OSError:
            pass
        self.progress_path = os.path.join(self.dir, "progress.json")
        self.win_path = os.path.join(self.dir, "_win.json")
        self.cards = []
        self.errors = []
        self._orig_progress = None
        self._orig_win_attr = None
        self._orig_resize = None
        self._real = {}
        self._entered = False

    # ---------- 上下文 ----------
    def __enter__(self):
        self._entered = True
        self._real = {"progress": _snapshot(REAL_PROGRESS), "win": _snapshot(REAL_WIN)}
        self._orig_progress = self.app.PROGRESS_PATH
        self.app.PROGRESS_PATH = self.progress_path
        # 优先用 main.py 暴露的 WIN_PATH；没有就替换 Card.resizeEvent（它原本写真实 data/_win.json）
        self._had_win_attr = hasattr(self.app, "WIN_PATH")
        self._orig_win_attr = getattr(self.app, "WIN_PATH", None)
        if self._had_win_attr:
            self.app.WIN_PATH = self.win_path
        else:
            from PyQt5.QtWidgets import QWidget
            sb = self

            def _resize(widget, ev):
                QWidget.resizeEvent(widget, ev)
                try:
                    json.dump({"x": widget.x(), "y": widget.y(),
                               "w": widget.width(), "h": widget.height()},
                              io.open(sb.win_path, "w"))
                except Exception:
                    pass
            self._orig_resize = self.app.Card.resizeEvent
            self.app.Card.resizeEvent = _resize
        return self

    def __exit__(self, exc_type, exc, tb):
        # 先在隔离路径仍然生效时停掉定时器、关窗、drain 事件；
        # 之后再还原全局路径，避免迟到的 resize/quiz 写到真实 data。
        for w in list(self.cards):
            try:
                w.quiz_timer.stop()
            except Exception:
                pass
            try:
                w.close()
            except Exception:
                pass
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                for _ in range(6):
                    app.processEvents()
        except Exception:
            pass
        # 恢复 main.py 的全局路径
        if self._orig_progress is not None:
            self.app.PROGRESS_PATH = self._orig_progress
        if self._had_win_attr:
            self.app.WIN_PATH = self._orig_win_attr
        if self._orig_resize is not None:
            self.app.Card.resizeEvent = self._orig_resize
        self.cards = []
        # 只校验真实数据：用户可能在测试期间正常学习，绝不能擅自覆盖/删除
        self._verify_real(REAL_PROGRESS, "progress", "data/progress.json")
        self._verify_real(REAL_WIN, "win", "data/_win.json")
        if not self.keep:
            shutil.rmtree(self.dir, ignore_errors=True)
        else:
            print("KEEP sandbox:", self.dir)
        return False

    def _verify_real(self, path, key, label):
        try:
            now = _snapshot(path)
        except Exception as e:
            self.errors.append("无法校验真实 %s：%r" % (label, e))
            return
        if now != self._real.get(key):
            self.errors.append("真实 %s 在测试期间发生变化（未覆盖，请确认是否有其它进程在写）" % label)

    # ---------- 沙箱内数据 ----------
    def path(self, name):
        return os.path.join(self.dir, name)

    def out(self, name):
        os.makedirs(self.outdir, exist_ok=True)
        return os.path.join(self.outdir, name)

    def shot(self, name):
        if not name.endswith(".png"):
            name += ".png"
        return self.out(name)

    def write_progress(self, data):
        if data is None:
            try:
                os.remove(self.progress_path)
            except OSError:
                pass
            return
        with io.open(self.progress_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def read_progress(self):
        try:
            with io.open(self.progress_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return {}

    def new_card(self, progress=None, show=True):
        """创建 Card。show=False 时拦截 __init__ 末尾的 show()，用于检查 show 前状态。"""
        if progress is not None:
            self.write_progress(progress)
        from PyQt5.QtWidgets import QWidget
        Card = self.app.Card
        own_show = Card.__dict__.get("show")
        # QWidget.show 是继承来的描述符，直接赋回类会变成 unbound；用删除恢复继承
        self._orig_show = QWidget.show

        def _show(widget):
            if not getattr(widget, "_test_show_called", False):
                widget._test_show_called = True
                # 记录“第一次 show 的瞬间”状态，供启动不闪学习页断言
                widget._test_first_show_mode = getattr(widget, "mode", None)
                widget._test_first_show_book = getattr(widget, "book_id", None)
                widget._test_first_show_queue_len = len(getattr(widget, "queue", []) or [])
                widget._test_first_show_queue_words_len = len(
                    getattr(widget, "queue_words", []) or [])
            if show:
                QWidget.show(widget)

        Card.show = _show
        try:
            w = Card()
        finally:
            if own_show is not None:
                Card.show = own_show
            else:
                try:
                    delattr(Card, "show")
                except AttributeError:
                    pass
        w._test_show_deferred = not show
        w._test_show_called = getattr(w, "_test_show_called", False)
        w._test_first_show_mode = getattr(w, "_test_first_show_mode", getattr(w, "mode", None))
        w._test_first_show_book = getattr(w, "_test_first_show_book", getattr(w, "book_id", None))
        w._test_first_show_queue_len = getattr(w, "_test_first_show_queue_len", 0)
        w._test_first_show_queue_words_len = getattr(
            w, "_test_first_show_queue_words_len", 0)
        self.cards.append(w)
        return w

    def show(self, w):
        from PyQt5.QtWidgets import QWidget
        QWidget.show(w)
        w._test_show_deferred = False

    def pump(self, app=None, n=8):
        app = app or new_app()
        for _ in range(n):
            app.processEvents()

    def finish(self, out, fails, filename="report.txt"):
        """写 UTF-8 报告；返回进程退出码（0/1）。"""
        lines = list(out)
        errs = list(self.errors)
        total_fails = len(fails) + len(errs)
        lines.append("")
        if total_fails:
            lines.append("失败 %d 项：%s" % (total_fails, " / ".join(list(fails) + errs)))
        else:
            lines.append("全部通过 ✓")
        path = self.out(filename)
        with io.open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("WROTE %d LINES; FAILS %d" % (len(lines), total_fails))
        print("REPORT", path)
        return 1 if total_fails else 0
