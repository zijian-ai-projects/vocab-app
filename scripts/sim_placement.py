# -*- coding: utf-8 -*-
"""模拟评估：给定真实 θ，按模型生成 50 题作答，看估出来的 θ 和筛选准不准。"""
import io, json, math, os, random, sys
sys.path.insert(0, r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\app")
import placement as pl

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
words = json.load(io.open(os.path.join(ROOT, "data", "words.json"), encoding="utf-8"))
bs = pl.build_profile(words)
L = ["n=%d  b范围=[%.2f, %.2f]" % (len(bs), min(bs), max(bs))]

rng = random.Random(1)
L.append("\n%-6s %-8s %-8s %-8s %-8s %-8s" % ("真θ", "平均估θ", "平均误差", "SE", "认识数", "筛选准确率"))
for true_theta in (-0.5, 0.5, 1.0, 1.5, 2.0, 2.5):
    ests, errs, ses, accs, knowns = [], [], [], [], []
    for rep in range(40):
        items = pl.sample_items(bs, 50, seed=rep * 7 + 3)
        resp = []
        for idx in items:
            p = pl.p_correct(true_theta, bs[idx])
            resp.append(1 if rng.random() < p else 0)
        th, se = pl.estimate_theta([bs[i] for i in items], resp)
        ests.append(th); errs.append(abs(th - true_theta)); ses.append(se)
        probs = pl.knowledge(bs, th)
        true_known = [pl.p_know(true_theta, b) >= 0.85 for b in bs]
        est_known = [p >= 0.85 for p in probs]
        acc = sum(1 for a, b in zip(true_known, est_known) if a == b) / len(bs)
        accs.append(acc); knowns.append(sum(est_known))
    L.append("%-6.1f %-8.2f %-8.2f %-8.2f %-8d %-8.1f%%" % (
        true_theta, sum(ests) / len(ests), sum(errs) / len(errs),
        sum(ses) / len(ses), sum(knowns) // len(knowns), 100.0 * sum(accs) / len(accs)))

L.append("\n不同门槛下「把会做的当成不会」和「把不会的当成会」的比例（真θ=1.5）：")
true_theta = 1.5
for thr in (0.7, 0.8, 0.85, 0.9, 0.95):
    fp = fn = tot_known = tot_unknown = 0
    for rep in range(60):
        items = pl.sample_items(bs, 50, seed=rep * 13 + 5)
        resp = [1 if rng.random() < pl.p_correct(true_theta, bs[i]) else 0 for i in items]
        th, _ = pl.estimate_theta([bs[i] for i in items], resp)
        for j, b in enumerate(bs):
            est = pl.p_know(th, b) >= thr
            true = pl.p_know(true_theta, b) >= 0.85
            if true and not est:
                fn += 1
            if not true and est:
                fp += 1
            tot_known += true
            tot_unknown += (not true)
    L.append("  门槛%.2f  漏判(会→学) %.1f%%   误判(不会→跳过) %.1f%%" %
             (thr, 100.0 * fn / tot_known, 100.0 * fp / tot_unknown))

io.open(os.path.join(ROOT, "data", "placement_sim.txt"), "w", encoding="utf-8").write("\n".join(L))
print("OK")
