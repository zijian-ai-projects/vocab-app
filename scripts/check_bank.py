# -*- coding: utf-8 -*-
"""数据校验：大词库 + 词书。结果写 data/check_bank.txt。"""
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
    check(15000 <= len(ws) <= 15300, "大词库 %d 词（目标 15,000+）" % len(ws))
    check(len(set(ws)) == len(ws), "大词库无重复")
    check(ws == sorted(ws), "大词库按字母序 A–Z 排列")
    check(all(x.get("s") for x in bank), "每个词都有卡面释义")
    check(sum(1 for x in bank if not x.get("ipa")) <= 30,
          "缺音标的词 %d 个（<=30）" % sum(1 for x in bank if not x.get("ipa")))
    lv = [0] * 15
    for x in bank:
        lv[x["lvl"]] += 1
    check(all(n > 0 for n in lv) and abs(max(lv) - min(lv)) < 20,
          "难度 15 档分布均匀：%s" % lv)
    check(all(-3.2 <= x["b"] <= 3.2 for x in bank), "难度 b 都在 [-3.2, 3.2]")

    bank_set = set(ws)
    ids = [b["id"] for b in books]
    check(len(ids) == 11, "词书 11 本：%s" % "、".join(ids))
    for b in books:
        check(len(b["words"]) == b["count"], "%s 词数标记一致：%d" % (b["id"], b["count"]))
        check(b["words"] == sorted(b["words"]), "%s 按字母序" % b["id"])
        check(len(set(b["words"])) == len(b["words"]), "%s 无重复" % b["id"])
        check(all(w in bank_set for w in b["words"]), "%s 的词都在大词库里" % b["id"])
        check(bool(b["name"]) and bool(b["desc"]), "%s 有名称/描述" % b["id"])

    io.open(os.path.join(DATA, "check_bank.txt"), "w", encoding="utf-8").write(
        "\n".join(out + ["", "FAILS %d" % len(fails)]))
    print("WROTE %d LINES; FAILS %d" % (len(out), len(fails)))


if __name__ == "__main__":
    main()
