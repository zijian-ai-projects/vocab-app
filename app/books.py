# -*- coding: utf-8 -*-
"""词书 V2：三级目录 主类 → 分组 → 词书（+ 分组全选并集 / 教材分册）。

数据来自 data/books.json（schema 2，由 scripts/build_books_v2.py 生成）：
  mains[] → groups[] → union{id,count,words} + items[{id,name,display,series,count,words}]

对上层保持简单接口：get/words/size/name/path/all/默认书；
三级目录另给 mains()/groups()/items()。旧 V1.1 的 11 个词书 id 用 LEGACY 映射到
对应分组的「全选」并集，保证旧进度能落到同一批词上。
"""
import io
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 旧 V1.1 词书 id → V2 分组并集 id
LEGACY = {
    "xiaoxue": "xx-ci-all",
    "chuzhong": "zhongkao-all",
    "gaokao": "gaokao-all",
    "cet4": "cet4-all",
    "cet6": "cet6-all",
    "kaoyan": "kaoyan-all",
    "kaobo": "kaoyan-all",
    "ielts": "ielts-all",
    "toefl": "toefl-all",
    "gre": "gre-all",
}


def _load():
    with io.open(os.path.join(DATA, "books.json"), encoding="utf-8") as f:
        return json.load(f)


def _build(data):
    books = {}
    mains = []
    groups = {}
    for m in data.get("mains", []):
        mm = {"id": m["id"], "name": m["name"], "groups": []}
        for g in m.get("groups", []):
            u = g["union"]
            gid = g["id"]
            union_book = {
                "id": u["id"],
                "name": g.get("union_name") or (g["name"] + "（全选）"),
                "display": g.get("union_name") or (g["name"] + "（全选）"),
                "count": u["count"],
                "words": u["words"],
                "kind": "union",
                "type": "word",
                "series": "",
                "is_union": True,
                "group": gid,
                "main": m["id"],
                "path": [m["name"], g["name"]],
            }
            books[union_book["id"]] = union_book
            items = []
            for it in g.get("items", []):
                b = {
                    "id": it["id"],
                    "name": it["name"],
                    "display": it.get("display") or it["name"],
                    "count": it["count"],
                    "words": it["words"],
                    "kind": it.get("kind") or "",
                    "type": it.get("type") or "word",
                    "series": it.get("series") or "",
                    "is_union": False,
                    "group": gid,
                    "main": m["id"],
                    "path": [m["name"], g["name"]],
                }
                books[b["id"]] = b
                items.append(b)
            series = []
            for it in items:
                s = it.get("series") or ""
                if s and s not in series:
                    series.append(s)
            gg = {
                "id": gid,
                "name": g["name"],
                "main": m["id"],
                "union": union_book,
                "items": items,
                "series": series,
                "count": len(items),
            }
            groups[gid] = gg
            mm["groups"].append(gg)
        mains.append(mm)
    return books, mains, groups


_data = _load()
BY_ID, MAINS, GROUPS = _build(_data)
DEFAULT = "cet6-all" if "cet6-all" in BY_ID else next(iter(BY_ID))


def mains():
    return MAINS


def groups(main_id=None):
    if main_id is None:
        return [g for m in MAINS for g in m["groups"]]
    for m in MAINS:
        if m["id"] == main_id:
            return m["groups"]
    return []


def items(group_id):
    g = GROUPS.get(group_id)
    return g["items"] if g else []


def all():
    """扁平列表，供旧界面/自测遍历用。"""
    out = []
    for m in MAINS:
        for g in m["groups"]:
            out.append(g["union"])
            out.extend(g["items"])
    return out


def resolve(book_id):
    if book_id in BY_ID:
        return book_id
    return LEGACY.get(book_id, DEFAULT)


def get(book_id):
    return BY_ID[resolve(book_id)]


def words(book_id):
    return get(book_id)["words"]


def size(book_id):
    return get(book_id)["count"]


def name(book_id):
    b = get(book_id)
    return b["display"] or b["name"]


def path(book_id):
    b = get(book_id)
    return " · ".join(b["path"] + [b["display"]])
