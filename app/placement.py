# -*- coding: utf-8 -*-
"""词汇量测试：难度模型 + 抽题 + 4 选 1 干扰项 + 能力估计 + 逐词掌握概率

模型（简化 3PL，猜测率固定 1/4）：
    每个词有难度 b_i（由词频排名换算成 logit 尺度）
    P(答对) = c + (1-c) * sigmoid(θ - b_i),  c = 0.25
    对 50 题做极大似然，估出 θ；再算每个词的掌握概率 σ(θ - b_i)。
"""
import math
import random
import re

GUESS = 0.25
SCALE = 0.9          # 词频分位 -> logit 的缩放
CLAMP = 3.2
KNOWN_THRESHOLD = 0.55   # 掌握概率高于这个就当已会，不进学习队列


def sigmoid(x):
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def build_profile(words):
    """给每个词算难度 b，返回与 words 等长的列表。"""
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
    """按难度分位抽题：从偏易到最难均匀铺开，避免全抽到会/不会的。"""
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
    # 不足则随机补
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


def split_known(probs, threshold=KNOWN_THRESHOLD):
    return [p >= threshold for p in probs]
