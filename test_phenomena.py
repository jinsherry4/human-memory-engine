# -*- coding: utf-8 -*-
"""test_phenomena.py — 行为验收：方法文档 §5.6 的典型现象能不能自发出现

这不是"教一条规则再断言它"的同义反复测试。每题只给**输入条件**，
断言的是**应当涌现的现象**，判据全部来自 HUMAN_LIKE_MIND_METHOD.md：
  §5.6 六个典型现象
  §5.7 Bjork 双强度四条动力学
  §5.3 提取练习调度 / NMPH / 潜在原因推断
  §5.8 再巩固窗口 / DRM 边界
  §7.2 ABC 与 Bisby
  §7.3 反刍检测
  §8   灵光（Aha ≠ 正确）
  §3.4 程序生疏与 savings

用法：python test_phenomena.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from affect import Affect
from affective_mind import Regulation, Workspace
from human_memory import HumanMemory
from insight_engine import InsightEngine
from procedural_memory import ProceduralMemory
from self_engine import SelfEngine
from semantic_graph import SemanticGraph

H = 3600.0
RESULTS = []


def check(name, ok, evidence):
    RESULTS.append((name, bool(ok), evidence))
    print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    print("      %s" % evidence)


def hm(tmp, name):
    return HumanMemory(os.path.join(tmp, name + ".json"), affect=Affect())


def main():
    tmp = tempfile.mkdtemp()
    T0 = 1_700_000_000.0

    # ---------- §5.6-1 只记大意忘原话 ----------
    h = hm(tmp, "ph1")
    for i in range(6):
        h.remember({"who": "妈妈", "where": "厨房", "when": "早上", "what": "做早饭",
                    "feel": "平常", "why": "每天", "result": "吃完上学"},
                   arousal=0.3, now=T0 + i * H)
    m = h.memories["m5"]
    check("§5.6-1 冗余日常被压缩成梗概，who/what 仍在",
          m["detail_kept"] < 0.8 and m["episode"].get("who") and m["episode"].get("what"),
          "第 6 次同样的早饭 detail_kept=%.2f，保留字段=%s"
          % (m["detail_kept"], sorted(m["episode"])))

    # ---------- §5.6-2 多年记得某瞬间 ----------
    h = hm(tmp, "ph2")
    big = h.remember({"who": "外公", "where": "老屋", "when": "三月", "what": "把相机给我",
                      "feel": "郑重", "why": "他认定我", "result": "我接过来"},
                     arousal=0.5, now=T0)
    h.memories[big]["self_defining"] = True
    for k in range(1, 7):
        h.rehearse(big, True, now=T0 + k * 200 * H)
    ordinary = h.remember({"who": "同学", "where": "教室", "what": "借橡皮"},
                          arousal=0.3, now=T0)
    far = T0 + 24 * 365 * H
    rs_big, rs_ord = h.rs(h.memories[big], far), h.rs(h.memories[ordinary], far)
    check("§5.6-2 自我定义 + 反复提取 → 一年后仍可及，普通事件已淡出",
          rs_big > rs_ord * 5 and rs_big > 0.10,
          "一年后 RS：自我定义=%.4f 普通=%.4f；SS=%.2f"
          % (rs_big, rs_ord, h.ss(h.memories[big])))

    # ---------- §5.6-3 记得却想不起（latent，强线索可恢复）----------
    h = hm(tmp, "ph3")
    mid = h.remember({"who": "邮递员", "where": "楼下", "when": "六月", "what": "送来通知书",
                      "feel": "手抖", "why": "等很久", "result": "签收"},
                     arousal=0.4, now=T0)
    later = T0 + 90 * 24 * H
    weak = h.recall({"what": "通知书"}, now=later, reinforce=False)
    strong = h.recall({"who": "邮递员", "where": "楼下", "when": "六月", "what": "送来通知书"},
                      now=later, reinforce=False)
    r0 = weak["results"][0] if weak["results"] else {}
    check("§5.6-3 availability 高但 accessibility 低；强线索能唤回",
          r0.get("availability") and r0.get("latent") and strong["best"] == mid,
          "弱线索 best=%s latent=%s availability=%s；强线索 best=%s"
          % (weak["best"], r0.get("latent"), r0.get("availability"), strong["best"]))

    # ---------- §5.6-4 记错却自信：confidence 与 fidelity 脱钩 ----------
    h = hm(tmp, "ph4")
    mid = h.remember({"who": "室友", "where": "宿舍", "when": "深夜", "what": "吵架",
                      "feel": "委屈", "why": "误会", "result": "冷战"},
                     arousal=0.95, now=T0)
    for k in range(4):
        h.rehearse(mid, False, correction=None, now=T0 + (k + 1) * 50 * H)
    r = h.recall({"who": "室友", "where": "宿舍", "what": "吵架"}, now=T0 + 300 * H)
    top = r["results"][0]
    check("§5.6-4 无反馈的错误提取：可及性/置信不降，保真度下降",
          top["fidelity"] < 0.9 and top["rs"] > 0.1,
          "fidelity=%.2f（初始 %.2f） rs=%.3f traces=%d"
          % (top["fidelity"], h.memories[mid]["detail_kept"], top["rs"], top["traces"]))

    # ---------- §5.6-5 创伤：item 保住、relational 受损 ----------
    h = hm(tmp, "ph5")
    mid = h.remember({"who": "自己", "where": "考场外", "when": "冬天", "what": "落榜",
                      "feel": "崩塌", "why": "差三分", "result": "雪里坐很久"},
                     arousal=1.0, now=T0)
    ep = h.memories[mid]["episode"]
    rel_lost = [k for k in ("when", "where", "result") if k not in ep]
    check("§5.6-5 高唤醒：item(who/what) 保住，relational 先丢",
          ep.get("who") and ep.get("what") and len(rel_lost) >= 1,
          "保留=%s 丢掉的 relational=%s arousal_loss=%.2f"
          % (sorted(ep), rel_lost, h.memories[mid]["arousal_loss"]))

    # ---------- §5.6-6 技能生疏但节省仍在 ----------
    pm = ProceduralMemory(os.path.join(tmp, "ph6.json"))
    pid = pm.learn("暗房冲洗", ["显影", "停显", "定影", "水洗"], now=T0)
    for k in range(4):
        pm.run(pid, True, now=T0 + k * H)
    cost_fresh = pm.cost(pid, now=T0 + 4 * H)
    rust_far = pm.rust(pm.procs[pid], now=T0 + 24 * 90 * H)
    cost_far = pm.cost(pid, now=T0 + 24 * 90 * H)
    sav = pm.savings(pid)
    check("§5.6-6 久不练：可及性降、成本升，但 savings 仍在",
          rust_far < 0.95 and cost_far > cost_fresh and sav > 0,
          "rust 新鲜=1.0 久置=%.3f；cost %.3f→%.3f；savings=%.3f；steps %d→%d"
          % (rust_far, cost_fresh, cost_far, sav,
             len(pm.procs[pid]["steps_explicit"]), len(pm.procs[pid]["steps"])))

    # ---------- §5.7 SS 只增 ----------
    h = hm(tmp, "ph7")
    mid = h.remember({"who": "老师", "where": "暗房", "what": "教冲洗"}, arousal=0.5, now=T0)
    ss_seq = [h.ss(h.memories[mid])]
    for k in range(1, 6):
        h.rehearse(mid, True, now=T0 + k * 100 * H)
        ss_seq.append(h.ss(h.memories[mid]))
    check("§5.7-a SS 单调不减",
          all(b >= a for a, b in zip(ss_seq, ss_seq[1:])) and ss_seq[-1] > ss_seq[0],
          "SS 序列=%s" % [round(x, 3) for x in ss_seq])

    # ---------- §5.7 SS 延缓 RS 丢失 ----------
    h = hm(tmp, "ph8")
    lo = h.remember({"who": "甲", "where": "A", "what": "同一件事"}, arousal=0.5, now=T0)
    hi = h.remember({"who": "乙", "where": "B", "what": "同一件事"}, arousal=0.5, now=T0)
    h.memories[hi]["ss"] = 4.0
    t = T0 + 24 * 60 * H
    r_lo, r_hi = h.rs(h.memories[lo], t), h.rs(h.memories[hi], t)
    check("§5.7-b 同样时间不提取，高 SS 忘得更慢",
          r_hi > r_lo * 1.5,
          "60 天后 RS：低SS(%.2f)=%.4f 高SS(4.0)=%.4f"
          % (h.ss(h.memories[lo]), r_lo, r_hi))

    # ---------- §5.7 SS 增量随 RS 递减（desirable difficulty）----------
    h = hm(tmp, "ph9")
    a = h.remember({"who": "甲", "where": "A", "what": "背单词"}, arousal=0.5, now=T0)
    b = h.remember({"who": "乙", "where": "B", "what": "背单词"}, arousal=0.5, now=T0)
    g_easy = h._ss_gain(h.memories[a], T0 + 0.05 * H)      # 刚刚才想起，RS 很高
    g_hard = h._ss_gain(h.memories[b], T0 + 24 * 30 * H)   # 快忘了才想起，RS 很低
    check("§5.7-c 间隔久（RS 低）时提取的 SS 增益更大",
          g_hard > g_easy * 1.3,
          "即时提取增益=%.4f 隔 30 天提取增益=%.4f" % (g_easy, g_hard))

    # ---------- §5.3 5–7 次后趋平 ----------
    h = hm(tmp, "ph10")
    mid = h.remember({"who": "老师", "where": "教室", "what": "讲曝光"}, arousal=0.5, now=T0)
    gains = []
    for k in range(1, 11):
        before = h.ss(h.memories[mid])
        h.rehearse(mid, True, now=T0 + k * 200 * H)
        gains.append(h.ss(h.memories[mid]) - before)
    check("§5.3-a 提取练习收益递减，第 8 次后接近平台",
          gains[0] > gains[-1] and gains[-1] < gains[0] * 0.35,
          "逐次 SS 增益=%s" % [round(g, 4) for g in gains])

    # ---------- §5.3 无反馈错误提取不增 SS ----------
    h = hm(tmp, "ph11")
    mid = h.remember({"who": "同学", "where": "操场", "what": "跑步"}, arousal=0.5, now=T0)
    ss0 = h.ss(h.memories[mid])
    h.rehearse(mid, False, correction=None, now=T0 + 100 * H)
    ss1 = h.ss(h.memories[mid])
    fid1 = h.memories[mid]["fidelity"]
    h.rehearse(mid, False, correction={"what": "快走"}, now=T0 + 300 * H)
    fid2 = h.memories[mid]["fidelity"]
    check("§5.3-b 答错无纠正：SS 不增、保真降；给正确答案才修复",
          abs(ss1 - ss0) < 1e-9 and fid1 < 1.0 and fid2 > fid1,
          "SS %.3f→%.3f；fidelity 1.0→%.2f→（给纠正）%.2f" % (ss0, ss1, fid1, fid2))

    # ---------- §5.8 再巩固窗口 ----------
    h = hm(tmp, "ph12")
    mid = h.remember({"who": "爸爸", "where": "家", "what": "谈摄影", "why": "他担心"},
                     arousal=0.5, now=T0)
    h.recall({"who": "爸爸", "where": "家", "what": "谈摄影"}, now=T0 + H)
    inside, d1 = h.update_or_new({"who": "爸爸", "where": "家", "what": "谈摄影",
                                  "result": "他松口了"}, now=T0 + 2 * H)
    outside, d2 = h.update_or_new({"who": "爸爸", "where": "家", "what": "谈摄影",
                                   "result": "又吵了"}, now=T0 + 100 * H)
    check("§5.8 窗口内整合、窗口外新建（raw 不覆盖）",
          d1 == "integrate" and inside == mid and d2 in ("new", "differentiate") and outside != mid,
          "窗口内 decision=%s id=%s；窗口外 decision=%s id=%s；原始痕迹仍在=%s"
          % (d1, inside, d2, outside,
             h.memories[mid]["traces"][0]["kind"] == "original"))

    # ---------- §5.3 潜在原因推断 ----------
    h = hm(tmp, "ph13")
    h.remember({"who": "客户", "where": "影棚", "what": "退片", "why": "嫌贵"},
               arousal=0.5, now=T0)
    nid, dec = h.update_or_new({"who": "客户", "where": "影棚", "what": "退片",
                                "why": "拍糊了"}, now=T0 + H)
    check("§5.3-c why 变了 = 新原因 → 新建痕迹而不是覆盖",
          dec == "new" and nid != "m0",
          "decision=%s 新 id=%s" % (dec, nid))

    # ---------- §7.2 mood-congruent ----------
    e = SelfEngine(affect=Affect(), human_store=os.path.join(tmp, "ph14.json"))
    e.set_age(20.5)
    good = e.remember({"who": "自己", "where": "展厅", "what": "个展开幕"}, valence=0.8, now=T0)
    bad = e.remember({"who": "自己", "where": "考场", "what": "落榜通知"}, valence=-0.8, now=T0)
    orders = []
    for mood in (-0.8, 0.8):
        e.affect.state.update({"valence": mood, "arousal": 0.35, "dominance": 0.0})
        r = e.recall({"who": "自己"}, top_k=2, now=T0 + H, reinforce=False)
        orders.append([x["id"] for x in r["results"]])
    check("§7.2-a 心情低落先想起坏事，心情好先想起好事",
          orders[0][0] == bad and orders[1][0] == good,
          "低落序=%s 高涨序=%s（好=%s 坏=%s）" % (orders[0], orders[1], good, bad))

    # ---------- §7.2 ABC：高优先级不唤醒也保细节 ----------
    h = hm(tmp, "ph15")
    hi = h.remember({"who": "评委", "where": "答辩厅", "when": "下午", "what": "打分",
                     "feel": "平静", "why": "决定名次", "result": "第一"},
                    arousal=0.2, priority=1.0, now=T0)
    lo = h.remember({"who": "路人", "where": "走廊", "when": "下午", "what": "路过",
                     "feel": "平静", "why": "没事", "result": "走了"},
                    arousal=0.2, priority=0.0, now=T0 + H)
    check("§7.2-b 同样低唤醒，高优先级项保住更多细节",
          h.memories[hi]["detail_kept"] > h.memories[lo]["detail_kept"],
          "高优先级 detail=%.2f 低优先级 detail=%.2f（arousal 都是 0.2）"
          % (h.memories[hi]["detail_kept"], h.memories[lo]["detail_kept"]))

    # ---------- §7.3 反刍检测 ----------
    reg = Regulation()
    aff = Affect()
    aff.state["valence"] = -0.6
    fired = False
    for i in range(4):
        if reg.note_thought("我是不是根本不适合拍照", -0.6, True, now=T0 + i * 60):
            fired = True
    v_after = aff.state["valence"]
    reg.interrupt(aff, now=T0 + 400)
    check("§7.3 重复负面自我聚焦被判为反刍并触发打断",
          fired and reg.thoughts == [] and aff.state["valence"] > v_after,
          "检出反刍=%s；打断后 valence %.2f→%.2f；策略族=%s"
          % (fired, v_after, aff.state["valence"], "cognitive_change"))

    # ---------- §7.3 强度×可控性选策略 ----------
    reg2 = Regulation()
    hi_intensity = reg2.select(0.9, 0.2)["family"]
    lo_ctrl = reg2.select(0.3, 0.9)["family"]
    lo_unctrl = reg2.select(0.3, 0.1)["family"]
    check("§7.3-b 高强度→脱离；低强度可控→改情境；不可控→改认知",
          hi_intensity == "attentional_deployment" and lo_ctrl == "situation_modification"
          and lo_unctrl == "cognitive_change",
          "高=%.s 低可控=%s 低不可控=%s" % (hi_intensity, lo_ctrl, lo_unctrl))

    # ---------- §4 工作空间点火 ----------
    ws = Workspace()
    ws.push("毕业创作选题", salience=0.9, now=T0, arousal=0.5)
    ws.push("午饭吃什么", salience=0.2, now=T0, arousal=0.5)
    fire = ws.ignite(now=T0)
    check("§4 容量受限 + 偏向竞争 + 领先项点火广播",
          fire is not None and fire["content"] == "毕业创作选题" and len(ws.items) <= ws.capacity,
          "点火=%s；当前 WM 项数=%d" % (fire and fire["content"], len(ws.items)))

    # ---------- §8 灵光：僵局→松弛→远程→校验；Aha≠正确 ----------
    sg = SemanticGraph(os.path.join(tmp, "ph19.json"))
    sg.teach("雯", "knows:构图", "三分法把主体放交点", source="a", now=T0)
    sg.teach("雯", "knows:留白", "空处也是画面的一部分", source="a", now=T0)
    sg.teach("雯", "knows:呼吸", "画面需要透气的地方", source="b", now=T0)
    sg.teach("雯", "knows:节奏", "疏密交替产生节奏", source="b", now=T0)
    sg.teach("雯", "knows:负空间", "空的地方决定主体重量", source="c", now=T0)
    sg.teach("雯", "knows:静", "画面安静下来才有分量", source="c", now=T0)
    for a, b in (("f0", "f2"), ("f2", "f4"), ("f1", "f5"),
                 ("f4", "f5"), ("f0", "f3"), ("f3", "f5")):
        sg.edges.append({"from": a, "to": b, "w": 0.6, "kind": "remote"})
    ie = InsightEngine(sg, Workspace(), Affect(), seed=3)
    for _ in range(4):
        ie.note_attempt("毕业创作", success=False, now=T0)
    out = ie.maybe_insight({"key": "毕业创作", "goal": "留白",
                            "entities": ["构图", "留白", "呼吸"],
                            "constraints": [{"text": "必须三分法", "hard": False},
                                            {"text": "不能裁掉人", "hard": True}]}, now=T0)
    fired_ok = out is not None and out.get("status") == "insight_candidate"
    verified_no = None
    if fired_ok:
        rec = ie.verify(out, evidence_ok=False, now=T0 + H)
        verified_no = rec["status"] == "imagined" and "insight:毕业创作" not in str(sg.facts)
    check("§8 僵局后产生候选，未过独立校验只标 imagined，不写成事实",
          bool(fired_ok and verified_no),
          "候选=%s；校验不通过→status=%s；未污染事实库=%s"
          % (out and out.get("insight"), out and out.get("status"), verified_no))

    # ---------- §9 Conway 四层 + 身份核心跨事件归纳 ----------
    # 注意：这里刻意用**内容各不相同**的事件。真实自传体知识库里，
    # 一般事件的措辞几乎不会逐字重复；若按字符串相等分组，"≥2 次支持"
    # 这道闸门就永远不可能达标（本项曾因此把缺陷测成 PASS）。
    e = SelfEngine(selfmodel=True, self_store=os.path.join(tmp, "ph20.json"))
    e.set_age(20.5)
    e.add_self_event({"what": "决定要考摄影专业", "where": "教室", "feel": "笃定"},
                     self_defining=True, now=T0)
    e.add_self_event({"what": "爸爸说摄影没出路", "where": "家里", "feel": "委屈"},
                     self_defining=True, now=T0 + H)
    e.add_self_event({"what": "第一次进暗房", "where": "学校暗房", "feel": "屏息"},
                     self_defining=True, now=T0 + 2 * H)
    e.add_self_event({"what": "买了一支长焦", "where": "器材店"}, self_defining=False, now=T0)
    e.reflect(now=T0 + 3 * H)
    esk_n = len(e.self_model["esk"])
    lp_n = len(e.self_model["lifetime_periods"])
    core = e.self_model["identity_core"]
    check("§9 Conway 四层真写入 + 身份核心由不同事件归纳出共同主题",
          esk_n > 0 and lp_n > 0 and "摄影" in core
          and not any("暗房" in c for c in core)
          and not any("长焦" in c for c in core),
          "ESK=%d 条 lifetime_periods=%d 段 identity_core=%s" % (esk_n, lp_n, core))

    e1 = SelfEngine(selfmodel=True, self_store=os.path.join(tmp, "ph20b.json"))
    e1.set_age(20.5)
    e1.add_self_event({"what": "第一次进暗房", "where": "学校暗房", "feel": "屏息"},
                      self_defining=True, now=T0)
    e1.reflect(now=T0 + H)
    check("§9 单条自我定义事件不足以确立身份核心",
          e1.self_model["identity_core"] == [],
          "只有一条 self_defining 时 identity_core=%s" % e1.self_model["identity_core"])

    # 字面不重合但语义相关的两条事件：只有语义图给出联系时才归成同一身份主题
    e2 = SelfEngine(selfmodel=True, semantic=True,
                    self_store=os.path.join(tmp, "ph20c.json"),
                    semantic_store=os.path.join(tmp, "ph20c_sem.json"))
    e2.set_age(20.5)
    e2.add_self_event({"what": "洗出第一张照片", "feel": "震动"}, self_defining=True, now=T0)
    e2.add_self_event({"what": "她的第一场个展", "feel": "发光"}, self_defining=True, now=T0 + H)
    e2.reflect(now=T0 + 2 * H)
    before = list(e2.self_model["identity_core"])
    e2.sem.teach("照片", "属于", "摄影", now=T0)
    e2.sem.teach("个展", "属于", "摄影", now=T0)
    e2.reflect(now=T0 + 3 * H)
    after = list(e2.self_model["identity_core"])
    check("§9 身份主题可经语义图跨字面归纳（无联系时不强行归并）",
          "摄影" not in before and "摄影" in after,
          "无语义联系时=%s；教会 照片/个展→摄影 后=%s" % (before, after))

    # ---------- §6.1 睡眠两阶段做的事不同 ----------
    hs = hm(tmp, "ph_sleep")
    for i in range(4):
        hs.remember({"who": "外公", "where": "天台", "when": "傍晚",
                     "what": "教我对焦%d" % i, "feel": "紧张", "why": "第一次",
                     "result": "拍糊了" if i % 2 else "拍清楚了"},
                    arousal=0.7, now=T0 + i * H)
    n_before = len(hs.memories)
    ss_before = {k: hs.ss(v) for k, v in hs.memories.items()}
    out = hs.sleep(now=T0 + 10 * H, hours=8.0)
    ss_after = {k: hs.ss(v) for k, v in hs.memories.items()}
    grew = sum(1 for k in ss_before if ss_after[k] > ss_before[k] + 1e-9)
    check("§6.1 SWS 回放蒸馏 + REM 只强化已回放痕迹，不新增内容",
          out["stages"] == ["SWS", "REM"] and out["sws"].get("replayed", 0) > 0
          and out["rem"]["strengthened"] > 0 and grew > 0
          and len(hs.memories) == n_before,
          "阶段=%s SWS回放=%s REM强化=%d SS上升=%d 记忆数 %d→%d"
          % (out["stages"], out["sws"].get("replayed"), out["rem"]["strengthened"],
             grew, n_before, len(hs.memories)))

    # ---------- §10 元认知效率 meta-d'/d' ----------
    # 正确率必须高于机遇水平，否则任务 d'=0、"效率"无定义（这是 SDT 的结论，
    # 不是实现缺陷）。两组正确率相同，只有置信与对错的对应关系相反。
    from affective_mind import MetaMind
    good = ([{"conf": 0.9, "correct": True}] * 8 + [{"conf": 0.2, "correct": True}] * 1
            + [{"conf": 0.2, "correct": False}] * 3)
    bad = ([{"conf": 0.2, "correct": True}] * 8 + [{"conf": 0.9, "correct": True}] * 1
           + [{"conf": 0.9, "correct": False}] * 3)
    g = MetaMind.meta_dprime(good)
    b = MetaMind.meta_dprime(bad)
    chance = MetaMind.meta_dprime([{"conf": 0.9, "correct": True}] * 6
                                  + [{"conf": 0.2, "correct": False}] * 6)
    # 正确率 51%：d' 趋零，效率比值会被放大成几十倍，必须拒报
    near = MetaMind.meta_dprime([{"conf": 0.9, "correct": True}] * 51
                                + [{"conf": 0.2, "correct": False}] * 49)
    check("§10 meta-d' 区分「知道自己知不知道」与反着来，机遇水平不硬报效率",
          g["meta_d_prime"] > 0 > b["meta_d_prime"]
          and g["efficiency"] is not None and g["efficiency"] > 0
          and chance["at_chance"] and chance["efficiency"] is None
          and near["ratio_unstable"] and near["efficiency"] is None,
          "同正确率下 校准好 meta-d'=%.3f 效率=%s；置信反相 meta-d'=%.3f；"
          "机遇组效率=%s；近机遇组 d'=%.3f 效率=%s"
          % (g["meta_d_prime"], g["efficiency"], b["meta_d_prime"],
             chance["efficiency"], near["d_prime"], near["efficiency"]))

    # ---------- §5.2A 压缩不能抹掉时空锚点 ----------
    hc = hm(tmp, "ph_anchor")
    first = hc.remember({"who": "自己", "where": "学校", "what": "开学第一天"},
                        arousal=0.4, now=T0)
    later_ids = [hc.remember({"who": "自己", "where": "学校", "what": "平常的一天%d" % i},
                             arousal=0.4, now=T0 + i * H) for i in range(4)]
    anchors = [bool(hc.memories[i]["episode"].get("where")
                    or hc.memories[i]["episode"].get("when"))
               for i in later_ids]
    fid = [hc.memories[i]["fidelity"] for i in later_ids]
    check("§5.2A 冗余事件被压缩，但时空锚点仍在（压缩落在保真度上）",
          all(anchors) and min(fid) < hc.memories[first]["fidelity"],
          "后四条是否都有 when/where=%s；保真度 首条=%.2f 后续=%s"
          % (anchors, hc.memories[first]["fidelity"], [round(x, 2) for x in fid]))

    # ---------- 线索信息量 ≠ 字段个数；强而无关的记忆不得占住 top ----------
    hr = hm(tmp, "ph_cue")
    target = hr.remember({"who": "自己", "when": "冬天", "what": "第一次艺考落榜",
                          "why": "差了三分", "result": "在雪里坐了很久"},
                         arousal=0.5, now=T0)
    for i in range(6):
        hr.remember({"who": "老师", "where": "学校", "when": "暑假",
                     "what": "第一次进暗房", "feel": "震动", "why": "冲卷",
                     "result": "影像浮出来"}, arousal=0.6, now=T0 + (i + 1) * H)
    far = T0 + 400 * 24 * H
    for i in range(6):
        hr.rehearse("m%d" % (i + 1), True, now=T0 + (i + 1) * 40 * H)
    one = hr.recall({"what": "第一次艺考落榜"}, now=far, reinforce=False)
    top = one["results"][0] if one["results"] else {}
    check("单字段但逐字命中的线索能唤回淡出痕迹，不被强而无关的记忆挤掉",
          one["best"] == target and top.get("text", 0) >= 0.85,
          "best=%s（目标 %s）top文本覆盖=%.2f top的RS=%.4f 目标RS=%.4f 从latent唤回=%s"
          % (one["best"], target, top.get("text", 0), top.get("rs", 0),
             hr.rs(hr.memories[target], far), top.get("recovered_from_latent")))

    # ---------- 语义双时间线：当时的错误信念要查得到 ----------
    from brain import Brain
    eb = SelfEngine(enabled=True, semantic=True,
                    human_store=os.path.join(tmp, "ph_bt.json"),
                    semantic_store=os.path.join(tmp, "ph_bt_sem.json"))
    eb.sem.teach("雯", "knows:景深", "照片里清晰的范围，光圈越大越大", now=T0)
    eb.sem.teach("雯", "knows:景深", "照片里清晰的范围，光圈越大越浅",
                 now=T0 + 100 * 24 * H, replace=True)
    b = Brain(eb)
    old_ans = b.turn("什么是景深", now=T0 + 10 * 24 * H)
    new_ans = b.turn("什么是景深", now=T0 + 200 * 24 * H)
    check("语义双时间线：早期问得到当时的错误版本，纠正后问得到新版本",
          "越大越大" in old_ans["say"] and "越浅" in new_ans["say"],
          "纠正前问：%s ｜ 纠正后问：%s" % (old_ans["say"], new_ans["say"]))

    # ---------- 知识问句不得被个人经历顶替 ----------
    ek = SelfEngine(enabled=True, semantic=True,
                    human_store=os.path.join(tmp, "ph_kq.json"),
                    semantic_store=os.path.join(tmp, "ph_kq_sem.json"))
    ek.remember({"who": "自己", "when": "冬天", "what": "第一次艺考落榜",
                 "why": "差了三分", "result": "在雪里坐了很久"},
                arousal=0.6, now=T0)
    bk = Brain(ek)
    kq = bk.turn("你知道艺考改革吗", now=T0 + 200 * 24 * H)
    check("没学过的概念问句只能弃答，不能拿同词的个人经历顶上",
          kq["mode"] == "abstain" and "落榜" not in kq["say"],
          "mode=%s say=%s" % (kq["mode"], kq["say"]))

    print()
    print("=" * 66)
    n = len(RESULTS)
    p = sum(1 for _, ok, _ in RESULTS if ok)
    print("现象级验收：%d / %d" % (p, n))
    for name, ok, _ in RESULTS:
        if not ok:
            print("  未通过：%s" % name)
    return 0 if p == n else 1


if __name__ == "__main__":
    sys.exit(main())
