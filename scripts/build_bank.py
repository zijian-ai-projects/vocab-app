# -*- coding: utf-8 -*-
"""构建 V1.1 大词库：8 个考试标签并集 + 人教版 PEP 小初词表，A–Z 排列。

用法：
    python scripts/build_bank.py --todo   # 只生成 data/bank_todo.json（待抓有道的词）
    python scripts/build_bank.py          # 合并 raw_youdao*.jsonl 生成 data/bank.json

bank.json 字段（在 v1.0 words.json 基础上加难度）：
    w / ipa / pos[] / s / tags[] / frq / collins / raw / ph_raw / lvl(0-14) / b
"""
import csv
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_words as bw  # noqa: E402

ECDICT = r"D:\user\Documents\deepseek-harness\default-workspace\ECDICT\ecdict.csv"
DATA = os.path.join(ROOT, "data")
BANK = os.path.join(DATA, "bank.json")
TODO = os.path.join(DATA, "bank_todo.json")
LOG = os.path.join(DATA, "build_bank.log")
EIGHT = ["zk", "gk", "cet4", "cet6", "ky", "ielts", "toefl", "gre"]
CLEAN = re.compile(r"^[a-z][a-z'-]*$")
BANDS = 15
# PEP 原始词表里的小毛病：拼写错/比较级/所有格/品牌名，能归一的归一，归不了的就丢掉
PEP_ALIAS = {
    "humorou": "humorous", "tomoto": "tomato", "smart-smarter": "smart",
    "teacher's": "teacher", "teachers'": "teacher",
    "selfimprovement": "self-improvement",
}
PEP_DROP = {"wildaid"}


def clean_pep_word(w):
    w = clean_word(w)
    if not w or w in PEP_DROP:
        return None
    return PEP_ALIAS.get(w, w)


def clean_word(w):
    w = (w or "").strip().lower()
    return w if (len(w) >= 2 and CLEAN.match(w)) else None


def load_pep():
    out = []
    for name in ("primary", "middle"):
        path = os.path.join(DATA, "pep_%s.json" % name)
        if not os.path.exists(path):
            continue
        for x in json.load(io.open(path, encoding="utf-8")):
            w = clean_pep_word(x.get("w"))
            if w:
                out.append((w, x))
    return out


def load_ecdict(needed):
    rows = {}
    csv.field_size_limit(10 ** 7)
    with io.open(ECDICT, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            w = (row.get("word") or "").strip().lower()
            if w in needed and w not in rows:
                rows[w] = {
                    "word": w,
                    "phonetic": (row.get("phonetic") or "").strip(),
                    "translation": (row.get("translation") or "").strip(),
                    "tag": (row.get("tag") or "").strip().split(),
                    "frq": (row.get("frq") or "").strip(),
                    "collins": (row.get("collins") or "").strip(),
                    "bnc": (row.get("bnc") or "").strip(),
                    "exchange": (row.get("exchange") or "").strip(),
                }
    return rows


def load_raw():
    got = {}
    for name in ("raw_youdao.jsonl", "raw_youdao_bank.jsonl"):
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            continue
        for line in io.open(path, encoding="utf-8"):
            try:
                o = json.loads(line)
            except Exception:
                continue
            if not isinstance(o, dict):
                continue
            w = (o.get("word") or "").lower()
            if w and not o.get("error"):
                got[w] = o
    return got


def load_existing():
    path = os.path.join(DATA, "words.json")
    if not os.path.exists(path):
        return {}
    out = {}
    for x in json.load(io.open(path, encoding="utf-8")):
        out[x["w"].lower()] = x
    return out


def to_int(s):
    try:
        n = int(str(s or "").strip())
    except Exception:
        n = 0
    return n if n > 0 else 0


def e_pos_set(trans):
    out = set()
    for line in (trans or "").replace("\\n", "\n").split("\n"):
        m = bw.POS_RE.match(line.strip())
        if m:
            out.add(m.group(1).lower())
    return out


def senses_from(ec, trans):
    """有道优先、ECDICT 兜底，返回 (pos 列表, 卡面释义)。"""
    raw_groups = bw.groups_from_youdao(ec)
    if not raw_groups:
        raw_groups = bw.groups_from_ecdict(trans)
    eps = e_pos_set(trans)
    groups = [(bw.refine(p, eps) if p else "", ts) for p, ts in raw_groups]
    groups = [(p, ts) for p, ts in groups if ts]
    if not groups:
        return [], ""
    if len(groups) == 1:
        p0, ts = groups[0]
        keep = [(p0, ts[:2])]
        s = ((p0 + "；".join(ts[:2])) if p0 else "；".join(ts[:2]))
    else:
        keep = [(g[0], g[1][:1]) for g in groups[:2]]
        s = "；".join(("%s%s" % (p, t)) if p else t for p, ts in keep for t in ts)
    s = bw.cap_meanings(s)
    return [p for p, _ in keep if p], s


def rank_of(w, e, rows, seen=None):
    """词的难度排名：frq > bnc > 词形还原后的原词；都没有则返回 None。"""
    if e:
        for key in ("frq", "bnc"):
            n = to_int(e.get(key))
            if n:
                return n
        m = re.search(r"(?:^|/)0:([^/]+)", e.get("exchange") or "")
        if m:
            lemma = m.group(1).strip().lower()
            if lemma and lemma != w and lemma in rows:
                return rank_of(lemma, rows[lemma], rows)
    return None


def plain_senses(e, y):
    """最后一道兜底：剥掉 [医]/[人名] 这类方括号前缀，取第一行中文释义。"""
    lines = []
    for line in (e.get("translation") or "").replace("\\n", "\n").split("\n"):
        line = re.sub(r"^\[[^\]]*\]\s*", "", line.strip())
        if line:
            lines.append(line)
    if not lines:
        for x in (y.get("ec") or []):
            t = re.sub(r"^\s*(n|v|vt|vi|adj|adv|a|prep|conj|pron|num|art|int|aux|abbr|rel|interrog|part)\.\s*",
                       "", str(x), flags=re.I)
            if t.strip():
                lines.append(t.strip())
    return bw.cap_meanings(lines[0]) if lines else ""


def build_entries(rows, needed, pep_by_word, existing, raw):
    entries = []
    stat = {"reuse": 0, "ydl": 0, "ecd": 0, "pep": 0, "plain": 0, "noipa": 0}
    for w in sorted(needed):
        e = rows.get(w) or {"phonetic": "", "translation": "", "tag": [],
                            "frq": "", "collins": "", "bnc": "", "exchange": ""}
        old = existing.get(w)
        if old and old.get("s"):
            entries.append({
                "w": w,
                "ipa": old.get("ipa") or e["phonetic"],
                "pos": old.get("pos") or [],
                "s": old["s"],
                "tags": old.get("tags") or e["tag"],
                "frq": to_int(old.get("frq")) or to_int(e.get("frq")),
                "collins": old.get("collins") or e["collins"],
                "raw": old.get("raw") or e["translation"],
                "ph_raw": old.get("ph_raw") or e["phonetic"],
            })
            stat["reuse"] += 1
            continue
        y = raw.get(w) or {}
        pos, s = senses_from(y.get("ec") or [], e["translation"])
        if s:
            stat["ydl" if y else "ecd"] += 1
        else:
            p = pep_by_word.get(w) or {}
            s = bw.cap_meanings(p.get("s") or "")
            pos = [p.get("pos").rstrip(".") + "."] if p.get("pos") else []
            if s:
                stat["pep"] += 1
        if not s:
            s = plain_senses(e, y)
            if s:
                stat["plain"] += 1
        if not s:
            continue
        ipa = y.get("usphone") or y.get("ukphone") or e["phonetic"] or ""
        if not ipa:
            ipa = (pep_by_word.get(w) or {}).get("ipa") or ""
            stat["noipa"] += 1
        entries.append({
            "w": w,
            "ipa": ipa,
            "pos": pos,
            "s": s,
            "tags": e["tag"],
            "frq": to_int(e.get("frq")),
            "collins": e["collins"],
            "raw": e["translation"] or (pep_by_word.get(w) or {}).get("s") or "",
            "ph_raw": e["phonetic"] or (pep_by_word.get(w) or {}).get("ipa") or "",
        })
    return entries, stat


def assign_difficulty(entries, rows):
    n = len(entries)
    ranked = []
    missing = 0
    for x in entries:
        r = rank_of(x["w"], rows.get(x["w"]), rows)
        if r is None:
            missing += 1
            r = 10 ** 9  # 极少数（缩写/人名），放到最难档
        ranked.append((r, x["w"]))
    ranked.sort()
    by_word = {x["w"]: x for x in entries}
    for pos, (_, w) in enumerate(ranked):
        x = by_word[w]
        q = (pos + 0.5) / n
        q = min(max(q, 0.01), 0.99)
        x["lvl"] = min(BANDS - 1, int(pos * BANDS / n))
        x["b"] = round(max(-3.2, min(3.2, math.log(q / (1 - q)) * 0.9)), 4)
    return missing


def main():
    pep = load_pep()
    pep_by_word = {}
    for w, x in pep:
        pep_by_word.setdefault(w, x)
    tagsets = {}
    needed = set(pep_by_word)
    with io.open(ECDICT, encoding="utf-8", newline="") as f:
        csv.field_size_limit(10 ** 7)
        for row in csv.DictReader(f):
            w = (row.get("word") or "").strip().lower()
            if not w:
                continue
            tl = (row.get("tag") or "").split()
            for t in tl:
                if t in EIGHT:
                    tagsets.setdefault(t, set()).add(w)
            if set(tl) & set(EIGHT):
                needed.add(w)
    needed = set(w for w in needed if len(w) >= 2 and CLEAN.match(w))
    rows = load_ecdict(needed)
    existing = load_existing()
    raw = load_raw()

    if "--todo" in sys.argv:
        todo = [w for w in sorted(needed) if w not in existing]
        io.open(TODO, "w", encoding="utf-8").write(json.dumps(todo, ensure_ascii=False, indent=0))
        msg = "todo=%d needed=%d existing=%d" % (len(todo), len(needed), len(existing))
        io.open(LOG, "w", encoding="utf-8").write(msg + "\n")
        print(msg)
        return

    entries, stat = build_entries(rows, needed, pep_by_word, existing, raw)
    missing = assign_difficulty(entries, rows)
    entries.sort(key=lambda x: x["w"])
    io.open(BANK, "w", encoding="utf-8").write(json.dumps(entries, ensure_ascii=False, indent=0))

    by_lvl = [0] * BANDS
    for x in entries:
        by_lvl[x["lvl"]] += 1
    lines = [
        "bank=%d  (needed=%d, ECDICT命中=%d)" % (len(entries), len(needed), len(rows)),
        "复用 v1.0 词条=%d  有道补=%d  ECDICT兜底=%d  PEP兜底=%d  纯文本兜底=%d  缺音标=%d"
        % (stat["reuse"], stat["ydl"], stat["ecd"], stat["pep"], stat["plain"], stat["noipa"]),
        "难度缺失(frq/bnc/lemma都没有)=%d  -> 归到最难档" % missing,
        "每档词数: %s" % by_lvl,
        "文件大小=%.2f MB" % (os.path.getsize(BANK) / 1048576.0),
    ]
    io.open(LOG, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("BANK %d  todo-left=%d" % (len(entries), sum(1 for w in needed if w not in raw and w not in existing)))
    print("size=%.2fMB" % (os.path.getsize(BANK) / 1048576.0))


if __name__ == "__main__":
    main()
