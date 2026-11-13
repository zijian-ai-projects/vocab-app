# -*- coding: utf-8 -*-
"""V1.4.2 frequency-entry CAT, independent of the legacy placement engine.

Only Python 3.8+ standard-library code is used.  No files are read or written.
A frequency rank here is the rank *among retained local entries*, not an
absolute corpus rank, a school level, or a VST word family.  The fixed 3PL
parameters and N(0, 2**2) prior are product heuristics, NOT population-calibrated
item parameters.  All intervals are conditional on this model and item bank.

Public UI interface:
    bank = FrequencyBank(words)
    state = new_state(seed)
    record = next_item(bank, state, records, responses)
    # The caller, not next_item(), appends record and record['key'].
    result = summarize(bank, records, responses)
    valid = validate_session(session, bank)

Option IDs are stable bank keys; A/B/C/D are slot keys, not word IDs.  Content
checks are deliberately conservative lexical checks over supplied Chinese
senses (including supplied raw alternate senses).  They do not assert that an
uncurated dictionary has been psychometrically or semantically validated.
"""
import hashlib
import json
import math
import random
import re
import unicodedata
from functools import lru_cache

ALGORITHM = "vst-cat-v142"
SESSION_SCHEMA = 2
MEASUREMENT_SCHEMA = 3
BAND_SIZE = 1000
MAX_WORDS = 20000
MIN_ITEMS = 40
MAX_ITEMS = 80
MIN_PER_BAND = 2
TARGET_SE = 0.30
A = 1.4
C = 0.25
PRIOR_MEAN = 0.0
PRIOR_SD = 2.0
THETA_MIN = -5.0
THETA_MAX = 7.0
THETA_STEP = 0.05
INTERVAL_LEVEL = 0.95
UNIT = "frequency_ranked_entries"
THETA_GRID = tuple(index / 20.0 for index in range(-100, 141))

# Changing content/selection rules must invalidate old sessions too.
_CONTENT_POLICY = "single-entries-zh-lexical-conflict-v2"
_DISTRACTOR_POOL = 6
# Explicit unambiguous abbreviations whose source entries can lack abbr tags.
# Never infer abbreviation status from short length: am/as/in/no/us, fig, mar,
# ad and the fully lexicalized etcetera have ordinary readings and stay valid.
_ABBREVIATION_KEYS = frozenset(("etc", "mr", "mrs", "ms", "dr", "vs", "ltd",
                                "inc", "jr", "sr", "pm", "eg", "ie", "aka",
                                "asap", "st"))
_SLOTS = "ABCD"
_WORD = re.compile(r"[a-z]+(?:[-'][a-z]+)*\Z", re.ASCII)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_POS = re.compile(
    r"(?<![a-z])(?:n|v|vt|vi|adj|a|adv|ad|prep|conj|pron|det|art|num|"
    r"aux|int|interj|abbr|un|na)\.", re.I)
_NON_MEANING = re.compile(
    r"(?:暂无(?:释义|解释|翻译)?|释义缺失|未收录|无释义|未知释义|待补充|"
    r"翻译错误|乱码|见词条|参见词条|同上|以上皆非|以上都不|以上全部|均不正确)")
_META_ENTITY = re.compile(
    r"(?:\b(?:abbr|abbrev|acronym|propn|proper\s+noun)\b|"
    r"[\[（(【]\s*(?:人名|地名|姓氏|男子名|女子名|男名|女名|国名|"
    r"城市名|省名|缩写|略语)|"
    r"(?:^|[；;\n])\s*(?:(?:n|un|na)\.\s*)?(?:人名|地名|姓氏|男子名|女子名)"
    r"(?:\s*$|[，,；;：:（(])|(?:的|之)(?:缩写|缩略形式|简称))", re.I)
_INFLECTION_FORM = (
    r"(?:复数|过去式|过去分词|现在分词|第三人称单数|比较级|最高级|"
    r"单数(?:第一|第二|第三)人称|(?:第一|第二)人称单数)")
_INFLECTION_ONLY = re.compile(
    r"^[\"'“‘]?[a-z]+(?:[-'][a-z]+)*[\"'”’]?\s*的\s*" + _INFLECTION_FORM
    + r"(?:\s*(?:和|及|与|或|、|[，,])\s*" + _INFLECTION_FORM + r")*"
    + r"(?:形式)?[。.!！]?$")
# These senses have lost their entity labels in some source dictionaries.
# Match a *whole leading gloss*, not a substring of an ordinary definition.
_PLACE_GLOSS = re.compile(
    r"^(?:中国|美国|英国|法国|德国|日本|加拿大|澳大利亚|印度|俄罗斯|意大利|"
    r"西班牙|葡萄牙|巴西|墨西哥|埃及|希腊|瑞典|瑞士|挪威|芬兰|丹麦|"
    r"荷兰|比利时|奥地利|波兰|乌克兰|新西兰|南非|韩国|朝鲜|越南|泰国|"
    r"新加坡|马来西亚|印度尼西亚|菲律宾|土耳其|伊朗|伊拉克|爱尔兰|"
    r"伦敦|巴黎|东京|北京|上海|纽约|华盛顿|罗马|柏林|悉尼|莫斯科|"
    r"亚洲|欧洲|非洲|美洲|大洋洲|南极洲)(?=$|[；;，,（(])")
_ENGLISH_STOP = frozenset(("a", "an", "the", "of", "to", "and", "or", "in"))
_LOG_ONE_MINUS_C = math.log1p(-C)
_PRIOR_LOG = tuple(-0.5 * ((theta - PRIOR_MEAN) / PRIOR_SD) ** 2
                   for theta in THETA_GRID)
_THETA_EXP = tuple(math.exp(A * theta) for theta in THETA_GRID)


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _number(value, name):
    if not _finite(value):
        raise ValueError("%s must be a finite number, not bool" % name)
    return float(value)


def _sigmoid(value):
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def difficulty(rank):
    """Fixed local-rank heuristic; source b/lvl are never consulted."""
    if type(rank) is not int or not 1 <= rank <= MAX_WORDS:
        raise ValueError("rank must be an integer between 1 and MAX_WORDS")
    return math.log((rank + 100) / 1000.0)


def p_known(theta, b):
    """Recognition probability, with no guessing component."""
    theta, b = _number(theta, "theta"), _number(b, "b")
    return _sigmoid(A * (theta - b))


def p_correct(theta, b):
    """Fixed 3PL answer probability: .25 + .75 * sigmoid(1.4*(theta-b))."""
    return C + (1.0 - C) * p_known(theta, b)


def fisher_information(theta, b):
    """3PL Fisher information; stable also at saturated probabilities."""
    known = p_known(theta, b)
    return (A * A * (1.0 - C) * known * known * (1.0 - known)
            / (C + (1.0 - C) * known))


def _pos_values(value):
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    elif value is None:
        values = []
    else:
        return None
    if any(not isinstance(part, str) for part in values):
        return None
    return tuple(part.strip() for part in values if part.strip())


def _primary_pos(values, sense):
    source = values[0] if values else sense
    match = re.match(r"\s*([a-z]+)(?:\.|\b)", source, re.I)
    value = match.group(1).lower() if match else "other"
    return {"vt": "v", "vi": "v", "a": "adj", "ad": "adv",
            "interj": "int"}.get(value, value)


def _sense_body(text):
    return _POS.sub("", unicodedata.normalize("NFKC", text).casefold())


def _semantic_profile(sense, raw=""):
    """Hashable conservative profile; never invent or translate a gloss.

    Two-character Chinese overlaps catch key fragments such as 害怕 within
    使害怕 / 感到害怕.  Single-character *whole* glosses are also protected.
    Raw alternate senses are extra ambiguity evidence, never answer text.
    """
    primary = _sense_body(sense)
    combined = primary + ";" + _sense_body(raw.replace("\\n", ";"))
    canonical = "".join(re.findall(r"[a-z0-9\u3400-\u4dbf\u4e00-\u9fff]", primary))
    grams = set()
    singles = set()
    runs = _CJK_RUN.findall(combined)
    for run in runs:
        if len(run) == 1:
            singles.add(run)
        else:
            grams.update(run[index:index + 2] for index in range(len(run) - 1))
    english = frozenset(word for word in re.findall(r"[a-z]{3,}", combined)
                        if word not in _ENGLISH_STOP)
    return (canonical, frozenset(grams), frozenset(singles), english,
            "".join(runs))


def _only_inflections(body):
    """Reject entire morphological pointers, not a lexical sense mentioning one."""
    if "的" not in body:
        return False
    parts = [part.strip(" \t\r\n()[]【】")
             for part in re.split(r"[;；\n]+", body.replace("\\n", "\n"))]
    parts = [part for part in parts if part]
    return bool(parts) and all(_INFLECTION_ONLY.fullmatch(part) for part in parts)


def _profiles_conflict(left, right):
    if left[0] in right[0] or right[0] in left[0]:
        return True
    if not left[1].isdisjoint(right[1]) or not left[3].isdisjoint(right[3]):
        return True
    if left[2] and any(char in right[4] for char in left[2]):
        return True
    return bool(right[2]) and any(char in left[4] for char in right[2])


def _prepare_entry(row):
    if not isinstance(row, dict):
        return None
    # Deliberately enumerate only these fields: never source b/lvl or school
    # membership.  No mutation of caller-owned dictionaries/lists occurs.
    word = row.get("w")
    frq = row.get("frq")
    sense = row.get("s")
    raw = row.get("raw", "")
    pos = _pos_values(row.get("pos"))
    caption = row.get("display_w", word)
    if (not isinstance(word, str) or word != word.strip()
            or not _finite(frq) or frq <= 0
            or not isinstance(sense, str) or pos is None):
        return None
    key = word.casefold()
    if (not _WORD.fullmatch(key) or key in _ABBREVIATION_KEYS
            or row.get("type") == "phrase"):
        return None
    # Retain the pronoun I, not arbitrary capitalized names or acronyms.
    if word != key and not (word == "I" and _primary_pos(pos, sense) == "pron"):
        return None
    if not isinstance(caption, str) or not caption.strip():
        caption = word
    caption = caption.strip()
    if caption != caption.casefold() and not (caption == "I" and key == "i"):
        return None
    sense = sense.strip()
    raw = raw.strip() if isinstance(raw, str) else ""
    body = _sense_body(sense).strip()
    if (not _CJK.search(body) or "\ufffd" in sense
            or any(ord(char) < 32 and char not in "\n\t\r" for char in sense)
            or _NON_MEANING.search(body)
            or _only_inflections(body)
            or re.match(r"\s*(?:=|参见|见\s*[a-z])", body, re.I)
            or _META_ENTITY.search((";".join(pos) + ";" + sense + ";" + raw)
                                   .replace("\\n", ";"))
            or _PLACE_GLOSS.match(body)):
        return None
    frequency = int(frq) if float(frq).is_integer() else float(frq)
    return {"key": key, "word": caption, "sense": sense, "pos": list(pos),
            "source_frq": frequency, "source_raw": raw}


@lru_cache(maxsize=MAX_WORDS)
def _rank_scale(rank):
    return math.exp(A * difficulty(rank))


@lru_cache(maxsize=512)
def _item_curves(rank):
    """Log likelihoods and Fisher information; no unstable log(1-p)."""
    scale = _rank_scale(rank)
    log_scale = math.log(scale)
    correct, failure, information = [], [], []
    for exponential in _THETA_EXP:
        denominator = exponential + scale
        known = exponential / denominator
        correct.append(math.log((exponential + C * scale) / denominator))
        failure.append(_LOG_ONE_MINUS_C + log_scale - math.log(denominator))
        information.append(A * A * (1.0 - C) * known * known * (1.0 - known)
                           / (C + (1.0 - C) * known))
    return tuple(correct), tuple(failure), tuple(information)


@lru_cache(maxsize=64)
def _range_curves(start, end):
    """Exact population and information sums, sharing probability work."""
    scales = tuple(_rank_scale(rank) for rank in range(start, end + 1))
    population, information = [], []
    factor, one_minus_c = A * A * (1.0 - C), 1.0 - C
    for exponential in _THETA_EXP:
        known = [exponential / (exponential + scale) for scale in scales]
        population.append(math.fsum(known))
        information.append(math.fsum([factor * q * q * (1.0 - q) / (C + one_minus_c * q)
                                      for q in known]))
    return tuple(population), tuple(information)


@lru_cache(maxsize=64)
def _population_curve(start, end):
    """Exact summation over every retained local rank, not band midpoints."""
    return _range_curves(start, end)[0]


@lru_cache(maxsize=64)
def _information_curve(ranks):
    if ranks and ranks[-1] - ranks[0] + 1 == len(ranks):
        return _range_curves(ranks[0], ranks[-1])[1]
    scales = tuple(_rank_scale(rank) for rank in ranks)
    result = []
    factor, one_minus_c = A * A * (1.0 - C), 1.0 - C
    for exponential in _THETA_EXP:
        known = [exponential / (exponential + scale) for scale in scales]
        result.append(math.fsum([factor * q * q * (1.0 - q) / (C + one_minus_c * q)
                                 for q in known]))
    return tuple(result)


def _select_entries(words):
    """Shared selection frame: frequency order, one key each, capped population."""
    if isinstance(words, (str, bytes, dict)):
        raise ValueError("words must be an iterable of entry dictionaries")
    try:
        iterator = iter(words)
    except TypeError as exc:
        raise ValueError("words must be iterable") from exc
    prepared, input_count = [], 0
    for row in iterator:
        input_count += 1
        entry = _prepare_entry(row)
        if entry is not None:
            prepared.append(entry)
    # The final tie breakers make duplicate resolution independent of the
    # source iteration order without changing primary (frq, w) ordering.
    prepared.sort(key=lambda item: (item["source_frq"], item["key"],
                                    item["sense"], tuple(item["pos"]),
                                    item["source_raw"], item["word"]))
    selected, seen = [], set()
    for item in prepared:
        if item["key"] not in seen:
            seen.add(item["key"])
            selected.append(item)
            if len(selected) == MAX_WORDS:
                break
    return selected, input_count


def population_summary_steps(words, batch_size=128):
    """Yield between bounded batches, then yield the exact population summary.

    Counts use the same validity rules as the full bank. Only the number of
    distinct valid keys is needed here; sorting and distractor pools are not.
    Caller-owned entries remain untouched, including for one-shot iterables.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if isinstance(words, (str, bytes, dict)):
        raise ValueError("words must be an iterable of entry dictionaries")
    try:
        iterator = iter(words)
    except TypeError as exc:
        raise ValueError("words must be iterable") from exc
    seen, input_count = set(), 0
    for row in iterator:
        input_count += 1
        entry = _prepare_entry(row)
        if entry is not None and len(seen) < MAX_WORDS:
            seen.add(entry["key"])
        if input_count % batch_size == 0:
            yield None
    size = len(seen)
    yield {"size": size, "excluded_count": input_count - size,
           "bands": (size + BAND_SIZE - 1) // BAND_SIZE}


def population_summary(words):
    """Exact size/band summary without item pools, profiles or fingerprint.

    The synchronous helper remains available to non-UI callers. Explanation
    pages can consume population_summary_steps one event-loop turn at a time.
    """
    for result in population_summary_steps(words):
        if result is not None:
            return result


class FrequencyBank:
    """Immutable-in-use local measurement population and cached option pools.

    size includes retained frequency entries even if conservative content
    checks cannot construct an item for some of them.  testable_size and
    untestable_count make that distinction explicit.  Such entries are never
    asked; an unfillable band is never silently called covered.
    """

    def __init__(self, words, progress=None):
        if progress is not None and not callable(progress):
            raise ValueError("progress must be callable or None")
        last_progress = [-1]

        def report(value):
            value = max(0, min(100, int(value)))
            if value <= last_progress[0]:
                return
            last_progress[0] = value
            if progress is not None:
                progress(value)

        report(0)
        selected, input_count = _select_entries(words)
        report(10)
        self.size = len(selected)
        self.excluded_count = input_count - self.size
        self.bands = []
        self.items = {}
        self._profiles = {}
        self._primary = {}
        self._by_band = {}
        self._by_band_pos = {}
        source_rows = []
        for start in range(1, self.size + 1, BAND_SIZE):
            end = min(start + BAND_SIZE - 1, self.size)
            band = (start - 1) // BAND_SIZE + 1
            self.bands.append({"id": band, "label": "本地有效词目 %d–%d" % (start, end),
                               "size": end - start + 1, "start": start, "end": end})
            self._by_band[band] = []
        item_total = max(1, len(selected))
        item_tick = max(1, item_total // 50)
        for rank, source in enumerate(selected, 1):
            key = source["key"]
            band = (rank - 1) // BAND_SIZE + 1
            item = {name: source[name] for name in ("key", "word", "sense", "source_frq")}
            item.update({"pos": list(source["pos"]), "rank": rank, "band": band,
                         "a": A, "b": difficulty(rank), "c": C})
            self.items[key] = item
            self._profiles[key] = _semantic_profile(item["sense"], source["source_raw"])
            primary = _primary_pos(item["pos"], item["sense"])
            self._primary[key] = primary
            self._by_band[band].append(key)
            self._by_band_pos.setdefault((band, primary), []).append(key)
            source_rows.append([key, item["word"], item["sense"], item["pos"],
                                item["source_frq"], source["source_raw"]])
            if rank == len(selected) or rank % item_tick == 0:
                report(10 + 20 * rank // item_total)
        report(30)
        # Repeated synonymous entries share construction work.  Candidate
        # pools themselves are pairwise compatible, so every sampled triple
        # is safe and next_item never scans the full bank for distractors.
        templates = {}
        self._distractors = {}
        self._testable_by_band = {band["id"]: [] for band in self.bands}
        distractor_total = max(1, len(self.items))
        distractor_tick = max(1, distractor_total // 100)
        for item_number, (key, item) in enumerate(self.items.items(), 1):
            signature = (item["band"], self._primary[key], self._profiles[key])
            if signature not in templates:
                templates[signature] = self._build_distractors(key)
            pool = templates[signature]
            self._distractors[key] = pool
            if len(pool) >= 3:
                self._testable_by_band[item["band"]].append(key)
            if item_number == len(self.items) or item_number % distractor_tick == 0:
                report(30 + 45 * item_number // distractor_total)
        report(75)
        self._by_band = {band: tuple(keys) for band, keys in self._by_band.items()}
        self._by_band_pos = {group: tuple(keys) for group, keys in self._by_band_pos.items()}
        self._testable_by_band = {band: tuple(keys)
                                  for band, keys in self._testable_by_band.items()}
        self.testable_size = sum(len(keys) for keys in self._testable_by_band.values())
        self.untestable_count = self.size - self.testable_size
        self._population = {}
        band_total = max(1, len(self.bands))
        for band_number, band in enumerate(self.bands, 1):
            self._population[band["id"]] = _population_curve(band["start"], band["end"])
            report(75 + 10 * band_number // band_total)
        report(85)
        self._information = {}
        information_total = max(1, len(self._testable_by_band))
        for band_number, (band, keys) in enumerate(self._testable_by_band.items(), 1):
            self._information[band] = _information_curve(
                tuple(self.items[key]["rank"] for key in keys))
            report(85 + 8 * band_number // information_total)
        report(93)
        self._total_population = tuple(math.fsum(curve[index] for curve in self._population.values())
                                       for index in range(len(THETA_GRID)))
        report(95)
        identity = {
            "algorithm": ALGORITHM, "session_schema": SESSION_SCHEMA,
            "measurement_schema": MEASUREMENT_SCHEMA, "unit": UNIT,
            "scope": {"size": self.size, "max_words": MAX_WORDS, "band_size": BAND_SIZE,
                      "local_rank": True, "bands": self.bands},
            "model": {"a": A, "c": C, "b": "ln((local_rank+100)/1000)",
                      "theta_grid": [THETA_MIN, THETA_MAX, THETA_STEP],
                      "prior": [PRIOR_MEAN, PRIOR_SD], "interval_level": INTERVAL_LEVEL},
            "test": {"min_items": MIN_ITEMS, "max_items": MAX_ITEMS,
                     "min_per_band": MIN_PER_BAND, "target_se": TARGET_SE,
                     "content_policy": _CONTENT_POLICY, "distractor_pool": _DISTRACTOR_POOL,
                     "abbreviation_keys": sorted(_ABBREVIATION_KEYS)},
            "sources": source_rows,
            "testable": [key for key in self.items if len(self._distractors[key]) >= 3],
        }
        self.fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True,
                                                    ensure_ascii=False, allow_nan=False,
                                                    separators=(",", ":")).encode("utf-8")).hexdigest()
        report(100)

    def _compatible(self, left, right):
        return left != right and not _profiles_conflict(self._profiles[left], self._profiles[right])

    def _candidate_groups(self, key):
        item = self.items[key]
        band, primary = item["band"], self._primary[key]
        nearest = sorted(self._by_band, key=lambda number: (abs(number - band), number))
        # Same POS and local frequency band first, then nearby bands of that
        # POS.  Only after those, use real senses from other POS groups.
        for number in nearest:
            yield self._by_band_pos.get((number, primary), ())
        for number in nearest:
            yield self._by_band[number]

    def _build_distractors(self, key):
        offset = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
        visited, profiles, compatible, pool, pool_profiles = set(), set(), [], [], []
        target_profile = self._profiles[key]
        for group in self._candidate_groups(key):
            length = len(group)
            if not length:
                continue
            start = offset % length
            for index in range(length):
                candidate = group[(start + index) % length]
                if candidate in visited:
                    continue
                visited.add(candidate)
                profile = self._profiles[candidate]
                if profile in profiles or _profiles_conflict(target_profile, profile):
                    continue
                profiles.add(profile)
                compatible.append(candidate)
                if all(not _profiles_conflict(profile, other) for other in pool_profiles):
                    pool.append(candidate)
                    pool_profiles.append(profile)
                    if len(pool) == _DISTRACTOR_POOL:
                        return tuple(pool)
            # Do not import lower-priority frequency/POS groups merely to
            # enlarge an already usable set of same-group distractors.
            if len(pool) >= 3:
                return tuple(pool)
        if len(pool) >= 3:
            return tuple(pool)
        # A greedy first candidate can block an otherwise valid triple.
        # Resolve that small/ambiguous case exactly rather than fabricate a
        # distractor or incorrectly declare the target impossible.
        for first_index, first in enumerate(compatible):
            neighbors = [second for second in compatible[first_index + 1:]
                         if self._compatible(first, second)]
            for second_index, second in enumerate(neighbors):
                for third in neighbors[second_index + 1:]:
                    if self._compatible(second, third):
                        return first, second, third
        return ()


def new_state(seed):
    if type(seed) is not int:
        raise ValueError("seed must be an integer, not bool")
    return {"seed": seed, "asked": [], "theta": 0.0, "se": 2.0}


def _require_bank(bank):
    if not isinstance(bank, FrequencyBank):
        raise ValueError("bank must be a FrequencyBank")


def _validate_record(bank, record):
    if not isinstance(record, dict):
        raise ValueError("record must be a dictionary")
    key = record.get("key")
    if not isinstance(key, str) or key not in bank.items:
        raise ValueError("record has an unknown key")
    source = bank.items[key]
    if (type(record.get("band")) is not int or record["band"] != source["band"]
            or type(record.get("rank")) is not int or record["rank"] != source["rank"]
            or record.get("phase") not in ("survey", "adaptive")):
        raise ValueError("record rank, band, or phase is invalid")
    irt = record.get("irt")
    if not isinstance(irt, dict) or any(not _finite(irt.get(name)) or irt[name] != source[name]
                                        for name in ("a", "b", "c")):
        raise ValueError("record IRT parameters do not match the fixed bank")
    item = record.get("item")
    if (not isinstance(item, dict) or item.get("item_id") != key
            or item.get("word") != source["word"]):
        raise ValueError("record target ID or display word does not match")
    options = item.get("options")
    correct = item.get("correct_index")
    if (not isinstance(options, list) or len(options) != 4
            or type(correct) is not int or not 0 <= correct < 4
            or item.get("correct_key") != _SLOTS[correct]):
        raise ValueError("item needs four slots and a valid correct slot")
    option_keys = []
    for index, option in enumerate(options):
        if not isinstance(option, dict) or option.get("key") != _SLOTS[index]:
            raise ValueError("option slot keys must be ordered A, B, C, D")
        option_id = option.get("item_id")
        if (not isinstance(option_id, str) or option_id not in bank.items
                or option.get("text") != bank.items[option_id]["sense"]):
            raise ValueError("option text and stable ID must match the bank")
        if any(not bank._compatible(option_id, previous) for previous in option_keys):
            raise ValueError("duplicate or conflicting option meanings")
        option_keys.append(option_id)
    if option_keys[correct] != key or option_keys.count(key) != 1:
        raise ValueError("exactly one option must be the target sense")
    return key


def _validate_history(bank, records, responses):
    _require_bank(bank)
    if not isinstance(records, (list, tuple)) or not isinstance(responses, (list, tuple)):
        raise ValueError("records and responses must be sequences")
    if (len(records) > MAX_ITEMS or len(responses) > MAX_ITEMS
            or len(records) - len(responses) not in (0, 1)):
        raise ValueError("history must contain only answered items and at most one pending item")
    if any(type(response) is not int or response not in (-1, 0, 1) for response in responses):
        raise ValueError("responses must be exact integers -1, 0, or 1")
    keys = []
    for record in records:
        key = _validate_record(bank, record)
        if key in keys:
            raise ValueError("target keys cannot repeat")
        keys.append(key)
    return keys


def _validate_state(state, keys):
    if (not isinstance(state, dict) or type(state.get("seed")) is not int
            or not isinstance(state.get("asked"), list)
            or state["asked"] != keys
            or not _finite(state.get("theta"))
            or not THETA_MIN <= state["theta"] <= THETA_MAX
            or not _finite(state.get("se")) or not 0 <= state["se"] <= 6.0):
        raise ValueError("state seed, asked keys, theta, or se is invalid")


@lru_cache(maxsize=192)
def _posterior(evidence):
    log_weights = list(_PRIOR_LOG)
    for rank, response in evidence:
        curve = _item_curves(rank)[0 if response == 1 else 1]
        log_weights = [left + right for left, right in zip(log_weights, curve)]
    maximum = max(log_weights)
    unnormalized = tuple(math.exp(value - maximum) for value in log_weights)
    normalizer = math.fsum(unnormalized)
    return tuple(value / normalizer for value in unnormalized)


def _weights(records, responses):
    # Unknown and wrong deliberately produce the identical cache key and
    # identical likelihood.  There is no rigor score, reward, or punishment.
    return _posterior(tuple((record["rank"], int(response == 1))
                            for record, response in zip(records, responses)))


def posterior(bank, records, responses):
    """Validated discrete posterior, as immutable (grid, normalized_weights)."""
    _validate_history(bank, records, responses)
    return THETA_GRID, _weights(records, responses)


def _dot(left, right):
    return math.fsum(a * b for a, b in zip(left, right))


def _theta_stats(weights):
    mean = _dot(THETA_GRID, weights)
    variance = math.fsum(weight * (theta - mean) ** 2 for theta, weight in zip(THETA_GRID, weights))
    return mean, math.sqrt(variance)


def _quantile_index(weights, probability):
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if cumulative >= probability:
            return index
    return len(weights) - 1


def _counts(bank, records, responses):
    counts = {band["id"]: [0, 0, 0] for band in bank.bands}
    for record, response in zip(records, responses):
        value = counts[record["band"]]
        value[0] += 1
        value[1] += int(response == 1)
        value[2] += int(response == -1)
    return counts


def _stop_reason(bank, records, responses, se, coverage):
    answered = len(responses)
    if answered >= MAX_ITEMS:
        return "max_items"
    if answered >= MIN_ITEMS and coverage == len(bank.bands) and se <= TARGET_SE:
        return "precision"
    # A last presented-but-unanswered item is still available evidence.
    if len(records) == answered and len(records) >= bank.testable_size:
        return "exhausted"
    return None


def summarize(bank, records, responses):
    """Unmodified EAP counts and transformed 95% equal-tail model intervals.

    Band estimates sum recognition probabilities over *all* its ranks, then
    integrate against the posterior.  Guessing is not counted as recognition.
    No observed-score rescaling, minimum-width caps, or endpoint adjustment is
    applied.  Availability requires 40 answers AND two answers in EVERY band.
    """
    _validate_history(bank, records, responses)
    weights = _weights(records, responses)
    theta, se = _theta_stats(weights)
    lower = _quantile_index(weights, (1.0 - INTERVAL_LEVEL) / 2.0)
    upper = _quantile_index(weights, 1.0 - (1.0 - INTERVAL_LEVEL) / 2.0)
    counts = _counts(bank, records, responses)
    bands = []
    for source in bank.bands:
        band = source["id"]
        answered, correct, unknown = counts[band]
        curve = bank._population[band]
        estimate = _dot(curve, weights)
        bands.append({"id": band, "label": source["label"], "size": source["size"],
                      "answered": answered, "correct": correct, "unknown": unknown,
                      "estimate": estimate, "low": curve[lower], "high": curve[upper],
                      "p_known": estimate / source["size"]})
    answered = len(responses)
    correct = sum(response == 1 for response in responses)
    coverage = sum(value[0] >= MIN_PER_BAND for value in counts.values())
    available = answered >= MIN_ITEMS and coverage == len(bank.bands)
    boundary = None
    if answered and correct == answered:
        boundary = "all_correct"
    elif answered and correct == 0:
        boundary = "all_incorrect"
    elif weights[0] + weights[-1] >= 0.01:
        boundary = "grid_edge"
    provisional = not available or se > TARGET_SE or boundary is not None
    population = bank._total_population
    return {
        "theta": theta, "se": se, "estimate": _dot(population, weights),
        "low": population[lower], "high": population[upper],
        "answered": answered, "correct_count": correct,
        "dontknow": sum(response == -1 for response in responses),
        "estimate_available": available, "provisional": provisional, "bands": bands,
        "coverage": coverage, "coverage_target": len(bank.bands),
        "survey_coverage": sum(value[0] >= 1 for value in counts.values()),
        "stop_reason": _stop_reason(bank, records, responses, se, coverage),
        "unit": UNIT, "interval_level": INTERVAL_LEVEL,
        "boundary": boundary, "theta_low": THETA_GRID[lower], "theta_high": THETA_GRID[upper],
        "evidence_limited": provisional, "model_only": True,
        "measurement_schema": MEASUREMENT_SCHEMA, "algo": ALGORITHM,
        "bank_id": bank.fingerprint, "population_size": bank.size,
        "testable_size": bank.testable_size, "untestable_count": bank.untestable_count,
    }


def _expected_information(bank, band, weights, records):
    """Expected Fisher information of a uniform *remaining* band draw."""
    asked = [record for record in records if record["band"] == band]
    remaining = len(bank._testable_by_band[band]) - len(asked)
    if remaining <= 0:
        raise ValueError("cannot score an exhausted band")
    total = _dot(bank._information[band], weights)
    used = math.fsum(_dot(_item_curves(record["rank"])[2], weights) for record in asked)
    return (total - used) / remaining


def next_item(bank, state, records, responses):
    """Pure selection: ordered survey, coverage-constrained information CAT.

    The layer is chosen by posterior expected 3PL Fisher information; the
    unasked target within it is a seeded UNIFORM draw, never an information
    maximum, an easy-edge shortlist, or a correct/wrong streak staircase.
    """
    keys = _validate_history(bank, records, responses)
    _validate_state(state, keys)
    if len(records) != len(responses):
        raise ValueError("answer the pending item before requesting another")
    weights = _weights(records, responses)
    _, se = _theta_stats(weights)
    counts = _counts(bank, records, responses)
    coverage = sum(value[0] >= MIN_PER_BAND for value in counts.values())
    if _stop_reason(bank, records, responses, se, coverage) is not None:
        return None
    asked = set(keys)
    available = [band["id"] for band in bank.bands
                 if len(bank._testable_by_band[band["id"]]) > counts[band["id"]][0]]
    if not available:
        return None
    survey = [band for band in available if counts[band][0] == 0]
    if survey:
        band, phase = survey[0], "survey"
    else:
        undercovered = [band for band in available if counts[band][0] < MIN_PER_BAND]
        candidates = undercovered or available
        band = max(candidates, key=lambda number: (_expected_information(bank, number, weights, records),
                                                   -number))
        phase = "adaptive"
    material = "%s|%s|%d|%d" % (ALGORITHM, bank.fingerprint, state["seed"], len(records))
    rng = random.Random(int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest(), "big"))
    unasked = [key for key in bank._testable_by_band[band] if key not in asked]
    key = unasked[rng.randrange(len(unasked))]
    source = bank.items[key]
    option_ids = [key] + rng.sample(bank._distractors[key], 3)
    rng.shuffle(option_ids)
    correct = option_ids.index(key)
    item = {"item_id": key, "word": source["word"],
            "options": [{"key": _SLOTS[index], "text": bank.items[option_id]["sense"],
                         "item_id": option_id} for index, option_id in enumerate(option_ids)],
            "correct_index": correct, "correct_key": _SLOTS[correct]}
    return {"key": key, "band": band, "rank": source["rank"], "phase": phase,
            "item": item, "irt": {name: source[name] for name in ("a", "b", "c")}}


def validate_session(session, bank):
    """Validate a current/pending or just-answered JSON snapshot, without TTL.

    Unknown extension fields are ignored and preserved.  This checks source
    identity, fixed parameters, exact option IDs/texts and content ambiguity;
    it is validation, not a cryptographic claim that a user never edited a
    response.  It never writes to session, bank, state, items, or responses.
    """
    try:
        _require_bank(bank)
        if (not isinstance(session, dict) or type(session.get("schema")) is not int
                or session["schema"] != SESSION_SCHEMA or session.get("algo") != ALGORITHM
                or session.get("bank_id") != bank.fingerprint):
            return False
        identifier = session.get("id")
        if (not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 256
                or any(ord(char) < 32 for char in identifier)
                or not _finite(session.get("started_at"))):
            return False
        items, responses, index = (session.get(name) for name in ("items", "resp", "i"))
        if (not isinstance(items, list) or not isinstance(responses, list)
                or type(index) is not int or not 0 <= index < MAX_ITEMS
                or len(items) != index + 1 or len(responses) not in (index, index + 1)):
            return False
        keys = _validate_history(bank, items, responses)
        _validate_state(session.get("state"), keys)
        # Enforce survey order/phase, without resampling or trusting saved
        # theta/se.  Adaptive item IDs need not be regenerated to validate.
        counts = {band["id"]: 0 for band in bank.bands}
        for record in items:
            unseen = [band["id"] for band in bank.bands
                      if counts[band["id"]] == 0 and bank._testable_by_band[band["id"]]]
            if unseen:
                if record["phase"] != "survey" or record["band"] != unseen[0]:
                    return False
            elif record["phase"] != "adaptive":
                return False
            counts[record["band"]] += 1
        return True
    except (ValueError, TypeError, KeyError, OverflowError, IndexError):
        return False
