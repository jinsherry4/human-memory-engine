# -*- coding: utf-8 -*-
"""为什么情景题被语义层抢答？"""
import os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, r"F:\ai chat\雯\sim")
sys.path.insert(0, r"F:\ai chat\memory_engine")
from affect import Affect
from brain import Brain
from self_engine import SelfEngine
from text_norm import normalize

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

for q in ["把旧相机带到宜昌那天你什么感觉", "个展那天你什么感觉",
          "分手的时候你什么感觉", "落榜那天你什么感觉"]:
    t = normalize(q)
    print("=" * 60)
    print("Q:", q)
    print("  _recall:", (b._recall(t) or {}).get("best"))
    print("  uncertain:", b._is_uncertain_claim(t))
    mem_req = (any(k in t for k in ('记得', '那次', '当时', '最开始', '刚才')))
    print("  mem_req:", mem_req, "| semantic:", b._semantic(t, now=END))
    print("  asked_dim:", __import__('wen_say').asked_dimension(t))
    print("  turn:", b.turn(q)["mode"], "|", b.turn(q)["say"][:60])
