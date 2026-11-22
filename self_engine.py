# -*- coding: utf-8 -*-
"""self_engine.py — 统一门面（研究规格版 v3）

把情景/语义/程序/情感/工作空间/元认知/灵光/自我装在一个对象里，
并保持旧脚本看见的字段与方法签名。

相对上一版的实质改动：
- enabled=False 真的关闭写入；mind/insight/selfmodel 开关真的决定是否装配。
- save_self 不再丢 timeline。
- metacognitive 走 MetaMind：FOK/TIP/置信三个独立信号，不再互相复制。
- construct_emotion 走概念建构；insight 走 EII 引擎；wm 走容量受限工作空间。
- recall_semantic 的 hops 真的走图多跳。
- reflect 走 §6.2 蒸馏（带证据指针 + 多情景支持），身份核心需反复验证。
- add_self_event 真写 ESK 与 lifetime_periods（Conway SMS 四层）。
"""

import time

from affect import Affect
from affective_mind import MetaMind, Regulation, Workspace, construct_emotion
from human_memory import HumanMemory
from insight_engine import InsightEngine
from persistence import append_jsonl, load_json, save_json
from procedural_memory import ProceduralMemory
from semantic_graph import SemanticGraph

IDENTITY_MIN_SUPPORT = 2

# ---- §18.5 印象形成 = 四套记忆系统（Amodio 2025）----
# 关系不再是一枚 trust 标量，而是四套各用各的更新规则：
#   episodic 情景（具体互动）/ semantic 语义（概括属性）/
#   instrumental 工具性（带来什么结果）/ pavlovian 情绪联结
REL_EPISODIC_MAX = 12          # 情景账本保留最近 N 条
REL_SEMANTIC_MIN_EPISODES = 3  # 语义概括所需的最少情景支持（慢更新）


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _new_relationship():
    return {
        "episodic": [],
        "semantic": {},
        "instrumental": {"utility": 0.5, "successes": 0, "failures": 0},
        "pavlovian": {"valence": 0.0, "trials": 0},
        # 聚合展示层：保留旧字段，旧调用方读到的仍是 0–1 的 trust
        "trust": 0.5, "interactions": 0, "unresolved": [], "rituals": [],
    }

# 语法性/序数性二字片段：出现在多条事件里也不构成身份主题
_THEME_STOP = {
    "第一", "一次", "开始", "决定", "那年", "那天", "那晚", "她的", "他的",
    "我的", "我们", "他们", "什么", "怎么", "这样", "一个", "很久",
    "没有", "没吃", "没说", "了很", "在雪", "雪里", "写了", "手里", "拿着",
}
# 纯虚词字符：任一端命中就不是身份主题词（通用汉语语法，非题库拟合）
_FUNCTION_CHARS = set("的了在是有和就都也很不没把被让使个们这那着过之而且或但却又再还只于对从向以为所其此等")


def _is_theme_gram(g):
    return g not in _THEME_STOP and not (set(g) & _FUNCTION_CHARS)


def _lcs(a, b):
    """最长公共子串（用于把二字种子扩展成可读的主题词）。"""
    best = ""
    for i in range(len(a)):
        for j in range(i + len(best) + 1, min(len(a), i + 9) + 1):
            if a[i:j] in b:
                best = a[i:j]
            else:
                break
    return best


def _identity_themes(events, links=()):
    """§9 Conway：身份核心由一般事件跨事件归纳，不是把单条事件抄一遍。

    做法：统计每个内容二字片段被多少条**不同**事件支持；支持数达标的种子
    再扩展成这些事件共有的最长子串作为主题标签。返回 [(label, support)]。

    links: [(term_a, term_b)] 来自语义图的关联词对。事件文本里出现 term_a 时，
    term_b 也计入该事件的支持袋——这样"洗出第一张照片"和"她的第一场个展"
    能经由"照片/个展 → 摄影"的语义联系归到同一身份主题，而不是只靠字面重合。
    """
    texts = []
    for ev in events:
        s = "".join(str(ev.get(k) or "") for k in ("what", "result", "feel"))
        if s:
            texts.append(s)
    support = {}
    for idx, s in enumerate(texts):
        grams = {s[i:i + 2] for i in range(len(s) - 1)}
        for a, b in links:
            a, b = str(a), str(b)
            if a and a in s:
                grams.update(b[i:i + 2] for i in range(max(0, len(b) - 1)))
        for g in grams:
            if len(g) != 2 or not _is_theme_gram(g):
                continue
            support.setdefault(g, set()).add(idx)
    seeds = [(g, ids) for g, ids in support.items() if len(ids) >= IDENTITY_MIN_SUPPORT]
    seeds.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    out, used = [], set()
    for g, ids in seeds:
        members = [texts[i] for i in sorted(ids)]
        label = g
        for other in members[1:]:
            ext = _lcs(label, other)
            if len(ext) >= 2:
                label = ext
        # 字面扩展失败（事件之间本就无共同子串）时保留二字种子本身
        if len(label) < 2:
            label = g
        if label in used or any(label in lab or lab in label for lab, _ in out):
            continue
        used.add(label)
        out.append((label, len(ids)))
    return out


class SelfEngine:
    def __init__(self, decay=0.5, affect=None, enabled=True, raw_path=None,
                 human_store=None, semantic=False, semantic_store=None,
                 procedural=False, proc_store=None, mind=False, insight=False,
                 selfmodel=False, self_store=None):
        self.enabled = enabled
        self.raw_path = raw_path
        self.affect = affect or Affect()
        self.human = HumanMemory(human_store, decay=decay, affect=self.affect)
        self.sem = SemanticGraph(semantic_store) if semantic else None
        self.proc = ProceduralMemory(proc_store) if procedural else None
        self.memories = self.human.memories
        self.facts = self.sem.facts if self.sem else {}
        self.rules = self.sem.rules if self.sem else {}
        self.procs = self.proc.procs if self.proc else {}
        self.self_store_path = self_store
        self.use_selfmodel = bool(selfmodel)
        self.self_model = {"life_story": "", "lifetime_periods": [],
                           "general_events": [], "identity_core": [], "esk": []}
        self.working_self = {"goals": [], "beliefs": [], "self_concept": []}
        self.relationships = {}
        self.timeline = []
        self.dev_age = None
        self.metacog = []
        # P5/P6 装配
        self.workspace = Workspace() if mind else None
        self.meta = MetaMind() if mind else None
        self.regulation = Regulation() if mind else None
        self.insight_engine = InsightEngine(self.sem, self.workspace, self.affect) if insight else None
        self.wm = []

    # ---------- 载入/保存 ----------
    def load_human(self):
        self.human.load()
        self.memories = self.human.memories
        return self

    def load_semantic(self):
        if self.sem:
            self.sem.load()
            self.facts, self.rules = self.sem.facts, self.sem.rules
        return self

    def load_proc(self):
        if self.proc:
            self.proc.load()
            self.procs = self.proc.procs
        return self

    def load_self(self):
        d = load_json(self.self_store_path, {}) or {}
        for k in ("self_model", "working_self", "relationships", "timeline"):
            if k in d:
                setattr(self, k, d[k])
        self.self_model.setdefault("identity_core", [])
        self.self_model.setdefault("general_events", [])
        self.self_model.setdefault("esk", [])
        self.self_model.setdefault("lifetime_periods", [])
        self.self_model.setdefault("life_story", "")
        # §18.5 旧关系数据（只有 trust/interactions）加载时补成四套子账本
        self.relationships = self.relationships or {}
        for rel in self.relationships.values():
            self._upgrade_relationship(rel)
        return self

    def save_human(self):
        self.human.save()
        return self

    def save_semantic(self):
        if self.sem:
            self.sem.save()
        return self

    def save_proc(self):
        if self.proc:
            self.proc.save()
        return self

    def save_self(self):
        save_json(self.self_store_path, {
            "self_model": self.self_model, "working_self": self.working_self,
            "relationships": self.relationships, "timeline": self.timeline,
        })
        return self

    def set_age(self, age):
        self.dev_age = float(age)
        return self

    def set_goal(self, goal):
        """working self 的当前目标 → 注入情景层，产生顶-down 优先级。"""
        if isinstance(goal, str):
            goal = {"what": goal}
        self.working_self.setdefault("goals", [])
        if goal.get("what") and goal["what"] not in self.working_self["goals"]:
            self.working_self["goals"].insert(0, goal["what"])
        self.human.set_goal(goal)
        return self

    # ---------- 情景 ----------
    def remember(self, episode, arousal=None, note="", valence=None, now=None,
                 source="experienced", priority=None):
        if not self.enabled:
            return None
        mid = self.human.remember(
            episode, arousal=arousal, note=note, valence=valence, now=now,
            min_age=3.0, dev_age=self.dev_age, source=source, priority=priority)
        if mid and self.raw_path:
            append_jsonl(self.raw_path, {"t": time.time() if now is None else now, "mid": mid,
                                         "episode": episode, "note": note,
                                         "source": source})
        if mid:
            m = self.human.memories.get(mid)
            if m is not None:
                # §7.1 Barrett：情绪实例在编码时由"当前核心 affect + 概念范畴化"
                # 建构——此前 construct_emotion 从未在仿真里被调用
                m["emotion_instance"] = construct_emotion(
                    self.affect, situation=str(episode.get("what", "")), now=now)
                # §7.3 反刍检测：负性自我相关事件喂给检测器，检出即触发调节打断
                v = float(m.get("valence", 0.0))
                if v <= -0.4 and self.regulation:
                    self.note_thought(str(episode.get("what", "")), v, now=now)
        return mid

    def update_or_new(self, episode, now=None, source="experienced", **kw):
        if not self.enabled:
            return None, "disabled"
        return self.human.update_or_new(episode, now=now, source=source,
                                        dev_age=self.dev_age, **kw)

    def rehearse(self, mid, correct, correction=None, now=None):
        rec = self.human.rehearse(mid, correct, correction=correction, now=now)
        if rec is not None:
            m = self.human.memories.get(mid)
            conf = float(m.get("last_retrieval_conf", 0.0)) if m else 0.0
            # §10 校准数据对（提取置信，练习反馈对错）——此前 compute_calibration
            # 永远拿到空表，ECE/Brier 恒为 0
            self.log_metacog(confidence=conf, correct=bool(correct), mid=mid)
        return rec

    def recall(self, cue, top_k=3, now=None, reinforce=True):
        return self.human.recall(cue, top_k=top_k, now=now, reinforce=reinforce)

    def consolidate(self, now=None, replay=True):
        return self.human.consolidate(now=now, replay=replay)

    def sleep(self, now=None, hours=8.0):
        return self.human.sleep(now=now, hours=hours)

    def rs(self, m, now=None):
        return self.human.rs(m, now=now)

    def ss(self, m):
        return self.human.ss(m)

    # ---------- §6.2 反思蒸馏 + §9 身份 ----------
    def reflect(self, now=None):
        now = time.time() if now is None else now
        insights = []
        if self.sem:
            eps = []
            for m in self.human.memories.values():
                ep = dict(m.get("full_episode") or {})
                ep["id"] = m["id"]
                ep["importance"] = 10 + 40 * m.get("surprise", 0.5) + (
                    60 if m.get("self_defining") else 0)
                eps.append(ep)
            insights = self.sem.reflect(eps, now=now)
        # 身份核心：从多条自我定义事件里归纳主题，单次事件不足以立身份
        core = self.self_model.setdefault("identity_core", [])
        if self.dev_age is None or self.dev_age >= 13:
            sds = [ev for ev in self.self_model.get("general_events", [])
                   if ev.get("self_defining") and ev.get("what")]
            links = []
            if self.sem:
                for f in self.sem.facts.values():
                    s, o = str(f.get("s") or ""), str(f.get("o") or "")
                    if s and o and s != o:
                        links.append((s, o))
                        links.append((o, s))
            for label, support in _identity_themes(sds, links=links):
                if support >= IDENTITY_MIN_SUPPORT and label not in core:
                    core.append(label)
        return {"identity_core": list(core), "insights": insights}

    def add_self_event(self, episode, self_defining=False, now=None, valence=0.0):
        now = time.time() if now is None else now
        ev = dict(episode)
        ev["self_defining"] = bool(self_defining)
        ev["t"] = now
        ev["valence"] = valence
        self.self_model.setdefault("general_events", []).append(ev)
        # Conway ESK：事件特异知识 = 感官细节，并带上父事件的出处标记
        esk = self.self_model.setdefault("esk", [])
        for k in ("where", "when", "feel", "result"):
            if ev.get(k):
                esk.append({"event": ev.get("what"), "what": ev.get("what"),
                            "role": k, "detail": ev[k], "t": now,
                            "self_defining": bool(self_defining), "valence": valence})
        # lifetime periods：按年龄段归并
        if self.dev_age is not None:
            band = "%d-%d岁" % (int(self.dev_age // 3) * 3, int(self.dev_age // 3) * 3 + 3)
            periods = self.self_model.setdefault("lifetime_periods", [])
            hit = next((p for p in periods if p["band"] == band), None)
            if hit is None:
                periods.append({"band": band, "events": [ev.get("what")],
                                "start": now, "end": now})
            else:
                if ev.get("what") not in hit["events"]:
                    hit["events"].append(ev.get("what"))
                hit["end"] = now
        self.timeline.append({"t": now, "what": ev.get("what"), "age": self.dev_age})
        return ev

    def recall_self(self, query=""):
        """working self 门控：当前目标/信念优先，其次时间近因。"""
        q = str(query)
        goals = self.working_self.get("goals", [])
        evs = [e for e in self.self_model.get("general_events", [])
               if not q or q in "".join(str(v) for v in e.values())]

        def rank(e):
            text = "".join(str(v) for v in e.values())
            g = sum(1 for x in goals if x and x[:2] in text)
            return (g, e.get("self_defining", False), e.get("t", 0))
        evs.sort(key=rank, reverse=True)
        return evs[:3]

    def reconstruct(self, cue, now=None, revive=False):
        c = dict(cue or {})
        if revive:
            c["_revive"] = True
        r = self.recall(c, now=now)
        out = dict(r)
        out["id"] = r.get("best")
        if r.get("gist_best"):
            out["gist"] = self.memories[r["gist_best"]].get("gist")
        return out

    # ---------- 语义 ----------
    def teach(self, s, p, o, source="taught", now=None, replace=False, episode_id=None):
        if self.sem:
            fid = self.sem.teach(s, p, o, source=source, now=now, replace=replace,
                                 episode_id=episode_id)
            self.facts = self.sem.facts
            return fid
        return None

    def teach_rule(self, name, conditions, action, source="taught", now=None, priority=0):
        if self.sem:
            r = self.sem.teach_rule(name, conditions, action, source=source,
                                    now=now, priority=priority)
            self.rules = self.sem.rules
            return r
        return None

    def match_rules(self, text, now=None):
        return self.sem.match_rules(text, now=now) if self.sem else None

    def confirm_rule(self, name, event=None):
        r = self.sem.confirm_rule(name, event=event) if self.sem else None
        if r:
            self.save_semantic()
        return r

    def recall_semantic(self, query="", top_k=3, hops=2, now=None):
        if not self.sem:
            return []
        if hops and int(hops) > 1:
            return [x["fact"] for x in self.sem.ask_graph(query, hops=int(hops),
                                                          top_k=top_k, now=now)]
        return self.sem.ask(query, top_k=top_k, now=now)

    def ask_semantic(self, s, p=None, top_k=20):
        out = []
        for f in self.facts.values():
            if s and f.get("s") != s:
                continue
            if p and not str(f.get("p", "")).startswith(p):
                continue
            out.append({"s": f.get("s"), "p": f.get("p"),
                        "o": f.get("o"), "status": f.get("status")})
        return out[:top_k]

    # ---------- 程序 ----------
    def learn(self, name, steps, kind="motor", now=None):
        if self.proc:
            pid = self.proc.learn(name, steps, kind=kind, now=now)
            self.procs = self.proc.procs
            return pid
        return None

    def run(self, pid, success, now=None):
        if self.proc:
            return self.proc.run(pid, success, now=now)
        return None

    @staticmethod
    def _upgrade_relationship(r):
        """把旧格式（只有 trust/interactions）补成四套子账本，不丢历史信息。"""
        if not isinstance(r, dict):
            return _new_relationship()
        had_inst = isinstance(r.get("instrumental"), dict)
        r.setdefault("episodic", [])
        r.setdefault("semantic", {})
        r.setdefault("instrumental", {"utility": 0.5, "successes": 0, "failures": 0})
        r.setdefault("pavlovian", {"valence": 0.0, "trials": 0})
        r.setdefault("trust", 0.5)
        r.setdefault("interactions", 0)
        r.setdefault("unresolved", [])
        r.setdefault("rituals", [])
        # 旧数据只有 trust：拿它当工具性效用的初始值，别让历史归零
        if not had_inst:
            r["instrumental"]["utility"] = float(r.get("trust", 0.5))
        return r

    def interact(self, name, ok=True, positive=None, now=None, episode=None,
                 valence=None, outcome=None):
        """一次互动同时喂四套记忆系统（Amodio 2025 印象形成）。

        - **episodic**：写具体一次（时间 + 情境 + 结果），只留最近 `REL_EPISODIC_MAX` 条
        - **instrumental**：按结果更新效用，学习率高（0.25）
        - **pavlovian**：按情绪效价做条件化；学习率高于消退率，符合情绪联结难消退
        - **semantic**：慢更新。要有 `REL_SEMANTIC_MIN_EPISODES` 条情景支持才概括，
          单次互动不能改写"这人可靠/不可靠"这类属性
        - **trust**：四套系统的聚合展示值，旧调用方继续读它

        `interact(name, ok)` 与 `interact(name, positive=...)` 两种旧调用都保持可用。
        """
        now = time.time() if now is None else now
        if positive is not None:
            ok = bool(positive)
        r = self.relationships.get(name)
        if r is None:
            r = _new_relationship()
            self.relationships[name] = r
        else:
            self._upgrade_relationship(r)

        r["interactions"] = int(r.get("interactions", 0)) + 1

        # 1) 情景系统：记具体事件，不做概括
        ev = dict(episode or {})
        ev.setdefault("t", now)
        ev["ok"] = bool(ok)
        if outcome is not None:
            ev["outcome"] = outcome
        r["episodic"].append(ev)
        r["episodic"] = r["episodic"][-REL_EPISODIC_MAX:]

        # 2) 工具性系统：结果 → 效用，学习率高
        inst = r["instrumental"]
        if ok:
            inst["successes"] = int(inst.get("successes", 0)) + 1
        else:
            inst["failures"] = int(inst.get("failures", 0)) + 1
        inst["utility"] = round(0.75 * float(inst.get("utility", 0.5))
                                + 0.25 * (1.0 if ok else 0.0), 3)

        # 3) Pavlovian：情绪条件化。与既有联结同向时学得快，反向时消退得慢
        pav = r["pavlovian"]
        if valence is not None:
            v = _clamp(float(valence), -1.0, 1.0)
            cur = float(pav.get("valence", 0.0))
            lr = 0.30 if abs(v) >= abs(cur) else 0.12
            pav["valence"] = round(_clamp(cur + lr * (v - cur), -1.0, 1.0), 3)
            pav["trials"] = int(pav.get("trials", 0)) + 1

        # 4) 语义系统：够多情景支持才慢速概括
        n_succ = int(inst.get("successes", 0))
        n_fail = int(inst.get("failures", 0))
        if n_succ + n_fail >= REL_SEMANTIC_MIN_EPISODES:
            rate = n_succ / float(n_succ + n_fail)
            sem = r["semantic"]
            sem["reliability"] = round(
                0.7 * float(sem.get("reliability", 0.5)) + 0.3 * rate, 3)
            if n_succ >= REL_SEMANTIC_MIN_EPISODES and rate >= 0.75:
                sem["role"] = "reliable"
            elif n_fail >= REL_SEMANTIC_MIN_EPISODES and rate <= 0.25:
                sem["role"] = "unreliable"

        # 5) 聚合 trust：工具性主导，Pavlovian 做偏置，语义小幅修正
        trust = (0.55 * float(inst.get("utility", 0.5))
                 + 0.30 * ((float(pav.get("valence", 0.0)) + 1.0) / 2.0)
                 + 0.15 * float(r["semantic"].get("reliability", 0.5)))
        r["trust"] = round(_clamp(trust, 0.0, 1.0), 3)
        return r

    def relationship_profile(self, name):
        """四套系统的分账视图，用于检查"哪一套在驱动印象"。"""
        r = self.relationships.get(name)
        if not r:
            return None
        self._upgrade_relationship(r)
        return {"name": name, "episodic_n": len(r["episodic"]),
                "episodic_recent": list(r["episodic"][-3:]),
                "semantic": dict(r["semantic"]),
                "instrumental": dict(r["instrumental"]),
                "pavlovian": dict(r["pavlovian"]),
                "trust": r.get("trust", 0.5),
                "interactions": r.get("interactions", 0)}

    def cost(self, pid, now=None):
        return self.proc.cost(pid, now=now) if self.proc else 1.0

    def _rust(self, p, now=None):
        return self.proc.rust(p, now=now) if self.proc else 1.0

    def savings(self, pid):
        return self.proc.savings(pid) if self.proc else 0.0

    # ---------- P5 情感 / 元认知 / 工作空间 ----------
    def construct_emotion(self, situation="", now=None):
        return construct_emotion(self.affect, situation, now=now)

    def regulate(self, intensity=None, controllability=0.5, situation="", now=None):
        if not self.regulation:
            return None
        if intensity is None:
            intensity = abs(self.affect.state["valence"]) * 0.6 + self.affect.state["arousal"] * 0.4
        choice = self.regulation.select(intensity, controllability, situation)
        rec = self.regulation.apply(self.affect, choice, now=now)
        rec["monitor"] = self.regulation.monitor(self.affect, choice)
        return rec

    def note_thought(self, text, valence=None, self_focused=True, now=None):
        if not self.regulation:
            return False
        v = self.affect.state["valence"] if valence is None else valence
        rum = self.regulation.note_thought(text, v, self_focused, now=now)
        if rum:
            self.regulation.interrupt(self.affect, now=now)
        return rum

    def metacognitive(self, res=None, cue=None, domain=None, counter_evidence=0.0):
        if self.meta:
            return self.meta.evaluate(res, cue=cue, domain=domain,
                                      counter_evidence=counter_evidence)
        conf = float((res or {}).get("confidence", 0.0)) if isinstance(res, dict) else 0.0
        conf = max(0.0, min(1.0, conf))
        return {"fok": conf, "tip": conf, "confidence": conf, "abstain": conf < 0.55}

    def compute_calibration(self):
        rows = [x for x in self.metacog if "conf" in x and "correct" in x]
        if not rows:
            return {"ece": 0.0, "brier": 0.0, "meta_d_prime": 0.0, "efficiency": 0.0}
        ece = sum(abs(x["conf"] - (1.0 if x["correct"] else 0.0)) for x in rows) / len(rows)
        brier = sum((x["conf"] - (1.0 if x["correct"] else 0.0)) ** 2 for x in rows) / len(rows)
        out = {"ece": round(ece, 3), "brier": round(brier, 3)}
        if self.meta:
            md = self.meta.meta_dprime(rows)
            out.update({"d_prime": md["d_prime"], "meta_d_prime": md["meta_d_prime"],
                        "efficiency": md["efficiency"]})
        return out

    def log_metacog(self, confidence=0.0, correct=False, **k):
        self.metacog.append({"t": time.time(), "conf": float(confidence),
                             "correct": bool(correct), "meta": k})
        return None

    def wm_push(self, *items, **kw):
        now = kw.get("now")
        sal = kw.get("salience", 0.5)
        for item in items:
            self.wm.append(item)
            if self.workspace:
                gm = 0.0
                goals = self.working_self.get("goals", [])
                text = str(item)
                if any(g and g[:2] in text for g in goals):
                    gm = 1.0
                self.workspace.push(item, salience=sal, now=now, goal_match=gm,
                                    arousal=self.affect.state["arousal"])
        self.wm = self.wm[-7:]
        return self.wm[-1] if self.wm else None

    def wm_step(self, now=None, **k):
        if self.workspace:
            top = self.workspace.step(now=now, arousal=self.affect.state["arousal"])
            self.workspace.ignite(now=now)
            return top
        return self.wm[-1] if self.wm else None

    # ---------- P6 灵光 ----------
    def insight(self, problem=None, now=None, **k):
        if not self.insight_engine:
            return {"insight": None, "confidence": 0.0}
        if problem is None:
            problem = k or {"key": "default", "entities": [], "constraints": []}
        out = self.insight_engine.maybe_insight(problem, now=now)
        if out is None:
            return {"insight": None, "confidence": 0.0}
        return {"insight": out.get("insight"), "confidence": out.get("icl", 0.0),
                "status": out.get("status"), "detail": out}
