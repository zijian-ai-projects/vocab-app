# -*- coding: utf-8 -*-
"""V1.3.5最终验收：独立进程、隔离资料、文件式stdout、全部代码与来源冻结守卫。"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

WORKSPACE = Path(__file__).resolve().parents[1]
ROOT = WORKSPACE / "vocab-app"
TEST_ROOT = WORKSPACE / ".vocab-ui-tests"
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))
import storage
from ui_test_support import fingerprint

parser = argparse.ArgumentParser()
parser.add_argument("--group", choices=("pure", "launcher", "compact", "ui", "native-ui"), required=True)
args = parser.parse_args()
TEST_ROOT.mkdir(exist_ok=True)
out = Path(tempfile.mkdtemp(prefix="final-v135-%s-" % args.group, dir=str(TEST_ROOT)))

PURE = [
    ("bank", "check_bank.py", ["--check"]),
    ("level-meanings-build", "build_level_meanings.py", ["--check"]),
    ("level-meanings", "test_level_meanings.py", []),
    ("school-reviews", "test_school_meaning_reviews.py", []),
    ("level-meanings-ui", "test_level_meanings_ui.py", []),
    ("community-books", "test_community_books.py", []),
    ("scheduler", "test_scheduler.py", []),
    ("queue", "test_study_queue.py", []),
    ("retry-gap", "test_retry_gap.py", []),
    ("storage", "test_storage.py", []),
    ("options", "test_study_options.py", ["--bank-perf"]),
    ("windowing", "test_windowing.py", []),
    ("dock-animation", "test_dock_animation.py", []),
    ("theme", "test_theme.py", []),
    ("pronunciation", "test_pronunciation.py", []),
    ("order-change", "test_order_change.py", []),
    ("phrases", "test_phrases.py", []),
    ("quiz-transactions", "test_quiz_transactions.py", []),
    ("launcher-unit", "test_launcher.py", []),
    ("reset-unit", "test_reset_records.py", []),
    ("sandbox", "test_ui_sandbox.py", []),
    ("plugin-records", "test_plugin_records.py", []),
    ("catalog", "test_catalog.py", []),
    ("onboarding", "test_onboarding.py", []),
    ("smoke", "smoke_ui.py", []),
]
LAUNCHER = [("launcher-" + mode, "check_launcher.py", ["--mode", mode])
            for mode in ("normal", "bare-path", "bad-record", "stale-lock")]
CASES = {
    "pure": PURE,
    "launcher": LAUNCHER,
    "compact": [("compact-native", "check_compact.py", [])],
    "ui": [("v130-offscreen", "test_v130_ui.py", []),
           ("v133-offscreen", "test_v133_ui.py", []),
           ("v134-offscreen", "test_v134_ui.py", []),
           ("v135-offscreen", "test_v135_ui.py", [])],
    "native-ui": [("v130-native", "test_v130_ui.py", ["--native"]),
                  ("v133-native", "test_v133_ui.py", ["--native"]),
                  ("v134-native", "test_v134_ui.py", ["--native"]),
                  ("v135-native", "test_v135_ui.py", ["--native"])],
}

# 真实资料不复制到报告，只留SHA；尚不存在的主文件/恢复/锁/日志路径同样守护。
directories = [str(ROOT / "data"), storage.data_dir(str(ROOT))]
directories.extend(storage._old_user_dirs())
bases = [os.path.join(folder, name) for folder in directories
         for name in ("progress.json", "_win.json", "vocab-app.lock", "startup.log")]
raw_before = fingerprint(bases)


def digest_map(values):
    return {key: hashlib.sha256(value).hexdigest() if value is not None else None
            for key, value in values.items()}


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def frozen_paths():
    paths = list((ROOT / "app").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    paths.extend(p for p in (ROOT / "assets").glob("*") if p.is_file())
    paths.extend(ROOT / "data" / name for name in
                 ("bank.json", "books.json", "level_meanings.json", "phrases.json", "phrase_books.json"))
    meanings = json.loads((ROOT / "data" / "level_meanings.json").read_text(encoding="utf-8"))
    for source in meanings["sources"]:
        path = (ROOT / source).resolve()
        if ROOT.resolve() not in path.parents:
            raise AssertionError("meaning provenance escapes project: " + source)
        paths.append(path)
    paths.extend(p for pattern in ("*.vbs", "*.bat") for p in ROOT.glob(pattern) if p.is_file())
    paths.extend((ROOT / "README.md", ROOT / ".gitattributes", ROOT / ".gitignore",
                  ROOT / "docs" / "level-meanings.md", ROOT / "docs" / "school-meanings-review-v135.md", Path(__file__).resolve(),
                  TEST_ROOT / "validate_final_v135.py"))
    paths.extend(TEST_ROOT / name for name in (
        "v135-audit-scope.json", "v135-audit-primary-input.json", "v135-audit-middleschool-input.json",
        "v135-primary-review.json", "v135-middle-review.json", "v135-original-level-meanings.json",
        "freeze_scope_v135.py", "build_primary_review_v135.py", "merge_review_v135.py",
        "build_review_ledger_v135.py", "make_final_tools_v135.py"))
    return sorted(set(paths))


core_before = {str(path): file_hash(path) for path in frozen_paths()}
(out / "records-before.json").write_text(json.dumps(digest_map(raw_before), indent=2), encoding="utf-8")
print("OUTPUT", str(out), flush=True)
results = []
for name, script, extra in CASES[args.group]:
    env = dict(os.environ)
    env["VOCABAPP_DATA_DIR"] = str(out / "profiles" / name)
    env["PYTHONIOENCODING"] = "utf-8"
    env["QT_QPA_PLATFORM"] = "offscreen" if args.group in ("pure", "ui") else "windows"
    env["QT_QPA_FONTDIR"] = os.path.join(env.get("WINDIR", "C:\\Windows"), "Fonts")
    for key in ("VOCAB_TEST_OUT", "VOCAB_TEST_KEEP", "VOCAB_V134_SKIP_IMAGES"):
        env.pop(key, None)
    command = [sys.executable, "-B", str(ROOT / "scripts" / script)] + extra
    report = out / (name + ".txt")
    started = time.monotonic()
    # 禁止PIPE捕获；工作区文件承接stdout/stderr，不触碰Windows命名管道边界。
    with report.open("wb") as stream:
        completed = subprocess.run(command, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT)
    text = report.read_text(encoding="utf-8", errors="replace")
    unit_count = re.search(r"Ran (\d+) tests?", text)
    ui_match = re.search(r"(?:V(?:130|133|134|135)|LEVEL MEANINGS) CHECKS (\d+) FAILS (\d+)", text)
    checks = int(ui_match.group(1)) if ui_match else len(re.findall(r"^\s*OK\s+", text, re.MULTILINE))
    result = {"name": name, "exit": completed.returncode, "seconds": round(time.monotonic() - started, 3),
              "unit_tests": int(unit_count.group(1)) if unit_count else None,
              "ui_checks": checks, "report": str(report), "command": command,
              "output": text[-1800:]}
    results.append(result)
    print("%s exit=%d unit=%s checks=%d seconds=%.3f" %
          (name, result["exit"], result["unit_tests"], checks, result["seconds"]), flush=True)
    if completed.returncode:
        print(text[-12000:], flush=True)

raw_after = fingerprint(bases)
core_after = {str(path): file_hash(path) for path in frozen_paths()}
changed = sorted(key for key in set(raw_before) | set(raw_after)
                 if raw_before.get(key, "<missing>") != raw_after.get(key, "<missing>"))
summary = {"version": "1.3.5", "group": args.group, "results": results,
           "records_protected": len(raw_before), "real_records_unchanged": raw_before == raw_after,
           "changed_paths": changed, "frozen_core_unchanged": core_before == core_after,
           "core_hashes": core_after}
(out / "records-after.json").write_text(json.dumps(digest_map(raw_after), indent=2), encoding="utf-8")
(out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print("REAL_RECORDS_AND_LOCKS_UNCHANGED", len(raw_before), raw_before == raw_after, flush=True)
for path in changed:
    print("CHANGED_PATH", path, flush=True)
print("FROZEN_CORE_AND_SOURCES_UNCHANGED", core_before == core_after, flush=True)
print("FAILED_PROCESSES", sum(result["exit"] != 0 for result in results), flush=True)
sys.exit(0 if raw_before == raw_after and core_before == core_after
         and all(result["exit"] == 0 for result in results) else 1)
