# -*- coding: utf-8 -*-
"""事件边界搜索：在问句里滑窗找「最小可命中记忆的子串」。

不动任何门限，只换线索。判据：真实命中升、虚构误报必须仍为 0。
"""
import os, sys, time, itertools
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


def spans(s, min_len=2, max_len=16):
    """所有长度 min..max 的子串，长的优先。"""
    out = []
    n = len(s)
    for L in range(min(max_len, n), min_len - 1, -1):
        for i in range(0, n - L + 1):
            out.append(s[i:i + L])
    return out


def try_cue(cue_text):
    r = e.recall({"what": cue_text})
    if r.get("best"):
        return (e.memories[r["best"]].get("episode") or {}).get("what") or ""
    return None


def boundary_hit(t):
    prem = b._deny_premise(t) or t
    # 先用整段短语，再滑窗找更短的边界
    hit = try_cue(prem)
    if hit:
        return prem, hit
    for sp in spans(prem, 2, 14):
        hit = try_cue(sp)
        if hit:
            return sp, hit
    return None, None


print("===== REAL（滑窗边界）")
okr = 0
for q, target in REAL:
    sp, got = boundary_hit(normalize(q))
    good = bool(got) and target in got
    okr += good
    print("  %-4s %-34s -> cue=%-14r %s" % ("PASS" if good else "FAIL", q[:30], sp, got))
print("===== FAKE（必须 0 命中）")
fps = []
for q in FAKE:
    sp, got = boundary_hit(normalize(q))
    if got:
        fps.append((q, sp, got))
print("  误报 %d/%d" % (len(fps), len(FAKE)))
for f in fps:
    print("    %-30s cue=%-14r -> %s" % (f[0][:28], f[1], f[2]))
print()
print("真实 %d/%d  虚构误报 %d/%d" % (okr, len(REAL), len(fps), len(FAKE)))
