# -*- coding: utf-8 -*-
"""窄通路候选：当 text 并列候选被 _dim 破平、且**破平后有明显胜者**时，
是否允许过门？

判据必须严：并列组 >=2、破平胜者的该维值明显更长、且断崖明显。
先看数据里这个信号有多干净。"""
import os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, r"F:\ai chat\memory_engine")
from affect import Affect
from brain import Brain
from self_engine import SelfEngine
from text_norm import normalize
import wen_say as W

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
b = Brain(e)

REAL = [("落榜那天你什么感觉", "第一次艺考落榜"),
        ("个展那天你什么感觉", "她的第一场个展"),
        ("分手的时候你什么感觉", "分手")]
FAKE = ["初中军训晕倒那次什么感觉", "你高中被老师没收相机那次什么感觉",
        "你去外地跟组实习那次什么感觉", "你姥姥教你调色那次什么感觉",
        "你把相机掉进江里那次什么感觉", "你高二转学那次什么感觉",
        "外公住院那年什么感觉", "你养过猫吗什么感觉"]

for tag, qs in (("REAL", REAL), ("FAKE", FAKE)):
    print("=====", tag)
    for item in qs:
        q, tgt = item if isinstance(item, tuple) else (item, None)
        t = normalize(q)
        dim = W.asked_dimension(t)
        prem = b._deny_premise(t)
        r = e.recall({"what": prem, "_dim": dim})
        res = r.get("results") or []
        top = res[0] if res else None
        tie = [x for x in res if top and abs(x["text"] - top["text"]) < 1e-9]
        if top:
            ep0 = e.memories[top["id"]].get("full_episode") or {}
            v0 = len(str(ep0.get(dim or "") or ""))
            v1 = 0
            for x in tie[1:]:
                ep = e.memories[x["id"]].get("full_episode") or {}
                v1 = max(v1, len(str(ep.get(dim or "") or "")))
        else:
            v0 = v1 = 0
        print("  %-28s prem=%-10r best=%-5s 并列=%d 胜者维长=%d 次者=%d"
              % (q[:26], prem, str(r.get("best")), len(tie), v0, v1))
