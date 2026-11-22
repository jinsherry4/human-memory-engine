"""perceive.py — 感知层（纯 Python 零依赖）

三个事件源：
  对话文本 → 情绪标记检测（正负、急缓），映射成情感冲击
  文件系统 → 目录内容变更（新增/修改），映射成"有事发生"
  时间流逝 → 距上次互动多久，映射成"隔了很久"

诚实边界：这是可解释的启发式，不是语义理解。
它能区分"崩了"和"成了"，读不出反讽和潜台词。真要做深，得接 LLM 做评估。
"""

import os

# 情绪标记词表。刻意保持小：词表越大越容易误判，宁可漏，不可乱。
POSITIVE = ("好", "谢谢", "不错", "棒", "喜欢", "可以", "成了", "成功", "通过", "对")
NEGATIVE = ("不行", "错", "失败", "崩", "烦", "讨厌", "差", "拒绝", "坏了", "问题")
URGENT = ("急", "马上", "赶紧", "现在", "立刻", "快点")


def appraise_text(text):
    """从一段话里估情感冲击。返回 (valence, arousal, dominance, weight, tags)。"""
    if not text:
        return 0.0, 0.0, 0.0, 0.0, []

    # 先处理否定/固定短语，避免“不好”被“好”判正、“没问题”被“问题”判负。
    # 替换成不含任何情绪词的哨兵记号：否则“好评”里的“好”会被词表再计一次，
    # 每个映射短语都被数成两份（历史 bug，2026-11-22 审查发现）。
    text = (text.replace("不错", "〖正〗").replace("不好", "〖负〗")
            .replace("没问题", "〖正〗").replace("没毛病", "〖正〗"))
    pos = sum(1 for w in POSITIVE if w in text)
    neg = sum(1 for w in NEGATIVE if w in text)
    urg = sum(1 for w in URGENT if w in text)
    pos += text.count("〖正〗")
    neg += text.count("〖负〗")

    tags = []
    if pos:
        tags.append("正+%d" % pos)
    if neg:
        tags.append("负+%d" % neg)
    if urg:
        tags.append("急+%d" % urg)

    total = pos + neg
    valence = (pos - neg) / max(1, total) * 0.5 if total else 0.0
    arousal = min(0.5, 0.12 * (total + urg))
    dominance = 0.08 if pos > neg else (-0.08 if neg > pos else 0.0)
    weight = min(1.0, 0.25 + 0.15 * (total + urg))
    return valence, arousal, dominance, weight, tags


def scan_changes(paths, since):
    """扫描目录/文件，返回 since 之后变更的条目。"""
    changed = []
    for base in paths:
        if not os.path.exists(base):
            continue
        if os.path.isfile(base):
            try:
                mt = os.path.getmtime(base)
            except OSError:
                continue
            if mt > since:
                changed.append({"path": base, "mtime": mt})
            continue
        for root, _dirs, files in os.walk(base):
            for name in files:
                full = os.path.join(root, name)
                try:
                    mt = os.path.getmtime(full)
                except OSError:
                    continue
                if mt > since:
                    changed.append({"path": full, "mtime": mt})
    changed.sort(key=lambda x: x["mtime"], reverse=True)
    return changed


def appraise_changes(changed, cap=5):
    """把文件变更折成一次情感冲击。变更多说明进展多，但边际递减。"""
    if not changed:
        return 0.0, 0.0, 0.0, 0.0, []
    n = min(len(changed), cap)
    return 0.10, 0.06 * n, 0.05, min(0.6, 0.12 * n), ["变更×%d" % len(changed)]


def appraise_gap(last_seen, now):
    """时间间隔本身是一种事件：隔得久了，唤醒略微回升，愉悦略降。"""
    gap_h = (now - last_seen) / 3600.0
    if gap_h < 1.0:
        return 0.0, 0.0, 0.0, 0.0, []
    weight = min(1.0, gap_h / 24.0)
    return -0.04, 0.05, 0.0, weight, ["间隔%.0f小时" % gap_h]
