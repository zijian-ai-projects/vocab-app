# -*- coding: utf-8 -*-
"""V1.3 本地存储回归测试；不导入/运行 main，不读取真实用户记录。

直接运行：python -B scripts/test_storage.py
全部 JSON 和环境目录都位于已验证的 platform temporary fixture 内。
清理前再次验证 fixture 的绝对位置；不生成 data/ 测试报告或 __pycache__。
"""
import copy
import errno
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from unittest import mock

sys.dont_write_bytecode = True
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(APP_ROOT, "app")
STORAGE_PATH = os.path.join(APP_DIR, "storage.py")
sys.path.insert(0, APP_DIR)
import storage


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temp_parent = os.path.realpath(tempfile.gettempdir())
        self.fixture = os.path.realpath(tempfile.mkdtemp(
            prefix="vocab-storage-tests-", dir=self.temp_parent))
        self._verify_fixture_root()
        self.addCleanup(self._cleanup_fixture)
        self.target = self.fixture_path("current", "progress.json")
        self.plugin = self.fixture_path("plugin")
        plugin_patch = mock.patch.object(storage, "_plugin_root", side_effect=lambda root=None:
                                          storage._absolute(root if root is not None else self.plugin))
        plugin_patch.start()
        self.addCleanup(plugin_patch.stop)
        self.legacy = self.fixture_path("v1.2.1", "data", "progress.json")
        self.payload = {
            "history": [{"t": 1700000000, "vocab": 1234, "baseline": True,
                         "answers": [{"word": "apple", "known": True}]}],
            "states": {"apple": {"st": "learning", "due": 1712345678,
                                 "lv": 4, "custom": {"preserve": "苹果"}}},
            "book": "series:fixture:version-one",
            "cursors": {"fixture-book": 17},
            "orders": {"fixture-book": {"mode": "seq", "seed": 123}},
            "theta": 0.5,
            "future_field": {"nested": [1, None, {"unicode": "未知字段"}]},
        }
        self.environment = {
            "VOCABAPP_DATA_DIR": self.fixture_path("current"),
            "LOCALAPPDATA": self.fixture_path("fake-localappdata"),
            "APPDATA": self.fixture_path("fake-appdata"),
            "HOME": self.fixture_path("fake-home"),
            "USERPROFILE": self.fixture_path("fake-home"),
        }
        env_patch = mock.patch.dict(os.environ, self.environment, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        # fail closed：即使实现回归错误，也不能读/扫描真实 root/data 或用户目录。
        self.read_document = storage._read_document
        self.recovery_candidates = storage._recovery_candidates
        read_patch = mock.patch.object(storage, "_read_document",
                                       side_effect=self._checked_read)
        scan_patch = mock.patch.object(storage, "_recovery_candidates",
                                       side_effect=self._checked_candidates)
        read_patch.start()
        scan_patch.start()
        self.addCleanup(read_patch.stop)
        self.addCleanup(scan_patch.stop)

    def _verify_fixture_root(self):
        absolute = os.path.realpath(self.fixture)
        if (not os.path.isabs(absolute) or absolute != self.fixture
                or os.path.normcase(os.path.dirname(absolute))
                != os.path.normcase(self.temp_parent)
                or not os.path.basename(absolute).startswith("vocab-storage-tests-")
                or os.path.islink(self.fixture)):
            raise AssertionError("Refusing unexpected fixture root: %r" % absolute)

    def assert_fixture_path(self, path):
        absolute = os.path.realpath(os.fspath(path))
        if (not os.path.isabs(absolute)
                or os.path.normcase(os.path.commonpath([absolute, self.fixture]))
                != os.path.normcase(self.fixture)):
            raise AssertionError("Refusing access outside fixture: %r" % absolute)
        return absolute

    def fixture_path(self, *parts):
        return self.assert_fixture_path(os.path.join(self.fixture, *parts))

    def _cleanup_fixture(self):
        # 任何 delete 前验证真实绝对根、父目录、唯一前缀和非符号链接。
        self._verify_fixture_root()
        shutil.rmtree(self.fixture)

    def remove_fixture_file(self, path):
        absolute = self.assert_fixture_path(path)
        if absolute == self.fixture:
            raise AssertionError("Refusing to remove fixture root as a file")
        os.remove(absolute)

    def _checked_read(self, path):
        self.assert_fixture_path(path)
        return self.read_document(path)

    def _checked_candidates(self, path):
        self.assert_fixture_path(path)
        return self.recovery_candidates(path)

    def write_bytes(self, path, raw):
        path = self.assert_fixture_path(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(raw)

    def write_json(self, path, data):
        self.write_bytes(path, (json.dumps(data, ensure_ascii=False)
                                + "\n").encode("utf-8"))

    def read_bytes(self, path):
        path = self.assert_fixture_path(path)
        with open(path, "rb") as stream:
            return stream.read()

    def read_json(self, path):
        return json.loads(self.read_bytes(path).decode("utf-8-sig"))

    def caught_load(self, path=None, **kwargs):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", storage.StorageWarning)
            result = storage.load_json(path or self.target, **kwargs)
        return result, caught

    def save(self, data, path=None):
        path = self.assert_fixture_path(path or self.target)
        return storage.atomic_save(path, data)

    def stages(self, path=None):
        target = path or self.target
        directory = self.assert_fixture_path(os.path.dirname(target))
        if not os.path.isdir(directory):
            return []
        prefix = os.path.basename(target) + ".tmp-"
        return [os.path.join(directory, name) for name in os.listdir(directory)
                if name.startswith(prefix)]


class PathTests(FixtureCase):
    def test_writable_plugin_data_has_priority_over_user_directories(self):
        os.makedirs(self.plugin)
        os.environ.pop("VOCABAPP_DATA_DIR")
        expected = os.path.join(self.plugin, "data")
        self.assertEqual(storage.data_dir(self.plugin), expected)
        self.assertEqual(storage.paths(self.plugin),
                         (os.path.join(expected, "progress.json"),
                          os.path.join(expected, "_win.json")))
        self.assertEqual(storage.paths(), storage.paths(self.plugin))
        self.assertFalse(os.path.exists(expected))
        self.assertEqual(os.listdir(self.plugin), [])

    def test_missing_plugin_uses_writable_ancestor_without_creating_directories(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        plugin = self.fixture_path("future", "plugin")
        self.assertEqual(storage.data_dir(plugin), os.path.join(plugin, "data"))
        self.assertFalse(os.path.exists(os.path.dirname(plugin)))

    def test_plugin_directory_upgrade_does_not_change_existing_records(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        target = os.path.join(self.plugin, "data", "progress.json")
        self.write_json(target, self.payload)
        before = self.read_bytes(target)
        for _ in range(3):
            self.assertEqual(storage.paths(self.plugin)[0], target)
            self.assertEqual(storage.load_json(target), self.payload)
            self.assertEqual(self.read_bytes(target), before)
        self.assertFalse(os.path.exists(target + ".bak"))

    def test_metadata_permission_denial_does_not_treat_root_as_missing(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        with mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage.os, "stat", side_effect=PermissionError("ACL denied")):
            self.assertEqual(storage.data_dir(self.plugin),
                             self.fixture_path("fake-localappdata", "VocabApp"))

    def test_writable_plugin_with_no_old_home_has_no_legacy_directories(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=True), \
                mock.patch.object(storage, "_home_dir", side_effect=storage.StorageError("no profile")):
            self.assertEqual(storage.data_dir(self.plugin), os.path.join(self.plugin, "data"))
            self.assertEqual(storage.legacy_dirs(self.plugin), [])

    def test_environment_override_is_exact_and_platform_independent(self):
        first = self.fixture_path("isolated", "custom-dir")
        second = self.fixture_path("another-isolated")
        for platform in ("nt", "posix"):
            with self.subTest(platform=platform), \
                    mock.patch.object(storage.os, "name", platform), \
                    mock.patch.object(storage, "_can_use_plugin", side_effect=AssertionError("override probed root")), \
                    mock.patch.object(storage, "_old_user_dirs", side_effect=AssertionError("override accessed old dirs")):
                os.environ["VOCABAPP_DATA_DIR"] = first
                self.assertEqual(storage.data_dir(), first)
                self.assertEqual(storage.legacy_dirs(), [])
                os.environ["VOCABAPP_DATA_DIR"] = second
                self.assertEqual(storage.paths(self.plugin)[0],
                                 os.path.join(second, "progress.json"))
        self.assertFalse(os.path.exists(first))
        self.assertFalse(os.path.exists(second))

    def test_relative_override_always_resolves_to_absolute_paths(self):
        override = os.path.relpath(self.fixture_path("relative-dir"))
        with mock.patch.dict(os.environ, {"VOCABAPP_DATA_DIR": override}, clear=True):
            self.assertEqual(storage.data_dir(), os.path.abspath(override))
            self.assertTrue(all(os.path.isabs(p) for p in storage.paths()))
        self.assertFalse(os.path.exists(os.path.abspath(override)))

    def test_readonly_plugin_falls_back_to_localappdata_without_probe_files(self):
        os.makedirs(self.plugin)
        os.environ.pop("VOCABAPP_DATA_DIR")
        with mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_directory_writable", return_value=False):
            self.assertEqual(storage.data_dir(self.plugin),
                             self.fixture_path("fake-localappdata", "VocabApp"))
        self.assertEqual(os.listdir(self.plugin), [])

    def test_existing_unwritable_data_also_falls_back(self):
        data = os.path.join(self.plugin, "data")
        os.makedirs(data)
        os.environ.pop("VOCABAPP_DATA_DIR")
        with mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_directory_writable", side_effect=lambda p: p != data):
            self.assertEqual(storage.data_dir(self.plugin),
                             self.fixture_path("fake-localappdata", "VocabApp"))
        self.assertEqual(os.listdir(data), [])

    def test_file_in_place_of_plugin_or_data_is_not_selected(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        self.write_bytes(self.plugin, b"not a directory")
        with mock.patch.object(storage.os, "name", "nt"):
            self.assertEqual(storage.data_dir(self.plugin),
                             self.fixture_path("fake-localappdata", "VocabApp"))
        other = self.fixture_path("other-plugin")
        self.write_bytes(os.path.join(other, "data"), b"not a directory")
        with mock.patch.object(storage.os, "name", "nt"):
            self.assertEqual(storage.data_dir(other),
                             self.fixture_path("fake-localappdata", "VocabApp"))

    def test_windows_uses_appdata_when_localappdata_is_missing(self):
        env = {"APPDATA": self.fixture_path("roaming")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=False):
            self.assertEqual(storage.data_dir(self.plugin),
                             self.fixture_path("roaming", "VocabApp"))

    def test_windows_readonly_fallback_uses_user_local_directory(self):
        home = self.fixture_path("profile")
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}, clear=True), \
                mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=False):
            expected = self.fixture_path("profile", "AppData", "Local", "VocabApp")
            self.assertEqual(storage.data_dir(self.plugin), expected)
            self.assertFalse(os.path.exists(expected))

    def test_non_windows_xdg_and_home_readonly_fallback(self):
        home = self.fixture_path("home")
        with mock.patch.object(storage.os, "name", "posix"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=False):
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.fixture_path("xdg")},
                                 clear=True):
                self.assertEqual(storage.data_dir(self.plugin), self.fixture_path("xdg", "VocabApp"))
            with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}, clear=True):
                self.assertEqual(storage.data_dir(self.plugin),
                                 self.fixture_path("home", ".local", "share", "VocabApp"))

    def test_legacy_directories_are_ordered_deduplicated_and_exclude_target(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        with mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=True):
            expected = [self.fixture_path("fake-localappdata", "VocabApp"),
                        self.fixture_path("fake-appdata", "VocabApp"),
                        self.fixture_path("fake-home", "AppData", "Local", "VocabApp")]
            self.assertEqual(storage.legacy_dirs(self.plugin), expected)
            os.environ["APPDATA"] = os.environ["LOCALAPPDATA"]
            self.assertEqual(storage.legacy_dirs(self.plugin), [expected[0], expected[2]])
        self.assertTrue(all(not os.path.exists(p) for p in expected))

    def test_readonly_legacy_dirs_exclude_current_user_target_and_keep_plugin_source(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        with mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=False):
            expected = [self.fixture_path("fake-appdata", "VocabApp"),
                        self.fixture_path("fake-home", "AppData", "Local", "VocabApp"),
                        os.path.join(self.plugin, "data")]
            self.assertEqual(storage.legacy_dirs(self.plugin), expected)

    def test_non_windows_legacy_dirs_and_pathlike_root(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        os.environ["XDG_DATA_HOME"] = self.fixture_path("xdg")
        from pathlib import Path
        plugin = Path(self.plugin)
        with mock.patch.object(storage.os, "name", "posix"):
            self.assertEqual(storage.legacy_dirs(plugin),
                             [self.fixture_path("xdg", "VocabApp"),
                              self.fixture_path("fake-home", ".local", "share", "VocabApp")])

    def test_import_and_path_resolution_do_not_write_or_scan_old_records(self):
        with open(STORAGE_PATH, "r", encoding="utf-8") as stream:
            code = compile(stream.read(), STORAGE_PATH, "exec")
        namespace = {"__name__": "storage_import_fixture", "__file__":
                     self.fixture_path("plugin", "app", "storage.py")}
        denied = AssertionError("import/path resolution attempted filesystem write/scan")
        with mock.patch("builtins.open", side_effect=denied), \
                mock.patch.object(os, "makedirs", side_effect=denied), \
                mock.patch.object(os, "mkdir", side_effect=denied), \
                mock.patch.object(os, "replace", side_effect=denied), \
                mock.patch.object(os, "remove", side_effect=denied), \
                mock.patch.object(os, "unlink", side_effect=denied), \
                mock.patch.object(os, "scandir", side_effect=denied), \
                mock.patch.object(tempfile, "mkstemp", side_effect=denied):
            exec(code, namespace)
            self.assertEqual(namespace["paths"]()[0], self.target)
            self.assertEqual(namespace["legacy_dirs"](), [])
            os.environ.pop("VOCABAPP_DATA_DIR")
            self.assertEqual(namespace["data_dir"](), os.path.join(self.plugin, "data"))
            for path in namespace["legacy_dirs"]():
                self.assert_fixture_path(path)
        self.assertFalse(os.path.exists(self.plugin))


class LoadingTests(FixtureCase):
    def test_old_user_records_copy_to_plugin_once_without_altering_any_old_files(self):
        os.environ.pop("VOCABAPP_DATA_DIR")
        olddir = self.fixture_path("fake-localappdata", "VocabApp")
        documents = {"progress.json": self.payload,
                     "_win.json": {"x": 11, "y": 22, "w": 520, "h": 430,
                                   "future_window": {"preserve": True}}}
        before = {}
        for filename, document in documents.items():
            old = os.path.join(olddir, filename)
            self.write_json(old, document)
            self.write_json(old + ".bak", {"previous": filename})
            self.write_json(old + ".tmp", {"pending": filename})
            for source in (old, old + ".bak", old + ".tmp"):
                before[source] = self.read_bytes(source)
        with mock.patch.object(storage.os, "name", "nt"), \
                mock.patch.object(storage, "_can_use_plugin", return_value=True):
            for filename, document in documents.items():
                target = os.path.join(storage.data_dir(self.plugin), filename)
                sources = [os.path.join(d, filename) for d in storage.legacy_dirs(self.plugin)]
                result, caught = self.caught_load(target, legacy_path=sources)
                self.assertEqual(result, document)
                self.assertEqual(self.read_json(target), document)
                self.assertEqual(len(caught), 1)
                # 已迁移后的记录优先，不再读取/复制旧来源，也不新建 target.bak。
                with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
                    again, notices = self.caught_load(target, legacy_path=sources)
                self.assertEqual(again, document)
                self.assertEqual(notices, [])
                self.assertEqual([c.args[0] for c in reads.call_args_list], [target])
                self.assertFalse(os.path.exists(target + ".bak"))
        for source, raw in before.items():
            self.assertEqual(self.read_bytes(source), raw)

    def test_old_backup_only_is_copied_without_recreating_old_primary(self):
        self.write_json(self.legacy + ".bak", self.payload)
        before = self.read_bytes(self.legacy + ".bak")
        result, caught = self.caught_load(legacy_path=[self.legacy])
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertFalse(os.path.exists(self.legacy))
        self.assertEqual(self.read_bytes(self.legacy + ".bak"), before)
        self.assertEqual(len(caught), 1)
        self.assertIn(self.legacy + ".bak", str(caught[0].message))

    def test_corrupt_old_primary_reads_own_backup_but_never_restores_old_files(self):
        self.write_bytes(self.legacy, b"broken old primary")
        self.write_json(self.legacy + ".bak", self.payload)
        self.write_json(self.legacy + ".tmp", {"pending": True})
        before = {p: self.read_bytes(p) for p in
                  (self.legacy, self.legacy + ".bak", self.legacy + ".tmp")}
        result, caught = self.caught_load(legacy_path=[self.legacy])
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)
        self.assertIn(self.legacy + ".bak", str(caught[0].message))
        for source, raw in before.items():
            self.assertEqual(self.read_bytes(source), raw)

    def test_old_missing_primary_with_invalid_backups_is_not_new_user(self):
        self.write_bytes(self.legacy + ".bak", b"broken old backup")
        self.write_bytes(self.legacy + ".tmp", b"null")
        with self.assertRaises(storage.StorageError):
            storage.load_json(self.target, legacy_path=[self.legacy])
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(self.read_bytes(self.legacy + ".bak"), b"broken old backup")
        self.assertEqual(self.read_bytes(self.legacy + ".tmp"), b"null")

    def test_legacy_list_skips_missing_and_uses_first_present_source(self):
        first = self.fixture_path("missing", "progress.json")
        later = self.fixture_path("older", "progress.json")
        self.write_json(self.legacy, self.payload)
        self.write_json(later, {"older": True})
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            result, caught = self.caught_load(legacy_path=[first, self.legacy, later])
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)
        self.assertNotIn(later, [c.args[0] for c in reads.call_args_list])
        self.assertEqual(self.read_json(later), {"older": True})

    def test_legacy_list_does_not_skip_corrupt_first_present_source(self):
        later = self.fixture_path("older", "progress.json")
        self.write_bytes(self.legacy, b"broken current old record")
        self.write_json(later, self.payload)
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            with self.assertRaises(storage.StorageError):
                storage.load_json(self.target, legacy_path=[self.legacy, later])
        self.assertNotIn(later, [c.args[0] for c in reads.call_args_list])
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(self.read_bytes(self.legacy), b"broken current old record")
        self.assertEqual(self.read_json(later), self.payload)

    def test_self_legacy_missing_does_not_migrate_or_create_files(self):
        result, caught = self.caught_load(legacy_path=[self.target, self.target])
        self.assertEqual(result, {})
        self.assertEqual(caught, [])
        self.assertFalse(os.path.exists(os.path.dirname(self.target)))

    def test_legacy_list_deduplicates_and_excludes_self(self):
        self.write_json(self.legacy, self.payload)
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            result, caught = self.caught_load(legacy_path=[self.target, self.legacy,
                                                         self.legacy, self.target])
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)
        self.assertEqual([c.args[0] for c in reads.call_args_list].count(self.legacy), 1)

    def test_pathlike_or_ordered_generator_legacy_is_supported(self):
        from pathlib import Path
        self.write_json(self.legacy, self.payload)
        result, caught = self.caught_load(legacy_path=(p for p in [Path(self.legacy)]))
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)
        self.assertEqual(self.read_json(self.target), self.payload)

    def test_window_accepts_legacy_path_list(self):
        window = {"x": -17, "y": 33, "future": {"theme": "fixture"}}
        old = self.fixture_path("old-local", "_win.json")
        target = self.fixture_path("new-plugin", "data", "_win.json")
        self.write_json(old, window)
        before = self.read_bytes(old)
        with self.assertWarns(storage.StorageWarning):
            self.assertEqual(storage.load_window(target, legacy_path=[old]), window)
        self.assertEqual(self.read_bytes(old), before)
        self.assertEqual(self.read_json(target), window)

    def test_existing_target_and_own_recovery_take_priority_over_legacy_list(self):
        self.write_bytes(self.target, b"broken target")
        self.write_json(self.target + ".bak", self.payload)
        self.write_json(self.legacy, {"old": True})
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            result, caught = self.caught_load(legacy_path=[self.legacy])
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)
        self.assertNotIn(self.legacy, [c.args[0] for c in reads.call_args_list])
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            result, caught = self.caught_load(legacy_path=[self.legacy])
        self.assertEqual(result, self.payload)
        self.assertEqual(caught, [])
        self.assertEqual([c.args[0] for c in reads.call_args_list], [self.target])

    def test_empty_or_missing_legacy_list_never_creates_empty_record(self):
        for sources in ([], [self.legacy]):
            with self.subTest(sources=sources):
                result, caught = self.caught_load(legacy_path=sources)
                self.assertEqual(result, {})
                self.assertEqual(caught, [])
                self.assertFalse(os.path.exists(os.path.dirname(self.target)))

    def test_bad_legacy_list_type_is_rejected_without_writes(self):
        for sources in (42, {self.legacy}, {"path": self.legacy}, [None]):
            with self.subTest(sources=sources), self.assertRaises(storage.StorageError):
                storage.load_json(self.target, legacy_path=sources)
        self.assertFalse(os.path.exists(os.path.dirname(self.target)))

    def test_missing_without_legacy_returns_independent_default_without_writes(self):
        default = {"states": {}, "history": [], "nested": {"values": []}}
        result, caught = self.caught_load(default=default)
        self.assertEqual(result, default)
        result["nested"]["values"].append("changed")
        self.assertEqual(default["nested"]["values"], [])
        self.assertEqual(caught, [])
        self.assertFalse(os.path.exists(os.path.dirname(self.target)))
        self.assertEqual(storage.load_json(self.target), {})

    def test_unspecified_legacy_never_reads_plugin_data(self):
        self.write_json(self.legacy, self.payload)
        raw = self.read_bytes(self.legacy)
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            result = storage.load_json(self.target)
        self.assertEqual(result, {})
        self.assertNotIn(self.legacy, [call.args[0] for call in reads.call_args_list])
        self.assertEqual(self.read_bytes(self.legacy), raw)
        self.assertFalse(os.path.exists(self.target))

    def test_explicit_migration_copies_full_history_states_and_unknown_fields(self):
        self.write_json(self.legacy, self.payload)
        before = self.read_bytes(self.legacy)
        result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(self.read_bytes(self.legacy), before)
        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, storage.StorageWarning)
        self.assertIn(self.legacy, str(caught[0].message))
        self.assertIn(self.target, str(caught[0].message))
        self.assertEqual(self.stages(), [])

    def test_window_migration_uses_same_protection_and_preserves_extra_fields(self):
        legacy = self.fixture_path("old", "data", "_win.json")
        target = self.fixture_path("current", "_win.json")
        window = {"x": -17, "y": 33, "w": 356, "h": 196,
                  "future_geometry": {"monitor": "fixture"}}
        self.write_json(legacy, window)
        before = self.read_bytes(legacy)
        with self.assertWarns(storage.StorageWarning):
            result = storage.load_window(target, legacy_path=legacy)
        self.assertEqual(result, window)
        self.assertEqual(self.read_json(target), window)
        self.assertEqual(self.read_bytes(legacy), before)
        self.assertEqual(storage.load_window(target, legacy_path=legacy), window)

    def test_valid_target_takes_priority_even_if_legacy_is_corrupt(self):
        self.write_json(self.target, self.payload)
        self.write_bytes(self.legacy, b"broken legacy")
        before = self.read_bytes(self.target)
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(caught, [])
        self.assertEqual(self.read_bytes(self.target), before)
        self.assertEqual([call.args[0] for call in reads.call_args_list], [self.target])

    def test_repeated_migration_never_recopies_or_resets_existing_target(self):
        self.write_json(self.legacy, self.payload)
        first, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(len(caught), 1)
        before = self.read_bytes(self.target)
        self.write_json(self.legacy, {"history": [], "states": {}, "different_version": True})
        for _ in range(3):
            result, caught = self.caught_load(legacy_path=self.legacy)
            self.assertEqual(result, first)
            self.assertEqual(caught, [])
            self.assertEqual(self.read_bytes(self.target), before)
        self.assertFalse(os.path.exists(self.target + ".bak"))

    def test_target_created_while_reading_legacy_is_not_overwritten(self):
        self.write_json(self.legacy, {"legacy": True})

        def create_target_on_legacy_read(path):
            document = self._checked_read(path)
            if path == self.legacy:
                self.write_json(self.target, self.payload)
            return document

        with mock.patch.object(storage, "_read_document",
                               side_effect=create_target_on_legacy_read):
            result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(caught, [])

    def test_corrupt_legacy_raises_and_is_not_deleted_or_reset(self):
        self.write_bytes(self.legacy, b'{"history":')
        before = self.read_bytes(self.legacy)
        with self.assertRaises(storage.StorageError):
            storage.load_json(self.target, default={}, legacy_path=self.legacy)
        self.assertEqual(self.read_bytes(self.legacy), before)
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(self.stages(), [])

    def test_corrupt_main_restores_backup_before_tmp_or_legacy(self):
        self.write_bytes(self.target, b'{"states":')
        self.write_json(self.target + ".bak", self.payload)
        self.write_json(self.target + ".tmp", {"pending": True})
        self.write_json(self.legacy, {"legacy": True})
        backup_before = self.read_bytes(self.target + ".bak")
        tmp_before = self.read_bytes(self.target + ".tmp")
        result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(self.read_bytes(self.target + ".bak"), backup_before)
        self.assertEqual(self.read_bytes(self.target + ".tmp"), tmp_before)
        self.assertEqual(len(caught), 1)
        self.assertIn(self.target + ".bak", str(caught[0].message))

    def test_corrupt_backup_falls_back_to_valid_tmp_without_overwriting_source(self):
        self.write_bytes(self.target, b"broken main")
        self.write_bytes(self.target + ".bak", b"broken backup")
        self.write_json(self.target + ".tmp", self.payload)
        tmp_before = self.read_bytes(self.target + ".tmp")
        result, caught = self.caught_load()
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(self.read_bytes(self.target + ".tmp"), tmp_before)
        self.assertEqual(self.read_bytes(self.target + ".bak"), b"broken backup")
        self.assertIn(self.target + ".tmp", str(caught[0].message))

    def test_missing_target_restores_backup_instead_of_remigrating_old_history(self):
        self.write_json(self.legacy, {"history": [], "states": {}})
        self.save({"history": [], "states": {}})
        self.save(self.payload)
        self.save(dict(self.payload, new_session=True))
        self.remove_fixture_file(self.target)
        result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(len(caught), 1)
        result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(caught, [])

    def test_corrupt_main_without_legal_backups_raises_without_any_changes(self):
        invalid_documents = [b'{"history":', b"not JSON", b"[]", b"null", b"42",
                             b"\xff", b'{"theta":NaN}', b'{"theta":Infinity}']
        for index, invalid in enumerate(invalid_documents):
            with self.subTest(invalid=invalid):
                target = self.fixture_path("invalid-%d" % index, "progress.json")
                self.write_bytes(target, invalid)
                self.write_bytes(target + ".bak", b"also corrupt")
                self.write_bytes(target + ".tmp", b"[]")
                before = {p: self.read_bytes(p) for p in
                          (target, target + ".bak", target + ".tmp")}
                with self.assertRaises(storage.StorageError) as raised:
                    storage.load_json(target, default={})
                self.assertIn(target, str(raised.exception))
                for path, raw in before.items():
                    self.assertEqual(self.read_bytes(path), raw)
                self.assertEqual(self.stages(target), [])

    def test_existing_corrupt_main_cannot_be_overwritten_from_valid_legacy(self):
        self.write_bytes(self.target, b"corrupt existing record")
        self.write_json(self.legacy, self.payload)
        with mock.patch.object(storage, "_read_document", wraps=self._checked_read) as reads:
            with self.assertRaises(storage.StorageError):
                storage.load_json(self.target, legacy_path=self.legacy)
        self.assertNotIn(self.legacy, [call.args[0] for call in reads.call_args_list])
        self.assertEqual(self.read_bytes(self.target), b"corrupt existing record")
        self.assertEqual(self.read_json(self.legacy), self.payload)

    def test_missing_target_with_only_invalid_backups_is_not_a_new_user(self):
        self.write_bytes(self.target + ".bak", b"broken backup")
        self.write_bytes(self.target + ".tmp", b"null")
        with self.assertRaises(storage.StorageError):
            storage.load_json(self.target)
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(self.read_bytes(self.target + ".bak"), b"broken backup")
        self.assertEqual(self.read_bytes(self.target + ".tmp"), b"null")

    def test_valid_main_ignores_invalid_backup_and_temporary_files(self):
        self.write_json(self.target, self.payload)
        self.write_bytes(self.target + ".bak", b"invalid")
        self.write_bytes(self.target + ".tmp", b"invalid")
        result, caught = self.caught_load()
        self.assertEqual(result, self.payload)
        self.assertEqual(caught, [])

    def test_utf8_bom_legacy_is_valid_and_bytes_remain_unchanged(self):
        raw = b"\xef\xbb\xbf" + json.dumps(self.payload, ensure_ascii=False).encode("utf-8")
        self.write_bytes(self.legacy, raw)
        result, caught = self.caught_load(legacy_path=self.legacy)
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)
        self.assertEqual(self.read_bytes(self.legacy), raw)

    def test_non_object_default_is_rejected(self):
        for default in ([], "bad", 0):
            with self.subTest(default=default), self.assertRaises(storage.StorageError):
                storage.load_json(self.target, default=default)
        self.assertFalse(os.path.exists(os.path.dirname(self.target)))


class SavingTests(FixtureCase):
    def test_successive_saves_keep_previous_valid_json_backup_and_unknown_fields(self):
        before_data = copy.deepcopy(self.payload)
        self.assertIsNone(self.save(self.payload))
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(self.payload, before_data)
        self.assertFalse(os.path.exists(self.target + ".bak"))
        first_raw = self.read_bytes(self.target)
        second = dict(self.payload, future_version={"field": ["preserved"]})
        self.save(second)
        self.assertEqual(self.read_bytes(self.target + ".bak"), first_raw)
        self.assertEqual(storage.load_json(self.target), second)
        second_raw = self.read_bytes(self.target)
        self.save(dict(second, another_session=True))
        self.assertEqual(self.read_bytes(self.target + ".bak"), second_raw)
        self.assertEqual(self.stages(), [])

    def test_serialization_failure_preserves_main_backup_and_existing_tmp(self):
        self.write_json(self.target, self.payload)
        self.write_json(self.target + ".bak", {"previous": "valid"})
        self.write_json(self.target + ".tmp", {"pending": "valid"})
        before = {p: self.read_bytes(p) for p in
                  (self.target, self.target + ".bak", self.target + ".tmp")}
        circular = {}
        circular["self"] = circular
        invalid_data = [{"nested": {"set": {1, 2}}}, {"number": float("nan")},
                        {"number": float("inf")}, {"value": object()}, circular,
                        {"bad_unicode": "\ud800"}, [], None]
        for data in invalid_data:
            with self.subTest(kind=type(data).__name__), \
                    mock.patch.object(storage.os, "makedirs") as mkdir, \
                    mock.patch.object(storage, "_write_stage") as stages, \
                    self.assertRaises(storage.StorageError):
                self.save(data)
            mkdir.assert_not_called()
            stages.assert_not_called()
            for path, raw in before.items():
                self.assertEqual(self.read_bytes(path), raw)
        self.assertEqual(self.stages(), [])

    def test_serialization_failure_for_new_file_does_not_create_directory(self):
        with self.assertRaises(storage.StorageError):
            self.save({"invalid": object()})
        self.assertFalse(os.path.exists(os.path.dirname(self.target)))

    def test_replace_failure_is_bounded_and_preserves_original_and_backup(self):
        self.write_json(self.target, self.payload)
        self.write_json(self.target + ".bak", {"earlier": "valid"})
        before = self.read_bytes(self.target)
        backup_before = self.read_bytes(self.target + ".bak")
        with mock.patch.object(storage.os, "replace", side_effect=PermissionError("busy")) \
                as replace, mock.patch.object(storage.time, "sleep") as sleep:
            with self.assertRaises(storage.StorageError):
                self.save(dict(self.payload, new_record=True))
        self.assertEqual(replace.call_count, storage._REPLACE_ATTEMPTS)
        self.assertEqual(sleep.call_count, storage._REPLACE_ATTEMPTS - 1)
        self.assertEqual(self.read_bytes(self.target), before)
        self.assertEqual(self.read_bytes(self.target + ".bak"), backup_before)
        for call in replace.call_args_list:
            source, target = call.args
            self.assert_fixture_path(source)
            self.assert_fixture_path(target)
            self.assertEqual(os.path.dirname(source), os.path.dirname(target))
        self.assertEqual(storage.load_json(self.target), self.payload)

    def test_main_replace_failure_after_backup_succeeds_preserves_main_data(self):
        self.write_json(self.target, self.payload)
        before = self.read_bytes(self.target)
        real_replace = os.replace
        attempts = []

        def fail_main(source, target):
            self.assert_fixture_path(source)
            self.assert_fixture_path(target)
            if target == self.target:
                attempts.append((source, target))
                raise PermissionError("main temporarily occupied")
            return real_replace(source, target)

        with mock.patch.object(storage.os, "replace", side_effect=fail_main), \
                mock.patch.object(storage.time, "sleep"):
            with self.assertRaises(storage.StorageError):
                self.save(dict(self.payload, new_record=True))
        self.assertEqual(len(attempts), storage._REPLACE_ATTEMPTS)
        self.assertEqual(self.read_bytes(self.target), before)
        self.assertEqual(self.read_bytes(self.target + ".bak"), before)
        self.assertEqual(len(self.stages()), 1)
        self.assertEqual(storage.load_json(self.target), self.payload)

    def test_new_file_replace_failure_leaves_recoverable_unique_temporary(self):
        with mock.patch.object(storage.os, "replace", side_effect=PermissionError("busy")), \
                mock.patch.object(storage.time, "sleep"):
            with self.assertRaises(storage.StorageError):
                self.save(self.payload)
        self.assertFalse(os.path.exists(self.target))
        stages = self.stages()
        self.assertEqual(len(stages), 1)
        self.assertEqual(self.read_json(stages[0]), self.payload)
        result, caught = self.caught_load()
        self.assertEqual(result, self.payload)
        self.assertEqual(self.read_json(self.target), self.payload)
        self.assertEqual(len(caught), 1)
        self.assertIn(stages[0], str(caught[0].message))
        self.assertEqual(self.read_json(stages[0]), self.payload)

    def test_transient_windows_occupancy_retries_then_succeeds_atomically(self):
        self.write_json(self.target, self.payload)
        before = self.read_bytes(self.target)
        real_replace = os.replace
        attempts = []
        newer = dict(self.payload, latest=True)

        def temporarily_busy(source, target):
            self.assert_fixture_path(source)
            self.assert_fixture_path(target)
            self.assertEqual(os.path.dirname(source), os.path.dirname(target))
            if target == self.target:
                attempts.append((source, target))
                if len(attempts) < 3:
                    raise PermissionError("transient Windows sharing violation")
            return real_replace(source, target)

        with mock.patch.object(storage.os, "replace", side_effect=temporarily_busy), \
                mock.patch.object(storage.time, "sleep") as sleep:
            self.save(newer)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.read_json(self.target), newer)
        self.assertEqual(self.read_bytes(self.target + ".bak"), before)

    def test_non_retryable_replace_failure_never_falls_back_to_direct_write(self):
        self.write_json(self.target, self.payload)
        before = self.read_bytes(self.target)
        with mock.patch.object(storage.os, "replace", side_effect=OSError(errno.ENOSPC,
                                                                          "disk full")) \
                as replace, mock.patch.object(storage.time, "sleep") as sleep:
            with self.assertRaises(storage.StorageError):
                self.save(dict(self.payload, new_record=True))
        self.assertEqual(replace.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(self.read_bytes(self.target), before)

    def test_corrupt_main_never_replaces_unique_good_backup_even_if_save_fails(self):
        self.write_bytes(self.target, b"broken main")
        self.write_json(self.target + ".bak", self.payload)
        backup_before = self.read_bytes(self.target + ".bak")
        with mock.patch.object(storage.os, "replace", side_effect=PermissionError("busy")), \
                mock.patch.object(storage.time, "sleep"):
            with self.assertRaises(storage.StorageError):
                self.save(dict(self.payload, next=True))
        self.assertEqual(self.read_bytes(self.target), b"broken main")
        self.assertEqual(self.read_bytes(self.target + ".bak"), backup_before)
        self.save(dict(self.payload, next=True))
        self.assertEqual(self.read_bytes(self.target + ".bak"), backup_before)
        self.assertEqual(self.read_json(self.target), dict(self.payload, next=True))

    def test_recovery_followed_by_save_never_promotes_corrupt_main_into_backup(self):
        self.write_bytes(self.target, b"broken main")
        self.write_json(self.target + ".bak", self.payload)
        backup_before = self.read_bytes(self.target + ".bak")
        result, caught = self.caught_load()
        self.assertEqual(len(caught), 1)
        self.assertEqual(self.read_bytes(self.target + ".bak"), backup_before)
        restored_raw = self.read_bytes(self.target)
        result["history"].append({"t": 1700000060, "vocab": 2345})
        self.save(result)
        self.assertEqual(self.read_bytes(self.target + ".bak"), restored_raw)
        self.assertEqual(self.read_json(self.target + ".bak"), self.payload)
        self.assertEqual(self.read_json(self.target), result)

    def test_tmp_only_recovery_failure_preserves_unique_valid_source(self):
        self.write_bytes(self.target, b"broken main")
        self.write_json(self.target + ".tmp", self.payload)
        before = self.read_bytes(self.target + ".tmp")
        with mock.patch.object(storage.os, "replace", side_effect=PermissionError("busy")), \
                mock.patch.object(storage.time, "sleep"):
            with self.assertRaises(storage.StorageError):
                storage.load_json(self.target)
        self.assertEqual(self.read_bytes(self.target), b"broken main")
        self.assertEqual(self.read_bytes(self.target + ".tmp"), before)
        result, caught = self.caught_load()
        self.assertEqual(result, self.payload)
        self.assertEqual(len(caught), 1)

    def test_stage_write_failure_preserves_main_and_existing_backup(self):
        self.write_json(self.target, self.payload)
        self.write_json(self.target + ".bak", {"earlier": "valid"})
        before = self.read_bytes(self.target)
        backup_before = self.read_bytes(self.target + ".bak")
        with mock.patch.object(storage.os, "fsync", side_effect=OSError("fsync failure")):
            with self.assertRaises(storage.StorageError):
                self.save(dict(self.payload, latest=True))
        self.assertEqual(self.read_bytes(self.target), before)
        self.assertEqual(self.read_bytes(self.target + ".bak"), backup_before)

    def test_unreadable_existing_main_raises_before_staging_or_backup_changes(self):
        self.write_json(self.target, self.payload)
        before = self.read_bytes(self.target)
        with mock.patch.object(storage, "_read_document", side_effect=PermissionError("denied")), \
                mock.patch.object(storage, "_write_stage") as write_stage:
            with self.assertRaises(storage.StorageError):
                self.save(dict(self.payload, latest=True))
        write_stage.assert_not_called()
        self.assertEqual(self.read_bytes(self.target), before)
        self.assertEqual(self.stages(), [])


if __name__ == "__main__":
    warnings.simplefilter("error", storage.StorageWarning)
    unittest.main(verbosity=2)
