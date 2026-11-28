# -*- coding: utf-8 -*-
"""验证「说法差异」是不是剩余漏答的主因：把目标记忆的 what 和问题短语并排看。"""
import os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, r"F:\ai chat\memory_engine")
from affect import Affect
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

STUCK = [("个展主题", "个展"), ("校运会你给班里拍照", "校运会"),
         ("把旧相机带到宜昌", "旧相机"), ("暗房冲洗课第一次独立冲卷", "暗房冲洗课"),
         ("第一次一个人出去拍片", "拍片")]

for prem, kw in STUCK:
    print("=" * 66)
    print("短语: %r  | 关键词: %r" % (prem, kw))
    # 库里 what 含关键词的条目
    hits = [(m.get("episode") or {}).get("what") for m in e.memories.values()
            if kw in str((m.get("episode") or {}).get("what") or "")]
    print("  含关键词的记忆 what:")
    for h in hits[:6]:
        print("     %r" % h)
    r = e.recall({"what": prem})
    print("  短语检索 best:", r.get("best"),
          "| top text=%.3f" % ((r.get("results") or [{}])[0].get("text", 0)
                               if r.get("results") else 0))
