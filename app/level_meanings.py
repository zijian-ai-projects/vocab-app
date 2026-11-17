# -*- coding: utf-8 -*-
"""小学/初中学段释义覆盖：安全加载 data/level_meanings.json，不修改通用 bank。

文件格式兼容两种（数据 owner 可任选，最终统一 schema）：
  {"primary": {"word": "小学释义"}, "middleschool": {...}}
  {"levels": {"primary": {...}, "middleschool": {...}}}
值可为字符串，或含 display_s/level_s（也接受 s/meaning/text/gloss）的对象；
有效释义对象可附 display_w，学校词形与稳定key分离。
任何缺失/损坏/非法字段都安全回退为空覆盖，不抛异常。
"""
import io
import json
import os

import paths

DATA = paths.data_root()
DEFAULT_PATH = os.path.join(DATA, "level_meanings.json")
STAGES = ("primary", "middleschool")
_STAGE_ALIASES = {
    "primary": "primary",
    "middleschool": "middleschool",
    "middle_school": "middleschool",
    "middle": "middleschool",
}
_STAGE_BY_MAIN = {"primary": "primary", "middleschool": "middleschool"}
_CACHE = None
_CACHE_PATH = None
_CACHE_MTIME = None


def stage_for_main(main):
    return _STAGE_BY_MAIN.get(main)


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _normalise(value):
    """归一有效显示释义及可选 display_w；无有效释义不接受单独别名。"""
    if isinstance(value, str):
        text = _text(value)
        if not text:
            return {}
        # 文件是纯字符串时，同时提供两个兼容字段，entries.meaning 取首个有效值。
        return {"display_s": text, "level_s": text}
    if not isinstance(value, dict):
        return {}
    out = {}
    for field in ("display_s", "level_s"):
        text = _text(value.get(field))
        if text:
            out[field] = text
    if not out:
        for field in ("s", "meaning", "text", "gloss"):
            text = _text(value.get(field))
            if text:
                out["display_s"] = text
                out["level_s"] = text
                break
    if out:
        display_word = _text(value.get("display_w"))
        if display_word:
            out["display_w"] = display_word
    return out


def _stage_mapping(source, stage):
    raw = source.get(stage)
    if not isinstance(raw, dict):
        for alias, canonical in _STAGE_ALIASES.items():
            if canonical == stage and isinstance(source.get(alias), dict):
                raw = source[alias]
                break
    if not isinstance(raw, dict):
        return {}
    result = {}
    for word, value in raw.items():
        if not isinstance(word, str) or not word:
            continue
        normalised = _normalise(value)
        if normalised:
            result[word] = normalised
    return result


def load(path=None):
    """返回 {primary: {word: {display_s/level_s}}, middleschool: {...}}。"""
    global _CACHE, _CACHE_PATH, _CACHE_MTIME
    filename = DEFAULT_PATH if path is None else path
    cached = (path is None and _CACHE is not None and _CACHE_PATH == filename)
    if cached:
        try:
            mtime = os.path.getmtime(filename) if filename and os.path.exists(filename) else None
        except OSError:
            mtime = None
        if mtime == _CACHE_MTIME:
            return _CACHE
    empty = {stage: {} for stage in STAGES}
    try:
        if not filename or not os.path.exists(filename):
            result = empty
        else:
            with io.open(filename, encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                result = empty
            else:
                levels = data.get("levels")
                source = levels if isinstance(levels, dict) else data
                result = {stage: _stage_mapping(source, stage) for stage in STAGES}
                # levels 不完整时也兼容顶层同名字段
                for stage in STAGES:
                    if not result[stage]:
                        result[stage] = _stage_mapping(data, stage)
    except (OSError, ValueError, TypeError, UnicodeError):
        result = empty
    if path is None:
        try:
            mtime = os.path.getmtime(filename) if filename and os.path.exists(filename) else None
        except OSError:
            mtime = None
        _CACHE = result
        _CACHE_PATH = filename
        _CACHE_MTIME = mtime
    return result


def clear_cache():
    global _CACHE, _CACHE_PATH, _CACHE_MTIME
    _CACHE = None
    _CACHE_PATH = None
    _CACHE_MTIME = None


def mapping_for(stage):
    if stage not in STAGES:
        return {}
    return load().get(stage) or {}


def decorate(entry, mapping=None):
    """浅拷贝有效显示义/可选学校词形；标记学校caption但绝不改原entry。"""
    copy = dict(entry)
    if mapping:
        override = mapping.get(copy.get("w"))
        if override:
            for field in ("display_s", "level_s", "display_w"):
                text = override.get(field)
                if text:
                    copy[field] = text
            if _text(override.get("display_w")):
                copy["_school_caption"] = True
    return copy
