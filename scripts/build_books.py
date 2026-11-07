# -*- coding: utf-8 -*-
"""从 bank.json 生成 11 本词书：data/books.json（每本书 = A–Z 顺序的单词列表）。

【历史脚本】v1.2.0 起词书由 scripts/build_books_v2.py 生成（三级目录）。
直接运行本脚本会用 11 本平铺词书覆盖 data/books.json，仅用于复现 v1.1。

词表来源：
  - 小学 / 初中：data/pep_primary.json / pep_middle.json（人教版 PEP 教材词表）
  - 高中 / 四级 / 六级 / 考研 / 雅思 / 托福 / GRE：ECDICT 的 gk/cet4/cet6/ky/ielts/toefl/gre 标签
  - 考博：ky ∪ gre（没有现成大纲标签，学术向合成，命名里注明）
  - 全部：大词库
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_bank as bb  # noqa: E402

DATA = os.path.join(ROOT, "data")
BANK = os.path.join(DATA, "bank.json")
BOOKS = os.path.join(DATA, "books.json")
STATS = os.path.join(DATA, "book_stats.txt")
CLEAN = __import__("re").compile(r"^[a-z][a-z'-]*$")


def clean(w):
    w = (w or "").strip().lower()
    return w if (len(w) >= 2 and CLEAN.match(w)) else None


def load_pep(name):
    path = os.path.join(DATA, "pep_%s.json" % name)
    out = set()
    if not os.path.exists(path):
        return out
    for x in json.load(io.open(path, encoding="utf-8")):
        w = bb.clean_pep_word(x.get("w"))
        if w:
            out.add(w)
    return out


def main():
    bank = json.load(io.open(BANK, encoding="utf-8"))
    words = [x["w"] for x in bank]
    wordset = set(words)
    tags = {}
    for x in bank:
        for t in x.get("tags") or []:
            tags.setdefault(t, set()).add(x["w"])

    raw_books = [
        ("xiaoxue", "小学词汇", "小学", "学段", "人教版 PEP 教材 · %s 词", load_pep("primary")),
        ("chuzhong", "初中词汇", "初中", "学段", "人教版 PEP 教材 · %s 词", load_pep("middle")),
        ("gaokao", "高中词汇", "高中", "学段", "高考大纲 · %s 词", tags.get("gk", set())),
        ("cet4", "四级词汇", "四级", "考试", "CET-4 大纲 · %s 词", tags.get("cet4", set())),
        ("cet6", "六级词汇", "六级", "考试", "CET-6 大纲 · %s 词", tags.get("cet6", set())),
        ("kaoyan", "考研词汇", "考研", "考试", "考研大纲 · %s 词", tags.get("ky", set())),
        ("kaobo", "考博词汇", "考博", "考试", "考研 + GRE 学术合成 · %s 词", tags.get("ky", set()) | tags.get("gre", set())),
        ("ielts", "雅思词汇", "雅思", "出国", "IELTS · %s 词", tags.get("ielts", set())),
        ("toefl", "托福词汇", "托福", "出国", "TOEFL · %s 词", tags.get("toefl", set())),
        ("gre", "GRE 词汇", "GRE", "出国", "GRE · %s 词", tags.get("gre", set())),
        ("all", "全部词汇", "全部", "全部", "大词库 · %s 词", wordset),
    ]

    out = []
    lines = ["词书校验（生成自 bank.json）", ""]
    problems = []
    for bid, name, short, cat, desc_tpl, ws in raw_books:
        missing = sorted(w for w in ws if w not in wordset)
        if missing:
            problems.append("%s 有 %d 个词不在大词库：%s" % (bid, len(missing), missing[:10]))
        ws = sorted(w for w in ws if w in wordset)
        desc = desc_tpl % format(len(ws), ",")
        out.append({"id": bid, "name": name, "short": short, "category": cat,
                    "desc": desc, "count": len(ws), "words": ws})
        lines.append("%-10s %-12s %5d 词  %s" % (bid, name, len(ws), desc))

    # 重叠矩阵（行书的词有多大比例也出现在列书）
    lines.append("")
    lines.append("重叠矩阵（行书的词也出现在列书的比例）：")
    ids = [b["id"] for b in out]
    sets = {b["id"]: set(b["words"]) for b in out}
    lines.append("  %-10s %s" % ("", " ".join("%6s" % i for i in ids)))
    for a in ids:
        row = []
        for b in ids:
            row.append("%6.2f" % (len(sets[a] & sets[b]) / max(1, len(sets[a]))))
        lines.append("  %-10s %s" % (a, " ".join(row)))

    if problems:
        lines.append("")
        lines.append("问题：")
        lines.extend("  " + p for p in problems)
    else:
        lines.append("")
        lines.append("全部词都在大词库里 ✓")

    io.open(BOOKS, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=0))
    io.open(STATS, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("BOOKS %d -> %s (%.1f KB)" % (len(out), BOOKS, os.path.getsize(BOOKS) / 1024.0))
    print("problems=%d" % len(problems))


if __name__ == "__main__":
    main()
