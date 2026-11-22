"""regress.py — 代码复查后的回归测试

覆盖 selftest 没测到的三处：
  1. accesses 截断：反复检索后访问轨迹有界（≤16 条），不会无限膨胀
  2. 退役判定：纯激活阈值驱动，长期不用的记忆会被标记，新记忆不被误伤
  3. 退役隔离：退役记忆不参与 CA3 召回，也不出现在召回结果里

用法：python regress.py
"""

import time

from engine import MemoryEngine

EP = {"who": "林晚", "where": "顶层公寓", "when": "深夜", "what": "改合同", "feel": "疲惫"}


def test_access_trace_bounded():
    eng = MemoryEngine()
    mid = eng.remember(EP, arousal=0.5)
    for _ in range(20):
        eng.recall({"who": "林晚", "where": "顶层公寓"})
    n = len(eng.memories[mid]["accesses"])
    ok = n <= 16
    print("[1] 访问轨迹有界")
    print("    检索 20 次后 accesses 长度 : %d（上限 16）" % n)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_retire_by_activation_only():
    eng = MemoryEngine()
    fresh = eng.remember(EP, arousal=0.0)   # 唤醒最低的新记忆
    old = eng.remember({"who": "路人", "where": "街角"}, arousal=0.5)

    # 刚创建时不允许被退役
    r0 = eng.consolidate()
    not_fresh = not eng.memories[fresh]["retired"]
    not_old = not eng.memories[old]["retired"]

    # 时间跳到三年后：长期不用的应被退役
    future = time.time() + 3 * 365 * 86400
    r1 = eng.consolidate(now=future)

    print("[2] 退役判定（纯激活阈值）")
    print("    刚创建后退役数 : %d（期望 0）" % r0["retired"])
    print("    三年后退役数   : %d（期望 2）" % r1["retired"])
    ok = r0["retired"] == 0 and not_fresh and not_old and r1["retired"] == 2
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_retired_excluded_from_recall():
    eng = MemoryEngine()
    mid = eng.remember(EP, arousal=0.5)
    future = time.time() + 3 * 365 * 86400
    eng.consolidate(now=future)          # 让它退役

    out = eng.recall({"who": "林晚", "where": "顶层公寓"})
    ids = [r["id"] for r in out["results"]]
    ok = mid not in ids and out["best"] is None
    print("[3] 退役隔离")
    print("    退役记忆 %s 是否出现在召回 : %s" % (mid, "是" if mid in ids else "否"))
    print("    best : %s" % out["best"])
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_legacy_store_compat():
    """缺 vec / pattern 的旧格式 store 应能恢复，而不是崩溃。"""
    import json
    import os

    import memory_api

    legacy = {
        "next_id": 1,
        "memories": [{
            "id": "m0",
            "episode": {"who": "林晚", "where": "顶层公寓"},
            "full_episode": {"who": "林晚", "where": "顶层公寓", "what": "改合同"},
            "created": time.time(),
        }],
    }
    old_store = memory_api.STORE
    tmp = os.path.join(os.path.dirname(old_store), "_legacy_test.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)
    memory_api.STORE = tmp
    try:
        eng = memory_api.load()
        m = eng.memories["m0"]
        ok = (
            "vec" in m and len(m["vec"]) == 1024
            and isinstance(m["pattern"], frozenset) and len(m["pattern"]) > 0
            and m["retired"] is False
        )
        info = "vec=%d pattern=%d retired=%s" % (
            len(m.get("vec", [])), len(m.get("pattern", [])), m.get("retired"))
    finally:
        memory_api.STORE = old_store
        if os.path.exists(tmp):
            os.remove(tmp)
    print("[4] 旧格式兼容")
    print("    恢复结果 : %s" % info)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def test_decay_timescale():
    """衰减尺度要符合遗忘曲线量级：1 小时后仍在，1 周后应退役。"""
    eng = MemoryEngine()
    mid = eng.remember(EP, arousal=0.5)
    t0 = eng.memories[mid]["created"]
    m = eng.memories[mid]

    act_1h = eng._activation(m, t0 + 3600)
    act_1d = eng._activation(m, t0 + 86400)
    act_1w = eng._activation(m, t0 + 7 * 86400)

    ok = act_1h > 0.15 and act_1w < 0.15
    print("[5] 衰减时间尺度")
    print("    1 小时激活 : %.3f" % act_1h)
    print("    1 天激活   : %.3f" % act_1d)
    print("    1 周激活   : %.3f（应低于退役阈值 0.15）" % act_1w)
    print("    判定：%s" % ("PASS" if ok else "FAIL"))
    return ok


def main():
    print("=" * 56)
    print("复查回归测试")
    print("=" * 56)
    results = [
        test_access_trace_bounded(),
        test_retire_by_activation_only(),
        test_retired_excluded_from_recall(),
        test_legacy_store_compat(),
        test_decay_timescale(),
    ]
    print("=" * 56)
    print("结果：%d / %d 项通过" % (sum(results), len(results)))
    print("=" * 56)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
