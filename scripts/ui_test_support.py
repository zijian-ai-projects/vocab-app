# -*- coding: utf-8 -*-
"""UI 测试沙箱（V1.3.0）。

所有 UI 自测都通过这里拿“隔离运行环境”：
  * progress.json / _win.json 写到临时目录，绝不碰用户真实记录；
  * 同时守护 legacy data/progress.json、data/_win.json 和
    app.DEFAULT_PROGRESS_PATH / DEFAULT_WIN_PATH（稳定记录目录）以及它们的
    .bak / .tmp / .tmp-* / .bak.tmp-* 恢复文件；
  * 进入沙箱时记录完整指纹；退出只校验、绝不覆盖/回滚/删除真实文件；
  * 测试结果 / 截图写到 workspace 的 .vocab-ui-tests，不写 data/；
  * 退出前先停掉所有 QTimer + window_ctl、关闭所有 Card 并 drain 事件，
    最后才恢复 main 的全局路径，避免迟到回调写真实记录；
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


def _related_paths(base):
    """一个记录文件 + storage 可能留下的 .bak/.tmp/唯一 temp 恢复文件。"""
    base = os.path.abspath(base)
    out = {base, base + ".bak", base + ".tmp"}
    directory = os.path.dirname(base)
    name = os.path.basename(base)
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        names = []
    except OSError as e:
        raise SandboxError("无法列出真实记录目录 %s：%r" % (directory, e))
    for fn in names:
        if fn.startswith(name + ".tmp-") or fn.startswith(name + ".bak.tmp-"):
            out.add(os.path.join(directory, fn))
    return out


def fingerprint(bases):
    """{path: bytes|None}；同时覆盖尚不存在的路径，创建新文件也能被发现。"""
    result = {}
    seen = set()
    for base in bases:
        if not base:
            continue
        base = os.path.abspath(base)
        if base in seen:
            continue
        seen.add(base)
        for path in _related_paths(base):
            result[path] = _snapshot(path)
    return result


def _fingerprint_changes(before, after):
    changed = []
    for path in sorted(set(before) | set(after)):
        if before.get(path, "<missing>") != after.get(path, "<missing>"):
            changed.append(path)
    return changed


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
        self._root = os.path.realpath(self.dir)
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
        self._real_bases = []
        self.watch_paths = []
        self._entered = False

    # ---------- 上下文 ----------
    def __enter__(self):
        self._entered = True
        # 真实记录：插件 data/* 目标 + 所有旧稳定资料目录的迁移来源。
        legacy_p = getattr(self.app, "LEGACY_PROGRESS_PATH", REAL_PROGRESS)
        legacy_w = getattr(self.app, "LEGACY_WIN_PATH", REAL_WIN)
        stable_p = getattr(self.app, "DEFAULT_PROGRESS_PATH",
                           getattr(self.app, "PROGRESS_PATH", REAL_PROGRESS))
        stable_w = getattr(self.app, "DEFAULT_WIN_PATH",
                           getattr(self.app, "WIN_PATH", REAL_WIN))
        self._real_bases = [legacy_p, legacy_w, stable_p, stable_w]
        self._real_bases.extend(getattr(self.app, "LEGACY_PROGRESS_PATHS", ()))
        self._real_bases.extend(getattr(self.app, "LEGACY_WIN_PATHS", ()))
        self.watch_paths = sorted(fingerprint(self._real_bases))
        self._real = fingerprint(self._real_bases)

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
        # 1) 仍在隔离路径下：停 timer/controller、close、强制 terminal 清理、drain。
        for w in list(self.cards):
            self._stop_card(w)
            try:
                w.close()
            except Exception:
                pass
        # close 可能因 StorageError 被 event.ignore：无论成功失败，强制终态，
        # 保证迟到 timer/键盘/direct action 的 _can_act 全为 False，且窗口隐藏。
        for w in list(self.cards):
            self._force_terminal(w)
        try:
            from PyQt5.QtCore import QCoreApplication, QEvent
            app = QCoreApplication.instance()
            if app is not None:
                for _ in range(8):
                    app.processEvents()
                app.sendPostedEvents(None, QEvent.DeferredDelete)
                for _ in range(8):
                    app.processEvents()
        except Exception:
            pass
        # 再停一次（closeEvent 失败恢复分支可能重启 timer）
        for w in list(self.cards):
            self._stop_card(w)

        # 2) 再恢复 main 的全局路径
        if self._orig_progress is not None:
            self.app.PROGRESS_PATH = self._orig_progress
        if self._had_win_attr:
            self.app.WIN_PATH = self._orig_win_attr
        if self._orig_resize is not None:
            self.app.Card.resizeEvent = self._orig_resize
        self.cards = []

        # 3) 只校验真实文件（legacy + stable + 恢复文件），绝不覆盖/回滚
        self.verify_real()
        if not self.keep:
            self._safe_rmtree(self._root)
        else:
            print("KEEP sandbox:", self._root)
        return False

    def _stop_card(self, w):
        try:
            from PyQt5.QtCore import QTimer
            for timer in w.findChildren(QTimer):
                timer.stop()
            ctl = getattr(w, "window_ctl", None)
            if ctl is not None:
                ctl.stop_timers()
        except Exception:
            pass

    def _force_terminal(self, w):
        """close 被 event.ignore 也强制进入 closed，隐藏并 deleteLater；记录终态。"""
        self._stop_card(w)
        try:
            w._closing = False
            w._closed = True
        except Exception:
            pass
        try:
            w.hide()
        except Exception:
            pass
        self._stop_card(w)
        visible = False
        active = 0
        try:
            visible = bool(w.isVisible())
            from PyQt5.QtCore import QTimer
            active = sum(1 for timer in w.findChildren(QTimer) if timer.isActive())
        except Exception:
            pass
        try:
            w._sandbox_terminal = {
                "closed": bool(getattr(w, "_closed", False)),
                "closing": bool(getattr(w, "_closing", False)),
                "visible": visible,
                "active_timers": active,
            }
        except Exception:
            pass
        try:
            w.deleteLater()
        except Exception:
            pass

    def _safe_rmtree(self, path):
        """只删原始 mkdtemp 沙箱；绝不接受被改写的 self.dir/任意子路径。"""
        root = os.path.realpath(path)
        original = os.path.realpath(self._root)
        base = os.path.realpath(TEST_ROOT)
        try:
            inside_test_root = os.path.commonpath([base, root]) == base and root != base
        except ValueError:
            inside_test_root = False
        if root != original or not inside_test_root:
            self.errors.append("拒绝删除非原始沙箱路径：%s（原始 %s）" % (root, original))
            return
        shutil.rmtree(root, ignore_errors=True)

    def _fixture_target(self, path):
        """校验夹具文件只能落在 self 原始 mkdtemp 目录内；防 mutated base 越界。"""
        root = os.path.realpath(self._root)
        target = os.path.realpath(os.path.abspath(path))
        try:
            inside = (os.path.commonpath([root, target]) == root
                      and target != root)
        except ValueError:
            inside = False
        if not inside:
            raise SandboxError("拒绝访问沙箱外夹具路径：%s（沙箱 %s）" % (target, root))
        return target

    def verify_real(self):
        """校验真实记录与恢复文件；只报告，不写/不恢复。"""
        try:
            now = fingerprint(self._real_bases)
        except Exception as e:
            self.errors.append("无法校验真实记录指纹：%r" % (e,))
            return False
        changed = _fingerprint_changes(self._real, now)
        if changed:
            self.errors.append("真实记录/恢复文件发生变化（未覆盖）：%s" %
                               " ; ".join(changed[:8]))
            return False
        return True

    def _clear_sidecars(self, base):
        """只清沙箱内该记录文件的 .bak/.tmp/唯一 temp，不删 base，绝不碰真实目录。"""
        base = self._fixture_target(base)
        for path in _related_paths(base):
            real = self._fixture_target(path)
            if real == base:
                continue
            try:
                if os.path.isfile(real):
                    os.remove(real)
            except OSError:
                pass

    # ---------- 沙箱内数据 ----------
    def path(self, name):
        return os.path.join(self._root, name)

    def out(self, name):
        os.makedirs(self.outdir, exist_ok=True)
        return os.path.join(self.outdir, name)

    def shot(self, name):
        if not name.endswith(".png"):
            name += ".png"
        return self.out(name)

    def write_progress(self, data):
        target = self._fixture_target(self.progress_path)
        self._clear_sidecars(target)
        if data is None:
            try:
                os.remove(target)
            except OSError:
                pass
            return
        with io.open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def read_progress(self):
        target = self._fixture_target(self.progress_path)
        try:
            with io.open(target, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return {}

    def write_win(self, data):
        target = self._fixture_target(self.win_path)
        self._clear_sidecars(target)
        if data is None:
            try:
                os.remove(target)
            except OSError:
                pass
            return
        with io.open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def read_win(self):
        target = self._fixture_target(self.win_path)
        try:
            with io.open(target, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return {}

    def clear_fixture_sidecars(self):
        """只清夹具的 .bak/.tmp/唯一 temp，保留 base 文件。"""
        self._clear_sidecars(self.progress_path)
        self._clear_sidecars(self.win_path)

    def reset(self, progress=None, win=None):
        """重置夹具：None 表示删除该 base + 全部恢复文件；非 None 表示写入。

        不是“只清 sidecar”；只清 sidecar 请用 clear_fixture_sidecars()。
        所有路径都限定在原始 mkdtemp 沙箱内，绝不触碰真实记录。
        """
        self.write_progress(progress)
        self.write_win(win)

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
