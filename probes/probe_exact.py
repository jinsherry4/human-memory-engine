# -*- coding: utf-8 -*-
"""两个新信号（都不是调阈值）：
  S1 what 精确相等：某条记忆的 what 与线索完全同字 → 直接中选（信息论上最强）
  S2 疑问对象词剥离：'个展主题' → '个展'（主题/名字/感觉/内容 是问的对象，不是事件）
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

OBJECT = ("主题", "名字", "感觉", "内容", "结果", "原因", "细节", "意义",
          "时候", "地点", "过程", "样子", "情况")


def exact(needle):
    """S1: what 与 needle 全等。"""
    for m in e.memories.values():
        if m.get("retired"):
            continue
        ep = m.get("episode") or {}
        if str(ep.get("what") or "") == needle:
            return str(ep.get("what"))
    return None


def strip_object(prem):
    """S2: 剥疑问对象词。"""
    out = []
    for w in OBJECT:
        if prem.endswith(w) and len(prem) > len(w):
            out.append(prem[: -len(w)])
    # 也试"把 X 的 Y"这种：取 X
    if "的" in prem:
        out.append(prem.split("的")[0])
    return [s for s in out if len(s) >= 2]


def probe(q):
    t = normalize(q)
    prem = b._deny_premise(t) or t
    # S1
    hit = exact(prem)
    if hit:
        return "S1", prem, hit
    # 原路
    r = e.recall({"what": prem})
    if r.get("best"):
        return "P", prem, (e.memories[r["best"]].get("episode") or {}).get("what")
    # S2
    for cand in strip_object(prem):
        hit = exact(cand)
        if hit:
            return "S1s", cand, hit
        r = e.recall({"what": cand})
        if r.get("best"):
            return "S2", cand, (e.memories[r["best"]].get("episode") or {}).get("what")
    return None, prem, None


for tag, qs in (("REAL", [(q, t) for q, t in REAL]),
                ("FAKE", [(q, None) for q in FAKE])):
    print("=====", tag)
    ok = 0
    for q, target in qs:
        how, cue, got = probe(q)
        good = bool(got) and (target is None or target in got)
        if target is not None:
            ok += good
        print("  %-4s %-5s %-28s cue=%-12r -> %s"
              % ("PASS" if good else "FAIL", how, q[:26], cue, got))
    if target is not None or tag == "REAL":
        print("  真实命中 %d/%d" % (ok, len(qs)))
