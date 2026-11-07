# -*- coding: utf-8 -*-
"""端到端校验：构造一个「认识前 60% 高频词」的虚拟用户，看估计值对不对。"""
import io, json, math, os, random, sys
sys.path.insert(0, r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\app")
import placement as pl

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
words = json.load(io.open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))
bs = pl.build_profile(words)

# 真实掌握：词频分位 q <= know_q 的词（越常见越可能认识）
order = sorted(range(len(bs)), key=lambda i: bs[i])
n = len(order)
L = []
for know_q, recog in ((0.60, 0.90), (0.80, 0.92), (0.40, 0.85), (0.90, 0.95)):
    true_known = set(order[:int(n * know_q)])
    rng = random.Random(42)
    ests, knowns, recall, precision = [], [], [], []
    for rep in range(30):
        items = pl.sample_items(bs, 50, seed=rep * 31 + 7)
        resp = []
        for i in items:
            if i in true_known:
                resp.append(1 if rng.random() < recog else 0)
            else:
                resp.append(1 if rng.random() < pl.GUESS else 0)
        th, se = pl.estimate_theta([bs[i] for i in items], resp)
        probs = pl.knowledge(bs, th)
        est_known = {i for i, p in enumerate(probs) if p >= pl.KNOWN_THRESHOLD}
        ests.append(th); knowns.append(sum(probs))
        tp = len(est_known & true_known)
        recall.append(tp / max(1, len(true_known)))
        precision.append(tp / max(1, len(est_known)))
    L.append("真实认识 %d 词(q<=%.2f)  ->  θ≈%.2f  预计认识 %.0f 词  筛选: 召回 %.1f%%  精确 %.1f%%" % (
        len(true_known), know_q, sum(ests) / len(ests), sum(knowns) / len(knowns),
        100 * sum(recall) / len(recall), 100 * sum(precision) / len(precision)))

# 全部 5556 词的 b 分布
for q in (0.1, 0.3, 0.5, 0.7, 0.9):
    i = order[int(n * q)]
    L.append("  q=%.1f -> b=%.2f (%s)" % (q, bs[i], words[i]["w"]))

io.open(os.path.join(ROOT, "data", "placement_check.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
