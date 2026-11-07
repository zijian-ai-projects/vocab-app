# -*- coding: utf-8 -*-
"""截取卡片窗口，供自检。

用法：python scripts/shot.py [输出名]     默认 shot.png
只截卡片本身（自动去掉截图留的 12px 边距）。
"""
import json, io, os, sys, time
from PIL import ImageGrab

DATA = r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\data"
geo = json.load(io.open(os.path.join(DATA, "_win.json"), encoding="utf-8"))
pad = 12
box = (geo["x"] - pad, geo["y"] - pad, geo["x"] + geo["w"] + pad, geo["y"] + geo["h"] + pad)
name = sys.argv[1] if len(sys.argv) > 1 else "shot"
if not name.endswith(".png"):
    name += ".png"
img = ImageGrab.grab(bbox=box, all_screens=True).crop((pad, pad, pad + geo["w"], pad + geo["h"]))
out = os.path.join(DATA, name)
img.save(out)
print("SHOT", img.size, out)
