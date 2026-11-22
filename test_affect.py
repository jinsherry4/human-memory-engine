"""test_affect.py — 情感状态与感知层的定量验证

验的是动力学，不是"能跑"：
  1. 回归：足够时间后回到基线（情绪不会永远卡住）
  2. 惯性差异：兴奋（arousal）比心情（valence）消退快
  3. 饱和：反复冲击不越界
  4. 语气映射：不同状态给出可区分的表达参数
  5. 文本感知：正负与急切能被区分
  6. 持久化：存盘再读，状态不漂移

用法：python test_affect.py
"""

import math
import os
import time

from affect import BASELINE, Affect
from perceive import appraise_changes, appraise_gap, appraise_text


def test_regression():
    a = Affect()
    a.appraise(valence=1.0, weight=1.0)
    start = a.state["valence"]
    a.tick(now=a.updated + 18 * 3600)   # 3 倍时间常数
    end = a.state["valence"]
    ok = abs(end - BASELINE["valence"]) < 0.1
    print("[1] 回归基线")
    print("    起点 %.3f → 18 小时后 %.3f（基线 %.2f）" % (start, end, BASELINE["valence"]))
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_inertia_difference():
    a = Affect()
    a.appraise(valence=1.0, arousal=1.0, weight=1.0)
    v0, ar0 = a.state["valence"], a.state["arousal"]
    a.tick(now=a.updated + 2 * 3600)
    v1, ar1 = a.state["valence"], a.state["arousal"]
    # 回归完成度：回到基线的比例
    v_done = (v0 - v1) / max(1e-9, v0 - BASELINE["valence"])
    ar_done = (ar0 - ar1) / max(1e-9, ar0 - BASELINE["arousal"])
    ok = ar_done > v_done
    print("[2] 惯性差异（唤醒退得比心情快）")
    print("    2 小时后：唤醒回归 %.0f%%，心情回归 %.0f%%" % (ar_done * 100, v_done * 100))
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_saturation():
    a = Affect()
    for _ in range(20):
        a.appraise(valence=0.5, arousal=0.5, dominance=0.5, weight=1.0)
    v, ar, d = a.state["valence"], a.state["arousal"], a.state["dominance"]
    ok = -1.0 <= v <= 1.0 and 0.0 <= ar <= 1.0 and -1.0 <= d <= 1.0
    print("[3] 饱和")
    print("    连续 20 次冲击后：v=%.2f a=%.2f d=%.2f" % (v, ar, d))
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_tone_mapping():
    bright = Affect()
    bright.appraise(valence=0.8, arousal=0.7, dominance=0.6, weight=1.0)
    low = Affect()
    low.appraise(valence=-0.8, arousal=-0.3, dominance=-0.5, weight=1.0)

    tb, tl = bright.tone(), low.tone()
    ok = (tb["verbosity"] > tl["verbosity"]
          and tb["warmth"] > tl["warmth"]
          and tb["assertiveness"] > tl["assertiveness"])
    print("[4] 语气映射")
    print("    轻快态：%s verbosity=%.2f warmth=%.2f assert=%.2f"
          % (tb["mood"], tb["verbosity"], tb["warmth"], tb["assertiveness"]))
    print("    低落态：%s verbosity=%.2f warmth=%.2f assert=%.2f"
          % (tl["mood"], tl["verbosity"], tl["warmth"], tl["assertiveness"]))
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_text_perception():
    pos = appraise_text("这个方案成了，不错")
    neg = appraise_text("崩了，失败了，问题很大")
    urg = appraise_text("马上，赶紧，现在就要")
    ok = pos[0] > 0 and neg[0] < 0 and urg[1] > 0
    print("[5] 文本感知")
    print("    正面句 valence=%.2f（应 > 0）" % pos[0])
    print("    负面句 valence=%.2f（应 < 0）" % neg[0])
    print("    急切句 arousal=%.2f（应 > 0）" % urg[1])
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_persistence():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_affect_test.json")
    a = Affect(path)
    a.appraise(valence=0.6, arousal=0.5, weight=1.0)
    a.save()
    before = dict(a.state)
    b = Affect(path)
    after = dict(b.state)
    ok = all(abs(before[k] - after[k]) < 0.02 for k in before)
    try:
        os.remove(path)
    except OSError:
        pass
    print("[6] 持久化")
    print("    存盘前 v=%.3f a=%.3f d=%.3f" % (before["valence"], before["arousal"], before["dominance"]))
    print("    读回后 v=%.3f a=%.3f d=%.3f" % (after["valence"], after["arousal"], after["dominance"]))
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_recall_bias():
    """情绪一致性：同向加权、反向抑制，**中性记忆不受偏置**。

    旧断言只查"同向>1、反向<1"，把"中性心情下中性记忆恒被放大到 1.27"
    这个缺陷当成了正确行为。这里改为查机制本身：中性必须≈1。
    """
    a = Affect()
    a.appraise(valence=1.0, weight=1.0)   # 心情拉满
    same = a.recall_bias(1.0)
    neutral = a.recall_bias(0.0)
    opposite = a.recall_bias(-1.0)
    b = Affect()
    b.state["valence"] = 0.0              # 中性心情
    n_pos, n_neg = b.recall_bias(1.0), b.recall_bias(-1.0)
    ok = (same > 1.0 and opposite < 1.0
          and abs(neutral - 1.0) < 0.02
          and abs(n_pos - 1.0) < 0.02 and abs(n_neg - 1.0) < 0.02)
    print("[7] 情绪一致性偏差")
    print("    高涨：同向 × %.2f  中性 × %.2f  反向 × %.2f" % (same, neutral, opposite))
    print("    中性心情：正性 × %.2f  负性 × %.2f（都应≈1.00）" % (n_pos, n_neg))
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def main():
    print("=" * 56)
    print("情感状态与感知层验证")
    print("=" * 56)
    results = [
        test_regression(),
        test_inertia_difference(),
        test_saturation(),
        test_tone_mapping(),
        test_text_perception(),
        test_persistence(),
        test_recall_bias(),
    ]
    print("=" * 56)
    print("结果：%d / %d 项通过" % (sum(results), len(results)))
    print("=" * 56)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
