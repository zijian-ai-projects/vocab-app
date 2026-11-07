# -*- coding: utf-8 -*-
"""门槛取舍：不同 KNOWN_THRESHOLD 下，跳过多少、准不准。"""
import io, json, os, random, sys
sys.path.insert(0, r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\app")
import placement as pl

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
words = json.load(io.open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))
bs = pl.build_profile(words)
order = sorted(range(len(bs)), key=lambda i: bs[i])
n = len(order)
L = []

for know_q, recog in ((0.60, 0.90), (0.85, 0.92)):
    true_known = set(order[:int(n * know_q)])
    L.append("\n=== 真实认识 %d 词（%.0f%%） ===" % (len(true_known), 100 * know_q))
    L.append("%-8s %-10s %-12s %-12s %-12s" % ("门槛", "跳过", "跳过里真会的", "会的被跳过", "要学"))
    rng = random.Random(7)
    for thr in (0.40, 0.50, 0.60, 0.70, 0.80, 0.85):
        skip, tp, tot_skip, tot_known = 0, 0, 0, len(true_known) * 30
        for rep in range(30):
            items = pl.sample_items(bs, 50, seed=rep * 17 + 1)
            resp = []
            for i in items:
                if i in true_known:
                    resp.append(1 if rng.random() < recog else 0)
                else:
                    resp.append(1 if rng.random() < pl.GUESS else 0)
            th, _ = pl.estimate_theta([bs[i] for i in items], resp)
            probs = pl.knowledge(bs, th)
            s = {i for i, p in enumerate(probs) if p >= thr}
            skip += len(s); tot_skip += len(s); tp += len(s & true_known)
        L.append("%-8.2f %-10d %-12.1f%% %-12.1f%% %-12d" % (
            thr, skip // 30, 100.0 * tp / max(1, tot_skip),
            100.0 * tp / max(1, tot_known), 5556 - skip // 30))

io.open(os.path.join(ROOT, "data", "threshold_sim.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
