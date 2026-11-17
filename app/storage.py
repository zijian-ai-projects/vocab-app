# -*- coding: utf-8 -*-
"""VocabApp 的独立本地记录存储（不依赖 Qt）。

路径解析和 import 都不创建目录；第一次成功保存/显式迁移时才创建目录。
默认优先使用可写插件根目录下的 data；只读安装目录回退旧的用户资料目录。
测试应显式设置 VOCABAPP_DATA_DIR，或把 root 和用户目录环境都指向临时夹具。

load_json 只在目标缺失、且明确传入 legacy_path（单路径或有序路径列表）时
复制旧记录。加载失败不会返回空记录；合法 .bak/.tmp（包括本模块的唯一
临时文件）可原子恢复。legacy_dirs 提供旧目录候选，不扫描或修改旧记录。
迁移/恢复通过 StorageWarning 报告来源，调用方可用 warnings.catch_warnings
收集后显示。所有未知字段原样保留，不在存储层进行学习记录 schema 转换。
"""
import copy
import json
import os
import tempfile
import time
import warnings

try:                                    # 冻结发行需要安装目录/用户目录的独立解析
    import paths as _paths
except ImportError:                     # 被单独复制时保持旧行为
    _paths = None


class StorageError(RuntimeError):
    """记录无法安全加载或保存；调用方不得将此异常视为新用户空记录。"""


class StorageWarning(UserWarning):
    """显式旧版迁移或备份恢复的说明（包含来源和目标路径）。"""


class _InvalidJSON(ValueError):
    pass


_REPLACE_ATTEMPTS = 6
_REPLACE_DELAY = 0.02


def _absolute(path):
    """只展开并解析路径，不查询/创建文件。"""
    return os.path.abspath(os.path.expanduser(os.path.expandvars(os.fsdecode(path))))


def _home_dir():
    home = os.path.expanduser("~")
    if home and home != "~":
        return _absolute(home)
    # 少数精简 Windows 环境没有 USERPROFILE，但仍可能提供 HOME。
    home = os.environ.get("HOME")
    if home:
        return _absolute(home)
    raise StorageError("无法确定用户本地目录；请设置 VOCABAPP_DATA_DIR。")


def _plugin_root(root=None):
    return _absolute(root if root is not None else
                     os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _directory_writable(path):
    """只查询现有目录权限；不创建探针文件。

    Windows 的 os.access 不足以判断 NTFS ACL，所以用 OPEN_EXISTING 打开
    目录并请求新增文件/子目录权限；这不是创建/改写文件，也不更改 ACL。
    """
    if not os.access(path, os.W_OK):
        return False
    if os.name != "nt":
        return bool(os.stat(path).st_mode & 0o222)
    import ctypes
    from ctypes import wintypes
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                           ctypes.c_void_p)
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        # FILE_ADD_FILE | FILE_ADD_SUBDIRECTORY, share read/write/delete,
        # OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS（只为打开目录）。
        handle = create(path, 0x0002 | 0x0004, 0x0007, None, 3, 0x02000000, None)
        if handle == ctypes.c_void_p(-1).value:
            return False
        try:
            return True
        finally:
            close(handle)
    except (AttributeError, OSError):
        return False                 # 无法证明可写时回退，不试写目录。


def _can_use_plugin(root):
    """root 不存在时查询最近的现有父目录；已有 data 也必须可写。"""
    candidate = root
    try:
        while True:
            try:
                os.stat(candidate)
                break
            except FileNotFoundError:
                if os.path.lexists(candidate):  # 悬空链接不当作可创建目录。
                    return False
                parent = os.path.dirname(candidate)
                if parent == candidate:
                    return False
                candidate = parent
        if not os.path.isdir(candidate) or not _directory_writable(candidate):
            return False
        data = os.path.join(root, "data")
        try:
            os.stat(data)
        except FileNotFoundError:
            return not os.path.lexists(data)
        return os.path.isdir(data) and _directory_writable(data)
    except OSError:
        return False


def _unique_dirs(directories, exclude=None):
    seen = {os.path.normcase(_absolute(exclude))} if exclude is not None else set()
    result = []
    for directory in directories:
        absolute = _absolute(directory)
        key = os.path.normcase(absolute)
        if key not in seen:
            seen.add(key)
            result.append(absolute)
    return result


def _old_user_dirs(name="VocabApp"):
    """旧稳定目录，按旧默认优先级排列；只计算路径，不查询是否存在。"""
    if os.name == "nt":
        bases = [os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA")]
        home_suffix = ("AppData", "Local")
    else:
        bases = [os.environ.get("XDG_DATA_HOME")]
        home_suffix = (".local", "share")
    bases = [base for base in bases if base]
    try:
        bases.append(os.path.join(_home_dir(), *home_suffix))
    except StorageError:
        if not bases:
            raise
    return _unique_dirs(os.path.join(base, name) for base in bases)


def _directory_redirected(directory):
    """只检测目录本身的链接/NTFS junction，允许安装根的祖先有合法链接。"""
    absolute = _absolute(directory)
    expected = os.path.join(os.path.realpath(os.path.dirname(absolute)),
                            os.path.basename(absolute))
    return (os.path.islink(absolute) or
            os.path.normcase(os.path.realpath(absolute)) != os.path.normcase(expected))


def _portable_ok(directory):
    """冻结发行：可写就便携；不存在时看父目录能否创建。"""
    try:
        if _directory_redirected(directory):
            return False
        if os.path.isdir(directory):
            return _directory_writable(directory)
        if os.path.lexists(directory):
            return False
        parent = os.path.dirname(directory)
        return os.path.isdir(parent) and _directory_writable(parent)
    except OSError:
        return False


def data_dir(root=None):
    """返回绝对记录目录，不创建目录。

    VOCABAPP_DATA_DIR 指定目录本身（不追加子目录），优先级最高。
    冻结发行（Windows 便携包）：安装目录旁 ``userdata``，只读安装回退到
    用户目录 ``VocabAppWindows``，与源码资料、DSH 插件资料互不相干。
    源码运行：可写 root 优先用 <root>/data；只读时回退旧用户目录。
    """
    override = os.environ.get("VOCABAPP_DATA_DIR")
    if override:
        return _absolute(override)
    if root is None and _paths is not None and _paths.is_frozen():
        portable = _absolute(_paths.portable_data_dir())
        if _directory_redirected(portable):
            raise StorageError("默认记录目录是目录链接，拒绝读写或清空：%s" % portable)
        if _portable_ok(portable):
            return portable
        fallback = _old_user_dirs("VocabAppWindows")[0]
        if _directory_redirected(fallback):
            raise StorageError("默认记录目录是目录链接，拒绝读写或清空：%s" % fallback)
        return fallback
    plugin = _plugin_root(root)
    if _can_use_plugin(plugin):
        return os.path.join(plugin, "data")
    return _old_user_dirs()[0]


def legacy_dirs(root=None):
    """供显式迁移使用的有序旧目录候选；不读/扫描/创建目录或记录。

    旧稳定用户目录优先；只读插件回退时也保留旧 <root>/data 候选。
    排除当前目标目录、去重。显式隔离 override 时返回 []，不引入真实资料。
    冻结发行返回 []：便携包不自动搬入源码树或旧 AppData 的既有记录。
    """
    if os.environ.get("VOCABAPP_DATA_DIR"):
        return []
    if root is None and _paths is not None and _paths.is_frozen():
        return []
    plugin = _plugin_root(root)
    target = data_dir(plugin)
    try:
        old = _old_user_dirs()
    except StorageError:
        old = []                    # 可写插件仍可用；不凭空猜一个用户资料目录。
    return _unique_dirs(old + [os.path.join(plugin, "data")], exclude=target)


def paths(root=None):
    """返回 (progress_path, win_path)，均为绝对 str；没有文件系统写入。"""
    directory = data_dir(root)
    return (os.path.join(directory, "progress.json"),
            os.path.join(directory, "_win.json"))


def _reject_constant(value):
    raise _InvalidJSON("不合法的 JSON 数值：%s" % value)


def _read_document(path):
    """同时返回完整对象和原始字节；.bak 保留上一份有效文件的原始内容。"""
    with open(path, "rb") as stream:
        raw = stream.read()
    try:
        data = json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _InvalidJSON("无效 JSON：%s" % exc) from exc
    if not isinstance(data, dict):
        raise _InvalidJSON("JSON 顶层必须是对象，不是 %s" % type(data).__name__)
    return data, raw


def _serialize(data):
    if not isinstance(data, dict):
        raise StorageError("保存失败：JSON 顶层必须是 dict。")
    try:
        # 先在内存完成序列化和编码，连 mkdir/.tmp/.bak 都不能提前修改。
        return (json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
                + "\n").encode("utf-8")
    except Exception as exc:
        raise StorageError("保存失败：记录无法序列化为有效 JSON：%s" % exc) from exc


def _write_stage(path, raw):
    """使用同目录的唯一临时文件，绝不截断已有的合法 .tmp 恢复来源。

    成功时 os.replace 消耗此文件；失败时保留它供后续恢复，不做危险的清理
    或非原子主文件写入。仅调用 atomic_save 才会到达这里。
    """
    fd, stage = tempfile.mkstemp(prefix=os.path.basename(path) + ".tmp-",
                                 dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd is not None:
            os.close(fd)
    return stage


def _replace(source, target):
    """只对短暂占用做有限重试；失败绝不退化为直接覆写目标文件。"""
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            busy = (isinstance(exc, PermissionError)
                    or getattr(exc, "winerror", None) in (5, 32, 33))
            if not busy or attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_DELAY * (attempt + 1))


def atomic_save(path, data):
    """原子保存 dict，保留上一份有效 JSON 的 .bak；成功返回 None。

    新文件同样只经同目录临时文件 + os.replace 建立。若原主文件损坏，不将
    它复制到 .bak，因此已有合法备份保持不变。序列化/写入/replace 失败抛
    StorageError；未完成替换的主文件和已有合法恢复来源不会被截断。
    """
    raw = _serialize(data)
    target = _absolute(path)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            _, previous_raw = _read_document(target)
        except FileNotFoundError:
            previous_raw = None
        except _InvalidJSON:
            previous_raw = None  # 不能用损坏主文件覆盖合法 .bak。
        stage = _write_stage(target, raw)
        if previous_raw is not None:
            backup = target + ".bak"
            backup_stage = _write_stage(backup, previous_raw)
            _replace(backup_stage, backup)
        _replace(stage, target)
    except (OSError, _InvalidJSON) as exc:
        raise StorageError("无法原子保存 %s：%s（未使用非原子覆写）" %
                           (target, exc)) from exc


def _recovery_candidates(path):
    # 已提交的上一份有效记录优先，其次是兼容旧版的固定 .tmp。
    yield path + ".bak"
    yield path + ".tmp"
    # 本模块的唯一 stage 不会覆盖旧 .tmp，失败后也能作为恢复来源。
    primary_prefix = os.path.basename(path) + ".tmp-"
    backup_prefix = os.path.basename(path) + ".bak.tmp-"
    stages = []
    try:
        with os.scandir(os.path.dirname(path)) as entries:
            for entry in entries:
                if entry.name.startswith(primary_prefix):
                    priority = 0
                elif entry.name.startswith(backup_prefix):
                    priority = 1
                else:
                    continue
                try:
                    if entry.is_file():
                        stages.append((priority, -entry.stat().st_mtime_ns,
                                       entry.name, entry.path))
                except FileNotFoundError:
                    pass  # 另一写入者已经完成原子替换。
    except FileNotFoundError:
        return
    for _, _, _, stage in sorted(stages):
        yield stage


def _load_error(path, problems):
    detail = "; ".join("%s：%s" % (source, exc) for source, exc in problems)
    return StorageError("无法加载 %s：没有可恢复的有效 JSON；记录未清空、"
                        "原文件未改写。%s" % (path, detail))


def _legacy_sources(value, target):
    """单 path / 有序 iterable 统一为去重路径；排除目标，避免自我迁移。"""
    if value is None:
        return
    if isinstance(value, (str, bytes, os.PathLike)):
        values = (value,)
    else:
        if isinstance(value, (dict, set, frozenset)):
            raise StorageError("legacy_path 必须为单路径或有序路径列表。")
        try:
            values = iter(value)
        except TypeError as exc:
            raise StorageError("legacy_path 必须为单路径或有序路径列表。") from exc
    seen = {os.path.normcase(target)}
    for source in values:
        try:
            absolute = _absolute(source)
        except (TypeError, ValueError) as exc:
            raise StorageError("legacy_path 含有非路径条目：%r" % (source,)) from exc
        key = os.path.normcase(absolute)
        if key not in seen:
            seen.add(key)
            yield absolute


def _read_legacy(legacy):
    """读取旧主文件或其恢复来源，但绝不恢复/改写旧目录中的文件。"""
    problems = []
    try:
        data, _ = _read_document(legacy)
        return data, legacy
    except FileNotFoundError:
        pass
    except (OSError, _InvalidJSON) as exc:
        problems.append((legacy, exc))
    try:
        for source in _recovery_candidates(legacy):
            try:
                data, _ = _read_document(source)
                return data, source
            except FileNotFoundError:
                continue
            except (OSError, _InvalidJSON) as exc:
                problems.append((source, exc))
    except OSError as exc:
        problems.append((os.path.dirname(legacy), exc))
    if problems:
        raise _load_error(legacy, problems)
    raise FileNotFoundError(legacy)


def load_json(path, default=None, legacy_path=None):
    """加载完整 dict；仅真正不存在的记录返回 default 的独立副本（默认 {}）。

    目标存在时永远优先，不从 legacy_path 覆盖它。目标缺失/损坏时先尝试
    合法 .bak/.tmp 并原子恢复；只有目标缺失且没有合法恢复来源时，才尝试
    明确指定的 legacy_path。迁移复制完整 JSON，旧文件不删除、不改写。
    主文件损坏且无法恢复、旧文件损坏、读写失败都抛 StorageError，而不是
    静默返回空记录。legacy_path 可为单路径或有序路径列表；未传时不访问
    任何旧记录。旧目录也可从自己的备份读取，但不在旧目录恢复或改写文件；
    首个现存旧记录损坏且无合法恢复来源即拒绝，不能悄悄改用更旧资料。
    """
    if default is not None and not isinstance(default, dict):
        raise StorageError("load_json 的 default 必须为 dict 或 None。")
    target = _absolute(path)
    problems = []
    try:
        data, _ = _read_document(target)
        return data
    except FileNotFoundError:
        missing = True
    except (OSError, _InvalidJSON) as exc:
        missing = False
        problems.append((target, exc))
    try:
        for source in _recovery_candidates(target):
            try:
                recovered, _ = _read_document(source)
            except FileNotFoundError:
                continue
            except (OSError, _InvalidJSON) as exc:
                problems.append((source, exc))
                continue
            atomic_save(target, recovered)
            warnings.warn("记录已从备份原子恢复：%s -> %s（备份保留）" %
                          (source, target), StorageWarning, stacklevel=2)
            return recovered
    except OSError as exc:
        problems.append((os.path.dirname(target), exc))
    if not missing:
        raise _load_error(target, problems)
    for legacy in _legacy_sources(legacy_path, target):
        try:
            migrated, migration_source = _read_legacy(legacy)
        except FileNotFoundError:
            continue
        except (OSError, _InvalidJSON) as exc:
            problems.append((legacy, exc))
            break                   # 更旧的另一个目录不能掩盖当前旧资料损坏。
        else:
            # 读取旧文件期间目标可能已经由调用方建立；再次优先读取目标。
            try:
                existing, _ = _read_document(target)
                return existing
            except FileNotFoundError:
                pass
            except (OSError, _InvalidJSON):
                return load_json(target, default=default)
            atomic_save(target, migrated)
            warnings.warn("旧版记录已复制到记录目录：%s -> %s（旧文件保留）" %
                          (migration_source, target), StorageWarning, stacklevel=2)
            return migrated
    if problems:
        raise _load_error(target, problems)
    return copy.deepcopy(default) if default is not None else {}


def load_window(path, default=None, legacy_path=None):
    """窗口记录与进度记录采用完全相同的优先级、显式迁移及损坏保护。"""
    return load_json(path, default=default, legacy_path=legacy_path)
