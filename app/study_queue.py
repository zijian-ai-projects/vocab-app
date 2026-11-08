# -*- coding: utf-8 -*-
"""当前词书的可持久化学习队列；不读取或写入任何文件。

words 已由调用方排好顺序，states 是跨书共享的记忆状态，record 是当前
词书的队列记录。两个 dict 均原地更新，调用方负责原子保存：
    {"cursor": 0, "new_count": 0, "pending": {}, "current": None}
pending 将词 key 映射到再次出现时所需的首次新词回答总数；current 只存
{"kind": ..., "key": ...}，因此重启或词书换序后仍能找到未回答的词。
额外 held_current（同样的结构或 None）保存被到期复习挂起的未答词；
last_retry（词 key 或 None）只用于书末提前重试的公平轮转。
"""
import time

try:                            # 同时支持 app.study_queue 与直接导入。
    from . import scheduler as sch
except ImportError:
    import scheduler as sch


_KINDS = ("new", "retry", "review")


def _count(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _has_answer(st):
    return bool(st and (_count(st.get("seen")) or _count(st.get("lapse"))))


class StudyQueue:
    """到期旧词优先；未答 new/retry 用 held_current 挂起后再恢复。

    新词忘记后隔 retry_gap 个「首次新词回答」重考（不是隔任意题数）。
    没有其它新词时允许提前重考，避免书末永久等待；last_retry 使多个
    提前重考的未知词公平轮转，不影响 ready retry 的目标计数/词书排序。
    等级、due、seen 和 lapse 的变化全部交给 scheduler，retry 仍然使用
    lv=0 的新词状态。
    """

    def __init__(self, words, states, record, retry_gap=3, known=None):
        if not isinstance(states, dict) or not isinstance(record, dict):
            raise TypeError("states and record must be shared dictionaries")
        gap = int(retry_gap)
        if gap <= 0:
            raise ValueError("retry_gap must be positive")
        self.words = list(words)
        self.states = states
        self.record = record
        self.retry_gap = gap
        self.known = known if known is not None else set()
        self._indices = {}
        for idx, w in enumerate(self.words):
            self._indices.setdefault(w["w"], idx)

        self.cursor = record.get("cursor", 0)
        record["new_count"] = _count(record.get("new_count", 0))
        record.setdefault("pending", {})
        if not isinstance(record["pending"], dict):
            raise TypeError("record.pending must be a dictionary")
        for key, target in list(record["pending"].items()):
            record["pending"][key] = _count(target)
        record.setdefault("current", None)
        record.setdefault("held_current", None)
        record.setdefault("last_retry", None)

    @property
    def cursor(self):
        return self.record["cursor"]

    @cursor.setter
    def cursor(self, value):
        self.record["cursor"] = min(len(self.words), _count(value))

    def _skip_known(self, key, st):
        # 显式状态或 pending 代表用户记录，优先于词汇量测试的估计。
        return key in self.known and not st and key not in self.record["pending"]

    def _sync_pending(self):
        pending = self.record["pending"]
        for key in list(pending):
            st = self.states.get(key)
            if st and not sch._is_new(st):
                # 同一词在其它词书中已认识/出库，旧 retry 就失效。
                pending.pop(key)
        for key in self._indices:
            st = self.states.get(key)
            if sch._is_new(st) and _has_answer(st):
                # 旧游标、换书或换序不得丢掉显式忘记而未认识的词。
                # 没有本书间隔记录时直接 ready，不伪造一次首次新词回答。
                pending.setdefault(key, self.record["new_count"])

    def _item(self, key, kind):
        idx = self._indices[key]
        return {"kind": kind, "w": self.words[idx],
                "st": self.states.get(key), "idx": idx}

    def _select(self, key, kind):
        self.record["current"] = {"kind": kind, "key": key}
        return self._item(key, kind)

    @staticmethod
    def _current_key(current):
        if not isinstance(current, dict):
            return None
        key = current.get("key")
        if key is None and isinstance(current.get("w"), dict):
            # 兼容调用方过去保存过完整 item 的记录。
            key = current["w"].get("w")
        return key

    def _reuse_current(self, now):
        current = self.record.get("current")
        key = self._current_key(current)
        kind = current.get("kind") if isinstance(current, dict) else None
        if key not in self._indices or kind not in _KINDS:
            self.record["current"] = None
            return None
        st = self.states.get(key)
        if kind == "review":
            if sch._is_learning(st) and st.get("due") is not None and st["due"] <= now:
                return self._select(key, kind)
        elif sch._is_new(st) and not self._skip_known(key, st):
            if kind == "retry" or key in self.record["pending"] or _has_answer(st):
                self.record["pending"].setdefault(key, self.record["new_count"])
                kind = "retry"
            return self._select(key, kind)
        self.record["current"] = None
        return None

    def _pending_order(self):
        # key 不在当前词书中时保留记录，但绝不加入本书队列。
        return sorted((target, self._indices[key], key)
                      for key, target in self.record["pending"].items()
                      if key in self._indices and sch._is_new(self.states.get(key)))

    def _next_new(self):
        n, start = len(self.words), self.cursor
        # 优先旧 cursor 后的词；尾部耗尽后补扫前缀，换序也不丢未学词。
        for indices in (range(start, n), range(0, start)):
            for idx in indices:
                w = self.words[idx]
                key = w["w"]
                st = self.states.get(key)
                if (sch._is_new(st) and key not in self.record["pending"]
                        and not self._skip_known(key, st)):
                    return key, idx
        return None

    def next(self, now=None):
        """取一题并保存 current；到期旧词优先，未答新词挂起后原样恢复。"""
        now = time.time() if now is None else now
        self._sync_pending()
        current = self._reuse_current(now)
        if current is not None and current["kind"] == "review":
            return current

        reviews = sch.review_items(self.words, self.states, now)
        if reviews:
            if current is not None:
                # next/startup 会优先复习；不前移 cursor、不增加 new_count，
                # 挂起的 new/retry 在所有到期旧词答完后继续原题。
                self.record["held_current"] = dict(self.record["current"])
            return self._select(reviews[0]["w"]["w"], "review")

        if current is not None:
            return current
        held = self.record.get("held_current")
        self.record["held_current"] = None
        if held is not None:
            self.record["current"] = held
            current = self._reuse_current(now)
            if current is not None:
                return current

        pending = self._pending_order()
        if pending and pending[0][0] <= self.record["new_count"]:
            return self._select(pending[0][2], "retry")

        candidate = self._next_new()
        if candidate is not None:
            key, idx = candidate
            self.cursor = idx
            return self._select(key, "new")

        self.cursor = len(self.words)
        if pending:
            # 书末没有首次新词可让计数前进。提前重试按词书轮转，避免多个
            # 未知词目标相同而第一个一直忘记时，永远看不到后面的未知词。
            last_idx = self._indices.get(self.record.get("last_retry"), -1)
            by_idx = sorted(pending, key=lambda entry: entry[1])
            choice = next((entry for entry in by_idx if entry[1] > last_idx), by_idx[0])
            return self._select(choice[2], "retry")
        return None

    def answer(self, item, remember: bool, now=None):
        """回答 next 返回的当前词，写 states，清 current，返回新状态。

        拒绝已回答或其它题的 stale item，避免重复计数；使用 states 中最新
        的状态而非 item.st 快照，保留跨书共享更新和所有自定义字段。
        """
        key = item["w"]["w"]
        kind = item["kind"]
        current = self.record.get("current")
        if (key not in self._indices or kind not in _KINDS
                or self._current_key(current) != key or current.get("kind") != kind):
            raise ValueError("answer must match the unanswered current item")

        before = self.states.get(key)
        first_new = (kind == "new" and sch._is_new(before) and not _has_answer(before)
                     and key not in self.record["pending"])
        before = before or sch.new_state(now)
        after = sch.on_remember(before, now) if remember else sch.on_forget(before, now)
        self.states[key] = after

        if first_new:
            self.record["new_count"] += 1
        if sch._is_new(after):
            self.record["pending"][key] = self.record["new_count"] + self.retry_gap
        else:
            self.record["pending"].pop(key, None)
        if kind == "new":
            self.cursor = self._indices[key] + 1
        elif kind == "retry":
            self.record["last_retry"] = key
        self.record["current"] = None
        return after

    def next_due_time(self, now=None):
        """当前词书最近的未来旧词 due；没有则 None。now 仅供固定时钟测试。"""
        now = time.time() if now is None else now
        dues = [st["due"] for key in self._indices
                for st in [self.states.get(key)]
                if sch._is_learning(st) and st.get("due") is not None and st["due"] > now]
        return min(dues) if dues else None
