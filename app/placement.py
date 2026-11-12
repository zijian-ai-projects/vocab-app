# -*- coding: utf-8 -*-
"""V1.4 placement core: Bayesian ability estimation and deterministic sampling."""
import hashlib
import math
import random
import re
from functools import lru_cache
from heapq import nsmallest

GUESS = 0.25
SCALE = 0.9
CLAMP = 3.2
KNOWN_THRESHOLD = 0.55
BANDS = 15
TOP_LEVEL = BANDS - 1
FAST_N = 8
NO_ANSWER = "没有正确答案"
GRID_MIN = -6.0
GRID_MAX = 6.0
GRID_STEP = 0.02
PRIOR_SD = 2.0
TRAP_PROB = 0.25


def sigmoid(x):
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def build_profile(words):
    n = len(words)
    if not n:
        return []
    order = sorted(range(n), key=lambda i: (words[i].get("frq") or 10 ** 9, words[i].get("w", "")))
    bs = [0.0] * n
    for pos, idx in enumerate(order):
        q = min(max((pos + 0.5) / n, 0.01), 0.99)
        bs[idx] = max(-CLAMP, min(CLAMP, math.log(q / (1 - q)) * SCALE))
    return bs


def p_correct(theta, b):
    return GUESS + (1 - GUESS) * sigmoid(theta - b)


def p_know(theta, b):
    return sigmoid(theta - b)


def sample_items(bs, k=50, seed=None):
    rng = random.Random(seed)
    n = len(bs)
    if n == 0 or k <= 0:
        return []
    order = sorted(range(n), key=lambda i: bs[i])
    if k >= n:
        result = list(order)
        rng.shuffle(result)
        return result
    points = [min(n - 1, int(n * (0.12 + 0.86 * j / max(1, k - 1)))) for j in range(k)]
    selected = list(dict.fromkeys(order[j] for j in points))
    remaining = [i for i in order if i not in set(selected)]
    rng.shuffle(remaining)
    selected.extend(remaining[:k - len(selected)])
    rng.shuffle(selected)
    return selected


def _sense(word):
    text = str(word.get("s") or word.get("raw") or "").strip()
    return _sense_text(text)


@lru_cache(maxsize=65536)
def _sense_text(text):
    # Cache by text, not by the mutable word record: editing a meaning naturally
    # gets a new cache key. The bounded cache keeps repeated questions cheap.
    text = re.sub(r"^[a-z]{1,6}\.\s*", "", text, flags=re.I)
    # Keep concise senses and discard duplicate/empty fragments.
    parts = re.split(r"[;；]|\s*/\s*|[。]", text)
    unique = []
    for part in parts:
        part = part.strip(" ，,、")
        if part and part not in unique:
            unique.append(part)
        if len(unique) == 2:
            break
    return "；".join(unique)


def _stable_id(word, idx):
    identity = str(word.get("w") or word.get("id") or idx)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def make_item(words, idx, rng=None, bs=None, trap_prob=TRAP_PROB):
    """Return stable keyed options A-D, or None if three plausible options cannot be built."""
    if idx < 0 or idx >= len(words):
        return None
    rng = rng or random.Random(0)
    target = words[idx]
    correct_sense = _sense(target)
    if not correct_sense:
        return None
    target_id = _stable_id(target, idx)
    pos = target.get("pos") or []
    pos0 = pos[0] if pos else ""
    target_b = bs[idx] if bs is not None and idx < len(bs) else 0.0
    senses = {}
    for j, word in enumerate(words):
        if j == idx:
            continue
        sense = _sense(word)
        if not sense or sense == correct_sense or sense == NO_ANSWER:
            continue
        sid = _stable_id(word, j)
        senses.setdefault(sense, (sid, word, j))
    candidates = nsmallest(24, senses.values(), key=lambda row: (
        0 if pos0 and pos0 in (row[1].get("pos") or []) else 1,
        abs((bs[row[2]] if bs is not None and row[2] < len(bs) else 0.0) - target_b), row[0]))
    if len(candidates) < 2:
        return None
    # Avoid semantic duplicates and ambiguous senses that collide after normalization.
    candidates = candidates[:max(2, min(len(candidates), 24))]
    trap = rng.random() < trap_prob
    distractor_count = 3 if trap else 2
    if len(candidates) < distractor_count:
        return None
    distractors = candidates[:]
    rng.shuffle(distractors)
    chosen = distractors[:distractor_count]
    if trap:
        payloads = [(_sense(row[1]), row[0]) for row in chosen]
    else:
        payloads = [(correct_sense, target_id)] + [(_sense(row[1]), row[0]) for row in chosen]
    # Three answer positions are A-C; D always means no correct answer.
    rng.shuffle(payloads)
    option_records = []
    correct_index = -1
    for slot, (text, item_id) in zip("ABC", payloads):
        option_records.append({"key": slot, "text": text, "item_id": item_id})
        if not trap and item_id == target_id:
            correct_index = len(option_records) - 1
    option_records.append({"key": "D", "text": NO_ANSWER, "item_id": "none"})
    if trap:
        correct_index = 3
    return {"item_id": target_id, "word": str(target.get("w") or ""),
            "options": option_records, "correct_key": "ABCD"[correct_index],
            "correct_index": correct_index, "trap": trap}


def make_options(words, idx, rng, bs=None, trap_prob=TRAP_PROB):
    """Compatibility API returning four option strings and correct numeric index."""
    item = make_item(words, idx, rng, bs, trap_prob)
    if item is None:
        return None, None
    return [option["text"] for option in item["options"]], item["correct_index"]


def new_session(seed=None):
    return {"level": 0, "up": 0, "down": 0, "wrong_streak": 0, "fast": True,
            "asked": [], "resp": [], "seed": seed if seed is not None else 0}


def step(sess, correct, answered, response=None):
    """Update level and rigor-like streak state; unknown pauses rather than clears streak."""
    if response is None:
        response = 1 if correct else 0
    if response < 0:
        return sess["level"]
    if correct:
        sess["up"] = min(105, sess.get("up", 0) + 1)
        sess["down"] = 0
        sess["wrong_streak"] = 0
        if sess["up"] >= 2:
            inc = 2 if sess.get("fast", False) and answered <= FAST_N else 1
            sess["level"] = min(TOP_LEVEL, sess["level"] + inc)
            sess["up"] = 0
            if answered >= FAST_N:
                sess["fast"] = False
    else:
        sess["wrong_streak"] = min(12, sess.get("wrong_streak", 0) + 1)
        sess["down"] = sess["wrong_streak"]
        sess["up"] = 0
        sess["fast"] = False
        if sess["down"] >= 2:
            sess["level"] = max(0, sess["level"] - 1)
            sess["down"] = 0
    return sess["level"]


def update_rigor(rigor, response):
    """Apply bounded V1.4 rigor updates; unknown answers do not alter rigor."""
    if response < 0:
        return float(rigor)
    if response:
        delta = max(1.0, 1.5 / (1.0 + max(0.0, float(rigor) - 50.0) / 20.0))
    else:
        delta = -min(12.0, 3.0 + max(0, min(11, int(rigor // 10))))
    return max(0.0, min(105.0, float(rigor) + delta))


def pick_idx(lvls, level, asked, rng, bs=None, theta=0.0):
    """Choose a unique item by nearest band, then Fisher information; exhaustion is None."""
    seen = set(asked)
    candidates = [i for i, band in enumerate(lvls) if i not in seen]
    if not candidates:
        return None
    band_distance = min(abs(lvls[i] - level) for i in candidates)
    candidates = [i for i in candidates if abs(lvls[i] - level) == band_distance]
    if bs is not None:
        candidates.sort(key=lambda i: (-(p_correct(theta, bs[i]) * (1 - p_correct(theta, bs[i]))), i))
        best_info = p_correct(theta, bs[candidates[0]]) * (1 - p_correct(theta, bs[candidates[0]]))
        candidates = [i for i in candidates if abs(p_correct(theta, bs[i]) * (1 - p_correct(theta, bs[i])) - best_info) < 1e-12]
    candidates.sort()
    # Deterministic for an RNG seed/state and independent of bank traversal order.
    return candidates[rng.randrange(len(candidates))]


def posterior(bs, responses, prior_sd=PRIOR_SD, grid_min=GRID_MIN, grid_max=GRID_MAX, grid_step=GRID_STEP):
    """Fixed-grid posterior for correct=1, wrong=0, unknown=-1 (unknown contributes no likelihood)."""
    if len(bs) != len(responses):
        raise ValueError("bs and responses must have equal length")
    if prior_sd <= 0 or grid_step <= 0 or grid_max < grid_min:
        raise ValueError("invalid grid or prior")
    grid = []
    t = grid_min
    while t <= grid_max + grid_step * 1e-9:
        grid.append(round(t, 10))
        t += grid_step
    logw = []
    for theta in grid:
        ll = -(theta * theta) / (2 * prior_sd * prior_sd)
        for b, response in zip(bs, responses):
            if response < 0:
                continue
            p = min(max(p_correct(theta, b), 1e-12), 1 - 1e-12)
            ll += math.log(p if response else 1 - p)
        logw.append(ll)
    top = max(logw)
    weights = [math.exp(value - top) for value in logw]
    total = sum(weights)
    return grid, [weight / total for weight in weights]


def _quantile(grid, weights, q):
    target = q * sum(weights)
    accumulated = 0.0
    for value, weight in zip(grid, weights):
        accumulated += weight
        if accumulated >= target:
            return value
    return grid[-1]


def estimate_theta(bs, responses):
    grid, weights = posterior(bs, responses)
    mean = sum(t * p for t, p in zip(grid, weights))
    variance = sum(p * (t - mean) ** 2 for t, p in zip(grid, weights))
    return mean, math.sqrt(variance)


def knowledge(bs, theta):
    return [p_know(theta, b) for b in bs]


def vocab_estimate(probs):
    return sum(probs)


def vocab_at(bs, theta):
    return sum(p_know(theta, b) for b in bs)


def vocab_posterior(bs, responses, bank_total=None):
    """Posterior expected vocabulary and equal-tail 95% vocabulary interval.

    `bank_total` may supply a precomputed plausible universe; when larger than the
    sampled difficulty bank, its unseen mass is conservatively assigned b=CLAMP.
    """
    total = len(bs) if bank_total is None else max(len(bs), int(bank_total))
    unseen = total - len(bs)
    grid, weights = posterior(bs[:len(responses)], responses)
    # All unseen terms use the same difficulty. Sum their mass once instead
    # of evaluating the identical sigmoid for every word at every grid point.
    # This preserves the existing posterior model while making UI work depend
    # on the answered sample size, not on the size of the entire word bank.
    vocab = [vocab_at(bs, theta) + unseen * p_know(theta, CLAMP) for theta in grid]
    mean = sum(value * weight for value, weight in zip(vocab, weights))
    return mean, _quantile(vocab, weights, 0.025), _quantile(vocab, weights, 0.975)


def error_band(bs, theta, se):
    # Retain legacy API: a normal approximation around theta.
    return vocab_at(bs, theta - se), vocab_at(bs, theta + se)


def split_known(probs, threshold=KNOWN_THRESHOLD):
    return [p >= threshold for p in probs]
