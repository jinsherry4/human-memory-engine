# -*- coding: utf-8 -*-
"""test_practice_engine.py — 曝光/显影/模糊/虚化的确定性结算。"""
import sys

import practice_engine as P

PASS = []


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%d] %s" % (len(PASS), name))
    if detail:
        print("    " + detail)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))


def main():
    t = "阴天下午，ISO 100，手持，光圈 f/8，快门 1/15，能拍吗？"
    out = P.exposure_plan(t, age=20.5)
    check("阴天 f/8 1/15 → f/4", out and "f/4" in out, str(out))
    check("18.7 岁前不算曝光", P.exposure_plan(t, age=17.0) is None)

    out = P.darkroom_plan("药温比标准高了2度，时间不变，底片会偏厚还是偏薄？", age=20.5)
    check("药温高 → 偏厚", out and "偏厚" in out, str(out))
    out = P.darkroom_plan("这卷底片冲出来太薄，是不是显影温度设高了？", age=20.5)
    check("是不是温度高 → 不抢答偏厚", out is None, str(out))

    out = P.blur_diagnosis("我按你说的把快门提到 1/60 了，照片还是糊，下一步查什么？", age=20.5)
    check("1/60 仍糊 → 查对焦", out and "对焦" in out, str(out))

    out = P.bokeh_feedback("夜里想背景虚化，f/2.8，快门 1/8，ISO 100，能拍吗？", age=20.5)
    check("f/2.8 不被当成 f/2 触发反馈", out is None, str(out))
    out = P.bokeh_feedback("我开到 f/2 了，也让他离背景远了，还是太清楚。", age=20.5)
    check("f/2 仍太清楚 → 查焦距", out and "长焦" in out, str(out))

    out = P.constraint_check("夜里只有一盏灯，ISO 100，手持，想拍清楚，能拍吗？", age=20.5)
    check("ISO100 夜里手持 → 拍不了", out and "拍不了" in out, str(out))

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
