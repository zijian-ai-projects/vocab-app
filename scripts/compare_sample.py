# -*- coding: utf-8 -*-
"""对比：xls 原始释义 vs 有道简明释义，并给出卡面短释义草案。"""
import io, json, os, re

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
xls = json.load(io.open(os.path.join(ROOT, "data", "words_xls.json"), encoding="utf-8"))
raw = {}
for line in io.open(os.path.join(ROOT, "data", "raw_youdao.jsonl"), encoding="utf-8"):
    o = json.loads(line)
    raw.setdefault(o["word"], o)

L = []
errc = 0
for w in xls:
    o = raw.get(w["word"])
    if not o:
        continue
    L.append("■ %-16s  音标 %s / %s" % (w["word"], o.get("usphone", ""), o.get("ukphone", "")))
    L.append("   xls : %s  [%s]" % (w["meaning_raw"], w["phonetic_raw"]))
    if "error" in o:
        errc += 1
        L.append("   有道: ERROR %s" % o["error"])
    else:
        for e in o["ec"]:
            L.append("   有道: %s" % e)
    L.append("")

L.append("fetched=%d errors=%d" % (sum(1 for w in xls if w["word"] in raw), errc))
io.open(os.path.join(ROOT, "data", "compare_40.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
