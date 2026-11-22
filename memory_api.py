"""memory_api.py — 记忆引擎的命令行接口 + 持久化

用法：
  python memory_api.py add --who 林晚 --where 顶层公寓 --what 改合同 --feel 疲惫 --arousal 0.5
  python memory_api.py recall --who 林晚 --where 顶层公寓
  python memory_api.py consolidate
  python memory_api.py stats
  python memory_api.py list

数据落在同目录 store.json，与日志文件互不干扰。
"""

import argparse
import json
import os
import time

from affect import Affect
from circuits import ROLES, encode
from engine import MemoryEngine
from perceive import appraise_text
from persistence import save_json

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store.json")
AFFECT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "affect.json")


def save(eng):
    """持久化。frozenset 转 list 才能进 JSON。"""
    payload = {
        "next_id": eng._next_id,
        "memories": [],
    }
    for m in eng.memories.values():
        item = dict(m)
        item["pattern"] = sorted(item["pattern"])
        payload["memories"].append(item)
    save_json(STORE, payload)
    eng.affect.save()


def load():
    """读取持久化数据。缺失字段按默认值补齐，兼容旧版本 store。"""
    eng = MemoryEngine(affect=Affect(AFFECT))
    if not os.path.exists(STORE):
        return eng
    with open(STORE, encoding="utf-8") as f:
        payload = json.load(f)
    eng._next_id = payload.get("next_id", 0)
    for item in payload.get("memories", []):
        # 旧版本可能缺 vec / pattern：从情景重新编码恢复，而不是直接报错
        if "vec" not in item:
            item["vec"] = encode(item.get("full_episode") or item.get("episode") or {})
        if "pattern" not in item:
            item["pattern"] = eng.dg.separate(item["vec"])
        else:
            item["pattern"] = frozenset(item["pattern"])
        item.setdefault("accesses", [item.get("created", time.time())])
        item.setdefault("arousal", 0.5)
        item.setdefault("relevance", 0.5)
        item.setdefault("valence", 0.0)
        item.setdefault("detail_kept", 1.0)
        item.setdefault("note", "")
        item.setdefault("retired", False)
        eng.memories[item["id"]] = item
        eng.ca3.store(item["pattern"], item["id"])
    return eng


def build_episode(args):
    ep = {}
    for role in ROLES:
        val = getattr(args, role, None)
        if val:
            ep[role] = val
    return ep


def main():
    ap = argparse.ArgumentParser(description="类海马体记忆引擎 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="存入一段经历")
    for role in ROLES:
        add.add_argument("--" + role, default=None, help="字段 %s" % role)
    add.add_argument("--arousal", type=float, default=None, help="唤醒度 0–1，省略则用当前情绪")

    rec = sub.add_parser("recall", help="用线索回忆")
    for role in ROLES:
        rec.add_argument("--" + role, default=None, help="线索字段 %s" % role)
    rec.add_argument("--top", type=int, default=3)

    sub.add_parser("mood", help="查看当前情绪与语气建议")
    sub.add_parser("consolidate", help="离线巩固")
    sub.add_parser("stats", help="统计")
    sub.add_parser("list", help="列出全部记忆")

    args = ap.parse_args()
    eng = load()

    if args.cmd == "add":
        ep = build_episode(args)
        if not ep:
            print("至少给一个字段。可选：" + ", ".join(ROLES))
            return 1
        # 先让这段话影响情绪，再记忆：情绪在编码前就位，符合真实发生顺序
        probe = " ".join(str(ep.get(k, "")) for k in ("what", "feel", "result"))
        v, a, d, w, tags = appraise_text(probe)
        if w > 0:
            eng.affect.appraise(v, a, d, w)
        mid = eng.remember(ep, arousal=args.arousal)
        save(eng)
        m = eng.memories[mid]
        print("已存储 %s  唤醒=%.2f  细节保留=%d%%  情绪=%s%s"
              % (mid, m["arousal"], m["detail_kept"] * 100, eng.affect.label(),
                 ("  [" + ",".join(tags) + "]") if tags else ""))
        return 0

    if args.cmd == "mood":
        t = eng.affect.tone()
        st = eng.affect.state
        print("当前情绪：%s" % t["mood"])
        print("  valence %.3f   arousal %.3f   dominance %.3f"
              % (st["valence"], st["arousal"], st["dominance"]))
        print("  语气：话量 %.2f · 句长 %s · 温度 %.2f · 笃定 %.2f · 主动性 %.2f"
              % (t["verbosity"], t["sentence_len"], t["warmth"],
                 t["assertiveness"], t["initiative"]))
        return 0

    if args.cmd == "recall":
        ep = build_episode(args)
        if not ep:
            print("至少给一个线索字段。可选：" + ", ".join(ROLES))
            return 1
        out = eng.recall(ep, top_k=args.top)
        save(eng)
        print("最佳匹配：%s  重叠=%.0f%%  置信=%.2f  新颖=%s"
              % (out["best"], out["overlap"] * 100, out["confidence"], out["novel"]))
        for r in out["results"]:
            print("  · %s  score=%.3f  sim=%.2f  细节=%d%%  %s"
                  % (r["id"], r["score"], r["similarity"],
                     r["detail_kept"] * 100,
                     json.dumps(r["episode"], ensure_ascii=False)))
        return 0

    if args.cmd == "consolidate":
        r = eng.consolidate()
        save(eng)
        print("巩固完成：退役 %d 条，活跃 %d 条" % (r["retired"], r["active"]))
        return 0

    if args.cmd == "stats":
        s = eng.stats()
        print("总记忆 %d · 活跃 %d · 平均细节保留 %.2f"
              % (s["total"], s["active"], s["avg_detail"]))
        return 0

    if args.cmd == "list":
        if not eng.memories:
            print("（空）")
            return 0
        for m in eng.memories.values():
            flag = "退役" if m["retired"] else "活跃"
            print("%s [%s] 唤醒=%.2f 细节=%d%% %s"
                  % (m["id"], flag, m["arousal"], m["detail_kept"] * 100,
                     json.dumps(m["full_episode"], ensure_ascii=False)))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
