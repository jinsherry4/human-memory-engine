# -*- coding: utf-8 -*-
"""歧义消解实测：多条候选同分时，用「问的维度」在候选里挑。

不是调门限，是在**并列候选**里用问句意图破平（tie-break）。
判据：真实事件命中升、虚构误报仍 0。"""
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
        ("分手的时候你什么感觉", "分手"),
        ("第一次进暗房是什么感觉", "第一次进暗房"),
        ("把旧相机带到宜昌那天你什么感觉", "把外公那台旧相机带到宜昌"),
        ("爸爸说摄影没出路那天你什么感觉", "爸爸说摄影没出路"),
        ("收到录取通知书那天你什么感觉", "收到录取通知书")]
FAKE = ["初中军训晕倒那次怎么回事", "你高中被老师没收相机那次怎么回事",
        "你去外地跟组实习那次什么感觉", "你姥姥教你调色那次什么感觉",
        "你把相机掉进江里那次什么感觉", "你高二转学那次什么感觉"]


def tie_break(res, dim):
    """并列 text 相同时，优先选**被问维度的值最具体**的那条。"""
    if not res:
        return None
    top_text = res[0]["text"]
    tied = [r for r in res if abs(r["text"] - top_text) < 1e-6]
    if len(tied) == 1:
        return tied[0]
    if not dim:
        return res[0]

    def score(r):
        ep = (e.memories[r["id"]].get("full_episode") or {})
        v = str(ep.get(dim) or "")
        return (len(v), r["score"])
    return max(tied, key=score)


def probe(q):
    t = normalize(q)
    dim = W.asked_dimension(t)
    prem = b._deny_premise(t)
    for cue in ([{"what": prem}] if prem else []) + ([{"what": t}]):
        r = e.recall(cue)
        if r.get("best"):
            return (e.memories[r["best"]].get("episode") or {}).get("what"), "hit"
        # 并列候选：看能不能破平后**仍在原有候选里**
        res = r.get("results") or []
        if res and len(cue) == 1:
            # 只在有 >=2 条 text 并列满分时破平
            top = res[0]["text"]
            tied = [x for x in res if abs(x["text"] - top) < 1e-6]
            if len(tied) >= 2 and top >= 0.95:
                pick = tie_break(res, dim)
                if pick:
                    return (e.memories[pick["id"]].get("episode") or {}).get("what"), "tie"
    return None, None


ok = 0
for q, tgt in REAL:
    got, how = probe(q)
    good = bool(got) and tgt in got
    ok += good
    print("  %-4s %-5s %-30s -> %s" % ("PASS" if good else "FAIL", how, q[:28], got))
print("  真实 %d/%d" % (ok, len(REAL)))
fp = 0
for q in FAKE:
    got, how = probe(q)
    if got:
        fp += 1
        print("  误报 %-5s %-28s -> %s" % (how, q[:26], got))
print("  虚构误报 %d/%d" % (fp, len(FAKE)))
