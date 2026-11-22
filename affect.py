"""affect.py — 持续情感状态（PAD 三维，纯 Python 零依赖）

为什么要 PAD 而不是单一"心情值"：
  愉悦（valence）决定她愿意多说还是少说，
  唤醒（arousal）决定句子长短与反应速度，
  掌控（dominance）决定语气笃定还是留余地。
  三个维度分开走，才能出现"低落但平静"和"低落又焦躁"这种区别。

两个关键动力学：
  惯性——事件冲击不会立刻消失，按各自时间常数衰减回基线。
  回归——不管发生什么，时间足够长都会回到基线，这是情绪的稳态。

arousal 衰减最快（1.5 小时），valence 最慢（6 小时）：
兴奋来得快去得也快，心情能挂一整天。这跟人的实际体验一致。
"""

import json
import math
import os
import time

from persistence import save_json

BASELINE = {"valence": 0.05, "arousal": 0.35, "dominance": 0.10}
TAU_HOURS = {"valence": 6.0, "arousal": 1.5, "dominance": 4.0}
LIMITS = {"valence": (-1.0, 1.0), "arousal": (0.0, 1.0), "dominance": (-1.0, 1.0)}


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class Affect:
    def __init__(self, path=None):
        self.path = path
        self.state = dict(BASELINE)
        self.updated = time.time()
        if path and os.path.exists(path):
            self._load()

    # ---------- 动力学 ----------
    def tick(self, now=None):
        """把状态按经过的时间回归基线。所有读取前先调这个。"""
        now = time.time() if now is None else now
        dt_h = (now - self.updated) / 3600.0
        if dt_h <= 0:
            return self.state
        for key, base in BASELINE.items():
            cur = self.state[key]
            decayed = base + (cur - base) * math.exp(-dt_h / TAU_HOURS[key])
            self.state[key] = _clamp(decayed, *LIMITS[key])
        self.updated = now
        return self.state

    def appraise(self, valence=0.0, arousal=0.0, dominance=0.0, weight=1.0):
        """评估一个事件带来的冲击。weight 是事件强度 0–1。

        对应杏仁核的相关性评估：同一件事对不同目标状态的人冲击不同，
        weight 就是那个"对我有多重要"的系数。
        """
        self.tick()
        self.state["valence"] = _clamp(
            self.state["valence"] + valence * weight, *LIMITS["valence"])
        self.state["arousal"] = _clamp(
            self.state["arousal"] + arousal * weight, *LIMITS["arousal"])
        self.state["dominance"] = _clamp(
            self.state["dominance"] + dominance * weight, *LIMITS["dominance"])
        return self.state

    # ---------- 读出 ----------
    def label(self):
        """把三维状态说成人话。"""
        v, a, d = self.state["valence"], self.state["arousal"], self.state["dominance"]
        if v >= 0.35 and a >= 0.55:
            mood = "轻快"
        elif v >= 0.35:
            mood = "舒展"
        elif v <= -0.35 and a >= 0.55:
            mood = "焦躁"
        elif v <= -0.35:
            mood = "低落"
        elif a >= 0.65 and v > 0.05:
            mood = "兴奋"
        elif a >= 0.65:
            mood = "警觉"
        elif a <= 0.2:
            mood = "倦"
        else:
            mood = "平稳"
        poise = "笃定" if d >= 0.3 else ("迟疑" if d <= -0.25 else "中性")
        return "%s·%s" % (mood, poise)

    def tone(self):
        """映射成表达参数，供对话层参考。

        只给倾向，不给硬模板——真正的措辞还是由生成时决定。
        """
        v, a, d = self.state["valence"], self.state["arousal"], self.state["dominance"]
        return {
            "mood": self.label(),
            "verbosity": round(0.5 + 0.35 * v - 0.25 * (a - 0.35), 3),   # 越高话越多
            "sentence_len": "short" if a >= 0.65 else ("long" if a <= 0.25 else "mixed"),
            "warmth": round((v + 1) / 2, 3),                              # 0 冷 1 暖
            "assertiveness": round((d + 1) / 2, 3),                       # 0 留余地 1 断言
            "initiative": round(0.4 + 0.4 * v + 0.2 * d, 3),              # 主动展开的程度
        }

    def recall_bias(self, memory_valence):
        """情绪一致性记忆（mood-congruent retrieval）：同向情绪的记忆更容易被想起。

        用 valence 的**乘积**而不是距离：
          同号 → >1（心情差时坏事更容易浮上来）
          异号 → <1
          中性记忆 → 恰好 1.0，不受偏置

        旧实现用 |v_state - v_mem| 的距离，导致中性心情下中性记忆恒被放大
        到 1.27、±1 的记忆恒被压到 0.70——那是"偏好平淡记忆"，不是情绪一致性。
        """
        prod = self.state["valence"] * float(memory_valence)
        return _clamp(1.0 + 0.35 * prod, 0.65, 1.35)

    def arousal_level(self):
        """给记忆巩固用的唤醒度：直接用当前 arousal，而不是手填。"""
        return self.state["arousal"]

    # ---------- 持久化 ----------
    def save(self):
        if not self.path:
            return
        save_json(self.path, {"state": self.state, "updated": self.updated})

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                payload = json.load(f)
            state = payload.get("state", {})
            for key in BASELINE:
                if key in state:
                    self.state[key] = _clamp(float(state[key]), *LIMITS[key])
            self.updated = float(payload.get("updated", time.time()))
            self.tick()
        except (OSError, ValueError, TypeError):
            pass
