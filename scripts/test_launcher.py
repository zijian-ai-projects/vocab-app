# -*- coding: utf-8 -*-
"""启动链自检：bootstrap 的 Qt 路径、日志、失败提示与 VBS 启动参数。

只测纯函数/静态文件，不启动真实应用、不读写真实学习记录：
* Qt DLL 目录只读查找，临时目录里放假的 Qt5Core_conda.dll；
* 日志写到临时资料目录（VOCABAPP_DATA_DIR），不碰默认目录；
* 真实 main 用假模块替换，对话框用 _show_message_box 注入替代。
"""
import io
import os
import sys
import types
import unittest
import tempfile
import shutil

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(APP, "app")
VBS = os.path.join(APP, "启动背单词.vbs")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import launcher


class QtPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="launcher-qt-")
        self.fake = os.path.join(self.tmp, "qtbin")
        os.makedirs(self.fake)
        self.old_dirs = launcher.qt_dll_dirs
        self.old_path = os.environ.get("PATH", "")
        self.old_box = launcher._show_message_box

    def tearDown(self):
        launcher.qt_dll_dirs = self.old_dirs
        os.environ["PATH"] = self.old_path
        launcher._show_message_box = self.old_box
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_conda_library_bin_is_always_probed(self):
        dirs = [os.path.normcase(os.path.abspath(p)) for p in launcher.qt_dll_dirs()]
        expected = os.path.normcase(os.path.join(sys.prefix, "Library", "bin"))
        self.assertIn(expected, dirs)

    def test_find_qt_dll_dir_requires_real_file(self):
        launcher.qt_dll_dirs = lambda: [self.tmp, self.fake]
        self.assertIsNone(launcher.find_qt_dll_dir())
        with open(os.path.join(self.fake, "Qt5Core_conda.dll"), "wb") as stream:
            stream.write(b"MZ")
        self.assertEqual(os.path.abspath(launcher.find_qt_dll_dir()),
                         os.path.abspath(self.fake))

    def test_metric_wheel_directory_is_probed(self):
        wheel = os.path.join(sys.prefix, "Lib", "site-packages", "PyQt5", "Qt", "bin")
        self.assertIn(os.path.normcase(os.path.abspath(wheel)),
                      [os.path.normcase(os.path.abspath(p)) for p in launcher.qt_dll_dirs()])

    def test_ensure_prepends_once_and_is_idempotent(self):
        with open(os.path.join(self.fake, "Qt5Core_conda.dll"), "wb") as stream:
            stream.write(b"MZ")
        launcher.qt_dll_dirs = lambda: [self.fake]
        os.environ["PATH"] = r"C:\Windows\System32"
        added = launcher.ensure_qt_on_path()
        self.assertEqual(os.path.abspath(added), os.path.abspath(self.fake))
        parts = os.environ["PATH"].split(os.pathsep)
        self.assertEqual(os.path.normcase(os.path.abspath(parts[0])),
                         os.path.normcase(os.path.abspath(self.fake)))
        self.assertIn(r"C:\Windows\System32", parts)
        before = os.environ["PATH"]
        self.assertIsNone(launcher.ensure_qt_on_path())
        self.assertEqual(os.environ["PATH"], before)

    def test_ensure_does_nothing_when_dll_missing(self):
        launcher.qt_dll_dirs = lambda: [self.fake]
        os.environ["PATH"] = r"C:\Windows"
        self.assertIsNone(launcher.ensure_qt_on_path())
        self.assertEqual(os.environ["PATH"], r"C:\Windows")
        self.assertEqual(os.listdir(self.fake), [])      # 只读查找，不创建任何文件


class LogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="launcher-log-")
        self.old_dir = os.environ.get("VOCABAPP_DATA_DIR")
        os.environ["VOCABAPP_DATA_DIR"] = os.path.join(self.tmp, "profile")

    def tearDown(self):
        if self.old_dir is None:
            os.environ.pop("VOCABAPP_DATA_DIR", None)
        else:
            os.environ["VOCABAPP_DATA_DIR"] = self.old_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_path_uses_profile_override_and_does_not_create(self):
        path = launcher.log_file()
        self.assertEqual(path, os.path.join(self.tmp, "profile", "startup.log"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "profile")))

    def test_default_log_path_uses_plugin_data_without_creating_directories(self):
        from unittest.mock import patch
        install = os.path.join(self.tmp, "isolated-install")
        with patch.object(launcher, "ROOT", install), patch.dict(os.environ):
            os.environ.pop("VOCABAPP_DATA_DIR", None)
            self.assertEqual(launcher.log_file(), os.path.join(install, "data", "startup.log"))
            self.assertFalse(os.path.exists(install))

    def test_write_log_creates_profile_and_appends(self):
        launcher.write_log("第一行")
        launcher.write_log("second")
        path = launcher.log_file()
        with io.open(path, encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("第一行", text)
        self.assertIn("second", text)
        self.assertEqual(text.count("\n"), 2)

    def test_write_log_trims_oversized_history(self):
        launcher.write_log("x" * (launcher.MAX_LOG_BYTES + 5000))
        launcher.write_log("tail-marker")
        size = os.path.getsize(launcher.log_file())
        self.assertLess(size, launcher.MAX_LOG_BYTES + 5000)
        with io.open(launcher.log_file(), encoding="utf-8", errors="replace") as stream:
            text = stream.read()
        self.assertIn("[log truncated]", text)
        self.assertIn("tail-marker", text)

    def test_write_log_never_raises_on_unwritable_target(self):
        os.environ["VOCABAPP_DATA_DIR"] = os.path.join(self.tmp, "blocked")
        os.makedirs(os.environ["VOCABAPP_DATA_DIR"])
        target = launcher.log_file()
        os.makedirs(target)          # 同名目录，写入必然失败
        self.assertEqual(launcher.write_log("boom"), target)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="launcher-run-")
        self.old_dir = os.environ.get("VOCABAPP_DATA_DIR")
        os.environ["VOCABAPP_DATA_DIR"] = os.path.join(self.tmp, "profile")
        self.old_main = sys.modules.get("main")
        self.old_ensure = launcher.ensure_qt_on_path
        self.old_box = launcher._show_message_box
        self.alerts = []
        launcher.ensure_qt_on_path = lambda: None
        launcher._show_message_box = lambda title, text: self.alerts.append((title, text))

    def tearDown(self):
        launcher.ensure_qt_on_path = self.old_ensure
        launcher._show_message_box = self.old_box
        if self.old_main is None:
            sys.modules.pop("main", None)
        else:
            sys.modules["main"] = self.old_main
        if self.old_dir is None:
            os.environ.pop("VOCABAPP_DATA_DIR", None)
        else:
            os.environ["VOCABAPP_DATA_DIR"] = self.old_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_main(self, behavior):
        module = types.ModuleType("main")
        module.VERSION = "9.9.9"
        module.main = behavior
        sys.modules["main"] = module
        return module

    def log_text(self):
        path = launcher.log_file()
        if not os.path.isfile(path):
            return ""
        with io.open(path, encoding="utf-8", errors="replace") as stream:
            return stream.read()

    def test_success_returns_zero_and_logs_start_and_exit(self):
        self.fake_main(lambda: None)
        self.assertEqual(launcher.run([]), 0)
        text = self.log_text()
        self.assertIn("start version=9.9.9", text)
        self.assertIn("exit code=0", text)
        self.assertEqual(self.alerts, [])

    def test_system_exit_code_is_returned_without_extra_dialog(self):
        def behavior():
            raise SystemExit(3)
        self.fake_main(behavior)
        self.assertEqual(launcher.run([]), 3)
        self.assertIn("exit code=3", self.log_text())
        self.assertEqual(self.alerts, [])

    def test_unexpected_failure_shows_visible_error_and_traceback(self):
        def behavior():
            raise RuntimeError("boom-launcher")
        self.fake_main(behavior)
        self.assertEqual(launcher.run([]), 1)
        text = self.log_text()
        self.assertIn("FAILED", text)
        self.assertIn("RuntimeError: boom-launcher", text)
        self.assertEqual(len(self.alerts), 1)
        title, message = self.alerts[0]
        self.assertEqual(title, "背单词启动失败")
        self.assertIn("学习记录没有清空", message)
        self.assertIn("startup.log", message)

    def test_missing_qt_import_error_is_reported(self):
        def behavior():
            raise ImportError("unable to find Qt5Core.dll on PATH")
        self.fake_main(behavior)
        self.assertEqual(launcher.run([]), 1)
        self.assertIn("ImportError", self.log_text())
        self.assertIn("unable to find Qt5Core.dll on PATH", self.alerts[0][1])


class VbsTests(unittest.TestCase):
    def setUp(self):
        with open(VBS, "rb") as stream:
            self.raw = stream.read()
        self.text = self.raw.decode("utf-16")

    def test_vbs_is_unicode_with_bom(self):
        self.assertTrue(self.raw.startswith(b"\xff\xfe"))
        self.assertIn("背单词", self.text)

    def test_vbs_uses_visible_window_style(self):
        self.assertIn("sh.Run(cmd, 1, True)", self.text)
        self.assertNotIn("sh.Run(cmd, 0,", self.text)
        self.assertNotIn(", 0, False)", self.text)

    def test_vbs_starts_through_bootstrap_not_main(self):
        self.assertIn(r"\app\launcher.py", self.text)
        self.assertNotIn(r"\app\main.py", self.text)

    def test_vbs_reports_failure_with_log_path(self):
        self.assertIn("背单词没能正常启动", self.text)
        self.assertIn("startup.log", self.text)
        self.assertIn("学习记录没有清空", self.text)
        self.assertIn("WScript.Quit code", self.text)

    def test_vbs_log_hint_uses_plugin_data_or_explicit_override(self):
        self.assertIn(r'here & "\data\startup.log"', self.text)
        self.assertIn("%VOCABAPP_DATA_DIR%", self.text)
        self.assertNotIn(r"\VocabApp\startup.log", self.text)

    def test_vbs_checks_missing_interpreter_and_launcher(self):
        self.assertIn("找不到启动文件", self.text)
        self.assertIn("找不到 Python", self.text)
        self.assertIn("pythonw.exe", self.text)


class IsolationTests(unittest.TestCase):
    def test_launcher_import_pulls_in_no_qt_and_no_app_main(self):
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); import launcher; "
                "print('PyQt5' in sys.modules, 'main' in sys.modules)" % APP_DIR)
        out = subprocess.check_output([sys.executable, "-B", "-c", code], text=True)
        self.assertEqual(out.strip(), "False False")


if __name__ == "__main__":
    unittest.main(verbosity=2)
