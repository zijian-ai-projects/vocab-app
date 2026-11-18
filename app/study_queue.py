# -*- coding: utf-8 -*-
"""当前词书的可持久化学习队列；不读取或写入任何文件。

words 已由调用方排好顺序，states 是跨书共享的记忆状态，record 是当前
词书的队列记录。两个 dict 均原地更新，调用方负责原子保存：
    {"cursor": 0, "new_count": 0, "pending": {}, "current": None}
pending 将词 key 映射到再次出现时所需的首次新词回答总数；current 只存
{"kind": ..., "key": ...}，因此重启或词书换序后仍能找到未回答的词。
额外 held_current（同样的结构或 None）保存被到期复习挂起的未答词；
last_retry（词 key 或 None）兼容保留；书末不会绕过 pending 的计数目标。
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


def _valid_target(value):
    # Unknown persisted values are not deadlines; never coerce them into ready 0.
    return (type(value) in (int, float) and 0 <= value <= 9007199254740991
            and value % 1 == 0)


def _has_answer(st):
    return bool(st and (_count(st.get("seen")) or _count(st.get("lapse"))))


class StudyQueue:
    """到期旧词优先；未答 new/retry 用 held_current 挂起后再恢复。

    新词忘记后隔 retry_gap 个「首次新词回答」重考（不是隔任意题数）。
    等级、due、seen 和 lapse 的变化全部交给 scheduler，retry 仍然使用
    lv=0 的新词状态。

    known 是仅跳过无显式状态词的预测；excluded 是调用方已规范化的
    学校词 key 集合，暂停所有题型但不删除记忆或 pending。清空/替换
    excluded 后恢复；被暂停的未答题沿用 policy_held 保存其额外字段。
    """

    def __init__(self, words, states, record, retry_gap=4, known=None,
                 excluded=None):
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
        # Explicit school exclusions override *all* queue paths, unlike prediction.
        # Keep the supplied collection live so disabling it resumes saved work.
        self.excluded = excluded if excluded is not None else set()
        policy_held = record.get("policy_held", [])
        if not isinstance(policy_held, list) or any(not isinstance(item, dict) for item in policy_held):
            raise TypeError("record.policy_held must be a list of saved items")
        self._indices = {}
        for idx, w in enumerate(self.words):
            self._indices.setdefault(w["w"], idx)

        self.cursor = record.get("cursor", 0)
        record["new_count"] = _count(record.get("new_count", 0))
        record.setdefault("pending", {})
        if not isinstance(record["pending"], dict):
            raise TypeError("record.pending must be a dictionary")
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
        # Prediction is explicitly opt-in and never overrides scheduler records.
        return key in self.known and not st and key not in self.record["pending"]

    def _sync_pending(self):
        pending = self.record["pending"]
        for key in list(pending):
            if key in self.excluded:
                continue                 # Suspension must not erase a retry target.
            st = self.states.get(key)
            if st and not sch._is_new(st):
                # 同一词在其它词书中已认识/出库，旧 retry 就失效。
                pending.pop(key)
        for key in self._indices:
            if key in self.excluded:
                continue
            st = self.states.get(key)
            if sch._is_new(st) and _has_answer(st):
                # 旧游标、换书或换序不得丢掉显式忘记而未认识的词。
                # 没有本书间隔记录时直接 ready，不伪造一次首次新词回答。
                pending.setdefault(key, self.record["new_count"])

    def _item(self, key, kind):
        idx = self._indices[key]
        return {"kind": kind, "w": self.words[idx],
                "st": self.states.get(key), "idx": idx}

    def _select(self, key, kind, resume=False, saved=None):
        # A resumed due review may be found by the scheduler before the saved
        # list is visited. Restore its metadata rather than replacing it.
        if saved is None:
            held = self.record.get("held_current")
            if self._current_key(held) == key:
                saved = held
                self.record["held_current"] = None
            else:
                parked = self.record.get("policy_held", [])
                for entry in list(parked):
                    if self._current_key(entry) == key:
                        saved = entry
                        parked.remove(entry)
                        break
        # 恢复同 key 的合法 current/policy_held 时保留原字典的未知字段；
        # 规范内部字段才覆盖，不同 key 绝不串字段。
        current = (dict(saved) if isinstance(saved, dict)
                   and self._current_key(saved) == key else {})
        current["kind"] = kind
        current["key"] = key
        if kind == "new":
            if resume:
                current["resume"] = True
            else:
                current.pop("resume", None)
        else:
            current.pop("resume", None)
        self.record["current"] = current
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
        if key in self.excluded:
            self._park_policy_current()
            return None
        if key not in self._indices or kind not in _KINDS:
            self.record["current"] = None
            return None
        st = self.states.get(key)
        if kind == "review":
            if sch._is_learning(st) and st.get("due") is not None and st["due"] <= now:
                return self._select(key, kind, saved=current)
        elif sch._is_new(st) and not self._skip_known(key, st):
            if kind == "retry" or key in self.record["pending"] or _has_answer(st):
                self.record["pending"].setdefault(key, self.record["new_count"])
                kind = "retry"
                target = self.record["pending"][key]
                if not _valid_target(target) or target > self.record["new_count"]:
                    # Unknown deadlines and saved items cannot bypass the target.
                    self._park_policy_current()
                    return None
            return self._select(key, kind,
                                resume=bool(current.get("resume")) if kind == "new" else False,
                                saved=current)
        self.record["current"] = None
        return None

    def _pending_order(self):
        # key 不在当前词书中时保留记录，但绝不加入本书队列。
        return sorted((target, self._indices[key], key)
                      for key, target in self.record["pending"].items()
                      if key in self._indices and key not in self.excluded
                      and _valid_target(target) and sch._is_new(self.states.get(key)))

    def _next_new(self):
        n, start = len(self.words), self.cursor
        # 优先旧 cursor 后的词；尾部耗尽后补扫前缀，换序也不丢未学词。
        for indices in (range(start, n), range(0, start)):
            for idx in indices:
                w = self.words[idx]
                key = w["w"]
                st = self.states.get(key)
                if (key not in self.excluded and sch._is_new(st)
                        and key not in self.record["pending"]
                        and not self._skip_known(key, st)):
                    return key, idx
        return None

    def _park_policy_current(self):
        """An extra saved list avoids overwriting the existing held_current slot."""
        current = self.record.get("current")
        if isinstance(current, dict):
            held = self.record.setdefault("policy_held", [])
            copy = dict(current)
            if copy not in held:
                held.append(copy)
        self.record["current"] = None

    def _hold_current(self):
        """Suspend current without overwriting an earlier interrupted item."""
        current = self.record.get("current")
        if not isinstance(current, dict):
            return
        held = self.record.get("held_current")
        if isinstance(held, dict) and held != current:
            saved = self.record.setdefault("policy_held", [])
            if held not in saved:
                saved.append(dict(held))
        self.record["held_current"] = dict(current)
        self.record["current"] = None

    def _take_policy_held(self, now):
        held = self.record.get("policy_held", [])
        for entry in list(held):
            key = self._current_key(entry)
            if key not in self._indices or key in self.excluded:
                continue                 # Keep foreign and suspended saved items.
            self.record["current"] = dict(entry)
            current = self._reuse_current(now)
            if current is not None:
                if current["kind"] == "new":
                    self.record["current"]["resume"] = True
                held.remove(entry)
                return current
        self.record["current"] = None
        return None

    def _reviews(self, now):
        return [item for item in sch.review_items(self.words, self.states, now)
                if item["w"]["w"] not in self.excluded]

    def next(self, now=None):
        """取一题并保存 current；到期旧词优先，新词重试严格按计数间隔。"""
        now = time.time() if now is None else now
        held = self.record.get("held_current")
        if isinstance(held, dict) and self._current_key(held) in self.excluded:
            # Free the single review-interruption slot without losing its metadata.
            saved = self.record.setdefault("policy_held", [])
            if held not in saved:
                saved.append(dict(held))
            self.record["held_current"] = None
        self._sync_pending()
        current = self._reuse_current(now)
        if current is not None and current["kind"] == "review":
            return current

        reviews = self._reviews(now)
        if reviews:
            if current is not None:
                # next/startup 会优先复习；不前移 cursor、不增加 new_count，
                # 挂起的 new/retry 在所有到期旧词答完后继续原题。
                self._hold_current()
            return self._select(reviews[0]["w"]["w"], "review")

        if current is not None and current["kind"] == "retry":
            return current
        # Ready retries also beat saved fresh items; suspend rather than lose them.
        pending = self._pending_order()
        if pending and pending[0][0] <= self.record["new_count"]:
            if current is not None:
                self._hold_current()
            return self._select(pending[0][2], "retry")
        if current is not None:
            return current
        held = self.record.get("held_current")
        self.record["held_current"] = None
        if held is not None:
            self.record["current"] = held
            current = self._reuse_current(now)
            if current is not None:
                return current
        # A restored school-new item cannot delay an already eligible retry.
        current = self._take_policy_held(now)
        if current is not None:
            return current

        candidate = self._next_new()
        if candidate is not None:
            key, idx = candidate
            self.cursor = idx
            return self._select(key, "new")
        self.cursor = len(self.words)
        return None

    def answer(self, item, remember: bool, now=None):
        """回答 next 返回的当前词，写 states，清 current，返回新状态。

        拒绝已回答或其它题的 stale item，避免重复计数；使用 states 中最新
        的状态而非 item.st 快照，保留跨书共享更新和所有自定义字段。
        """
        now = time.time() if now is None else now
        key = item["w"]["w"]
        kind = item["kind"]
        current = self.record.get("current")
        if (key not in self._indices or key in self.excluded or kind not in _KINDS
                or self._current_key(current) != key or current.get("kind") != kind):
            raise ValueError("answer must match the unanswered current item")

        resume = bool(isinstance(current, dict) and current.get("resume"))
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
        if kind == "new" and not resume:
            self.cursor = self._indices[key] + 1
        elif kind == "retry":
            self.record["last_retry"] = key
        if "policy_held" in self.record:
            self.record["policy_held"][:] = [
                saved for saved in self.record["policy_held"]
                if self._current_key(saved) != key]
        self.record["current"] = None
        return after

    def next_due_time(self, now=None):
        """当前词书最近的未来旧词 due；没有则 None。now 仅供固定时钟测试。"""
        now = time.time() if now is None else now
        dues = [st["due"] for key in self._indices
                for st in [self.states.get(key)]
                if key not in self.excluded and sch._is_learning(st)
                and st.get("due") is not None and st["due"] > now]
        return min(dues) if dues else None
