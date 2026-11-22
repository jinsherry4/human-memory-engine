# -*- coding: utf-8 -*-
"""procedural_memory.py — 程序记忆（研究规格版 v3）

§3.4 / 蓝图 §8：程序不是"知道步骤"，是"会做"。三件事必须真的有行为后果：
  编译自动化：连续成功 → steps 合并变短、cost 下降；失败 → 解编译回显式步骤。
  生疏 rust：久不练 → 可及性/效用下降，但 **savings 仍在**（重学比初学快）。
  shaky：连续失败进入不稳态，**随时间自行恢复**（SHAKY_TAU_HOURS 真的被用）。
"""

import math
import time

from persistence import load_json, save_json

COMPILE_AFTER = 3
RECOMPILE_AFTER = 2
SHAKY_TAU_HOURS = 240.0     # shaky 自行恢复的时间常数（10 天量级）
RUST_TAU_HOURS = 720.0      # 生疏时间常数（30 天量级）
COMPILE_GAIN = 0.35         # 编译后执行成本下降比例

# ---- §18.6 编译 = 组合表征 → 联结表征，迁移随自动化收窄（Mill & Cole 2025）----
# 自动化程度越高，行为越绑定当前步骤组合，迁移到新情境的余量越小。
AUTO_SCOPE_DROP = 0.65      # 完全自动化时迁移范围收缩的比例


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class ProceduralMemory:
    def __init__(self, path=None):
        self.path = path
        self.procs = {}
        self.pid = 0

    def load(self):
        d = load_json(self.path, {}) or {}
        self.pid = int(d.get("pid", 0))
        self.procs = {p["id"]: dict(p) for p in d.get("procs", [])}
        for p in self.procs.values():
            p.setdefault("steps_explicit", list(p.get("steps", [])))
            p.setdefault("shaky_at", 0.0)
            p.setdefault("first_learn_runs", int(p.get("runs", 0)) or 1)
            p.setdefault("relearn_runs", 0)
            p.setdefault("compiled", False)
            p.setdefault("compiled_ever", False)
        return self

    def save(self):
        save_json(self.path, {"pid": self.pid, "procs": list(self.procs.values())})
        return self

    def learn(self, name, steps, kind="motor", now=None):
        now = time.time() if now is None else now
        for p in self.procs.values():
            if p.get("name") == name:
                # 重学：记录达到同样熟练度所需的次数，用于 savings
                p["relearn_runs"] = int(p.get("relearn_runs", 0)) + 1
                p["steps_explicit"] = list(steps)
                p["steps"] = list(steps)
                p["compiled"] = False
                p["last_run"] = now
                return p["id"]
        pid = "p%d" % self.pid
        self.pid += 1
        self.procs[pid] = {
            "id": pid, "name": name, "type": kind, "steps": list(steps),
            "steps_explicit": list(steps),
            "utility": 0.5, "runs": 0, "successes": 0, "streak": 0,
            "compiled": False, "compiled_ever": False, "fail_streak": 0,
            "shaky": False, "shaky_at": 0.0, "last_run": now,
            "first_learn_runs": 0, "relearn_runs": 0,
        }
        return pid

    # ---------- §3.4 shaky 随时间恢复 ----------
    def shaky(self, p, now=None):
        if not p.get("shaky"):
            return False
        now = time.time() if now is None else now
        dt_h = max(0.0, (now - float(p.get("shaky_at", now))) / 3600.0)
        # 指数恢复：足够久之后不稳态自行消退
        return math.exp(-dt_h / SHAKY_TAU_HOURS) > 0.5

    def _compile(self, p):
        """把相邻显式步骤合并成块，steps 真的变短。"""
        ex = p.get("steps_explicit") or p.get("steps") or []
        if len(ex) <= 1:
            p["steps"] = list(ex)
            return
        merged = []
        for i in range(0, len(ex), 2):
            chunk = ex[i:i + 2]
            merged.append("+".join(str(x) for x in chunk))
        p["steps"] = merged
        p["compiled"] = True
        p["compiled_ever"] = True

    def _decompile(self, p):
        p["steps"] = list(p.get("steps_explicit") or p.get("steps") or [])
        p["compiled"] = False

    def run(self, pid, success, now=None):
        now = time.time() if now is None else now
        p = self.procs.get(pid)
        if not p:
            return None
        p["runs"] = int(p.get("runs", 0)) + 1
        if p.get("first_learn_runs", 0) == 0:
            p["first_learn_runs"] = p["runs"]
        p["last_run"] = now
        if success:
            p["successes"] = int(p.get("successes", 0)) + 1
            p["streak"] = int(p.get("streak", 0)) + 1
            p["fail_streak"] = 0
            p["shaky"] = False
            p["utility"] = 0.8 * p.get("utility", 0.5) + 0.2 * 1.0
            if p["streak"] >= COMPILE_AFTER:
                self._compile(p)
        else:
            p["streak"] = 0
            p["fail_streak"] = int(p.get("fail_streak", 0)) + 1
            p["utility"] = 0.8 * p.get("utility", 0.5) + 0.2 * 0.0
            if p["fail_streak"] >= RECOMPILE_AFTER:
                p["shaky"] = True
                p["shaky_at"] = now
                self._decompile(p)
        return p

    def cost(self, pid, now=None):
        """执行成本：效用越高越省；编译后再省一截；生疏与 shaky 加价。"""
        p = self.procs.get(pid)
        if not p:
            return 1.0
        base = 1.0 - 0.6 * p.get("utility", 0.5)
        if p.get("compiled"):
            base *= (1.0 - COMPILE_GAIN)
        base *= (2.0 - self.rust(p, now=now))       # rust∈[0.85,1] → 加价 0–15%
        if self.shaky(p, now=now):
            base *= 1.25
        return round(min(1.5, base), 3)

    def rust(self, p, now=None):
        """生疏程度：1.0 = 熟练，随时间下降。savings 由 compiled_ever 保留。"""
        now = time.time() if now is None else now
        hours = max(0.0, (now - p.get("last_run", now)) / 3600.0)
        floor = 0.70 if p.get("compiled_ever") else 0.85
        return round(1.0 - (1.0 - floor) * (1.0 - math.exp(-hours / RUST_TAU_HOURS)), 4)

    def savings(self, pid):
        """重学节省率：曾经编译过的程序，重学所需次数更少。

        返回 0–1；0 表示没有节省证据。
        """
        p = self.procs.get(pid)
        if not p or not p.get("compiled_ever"):
            return 0.0
        first = max(1, int(p.get("first_learn_runs", 1)))
        relearn = int(p.get("relearn_runs", 0))
        if relearn <= 0:
            # 还没重学过：用编译史给出理论节省（步骤压缩比）
            ex = len(p.get("steps_explicit") or [])
            cur = len(p.get("steps") or [])
            return round(1.0 - cur / max(1, ex), 3) if ex else 0.0
        return round(max(0.0, 1.0 - relearn / float(first)), 3)

    # ---------- §18.6 自动化 ↔ 迁移范围 ----------
    def automatization(self, pid):
        """自动化程度 0–1：连续成功、编译状态、执行次数共同决定。

        §3.4 的"编译"不只是步骤变短，而是组合表征向联结表征的转移
        （Mill & Cole 2025）：转移越彻底，执行越依赖特定组合。
        """
        p = self.procs.get(pid)
        if not p:
            return 0.0
        streak = min(1.0, int(p.get("streak", 0)) / float(max(1, COMPILE_AFTER * 2)))
        compiled = 1.0 if p.get("compiled") else 0.0
        runs = min(1.0, int(p.get("runs", 0)) / 10.0)
        return round(_clamp(0.55 * streak + 0.30 * compiled + 0.15 * runs, 0.0, 1.0), 3)

    def transfer_scope(self, pid):
        """迁移范围：1.0 = 可迁到新情境，越小越是绑死当前步骤组合。

        不变量：在纯成功序列上，automatization 单调不减，transfer_scope 单调不增。
        """
        return round(1.0 - AUTO_SCOPE_DROP * self.automatization(pid), 3)
