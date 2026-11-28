# -*- coding: utf-8 -*-
"""量化：现行 feel 框架选择 vs 按语料众数选择的偏差有多大。"""
import json, os, sys
sys.path.insert(0, r"F:\ai chat\memory_engine")
import wen_say as W

d = json.load(open(r"F:\ai chat\memory_engine\feel_frames.json", encoding="utf-8"))["words"]

rows = []
for w, v in d.items():
    total = int(v.get("总次数") or 0)
    if total <= 0:
        continue
    frames = v.get("框架") or {}
    if not frames:
        continue
    # 语料真众数
    truth = max(frames.items(), key=lambda kv: kv[1])
    cur = W.FEEL_FRAMES.get(w)
    rows.append((w, total, truth[0], truth[1], cur, frames.get("裸用", 0)))

same = sum(1 for r in rows if r[4] == (r[0] if r[2] == "裸用" else r[2]))
print("有框架的词 %d 个；现行选择与语料众数一致 %d 个（%.0f%%）"
      % (len(rows), same, 100.0 * same / max(1, len(rows))))
print()
print("%-10s %-6s %-10s %-6s %-10s %-6s %s"
      % ("词", "总次数", "语料众数", "次数", "引擎现用", "裸用", "偏差"))
n_bad = 0
for w, total, tw, tn, cur, bare in sorted(rows, key=lambda r: -r[1]):
    bad = (cur != (w if tw == "裸用" else tw))
    if bad:
        n_bad += 1
    if bad and total >= 30:
        print("%-10s %-6d %-10s %-6d %-10s %-6d %s"
              % (w, total, tw, tn, str(cur), bare, "← 偏"))
print()
print("总计偏差 %d 个词（其中总次数>=30 的重点词见上）" % n_bad)
