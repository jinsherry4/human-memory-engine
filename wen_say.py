# -*- coding: utf-8 -*-
"""wen_say.py — 把一条记忆说成一句人话（R129 起，R130 扩展）

R129 建立的骨架（字段选择 + 从句组装）在 R130 补三件事：

1. **情绪框架逐词选**（`feel_frames.json`）
   真人聊天里"挺{feel}的"只在"好玩"上常见；"笃定/郑重/警觉"这类词在 29.8 万条
   真实消息里一次都没出现。所以情绪尾巴的框架必须**按词从语料里查**，
   查不到前缀框架的词就**不带出来**（宁可不说，也不说"挺笃定的"这种不像人的话）。

2. **立场 / 因果连接词层**
   真人表达对过去的评价靠的是评价性副词（其实 753 / 反正 356 / 还好 198 /
   幸好 50）和连接词（X但是Y 396 / X所以Y 95 / 因为X 521 / 然后X 1029），
   而不是自我报告情绪标签（"我很笃定"这种真人不这么说）。
   因果只接**真因果**：why 字段才是原因 → "因为{why}"；result 是结果 → "然后{result}"。
   绝不"因为{result}"（那是编造因果）。

3. **长度预算**
   答案要短：真人聊天中位 6 字，回忆类也该在 15 字上下。
   装不下时从**情绪尾巴 → 结果尾巴 → 状语从句**依次砍，先砍装饰后砍信息。

**所有连接词都来自真实语料**（`chat_voice.json`，build_voice.py 挖出），
本模块不造句，只做"选哪一维"和"怎么拼"。
"""
import json
import os
import re

from chat_voice import first_person

_HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 泛化词：说了等于没说，不值得单独占一个状语位置 ----
GENERIC_WHERE = frozenset([
    "家", "老家", "学校", "教室", "宿舍", "幼儿园", "大学", "公司", "外面",
    "那边", "这里", "路上", "办公室", "画室", "宿舍楼", "教室", "学校",
])
# 非处所：这些是"媒介/场合"不是地方。"在电话的时候"不成话。
MEDIUM_WHERE = frozenset([
    "电话", "微信", "线上", "消息", "短信", "手机", "网课", "线上聊天",
])
GENERIC_WHEN = frozenset([
    "白天", "那天", "以后", "以前", "当时", "后来", "现在", "平时", "那天",
    "有一天", "某天",
])
# 通用短语：问句里这些词不带内容指向，匹配字段时先剔掉，
# 否则"第一次进暗房是什么感觉"会因为"第一次"匹配上 why="第一次冲卷"。
GENERIC_PHRASES = (
    "第一次", "那次", "那回", "那会儿", "那次儿", "上次", "以前", "之前",
    "后来", "当时", "有时候", "小时候", "最开始", "头一次",
)
# 日期/季节/场合类的时间词：值得做状语（"三月的时候"）
DATEISH = re.compile(
    r"(月|年|季|节|周末|周[一二三四五六日天]|寒假|暑假|开学|期末|春节|除夕|"
    r"中秋|国庆|清明|冬至|春|夏|秋|冬|元旦)")
# 核心句开头自带的时间标记（"那天…""年三十前…"）——此时不要再叠时间状语
_TIME_HEAD = re.compile(r"(那天|那会儿|当时|那年|年前|年三十前|时候|夜里|早上|"
                         r"晚上|下午|中午|年前)")


def _load_feel_frames():
    """情绪词 → 该词在真实聊天里实际用的框架。

    规则（R130）：
      1. 该词在语料里 0 次 → 不带出来（连真人都不这么用的词，别让她说）
      2. 有**前缀框架**（有点X/很X/好X/太X/真X/挺X…）→ 用出现最多的那个
      3. 只有后置形式（…的/…地，定语用法）或只有裸用 → 不带出来
    """
    path = os.path.join(_HERE, "feel_frames.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}, set()
    words = data.get("words") or data
    out = {}
    known = set()
    for w, v in (words or {}).items():
        if not isinstance(v, dict):
            continue
        total = int(v.get("总次数") or 0)
        if total <= 0:
            continue          # 语料里一次都没出现过 → 不带出来
        known.add(w)
        frames = v.get("框架") or {}
        # 只收**前缀**框架：后置的"…的/…地"是定语/副词形式，不能当句尾
        cand = [(k, n) for k, n in frames.items()
                if k != "裸用" and n >= 1 and not k.endswith(("的", "地"))]
        if not cand:
            continue
        cand.sort(key=lambda kv: (-kv[1], len(kv[0])))
        out[w] = cand[0][0]          # 已是完整字面（含词），直接当尾巴用
    return out, known


FEEL_FRAMES, FEEL_KNOWN = _load_feel_frames()

# 问句在问哪一维。真人先答被问的那一维——这既是人的说话习惯，
# 也正好让"问什么时候"就答时间、"问在哪"就答地点。
# 顺序有讲究：先原因、再感受、再地点、再时间、最后顺序。
DIMENSION = (
    ("why",    re.compile(r"(为什么|为啥|原因|怎么回事|咋回事|怎么会)")),
    ("feel",   re.compile(r"(什么感觉|感觉如何|心情|感受|什么感受|情绪|气氛|什么心情)")),
    ("where",  re.compile(r"(在哪|哪儿|哪里|什么地方|在家|在哪儿|地点|哪儿)")),
    ("when",   re.compile(r"(什么时候|啥时候|哪年|哪会儿|那会儿|何时|几号|日期)")),
    ("result", re.compile(r"(后来|然后|之后|结果|接着)")),
    ("who",    re.compile(r"(是谁|谁给的|谁拍|和谁|跟谁|谁让|谁说)")),
)

# 目标长度：真人聊天中位 6 字；回忆类答案放宽到 15 字上下（语料回忆句中位 ~15）
TARGET_LEN = 20
MAX_LEN = 24


def asked_dimension(question):
    """问句在问哪一维；问不出来返回 None。"""
    q = str(question or "")
    for dim, rx in DIMENSION:
        if rx.search(q):
            return dim
    return None


def _lcs_len(a, b):
    """最长公共子串长度（中文按字算）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def match_field(ep, question):
    """问句里的实词落在记忆的**哪一层**上。

    真人被问"个展主题叫什么"，她想起的是"主题叫窗"那一层，不是"拍了三年"。
    返回字段名（why/result/feel/where/when），没有明显对应返回 None。
    """
    q = str(question or "")
    if len(q) < 3:
        return None
    for ph in GENERIC_PHRASES:      # 剔掉通用短语，只拿有内容指向的词去匹配
        q = q.replace(ph, "")
    if len(q) < 2:
        return None
    best, best_len = None, 0
    for k in ("why", "result", "feel", "where", "when"):
        v = str(ep.get(k) or "")
        if not v:
            continue
        n = _lcs_len(q, v)
        if n > best_len:
            best_len, best = n, k
    # 阈值 3：两字的重合多半是"外婆""老师"这种通称，
    # 会把答案指到错的那一层（holdout w11：问"外婆见到通知书了吗"，
    # 结果匹配上了 why="外婆想亲手摸通知书"，而答案该是 result）。
    return best if best_len >= 3 else None


def _specific(dim, v):
    """这个地点/时间值值不值得单独说。"""
    if not v or len(v) > 10:
        return False
    if dim == "where":
        return v not in GENERIC_WHERE and v not in MEDIUM_WHERE
    if dim == "when":
        return v not in GENERIC_WHEN
    return True


def select_slots(ep, question="", arousal=0.4, valence=0.0, force_dim=None,
                 max_tails=2):
    """挑出这条记忆**该说哪几层**。

    返回 dict：
      core    核心小句（what，已改第一人称）
      dim     问句在问哪一维（None=没问出来）
      matched 问句点到的那一层（None=没对上）
      adv     状语从句 (维度, 值) 或 None
      tails   尾巴从句 [(维度, 值), ...]，最多 max_tails 条

    **尾巴优先级**：被问的那一维 > 问句点到的层 > result（具体物证）
    > feel（情绪）> why。
    情绪排在 result 之后——情绪尾巴不许挤掉更具体的时间/地点/物证。
    """
    if not ep:
        return {"core": "", "dim": None, "matched": None, "adv": None, "tails": []}
    core = first_person(ep.get("what") or "").strip(" ，,")
    dim = force_dim or asked_dimension(question)

    # ---- 状语从句：时间/地点做句首状语，不进逗号清单 ----
    adv_dim, adv_val = None, ""
    if dim in ("when", "where"):
        # 被问到的这一维必须说，哪怕值很泛（问"在家吗"就得答"家"）
        v = first_person(ep.get(dim) or "").strip(" ，,")
        if v and len(v) <= 12 and not (dim == "where" and v in MEDIUM_WHERE):
            adv_dim, adv_val = dim, v
    elif dim is None:
        w = first_person(ep.get("when") or "").strip(" ，,")
        p = first_person(ep.get("where") or "").strip(" ，,")
        # 日期/季节/场合最值得说；否则说具体的地点
        if _specific("when", w) and DATEISH.search(w):
            adv_dim, adv_val = "when", w
        elif _specific("where", p):
            adv_dim, adv_val = "where", p
        elif _specific("when", w):
            adv_dim, adv_val = "when", w
        elif _specific("where", p):
            adv_dim, adv_val = "where", p

    # ---- 尾巴从句 ----
    matched = match_field(ep, question)
    order = []
    if dim in ("why", "feel", "result", "who") and ep.get(dim):
        order.append(dim)
    if matched and matched not in order:
        order.append(matched)
    # 尾巴的**位置**也是优先级：被问/问句点到的层在最前，其次是结果（物证），
    # 再是原因，最后是情绪（最可丢）。长度不够时兜底保留的就是第一条。
    for k in ("result", "why", "feel"):
        if k not in order:
            order.append(k)
    tails = []
    for k in order:
        if len(tails) >= max_tails:
            break
        v = first_person(ep.get(k) or "").strip(" ，,")
        if not v:
            continue
        if k == adv_dim:
            # 已经做状语从句了，别再说一遍
            continue
        if k == "where" and v in MEDIUM_WHERE:
            continue
        if k == dim or k == matched:
            tails.append((k, v))
        elif k == "result" and len(v) >= 4:
            tails.append((k, v))
        elif k == "feel" and len(v) <= 8 and (arousal >= 0.45 or abs(valence) >= 0.4):
            tails.append((k, v))
        elif k == "why" and len(v) >= 3:
            tails.append((k, v))
    return {"core": core, "dim": dim, "matched": matched,
            "adv": (adv_dim, adv_val) if adv_dim else None,
            "tails": tails}


def _feel_clause(value):
    """情绪尾巴：框架按词从语料里查；查不到前缀框架就用"感觉{feel}"兜底。

    规则（R130）：
      1. 该词在语料里 0 次 → **不带出来**（真人都不这么用的词，别让她说）
      2. 有前缀框架（有点X/很X/好X/太X/真X/挺X…）→ 用出现最多的那个
      3. 只有裸用/定语形式，但语料里出现过 → 用"感觉{feel}"
         （"感觉{feel}"本身在语料里有 482 次支撑，是最强的情绪框架之一）
    """
    v = str(value or "").strip()
    if not v:
        return None
    frame = FEEL_FRAMES.get(v)
    if frame:
        return frame
    for w in FEEL_FRAMES:                 # 词里可能带修饰（"有点委屈"）
        if w in v and len(w) >= 2:
            return FEEL_FRAMES[w]
    if v in FEEL_KNOWN:                    # 兜底："感觉X"
        return "感觉" + v
    return None


def _tail_clause(dim, value, voice, valence):
    """把一个字段渲染成从句。"""
    if dim == "feel":
        return _feel_clause(value)
    return value


def _connect(dim, text, voice):
    """给尾巴接上语料里的连接词。

    - why  → "因为X"（why 字段本身就是原因，接因为不编造因果）
    - result → "然后X"（结果是后续动作，接然后是时间顺序）
    其它维度不加连接词。
    """
    if dim == "why":
        frame = voice.say("cause", {"why": text}) if voice else None
        return frame or ("因为" + text)
    if dim == "result":
        frame = voice.say("seq", {"what": text}) if voice else None
        return frame or ("然后" + text)
    return text


def _clip_tail(text, maxlen=16):
    """尾巴太长就截断——真人的补充句不会那么长（最多留两个小句）。

    **不能切在词中间**（"说比 CCD 有味道"不能切成"说比 CCD 有"），
    所以优先按小句边界切；切不动就宁可长一点也不切半个词。
    """
    t = str(text or "").strip()
    if len(t) <= maxlen:
        return t
    segs = re.split(r"([,，])", t)
    keep = ""
    n = 0
    for i in range(0, len(segs), 2):
        if n >= 2:
            break
        keep += segs[i] + (segs[i + 1] if i + 1 < len(segs) else "")
        n += 1
    keep = keep.rstrip(",，")
    if len(keep) <= maxlen:
        return keep
    cut = max(keep.rfind("，"), keep.rfind(","))
    if cut > 0:
        return keep[:cut]
    return keep


def realize(ep, voice, question="", arousal=0.4, valence=0.0, mode="recall",
            rot=0, force_dim=None, max_len=MAX_LEN):
    """把一条记忆说成一句人话。

    ep      : 记忆的字段字典（what/where/when/feel/why/result/who）
    voice   : ChatVoice（提供语料框架）
    question: 用户问句——决定先答哪一维
    force_dim: 强制先答某一维（followup 路径用："后来呢"→result，"为什么"→why）
    rot     : 轮换计数（同档轮换，避免句式老是同一个）

    返回一句话；框架填不上返回 None，调用方退回旧模板。
    """
    if not ep or not voice:
        return None
    sel = select_slots(ep, question=question, arousal=arousal, valence=valence,
                       force_dim=force_dim)
    core = sel["core"]
    if not core:
        return None
    adv = sel["adv"]
    tails = sel["tails"]

    # ---- 状语不重复核心句已有的信息 ----
    # 真人不会说"在影楼的时候开始在影楼兼职修图""在市美术馆的时候跟学姐去美术馆…"——
    # 状语值整个出现在核心句里、或与核心句重叠 ≥3 字，就不做状语
    # （省下的字数留给结果/物证）。重叠 2 字不算（"家门口" vs "老家赶来"
    # 撞的是"老家"，不是同一个地方）。
    if adv and (adv[1] in core or _lcs_len(adv[1], core) >= 3):
        adv = None
    # 核心句自己就带时间标记时，别再叠一个时间状语
    # （"在家的时候年三十前说…"——两个时间标记打架）。
    if adv and adv[0] == "when" and _TIME_HEAD.search(core[:6]):
        adv = None
    if adv and adv[0] == "where" and _TIME_HEAD.search(core[:6]):
        adv = None

    # ---- 组装：状语 + 核心 + 尾巴 ----
    def build(with_adv=True, tail_list=None, short_adv=False):
        parts = []
        if with_adv and adv:
            if short_adv:
                # 短状语：裸地/裸时间（"在家""春天"）——场景框架太长挤掉
                # 被问的那一维时，先试这个（2026-11-22 复查修复：长度预算
                # 此前会把被问的 where/when 随状语整句砍掉）。
                # 不自带尾逗号——join 统一补，否则出现"，,"
                v = adv[1]
                sv = v if (adv[0] == "when" or v.startswith(("在", "于"))) else ("在" + v)
                parts.append(sv)
                parts.append(core)   # 短状语只是前缀,核心句必须跟上(m17 教训)
            else:
                frame = voice.say("scene", {adv[0]: adv[1], "what": core},
                                  need_slot=adv[0])
                # 语料里的 scene 框架必须真带 {what} 槽——没有时核心句会被
                # 静默丢掉（m17"那会儿在评图室，，然后…"，2026-11-22 复查修复）
                if frame and (core[:4] in frame or core[:2] in frame):
                    parts.append(frame)
                else:
                    parts.append("%s，%s" % (adv[1], core))
        else:
            parts.append(core)
        for t in (tail_list if tail_list is not None else tails):
            d, v = t[0], t[1]
            c = _tail_clause(d, v, voice, valence)
            if not c:
                continue
            if len(t) == 3 and t[2] == "plain":
                # 截短尾巴不带连接词——预算按裸从句算，连接词会挤掉内容
                parts.append(_clip_tail(c))
            else:
                parts.append(_connect(d, _clip_tail(c), voice))
        return "，".join(parts)

    out = build()
    # ---- 长度预算：按**信息量**排一串候选方案，挑第一个装得下的 ----
    # 砍的优先级：情绪(最可丢) > 原因 > 状语从句 > 物证/结果(最不能丢)。
    # 不能按位置砍——尾巴顺序是"被问的那一维"在前，物证在后，
    # 按位置砍会先把物证砍掉（holdout w11 就是这么丢的）；
    # 也不能在兜底时把尾巴全加回来——那会把裁剪撤销。
    # 被问/问句点到的那一维进 keep——长度预算绝不先砍它
    # （"在家吗"就答家、"主题叫什么"就答窗，2026-11-22 复查修复）。
    keep = {d for d in (sel["dim"], sel["matched"]) if d}
    no_feel = [t for t in tails if t[0] != "feel"]
    no_feel_why = [t for t in tails
                   if t[0] not in ("feel", "why") or t[0] in keep]
    only_result = [t for t in tails if t[0] == "result" or t[0] in keep][:1]

    def _clipped(tail_list):
        """截短尾巴而不是整条丢——物证最不能丢（阶梯原文）。

        预算按裸从句算（plain，连接词不占字），先剥"我把/我"前缀
        （first_person 的残留，真人口语里不会重复主语）。
        """
        room = max_len - len(core) - 1
        out_tails = []
        for t in tail_list:
            d, v = t[0], t[1]
            if room < 4:
                break
            if v.startswith("我把") and len(v) - 2 >= 4:
                v = v[2:]
            elif v.startswith("我") and len(v) - 1 >= 4:
                v = v[1:]
            if len(v) > room:
                # 把字句省略主语是汉语的自然省略（"外婆把通知书包了三层红纸"
                # →"把通知书包了三层红纸"），内容零损失（holdout7 w11 教训）
                m = re.match(r"^(.{1,3}?)把(.+)$", v)
                if m and len(m.group(2)) >= 4:
                    v = m.group(2)
            cv = _clip_tail(v, room)
            if cv:
                out_tails.append((d, cv, "plain"))
                room -= len(cv) + 1
        return out_tails

    cands = [
        build(tail_list=tails),
        build(tail_list=no_feel),
        build(tail_list=no_feel_why),
        build(short_adv=True, tail_list=no_feel_why),   # 短状语先于去状语
        build(with_adv=False, tail_list=no_feel_why),   # 砍状语，保住结果
        build(with_adv=False, tail_list=_clipped(no_feel_why)),   # 截短保物证
        build(with_adv=False, tail_list=only_result),   # 再砍原因
        build(with_adv=False, tail_list=_clipped(only_result)),
    ]
    for text in cands:
        if len(text) <= max_len:
            out = text
            break
    else:
        # 物证宽限：只剩核心但 result 存在时,允许 +3 字保留结果小句
        # （"物证最不能丢"的最后一道,2026-11-22 复查修复）
        res = [t for t in tails if t[0] == "result"][:1]
        if res:
            # 宽限路径用裸从句(不带"然后"连接词)——连接词的两格会把物证
            # 再挤出去(m24 教训:28>27 差两格)
            out = build(with_adv=False,
                        tail_list=[(res[0][0], res[0][1], "plain")])
        else:
            out = core
        if len(out) > max_len + 3:
            out = core

    # ---- 外框：回忆标记 或 立场副词（轮换）----
    # 有时间状语时**不能**再叠"上次/之前/以前"——两个时间标记会打架
    # （"上次年三十前说今年不能串门"）。
    time_mark_conflict = ("上次", "之前", "以前") if adv else ()
    if mode == "recall":
        if "记得" in str(question or ""):
            ans = voice.say("recall", {"what": out},
                            exclude_prefixes=time_mark_conflict)
        elif rot % 3 == 2:
            # 立场副词：真人表达对过去的态度靠它，不靠自我报告情绪
            ans = voice.say("stance", {"what": out})
            # "还好/幸好"只对正向记忆成立
            if ans and (valence < 0) and ans[:2] in ("还好", "幸好"):
                ans = voice.say("recall", {"what": out},
                                exclude_prefixes=time_mark_conflict)
        else:
            ans = voice.say("recall", {"what": out},
                            exclude_prefixes=time_mark_conflict)
        if ans:
            return ans
    elif mode == "gist":
        ans = voice.say("gist", {"what": out})
        if ans:
            return ans
    return out


def realize_followup(ep, voice, kind, question="", arousal=0.4, valence=0.0,
                     rot=0, max_len=MAX_LEN):
    """追问路径的专门实现："后来呢" / "为什么" / "当时呢"。"""
    if not ep:
        return None
    dim = {"后来": "result", "为什么": "why", "当时": "where"}.get(kind)
    if dim is None:
        return None
    v = first_person(ep.get(dim) or "").strip(" ，,")
    if not v:
        return None
    if kind == "为什么":
        frame = voice.say("cause", {"why": v}) if voice else None
        return frame or ("因为" + v)
    if kind == "后来":
        # 追问"后来呢"要的是**结果那一层**，不是把整件事重说一遍
        if v.startswith("后来"):
            return v
        if any(k in str(question or "") for k in ("后来", "然后", "接着", "之后")):
            return "后来" + v
        return v
    return realize(ep, voice, question=question, arousal=arousal,
                   valence=valence, mode="recall", rot=rot,
                   force_dim=dim, max_len=max_len)
