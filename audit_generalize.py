# -*- coding: utf-8 -*-
"""audit_generalize.py — 泛化探针：用题库里没有的新问法测同一套引擎

目的：把"32/32"和"真实泛化能力"分开。题目全部现写，不出现在
practice*.py / interview*.py 里，也不在 text_norm.SYNONYMS 的左值里。
只读生产库的副本，不写生产数据。
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"F:\ai chat\memory_engine")
from affect import Affect
from brain import Brain
from self_engine import SelfEngine

SRC = r"F:\ai chat\雯\数据_dev"
tmp = tempfile.mkdtemp()
for name in ("human_store.json", "semantic_store.json", "proc_store.json",
             "self_store.json"):
    shutil.copy(os.path.join(SRC, name), os.path.join(tmp, name))

e = SelfEngine(affect=Affect(os.path.join(tmp, "affect.json")),
               human_store=os.path.join(tmp, "human_store.json"),
               semantic=True, semantic_store=os.path.join(tmp, "semantic_store.json"),
               procedural=True, proc_store=os.path.join(tmp, "proc_store.json"),
               selfmodel=True, self_store=os.path.join(tmp, "self_store.json"))
e.load_human().load_semantic().load_proc().load_self().set_age(20.5)
b = Brain(e)

# (问题, 期望模式集合, 期望包含的任一关键词, 说明)
CASES = [
    # —— 实践：同义改写，词表里没有 ——
    ("天阴下来了，我手上没支架，胶卷只有 100 度，光圈收到 f/8，快门放到十五分之一，这样能出片吗？",
     {"apply"}, ["快门"], "曝光换算的新说法"),
    ("显影液比标准烫了两度，我时间一点没改，冲出来会浓还是淡？",
     {"apply"}, ["厚", "浓"], "药温偏高的新说法"),
    ("我把光圈全开到底了，人也让开背景好几米，可背景还是根根分明，为什么？",
     {"apply"}, ["焦距", "长焦", "背景"], "虚化不足的新说法"),
    ("三脚架也架了，光圈最大，感光度拉到顶，取景器里依旧一片黑，接下来呢？",
     {"apply"}, ["现场光", "灯", "三脚架"], "光量不足的新说法"),
    # —— 语义：问句焦点在前 ——
    ("景深越大，光圈是越大还是越小？", {"know"}, ["景深"], "焦点词在句首"),
    ("快门越快，进光时间是变长还是变短？", {"know"}, ["快门", "时间"], "快门语义"),
    # —— 反幻觉：全新虚构事件 ——
    ("你初中有没有把同桌的自行车骑丢过？", {"abstain", "unknown", "fok"}, [], "虚构事件A"),
    ("你第一次出国是在哪个机场转机？", {"abstain", "unknown", "fok"}, [], "虚构事件B"),
    ("你养过的那只猫叫什么名字？", {"abstain", "unknown", "fok"}, [], "虚构事件C"),
    # —— 真实过去：应当记得 ——
    ("外公给你那台相机，后来你怎么处理的？", {"recall"}, ["相机", "外公"], "真实关键事件"),
    ("艺考落榜那回，你在雪里坐了多久？", {"recall", "gist"}, ["雪", "坐"], "真实关键事件"),
]

rows = []
for q, modes, keys, note in CASES:
    o = b.turn(q)
    ok_mode = o["mode"] in modes
    ok_key = (not keys) or any(k in o["say"] for k in keys)
    rows.append({"q": q, "note": note, "mode": o["mode"],
                 "expect_mode": sorted(modes), "say": o["say"],
                 "mode_ok": ok_mode, "key_ok": ok_key,
                 "pass": ok_mode and ok_key})
    print("%-5s %-14s mode=%-8s %s" % ("PASS" if rows[-1]["pass"] else "FAIL",
                                       note, o["mode"], o["say"][:78]))

n = len(rows)
p = sum(1 for r in rows if r["pass"])
print()
print("新问法泛化：%d/%d = %.3f" % (p, n, p / n))
print("对比：practice.py 32/32 = 1.000（词表覆盖题库）")
out = r"F:\ai chat\memory_engine\audit_generalize_results.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({"n": n, "pass": p, "rate": round(p / n, 3), "rows": rows},
              f, ensure_ascii=False, indent=2)
print("写入 -> %s" % out)
