# -*- coding: utf-8 -*-
"""V1.3.4 民间词表保留回归：只读比对冻结 V1.3.3 原数据、成员和 community 来源。"""
import hashlib
import io
import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, "app"))
sys.path.insert(0, os.path.join(APP, "scripts"))

import books as bk
import check_bank

DATA = os.path.join(APP, "data")
# V1.3.3 tag a50eeaa 中 git show 的 LF 内容 SHA256。
FROZEN = {
    "bank.json": "0b646475f3c6bd4598050391a2dc7d8e25f8b232435656cbff39a68687013e33",
    "books.json": "9a6c0a59460d25c70abd496e8804a338ca84e74284163fe96f48354c4882843c",
    "phrases.json": "34f8a555c39b68526ef2304f963e0c76a8a18be25aab4521e8947ae4a697fb5c",
    "phrase_books.json": "98d7a2c0ceaa3890fa99788519a7cbe7d0d403fc4abeb6bc4ecb45c20ad13141",
}
AUDIT_ARTIFACTS = (
    "data/book_sources.json",
    "data/syllabuses",
    "scripts/audit_syllabuses.py",
    "scripts/test_syllabuses.py",
    "scripts/test_syllabus_queue_compat.py",
    "docs/syllabus-diff-v134.json",
    "docs/syllabus-audit.md",
)

out, fails = [], []


def check(ok, message):
    out.append(("  OK   " if ok else "  FAIL ") + message)
    if not ok:
        fails.append(message)


def normalized_sha256(path):
    with io.open(path, "rb") as stream:
        data = stream.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def main():
    # 1) 冻结原数据字节（工作树 CRLF 归一后比较）
    for name, expected in FROZEN.items():
        path = os.path.join(DATA, name)
        actual = normalized_sha256(path)
        check(actual == expected,
              "%s 保持 V1.3.3 原数据：%s" % (name, actual))

    # 2) 原目录成员/词组/并集数量
    word_books = [b for b in bk.BY_ID.values()
                  if b.get("type") in ("word", "volume")
                  and not b.get("is_union")]
    phrase_books = [b for b in bk.BY_ID.values()
                    if b.get("type") == "phrase" and not b.get("is_union")]
    unions = [b for b in bk.BY_ID.values() if b.get("is_union")]
    check(len(word_books) == 175,
          "175 原单词书（word+volume，非 union）：%d" % len(word_books))
    check(len(phrase_books) == 8,
          "8 原词组书：%d" % len(phrase_books))
    check(len(unions) == 41,
          "41 原并集：%d" % len(unions))
    check(len(word_books) + len(phrase_books) + len(unions) == 224,
          "原目录总条目 224（175+8+41）")

    # 3) zz2572 与全部 community 来源
    zz = bk.BY_ID.get("zz") or {}
    check(zz.get("count") == 2572 and len(bk.words("zz")) == 2572,
          "中职 zz 保持 2572 原成员数")
    check(all(b.get("source_status") == "community_compilation"
              for b in bk.BY_ID.values()),
          "全部原目录条目均为 community_compilation")
    check(all(b.get("official_entry_count") is None
              for b in bk.BY_ID.values()),
          "不把民间词表冒充 official_entry_count")
    check(all(isinstance(b.get("source_note"), str) and b["source_note"].strip()
              for b in bk.BY_ID.values()),
          "community 来源注记非空")

    # 4) check_bank 不再依赖已删除官方审计
    bank_checks, bank_fails = check_bank.validate(DATA)
    check(not bank_fails,
          "check_bank 民间词表只读校验无失败（%d checks）" % len(bank_checks))
    source = io.open(os.path.join(APP, "scripts", "check_bank.py"),
                     encoding="utf-8").read()
    check("audit_syllabuses" not in source and "book_sources.json" not in source,
          "check_bank 已移除官方 source audit 依赖")

    # 5) 官方审计产物确实不存在
    for relative in AUDIT_ARTIFACTS:
        path = os.path.join(APP, relative.replace("/", os.sep))
        check(not os.path.exists(path), "无官方审计产物：" + relative)

    out.append("")
    out.append("COMMUNITY_BOOKS_CHECKS %d; FAILS %d" % (len(out) - 1, len(fails)))
    print("\n".join(out))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
