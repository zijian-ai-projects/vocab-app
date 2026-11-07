# -*- coding: utf-8 -*-
"""抓有道 jsonapi 的「简明英汉(ec)」释义 + 真 IPA 音标。可续跑。"""
import urllib.request, urllib.parse, json, io, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
OUTJSONL = os.path.join(ROOT, "data", "raw_youdao.jsonl")
XLSDATA = os.path.join(ROOT, "data", "words_xls.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Referer": "https://dict.youdao.com/"}

lock = threading.Lock()

def load_words():
    with io.open(XLSDATA, encoding="utf-8") as f:
        return json.load(f)

def fetch(w, tries=3):
    url = "https://dict.youdao.com/jsonapi?q=" + urllib.parse.quote(w)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            raw = urllib.request.urlopen(req, timeout=15).read()
            d = json.loads(raw.decode("utf-8", "replace"))
            ec = (d.get("ec") or {}).get("word") or []
            if not ec:
                return None
            w0 = ec[0]
            trs = []
            for tr in w0.get("trs", []):
                try:
                    trs.append(tr["tr"][0]["l"]["i"][0])
                except Exception:
                    pass
            simple = (d.get("simple") or {}).get("word") or [{}]
            s0 = simple[0]
            return {
                "word": w,
                "usphone": w0.get("usphone") or s0.get("usphone") or "",
                "ukphone": w0.get("ukphone") or s0.get("ukphone") or "",
                "ec": trs,
            }
        except Exception as e:
            last = e
            time.sleep(0.6 * (i + 1))
    return {"word": w, "error": "%s: %s" % (type(last).__name__, str(last)[:100])}

def main():
    words = load_words()
    if len(sys.argv) > 1 and sys.argv[1] == "--limit":
        words = words[:int(sys.argv[2])]
    done = set()
    if os.path.exists(OUTJSONL):
        with io.open(OUTJSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["word"])
                except Exception:
                    pass
    todo = [w["word"] for w in words if w["word"] not in done]
    print("total=%d done=%d todo=%d" % (len(words), len(done), len(todo)))
    os.makedirs(os.path.dirname(OUTJSONL), exist_ok=True)
    t0 = time.time()
    n = 0
    with io.open(OUTJSONL, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(fetch, todo):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 200 == 0:
                print("  %d/%d  %.1fs" % (n, len(todo), time.time() - t0), flush=True)
    print("FINISHED %d in %.1fs" % (n, time.time() - t0))

if __name__ == "__main__":
    main()
