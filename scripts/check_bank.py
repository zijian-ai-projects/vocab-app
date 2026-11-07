# -*- coding: utf-8 -*-
"""数据校验 V2：大词库 + 三级目录词书。结果写 data/check_bank.txt。"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


def main():
    out = []
    fails = []

    def check(ok, msg):
        out.append(("  OK   " if ok else "  FAIL ") + msg)
        if not ok:
            fails.append(msg)

    bank = json.load(io.open(os.path.join(DATA, "bank.json"), encoding="utf-8"))
    books = json.load(io.open(os.path.join(DATA, "books.json"), encoding="utf-8"))
    ws = [x["w"] for x in bank]
    check(30000 <= len(ws) <= 40000, "大词库 %d 词（目标 30,000+）" % len(ws))
    check(len(set(ws)) == len(ws), "大词库无重复")
    check(ws == sorted(ws), "大词库按字母序 A–Z 排列")
    check(all(x.get("s") for x in bank), "每个词都有卡面释义")
    noipa = sum(1 for x in bank if not x.get("ipa"))
    check(noipa <= 3000, "缺音标的词 %d 个（<=3000，ECDICT 本身缺）" % noipa)
    lv = [0] * 15
    for x in bank:
        lv[x["lvl"]] += 1
    check(all(n > 0 for n in lv) and abs(max(lv) - min(lv)) < 20,
          "难度 15 档分布均匀：%s" % lv)
    check(all(-3.2 <= x["b"] <= 3.2 for x in bank), "难度 b 都在 [-3.2, 3.2]")
    check(len(set(x["pos"] and tuple(x["pos"]) or () for x in bank)) > 5, "词性字段有内容")

    bank_set = set(ws)
    check(books.get("schema") == 2, "词书 schema=2")
    mains = books.get("mains") or []
    check(len(mains) == 8, "主类 8 个：%s" % "、".join(m["name"] for m in mains))
    n_groups = sum(len(m["groups"]) for m in mains)
    n_items = sum(len(g["items"]) for m in mains for g in m["groups"])
    check(30 <= n_groups <= 50, "分组 %d 个" % n_groups)
    check(150 <= n_items <= 180, "词书 %d 本" % n_items)
    all_item_words = set()
    for m in mains:
        for g in m["groups"]:
            u = g["union"]
            check(u["count"] == len(u["words"]), "%s 并集词数标记一致：%d" % (g["id"], u["count"]))
            check(len(set(u["words"])) == len(u["words"]), "%s 并集无重复" % g["id"])
            check(all(w in bank_set for w in u["words"]), "%s 并集的词都在大词库里" % g["id"])
            ids = set()
            seen = set()
            expect = []
            for it in g["items"]:
                check(it["count"] == len(it["words"]), "%s 词数标记一致：%d" % (it["id"], it["count"]))
                check(len(set(it["words"])) == len(it["words"]), "%s 无重复" % it["id"])
                check(all(w in bank_set for w in it["words"]), "%s 的词都在大词库里" % it["id"])
                check(bool(it["name"]), "%s 有名称" % it["id"])
                check(it["id"] not in ids, "%s id 唯一" % it["id"])
                ids.add(it["id"])
                all_item_words.update(it["words"])
                for w in it["words"]:
                    if w not in seen:
                        seen.add(w)
                        expect.append(w)
            check(u["words"] == expect, "%s 并集 = 各词书按序去重" % g["id"])
            check(g.get("union_name"), "%s 有并集名" % g["id"])
            series = [it.get("series") for it in g["items"] if it.get("series")]
            if len(g["items"]) >= 8 and series:
                check(len(set(series)) >= 2, "%s 是教材分册（%d 册/%d 版本）" % (
                    g["id"], len(g["items"]), len(set(series))))
    check(all_item_words == bank_set,
          "所有词书并集 = 大词库（%d vs %d）" % (len(all_item_words), len(bank_set)))

    io.open(os.path.join(DATA, "check_bank.txt"), "w", encoding="utf-8").write(
        "\n".join(out + ["", "FAILS %d" % len(fails)]))
    print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))
    for f in fails:
        print("FAIL", f)


if __name__ == "__main__":
    main()
