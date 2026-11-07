# -*- coding: utf-8 -*-
"""V2 大词库：175 本词书的并集（源顺序已由 extract_lists.py 保留）。

- needed = build/lists/*.txt 的并集
- 释义优先级：现有 bank 词条 > 有道(旧词) > ECDICT > 词书自带 gloss > ECDICT 纯文本兜底
- 难度 lvl(0-14)/b 沿用 V1.1 的分位算法（frq > bnc > 词形还原）
- 与 V1.1 一致：A–Z 排序、字段 w/ipa/pos/s/tags/frq/collins/raw/ph_raw/lvl/b

输出：data/bank.json、data/build_bank_v2.log、build/bank_dropped.txt
"""
import csv
import io
import json
import math
import os
import re
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_words as bw  # noqa: E402
import build_bank as bb  # noqa: E402

BUILD = os.path.join(ROOT, "build")
LISTS = os.path.join(BUILD, "lists")
GLOSS = os.path.join(BUILD, "gloss")
DATA = os.path.join(ROOT, "data")
BANK = os.path.join(DATA, "bank.json")
LOG = os.path.join(DATA, "build_bank_v2.log")
DROPPED = os.path.join(BUILD, "bank_dropped.txt")
BANDS = 15
CJK = re.compile(r"[\u4e00-\u9fff]")
ALIAS = re.compile(r"^.*?=\s*([a-z][a-z'\-]*)\s*$", re.I)
POS_LABELS = r"(?:n|v|vt|vi|adj|adv|prep|conj|pron|num|art|int|aux)"


def prep_translation(trans):
    """把 ECDICT 释义规整成 groups_from_ecdict 能吃的格式。"""
    t = (trans or "").replace("\\n", "\n")
    t = re.sub(r"\[[^\]]{1,8}\]", "", t)              # 去掉 [医][计] 这类领域标签
    t = re.sub(r"(?<=\.)\s*&\s*(?=(?:%s)\.)" % POS_LABELS, "\n", t)
    t = re.sub(r"(?<=\.)(?=(?:%s)\.\s)" % POS_LABELS, "\n", t)
    t = re.sub(r"^(%s)\.\s*\1\.\s*" % POS_LABELS, r"\1. ", t, flags=re.I)
    return t


def alias_target(trans, word):
    """'v.=acclimatize' 这类释义指向另一个拼写，取那个词的释义。"""
    m = ALIAS.match((trans or "").replace("\\n", " ").strip())
    if not m:
        return ""
    base = m.group(1).lower()
    return base if base != word else ""


def lemma_ipa(e, rows):
    m = re.search(r"(?:^|/)0:([^/]+)", (e or {}).get("exchange") or "")
    if not m:
        return ""
    lemma = m.group(1).strip().lower()
    if lemma and lemma != "" and lemma in rows:
        return (rows[lemma].get("phonetic") or "").strip()
    return ""


def load_lists():
    out = {}
    union = set()
    for fn in sorted(os.listdir(LISTS)):
        if not fn.endswith(".txt"):
            continue
        ws = [x.strip() for x in io.open(os.path.join(LISTS, fn), encoding="utf-8") if x.strip()]
        out[fn[:-4]] = ws
        union.update(ws)
    return out, union


def load_gloss():
    out = {}
    for fn in sorted(os.listdir(GLOSS)):
        if not fn.endswith(".json"):
            continue
        try:
            d = json.load(io.open(os.path.join(GLOSS, fn), encoding="utf-8"))
        except Exception:
            continue
        for w, v in d.items():
            if v.get("tr") and w not in out:
                out[w] = v
    return out


def load_old_bank():
    out = {}
    for x in json.load(io.open(BANK, encoding="utf-8")):
        out[x["w"]] = x
    return out


def load_ecdict_with_alias(needed):
    """第一遍取 needed 词条并记录拼写别名，第二遍补别名目标词的词条。"""
    rows = {}
    targets = set()
    csv.field_size_limit(10 ** 7)
    with io.open(bb.ECDICT, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            w = (row.get("word") or "").strip().lower()
            if not w or w in rows:
                continue
            if w in needed:
                rows[w] = {
                    "word": w,
                    "phonetic": (row.get("phonetic") or "").strip(),
                    "translation": (row.get("translation") or "").strip(),
                    "tag": (row.get("tag") or "").strip().split(),
                    "frq": (row.get("frq") or "").strip(),
                    "collins": (row.get("collins") or "").strip(),
                    "bnc": (row.get("bnc") or "").strip(),
                    "exchange": (row.get("exchange") or "").strip(),
                }
                at = alias_target(row.get("translation") or "", w)
                if at:
                    targets.add(at)
    with io.open(bb.ECDICT, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            w = (row.get("word") or "").strip().lower()
            if w in targets and w not in rows:
                rows[w] = {
                    "word": w,
                    "phonetic": (row.get("phonetic") or "").strip(),
                    "translation": (row.get("translation") or "").strip(),
                    "tag": (row.get("tag") or "").strip().split(),
                    "frq": (row.get("frq") or "").strip(),
                    "collins": (row.get("collins") or "").strip(),
                    "bnc": (row.get("bnc") or "").strip(),
                    "exchange": (row.get("exchange") or "").strip(),
                }
    return rows


def build_entries(needed, rows, old, gloss, raw):
    entries = []
    stat = {"reuse": 0, "youdao": 0, "ecd": 0, "gloss": 0, "plain": 0,
            "noipa": 0, "dropped": 0, "alias": 0, "short": 0,
            "dropped_words": [], "noipa_words": []}
    for w in sorted(needed):
        if len(w) < 2:  # a / i 这类单字母：卡面价值低，不收
            stat["short"] += 1
            continue
        o = old.get(w)
        if o and o.get("s"):
            entries.append({
                "w": w,
                "ipa": o.get("ipa") or "",
                "pos": o.get("pos") or [],
                "s": o.get("s"),
                "tags": o.get("tags") or [],
                "frq": bb.to_int(o.get("frq")),
                "collins": o.get("collins") or "",
                "raw": o.get("raw") or "",
                "ph_raw": o.get("ph_raw") or "",
            })
            stat["reuse"] += 1
            continue

        e = rows.get(w) or {"phonetic": "", "translation": "", "tag": [],
                            "frq": "", "collins": "", "bnc": "", "exchange": ""}
        y = raw.get(w) or {}
        trans = prep_translation(e["translation"])
        at = alias_target(e["translation"], w)
        if at and at in rows and rows[at]["translation"]:
            trans = prep_translation(rows[at]["translation"])
            stat["alias"] += 1
        pos, s = bb.senses_from(y.get("ec") or [], trans)
        src = "youdao" if (s and y) else "ecd"
        g = gloss.get(w) or {}
        if not (s and CJK.search(s)) and g.get("tr"):
            pos2, s2 = bb.senses_from([], prep_translation(g["tr"]))
            if s2 and CJK.search(s2):
                pos, s, src = pos2, s2, "gloss"
        if not (s and CJK.search(s)):
            s2 = bb.plain_senses(e, y)
            if s2 and CJK.search(s2):
                s, src = s2, "plain"
        if not (s and CJK.search(s)):
            stat["dropped"] += 1
            stat["dropped_words"].append(w)
            continue
        stat[src] += 1

        ipa = y.get("usphone") or y.get("ukphone") or e["phonetic"] or g.get("ipa") or ""
        if not ipa:
            ipa = lemma_ipa(e, rows)
        if not ipa:
            stat["noipa"] += 1
            stat["noipa_words"].append(w)
        entries.append({
            "w": w,
            "ipa": ipa,
            "pos": pos,
            "s": s,
            "tags": e["tag"],
            "frq": bb.to_int(e.get("frq")),
            "collins": e["collins"],
            "raw": e["translation"] or g.get("tr") or "",
            "ph_raw": e["phonetic"] or g.get("ipa") or "",
        })
    return entries, stat


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(obj, ensure_ascii=False, indent=0))
    for i in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, path)


def display_units(s):
    """卡面宽度估算：全角 2 单位、半角 1 单位（紧凑窗一行约 34 单位，两行 68）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def fit_two_lines(s, limit=62):
    """保证释义在紧凑窗里最多两行：先丢第二个释义，再截断。"""
    while display_units(s) > limit and "；" in s:
        s = s.rsplit("；", 1)[0]
    if display_units(s) > limit:
        out, u = [], 0
        for ch in s:
            w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if u + w > limit - 1:
                break
            out.append(ch)
            u += w
        s = "".join(out).rstrip("，；、 ,;") + "…"
    return s


def main():
    per_book, needed = load_lists()
    print("books=%d union=%d" % (len(per_book), len(needed)))
    gloss = load_gloss()
    old = load_old_bank()
    rows = load_ecdict_with_alias(needed)
    raw = bb.load_raw()
    print("ecdict_hit=%d gloss_hit=%d old_hit=%d" % (
        len(rows), len(gloss), len(old)))

    entries, stat = build_entries(needed, rows, old, gloss, raw)
    for x in entries:
        x["s"] = fit_two_lines(x["s"])
    missing = bb.assign_difficulty(entries, rows)
    entries.sort(key=lambda x: x["w"])
    write_json_atomic(BANK, entries)
    io.open(DROPPED, "w", encoding="utf-8").write("\n".join(stat["dropped_words"]) + "\n")
    io.open(os.path.join(BUILD, "bank_noipa.txt"), "w", encoding="utf-8").write(
        "\n".join(stat["noipa_words"]) + "\n")

    by_lvl = [0] * BANDS
    for x in entries:
        by_lvl[x["lvl"]] += 1
    n = len(entries)
    lines = [
        "V2 bank=%d（并集 %d，剔除无释义 %d，单字母 %d）" % (
            n, len(needed), stat["dropped"], stat["short"]),
        "复用 V1.1 bank=%d  有道补=%d  ECDICT=%d  词书 gloss 兜底=%d  纯文本兜底=%d  拼写别名归一=%d"
        % (stat["reuse"], stat["youdao"], stat["ecd"], stat["gloss"], stat["plain"], stat["alias"]),
        "缺音标=%d（全库统计）" % sum(1 for x in entries if not x["ipa"]),
        "难度缺失(frq/bnc/lemma 都没有)=%d" % missing,
        "每档词数: %s" % by_lvl,
        "文件大小=%.2f MB" % (os.path.getsize(BANK) / 1048576.0),
        "无释义剔除词: %s" % (" ".join(stat["dropped_words"][:40])),
    ]
    io.open(LOG, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("BANK %d dropped=%d short=%d size=%.2fMB noipa=%d" % (
        n, stat["dropped"], stat["short"], os.path.getsize(BANK) / 1048576.0, stat["noipa"]))
    print("reuse=%d youdao=%d ecd=%d gloss=%d plain=%d alias=%d" % (
        stat["reuse"], stat["youdao"], stat["ecd"], stat["gloss"], stat["plain"], stat["alias"]))


if __name__ == "__main__":
    main()

