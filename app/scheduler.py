# -*- coding: utf-8 -*-
"""V1.3 的纯逻辑记忆排期；状态跨词书共享，队列只使用传入词书。

lv=0 是尚未认识的新词，没有时间排期。认识后进入 lv=1，随后每次
记得升一级；lv=1..9 的下一次复习分别在 5min..30d 后，lv=10 出库。
迁移只改变等级表示，不重新计算已保存的时间。所有状态操作返回副本。
"""
from copy import deepcopy
import time

MIN = 60
HOUR = 3600
DAY = 86400

LEVELS = [5 * MIN, 30 * MIN, 12 * HOUR, DAY, 2 * DAY, 4 * DAY,
          7 * DAY, 15 * DAY, 30 * DAY]
LEVEL_NAMES = ["5分钟", "30分钟", "12小时", "1天", "2天", "4天", "7天", "15天", "30天"]
MASTERED = 10
DONE = ("retired", "mastered", "learning", "known")
_TERMINAL = ("retired", "mastered", "known")


def _now(now):
    # 0 是合法的固定时钟，不能用 `now or time.time()`。
    return time.time() if now is None else now


def _level(st):
    try:
        return max(0, min(MASTERED, int((st or {}).get("lv", 0))))
    except (TypeError, ValueError, OverflowError):
        return 0


def _is_new(st):
    return not st or (st.get("st", "new") == "new" and _level(st) == 0)


def _is_learning(st):
    return bool(st and st.get("st") == "learning" and 1 <= _level(st) < MASTERED)


def new_state(now=None):
    """尚未认识的词没有 due；保留 now 参数以兼容旧调用。"""
    return {"lv": 0, "due": None, "seen": 0, "lapse": 0, "streak": 0, "st": "new"}


def migrate_state(st, legacy=False):
    """返回独立副本，将旧 0 基等级转换为 V1.3 的 1 基学习等级。

    legacy 必须由调用方的 memory_schema != 2 决定，并在保存后将 schema
    标为 2。现代状态（默认 legacy=False）不再升一级，反复规范化是幂等的。
    旧 st=new 实际表示已点过认识，故转为 learning/lv=1；旧 learning
    的等级加一；旧 mastered 固定为 10。保留 due、统计和自定义字段，
    仅移除已废弃的 retry_now；不读取时钟，不整体重排复习时间。
    """
    out = deepcopy(st) if st else new_state()
    out.pop("retry_now", None)
    lv = _level(out)
    status = out.get("st") or ("learning" if lv else "new")

    if legacy:
        if status == "new":
            lv, status = 1, "learning"
        elif status == "learning":
            lv = min(MASTERED, lv + 1)
        elif status == "mastered":
            lv = MASTERED

    if status == "mastered" or (lv == MASTERED and status not in ("retired", "known")):
        lv, status = MASTERED, "mastered"
    elif status in ("new", "learning"):
        status = "learning" if lv else "new"

    out["lv"] = lv
    out["st"] = status
    out.setdefault("due", None)
    if status in _TERMINAL or (status == "new" and lv == 0):
        out["due"] = None
    out.setdefault("seen", 0)
    out.setdefault("lapse", 0)
    out.setdefault("streak", 0)
    return out


def migrate_states(states, legacy=False):
    """逐词迁移，原 states 和其中的状态（包括嵌套字段）均不修改。"""
    return {key: migrate_state(st, legacy=legacy) for key, st in states.items()}


def on_remember(st, now=None):
    """认识新词进入 1 级；记得旧词升一级，10 级永久出库。"""
    out = migrate_state(st)
    if out["st"] in _TERMINAL:
        return out
    out["seen"] += 1
    out["streak"] = 0
    lv = min(MASTERED, out["lv"] + 1)
    out["lv"] = lv
    out["st"] = "mastered" if lv == MASTERED else "learning"
    out["due"] = None if lv == MASTERED else _now(now) + LEVELS[lv - 1]
    return out


def on_forget(st, now=None):
    """忘记不退级：旧词统一 5 分钟后再复习，新词仍然是无 due 的新词。"""
    out = migrate_state(st)
    if out["st"] in _TERMINAL:
        return out
    out["seen"] += 1
    out["lapse"] += 1
    out["streak"] += 1
    lv = out["lv"]
    out["st"] = "learning" if lv else "new"
    out["due"] = _now(now) + LEVELS[0] if lv else None
    return out


def on_fuzzy(st, now=None):
    """兼容旧的模糊按钮：同级刷新，不升降级，不增加 lapse。"""
    out = migrate_state(st)
    if out["st"] in _TERMINAL:
        return out
    out["seen"] += 1
    out["streak"] = 0
    lv = out["lv"]
    out["st"] = "learning" if lv else "new"
    out["due"] = _now(now) + LEVELS[lv - 1] if lv else None
    return out


def on_retire(st):
    """保留旧 API 的主动出库；不会再被新词或复习队列选中。"""
    out = migrate_state(st)
    out["st"] = "retired"
    out["due"] = None
    return out


def _due_entries(words, states, now):
    for idx, w in enumerate(words):
        st = states.get(w["w"])
        if _is_learning(st) and st.get("due") is not None and st["due"] <= now:
            yield idx, w, st


def due_queue(words, states, now=None):
    """保留旧 (due, word, state) 结构，按传入词书顺序而不是 due 排序。"""
    return [(st["due"], w, st) for _, w, st in _due_entries(words, states, _now(now))]


def review_items(words, states, now=None):
    """当前词书此刻的到期旧词；idx 是传入 words 的真实索引。"""
    return [{"kind": "review", "w": w, "st": st, "idx": idx}
            for idx, w, st in _due_entries(words, states, _now(now))]


def next_new(words, states, cursor):
    """兼容旧的单步新词 API，返回 (item, cursor)，不修改 states。

    此 API 不管理重试间隔；完整学习流程使用 StudyQueue。
    """
    i = max(0, int(cursor))
    while i < len(words):
        w = words[i]
        st = states.get(w["w"])
        if _is_new(st):
            return {"kind": "new", "w": w, "st": st, "idx": i}, i
        i += 1
    return None, i
