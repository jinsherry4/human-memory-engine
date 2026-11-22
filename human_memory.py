# -*- coding: utf-8 -*-
"""human_memory.py — 情景/自传记忆（研究规格版 v3）

按 HUMAN_LIKE_MIND_METHOD.md 落地，而不是按测试期望落地：

§5.1 四个独立指标：availability / accessibility / fidelity / confidence，不合成。
§5.2A variable-rate 编码：压缩速率 ∝ surprise；层级压缩先丢浅层感觉、保深层 gist。
§5.2B 可及性下降：干扰 + 抑制，存了找不到 ≠ 没存。
§5.3 多痕迹共存、潜在原因推断、NMPH 非单调可塑、提取练习调度（带正确答案反馈）、RIF。
§5.7 Bjork 双强度：SS 只增、RS 衰减；SS 延缓 RS 丢失；SS 增量随当前 RS 递减。
§5.8 再巩固：提取打开有界 labile 窗口，窗口内可更新，窗口外只能新建痕迹。
§7.2 ABC / Bisby：高唤醒优先丢 relational（when/where/result），保 item（who/what）。
§10  来源监控：experienced / told / imagined / inferred。

旧 store 字段全部保留；新字段缺失时按默认补齐，可直接加载 数据_dev。
"""

import math
import random
import time

from circuits import CA1, CA3, DentateGyrus, _stable_hash, encode, similarity
from persistence import load_json, save_json

# ---- 动力学常数（功能级拟合，需真实数据校准；见方法文档 §17 残余 4）----
RS_SAT = 2.0            # RS 归一化饱和点
RETIRE_RS = 0.03        # 低于此值判为 latent / 可退役
RECONSOL_HOURS = 5.0    # §5.8 再巩固窗口（数小时量级）
MIN_SPACING_HOURS = 0.1 # §5.3 desirable difficulty：6 分钟以内的即时提取几乎无增益
OPTIMAL_PRACTICE = 7    # §5.3 5–7 次成功提取后趋平
INHIB_TAU_HOURS = 24.0  # RIF 抑制的时间常数
SS_MAX = 6.0

# ---- §18.1 再巩固的两层（Dewa 2025 Nature / Beron 2025）----
# 原来只有"提取→labile→数小时重稳定"一个尺度。跨天尺度的证据表明：
# 单次提取只做**临时刷新**；长期稳定要"重复性 + 效价"共同过门槛。
FIRST_RETRIEVAL_GAIN = 0.35   # 首次提取只兑现 35% 的 SS 增益
DURABLE_RETRIEVALS = 2        # 累计提取达到此次数，才给满额（重复性门槛）
DURABLE_VALENCE = 0.5         # |效价| 达到此值视作情绪性记忆，一次即可稳定

# ---- §18.1 情境扩散层（Beron 2025）----
# 再激活一条记忆会回溯/前瞻地增强**同一情境**的外围记忆；情境一分离效应就消失。
# 因此门槛必须靠"共享情境锚"而不是"时间接近"，锚只取 raw full_episode。
CONTEXT_SPREAD_GAIN = 0.12    # 外围记忆分到目标 SS 增量的比例
CONTEXT_MIN_ANCHORS = 2       # 至少共享两个锚（who/where/when 中）才算同情境
CONTEXT_SPREAD_TRACE_MAX = 6  # 单条记忆的扩散痕迹上限，防 traces 无界膨胀

# ---- §18.2 离线回放按新旧分时（Chang 2025 Nature）----
# 同一 NREM 内，近期痕迹与已巩固旧痕迹分批回放，避免互相干扰。
RECENT_HOURS = 24.0

# 层级压缩顺序（§5.2A）：**知觉细节**先丢，深层语义最后丢。
#
# R130 更正（2026-11-22）：原实现把 "feel" 排在第一位、第一个丢。
# 查证后发现那是**术语误读**：
#   - §5.2A 引的 "Rugg 前移 / 概念重加权" 说的是**知觉性细节 vs 概念 gist**，
#     不是情感色彩；雯的 feel 字段 265 种取值全是情感状态（专注/平常/麻木/烦/
#     郑重/好奇/心疼…），没有一个是知觉细节。
#   - 情绪记忆这条线方法文档从未引用，而它结论相反：情绪记忆的**事实一致性**
#     与日常记忆一样衰减，但**鲜度/感受性/信心长期保持**
#     （Talarico & Rubin 2003, 2007）；情绪唤醒会**制造**记忆
#     （Cahill, Prins, Weber & McGaugh 1994, Nature）。
#   - 实测代价（R129 隔离副本实验）：把 feel 挪到最后 = **拿时间换情绪**
#     ——when 保留率 63% → 13.5%，feel 保留率 6.4% → 66%。
#
# → 情绪不是细节：**feel 不参与细节级压缩预算，也不参与丢弃**。
SHALLOW_FIRST = ("when", "where", "result", "why")
ITEM_CORE = ("who", "what")           # §7.2 item 保住
RELATIONAL = ("when", "where", "result")  # §7.2 relational 先受损

# 中文功能词二字片段：不参与文本覆盖打分，避免"第一/一张"这类偶然命中
STOP_GRAMS = {
    "我们", "你们", "他们", "这个", "那个", "什么", "怎么", "是不", "不是",
    "有没", "没有", "可以", "还是", "就是", "一个", "一张", "第一", "那次",
    "那年", "那天", "当时", "时候", "现在", "以前", "后来", "自己",
    "了以", "了吗", "的话",
}


def _grams(text):
    s = str(text)
    if len(s) < 2:
        return [s] if s else []
    return [s[i:i + 2] for i in range(len(s) - 1)]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class HumanMemory:
    def __init__(self, path=None, decay=0.5, affect=None):
        self.path = path
        self.decay = decay
        self.affect = affect
        self.memories = {}
        self.next_id = 0
        self.dg = DentateGyrus()
        self.ca3 = CA3()
        self.ca1 = CA1()
        self.goal = None          # §5.4 goal_relevance：由 set_goal 注入
        self.goal_vec = None
        self.replay_log = []

    # ---------- 目标（ABC 顶-down 优先级 / Amygdala relevance）----------
    def set_goal(self, goal_episode):
        self.goal = dict(goal_episode or {}) or None
        self.goal_vec = encode(self.goal) if self.goal else None
        for m in self.memories.values():
            m["relevance"] = self._relevance(m)
        return self

    def _relevance(self, m):
        if self.goal_vec is None:
            return 0.5
        s = similarity(m.get("vec") or encode(m.get("episode") or {}), self.goal_vec)
        return _clamp((s - 0.5) * 2.0, 0.0, 1.0)

    # ---------- 载入/保存 ----------
    def load(self):
        d = load_json(self.path, {}) or {}
        self.next_id = int(d.get("next_id", 0))
        for item in d.get("memories", []):
            item = dict(item)
            if "vec" not in item:
                item["vec"] = encode(item.get("full_episode") or item.get("episode") or {})
            if "pattern" not in item:
                item["pattern"] = self.dg.separate(item["vec"])
            else:
                item["pattern"] = frozenset(item["pattern"])
            item.setdefault("accesses", [item.get("created", time.time())])
            item.setdefault("arousal", 0.5)
            item.setdefault("valence", 0.0)
            item.setdefault("detail_kept", 1.0)
            item.setdefault("retired", False)
            item.setdefault("self_defining", False)
            item.setdefault("encoded_age", None)
            item.setdefault("durable", float(item.get("arousal", 0.5)) >= 0.6
                            or abs(float(item.get("valence", 0.0))) >= DURABLE_VALENCE)
            # --- v3 新字段：旧库缺失时按"已发生过一次编码"补齐 ---
            item.setdefault("ss", 0.6)
            item.setdefault("surprise", 0.5)
            item.setdefault("compression_rate", 0.0)
            item.setdefault("arousal_loss", 0.0)
            item.setdefault("fidelity", float(item.get("detail_kept", 1.0)))
            item.setdefault("source", "experienced")
            item.setdefault("traces", [{"t": item.get("created", time.time()),
                                        "episode": item.get("full_episode") or {},
                                        "source": "experienced", "kind": "original"}])
            item.setdefault("labile_until", 0.0)
            item.setdefault("practice", [])
            item.setdefault("n_success", 0)
            item.setdefault("inhibition", 0.0)
            item.setdefault("inhib_at", item.get("created", time.time()))
            item.setdefault("relevance", 0.5)
            item.setdefault("retrievals", 0)
            self.memories[item["id"]] = item
            self.ca3.store(item["pattern"], item["id"])
        # next_id 与现有 id 对账：陈旧/缺失的 next_id 不许造成静默覆盖
        max_id = -1
        for k in self.memories:
            if k.startswith("m") and k[1:].isdigit():
                max_id = max(max_id, int(k[1:]))
        self.next_id = max(self.next_id, max_id + 1)
        if self.goal_vec is not None:
            for m in self.memories.values():
                m["relevance"] = self._relevance(m)
        return self

    def save(self):
        payload = {"next_id": self.next_id, "memories": []}
        for m in self.memories.values():
            item = dict(m)
            item["pattern"] = sorted(item.get("pattern", []))
            payload["memories"].append(item)
        save_json(self.path, payload)
        return self

    # ---------- 编码 ----------
    @staticmethod
    def _context_anchors(m):
        """情境锚：只从 raw `full_episode` 取。

        压缩后的 `episode` 可能已经把 when/where 丢掉（§5.2A 先丢浅层时空线索），
        拿它当锚会把"同一情境"判成"不同情境"，也会把不同情境误并。
        """
        ep = m.get("full_episode") or {}
        out = {}
        for k in ("who", "where", "when"):
            v = ep.get(k)
            if v not in (None, ""):
                out[k] = str(v)
        return out

    @classmethod
    def _shared_context(cls, a, b):
        """返回两条记忆共享且取值相同的情境锚集合。"""
        A, B = cls._context_anchors(a), cls._context_anchors(b)
        return {k for k in A if k in B and A[k] == B[k]}

    def _surprise(self, vec):
        """新颖度代理：与已有记忆的最大相似度越低越惊讶。

        诚实标注：这是 Bayesian surprise 的代理量，不是精度加权预测误差
        （方法文档 §17 残余 2：需接真实生成模型）。
        """
        best = 0.5
        for m in self.memories.values():
            if m.get("retired"):
                continue
            s = similarity(vec, m.get("vec") or [])
            if s > best:
                best = s
        return _clamp((0.88 - best) / 0.38, 0.0, 1.0)

    def remember(self, episode, arousal=None, note="", valence=None, now=None,
                 min_age=None, dev_age=None, source="experienced", priority=None):
        if min_age is not None and dev_age is not None and dev_age < min_age:
            return None
        now = time.time() if now is None else now
        ep = {k: v for k, v in (episode or {}).items() if v not in (None, "")}
        if not ep:
            return None
        if dev_age is not None and dev_age < 3.0:
            return None
        if arousal is None:
            arousal = self.affect.arousal_level() if self.affect else 0.5
        arousal = _clamp(float(arousal), 0.0, 1.0)
        gain = 4.0 * arousal * (1.0 - arousal)          # 倒 U
        if valence is None:
            valence = self.affect.state["valence"] if self.affect else 0.0

        full_vec = encode(ep)
        surprise = self._surprise(full_vec)

        # §5.4 优先级 = 底-up 惊讶 + 顶-down 目标相关 + 情绪相关
        rel = 0.5
        if self.goal_vec is not None:
            rel = _clamp((similarity(full_vec, self.goal_vec) - 0.5) * 2.0, 0.0, 1.0)
        pri = _clamp(0.4 * surprise + 0.4 * rel + 0.2 * abs(float(valence)), 0.0, 1.0) \
            if priority is None else _clamp(float(priority), 0.0, 1.0)

        kept = dict(ep)
        n0 = len(ep)
        # 情绪不是细节：feel 不计入细节级压缩预算（见 SHALLOW_FIRST 的 R130 更正）。
        # 预算的分子分母都只算细节字段，于是"多留情绪"不会挤掉 when/where/result。
        _has_feel = "feel" in ep
        n_detail = max(1, n0 - (1 if _has_feel else 0))

        # --- A. variable-rate 压缩：冗余事件压缩更狠（§5.2A）---
        target_keep = 0.45 + 0.55 * surprise
        # ABC：高优先级项即使不唤醒也保细节
        target_keep = _clamp(target_keep + 0.25 * pri, 0.35, 1.0)
        dropped_compression = []
        compression_debt = 0.0
        for k in SHALLOW_FIRST:
            if (len(kept) - (1 if _has_feel else 0)) / n_detail <= target_keep:
                break
            if k in kept and k not in ITEM_CORE:
                # 保住至少一个时空锚点：情景记忆若丢掉全部 when/where，
                # 就退化成纯语义条目、再也无法被情境线索唤起（Conway ESK）。
                if k in ("when", "where") and not any(
                        x in kept and x != k for x in ("when", "where")):
                    # 想压却压不动：这份压缩落差记在保真度上
                    # （"记得这件事，但说不细"），而不是硬删线索字段。
                    compression_debt += 1.0 / max(1, n0)
                    continue
                kept.pop(k)
                dropped_compression.append(k)
        compression_rate = len(dropped_compression) / max(1, n0)

        # --- B. 高唤醒：item↑ relational↓（§7.2 Bisby），不是均匀随机丢 ---
        dropped_arousal = []
        if arousal > 0.85:
            loss = (arousal - 0.85) / 0.15 * 0.5
            rng = random.Random(_stable_hash(repr(sorted(ep.items()))) ^ int(arousal * 1000))
            for k in RELATIONAL:
                if k in kept and rng.random() < loss:
                    kept.pop(k)
                    dropped_arousal.append(k)
            if not dropped_arousal:
                # R130：feel 不参与丢弃（情绪是最后才该没的东西），
                # 兜底只从 why 里找。
                for k in RELATIONAL + ("why",):
                    if k in kept:
                        kept.pop(k)
                        dropped_arousal.append(k)
                        break
        arousal_loss = len(dropped_arousal) / max(1, n0)

        # --- C. 发育编码深度（年龄闸门）---
        if dev_age is not None:
            if dev_age < 6.0:
                allowed = ("who", "what")
            elif dev_age < 12.0:
                allowed = ("who", "what", "where", "when")
            elif dev_age < 15.0:
                allowed = ("who", "what", "where", "when", "feel", "why")
            else:
                allowed = tuple(kept.keys())
            kept = {k: v for k, v in kept.items() if k in allowed}

        vec = encode(kept)
        pat = self.dg.separate(vec)
        mid = "m%d" % self.next_id
        self.next_id += 1
        detail = len(kept) / max(1, n0)

        # §5.7 SS 初值：惊讶、优先级、唤醒增益共同决定"学得多牢"
        ss0 = _clamp(0.35 + 0.85 * surprise + 0.55 * gain * (0.4 + 0.6 * pri), 0.2, 2.2)

        self.memories[mid] = {
            "id": mid, "episode": kept, "full_episode": dict(ep),
            "vec": vec, "pattern": pat,
            "created": now, "accesses": [now], "arousal": arousal,
            "valence": float(valence), "detail_kept": round(detail, 3),
            "encoded_age": dev_age, "note": note, "retired": False,
            "self_defining": False,
            "durable": arousal >= 0.6 or abs(float(valence)) >= DURABLE_VALENCE,
            "gist": {k: kept.get(k) for k in ("who", "where", "when", "what") if kept.get(k)},
            # --- v3 ---
            "ss": round(ss0, 4),
            "surprise": round(surprise, 3),
            "priority": round(pri, 3),
            "compression_rate": round(compression_rate, 3),
            "arousal_loss": round(arousal_loss, 3),
            "fidelity": round(_clamp(detail - 0.5 * compression_debt, 0.35, 1.0), 3),
            "source": source,
            "traces": [{"t": now, "episode": dict(ep), "source": source, "kind": "original"}],
            "labile_until": 0.0,
            "practice": [], "n_success": 0,
            "inhibition": 0.0, "inhib_at": now,
            "relevance": round(rel, 3),
            "retrievals": 0,
        }
        self.ca3.store(pat, mid)
        return mid

    # ---------- §5.7 双强度动力学 ----------
    def ss(self, m):
        return float(m.get("ss", 0.6))

    def _inhib(self, m, now):
        inh = float(m.get("inhibition", 0.0))
        if inh <= 0:
            return 0.0
        dt = max(0.0, (now - m.get("inhib_at", now)) / 3600.0)
        return inh * math.exp(-dt / INHIB_TAU_HOURS)

    def rs(self, m, now=None):
        """提取强度 = 当前可及性。只由时间、提取次数、SS、抑制决定。

        SS 越大 → 有效衰减指数越小 → 忘得越慢（Bjork：SS 延缓 RS 丢失）。
        情绪不直接进 RS；情绪走编码增益(SS)与检索偏置(mood-congruent)。
        """
        now = time.time() if now is None else now
        ss = self.ss(m)
        d_eff = self.decay / (1.0 + 0.40 * ss)
        base = 0.0
        for t in (m.get("accesses") or [m.get("created", now)]):
            dt = max(1.0 / 60.0, (now - t) / 3600.0)
            base += dt ** (-d_eff)
        return base / (1.0 + self._inhib(m, now))

    def _ss_gain(self, m, now, rs_now=None, correct=True):
        """SS 增量：随当前 RS 递减（desirable difficulty），随成功次数趋平。"""
        if not correct:
            return 0.0
        rs_now = self.rs(m, now) if rs_now is None else rs_now
        rs_norm = _clamp(rs_now / RS_SAT, 0.0, 1.0)
        n = int(m.get("n_success", 0))
        plateau = _clamp(1.0 - n / float(OPTIMAL_PRACTICE), 0.05, 1.0)
        return 0.45 * (1.0 - 0.75 * rs_norm) * plateau

    def _grow_ss(self, m, delta):
        m["ss"] = round(min(SS_MAX, self.ss(m) + max(0.0, delta)), 4)

    # ---------- §5.3 提取练习调度 ----------
    def next_practice_at(self, m):
        """等间隔调度（长时程等间隔 > 扩展间隔），最小间隔保证 desirable difficulty。"""
        n = int(m.get("n_success", 0))
        last = m.get("accesses", [m.get("created", 0)])[-1]
        gap_h = max(MIN_SPACING_HOURS, 6.0 * (n + 1))
        return last + gap_h * 3600.0

    def rehearse(self, mid, correct, correction=None, now=None, source="practice"):
        """带正确答案反馈的提取练习。

        §5.3：无反馈地反复提取错误会强化错误 → 答错且无纠正时，
        不增 SS，并把错误内容作为 error 痕迹记下来（可被来源监控识别）。
        """
        now = time.time() if now is None else now
        m = self.memories.get(mid)
        if not m:
            return None
        last = (m.get("accesses") or [m.get("created", now)])[-1]
        spacing_h = (now - last) / 3600.0
        spaced = spacing_h >= MIN_SPACING_HOURS
        rec = {"t": now, "correct": bool(correct), "spacing_h": round(spacing_h, 3)}
        rs_before = self.rs(m, now)   # 提取前 RS：desirable difficulty 的基准
        m.setdefault("practice", []).append(rec)
        m["practice"] = m["practice"][-32:]
        m.setdefault("accesses", []).append(now)
        m["accesses"] = m["accesses"][-16:]
        gain = 0.0
        if correct:
            m["n_success"] = int(m.get("n_success", 0)) + 1
            if spaced:
                gain = self._ss_gain(m, now, rs_now=rs_before)
                self._grow_ss(m, gain)
                m["fidelity"] = round(min(1.0, float(m.get("fidelity", 1.0)) + 0.03), 3)
            rec["ss_gain"] = round(gain, 4)
        else:
            if correction is not None:
                # 有正确答案反馈 → 修订痕迹，不强化错误
                m.setdefault("traces", []).append(
                    {"t": now, "episode": dict(correction), "source": source, "kind": "corrected"})
                m["fidelity"] = round(min(1.0, float(m.get("fidelity", 1.0)) + 0.02), 3)
            else:
                # 无反馈：错误被强化，保真度下降（DRM 边界，§5.8）
                m.setdefault("traces", []).append(
                    {"t": now, "episode": {}, "source": source, "kind": "error"})
                m["fidelity"] = round(max(0.2, float(m.get("fidelity", 1.0)) - 0.08), 3)
        m["labile_until"] = now + RECONSOL_HOURS * 3600.0
        return rec

    # ---------- §5.3 / §5.8 更新 vs 新建 ----------
    def update_or_new(self, episode, now=None, source="experienced", **kw):
        """潜在原因推断 + NMPH + 再巩固窗口，决定是更新旧痕迹还是新建。

        返回 (mid, decision)。decision ∈ {new, integrate, differentiate}
        """
        now = time.time() if now is None else now
        ep = {k: v for k, v in (episode or {}).items() if v not in (None, "")}
        if not ep:
            return None, "empty"
        vec = encode(ep)
        best, best_sim = None, 0.0
        for m in self.memories.values():
            if m.get("retired"):
                continue
            s = similarity(vec, m.get("vec") or [])
            if s > best_sim:
                best, best_sim = m, s
        if best is None or best_sim < 0.62:
            return self.remember(ep, now=now, source=source, **kw), "new"

        # 潜在原因推断：why/result 变了 → 新原因 → 新痕迹（Gershman）
        old = best.get("full_episode") or {}
        cause_changed = any(ep.get(k) and old.get(k) and ep[k] != old[k]
                            for k in ("why", "result"))
        if cause_changed:
            return self.remember(ep, now=now, source=source, **kw), "new"

        # NMPH：中等共激活 → 弱化/分化；高共激活 → 强化/整合
        if best_sim < 0.80:
            best["inhibition"] = round(float(best.get("inhibition", 0.0)) + 0.35, 3)
            best["inhib_at"] = now
            return self.remember(ep, now=now, source=source, **kw), "differentiate"

        if now <= float(best.get("labile_until", 0.0)):
            # 窗口内：允许修订，但 raw 永不覆盖
            best.setdefault("traces", []).append(
                {"t": now, "episode": dict(ep), "source": source, "kind": "update"})
            merged = dict(best.get("episode") or {})
            merged.update({k: v for k, v in ep.items() if v})
            best["episode"] = merged
            best["vec"] = encode(merged)
            best["pattern"] = self.dg.separate(best["vec"])
            self.ca3.store(best["pattern"], best["id"])   # 吸引子同步，防陈旧模式
            best["gist"] = {k: merged.get(k) for k in ("who", "where", "when", "what") if merged.get(k)}
            self._grow_ss(best, 0.15)
            best["labile_until"] = now + RECONSOL_HOURS * 3600.0
            return best["id"], "integrate"
        # 窗口外：不突变，另建痕迹
        return self.remember(ep, now=now, source=source, **kw), "new"

    # ---------- 巩固 + 变换性回放（§6.1）----------
    def consolidate(self, now=None, replay=True):
        now = time.time() if now is None else now
        retired = 0
        replayed = 0
        recombined_n = 0
        batch_counts = {}
        if replay:
            # prioritized replay：弱记忆回放更多，惊讶/自我相关优先
            act = [m for m in self.memories.values() if not m.get("retired")]
            def prio(m):
                weak = 1.0 / (0.2 + self.rs(m, now))
                return weak * (0.5 + m.get("surprise", 0.5)) * (
                    2.0 if m.get("self_defining") else 1.0)
            # §18.2 分时回放：近期痕迹与已巩固旧痕迹分批处理，不在同一批里交错。
            # 依据 Chang 2025：同一 NREM 内收缩瞳孔亚态回放近期、扩张亚态回放旧记忆，
            # 分时避免新旧表征互相干扰。功能类比，非动物机制移植。
            cut = now - RECENT_HOURS * 3600.0
            buckets = (
                ("recent", [m for m in act if float(m.get("created", 0)) >= cut]),
                ("old", [m for m in act if float(m.get("created", 0)) < cut]),
            )
            for tag, bucket in buckets:
                if not bucket:
                    batch_counts[tag] = 0
                    continue
                bucket.sort(key=prio, reverse=True)
                n_tag = 0
                for m in bucket[:max(1, len(bucket) // 3)]:
                    # 变换性回放：只回放 gist（压缩），不是忠实重播
                    g = m.get("gist") or {}
                    if not g:
                        continue
                    m.setdefault("traces", []).append(
                        {"t": now, "episode": dict(g), "source": "replay",
                         "kind": "gist_replay", "batch": tag})
                    m["traces"] = m["traces"][-24:]
                    self._grow_ss(m, 0.12 * (0.4 + m.get("surprise", 0.5)))
                    # gist 化：回放提升可及性但降低细节保真（§5.3 提取把表征感觉→语义）
                    m["fidelity"] = round(max(0.35, float(m.get("fidelity", 1.0)) - 0.015), 3)
                    # §6.1 变换性回放·重组：同情境的另一条记忆与它交叉成新痕迹。
                    # 只记 recombined 痕迹（来源=回放，来源监控可识别，Xue 2025 的
                    # recombination），不改写可答表征——DRM 式伪记忆是这道机制的
                    # 已知边界（§5.8），由 trace 来源标记负责，不硬拦。
                    if recombined_n < 3:
                        for oid, other in self.memories.items():
                            if oid == m["id"] or other.get("retired"):
                                continue
                            if len(self._shared_context(m, other)) >= CONTEXT_MIN_ANCHORS:
                                og = other.get("gist") or {}
                                m.setdefault("traces", []).append(
                                    {"t": now, "source": "replay", "kind": "recombined",
                                     "with": oid, "batch": tag,
                                     "episode": {"what": "%s；%s" % (
                                         str(g.get("what") or "")[:20],
                                         str(og.get("what") or "")[:20]),
                                         "who": g.get("who") or og.get("who")}})
                                m["traces"] = m["traces"][-24:]
                                recombined_n += 1
                                break
                    replayed += 1
                    n_tag += 1
                batch_counts[tag] = n_tag
            self.replay_log.append({"t": now, "n": replayed, "batches": batch_counts})
            self.replay_log = self.replay_log[-64:]
        for m in self.memories.values():
            if m.get("retired"):
                continue
            if m.get("self_defining") or m.get("durable") and self.ss(m) >= 2.0:
                continue
            if self.rs(m, now) < RETIRE_RS:
                m["retired"] = True
                retired += 1
        return {"retired": retired, "replayed": replayed, "batches": batch_counts,
                "active": sum(1 for m in self.memories.values() if not m.get("retired"))}

    # ---------- §6.1 睡眠两阶段 ----------
    def sleep(self, now=None, hours=8.0):
        """SWS（系统巩固）→ REM（突触巩固），两阶段做的事不同。

        SWS：低 ACh，海马重激活 → 变换性回放 + 蒸馏到语义（redistribution）。
        REM：高 ACh，可塑基因表达 → 强化已回放痕迹的皮层突触（SS 再涨一点），
             但不引入新内容。清醒静息不做这一步。
        """
        now = time.time() if now is None else now
        sws_end = now + hours * 0.6 * 3600.0
        rem_end = now + hours * 3600.0
        sws = self.consolidate(now=sws_end, replay=True)
        strengthened = 0
        for m in self.memories.values():
            if m.get("retired"):
                continue
            traces = m.get("traces") or []
            if any(t.get("kind") == "gist_replay" and t.get("t", 0) >= now for t in traces):
                self._grow_ss(m, 0.08 * (0.5 + m.get("surprise", 0.5)))
                strengthened += 1
        return {"sws": sws, "rem": {"strengthened": strengthened},
                "stages": ["SWS", "REM"], "end": rem_end}

    # ---------- 检索 ----------
    @staticmethod
    def _text_score(cue, episode):
        """加权二字片段覆盖率，而不是"任意片段命中即满分"。

        整串命中给 1.0；否则按去停用词后的片段覆盖比例给分。
        长问句里偶然出现"第一/一张"不再能把无关记忆抬到满分。
        """
        vals = [str(v) for v in cue.values() if v not in (None, "", False)]
        if not vals:
            return 0.0
        hay = " ".join(str(v) for v in episode.values() if v not in (None, ""))
        if not hay:
            return 0.0
        total, hit = 0.0, 0.0
        for v in vals:
            if v and v in hay:
                total += 1.0
                hit += 1.0
                continue
            gs = [g for g in _grams(v) if g not in STOP_GRAMS]
            if not gs:
                gs = _grams(v)
            if not gs:
                continue
            found = sum(1 for g in gs if g in hay)
            total += 1.0
            hit += found / float(len(gs))
        return hit / total if total else 0.0

    @staticmethod
    def _core_hit(cue, m):
        """线索的**语义核心字段**（what/feel/when）是否落在这条记忆里。

        只靠"谁/在哪"对上的匹配不算数——那是跨字段凑数：线索 {高中,老师,相机}
        能凑上"高中班主任找我谈话"（历史教训 a02：把没发生过的事答成了回忆）。
        """
        ep = m.get("full_episode") or m.get("episode") or {}
        hay = " ".join(str(v) for v in ep.values() if v)
        for k in ("what", "feel", "when"):
            v = cue.get(k)
            if v and str(v) in hay:
                return True
        return False

    def recall(self, cue, top_k=3, now=None, reinforce=True):
        """检索：DG 硬重叠 + HDC 软相似 + 文本覆盖 → 匹配度；
        再乘 RS（可及性）与 mood-congruent 偏置排序。

        reinforce=False 时为只读探针，不写 accesses、不改状态。
        """
        now = time.time() if now is None else now
        cue = {k: v for k, v in (cue or {}).items() if v not in (None, "", False)}
        flags = {k: v for k, v in cue.items() if k.startswith("_")}
        cue = {k: v for k, v in cue.items() if not k.startswith("_")}
        if not cue:
            return {"best": None, "gist_best": None, "results": [],
                    "ca3": None, "overlap": 0.0, "confidence": 0.0,
                    "spread": [], "novel": True}
        has_photo = bool(flags.get("_photo"))
        has_specific = bool(flags.get("_specific"))
        has_revive = bool(flags.get("_revive"))
        cue_vec = encode(cue)
        cue_pat = self.dg.separate(cue_vec)

        # CA3 模式完成：残缺线索收敛到吸引子（只在允许集合内）
        allow = {mid for mid, m in self.memories.items()
                 if not m.get("retired") or has_photo or has_revive or len(cue) >= 3}
        ca3_id, ca3_overlap, _ = self.ca3.recall(cue_pat, allow=allow)

        scored = []
        for m in self.memories.values():
            if m["id"] not in allow:
                continue
            soft = similarity(cue_vec, m.get("vec") or [])
            hard = len(cue_pat & (m.get("pattern") or frozenset())) / max(1, len(cue_pat))
            # 线索匹配要对齐**编码时的痕迹**，不是压缩后的表征：
            # 分层压缩丢的是"她现在能讲出多少"，不是"当年到底编码了什么"。
            # 问句线索来自知道这件事的人，它匹配的是原始痕迹（编码特异性，
            # Tulving）；这正是 §5.1-3 线索化可及性的机制含义。
            search_ep = m.get("full_episode") or m.get("episode") or {}
            txt = self._text_score(cue, search_ep)
            # 逐字命名：what 线索足够长且与某条记忆的 what 互为子串，
            # 等于点名了那条记忆——匹配加分，压过靠复刷堆出来的 RS 优势
            what_cue = str(cue.get("what") or "")
            ep_what = str(search_ep.get("what") or "")
            named = (len(what_cue) >= 6 and len(ep_what) > 0
                     and (what_cue in ep_what or ep_what in what_cue))
            # 候选资格（ACT-R 部分匹配的失配惩罚）：与线索毫无实质重合的痕迹
            # 不能只靠"本身很强"挤进候选。否则一条 RS 很高的无关记忆会占住
            # top，把逐字命中但已淡出的那条挤出视野——过门只看 top，就永远漏检。
            if not (txt >= 0.25 or hard >= 0.20 or soft >= 0.70 or named):
                continue
            match = 0.40 * soft + 0.25 * hard + 0.35 * txt + (0.12 if named else 0.0)
            rs_v = self.rs(m, now)
            rs_w = 0.35 + 0.65 * _clamp(rs_v / RS_SAT, 0.0, 1.0)
            bias = self.affect.recall_bias(m.get("valence", 0.0)) if self.affect else 1.0
            # ABC 顶-down：与当前目标相关的记忆被增强（哪怕它本身不唤醒）
            goal_w = 0.85 + 0.30 * float(m.get("relevance", 0.5))
            score = match * rs_w * bias * goal_w
            scored.append((score, soft, hard, txt, rs_v, m))
        scored.sort(key=lambda x: x[0], reverse=True)

        def _mk_result(row):
            score, soft, hard, txt, rs_v, m = row
            dk = m.get("detail_kept", 1.0)
            fid = float(m.get("fidelity", dk))
            detail = "full" if fid >= 0.8 else ("gist" if fid <= 0.55 else "partial")
            return {
                "id": m["id"], "episode": m.get("episode"),
                "full_episode": m.get("full_episode"),
                "score": round(score, 3), "similarity": round(soft, 3),
                "dg_overlap": round(hard, 3), "text": round(txt, 3),
                "detail_level": detail, "detail_kept": dk,
                "retired": bool(m.get("retired")),
                # §5.1 四指标，各自独立。accessible/latent 是**线索相对**的
                # （Tulving 编码特异性）：本次线索是否真能提出、有痕但提不出；
                # rs/ss 是存储侧痕迹属性，不因线索强弱改变。
                "availability": bool(m.get("full_episode")),
                "accessible": False,
                "fidelity": round(fid, 3),
                "rs": round(rs_v, 3), "ss": round(self.ss(m), 3),
                "latent": bool(m.get("full_episode")),
                "recovered_from_latent": False,
                "source": m.get("source", "experienced"),
                "traces": len(m.get("traces") or []),
                "reinforced": False,
                "reinforce_layer": None,
            }

        results = [_mk_result(row) for row in scored[:top_k]]

        # 逐字命名优先：cue 长文本几乎逐字落在某条记忆的 what 里 = 点名了那条记忆。
        # 必须在**全体候选**里判定，不能只看 top_k——否则一条被反复复刷、
        # RS 堆得很高的无关记忆会把它挤出候选，命名检索就名存实亡
        # （历史教训 p07：cue.what="爸爸说摄影没出路" 被挤到 top-3 之外）。
        # 命中后直接置顶：被点名的记忆不该被复刷优势挤掉
        # （提取练习的富者愈富不该改写命名检索，Tulving 编码特异性）。
        cue_chars = sum(len(str(v)) for v in cue.values())
        what_cue = str(cue.get("what") or "")
        if cue_chars >= 6 and what_cue:
            for row in scored:
                m = row[5]
                tw = str((m.get("full_episode") or m.get("episode") or {}).get("what") or "")
                if not tw or not (what_cue in tw or tw in what_cue):
                    continue
                if row[3] < 0.98:
                    continue
                named = _mk_result(row)
                results = [named] + [r for r in results if r["id"] != named["id"]]
                break

        # ---- 过门 ----
        # 线索的"信息量"不等于字段个数：单字段但取值长且逐字命中，
        # 比三个泛泛的字段更特异（cue overload / fan effect）。
        #
        # 证据优先于 RS：线索越具体、命中越多，越该由"对得上的那条"胜出，
        # 而不是由"最近被复刷过的那条"（RS 优势）胜出——提取练习的富者愈富
        # 不该改写线索检索（Tulving 编码特异性）。
        # 两条限制，否则会变成编造：
        #   1. 只在 ≥3 字段的线索、命中 ≥60% 字段、且比当前 top 高出 0.25 以上
        #      时才让证据条顶上（历史教训 k01：学校+暑假+震动 这条线索对上
        #      "第一次进暗房"两处，却被"看电影"那条按 RS 挤掉）；
        #   2. **匹配里必须含语义核心字段**（what/feel/when）。只靠
        #      谁/在哪对上的不算——那是跨字段凑数（历史教训 a02：线索是
        #      {高中,老师,相机}，顶上来的却是"高中班主任找我谈话"，
        #      跟"被没收相机"根本不是一回事）。
        if len(cue) >= 3 and results:
            evid = None
            for row in scored:
                if row[3] < 0.60:
                    continue
                if not self._core_hit(cue, row[5]):
                    continue
                if evid is None or row[3] > evid[3]:
                    evid = row
            if evid is not None and (evid[3] - results[0]["text"]) >= 0.25:
                ev = _mk_result(evid)
                results = [ev] + [r for r in results if r["id"] != ev["id"]]

        margin = (results[0]["score"] - results[1]["score"]) if len(results) > 1 else 1.0
        best = None
        if results:
            top = results[0]
            n = len(cue)
            # 逐字命名优先：cue 长文本几乎逐字落在某条记忆里 = 点名了那条记忆。
            # 它应直接中选,不被复刷堆出来的 RS 优势挤掉——提取练习的富者愈富
            # 不该改写命名检索(Tulving 编码特异性)
            verbatim = None
            if cue_chars >= 6:
                for res in results:
                    if res["text"] >= 0.98:
                        verbatim = res
                        break
            if verbatim is not None:
                best = verbatim["id"]
            elif (n >= 2 and top["text"] >= 0.60) or (n >= 3 and top["text"] >= 0.42):
                best = top["id"]
            elif has_specific and n >= 1 and top["text"] >= 0.85:
                best = top["id"]
            elif top["text"] >= 0.95 and cue_chars >= 6:
                # 近逐字长线索几乎点名了那条记忆：不必再要求与次名拉开间隔
                best = top["id"]
            elif top["text"] >= 0.85 and cue_chars >= 4 and margin >= 0.15:
                best = top["id"]
            elif n >= 3 and top["similarity"] >= 0.82 and top["text"] >= 0.30:
                best = top["id"]
            elif ca3_id == top["id"] and ca3_overlap >= 0.55 and top["text"] >= 0.45:
                best = top["id"]
            # 注意：这里**不**按 accessible 一刀切。可及性是线索依赖的
            # （Tulving 编码特异性）：足够丰富的重现线索能把 latent 痕迹唤回，
            # 这正是 §5.6-3 的 β 恢复。弱线索过不了上面的门，仍表现为"想不起"。

        # gist_best 必须与对外 top 同一条，避免"说的是A、top是B"
        gist_best = None
        if (best is None and results and results[0]["text"] >= 0.30
                and (len(cue) >= 2 or cue_chars >= 4)
                and results[0]["availability"]):
            gist_best = results[0]["id"]

        if best is not None:
            for res in results:
                if res["id"] == best:
                    # 过门 = 本次线索下真正可提取；rs 低于退役阈值却被强线索
                    # 拉回 = §5.6-3 的 β 恢复（存储侧真 latent，线索侧唤回）
                    res["accessible"] = True
                    res["latent"] = False
                    if res["rs"] < RETIRE_RS:
                        res["recovered_from_latent"] = True

        spread = []
        if best is not None and reinforce:
            m = self.memories[best]
            rs_before = self.rs(m, now)   # 提取前 RS：desirable difficulty 的基准
            m.setdefault("accesses", []).append(now)
            m["accesses"] = m["accesses"][-16:]
            m["retrievals"] = int(m.get("retrievals", 0)) + 1
            m["labile_until"] = now + RECONSOL_HOURS * 3600.0   # §5.8 打开窗口
            # §18.1 两层再巩固：单次提取只兑现 FIRST_RETRIEVAL_GAIN 的 SS 增量
            # （临时刷新，情绪记忆靠天尺度重稳定）；累计到 DURABLE_RETRIEVALS 次
            # 或本身是高|效价|的情绪性记忆，才按满额加固。
            n_ret = int(m["retrievals"])
            durable = (n_ret >= DURABLE_RETRIEVALS
                       or abs(float(m.get("valence", 0.0))) >= DURABLE_VALENCE)
            scale = 1.0 if durable else FIRST_RETRIEVAL_GAIN
            self._grow_ss(m, self._ss_gain(m, now, rs_now=rs_before) * scale)
            layer = "durable" if durable else "labile_only"
            # §5.3 提取把表征推向语义：可及性升、细节保真略降
            m["fidelity"] = round(max(0.35, float(m.get("fidelity", 1.0)) - 0.01), 3)
            for res in results:
                if res["id"] == best:
                    res["reinforced"] = True
                    res["reinforce_layer"] = layer
                    m["last_retrieval_conf"] = res["score"]   # §10 校准数据源
                elif res["score"] >= 0.25:
                    # RIF：竞争项被抑制
                    c = self.memories[res["id"]]
                    c["inhibition"] = round(float(c.get("inhibition", 0.0)) + 0.20, 3)
                    c["inhib_at"] = now

            # §18.1 情境扩散层（Beron 2025）：目标被再激活时，同一情境里的外围记忆
            # 一起获得小幅 SS 增强，回溯（更早）与前瞻（更晚）都算。两个硬约束：
            #   1) 锚取自 raw `full_episode`，压缩后的 episode 可能已丢掉 when/where；
            #   2) **只加 SS、不开 labile 窗口**——扩散给的是稳定度，不是改写权。
            #      错误会被一起扩散（§5.8 DRM 边界），所以绝不让外围记忆跟着进入可修订态。
            for oid, other in self.memories.items():
                if oid == best or other.get("retired"):
                    continue
                if len(self._shared_context(m, other)) < CONTEXT_MIN_ANCHORS:
                    continue
                self._grow_ss(other, self._ss_gain(other, now) * CONTEXT_SPREAD_GAIN)
                tr = other.setdefault("traces", [])
                old_spread = [x for x in tr if x.get("kind") == "context_spread"]
                if len(old_spread) >= CONTEXT_SPREAD_TRACE_MAX:
                    tr.remove(old_spread[0])
                tr.append({"t": now, "episode": {}, "source": "spread",
                           "kind": "context_spread", "from": best})
                spread.append(oid)

        return {"best": best, "gist_best": gist_best, "results": results,
                "ca3": ca3_id, "overlap": round(results[0]["text"], 2) if results else 0.0,
                "confidence": round(results[0]["score"], 2) if results else 0.0,
                "spread": spread, "novel": best is None}
