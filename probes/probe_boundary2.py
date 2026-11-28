# -*- coding: utf-8 -*-
"""滑窗加约束：① 子串长度 >= 4 ② 命中记忆的 what 要覆盖子串的大部分（防"课第一次独立"）"""
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


def spans(s, min_len, max_len=16):
    out = []
    n = len(s)
    for L in range(min(max_len, n), min_len - 1, -1):
        for i in range(0, n - L + 1):
            out.append(s[i:i + L])
    return out


def cover(needle, hay):
    """needle 的二字片段有多少落在 hay 里。"""
    if len(needle) < 2:
        return 0.0
    gs = [needle[i:i + 2] for i in range(len(needle) - 1)]
    return sum(1 for g in gs if g in hay) / float(len(gs))


def boundary(t, min_len, cov_min):
    prem = b._deny_premise(t) or t
    for sp in [prem] + spans(prem, min_len, 14):
        r = e.recall({"what": sp})
        bid = r.get("best")
        if not bid:
            continue
        m = e.memories[bid]
        ep = m.get("episode") or {}
        hay = " ".join(str(v) for v in (m.get("full_episode") or ep).values())
        what = str(ep.get("what") or "")
        # 命中的 what 必须"包含"或"被包含"于子串，或至少二字覆盖过半
        if sp in what or what in sp or cover(sp, hay) >= cov_min:
            return sp, what
    return None, None


for min_len, cov in ((4, 0.6), (4, 0.5), (5, 0.6), (6, 0.6)):
    okr = 0
    fails = []
    for q, target in REAL:
        sp, got = boundary(normalize(q), min_len, cov)
        good = bool(got) and target in got
        okr += good
        if not good:
            fails.append((q, sp, got))
    fp = []
    for q in FAKE:
        sp, got = boundary(normalize(q), min_len, cov)
        if got:
            fp.append((q, sp, got))
    print("min_len=%d cov>=%.1f  REAL %d/%d  FAKE 误报 %d/%d"
          % (min_len, cov, okr, len(REAL), len(fp), len(FAKE)))
    for f in fails:
        print("    未命中 %-28s cue=%r -> %s" % (f[0][:26], f[1], f[2]))
    for f in fp:
        print("    误报   %-28s cue=%r -> %s" % (f[0][:26], f[1], f[2]))
