# -*- coding: utf-8 -*-
"""补抓有道：读 data/bank_todo.json，把结果追加到 data/raw_youdao_bank.jsonl。可续跑。"""
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fetch_youdao import fetch  # noqa: E402

DATA = os.path.join(ROOT, "data")
TODO = os.path.join(DATA, "bank_todo.json")
OUT = os.path.join(DATA, "raw_youdao_bank.jsonl")


def main():
    words = json.load(io.open(TODO, encoding="utf-8"))
    done = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            try:
                o = json.loads(line)
            except Exception:
                continue
            if isinstance(o, dict) and o.get("word") and not o.get("error"):
                done.add(o["word"])
    todo = [w for w in words if w not in done]
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=", 1)[1])
    if limit:
        todo = todo[:limit]
    print("total=%d done=%d todo=%d" % (len(words), len(done), len(todo)))
    t0 = time.time()
    n = 0
    with io.open(OUT, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(fetch, todo):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 500 == 0:
                print("  %d/%d  %.1fs" % (n, len(todo), time.time() - t0), flush=True)
    print("FINISHED %d in %.1fs" % (n, time.time() - t0))


if __name__ == "__main__":
    main()
