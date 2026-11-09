# -*- coding: utf-8 -*-
"""Build the auditable primary/middle-school meaning overlays.

The runtime bank stays untouched.  This script reads the frozen book membership,
existing bank/phrase meanings, and book-linked gloss files.  By default it is a
read-only reproducibility check; only ``--write`` replaces the generated JSON.
"""
from __future__ import print_function

import argparse
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
GLOSS = os.path.join(DATA, "school_gloss")
BANK_PATH = os.path.join(DATA, "bank.json")
PHRASES_PATH = os.path.join(DATA, "phrases.json")
PHRASE_BOOKS_PATH = os.path.join(DATA, "phrase_books.json")
BOOKS_PATH = os.path.join(DATA, "books.json")
OUT_PATH = os.path.join(DATA, "level_meanings.json")
STAGES = ("primary", "middleschool")
RULE_VERSION = "school-meaning-overlay-v3-community"
REVIEW_NOTES = {
    "alice": "书籍成员疑似人名 Alice，但本地词书无中文 gloss；当前只能保留通用 bank 回退。",
    "matt": "书籍成员疑似人名 Matt，但本地词书无中文 gloss；当前只能保留通用 bank 回退。",
    "bds": "成员缩写的教材上下文未随本地 gloss 提供；当前只能保留通用 bank 回退。",
}

CJK_RE = re.compile(r"[\u3400-\u9fff]")
POS_TOKEN = r"(?:n|v|vt|vi|adj|adv|prep|conj|pron|det|art|num|aux|int|interj|abbr|a)"
POS_RE = re.compile(r"(?<![A-Za-z])(%s)\.\s*" % POS_TOKEN, re.I)
SENSE_SEPARATORS = frozenset("；;，,、/")
LEADING_LABEL_RE = re.compile(r"^[\s（(\[【][^）)\]】]{1,12}[）)\]】]\s*")
PAREN_RE = re.compile(r"（[^）]*）|\([^)]*\)")
EMBEDDED_POS_RE = re.compile(r"(?:n|v|vt|vi|adj|adv|prep|conj|pron|det|art|num|aux|int|interj|abbr)\.\s*", re.I)
BAD_LABEL_RE = re.compile(r"(?:^[（(\[【][^）)\]】]{0,8}(?:俚|粗|俗|贬|医|计|法|化|物|军|古|方)|人名|姓氏)", re.I)
SPACE_RE = re.compile(r"\s+")
POS_CANON = {"a": "adj"}

# These are sense selectors, not authored translations.  A selector is applied
# only when that exact Chinese fragment occurs in a hashed local source; the
# emitted text is the source fragment itself.  Unsupported selectors fail safe
# to the deterministic general rule and are reported in metadata.
PREFERRED = {
    "primary": {
        "a": ("一（个）", "一个"), "an": ("一",), "i": ("我",),
        "ruler": ("尺", "尺子", "直尺"), "good": ("好的", "优良的"),
        "bear": ("熊",), "bank": ("银行",), "class": ("班级", "班"),
        "book": ("书", "书籍"), "plant": ("植物",), "play": ("玩", "玩耍"),
        "can": ("能", "能够"), "will": ("将", "将要"),
        "right": ("右边", "右方"), "left": ("左边",), "light": ("光", "光线"),
        "watch": ("看", "观看", "注视"), "orange": ("橙色", "橘色"),
        "kind": ("和蔼", "友好", "亲切"), "like": ("喜欢",),
        "fine": ("好的", "很好"), "fly": ("飞", "飞行"), "draw": ("画", "绘画"),
        "park": ("公园",), "present": ("礼物",), "letter": ("字母", "信"),
        "mean": ("意味", "意思"), "match": ("比赛",), "spring": ("春天",),
        "fall": ("秋天", "落下"), "date": ("日期",), "bat": ("蝙蝠",),
        "duck": ("鸭子",), "well": ("很好", "好"), "last": ("最后的",),
        "back": ("后面", "背部"), "close": ("关闭", "关"), "live": ("居住", "生活"),
        "read": ("阅读", "读"), "break": ("休息", "间歇"), "row": ("一排", "一行"),
        "rice": ("米饭", "稻"), "crayons": ("蜡笔",),
        "dropped": ("下降", "掉下"), "fell": ("掉下", "摔倒"),
        "jumping": ("跳", "跳跃"), "pop": ("流行音乐",),
        "minute": ("分钟",), "march": ("行军",), "March": ("三月",),
        "may": ("可以", "可能"), "May": ("五月",),
        "miss": ("想念", "错过"), "Miss": ("小姐", "女士"),
        "it": ("它",), "IT": ("信息技术",),
        "China": ("中国",), "china": ("瓷器", "瓷"),
        "US": ("美国",), "us": ("我们",),
    },
    "middleschool": {
        "a": ("一（个）", "一个"), "an": ("一",), "i": ("我",),
        "ruler": ("尺", "尺子", "直尺"), "good": ("好的", "优良的"),
        "bear": ("熊",), "bank": ("银行",), "class": ("班级", "班"),
        "can": ("能", "能够", "可以"),
        "rice": ("米饭", "稻"), "fell": ("掉下", "摔倒"),
        "jumping": ("跳", "跳跃"), "pop": ("流行音乐",),
        "recycling": ("回收利用", "回收"), "relaxed": ("放松的", "轻松的"),
        "at": ("在",), "the": ("这",), "than": ("比",), "whether": ("是否",),
        "till": ("直到",), "until": ("直到",), "however": ("然而", "可是"),
        "same": ("相同的",), "church": ("教堂",),
        "cali": ("卡利",), "not": ("表示否定",),
        "march": ("行军",), "March": ("三月",),
        "may": ("可以", "可能"), "May": ("五月",),
        "miss": ("想念", "错过"), "Miss": ("小姐", "女士"),
        "it": ("它",), "IT": ("信息技术",),
        "China": ("中国",), "china": ("瓷器", "瓷"),
        "US": ("美国",), "us": ("我们",),
    },
}

# Reviewed classroom selectors: these still have to match literal source text.
# Unreviewed secondary dictionary senses must not be appended to these words.
COMMON_CLASSROOM = {
    "term": ("学期",), "board": ("黑板", "木板", "板"),
    "sick": ("生病的", "有病的", "病的"), "open": ("打开", "开"),
    "subject": ("学科", "科目"), "matter": ("事情", "问题"),
    "practice": ("练习",), "mind": ("介意", "头脑"),
    "sound": ("声音",), "club": ("俱乐部",), "paper": ("纸",),
    "heart": ("心脏", "心"), "state": ("状态", "情况", "州"),
    "even": ("甚至",), "also": ("也",), "too": ("也",),
    "hard": ("困难的", "艰难的", "硬的", "坚硬的"),
    "raise": ("举起", "抬起", "提高"), "sign": ("标志", "符号"),
    "leave": ("离开",), "date": ("日期",),
}
for _stage in STAGES:
    PREFERRED[_stage].update(COMMON_CLASSROOM)
PREFERRED["middleschool"].update({
    "present": ("礼物",), "plant": ("植物",), "letter": ("信",),
    "right": ("正确的", "对的"), "order": ("顺序",),
})
PREFERRED_SECONDARY = {
    "middleschool": {
        "present": ("出席的",), "plant": ("栽种", "种植"),
        "letter": ("字母",), "right": ("右边", "右方"),
        "too": ("太",), "hard": ("努力地",), "sound": ("听起来",),
        "order": ("订购", "点菜"),
    },
}

# The restored community exports sometimes fold proper nouns into lowercase
# keys.  In that case, school context must not mistake China for porcelain or
# March for a military verb.  These are reviewed literal source substrings, not
# new translations or new keys.  Separate case-sensitive entries, if present,
# continue to use their own selectors above.
CASEFOLD_CONTEXT = {
    "china": ("China", {
        "primary": (("n", "中国"),),
        "middleschool": (("n", "中国"), ("adj", "中国的")),
    }),
    "march": ("March", {
        "primary": (("n", "三月"),),
        "middleschool": (("n", "三月"), ("v", "行军")),
    }),
    "may": ("May", {
        "primary": (("n", "五月"),),
        "middleschool": (("aux", "可以"), ("n", "五月")),
    }),
    "miss": ("Miss", {
        "primary": (("n", "小姐"),),
        "middleschool": (("vt", "想念"), ("n", "小姐")),
    }),
}


def read_json(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path):
    # All inputs are UTF-8 JSON; canonical LF avoids checkout-only hash drift.
    with open(path, "rb") as stream:
        payload = stream.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


def relpath(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def canonical_pos(value):
    value = (value or "").strip().lower().rstrip(".")
    return POS_CANON.get(value, value)


def split_senses(body):
    """Split punctuation only outside Chinese/ASCII parenthetical notes."""
    result, chunk, depth = [], [], 0
    for char in body:
        if char in "（(":
            depth += 1
        elif char in "）)" and depth:
            depth -= 1
        if char in SENSE_SEPARATORS and depth == 0:
            result.append("".join(chunk))
            chunk = []
        else:
            chunk.append(char)
    result.append("".join(chunk))
    return result


def clean_fragment(value):
    value = (value or "").strip(" \t\r\n，,；;。.:：·")
    # Parenthetical dictionary explanations are provenance-bearing context, not
    # part of a low-level answer.  Removing them only selects a shorter literal
    # substring; an unmatched opener is truncated rather than displayed broken.
    previous = None
    while previous != value:
        previous = value
        value = PAREN_RE.sub("", value)
    for opener, closer in (("（", "）"), ("(", ")")):
        if value.count(opener) > value.count(closer):
            value = value.split(opener, 1)[0]
        elif closer in value and opener not in value:
            value = value.split(closer, 1)[0]
        value = value.strip(closer)
    while LEADING_LABEL_RE.match(value):
        value = LEADING_LABEL_RE.sub("", value, count=1).strip()
    # Some historical glosses concatenate another POS without punctuation.
    embedded = list(EMBEDDED_POS_RE.finditer(value))
    if embedded and embedded[0].start() > 0:
        value = value[:embedded[0].start()]
    value = SPACE_RE.sub(" ", value).strip(" \t\r\n，,；;。.:：·")
    first_cjk = CJK_RE.search(value)
    if first_cjk and first_cjk.start() > 1 and " " in value[:first_cjk.start()]:
        value = value[first_cjk.start():]
    parts = value.split()
    if len(parts) > 1 and all(CJK_RE.search(part) for part in parts):
        value = parts[0]
    return value.strip(" )）")


def candidates(text, source):
    """Return ordered source fragments; each emitted sense is present in text."""
    raw = (text or "").replace("\\n", "\n").replace("\r", "\n")
    matches = list(POS_RE.finditer(raw))
    blocks = []
    if matches:
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
            blocks.append((canonical_pos(match.group(1)), raw[match.end():end]))
    else:
        blocks.append(("", raw))
    result = []
    for pos, body in blocks:
        for original in split_senses(body):
            original = original.strip()
            if not original or BAD_LABEL_RE.search(original):
                continue
            sense = clean_fragment(original)
            if not sense or not CJK_RE.search(sense):
                continue
            # Long explanatory clauses are not appropriate card answers.  They
            # remain available through the untouched general bank fallback.
            if len(sense) > 24:
                continue
            result.append({"pos": pos, "sense": sense, "source": source})
    return result


def source_record(path):
    return {"path": relpath(path), "sha256": sha256(path)}


def ordered_stage_words(books, stage, phrase_books=None):
    out, seen, book_ids = [], set(), []
    supplements = {}
    for item in (phrase_books or {}).get("items", []):
        supplements.setdefault(item.get("group"), []).append(item)
    main = next(item for item in books["mains"] if item["id"] == stage)
    for group in main.get("groups", []):
        items = list(group.get("items", [])) + supplements.get(group["id"], [])
        for item in items:
            book_ids.append(item["id"])
            for word in item.get("words", []):
                if word not in seen:
                    seen.add(word)
                    out.append(word)
    return out, book_ids


def gloss_index(book_ids, sources):
    index = {}
    for book_id in book_ids:
        path = os.path.join(GLOSS, book_id + ".json")
        if not os.path.isfile(path):
            continue
        source = relpath(path)
        sources[source] = source_record(path)
        data = read_json(path)
        for word, row in data.items():
            text = row.get("tr") if isinstance(row, dict) else ""
            if not text:
                continue
            index.setdefault(word, []).extend(candidates(text, source))
    return index


def unique_candidates(items):
    out, seen = [], set()
    for item in items:
        key = (item["pos"], item["sense"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def preferred_candidate(stage, word, items, selectors=None):
    if selectors is None:
        selectors = PREFERRED.get(stage, {}).get(word, ())
    # Any exact selector is safer than an earlier selector merely contained in
    # a long dictionary fragment.
    for selector in selectors:
        exact = [item for item in items if item["sense"] == selector]
        if exact:
            return exact[0], selector
    for selector in selectors:
        contained = [item for item in items
                     if selector in item["sense"] and len(item["sense"]) <= len(selector) + 6]
        if contained:
            contained.sort(key=lambda item: (len(item["sense"]), items.index(item)))
            return contained[0], selector
    return None, None


def pos_order(entry):
    value = entry.get("pos") or []
    if isinstance(value, str):
        value = [value]
    return [canonical_pos(item) for item in value if canonical_pos(item)]


def first_for_pos(items, pos):
    for item in items:
        if item["pos"] == pos:
            return item
    return None


def render(item, entry):
    pos = item.get("pos") or (pos_order(entry)[0] if pos_order(entry) else "")
    return ((pos + ".") if pos else "") + item["sense"]


def casefold_selection(selectors, items):
    selected = []
    for pos, fragment in selectors or ():
        matching = [item for item in items
                    if item["pos"] == pos and fragment in item["sense"]]
        if matching:
            matching.sort(key=lambda item: (item["sense"] != fragment,
                                             len(item["sense"]), items.index(item)))
            chosen = dict(matching[0])
            chosen["sense"] = fragment
            selected.append(chosen)
    return selected


def select_meaning(stage, word, entry, gloss_items, casefold_selectors=None):
    bank_source = relpath(BANK_PATH if entry.get("type") != "phrase" else PHRASES_PATH)
    bank_items = candidates(entry.get("s") or "", bank_source)
    bank_items.extend(candidates(entry.get("raw") or "", bank_source))
    all_items = unique_candidates(list(gloss_items) + bank_items)
    safe_items = [item for item in all_items if len(item["sense"]) <= 20]
    if safe_items:
        all_items = safe_items
    selected = casefold_selection(casefold_selectors, all_items)
    if selected:
        return "；".join(render(item, entry) for item in selected), {
            "source": selected[0]["source"],
            "sources": list(dict.fromkeys(item["source"] for item in selected)),
            "rule": "verified_legacy_casefold_fragment",
            "selections": [{"source": item["source"], "pos": item["pos"],
                            "fragment": item["sense"]} for item in selected],
        }
    chosen, selector = preferred_candidate(stage, word, all_items)
    if chosen is not None:
        selected = [chosen]
        secondary, secondary_selector = preferred_candidate(
            stage, word, all_items,
            selectors=PREFERRED_SECONDARY.get(stage, {}).get(word, ()))
        if secondary is not None and secondary["sense"] != chosen["sense"]:
            selected.append(secondary)
        provenance = {
            "source": chosen["source"], "rule": "verified_preferred_fragment",
            "sources": list(dict.fromkeys(item["source"] for item in selected)),
            "selector": selector,
        }
        if len(selected) > 1:
            provenance["secondary_selector"] = secondary_selector
        return "；".join(render(item, entry) for item in selected), provenance

    preferred = pos_order(entry)
    selected = []
    limit = 1 if stage == "primary" else 2
    # Prefer a book-linked gloss for each existing general POS, then the bank.
    for pos in preferred:
        item = first_for_pos(gloss_items, pos) or first_for_pos(all_items, pos)
        if item and (item["pos"], item["sense"]) not in {(x["pos"], x["sense"]) for x in selected}:
            selected.append(item)
        if len(selected) >= limit:
            break
    if not selected and all_items:
        selected.append(all_items[0])
    if not selected:
        # This is only for integrity-preserving failure reporting; tests reject
        # it for every active school-book member.
        return "", {"source": bank_source, "rule": "missing_real_meaning"}
    text = "；".join(render(item, entry) for item in selected[:limit])
    return text, {
        "source": selected[0]["source"],
        "sources": list(dict.fromkeys(item["source"] for item in selected[:limit])),
        "rule": "preferred_pos_first_source_sense" if gloss_items else "general_first_sense_fallback",
    }


def build():
    books = read_json(BOOKS_PATH)
    phrase_books = read_json(PHRASE_BOOKS_PATH) if os.path.isfile(PHRASE_BOOKS_PATH) else {}
    bank_rows = read_json(BANK_PATH)
    phrase_rows = read_json(PHRASES_PATH) if os.path.isfile(PHRASES_PATH) else []
    entries = {row["w"]: row for row in bank_rows}
    entries.update({row["w"]: row for row in phrase_rows})
    sources = {
        relpath(BOOKS_PATH): source_record(BOOKS_PATH),
        relpath(BANK_PATH): source_record(BANK_PATH),
    }
    if os.path.isfile(PHRASES_PATH):
        sources[relpath(PHRASES_PATH)] = source_record(PHRASES_PATH)
    if os.path.isfile(PHRASE_BOOKS_PATH):
        sources[relpath(PHRASE_BOOKS_PATH)] = source_record(PHRASE_BOOKS_PATH)
    source_index = os.path.join(GLOSS, "source-index.json")
    if os.path.isfile(source_index):
        sources[relpath(source_index)] = source_record(source_index)

    levels, stats, missing = {}, {}, []
    review_required = {}
    for stage in STAGES:
        words, book_ids = ordered_stage_words(books, stage, phrase_books)
        glosses = gloss_index(book_ids, sources)
        mapping = {}
        rules = {}
        review_required[stage] = []
        for word in words:
            entry = entries.get(word)
            if entry is None:
                missing.append({"stage": stage, "word": word})
                continue
            context = CASEFOLD_CONTEXT.get(word)
            selectors = context[1].get(stage) if context and context[0] not in entries else None
            meaning, provenance = select_meaning(
                stage, word, entry, glosses.get(word, []), selectors)
            mapping[word] = {"meaning": meaning, "provenance": provenance}
            if word in REVIEW_NOTES and not glosses.get(word):
                review_required[stage].append({
                    "word": word, "reason": REVIEW_NOTES[word],
                    "fallback_meaning": meaning,
                })
            rules[provenance["rule"]] = rules.get(provenance["rule"], 0) + 1
        levels[stage] = mapping
        stats[stage] = {
            "books": len(book_ids), "members": len(words), "meanings": len(mapping),
            "rules": rules,
        }
    if missing:
        raise ValueError("school members missing from bank/phrases: %r" % missing[:20])

    return {
        "schema": 1,
        "rule_version": RULE_VERSION,
        "description": "原民间词书的小学/初中短释义显示覆盖；不改通用词库或原成员，不主张官方来源。",
        "rules": {
            "general_bank_unchanged": True,
            "source_hash_normalization": "UTF-8 JSON bytes with CRLF converted to LF",
            "primary_max_sense_groups": 1,
            "middleschool_max_sense_groups": 2,
            "fallback": "existing general first common sense; never invent or pad",
            "selection": "hashed book-gloss fragment by existing POS, with verified source-fragment selectors for ambiguous school words",
        },
        "sources": dict(sorted(sources.items())),
        "stats": stats,
        "review_required": review_required,
        "levels": levels,
    }


def serialized(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def check_output(data):
    expected = serialized(data)
    try:
        with open(OUT_PATH, "rb") as stream:
            actual = stream.read()
    except IOError:
        actual = b""
    if actual != expected:
        print("LEVEL_MEANINGS OUT OF DATE: run python -B scripts/build_level_meanings.py --write")
        return 1
    print("LEVEL_MEANINGS CHECK OK primary=%d middleschool=%d sha256=%s" % (
        len(data["levels"]["primary"]), len(data["levels"]["middleschool"]),
        hashlib.sha256(actual).hexdigest()))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="rebuild in memory and compare (default)")
    group.add_argument("--write", action="store_true", help="explicitly replace generated data")
    args = parser.parse_args(argv)
    data = build()
    if args.write:
        payload = serialized(data)
        with open(OUT_PATH, "wb") as stream:
            stream.write(payload)
        print("WROTE %s primary=%d middleschool=%d sha256=%s" % (
            relpath(OUT_PATH), len(data["levels"]["primary"]),
            len(data["levels"]["middleschool"]), hashlib.sha256(payload).hexdigest()))
        return 0
    return check_output(data)


if __name__ == "__main__":
    sys.exit(main())
