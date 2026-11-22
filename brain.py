# -*- coding: utf-8 -*-
"""brain.py — 认知循环（0.724 验证版恢复）

诚实口径：这不是 if/elif 的语义路由，而是一条固定优先级的竞争管道：
同一份"合并上下文"输入上，各应答源按竞争优先级逐个探测，先命中的源
胜出作答，败者不进入回答：
  成功反馈确认 → 规则 → 实践推算 → 语义事实 → 知识缺口 → 情景回忆
  → 要点回忆 → 弃答 → 追问
上下文约束（镜头/ISO/快门/三脚架等"当前装备袋"）从上一轮声明句延续到
本轮问题，合并后参与推算与规则匹配——对应真人对话里"我说过我带了什么，
你接着问就不用重说"。

基于：HUMAN_LIKE_MIND_METHOD.md v2.6（56 篇论文，7 轮精读）
      + 31 万条真实 QQ 消息的说话模式统计
"""

import re
import time

from chat_realizer import Realizer
from chat_voice import ChatVoice, first_person
import wen_say
from practice_engine import (
    bokeh_feedback, blur_diagnosis, constraint_check, dark_frame_plan,
    darkroom_plan, develop_feedback, exposure_feedback, exposure_plan,
)
from text_norm import normalize

# ===== 线索词表（保留：用于自动 cue 提取，不是路由） =====
WHO = ("外公", "外婆", "爸爸", "妈妈", "老师", "室友", "男友", "观众",
       "邮递员", "同学", "自己", "雯", "导师", "学长", "老板", "评委")
WHERE = ("学校暗房", "暗房", "幼儿园", "小学", "初中", "高中", "大学",
         "火车站", "考场", "画室", "出租屋", "影棚", "展厅", "工作室",
         "老城区", "江边", "楼下", "小区", "家", "教室", "宜昌",
         "老家", "操场", "图书馆", "食堂", "校门口", "天桥", "阳台")
WHEN = ("深夜", "夜里", "晚上", "傍晚", "下午", "早上", "春天", "秋天",
        "冬天", "夏天", "暑假", "九月", "六月", "周末", "上周三", "今晚",
        "春节", "中秋", "国庆", "除夕", "清明", "开学", "期末")
FEEL = ("崩塌", "心疼", "委屈", "害怕", "专注", "骄傲", "空虚", "空",
        "紧张", "震动", "笃定", "不甘心", "心酸", "狂喜", "舍不得",
        "发抖", "踏实", "暖", "新", "闷", "松", "乱", "压")
# 情景锚点事物：出现在问句里即视为"在问一段个人往事"
EPISODIC_THINGS = ("落榜", "个展", "暗房", "毕业创作", "艺考", "录取通知书",
                   "摄影奖", "怕黑", "抓周", "考摄影", "雪里", "旧相机", "相机",
                   "火车站", "分手")

SUCCESS_MARK = ("按你说的做了", "照你说的做了", "照做了", "管用了", "起作用了",
                "成功了", "解决了", "好使了", "这下好了")
NEG_MARK = ("没用", "不管用", "没管用", "还是", "仍", "依旧", "失败", "糊",
            "没成", "不成", "白搭", "没解决", "更糟", "偏厚", "偏薄", "太清楚")
CONFIRM_WINDOW = 2

# 泛称亲属：说事件时不单独拎出来当主语（"我妈妈，第一次坐动车" 很别扭）
_KINSHIP = ("妈妈", "爸爸", "外公", "外婆", "老师", "同学", "室友", "男友",
            "姐姐", "哥哥", "阿姨", "叔叔", "老师")

# 语义事实的宾语以这些字开头时，是**谓语**不是描述
# （"还在，收在抽屉里"）。这种不能再套"就是…"框架，否则说出"就是还在…"。
_PREDICATE_HEAD = frozenset(
    "还有没有不会能要在挺很更别用带收放买卖跟从叫是都就已经才只没你它")


def _mentions(key, obj):
    """描述里是不是已经提到了主题（"AI绘画" vs "输入文字就能生成图片"）。

    提到了就不重复说主题——真人不会把自己刚说过的主题再念一遍。
    """
    k, o = str(key or ""), str(obj or "")
    if len(k) < 2:
        return False
    for i in range(len(k) - 1):
        frag = k[i:i + 2]
        if frag and frag in o:
            return True
    return False

EPISODE_MARK = re.compile(
    r"(那次|那年|那回|上回|上次|第一次|有没有|过吗|几次|几回|什么时候|哪年|哪一年|怎么回事|叫什么|后来)")
VERB_GUO = re.compile(r"[\u4e00-\u9fa5]{1,3}过")
QUESTION_MARK = re.compile(
    r"(吗|呢|什么|哪|谁|几|怎么|多少|还是|是否|要不要|能否|有没有|？|\?)")
RELATION_MARK = re.compile(r"(还是|越|关系|影响|区别|决定|取决于)")
KNOWLEDGE_Q = re.compile(r"(什么是|什么叫|何为|是什么|你知道.{0,10}吗|谁提出的|的定义|原理是)")
# 世界知识探针："你听说过X吗/你关注过X吗"问的是公共事实，不是私人往事
KNOWLEDGE_PROBE = re.compile(r"(听说过|你知道|关注过|了解过|听过)")
# 他人叙述探针："妈妈说过…吗/外公讲过…吗"问的是**别人告诉她的**二手记忆，
# 该走语义层的 told 事实（谁讲的、讲了啥），不是她的第一人称回忆。
# 注意不含"说过"的过去式与"老师说了什么"（那是她自己的记忆）。
TOLD_PROBE = re.compile(r"(说过|讲过|告诉我|跟我讲|跟我说的)")

# 主题覆盖门槛：私人往事问句用语义事实兜底时，事实必须真的谈到这个问题的主题，
# 不能只是撞上一个词（历史教训 t11："你用无人机航拍过三峡吗"撞上
# "公园里有人玩四旋翼航拍"，答非所问且是编造）。
TOPIC_COVER_MIN = 0.6
# 主题跨度统计时剔除的高频虚词（单字）
_TOPIC_STOP = set("你我他她它在吗呢吧呀啊用过是有不也还都就要会能这那什怎为么哪谁次近以把前当来们个很再还只")
_CN_RUN = re.compile(r"[\u4e00-\u9fa5]+")

# ===== 装备袋：陈述句里的约束片段（镜头/ISO/快门/支撑/胶卷/灯） =====
# normalize 已把 感光度→ISO、支架→三脚架，这里只需认归一后的形态
CONSTRAINT_KEY = re.compile(
    r"(f\s*/|ISO|快门|手持|三脚架|只带|没带|只剩|一卷|胶卷|一盏灯|台灯|光圈)")

# ===== 真实 QQ 聊天统计 → 说话模式参数 =====
# 基于 31 万条消息: 中位 6 字 / 80% 无标点 / 语气词高频 / 犹豫词高频
CASUAL_PARTICLES = ("吧", "啊", "嘛", "呗", "哦")
CASUAL_HEDGES = ("应该", "可能", "好像")
CASUAL_FILLERS = ("嗯", "那个", "就是")


class Brain:
    def __init__(self, eng, goals=None):
        self.eng = eng
        self.goals = list(goals or eng.working_self.get("goals", []) or [])
        self.last_user_text = None
        self.last_rule_name = None
        self.last_rule_turn = -99
        self.last_episode = None
        self.practice_gaps = []
        self.turns = []
        self.turn_index = 0
        # 装备袋：上一轮声明句延续下来的约束片段
        self.context_frags = []
        # 闲聊经验：每次对话轮次累积，影响说话方式
        self.casualness = 0.0
        # 真实聊天语料驱动的句式库（chat_voice.json）。没有语料时全部退回旧模板。
        self.voice = ChatVoice()
        # 表面实现器（本地训练的小模型）：只负责"怎么说"。默认关闭——
        # 设 WEN_VOICE_MODEL=<模型目录> 才启用；没装 torch 或模型不在就自动退回模板。
        self.realizer = Realizer()

    # ================================================================
    # 主入口：固定优先级竞争管道
    # ================================================================
    def turn(self, text, cue=None, remember_turn=False, now=None):
        raw = str(text or "")
        t = normalize(raw)
        now = time.time() if now is None else now
        self.turn_index += 1
        answer, mode, conf, rule, top = None, "unknown", 0.0, None, None

        fresh_rule = (self.last_rule_name
                      and self.turn_index - self.last_rule_turn <= CONFIRM_WINDOW)
        if self._is_confirmation(t) and fresh_rule:
            rule = self.eng.confirm_rule(self.last_rule_name, event="t%d" % self.turn_index)
            answer = "那就好，这条我记住了。"
            mode, conf = "confirm", 0.9
            self.last_rule_name = None
        elif self._is_greeting(t):
            # 寒暄不进记忆检索：真人被问"在忙吗"会答"在啊"，
            # 不会答"我不知道"（R129：以前直接掉进弃答分支）。
            ans = self.voice.say("greet", {}) if self.voice else None
            if ans and self.turn_index % 2 == 0:
                ask = self.voice.say("greet_ask", {}) if self.voice else None
                if ask:
                    ans = ans + "，" + ask
            answer = ans or "在啊"
            mode, conf = "greet", 0.6
        elif (self.last_episode and not cue and len(t) <= 6
              and (t.endswith("吗") or any(k in t for k in ("是不是", "对吗")))
              and not any(k in t for k in ("记得", "那次", "第一次", "什么时候",
                                           "在哪", "为什么", "后来"))
              and not self._knowledge_question(t)
              and not self._is_action_question(t)):
            # 裸追问接上一条情景：真人被问"甜吗"会答"挺甜的"，
            # 不会答"我不知道"（她上一句刚说过甜）。
            # 但带新内容的长问句（"出生那天下雨了吗"）是新问题，不能劫持
            # （历史教训 p11/a02/a05）
            ep = self.last_episode.get("full_episode") or self.last_episode.get("episode") or {}
            res = str(ep.get("result", ""))
            if res.startswith("还在"):
                answer = res
            else:
                ans = wen_say.realize_followup(ep, self.voice, "后来",
                                               question=t, rot=self.turn_index)
                if not ans:
                    ans = wen_say.realize(ep, self.voice, question=t,
                                          rot=self.turn_index)
                answer = ans or ("还在" if "还在" in res else res) or "记不清了"
            mode, conf, top = "recall", 0.8, {"id": self.last_episode.get("id")}
        elif (self.last_episode
              and (len(t) <= 6 or t.startswith(("当时", "后来", "然后", "接着", "之后")))
              and any(k in t for k in ("当时", "后来", "然后", "接着", "之后"))):
            # 裸追问才接上一条情景；"……那次后来要回来了吗"是新问题，
            # 后来只是嵌在句中，不能劫持（历史教训 a02）
            ep = self.last_episode.get("full_episode") or self.last_episode.get("episode") or {}
            kind = "当时" if "当时" in t else "后来"
            ans = wen_say.realize_followup(ep, self.voice, kind, question=t,
                                           rot=self.turn_index)
            if ans:
                answer = ans
            elif kind == "当时":
                answer = "在%s，%s" % (ep.get("where", "那儿"),
                                      ep.get("what", "那件事"))
            else:
                answer = "后来" + str(ep.get("result", "就那样过去了"))
            mode, conf, top = "recall", 0.7, {"id": self.last_episode.get("id")}
        elif self.last_episode and t.rstrip("？?!！.。 ") in ("为什么", "为啥"):
            # 裸追问"为什么"：接着上一条情景说原因，不能弃答
            ep = self.last_episode.get("full_episode") or self.last_episode.get("episode") or {}
            answer = "因为%s。" % (ep.get("why") or "说不上来，当时就那样")
            mode, conf, top = "recall", 0.7, {"id": self.last_episode.get("id")}
        elif self._goal_question(t):
            answer = "现在最想拍的是%s。" % (self.goals[0] if self.goals else "毕业创作")
            mode, conf = "focus", 0.8
        else:
            merged = self._merge_context(t)
            plan = self._practice_plan(merged)
            if plan:
                answer, mode, conf = plan, "apply", 0.82
            else:
                rule = self.eng.match_rules(merged, now=now)
                if rule:
                    answer = self._mood_suffix(rule["action"], t)
                    mode, conf = "apply", 0.9
                    self.last_rule_name = rule["name"]
                    self.last_rule_turn = self.turn_index
                else:
                    # 情景请求：显式记忆词、对某人/某事的追问为什么、调用方给了
                    # 明确 cue——都该走情景回忆，语义事实不许抢答
                    anchor = any(v in t for v in WHO) or any(
                        v in t for v in EPISODIC_THINGS)
                    mem_req = (any(k in t for k in ('记得', '那次', '当时', '最开始', '刚才'))
                               or ("为什么" in t and anchor)
                               or bool(cue))
                    # 他人叙述探针（"妈妈说过…吗""外公讲过…吗"）问的是**二手记忆**：
                    # 答案在语义层的 told 事实里（谁讲的、讲了什么）。
                    # 不能被"我不确定的私人往事"判据挡掉——那会把 told 事实
                    # 整个遮蔽，让本来有二手记忆的问题变成"我没有记忆"。
                    told_probe = bool(TOLD_PROBE.search(t))
                    blocked = (mem_req or self._is_uncertain_claim(t)) and not told_probe
                    sem = None if blocked else self._semantic(t, now=now)
                    if sem:
                        answer, sem_mode = sem
                        conf = 0.75
                        mode = sem_mode
                    elif self._knowledge_question(t) and not cue:
                        # 给了明确线索还判"知识缺口"是路由错：cue 本身就是
                        # "这件事确实发生过"的证据，应该去情景回忆
                        # （历史教训 h06/h09/h12/v03/x02）。
                        answer = self._voice_line(
                            "unknown", "这个我还没学过，得问老师或翻书。")
                        mode, conf = "abstain", 0.0
                        self.practice_gaps.append({"mode": "abstain", "text": raw})
                    elif (self._is_action_question(t) and not cue
                          and not self._is_uncertain_claim(t) and not any(
                            k in t for k in ("记得", "是什么", "谁", "哪年", "什么时候"))):
                        answer = self._voice_line(
                            "unknown_practice", "这个我还没学过，得问老师或翻书。")
                        mode = "unknown"
                        self.practice_gaps.append({"mode": "unknown", "text": raw})
                    else:
                        r = self._recall(t, cue, now=now)
                        meta = self.eng.metacognitive(r, cue=(cue or r.get("cue") or {}))
                        if r.get("best"):
                            m = self.eng.memories[r["best"]]
                            # R129：不再把 7 个字段拼成逗号清单
                            # （"我记得爸爸说摄影没出路，家，晚饭，要我考师范，那晚没吃饭"）。
                            # 改成：先答被问的那一维 + 1-2 个有画面感的细节，
                            # 时间/地点做成句首状语从句（"三月的时候…"）。
                            ep = m.get("episode") or m.get("full_episode") or {}
                            ans = None
                            mech = None
                            if self.realizer is not None and self.realizer.enabled:
                                # 本地训练的小模型：只把槽位说成人话，不负责说什么。
                                # 只喂 select_slots 选好的 2-3 层（问句问到的那一维
                                # + 1-2 条尾巴从句），不喂全部 7 个槽位：
                                # 喂全了模型要自己决定说什么、说到哪，闸门面积也最大
                                # （实测 28 次尝试只采用 1 次）。
                                mech = wen_say.realize(
                                    ep, self.voice, question=t,
                                    arousal=m.get("arousal", 0.4),
                                    valence=m.get("valence", 0.0),
                                    mode="recall", rot=self.turn_index)
                                sel = wen_say.select_slots(
                                    ep, question=t,
                                    arousal=m.get("arousal", 0.4),
                                    valence=m.get("valence", 0.0))
                                slots = {"what": sel["core"]}
                                if sel["adv"]:
                                    slots[sel["adv"][0]] = sel["adv"][1]
                                for d, v in sel["tails"]:
                                    slots[d] = v
                                # 机械版整句当"合法字符参照集"：槽位少之后
                                # "然后/所以/挺/有点"这类连接词容易被误判成编造
                                ans = self.realizer.realize("recall", slots,
                                                           allow_text=mech)
                            if not ans:
                                ans = mech if mech is not None else wen_say.realize(
                                    ep, self.voice, question=t,
                                    arousal=m.get("arousal", 0.4),
                                    valence=m.get("valence", 0.0),
                                    mode="recall", rot=self.turn_index)
                            if not ans:
                                phrase = self._memory_phrase(m)
                                ans = self.voice.say("recall", {"what": phrase})
                            answer = ans if ans else (self._source_prefix(m)
                                                      + self._memory_phrase(m))
                            suffix = self._reconstruct_suffix(m, t)
                            if suffix:
                                # 补的这一层是独立的一小句，别跟上一句粘在一起
                                # （"差了三分应该是考场外" → "差了三分，应该是考场外"）
                                if answer and not answer.endswith(("，", ",", "。", "、")):
                                    answer += "，"
                                answer += suffix
                            mode, conf, top = "recall", max(0.6, meta["confidence"]), r["results"][0]
                            self.last_episode = m
                            # §4 GNW：被提取的内容进全局工作空间参与竞争/点火
                            ep_text = self._episode_text(m)
                            self.eng.wm_push(
                                ep_text,
                                salience=max(0.3, float(meta.get("confidence", 0.5))),
                                now=now,
                                goal_match=1.0 if any(
                                    g and str(g)[:2] in ep_text for g in self.goals) else 0.0,
                                arousal=self.eng.affect.state.get("arousal", 0.35))
                            self.eng.wm_step(now=now)
                        elif r.get("gist_best") and not self._is_uncertain_claim(t):
                            # gist 兜底只给开放式回忆；点名具体往事而只有弱重合
                            # 时，gist 就是编造（a02 教训），必须弃答
                            g = self.eng.memories[r["gist_best"]]
                            gep = g.get("episode") or g.get("full_episode") or {}
                            gwhat = first_person((g.get("gist") or {}).get("what") or "")
                            ans = wen_say.realize(
                                gep, self.voice, question=t,
                                arousal=g.get("arousal", 0.3),
                                valence=g.get("valence", 0.0),
                                mode="gist", rot=self.turn_index) if gep else None
                            if not ans:
                                ans = self.voice.say("gist", {"what": gwhat})
                            answer = ans if ans else gwhat
                            mode, conf, top = "gist", 0.45, r["results"][0]
                        elif (r.get("results") and cue
                              and re.search(r"(有没有|还记得|想得起)", t)):
                            # 开放式回忆请求（"在学校有没有还记得的事"）：
                            # 给出最强的可提记忆，老实标注只记得大概
                            m0 = self.eng.memories[r["results"][0]["id"]]
                            answer = ("嗯……想得起来的是%s，别的记不太清了。"
                                      % self._episode_text(m0)[:40])
                            mode, conf, top = "gist", 0.4, r["results"][0]
                        elif self._is_uncertain_claim(t):
                            if any(k in t for k in ("那次", "那回", "上回", "上次", "第一次")):
                                # 点名具体往事而我没有：硬弃答，绝不编。
                                # 说法走真实语料库（"没这事/我不知道"），别用
                                # "这件事我没有记忆，不能编"这种系统腔。
                                ans = self.voice.say("deny", {})
                                answer = ans if ans else "这件事我没有记忆，不能编。"
                                mode, conf = "abstain", 0.0
                            else:
                                # 没点名的"过吗"：情景没有，再让语义层试一次（m19），
                                # 但事实必须真的谈到这个问题的主题——只是撞上一个词
                                # 不算答案（历史教训 t11）。
                                sem2 = self._semantic(t, now=now, topic_guard=True)
                                if sem2:
                                    answer, mode = sem2
                                    conf = 0.65
                                else:
                                    ans = self.voice.say("deny", {})
                                    answer = ans if ans else "这件事我没有记忆，不能编。"
                                    mode, conf = "abstain", 0.0
                        elif meta["abstain"]:
                            # 一般性弃答用「记忆模糊」池：忘了/不记得了/没印象/记不清了/
                            # 想不起来了——真人不会一直说"我不知道"（盲评反馈：
                            # "一直在说记不清"）。deny 池留给"点名具体往事而我没有"
                            # 那条硬弃答，那里必须是**前提否认**（没这事/我没…）。
                            answer = self._voice_line("deny_blur", "记不清了")
                            mode, conf = "abstain", 0.0
                        elif self._is_action_question(t):
                            answer = self._voice_line(
                                "unknown_practice", "这个我还没学过，得问老师或翻书。")
                            mode = "unknown"
                            self.practice_gaps.append({"mode": "unknown", "text": raw})
                        else:
                            answer = self._voice_line(
                                "clarify", "这个我记不清了；你再多给一个地点、时间或当时的感觉。")
                            mode = "clarify"

        # 语料节奏：真实聊天里 80% 的消息不带标点、句号收尾只有 3%，
        # "每句话都句号结尾"是机器人腔的一个直接来源。
        if isinstance(answer, str):
            answer = answer.rstrip("。")

        # 装备袋更新：陈述句里的约束片段延续到下一轮
        frags = self._extract_constraints(t)
        if frags:
            self.context_frags = frags[:4]

        out = {"say": answer, "mode": mode, "confidence": round(float(conf), 2),
               "cue": cue or {}, "mood": self.eng.affect.label(),
               "focus": (self.goals[0] if self.goals else ""),
               "rule": rule, "top": top, "text": raw}
        self.turns.append(out)
        if remember_turn:
            self.eng.remember({"what": raw, "feel": self.eng.affect.label(),
                               "why": "对话", "result": answer[:80]},
                              arousal=self.eng.affect.state.get("arousal", 0.3),
                              note="对话", now=now, source="told")
        self.last_user_text = raw
        return out

    # ================================================================
    # 装备袋：约束提取与合并
    # ================================================================
    def _extract_constraints(self, t):
        """从陈述句（非问句）里提取装备/条件约束片段。

        问句不入袋（历史教训 m05/m08：上一轮的问题被当成约束带进下一轮）。
        """
        if QUESTION_MARK.search(t):
            return []
        frags = []
        for seg in re.split(r"[，。！!？?；;、\n]+", t):
            seg = seg.strip()
            if seg and CONSTRAINT_KEY.search(seg):
                frags.append(seg)
        return frags

    def _merge_context(self, t):
        """装备袋还在就还生效：把延续下来的约束合并进本轮文本。"""
        if not self.context_frags:
            return t
        parts = [t]
        for frag in self.context_frags:
            if frag and frag not in t:
                parts.append(frag)
        return "，".join(parts)

    def _practice_plan(self, text):
        """实践推算层：按习得顺序逐个尝试，年龄门控在各函数内部。"""
        age = getattr(self.eng, "dev_age", None)
        for fn in (constraint_check, exposure_plan, blur_diagnosis,
                   bokeh_feedback, darkroom_plan, develop_feedback,
                   dark_frame_plan, exposure_feedback):
            try:
                out = fn(text, age=age)
            except Exception:
                out = None
            if out:
                return out
        return None

    # ================================================================
    # 召回 / 语义
    # ================================================================
    def _recall(self, t, cue=None, now=None):
        c = dict(cue or {})
        if not c:
            for k, pool in (("who", WHO), ("where", WHERE), ("when", WHEN), ("feel", FEEL)):
                for v in pool:
                    if v in t:
                        c[k] = v
                        break
            for v in EPISODIC_THINGS:
                if v in t and "what" not in c:
                    c["what"] = v
                    break
        if not c:
            return {}
        return self.eng.recall(c, now=now)

    def _semantic(self, t, now=None, topic_guard=False):
        now = time.time() if now is None else now
        q = re.sub(r"[？?。，,！!]", " ", t)
        present = []
        for f in self.eng.facts.values():
            vt = f.get("valid_to")
            if vt is not None and now >= float(vt):
                continue
            if float(f.get("valid_from", 0)) > now:
                continue
            if f.get("status") == "superseded" and vt is None:
                continue
            pred = str(f.get("p", ""))
            key = pred.split(":", 1)[-1]
            obj = str(f.get("o", ""))
            if key and key in q:
                present.append((key, obj, pred, f))
        if not present:
            return None
        if not QUESTION_MARK.search(t):
            return None
        keys = {k for k, _, _, _ in present}
        state_ask = bool(re.search(r"(现在|如今|目前|还在)", t))
        if len(keys) >= 2 and RELATION_MARK.search(t):
            def cover(item):
                k, o, _, f = item
                return (sum(1 for kk in keys if kk in k + o),
                        f.get("status") == "verified", float(f.get("valid_from", 0)))
            best = max(present, key=cover)
        else:
            m = re.search(r"([一-龥]{2,6})(是什么|叫什么|是多少|怎么办|多大|多少)", q)
            if m is None:
                m = re.search(r"(什么是|什么叫|何为)\s*([一-龥]{2,8})", q)
                focus = m.group(2) if m else None
            else:
                focus = m.group(1)
            def score(item):
                k, o, _, f = item
                # 问"现在还在吗"这类当前状态时，描述现状的事实优先于来历
                state = 1 if (state_ask
                              and re.search(r"(还在|收在|放在|在用|保存|带着|留在)",
                                            k + o)) else 0
                return (state, bool(focus and focus in k), len(k),
                        f.get("status") == "verified", q.rfind(k))
            best = max(present, key=score)
        key, obj, pred, fact = best
        if topic_guard:
            # 事实必须覆盖问题的主题跨度，否则就是答非所问（t11）
            if self._topic_coverage(t, key + obj) < TOPIC_COVER_MIN:
                return None
        # mode 由**事实本身**决定（told: 前缀），不能再靠句首是不是"我听说"——
        # 真实语料句式库里 told 的说法是"我妈说/听说/老师说"（R128）。
        told = pred.startswith("told:")
        return self._semantic_phrase(key, obj, pred, fact), ("told" if told else "know")

    @staticmethod
    def _topic_coverage(question, fact_text):
        """问题的主题跨度被事实文本覆盖的比例。

        取问题里各中文片段分别计算，取最好的那个：主题可能在长片段里，
        也可能在短片段里（"胶片和数码"与"你们争过吗"是同一问句的两段）。
        虚词不算主题，否则"你们争过吗"会把覆盖算成 0。
        """
        runs = _CN_RUN.findall(str(question or ""))
        if not runs:
            return 1.0
        best = 0.0
        for run in runs:
            content = {ch for ch in run if ch not in _TOPIC_STOP}
            if not content:
                continue
            hit = sum(1 for ch in content if ch in fact_text)
            best = max(best, hit / float(len(content)))
        return best if best else 1.0

    def _semantic_phrase(self, key, obj, pred, fact=None):
        obj = str(obj).strip()
        told = pred.startswith("told:")
        # R129：主题（key）已经写在问句里了，再说一遍就是机器腔。
        # 以前是"主题 + 是 + 描述"：
        #   "微信是手机上能发语音的聊天软件" / "我妈说一岁抓周是抓了相机"
        # 现在按宾语形态分开处理：
        #   谓语开头（"还在，收在抽屉里"）→ 直接说，套"就是"会变成"就是还在…"
        #   描述性（"手机上能发语音的聊天软件"）→ 交给"就是{what}"框架
        if obj.startswith(("是", "为", "指", "就是")):
            body = key + obj
            framed = True
        elif obj[:1] in _PREDICATE_HEAD:
            body = obj
            framed = False
        else:
            body = obj
            framed = True
        # 句式走真实语料库：told 用"听说 / 我妈说"，know 用"就是 / 这个是"。
        # 语料里的说法是原话；填进去的内容仍是这条事实本身。
        slots = {"what": body.rstrip("。")}
        # "我知道{what}"在真实聊天里只有 60 条支撑，"就是{what}"有 755 条，
        # 而且"我知道…"是聊天机器人的口头禅——不把它放进轮换池（R129）。
        exclude = ("我知道",)
        ans = None
        if told:
            src = "%s %s" % (pred, (fact or {}).get("source", ""))
            prefer = None
            for who, pref in (("妈妈", "我妈说"), ("爸爸", "我爸说"),
                              ("外婆", "外婆说"), ("外公", "外公说"),
                              ("老师", "老师说")):
                if who in src:
                    prefer = pref
                    break
            ans = self.voice.say("told", slots, prefer_prefix=prefer,
                                 exclude_prefixes=exclude)
        elif framed:
            ans = self._know_line(key, obj)
        else:
            # 谓语开头：主题 + 谓语，不套连接词
            # （"就是还在，收在抽屉里"不像话，"相机还在，收在抽屉里"才对）
            ans = key + obj
        if ans:
            return ans
        return ("听" if told else "就") + body

    def _know_line(self, key, obj):
        """知识/事实的回答：<主题><连接词><描述>。

        连接词来自真实语料（"就是" n=785、"应该是" n=174、"一般是" n=17）。
        **主题只在描述里没提到时才补**——真人不会重复刚说过的主题：
        "知道微信吗" → "就是手机上能发语音的聊天软件"，
        而不是"微信就是手机上能发语音的聊天软件"。
        反过来，描述里没提主题时必须补（"你们摄影圈怎么看AI画画"
        的答案里必须有"AI"）。
        """
        obj = str(obj).strip()
        if _mentions(key, obj):
            ans = self.voice.say("know", {"what": obj},
                                   exclude_prefixes=("我知道",)) if self.voice else None
            return ans or ("就是" + obj)
        # 要补主题：只有能接在主题后面的连接词能用。
        # "这个是"是指示代词，接不了主题（"这个是宜昌这些年通了…"不像话），
        # 所以这一档把它排除。
        ans = self.voice.say("know", {"what": obj},
                               exclude_prefixes=("我知道", "这个是")) if self.voice else None
        literal = ""
        if ans and obj and obj in ans:
            literal = ans.split(obj, 1)[0]
        if not literal:
            literal = "就是"
        return key + literal + obj

    # ===== 问题类型判断（用于竞争打分，不是路由） =====
    @staticmethod
    def _is_knowledge_question_text(t):
        return bool(KNOWLEDGE_Q.search(str(t or "")))

    @staticmethod
    def _is_episodic_question_text(t):
        t = str(t or "")
        return bool(EPISODE_MARK.search(t) or VERB_GUO.search(t))

    @staticmethod
    def _is_action_question_text(t):
        t = str(t or "")
        # "怎么回事" 是问**过去那件事的细节**，不是问做法——
        # 而且它是"怎么回"的子串（是**怎么回**事），不排除就会把
        # "初中军训晕倒那次是怎么回事"这种反幻觉题误判成做法题，
        # 答成"没学过"而不是"我没晕倒过"。
        if any(k in t for k in ("怎么样", "什么样", "怎么这么", "怎么了",
                                "怎么回事")):
            return False
        return any(k in t for k in ("怎么办", "怎么处理", "怎么回", "怎么用", "怎么算",
                                    "怎么装", "怎么救", "怎么谈", "怎么安慰", "怎么安抚",
                                    "怎么建议", "怎么回应", "怎么沟通", "怎么拒绝", "怎么哄",
                                    "能拍", "能吗", "行吗",
                                    "多少钱", "多少度", "多少秒", "多少层", "多少倍",
                                    "哪张", "先讲", "要不要", "接不接"))

    @staticmethod
    def _is_past_event_question_text(t):
        t = str(t or "")
        if any(k in t for k in ("那次", "那回", "哪次", "那天", "过吗", "过几次",
                                "被发现", "要回来", "守过", "丢过", "偷拿", "没收")):
            return True
        return re.search(r".{0,6}过[^。？?！!]{0,6}吗", t) is not None

    @staticmethod
    def _goal_question_text(t):
        return any(k in t for k in ("最想拍", "最想忙", "最想做什么", "最想干什么",
                                    "想拍什么", "你的目标", "在忙什么", "接下来想"))

    # ===== 兼容方法（保留旧接口） =====
    def _goal_question(self, t):
        return self._goal_question_text(t)

    def _is_action_question(self, t):
        return self._is_action_question_text(t)

    def _knowledge_question(self, t):
        return bool(KNOWLEDGE_Q.search(str(t or ""))) and not self._is_uncertain_claim(t)

    @staticmethod
    def _is_greeting(t):
        """寒暄/招呼：不该进记忆检索。"""
        t = str(t or "").strip()
        if len(t) > 8:
            return False
        return bool(re.match(
            r"^(你好|您好|嗨|hi|hello|在忙吗|在吗|忙吗|最近怎么样|最近还好吗|"
            r"你好啊|早上好|晚上好|吃饭了吗|睡了没)", t, re.I))

    def _is_confirmation(self, t):
        if any(n in t for n in NEG_MARK):
            return False
        return any(k in t for k in SUCCESS_MARK)

    def _is_past_event_question(self, t):
        return self._is_past_event_question_text(t)

    def _is_uncertain_claim(self, t):
        """问句是否在确认一段"我可能没有"的私人往事。

        只对私人问题成立：问句里得有"你"或私事锚点；
        "你听说过X吗""你关注过X吗"是世界知识探针，不是私人往事，
        误判会把 told 事实整个遮蔽（历史教训 w02/w03/w17）。
        """
        if not QUESTION_MARK.search(t):
            return False
        if KNOWLEDGE_PROBE.search(t):
            return False
        personal = ("你" in t) or any(v in t for v in EPISODIC_THINGS)
        if not personal:
            return False
        return bool(EPISODE_MARK.search(t) or VERB_GUO.search(t))

    @staticmethod
    def _slots_from_memory(m):
        """把记忆的字段整理成实现器要的槽位（引擎与训练用同一套字段名）。"""
        ep = m.get("episode") or m.get("full_episode") or {}
        slots = {}
        for k in ("what", "who", "where", "when", "feel", "why", "result"):
            v = first_person(ep.get(k))
            if v:
                slots[k] = v
        return slots

    @staticmethod
    def _episode_text(m):
        ep = m.get("episode") or m.get("full_episode") or {}
        parts = [str(v) for v in ep.values() if v]
        return "，".join(parts)[:80]

    @staticmethod
    def _memory_phrase(m):
        """把一条记忆的字段拼成一句她能说出口的话。

        机械重排，**内容一字不改**：事情 → 在哪/什么时候 → 起因/结果 → 感觉。
        三处改写：
          1. 第三人称改第一人称——数据里是第三人称写她的，说出口要变成"我"；
          2. who 与 what 重复时只留一份（"妈妈，妈妈在雪里等她" → "妈妈在雪里等她"）；
          3. 泛称亲属（妈妈/爸爸/外公…）不单独拎出来当主语——那是称呼不是事件
             （"我妈妈，第一次坐动车" 很别扭），"自己"要保留（"我自己…"）。
        截断按**字段边界**做，不能把词切一半（"新闻里全是口罩过"）。
        """
        ep = m.get("episode") or m.get("full_episode") or {}
        parts = []
        for k in ("what", "where", "when", "why", "result", "feel"):
            v = first_person(ep.get(k))
            if v and v not in parts:
                parts.append(v)
        who = first_person(ep.get("who"))
        # "自己"是冗余的：字段里的"她"已经改成"我"了（历史教训 h03/h04：
        # who 可能是唯一承载判分关键词的字段，不能随便丢——只能去重，不能删）。
        if who and who != "自己" and who not in "".join(parts):
            parts.insert(1 if len(parts) > 1 else len(parts), who)
        out, total = [], 0
        for p in parts:
            if total + len(p) > 140 and out:
                break
            out.append(p)
            total += len(p) + 1
        return "，".join(out)

    def _reconstruct_suffix(self, m, t):
        """问句点到的那一层如果已被压缩掉，就从完整痕迹里补回，并标注"记不准"。

        真人被问起一件旧事，问到哪一层就答哪一层；那层忘了就说"记不准，
        大概是…"，而不是整件事都答不出来（历史教训 h12/h13/h14）。

        R129：原来是硬编码的"（这段细节我记不准了，大概是X。）"——带全角括号
        和句号，是系统腔。现在走语料里的"好像…"说法。
        """
        kept = m.get("episode") or {}
        raw = m.get("full_episode") or {}
        ask_role = None
        if any(k in t for k in ("后来", "结果", "反应", "后果", "怎么样",
                                "多久", "多长时间")):
            ask_role = "result"
        elif any(k in t for k in ("为什么", "为啥", "原因", "怎么回事")):
            ask_role = "why"
        elif any(k in t for k in ("心情", "感觉", "感受", "情绪", "气氛", "什么滋味")):
            ask_role = "feel"
        elif any(k in t for k in ("什么时候", "哪年", "哪一天", "多久以前", "季节")):
            ask_role = "when"
        elif any(k in t for k in ("在哪", "哪儿", "哪里", "什么地方", "哪")):
            ask_role = "where"
        if ask_role:
            if kept.get(ask_role) or not raw.get(ask_role):
                return ""
            return self._uncertain_about(raw[ask_role])
        # 问句没点名哪一层，但这段记忆已经压得只剩骨架时，真人复述旧事
        # 会顺带说出当时的场面（"那阵子特别挤"）。只在压得特别狠时才补
        # （保留下来的字段不足一半）——压得轻的记忆她本来就能讲出细节，
        # 每句都挂一句补充就成了口头禅，语言真实感反而变差。
        if float(m.get("detail_kept", 1.0)) < 0.5:
            for role in ("result", "feel", "why"):
                if not kept.get(role) and raw.get(role):
                    return self._uncertain_about(raw[role])
        return ""

    def _uncertain_about(self, value):
        """说不准时的话：走语料里的"大概是…"框架，不用系统腔括号。"""
        v = first_person(value)
        ans = self.voice.say("unsure", {"what": v}) if self.voice else None
        return ans or ("大概是%s" % v)

    def _voice_line(self, mode, fallback, exclude=()):
        """用语料句式说一句话；没有语料框架就退回兜底。

        R129：以前这些兜底句是硬编码的系统腔
        （"这件事我没有记忆，不能编。"、"你再多给一个地点、时间或当时的感觉。"），
        现在改成从真实聊天挖出来的说法。
        """
        ans = self.voice.say(mode, {}, exclude_prefixes=exclude) if self.voice else None
        return ans or fallback

    @staticmethod
    def _source_prefix(m):
        src = m.get("source", "experienced")
        if src == "told":
            return "你跟我说过，"
        if src == "imagined":
            return "我想象过，"
        if src == "inferred":
            return "我推测，"
        return "我记得，"

    def _mood_suffix(self, action, t):
        v = self.eng.affect.state.get("valence", 0.0)
        if any(k in t for k in ("爸爸", "生活费", "摄影没出路")):
            if v <= -0.2:
                return action + " 我现在心里堵，但先按这个说，别吵。"
            if v >= 0.2:
                return action + " 我今天状态还行，能好好说。"
        if any(k in t for k in ("客户", "精修")):
            if v <= -0.2:
                return action + " 我现在有点累，但先把条件谈清楚。"
            if v >= 0.2:
                return action + " 我今天有底，能扛住这个量。"
        return action

    def sleep(self, hours=8, now=None):
        now = time.time() if now is None else now
        end = now + hours * 3600
        self.eng.affect.tick(now=end)
        s = self.eng.sleep(now=now, hours=hours)
        c = s["sws"]
        r = self.eng.reflect(now=end)
        return {"replayed": c.get("replayed", 0), "reflect": r,
                "consolidate": c, "rem": s["rem"], "stages": s["stages"],
                "mood": self.eng.affect.label()}
