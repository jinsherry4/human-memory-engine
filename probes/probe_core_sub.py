# -*- coding: utf-8 -*-
"""测「实词骨架子串」：把 prem 与 what 都剥掉修饰/虚词后，看骨架是否互为子串。

目标：'个展主题' vs '她的第一场个展' → 骨架 '个展' vs '个展' → 命中
      '校运会你给班里拍照' vs '校运会拍了一整天' → '校运会班里拍照' vs '校运会拍整天'
两者仍不同，所以这条也救不了校运会。先量清楚各条能到哪。
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

REAL = [("个展主题叫什么名字", "她的第一场个展"),
        ("校运会你给班里拍照了吗", "校运会"),
        ("分手那次是谁先说的", "分手"),
        ("把旧相机带到宜昌那天", "把外公那台旧相机带到宜昌"),
        ("暗房冲洗课第一次独立冲卷", "暗房冲洗课")]
FAKE = ["初中军训晕倒那次是怎么回事", "你高中被老师没收相机那次后来要回来了吗",
        "你去外地跟组实习那次,学到什么", "去年生日收到的那台无人机,你飞过几次",
        "你偷拿爸爸信用卡买镜头那次,被发现了吗", "你和室友去重庆拍夜景回来丢过存储卡吗",
        "你高二转学那次适应得怎么样", "外公住院那年你在医院守过夜吗",
        "你姥姥教你调色那次是怎么回事", "你把相机掉进江里那次捞回来了吗",
        "你去北京看展那次见了谁", "你养过猫吗,叫什么名字",
        "你拿过国际摄影大奖吗", "你辍学过吗,当时怎么想的"]

MOD = set("她的他我的你的第一场个次号那这此些有在了很太都也就还是")


def core(s):
    """实词骨架：去修饰/虚词。"""
    return "".join(ch for ch in str(s or "") if ch not in MOD)


def sub_match(needle):
    n = core(needle)
    best = None
    for m in e.memories.values():
        if m.get("retired"):
            continue
        what = str((m.get("episode") or {}).get("what") or "")
        w = core(what)
        if not w or not n:
            continue
        if n in w or w in n:
            score = (len(n) / float(len(w) + len(n)), -len(w))
            if best is None or score > best[0]:
                best = (score, what)
    return best[1] if best else None


for tag, qs in (("REAL", [(q, t) for q, t in REAL]),
                ("FAKE", [(q, None) for q in FAKE])):
    print("=====", tag)
    ok = 0
    for q, target in qs:
        t = normalize(q)
        prem = b._deny_premise(t)
        hit = sub_match(prem) or sub_match(t)
        good = bool(hit) and (target is None or target in hit)
        if target is not None:
            ok += good
        if target is None and hit:
            print("  误报 %-28s -> %s" % (q[:26], hit))
        elif target is not None:
            print("  %-4s %-28s core(%r)-> %s"
                  % ("PASS" if good else "FAIL", q[:26], prem, hit))
    if tag == "REAL":
        print("  真实命中 %d/%d" % (ok, len(qs)))
