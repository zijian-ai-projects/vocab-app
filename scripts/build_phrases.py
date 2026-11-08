# -*- coding: utf-8 -*-
"""把工作区已提供的词组词表/释义构建成独立补充库；不改原单词库或原词书。

只收有真实中文释义的词组，源顺序去重。源缺释义且其它已提供来源也无法补全则跳过。
卡面保留两个短释义，完整来源释义留 raw 供内容浏览。无需联网。
"""
import csv
import io
import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(os.path.dirname(ROOT), "vocablib", "maimemo-export-main", "exported")
SOURCES = [
    ("cet4-phrases", "cet4", "四六级常考核心词组", "四六级常考核心词组1500"),
    ("cet6-phrases", "cet6", "四六级常考核心词组", "四六级常考核心词组1500"),
    ("zk-phrases", "zhongkao", "初中英语常考短语", "初中英语常考短语"),
    ("gk-phrases", "gaokao", "高考英语必背短语", "24天突破高考英语必背短语"),
    ("ky-phrases", "kaoyan", "考研英语词组 · 恋练不忘", "2026恋练不忘考研英语词组"),
    ("ielts-phrases", "ielts", "雅思词组必备", "雅思词组必备"),
    ("toefl-phrases", "toefl", "托福词组必备", "托福词组必备"),
    ("gre-phrases", "gre", "GRE 短语搭配", "GRE高分必备短语搭配"),
]
CN = re.compile(r"[\u4e00-\u9fff]")
POS = re.compile(r"^(n|v|vt|vi|adj|adv|prep|conj|pron|det|num|aux|int|interj)\.\s*")
UNKNOWN_POS = re.compile(r"^(?:na|un)\.\s*", re.I)


def key(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).strip()).lower()


def make_entry(word, translation):
    lines = [line.strip() for line in translation.splitlines() if line.strip()]
    if not lines or not CN.search(translation):
        return None
    pos = POS.match(lines[0])
    # 导出词典第二行通常是更常用的义项，避开第一行的“xx 的变体”等噪声。
    text = next((line for line in reversed(lines) if CN.search(line)), lines[0])
    text = UNKNOWN_POS.sub("", text)
    text = POS.sub("", text)
    senses = []
    for sense in re.split(r"[；;]", text):
        sense = sense.strip(" ，,；;\t")
        if sense and sense not in senses:
            senses.append(sense)
        if len(senses) == 2:
            break
    short = "；".join(senses)
    if not short or not CN.search(short):
        return None
    return {"w": word, "type": "phrase", "ipa": "", "pos": [pos.group(1) + "."] if pos else [],
            "s": short, "raw": translation.strip()}


def main():
    gloss = {}
    loaded = {}
    for _, _, _, name in SOURCES:
        if name in loaded:
            continue
        path = os.path.join(SOURCE, "translation", name + ".csv")
        with io.open(path, encoding="utf-8-sig", newline="") as stream:
            for row in csv.reader(stream):
                if len(row) < 2:
                    continue
                word = key(row[0])
                if not re.search(r"\s", word) or not re.match(r"^[a-z]", word) or CN.search(word):
                    continue
                entry = make_entry(word, row[1])
                if entry and word not in gloss:
                    gloss[word] = entry
        order_path = os.path.join(SOURCE, "word", name + ".txt")
        with io.open(order_path, encoding="utf-8-sig") as stream:
            loaded[name] = [key(line) for line in stream if line.strip()]
    books, used, report = [], set(), []
    for book_id, group, name, source_name in SOURCES:
        words, seen, missing = [], set(), 0
        for word in loaded[source_name]:
            if word in seen or not re.search(r"\s", word):
                continue
            seen.add(word)
            if word not in gloss:
                missing += 1
                continue
            words.append(word)
            used.add(word)
        books.append({"id": book_id, "group": group, "name": name, "display": name,
                      "type": "phrase", "kind": "local-phrase", "series": "", "count": len(words),
                      "words": words, "source": "maimemo-export/" + source_name})
        report.append({"book": book_id, "usable": len(words), "without_translation": missing})
    phrases = [gloss[word] for word in sorted(used)]
    for name, payload in (("phrases.json", phrases),
                          ("phrase_books.json", {"schema": 1, "items": books})):
        path = os.path.abspath(os.path.join(ROOT, "data", name))
        assert os.path.dirname(path) == os.path.join(ROOT, "data")
        with io.open(path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
    print(json.dumps({"phrases": len(phrases), "books": report}, ensure_ascii=True))


if __name__ == "__main__":
    main()
