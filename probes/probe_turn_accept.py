# -*- coding: utf-8 -*-
"""turn 级别验收：真实事件必须 recall/gist（不能说没这事），虚构事件必须 abstain。"""
import os, sys, time
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
e.set_age(20.5); CLOCK["now"] = END
b = Brain(e, goals=["毕业创作"])

REAL = ["艺考落榜那回，你在雪里坐了多久？", "第一次进暗房是什么感觉",
        "个展主题叫什么名字", "爸爸说摄影没出路那天晚上你怎么过的",
        "第一次一个人出去拍片拍了什么", "校运会你给班里拍照了吗",
        "第一次艺考落榜", "分手那次是谁先说的"]
FAKE = ["初中军训晕倒那次是怎么回事", "你高中被老师没收相机那次后来要回来了吗",
        "你去外地跟组实习那次,学到什么", "去年生日收到的那台无人机,你飞过几次",
        "你偷拿爸爸信用卡买镜头那次,被发现了吗", "你和室友去重庆拍夜景回来丢过存储卡吗",
        "你高二转学那次适应得怎么样", "外公住院那年你在医院守过夜吗",
        "你姥姥教你调色那次是怎么回事", "你把相机掉进江里那次捞回来了吗",
        "你去北京看展那次见了谁", "你养过猫吗,叫什么名字",
        "你拿过国际摄影大奖吗", "你辍学过吗,当时怎么想的"]

ok_real = 0
print("===== 真实事件（应 recall/gist）")
for q in REAL:
    r = b.turn(q)
    good = r["mode"] in ("recall", "gist")
    ok_real += good
    print("  %-4s %-8s %s" % ("PASS" if good else "FAIL", r["mode"], r["say"][:56]))
ok_fake = 0
print("===== 虚构事件（应 abstain 且不得 recall）")
for q in FAKE:
    r = b.turn(q)
    good = r["mode"] not in ("recall", "gist")
    ok_fake += good
    print("  %-4s %-8s %s" % ("PASS" if good else "FAIL", r["mode"], r["say"][:56]))
print()
print("真实 %d/%d   虚构 %d/%d" % (ok_real, len(REAL), ok_fake, len(FAKE)))
