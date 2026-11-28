# -*- coding: utf-8 -*-
"""测「子串命名」信号：cue 是某条记忆 what 的**完整子串**（不是二字片段重叠），
说明问句确实在说这件事。

与现有 named 的区别：现有 named 要求 len(what_cue)>=6 且互为子串，
短词（"落榜"2字、"个展"2字）永远进不去。这里放开长度，但要求
**cue 是 what 的连续子串**——这比片段覆盖强得多，且不会把
"课第一次独立"这种跨词拼出来的串当命中。

判据：真实命中升、虚构误报必须仍为 0。
"""
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

REAL = [("艺考落榜那回，你在雪里坐了多久？", "第一次艺考落榜"),
        ("第一次进暗房是什么感觉", "第一次进暗房"),
        ("个展主题叫什么名字", "她的第一场个展"),
        ("爸爸说摄影没出路那天晚上你怎么过的", "爸爸说摄影没出路"),
        ("第一次一个人出去拍片拍了什么", "第一次一个人出去拍片"),
        ("校运会你给班里拍照了吗", "校运会"),
        ("第一次艺考落榜", "第一次艺考落榜"),
        ("分手那次是谁先说的", "分手"),
        ("把旧相机带到宜昌那天", "把外公那台旧相机带到宜昌"),
        ("暗房冲洗课第一次独立冲卷", "暗房冲洗课"),
        ("落榜那天你在哪", "第一次艺考落榜"),
        ("个展那天你什么感觉", "她的第一场个展")]
FAKE = ["初中军训晕倒那次是怎么回事", "你高中被老师没收相机那次后来要回来了吗",
        "你去外地跟组实习那次,学到什么", "去年生日收到的那台无人机,你飞过几次",
        "你偷拿爸爸信用卡买镜头那次,被发现了吗", "你和室友去重庆拍夜景回来丢过存储卡吗",
        "你高二转学那次适应得怎么样", "外公住院那年你在医院守过夜吗",
        "你姥姥教你调色那次是怎么回事", "你把相机掉进江里那次捞回来了吗",
        "你去北京看展那次见了谁", "你养过猫吗,叫什么名字",
        "你拿过国际摄影大奖吗", "你辍学过吗,当时怎么想的",
        "你小时候摔断过胳膊吗", "你和室友去爬过泰山吗",
        "你参加过省里的摄影比赛吗", "你卖过照片吗"]


def substring_hit(needle):
    """needle 是否为某条记忆 what 的连续子串（要求 needle 长度>=2）。"""
    if len(needle) < 2:
        return None
    best = None
    for m in e.memories.values():
        if m.get("retired"):
            continue
        what = str((m.get("episode") or {}).get("what") or "")
        if not what:
            continue
        if needle in what or what in needle:
            # 命中的 what 越短越精准（"分手"命中"分手"，比命中长句更确定）
            score = (len(needle) / float(len(what) + len(needle)), -len(what))
            if best is None or score > best[0]:
                best = (score, what)
    return best[1] if best else None


for tag, qs in (("REAL", [(q, t) for q, t in REAL]),
                ("FAKE", [(q, None) for q in FAKE])):
    print("=====", tag)
    ok = 0
    for q, target in qs:
        t = normalize(q)
        prem = b._deny_premise(t) or t
        hit = substring_hit(prem)
        if hit is None and prem != t:
            hit = substring_hit(t)
        good = bool(hit) and (target is None or target in hit)
        if target is not None:
            ok += good
        print("  %-4s %-30s prem=%-12r -> %s"
              % ("PASS" if good else ("FAIL" if target else "误报"),
                 q[:28], prem, hit))
    if tag == "REAL":
        print("  真实命中 %d/%d" % (ok, len(qs)))
