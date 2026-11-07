# -*- coding: utf-8 -*-
"""排期引擎的逻辑自测（不依赖界面）。"""
import sys, io, os, time
sys.path.insert(0, r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\app")
import scheduler as sch

fails = []


def check(name, cond, extra=""):
    if not cond:
        fails.append(name)
    print(("PASS " if cond else "FAIL ") + name + ("   " + str(extra) if extra else ""))


t0 = 1_000_000.0
words = [{"w": "w%d" % i} for i in range(5)]
words += [{"w": "known1"}, {"w": "retired1"}, {"w": "mastered1"}]
states = {"known1": {"st": "known", "due": None, "lv": 9},
          "retired1": {"st": "retired", "due": None, "lv": 9},
          "mastered1": {"st": "mastered", "due": None, "lv": 9}}

# 新词：一次取一个，跳过已出库/已会
item, cur = sch.next_new(words, states, 0)
check("取第一个新词", item and item["w"]["w"] == "w0" and item["idx"] == 0, item)
item2, cur2 = sch.next_new(words, states, 5)
check("跳过 known/retired/mastered", item2 is None and cur2 == len(words), (item2, cur2))

# 学到哪儿 cursor 就到哪儿，跨过连续出库的词
states2 = {"w0": {"st": "learning", "due": 0, "lv": 1}}
item3, cur3 = sch.next_new(words, states2, 0)
check("已开始学的词不再当新词", item3["w"]["w"] == "w1", item3["w"]["w"])

# 到期队列
states3 = {"a": {"st": "learning", "due": t0 - 100, "lv": 2},
           "b": {"st": "learning", "due": t0 - 500, "lv": 1},
           "c": {"st": "learning", "due": t0 + 500, "lv": 1}}
words3 = [{"w": "a"}, {"w": "b"}, {"w": "c"}]
dq = sch.due_queue(words3, states3, t0)
check("到期排序 + 未到期不出现", [w["w"] for _, w, _ in dq] == ["b", "a"], dq)
items = sch.review_items(words3, states3, t0)
check("review_items 结构", [it["kind"] for it in items] == ["review", "review"], items)

# 记得 / 模糊 / 不记得
st = sch.new_state(t0)
check("新词 lv=0、5 分钟后", st["lv"] == 0 and abs(st["due"] - (t0 + 300)) < 1, st)

st = sch.new_state(t0)
st["lv"] = 3
fz = sch.on_fuzzy(st, t0)
check("模糊不升不降", fz["lv"] == 3, fz)
check("模糊把复习提前一个节点", abs(fz["due"] - (t0 + sch.LEVELS[2])) < 1, fz)

st = sch.new_state(t0)
st["lv"] = 5
fg = sch.on_forget(st, t0)
check("不记得回退一级", fg["lv"] == 4, fg)
check("不记得 10 分钟后", abs(fg["due"] - (t0 + 600)) < 1, fg)
check("连续两次不记得触发当场重考", sch.on_forget(fg, t0).get("retry_now") is True)

st = sch.new_state(t0)
t = t0
for i in range(9):
    t += 10
    st = sch.on_remember(st, t)
check("9 轮后已掌握", st["st"] == "mastered" and st["due"] is None, st)

st3 = sch.on_retire(sch.new_state(t0))
check("不再出现", st3["st"] == "retired" and st3["due"] is None, st3)

lines = ["FAILED: %r" % fails if fails else "ALL OK"]
io.open(r"D:\user\Documents\deepseek-harness\default-workspace\vocab-app\data\test_result.txt",
        "w", encoding="utf-8").write("\n".join(lines))
print("ALL OK" if not fails else ("FAILED %d" % len(fails)))
sys.exit(1 if fails else 0)
