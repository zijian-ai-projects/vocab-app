# -*- coding: utf-8 -*-
"""词书。

现在只有一本《六级词汇（乱序）》。以后加书：在 BOOKS 里加一项，并把同结构的
词表 json 放进 data/（字段与 words.json 一致），设置页和词书页会自动列出来。
"""
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

BOOKS = [
    {
        "id": "cet6",
        "name": "六级词汇（乱序）",
        "desc": "大学英语六级 · 5,556 词 · 乱序",
        "file": "words.json",
    },
]

DEFAULT = BOOKS[0]["id"]


def all():
    return BOOKS


def get(book_id):
    for b in BOOKS:
        if b["id"] == book_id:
            return b
    return BOOKS[0]


def path(book_id):
    return os.path.join(DATA, get(book_id)["file"])
