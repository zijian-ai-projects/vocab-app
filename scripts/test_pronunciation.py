# -*- coding: utf-8 -*-
"""V1.3.3 保守音标展示：全词库只读校验 + Sandbox实际刷词/选择题可见性。"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
import entries


class PronunciationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "data" / "bank.json"
        cls.before = hashlib.sha256(cls.path.read_bytes()).hexdigest()
        cls.bank = json.loads(cls.path.read_text(encoding="utf-8"))
        cls.by_word = {word["w"]: word for word in cls.bank}

    @classmethod
    def tearDownClass(cls):
        assert hashlib.sha256(cls.path.read_bytes()).hexdigest() == cls.before, "真实bank字节变化"

    def test_empty_and_wrapper_only_fields_never_display_a_bare_slash(self):
        for value in (None, "", " ", "/", "//", " / / ", "[]", "[ ]", "?", "--", "ˈˌː"):
            with self.subTest(value=value):
                self.assertEqual(entries.pronunciation({"w": "word", "ipa": value, "ph_raw": ""}), "")

    def test_backslash_and_escape_damage_are_not_guessed_or_deleted_into_fake_ipa(self):
        for value in ("\\", "\\\\", "p\\\\:sən", r"\u0259", r"\x02", "\x02æ", "wɜ\nd"):
            with self.subTest(value=value):
                source = {"w": "word", "ipa": value, "ph_raw": value}
                before = copy.deepcopy(source)
                self.assertEqual(entries.pronunciation(source), "")
                self.assertEqual(source, before)

    def test_existing_valid_raw_fallback_is_used_but_never_invented(self):
        for value in ("", "/", " ", "\\", "p\\\\:sən", None, 42, {}):
            with self.subTest(value=value):
                self.assertEqual(entries.pronunciation({"w": "word", "ipa": value,
                                                       "ph_raw": " /wɜːd/ "}), "/wɜːd/")

    def test_valid_unicode_and_ipa_precedence_are_preserved_exactly(self):
        for value in ("wɜːd", "ˈkɒntrəvɜːsi", "ə", "ʔ", "ɑ̃", "[wɜːd]", "rɪˈsiːv (r)"):
            source = {"w": "word", "ipa": value, "ph_raw": "invalid\\"}
            before = copy.deepcopy(source)
            with self.subTest(value=value):
                self.assertEqual(entries.pronunciation(source), "/%s/" % value)
                self.assertEqual(source, before)
        self.assertEqual(entries.pronunciation({"w": "word", "ipa": " /wɜːd/ ",
                                               "ph_raw": "different"}), "/wɜːd/")

    def test_real_encephalomyeloradiculitis_is_missing_not_guessed(self):
        word = self.by_word["encephalomyeloradiculitis"]
        self.assertEqual(word.get("ipa"), "")
        self.assertEqual(word.get("ph_raw"), "")
        self.assertEqual(entries.pronunciation(word), "")
        self.assertEqual(entries.pronunciation({"w": "on the way", "ipa": "valid", "ph_raw": "valid"}), "")

    def test_real_bank_has_no_backslash_or_only_wrapper_display_and_no_changed_valid_ipa(self):
        missing = damaged = retained = 0
        for word in self.bank:
            before = copy.deepcopy(word)
            result = entries.pronunciation(word)
            self.assertEqual(word, before, word["w"])
            if result:
                self.assertNotIn("\\", result, word["w"])
                self.assertTrue(any(char.isalpha() for char in result.strip("/")), word["w"])
                self.assertFalse(any(ord(char) < 32 for char in result), word["w"])
                candidates = [v.strip().strip("/").strip() for v in
                              (word.get("ipa"), word.get("ph_raw")) if isinstance(v, str)]
                self.assertIn(result, ["/%s/" % v for v in candidates], word["w"])
                retained += 1
            else:
                missing += 1
            value = word.get("ipa") or ""
            if value and "\\" in value:
                damaged += 1
            elif value and any(c.isalpha() for c in value) and not entries.is_phrase(word):
                self.assertEqual(result, "/%s/" % value.strip().strip("/").strip(), word["w"])
        # 真实合法ipa不因损坏的ph_raw被丢掉；源库内容逐字保留。
        self.assertEqual(entries.pronunciation(self.by_word["bert"]), "/bɜːt/")
        self.assertEqual(entries.pronunciation(self.by_word["anchorperson"]), "")
        print("ALL_BANK_READONLY", len(self.bank), "DISPLAYED", retained,
              "HIDDEN", missing, "DAMAGED_IPA", damaged, "BANK_SHA_UNCHANGED", True)


class PronunciationUITests(unittest.TestCase):
    def check_modes(self, key, expected):
        # helper只被复用；其OrderChangeTests不会被本文件loader执行。
        import test_order_change as h
        from ui_test_support import Sandbox, set_nottest
        set_nottest(True)
        source = json.loads((ROOT / "data" / "bank.json").read_text(encoding="utf-8"))
        target = next(word for word in source if word["w"] == key)
        for mode in ("brush", "choice"):
            with self.subTest(key=key, mode=mode):
                sb = Sandbox(h.app_main, "pronunciation")
                books = h.TinyBooks()
                books.BY_ID[h.A]["words"][0] = key
                bank = copy.deepcopy(h.WORDS)
                bank[0] = copy.deepcopy(target)
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(os.environ, {"VOCABAPP_DATA_DIR": sb.dir}))
                    stack.enter_context(patch.object(h.app_main, "DATA", sb.dir))
                    stack.enter_context(patch.object(h.app_main, "bk", books))
                    stack.enter_context(patch.object(h.app_main.time, "time", lambda: 2000000000.0))
                    stack.enter_context(sb)
                    with io.open(sb.path("bank.json"), "w", encoding="utf-8") as stream:
                        json.dump(bank, stream, ensure_ascii=False)
                    sb.reset(h.fixture(study_mode=mode), {"mode": "normal", "w": 520, "h": 430})
                    w = sb.new_card(show=True)
                    sb.pump(h.APP)
                    self.assertEqual(h.current(w), ("new", key))
                    label = w.choice_ipa if mode == "choice" else w.ipa
                    self.assertEqual(label.text(), expected)
                    self.assertEqual(label.isVisible(), bool(expected))
                    self.assertTrue(sb.verify_real())
                self.assertFalse(sb.errors, " / ".join(sb.errors))
                print("UI_PHONETICS", key, mode, repr(expected), "VISIBLE", bool(expected),
                      "PROTECTED_PATHS", len(sb.watch_paths), "UNCHANGED", True)

    def test_missing_real_word_ipa_is_hidden_in_brush_and_choice(self):
        self.check_modes("encephalomyeloradiculitis", "")

    def test_damaged_real_word_ipa_is_hidden_in_brush_and_choice(self):
        self.check_modes("anchorperson", "")

    def test_valid_real_ipa_is_visible_despite_damaged_raw(self):
        self.check_modes("bert", "/bɜːt/")


if __name__ == "__main__":
    import tempfile
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    from ui_test_support import TEST_ROOT
    os.makedirs(TEST_ROOT, exist_ok=True)
    buffer = io.StringIO()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (PronunciationTests, PronunciationUITests))
    with redirect_stdout(buffer):
        result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    outdir = Path(tempfile.mkdtemp(prefix="pronunciation-out-", dir=TEST_ROOT))
    report = outdir / "test_pronunciation.txt"
    report.write_text(buffer.getvalue(), encoding="utf-8")
    print(buffer.getvalue())
    print("REPORT", str(report))
    print("PRONUNCIATION_TESTS", result.testsRun, "FAILS", len(result.failures), "ERRORS", len(result.errors))
    sys.exit(0 if result.wasSuccessful() else 1)
