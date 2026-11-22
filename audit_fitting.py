# -*- coding: utf-8 -*-
"""audit_fitting.py — 量化"词表是不是照着题库写的"

只做统计，不改任何引擎文件。输出：
  1. text_norm.SYNONYMS 有多少条右值直接出现在 practice/interview 题库里
  2. brain 的 SPECIFIC / _is_uncertain_claim / _merge_context 词表同上
  3. 哪些 sim 脚本用 remember_turn=True（会把问句写成她自己的经历）
"""
import glob
import inspect
import json
import os
import re
import sys

sys.path.insert(0, r"F:\ai chat\memory_engine")
import brain as B
from text_norm import SYNONYMS

files = sorted(glob.glob(r"F:\ai chat\雯\sim\practice*.py")
               + glob.glob(r"F:\ai chat\雯\sim\interview*.py"))
C = "\n".join(open(p, encoding="utf-8").read() for p in files)

out = {}
out["题库文件数"] = len(files)
out["SYNONYMS 总数"] = len(SYNONYMS)
syn_hit = [(a, b) for a, b in SYNONYMS if b in C]
out["SYNONYMS 右值命中题库"] = len(syn_hit)
out["SYNONYMS 恒等映射"] = [(a, b) for a, b in SYNONYMS if a == b]
out["SYNONYMS 命中样例"] = syn_hit[:12]

spec = list(B.SPECIFIC)
out["SPECIFIC 总数"] = len(spec)
out["SPECIFIC 命中题库"] = [k for k in spec if k in C]


def kws(fn):
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) >= 2:
                out.append(node.value)
    return out


u = kws(B.Brain._is_uncertain_claim)
m = kws(B.Brain._merge_context)
out["_is_uncertain_claim 词数"] = len(u)
out["_is_uncertain_claim 命中题库"] = [k for k in u if k in C]
out["_merge_context 词数"] = len(m)
out["_merge_context 命中题库"] = [k for k in m if k in C]

turn_on = []
for p in sorted(glob.glob(r"F:\ai chat\雯\sim\*.py")):
    txt = open(p, encoding="utf-8").read()
    if "remember_turn=True" in txt:
        turn_on.append(os.path.basename(p))
out["remember_turn=True 的脚本"] = turn_on

print(json.dumps(out, ensure_ascii=False, indent=2))
with open(r"F:\ai chat\memory_engine\audit_fitting_results.json", "w",
          encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
