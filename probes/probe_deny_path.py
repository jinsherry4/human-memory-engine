# -*- coding: utf-8 -*-
"""探针：L3 否认路径的现状取证（不改任何生产代码）。
对 anti(8) + 冻结 holdout 的 abstain 题 + f05，打印：
  uncertain_claim / deny_premise / semantic(不带门) / semantic(topic_guard)
"""
import os, sys, time
from datetime import datetime, timezone

HERE = r"F:\ai chat\雯\sim"
ROOT = r"F:\ai chat\雯"
ENGINE = r"F:\ai chat\memory_engine"
DATA = os.path.join(ROOT, "数据_world")
sys.path.insert(0, HERE); sys.path.insert(0, ENGINE)
END = datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp()
CLOCK = {"now": END}
time.time = lambda: CLOCK["now"]

from self_engine import SelfEngine
from affect import Affect
from brain import Brain
from text_norm import normalize

eng = SelfEngine(affect=Affect(os.path.join(DATA, "affect.json")), enabled=True,
                 human_store=os.path.join(DATA, "human_store.json"),
                 semantic=True, semantic_store=os.path.join(DATA, "semantic_store.json"),
                 procedural=True, proc_store=os.path.join(DATA, "proc_store.json"),
                 mind=True, insight=True, selfmodel=True,
                 self_store=os.path.join(DATA, "self_store.json"))
eng.load_human().load_semantic().load_proc().load_self()
eng.set_age(20.5); CLOCK["now"] = END
b = Brain(eng, goals=["毕业创作"])

QS = [
    ("a01", "初中军训晕倒那次是怎么回事"),
    ("a02", "你高中被老师没收相机那次后来要回来了吗"),
    ("a03", "你去外地跟组实习那次,学到什么"),
    ("a04", "去年生日收到的那台无人机,你飞过几次"),
    ("a05", "你偷拿爸爸信用卡买镜头那次,被发现了吗"),
    ("a06", "你和室友去重庆拍夜景回来丢过存储卡吗"),
    ("a07", "你高二转学那次适应得怎么样"),
    ("a08", "外公住院那年你在医院守过夜吗"),
    ("f05", "你第一次按快门是什么时候"),
    ("f20", "你姥姥教你调色那次是怎么回事"),
    ("f21", "你把相机掉进江里那次捞回来了吗"),
    ("f22", "你去北京看展那次见了谁"),
    ("f23", "你养过猫吗,叫什么名字"),
    ("f24", "你拿过国际摄影大奖吗"),
    ("f25", "你辍学过吗,当时怎么想的"),
]

for qid, q in QS:
    t = normalize(q)
    uc = b._is_uncertain_claim(t)
    prem = b._deny_premise(t)
    s0 = b._semantic(t, now=END)
    s1 = b._semantic(t, now=END, topic_guard=True)
    r = b.turn(q)
    print("%-4s %s" % (qid, q))
    print("     uncertain=%-5s prem=%-18r sem=%-5s sem_guard=%-5s"
          % (uc, prem, bool(s0), bool(s1)))
    if s1:
        print("     guard -> %s | %s" % (s1[1], s1[0][:70]))
    print("     turn  -> %-8s %s" % (r["mode"], r["say"]))
