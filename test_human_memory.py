# -*- coding: utf-8 -*-
"""test_human_memory.py — 情景记忆的编码、过门检索、细节与持久化。"""
import os
import sys
import tempfile
import time

from affect import Affect
from human_memory import HumanMemory

PASS = []


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%d] %s" % (len(PASS), name))
    if detail:
        print("    " + detail)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))


def main():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "human.json")
    a = Affect()
    h = HumanMemory(path, decay=0.5, affect=a)

    # 年龄闸门：3 岁前不形成自传体记忆
    mid0 = h.remember({"who": "妈妈", "what": "抱我"}, dev_age=2.0, min_age=3.0, now=100)
    check("3 岁前拒绝编码", mid0 is None, "mid=%s" % mid0)

    ep = {"who": "外公", "where": "家", "when": "三月", "what": "给我旧相机",
          "feel": "郑重", "why": "想学", "result": "皮套磨破了"}
    mid = h.remember(ep, arousal=0.95, valence=0.7, now=1000, dev_age=20)
    m = h.memories[mid]
    check("高唤醒保留核心、压细节",
          len(m["episode"]) < len(m["full_episode"]) and "who" in m["episode"] and "what" in m["episode"],
          "episode=%d full=%d detail=%.2f" % (len(m["episode"]), len(m["full_episode"]), m["detail_kept"]))
    check("全量原文仍在", m["full_episode"].get("when") == "三月",
          str(m["full_episode"]))

    r = h.recall({"who": "外公", "what": "旧相机"}, now=2000)
    check("有关线索命中", r["best"] == mid, "best=%s conf=%.2f" % (r["best"], r["confidence"]))
    r2 = h.recall({"what": "火星殖民地"}, now=2000)
    check("无关线索不硬认", r2["best"] is None, "best=%s" % r2["best"])

    h.save()
    h2 = HumanMemory(path, decay=0.5, affect=a).load()
    check("存盘再读不丢记忆", mid in h2.memories and h2.memories[mid]["full_episode"] == ep)
    check("原子写不留临时文件", not any(x.endswith(".tmp") for x in os.listdir(tmp)),
          str(os.listdir(tmp)))
    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
