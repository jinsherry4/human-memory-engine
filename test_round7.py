# -*- coding: utf-8 -*-
"""test_round7.py — 第七轮论文增量的落地验证

覆盖 HUMAN_LIKE_MIND_METHOD.md §18 的 6 条可落地项：
  §18.1 再巩固两层：单次提取只临时刷新，重复/高效价才长期加固
  §18.2 回放分时：近期痕迹与已巩固旧痕迹分批
  §18.3 精度边界：低精度不套用 salience = precision × PE 的乘法式
  §18.4 元认知硬边界：d' ≤ 1 时 efficiency 报 null
  §18.5 change-of-mind：弃答不是终局，新线索可使置信回升
  §18.6 自动化 ↔ 迁移范围：自动化上升则迁移范围不增

这些断言只检验"行为有没有真的变"，不检验分数好不好看。
"""

import os
import sys
import tempfile

from affect import Affect
from affective_mind import MetaMind, Workspace, MIN_DPRIME_FOR_RATIO
from human_memory import HumanMemory, DURABLE_VALENCE
from procedural_memory import ProceduralMemory
from self_engine import SelfEngine

PASS = []
T0 = 1_000_000.0
H = 3600.0
D = 86400.0


def check(name, ok, detail=""):
    PASS.append(bool(ok))
    print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    if detail:
        print("    " + detail)


def main():
    tmp = tempfile.mkdtemp()

    # ---------- §18.1 再巩固两层 ----------
    h = HumanMemory(os.path.join(tmp, "r7_1.json"), affect=Affect())
    cue = {"who": "外公", "where": "天台", "what": "教我对焦"}
    mid = h.remember(dict(cue), arousal=0.4, valence=0.0, now=T0)
    ss0 = h.ss(h.memories[mid])
    r1 = h.recall(dict(cue), now=T0 + H)
    ss1 = h.ss(h.memories[mid])
    r2 = h.recall(dict(cue), now=T0 + 2 * H)
    ss2 = h.ss(h.memories[mid])
    layer1 = r1["results"][0]["reinforce_layer"]
    layer2 = r2["results"][0]["reinforce_layer"]
    gain1 = ss1 - ss0
    check("§18.1-a 中性记忆首次提取只给 labile_only，SS 增量受限",
          r1["best"] == mid and layer1 == "labile_only" and 0 < gain1 < 0.20,
          "首次 layer=%s SS %.3f→%.3f（+%.4f）" % (layer1, ss0, ss1, gain1))
    check("§18.1-b 同一记忆第二次提取达到重复性门槛，转为 durable",
          r2["best"] == mid and layer2 == "durable" and ss2 > ss1,
          "第二次 layer=%s SS %.3f→%.3f" % (layer2, ss1, ss2))

    # 高效价记忆不必等第二次，一次就按满额加固
    mid_v = h.remember({"who": "自己", "where": "展厅", "what": "个展开幕"},
                       arousal=0.4, valence=0.8, now=T0)
    rv = h.recall({"who": "自己", "where": "展厅", "what": "个展开幕"}, now=T0 + H)
    check("§18.1-c 高|效价|记忆首次即 durable（情绪性记忆走另一条门槛）",
          rv["best"] == mid_v and rv["results"][0]["reinforce_layer"] == "durable"
          and bool(h.memories[mid_v]["durable"]),
          "layer=%s durable=%s" % (rv["results"][0]["reinforce_layer"],
                                   h.memories[mid_v]["durable"]))

    # ---------- §18.2 回放分时 ----------
    hs = HumanMemory(os.path.join(tmp, "r7_2.json"), affect=Affect())
    now = T0 + 3 * D
    for i in range(2):   # 2 小时前刚发生
        hs.remember({"who": "自己", "where": "暗房", "what": "刚冲的卷%d" % i},
                    arousal=0.6, now=now - 2 * H)
    for i in range(2):   # 3 天前，已经过一轮巩固
        hs.remember({"who": "外公", "where": "天台", "what": "旧的对焦课%d" % i},
                    arousal=0.6, now=T0)
    out = hs.consolidate(now=now)
    batches = out.get("batches") or {}
    tags = {t.get("batch") for m in hs.memories.values()
            for t in (m.get("traces") or []) if t.get("kind") == "gist_replay"}
    check("§18.2 近期与旧痕迹分别成批回放，不混在同一批里",
          batches.get("recent", 0) >= 1 and batches.get("old", 0) >= 1
          and tags == {"recent", "old"},
          "batches=%s 回放批次标记=%s 总回放=%d"
          % (batches, sorted(t for t in tags if t), out.get("replayed", 0)))

    # ---------- §18.4 元认知硬边界 ----------
    mid_d = ([{"conf": 0.9, "correct": True}] * 31
             + [{"conf": 0.2, "correct": False}] * 19)          # 62% → d'≈0.61
    hi_d = ([{"conf": 0.9, "correct": True}] * 75
            + [{"conf": 0.2, "correct": False}] * 25)           # 75% → d'≈1.35
    m_low = MetaMind.meta_dprime(mid_d)
    m_high = MetaMind.meta_dprime(hi_d)
    check("§18.4 d'≤1 时只报 meta-d'，efficiency 报 null",
          MIN_DPRIME_FOR_RATIO == 1.0 and m_low["d_prime"] < 1.0
          and m_low["ratio_unstable"] and m_low["efficiency"] is None,
          "低组 d'=%.3f efficiency=%s ratio_unstable=%s"
          % (m_low["d_prime"], m_low["efficiency"], m_low["ratio_unstable"]))
    check("§18.4 d'>1 时 efficiency 正常给出",
          m_high["d_prime"] > 1.0 and not m_high["ratio_unstable"]
          and m_high["efficiency"] is not None and m_high["efficiency"] > 0,
          "高组 d'=%.3f meta-d'=%.3f efficiency=%s"
          % (m_high["d_prime"], m_high["meta_d_prime"], m_high["efficiency"]))

    # ---------- §18.3 低精度不套乘法 ----------
    w_hi = Workspace()
    a_hi = w_hi.push("高精度项", salience=0.8, precision=0.9, now=T0)
    w_lo = Workspace()
    a_lo = w_lo.push("低精度项", salience=0.8, precision=0.1, now=T0)
    w_old = Workspace()
    a_old = w_old.push("旧路径", salience=0.8, now=T0)
    naive = 0.8 * 0.1   # 若硬套 precision×PE 会得到 0.08
    check("§18.3 低精度下显著度不随精度线性塌缩（反贝叶斯边界）",
          a_lo["salience"] > naive and a_lo.get("low_precision") is True
          and a_hi["salience"] < a_old["salience"],
          "低精度 salience=%.3f（乘法式应为 %.3f） 高精度=%.3f 不传精度=%.3f"
          % (a_lo["salience"], naive, a_hi["salience"], a_old["salience"]))

    # ---------- §18.5 change-of-mind ----------
    mm = MetaMind()
    r0 = mm.evaluate({"best": None, "results": []})
    r1 = mm.evaluate({"best": "m0",
                      "results": [{"score": 0.9, "text": 0.9, "fidelity": 1.0,
                                   "source": "experienced"}]},
                     cue={"who": "外公"}, prev=r0)
    check("§18.5 弃答后来了新线索，置信回升且标记 reopened",
          r0["abstain"] and (not r1["abstain"]) and r1["reopened"]
          and r1["confidence"] > r0["confidence"],
          "首次 abstain=%s conf=%.3f；复评 abstain=%s conf=%.3f reopened=%s"
          % (r0["abstain"], r0["confidence"], r1["abstain"], r1["confidence"],
             r1["reopened"]))

    # ---------- §18.6 自动化 ↔ 迁移范围 ----------
    pm = ProceduralMemory()
    pid = pm.learn("手动对焦", ["测光", "取景", "转对焦环", "确认合焦"])
    autos, scopes = [], []
    for _ in range(6):
        pm.run(pid, True)
        autos.append(pm.automatization(pid))
        scopes.append(pm.transfer_scope(pid))
    mono_auto = all(autos[i] <= autos[i + 1] + 1e-9 for i in range(len(autos) - 1))
    mono_scope = all(scopes[i] >= scopes[i + 1] - 1e-9 for i in range(len(scopes) - 1))
    check("§18.6 纯成功序列上自动化单调不减、迁移范围单调不增",
          mono_auto and mono_scope and autos[-1] > autos[0]
          and scopes[-1] < scopes[0] and 0.0 < scopes[-1] <= 1.0,
          "automation=%s transfer_scope=%s" % (autos, scopes))

    # 解编译后自动化应回落（失败真的削弱联结表征）
    pm.run(pid, False)
    pm.run(pid, False)
    check("§18.6 连续失败解编译后自动化回落、迁移范围回升",
          pm.automatization(pid) < autos[-1]
          and pm.transfer_scope(pid) > scopes[-1],
          "失败后 automation=%.3f（原 %.3f） transfer_scope=%.3f（原 %.3f）"
          % (pm.automatization(pid), autos[-1],
             pm.transfer_scope(pid), scopes[-1]))

    # ---------- §18.1 情境扩散层 ----------
    hx = HumanMemory(os.path.join(tmp, "r7_3.json"), affect=Affect())
    tgt = hx.remember({"who": "外公", "where": "天台", "when": "傍晚",
                       "what": "教我对焦"}, arousal=0.4, now=T0)
    sib = hx.remember({"who": "外公", "where": "天台", "when": "傍晚",
                       "what": "收拾三脚架"}, arousal=0.4, now=T0 + 60)
    far = hx.remember({"who": "室友", "where": "宿舍", "when": "冬天",
                       "what": "煮泡面"}, arousal=0.4, now=T0 + 120)
    ss_sib0, ss_far0 = hx.ss(hx.memories[sib]), hx.ss(hx.memories[far])
    rr = hx.recall({"who": "外公", "where": "天台", "when": "傍晚", "what": "教我对焦"},
                   now=T0 + H)
    check("§18.1-d 同情境外围记忆被一起强化，异情境不受影响",
          rr["best"] == tgt and rr.get("spread") == [sib]
          and hx.ss(hx.memories[sib]) > ss_sib0
          and abs(hx.ss(hx.memories[far]) - ss_far0) < 1e-9,
          "spread=%s 同情境 SS %.3f→%.3f，异情境 SS %.3f→%.3f"
          % (rr.get("spread"), ss_sib0, hx.ss(hx.memories[sib]),
             ss_far0, hx.ss(hx.memories[far])))
    check("§18.1-e 扩散只给稳定度、不给改写权（外围 labile 窗口仍关闭）",
          hx.memories[sib]["labile_until"] == 0.0
          and any(t.get("kind") == "context_spread"
                  for t in hx.memories[sib]["traces"]),
          "sib labile_until=%.0f，spread 痕迹=%d"
          % (hx.memories[sib]["labile_until"],
             sum(1 for t in hx.memories[sib]["traces"]
                 if t.get("kind") == "context_spread")))
    # 锚必须取自 raw：模拟压缩把 where/when 丢光，锚仍应完整
    mm = dict(hx.memories[tgt])
    mm["episode"] = {"who": "外公"}
    anchors = HumanMemory._context_anchors(mm)
    check("§18.1-f 情境锚取自 raw full_episode，不依赖压缩后的 episode",
          set(anchors) == {"who", "where", "when"},
          "压缩后 episode 只剩 who，锚仍为 %s" % sorted(anchors))

    # ---------- §18.5 四系统关系模型 ----------
    e = SelfEngine()
    for i, v in enumerate((-0.6, 0.2, 0.3)):
        e.interact("爸爸", True, now=T0 + i * 10, valence=v,
                   episode={"what": "教我第%d次" % i}, outcome="拍清楚了")
    for i in range(3):
        e.interact("妈妈", True, now=T0 + i * 10, valence=0.6)
    p_dad = e.relationship_profile("爸爸")
    p_mom = e.relationship_profile("妈妈")
    check("§18.5-a 四套系统各自记账：情景条数、工具性成功率、语义概括分开",
          p_dad["episodic_n"] == 3 and p_dad["instrumental"]["successes"] == 3
          and p_dad["semantic"].get("role") == "reliable",
          "episodic=%d successes=%d role=%s"
          % (p_dad["episodic_n"], p_dad["instrumental"]["successes"],
             p_dad["semantic"].get("role")))
    check("§18.5-b Pavlovian 联结被首个负性事件拉低，没被后续正性立刻抹平",
          p_dad["pavlovian"]["valence"] < p_mom["pavlovian"]["valence"],
          "爸爸 pavlovian=%.3f，妈妈=%.3f"
          % (p_dad["pavlovian"]["valence"], p_mom["pavlovian"]["valence"]))
    e.interact("路人", True)
    p_one = e.relationship_profile("路人")
    check("§18.5-c 语义概括是慢更新：单次互动不立「可靠」标签",
          "role" not in p_one["semantic"] and p_one["instrumental"]["successes"] == 1,
          "单次后 semantic=%s" % p_one["semantic"])
    e.relationships["旧朋友"] = {"trust": 0.72, "interactions": 5}
    p_old = e.relationship_profile("旧朋友")
    check("§18.5-d 旧格式（只有 trust）升级后历史不丢",
          p_old["instrumental"]["utility"] == 0.72 and p_old["trust"] == 0.72
          and p_old["episodic_n"] == 0,
          "旧 trust 0.72 → utility=%.2f，episodic=%d"
          % (p_old["instrumental"]["utility"], p_old["episodic_n"]))

    # 旧 self_store.json 的加载路径也要能升级，不能只在内存里补
    import json as _json
    sp = os.path.join(tmp, "r7_self.json")
    with open(sp, "w", encoding="utf-8") as f:
        _json.dump({"relationships": {"老同事": {"trust": 0.66, "interactions": 9}},
                    "self_model": {}, "working_self": {}, "timeline": []},
                   f, ensure_ascii=False)
    e2 = SelfEngine(self_store=sp).load_self()
    r_old = e2.relationships["老同事"]
    check("§18.5-e 从旧 self_store 文件加载时关系自动补成四账",
          "pavlovian" in r_old and "episodic" in r_old
          and r_old["instrumental"]["utility"] == 0.66
          and r_old.get("trust") == 0.66,
          "加载后四账齐全=%s utility=%.2f trust=%.2f"
          % ({"pavlovian", "episodic", "instrumental", "semantic"} <= set(r_old),
             r_old["instrumental"]["utility"], r_old.get("trust", -1)))

    print("=" * 60)
    print("结果：%d / %d 项通过" % (sum(PASS), len(PASS)))
    return 0 if all(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
