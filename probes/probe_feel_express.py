# -*- coding: utf-8 -*-
"""情绪表达正确性验收：造一批**真的在问情绪**的问句，看她的输出。

不是改测试集，是补一个缺失的测量维度：现有 96 问题只有 2 题问情绪，
"情绪词覆盖 3%" 是测量缺口，不是表达缺陷。
"""
import os, sys, time, json
from datetime import datetime, timezone

sys.path.insert(0, r"F:\ai chat\雯\sim")
sys.path.insert(0, r"F:\ai chat\memory_engine")
from affect import Affect
from brain import Brain
from self_engine import SelfEngine

DATA = r"F:\ai chat\雯\数据_world"
END = datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp()
CLOCK = {"now": END}
time.time = lambda: CLOCK["now"]
e = SelfEngine(affect=Affect(os.path.join(DATA, "affect.json")), enabled=True,
               human_store=os.path.join(DATA, "human_store.json"),
               semantic=True, semantic_store=os.path.join(DATA, "semantic_store.json"),
               procedural=True, proc_store=os.path.join(DATA, "proc_store.json"),
               mind=True, insight=True, selfmodel=True,
               self_store=os.path.join(DATA, "self_store.json"))
e.load_human().load_semantic().load_proc().load_self()
e.set_age(20.5)
b = Brain(e, goals=["毕业创作"])

# 真在问情绪的问句（对着库里有 feel 的记忆）
QS = ["第一次进暗房是什么感觉", "落榜那天你什么感觉",
      "爸爸说摄影没出路那天你什么感觉", "个展那天你什么感觉",
      "分手的时候你什么感觉", "第一次一个人出去拍片是什么感觉",
      "把旧相机带到宜昌那天你什么感觉", "收到录取通知书那天你什么感觉"]

FEEL_WORDS = set(json.load(open(r"F:\ai chat\memory_engine\feel_frames.json",
                                encoding="utf-8"))["words"])
hit = 0
for q in QS:
    r = b.turn(q)
    say = r["say"]
    has = any(w in say for w in FEEL_WORDS if len(w) >= 1)
    hit += has
    print("  %-4s %-8s %s" % ("FEEL" if has else "----", r["mode"], say[:64]))
print()
print("带出情绪词 %d/%d" % (hit, len(QS)))
