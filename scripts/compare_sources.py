# -*- coding: utf-8 -*-
"""ECDICT 释义 vs 有道释义 抽样对比。"""
import io, json, os, random, sys
sys.path.insert(0, r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\scripts")
ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
words = json.load(io.open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))
ydl = {}
for line in io.open(os.path.join(ROOT, "data", "raw_youdao.jsonl"), encoding="utf-8"):
    o = json.loads(line)
    if not o:
        continue
    ydl[o["word"].lower()] = o.get("ec") or []

random.seed(11)
L = []
for w in random.sample(words, 30):
    L.append("■ %-15s %-18s %s" % (w["w"], w["ipa"][:18], "/".join(w["pos"])))
    L.append("   ECDICT: %s" % w["s"])
    ec = ydl.get(w["w"].lower()) or []
    L.append("   有道  : %s" % (" | ".join(ec)[:160] if ec else "-"))
io.open(os.path.join(ROOT, "data", "compare_sources.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
