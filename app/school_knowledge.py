# -*- coding: utf-8 -*-
"""Optional cumulative school vocabulary assumptions, separate from memory records."""
from functools import lru_cache
import books

LEVELS = (("off", "关闭"), ("primary", "小学"),
          ("middle", "小初"), ("high", "小初高"))
BOOKS = ("xx-dg", "zk-dg", "gk-dg")


def normalize(value):
    return value if isinstance(value, str) and value in dict(LEVELS) else "off"


@lru_cache(maxsize=4)
def words(level):
    level = normalize(level)
    count = [key for key, _ in LEVELS].index(level)
    return frozenset(word for book in BOOKS[:count] for word in books.words(book))
