# -*- coding: utf-8 -*-
"""semantic_graph.py — 事实、规则、联想图、反思蒸馏（研究规格版 v3）

§3.3 语义 = 单一工作假设：同一 (s,p) 只保留一条 active，旧的 superseded 不删。
     provenance 真写入；双时间线（有效期 valid_from/valid_to + 记录期 recorded_at）。
§3.5 联想图是键/索引层：edges 参与多跳检索，hyper 绑定同一情景的多个事实。
§6.2 反思 = 情景→语义蒸馏：importance 累积触发，洞察必须带证据指针，
     且需多情景支持才晋升 verified。
§5.3 事实"两次独立传授"必须来源不同或时间可分，同源同秒重复不算两次。
"""

import time

from persistence import load_json, save_json
from text_norm import normalize

MIN_LESSON_GAP = 60.0        # 同一来源两次传授至少间隔 60 秒才算独立
MIN_CONFIRM_GAP = 300.0      # 两次实践确认至少间隔 5 分钟
REFLECT_THRESHOLD = 150.0    # §6.2 importance 累积阈值
EDGE_SHARED_TOKENS = 2


def _key(text):
    return normalize(text).lower().replace(" ", "")


def _tokens(text):
    s = _key(text)
    return {s[i:i + 2] for i in range(max(0, len(s) - 1))}


class SemanticGraph:
    def __init__(self, path=None):
        self.path = path
        self.facts = {}
        self.rules = {}
        self.edges = []
        self.fid = 0
        self.rid = 0
        self.hyper = []
        self.conflicts = []
        self.reflections = []
        self.importance_acc = 0.0

    # ---------- 载入/保存 ----------
    def load(self):
        d = load_json(self.path, {}) or {}
        self.fid = int(d.get("fid", 0))
        self.rid = int(d.get("rid", 0))
        self.facts = {f["id"]: dict(f) for f in d.get("facts", [])}
        self.rules = {r["name"]: dict(r) for r in d.get("rules", [])}
        self.edges = list(d.get("edges", []))
        self.hyper = list(d.get("hyper", []))
        self.conflicts = list(d.get("conflicts", []))
        self.reflections = list(d.get("reflections", []))
        for f in self.facts.values():
            f.setdefault("provenance", [])
            f.setdefault("recorded_at", f.get("first_learned", f.get("valid_from", 0)))
            f.setdefault("lessons", [])
            f.setdefault("support", 1)
        for r in self.rules.values():
            r.setdefault("confirms", [])
            r.setdefault("lessons", [])
        return self

    def save(self):
        payload = {"fid": self.fid, "facts": list(self.facts.values()),
                   "edges": self.edges, "hyper": self.hyper,
                   "rid": self.rid, "rules": list(self.rules.values()),
                   "conflicts": self.conflicts, "reflections": self.reflections}
        save_json(self.path, payload)
        return self

    # ---------- 事实 ----------
    def _active(self, f, now=None):
        if f.get("status") == "superseded":
            return False
        if now is not None:
            if float(f.get("valid_from", 0)) > now:
                return False
            vt = f.get("valid_to")
            if vt is not None and float(vt) <= now:
                return False
        return True

    def _link(self, fid):
        """联想边：共享 ≥2 个二字片段的事实之间连边（键/索引层）。"""
        f = self.facts[fid]
        tk = _tokens(f.get("s", "")) | _tokens(f.get("o", ""))
        for other in self.facts.values():
            if other["id"] == fid or other.get("status") == "superseded":
                continue
            ot = _tokens(other.get("s", "")) | _tokens(other.get("o", ""))
            shared = len(tk & ot)
            if shared >= EDGE_SHARED_TOKENS:
                self.edges.append({"from": fid, "to": other["id"],
                                   "w": round(shared / 10.0, 3), "kind": "shared"})

    def teach(self, s, p, o, source="taught", now=None, replace=False, episode_id=None):
        now = time.time() if now is None else now
        lesson = "%s@%d" % (source, now)

        # 1) 同值重复：只有"来源不同"或"时间可分"才算第二次独立传授
        for f in self.facts.values():
            if f.get("s") == s and f.get("p") == p and f.get("o") == o:
                ls = f.setdefault("lessons", [])
                independent = True
                for prev in ls:
                    psrc, _, pts = prev.rpartition("@")
                    try:
                        pts = float(pts)
                    except ValueError:
                        pts = 0.0
                    if psrc == source and abs(now - pts) < MIN_LESSON_GAP:
                        independent = False
                        break
                if independent and lesson not in ls:
                    ls.append(lesson)
                    f["support"] = int(f.get("support", 1)) + 1
                    f.setdefault("provenance", []).append(
                        {"source": source, "t": now, "episode": episode_id})
                if len({x.rpartition("@")[0] for x in ls}) >= 2 or len(ls) >= 2:
                    f["status"] = "verified"
                if replace:
                    self._supersede_others(s, p, o, now)
                return f["id"]

        # 2) 新值：先把同 (s,p) 的其它 active 说法置为 superseded
        if replace:
            self._supersede_others(s, p, o, now)
        fid = "f%d" % self.fid
        self.fid += 1
        self.facts[fid] = {
            "id": fid, "s": s, "p": p, "o": o,
            "provenance": [{"source": source, "t": now, "episode": episode_id}],
            "lessons": [lesson], "support": 1,
            "status": "proposed", "v": 0, "valid_from": now,
            "valid_to": None, "source": source, "first_learned": now,
            "recorded_at": now, "episode": episode_id,
        }
        self._link(fid)
        return fid

    def _supersede_others(self, s, p, keep_o, now):
        for f in self.facts.values():
            if f.get("s") == s and f.get("p") == p and f.get("o") != keep_o:
                if f.get("status") != "superseded":
                    f["status"] = "superseded"
                    f["valid_to"] = now
                    self.conflicts.append({"s": s, "p": p, "old": f["o"],
                                           "new": keep_o, "t": now, "resolved": True})

    def revise(self, fid, o=None, p=None, status=None):
        f = self.facts.get(fid)
        if not f:
            return None
        if o is not None:
            f["o"] = o
        if p is not None:
            f["p"] = p
        if status:
            f["status"] = status
        return f

    def resolve(self, s, p, now=None):
        """冲突解决器：同 (s,p) 多条 active → 保留 verified 中最新的一条。"""
        now = time.time() if now is None else now
        cands = [f for f in self.facts.values()
                 if f.get("s") == s and f.get("p") == p and self._active(f, now)]
        if len(cands) <= 1:
            return cands[0] if cands else None
        cands.sort(key=lambda f: (f.get("status") != "verified",
                                  -float(f.get("valid_from", 0))))
        keep = cands[0]
        for f in cands[1:]:
            f["status"] = "superseded"
            f["valid_to"] = now
            self.conflicts.append({"s": s, "p": p, "old": f["o"], "new": keep["o"],
                                   "t": now, "resolved": True})
        return keep

    def ask(self, s, p=None, top_k=3, now=None):
        now = time.time() if now is None else now
        out = []
        for f in self.facts.values():
            if s and s not in (f.get("s", "") + f.get("p", "") + str(f.get("o", ""))):
                continue
            if p and p not in f.get("p", ""):
                continue
            if not self._active(f, now):
                continue
            out.append(f)
        out.sort(key=lambda f: (f.get("status") != "verified",
                                -float(f.get("valid_from", 0))))
        return out[:top_k]

    def ask_graph(self, query, hops=2, top_k=6, now=None):
        """§3.5 多跳：先命中种子事实，再沿 edges 扩展 hops 跳。"""
        seeds = self.ask(query, top_k=top_k, now=now)
        seen = {f["id"]: (f, 0) for f in seeds}
        frontier = [f["id"] for f in seeds]
        for h in range(1, max(1, int(hops)) + 1):
            nxt = []
            for e in self.edges:
                a, b = e.get("from"), e.get("to")
                if a in frontier and b not in seen:
                    nxt.append(b)
                elif b in frontier and a not in seen:
                    nxt.append(a)
            for fid in nxt:
                f = self.facts.get(fid)
                if f and self._active(f, now):
                    seen[fid] = (f, h)
            frontier = nxt
            if not frontier:
                break
        out = [{"fact": f, "hop": h} for f, h in seen.values()]
        out.sort(key=lambda x: (x["hop"], x["fact"].get("status") != "verified"))
        return out[:top_k]

    # ---------- §6.2 反思蒸馏 ----------
    def reflect(self, episodes, now=None, min_support=2):
        """episodes: [{id, what, why, importance, ...}]

        importance 累积过阈值才触发；洞察必须带证据指针；
        同一模式需 ≥min_support 条不同情景支持才 verified。
        """
        now = time.time() if now is None else now
        self.importance_acc += sum(float(e.get("importance", 10)) for e in episodes)
        if self.importance_acc < REFLECT_THRESHOLD:
            return []
        self.importance_acc = 0.0
        buckets = {}
        for e in episodes:
            key = _key(e.get("why") or e.get("result") or "")
            if not key:
                continue
            buckets.setdefault(key, []).append(e)
        made = []
        for key, evs in buckets.items():
            if len({e.get("id") for e in evs}) < min_support:
                continue
            why = evs[0].get("why") or evs[0].get("result")
            insight = "反复出现：%s" % why
            refs = [e.get("id") for e in evs]
            rec = {"insight": insight, "because_of": refs, "t": now,
                   "support": len(refs), "status": "verified" if len(refs) >= min_support else "proposed"}
            self.reflections.append(rec)
            fid = self.teach("我", "reflect:%s" % key[:12], insight,
                             source="reflection", now=now)
            self.hyper.append({"fact": fid, "episodes": refs, "t": now})
            rec["fid"] = fid
            made.append(rec)
        return made

    # ---------- 规则 ----------
    def teach_rule(self, name, conditions, action, source="taught", now=None, priority=0):
        now = time.time() if now is None else now
        r = self.rules.get(name)
        lesson = "%s@%d" % (source, now)
        if r is None:
            self.rid += 1
            r = {"id": "r%d" % self.rid, "name": name,
                 "conditions": [list(g) for g in conditions],
                 "action": action, "source": source, "lessons": [lesson],
                 "practice": 0, "confirms": [], "priority": int(priority),
                 "valid_from": now, "valid_to": None, "status": "proposed"}
            self.rules[name] = r
        else:
            if lesson not in r.setdefault("lessons", []):
                r["lessons"].append(lesson)
            if len({x.rpartition("@")[0] for x in r["lessons"]}) >= 2:
                r["status"] = "verified"
            r["priority"] = max(int(priority), int(r.get("priority", 0)))
            if action:
                r["action"] = action
        return r

    def match_rules(self, text, now=None):
        t = _key(text)
        if not t:
            return None
        best, best_score, best_pri = None, 0, -1
        for r in self.rules.values():
            if now is not None and r.get("valid_from", 0) > now:
                continue
            vt = r.get("valid_to")
            if vt is not None and (now is None or float(vt) <= now):
                continue
            for group in r.get("conditions", []):
                toks = [_key(k) for k in group if k]
                if toks and all(k in t for k in toks):
                    score = len(toks)
                    pri = int(r.get("priority", 0))
                    if (score > best_score or (score == best_score and pri > best_pri)
                            or (score == best_score and pri == best_pri
                                and best is not None
                                and r.get("valid_from", 0) > best.get("valid_from", 0))):
                        best, best_score, best_pri = r, score, pri
        return best

    def confirm_rule(self, name, now=None, event=None):
        """实践确认：两次独立实践才 verified。

        独立性按**事件**判定而不是墙钟：仿真里 time.time 常被冻结，
        用时间间隔去重会把两个真实的不同轮次误判成同一次。
        event 由对话层传入轮次标识；同一轮内重复确认不累加。
        """
        now = time.time() if now is None else now
        r = self.rules.get(name)
        if not r:
            return None
        events = r.setdefault("confirm_events", [])
        if event is not None and event in events:
            return r
        if event is not None:
            events.append(event)
        r.setdefault("confirms", []).append(now)
        r["practice"] = int(r.get("practice", 0)) + 1
        if r["practice"] >= 2:
            r["status"] = "verified"
        return r
