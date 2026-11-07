# -*- coding: utf-8 -*-
"""把 xls 词表抽成 words_xls.json（用 anaconda 的 xlrd）。"""
import xlrd, io, json, os

SRC = r"C:\Users\zijian\Desktop\背单词\Excel大学英语六级词汇带音标-乱序版.xls"
ROOT = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app"
OUT = os.path.join(ROOT, "data", "words_xls.json")

bk = xlrd.open_workbook(SRC)
sh = bk.sheet_by_index(0)
rows = []
for r in range(1, sh.nrows):
    w = str(sh.cell_value(r, 1)).strip()
    if not w:
        continue
    rows.append({
        "idx": int(sh.cell_value(r, 0)) if str(sh.cell_value(r, 0)).strip().isdigit() else len(rows) + 1,
        "word": w,
        "phonetic_raw": str(sh.cell_value(r, 2)).strip(),
        "meaning_raw": str(sh.cell_value(r, 3)).strip(),
    })
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with io.open(OUT, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=0)
print("WROTE %d words" % len(rows))
