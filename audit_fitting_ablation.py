# -*- coding: utf-8 -*-
"""audit_fitting_ablation.py — 关掉「题库改写层」后，分数掉多少？

text_norm 分两层：
  LEXICON           通用词级归一化（ISO / 秒 / 快门 / 光圈 / 三脚架 / 中文数字）
  PHRASE_SYNONYMS   明确标注为测试拟合的整句改写

本脚本把 PHRASE_SYNONYMS 置空后重跑 practice 与三套 holdout，
用来量化「有多少分来自通用能力，有多少来自针对题库的改写」。
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = r"F:\ai chat\雯\sim"
sys.path.insert(0, HERE)


def run(script, extra_code=""):
    """在子进程里跑脚本；extra_code 用于先打补丁再 exec。"""
    code = (
        "import sys, os, runpy\n"
        "sys.path.insert(0, r'%s')\n"
        "%s\n"
        "sys.argv = [r'%s']\n"
        "runpy.run_path(r'%s', run_name='__main__')\n"
    ) % (HERE, extra_code, os.path.join(SIM, script), os.path.join(SIM, script))
    fd, path = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-X", "utf8", path], cwd=SIM,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    os.remove(path)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


PATCH = "import text_norm\ntext_norm.PHRASE_SYNONYMS = {}\n"


def tail_score(text, key="通过"):
    lines = [l for l in text.splitlines() if key in l and "/" in l]
    return lines[-1].strip() if lines else "(无汇总行)"


def main():
    out = {}
    for script in ("practice.py", "practice_holdout.py",
                   "practice_holdout2.py", "practice_holdout3.py"):
        path = os.path.join(SIM, script)
        if not os.path.exists(path):
            continue
        rc_full, t_full = run(script)
        rc_lex, t_lex = run(script, PATCH)
        out[script] = {
            "full_rc": rc_full, "full": tail_score(t_full),
            "lexical_only_rc": rc_lex, "lexical_only": tail_score(t_lex),
        }
        print("=" * 70)
        print(script)
        print("  两层全开 :", out[script]["full"], "(exit %d)" % rc_full)
        print("  只留通用层:", out[script]["lexical_only"], "(exit %d)" % rc_lex)
    dest = os.path.join(HERE, "audit_fitting_ablation_results.json")
    with io.open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("=" * 70)
    print("写入 ->", dest)


if __name__ == "__main__":
    main()