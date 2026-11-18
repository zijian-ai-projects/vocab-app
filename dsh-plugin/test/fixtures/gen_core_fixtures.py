# -*- coding: utf-8 -*-
"""生成 core 差分 fixture（只读合成数据 + data/ 只读文件，绝不读写用户记录）。

用法（工作目录随意）：
    D:\\software\\anaconda\\python.exe -B -I test/fixtures/gen_core_fixtures.py

输出：与本文件同目录的 core-*.json。JS 侧 test/core.test.mjs 逐项比对。
不要手工编辑生成的 JSON；改本脚本后重跑。
"""
import copy
import datetime as dt
import hashlib
import json
import math
import os
import random as pyrandom
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE.parents[1]          # dsh-plugin
APP_DIR = PLUGIN_DIR.parent / "app"   # vocab-app/app
DATA_DIR = PLUGIN_DIR.parent / "data"  # vocab-app/data（只读）
sys.path.insert(0, str(APP_DIR))

import assessment_history as ah          # noqa: E402
import books as bk                       # noqa: E402
import entries as ent                    # noqa: E402
import learning_policy as learn          # noqa: E402
import level_meanings as lm              # noqa: E402
import prediction as pred                # noqa: E402
import scheduler as sch                  # noqa: E402
import school_knowledge as school        # noqa: E402
import study_options as so               # noqa: E402
from study_queue import StudyQueue       # noqa: E402


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_json(value):
    return sha_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")))


def sha_lines(values):
    return sha_text("\n".join(values))


def write_fixture(name, payload):
    filename = HERE / name
    with open(filename, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=False,
                  separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    print("wrote %s (%d bytes)" % (filename.name, filename.stat().st_size))


def deep(value):
    return copy.deepcopy(value)


def jsonable(value):
    """把 namedtuple / frozenset / tuple 等转成 JSON 可比对结构。"""
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value


class ScriptRng(object):
    """与 test/core.test.mjs 中 ScriptRng 完全相同的确定性 PRNG。

    Park–Miller（state = state * 48271 % 2147483647）；sample/shuffle 的抽样
    算法与 dsh-plugin/lib/core/rng.js 的 sample/shuffle 相同，供差分测试注入。
    """

    MODULUS = 2147483647
    MULTIPLIER = 48271

    def __init__(self, seed=12345):
        value = int(seed) % self.MODULUS
        self.state = value or 1
        self.calls = []

    def _next(self):
        self.state = (self.state * self.MULTIPLIER) % self.MODULUS
        return self.state

    def randrange(self, n):
        if n <= 0:
            raise ValueError("randrange need positive")
        if n == 1:
            return 0
        limit = self.MODULUS - (self.MODULUS % n)
        while True:
            value = self._next()
            if value < limit:
                return value % n

    def sample(self, seq, k):
        pool = list(seq)
        record = {"op": "sample", "n": len(pool), "k": k,
                  "seq": [item for item in pool] if len(pool) <= 40 else None}
        self.calls.append(record)
        out = []
        for index in range(k):
            picked = self.randrange(len(pool) - index)
            out.append(pool[picked])
            pool[picked] = pool[len(pool) - index - 1]
        record["out"] = list(out)
        return out

    def shuffle(self, seq):
        values = list(seq)
        record = {"op": "shuffle", "n": len(values),
                  "seq": [jsonable(item) for item in values] if len(values) <= 40 else None}
        self.calls.append(record)
        for index in range(len(values) - 1, 0, -1):
            picked = self.randrange(index + 1)
            values[index], values[picked] = values[picked], values[index]
        record["out"] = [jsonable(item) for item in values]
        return values


# --------------------------------------------------------------------------- #
# books
# --------------------------------------------------------------------------- #
def book_summary(book):
    words = book["words"]
    return {
        "id": book["id"],
        "name": book["name"],
        "display": book["display"],
        "count": book["count"],
        "kind": book["kind"],
        "type": book["type"],
        "series": book["series"],
        "is_union": book["is_union"],
        "group": book["group"],
        "main": book["main"],
        "path": book["path"],
        "source_status": book["source_status"],
        "source_version": book["source_version"],
        "count_rule": book["count_rule"],
        "official_entry_count": book["official_entry_count"],
        "source_note": book["source_note"],
        "word_count": len(words),
        "word_sha": sha_lines([str(word) for word in words]),
        "first_words": words[:3],
        "last_words": words[-3:],
    }


def catalogue_snapshot(by_id, main_list, group_map, default_id):
    mains = []
    for main in main_list:
        groups = []
        for group in main["groups"]:
            groups.append({
                "id": group["id"],
                "name": group["name"],
                "main": group["main"],
                "count": group["count"],
                "series": group["series"],
                "union": book_summary(group["union"]),
                "item_ids": [item["id"] for item in group["items"]],
            })
        mains.append({"id": main["id"], "name": main["name"], "groups": groups})

    all_ids = []
    for main in main_list:
        for group in main["groups"]:
            all_ids.append(group["union"]["id"])
            all_ids.extend(item["id"] for item in group["items"])

    def resolve(book_id):
        if book_id in by_id:
            return book_id
        return bk.LEGACY.get(book_id, default_id)

    def get(book_id):
        return by_id[resolve(book_id)]

    def name(book_id):
        book = get(book_id)
        return book["display"] or book["name"]

    def path(book_id):
        book = get(book_id)
        return " · ".join(book["path"] + [book["display"]])

    def source_info(book_id):
        book = get(book_id)
        return {
            "status": "community_compilation",
            "version": "community",
            "study_count": book["count"],
            "official_entry_count": None,
            "count_basis": ("ordered_unique_first_occurrence_union"
                            if book.get("is_union") else "existing_ordered_membership"),
            "source_ids": [],
            "sources": [],
            "note": book.get("source_note") or "词表由民间整理。",
        }

    resolve_inputs = list(by_id.keys()) + list(bk.LEGACY.keys()) + [
        "does-not-exist", None, "", 0,
    ]
    return {
        "default": default_id,
        "legacy": dict(bk.LEGACY),
        "mains": mains,
        "all_ids": all_ids,
        "by_id": {book_id: book_summary(book) for book_id, book in by_id.items()},
        "sizes": {book_id: get(book_id)["count"] for book_id in all_ids},
        "names": {book_id: name(book_id) for book_id in all_ids},
        "paths": {book_id: path(book_id) for book_id in all_ids},
        "resolve": [{"input": value, "output": resolve(value)}
                    for value in resolve_inputs],
        "source_info": {book_id: source_info(book_id)
                        for book_id in (all_ids[:5] + [default_id])},
        "source_rows": {book_id: []
                        for book_id in (all_ids[:3] + [default_id])},
        "groups_no_arg_ids": [
            group["id"] for main in main_list for group in main["groups"]
        ],
        "groups_by_main": {
            main["id"]: [group["id"] for group in main["groups"]]
            for main in main_list
        },
        "items_by_group": {
            group["id"]: [item["id"] for item in group["items"]]
            for main in main_list for group in main["groups"]
        },
    }


def build_books_fixture():
    real_by_id, real_mains, real_groups = bk.BY_ID, bk.MAINS, bk.GROUPS
    real = catalogue_snapshot(real_by_id, real_mains, real_groups, bk.DEFAULT)

    synthetic_books = {
        "schema": 2,
        "mains": [
            {
                "id": "test-main",
                "name": "测试主类",
                "groups": [
                    {
                        "id": "cet6",
                        "name": "六级",
                        "union": {"id": "cet6-all", "count": 5,
                                  "words": ["alpha", "beta", "gamma", "delta", "epsilon"]},
                        "items": [
                            {"id": "cet6-dg", "name": "六级大纲",
                             "display": "六级大纲英语词汇", "kind": "",
                             "type": "word", "series": "A", "count": 4,
                             "words": ["alpha", "beta", "gamma", "delta"]},
                            {"id": "cet6-book2", "name": "六级第二册", "display": "",
                             "kind": "book", "count": 2,
                             "words": ["beta", "epsilon"], "series": "A"},
                        ],
                    },
                    {
                        "id": "primary",
                        "name": "小学",
                        "union_name": "小学全选",
                        "union": {"id": "primary-all", "count": 2,
                                  "words": ["apple", "dog"]},
                        "items": [
                            {"id": "primary-book", "name": "小学词汇",
                             "count": 2, "words": ["apple", "dog"]},
                        ],
                    },
                ],
            }
        ],
    }
    synthetic_phrases = {
        "schema": 2,
        "items": [
            {"id": "cet6-phrases", "group": "cet6", "name": "六级词组",
             "display": "六级短语", "type": "phrase", "kind": "phrase",
             "series": "B", "count": 3, "words": ["beta", "zeta", "eta"]},
            {"id": "cet6-dg", "group": "cet6", "name": "重复 id 应被忽略",
             "display": "重复", "type": "word", "kind": "", "series": "",
             "count": 1, "words": ["nope"]},
            {"id": "orphan", "group": "no-such-group", "name": "孤儿项",
             "display": "孤儿", "type": "word", "kind": "", "series": "",
             "count": 1, "words": ["nope"]},
            {"id": "primary-phrases", "group": "primary", "name": "小学短语",
             "display": "小学短语", "type": "phrase", "kind": "phrase",
             "series": "", "count": 2, "words": ["apple", "cat"]},
        ],
    }
    minimal_books = {
        "schema": 2,
        "mains": [
            {"id": "only-main", "name": "唯一主类", "groups": [
                {"id": "only-group", "name": "唯一分组",
                 "union": {"id": "only-all", "count": 1, "words": ["x"]},
                 "items": []},
            ]},
        ],
    }

    saved_data = bk.DATA
    variants = []
    try:
        for label, books_payload, phrases_payload in (
                ("merged", synthetic_books, synthetic_phrases),
                ("fallback_default", minimal_books, None)):
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, "books.json"), "w", encoding="utf-8") as fp:
                    json.dump(books_payload, fp, ensure_ascii=False)
                if phrases_payload is not None:
                    with open(os.path.join(tmpdir, "phrase_books.json"), "w",
                              encoding="utf-8") as fp:
                        json.dump(phrases_payload, fp, ensure_ascii=False)
                bk.DATA = tmpdir
                data = bk._load()
                by_id, mains, groups = bk._build(data)
                default_id = ("cet6-dg" if "cet6-dg" in by_id
                              else next(iter(by_id)))
                snapshot = catalogue_snapshot(by_id, mains, groups, default_id)
            variants.append({
                "name": label,
                "books_json": books_payload,
                "phrase_books_json": phrases_payload,
                "expected": snapshot,
            })
    finally:
        bk.DATA = saved_data

    fixture = {"real": real, "synthetic": variants}
    write_fixture("core-books.json", fixture)


# --------------------------------------------------------------------------- #
# level_meanings
# --------------------------------------------------------------------------- #
def build_level_meanings_fixture():
    stages = list(lm.STAGES)
    real_mapping = lm.load()
    sample_keys = {}
    for stage in stages:
        keys = list(real_mapping[stage].keys())
        sample_keys[stage] = keys[:20] + keys[-10:]
    decorate_entries = []
    bank = json.load(open(DATA_DIR / "bank.json", encoding="utf-8"))
    primary_words = [word for word in real_mapping["primary"]
                     if any(entry.get("w") == word for entry in bank[:2000])][:3]
    decorated_inputs = []
    for word in primary_words:
        source = next(entry for entry in bank[:2000] if entry.get("w") == word)
        decorated_inputs.append(source)
    decorated_inputs.append({"w": "no-such-word-zz", "s": "通用释义", "pos": []})
    decorated = []
    for entry in decorated_inputs:
        stage = "primary"
        decorated.append({
            "entry": entry,
            "stage": stage,
            "output": lm.decorate(entry, real_mapping[stage]),
        })

    synthetic_files = [
        {
            "name": "top_level_strings_and_objects",
            "content": json.dumps({
                "primary": {
                    "apple": "苹果",
                    "dog": {"display_s": "狗", "display_w": "Dog", "level_s": ""},
                    "empty": "   ",
                    "bad": 123,
                    "nested": {"s": "猫", "display_w": "Cat"},
                    "bare": {"display_w": "Bare"},
                },
                "middleschool": {
                    "run": {"meaning": "跑"},
                    "swim": {"gloss": "游泳", "display_w": "Swim"},
                },
            }, ensure_ascii=False),
            "expected": None,
        },
        {
            "name": "levels_wrapper_with_alias",
            "content": json.dumps({
                "levels": {
                    "primary": {"apple": {"level_s": "苹果（小学）"}},
                    "middle": {"run": "跑（初中）"},
                    "middle_school": {"walk": "走（初中）"},
                },
            }, ensure_ascii=False),
            "expected": None,
        },
        {
            "name": "invalid_json",
            "content": "{not valid json",
            "expected": None,
        },
        {
            "name": "top_level_array",
            "content": "[1, 2, 3]",
            "expected": None,
        },
    ]
    for variant in synthetic_files:
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "level_meanings.json"), "w",
                      encoding="utf-8") as fp:
                fp.write(variant["content"])
            variant["expected"] = lm.load(os.path.join(tmpdir, "level_meanings.json"))
    translate = {
        "display_s": "display_s", "level_s": "level_s", "display_w": "display_w",
    }
    # 统一把 Python dict 原样输出即可（值都是 JSON 基础类型）。

    fixture = {
        "stages": stages,
        "real": {
            "counts": {stage: len(real_mapping[stage]) for stage in stages},
            "sha": {stage: sha_json(real_mapping[stage]) for stage in stages},
            "samples": {
                stage: {word: real_mapping[stage][word] for word in sample_keys[stage]}
                for stage in stages
            },
        },
        "decorate": decorated,
        "stage_for_main": [{"input": value, "output": lm.stage_for_main(value)}
                           for value in ("primary", "middleschool", "university",
                                         None, "", "highschool")],
        "synthetic": synthetic_files,
        "synthetic_decorate": [],
        "translate": translate,
    }
    write_fixture("core-level-meanings.json", fixture)


# --------------------------------------------------------------------------- #
# entries
# --------------------------------------------------------------------------- #
def build_entries_fixture():
    bank = json.load(open(DATA_DIR / "bank.json", encoding="utf-8"))
    phrases = json.load(open(DATA_DIR / "phrases.json", encoding="utf-8"))

    chosen = list(bank[:30])
    extras = []
    for entry in bank[:6000]:
        if entry.get("display_w") and entry not in extras:
            extras.append(entry)
        if len(extras) >= 6:
            break
    chosen.extend(extras)
    weird_ipa = []
    for entry in bank:
        value = entry.get("ipa")
        if isinstance(value, str) and value.strip() and "\\" in value:
            weird_ipa.append(entry)
            if len(weird_ipa) >= 3:
                break
    chosen.extend(weird_ipa)
    chosen.extend(list(phrases[:8]))

    display = []
    for entry in chosen:
        display.append({
            "entry": entry,
            "word_caption": ent.word_caption(entry),
            "is_phrase": ent.is_phrase(entry),
            "meaning": ent.meaning(entry),
            "pronunciation": ent.pronunciation(entry),
        })

    states = {}
    synthetic_keys = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
    states["alpha"] = {"lv": 10, "st": "mastered", "seen": 3, "due": None}
    states["beta"] = {"lv": 0, "st": "new", "seen": 0, "lapse": 0}
    states["gamma"] = {"lv": 3, "st": "learning", "seen": 2, "due": 123.0}
    states["delta"] = {"lv": 4, "st": "new", "seen": 1, "due": None}
    states["epsilon"] = {"lv": 10, "st": "retired", "seen": 9, "due": None}
    states["zeta"] = {"lv": "3", "st": "learning", "due": 5.0, "seen": "2"}
    memory_cases = []
    known = {"known-only", "alpha"}
    predicted = {"predicted-only", "gamma"}
    for key in synthetic_keys + ["known-only", "predicted-only", "absent-word"]:
        memory_cases.append({
            "key": key,
            "states": states,
            "known": sorted(known),
            "predicted": sorted(predicted),
            "output": list(ent.memory_info(key, states, known, predicted)),
        })
    memory_cases.append({
        "key": "missing",
        "states": {},
        "known": [],
        "predicted": [],
        "output": list(ent.memory_info("missing", {}, set(), set())),
    })

    fixture = {
        "categories": [list(item) for item in ent.CATEGORIES],
        "display": display,
        "memory": memory_cases,
    }
    write_fixture("core-entries.json", fixture)


# --------------------------------------------------------------------------- #
# study_options
# --------------------------------------------------------------------------- #
def choices_digest(pool):
    pool.prepare()
    out = []
    for choice in pool._choices:
        keys = sorted(key for key in choice.keys if key is not None)
        out.append({
            "text": choice.text,
            "senses": sorted(choice.senses),
            "keys": keys,
            "has_null_key": None in choice.keys,
        })
    return out


def build_study_options_fixture():
    synthetic_entries = [
        {"w": "apple", "s": "苹果", "pos": ["n."]},
        {"w": "apple2", "s": "苹果", "pos": []},
        {"w": "apple-tree", "s": "苹果；苹果树", "pos": []},
        {"w": "red-apple", "s": "n. 红苹果", "pos": []},
        {"w": "banana", "s": "香蕉", "pos": ["n."]},
        {"w": "banana2", "s": "香蕉（可数）", "pos": []},
        {"w": "orange", "s": "橘子，橙子", "pos": ["n."]},
        {"w": "grape", "s": "葡萄", "pos": []},
        {"w": "pear", "s": "梨", "pos": []},
        {"w": "peach", "s": "桃子", "pos": []},
        {"w": "melon", "s": "甜瓜/香瓜", "pos": []},
        {"w": "reserved-1", "s": "没有正确答案", "pos": []},
        {"w": "reserved-2", "s": "不认识", "pos": []},
        {"w": "empty", "s": "   ", "pos": []},
        {"w": "blank", "s": "", "raw": "", "pos": []},
        {"w": "raw-only", "raw": "仅原始释义", "pos": []},
        {"w": "display-override", "s": "应该被覆盖", "display_s": "覆盖释义",
         "level_s": "", "pos": ["n."]},
        {"w": "phrase one", "s": "一个词组", "type": "phrase", "pos": []},
        {"w": "same-sense-a", "s": "相同义项", "pos": []},
        {"w": "same-sense-b", "s": "相同义项", "pos": []},
        {"w": "same-sense-c", "s": "相同义项", "pos": []},
        {"w": "apple3", "s": "苹果；苹果树；苹果（水果）", "pos": []},
    ]
    pool = so.OptionPool(synthetic_entries)
    targets = ["apple", "banana", "orange", "grape", "raw-only",
               "display-override", "same-sense-a", "phrase one"]
    cases = []
    for target_key in targets:
        entry = next(item for item in synthetic_entries if item["w"] == target_key)
        rng = ScriptRng(20260101)
        try:
            result = so.make_options(entry, pool, rng)
            cases.append({
                "target": target_key,
                "options": result["options"],
                "correct": result["correct"],
                "calls": rng.calls,
                "error": None,
            })
        except ValueError as error:
            cases.append({"target": target_key, "error": str(error),
                          "calls": rng.calls})
    cases.append({
        "target": "empty",
        "error": None,
        "calls": [],
    })
    rng = ScriptRng(7)
    try:
        so.make_options({"w": "empty", "s": ""}, pool, rng)
        error_text = None
    except ValueError as error:
        error_text = str(error)
    cases[-1]["error"] = error_text
    cases[-1]["calls"] = rng.calls

    tiny_pool = so.OptionPool([{"w": "a", "s": "甲"}, {"w": "b", "s": "乙"}])
    rng = ScriptRng(8)
    try:
        so.make_options({"w": "a", "s": "甲"}, tiny_pool, rng)
        tiny_error = None
    except ValueError as error:
        tiny_error = str(error)
    tiny = {"entries": tiny_pool.entries, "error": tiny_error,
            "calls": rng.calls}

    # 真实词库切片：验证 POS/学段/多义项解析与选项生成。
    bank = json.load(open(DATA_DIR / "bank.json", encoding="utf-8"))
    real_entries = bank[:600]
    real_pool = so.OptionPool(real_entries)
    real_pool.prepare()
    real_targets = []
    for entry in real_entries:
        target = real_pool._target(entry)
        if so._usable(target) and target.key not in [item["target"] for item in real_targets]:
            real_targets.append({"entry": entry, "target": entry["w"]})
        if len(real_targets) >= 5:
            break
    real_cases = []
    for item in real_targets:
        rng = ScriptRng(424242)
        result = so.make_options(item["entry"], real_pool, rng)
        real_cases.append({
            "target": item["target"],
            "options": result["options"],
            "correct": result["correct"],
            "calls": rng.calls,
        })

    fixture = {
        "entries": synthetic_entries,
        "pool_size": len(pool),
        "prepared_choices": choices_digest(pool),
        "cases": cases,
        "tiny": tiny,
        "real_entries": real_entries,
        "real_pool_size": len(real_pool),
        "real_choices": choices_digest(real_pool),
        "real_cases": real_cases,
    }
    write_fixture("core-study-options.json", fixture)


# --------------------------------------------------------------------------- #
# scheduler
# --------------------------------------------------------------------------- #
def build_scheduler_fixture():
    cases = []

    def push(op, st, expected, now=None, legacy=None):
        item = {"op": op, "state": st, "expected": expected}
        if now is not None:
            item["now"] = now
        if legacy is not None:
            item["legacy"] = legacy
        cases.append(item)

    now = 1700000000.0
    push("newState", None, sch.new_state(now), now=now)
    base_states = [
        None, {}, {"lv": 0, "due": None, "seen": 0, "lapse": 0, "streak": 0,
                   "st": "new"},
        {"lv": 1, "due": 1700000300.0, "seen": 1, "lapse": 0, "streak": 0,
         "st": "learning"},
        {"lv": "3", "due": 1700000400.0, "st": "learning", "seen": "2",
         "custom": {"nested": [1, 2, 3]}},
        {"lv": 2.7, "st": "learning", "seen": 1},
        {"lv": None, "st": None, "seen": None, "due": 12},
        {"lv": 10, "st": "learning", "seen": 5},
        {"lv": 10, "st": "known", "seen": 5, "due": 99},
        {"lv": 0, "st": "retired", "seen": 2},
        {"lv": 4, "st": "mastered", "seen": 6, "retry_now": True},
        {"lv": 0, "st": "new", "seen": 0, "lapse": 0, "streak": 0,
         "due": 123, "retry_now": 77},
        {"lv": 9, "st": "learning", "seen": 8, "lapse": 2, "streak": 1,
         "due": 1700000001.5, "tags": ["x"]},
    ]
    for index, state in enumerate(base_states):
        for legacy in (False, True):
            push("migrate", state, sch.migrate_state(deep(state), legacy=legacy),
                 legacy=legacy)
        def counter_ok(field):
            if state is None or field not in state:
                return True
            return isinstance(state[field], (int, float))

        numeric_counters = all(counter_ok(field)
                               for field in ("seen", "lapse", "streak"))
        if not numeric_counters:
            continue
        for op, function in (("remember", sch.on_remember),
                             ("forget", sch.on_forget),
                             ("fuzzy", sch.on_fuzzy)):
            push(op, state, function(deep(state), now), now=now)
        push("retire", state, sch.on_retire(deep(state)))

    states_map = {
        "a": None,
        "b": {"lv": 1, "st": "learning", "due": 1700000100.0, "seen": 1},
        "c": {"lv": 0, "st": "new"},
        "d": {"lv": 3, "st": "learning", "due": 1700000000.0, "seen": 2},
        "e": {"lv": 10, "st": "mastered", "due": None, "seen": 4},
        "f": {"lv": 2, "st": "learning", "due": 1700000500.0, "seen": 2},
    }
    words = [{"w": key} for key in ("a", "b", "c", "d", "e", "f", "g")]
    migrated_modern = sch.migrate_states(deep(states_map), legacy=False)
    migrated_legacy = sch.migrate_states(deep(states_map), legacy=True)
    schema_fixture = {
        "words": words,
        "states": states_map,
        "now": 1700000100.0,
        "migrate_modern": migrated_modern,
        "migrate_legacy": migrated_legacy,
        "due_queue": sch.due_queue(words, deep(states_map), 1700000100.0),
        "review_items": sch.review_items(words, deep(states_map), 1700000100.0),
        "next_new": [
            list(sch.next_new(words, deep(states_map), cursor))
            for cursor in (0, 1, 3, 6, -2, "2")
        ],
    }
    fixture = {
        "constants": {
            "MIN": sch.MIN, "HOUR": sch.HOUR, "DAY": sch.DAY,
            "LEVELS": list(sch.LEVELS), "LEVEL_NAMES": list(sch.LEVEL_NAMES),
            "MASTERED": sch.MASTERED, "DONE": list(sch.DONE),
        },
        "cases": cases,
        "batch": schema_fixture,
    }
    write_fixture("core-scheduler.json", fixture)


# --------------------------------------------------------------------------- #
# learning_policy
# --------------------------------------------------------------------------- #
def build_learning_policy_fixture():
    raw_settings = [
        None, {}, {"mode": "review_first"}, {"mode": "daily_new_first"},
        {"mode": "bogus", "daily_new": 5}, {"daily_new": "30"},
        {"daily_new": " 30 "}, {"daily_new": "030"}, {"daily_new": 30.0},
        {"daily_new": 30.7}, {"daily_new": True}, {"daily_new": False},
        {"daily_new": None}, {"daily_new": -1}, {"daily_new": 1000},
        {"daily_new": 999}, {"daily_new": 0}, {"daily_new": "abc"},
        {"daily_new": [1]}, {"mode": "daily_new_first", "extra": {"keep": 1}},
    ]
    normalized = [{"raw": raw, "output": learn.normalize_settings(raw)}
                  for raw in raw_settings]

    ledger_cases = []
    for ledger in (
            {}, {"schema": 1}, {"days": {}},
            {"schema": 1, "days": {"2023-11-14": ["a", "b"]}},
            {"days": {"2023-2-3": []}},
            {"days": {"2023-02-30": []}},
            {"days": {"0000-01-01": []}},
            {"days": {"2023-11-14": [""]}},
            {"days": {"2023-11-14": [1]}},
            {"days": {"2023-11-14": "a"}},
            {"days": []}, [], {"days": {"2023-11-14": []}, "unknown": 5}):
        try:
            result = learn.validate_ledger(deep(ledger))
            ledger_cases.append({"ledger": ledger, "ok": bool(result), "error": None})
        except ValueError as error:
            ledger_cases.append({"ledger": ledger, "ok": False,
                                 "error": str(error)})

    def ts(year, month, day, hour=12, minute=0):
        return dt.datetime(year, month, day, hour, minute, 0).timestamp()

    behavior = []
    scenarios = [
        {"settings": {"mode": "review_first", "daily_new": 2},
         "ledger": {"schema": 1, "days": {"2024-03-01": ["a", "b", "a"]}},
         "now": ts(2024, 3, 1)},
        {"settings": {"mode": "review_first", "daily_new": 0},
         "ledger": {},
         "now": ts(2024, 3, 1)},
        {"settings": {"mode": "daily_new_first", "daily_new": 3},
         "ledger": {"days": {"2024-03-01": ["x"]}},
         "now": ts(2024, 3, 1)},
        {"settings": {"mode": "daily_new_first", "daily_new": 3},
         "ledger": {"days": {"2024-03-01": ["x", "y", "z"]}},
         "now": ts(2024, 3, 1)},
        {"settings": {"mode": "daily_new_first", "daily_new": 999},
         "ledger": {"days": {"2024-02-29": ["leap"]}},
         "now": ts(2024, 3, 1)},
    ]
    for scenario in scenarios:
        settings = learn.normalize_settings(scenario["settings"])
        settings["mode"] = scenario["settings"].get("mode", learn.REVIEW_FIRST) \
            if scenario["settings"].get("mode") in (
                learn.REVIEW_FIRST, learn.DAILY_NEW_FIRST) else learn.REVIEW_FIRST
        ledger = deep(scenario["ledger"])
        policy = learn.LearningPolicy(settings, ledger)
        now = scenario["now"]
        entry = {
            "settings": settings,
            "ledger_before": deep(scenario["ledger"]),
            "now": now,
            "daily_new_first": policy.daily_new_first,
            "limit": policy.limit,
            "learned_today": policy.learned_today(now),
            "remaining": policy.remaining(now),
            "allows_new": policy.allows_new(now),
            "should_review_before_new": policy.should_review_before_new(now),
            "next_day_time": policy.next_day_time(now),
            "local_day": learn.local_day(now),
            "introduce": [],
            "ledger_after": None,
        }
        for key, when in (("novel", now), ("a", now), ("next-day", now + 86400),
                          ("", now), ("  ", now)):
            try:
                added = policy.introduce_new(key, when)
                entry["introduce"].append({"key": key, "now": when,
                                           "added": added})
            except ValueError as error:
                entry["introduce"].append({"key": key, "now": when,
                                           "error": str(error)})
        entry["ledger_after"] = deep(ledger)
        behavior.append(entry)

    clock_times = [learn.local_day(value) for value in (
        0, 1, 86399, 86400, 1700000000.0, ts(2024, 2, 29),
        ts(2024, 3, 1), ts(2024, 12, 31, 23, 59))]
    next_days = [learn.LearningPolicy(
        {"mode": "review_first", "daily_new": 20}, {}).next_day_time(now)
        for now in (ts(2024, 2, 29), ts(2024, 3, 31), ts(2024, 12, 31, 23, 59))]

    fixture = {
        "constants": {
            "REVIEW_FIRST": learn.REVIEW_FIRST,
            "DAILY_NEW_FIRST": learn.DAILY_NEW_FIRST,
            "DEFAULTS": learn.DEFAULTS,
            "MAX_DAILY_NEW": learn.MAX_DAILY_NEW,
        },
        "normalize": normalized,
        "ledger": ledger_cases,
        "behavior": behavior,
        "clock": clock_times,
        "next_day_time": next_days,
    }
    write_fixture("core-learning-policy.json", fixture)


# --------------------------------------------------------------------------- #
# school_knowledge
# --------------------------------------------------------------------------- #
def build_school_fixture():
    levels = [list(item) for item in school.LEVELS]
    words_output = {}
    for key, _label in school.LEVELS:
        values = sorted(school.words(key))
        words_output[key] = {
            "count": len(values),
            "sha": sha_lines(values),
            "first": values[:20],
            "last": values[-20:],
        }
    fixture = {
        "levels": levels,
        "books": list(school.BOOKS),
        "normalize": [{"input": value, "output": school.normalize(value)}
                      for value in ("off", "primary", "middle", "high",
                                    "bogus", None, "", 3)],
        "words": words_output,
    }
    write_fixture("core-school-knowledge.json", fixture)


# --------------------------------------------------------------------------- #
# prediction
# --------------------------------------------------------------------------- #
def build_prediction_fixture():
    valid = pred.new_prediction_data()
    valid["selected"] = ["b", "c"]
    valid["effective"] = {"target": 5, "available": 9, "selected": 2}
    valid_again = deep(valid)
    validate_cases = []
    for document in (
            valid,
            {}, {"schema": 1}, {"schema": 2, "selected": [], "rejected": [],
                                "excluded": [],
                                "effective": {"target": 0, "available": 0,
                                              "selected": 0}},
            {"schema": 1, "selected": ["a", "a"], "rejected": [],
             "excluded": [],
             "effective": {"target": 0, "available": 0, "selected": 2}},
            {"schema": 1, "selected": [], "rejected": [""], "excluded": [],
             "effective": {"target": 0, "available": 0, "selected": 0}},
            {"schema": 1, "selected": [], "rejected": [], "excluded": [],
             "effective": {"target": -1, "available": 0, "selected": 0}},
            {"schema": 1, "selected": ["a"], "rejected": [], "excluded": [],
             "effective": {"target": 1, "available": 1, "selected": 0}}):
        try:
            result = pred.validate_prediction_data(deep(document))
            validate_cases.append({"document": document, "ok": True,
                                   "error": None,
                                   "returned_same": result == document})
        except ValueError as error:
            validate_cases.append({"document": document, "ok": False,
                                   "error": str(error)})

    strategy_cases = []
    for estimate, error, strategy in (
            (100, 10.5, "conservative"), (100, 10.5, "estimate"),
            (100, 10.5, "optimistic"), (0, 0, "conservative"),
            (2.5, 0, "estimate"), (3.5, 0, "estimate"),
            (10, 20, "conservative"),
            (1e6, 1e-3, "optimistic"), (0.5, 0.5, "estimate"),
            (2.675, 0.0, "estimate")):
        strategy_cases.append({
            "estimate": estimate, "error": error, "strategy": strategy,
            "output": pred.apply_strategy(estimate, error, strategy),
        })
    for estimate, error, strategy in (
            (100, 10, "bogus"), (100, 10, None), (True, 1, "estimate"),
            (100, -1, "estimate"), ("100", 1, "estimate"),
            (-1, 5, "conservative"), (100, 10, 3)):
        try:
            pred.apply_strategy(estimate, error, strategy)
            strategy_cases.append({"estimate": estimate, "error": error,
                                   "strategy": strategy, "output": None,
                                   "value_error": None})
        except ValueError as error_object:
            strategy_cases.append({"estimate": estimate, "error": error,
                                   "strategy": strategy, "output": None,
                                   "value_error": str(error_object)})

    entries_list = [
        {"w": "w01", "lvl": 1}, {"w": "w02", "lvl": 1}, {"w": "w03", "lvl": 1},
        {"w": "w04", "lvl": 2}, {"w": "w05", "lvl": 2}, {"w": "w06", "lvl": 3},
        {"w": "w07", "lvl": 3}, {"w": "w08", "lvl": 3}, {"w": "w09", "lvl": 3},
        {"w": "w10", "lvl": 4}, {"w": "w11"},
        {"w": "", "lvl": 1}, {"w": None, "lvl": 1},
    ]
    states = {"w02": {"lv": 1, "st": "learning", "due": 1.0},
              "w06": {"lv": 0, "st": "new"}}
    selection_cases = []

    def run_selection(name, target, bands=None, rejected=None, excluded=None,
                      seed=777):
        module_random = pred.random
        pred.random = types.SimpleNamespace(Random=lambda value: ScriptRng(value))
        try:
            selected, counts = pred.select_prediction_candidates(
                deep(entries_list), deep(states), target, bands=bands,
                rejected=rejected, excluded=excluded, seed=seed)
        finally:
            pred.random = module_random
        selection_cases.append({
            "name": name, "target": target, "bands": bands,
            "rejected": rejected, "excluded": excluded, "seed": seed,
            "selected": sorted(selected), "counts": counts,
        })

    run_selection("full_levels", 3)
    run_selection("partial_band", 4)
    run_selection("single_from_band", 1)
    run_selection("all", 99)
    run_selection("zero", 0)
    run_selection("excluded_and_rejected", 2,
                  rejected=["w01"], excluded=["w04"])
    run_selection("bands_map_partial", 2,
                  bands={"w01": 1, "w02": 1, "w03": 1, "w04": 2, "w05": 2})
    run_selection("bands_array", 3,
                  bands=[1, 1, 1, 2, 2, 3, 3, 3, 3, 4, 4, 1, 1])
    run_selection("seed_zero", 2, seed=0)

    selection_errors = []
    for name, kwargs in (
            ("bad_target", {"target": -1}),
            ("bad_target_bool", {"target": True}),
            ("bad_states", {"target": 1, "states": []}),
            ("bad_bands", {"target": 1, "bands": [1, 2]}),
            ("bad_level", {"target": 1, "bands": {"w01": "one", "w02": 2}}),
            ("bad_level_bool", {"target": 1, "bands": {"w01": True, "w02": 2}})):
        arguments = {"entries": deep(entries_list),
                     "states": deep(states), "target": kwargs.pop("target")}
        arguments.update({"bands": kwargs.pop("bands", None)})
        arguments.update(kwargs)
        try:
            pred.select_prediction_candidates(**arguments)
            selection_errors.append({"name": name, "error": None})
        except ValueError as error:
            selection_errors.append({"name": name, "error": str(error)})

    fixture = {
        "constants": {"SCHEMA": pred.SCHEMA,
                      "STRATEGIES": list(pred.STRATEGIES)},
        "new_data": pred.new_prediction_data(),
        "validate": validate_cases,
        "strategy": strategy_cases,
        "entries": entries_list,
        "states": states,
        "selection": selection_cases,
        "selection_errors": selection_errors,
    }
    write_fixture("core-prediction.json", fixture)


# --------------------------------------------------------------------------- #
# assessment_history
# --------------------------------------------------------------------------- #
def build_assessment_history_fixture():
    saved_algorithm = ah.ALGORITHM
    ah.ALGORITHM = "vst-cat-v143-web"  # 与 DSH 版 core 一致后做差分
    try:
        current_record = {
            "algo": "vst-cat-v143-web", "measurement_schema": 3,
            "unit": "frequency_ranked_entries", "bank_id": "bank-x",
            "estimate_available": True, "completed": True,
            "ts": 1700000000, "vocab": 4321,
        }
        records = [
            current_record,
            {"algo": "vst-cat-v142", "measurement_schema": 3,
             "unit": "frequency_ranked_entries", "ts": 1, "vocab": 2},
            {"algo": "vst-cat-v143-web", "measurement_schema": 2,
             "unit": "frequency_ranked_entries"},
            {},
            {"estimate_available": False, "ts": 1, "vocab": 2},
            {"ts": "1", "vocab": 2},
            {"ts": True, "vocab": 2},
            {"ts": 1, "vocab": None},
            {"algo": "vst-cat-v143-web", "measurement_schema": 3,
             "unit": "frequency_ranked_entries", "completed": False,
             "estimate_available": True, "ts": 5, "vocab": 6},
            {"algo": "legacy", "bank_id": "b0", "ts": 7, "vocab": 8},
        ]
        odd_records = [None, []]
        is_current = [{"record": record, "output": ah.is_current(record)}
                      for record in records + odd_records]
        series = [{"record": record, "output": list(ah.series_key(record))}
                  for record in records]
        plot = [{"record": record, "output": ah.plottable(record)}
                for record in records + odd_records]
        history = [
            {"algo": "vst-cat-v143-web", "measurement_schema": 3,
             "unit": "frequency_ranked_entries", "bank_id": "b1",
             "completed": True, "estimate_available": True,
             "ts": 1, "vocab": 10},
            {"algo": "vst-cat-v143-web", "measurement_schema": 3,
             "unit": "frequency_ranked_entries", "bank_id": "b2",
             "completed": True, "estimate_available": True,
             "ts": 2, "vocab": 20},
            {"algo": "legacy", "bank_id": "b1", "ts": 3, "vocab": 30},
            {"algo": "vst-cat-v143-web", "measurement_schema": 3,
             "unit": "frequency_ranked_entries", "bank_id": "b1",
             "completed": False, "estimate_available": True,
             "ts": 4, "vocab": 40},
            {"algo": "vst-cat-v143-web", "measurement_schema": 3,
             "unit": "frequency_ranked_entries", "bank_id": "b1",
             "completed": True, "estimate_available": True,
             "ts": 5, "vocab": 50},
        ]
        comparable = ah.comparable(history, history[0])
        trend = ah.current_trend(history, "b1")

        archive_cases = []
        session = {"id": "s1", "state": {"theta": 1.5, "asked": ["a", "b"]},
                   "items": [{"key": "a"}], "resp": [{"answer": 1}], "i": 1}
        base_progress = {"quiz_session": deep(session), "history": []}

        def run_archive(name, progress_input, timestamp, reason):
            progress = deep(progress_input)
            try:
                result = ah.archive_session(progress, timestamp, reason)
                archive_cases.append({
                    "name": name, "timestamp": timestamp, "reason": reason,
                    "input": deep(progress_input), "progress": progress,
                    "returned": result, "error": None,
                })
            except ValueError as error:
                archive_cases.append({
                    "name": name, "timestamp": timestamp, "reason": reason,
                    "input": deep(progress_input), "progress": None,
                    "returned": None, "error": str(error),
                })

        run_archive("fresh", base_progress, 1700000000, "new_attempt")
        dedupe_progress = deep(base_progress)
        dedupe_progress["quiz_archives"] = [
            {"archived_at": 1, "reason": "old", "session": deep(session)},
        ]
        run_archive("dedupe_deep_equal", dedupe_progress, 1700000001,
                    "new_attempt")
        bad_archives = deep(base_progress)
        bad_archives["quiz_archives"] = "not-a-list"
        run_archive("bad_archives", bad_archives, 1, "new_attempt")
        run_archive("no_session", {"quiz_session": None, "history": []},
                    1, "x")
        run_archive("missing_session", {}, 1, "x")

        fixture = {
            "constants": {
                "ALGORITHM": ah.ALGORITHM,
                "UNIT": ah.UNIT,
                "MEASUREMENT_SCHEMA": ah.MEASUREMENT_SCHEMA,
            },
            "is_current": is_current,
            "series_key": series,
            "plottable": plot,
            "history": history,
            "comparable_reference": history[0],
            "comparable_output": comparable,
            "trend_bank": "b1",
            "trend_output": trend,
            "archives": archive_cases,
        }
        write_fixture("core-assessment-history.json", fixture)
    finally:
        ah.ALGORITHM = saved_algorithm


# --------------------------------------------------------------------------- #
# exactSum（math.fsum 语义）
# --------------------------------------------------------------------------- #
def build_sum_fixture():
    case_values = [
        [0.1, 0.2],
        [0.1, 0.2, 0.3],
        [1e16, 1.0, -1e16],
        [1.0, 1e-16, 1e-16],
        [0.1] * 10,
        [0.1] * 1000,
        [-0.1] * 1000,
        [1, 2, 3, 4, 5],
        [1.5, -0.5],
        [1e308, 1e-308],
        [1e-308, -1e-308],
        [2.0 ** 53, 1.0],
        [2.0 ** 53, 1.0, 1.0],
        [2.0 ** 53, -1.0],
        [float(2 ** 52), 0.5],
        [0.0, -0.0],
        [],
        [1.0000000000000002, 1.0000000000000002, -2.0000000000000004],
        [123456789.123456789, -123456789.123456789, 1e-9],
        [5e-324, 5e-324],
    ]
    cases = [{"values": values, "output": math.fsum(values)}
             for values in case_values]
    fixture = {"cases": cases}
    write_fixture("core-sum.json", fixture)


# --------------------------------------------------------------------------- #
# study_queue（固定时钟轨迹）
# --------------------------------------------------------------------------- #
def build_queue_fixture():
    base = 1700000000.0
    scenarios = []

    def item_snapshot(item):
        if item is None:
            return None
        return {
            "kind": item["kind"],
            "key": item["w"]["w"],
            "w": deep(item["w"]),
            "st": deep(item["st"]),
            "idx": item["idx"],
        }

    def run_scenario(name, words, states, record, steps,
                     excluded=None, known=None, retry_gap=4):
        state_dict = deep(states)
        record_dict = deep(record)
        queue = StudyQueue([{"w": word} for word in words], state_dict,
                           record_dict, retry_gap=retry_gap,
                           known=set(known or ()), excluded=set(excluded or ()))
        record_after_init = deep(record_dict)
        cursor_after_init = queue.cursor
        trace = []
        pending_item = None
        for step in steps:
            now = step["now"]
            if step["op"] == "next":
                pending_item = queue.next(now)
                trace.append({
                    "op": "next", "now": now,
                    "item": item_snapshot(pending_item),
                    "cursor": queue.cursor,
                    "next_due": queue.next_due_time(now),
                    "record": deep(record_dict),
                    "states": deep(state_dict),
                })
            else:
                after = queue.answer(pending_item, step["remember"], now)
                trace.append({
                    "op": "answer", "now": now,
                    "remember": step["remember"],
                    "state": deep(after),
                    "cursor": queue.cursor,
                    "next_due": queue.next_due_time(now),
                    "record": deep(record_dict),
                    "states": deep(state_dict),
                })
                pending_item = None
        scenarios.append({
            "name": name,
            "words": [{"w": word} for word in words],
            "states": deep(states),
            "record": deep(record),
            "excluded": sorted(excluded or ()),
            "known": sorted(known or ()),
            "retry_gap": retry_gap,
            "record_after_init": record_after_init,
            "cursor_after_init": cursor_after_init,
            "steps": steps,
            "trace": trace,
        })

    # A. review_first 默认策略的 20 步（10 次 next/answer）。
    steps_a = []
    clock = base
    for index in range(10):
        steps_a.append({"op": "next", "now": clock})
        steps_a.append({"op": "answer", "remember": index % 3 != 2,
                        "now": clock + 1})
        clock += 7
    run_scenario("review_first_trajectory", [f"w{index}" for index in range(12)],
                 {}, {}, steps_a)

    # C. A retry is delayed until four other first-new answers are complete.
    steps_c = [
        {"op": "next", "now": base},
        {"op": "answer", "remember": False, "now": base + 1},
        {"op": "next", "now": base + 2},
        {"op": "answer", "remember": True, "now": base + 3},
        {"op": "next", "now": base + 3},
        {"op": "answer", "remember": True, "now": base + 4},
        {"op": "next", "now": base + 4},
        {"op": "answer", "remember": True, "now": base + 5},
        {"op": "next", "now": base + 6},
        {"op": "answer", "remember": True, "now": base + 7},
        {"op": "next", "now": base + 8},
        {"op": "next", "now": base + 400},
        {"op": "answer", "remember": True, "now": base + 401},
        {"op": "next", "now": base + 402},
        {"op": "answer", "remember": True, "now": base + 403},
        {"op": "next", "now": base + 404},
        {"op": "answer", "remember": True, "now": base + 405},
        {"op": "next", "now": base + 406},
        {"op": "next", "now": base + 500},
        {"op": "answer", "remember": True, "now": base + 501},
    ]
    run_scenario("retry_gap_and_book_end", ["a", "b", "c", "d", "e", "f"], {}, {},
                 steps_c)

    # D. excluded 学校词：跳过新词与复习，但保留挂起记录。
    steps_d = []
    steps_d.append({"op": "next", "now": base})
    steps_d.append({"op": "answer", "remember": True, "now": base + 1})
    steps_d.append({"op": "next", "now": base + 2})
    steps_d.append({"op": "answer", "remember": True, "now": base + 3})
    steps_d.append({"op": "next", "now": base + 4})
    run_scenario("excluded_is_skipped", ["a", "b", "c", "d"], {}, {},
                 steps_d, excluded=["b", "c"])

    # E. 已保存 current 指向被学校词表暂停的词：移入 policy_held 后继续。
    steps_e = [
        {"op": "next", "now": base},
        {"op": "answer", "remember": True, "now": base + 1},
        {"op": "next", "now": base + 2},
    ]
    run_scenario("park_excluded_current", ["a", "b", "c"],
                 {}, {"current": {"kind": "new", "key": "b"}},
                 steps_e, excluded=["b"])

    # F. 旧计数/current.w 兼容；异常 pending 目标保持不透明，不推断为 ready。
    damaged = {
        "cursor": "-3",
        "new_count": "7",
        "pending": {"a": "bad", "b": "2", "zzz": 5},
        "current": {"w": {"w": "b"}, "extra": 1},
        "held_current": {"kind": "review", "key": "c", "extra": 2},
        "last_retry": "b",
        "policy_held": [],
    }
    steps_f = [
        {"op": "next", "now": base},
        {"op": "answer", "remember": False, "now": base + 1},
        {"op": "next", "now": base + 2},
        {"op": "next", "now": base + 3},
    ]
    run_scenario("damaged_record", ["a", "b", "c"], {}, damaged, steps_f)
    # Unknown targets are not made ready, nor replaced during initialization.

    # Nested interruptions must keep both the held new and the retry metadata.
    run_scenario("nested_review_retry_restore", ["a", "p", "old"],
                 {"p": sch.on_forget(sch.new_state(), base),
                  "old": {"st": "learning", "lv": 2, "due": base + 10, "seen": 2}},
                 {"new_count": 5, "pending": {"p": 5},
                  "current": {"kind": "new", "key": "a", "custom": {"new": [1]}},
                  "policy_held": [{"kind": "retry", "key": "p", "custom": {"retry": [2]}}]},
                 [{"op": "next", "now": base},
                  {"op": "next", "now": base + 10},
                  {"op": "answer", "remember": True, "now": base + 10},
                  {"op": "next", "now": base + 10},
                  {"op": "answer", "remember": True, "now": base + 10},
                  {"op": "next", "now": base + 10}])

    # G. known 预测词：只跳过没有显式状态的词。
    steps_g = [
        {"op": "next", "now": base},
        {"op": "answer", "remember": False, "now": base + 1},
        {"op": "next", "now": base + 2},
        {"op": "answer", "remember": True, "now": base + 3},
        {"op": "next", "now": base + 4},
        {"op": "answer", "remember": True, "now": base + 5},
        {"op": "next", "now": base + 6},
    ]
    run_scenario("known_is_skipped", ["a", "b", "c", "d"], {},
                 {}, steps_g, known=["b"])

    # 构造期校验失败
    construction_errors = []

    def try_construct(name, words, states, record, exact=True, **options):
        try:
            StudyQueue([{"w": word} for word in words], deep(states),
                       deep(record), **options)
            construction_errors.append({"name": name, "error": None,
                                        "exact": exact})
        except (TypeError, ValueError) as error:
            construction_errors.append({"name": name, "error": str(error),
                                        "exact": exact})

    try_construct("states_not_dict", ["a"], [], {})
    try_construct("record_not_dict", ["a"], {}, [])
    try_construct("pending_not_dict", ["a"], {}, {"pending": []})
    try_construct("policy_held_not_list", ["a"], {}, {"policy_held": "x"})
    try_construct("policy_held_item_not_dict", ["a"], {},
                  {"policy_held": [1]})
    try_construct("retry_gap_zero", ["a"], {}, {}, retry_gap=0)
    try_construct("retry_gap_negative", ["a"], {}, {}, retry_gap=-2)
    try_construct("retry_gap_string", ["a"], {}, {}, exact=False,
                  retry_gap="abc")

    # answer 的 stale/错配保护
    answer_errors = []
    words = [{"w": "a"}, {"w": "b"}]
    states = {}
    record = {}
    queue = StudyQueue(words, states, record, retry_gap=4, known=set(),
                       excluded=set())
    first = queue.next(base)
    queue.answer(first, True, base + 1)
    for name, item, remember in (
            ("double_answer", deep(first), True),
            ("wrong_kind", {"kind": "review", "w": {"w": "a"},
                            "st": None, "idx": 0}, True),
            ("missing_key", {"kind": "new", "w": {"w": "zzz"},
                             "st": None, "idx": 0}, True)):
        try:
            queue.answer(item, remember, base + 2)
            answer_errors.append({"name": name, "error": None})
        except ValueError as error:
            answer_errors.append({"name": name, "error": str(error)})

    fixture = {
        "base": base,
        "scenarios": scenarios,
        "construction_errors": construction_errors,
        "answer_errors": answer_errors,
    }
    write_fixture("core-queue.json", fixture)


def main():
    build_books_fixture()
    build_level_meanings_fixture()
    build_entries_fixture()
    build_study_options_fixture()
    build_scheduler_fixture()
    build_learning_policy_fixture()
    build_school_fixture()
    build_prediction_fixture()
    build_assessment_history_fixture()
    build_queue_fixture()
    build_sum_fixture()
    print("all fixtures generated in", HERE)


if __name__ == "__main__":
    main()
