# -*- coding: utf-8 -*-
"""反向覆盖：问句的二字段落在记忆里的比例（而不是记忆覆盖问句全部）。

现有 _text_score 用的是 hit/total 已经就是这个方向……但候选资格那条
（txt>=0.25 or hard>=0.20 or soft>=0.70 or named）过了，卡的是**过门**里
n==1 要求 text>=0.60。测：把"问句去掉记忆没有的字"后再检索，看能否干净拿到。
"""
import os, sys, time
from datetime import datetime, timezone

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
b = Brain(e)

REAL = [("艺考落榜那回，你在雪里坐了多久？", "第一次艺考落榜"),
        ("第一次进暗房是什么感觉", "第一次进暗房"),
        ("个展主题叫什么名字", "她的第一场个展"),
        ("爸爸说摄影没出路那天晚上你怎么过的", "爸爸说摄影没出路"),
        ("第一次一个人出去拍片拍了什么", "第一次一个人出去拍片"),
        ("校运会你给班里拍照了吗", "校运会"),
        ("第一次艺考落榜", "第一次艺考落榜"),
        ("分手那次是谁先说的", "分手"),
        ("把旧相机带到宜昌那天", "把外公那台旧相机带到宜昌"),
        ("暗房冲洗课第一次独立冲卷", "暗房冲洗课")]
FAKE = ["初中军训晕倒那次是怎么回事", "你高中被老师没收相机那次后来要回来了吗",
        "你去外地跟组实习那次,学到什么", "去年生日收到的那台无人机,你飞过几次",
        "你偷拿爸爸信用卡买镜头那次,被发现了吗", "你和室友去重庆拍夜景回来丢过存储卡吗",
        "你高二转学那次适应得怎么样", "外公住院那年你在医院守过夜吗",
        "你姥姥教你调色那次是怎么回事", "你把相机掉进江里那次捞回来了吗",
        "你去北京看展那次见了谁", "你养过猫吗,叫什么名字",
        "你拿过国际摄影大奖吗", "你辍学过吗,当时怎么想的",
        "你小时候摔断过胳膊吗", "你和室友去爬过泰山吗",
        "你参加过省里的摄影比赛吗", "你卖过照片吗"]

# 疑问/虚词字：从问句里剔掉它们，剩下的就是"事件内容字"
FILLER = set("你你们我她他吗呢吧啊呀的是了在有和跟给把被就都也还又很挺太"
             "怎么什么哪谁几多少要不要能不能会可以那次回上下天年时候个种样"
             "主题名字感觉内容结果原因细节意义地点过程情况多久多少")


def skeleton(s):
    """去掉疑问与虚词后的实词骨架（保序）。"""
    out = []
    for ch in s:
        if ch in FILLER:
            continue
        out.append(ch)
    return "".join(out)


def probe(q):
    t = normalize(q)
    prem = b._deny_premise(t) or t
    # 原路
    r = e.recall({"what": prem})
    if r.get("best"):
        return "P", prem, (e.memories[r["best"]].get("episode") or {}).get("what")
    # 骨架路
    for cand in (skeleton(prem), skeleton(t)):
        if len(cand) < 2:
            continue
        r = e.recall({"what": cand})
        if r.get("best"):
            return "K", cand, (e.memories[r["best"]].get("episode") or {}).get("what")
    return None, prem, None


for tag in ("REAL", "FAKE"):
    print("=====", tag)
    ok = 0
    qs = [(q, tg) for q, tg in REAL] if tag == "REAL" else [(q, None) for q in FAKE]
    for q, target in qs:
        how, cue, got = probe(q)
        good = bool(got) and (target is None or target in got)
        if target is not None:
            ok += good
        print("  %-4s %-3s %-26s cue=%-14r -> %s"
              % ("PASS" if good else ("FAIL" if target else "误报"), how,
                 q[:24], cue, got))
    if tag == "REAL":
        print("  真实命中 %d/%d" % (ok, len(qs)))
