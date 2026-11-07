# -*- coding: utf-8 -*-
"""蒙特卡洛：验证阶梯自适应测试的估值偏差 / MAE / 误差带覆盖率。

假人按真实能力 θ_true 作答：P(答对)=0.25+0.75σ(θ−b)（与模型一致），
跑 50 题阶梯后估计 θ̂，比较 vocab_at(θ̂) 与 vocab_at(θ_true)。
"""
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))
import placement as pl

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "adaptive_sim.txt")
N_SIM = 60
QUIZ_N = 50


def run(true_theta, seed):
    rng = random.Random(seed)
    sess = pl.new_session(seed=seed)
    asked = set()
    bs_asked, resp = [], []
    for n in range(QUIZ_N):
        lv = sess["level"]
        cand = [i for i in bands[lv] if i not in asked]
        if not cand:
            cand = [i for i in range(len(bs)) if i not in asked]
        idx = cand[rng.randrange(len(cand))]
        asked.add(idx)
        sess["asked"].append(idx)
        b = bs[idx]
        ok = rng.random() < pl.p_correct(true_theta, b)
        resp.append(1 if ok else 0)
        bs_asked.append(b)
        pl.step(sess, ok, n + 1)
    theta, se = pl.estimate_theta(bs_asked, resp)
    est = pl.vocab_at(bs, theta)
    true_v = pl.vocab_at(bs, true_theta)
    lo, hi = pl.error_band(bs, theta, se * 1.5)
    return est, true_v, lo, hi, theta


bank = json.load(io.open(os.path.join(DATA, "bank.json"), encoding="utf-8"))
bs = [x["b"] for x in bank]
lvls = [x["lvl"] for x in bank]
bands = [[] for _ in range(15)]
for i, lv in enumerate(lvls):
    bands[lv].append(i)
lines = ["阶梯自适应测试模拟（%d 次/档，50 题）" % N_SIM, ""]
lines.append("%8s %10s %10s %9s %9s %8s %8s" %
             ("θ_true", "真实词汇量", "平均估计", "平均偏差", "MAE", "RMSE", "区间覆盖"))
total_mae = []
for th in (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0):
    errs, cover = [], 0
    ests = []
    true_v = pl.vocab_at(bs, th)
    for k in range(N_SIM):
        est, tv, lo, hi, th_hat = run(th, seed=1000 + k)
        errs.append(est - true_v)
        ests.append(est)
        se_err = (hi - lo) / 2.0 / max(1, est) * 100.0
        err = max(4.0, min(40.0, se_err))
        if est * (1 - err / 100.0) <= true_v <= est * (1 + err / 100.0):
            cover += 1
    mae = sum(abs(e) for e in errs) / len(errs)
    rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5
    total_mae.append(mae)
    lines.append("%8.1f %10s %10s %9s %9s %8s %8s" %
                 (th, format(int(round(true_v)), ","), format(int(round(sum(ests) / len(ests))), ","),
                  format(int(round(sum(errs) / len(errs))), ","), format(int(round(mae)), ","),
                  format(int(round(rmse)), ","), "%d%%" % (100 * cover // N_SIM)))

lines.append("")
lines.append("平均 MAE = %s 词（50 题 / 3.5 万词库，理论精度约 ±1,400 词/1SE；目标 ≤ 1,800）"
             % format(int(round(sum(total_mae) / len(total_mae))), ","))
io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("WROTE", OUT)
