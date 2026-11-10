# -*- coding: utf-8 -*-
"""学习安排与全局自然日新词账本；只操作调用方共享字典，不读写文件。

一次首次实际作答即引入新词，认识/不认识都计入；展示、重试与复习不计。
review_first 不限制新词，但仍记账；daily_new_first 只决定何时优先清理到期复习。
"""
import datetime as dt
import time

REVIEW_FIRST = "review_first"
DAILY_NEW_FIRST = "daily_new_first"
DEFAULTS = {"mode": REVIEW_FIRST, "daily_new": 20}
MAX_DAILY_NEW = 999


def normalize_settings(raw=None):
    out = dict(raw) if isinstance(raw, dict) else {}
    if out.get("mode") not in (REVIEW_FIRST, DAILY_NEW_FIRST):
        out["mode"] = REVIEW_FIRST
    value = out.get("daily_new", DEFAULTS["daily_new"])
    try:
        if isinstance(value, bool):
            raise ValueError("boolean is not a word limit")
        number = int(value)
        if number != value and not (isinstance(value, str) and str(number) == value.strip()):
            raise ValueError("not an integer")
        if not 0 <= number <= MAX_DAILY_NEW:
            raise ValueError("out of range")
    except (TypeError, ValueError, OverflowError):
        number = DEFAULTS["daily_new"]
    out["daily_new"] = number
    return out


def validate_ledger(ledger):
    if not isinstance(ledger, dict):
        raise ValueError("daily_new_ledger must be a dictionary")
    days = ledger.get("days", {})
    if not isinstance(days, dict):
        raise ValueError("daily_new_ledger.days must be a dictionary")
    for day, words in days.items():
        try:
            if not isinstance(day, str) or dt.date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid day")
        except (TypeError, ValueError):
            raise ValueError("daily_new_ledger contains an invalid local date")
        if not isinstance(words, list) or any(not isinstance(w, str) or not w.strip() for w in words):
            raise ValueError("daily_new_ledger words must be stable nonempty string keys")
    return True


def _timestamp(now):
    return time.time() if now is None else float(now)


def local_day(now=None):
    return dt.datetime.fromtimestamp(_timestamp(now)).date().isoformat()


class LearningPolicy:
    def __init__(self, settings, ledger):
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dictionary")
        validate_ledger(ledger)
        self.settings = settings
        self.ledger = ledger
        # Missing containers are created, but existing dates/unknown fields are never erased.
        ledger.setdefault("schema", 1)
        ledger.setdefault("days", {})

    @property
    def daily_new_first(self):
        return self.settings.get("mode") == DAILY_NEW_FIRST

    @property
    def limit(self):
        return normalize_settings(self.settings)["daily_new"]

    def learned_today(self, now=None):
        return len(set(self.ledger["days"].get(local_day(now), [])))

    def remaining(self, now=None):
        return max(0, self.limit - self.learned_today(now))

    def allows_new(self, now=None):
        return True

    def should_review_before_new(self, now=None):
        return self.daily_new_first and self.remaining(now) <= 0

    def introduce_new(self, key, now=None):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("A stable nonempty word key is required")
        day = local_day(now)
        words = self.ledger["days"].setdefault(day, [])
        if key in words:
            return False
        words.append(key)
        return True

    def next_day_time(self, now=None):
        today = dt.datetime.fromtimestamp(_timestamp(now)).date()
        # Build the next local midnight, not now+24h; natural days survive DST changes.
        tomorrow = today + dt.timedelta(days=1)
        return dt.datetime.combine(tomorrow, dt.time.min).timestamp()
