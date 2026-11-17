# -*- coding: utf-8 -*-
"""为 DSH 版 `lib/core/vocabulary_test.js` 生成 Python 侧差分基线（只读合成数据）。

用法（工作目录不限，禁止联网）：
    D:\\software\\anaconda\\python.exe -B -I gen_cat_fixtures.py

输出（本目录）：
    cat-words.json      3 组固定合成词表（main / small / conflict）
    cat-bank.json       每组词表的 Python FrequencyBank 期望：size/bands/池/identity
    cat-entries.json    内容策略边界词条：期望保留的 sources 与干扰项池
    cat-primitives.json difficulty/pKnown/pCorrect/fisherInformation 数值表
    cat-trace.json      固定种子与固定答案序列的逐 step 记录 + summarize 期望

本文件不读取任何个人数据，不修改 `app/`。JS 侧 `test/vocabulary_test.test.mjs`
读取这些 JSON 做逐项比对。随机数只出现在“Python 选题”里，因此 fixture 里
`items` 是 Python PRNG 选出的；JS 侧复用这些记录（band/phase/rank/选项兼容性
仍然会被 JS 的 validateSession/_validate_record 全量校验），逐步比对不依赖随机
的量：band/phase/stop_reason/theta/se/estimate/interval/summary。
"""
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "app"))
sys.path.insert(0, APP_DIR)
import vocabulary_test as vt  # noqa: E402

OUT_DIR = HERE

# ---------------------------------------------------------------------------
# 合成词表素材
# ---------------------------------------------------------------------------
CHARS = (
    "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动"
    "同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理"
    "起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事"
    "平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问"
    "意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特"
    "件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做"
    "必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极"
    "交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积"
    "示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律"
    "叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响"
)
ENGLISH = (
    "abandon", "ability", "absent", "absorb", "accent", "accept", "access", "accident",
    "account", "achieve", "across", "action", "active", "actual", "adapt", "address",
    "adjust", "admire", "admit", "advance", "advice", "affect", "afford", "afraid",
    "agency", "agenda", "agree", "ahead", "alarm", "album", "alive", "allow",
    "almost", "alone", "along", "alter", "amount", "ancient", "anger", "angle",
    "animal", "announce", "annual", "answer", "anxious", "apart", "appeal", "appear",
    "apply", "approach", "argue", "arrange", "arrive", "article", "aspect", "assess",
    "assign", "assist", "assume", "attach", "attack", "attempt", "attend", "attract",
)
POS_CYCLE = (("n",), ("v",), ("adj",), ("adv",), ("n", "v"), ("vt",))
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _encode3(index):
    return LETTERS[index // 676 % 26] + LETTERS[index // 26 % 26] + LETTERS[index % 26]


def make_word(index, prefix="zq"):
    base = prefix + _encode3(index)
    if index % 37 == 5:
        return base + "-" + _encode3(index + 11)
    if index % 41 == 7:
        return base + "'" + _encode3(index + 13)
    return base


def make_gloss_pool(count=None):
    size = len(CHARS) if count is None else count
    return [CHARS[i] + CHARS[(i * 7 + 3) % len(CHARS)] for i in range(size)]


GLOSSES = make_gloss_pool()


def build_main_rows():
    """2450 条普通词条（单义/多义/互补同义/英文提示/带 raw）+ 40 余条边界词条。"""
    rows = []
    for index in range(2450):
        if index % 2 == 0:
            sense = GLOSSES[index % len(GLOSSES)]
            if index % 5 == 0:
                sense += "；" + GLOSSES[(index * 11 + 5) % len(GLOSSES)]
            if index % 11 == 0:
                sense += "（" + ENGLISH[index % len(ENGLISH)] + "）"
            if index % 13 == 0:
                sense = "使" + GLOSSES[(index * 3 + 1) % len(GLOSSES)]
            row = {"w": make_word(index), "frq": index + 10, "s": sense,
                   "pos": list(POS_CYCLE[index % len(POS_CYCLE)])}
        else:
            sense = GLOSSES[(index * 13 + 7) % len(GLOSSES)]
            if index % 7 == 0:
                sense += "；" + GLOSSES[(index * 17 + 3) % len(GLOSSES)]
            row = {"w": make_word(index), "frq": index + 10, "s": sense,
                   "pos": list(POS_CYCLE[(index + 2) % len(POS_CYCLE)]),
                   "raw": GLOSSES[(index * 17 + 3) % len(GLOSSES)] + "\\n"
                          + GLOSSES[(index * 19 + 9) % len(GLOSSES)]}
        rows.append(row)
    rows.extend([
        {"w": "I", "frq": 2460, "s": "我", "pos": ["pron"]},
        {"w": "i", "frq": 2461, "s": "我", "pos": ["pron"]},
        {"w": "zqgoodcaption", "frq": 2462, "s": "词", "pos": ["n"],
         "display_w": "zqgoodcaption"},
        {"w": "zqlongwordabcdefghijklmnopqrstuvwxyz", "frq": 2463, "s": "长词", "pos": ["adj"]},
        {"w": "zqx" + "x" * 100, "frq": 2464, "s": "超长词", "pos": ["adj"]},
        {"w": "zqquote", "frq": 2465, "s": "引号\"词", "pos": ["n"]},
        {"w": "zqnum", "frq": 2466, "s": "数字", "pos": ["num"]},
        # 以下应被内容策略排除（用于 excluded_count / identity.sources 差分）
        {"w": "zqetc", "frq": 2467, "s": "等等", "pos": ["abbr"]},
        {"w": "Dr", "frq": 2468, "s": "医生", "pos": ["n"]},
        {"w": "Apple", "frq": 2469, "s": "苹果公司", "pos": ["n"]},
        {"w": "中国", "frq": 2470, "s": "中国", "pos": ["n"]},
        {"w": "zqplace", "frq": 2471, "s": "中国", "pos": ["n"]},
        {"w": "zqinflect", "frq": 2472, "s": "go的过去式", "pos": ["v"]},
        {"w": "zqinflect2", "frq": 2473, "s": "go的复数", "pos": ["n"]},
        {"w": "zqnonmean", "frq": 2474, "s": "暂无释义", "pos": ["n"]},
        {"w": "zqsee", "frq": 2475, "s": "参见 zq", "pos": ["n"]},
        {"w": "zqmeta", "frq": 2476, "s": "（人名）约翰", "pos": ["n"]},
        {"w": "zqmeta2", "frq": 2477, "s": "n. 人名", "pos": ["n"]},
        {"w": "zqphrase", "frq": 2478, "s": "短语", "pos": ["n"], "type": "phrase"},
        {"w": "zqbadfrq", "frq": "1", "s": "词", "pos": ["n"]},
        {"w": "zqbadfrq2", "frq": 0, "s": "词", "pos": ["n"]},
        {"w": "zqbadpos", "frq": 2479, "s": "词", "pos": [1]},
        {"w": "zqbadcaption", "frq": 2480, "s": "词", "pos": ["n"], "display_w": "Apple"},
        {"w": "zqctrl", "frq": 2481, "s": "词\u0001", "pos": ["n"]},
        {"w": "zqreplace", "frq": 2482, "s": "词\ufffd", "pos": ["n"]},
        {"w": "zqequals", "frq": 2483, "s": "= 词", "pos": ["n"]},
        {"w": "zqabbrtag", "frq": 2484, "s": "缩写词", "pos": ["n", "abbr"]},
    ])
    return rows


def build_small_rows():
    """20 条一符一词义、两两相容的词条（单层）：用于 exhausted 停止理由。"""
    rows = []
    for index in range(20):
        gloss = CHARS[index * 4] + CHARS[index * 4 + 1]
        rows.append({"w": "zs" + _encode3(index), "frq": index + 1, "s": gloss, "pos": ["n"]})
    return rows


def _conflict_layout(target_index):
    """冲突结构：目标 T 与 5 个候选；贪心会先取“书”，从而必须走精确回退。"""
    return [
        {"w": None, "frq": 1, "s": "网", "pos": ["n"]},
        {"w": "zqbook", "frq": 2, "s": "书", "pos": ["n"]},
        {"w": "zqbooks", "frq": 3, "s": "书本", "pos": ["n"]},
        {"w": "zqjia", "frq": 4, "s": "甲书", "pos": ["n"]},
        {"w": "zqyi", "frq": 5, "s": "乙书", "pos": ["n"]},
        {"w": "zqbing", "frq": 6, "s": "丙书", "pos": ["n"]},
    ]


def build_conflict_rows():
    """搜索一个词名，使 sha256(词名)[:8] % 6 == 1（候选轮转从“书”开始）。"""
    wanted = 1
    for index in range(2000):
        target = "zq" + _encode3(index)
        offset = int.from_bytes(hashlib.sha256(target.encode("utf-8")).digest()[:8], "big")
        if offset % 6 != wanted:
            continue
        rows = _conflict_layout(wanted)
        rows[0]["w"] = target
        return rows
    raise AssertionError("找不到满足轮转起点的目标词名")


class CountingBank(vt.FrequencyBank):
    """统计 `_compatible` 调用次数：>0 说明精确回退分支被执行过。"""

    calls = 0

    def _compatible(self, left, right):
        CountingBank.calls += 1
        return super()._compatible(left, right)


# ---------------------------------------------------------------------------
# 期望提取
# ---------------------------------------------------------------------------

def source_rows_of(words):
    selected, input_count = vt._select_entries(words)
    return [[item["key"], item["word"], item["sense"], item["pos"],
             item["source_frq"], item["source_raw"]] for item in selected], input_count


def python_identity(bank, words):
    """按 app/vocabulary_test.py `FrequencyBank.__init__` 同构重建 identity。

    只读取 bank/`_select_entries` 的公开结果，不改任何状态；重建后的 sha256 必须
    等于 bank.fingerprint（下面断言），从而证明 fixture 结构与 Python 实际一致。
    """
    sources, _ = source_rows_of(words)
    testable = [key for key in bank.items if len(bank._distractors[key]) >= 3]
    return {
        "algorithm": vt.ALGORITHM, "session_schema": vt.SESSION_SCHEMA,
        "measurement_schema": vt.MEASUREMENT_SCHEMA, "unit": vt.UNIT,
        "scope": {"size": bank.size, "max_words": vt.MAX_WORDS, "band_size": vt.BAND_SIZE,
                  "local_rank": True, "bands": bank.bands},
        "model": {"a": vt.A, "c": vt.C, "b": "ln((local_rank+100)/1000)",
                  "theta_grid": [vt.THETA_MIN, vt.THETA_MAX, vt.THETA_STEP],
                  "prior": [vt.PRIOR_MEAN, vt.PRIOR_SD], "interval_level": vt.INTERVAL_LEVEL},
        "test": {"min_items": vt.MIN_ITEMS, "max_items": vt.MAX_ITEMS,
                 "min_per_band": vt.MIN_PER_BAND, "target_se": vt.TARGET_SE,
                 "content_policy": vt._CONTENT_POLICY,
                 "distractor_pool": vt._DISTRACTOR_POOL,
                 "abbreviation_keys": sorted(vt._ABBREVIATION_KEYS)},
        "sources": sources,
        "testable": testable,
    }


def identity_fingerprint(identity):
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def bank_payload(bank, words, fallback_calls=None):
    identity = python_identity(bank, words)
    fingerprint = identity_fingerprint(identity)
    if fingerprint != bank.fingerprint:
        raise AssertionError("重建 identity 的指纹与 Python bank.fingerprint 不一致")
    payload = {
        "size": bank.size,
        "excluded_count": bank.excluded_count,
        "bands": bank.bands,
        "testable_size": bank.testable_size,
        "untestable_count": bank.untestable_count,
        "identity": identity,
        "fingerprint_py": bank.fingerprint,
        "pools": {key: list(bank._distractors[key]) for key in bank.items},
        "testable": [key for key in bank.items if len(bank._distractors[key]) >= 3],
        "band_testable": {str(band): len(keys) for band, keys in bank._testable_by_band.items()},
    }
    if fallback_calls is not None:
        payload["fallback_calls_py"] = fallback_calls
    return payload


def compact_summary(summary):
    return {
        "theta": summary["theta"],
        "se": summary["se"],
        "estimate": summary["estimate"],
        "low": summary["low"],
        "high": summary["high"],
        "answered": summary["answered"],
        "correct_count": summary["correct_count"],
        "dontknow": summary["dontknow"],
        "estimate_available": summary["estimate_available"],
        "provisional": summary["provisional"],
        "coverage": summary["coverage"],
        "survey_coverage": summary["survey_coverage"],
        "stop_reason": summary["stop_reason"],
        "boundary": summary["boundary"],
        "theta_low": summary["theta_low"],
        "theta_high": summary["theta_high"],
        "bands": [
            {"id": band["id"], "answered": band["answered"], "correct": band["correct"],
             "unknown": band["unknown"], "estimate": band["estimate"],
             "low": band["low"], "high": band["high"], "p_known": band["p_known"]}
            for band in summary["bands"]
        ],
    }


def scenario_constants(bank):
    return {
        "unit": vt.UNIT,
        "interval_level": vt.INTERVAL_LEVEL,
        "measurement_schema": vt.MEASUREMENT_SCHEMA,
        "algo_py": vt.ALGORITHM,
        "coverage_target": len(bank.bands),
        "population_size": bank.size,
        "testable_size": bank.testable_size,
        "untestable_count": bank.untestable_count,
    }


def simulate(bank, seed, answer_rule):
    """完全照 app/main.py 的调用顺序模拟：next_item → append → answer → summarize。"""
    state = vt.new_state(seed)
    items, responses = [], []
    expected_next, summaries = [], []
    while True:
        record = vt.next_item(bank, state, items, responses)
        expected_next.append(None if record is None else {
            "band": record["band"],
            "phase": record["phase"],
            "key_py": record["key"],
        })
        summaries.append(compact_summary(vt.summarize(bank, items, responses)))
        if record is None:
            break
        items.append(record)
        state["asked"].append(record["key"])
        responses.append(answer_rule(len(items) - 1, record))
        summary = vt.summarize(bank, items, responses)
        state["theta"], state["se"] = summary["theta"], summary["se"]
        if len(items) > vt.MAX_ITEMS:
            raise AssertionError("模拟超过 MAX_ITEMS 仍未被停止")
    return items, responses, expected_next, summaries


def make_simulation_scenario(name, bank, bank_name, seed, answer_rule):
    items, responses, expected_next, summaries = simulate(bank, seed, answer_rule)
    return {
        "name": name,
        "kind": "simulation",
        "bank": bank_name,
        "seed": seed,
        "constants": scenario_constants(bank),
        "items": items,
        "responses": responses,
        "expected_next": expected_next,
        "summaries": summaries,
    }


def make_direct_scenario(name, bank, bank_name, items, responses):
    summary = vt.summarize(bank, items, responses)
    return {
        "name": name,
        "kind": "direct",
        "bank": bank_name,
        "constants": scenario_constants(bank),
        "items": items,
        "responses": responses,
        "summaries": [compact_summary(summary)],
    }


def rule_hash(key_char, step):
    return key_char


def hash_rule(step, record):
    digest = hashlib.sha256(record["key"].encode("utf-8")).digest()[0]
    if digest % 100 < 4:
        return -1
    return 1 if digest % 100 < 58 else 0


def random_bit_rule(step, record):
    digest = hashlib.sha256(record["key"].encode("utf-8")).digest()[1]
    return 1 if digest % 2 == 0 else 0


def always_rule(value):
    def rule(step, record):
        return value
    return rule


def alternating_rule(step, record):
    return 1 if step % 2 == 0 else 0


def find_seed(bank, rule, predicate, limit=400):
    for seed in range(1, limit):
        _, responses, _, summaries = simulate(bank, seed, rule)
        if predicate(responses, summaries):
            return seed
    raise AssertionError("找不到满足条件的固定种子")


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def build_entries_rows():
    """内容策略边界词条（JSON 可表示），覆盖正则/NFKC/casefold/字段类型边界。"""
    return [
        {"w": "plainword", "frq": 1, "s": "放弃", "pos": ["v"]},
        {"w": "multipos", "frq": 2, "s": "抛弃；离开", "pos": ["v", "vt"]},
        {"w": "well-known", "frq": 3, "s": "著名的", "pos": ["adj"]},
        {"w": "don't", "frq": 4, "s": "不", "pos": ["adv"]},
        {"w": "I", "frq": 5, "s": "我", "pos": ["pron"]},
        {"w": "i", "frq": 6, "s": "我", "pos": ["pron"]},
        {"w": "placeonly", "frq": 7, "s": "北京", "pos": ["n"]},
        {"w": "placeprefix", "frq": 8, "s": "中国的首都", "pos": ["n"]},
        {"w": "inflectonly", "frq": 9, "s": "go的过去式和过去分词", "pos": ["v"]},
        {"w": "inflectquote", "frq": 10, "s": "\"go\" 的复数形式", "pos": ["n"]},
        {"w": "meaningmention", "frq": 11, "s": "过去式形式的说明", "pos": ["n"]},
        {"w": "nonmean", "frq": 12, "s": "未收录", "pos": ["n"]},
        {"w": "seeentry", "frq": 13, "s": "见 abandon", "pos": ["v"]},
        {"w": "metaparen", "frq": 14, "s": "（地名）某处", "pos": ["n"]},
        {"w": "metasemicolon", "frq": 15, "s": "；n. 姓氏", "pos": ["n"]},
        {"w": "metaabbr", "frq": 16, "s": "acronym of something", "pos": ["n"]},
        {"w": "metaof", "frq": 17, "s": "某词的缩写", "pos": ["n"]},
        {"w": "replacement", "frq": 18, "s": "词\ufffd", "pos": ["n"]},
        {"w": "controlchar", "frq": 19, "s": "词\u0002", "pos": ["n"]},
        {"w": "equals", "frq": 20, "s": "＝词", "pos": ["n"]},
        {"w": "cjkonly", "frq": 21, "s": "㐀", "pos": ["n"]},
        {"w": "cjklast", "frq": 22, "s": "一\u4dbf二", "pos": ["n"]},
        {"w": "cjkout", "frq": 23, "s": "\u4dc0", "pos": ["n"]},
        {"w": "nfkccase", "frq": 24, "s": "甲（ＡＢＣＤ）", "pos": ["n"]},
        {"w": "nfkccase2", "frq": 25, "s": "乙（abcd）", "pos": ["n"]},
        {"w": "germancase", "frq": 26, "s": "丙（straße）", "pos": ["n"]},
        {"w": "germancase2", "frq": 27, "s": "丁（STRASSE）", "pos": ["n"]},
        {"w": "singles", "frq": 28, "s": "书", "pos": ["n"]},
        {"w": "singles2", "frq": 29, "s": "木", "pos": ["n"]},
        {"w": "compound1", "frq": 30, "s": "图书", "pos": ["n"]},
        {"w": "compound2", "frq": 31, "s": "树木", "pos": ["n"]},
        {"w": "bigram1", "frq": 32, "s": "害怕", "pos": ["v"]},
        {"w": "bigram2", "frq": 33, "s": "使害怕", "pos": ["v"]},
        {"w": "english1", "frq": 34, "s": "恐惧（frighten）", "pos": ["v"]},
        {"w": "english2", "frq": 35, "s": "惊吓（frighten）", "pos": ["v"]},
        {"w": "rawconflict", "frq": 36, "s": "单调", "pos": ["n"], "raw": "甲\\n乙"},
        {"w": "rawconflict2", "frq": 37, "s": "多调", "pos": ["n"], "raw": "甲\\n丙"},
        {"w": "captionok", "frq": 38, "s": "词", "pos": ["n"], "display_w": "  captionok  "},
        {"w": "captionbad", "frq": 39, "s": "词", "pos": ["n"], "display_w": "Apple"},
        {"w": "captionempty", "frq": 40, "s": "词", "pos": ["n"], "display_w": "   "},
        {"w": "spaced", "frq": 41, "s": "词", "pos": ["n"], "display_w": "spaced"},
        {"w": " dup", "frq": 42, "s": "词", "pos": ["n"]},
        {"w": "dup1", "frq": 43, "s": "甲", "pos": ["n"]},
        {"w": "dup1", "frq": 43, "s": "乙", "pos": ["n"]},
        {"w": "dup2", "frq": 43, "s": "丙", "pos": ["n"]},
        {"w": "dup2", "frq": 43, "s": "丁", "pos": ["n"]},
        {"w": "tiefrqA", "frq": 44, "s": "子", "pos": ["n"]},
        {"w": "tiefrqB", "frq": 44, "s": "丑", "pos": ["n"]},
        {"w": "badfrqstr", "frq": "45", "s": "词", "pos": ["n"]},
        {"w": "badfrqzero", "frq": 0, "s": "词", "pos": ["n"]},
        {"w": "badfrqneg", "frq": -1, "s": "词", "pos": ["n"]},
        {"w": "badposnone", "frq": 46, "s": "词", "pos": None},
        {"w": "badposnum", "frq": 47, "s": "词", "pos": [3]},
        {"w": "badposobj", "frq": 48, "s": "词", "pos": {"a": 1}},
        {"w": "nosense", "frq": 49, "pos": ["n"]},
        {"w": "phrase", "frq": 50, "s": "短语", "pos": ["n"], "type": "phrase"},
        {"w": "etc", "frq": 51, "s": "等等", "pos": ["abbr"]},
        {"w": "am", "frq": 52, "s": "是", "pos": ["v"]},
        {"w": "café", "frq": 53, "s": "咖啡馆", "pos": ["n"]},
        {"w": "nobody", "frq": 54, "s": "无人", "pos": ["pron"]},
    ]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    main_words = build_main_rows()
    small_words = build_small_rows()
    conflict_words = build_conflict_rows()
    banks_words = {"main": main_words, "small": small_words, "conflict": conflict_words}

    write_payload = {"description": "固定合成词表；由 gen_cat_fixtures.py 生成",
                     "banks": banks_words}
    write_json("cat-words.json", write_payload)

    # ---- banks ----
    banks = {}
    bank_payloads = {}
    banks["main"] = vt.FrequencyBank(main_words)
    banks["small"] = vt.FrequencyBank(small_words)
    CountingBank.calls = 0
    banks["conflict"] = CountingBank(conflict_words)
    fallback_calls = CountingBank.calls
    if fallback_calls <= 0:
        raise AssertionError("conflict 词表没有触发精确回退分支")
    for name in ("main", "small", "conflict"):
        calls = fallback_calls if name == "conflict" else None
        bank_payloads[name] = bank_payload(banks[name], banks_words[name], calls)
    write_json("cat-bank.json", bank_payloads)

    # ---- 内容策略边界词条 ----
    entry_rows = build_entries_rows()
    CountingBank.calls = 0
    entry_bank = CountingBank(entry_rows)
    entry_identity = python_identity(entry_bank, entry_rows)
    if identity_fingerprint(entry_identity) != entry_bank.fingerprint:
        raise AssertionError("内容策略词条 identity 重建指纹不一致")
    write_json("cat-entries.json", {
        "rows": entry_rows,
        "expected": {
            "size": entry_bank.size,
            "excluded_count": entry_bank.excluded_count,
            "bands": entry_bank.bands,
            "testable_size": entry_bank.testable_size,
            "untestable_count": entry_bank.untestable_count,
            "sources": entry_identity["sources"],
            "testable": entry_identity["testable"],
            "pools": {key: list(entry_bank._distractors[key]) for key in entry_bank.items},
            "fallback_calls_py": CountingBank.calls,
        },
    })

    # ---- 数学原语 ----
    ranks = [1, 2, 3, 7, 39, 52, 100, 500, 999, 1000, 1001, 1500, 2000, 2456, 20000]
    thetas = [-6.0, -4.9, -3.3, -1.0, 0.0, 0.25, 1.5, 3.0, 5.0, 6.9, 9.0]
    primitives = {
        "ranks": ranks,
        "thetas": thetas,
        "difficulty": [vt.difficulty(rank) for rank in ranks],
        "p_known": [[vt.p_known(theta, vt.difficulty(rank)) for rank in ranks] for theta in thetas],
        "p_correct": [[vt.p_correct(theta, vt.difficulty(rank)) for rank in ranks] for theta in thetas],
        "fisher_information": [[vt.fisher_information(theta, vt.difficulty(rank))
                                for rank in ranks] for theta in thetas],
        # Python 内建 round（银行家舍入）：JS 侧 pyRound 必须一致。
        "round_values": [0.49999999999999994, 0.5, 1.5, 2.5, 3.5, -0.5, -1.5, -2.5,
                         1234.5, 1235.5, -1234.5, 4503599627370495.5,
                         9007199254740992.0, -0.0, 0.0],
        "round_expected": [round(value) for value in [
            0.49999999999999994, 0.5, 1.5, 2.5, 3.5, -0.5, -1.5, -2.5,
            1234.5, 1235.5, -1234.5, 4503599627370495.5,
            9007199254740992.0, -0.0, 0.0]],
    }
    write_json("cat-primitives.json", primitives)

    # ---- trace 场景 ----
    main_bank = banks["main"]
    small_bank = banks["small"]

    precision_seed = find_seed(
        main_bank, hash_rule,
        lambda responses, summaries: summaries[-1]["stop_reason"] == "precision")
    max_seed = find_seed(
        main_bank, random_bit_rule,
        lambda responses, summaries: summaries[-1]["stop_reason"] == "max_items")
    all_correct_seed = find_seed(
        main_bank, always_rule(1),
        lambda responses, summaries: summaries[-1]["boundary"] == "all_correct")
    all_unknown_seed = find_seed(
        main_bank, always_rule(-1),
        lambda responses, summaries: summaries[-1]["boundary"] == "all_incorrect")
    exhausted_seed = find_seed(
        small_bank, alternating_rule,
        lambda responses, summaries: summaries[-1]["stop_reason"] == "exhausted")

    scenarios = [
        make_simulation_scenario("main-hash-precision", main_bank, "main",
                                 precision_seed, hash_rule),
        make_simulation_scenario("main-random-max-items", main_bank, "main",
                                 max_seed, random_bit_rule),
        make_simulation_scenario("main-all-correct", main_bank, "main",
                                 all_correct_seed, always_rule(1)),
        make_simulation_scenario("main-all-unknown", main_bank, "main",
                                 all_unknown_seed, always_rule(-1)),
        make_simulation_scenario("small-alternating-exhausted", small_bank, "small",
                                 exhausted_seed, alternating_rule),
    ]

    # direct 场景的合法记录池：合并多个 trace 的词条并按键去重（记录本身仍由 Python
    # next_item 生成，JS 侧会逐条重新校验 band/rank/选项兼容性）。
    record_pool = []
    seen_keys = set()
    for simulation in scenarios:
        for record in simulation["items"]:
            if record["key"] not in seen_keys:
                seen_keys.add(record["key"])
                record_pool.append(record)
    if len(record_pool) < 80:
        raise AssertionError("合并记录池不足 80 条：%d" % len(record_pool))

    direct = [
        make_direct_scenario("direct-empty", main_bank, "main", [], []),
        make_direct_scenario("direct-two-answers", main_bank, "main",
                             record_pool[:2], [1, 0]),
        make_direct_scenario("direct-mixed-ten", main_bank, "main",
                             record_pool[:10], [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]),
    ]

    grid_edge = None
    for count in (40, 50, 60):
        prefix = record_pool[:count]
        patterns = []
        for first_ones in (0, 1, 2, 3, 5, 10):
            patterns.append(("leading-ones-%d" % first_ones,
                             [1] * first_ones + [0] * (count - first_ones)))
        for last_ones in (0, 1, 2, 3, 5, 10):
            patterns.append(("trailing-ones-%d" % last_ones,
                             [0] * (count - last_ones) + [1] * last_ones))
        for position in (0, count // 4, count // 2, (3 * count) // 4, count - 1):
            single_one = [0] * count
            single_one[position] = 1
            patterns.append(("single-one-%d" % position, single_one))
            single_zero = [1] * count
            single_zero[position] = 0
            patterns.append(("single-zero-%d" % position, single_zero))
        for label, responses in patterns:
            summary = vt.summarize(main_bank, prefix, responses)
            if summary["boundary"] == "grid_edge":
                grid_edge = make_direct_scenario("direct-grid-edge", main_bank, "main",
                                                 prefix, responses)
                grid_edge["pattern"] = "%s@%d" % (label, count)
                break
        if grid_edge is not None:
            break
    if grid_edge is None:
        raise AssertionError("找不到 grid_edge 边界场景")
    direct.append(grid_edge)

    direct.append(make_direct_scenario(
        "direct-all-correct-40", main_bank, "main", record_pool[:40], [1] * 40))
    direct.append(make_direct_scenario(
        "direct-all-incorrect-40", main_bank, "main", record_pool[:40], [0] * 40))

    partial = [record for record in record_pool if record["band"] in (1, 2)]
    if len(partial) < 40:
        raise AssertionError("前两层记录不足 40 条，无法构造覆盖不足场景")
    direct.append(make_direct_scenario(
        "direct-partial-coverage", main_bank, "main", partial[:40], [1] * 40))

    scenarios.extend(direct)

    # ---- 分支覆盖自检（否则 fixture 起不到差分作用）----
    stop_reasons = set()
    boundaries = set()
    for scenario in scenarios:
        for summary in scenario["summaries"]:
            stop_reasons.add(summary["stop_reason"])
            boundaries.add(summary["boundary"])
    if not {"precision", "max_items", "exhausted"} <= stop_reasons:
        raise AssertionError("trace 未覆盖全部停止理由: %r" % (stop_reasons,))
    if None not in stop_reasons:
        raise AssertionError("trace 未覆盖 stop_reason=None")
    if not {"all_correct", "all_incorrect", "grid_edge"} <= boundaries:
        raise AssertionError("trace 未覆盖全部 boundary: %r" % (boundaries,))
    if None not in boundaries:
        raise AssertionError("trace 未覆盖 boundary=None")

    write_json("cat-trace.json", {
        "description": "Python 侧固定种子/固定答案序列的逐 step 期望（不要求 JS 选中同一词）",
        "scenarios": scenarios,
    })

    total = 0
    print("banks:", {name: (payload["size"], len(payload["bands"]),
                            payload["testable_size"], payload["untestable_count"])
                     for name, payload in bank_payloads.items()})
    print("conflict fallback calls:", fallback_calls)
    print("scenarios:", [(scenario["name"], len(scenario["items"]),
                          len(scenario["summaries"])) for scenario in scenarios])
    for name in os.listdir(OUT_DIR):
        if name.startswith("cat-") and name.endswith(".json"):
            size = os.path.getsize(os.path.join(OUT_DIR, name))
            total += size
            print("  %-20s %8d bytes" % (name, size))
    print("total fixture bytes:", total)
    print("stop_reasons:", sorted(str(value) for value in stop_reasons))
    print("boundaries:", sorted(str(value) for value in boundaries))


def write_json(name, payload):
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, allow_nan=False,
                  separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
