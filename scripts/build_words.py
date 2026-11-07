# -*- coding: utf-8 -*-
"""合成卡面数据：有道(常用度排序的简明释义) + ECDICT(词性细化/标签/词频/兜底)

输出 data/words.json：
  w / ipa / pos[] / s / tags[] / frq / collins / raw / ph_raw
"""
import io, json, os, re

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
XLS = os.path.join(ROOT, "data", "words_xls.json")
ECD = os.path.join(ROOT, "data", "ecdict_subset.json")
RAW = os.path.join(ROOT, "data", "raw_youdao.jsonl")
OUT = os.path.join(ROOT, "data", "words.json")

POS_RE = re.compile(r"^\s*(n|v|vt|vi|adj|adv|a|prep|conj|pron|num|art|int|aux|abbr|rel|interrog|part)\.\s*", re.I)
KNOWN = {"n", "v", "vt", "vi", "adj", "adv", "a", "prep", "conj", "pron", "num",
         "art", "int", "aux", "abbr", "rel", "interrog", "part"}
LABEL = {"a": "adj.", "v": "v.", "n": "n.", "vt": "vt.", "vi": "vi.", "adj": "adj.",
         "adv": "adv.", "prep": "prep.", "conj": "conj.", "pron": "pron.", "num": "num.",
         "art": "art.", "int": "int.", "aux": "aux.", "abbr": "abbr.", "rel": "rel.",
         "interrog": "interrog.", "part": "part."}
NOISE = re.compile(r"<[^>]*>|[（(][^）)]*[）)]|【[^】]*】")
MAX_SENSE = 14
MAX_TOTAL = 24


def tidy(s):
    s = NOISE.sub("", s)
    s = s.replace("……", "…").replace("...", "…")
    # 半角分隔符统一成中文的，避免 "；" 之外还冒出 ";"（有道/ECDICT 都有混用）
    s = s.replace(";", "；").replace(",", "，")
    return s.strip(" ，。；、:：·,.;")


def cap_meanings(s):
    """最后一道闸门：一条卡面最多 2 个释义。"""
    s = tidy(s)
    parts = [p for p in s.split("；") if p.strip()]
    return "；".join(parts[:2])


def shorten(c, limit=MAX_SENSE):
    """太长的义项截断，尽量断在空格 / 标点处，别把英文单词切成 "sa…"。"""
    if len(c) <= limit:
        return c
    cut = c[:limit]
    m = max(cut.rfind(" "), cut.rfind("，"), cut.rfind("、"), cut.rfind("："))
    if m >= limit * 0.5:
        cut = cut[:m]
    cut = cut.rstrip(" ，、：:；;·")
    return cut + "…" if cut else c[:limit] + "…"


def first_senses(body, maxlen=8, n=2):
    out, total = [], 0
    for chunk in re.split(r"[,，]", body):
        c = tidy(chunk)
        if not c:
            continue
        if len(c) > MAX_SENSE:
            c = shorten(c)
        if out and total + len(c) > maxlen:
            break
        out.append(c)
        total += len(c)
        if len(out) >= n:
            break
    return out


def groups_from_youdao(ec_list):
    """有道：每个词性一条，义项按常用度排列，分隔符 '；'"""
    groups = []
    for entry in ec_list:
        m = POS_RE.match(entry)
        if not m:
            continue
        pos = m.group(1).lower()
        if pos not in KNOWN:
            continue
        body = tidy(entry[m.end():])
        if not body or "人名" in body or "姓氏" in body:
            continue
        senses = [x for x in body.split("；") if x.strip()]
        texts = []
        for s in senses[:2]:
            frags = first_senses(s)          # 同义片段合成"一个意思"
            if frags:
                texts.append("，".join(frags))
        if texts:
            groups.append((pos, texts))
        if len(groups) >= 4:
            break
    return groups


def groups_from_ecdict(translation):
    translation = (translation or "").replace("\\n", "\n")
    groups = []
    for line in translation.split("\n"):
        line = line.strip()
        if not line or line.startswith("["):
            continue
        m = POS_RE.match(line)
        pos = m.group(1).lower() if m else ""
        body = tidy(line[m.end():] if m else line)
        if not body:
            continue
        texts = []
        for s in [x for x in body.split("；") if x.strip()][:2]:
            frags = first_senses(s)
            if frags:
                texts.append("，".join(frags))
        if texts:
            groups.append((pos, texts))
        if len(groups) >= 4:
            break
    return groups


def ecdict_pos_all(translation):
    """ECDICT 里这个词出现过的所有词性（按出现顺序）"""
    out = []
    for line in (translation or "").replace("\\n", "\n").split("\n"):
        m = POS_RE.match(line.strip())
        if not m:
            continue
        p = m.group(1).lower()
        if p in LABEL and LABEL[p] not in out:
            out.append(LABEL[p])
    return out


def refine(p, e_pos_set):
    """有道只给 v. 时，用 ECDICT 的 vt./vi. 细化（只有一种才确定）"""
    if p == "v":
        sub = {x for x in e_pos_set if x in ("vt", "vi")}
        if len(sub) == 1:
            return LABEL[sub.pop()]
    return LABEL.get(p, p + "." if p else "")


def join_groups(groups):
    out = ""
    for pos, body in groups:
        piece = ("%s %s" % (pos, body)) if pos else body
        if out and len(out) + len(piece) + 1 > MAX_TOTAL:
            break
        out = (out + "；" + piece) if out else piece
    return out


def main():
    xls = json.load(io.open(XLS, encoding="utf-8"))
    ecd = json.load(io.open(ECD, encoding="utf-8"))
    ydl = {}
    for line in io.open(RAW, encoding="utf-8"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o and o.get("word"):
            ydl[o["word"].lower()] = o

    words = []
    stat = {"ydl": 0, "ecd": 0, "xls": 0, "noipa": 0}
    for w in xls:
        lw = w["word"].lower()
        e = ecd.get(lw, {})
        y = ydl.get(lw, {})
        trans = e.get("translation", "")
        e_pos_set = set()
        for line in trans.replace("\\n", "\n").split("\n"):
            m = POS_RE.match(line.strip())
            if m:
                e_pos_set.add(m.group(1).lower())

        raw_groups = groups_from_youdao(y.get("ec") or [])
        src = "ydl"
        if not raw_groups:
            raw_groups = groups_from_ecdict(trans)
            src = "ecd"
        groups = [(refine(p, e_pos_set) if p else "", texts)
                  for p, texts in raw_groups]
        groups = [(p, ts) for p, ts in groups if ts]
        if len(groups) == 1:
            # 单词性：最多 2 个意思，共享一个词性前缀
            p0, ts = groups[0]
            s = ((p0 + "；".join(ts[:2])) if p0 else "；".join(ts[:2]))
            keep = [(p0, ts[:2])]
        else:
            # 2 个及以上词性：取最常见的两个，各 1 个意思
            keep = [(g[0], g[1][:1]) for g in groups[:2]]
            s = "；".join(("%s%s" % (p, t)) if p else t for p, ts in keep for t in ts)
        if s:
            s = cap_meanings(s)
        if s:
            stat[src] += 1
        else:
            s = cap_meanings(w["meaning_raw"])
            stat["xls"] += 1

        pos = [p for p, _ in keep if p]

        ipa = y.get("usphone") or y.get("ukphone") or ""
        if not ipa:
            stat["noipa"] += 1
            ipa = e.get("phonetic", "")

        try:
            frq = int(e.get("frq") or 0)
        except ValueError:
            frq = 0

        words.append({
            "w": w["word"],
            "ipa": ipa,
            "pos": pos[:4],
            "s": s,
            "tags": (e.get("tag") or "").split(),
            "frq": frq,
            "collins": e.get("collins", ""),
            "raw": w["meaning_raw"],
            "ph_raw": w["phonetic_raw"],
        })

    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=0)
    print("words=%d 有道=%d ECDICT兜底=%d xls兜底=%d 缺IPA=%d" %
          (len(words), stat["ydl"], stat["ecd"], stat["xls"], stat["noipa"]))

    lines = []
    for x in words[:24]:
        lines.append("%-15s %-20s %-14s %s" % (x["w"], x["ipa"][:20], " ".join(x["pos"]), x["s"]))
    io.open(os.path.join(ROOT, "data", "preview.txt"), "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    main()
