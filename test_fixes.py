# -*- coding: utf-8 -*-
"""test_fixes.py — 针对复查报告里旧代码缺陷的回归测试。

这些不是“新功能”，是防止重建版把旧坑再踩一遍：
无关线索硬认、高唤醒细节不可见、非原子写、否定句、误确认、f/2.8 误触发。
"""
import json
import os
import sys
import tempfile

from affect import Affect
from human_memory import HumanMemory
from persistence import save_json
from perceive import appraise_text
from practice_engine import bokeh_feedback

PASS = []


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%d] %s" % (len(PASS), name))
    if detail:
        print("    " + detail)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))


def main():
    tmp = tempfile.mkdtemp()

    # 1. 无关线索不硬认
    h = HumanMemory(os.path.join(tmp, "h.json"), affect=Affect())
    h.remember({"who": "外公", "what": "给相机"}, now=100)
    r = h.recall({"what": "完全无关的量子计算机"})
    check("无关线索 best=None", r["best"] is None, "best=%s" % r["best"])

    # 2. 高唤醒时 full_episode 不被 episode 掩盖
    ep = {"who": "自己", "where": "考场外", "when": "冬天",
          "what": "落榜", "feel": "空", "why": "差三分", "result": "雪里坐很久"}
    mid = h.remember(ep, arousal=1.0, now=200)
    m = h.memories[mid]
    check("高唤醒 detail_kept<1 但 full_episode 完整",
          m["detail_kept"] < 1.0 and len(m["full_episode"]) == len(ep),
          "detail=%.2f full=%d" % (m["detail_kept"], len(m["full_episode"])))

    # 3. 原子写 + .bak
    p = os.path.join(tmp, "a.json")
    save_json(p, {"v": 1})
    save_json(p, {"v": 2})
    got = json.load(open(p, encoding="utf-8"))
    bak = json.load(open(p + ".bak", encoding="utf-8"))
    check("第二次写保留 .bak 且当前文件正确", got["v"] == 2 and bak["v"] == 1,
          "now=%s bak=%s" % (got, bak))
    check("没有遗留 .tmp", not any(x.endswith(".tmp") for x in os.listdir(tmp)),
          str(os.listdir(tmp)))

    # 4. f/2.8 不应被当作 f/2 触发“已经开大仍不虚”
    out = bokeh_feedback("夜里想背景虚化，f/2.8，快门 1/8，ISO 100，能拍吗？")
    check("f/2.8 不误触发 bokeh_feedback", out is None, str(out))

    # 5. 否定句不再反转
    v1 = appraise_text("不好")[0]
    v2 = appraise_text("没问题")[0]
    check("否定句情感方向正确", v1 < 0 and v2 > 0, "不好=%.2f 没问题=%.2f" % (v1, v2))

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
