# -*- coding: utf-8 -*-
"""隔离验证：默认记录缺失时真实 Card 的旧记录迁移 / 已有目标保留 / override 不迁移。

只新建本文件，不改生产代码。所有 source/target/ENV 都指向工作区
.vocab-ui-tests/<sandbox>/...；真实 legacy/stable 记录由 Sandbox 指纹保护。
"""
import os
import sys
import io
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
WORKSPACE = os.path.dirname(APP)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(APP, "app"))

from ui_test_support import configure_qt, Sandbox, set_nottest, new_app

configure_qt("offscreen")
set_nottest(True)

from PyQt5.QtWidgets import QApplication

app = new_app(sys.argv)
out = []
fails = []


def check(cond, msg):
    out.append(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


def pump(seconds=0.0, n=10):
    for _ in range(n):
        app.processEvents()
    if seconds:
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.008)
    for _ in range(n):
        app.processEvents()


def read_bytes(path):
    try:
        with io.open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "wb") as f:
        f.write(data)
    return data


def snap(paths):
    return {path: read_bytes(path) for path in paths}


def make_history(n, base_ts=1700000000):
    return [{"ts": base_ts + i * 60, "vocab": 1000 + i, "right": 10 + i % 30,
             "dontknow": 5 + i % 8, "total": 50, "theta": 0.1,
             "se": 0.5, "baseline": i == 0, "known": 3000 + i,
             "to_learn": 12000 - i, "rigor": 90, "err": 10,
             "lo": 900 + i, "hi": 1200 + i} for i in range(n)]


def fixture_progress(n=60, marker="legacy"):
    return {
        "welcome_done": True,
        "book_confirmed": True,
        "book": "cet4-dg",
        "theme": "light",
        "states": {"survey": {"st": "learning", "lv": 3,
                              "due": 1700000500, "seen": 2,
                              "lapse": 0, "streak": 1}},
        "cursors": {"cet4-dg": 7},
        "orders": {"cet4-dg": {"mode": "seq", "seed": 12345}},
        "study_records": {"cet4-dg": {"pending": {},
                                      "current": None,
                                      "held_current": None}},
        "history": make_history(n),
        "memory_schema": 2,
        "retry_gap": 5,
        marker: {"keep": True},
    }


def fixture_window(marker="legacy"):
    return {"normal_w": 640, "normal_h": 520, "x": 80, "y": 70,
            "compact": False, "dock_edge": None,
            marker: {"keep": 2}}


def set_env(key, value):
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


def storage_fake_checks(sb, storage):
    fake_root = sb.path("fake_plugin")
    fake_data = os.path.join(fake_root, "data")
    os.makedirs(fake_data, exist_ok=True)
    fake_old = sb.path("fake_local")
    fake_old2 = sb.path("fake_appdata")
    fake_home = sb.path("fake_home")
    for d in (os.path.join(fake_old, "VocabApp"),
              os.path.join(fake_old2, "VocabApp"), fake_home):
        os.makedirs(d, exist_ok=True)
    keys = ("VOCABAPP_DATA_DIR", "LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME",
            "HOME", "USERPROFILE")
    saved = {key: os.environ.get(key) for key in keys}
    try:
        set_env("VOCABAPP_DATA_DIR", None)
        set_env("LOCALAPPDATA", fake_old)
        set_env("APPDATA", fake_old2)
        set_env("XDG_DATA_HOME", None)
        set_env("HOME", fake_home)
        set_env("USERPROFILE", fake_home)
        paths = storage.paths(fake_root)
        check(paths == (os.path.join(fake_data, "progress.json"),
                        os.path.join(fake_data, "_win.json")),
              "storage.paths(fake_root) -> fake_plugin/data")
        candidates = storage.legacy_dirs(fake_root)
        check(os.path.join(fake_data, "progress.json") not in candidates,
              "legacy_dirs 排除当前 target")
        check(len(candidates) >= 1, "legacy_dirs 候选来自 fake 旧目录：%r" % (candidates,))

        set_env("VOCABAPP_DATA_DIR", sb.dir)
        check(storage.paths(fake_root) ==
              (sb.progress_path, sb.win_path),
              "VOCABAPP_DATA_DIR override -> sandbox paths")
        check(storage.legacy_dirs(fake_root) == [],
              "override 时 legacy_dirs 候选为空")
    finally:
        for key, value in saved.items():
            set_env(key, value)


def main():
    import main as app_main
    import storage

    sb = Sandbox(app_main, "plugin-records")
    sb.__enter__()
    cards = []
    orig_globals = {}
    try:
        check(sb.verify_real(), "进入 Sandbox 后真实记录指纹未变")
        out.append("      REAL_FINGERPRINT protected=%d" % len(sb.watch_paths))

        # 模拟旧源目录与默认目标（全部在 sb.dir 内）
        legacy_dir = sb.path("legacy_source")
        os.makedirs(legacy_dir, exist_ok=True)
        legacy_progress = os.path.join(legacy_dir, "progress.json")
        legacy_win = os.path.join(legacy_dir, "_win.json")
        legacy_p_backup = legacy_progress + ".bak"
        legacy_p_temp = legacy_progress + ".tmp-fixed"
        legacy_w_backup = legacy_win + ".bak"

        # 该用例在任一 Card 构造前已把 default/global 路径全部放入 Sandbox；
        # 清除 override，才真正覆盖目标缺失时的默认迁移分支（退出时还原）。
        if os.environ.get("VOCABAPP_DATA_DIR") is not None:
            orig_globals["_PLUGIN_RECORDS_ENV"] = os.environ.pop("VOCABAPP_DATA_DIR")

        # patch main 的默认/legacy 分支：DEFAULT==当前 sb target，legacy 指向 fake 旧源
        for name in ("DEFAULT_PROGRESS_PATH", "DEFAULT_WIN_PATH",
                     "LEGACY_PROGRESS_PATHS", "LEGACY_WIN_PATHS"):
            orig_globals[name] = getattr(app_main, name)
        app_main.DEFAULT_PROGRESS_PATH = sb.progress_path
        app_main.DEFAULT_WIN_PATH = sb.win_path
        app_main.LEGACY_PROGRESS_PATHS = (legacy_progress,)
        app_main.LEGACY_WIN_PATHS = (legacy_win,)

        # 确保默认目标缺失 + 旧源存在；旧源 sidecar 也要有独立字节
        sb.write_progress(None)
        sb.write_win(None)
        progress_source = fixture_progress(60, "legacy_extension")
        window_source = fixture_window("legacy_win_extension")
        write_bytes(legacy_progress, json.dumps(progress_source, ensure_ascii=False).encode("utf-8"))
        write_bytes(legacy_win, json.dumps(window_source, ensure_ascii=False).encode("utf-8"))
        write_bytes(legacy_p_backup, b"legacy-progress-backup-bytes")
        write_bytes(legacy_p_temp, b"legacy-progress-temp-bytes")
        write_bytes(legacy_w_backup, b"legacy-win-backup-bytes")
        source_paths = (legacy_progress, legacy_win, legacy_p_backup,
                        legacy_p_temp, legacy_w_backup)
        source_before = snap(source_paths)

        # 1) 默认目标缺失 + 旧源存在：真实 Card 构造走 main 迁移分支
        w = sb.new_card(show=True)
        cards.append(w)
        pump(0.08)
        check(os.path.exists(sb.progress_path) and os.path.exists(sb.win_path),
              "默认目标缺失时真实 Card 完成 progress/_win 迁移")
        target_progress = sb.read_progress()
        target_window = sb.read_win()
        check(len(target_progress.get("history", [])) >= 60,
              "迁移 history 完整 >=60 条：%d" % len(target_progress.get("history", [])))
        check(target_progress.get("history") == progress_source["history"],
              "迁移 history 内容逐条保留")
        check(target_progress.get("legacy_extension") == {"keep": True},
              "迁移保留未知 progress 扩展字段")
        check(target_window.get("legacy_win_extension") == {"keep": 2},
              "迁移保留未知 window 扩展字段")
        check(target_progress.get("retry_gap") == 3,
              "迁移后固定 retry_gap=3（源=%r）" % progress_source.get("retry_gap"))
        check(target_progress.get("memory_schema") == 2,
              "既有 memory_schema=2 兼容保留")
        check(w.progress.get("history") == progress_source["history"],
              "Card 内存 progress 保留完整 60+ history")
        w.open_settings()
        pump(0.05)
        check(len(w.progress.get("history", [])) >= 60,
              "打开设置（仅显示最近5条）后 progress history 未截断：%d" %
              len(w.progress.get("history", [])))
        check(source_before == snap(source_paths),
              "旧 source 及其 .bak/.tmp sidecars 字节未变")
        w.close()
        pump(0.05)
        check(len(sb.read_progress().get("history", [])) >= 60,
              "关闭后目标历史仍完整")
        check(sb.read_progress().get("legacy_extension") == {"keep": True},
              "关闭后目标未知字段仍在")

        # 2) 已有 target 不被不同/损坏 legacy source 覆盖
        target_progress = fixture_progress(70, "target_extension")
        target_progress["retry_gap"] = 7
        target_window = fixture_window("target_win_extension")
        sb.write_progress(target_progress)
        sb.write_win(target_window)
        target_before = snap([sb.progress_path, sb.win_path])
        # 旧源换成完全不同内容（坏 JSON / 不同 marker）
        write_bytes(legacy_progress,
                    b'{"bad": "different legacy source", "history": []}')
        write_bytes(legacy_win, b'{"different": true}')
        source_before2 = snap(source_paths)
        w2 = sb.new_card(show=True)
        cards.append(w2)
        pump(0.08)
        got = sb.read_progress()
        check(len(got.get("history", [])) == 70,
              "已有 target wins：目标 history=70 不被旧源覆盖（实际 %d）" %
              len(got.get("history", [])))
        check(got.get("target_extension") == {"keep": True},
              "已有 target 的未知字段保留")
        check("legacy_extension" not in got,
              "已有 target 不导入 legacy 扩展字段")
        check(sb.read_win().get("target_win_extension") == {"keep": 2},
              "已有 target window 未知字段保留")
        check(source_before2 == snap(source_paths),
              "已有 target 时旧 source/sidecars 字节未变")
        w2.close()
        pump(0.05)
        got2 = sb.read_progress()
        check(got2.get("target_extension") == {"keep": True}
              and len(got2.get("history", [])) == 70,
              "关闭后 target 扩展/完整 history 保持")
        check(source_before2 == snap(source_paths),
              "关闭后旧 source/sidecars 仍字节未变")

        # 3) VOCABAPP_DATA_DIR override：不导入旧源
        sb.write_progress(None)
        sb.write_win(None)
        source_before3 = snap(source_paths)
        old_override = os.environ.get("VOCABAPP_DATA_DIR")
        os.environ["VOCABAPP_DATA_DIR"] = sb.dir
        try:
            w3 = sb.new_card(show=True)
            cards.append(w3)
            pump(0.05)
            check("legacy_extension" not in w3.progress,
                  "override 时不导入 legacy progress")
            check("legacy_win_extension" not in getattr(w3, "window_record", {}),
                  "override 时不导入 legacy window")
            check(source_before3 == snap(source_paths),
                  "override 时旧 source/sidecars 字节未变")
            w3.close()
            pump(0.05)
            check(source_before3 == snap(source_paths),
                  "override 关闭后旧 source/sidecars 仍字节未变")
        finally:
            set_env("VOCABAPP_DATA_DIR", old_override)

        # 4) storage.paths/legacy_dirs fake env 语义
        storage_fake_checks(sb, storage)

    except Exception:
        import traceback
        check(False, "插件记录迁移场景异常：\n" + traceback.format_exc())
    finally:
        for w in cards:
            try:
                for timer in w.findChildren(__import__("PyQt5.QtCore",
                                                       fromlist=["QTimer"]).QTimer):
                    timer.stop()
                w.close()
            except Exception:
                pass
        for name, value in orig_globals.items():
            if name == "_PLUGIN_RECORDS_ENV":
                os.environ["VOCABAPP_DATA_DIR"] = value
            else:
                setattr(app_main, name, value)
        sb.__exit__(None, None, None)
        check(not sb.errors, "真实 records 指纹（含恢复文件）未变：%r" % (sb.errors,))
        out.append("      FINGERPRINT protected=%d unchanged=%s" %
                   (len(sb.watch_paths), not sb.errors))

    return sb.finish(out, fails, "test_plugin_records.txt")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
