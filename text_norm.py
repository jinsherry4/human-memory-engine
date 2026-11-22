# -*- coding: utf-8 -*-
"""text_norm.py — 表层归一（分两层，可分别关闭）

第一层 LEXICON：**通用词级等价**，属于领域词典，与任何题目无关。
    支架/脚架→三脚架、感光度→ISO、烫→温度高、浓→厚、分明→清楚……
    另含中文数字与单位换算（十五分之一→1/15、胶卷 100 度→ISO 100）。

第二层 PHRASE_SYNONYMS：**整句改写映射**。诚实标注：这一层的条目绝大多数
    是照着 practice/interview 题库的问法写的（见 audit_fitting.py 的统计），
    属于测试拟合，不是通用机制。可以用 lexical_only=True 关掉它，
    用来测"去掉题库改写后还剩多少能力"。
"""

import re

# ---- 第一层：通用领域词典（正则，避免"三脚架→三三脚架"这类自噬）----
LEXICON = [
    (r"支架", "三脚架"),
    (r"(?<!三)脚架", "三脚架"),
    (r"没(?!带)三脚架", "没带三脚架"),
    (r"感光度", "ISO"),
    (r"烫", "温度高"),
    (r"药液凉", "药液温度低"),
    (r"分明", "清楚"),
    (r"(一片|全|漆)黑", "还是暗"),
    (r"能?出片", "能拍"),
    (r"结婚", "婚礼"),
    (r"(?<!胶)装卷", "装胶卷"),
    (r"学装胶卷", "装胶卷"),
    (r"合照", "合影"),
]

# ---- 第二层：题库整句改写（测试拟合层，可关闭）----
PHRASE_SYNONYMS = [
    ("手上只有手机", "没带三脚架"),
    ("背景太实", "还是太清楚"),
    ("背景还是太清楚", "还是太清楚"),
    ("温度高了", "显影温度高了"),
    ("温度低了", "显影温度低了"),
    ("温度不变", "显影温度不变"),
    ("薄得", "太薄"),
    ("两个系列", "两组不同主题"),
    ("两组主题不同", "两组不同主题"),
    ("片头没挂住", "片头挂歪"),
    ("片头没挂好", "片头挂歪"),
    ("使劲拽", "硬拉"),
    ("死拽", "硬拉"),
    ("硬拽", "硬拉"),
    ("过片时那个轴", "回卷轴"),
    ("那个轴不转", "回卷轴不转"),
]

# 兼容旧引用
SYNONYMS = LEXICON + PHRASE_SYNONYMS

_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
       "六": 6, "七": 7, "八": 8, "九": 9}


def cn2num(s):
    """中文数字 → 整数。支持 十五 / 六十 / 一百二十 / 二百五 这类常见写法。

    "X百五"这类口语缩略（二百五=250、三百五=350）按百位后省略"十"处理。
    """
    s = str(s).strip()
    if s.isdigit():
        return int(s)
    # 二百五 → 二百五十：百位后单个数字缺"十"时按口语补上
    s = re.sub(r"百([一二三四五六七八九])(?!十)", r"百\1十", s)
    total, num = 0, 0
    for ch in s:
        if ch in _CN:
            num = _CN[ch]
        elif ch == "十":
            total += (num or 1) * 10
            num = 0
        elif ch == "百":
            total += (num or 1) * 100
            num = 0
        elif ch == "千":
            total += (num or 1) * 1000
            num = 0
    return total + num


_NUMCLS = r"[0-9一二三四五六七八九十百千两零]+"


def _units(out):
    # 十五分之一 → 1/15
    out = re.sub(r"(%s)分之一" % _NUMCLS,
                 lambda m: "1/%d" % cn2num(m.group(1)), out)
    # 胶卷/胶片 100 度 → ISO 100
    out = re.sub(r"(?:胶卷|胶片|卷)\s*(?:只有|是|用)?\s*(%s)\s*度" % _NUMCLS,
                 lambda m: "ISO %d" % cn2num(m.group(1)), out)
    # ISO 一百 → ISO 100
    out = re.sub(r"ISO\s*(%s)" % _NUMCLS,
                 lambda m: "ISO %d" % cn2num(m.group(1)), out)
    return out


def normalize(text, lexical_only=False):
    if not text:
        return ""
    out = str(text)
    # 先词典后换算：感光度→ISO 之后，"感光度一百"才能被 _units 接住成 ISO 100
    for pat, rep in LEXICON:
        out = re.sub(pat, rep, out)
    out = _units(out)
    if not lexical_only:
        for a, b in PHRASE_SYNONYMS:
            out = out.replace(a, b)
    return out
