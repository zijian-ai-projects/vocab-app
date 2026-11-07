# -*- coding: utf-8 -*-
"""词汇量测试：难度模型 + 阶梯自适应抽题 + 4 选 1 干扰项 + 能力估计 + 逐词掌握概率。

词汇量测试（v1.1，阶梯自适应）：
    大词库按难度分 15 档（每档约 1,015 词，lvl 存在 bank.json）
    从档 0 开始；连对 2 题升 1 档、连错 2 题降 1 档、单个对/错留在同档换词
    前 8 题"快速定位"：连对 2 题升 2 档；第一次答错后恢复正常 1 档
    50 题后沿用 3PL（猜测率 1/4）网格极大似然估 θ，词汇量 = Σ σ(θ−b)
"""
import math
import random
import re

GUESS = 0.25
SCALE = 0.9          # 词频分位 -> logit 的缩放
CLAMP = 3.2
KNOWN_THRESHOLD = 0.55   # 掌握概率高于这个就当已会，不进学习队列
BANDS = 15
TOP_LEVEL = BANDS - 1
FAST_N = 8               # 前 8 题快速定位


def sigmoid(x):
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def build_profile(words):
    """给每个词算难度 b（旧接口，仍用于少量离线脚本）。"""
    n = len(words)
    order = sorted(range(n), key=lambda i: (words[i].get("frq") or 10 ** 9, words[i]["w"]))
    bs = [0.0] * n
    for pos, idx in enumerate(order):
        q = (pos + 0.5) / n
        q = min(max(q, 0.01), 0.99)
        b = math.log(q / (1 - q)) * SCALE
        bs[idx] = max(-CLAMP, min(CLAMP, b))
    return bs


def p_correct(theta, b):
    return GUESS + (1 - GUESS) * sigmoid(theta - b)


def p_know(theta, b):
    return sigmoid(theta - b)


def sample_items(bs, k=50, seed=None):
    """旧接口：按难度分位均匀抽题（v1.0 用；保留给离线模拟）。"""
    rng = random.Random(seed)
    n = len(bs)
    order = sorted(range(n), key=lambda i: bs[i])
    picked, seen = [], set()
    for j in range(k):
        q = 0.12 + (0.98 - 0.12) * j / max(1, k - 1)
        idx = order[min(n - 1, int(n * q))]
        if idx not in seen:
            seen.add(idx)
            picked.append(idx)
    while len(picked) < k:
        idx = rng.randrange(n)
        if idx not in seen:
            seen.add(idx)
            picked.append(idx)
    rng.shuffle(picked)
    return picked


NO_ANSWER = "没有正确答案"


def make_options(words, idx, rng, bs=None, trap_prob=0.3):
    """三个释义 + 一个「没有正确答案」。

    有 30% 的题是陷阱题：三个释义全是错的，正确选项就是「没有正确答案」。
    返回 (选项列表, 正确项下标)。
    """
    def fmt(w):
        s = (w.get("s") or w.get("raw") or "").strip()
        pos = (w.get("pos") or [])
        # 卡面释义已经带词性前缀了（"adj.有益的…"），别再拼一次
        if pos and not re.match(r"^[a-z]{1,6}\.", s):
            return "%s %s" % (pos[0], s)
        return s

    word = words[idx]
    correct = fmt(word)
    trap = rng.random() < trap_prob
    need = 3 if trap else 2
    pos0 = (word.get("pos") or [""])[0]
    b0 = bs[idx] if bs else 0.0

    pool, back = [], []
    for j, w in enumerate(words):
        if j == idx:
            continue
        s = fmt(w)
        if not s or s == correct or s == NO_ANSWER:
            continue
        same_pos = pos0 and pos0 in (w.get("pos") or [])
        near = abs((bs[j] if bs else 0.0) - b0) <= 0.8
        (pool if (same_pos and near) else back).append(s)

    rng.shuffle(pool)
    rng.shuffle(back)
    distract = []
    for s in pool + back:
        if s == correct or s in distract:
            continue
        if distract and s[0] == correct[0] and len(distract) < need:
            continue
        distract.append(s)
        if len(distract) == need:
            break

    if trap:
        opts = distract + [NO_ANSWER]
        correct_idx = len(opts) - 1
    else:
        opts = distract + [correct, NO_ANSWER]
        correct_idx = len(opts) - 2

    order = list(range(len(opts)))
    rng.shuffle(order)
    shuffled = [opts[i] for i in order]
    return shuffled, order.index(correct_idx)


# ---------- 阶梯自适应 ----------
def new_session(seed=None):
    """一次测试的阶梯状态。"""
    return {"level": 0, "up": 0, "down": 0, "fast": True,
            "asked": [], "resp": [], "seed": seed if seed is not None else 0}


def step(sess, correct, answered):
    """按阶梯规则更新状态；answered = 含这道题在内已答题数。返回新的 level。"""
    if correct:
        sess["up"] += 1
        sess["down"] = 0
        if sess["up"] >= 2:
            up_step = 2 if (sess["fast"] and answered <= FAST_N) else 1
            sess["level"] = min(TOP_LEVEL, sess["level"] + up_step)
            sess["up"] = 0
            if sess["fast"] and answered >= FAST_N:
                sess["fast"] = False
    else:
        sess["down"] += 1
        sess["up"] = 0
        sess["fast"] = False
        if sess["down"] >= 2:
            sess["level"] = max(0, sess["level"] - 1)
            sess["down"] = 0
    return sess["level"]


def pick_idx(lvls, level, asked, rng):
    """在当前难度档里随机挑一个没做过的词；档抽空了就往相邻档扩。"""
    asked = set(asked)
    for d in range(BANDS):
        for lv in (level + d, level - d):
            if 0 <= lv < BANDS:
                cand = [i for i, x in enumerate(lvls) if x == lv and i not in asked]
                if cand:
                    return cand[rng.randrange(len(cand))]
    return rng.randrange(len(lvls))


def estimate_theta(bs, responses):
    """网格极大似然，返回 (theta, 标准误近似)。

    responses: 1 = 答对；0 = 四选一答错（可能是蒙的）；-1 = 点了「不知道」
    """
    best, best_ll = 0.0, -1e18
    lo, hi, step = -4.0, 4.0, 0.02
    t = lo
    while t <= hi + 1e-9:
        ll = 0.0
        for b, y in zip(bs, responses):
            if y < 0:                      # 不知道：直接用「不会」的概率
                q = min(max(1 - p_know(t, b), 1e-6), 1 - 1e-6)
                ll += math.log(q)
            else:
                p = p_correct(t, b)
                p = min(max(p, 1e-6), 1 - 1e-6)
                ll += math.log(p) if y else math.log(1 - p)
        if ll > best_ll:
            best_ll, best = ll, t
        t += step
    # 信息量 -> 标准误
    info = 0.0
    for b in bs:
        p = p_correct(best, b)
        dp = (1 - GUESS) * p_know(best, b) * (1 - p_know(best, b))
        info += (dp * dp) / max(p * (1 - p), 1e-9)
    se = 1.0 / math.sqrt(info) if info > 0 else 9.9
    return best, se


def knowledge(bs, theta):
    return [p_know(theta, b) for b in bs]


def vocab_estimate(probs):
    return sum(probs)


def vocab_at(bs, theta):
    return sum(p_know(theta, b) for b in bs)


def error_band(bs, theta, se):
    """θ 的 ±1SE 对应的词数区间。"""
    return vocab_at(bs, theta - se), vocab_at(bs, theta + se)


def split_known(probs, threshold=KNOWN_THRESHOLD):
    return [p >= threshold for p in probs]
