# -*- coding: utf-8 -*-
"""看看词频分布，决定难度标尺怎么定。"""
import io, json, os

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
words = json.load(io.open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))
n = len(words)
frq = [w["frq"] for w in words]
zero = sum(1 for f in frq if not f)
L = ["total=%d  frq=0: %d (%.1f%%)" % (n, zero, 100.0 * zero / n)]
pos = sorted(f for f in frq if f)
for p in (0, 5, 10, 25, 50, 75, 90, 95, 99, 100):
    idx = int(len(pos) * p / 100.0) - 1 if p else 0
    idx = max(0, min(len(pos) - 1, idx))
    L.append("  p%-3d = %d" % (p, pos[idx]))

tags = {}
for w in words:
    for t in w["tags"]:
        tags[t] = tags.get(t, 0) + 1
L.append("tags: %r" % sorted(tags.items(), key=lambda x: -x[1]))

# 按词频排序后，几个位置上的词长什么样
order = sorted(range(n), key=lambda i: (words[i]["frq"] if words[i]["frq"] else 10 ** 9))
for p in (1, 10, 25, 50, 75, 90, 99):
    i = int(n * p / 100.0)
    i = min(i, n - 1)
    w = words[order[i]]
    L.append("  q=%.2f  %-16s frq=%-7d %s" % (p / 100.0, w["w"], w["frq"], w["s"][:30]))

io.open(os.path.join(ROOT, "data", "frq.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
