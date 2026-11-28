# -*- coding: utf-8 -*-
"""chat_voice.py — 真实聊天语料驱动的说话方式。

骨架来自 `build_voice.py` 从真实 QQ 聊天记录挖出的 `chat_voice.json`：
每个骨架都带 n（真实语料里的支撑条数）和 ex（原句证据），**不是人工编的模板**。
没有语料文件、或骨架填不上时，一律退回旧模板，引擎自保。

选骨架的规则：
  1. 只用槽位都填得上的骨架（缺槽位的骨架直接排除，不做半截句）；
  2. 同档里按真实支撑条数 n 排，n 越大越常用；
  3. 同档轮换（self._i），让同一段访谈里句式不至于全一样，又保持可复现。
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_HERE, "chat_voice.json")

# R133-f：载荷以这些**明确时间词**起头时，不再套时间前缀框架（防"之前年三十前…"）。
# 刻意不收回"上/下/前/后/那/当"这类：太多普通词以它们开头（"上次""后来"都不该算），
# 收窄到真正的日历/时段字。
_TIME_HEAD = ("年", "月", "日", "号", "春节", "除夕", "中秋", "国庆", "清明",
              "端午", "周末", "寒假", "暑假", "开学", "期末", "元旦",
              "今", "昨", "明", "春", "夏", "秋", "冬")

# 第一人称改写：数据里的人物小传是第三人称写她的，说出口要变第一人称。
# 这是**机械替换**，不改内容。
_THIRD_PERSON = re.compile(r"她")


def first_person(text):
    """把第三人称的她改成我（机械替换，不改内容）。"""
    return _THIRD_PERSON.sub("我", str(text or ""))


class ChatVoice:
    def __init__(self, path=None):
        self.frames = {}
        self._i = 0
        try:
            with open(path or _PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.frames = data.get("frames") or {}
        except Exception:
            self.frames = {}

    def available(self, mode):
        return list(self.frames.get(mode) or [])

    def say(self, mode, slots, prefer_prefix=None, exclude_prefixes=(),
            need_slot=None):
        """挑一条骨架并填槽；没有可用骨架返回 None（调用方退回旧模板）。

        slots  : {槽位名: 内容}
        prefer_prefix : 只优先用字面前缀以它开头的骨架（例如 told 里
                        "我妈说" 要配妈妈这个来源）。
        exclude_prefixes : 排除字面前缀在列表里的骨架（例如事实本身带
                        "是" 时，别再用"就是…是…"这种双系动词句式）。
        need_slot : 骨架必须带这个槽位才可用（R129 用它区分
                    "在{where}的时候…" 与 "{when}的时候…" 两类状语框架）。
        """
        cands = []
        for fr in self.frames.get(mode) or []:
            need = fr.get("slots") or []
            if not all(slots.get(s) for s in need):
                continue
            if need_slot and need_slot not in need:
                continue
            t = fr.get("t", "")
            if prefer_prefix and not t.startswith(prefer_prefix):
                continue
            if any(t.startswith(p) for p in exclude_prefixes):
                continue
            cands.append(fr)
        if not cands:
            return None
        # 槽位用得越多的骨架越贴合（能把"在哪/什么时候"带进句子里），
        # 同槽位数里再按真实支撑条数排。
        cands.sort(key=lambda fr: (-len(fr.get("slots") or []), -fr.get("n", 0)))
        best_n = len(cands[0].get("slots") or [])
        tier = [c for c in cands if len(c.get("slots") or []) == best_n]
        # R133-d：同档内**按语料支撑条数加权轮换**，不是等概率。
        # 本文件开头写的规则是"n 越大越常用"，但原实现是 tier[i % len(tier)]
        # 等概率轮转——know 池只有三个候选时，"一般是"（n=17）和"就是"（n=785）
        # 各占 1/3，于是三分之一的知识回答都以"一般是"开头，读起来像同一个人
        # 反复念同一句口头禅（固定开场率 23% 的直接来源之一）。
        #
        # 加权方式：n 开方（压长尾）→ 归一到总长度 20 的序列 → 每个候选**至少
        # 留一格**。第一版直接把开方值当重复次数并 cap 12，结果 sqrt(785)≈28 与
        # sqrt(174)≈13 双双触顶，序列里全是"就是"，反而更单调。
        weights = [max(1.0, float(c.get("n", 0)) ** 0.5) for c in tier]
        tot = sum(weights)
        seq = []
        for c, w in zip(tier, weights):
            k = max(1, int(round(w / tot * 20)))
            seq.extend([c] * k)
        fr = seq[self._i % len(seq)]
        self._i += 1
        out = fr.get("t", "")
        for s in (fr.get("slots") or []):
            out = out.replace("{%s}" % s, str(slots.get(s) or ""), 1)
        # R133-f：时间前缀 + 已带时间成分的载荷会叠词。
        # "之前{what}" 套 "年三十前说今年不能串门" → "之前年三十前说…"（两个时间词挤在开头）。
        # 载荷自己已经以**明确时间词**起头时，去掉框架的时间前缀，直接说载荷。
        if out:
            payload = str(slots.get("what") or "")
            if payload and payload.startswith(_TIME_HEAD):
                for pre in ("之前", "上次", "以前", "那会儿", "那次"):
                    if out.startswith(pre):
                        return payload
        return out
