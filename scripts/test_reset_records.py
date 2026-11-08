# -*- coding: utf-8 -*-
"""清空工具仅在工作区假安装/假资料目录测试；从不运行真实资料的清空入口。"""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
import storage
import reset_records as reset
from ui_test_support import fingerprint


class ResetTests(unittest.TestCase):
    def setUp(self):
        out = WORKSPACE / ".vocab-ui-tests"
        out.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="reset-", dir=str(out))).resolve()
        self.install = self.tmp / "install"
        (self.install / "app").mkdir(parents=True)
        (self.install / "scripts").mkdir()
        (self.install / "data").mkdir()
        (self.install / "app" / "main.py").write_text("# isolated marker\n", encoding="utf-8")
        self.bank = self.install / "data" / "bank.json"
        self.bank.write_bytes(b'{"fixture":true}')
        self.profile = self.tmp / "local" / "VocabApp"
        self.profile.mkdir(parents=True)
        self.env = patch.dict(os.environ, {
            "LOCALAPPDATA": str(self.tmp / "local"),
            "APPDATA": str(self.tmp / "roaming"), "USERPROFILE": str(self.tmp / "home"),
            "VOCABAPP_PYTHON": sys.executable, "PYTHONIOENCODING": "utf-8"})
        self.env.start()
        os.environ.pop("VOCABAPP_DATA_DIR", None)

    def tearDown(self):
        self.env.stop()
        target = self.tmp.resolve()
        assert target.parent == (WORKSPACE / ".vocab-ui-tests").resolve()
        assert target.name.startswith("reset-")
        shutil.rmtree(str(target))

    def seed(self):
        files = []
        for folder in (self.profile, self.install / "data"):
            for base in ("progress.json", "_win.json"):
                for suffix in ("", ".bak", ".tmp", ".tmp-fixture", ".bak.tmp-fixture"):
                    path = folder / (base + suffix)
                    path.write_text('{"fixture":1}', encoding="utf-8")
                    files.append(path)
            for name in ("books.json", "progress-copy.json", "_win.json.notes", "other.tmp", "future.json"):
                (folder / name).write_text("KEEP", encoding="utf-8")
        return files

    def copy_cli(self):
        for src, dest in ((ROOT / "scripts" / "reset_records.py", self.install / "scripts" / "reset_records.py"),
                          (ROOT / "app" / "storage.py", self.install / "app" / "storage.py"),
                          (ROOT / "清空使用记录.bat", self.install / "清空使用记录.bat")):
            shutil.copyfile(str(src), str(dest))

    def cli(self, args, input_text=""):
        self.copy_cli()
        source = self.tmp / "stdin.txt"
        output = self.tmp / "stdout.txt"
        source.write_text(input_text, encoding="utf-8")
        with source.open("rb") as stdin, output.open("wb") as stdout:
            result = subprocess.run([sys.executable, "-B", str(self.install / "scripts" / "reset_records.py"), *args],
                                    cwd=str(self.install), env=os.environ.copy(), stdin=stdin, stdout=stdout,
                                    stderr=subprocess.STDOUT, timeout=20)
        return result.returncode, output.read_text(encoding="utf-8", errors="replace")

    def test_confirmation_is_mandatory(self):
        files = self.seed()
        with self.assertRaises(reset.ResetError):
            reset.clear_records(self.install)
        self.assertTrue(all(path.exists() for path in files))

    def test_clears_primary_backup_unique_stages_and_legacy_only(self):
        files = self.seed()
        removed = reset.clear_records(self.install, confirmed=True)
        self.assertEqual(len(removed), 20)
        self.assertTrue(all(not path.exists() for path in files))
        self.assertEqual(self.bank.read_bytes(), b'{"fixture":true}')
        for folder in (self.profile, self.install / "data"):
            self.assertTrue(folder.is_dir())
            for name in ("books.json", "progress-copy.json", "_win.json.notes", "other.tmp", "future.json"):
                self.assertEqual((folder / name).read_text(encoding="utf-8"), "KEEP")

    def test_empty_profile_and_repeated_reset(self):
        self.assertEqual(reset.clear_records(self.install, confirmed=True), [])
        self.assertEqual(reset.clear_records(self.install, confirmed=True), [])
        self.assertFalse((self.profile / "vocab-app.lock").exists())

    def test_invalid_install_never_deletes(self):
        files = self.seed()
        with self.assertRaises(reset.ResetError):
            reset.clear_records(self.tmp / "not-an-install", confirmed=True)
        self.assertTrue(all(path.exists() for path in files))

    def test_running_application_lock_refuses_all_deletion(self):
        from PyQt5.QtCore import QLockFile
        files = self.seed()
        lock = QLockFile(str(self.profile / "vocab-app.lock"))
        lock.setStaleLockTime(0)
        self.assertTrue(lock.tryLock(0))
        try:
            with self.assertRaises(reset.ResetError):
                reset.clear_records(self.install, confirmed=True)
            self.assertTrue(all(path.exists() for path in files))
        finally:
            lock.unlock()

    def test_plugin_directory_first_and_readonly_fallbacks_are_fixture_local(self):
        with patch.dict(os.environ):
            os.environ.pop("VOCABAPP_DATA_DIR", None)
            self.assertEqual(reset.record_dirs(self.install)[0], self.install / "data")
            self.assertIn(self.profile, reset.record_dirs(self.install))
            with patch.object(storage, "_can_use_plugin", return_value=False):
                self.assertEqual(reset.record_dirs(self.install)[0], self.profile)
                os.environ.pop("LOCALAPPDATA", None)
                self.assertEqual(reset.record_dirs(self.install)[0], self.tmp / "roaming" / "VocabApp")
                os.environ.pop("APPDATA", None)
                self.assertEqual(reset.record_dirs(self.install)[0], self.tmp / "home" / "AppData" / "Local" / "VocabApp")

    def test_running_plugin_directory_lock_refuses_all_deletion(self):
        from PyQt5.QtCore import QLockFile
        files = self.seed()
        lock = QLockFile(str(self.install / "data" / "vocab-app.lock"))
        lock.setStaleLockTime(0)
        self.assertTrue(lock.tryLock(0))
        try:
            with self.assertRaises(reset.ResetError):
                reset.clear_records(self.install, confirmed=True)
            self.assertTrue(all(path.exists() for path in files))
        finally:
            lock.unlock()

    def test_cleared_old_backups_cannot_resurrect_on_next_load(self):
        self.seed()
        reset.clear_records(self.install, confirmed=True)
        sources = [os.path.join(directory, "progress.json")
                   for directory in storage.legacy_dirs(str(self.install))]
        target = storage.paths(str(self.install))[0]
        self.assertEqual(storage.load_json(target, {}, legacy_path=sources), {})
        self.assertFalse(Path(target).exists())

    def test_override_clears_only_selected_profile_not_default_or_legacy(self):
        protected = self.seed()
        before = {path: path.read_bytes() for path in protected}
        custom = self.tmp / "custom"
        custom.mkdir()
        target = custom / "progress.json"
        target.write_text('{"fixture":2}', encoding="utf-8")
        with patch.dict(os.environ, {"VOCABAPP_DATA_DIR": str(custom)}):
            removed = reset.clear_records(self.install, confirmed=True)
        self.assertEqual(removed, [str(target)])
        self.assertFalse(target.exists())
        self.assertEqual({path: path.read_bytes() for path in protected}, before)

    def test_record_named_directory_is_not_deleted(self):
        folder = self.profile / "progress.json"
        folder.mkdir()
        (folder / "keep").write_text("KEEP", encoding="utf-8")
        reset.clear_records(self.install, confirmed=True)
        self.assertTrue(folder.is_dir())
        self.assertEqual((folder / "keep").read_text(encoding="utf-8"), "KEEP")

    def test_file_link_is_refused_not_followed(self):
        protected = self.tmp / "protected.json"
        protected.write_text("KEEP", encoding="utf-8")
        link = self.profile / "progress.json"
        try:
            link.symlink_to(protected)
        except OSError as error:
            self.skipTest("当前Windows不允许创建测试链接：" + str(error))
        with self.assertRaises(reset.ResetError):
            reset.clear_records(self.install, confirmed=True)
        self.assertEqual(protected.read_text(encoding="utf-8"), "KEEP")

    def test_cli_dry_run_never_deletes(self):
        files = self.seed()
        code, out = self.cli(["--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertIn(str(self.profile), out)
        self.assertIn("20", out)
        self.assertTrue(all(path.exists() for path in files))

    def test_cli_cancel_never_deletes(self):
        files = self.seed()
        code, out = self.cli([], "cancel\n")
        self.assertEqual(code, 2, out)
        self.assertTrue(all(path.exists() for path in files))

    def test_cli_clear_explicit_confirmation(self):
        files = self.seed()
        code, out = self.cli([], "CLEAR\n")
        self.assertEqual(code, 0, out)
        self.assertTrue(all(not path.exists() for path in files))
        self.assertTrue(self.bank.exists())

    @unittest.skipUnless(os.name == "nt", "Windows batch entry")
    def test_batch_entry_fixture_only_explicit_yes(self):
        files = self.seed()
        self.copy_cli()
        source, output = self.tmp / "batch-in.txt", self.tmp / "batch-out.txt"
        source.write_bytes(b"CLEAR\r\n\r\n")
        with source.open("rb") as stdin, output.open("wb") as stdout:
            result = subprocess.run(["cmd.exe", "/d", "/c", str(self.install / "清空使用记录.bat"), "--yes"],
                                    cwd=str(self.install), env=os.environ.copy(), stdin=stdin, stdout=stdout,
                                    stderr=subprocess.STDOUT, timeout=20)
        self.assertEqual(result.returncode, 0, output.read_text(encoding="utf-8", errors="replace"))
        self.assertTrue(all(not path.exists() for path in files))
        self.assertTrue(self.bank.exists())


if __name__ == "__main__":
    protected = [*storage.paths(str(ROOT)), str(ROOT / "data" / "progress.json"), str(ROOT / "data" / "_win.json")]
    protected.extend(os.path.join(directory, name) for directory in storage.legacy_dirs(str(ROOT))
                     for name in ("progress.json", "_win.json"))
    before = fingerprint(protected)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ResetTests))
    safe = fingerprint(protected) == before
    print("REAL_RECORD_FINGERPRINT_UNCHANGED", safe)
    sys.exit(0 if result.wasSuccessful() and safe else 1)
