# -*- coding: utf-8 -*-
"""test_wen_say_expr.py — §19 表达层机制测试（第八轮落地验证）。

覆盖方法文档 §19.7 的可单测项：
  1. hedge 档位：置信→措辞（高置信干净、中置信"好像"）
  2. 认识立场语气词：中置信+轮换位 → 收"吧"；师长档禁用
  3. 语域收敛：师长档跳过随意立场副词
  4. 潜台词 avoid：尾巴撞上"不说什么"清单就留白
  5. 语义 hedge：单次传授的知道类事实"就是"→"应该是"
  6. Self-monitoring 事闸：未引用的库内断言被标记
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from affect import Affect
from brain import Brain
from chat_voice import ChatVoice
from self_engine import SelfEngine
from text_norm import normalize
import wen_say

PASS = []


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%d] %s" % (len(PASS), name))
    if detail:
        print("    " + detail)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))


EP = {"who": "自己", "where": "宜昌", "when": "春天", "what": "把外公那台旧相机带到宜昌",
      "feel": "踏实", "why": "一直放在家里不放心",
      "result": "旧相机还在，收在抽屉里，隔几天拿出来擦"}
VOICE = ChatVoice()
T0 = 1_000_000.0


def main():
    tmp = tempfile.mkdtemp()

    # ---- 1) hedge 档位 ----
    hi = wen_say.realize(dict(EP), VOICE, question="旧相机呢", mode="recall",
                         rot=0, conf=0.92, max_len=60)
    mid = wen_say.realize(dict(EP), VOICE, question="旧相机呢", mode="recall",
                          rot=0, conf=0.65, max_len=60)
    check("1 置信→hedge 档位：高置信干净，中置信出现'好像'",
          ("好像" not in hi) and ("好像" in mid),
          "高=%s｜中=%s" % (hi[:30], mid[:30]))

    # ---- 2) 认识立场语气词 ----
    got_ba = wen_say.realize(dict(EP), VOICE, question="旧相机呢", mode="recall",
                             rot=1, conf=0.7, max_len=60)
    elder = wen_say.realize(dict(EP), VOICE, question="旧相机呢", mode="recall",
                            rot=1, conf=0.7, register="师长", max_len=60)
    check("2 中置信平辈档收'吧'，师长档禁用",
          got_ba.rstrip("。 ").endswith("吧") and not elder.rstrip("。 ").endswith("吧"),
          "平辈=%s｜师长=%s" % (got_ba[-12:], elder[-12:]))

    # ---- 3) 语域收敛：师长档跳过随意立场副词 ----
    outs = set()
    for r in range(3):
        outs.add(wen_say.realize(dict(EP), VOICE, question="旧相机呢", mode="recall",
                                 rot=r, conf=0.9, register="师长", max_len=60))
    casual = any(o.startswith(("反正", "还好", "说实话")) for o in outs)
    check("3 师长档无随意立场副词", not casual,
          "师长档首词: %s" % [o[:4] for o in outs])

    # ---- 4) 潜台词 avoid：尾巴留白 ----
    sel = wen_say.select_slots(dict(EP), question="旧相机呢", avoid=("抽屉",))
    tail_vals = " ".join(v for _, v in sel["tails"])
    sel2 = wen_say.select_slots(dict(EP), question="旧相机呢")
    tail_vals2 = " ".join(v for _, v in sel2["tails"])
    check("4 avoid 清单让尾巴留白（撞上就不主动说）",
          ("抽屉" not in tail_vals) and ("抽屉" in tail_vals2),
          "有avoid尾巴=%s｜无avoid尾巴=%s" % (tail_vals[:22], tail_vals2[:22]))

    # ---- 5) 语义 hedge：单次传授的事实降格表达 ----
    e = SelfEngine(affect=Affect(), human_store=os.path.join(tmp, "h.json"),
                   semantic=True, semantic_store=os.path.join(tmp, "s.json"), mind=True)
    e.set_age(20.5)
    b = Brain(e)
    e.teach("雯", "knows:影调分离", "先分曝光再分色调", source="课", now=T0)
    o = b.turn("什么是影调分离")
    check("5 单次传授的知道类事实降格'应该是'",
          "应该是" in (o["say"] or "") and "就是" not in (o["say"] or ""),
          o["say"][:40])

    # ---- 6) Self-monitoring 事闸 ----
    D = 86400.0
    e.remember({"who": "外公", "where": "家", "what": "外公把那台旧相机当生日礼物给她",
                "feel": "郑重"}, arousal=0.5, now=T0 + 5 * D)
    b2 = Brain(e)
    o2 = b2.turn("还记得外公给你的相机吗")
    check("6 命中路径 self_monitor 通过", o2.get("self_monitor") is True,
          "why=%s" % o2.get("self_monitor_why"))
    # v1 事闸语义：回答引用了库内记忆的 what 却没指向本次命中的痕迹 → 标记
    cited = b2._self_monitor("我记得外公把那台旧相机当生日礼物给她", [o2.get("top", {}).get("id")])
    fake = "我还记得外公把那台旧相机当生日礼物给她，还包了三层红纸"
    ok, why = b2._self_monitor(fake, [])
    check("6-b 引用库内断言但未指向命中痕迹 → 事闸标记",
          cited[0] is True and ok is False and "断言" in why,
          "cited=%s fake=%s %s" % (cited[0], ok, why))

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
