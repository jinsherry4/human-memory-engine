# -*- coding: utf-8 -*-
"""audit_research_map.py — 研究结论 → 重建版代码 的落地核查

对照 HUMAN_LIKE_MIND_METHOD.md（v2.6）§5–§10 与 §17 的"已实现"清单，
逐条在 F:\\ai chat\\memory_engine 里找实现证据。

判定口径：
  MISSING  关键符号/文件在全引擎中零出现
  STUB     有函数名但函数体是占位/恒等返回
  PARTIAL  有实现但只覆盖研究结论的一部分
  PRESENT  有可执行实现（不代表已验证正确）
"""
import json
import os
import re
import sys

ENG = r"F:\ai chat\memory_engine"
sys.path.insert(0, ENG)

SRC = {}
# 只扫实现模块；审计脚本与测试文件不算实现证据
SKIP = ("audit_", "test_", "regress", "selftest")
for name in sorted(os.listdir(ENG)):
    if name.endswith(".py") and not name.startswith(SKIP):
        SRC[name] = open(os.path.join(ENG, name), encoding="utf-8").read()
ALL = "\n".join(SRC.values())


def find(*pats):
    """返回 {文件: 命中行号} ，只算真实代码行（跳过纯注释/docstring 行的粗略过滤）。"""
    hits = {}
    for name, txt in SRC.items():
        for i, line in enumerate(txt.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            if any(re.search(p, line) for p in pats):
                hits.setdefault(name, []).append(i)
    return hits


# (编号, 研究结论, 出处, 判定用关键符号, 预判)
ITEMS = [
    # ---- 记忆 §5 ----
    ("M01", "SS/RS 双强度：SS 只增、RS 衰减、SS 延缓 RS 丢失", "§5.7 Bjork",
     [r"ss_gain", r"ss\s*\+=", r"rs_regain", r"storage_strength"], None),
    ("M02", "SS 增量随当前 RS 递减（desirable difficulty）", "§5.7",
     [r"_ss_gain", r"rs_norm"], None),
    ("M03", "variable-rate 编码：rate ∝ Bayesian surprise", "§5.2A Nagy",
     [r"surprise"], None),
    ("M04", "层级压缩：先丢浅层感觉、保深层 gist", "§5.2A Rugg",
     [r"SHALLOW_FIRST", r"ITEM_CORE"], None),
    ("M05", "多痕迹共存 episode_traces（原始仍在，特异线索可提取）", "§5.3 Rugg/Shao",
     [r"traces"], None),
    ("M06", "更新 vs 新建 = 潜在原因推断", "§5.3 Gershman2017",
     [r"cause_changed", r"update_or_new"], None),
    ("M07", "非单调可塑 NMPH（共激活中→弱化、高→强化，U 形）", "§5.3 Xue",
     [r"differentiate", r"integrate"], None),
    ("M08", "提取练习调度：间隔 + 正确答案反馈 + 5–7 次", "§5.3 Roediger&Butler",
     [r"spaced", r"recall_schedule", r"feedback_correct"], None),
    ("M09", "再巩固更新窗口（提取后 labile，有界）", "§5.8 Nader",
     [r"labile", r"reconsolid", r"restabil"], None),
    ("M10", "检索诱发遗忘 RIF：抑制竞争项", "§5.3 Roediger",
     [r"\brif\b", r"suppress", r"inhibit.*compet"], None),
    ("M11", "干扰项 interference 降低可及性", "§5.2B Wixted",
     [r"inhibition", r"_inhib"], None),
    ("M12", "来源监控：记得/想象/被告知/推断", "§10 Rugg/Johnson",
     [r"source_monitor", r"imagined", r"source_kind"], None),
    ("M13", "raw append-only 原始证据库", "§3.1",
     [r"append_jsonl", r"raw_path"], None),
    ("M14", "四指标不合成：availability/accessibility/fidelity/confidence", "§5.1",
     [r"accessible", r"fidelity"], None),
    # ---- 离线 §6 ----
    ("O01", "变换性回放：压缩/反转/重组，弱记忆回放更多", "§6.1 Xue/CLS",
     [r"replay", r"prioritized"], None),
    ("O02", "睡眠两阶段 SWS 系统巩固 / REM 突触巩固", "§6.1 Diekelmann&Born",
     [r"SWS", r"REM", r"def sleep"], None),
    ("O03", "反思蒸馏：importance 累积触发 + 洞察带证据引用", "§6.2 GenerativeAgents",
     [r"importance", r"because_of", r"reflection"], None),
    ("O04", "mind-wandering 自发模拟 / 孵化", "§6.1 Smallwood",
     [r"incubat", r"mind_wander", r"residual"], None),
    # ---- 情感 §7 ----
    ("E01", "core affect PAD，tonic 慢衰减", "§7.1 Barrett",
     [r"TAU_HOURS", r"valence"], None),
    ("E02", "emotion_instance：用概念范畴化建构离散情绪", "§7.1 Barrett",
     [r"emotion_instance", r"categoriz", r"concept.*emotion"], None),
    ("E03", "appraisal_features 可解释评价维度", "§7.1 Yeo&Ong",
     [r"appraisal", r"appraise"], None),
    ("E04", "ABC：唤醒 × 优先级（高优先级不唤醒也增强）", "§7.2 Mather",
     [r"priority", r"\babc\b"], None),
    ("E05", "item↑ / relational↓：负性损害上下文绑定", "§7.2 Bisby",
     [r"relational", r"binding.*loss", r"coherence"], None),
    ("E06", "mood-congruent 检索偏置", "§7.2",
     [r"recall_bias"], None),
    ("E07", "调节工具箱：五策略族 + 健康度权重 + 多样性", "§7.3 Gross/Baldwin",
     [r"reapprais", r"regulat", r"distancing", r"suppression"], None),
    ("E08", "反刍检测器（重复+负面+自我聚焦+无进展）", "§7.3 Aldao",
     [r"ruminat", r"反刍"], None),
    ("E09", "调节灵活性：强度 × 可控性选策略", "§7.3 Sheppes/Bonanno",
     [r"controllab", r"flexibil", r"strategy_select"], None),
    # ---- 认知 §4/§8/§10 ----
    ("C01", "全局工作空间：偏向竞争 + 点火广播", "§4 GNW",
     [r"ignit", r"broadcast", r"salience"], None),
    ("C02", "WM 容量限制与互相抑制", "§4",
     [r"capacity", r"_compete"], None),
    ("C03", "元认知：置信独立于检索分（FOK/TIP 可脱钩）", "§10 Fleming",
     [r"fok", r"tip"], None),
    ("C04", "校准 ECE / Brier", "§10",
     [r"ece", r"brier"], None),
    ("C05", "meta-d' / d' 元认知效率", "§10",
     [r"meta_dprime", r"d_prime"], None),
    ("C06", "正证据偏差 PEB：显式加权反证", "§10",
     [r"\bpeb\b", r"counter_evidence", r"disconfirm"], None),
    ("C07", "弃答：可以说不知道", "§10",
     [r"abstain"], None),
    ("C08", "灵光 EII/CLARION：显隐整合 + 温度 + ICL 阈值", "§8.2 Hélie&Sun",
     [r"\bicl\b", r"clarion", r"temperature", r"impasse"], None),
    ("C09", "灵光独立慢校验（Aha ≠ 正确）", "§8.2 Metcalfe",
     [r"verif", r"insight_candidate"], None),
    # ---- 自我 §9 ----
    ("S01", "Conway SMS 四层：life_story/lifetime_periods/general_events/ESK", "§9 Conway",
     [r"lifetime_periods", r"\besk\b"], None),
    ("S02", "working self 门控 recall", "§9 Conway",
     [r"working self 门控", r"def recall_self"], None),
    ("S03", "身份核心不被单次改写（需反复验证）", "§9",
     [r"identity_core", r"identity.*verif"], None),
    ("S04", "关系模型：信任 / 未解冲突 / 仪式", "§9",
     [r"trust", r"unresolved", r"ritual"], None),
    # ---- 语义/程序 §3 ----
    ("G01", "图多跳检索 + 超边 episodic_hyperedges", "§3.5",
     [r"hops", r"hyper"], None),
    ("G02", "事实 provenance / 版本化 / 双时间线 / 冲突解决", "§3.3",
     [r"provenance", r"valid_from", r"conflict"], None),
    ("G03", "程序 savings（生疏后重学更快）", "§3.4",
     [r"savings"], None),
    ("G04", "程序编译自动化 → 步骤缩短 / 成本下降", "§3.4",
     [r"compiled"], None),
]

CLAIMED_MODULES = ["affective_mind.py", "insight_engine.py"]

rows = []
for pid, claim, ref, pats, _ in ITEMS:
    hits = find(*pats)
    n = sum(len(v) for v in hits.values())
    rows.append({"id": pid, "claim": claim, "ref": ref,
                 "patterns": pats, "hit_files": hits, "hit_lines": n})

print("=" * 78)
print("研究结论 → 重建版代码 落地核查（符号级）")
print("=" * 78)
for r in rows:
    files = ",".join("%s:%s" % (k, v[:4]) for k, v in r["hit_files"].items())
    flag = "MISSING" if r["hit_lines"] == 0 else "有符号"
    print("%-4s %-7s %-46s %s" % (r["id"], flag, r["claim"][:46], files[:90]))

print()
print("§17 声称已实现的模块是否存在：")
for m in CLAIMED_MODULES:
    print("  %-22s %s" % (m, "存在" if m in SRC else "不存在"))

print()
print("重建版实际文件：", ", ".join(sorted(SRC)))

miss = [r["id"] for r in rows if r["hit_lines"] == 0]
print()
print("零符号命中 %d / %d 条：%s" % (len(miss), len(rows), ",".join(miss)))

out = os.path.join(ENG, "audit_research_map_results.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"items": rows,
               "claimed_modules_missing": [m for m in CLAIMED_MODULES if m not in SRC],
               "zero_hit": miss}, f, ensure_ascii=False, indent=2)
print("写入 -> %s" % out)
