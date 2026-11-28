# -*- coding: utf-8 -*-
"""test_comm_repair.py — 会话修复与陪伴模式测试（DS-COMM-01 第六/四章落地验证）。

  1. 纠正→rehearse 修订痕迹→具体承认（"对，是X。我刚才记岔了。"）
  2. 陪伴模式：情绪陈述句接住，不给方案、不追问、不病理化
  3. 装备陈述不走陪伴（走原路径）
  4. 确认路径不受修复分支影响
  5. 无目标纠正不硬认（教材 5.3：对方记错时用证据澄清）
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from affect import Affect
from brain import Brain
from self_engine import SelfEngine

PASS = []
T0 = 1_000_000.0
D = 86400.0


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%d] %s" % (len(PASS), name))
    if detail:
        print("    " + detail)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))


def main():
    tmp = tempfile.mkdtemp()
    e = SelfEngine(affect=Affect(), human_store=os.path.join(tmp, "h.json"),
                   semantic=True, semantic_store=os.path.join(tmp, "s.json"),
                   mind=True, selfmodel=True,
                   self_store=os.path.join(tmp, "self.json"))
    e.set_age(20.5)
    b = Brain(e)
    e.remember({"who": "自己", "where": "考场外", "when": "冬天",
                "what": "第一次艺考落榜", "feel": "崩塌",
                "result": "在雪里坐了很久"}, arousal=0.8, now=T0 + 5 * D,
               valence=-0.8)

    # ---- 1) 纠正→rehearse→具体承认 ----
    o1 = b.turn("落榜那天你在哪")
    check("1a 先命中情景回忆", o1["mode"] == "recall", o1["say"][:30])
    o2 = b.turn("你说的不对，那天是阴天，没有下雪")
    check("1b 纠正→repair 模式+具体承认", o2["mode"] == "repair"
          and "阴天" in o2["say"] and "记岔" in o2["say"], o2["say"])
    mid = o1.get("top", {}).get("id")
    traces = e.memories[mid]["traces"] if mid in e.memories else []
    check("1c rehearse 写入 corrected 痕迹",
          any(t.get("kind") == "corrected" for t in traces),
          "traces=%s" % [t.get("kind") for t in traces][-3:])

    # ---- 2) 陪伴模式 ----
    o3 = b.turn("今天修图修了一整天，眼睛都要瞎了，好累")
    check("2a 情绪陈述→陪伴模式（不给方案）", o3["mode"] == "empathy"
          and "建议" not in o3["say"] and "应该" not in o3["say"], o3["say"])
    o4 = b.turn("嗯，就是眼干加颈椎疼")
    check("2b 后续陈述仍接住", o4["mode"] == "empathy", o4["say"])

    # ---- 3) 装备陈述不走陪伴 ----
    o5 = b.turn("今晚只带了一支 f/2.8 的镜头，没带三脚架")
    check("3 装备陈述不触发陪伴", o5["mode"] != "empathy", o5["mode"])

    # ---- 4) 确认路径不受影响 ----
    e.teach_rule("合影要虚化", [["合影", "虚化"]], "收小光圈，别为了虚化开大",
                 priority=2, now=T0 + 700 * D)
    o6 = b.turn("给二十个同学拍合影，又想背景虚化，光圈开大还是收小？")
    o7 = b.turn("按你说的做了，管用了。")
    check("4 确认路径正常（repair 分支未劫持）",
          o6["mode"] == "apply" and o7["mode"] == "confirm",
          "%s / %s" % (o6["mode"], o7["mode"]))

    # ---- 5) 无目标纠正不硬认 ----
    o8 = b.turn("你说的不对， cortisol 是皮质醇")
    check("5 无情景目标的纠正不产生虚假认错", o8["mode"] != "repair", o8["say"][:30])

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
