# -*- coding: utf-8 -*-
"""从 ECDICT 大表里抽出我们词表需要的字段，存成小索引。"""
import io, csv, json, os

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
SRC = r"D:\user\Documents\deepseek-harness\default-workspace\ECDICT\ecdict.csv"
XLS = os.path.join(ROOT, "data", "words_xls.json")
OUT = os.path.join(ROOT, "data", "ecdict_subset.json")

xls = json.load(io.open(XLS, encoding="utf-8"))
need = {}
for w in xls:
    need.setdefault(w["word"].lower(), w["word"])

got = {}
with io.open(SRC, encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        w = (row.get("word") or "").strip()
        lw = w.lower()
        if lw in need and lw not in got:
            got[lw] = {
                "word": w,
                "phonetic": (row.get("phonetic") or "").strip(),
                "translation": (row.get("translation") or "").strip(),
                "definition": (row.get("definition") or "").strip(),
                "collins": (row.get("collins") or "").strip(),
                "oxford": (row.get("oxford") or "").strip(),
                "tag": (row.get("tag") or "").strip(),
                "bnc": (row.get("bnc") or "").strip(),
                "frq": (row.get("frq") or "").strip(),
            }

with io.open(OUT, "w", encoding="utf-8") as f:
    json.dump(got, f, ensure_ascii=False)
print("hit=%d / need=%d -> %s" % (len(got), len(need), OUT))
