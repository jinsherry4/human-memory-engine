# -*- coding: utf-8 -*-
"""affective_mind.py — 工作空间 / 元认知 / 情绪建构 / 情绪调节（P5）

对应 HUMAN_LIKE_MIND_METHOD.md：
§4    全局工作空间：容量受限 + 偏向竞争 + 点火广播（GNW 的计算类比，不声称意识）
§7.1  Barrett 建构论：core affect(PAD) + 概念范畴化 → emotion_instance，
      同一类别可由多种模式实现（简并性），不是固定 lookup
§7.2  ABC：唤醒放大偏向竞争（高优先级被增强、低优先级被压低）
§7.3  Gross 五策略族 × Bonanno 灵活性 × Sheppes 强度×可控性 × Aldao 反刍检测
§10   Fleming：FOK/TIP 与命题置信可脱钩；正证据偏差 PEB 显式加权反证
"""

import math
import time

WM_CAPACITY = 4
WM_TAU_HOURS = 0.5
IGNITION_THRESHOLD = 0.62
IGNITION_MARGIN = 0.12

# §7.3 健康度权重（Baldwin & Kross 2025 的相对分，映射到五族）
STRATEGY_HEALTH = {
    "situation_selection": 4.0,
    "situation_modification": 4.1,
    "attentional_deployment": 3.5,   # distraction
    "cognitive_change": 4.3,         # reappraisal / distancing
    "response_modulation": 1.5,      # suppression：仅短期应急
}
RUMINATION_WINDOW = 6
RUMINATION_MIN = 3
# meta-d'/d' 的分母下限：任务 d' 低于此值时比值不稳定，不予报告。
# §18.4（Rahnev 2025，17 种指标评估）：meta-d'/ratio 类指标要求 d' > 1
# （正确率约 69%）才稳定，更低时 efficiency 一律报 null，只报 meta-d' 本身。
MIN_DPRIME_FOR_RATIO = 1.0

# §18.3（Morgan 2025）：低精度条件下主观变化显著度反而更高（反贝叶斯）。
# 低于此精度时不再套用 salience = precision × PE 的乘法式，改用饱和映射。
LOW_PRECISION_CUT = 0.35


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Workspace:
    """容量受限的全局工作空间。salience 决定谁能留下、谁能点火。"""

    def __init__(self, capacity=WM_CAPACITY):
        self.capacity = capacity
        self.items = []
        self.broadcasts = []

    def push(self, content, salience=0.5, now=None, goal_match=0.0, arousal=0.35,
             precision=None):
        """把内容推进工作空间竞争。

        precision 为 None 时走旧路径（不参与精度调制），保持既有行为。
        给了 precision 才启用 §18.3 的适用边界：
          - 高精度（>= LOW_PRECISION_CUT）：salience = 显著度 × 精度（经典 precision×PE）
          - 低精度（<  LOW_PRECISION_CUT）：**不乘精度**，改用随精度下降而略升的
            饱和映射。依据 Morgan 2025 四个听觉实验：低信噪比下主观变化显著度
            反而更高（counter-Bayesian，可证伪），此时乘法式会把该现象算反。
        """
        now = time.time() if now is None else now
        low_precision = False
        if precision is None:
            s = float(salience)
        else:
            p = _clamp(float(precision), 0.0, 1.0)
            if p >= LOW_PRECISION_CUT:
                s = float(salience) * p
            else:
                # 低信噪比：显著度对精度的依赖反转，用 (1 - 0.4p) 做温和放大
                s = float(salience) * (1.0 - 0.4 * p)
                low_precision = True
        # ABC 顶-down：与当前目标匹配的项即使不唤醒也被抬高
        s = _clamp(s * (1.0 + 0.5 * goal_match), 0.0, 1.5)
        rec = {"content": content, "salience": s, "t": now,
               "precision": None if precision is None else round(float(precision), 3)}
        if low_precision:
            rec["low_precision"] = True
        self.items.append(rec)
        self._compete(arousal)
        return self.items[-1] if self.items else None

    def _compete(self, arousal):
        if not self.items:
            return
        mean = sum(i["salience"] for i in self.items) / len(self.items)
        # 唤醒放大对比：高于均值的更高、低于均值的更低
        k = 1.0 + 1.2 * float(arousal)
        for i in self.items:
            i["salience"] = _clamp(mean + (i["salience"] - mean) * k, 0.0, 1.5)
        self.items.sort(key=lambda i: i["salience"], reverse=True)
        # 容量限制 + 互相抑制：挤出去的丢弃
        self.items = self.items[:self.capacity]

    def step(self, now=None, arousal=0.35):
        now = time.time() if now is None else now
        kept = []
        for i in self.items:
            dt = max(0.0, (now - i["t"]) / 3600.0)
            i["salience"] *= math.exp(-dt / WM_TAU_HOURS)
            i["t"] = now
            if i["salience"] >= 0.05:
                kept.append(i)
        self.items = kept
        self._compete(arousal)
        return self.items[0]["content"] if self.items else None

    def ignite(self, now=None):
        """点火：最强项过阈值且明显领先第二名，才广播。"""
        now = time.time() if now is None else now
        if not self.items:
            return None
        top = self.items[0]
        second = self.items[1]["salience"] if len(self.items) > 1 else 0.0
        if top["salience"] >= IGNITION_THRESHOLD and top["salience"] - second >= IGNITION_MARGIN:
            rec = {"t": now, "content": top["content"], "salience": round(top["salience"], 3)}
            self.broadcasts.append(rec)
            return rec
        return None


class MetaMind:
    """元认知：三个信号各自独立来源，不互相复制。"""

    def __init__(self, self_bias=None):
        self.self_bias = dict(self_bias or {})   # 例如 {"names": -0.15}
        self.log = []

    @staticmethod
    def meta_dprime(rows):
        """§10 元认知效率：任务 d' 与元认知 meta-d'。

        rows: [{"conf": 0..1, "correct": bool}]

        meta-d' 用 **type-2 ROC 面积**估计：AUC = P(答对的试次置信 > 答错的试次)，
        并列计 0.5；等方差高斯下 d' = √2·z(AUC)。这是 AUC 型估计，不是
        Maniscalco & Lau 的极大似然拟合，但好处是不依赖任意二分点——
        置信取值大量并列时，中位数二分会退化成一个空组。

        任务 d'：只给 conf/correct 时按无偏观察者由正确率反推 pc = Φ(d'/2)。
        pc = 0.5 即机遇水平，d' = 0，此时"效率"数学上无定义，返回 None。
        """
        import math
        rows = [r for r in rows if "conf" in r and "correct" in r]
        base = {"d_prime": 0.0, "meta_d_prime": 0.0, "efficiency": None,
                "at_chance": True, "ratio_unstable": True, "auc": None, "n": len(rows)}
        if len(rows) < 4:
            return base

        def z(p):
            p = min(0.999, max(0.001, p))
            # 标准正态分位数的有理近似（Abramowitz & Stegun 26.2.23）
            t = math.sqrt(-2.0 * math.log(1.0 - p)) if p >= 0.5 else math.sqrt(-2.0 * math.log(p))
            val = t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (
                1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t)
            return val if p >= 0.5 else -val

        ok = [r["conf"] for r in rows if r["correct"]]
        no = [r["conf"] for r in rows if not r["correct"]]
        pc = len(ok) / len(rows)
        d = 2.0 * z(pc)
        at_chance = abs(d) < 1e-6
        if not ok or not no:
            base.update({"d_prime": round(d, 3), "at_chance": at_chance})
            return base
        conc = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in ok for b in no)
        auc = conc / (len(ok) * len(no))
        meta_d = math.sqrt(2.0) * z(auc)
        # d' 太小时比值不稳定（分母趋零会把效率放大成几十倍），
        # 此时只报 meta-d' 本身，不报效率。
        unstable = abs(d) < MIN_DPRIME_FOR_RATIO
        eff = None if unstable else round(meta_d / d, 3)
        return {"d_prime": round(d, 3), "meta_d_prime": round(meta_d, 3),
                "efficiency": eff, "at_chance": at_chance,
                "ratio_unstable": unstable,
                "auc": round(auc, 3), "n": len(rows)}

    def evaluate(self, res, cue=None, domain=None, counter_evidence=0.0, now=None,
                 prev=None):
        """对一次检索结果给出 FOK / TIP / 命题置信。

        prev 传入上一次的 evaluate 输出（可选）。§18.5（Goueytes 2025）：
        置信与改主意来自决策前 pre-SMA + 决策后岛叶的证据累积——
        弃答后若来了新线索，置信应能回升，不能被上一次的弃答结论锁死。
        因此这里显式记 reopened，而不是把 abstain 当终局。
        """
        now = time.time() if now is None else now
        res = res or {}
        results = res.get("results") or []
        top = results[0] if results else {}
        match = float(top.get("score", 0.0))
        text = float(top.get("text", 0.0))

        # FOK：键侧熟悉度——线索本身有多少被认识，与"找没找到"无关
        cue = cue or {}
        familiarity = _clamp(0.25 * len(cue) + 0.5 * text, 0.0, 1.0)
        fok = _clamp(familiarity, 0.0, 1.0)

        # TIP：部分可及——差一点就想起来的程度（命中但未过门时最高）
        near = 1.0 if (res.get("best") is None and match > 0.2) else 0.0
        tip = _clamp(0.6 * near + 0.4 * _clamp(match / 0.6, 0, 1) * (1 - near), 0.0, 1.0)

        # 命题置信：证据强度 × 来源可靠性 − 反证 − 自我模型偏差
        src = top.get("source", "experienced")
        src_w = {"experienced": 1.0, "told": 0.85, "inferred": 0.7, "imagined": 0.45}.get(src, 0.9)
        fid = float(top.get("fidelity", 1.0))
        conf = match * src_w * (0.5 + 0.5 * fid)
        conf -= 0.35 * float(counter_evidence)          # PEB：显式加权反证
        conf += float(self.self_bias.get(domain, 0.0))
        if res.get("best") is None:
            conf *= 0.5
        conf = _clamp(conf, 0.0, 1.0)

        # §18.5 change-of-mind：上一次弃答不算终局。若这次置信已回到可答线以上，
        # 标记 reopened，供上层把"又想起来"和"一直有把握"区分开。
        was_abstain = bool(prev and prev.get("abstain"))
        reopened = bool(was_abstain and conf >= 0.35)
        out = {"fok": round(fok, 3), "tip": round(tip, 3), "confidence": round(conf, 3),
               "source": src, "counter_evidence": float(counter_evidence),
               "abstain": bool(conf < 0.35 and fok < 0.6),
               "strategy": "ask_user" if conf < 0.35 else "answer",
               "reopened": reopened}
        if prev is not None:
            out["prev_confidence"] = round(float(prev.get("confidence", 0.0)), 3)
        self.log.append({"t": now, **out})
        return out


# §7.1 情绪概念库：范畴由 (核心情感区域 + 情境预测) 共同决定，允许多范畴竞争
CONCEPTS = [
    {"name": "焦虑", "v": (-1.0, -0.05), "a": (0.55, 1.0), "d": (-1.0, 0.0),
     "context": (" deadline", "赶", "来不及", "怕", "担心", "考核")},
    {"name": "委屈", "v": (-1.0, -0.15), "a": (0.2, 0.7), "d": (-1.0, -0.05),
     "context": ("否定", "误解", "不公平", "没出路", "被说")},
    {"name": "低落", "v": (-1.0, -0.2), "a": (0.0, 0.45), "d": (-1.0, 0.1),
     "context": ("累", "空", "没意思", "落榜", "分开")},
    {"name": "专注", "v": (-0.15, 0.35), "a": (0.4, 0.75), "d": (0.0, 1.0),
     "context": ("暗房", "冲", "拍", "调", "做")},
    {"name": "轻快", "v": (0.25, 1.0), "a": (0.45, 1.0), "d": (-0.2, 1.0),
     "context": ("成了", "获奖", "个展", "开心", "顺利")},
    {"name": "舒展", "v": (0.2, 1.0), "a": (0.0, 0.5), "d": (-0.2, 1.0),
     "context": ("休息", "散步", "江边", "安静")},
    {"name": "警觉", "v": (-0.3, 0.2), "a": (0.65, 1.0), "d": (-0.3, 0.4),
     "context": ("陌生", "突然", "黑", "响")},
]


def construct_emotion(affect, situation="", now=None):
    """把 core affect + 情境范畴化成一个情绪实例。

    简并性：同一 PAD 区域可落到不同概念，由情境预测决定；
    没有情境支持时给"未分化"，不硬贴标签。
    """
    v = affect.state["valence"]
    a = affect.state["arousal"]
    d = affect.state["dominance"]
    cands = []
    for c in CONCEPTS:
        if not (c["v"][0] <= v <= c["v"][1] and c["a"][0] <= a <= c["a"][1]
                and c["d"][0] <= d <= c["d"][1]):
            continue
        ctx = sum(1 for k in c["context"] if k.strip() and k.strip() in situation)
        # 区域中心距离越小越典型
        cv = (c["v"][0] + c["v"][1]) / 2
        ca = (c["a"][0] + c["a"][1]) / 2
        cd = (c["d"][0] + c["d"][1]) / 2
        dist = math.sqrt((v - cv) ** 2 + (a - ca) ** 2 + (d - cd) ** 2)
        score = 1.0 / (0.3 + dist) + 0.8 * ctx
        cands.append((score, c["name"], ctx))
    if not cands:
        return {"concept": "未分化", "confidence": 0.2, "core_affect": dict(affect.state),
                "appraisal": {"valence": v, "arousal": a, "dominance": d}}
    cands.sort(reverse=True)
    total = sum(s for s, _, _ in cands)
    top = cands[0]
    return {"concept": top[1], "confidence": round(top[0] / total, 3),
            "alternatives": [n for _, n, _ in cands[1:3]],
            "core_affect": dict(affect.state),
            "appraisal": {"valence": round(v, 3), "arousal": round(a, 3),
                          "dominance": round(d, 3), "context_hits": top[2]}}


class Regulation:
    """情绪调节：策略库 + 情境选择 + 反馈监控 + 反刍检测。"""

    def __init__(self):
        self.history = []
        self.thoughts = []

    def select(self, intensity, controllability, situation=""):
        """Sheppes：高强度→早期脱离；低强度→晚期 engaged。
        Troy：可控→改情境；不可控→改情绪。
        Gross 五族补全（2026-11-22）：
          - situation_selection：极高强度且几乎不可控——唯一有效的是不再暴露
          - response_modulation：极强但完全可控、情境要求立刻顶住——短期压制，
            健康度最低，仅限应急（STRATEGY_HEALTH 里那两个一直没被选到的族）
        """
        intensity = _clamp(float(intensity), 0.0, 1.0)
        controllability = _clamp(float(controllability), 0.0, 1.0)
        if intensity >= 0.90 and controllability < 0.15:
            fam = "situation_selection"    # 极端:先离开现场再说
        elif intensity >= 0.90 and controllability >= 0.80:
            fam = "response_modulation"    # 极端:必须稳住表现,先压住
        elif intensity >= 0.7:
            fam = "attentional_deployment"   # Sheppes:高强度分心优于重构
        elif controllability >= 0.5:
            fam = "situation_modification"
        else:
            fam = "cognitive_change"
        return {"family": fam, "health": STRATEGY_HEALTH[fam],
                "intensity": round(intensity, 3), "controllability": round(controllability, 3),
                "note": "suppression 仅短期应急" if fam == "response_modulation" else ""}

    def apply(self, affect, choice, now=None):
        now = time.time() if now is None else now
        fam = choice["family"]
        eff = {"attentional_deployment": (-0.25, 0.0),
               "cognitive_change": (0.20, -0.10),
               "situation_modification": (0.15, -0.05),
               "situation_selection": (0.12, -0.08),
               "response_modulation": (0.02, 0.05)}[fam]
        before = dict(affect.state)
        affect.appraise(valence=eff[0], arousal=eff[1], weight=0.6)
        rec = {"t": now, "family": fam, "before": before, "after": dict(affect.state),
               "health": choice["health"]}
        self.history.append(rec)
        return rec

    def monitor(self, affect, choice):
        """反馈监控：没改善就换族（Bonanno 灵活性），不固定"健康"标签。"""
        if not self.history:
            return None
        last = self.history[-1]
        dv = last["after"]["valence"] - last["before"]["valence"]
        if dv <= 0.01:
            alt = "cognitive_change" if choice["family"] != "cognitive_change" else "attentional_deployment"
            return {"switch_to": alt, "reason": "上一策略无改善"}
        return {"keep": choice["family"]}

    def note_thought(self, text, valence, self_focused=True, now=None):
        now = time.time() if now is None else now
        self.thoughts.append({"t": now, "text": str(text), "v": float(valence),
                              "self": bool(self_focused)})
        self.thoughts = self.thoughts[-RUMINATION_WINDOW:]
        return self.ruminating()

    def ruminating(self):
        """Aldao：重复 + 负面 + 自我聚焦 + 无进展 = 反刍。"""
        neg = [x for x in self.thoughts if x["v"] < -0.1 and x["self"]]
        if len(neg) < RUMINATION_MIN:
            return False
        keys = [x["text"][:12] for x in neg]
        repeated = len(keys) - len(set(keys))
        return repeated >= 1 or len(neg) >= RUMINATION_MIN + 1

    def interrupt(self, affect, now=None):
        """检测到反刍 → 打断 + 换视角（时间距离化），而不是继续加正面重构。"""
        choice = {"family": "cognitive_change", "health": STRATEGY_HEALTH["cognitive_change"],
                  "intensity": 0.5, "controllability": 0.3, "note": "temporal distancing"}
        rec = self.apply(affect, choice, now=now)
        self.thoughts = []
        return {"interrupted": True, "strategy": "temporal_distancing", "record": rec}
