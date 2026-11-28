# -*- coding: utf-8 -*-
"""如果要再过 3 条，需要动哪一行门限？代价多大？

现状（不改门限）：真实 5/8、虚构 0 误报。
候选开关：n==1 且 text>=0.60 时允许过门（现要求 0.85+margin 或 0.95）。
测这条开关在更大样本上的收益与风险。
"""
import os, sys, time, shutil, tempfile
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

def mk():
    e = SelfEngine(affect=Affect(os.path.join(DATA, "affect.json")), enabled=True,
                   human_store=os.path.join(DATA, "human_store.json"),
                   semantic=True, semantic_store=os.path.join(DATA, "semantic_store.json"),
                   procedural=True, proc_store=os.path.join(DATA, "proc_store.json"),
                   mind=True, insight=True, selfmodel=True,
                   self_store=os.path.join(DATA, "self_store.json"))
    e.load_human().load_semantic().load_proc().load_self()
    e.set_age(20.5)
    return e

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
        # 追加：更接近真实的"没发生过但结构正常"的事件，防过拟合到 14 条
        "你小时候摔断过胳膊吗", "你和室友去爬过泰山吗",
        "你参加过省里的摄影比赛吗", "你卖过照片吗"]

e = mk()
b = Brain(e)


def probe(q, floor):
    """floor=None 用现存收；否则覆盖 human_memory 的收口判定。"""
    import human_memory as HM
    t = normalize(q)
    prem = b._deny_premise(t)
    cues = []
    if prem and len(prem) >= 2:
        cues.append({"what": prem})
    tok = {}
    import brain as B
    for k, pool in (("who", B.WHO), ("where", B.WHERE), ("when", B.WHEN), ("feel", B.FEEL)):
        for v in pool:
            if v in t:
                tok[k] = v
                break
    for v in B.EPISODIC_THINGS:
        if v in t and "what" not in tok:
            tok["what"] = v
            break
    if tok:
        cues.append(tok)
    for cue in cues:
        r = e.recall(cue)
        if r.get("best"):
            return True, (e.memories[r["best"]].get("episode") or {}).get("what") or ""
        if floor is not None:
            res = r.get("results") or []
            if res and len(cue) == 1 and res[0]["text"] >= floor:
                return True, (e.memories[res[0]["id"]].get("episode") or {}).get("what") or ""
    return False, None


for floor in (None, 0.90, 0.80, 0.70, 0.60):
    hit = sum(1 for q, tgt in REAL if probe(q, floor)[0])
    fp = [q for q in FAKE if probe(q, floor)[0]]
    tag = "不改门限" if floor is None else "n==1 且 text>=%.2f" % floor
    print("%-18s 真实 %d/%d   虚构误报 %d/%d  %s"
          % (tag, hit, len(REAL), len(fp), len(FAKE), fp[:3]))
