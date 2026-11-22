"""circuits.py — 类海马体回路层（纯 Python，零依赖）

对应生物结构：
  HDC 编码  → 内嗅皮层分布式表征（角色-填充绑定）
  DG        → 模式分离（扩展 + kWTA 稀疏化）
  CA3       → 模式完成（稀疏自联想吸引子）
  CA1       → 新颖度检测（重构与线索的重叠比）

设计原则：每个函数都能对着一条神经机制讲清楚为什么这么写。
"""

import hashlib
import random


DIM = 1024           # 超维向量的维度
DG_GAIN = 6.0        # DG 扩展倍率（生物上 DG 细胞远多于 EC 输入）
DG_SPARSITY = 0.02   # DG 激活比例，对应生物 1–2% 放电
ROLES = ("who", "where", "when", "what", "feel", "why", "result")


def _stable_hash(text):
    """跨进程稳定的哈希。Python 内置 hash 对 str 有随机化，不能用。"""
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def _bipolar(seed_text):
    """确定性生成 ±1 随机向量。同样的字符串永远得到同样的向量。"""
    rng = random.Random(_stable_hash(seed_text))
    return [1 if rng.random() < 0.5 else -1 for _ in range(DIM)]


# 角色基向量固定，值向量按内容生成
_ROLE_VECS = {r: _bipolar("role:" + r) for r in ROLES}


def value_vec(value):
    """填充值的基向量。同一个值（比如同一个地点）在不同情景里得到同一向量。"""
    return _bipolar("val:" + str(value))


def bind(a, b):
    """绑定：逐元素相乘。HDC 里乘法把两个向量耦合成新向量，且可解绑。"""
    return [x * y for x, y in zip(a, b)]


def bundle(vectors):
    """捆绑：逐元素相加后取符号。保留下所有成分的叠加。"""
    acc = [0] * DIM
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    return [1 if x >= 0 else -1 for x in acc]


def encode(episode):
    """把一个情景字典编码成超维向量。

    episode 形如 {"who": "林晚", "where": "顶层公寓", "when": "深夜", ...}
    每个字段做 角色向量 × 值向量 的绑定，再把所有字段捆绑。
    这一步对应内嗅皮层把多模态输入压成单一分布式表征。
    """
    parts = []
    for role, value in episode.items():
        if role not in _ROLE_VECS or value in (None, ""):
            continue
        parts.append(bind(_ROLE_VECS[role], value_vec(value)))
    if not parts:
        return [1] * DIM
    return bundle(parts)


def similarity(a, b):
    """相同位占比，bipolar 向量的汉明相似度。

    对 ±1 向量，相同位占比 = (1 + 余弦) / 2，所以 0.5 表示正交，1 表示完全相同。
    取值 [0,1]，0 表示完全相反。
    """
    same = sum(1 for x, y in zip(a, b) if x == y)
    return same / len(a)


class DentateGyrus:
    """齿状回：模式分离。

    生物机制：DG 细胞数远多于内嗅皮层输入，且抑制极强，任一时刻只有 1–2% 放电。
    后果是相似输入被推到几乎不重叠的稀疏表征上，避免记忆互相干扰。
    """

    def __init__(self):
        rng = random.Random(_stable_hash("dg:projection"))
        self.n_out = int(DIM * DG_GAIN)
        # 每个 DG 单元随机连 ~12 个输入，权重 ±1：稀疏投影，纯 Python 也够快
        self.fan_in = 12
        self.proj = []
        for _ in range(self.n_out):
            idx = rng.sample(range(DIM), self.fan_in)
            signs = [1 if rng.random() < 0.5 else -1 for _ in range(self.fan_in)]
            self.proj.append((idx, signs))

    def separate(self, vec):
        """投影到高维后做 kWTA，只留激活最强的一小撮。返回非零索引的 frozenset。"""
        acts = []
        for j, (idx, signs) in enumerate(self.proj):
            s = 0
            for k, i in enumerate(idx):
                s += signs[k] * vec[i]
            acts.append((s, j))
        acts.sort(reverse=True)
        keep = max(4, int(self.n_out * DG_SPARSITY))
        return frozenset(j for _, j in acts[:keep])


class CA3:
    """CA3：模式完成。

    生物机制：CA3 有大量循环侧支，能把部分线索补全成完整记忆（吸引子动力学）。
    软件对应：稀疏自联想记忆——存完整模式，用线索的最大重叠去检索，迭代收敛。
    """

    def __init__(self):
        self.patterns = []      # 每项是 frozenset
        self.labels = []        # 对应的记忆 id

    def store(self, pattern, label):
        self.patterns.append(pattern)
        self.labels.append(label)

    def recall(self, cue, rounds=3, allow=None):
        """给定残缺/带噪线索，收敛到最匹配的吸引子。返回 (label, 重叠度, 置信)。

        每轮把 current 替换为最匹配模式，连续两轮不变即收敛——这样噪声位被丢弃，
        而不是像并集那样越滚越大。allow 是允许召回的标签集合（用于跳过退役记忆）。
        """
        if not self.patterns:
            return None, 0.0, 0.0
        current = cue
        best_i, best_overlap = -1, -1
        for _ in range(rounds):
            prev_i = best_i
            best_i, best_overlap = -1, -1
            for i, pat in enumerate(self.patterns):
                if allow is not None and self.labels[i] not in allow:
                    continue
                ov = len(current & pat)
                if ov > best_overlap:
                    best_overlap, best_i = ov, i
            if best_i < 0:
                return None, 0.0, 0.0
            # 收敛判定：本轮选中的模式与上一轮相同，说明已稳定在吸引子上
            if best_i == prev_i:
                break
            current = self.patterns[best_i]
        overlap = len(cue & self.patterns[best_i]) / max(1, len(cue))
        conf = overlap * (best_overlap / max(1, len(self.patterns[best_i])))
        return self.labels[best_i], overlap, conf


class CA1:
    """CA1：新颖度检测。

    生物机制：CA1 比较"输入"与"重构结果"，匹配度高说明是熟悉情境，低则触发新编码。
    软件对应：线索与最匹配模式的重叠比。低于阈值 → 判定为新经历。
    """

    def __init__(self, novelty_threshold=0.45):
        self.threshold = novelty_threshold

    def is_novel(self, overlap):
        return overlap < self.threshold
