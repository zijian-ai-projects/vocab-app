# -*- coding: utf-8 -*-
"""逐本抽取词表（按 books_spec.json 的 175 个条目）。

输出（都在 vocab-app/build/ 下）：
    raw/<id>.txt      源顺序的原始词条（清洗前，便于核对）
    lists/<id>.txt    清洗后、去重、源顺序的单词
    gloss/<id>.json   源里自带的释义/音标 {word: {tr, ipa}}
    report/<id>.txt   逐本统计
    index.json        全部条目的机器可读统计
    union.txt         并集统计（vs 现有 bank.json）
    extract_report.md 汇总报告

用法：
    python scripts/extract_lists.py --dry-run   只解析来源、不写词表
    python scripts/extract_lists.py             全量抽取
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VOCABLIB = os.path.abspath(os.path.join(ROOT, "..", "vocablib"))
BUILD = os.path.join(ROOT, "build")
SPEC = os.path.join(VOCABLIB, "books_spec.json")
MM = os.path.join(VOCABLIB, "maimemo-export-main", "exported")
DQ = os.path.join(VOCABLIB, "单词书大全")
ZG = os.path.join(VOCABLIB, "中高职CATTI")
EXT = os.path.join(VOCABLIB, "external")
BANK = os.path.join(ROOT, "data", "bank.json")

# 单词：纯字母（可带 ' 或 -），与 bank 的过滤规则一致；a / i 特批
WORD_RE = re.compile(r"^[a-z][a-z'\-]*$")
RAW_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-\.]*$")
KEEP_SINGLE = {"a", "i"}
# 短语：最多 4 个英文词（词书里的 go along with / according to）
PHRASE_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*(?:[ /][A-Za-z][A-Za-z'\-]*){1,5}$")
DOTS = {"a.m.", "p.m.", "etc.", "e.g.", "i.e.", "u.s.", "u.k."}

csv.field_size_limit(10 ** 7)


# ---------------------------------------------------------------- 工具

def read_text(path):
    data = io.open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def norm_name(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"[\s_\-—–·・:：,，.。'\"“”‘’()（）\[\]【】]", "", s)
    return s


def clean_token(tok, kind_type="word"):
    t = unicodedata.normalize("NFKC", tok or "").strip()
    t = t.strip(" \t\r\n\"'“”‘’")
    t = re.sub(r"\s+", " ", t)
    if not t:
        return None, "empty"
    low = t.lower()
    if WORD_RE.match(low) and (len(low) >= 2 or low in KEEP_SINGLE):
        return low, None
    if kind_type == "phrase" and PHRASE_RE.match(t):
        return low, None
    if " " in t or "/" in t:
        return low, "phrase"
    return None, "not-word"


def resolve_maimemo(name):
    """在 exported/word 里找文件：先精确，再归一化，再模糊。"""
    word_dir = os.path.join(MM, "word")
    path = os.path.join(word_dir, name + ".txt")
    if os.path.exists(path):
        return path, "exact"
    target = norm_name(name)
    best = None
    for fn in os.listdir(word_dir):
        if not fn.lower().endswith(".txt"):
            continue
        base = os.path.splitext(fn)[0]
        if norm_name(base) == target:
            return os.path.join(word_dir, fn), "normalized"
        ratio = _ratio(target, norm_name(base))
        if best is None or ratio > best[0]:
            best = (ratio, os.path.join(word_dir, fn))
    if best and best[0] >= 0.86:
        return best[1], "fuzzy %.2f" % best[0]
    return None, "missing"


def _ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def read_lines(path):
    text = read_text(path)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


# ---------------------------------------------------------------- 各来源读取

def src_maimemo(item):
    name = item["ref"]
    path, how = resolve_maimemo(name)
    if not path:
        return None, {"source": "maimemo:" + name, "problems": ["找不到 maimemo 词表文件"]}
    toks = read_lines(path)
    gloss = read_maimemo_gloss(path)
    return toks, {"source": rel(path), "how": how, "gloss": gloss}


def src_maimemo_multi(item):
    all_toks, gloss, problems, hows = [], {}, [], []
    for name in item["ref"]:
        path, how = resolve_maimemo(name)
        hows.append("%s(%s)" % (name, how))
        if not path:
            problems.append("找不到 maimemo 词表文件: " + name)
            continue
        all_toks.extend(read_lines(path))
        for k, v in read_maimemo_gloss(path).items():
            gloss.setdefault(k, v)
    return all_toks, {"source": "maimemo x%d" % len(item["ref"]), "how": "; ".join(hows),
                      "gloss": gloss, "problems": problems}


def read_maimemo_gloss(word_path):
    """同名的 translation/*.csv：word,"n. ...\\nvt. ..."（可能带音标列）。"""
    base = os.path.splitext(os.path.basename(word_path))[0]
    csv_path = os.path.join(MM, "translation", base + ".csv")
    if not os.path.exists(csv_path):
        return {}
    out = {}
    try:
        text = read_text(csv_path)
        rows = list(csv.reader(io.StringIO(text)))
    except Exception:
        return {}
    for row in rows:
        if not row:
            continue
        w = (row[0] or "").strip().lower()
        if not w or w in ("word", "单词"):
            continue
        tr = (row[1] if len(row) > 1 else "").strip()
        ipa = ""
        for cell in row[2:]:
            cell = (cell or "").strip()
            if cell and re.search(r"[ˈˌəɪʊɛæɑɔʌθðʃʒŋ]", cell):
                ipa = cell
                break
        if tr or ipa:
            out.setdefault(w, {"tr": tr, "ipa": ipa})
    return out


def find_file_ci(base, rel_path):
    """不区分大小写、容忍分隔符差异地找文件。"""
    p = os.path.join(base, rel_path)
    if os.path.exists(p):
        return p
    # 逐级模糊
    parts = re.split(r"[\\/]", rel_path)
    cur = base
    for i, part in enumerate(parts):
        last = (i == len(parts) - 1)
        if not os.path.isdir(cur):
            return None
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        hit = None
        if part in names:
            hit = part
        else:
            tgt = norm_name(part if not last else os.path.splitext(part)[0])
            for n in names:
                if norm_name(n if not last else os.path.splitext(n)[0]) == tgt:
                    hit = n
                    break
        if hit is None:
            return None
        cur = os.path.join(cur, hit)
    return cur if os.path.exists(cur) else None


def src_daquan(item):
    path = find_file_ci(DQ, item["ref"])
    if not path:
        return None, {"source": "daquan:" + item["ref"], "problems": ["找不到词书大全文件"]}
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt", ".tsv"):
        pairs = read_table_pairs(path)
    elif ext in (".xlsx", ".xlsm"):
        pairs = read_xlsx_pairs(path)
    else:
        return None, {"source": rel(path), "problems": ["不支持的文件类型 " + ext]}
    toks = [w for w, _ in pairs]
    gloss = {}
    for w, tr in pairs:
        if tr:
            gloss.setdefault(w, {"tr": tr, "ipa": ""})
    return toks, {"source": rel(path), "gloss": gloss, "pairs": True}


def read_table_pairs(path):
    """CSV/TSV：优先 word/translation 两列；否则第一列当词。返回 [(raw_word, translation)]。"""
    text = read_text(path)
    delim = "\t" if path.lower().endswith((".tsv",)) else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return []
    header = [(c or "").strip().lower() for c in rows[0]]
    wi, ti = None, None
    has_header = False
    for i, h in enumerate(header):
        if h in ("word", "words", "单词", "词条", "英文") or h == "term" or h.startswith("term "):
            wi = i
            has_header = True
        if h in ("translation", "meaning", "trans", "释义", "中文", "词义"):
            ti = i
    if wi is None:
        wi = 0
    if ti is None:
        ti = 1 if len(header) > 1 else None
    body = rows[1:] if has_header else rows
    out = []
    for row in body:
        if not row:
            continue
        w = (row[wi] if wi < len(row) else "").strip()
        tr = (row[ti] if ti is not None and ti < len(row) else "").strip()
        if w:
            out.append((w, tr))
    return out


def read_xlsx_pairs(path):
    try:
        import openpyxl
    except ImportError:
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append([("" if c is None else str(c)).strip() for c in row])
    wb.close()
    if not rows:
        return []
    header = [c.lower() for c in rows[0]]
    wi, ti = 0, None
    for i, h in enumerate(header):
        if h in ("word", "words", "单词", "词条", "英文"):
            wi = i
        if h in ("translation", "meaning", "trans", "释义", "中文", "词义"):
            ti = i
    body = rows
    if any(h in ("word", "单词", "词条", "英文") for h in header):
        body = rows[1:]
    out = []
    for row in body:
        w = (row[wi] if wi < len(row) else "").strip()
        tr = (row[ti] if ti is not None and ti < len(row) else "").strip()
        if w:
            out.append((w, tr))
    return out


def src_official(item):
    ref = item["ref"]
    if ref.startswith("高等职业教育"):
        toks = official_gaozhi(os.path.join(ZG, ref))
        return toks, {"source": rel(os.path.join(ZG, ref)), "gloss": {}}
    if ref.startswith("中等职业学校"):
        toks, gloss = official_zhongzhi(os.path.join(ZG, ref))
        return toks, {"source": rel(os.path.join(ZG, ref)), "gloss": gloss}
    if "catti" in ref.lower():
        toks = official_catti(os.path.join(ZG, ref))
        return toks, {"source": rel(os.path.join(ZG, ref)), "gloss": {}}
    return None, {"source": "official:" + ref, "problems": ["未知官方来源"]}


def official_gaozhi(path):
    """高职 2021 PDF：3 个词列，按 列→行 顺序读（词典排版）。"""
    import fitz
    doc = fitz.open(path)
    toks = []
    for page in doc:
        ws = page.get_text("words")
        cols = {0: [], 1: [], 2: []}
        for w in ws:
            x0, y0, txt = w[0], w[1], w[4]
            if x0 < 220:
                c = 0
            elif x0 < 370:
                c = 1
            else:
                c = 2
            cols[c].append((y0, x0, txt))
        for c in (0, 1, 2):
            for _, _, txt in sorted(cols[c]):
                for part in re.split(r"[/]", txt):
                    part = part.strip()
                    if part:
                        toks.append(part)
    doc.close()
    return toks


def official_zhongzhi(path):
    """中职 2020 docx：每段一条 'word /ipa/ 词性. 词义'。"""
    import docx
    d = docx.Document(path)
    toks, gloss = [], {}
    pat = re.compile(r"^([A-Za-z][A-Za-z'\-]*)\s*(?:\([^)]*\))?\s*(.*)$")
    for para in d.paragraphs:
        line = para.text.strip()
        if not line or not re.match(r"^[A-Za-z]", line):
            continue
        m = pat.match(line)
        if not m:
            continue
        w, rest = m.group(1), m.group(2)
        toks.append(w)
        tr = rest
        ipa = ""
        mi = re.search(r"/([^/]{1,40})/", tr)
        if mi:
            ipa = mi.group(1).strip()
            tr = (tr[:mi.start()] + " " + tr[mi.end():]).strip()
        tr = re.sub(r"\s+", " ", tr)
        # 句内多个词性：拆成 ECDICT 风格的多行
        tr = re.sub(r"\s+(?=(?:n|v|vt|vi|a|ad|adj|adv|prep|conj|pron|num|art|int|aux)\.\s)", "\n", tr)
        gloss.setdefault(w.lower(), {"tr": tr.strip(), "ipa": ipa})
    return toks, gloss


def official_catti(path):
    """CATTI 3 级 .doc：OLE WordDocument 流 cp1252 解码后的逗号分隔词表。

    文档流里混着二进制垃圾，先只取「连续可打印 ASCII 长串」——真正的词表
    就是其中最长的几段逗号分隔文本。
    """
    import olefile
    ole = olefile.OleFileIO(path)
    text = ole.openstream("WordDocument").read().decode("cp1252", errors="ignore")
    ole.close()
    runs = re.findall(r"[A-Za-z][A-Za-z ,;'\-\.]{40,}", text)
    toks = []
    for run in runs:
        for part in re.split(r"[,;\n]", run):
            part = part.strip()
            if part:
                toks.append(part)
    return toks


def src_external(item):
    ref = item["ref"]
    if ref.startswith("qwerty:"):
        fn = ref.split(":", 1)[1]
        path = os.path.join(EXT, "qwerty", fn)
        if not os.path.exists(path):
            return None, {"source": "qwerty:" + fn, "problems": ["外部词表未下载"]}
        data = json.load(io.open(path, encoding="utf-8"))
        toks, gloss = [], {}
        for obj in data:
            w = (obj.get("name") or "").strip()
            if not w:
                continue
            toks.append(w)
            tr = obj.get("trans") or []
            if isinstance(tr, str):
                tr = [tr]
            gloss.setdefault(w.lower(), {
                "tr": "\n".join(x for x in tr if x),
                "ipa": obj.get("usphone") or obj.get("ukphone") or "",
            })
        return toks, {"source": "qwerty:" + fn, "gloss": gloss}
    if ref.startswith("cc-by-sa:LexPredict:"):
        relp = ref.split(":", 2)[2]
        path = os.path.join(EXT, "lexpredict", os.path.basename(relp))
        if not os.path.exists(path):
            return None, {"source": ref, "problems": ["外部词表未下载"]}
        pairs = read_table_pairs(path)
        toks = [w for w, _ in pairs]
        gloss = {w.lower(): {"tr": tr, "ipa": ""} for w, tr in pairs if tr}
        return toks, {"source": rel(path), "gloss": gloss}
    if ref.startswith("github:"):
        return None, {"source": ref, "problems": ["句子级词表，暂不进入单词库"]}
    return None, {"source": ref, "problems": ["未知外部来源"]}


# ---------------------------------------------------------------- 主流程

def rel(p):
    try:
        return os.path.relpath(p, VOCABLIB).replace("\\", "/")
    except ValueError:
        return p


def load_spec():
    return json.load(io.open(SPEC, encoding="utf-8"))


def iter_items(spec):
    for main in spec["main_categories"]:
        for g in main["groups"]:
            for it in g["items"]:
                yield main, g, it


def extract(item):
    kind = item.get("kind")
    if kind == "maimemo":
        return src_maimemo(item)
    if kind == "maimemo_multi":
        return src_maimemo_multi(item)
    if kind == "daquan":
        return src_daquan(item)
    if kind == "official":
        return src_official(item)
    if kind == "external":
        return src_external(item)
    if kind == "missing":
        return None, {"source": "", "problems": ["书源缺失（已知）"]}
    return None, {"source": "", "problems": ["未知 kind " + str(kind)]}


def process(item, args):
    item_id = item["id"]
    kind_type = item.get("type") or "word"
    raw, meta = extract(item)
    problems = list(meta.get("problems") or [])
    gloss = meta.get("gloss") or {}
    stat = {"id": item_id, "name": item["name"], "kind": item.get("kind"),
            "main": meta.get("main", ""), "source": meta.get("source", ""),
            "status": item.get("status"), "type": kind_type,
            "raw": 0, "kept": 0, "dropped": 0, "dup": 0, "phrases": 0,
            "gloss": 0, "problems": problems}

    if raw is None:
        stat["status"] = "skipped"
        return stat, None, None, None

    stat["raw"] = len(raw)
    dropped_samples = {}
    kept, seen = [], set()
    cleaned_gloss = {}
    for tok in raw:
        w, why = clean_token(tok, kind_type)
        if why:
            stat["dropped"] += 1
            if why == "phrase":
                stat["phrases"] += 1
            dropped_samples.setdefault(why, []).append(str(tok)[:30])
            continue
        if w in seen:
            stat["dup"] += 1
            continue
        seen.add(w)
        kept.append(w)
        g = gloss.get(w)
        if g and (g.get("tr") or g.get("ipa")):
            cleaned_gloss[w] = {"tr": (g.get("tr") or "").strip(), "ipa": (g.get("ipa") or "").strip()}
    stat["kept"] = len(kept)
    stat["gloss"] = len(cleaned_gloss)
    stat["problems"] = problems
    stat["dropped_samples"] = {k: v[:8] for k, v in dropped_samples.items()}

    if args.dry_run:
        print("%-12s raw=%-6d kept=%-6d gloss=%-6d %s" % (
            item_id, stat["raw"], stat["kept"], stat["gloss"],
            ("问题:" + ";".join(problems)) if problems else ""))
        return stat, None, None, None

    for sub in ("raw", "lists", "gloss", "report"):
        os.makedirs(os.path.join(BUILD, sub), exist_ok=True)
    io.open(os.path.join(BUILD, "raw", item_id + ".txt"), "w", encoding="utf-8").write(
        "\n".join(raw) + "\n")
    io.open(os.path.join(BUILD, "lists", item_id + ".txt"), "w", encoding="utf-8").write(
        "\n".join(kept) + "\n")
    io.open(os.path.join(BUILD, "gloss", item_id + ".json"), "w", encoding="utf-8").write(
        json.dumps(cleaned_gloss, ensure_ascii=False, indent=0) if cleaned_gloss else "{}")
    lines = [
        "%s  %s" % (item_id, item["name"]),
        "main=%s  kind=%s  type=%s  status=%s" % (meta.get("main", ""), item.get("kind"), kind_type, item.get("status")),
        "source=%s" % stat["source"],
        "raw=%d  kept=%d  dropped=%d  dup=%d  gloss=%d" % (
            stat["raw"], stat["kept"], stat["dropped"], stat["dup"], stat["gloss"]),
    ]
    if stat.get("how"):
        lines.append("how=%s" % stat["how"])
    for why, samples in stat["dropped_samples"].items():
        lines.append("dropped[%s] e.g. %s" % (why, ", ".join(samples)))
    if problems:
        lines.append("problems: " + " | ".join(problems))
    io.open(os.path.join(BUILD, "report", item_id + ".txt"), "w", encoding="utf-8").write(
        "\n".join(lines) + "\n")
    return stat, kept, cleaned_gloss, raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="", help="只跑这些 id（逗号分隔）")
    args = ap.parse_args()

    spec = load_spec()
    only = set(x.strip() for x in args.only.split(",") if x.strip())
    all_stats, unions = [], {}
    for main_cat, g, it in iter_items(spec):
        if only and it["id"] not in only:
            continue
        stat, kept, gl, raw = process(it, args)
        stat["main"] = main_cat["name"]
        all_stats.append(stat)
        if kept:
            unions.setdefault(main_cat["name"], set()).update(kept)
            unions.setdefault("__all__", set()).update(kept)

    if args.dry_run:
        bad = [s for s in all_stats if s["problems"]]
        print("\nitems=%d  problems=%d" % (len(all_stats), len(bad)))
        for s in bad:
            print("  %-12s %s" % (s["id"], " | ".join(s["problems"])))
        return

    io.open(os.path.join(BUILD, "index.json"), "w", encoding="utf-8").write(
        json.dumps(all_stats, ensure_ascii=False, indent=1))

    # 并集统计
    bank_words = set()
    if os.path.exists(BANK):
        for x in json.load(io.open(BANK, encoding="utf-8")):
            bank_words.add(x["w"])
    all_union = unions.get("__all__", set())
    new_words = sorted(all_union - bank_words)
    lines = ["并集统计（全部已抽词表）", ""]
    lines.append("条目 %d，有词表的条目 %d" % (
        len(all_stats), sum(1 for s in all_stats if s["kept"])))
    lines.append("并集去重 = %d" % len(all_union))
    lines.append("现有 bank = %d" % len(bank_words))
    lines.append("bank 已覆盖 = %d (%.1f%%)" % (
        len(all_union & bank_words), 100.0 * len(all_union & bank_words) / max(1, len(all_union))))
    lines.append("需新增 = %d" % len(new_words))
    lines.append("")
    lines.append("各主类并集：")
    for mc in [m["name"] for m in spec["main_categories"]]:
        s = unions.get(mc, set())
        lines.append("  %-4s %6d  （新增 %d）" % (mc, len(s), len(s - bank_words)))
    lines.append("")
    lines.append("重复度最高的 15 组（并集重叠）：")
    stats = sorted(((s["kept"], s["id"], s["name"]) for s in all_stats if s["kept"]), reverse=True)[:15]
    for n, i, nm in stats:
        lines.append("  %-12s %5d  %s" % (i, n, nm))
    io.open(os.path.join(BUILD, "union.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    io.open(os.path.join(BUILD, "new_words.txt"), "w", encoding="utf-8").write(
        "\n".join(new_words) + "\n")

    # Markdown 汇总
    md = ["# 词表抽取报告", "",
          "生成自 `books_spec.json`，逐本抽取，保留源顺序。", "",
          "| 条目 | 名称 | 来源 | 原始 | 保留 | 新词条释义 | 问题 |",
          "|---|---|---|---:|---:|---:|---|"]
    for s in all_stats:
        md.append("| %s | %s | %s | %d | %d | %d | %s |" % (
            s["id"], s["name"], s["source"].split("/")[-1], s["raw"], s["kept"],
            s["gloss"], "；".join(s["problems"])))
    md.append("")
    md.append("并集 %d，现有 bank 覆盖 %d，需新增 %d。" % (
        len(all_union), len(all_union & bank_words), len(new_words)))
    io.open(os.path.join(BUILD, "extract_report.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")

    print("items=%d union=%d new=%d" % (len(all_stats), len(all_union), len(new_words)))
    bad = [s for s in all_stats if s["problems"]]
    print("problems=%d" % len(bad))
    for s in bad:
        print("  %-12s %s" % (s["id"], " | ".join(s["problems"])))


if __name__ == "__main__":
    main()
