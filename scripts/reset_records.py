# -*- coding: utf-8 -*-
"""明确确认后清空 VocabApp 使用记录；仅删除已知记录文件，不删目录或词库。

命令行必须从真实安装目录运行（由本文件位置确定）。测试仅调用隔离安装目录。
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import storage


class ResetError(RuntimeError):
    pass


def record_dirs(root=ROOT):
    root = Path(root).resolve()
    if not (root / "app" / "main.py").is_file() or not (root / "data" / "bank.json").is_file():
        raise ResetError("安装目录校验失败，拒绝清空。")
    target = Path(storage.data_dir(str(root))).resolve()
    if os.environ.get("VOCABAPP_DATA_DIR"):
        return [target]
    legacy = (root / "data").resolve()
    # data 目录本身不能是指向另一个安装目录的链接。
    if legacy.parent != root:
        raise ResetError("旧记录目录不在已校验安装目录中，拒绝清空。")
    sources = [Path(directory).resolve() for directory in storage.legacy_dirs(str(root))]
    return list(dict.fromkeys([target, legacy] + sources))


def _is_record(name):
    name = name.casefold()
    return any(name in (base, base + ".bak", base + ".tmp")
               or name.startswith(base + ".tmp-")
               or name.startswith(base + ".bak.tmp-")
               for base in ("progress.json", "_win.json"))


def record_files(directories):
    """发现之后再验证绝对路径；文件链接、目录、未知文件一律不删除。"""
    found = []
    for directory in directories:
        directory = Path(directory).resolve()
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise ResetError("记录路径不是目录：%s" % directory)
        for path in directory.iterdir():
            if not _is_record(path.name):
                continue
            resolved = path.resolve()
            if path.is_symlink() or resolved.parent != directory or resolved != path.absolute():
                raise ResetError("记录文件指向目录外或是链接，拒绝删除：%s" % path)
            if path.is_file():
                found.append(path)
    return sorted(set(found), key=str)


def clear_records(root=ROOT, confirmed=False):
    """仅在明确确认及取得与主程序相同的单实例锁后删除。"""
    if not confirmed:
        raise ResetError("未确认，不清空任何记录。")
    directories = record_dirs(root)
    # 必须在读取待删除名单前取得锁，避免与迁移或新进程启动交错。
    stable = Path(storage.data_dir(str(Path(root).resolve()))).resolve()
    try:
        stable.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ResetError("无法访问记录目录：%s" % error) from error
    from PyQt5.QtCore import QLockFile
    locks = []
    deleted = []
    try:
        # 旧版可能仍在旧稳定资料目录运行；全部取得锁后才删除第一份记录。
        for directory in directories:
            if not directory.exists():
                continue
            if not directory.is_dir():
                raise ResetError("记录路径不是目录：%s" % directory)
            lock = QLockFile(str(directory / "vocab-app.lock"))
            lock.setStaleLockTime(0)
            if not lock.tryLock(0):
                raise ResetError("背单词可能仍在运行或记录目录不可写，请先关闭窗口再重试：%s" % directory)
            locks.append(lock)
        for path in record_files(directories):
            # 删除前再次确认解析后的绝对文件仍是同一个目标，避免中途变成链接。
            if path.is_symlink() or path.resolve() != path.absolute() or not _is_record(path.name):
                raise ResetError("记录文件路径已变化，停止清空：%s" % path)
            try:
                path.unlink()
            except OSError as error:
                raise ResetError("无法删除 %s：%s；词库未删除。" % (path, error)) from error
            deleted.append(str(path))
    finally:
        for lock in reversed(locks):
            lock.unlock()
    return deleted


def preview(root=ROOT):
    """List exact immediate candidates without reading record contents or deleting."""
    directories = record_dirs(root)
    active = Path(storage.data_dir(str(Path(root).resolve()))).resolve()
    files = record_files(directories)
    print("当前写入目录仅有一个；旧目录是兼容迁移检查来源，不表示程序同时向多处写入。")
    print("清空时也检查旧来源，避免下次启动把旧进度迁移回来；不会删除词库或整个目录。")
    for directory in directories:
        role = "当前写入目录" if directory == active else "旧版迁移来源（非当前写入目录）"
        matches = [path for path in files if path.parent == directory]
        print("%s：%s（%d 个匹配文件）" % (role, directory, len(matches)))
        for path in matches:
            print("  - %s" % path.name)
        if not matches:
            print("  - 无匹配记录文件")
    print("发现 %d 个已知记录/备份/临时文件（这是文件数，不是目录数）。" % len(files))
    print("只匹配各目录第一层 progress.json、_win.json 及其已知备份/临时文件；不递归扫描。")
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只显示目标，不清空")
    parser.add_argument("--yes", action="store_true", help="明确确认清空（自动化用）")
    args = parser.parse_args(argv)
    try:
        print("请先关闭背单词。将清空学习进度、词汇量测试历史与窗口设置，词库不会删除。")
        preview()
        if args.dry_run:
            return 0
        if not args.yes and input("输入 CLEAR 并回车确认，其它输入取消：").strip() != "CLEAR":
            print("已取消，没有清空。")
            return 2
        deleted = clear_records(confirmed=True)
        print("已清空 %d 个使用记录文件。重新打开插件即可。" % len(deleted))
        return 0
    except (ResetError, OSError, EOFError) as error:
        print("清空未完成：" + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
