# -*- coding: utf-8 -*-
"""排期引擎：王江涛时间表的 9 个节点，落到每个单词自己的状态上。

节点：5min, 30min, 12h, 1d, 2d, 4d, 7d, 15d, 30d
lv = 下一个要走的节点下标；lv==9 表示走完 9 遍，出库。
"""
import time

MIN = 60
HOUR = 3600
DAY = 86400

LEVELS = [5 * MIN, 30 * MIN, 12 * HOUR, 1 * DAY, 2 * DAY, 4 * DAY, 7 * DAY, 15 * DAY, 30 * DAY]
LEVEL_NAMES = ["5分钟", "30分钟", "12小时", "1天", "2天", "4天", "7天", "15天", "30天"]
MASTERED = 9
RELEARN = 10 * MIN          # 不记得后 10 分钟回炉
SESSION_RETRY = 2           # 连续不记得几次就当场重考
# 不进新词队列的状态：已出库 / 已掌握 / 已开始学 / 测试判定为会
DONE = ("retired", "mastered", "learning", "known")


def new_state(now=None):
    now = now or time.time()
    return {"lv": 0, "due": now + LEVELS[0], "seen": 0, "lapse": 0, "streak": 0, "st": "new"}


def on_remember(st, now=None):
    """点「记得」：前进一个节点。"""
    now = now or time.time()
    st = dict(st)
    st["seen"] = st.get("seen", 0) + 1
    st["streak"] = 0
    lv = st.get("lv", 0) + 1
    st["lv"] = lv
    st["st"] = "learning"
    if lv >= MASTERED:
        st["st"] = "mastered"
        st["due"] = None
    else:
        st["due"] = now + LEVELS[lv]
    return st


def on_forget(st, now=None):
    """点「不记得」：后退一个节点，10 分钟后再考；连续两次以上则当场重考。"""
    now = now or time.time()
    st = dict(st)
    st["seen"] = st.get("seen", 0) + 1
    st["lapse"] = st.get("lapse", 0) + 1
    st["streak"] = st.get("streak", 0) + 1
    st["lv"] = max(0, st.get("lv", 0) - 1)
    st["due"] = now + RELEARN
    st["st"] = "learning"
    st["retry_now"] = st["streak"] >= SESSION_RETRY
    return st


def on_fuzzy(st, now=None):
    """点「模糊」：既不前进也不后退，只是把下次复习提前一个节点。"""
    now = now or time.time()
    st = dict(st)
    st["seen"] = st.get("seen", 0) + 1
    st["streak"] = 0
    lv = max(0, st.get("lv", 0))
    st["st"] = "learning"
    st["due"] = now + LEVELS[max(0, lv - 1)]
    return st


def on_retire(st):
    """点「不再出现」。"""
    st = dict(st)
    st["st"] = "retired"
    st["due"] = None
    return st


def due_queue(words, states, now=None):
    """到期复习队列，最该复习的排前面。"""
    now = now or time.time()
    out = []
    for w in words:
        st = states.get(w["w"])
        if not st or st.get("st") in ("retired", "mastered", "known"):
            continue
        if st.get("due") is not None and st["due"] <= now:
            out.append((st["due"], w, st))
    out.sort(key=lambda t: t[0])
    return out


def review_items(words, states, now=None):
    """本次到期要复习的词（不设上限）。"""
    return [{"kind": "review", "w": w, "st": st, "idx": -1}
            for _, w, st in due_queue(words, states, now)]


def next_new(words, states, cursor):
    """取下一个还没学过的词（自由学习：一次只取一个）。

    返回 (item, 新 cursor)；没有更多词时返回 (None, cursor)。
    """
    i = cursor
    while i < len(words):
        w = words[i]
        st = states.get(w["w"])
        if st and st.get("st") in DONE:
            i += 1
            continue
        return {"kind": "new", "w": w, "st": st, "idx": i}, i
    return None, i
