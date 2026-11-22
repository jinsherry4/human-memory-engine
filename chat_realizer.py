# -*- coding: utf-8 -*-
"""chat_realizer.py — 表面实现器：把记忆槽位说成一句人话。

它**只负责怎么说**，不负责说什么：
  - 说什么 = 引擎检索出来的记忆内容（槽位）
  - 怎么说 = 这里生成的句子（模型，或退回模板库）

安全设计（这是它能不能进引擎的关键）：
  1. **保真校验**：生成句必须保住"事情"本身（字符重合度门槛），
     否则判定为编造/跑题 → 返回 None，调用方退回模板库。
  2. **不许冒出新实体**：生成句里除高频口语字/语气词之外的字符，
     必须都出现在槽位内容里。
  3. **长度与格式**：单句、不过长、不带换行与引号。
  4. **默认关闭**：必须显式设置环境变量 WEN_VOICE_MODEL=<模型目录> 才启用；
     没装 torch/transformers 或模型不在，都自动退回模板，不影响引擎自保。

依赖 torch+transformers（GPU 环境跑；CPU 也能跑但慢）。
"""
import os
import re

# 高频口语功能字/语气词/连接词：它们不属于"内容"，出现不算编造。
# （含常见双字连接词的字：然后所以但是不过因为由于结果后来其实感觉觉得
#   大概可能应该好像似乎直接已经还是就是不是一个什么怎么这样那样）
FUNC_CHARS = set(
    "了着过吗呢吧啊哦嗯呀哈呗嘛啦咯哇噢唔唉哎呦哟嘿嗨"
    "我你他她它们这那哪谁什怎但而且就都也还也很又只"
    "在有没不没是是的会能要说说道看想觉觉得知道记得忘"
    "个的一二三两多少点些太更最挺有点从到跟把被让与及并且则即若如比"
    "或而所其此该由向朝趁随每各别另再又还也只就是都"
    "然后所以但过因结果后其实感觉大概可能应该好像似乎直接已经"
    "什么怎么这样那样一个点些还太更最挺有点觉得知道记得说告诉"
    "为什怎哪谁几时年月日上下里中前后边"
)
STRIP_RE = re.compile(r"[\r\n\t「」\"'“”‘’]")

# 槽位名 → 训练时用的中文标签（必须与 build_dataset2.py 一致）
SLOT_LABEL = {
    "what": "事情", "who": "人", "where": "地点", "when": "时间",
    "feel": "感觉", "why": "原因", "result": "后来",
}
SLOT_ORDER = ("what", "who", "where", "when", "feel", "why", "result")
SYSTEM = ("你在用聊天软件回消息。照着给的记忆内容，用一两句自然的中文口语说出来，"
          "像熟人发消息那样：短、不用标点结尾、不写解释、不要罗列字段。")


class Realizer:
    def __init__(self, path=None, min_overlap=0.65, max_len=60):
        self.model = None
        self.tok = None
        self.min_overlap = min_overlap
        self.max_len = max_len
        self.enabled = False
        self.stat = {"try": 0, "ok": 0, "reject": {}}
        self.debug = bool(os.environ.get("WEN_VOICE_DEBUG"))
        path = path or os.environ.get("WEN_VOICE_MODEL")
        if not path or not os.path.isdir(path):
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self.torch = torch
            self.tok = AutoTokenizer.from_pretrained(path)
            kw = {"dtype": torch.bfloat16}
            try:
                m = AutoModelForCausalLM.from_pretrained(path, **kw)
            except TypeError:
                m = AutoModelForCausalLM.from_pretrained(path,
                                                        torch_dtype=torch.bfloat16)
            if torch.cuda.is_available():
                m = m.to("cuda")
            else:
                m = m.to("cpu")
            m.eval()
            self.model = m
            self.enabled = True
            if self.debug:
                import atexit
                import sys

                def _dump():
                    print("[realizer] 统计: 尝试 %d, 采用 %d, 拒绝 %s" % (
                        self.stat["try"], self.stat["ok"],
                        self.stat["reject"]), file=sys.stderr)
                atexit.register(_dump)
        except Exception as e:      # 装不上/模型坏了 → 引擎照旧跑
            self.enabled = False
            self.err = str(e)

    # ---------- 校验 ----------
    @staticmethod
    def _overlap(a, b):
        """a 的字符有多大比例出现在 b 里。"""
        a = re.sub(r"\s+", "", str(a or ""))
        b = re.sub(r"\s+", "", str(b or ""))
        if not a:
            return 1.0
        chars = [c for c in a if c not in FUNC_CHARS]
        if not chars:
            return 1.0
        return sum(1 for c in chars if c in b) / float(len(chars))

    @staticmethod
    def _new_entities(out, slots, allow_text=None):
        """输出里冒出了槽位内容之外的实义 → 判为编造。

        合法字符集 = 槽位内容 ∪ allow_text（机械版整句）∪ 高频功能字。
        判据：只看**连续两个以上**的未知字。单个未知字多半是连接词
        （"然后/所以/因为"里的字），不算编造；连续出现才像编出来的人名地名。
        """
        allowed = set("".join(str(v) for v in slots.values()))
        if allow_text:
            allowed |= set(str(allow_text))
        unknown = [c for c in out
                   if c not in FUNC_CHARS and c not in allowed
                   and re.match(r"[一-鿿A-Za-z0-9]", c)]
        # 按原串扫描，统计连续未知字的游程（单个=连接词，两个以上=像编出来的实体）
        best = 0
        cur = 0
        for c in out:
            if c in FUNC_CHARS or c in allowed:
                cur = 0
                continue
            if re.match(r"[一-鿿A-Za-z0-9]", c):
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return set(unknown) if best >= 2 else set()

    @staticmethod
    def _ordered_ok(slots, out):
        """槽位里的内容不能被拆开重排。

        模型会把槽位当原料重新组合，于是"年三十前"被拆成"去年三十在家中前"、
        "我把曝光补偿"被换成"我把他曝光补偿"（人称都换了）。
        判据：每个槽位的实义字符必须在输出里**按原顺序**出现（有序子序列）。
        人称(我/他/她)算实义字符，不当虚词放过。
        """
        for v in slots.values():
            if not v:
                continue
            chars = [c for c in re.sub(r"\s+", "", str(v))
                     if c not in FUNC_CHARS or c in "我你他她"]
            if not chars:
                continue
            pos = 0
            for c in out:
                if pos < len(chars) and c == chars[pos]:
                    pos += 1
            if pos < len(chars):
                return False
        return True

    @staticmethod
    def _extra_chars_ok(out, slots):
        """除槽位内容之外，模型只准加**功能字/连接词**，不准加别的。

        有序子序列检查挡不住"插入式重排"：原槽位"年三十前"被插成"去年三十前"，
        字面顺序仍满足子序列，但语义已经坏了（另一会话 R129 指出）。
        所以再加一道：输出里多出来的字，必须全是高频功能字或连接词
        （因为/所以/然后/但是/不过/结果/搞…），出现别的字就是模型自己加料。
        """
        inside = set("".join(str(v) for v in slots.values()))
        for c in out:
            if c in inside or c in FUNC_CHARS:
                continue
            # 标点与空白不算"加料"（模型会自己加逗号和空格）
            if c.isspace() or c in "，。、；：？！“”「」『』（）()《》〈〉…—-·,.!?:;":
                continue
            if c in "因为所以然后但是不过结果搞而且就是还也就都挺有点嘛呢哦哈呗啊嗯呀了着过":
                continue
            return False
        return True

    def check(self, out, slots, allow_text=None):
        """内容保全：事件本身必须在，整体内容覆盖率也要够。

        判据分三层：
          1. "事情"（事件本体）必须几乎逐字在 → 防止模型说到别的事上去；
          2. 事件之外的内容（地点/时间/感觉/原因/后来）整体覆盖率 ≥80%
             → 防止它把判分盯着的关键词（常在这些字段里）悄悄吞掉；
          3. 不许冒出**机械版整句与槽位之外**的实义 → 防止编造。
             allow_text 是机械版整句，当作合法字符的参照集。
        "人"不单列要求：训练语料的切分器几乎不产该槽位，模型没学过用它，
        而且人物名通常已经写在"事情"里（"爸爸说摄影没出路"）。
        """
        if not out or not out.strip():
            return self._reject("空", out)
        out = out.strip()
        if len(out) > self.max_len or "\n" in out:
            return self._reject("过长/换行", out)
        what = slots.get("what") or ""
        if what and self._overlap(what, out) < 0.75:
            return self._reject("丢事件", out)
        rest = {k: v for k, v in slots.items()
                if k not in ("what", "who") and v}
        if rest:
            total = cover = 0
            for v in rest.values():
                chars = [c for c in re.sub(r"\s+", "", str(v)) if c not in FUNC_CHARS]
                if not chars:
                    continue
                total += len(chars)
                cover += sum(1 for c in chars if c in out)
            if total and (cover / float(total)) < 0.80:
                return self._reject("内容覆盖不足", out)
        bad = self._new_entities(out, slots, allow_text)
        if bad:
            return self._reject("新实体:%s" % "".join(sorted(bad)), out)
        if not self._ordered_ok(slots, out):
            return self._reject("槽位被拆开重排", out)
        if not self._extra_chars_ok(out, slots):
            return self._reject("模型自己加了料", out)
        return True

    def _reject(self, why, text=None):
        self.stat["reject"][why] = self.stat["reject"].get(why, 0) + 1
        if self.debug and text:
            import sys
            print("[realizer] 拒(%s): %s" % (why, text), file=sys.stderr)
        return False

    # ---------- 生成 ----------
    def realize(self, mode, slots, allow_text=None):
        """返回一句人话；不合格返回 None（调用方退回模板）。

        allow_text：机械版组装出来的整句，当作"这些字是合法的"参照集。
        槽位变少以后，"然后/所以/挺/有点"这类合法连接词很容易被判成新实体；
        拿机械版整句做参照集，判据就稳得多。
        """
        if not self.enabled or not slots or not slots.get("what"):
            return None
        self.stat["try"] += 1
        lines = ["【内容】"]
        for k in SLOT_ORDER:
            v = slots.get(k)
            if v:
                lines.append("- %s：%s" % (SLOT_LABEL[k], v))
        lines.append("【说一句话】")
        prompt = self.tok.apply_chat_template(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": "\n".join(lines)}],
            tokenize=False, add_generation_prompt=True)
        try:
            ids = self.tok(prompt, return_tensors="pt").to(self.model.device)
            with self.torch.no_grad():
                # 贪心解码（do_sample=False）：实现器开着时同一句问必须每次给同一句
                # 答案——整个项目的回归靠 scores.json 的历史对比，采样会让判分飘。
                # 用确定性换措辞多样性，这是刻意的取舍。
                out = self.model.generate(
                    **ids, max_new_tokens=48, do_sample=False,
                    repetition_penalty=1.05,
                    pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id)
            gen = out[0][ids["input_ids"].shape[1]:]
            text = STRIP_RE.sub("", self.tok.decode(gen, skip_special_tokens=True)).strip()
            text = text.split("\n")[0].strip()
            if text.endswith(("。", ".", "!", "！", "?", "？")):
                text = text[:-1].strip()
        except Exception:
            return None
        if not self.check(text, slots, allow_text):
            return self._reject("闸门未过", text)
        self.stat["ok"] += 1
        if self.debug:
            import sys
            print("[realizer] OK: %s" % text, file=sys.stderr)
        return text
