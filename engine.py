"""engine.py — 类海马体记忆引擎系统层（纯 Python，零依赖）

在 circuits.py 的回路之上加三样系统机制：
  杏仁核  → 相关性检测 + 情绪调制（倒 U 增益，过量唤醒反而损细节）
  巩固    → ACT-R 基础激活 + 离线回放（高频强化、低频衰减、失效不删除）
  接口    → remember / recall / consolidate，可直接接项目日志

设计要点：情绪调制项是动态可学习的，不是硬编码权重；拉满反而伤记忆，
这一点在自检里会定量验证。
"""

import random
import time

from affect import Affect
from circuits import CA1, CA3, DIM, DentateGyrus, encode, similarity


class Amygdala:
    """杏仁核：相关性检测器 + 记忆巩固的调制器。

    生物机制：杏仁核不判断"危险吗"，而判断"这跟我当前目标有关吗"。
    相关则向海马体发出调制信号，增强这段记忆的巩固强度。
    但唤醒过高时，抑制性中间神经元压制其他输入，导致记忆丢失细节、过度泛化。
    """

    def __init__(self, goal=None):
        # 当前目标向量；目标变了，相关性判断跟着变
        self.has_goal = goal is not None
        self.goal = encode(goal) if goal else [1] * DIM
        # 每个刺激值的情绪强度，可学习（对应 ACT-R 情绪项的强化式更新）
        self.arousal = {}

    def relevance(self, episode):
        """情景与当前目标的相关性，符号余弦映射到 [0,1]。
        没有设定目标时返回中性值 0.5，而不是接近 0 的噪声。"""
        if not self.has_goal:
            return 0.5
        ev = encode(episode)
        s = similarity(ev, self.goal)
        return max(0.0, min(1.0, (s - 0.5) * 2))

    def gain(self, arousal):
        """倒 U 增益：0.5 唤醒时巩固最强，两端都弱。"""
        a = max(0.0, min(1.0, arousal))
        return 4.0 * a * (1.0 - a)

    def detail_loss(self, arousal):
        """过量唤醒导致的细节丢失比例。

        阈值 0.85：超过后抑制性中间神经元开始压制细节输入。
        对应 PTSD / 病态恐惧里记忆变成"梗概"的现象。
        """
        a = max(0.0, min(1.0, arousal))
        if a <= 0.85:
            return 0.0
        return (a - 0.85) / 0.15 * 0.5  # 最高丢一半细节


class MemoryEngine:
    def __init__(self, decay=0.5, affect=None):
        self.dg = DentateGyrus()
        self.ca3 = CA3()
        self.ca1 = CA1()
        self.amygdala = Amygdala()
        self.affect = affect or Affect()   # 持续情感状态；不传则用默认基线
        self.decay = decay          # ACT-R 时间衰减指数
        self.memories = {}          # id -> 记录
        self._next_id = 0

    # ---------- 写入 ----------
    def remember(self, episode, arousal=None, note=""):
        """存一段经历。返回记忆 id。

        episode 是情景字典（who/where/when/what/feel/why/result）。
        arousal 不传则取当前情感状态——这样巩固强度由她此刻的情绪决定，
        而不是每次手工指定。传入则覆盖（用于回放历史场景）。
        """
        if arousal is None:
            arousal = self.affect.arousal_level()
        arousal = max(0.0, min(1.0, arousal))
        rel = self.amygdala.relevance(episode)
        # 细节丢失：高唤醒时随机丢弃部分非核心字段（模拟表征变粗）
        kept = dict(episode)
        loss = self.amygdala.detail_loss(arousal)
        if loss > 0:
            droppable = [k for k in kept if k not in ("who", "what")]
            rng = random.Random(_stable(episode) ^ int(arousal * 1000))
            # 按概率逐个丢弃：唤醒越高，每个细节字段被压制的概率越大
            for k in droppable:
                if rng.random() < loss:
                    kept.pop(k, None)

        vec = encode(kept)
        pat = self.dg.separate(vec)
        mid = "m%d" % self._next_id
        self._next_id += 1

        now = time.time()
        self.ca3.store(pat, mid)
        self.memories[mid] = {
            "id": mid,
            "episode": kept,
            "full_episode": dict(episode),
            "vec": vec,
            "pattern": pat,
            "created": now,
            "accesses": [now],
            "arousal": arousal,
            "relevance": rel,
            "valence": self.affect.state["valence"],   # 编码时的情绪色彩，用于情绪一致性检索
            "detail_kept": len(kept) / max(1, len(episode)),
            "note": note,
            "retired": False,
        }
        return mid

    # ---------- 检索 ----------
    def recall(self, cue_episode, top_k=3):
        """用残缺/带噪线索回忆。返回按综合激活排序的候选。

        双通道：
          DG 重叠（hard）→ 精确分离判定，负责"是不是同一条"
          HDC 相似（soft）→ 分布式软匹配，负责"有多像"
        """
        cue_vec = encode(cue_episode)
        cue_pat = self.dg.separate(cue_vec)

        # 空线索不该硬匹配：所有字段都为空时直接返回"想不起来"
        if not any(v for v in cue_episode.values() if v):
            return {"best": None, "ca3_pattern": None, "overlap": 0.0,
                    "confidence": 0.0, "novel": True, "results": []}

        # 只在活跃记忆上召回，退役记忆不参与吸引子收敛
        allow = {mid for mid, m in self.memories.items() if not m["retired"]}
        mid_ca3, overlap, conf = self.ca3.recall(cue_pat, allow=allow)
        novel = self.ca1.is_novel(overlap)

        now = time.time()
        scored = []
        for m in self.memories.values():
            if m["retired"]:
                continue
            act = self._activation(m, now)
            soft = similarity(cue_vec, m["vec"])
            hard = len(cue_pat & m["pattern"]) / max(1, len(cue_pat))
            gate = 0.5 * soft + 0.5 * hard
            # 情绪一致性：当前心情与记忆色彩同向时更容易被想起
            bias = self.affect.recall_bias(m.get("valence", 0.0))
            scored.append((act * (0.3 + gate) * bias, soft, hard, gate, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, soft, hard, gate, m in scored[:top_k]:
            # 只强化真正匹配上的记忆。随机向量间的软相似度约 0.5，
            # 0.6 以上才算"想起了这件事"；匹配差的也 append 会造成记忆污染。
            if soft >= 0.6:
                m["accesses"].append(now)
                if len(m["accesses"]) > 16:
                    m["accesses"] = m["accesses"][-16:]
            results.append({
                "id": m["id"],
                "episode": m["episode"],
                "full_episode": m["full_episode"],
                "score": round(score, 3),
                "similarity": round(soft, 3),
                "dg_overlap": round(hard, 3),
                "detail_kept": round(m["detail_kept"], 2),
            })
        # 过门：排序第一不等于"想起来了"。软相似度低于 0.62 且硬重叠不足时
        # 判为想不起，避免无关线索也返回一条记忆。
        best = None
        if results:
            top = results[0]
            if top["similarity"] >= 0.62 or top["dg_overlap"] >= 0.35:
                best = top["id"]
        return {
            "best": best,
            "ca3_pattern": mid_ca3,
            "overlap": round(overlap, 2),
            "confidence": round(conf, 2),
            "novel": novel,
            "results": results,
        }

    # ---------- 巩固 ----------
    def _activation(self, m, now):
        """ACT-R 基础激活：按小时归一化，避免秒级衰减过快。

        dt_hours^-d：1 小时内约 1–7，1 天≈0.20，1 周≈0.08，1 年≈0.01。
        这样"几天不用开始淡出、一周左右退役"符合遗忘曲线的量级。
        """
        base = 0.0
        for t in m["accesses"]:
            dt_hours = max(1.0 / 60.0, (now - t) / 3600.0)
            base += dt_hours ** (-self.decay)
        gain = self.amygdala.gain(m["arousal"])
        rel = m["relevance"]
        return base * (0.5 + gain) * (0.5 + rel)

    def consolidate(self, now=None):
        """离线回放：激活低于阈值的标记 retired（不删除），保留可追溯。

        激活本身已含时间衰减 × 访问频率 × 情绪增益，所以直接用它判定即可。
        新记忆激活恒 > 0.15（即使唤醒很低），不会被误退役。
        """
        now = time.time() if now is None else now
        retired = 0
        for m in self.memories.values():
            if m["retired"]:
                continue
            if self._activation(m, now) < 0.15:
                m["retired"] = True
                retired += 1
        return {"retired": retired, "active": sum(1 for m in self.memories.values() if not m["retired"])}

    def stats(self):
        active = [m for m in self.memories.values() if not m["retired"]]
        return {
            "total": len(self.memories),
            "active": len(active),
            "avg_detail": round(sum(m["detail_kept"] for m in active) / max(1, len(active)), 2),
        }


def _stable(episode):
    from circuits import _stable_hash
    return _stable_hash(repr(sorted(episode.items())))
