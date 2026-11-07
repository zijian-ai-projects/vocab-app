# -*- coding: utf-8 -*-
"""检查卡面短释义的整体质量。"""
import io, json, os, random

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
words = json.load(io.open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))
L = []
n = len(words)
lens = sorted(len(w["s"]) for w in words)
L.append("total=%d 短释义字数 min=%d p50=%d p90=%d p99=%d max=%d" %
         (n, lens[0], lens[n // 2], lens[int(n * .9)], lens[int(n * .99)], lens[-1]))
noipa = sum(1 for w in words if not w["ipa"])
L.append("缺音标: %d" % noipa)

random.seed(7)
L.append("\n== 随机 25 条 ==")
for w in random.sample(words, 25):
    L.append("%-16s %-20s %s" % (w["w"], w["ipa"][:20], w["s"]))

L.append("\n== 最长的 20 条 ==")
for w in sorted(words, key=lambda x: -len(x["s"]))[:20]:
    L.append("%-16s %-20s %s" % (w["w"], w["ipa"][:20], w["s"]))

L.append("\n== 仍以原释义兜底的 45 条 ==")
for w in words:
    if w["s"] == w["raw"][:14]:
        L.append("%-16s %s" % (w["w"], w["raw"][:40]))

io.open(os.path.join(ROOT, "data", "quality.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
