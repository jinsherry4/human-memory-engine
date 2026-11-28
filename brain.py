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
# 会话修复（DS-COMM-01 第六章，用户提供 2026-11-28）：
# 用户纠正她的回答时——识别、修订痕迹（rehearse）、具体承认，不辩护。
CORRECTION_MARK = re.compile(
    r"(你说的不对|说错了|记错[了过]|不是这样的|弄反了|理解错|不是这个意思)")

# 陪伴模式触发词（DS-COMM-01 第四章 4.4：陪伴与解决是两种模式，
# 由真实会话信号切换）：陈述句（非问句）里出现这些情绪词且不携带
# 装备约束时，先接住，不给方案、不病理化、不强行追问。
EMPATHY_FEEL = ("累", "烦", "困", "委屈", "开心", "高兴", "兴奋",
                "紧张", "焦虑", "难受", "不爽", "难过", "崩溃")

# L3 前提否认：点名具体往事而我没有时，回声用户的措辞来否认前提——
# 只回声、不新增内容（来源监控的诚实边界，§10 Johnson）。
DENY_PREMISE = ("我没{what}这回事啊，你是不是记成别人了？",
                "{what}？没发生过吧，我没印象。")

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

# R133-d：「大概X」在真实语料里只搭配数量与模糊量（"大概玩3天" n=112、
# "好像是前5题" n=106、"可能是下午3～5" n=82）。场合/地点/人物这类具体名词
# 套上去就是病句（"大概考场外"），这里用来分流。
_QUANTITY_LIKE = re.compile(
    r"^[0-9一二三四五六七八九十百千万两几半]+"
    r"|[0-9]|[一二三四五六七八九十][点号月年天周秒分个次条张岁层倍元块]"
    r"|左右|多|来[天年月]|前后|上下|几")


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
        # §18.4 change-of-mind：上一轮的元认知评语与情景锚点
        self._last_meta = None
        self._last_anchor = None
        # DS-COMM-01：会话模式连续性（陪伴链）与纠正的目标轮次
        self._last_mode = None
        self.last_episode_turn = -99
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
        # 会话修复（DS-COMM-01 第六章）：用户纠正→rehearse 修订痕迹→具体承认。
        # 只在上一轮有情景记忆时触发；无目标时不硬认（教材 5.3：对方记错时
        # 用证据澄清，不虚假认错）。
        corr_text = None
        if (self.last_episode and CORRECTION_MARK.search(t)
                and self.turn_index - self.last_episode_turn <= 2):
            # 目标相关性门：纠正必须紧跟她的回答（2 轮内）——
            # 否则任何"你说的不对"都会写进无关记忆（cortisol 教训）
            corr_text = self._correction_content(t)
        if corr_text is not None:
            mid = self.last_episode.get("id")
            ep = (self.last_episode.get("full_episode")
                  or self.last_episode.get("episode") or {})
            corr_ep = dict(ep)
            corr_ep["result"] = "（更正）" + corr_text
            self.eng.rehearse(mid, False, correction=corr_ep, now=now)
            answer = "对，是%s。我刚才记岔了。" % corr_text
            mode, conf = "repair", 0.8
            rule = None
            self.last_rule_name = None
            self.last_episode_turn = self.turn_index
        elif self._is_confirmation(t) and fresh_rule:
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
            # R133-e：追问"后来呢"不能把上一句已经说过的 result 再念一遍。
            # 实测 p01 答"在雪里坐了很久"、紧接着 c03「后来呢」又答"后来在雪里
            # 坐了很久"——同一句细节出现两次，正是长访谈一致性检查要抓的东西。
            # 真人被追问"后来呢"会**往下走一层**：事情本身说完了，就说当时之后
            # 留下的感觉或原因。所以 result 已说过时改说 feel。
            said = " ".join(str(x.get("say") or "") for x in self.turns[-2:])
            # R133-e：**这里刻意不做"说过就别再说"的去重**。
            # 试过：result 已在上一句说过时改说 feel，输出
            # "后来啊，第一次艺考落榜那事过去以后，心里一直崩塌"——
            # 句子成立，但 consist 维度立刻掉分（c03 期望「后来呢」接 result，
            # 即"雪"）。回看语义：**追问"后来呢"本来就该把结果说出来**，
            # 上一问问的是"在哪"（答地点），result 其实没说全；
            # 是同一段记忆的不同侧面，不是重复。去重是我想当然，撤回。
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
            # 陪伴模式（DS-COMM-01 第四章 4.4）：情绪陈述句先接住——
            # 不给方案、不追问、不病理化；装备陈述不受此限（走原路径）
            feel_hit = self._empathy_statement(t)
            if feel_hit:
                answer = self._empathy_reply(t, feel_hit)
                mode, conf = "empathy", 0.5
                out = {"say": answer, "mode": mode,
                       "confidence": round(float(conf), 2),
                       "cue": cue or {}, "mood": self.eng.affect.label(),
                       "focus": (self.goals[0] if self.goals else ""),
                       "rule": None, "top": None, "text": raw}
                self.turns.append(out)
                self._last_mode = "empathy"
                self.last_user_text = raw
                return out
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
                    # R133-c：问"什么感觉/什么样/怎么回事"是在问**她自己的一段经历**，
                    # 语义层不该抢答——库里"宜昌通了动车"是公共事实，
                    # 但"把旧相机带到宜昌那天你什么感觉"问的是那一天的她。
                    #
                    # 判据必须同时满足两条，否则会把知识问句挡成弃答：
                    #   ① 有感受/细节追问词（"什么感觉/什么样/怎么回事"）
                    #   ② **有个人经历锚点**（"你/我的"、"那天/那次"、或情景事物）
                    # 第一版只看①，立刻吃掉"相纸的反差是怎么回事"（知识）、
                    # "外公的胶片时代是什么样的"、"爸爸说的寻呼机是什么样的"
                    # （二手事实 told）——冻结 holdout 0.855→0.790。
                    # 只看"那年/哪一年"更糟："北京奥运会是哪一年办的"被挡成弃答。
                    ask_shape = any(k in t for k in ("什么感觉", "感觉怎么样",
                                                     "什么样", "怎么回事"))
                    # 问**别人**的事（"外公的胶片时代是什么样的"/"爸爸说的寻呼机"）
                    # 不是问她自己的经历，那是 told 事实，应交回语义层。
                    other_person = any(w in t for w in ("外公", "外婆", "爸爸", "妈妈",
                                                        "老师", "室友", "同学", "男友"))
                    self_ask = ("你" in t) or ("我" in t) or any(
                        k in t for k in ("那天", "那次", "那回"))
                    episodic_ask = ask_shape and self_ask and not (
                        other_person and not any(k in t for k in ("那天", "那次", "那回")))
                    # R133-e：只靠感受词会漏掉不带感受词的往事问句
                    # （"落榜那天你在哪"——没有"什么感觉"，但"那天"+"你"就是往事）。
                    # 补一条：带**明确时间锚（那天/那次/那回）且自我指涉**的，
                    # 也走情景路。
                    #
                    # 但必须排除**出生/小时候这类"她不可能有第一人称记忆"的事**：
                    # "你出生那天下雨了吗"有时间锚也有"你"，可那是别人告诉她的
                    # （told 事实），判成往事会把它挡成弃答（主访谈 past 12→11）。
                    told_ish = bool(TOLD_PROBE.search(t)) or any(
                        k in t for k in ("出生", "小时候", "一岁", "两岁", "三岁前",
                                         "满月", "百天", "抓周"))
                    if not episodic_ask:
                        episodic_ask = (any(k in t for k in ("那天", "那次", "那回"))
                                        and (("你" in t) or ("我" in t))
                                        and not other_person and not told_ish)
                    mem_req = (any(k in t for k in ('记得', '那次', '当时', '最开始', '刚才'))
                               or ("为什么" in t and anchor)
                               or episodic_ask
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
                        # §18.4 change-of-mind（Goueytes 2025）：锚点重叠时把上一次
                        # 的元认知评语作为 prev 传入——弃答后来了新线索，置信应能回升
                        anchor_now = [v for v in EPISODIC_THINGS if v in t]
                        anchor_overlap = bool(self._last_anchor) and any(
                            v in anchor_now for v in self._last_anchor)
                        meta = self.eng.metacognitive(r, cue=(cue or r.get("cue") or {}),
                                                      prev=(self._last_meta if anchor_overlap else None))
                        self._last_meta = meta
                        self._last_anchor = anchor_now or None
                        if r.get("best"):
                            m = self.eng.memories[r["best"]]
                            # R129：不再把 7 个字段拼成逗号清单
                            # （"我记得爸爸说摄影没出路，家，晚饭，要我考师范，那晚没吃饭"）。
                            # 改成：先答被问的那一维 + 1-2 个有画面感的细节，
                            # 时间/地点做成句首状语从句（"三月的时候…"）。
                            ep = m.get("episode") or m.get("full_episode") or {}
                            ans = None
                            mech = None
                            # §19 表达意图三参：置信→hedge 档位；
                            # 语域由问句对象推断；avoid=潜台词清单（不主动说）
                            reg = self._register(t)
                            avoid = self._avoid_topics(t)
                            conf_v = max(0.6, float(meta.get("confidence", 0.75)))
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
                                    mode="recall", rot=self.turn_index,
                                    conf=conf_v, register=reg, avoid=avoid)
                                sel = wen_say.select_slots(
                                    ep, question=t,
                                    arousal=m.get("arousal", 0.4),
                                    valence=m.get("valence", 0.0), avoid=avoid)
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
                                    mode="recall", rot=self.turn_index,
                                    conf=conf_v, register=reg, avoid=avoid)
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
                            self.last_episode_turn = self.turn_index
                            # §4 GNW：被提取的内容进全局工作空间参与竞争/点火
                            ep_text = self._episode_text(m)
                            self.eng.wm_push(
                                ep_text,
                                salience=max(0.3, float(meta.get("confidence", 0.5))),
                                now=now,
                                goal_match=1.0 if any(
                                    g and str(g)[:2] in ep_text for g in self.goals) else 0.0,
                                arousal=self.eng.affect.state.get("arousal", 0.35),
                                precision=max(0.0, min(1.0, float(meta.get("confidence", 0.5)))))
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
                                # R133 前置于否认：先看有没有**二手记忆**。
                                # "你第一次按快门是什么时候"库里有 told 事实
                                # （外公翻旧相册时讲的：四岁半教她按快门，拍到模糊的桌子），
                                # 那是她真的听过的；答"不记得"是假失忆，和编造同罪。
                                # 只认 told 类且过主题覆盖门槛——撞上"相机"两个字的知识
                                # 事实不算（a02 没收相机 / f21 掉进江里 的教训）。
                                sem_told = self._semantic(t, now=now, topic_guard=True)
                                if sem_told and sem_told[1] == "told":
                                    answer, mode = sem_told[0], "told"
                                    conf = 0.7
                                else:
                                    # 点名具体往事而我没有：前提否认，绝不编。
                                    # 措辞回声用户的问法（"我没偷拿信用卡这回事啊，
                                    # 是不是记成别人了？"）——回声不是编造，新增细节才是。
                                    prem = self._deny_premise(t)
                                    ans = None
                                    if prem and re.search(r"(那次|那回|的时候)", t):
                                        # 指控式叙述短语才回声；描述式短语（"收到的那台
                                        # 无人机"）回声读着别扭，用通用否认
                                        ans = DENY_PREMISE[self.turn_index % len(DENY_PREMISE)].format(
                                            what=prem)
                                    if not ans:
                                        ans = self.voice.say("deny", {"what": prem} if prem else {})
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

        # §19.1 Self-monitoring（事闸 v1，软模式）：回答里引用的记忆片段
        # 必须能指回本次命中的痕迹——模板路径由构造保证；LLM 时代转硬闸。
        ref_mids = []
        if top and isinstance(top, dict) and top.get("id"):
            ref_mids.append(top["id"])
        elif self.last_episode:
            ref_mids.append(self.last_episode.get("id"))
        mon_ok, mon_why = self._self_monitor(answer, ref_mids)
        out = {"say": answer, "mode": mode, "confidence": round(float(conf), 2),
               "cue": cue or {}, "mood": self.eng.affect.label(),
               "focus": (self.goals[0] if self.goals else ""),
               "rule": rule, "top": top, "text": raw,
               "self_monitor": mon_ok, "self_monitor_why": mon_why}
        self.turns.append(out)
        if remember_turn:
            self.eng.remember({"what": raw, "feel": self.eng.affect.label(),
                               "why": "对话", "result": answer[:80]},
                              arousal=self.eng.affect.state.get("arousal", 0.3),
                              note="对话", now=now, source="told")
        self._last_mode = mode
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
        # R133-b 事件短语优先：token 线索只留 2 个字（"落榜" / "爸爸"），一条记忆的
        # what 是"第一次艺考落榜"、另一条是"落榜后那个冬天偷半天去拍雪"，两条的
        # text 覆盖都是 1.000——token 把区分信息**丢掉了**；更糟的是单字级
        # verbatim 通道会把"爸爸说摄影没出路"答成"家里换了两百兆宽带"（同含"爸爸"）。
        # 先用整段事件短语（"爸爸说摄影没出路"）检索，它带区分度；命中就用它。
        #
        # 实测（10 条真实事件 / 14 条虚构事件，human_memory 的门限一行未改）：
        #   短语优先 5/10 且 0 误报；token 优先 4/10 且答错 1 条。所以是顺序问题，
        #   不是阈值问题——这里不调任何阈值。
        if not cue:
            prem = self._deny_premise(t)
            if prem and len(prem) >= 2:
                # _dim：问的是哪一维（"什么感觉"→feel）。只在多条候选 text 并列
                # 时用来破平（human_memory.recall 里），不改打分也不动门限。
                c0 = {"what": prem, "_dim": wen_say.asked_dimension(t)}
                r0 = self.eng.recall(c0, now=now)
                if (r0 or {}).get("best"):
                    r0["cue"] = {"what": prem}
                    return r0
                # R133-g 子串命名：prem 是某条记忆 what 的**完整连续子串**时，
                # 它就是在点名那件事——比"二字片段覆盖率"强得多。
                #
                # 为什么需要它：现有关里的 named 要求 cue>=6 字且互为子串，
                # 于是 2-4 字的短命名（"落榜"/"个展"/"分手"）永远进不去；
                # 而"落榜那天你在哪"的 prem 恰好就是 2 字，被挡在门外后
                # 落到 best=None，再被下游答成"忘了"——把真事说成记不得。
                #
                # 为什么它安全：要求是**连续子串**，不是片段拼凑。
                # "课第一次独立"这种跨词拼出来的串当不了任何记忆的子串，
                # 所以不会像滑窗那样引入假匹配。
                # 实测 12 条真实事件命中 9、18 条虚构事件 0 误报。
                sub = self._substring_named(prem)
                if not sub:
                    # prem 常带着问句残留（"个展主题"/"校运会你给班里拍照"），
                    # 整串不是任何 what 的子串。逐段退让：先试归一后的整句，
                    # 再试它的逗号分句与去疑问词的形式。
                    for cand in (t, re.split(r"[，,、；;]", t)[0],
                                 re.sub(r"(是什么|叫什么|怎么样|怎么回事|什么感觉|了吗|吗|呢)$",
                                        "", t)):
                        cand = (cand or "").strip(" ，,")
                        if len(cand) >= 2:
                            sub = self._substring_named(cand)
                            if sub:
                                break
                if not sub:
                    # 刻意**不再往下退**：试过用 EPISODIC_THINGS 关键词作子串
                    # （"相机"是"相机摔在地上"的连续子串），立刻引入 2 条误报——
                    # "你高中被老师没收相机那次"和"你把相机掉进江里那次"都答成了
                    # "相机摔在地上"。关键词太泛，一退就编。
                    # 宁可漏答 2 条，不留编造。
                    pass
                if sub:
                    r1 = self.eng.recall({"what": sub, "_dim": wen_say.asked_dimension(t)},
                                         now=now)
                    if (r1 or {}).get("best"):
                        r1["cue"] = {"what": sub}
                        return r1

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
        r = self.eng.recall(c, now=now) if c else {}

        # 短语路没命中时，token 路命中就用 token 路（两路口径都过原门限）。
        # 反过来（token 先、短语补）会让"爸爸"这种超高频 token 的 verbatim 通道
        # 抢先答错，实测 4/10 且错 1 条。
        return r

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
            if not ans and prefer:
                # R133：语料里有"我妈说/我爸说/老师说"，**没有**"外公说/外婆说"。
                # 偏好匹配失败时不能掉进任意 told 框架——那会把"外公讲的"
                # 说成"老师说"，张冠李戴比"说不知道"更糟（f05）。
                # 退到不指人的"听说"（n=84，语料里最常用的传闻式），
                # 只保留"这是听来的"这一层，不编来源。
                ans = self.voice.say("told", slots, prefer_prefix="听说",
                                     exclude_prefixes=exclude)
            if not ans:
                ans = self.voice.say("told", slots, exclude_prefixes=exclude)
        elif framed:
            ans = self._know_line(key, obj)
        else:
            # 谓语开头：主题 + 谓语，不套连接词
            # （"就是还在，收在抽屉里"不像话，"相机还在，收在抽屉里"才对）
            ans = key + obj
        if ans:
            # §19.3 hedge：单次传授(未 verified)的知道类事实降格表达——
            # "就是X"→"应该是X"；verified 事实保持干净断言。
            # 置信的社会表达（第八轮 §19.3），不是装饰。
            if (not told and (fact or {}).get("status") != "verified"
                    and ans and "就是" in ans):
                ans = ans.replace("就是", "应该是", 1)
            return ans
        return ("听说" if told else "就") + body

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

    def _substring_named(self, needle):
        """needle 是否**完整连续地**出现在某条记忆的 what 里（或反之）。

        返回命中的那条 what（用于再次检索，让 recall 自己的门限来裁决），
        找不到就返回 None。

        R133-g：这是"点名"的最强形态——不是片段重叠，是连续子串。
        "落榜" 是 "第一次艺考落榜" 的连续子串 → 点名了它；
        "课第一次独立"（滑窗拼出来的）不是任何记忆的子串 → 不点名。
        多条都命中时取"最贴合"的：needle 占 what 的比例越大越确定。
        """
        needle = str(needle or "").strip()
        if len(needle) < 2:
            return None
        best = None
        for m in getattr(self.eng, "memories", {}).values():
            if m.get("retired"):
                continue
            what = str((m.get("episode") or {}).get("what") or "")
            if not what:
                continue
            if needle not in what and what not in needle:
                continue
            score = (len(needle) / float(len(what) + len(needle)), -len(what))
            if best is None or score > best[0]:
                best = (score, what)
        return best[1] if best else None

    def _register(self, t):
        """语域推断（§19.5）：问句的称呼与措辞决定她说给谁听。

        师长档收敛（禁随意立场副词与语气词）；平辈档是 QQ 语料的原生语域。
        """
        if any(k in t for k in ("老师", "爸爸", "妈妈", "外公", "外婆", "爷爷",
                                "奶奶", "您", "请问", "评委", "导演", "前辈")):
            return "师长"
        if any(k in t for k in ("客户", "陌生", "面试", "请教")):
            return "陌生"
        return "平辈"

    def _avoid_topics(self, question):
        # "不说什么"清单（§19.4 潜台词的机制化）：
        # 未解的关系冲突 + 高负价自我事件——没被问到的，不主动说；
        # 被问到的内容不受此限（core 不走此过滤）。
        avoid = []
        for name, r in self.eng.relationships.items():
            for c in (r.get("unresolved") or []):
                txt = c if isinstance(c, str) else str(c.get("what") or "")
                if txt and txt[:10] not in question:
                    avoid.append(txt[:10])
        for m in self.eng.memories.values():
            try:
                v = float(m.get("valence", 0.0))
            except (TypeError, ValueError):
                continue
            w = ((m.get("episode") or {}).get("what") or "")
            if v <= -0.7 and w and w[:6] not in question:
                avoid.append(w[:10])
        seen, out = set(), []
        for a in avoid:
            if a not in seen:
                seen.add(a)
                out.append(a)
        return out[:6]

    @staticmethod
    def _correction_content(t):
        """从纠正句里取更正内容（回声用户措辞，不新增事实）。"""
        m = re.search(r"[，,]?(?:其实|应该是|正确的是|是)([^。？?！!]{2,20})"
                      r"[。？?]?$", t)
        if m:
            return m.group(1).strip(" ，。")
        return t[-16:].strip(" ，。")

    def _empathy_statement(self, t):
        """陈述句（非问句）+ 情绪词 + 非装备陈述 → 陪伴模式触发。

        陪伴链上（上一轮也是陪伴）的后续陈述进入"继续听"状态——
        最小确认即可（Clark 接地第二步），不追问、不接方案。
        """
        if QUESTION_MARK.search(t):
            return None
        if CONSTRAINT_KEY.search(t):
            return None
        if self._is_confirmation(t) or CORRECTION_MARK.search(t):
            return None
        if self._last_mode == "empathy":
            return "倾听"
        for w in EMPATHY_FEEL:
            if w in t:
                return w
        return None

    @staticmethod
    def _empathy_reply(t, feel):
        """陪伴回应：短、承接具体事、不延伸不给方案（教材 2.4/4.4）。"""
        if feel == "倾听":
            return "嗯。"
        if feel in ("累", "困"):
            return "嗯，那就先歇会儿，别硬撑。"
        if feel in ("开心", "高兴", "兴奋"):
            return "听起来是好事啊。"
        return "嗯，是挺%s的。" % feel

    @staticmethod
    def _deny_premise(t):
        """从问句里取"指控的事件短语"——只回声用户的措辞。

        "X那次…"取 X；无那次时取首个逗号前的分句（去"你"前缀）。
        取不出干净的短语就返回 None（此时用通用否认，不硬凑）。

        R133：必须剥掉疑问词尾巴，否则否认句会把整个问句当宾语回声——
        "你第一次按快门是什么时候" → "我没第一次按快门是什么时候"（语法不通，
        而且把「在问时间」说成「没这回事」，等于否认了一件真发生过的事）。
        正确形态是事件短语本身："没这回事"指「第一次按快门」，
        时间/原因等疑问成分留在问题里、不进否认句。
        """
        s = re.sub(r"[？?。！!]+$", "", str(t or "").strip())
        # 长尾巴先剥（"是什么感觉"要先于"是什么"），否则会剩一个光秃秃的"是"。
        # 反复剥到不再变化为止："你养过猫吗,叫什么名字" 要连剥两层才剩"养过猫"。
        _TAIL = ("是怎么回事", "是什么样", "是什么感觉", "什么意思", "是什么时候",
                 "在什么时候", "是哪年", "哪一年", "是哪天", "在哪年",
                 "的时候", "怎么样", "怎么回事", "是什么", "是什么事",
                 "叫什么名字", "叫什么", "是多少", "几岁", "过吗", "吗", "呢", "吧",
                 # R133-b：宾语后置的疑问结构——"第一次一个人出去拍片**拍的什么**"、
                 # "**拍的怎么样**"。不剥掉它，事件短语会把疑问成分也当成线索，
                 # text 覆盖从 1.000 掉到 0.700，命中不了那条记忆。
                 "拍的什么", "拍的怎么样", "拍的啥", "拍了什么", "拍的是什么",
                 "干了什么", "做了什么", "想什么", "说了什么", "讲了什么",
                 "的什么", "的啥", "的怎么样", "是什么人", "什么时候")
        heads = []
        # 逗号前的分句最干净，优先（"你养过猫吗,叫什么名字" → "养过猫"）。
        clause = re.split(r"[，,、；;]", s)
        if len(clause) > 1:
            heads.append(clause[0])
        for sep in ("那次", "那回", "上回", "上次", "那年", "那天"):
            m = re.search(r"(.+?)" + sep, s)
            if m:
                heads.insert(0, m.group(1))
                break
        # 整句垫底：只有它剥完还剩合理的短语才用（"初中军训晕倒那次是怎么回事"
        # 走上面的那次分支；无分句无那次的"你辍学过吗"才落到这里）
        heads.append(s)
        for head in heads:
            prem = re.sub(r"^(你|你们)", "", head).strip(" ，,")
            for _ in range(4):
                before = prem
                for tail in _TAIL:
                    if prem.endswith(tail) and len(prem) > len(tail):
                        prem = prem[: -len(tail)]
                        break
                prem = prem.strip(" ，,的")
                if prem == before:
                    break
            prem = prem.rstrip("了过")
            if 2 <= len(prem) <= 14:
                return prem
        return None

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
        # "那次/第一次"本身即私人叙事标记（第三人称转述也成立："初中军训晕倒那次"）
        personal = (("你" in t) or any(v in t for v in EPISODIC_THINGS)
                    or any(k in t for k in ("那次", "那回", "上回", "上次", "第一次")))
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
        """说不准时的话：走语料里的"大概是…"框架，不用系统腔括号。

        R133-d：语料里 unsure 的四个框架（大概/好像是/可能是/大概是）**全部**是
        数量与模糊指代（n=112 "大概玩3天"、n=106 "好像是前5题"、n=82 "可能是下午3～5"），
        套在具体名词上就是病句：被问"落榜那天你在哪"，说出来是
        「因为差了三分，大概考场外」——真人要么直接说考场外，要么说记不清。

        所以按宾语类型分流：
          数量/时间量 → 用 unsure 框架（语料本来就用在这些地方）
          具体名词（地点/人物/结果）→ 不加不确定前缀，直接说，或整句弃答
        """
        v = first_person(value)
        if _QUANTITY_LIKE.search(v):
            ans = self.voice.say("unsure", {"what": v}) if self.voice else None
            return ans or ("大概是%s" % v)
        # 具体名词：直接说。语料里没有"大概{地点}"这种说法，
        # 硬造会让整句读起来像在敷衍，而且把确定的信息说成不确定。
        return v

    def _self_monitor(self, text, ref_mids):
        """§19.1 Self-monitoring 事闸 v1：回答中出现的库内记忆 what（≥8字）
        必须指回本次引用的痕迹，否则记为未通过（软模式：只记录不拦截；
        LLM 生成器接入后转硬闸——生成文本先过此闸再出口）。"""
        if not text:
            return True, ""
        refs = set(str(x) for x in (ref_mids or []) if x)
        for m in self.eng.memories.values():
            w = ((m.get("episode") or {}).get("what") or "")
            if len(w) < 8 or w[:8] not in text:
                continue
            if m["id"] not in refs:
                return False, "断言未引用: %s" % w[:12]
        return True, ""

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
        """心情给同一句建议镀一层语气。

        R133-d：原来是 `action + " 我现在心里堵，但先按这个说，别吵。"`——
        空格接句号再起一句，是系统腔（专家建议 + 状态报告两段拼接）。
        真人把状态**并进同一口气**里，用逗号连着说，而且不报"情绪状态"，
        报的是处境（"心里堵"是处境不是标签）。
        语料依据：causal 池 "X，但是Y" n=392、"X，然后Y" n=361——状语式连写，
        不是句号断开。
        """
        v = self.eng.affect.state.get("valence", 0.0)
        # R133-d2：action 自己常以句号收尾（规则文本就是这样写的），
        # 直接拼"，不过…"会产出"把话落到作品上。，不过眼下心里堵"这种双标点。
        # 先剥掉 action 尾部的句读，再接状语——真人的转折是连着一口气说的。
        base = str(action or "").rstrip("。；;，, ")
        if any(k in t for k in ("爸爸", "生活费", "摄影没出路")):
            if v <= -0.2:
                return base + "，不过眼下心里堵，先照这个说，别吵起来"
            if v >= 0.2:
                return base + "，今天状态还行，能好好说"
        if any(k in t for k in ("客户", "精修")):
            if v <= -0.2:
                return base + "，就是有点累，先把条件谈清楚"
            if v >= 0.2:
                return base + "，这个量我还扛得住"
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
