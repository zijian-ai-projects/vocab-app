# -*- coding: utf-8 -*-
"""生成 V2 三级目录 books.json：主类 → 分组 → 词书（+ 分组并集 / 教材分册）。

输入：vocablib/books_spec.json（顺序、命名、kind）、build/lists/<id>.txt（源顺序）、
      data/bank_v2.json（只保留有释义的词）
输出：data/books_v2.json、data/build_books_v2.log
"""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VOCABLIB = os.path.abspath(os.path.join(ROOT, "..", "vocablib"))
SPEC = os.path.join(VOCABLIB, "books_spec.json")
LISTS = os.path.join(ROOT, "build", "lists")
BANK = os.path.join(ROOT, "data", "bank.json")
OUT = os.path.join(ROOT, "data", "books.json")
LOG = os.path.join(ROOT, "data", "build_books_v2.log")


def main():
    spec = json.load(io.open(SPEC, encoding="utf-8"))
    bank_words = set(x["w"] for x in json.load(io.open(BANK, encoding="utf-8")))

    def load(id_):
        p = os.path.join(LISTS, id_ + ".txt")
        if not os.path.exists(p):
            return []
        return [x.strip() for x in io.open(p, encoding="utf-8") if x.strip()]

    mains = []
    log = ["V2 books（三级目录）", ""]
    excluded = []
    missing_words = {}
    total_items = 0
    for main in spec["main_categories"]:
        groups = []
        for g in main["groups"]:
            items = []
            for it in g["items"]:
                raw = load(it["id"])
                ws = [w for w in raw if w in bank_words]
                gone = [w for w in raw if w not in bank_words]
                if gone:
                    missing_words[it["id"]] = gone
                if not ws:
                    excluded.append((it["id"], it["name"], it.get("status")))
                    continue
                total_items += 1
                items.append({
                    "id": it["id"],
                    "name": it["name"],
                    "display": it.get("display") or it["name"],
                    "kind": it.get("kind"),
                    "type": it.get("type") or "word",
                    "series": it.get("series") or "",
                    "status": "ready",
                    "count": len(ws),
                    "words": ws,
                })
            if not items:
                continue
            # 分组并集：按 spec 里的词书顺序拼接后去重（保留第一次出现的位置）
            seen = set()
            union = []
            for it in items:
                for w in it["words"]:
                    if w not in seen:
                        seen.add(w)
                        union.append(w)
            groups.append({
                "id": g["id"],
                "name": g["name"],
                "union_name": g.get("union_name") or (g["name"] + "（全选）"),
                "union": {"id": g["id"] + "-all", "count": len(union), "words": union},
                "items": items,
            })
            log.append("%-4s %-6s %-10s items=%2d union=%5d  max=%5d" % (
                main["name"], g["name"], g["id"], len(items), len(union),
                max(x["count"] for x in items)))
        if groups:
            mains.append({"id": main["id"], "name": main["name"], "groups": groups})

    data = {
        "schema": 2,
        "bank_count": len(bank_words),
        "mains": mains,
    }
    tmp = OUT + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=0))
    for i in range(6):
        try:
            os.replace(tmp, OUT)
            break
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    else:
        os.replace(tmp, OUT)

    # 校验
    problems = []
    ids = set()
    for main in mains:
        for g in main["groups"]:
            if g["union"]["count"] < max(x["count"] for x in g["items"]):
                problems.append("%s 并集小于最大词书" % g["id"])
            for it in g["items"]:
                if it["id"] in ids:
                    problems.append("重复词书 id " + it["id"])
                ids.add(it["id"])
    missing_total = sum(len(v) for v in missing_words.values())
    log.append("")
    log.append("主类=%d 分组=%d 词书=%d  bank=%d" % (
        len(mains), sum(len(m["groups"]) for m in mains), total_items, len(bank_words)))
    log.append("被 bank 剔除的词（无释义/单字母）共 %d 个，涉及 %d 本" % (
        missing_total, len(missing_words)))
    for k in sorted(missing_words)[:10]:
        log.append("  %-12s %s" % (k, " ".join(missing_words[k][:12])))
    log.append("整本被排除：%s" % ([x[0] for x in excluded] or "无"))
    log.append("校验问题：%s" % (problems or "无"))
    log.append("文件大小=%.2f MB" % (os.path.getsize(OUT) / 1048576.0))
    io.open(LOG, "w", encoding="utf-8").write("\n".join(log) + "\n")
    io.open(os.path.join(ROOT, "data", "book_stats.txt"), "w", encoding="utf-8").write(
        "\n".join(log) + "\n")
    print("mains=%d groups=%d items=%d problems=%d size=%.2fMB" % (
        len(mains), sum(len(m["groups"]) for m in mains), total_items,
        len(problems), os.path.getsize(OUT) / 1048576.0))


if __name__ == "__main__":
    main()
