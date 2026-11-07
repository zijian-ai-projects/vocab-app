# -*- coding: utf-8 -*-
"""词书：从 data/books.json 读取。

每本书 = 一份 A–Z 顺序的单词列表（数据只存"顺序"）；乱序在读取层用 seed 洗牌，
不写第二份数据。加书：改 scripts/build_books.py 重新生成 books.json。
"""
import io
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DEFAULT = "cet6"


def _load():
    path = os.path.join(DATA, "books.json")
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


BOOKS = _load()
_BY_ID = {b["id"]: b for b in BOOKS}
DEFAULT = "cet6" if "cet6" in _BY_ID else BOOKS[0]["id"]


def all():
    return BOOKS


def get(book_id):
    return _BY_ID.get(book_id) or _BY_ID[DEFAULT]


def words(book_id):
    return get(book_id)["words"]


def size(book_id):
    return get(book_id)["count"]
