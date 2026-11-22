# -*- coding: utf-8 -*-
"""test_semantic_graph.py — 事实、规则匹配、优先级、时间有效性、两次实践。"""
import os
import sys
import tempfile
import time

from semantic_graph import SemanticGraph

PASS = []


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%d] %s" % (len(PASS), name))
    if detail:
        print("    " + detail)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))


def main():
    tmp = tempfile.mkdtemp()
    sg = SemanticGraph(os.path.join(tmp, "sem.json"))

    # 普通化：空格/大小写/全半角
    sg.teach_rule("装卷", [["片头", "挂歪"]], "别硬拉，打开后盖重挂", priority=0, now=100)
    r = sg.match_rules("片头  挂歪了", now=200)
    check("规则做表层归一", r is not None and r["name"] == "装卷", str(r and r["name"]))

    sg.teach_rule("装卷优先", [["片头", "挂歪"]], "先停手", priority=2, now=110)
    r = sg.match_rules("片头挂歪", now=200)
    check("同条件按 priority", r and r["name"] == "装卷优先", str(r and r["name"]))

    sg.teach_rule("未来规则", [["片头", "挂歪"]], "未来才教", priority=9, now=500)
    r = sg.match_rules("片头挂歪", now=200)
    check("valid_from 未到不生效", r and r["name"] == "装卷优先", str(r and r["name"]))

    # 两次独立 lesson 才 verified
    sg.teach_rule("两次", [["合影", "虚化"]], "收小", source="课一", now=300)
    sg.teach_rule("两次", [["合影", "虚化"]], "收小", source="课二", now=400)
    r = sg.rules["两次"]
    check("两次独立教学转 verified", r["status"] == "verified" and len(r["lessons"]) == 2,
          "status=%s lessons=%d" % (r["status"], len(r["lessons"])))

    # 事实：两次支持转 verified；replace 标记旧说法
    fid = sg.teach("雯", "knows:景深", "清晰范围", source="a", now=300)
    sg.teach("雯", "knows:景深", "清晰范围", source="b", now=400)
    check("事实两次支持转 verified", sg.facts[fid]["status"] == "verified",
          sg.facts[fid]["status"])
    old = sg.teach("雯", "knows:景深", "越大越深", source="c", now=500, replace=True)
    check("replace 旧说法 superseded", sg.facts[fid]["status"] == "superseded",
          sg.facts[fid]["status"])

    # 确认练习
    before = sg.rules["两次"]["practice"]
    sg.confirm_rule("两次")
    sg.confirm_rule("两次")
    check("两次确认后 practice=2 且 verified",
          sg.rules["两次"]["practice"] == before + 2 and sg.rules["两次"]["status"] == "verified",
          "practice=%d" % sg.rules["两次"]["practice"])

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
