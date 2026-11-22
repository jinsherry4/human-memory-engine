# -*- coding: utf-8 -*-
"""insight_engine.py — 灵光一闪（P6，EII / CLARION 计算类比）

严格按 HUMAN_LIKE_MIND_METHOD.md §8.2–8.3：
  不是随机 top-k、不是纯图扩散、不是自由联想。
  僵局检测 → 约束松弛（只放松非事实约束）→ 高温远程联想（排除习惯近邻）
  → 显隐式 Max 整合 → ICL 取分布众数 → 双独立路径 + 阈值 → 点火广播
  → 入独立慢校验队列；未过校验只标 insight_candidate，绝不写成事实。
  未达阈值 → 溯因反传 + 残差累积（incubation 靠残差携带，不靠随机）。

诚实标注：ICL/温度/阈值是功能级拟合，Aha 强度 ≠ 正确性（Metcalfe & Wiebe）。
"""

import math
import random
import time

IMPASSE_ATTEMPTS = 3
COOLDOWN_HOURS = 2.0
TEMP_HIGH = 1.6
SOLUTION_THRESHOLD = 0.62
HUNCH_THRESHOLD = 0.40
RESIDUAL_TAU_HOURS = 12.0


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class InsightEngine:
    def __init__(self, sem=None, workspace=None, affect=None, seed=7):
        self.sem = sem
        self.wm = workspace
        self.affect = affect
        self.rng = random.Random(seed)
        self.attempts = {}
        self.last_fire = -1e9
        self.residual = {}
        self.candidates = []
        self.verification_queue = []
        self.fired = []

    # ---------- A 僵局 ----------
    def note_attempt(self, problem_key, success=False, now=None):
        now = time.time() if now is None else now
        rec = self.attempts.setdefault(problem_key, {"n": 0, "fail": 0, "t": now})
        rec["n"] += 1
        rec["t"] = now
        if success:
            rec["fail"] = 0
        else:
            rec["fail"] += 1
        return rec

    def detect_impasse(self, problem_key):
        rec = self.attempts.get(problem_key)
        return bool(rec and rec["fail"] >= IMPASSE_ATTEMPTS)

    def cooldown_active(self, now):
        return (now - self.last_fire) < COOLDOWN_HOURS * 3600.0

    # ---------- B 约束松弛 ----------
    @staticmethod
    def extract_constraints(problem):
        return list(problem.get("constraints") or [])

    @staticmethod
    def relax_one_unwarranted(constraints):
        """只放松"没根据的假设"，绝不放松事实/边界（hard=True）。"""
        soft = [c for c in constraints if not c.get("hard")]
        if not soft:
            return constraints, None
        dropped = soft[-1]
        return [c for c in constraints if c is not dropped], dropped

    # ---------- C 高温远程联想 ----------
    def _reachable(self, core, hops=3, now=None):
        """从僵局核心做 BFS，记录每个事实到核心的最短跳数与可达邻居。"""
        if not self.sem:
            return {}, {}
        seeds = [f["id"] for f in self.sem.ask(core, top_k=3, now=now)]
        dist = {sid: 0 for sid in seeds}
        adj = {}
        for e in self.sem.edges:
            a, b = e.get("from"), e.get("to")
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        frontier = list(seeds)
        for h in range(1, hops + 1):
            nxt = []
            for nid in frontier:
                for nb in adj.get(nid, ()):
                    if nb not in dist:
                        dist[nb] = h
                        nxt.append(nb)
            frontier = nxt
            if not frontier:
                break
        return dist, adj

    def remote_walk(self, entities, exclude=None, hops=3, temp=TEMP_HIGH, now=None):
        if not self.sem or not entities:
            return []
        exclude = set(exclude or [])
        core = entities[0]
        dist, adj = self._reachable(core, hops=hops, now=now)
        self._adj = adj
        self._dist = dist
        pool = []
        for fid, h in dist.items():
            if h < 2:                 # 排除习惯近邻：核心一跳内不算远程
                continue
            if fid in exclude:
                continue
            f = self.sem.facts.get(fid)
            if f and f.get("status") != "superseded":
                pool.append((f, h))
        if not pool:
            return []
        weights = []
        for f, h in pool:
            base = math.exp(-h / temp)
            base += 0.5 * self.residual.get(f["id"], 0.0)
            weights.append(max(1e-6, base))
        total = sum(weights)
        picked, seen = [], set()
        for _ in range(min(6, len(pool))):
            r = self.rng.random() * total
            acc = 0.0
            for (f, h), w in zip(pool, weights):
                acc += w
                if acc >= r:
                    if f["id"] not in seen:
                        seen.add(f["id"])
                        picked.append({"fact": f, "hop": h})
                    break
        return picked

    # ---------- D 整合 + ICL ----------
    def _supporters(self, candidate):
        fid = candidate["fact"]["id"]
        adj = getattr(self, "_adj", {})
        dist = getattr(self, "_dist", {})
        return [nb for nb in adj.get(fid, ()) if nb in dist and nb != fid]

    def integrate(self, candidate, relaxed_constraints, n_support=0):
        """显式（约束满足）与隐式（吸引子激活）取 Max —— §8.2 y_int=Max(...)。

        隐式强度不是 1/(1+hop)：远程不等于弱。吸引子激活由**汇聚支持数**
        与孵化残差决定，这正是 incubation 靠残差携带而非随机的地方。
        """
        text = str(candidate["fact"].get("o", ""))
        explicit = sum(1 for c in relaxed_constraints
                       if str(c.get("text", "")) and str(c["text"])[:2] in text)
        explicit = _clamp(explicit / max(1, len(relaxed_constraints)), 0.0, 1.0)
        support_norm = _clamp(n_support / 2.0, 0.0, 1.0)
        residual = self.residual.get(candidate["fact"]["id"], 0.0)
        implicit = _clamp(0.35 + 0.45 * support_norm + 0.5 * residual, 0.0, 1.0)
        return max(explicit, 0.85 * implicit)

    def coherence_mode(self, candidate, goal_text="", supporters=None):
        """ICL = 一致性分布的众数（§8.2），不是自造乘积。

        一致性用**内容字重叠**度量（中文短语的二字片段几乎不重叠，
        用字级才有效）；每个支持者给一个分，取众数。
        """
        f = candidate["fact"]
        text = set(str(f.get("o", "")))
        supporters = supporters or []
        scores = []
        for nb in supporters:
            nf = (self.sem.facts.get(nb) if self.sem else None) or {}
            at = set(str(nf.get("o", "")))
            if not at:
                continue
            s = len(text & at) / float(max(1, min(len(text), len(at))))
            if goal_text and set(goal_text) & (text | at):
                s = _clamp(s + 0.25, 0.0, 1.0)
            scores.append(round(s, 1))
        if not scores:
            return 0.0, 0
        buckets = {}
        for s in scores:
            buckets[s] = buckets.get(s, 0) + 1
        mode = max(buckets.items(), key=lambda kv: (kv[1], kv[0]))[0]
        return mode, len(scores)

    def independent_routes(self, candidate, picked):
        """独立路径数 = 有多少个**不同的可达节点**都指向这个候选。"""
        return len(self._supporters(candidate))

    # ---------- E 主循环 ----------
    def maybe_insight(self, problem, now=None):
        now = time.time() if now is None else now
        key = problem.get("key") or problem.get("goal") or "problem"
        if not self.detect_impasse(key) or self.cooldown_active(now):
            return None
        constraints = self.extract_constraints(problem)
        relaxed, dropped = self.relax_one_unwarranted(constraints)
        entities = problem.get("entities") or []
        habitual = {f["id"] for f in (self.sem.ask(entities[0], top_k=3, now=now)
                                      if (self.sem and entities) else [])}
        picked = self.remote_walk(entities, exclude=habitual, hops=3, now=now)
        best_hunch = None
        for c in picked:
            sup = self._supporters(c)
            strength = self.integrate(c, relaxed, len(sup))
            coh, n = self.coherence_mode(c, problem.get("goal", ""), sup)
            icl = _clamp(max(strength, coh), 0.0, 1.0)   # §8.2 Max 整合
            routes = len(sup)
            if icl > SOLUTION_THRESHOLD and routes >= 2:
                rec = {"t": now, "key": key, "insight": c["fact"].get("o"),
                       "fid": c["fact"]["id"], "icl": round(icl, 3),
                       "routes": routes, "relaxed": dropped,
                       "status": "insight_candidate"}
                self.candidates.append(rec)
                self.verification_queue.append(rec)
                self.fired.append(rec)
                self.last_fire = now
                jump = _clamp(icl - (best_hunch or 0.0), 0.0, 0.7)
                if self.affect:
                    self.affect.appraise(valence=0.3, arousal=jump, weight=0.5)
                if self.wm:
                    self.wm.push(rec["insight"], salience=icl, now=now)
                    self.wm.ignite(now=now)
                self.attempts[key]["fail"] = 0
                return rec
            # 未达阈值：溯因反传 + 残差累积（incubation）
            self.residual[c["fact"]["id"]] = _clamp(
                self.residual.get(c["fact"]["id"], 0.0) + 0.25 * icl, 0.0, 1.5)
            if icl > HUNCH_THRESHOLD and (best_hunch is None or icl > best_hunch):
                best_hunch = icl
        self._decay_residual(now)
        if best_hunch:
            return {"status": "hunch", "icl": round(best_hunch, 3), "key": key, "t": now}
        return None

    def _decay_residual(self, now):
        for k in list(self.residual):
            self.residual[k] *= math.exp(-1.0 / RESIDUAL_TAU_HOURS)
            if self.residual[k] < 0.01:
                del self.residual[k]

    # ---------- 独立慢校验：Aha ≠ 正确 ----------
    def verify(self, rec, evidence_ok, now=None):
        now = time.time() if now is None else now
        rec["verified"] = bool(evidence_ok)
        rec["verified_at"] = now
        rec["status"] = "verified_insight" if evidence_ok else "imagined"
        if rec in self.verification_queue:
            self.verification_queue.remove(rec)
        if evidence_ok and self.sem:
            self.sem.teach("我", "insight:%s" % rec["key"][:10], rec["insight"],
                           source="insight_verified", now=now)
        return rec
