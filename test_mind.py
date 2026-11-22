# -*- coding: utf-8 -*-
"""test_mind.py — Brain 的分层路由：规则、推算、回忆、知识、未知、确认、上下文。"""
import os
import sys
import tempfile

from affect import Affect
from brain import Brain
from self_engine import SelfEngine

PASS = []


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
                   procedural=True, proc_store=os.path.join(tmp, "p.json"),
                   selfmodel=True, self_store=os.path.join(tmp, "self.json"))
    e.set_age(20.5)
    b = Brain(e)

    e.teach_rule("合影要虚化", [["合影", "虚化"]], "收小光圈，别为了虚化开大", priority=2, now=100)
    out = b.turn("给二十个同学拍合影，又想背景虚化，光圈开大还是收小？")
    check("规则优先于泛化虚化反馈", out["mode"] == "apply" and "收小" in out["say"],
          out["say"])

    b.turn("今晚我只带了一支 f/2.8 的镜头，没带三脚架。")
    out = b.turn("江边夜景，ISO 100，快门 1/4，能拍吗？")
    check("上一句 f/2.8 能回带算差 4 档", "差 4 档" in out["say"], out["say"])

    e.remember({"who": "外公", "where": "家", "when": "三月",
                "what": "把旧相机给我", "feel": "郑重"}, now=200)
    out = b.turn("还记得外公给你的相机吗？")
    check("情景回忆命中", out["mode"] == "recall", "%s | %s" % (out["mode"], out["say"]))

    e.teach("雯", "knows:景深", "照片里清晰的范围", source="课一", now=300)
    e.teach("雯", "knows:景深", "照片里清晰的范围", source="课二", now=400)
    out = b.turn("什么是景深？")
    check("语义知识命中", out["mode"] == "know" and "清晰" in out["say"],
          "%s | %s" % (out["mode"], out["say"]))

    out = b.turn("测光表怎么用？")
    check("没学过 → unknown", out["mode"] == "unknown", out["say"])

    e.teach_rule("片头挂歪", [["片头", "挂歪", "硬拉"]], "别硬拉，打开后盖重挂", now=500)
    out = b.turn("新生装卷片头挂歪了还硬拉，怎么办？")
    check("装卷规则命中", out["mode"] == "apply" and "别硬拉" in out["say"], out["say"])
    out = b.turn("按你说的做了，管用了。")
    check("成功反馈确认规则", out["mode"] == "confirm" and out["rule"]["practice"] == 1,
          str(out["rule"] and out["rule"].get("practice")))

    out = b.turn("我按你说的把快门提到 1/60 了，照片还是糊，下一步查什么？")
    check("“按你说的”不带做了不算确认", out["mode"] == "apply" and "对焦" in out["say"],
          "%s | %s" % (out["mode"], out["say"]))

    e.affect.state["valence"] = -0.4
    e.teach_rule("父亲否定", [["爸爸", "摄影没出路"]], "不争对错，把话落到作品上", priority=2, now=600)
    out = b.turn("爸爸又说摄影没出路。")
    check("低落时家庭话题带语气", "心里堵" in out["say"], out["say"])

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
