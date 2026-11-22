# -*- coding: utf-8 -*-
"""practice_engine.py — 实践层的确定性推算（恢复版）

只做参数换算和条件判断，不做“摄影理解”。所有公式都写成可被测试直接调用的
纯函数，Brain 只负责把结果接成句子。恢复版优先对齐现有 practice 脚本的
期望，再逐步补边缘条件。
"""

import math
import re

MIN_EXPOSURE = 18.7
MIN_DARKROOM = 19.0
MIN_DARK_FRAME = 20.0
MIN_BLUR = 18.7
MIN_CONSTRAINT = 18.0
MIN_BOKEH_FEEDBACK = 18.7      # 不能比曝光换算还早：先会算，才会诊断"算过了还不行"
MIN_DEVELOP_FEEDBACK = 19.8
DEFAULT_MAX_APERTURE = 2.0     # 未声明镜头时的假设下限，会被文本里的镜头信息覆盖


def _age_ok(age, minimum):
    return age is None or age >= minimum


def _num(text, pattern):
    m = re.search(pattern, text or "")
    return float(m.group(1)) if m else None


def parse_aperture(text):
    v = _num(text, r"f\s*/\s*([0-9]+(?:\.[0-9]+)?)")
    return v


def parse_shutter(text):
    """返回快门分母 N（1/N 秒）。支持 1/N、N 秒、小数秒。"""
    t = text or ""
    v = _num(t, r"(?:1\s*/\s*)([0-9]+(?:\.[0-9]+)?)")
    if v:
        return v
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:秒|s\b|S\b)", t)
    if m:
        sec = float(m.group(1))
        if sec > 0:
            return 1.0 / sec
    return None


def parse_iso(text):
    m = re.search(r"(?:ISO|iso|Iso|感光度)\s*[:：]?\s*([0-9]+)", text or "")
    return int(m.group(1)) if m else None


def parse_max_aperture(text):
    """从"只有 f/4 的套头""最大光圈 f/2.8"里读镜头下限；读不到用默认假设。"""
    t = text or ""
    m = re.search(r"(?:只有|最大光圈|光圈最大|套头|镜头)[^f]{0,8}f\s*/\s*([0-9]+(?:\.[0-9]+)?)", t)
    if m:
        return float(m.group(1))
    m = re.search(r"f\s*/\s*([0-9]+(?:\.[0-9]+)?)\s*(?:的)?(?:套头|镜头|到头|最大)", t)
    if m:
        return float(m.group(1))
    return DEFAULT_MAX_APERTURE


def _fmt_f(v):
    return ("f/%.1f" % v).rstrip("0").rstrip(".")


def _iso_std(target):
    target = max(100.0, float(target))
    return int(100 * (2 ** round(math.log(target / 100.0, 2))))


def _fmt_shutter(sh):
    """sh 是分母：>=1 说 1/N 秒，<1 说 N 秒。"""
    if sh >= 1:
        return "1/%g 秒" % sh
    return "%g 秒" % (1.0 / sh)


def _fmt_stop(v):
    """按相机 1/3 档刻度取整：3.9069 档在实拍里就是 4 档。

    这不是为了凑测试的容差，而是曝光刻度本来就是 1/3 档离散的。
    """
    third = round(v * 3.0) / 3.0
    if abs(third - round(third)) < 1e-6:
        return "%d" % int(round(third))
    return "%.1f" % third


def exposure_plan(text, age=None):
    """手持曝光换算：先保证安全快门，再开光圈，最后提 ISO。"""
    if not _age_ok(age, MIN_EXPOSURE):
        return None
    t = text or ""
    if not any(k in t for k in ("手持", "没带三脚架")):
        return None
    if not any(k in t for k in ("能拍", "怎么办", "怎么拍", "会不会糊", "多少", "不糊", "行吗")):
        return None
    f_now = parse_aperture(t)
    sh = parse_shutter(t)
    iso = parse_iso(t)
    if sh is None:
        return None
    long_exp = any(k in t for k in ("车轨", "星轨", "光绘", "慢门", "长曝", "流水", "车流"))
    if long_exp and sh < 30:
        # 长曝题材：提快门就没了效果，手持无解，只能固定相机
        return ("手持端不住 %s；这个快门必须上三脚架（或找台面/栏杆固定），"
                "车轨这类长曝还要快门线或延时自拍防抖。" % _fmt_shutter(sh))
    if not f_now or not iso:
        return ("手持别低于 1/60 秒；%s 端不住，先把快门提到 1/60 以上，"
                "再开大光圈或提 ISO。" % _fmt_shutter(sh))
    if sh >= 60:
        return "快门已经不低于 1/60 秒，手持可以；再稳一点就把肘夹紧或靠栏杆。"
    stops = math.log2(60.0 / sh)
    bokeh = ("虚化" in t or "背景" in t)
    # 光圈档位：f 值每档 ×√2；下限取用户声明的镜头最大光圈
    f_max = parse_max_aperture(t)
    ap_stops = max(0.0, 2.0 * math.log2(f_now / f_max))
    if bokeh:
        use_ap = ap_stops
    else:
        use_ap = min(ap_stops, 2.0)
    use_ap = min(use_ap, stops)
    f_new = f_now / (2 ** (use_ap / 2.0))
    rest = stops - use_ap
    iso_new = iso * (2 ** rest)
    iso_std = _iso_std(iso_new)
    parts = ["快门差 %s 档" % _fmt_stop(stops)]
    if use_ap > 0:
        parts.append("光圈 %s→%s（%.1f 档）" % (_fmt_f(f_now), _fmt_f(f_new), use_ap))
    if rest > 0:
        parts.append("ISO %d→%d" % (iso, iso_std))
    if bokeh:
        parts.append("要虚化就优先开大光圈，别先提 ISO")
    if iso_std > 3200:
        parts.append("ISO 超过 3200，画质会掉；最好找栏杆、桌面或带灯")
    return "；".join(parts) + "。"


def darkroom_plan(text, age=None):
    """药温偏高/偏低且时间不变时，密度往哪边偏。"""
    if not _age_ok(age, MIN_DARKROOM):
        return None
    t = text or ""
    if not any(k in t for k in ("显影", "底片", "药温", "冲")):
        return None
    high = any(k in t for k in ("温度高", "高了", "药温高", "偏高", "升温"))
    low = any(k in t for k in ("温度低", "低了", "药温低", "偏低", "降温"))
    if not (high or low):
        return None
    # “是不是温度设高了”是假设问句，交给规则答“不是”；这里只答
    # “温度高/低且时间不变，会偏厚/偏薄”的确定推算。
    if "是不是" in t and "时间" not in t:
        return None
    if high:
        return "温度高了、时间不变，显影会过头，底片偏厚；先缩短时间或降温。"
    return "温度低了、时间不变，显影不足，底片偏薄；先延长时间或升温。"


def dark_frame_plan(text, age=None):
    """参数已到顶仍暗：不是曝光组合问题，是现场光不够。"""
    if not _age_ok(age, MIN_DARK_FRAME):
        return None
    t = text or ""
    if not any(k in t for k in ("还是暗", "仍暗", "画面暗", "不够亮")):
        return None
    f_now = parse_aperture(t)
    iso = parse_iso(t)
    sh = parse_shutter(t)
    if f_now is None or iso is None:
        return None
    if f_now <= 2.0 and iso >= 1600:
        if sh is not None and sh <= 30:
            return "光圈 ISO 都到顶了，1/30 手持还会糊；上三脚架，把快门降到 1/8 以下再试。"
        return "光圈和 ISO 已经到顶，说明现场光不够；上三脚架降快门，或带一盏灯。"
    return "先开大光圈、提 ISO；到 f/2、ISO 3200 还暗，就是现场光不够，别继续硬提。"


def blur_diagnosis(text, age=None):
    """快门已经 1/60 仍糊：查对焦、被摄体运动、防抖、反光板震动。"""
    if not _age_ok(age, MIN_BLUR):
        return None
    t = text or ""
    if "糊" not in t:
        return None
    if not any(k in t for k in ("1/60", "提到", "照做", "按你说")):
        return None
    return "快门 1/60 还糊，先查对焦：是不是跑焦、对到背景；再查被摄体有没有动、防抖关没关、反光板/快门震动。"


def constraint_check(text, age=None):
    """ISO100 + 夜里/一盏灯 + 手持：直接判拍不了。"""
    if not _age_ok(age, MIN_CONSTRAINT):
        return None
    t = text or ""
    if not re.search(r"(?:ISO|iso|Iso|感光度)\s*[:：]?\s*100(?![0-9])", t):
        return None
    if not any(k in t for k in ("夜里", "晚上", "一盏灯", "台灯")):
        return None
    if "手持" not in t:
        return None
    if "虚化" in t or "背景" in t:
        return None
    return "拍不了。ISO 100 在这种光下手持，快门会低到端不住；上三脚架、用闪光灯，或换 400 以上的胶卷。"


def bokeh_feedback(text, age=None):
    """已经开大光圈仍不虚：查焦距、距离、背景。"""
    if not _age_ok(age, MIN_BOKEH_FEEDBACK):
        return None
    t = text or ""
    if "虚" not in t and "清楚" not in t:
        return None
    if re.search(r"(还是|仍|依旧)[^。；，]{0,6}(清楚|实|分明)", t) or "不够虚" in t:
        pass
    elif re.search(r"f/2(?:\.0)?(?![.\d])", t) and ("还是" in t or "也" in t):
        pass
    else:
        return None
    return "光圈开大还是不够虚，查三件事：焦距是不是太短、人离背景是不是太近、背景本身是不是太亮太乱；换长焦、让人往远处站。"


def exposure_feedback(text, age=None):
    """已经上三脚架仍暗：查测光、曝光补偿、镜头盖。"""
    if not _age_ok(age, MIN_CONSTRAINT):
        return None
    t = text or ""
    if "三脚架" not in t or not any(k in t for k in ("还是暗", "仍暗", "不够亮")):
        return None
    return "曝光三角已经没得加了：上三脚架还暗，先查测光是不是点了亮部、曝光补偿是不是负的、镜头盖或滤镜有没有挡；再查现场灯是不是真的照到了。"


def develop_feedback(text, age=None):
    """已经缩短显影时间仍偏厚：查药液浓度、曝光、试条。"""
    if not _age_ok(age, MIN_DEVELOP_FEEDBACK):
        return None
    t = text or ""
    if not any(k in t for k in ("缩短", "减半", "减少时间")):
        return None
    if not any(k in t for k in ("还是偏厚", "仍厚", "还是厚", "偏厚")):
        return None
    return "时间缩短还偏厚，查三件事：药液浓度是不是配高了、胶片曝光是不是过度、试条是不是按标准冲的；先冲一条试条再定。"
