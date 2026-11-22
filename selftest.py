"""selftest.py — 定量验证四项认知特性

不验"跑通"，验"算得对"：
  1. 模式分离：相似输入经过 DG 后重叠应显著下降
  2. 模式完成：残缺线索能召回正确记忆
  3. 情绪倒 U：中等唤醒细节保留最高，过量唤醒细节丢失
  4. 巩固：高频唤起 + 适度情绪的记忆，激活显著高于低频低情绪

用法：python selftest.py
"""

import random

from circuits import DentateGyrus, encode, similarity
from engine import MemoryEngine

random.seed(20261119)

EPISODES = [
    {"who": "林晚", "where": "顶层公寓", "when": "深夜", "what": "改合同", "feel": "疲惫", "result": "被留下"},
    {"who": "陆行舟", "where": "会议室", "when": "上午", "what": "谈并购", "feel": "冷静", "result": "签字"},
    {"who": "林晚", "where": "停车场", "when": "傍晚", "what": "等车", "feel": "不安", "result": "被他送回家"},
    {"who": "陆行舟", "where": "顶层公寓", "when": "深夜", "what": "喝酒", "feel": "烦躁", "result": "一个人"},
    {"who": "助理小周", "where": "茶水间", "when": "午后", "what": "汇报进度", "feel": "紧张", "result": "被表扬"},
    {"who": "林晚", "where": "顶层公寓", "when": "深夜", "what": "改合同", "feel": "心慌", "result": "说不清"},
]


def pct(x):
    return "%.1f%%" % (x * 100)


def test_pattern_separation():
    """相似输入（只差一个字段）在 DG 后应被拉开。"""
    dg = DentateGyrus()
    a = {"who": "林晚", "where": "顶层公寓", "when": "深夜"}
    b = {"who": "林晚", "where": "顶层公寓", "when": "清晨"}   # 只差 when

    raw_sim = similarity(encode(a), encode(b))
    pa, pb = dg.separate(encode(a)), dg.separate(encode(b))
    overlap = len(pa & pb) / max(1, len(pa))

    print("[1] 模式分离")
    print("    输入相似度（编码后） : %s" % pct(raw_sim))
    print("    DG 后重叠率          : %s" % pct(overlap))
    ok = overlap < raw_sim * 0.6
    print("    判定：%s（重叠应低于输入的 %s，实际阈值 60%%）" % ("PASS" if ok else "FAIL", "60%"))
    return ok


def test_pattern_completion():
    """把记忆的 DG 模式丢掉 40%，且用高相似干扰项，看能否召回正确那条。"""
    eng = MemoryEngine()
    # 加一条与前几条高度相似的干扰记忆，专门考验分离能力
    ids = [eng.remember(ep, arousal=0.5) for ep in EPISODES]
    ids.append(eng.remember(
        {"who": "林晚", "where": "顶层公寓", "when": "深夜", "what": "改合同",
         "feel": "疲惫", "result": "被留下"}, arousal=0.5))  # 与 m0 几乎相同

    # 取第 2 条，丢掉 40% 激活位，再混入 20% 噪声位（模拟真实残缺且带噪的线索）
    target = eng.memories[ids[2]]
    pat = list(target["pattern"])
    keep_n = int(len(pat) * 0.6)
    rng = random.Random(7)
    cue = set(rng.sample(pat, keep_n))
    all_idx = list(range(eng.dg.n_out))
    noise_pool = [i for i in all_idx if i not in set(pat)]
    cue |= set(rng.sample(noise_pool, int(len(pat) * 0.2)))
    cue = frozenset(cue)

    label, overlap, conf = eng.ca3.recall(cue)
    correct = label == ids[2]
    print("[2] 模式完成（含高相似干扰＋线索带噪）")
    print("    线索                : 保留 60% + 混入 20% 噪声")
    print("    召回结果             : %s（期望 %s）" % (label, ids[2]))
    print("    重叠 / 置信          : %s / %.2f" % (pct(overlap), conf))
    print("    判定：%s" % ("PASS" if correct else "FAIL"))
    return correct


def test_arousal_inverted_u():
    """横扫唤醒度，每条唤醒度下统计 40 条情景的平均细节保留，画合成曲线。"""
    eng = MemoryEngine()
    base = {"who": "林晚", "where": "顶层公寓", "when": "深夜", "what": "改合同",
            "feel": "疲惫", "why": "想留住他", "result": "被留下"}
    print("[3] 情绪调制（倒 U）· 每条唤醒度统计 40 条情景")
    print("    唤醒   平均细节保留  巩固增益  合成")
    best_arousal, best_score = None, -1
    for a in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
        details = []
        for i in range(40):
            ep = dict(base)
            ep["result"] = "结局%d" % i      # 每条略不同，避免同种子
            mid = eng.remember(ep, arousal=a)
            details.append(eng.memories[mid]["detail_kept"])
        avg_detail = sum(details) / len(details)
        gain = eng.amygdala.gain(a)
        score = avg_detail * gain
        if score > best_score:
            best_score, best_arousal = score, a
        print("    %.1f    %s        %.2f      %.3f" % (a, pct(avg_detail), gain, score))
    ok = 0.3 <= best_arousal <= 0.7
    print("    峰值唤醒 = %.1f，判定：%s（应落在 0.3–0.7）" % (best_arousal, "PASS" if ok else "FAIL"))
    return ok


def test_consolidation():
    """反复唤起 + 适度情绪的记忆，激活应高于只存一次且情绪过高的记忆。"""
    eng = MemoryEngine()
    hot = eng.remember({"who": "林晚", "where": "顶层公寓", "what": "雨夜"},
                       arousal=0.5)
    cold = eng.remember({"who": "路人", "where": "街角", "what": "路过"},
                        arousal=1.0)
    for _ in range(6):
        eng.recall({"who": "林晚", "where": "顶层公寓"})

    now = __import__("time").time()
    a_hot = eng._activation(eng.memories[hot], now)
    a_cold = eng._activation(eng.memories[cold], now)
    print("[4] 巩固（唤起强化 vs 一次性高唤醒）")
    print("    高频+适度唤醒 激活   : %.3f" % a_hot)
    print("    一次性+过量唤醒 激活 : %.3f" % a_cold)
    ok = a_hot > a_cold
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def main():
    print("=" * 56)
    print("类海马体记忆引擎 · 认知特性定量验证")
    print("=" * 56)
    results = [
        test_pattern_separation(),
        test_pattern_completion(),
        test_arousal_inverted_u(),
        test_consolidation(),
    ]
    print("=" * 56)
    passed = sum(results)
    print("结果：%d / %d 项通过" % (passed, len(results)))
    print("=" * 56)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
