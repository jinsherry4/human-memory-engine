# -*- coding: utf-8 -*-
"""为什么 96 问里只有 3 条带出情绪词：trace select_slots 的选择。"""
import os, sys, json
sys.path.insert(0, r"F:\ai chat\memory_engine")
import wen_say as W

data = json.load(open(r"F:\ai chat\雯\judging\interview_latest.json", encoding="utf-8"))
rows = data if isinstance(data, list) else data.get("rows") or data.get("records") or []
print("访谈记录", len(rows))

# 该问是否"在问情绪"
asked_feel = 0
tail_feel = 0
no_feel_val = 0
detail = []
for r in rows:
    q = r.get("q") or ""
    if W.asked_dimension(q) == "feel":
        asked_feel += 1
print("问句本身在问 feel 的题:", asked_feel)

# 直接测：拿库里的记忆跑 select_slots，统计 feel 进入 tails 的比例
sys.path.insert(0, r"F:\ai chat\雯\sim")
d = json.load(open(r"F:\ai chat\雯\数据_world\human_store.json", encoding="utf-8"))
ms = list(d["memories"].values()) if isinstance(d["memories"], dict) else d["memories"]
n = 0
for m in ms[:200]:
    ep = m.get("episode") or {}
    if not ep.get("feel"):
        continue
    n += 1
    sel = W.select_slots(ep, question="那件事你什么感觉", max_tails=2)
    if ("feel", ep["feel"]) in sel["tails"]:
        tail_feel += 1
print("带 feel 的记忆 %d 条；问'什么感觉'时 feel 进尾巴 %d 条（%.0f%%）"
      % (n, tail_feel, 100.0 * tail_feel / max(1, n)))

# 问句不问 feel 时呢
tail2 = 0
for m in ms[:200]:
    ep = m.get("episode") or {}
    if not ep.get("feel"):
        continue
    sel = W.select_slots(ep, question="落榜那天你在哪", max_tails=2)
    if any(k == "feel" for k, _ in sel["tails"]):
        tail2 += 1
print("问'你在哪'（不问情绪）时 feel 进尾巴 %d/%d" % (tail2, n))
