# -*- coding: utf-8 -*-
"""audit_probe.py — 第三方复查探针（2026-11-21）

不是单元测试，不追求"全绿"。每条探针只做一件事：把一个可疑设计点变成
可复现的数字或反例。打印 [Pxx] 标题 + 证据 + 判定（BUG / GAP / OK）。

用法：python audit_probe.py
"""
import json
import math
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from affect import Affect
from brain import Brain
from circuits import CA1, CA3
from engine import MemoryEngine
from human_memory import HumanMemory
from persistence import load_json, save_json
from practice_engine import (constraint_check, exposure_plan, parse_shutter,
                             _fmt_stop)
from procedural_memory import ProceduralMemory
from self_engine import SelfEngine
from semantic_graph import SemanticGraph

RESULTS = []


def rec(pid, title, verdict, evidence):
    RESULTS.append((pid, title, verdict, evidence))
    print("[%s] %s" % (pid, title))
    print("    证据：%s" % evidence)
    print("    判定：%s" % verdict)
    print()


def new_eng(tmp, age=20.5):
    e = SelfEngine(affect=Affect(), human_store=os.path.join(tmp, "h.json"),
                   semantic=True, semantic_store=os.path.join(tmp, "s.json"),
                   procedural=True, proc_store=os.path.join(tmp, "p.json"),
                   selfmodel=True, self_store=os.path.join(tmp, "self.json"))
    e.set_age(age)
    return e


def main():
    tmp = tempfile.mkdtemp()

    # ---- P01 检索强化只在最弱的分支里执行 ----
    h = HumanMemory(os.path.join(tmp, "p01.json"), affect=Affect())
    mid = h.remember({"who": "外公", "where": "家", "what": "给我旧相机"}, now=1000)
    n0 = len(h.memories[mid]["accesses"])
    r = h.recall({"who": "外公", "where": "家", "what": "给我旧相机"}, now=2000)
    n1 = len(h.memories[mid]["accesses"])
    rec("P01", "命中主门时是否写入提取练习（accesses / reinforced）",
        "BUG" if (r["best"] == mid and n1 == n0) else "OK",
        "best=%s accesses %d→%d reinforced=%s"
        % (r["best"], n0, n1, r["results"][0]["reinforced"]))

    # ---- P02 编码丢掉的细节仍能检索到 ----
    h2 = HumanMemory(os.path.join(tmp, "p02.json"), affect=Affect())
    ep = {"who": "自己", "where": "考场外", "when": "冬天", "what": "落榜",
          "feel": "空", "why": "差三分", "result": "雪里坐很久"}
    m2 = h2.remember(ep, arousal=1.0, now=1000, dev_age=20.5)
    dropped = [k for k in ep if k not in h2.memories[m2]["episode"]]
    hit_by_dropped = None
    if dropped:
        k = dropped[0]
        rr = h2.recall({k: ep[k], "what": "落榜"}, now=2000)
        hit_by_dropped = (rr["best"] == m2)
    rec("P02", "detail_kept 下降后，被丢字段是否仍可作为检索线索",
        "GAP" if hit_by_dropped else "OK",
        "detail_kept=%.2f 丢掉=%s 用被丢字段+what 检索命中=%s"
        % (h2.memories[m2]["detail_kept"], dropped, hit_by_dropped))

    # ---- P03 文本打分用二字片段，长问句会误命中 ----
    h3 = HumanMemory(os.path.join(tmp, "p03.json"), affect=Affect())
    a = h3.remember({"who": "老师", "where": "小学", "what": "第一次拿奖"}, now=1000)
    b = h3.remember({"who": "自己", "where": "家", "what": "第一次做饭"}, now=1000)
    s_a = h3._text_score({"what": "聊起洗出第一张照片"}, h3.memories[a]["full_episode"])
    s_b = h3._text_score({"what": "聊起洗出第一张照片"}, h3.memories[b]["full_episode"])
    rec("P03", "_text_score 对无关长句是否给出满分覆盖",
        "BUG" if max(s_a, s_b) >= 0.99 else "OK",
        "问『聊起洗出第一张照片』：拿奖=%.2f 做饭=%.2f（两条都没有照片）" % (s_a, s_b))

    # ---- P04 新检索路径是否使用情绪一致性偏置 ----
    e = new_eng(tmp)
    for v, what in ((0.8, "开心的一天"), (-0.8, "难过的一天"), (0.0, "平常的一天")):
        e.remember({"who": "自己", "where": "学校", "what": what}, valence=v, now=1000)
    outs = []
    for mood in (-0.8, 0.8):
        e.affect.state.update({"valence": mood, "arousal": 0.35, "dominance": 0.1})
        rr = e.recall({"where": "学校"}, top_k=3, now=2000)
        outs.append([x["id"] for x in rr["results"]])
    rec("P04", "心情正/负时检索排序是否不同（情绪一致性检索）",
        "GAP" if outs[0] == outs[1] else "OK",
        "低落序=%s 高涨序=%s；affect.recall_bias 在 human_memory 中的调用次数=0"
        % (outs[0], outs[1]))

    # ---- P05 排序是否含激活/遗忘 ----
    e5 = new_eng(tmp)
    old = e5.remember({"who": "妈妈", "where": "家", "what": "做饭"}, now=0)
    fresh = e5.remember({"who": "妈妈", "where": "家", "what": "做饭"}, now=10 ** 9)
    rr = e5.recall({"who": "妈妈", "where": "家", "what": "做饭"}, top_k=2, now=10 ** 9)
    rec("P05", "同内容新旧两条记忆，检索是否偏向近期（RS 参与排序）",
        "GAP" if rr["results"][0]["id"] == old else "OK",
        "top1=%s（old=%s fresh=%s）rs_old=%.4f rs_fresh=%.4f"
        % (rr["results"][0]["id"], old, fresh,
           rr["results"][0]["rs"], rr["results"][1]["rs"]))

    # ---- P06 save_self 是否丢 timeline ----
    sp = os.path.join(tmp, "p06_self.json")
    save_json(sp, {"self_model": {"identity_core": ["x"]},
                   "working_self": {"goals": ["g"]},
                   "relationships": {}, "timeline": [{"t": 1, "what": "出生"}]})
    e6 = SelfEngine(selfmodel=True, self_store=sp)
    e6.load_self()
    had = hasattr(e6, "timeline") and bool(e6.timeline)
    e6.save_self()
    after = load_json(sp, {})
    rec("P06", "load_self 读入的 timeline 能否被 save_self 写回",
        "BUG" if (had and "timeline" not in after) else "OK",
        "读入 timeline=%s；保存后 keys=%s" % (had, sorted(after.keys())))

    # ---- P07 事实"两次独立传授"是否真独立 ----
    sg = SemanticGraph(os.path.join(tmp, "p07.json"))
    f1 = sg.teach("雯", "knows:景深", "清晰范围", source="同一节课", now=500)
    sg.teach("雯", "knows:景深", "清晰范围", source="同一节课", now=500)
    rec("P07", "同一来源同一秒重复教一次，事实是否直接 verified",
        "BUG" if sg.facts[f1]["status"] == "verified" else "OK",
        "status=%s lessons=%s" % (sg.facts[f1]["status"], sg.facts[f1]["lessons"]))

    # ---- P08 replace 后是否仍有同谓词的活跃旧说法 ----
    sg8 = SemanticGraph(os.path.join(tmp, "p08.json"))
    sg8.teach("雯", "knows:景深", "越大越深", source="a", now=100)
    sg8.teach("雯", "knows:景深", "越大越浅", source="b", now=200, replace=True)
    sg8.teach("雯", "knows:景深", "越大越浅", source="c", now=300, replace=True)
    active = [f["o"] for f in sg8.facts.values()
              if f["p"] == "knows:景深" and f["status"] != "superseded"]
    rec("P08", "replace=True 重复教同一新说法后，同谓词活跃说法数量",
        "BUG" if len(set(active)) > 1 else "OK",
        "活跃说法=%s" % active)

    # ---- P09 ask 是否遵守时间有效性 ----
    sg9 = SemanticGraph(os.path.join(tmp, "p09.json"))
    t_now = time.time()
    sg9.teach("雯", "knows:未来", "还没学", source="x", now=t_now + 86400)
    got = sg9.ask("雯", "knows:未来", now=t_now)
    rec("P09", "semantic_graph.ask 是否过滤 valid_from 未到的事实",
        "OK" if not got else "BUG",
        "now=今天 时 ask 返回 %d 条（明天才生效的事实）" % len(got))

    # ---- P10 confirm_rule 是否要求两次独立实践 ----
    sg10 = SemanticGraph(os.path.join(tmp, "p10.json"))
    sg10.teach_rule("r", [["a"]], "do", now=100)
    for _ in range(5):
        sg10.confirm_rule("r", event="same-turn")
    same = sg10.rules["r"]["practice"]
    for i in range(2):
        sg10.confirm_rule("r", event="turn-%d" % i)
    diff = sg10.rules["r"]["practice"]
    rec("P10", "同一轮重复确认不累加；不同轮才累加",
        "OK" if (same == 1 and diff == 3) else "BUG",
        "同轮 5 次 → practice=%d；再加 2 个不同轮 → practice=%d" % (same, diff))

    # ---- P11 shaky 是否随时间恢复；compiled 是否降本 ----
    pm = ProceduralMemory(os.path.join(tmp, "p11.json"))
    pid = pm.learn("暗房", ["显影", "停显", "定影"], now=0)
    pm.run(pid, False, now=0)
    pm.run(pid, False, now=0)
    shaky0 = pm.procs[pid]["shaky"]
    pm.procs[pid]["last_run"] = 0
    shaky_later = pm.shaky(pm.procs[pid], now=10 ** 7)
    cost_uncompiled = pm.cost(pid, now=0)
    pm.procs[pid]["compiled"] = True
    cost_compiled = pm.cost(pid, now=0)
    ok11 = shaky0 and not shaky_later and cost_compiled < cost_uncompiled
    rec("P11", "shaky 随时间恢复 / compiled 降低执行成本",
        "OK" if ok11 else "GAP",
        "刚失败 shaky=%s，久置后 shaky=%s；cost 未编译=%.3f 编译后=%.3f"
        % (shaky0, shaky_later, cost_uncompiled, cost_compiled))

    # ---- P12 曝光推算的镜头假设与兜底文案 ----
    t12 = "手持，光圈 f/5.6，快门 1/8，ISO 400，能拍吗？我只有 f/4 的套头。"
    out12 = exposure_plan(t12, age=20.5)
    t12b = "手持，快门 1/8，能拍吗？"
    out12b = exposure_plan(t12b, age=20.5)
    ok12 = ("f/2.8" not in (out12 or "")) and ("1/8" in (out12b or ""))
    rec("P12", "曝光推算是否读取镜头最大光圈 / 兜底文案是否随快门变化",
        "OK" if ok12 else "GAP",
        "只有 f/4 套头 → %s ｜ 快门 1/8 兜底 → %s" % (out12, out12b))

    # ---- P13 档位显示取整 ----
    true_stops = math.log2(15)
    shown = _fmt_stop(true_stops)
    ok13 = abs(float(shown) - round(true_stops * 3) / 3) < 1e-6
    rec("P13", "档位是否按相机 1/3 档刻度取整（而非为凑测试的容差）",
        "OK" if ok13 else "GAP",
        "真实 log2(60/4)=%.4f 档；1/3 档刻度=%.4f；输出『%s』"
        % (true_stops, round(true_stops * 3) / 3, shown))

    # ---- P14 大小写 / 单位解析 ----
    lower = constraint_check("夜里只有一盏灯，iso 100，手持，能拍吗？", age=20.5)
    sec = parse_shutter("快门 2 秒")
    ok14 = lower is not None and sec is not None and abs(sec - 0.5) < 1e-6
    rec("P14", "practice_engine 是否做大小写归一与秒级快门解析",
        "OK" if ok14 else "GAP",
        "小写 iso 100 触发约束=%s；『2 秒』解析分母=%s（应为 0.5）" % (lower is not None, sec))

    # ---- P15 年龄闸门次序 ----
    e15 = new_eng(tmp, age=17.0)
    b15 = Brain(e15)
    o15 = b15.turn("我开到 f/2 了，也让他离背景远了，还是太清楚。")
    o15b = b15.turn("阴天下午，ISO 100，手持，光圈 f/8，快门 1/15，能拍吗？")
    ok15 = o15["mode"] != "apply"
    rec("P15", "17 岁：诊断虚化不应早于会算曝光",
        "OK" if ok15 else "GAP",
        "曝光=%s ｜ 虚化诊断=%s（闸门已统一为 18.7）" % (o15b["mode"], o15["mode"]))

    # ---- P16 "成了"误判为成功反馈 + 陈旧规则归因 ----
    e16 = new_eng(tmp)
    b16 = Brain(e16)
    e16.teach_rule("装卷", [["片头", "挂歪"]], "别硬拉", now=100)
    b16.turn("片头挂歪了怎么办？")
    for _ in range(3):
        b16.turn("今天天气不错")
    o16 = b16.turn("这张拍成了糊片")
    rec("P16", "『成了』出现在负面陈述里 / 隔多轮后是否仍确认旧规则",
        "BUG" if o16["mode"] == "confirm" else "OK",
        "输入『这张拍成了糊片』→ mode=%s say=%s 归因规则=%s"
        % (o16["mode"], o16["say"], o16.get("rule") and o16["rule"]["name"]))

    # ---- P17 gist 分支的 top 与 gist_best 是否同一条 ----
    e17 = new_eng(tmp)
    e17.remember({"who": "老师", "where": "小学", "what": "第一次拿奖"}, now=1000)
    e17.remember({"who": "自己", "where": "家", "what": "第一次做饭"}, now=1000)
    rr17 = e17.recall({"who": "老师", "what": "聊起洗出第一张照片"}, now=2000)
    mismatch = (rr17["gist_best"] is not None and rr17["results"]
                and rr17["gist_best"] != rr17["results"][0]["id"])
    rec("P17", "gist 命中记忆与对外 top 是否可能不是同一条",
        "GAP" if mismatch else "OK",
        "best=%s gist_best=%s top=%s"
        % (rr17["best"], rr17["gist_best"],
           rr17["results"][0]["id"] if rr17["results"] else None))

    # ---- P18 语义作答的措辞与问句焦点 ----
    e18 = new_eng(tmp)
    e18.teach("雯", "told:那台相机", "他年轻时买的", source="外婆", now=100)
    e18.teach("雯", "knows:光圈", "控制进光量", source="课", now=100)
    e18.teach("雯", "knows:景深", "清晰范围，光圈越大越浅", source="课", now=100)
    b18 = Brain(e18)
    o18a = b18.turn("那台相机是哪来的？")
    o18b = b18.turn("景深越大，光圈越大还是越小？")
    ok18 = ("是是" not in o18a["say"]) and ("景深" in o18b["say"])
    rec("P18", "told 类事实的措辞 / 关系问句是否答到被问的关系",
        "OK" if ok18 else "GAP",
        "问相机来历→『%s』；问『景深越大，光圈越大还是越小』→『%s』"
        % (o18a["say"], o18b["say"]))

    # ---- P19 旧 MemoryEngine 是否仍保留原两处缺陷 ----
    me = MemoryEngine(affect=Affect())
    me.remember({"who": "外公", "what": "给相机"}, arousal=0.5)
    rr19 = me.recall({"what": "火星殖民地量子计算机"})
    leak = None
    if rr19["results"]:
        m = me.memories[rr19["results"][0]["id"]]
        leak = rr19["results"][0]["episode"] == m["full_episode"]
    rec("P19", "兼容层 engine.MemoryEngine 是否仍无条件 best=results[0] 且回全字段",
        "BUG" if (rr19["best"] is not None and leak) else "OK",
        "无关线索 best=%s；返回 episode 是否等于 full_episode=%s" % (rr19["best"], leak))

    # ---- P20 损坏 store 是否还会静默降级 ----
    from persistence import StoreCorrupt, recover_latest_backup
    bad = os.path.join(tmp, "p20.json")
    with open(bad, "w", encoding="utf-8") as f:
        f.write('{"memories": [ 半个 JSON')
    raised = False
    try:
        load_json(bad, {})
    except StoreCorrupt:
        raised = True
    degraded = load_json(bad, {}, strict=False)
    rec("P20", "store 损坏时是否抛错而不是静默当空库",
        "OK" if raised else "BUG",
        "strict 抛 StoreCorrupt=%s；显式 strict=False 才降级=%s" % (raised, degraded == {}))

    # ---- P21 回路层与联想边是否接入新检索 ----
    import inspect
    src = inspect.getsource(HumanMemory)
    uses = {"CA3": "CA3" in src, "CA1": "CA1" in src,
            "dg.separate 用于检索": "cue_pat" in src,
            "recall_bias": "recall_bias" in src,
            "relevance": "relevance" in src and "m.get(\"relevance\"" in src}
    hop_used = "edges" in inspect.getsource(SemanticGraph.ask_graph)
    ok21 = all(uses.values()) and hop_used
    rec("P21", "DG/CA3/CA1、情绪偏置、联想边是否参与重建版检索",
        "OK" if ok21 else "GAP",
        "human_memory 引用情况=%s；ask_graph 是否用 edges=%s" % (uses, hop_used))

    # ---- P22 enabled / mind / insight 开关是否有效 ----
    e22 = SelfEngine(enabled=False, mind=False, insight=False)
    mid22 = e22.remember({"what": "关掉引擎后仍写入"}, now=100)
    rec("P22", "enabled=False 是否真的关闭写入；insight 是否有实现",
        "GAP" if mid22 is not None else "OK",
        "enabled=False 仍返回 mid=%s；insight()=%s" % (mid22, e22.insight()))

    print("=" * 70)
    tally = {}
    for _, _, v, _ in RESULTS:
        tally[v] = tally.get(v, 0) + 1
    print("探针 %d 条：%s" % (len(RESULTS), tally))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "audit_probe_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump([{"id": p, "title": t, "verdict": v, "evidence": ev}
                   for p, t, v, ev in RESULTS], f, ensure_ascii=False, indent=2)
    print("写入 -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
