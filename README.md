# memory_engine — 类人心智记忆引擎

一个以认知神经科学文献为纲实现的记忆/心智引擎：让一个虚构人物在模拟的二十年生活里
积累情景记忆、语义知识、程序技能与情绪经验，并以"像不像一个真实活过二十年的人"
为标准做访谈式验收。**研究项目，不宣称达到人类水平**；所有"验收"指自建测试与访谈。

方法文档见仓库外（HUMAN_LIKE_MIND_METHOD.md，56 篇文献精读），代码实现与文献条目
一一对应：`audit_research_map.py` 做符号级核查，`audit_fitting*.py` 诚实量化"题库拟合"占比。

## 模块

| 文件 | 职责 |
|---|---|
| `human_memory.py` | 情景记忆核心：SS/RS 双强度（Bjork）、变率编码、多痕迹、再巩固窗口、四指标（availability/accessible/latent/fidelity 各自独立）、退役、两阶段睡眠回放（含变换性重组） |
| `semantic_graph.py` | 语义事实（provenance/双时间线/冲突解决）、条件规则、联想图、反思蒸馏 |
| `procedural_memory.py` | 程序记忆：编译自动化、生疏 rust、savings、自动化↔迁移范围权衡 |
| `affect.py` | PAD 三维 core affect，tonic 衰减，mood-congruent 检索偏置 |
| `affective_mind.py` | 全局工作空间（GNW）、元认知（FOK/TIP/校准/meta-d'）、情绪建构（Barrett）、调节五族、反刍检测 |
| `insight_engine.py` | 灵光：僵局→约束松弛→高温远程联想→ICL 众数→双独立路径→独立慢校验（Aha ≠ 正确） |
| `self_engine.py` | 统一门面：teach/recall/rehearse、关系四账本（Amodio）、Conway 身份层、工作空间/元认知装配 |
| `brain.py` | 对话认知循环：固定优先级竞争管道（确认→实践推算→规则→语义→回忆→gist→弃答），装备袋约束延续 |
| `practice_engine.py` | 领域实践推算（摄影）：曝光/暗房/虚化等 8 个纯函数，带习得年龄门 |
| `wen_say.py` / `chat_voice.py` / `chat_realizer.py` | 语言实现层：按语料句式框架生成口语化回答；无私有语料时自动退回模板 |
| `text_norm.py` | 表层归一：通用词级词典 + 显式标注的题库改写层（可关闭以测量拟合度） |
| `persistence.py` | 原子写：临时文件 + `os.replace` + `fsync`，覆盖前保留 `.bak` |

## 运行测试

```bash
python test_mind.py          # 认知循环分层：规则/推算/回忆/知识/未知/确认/上下文
python test_phenomena.py     # 行为验收：§5.6 典型记忆现象、§5.7 双强度动力学、§7.3 反刍、§8 灵光
python test_round7.py        # 关系/身份/程序/装配
python selftest.py regress.py test_fixes.py   # 回归
```

十套共 **99/99 通过**（2026-11-22）。

## 私有语料说明

`wen_say` 的句式框架由作者本人的真实聊天语料挖出（`chat_voice.json`、`feel_frames.json`，
含原句证据）——**这两份语料属于私人数据，不在本仓库中**。没有语料时引擎自动退回
内置模板，全部测试仍然通过。若要从你自己的语料生成，参照 `build_voice.py` 的
统计方法（句式骨架 + 支撑计数 + 槽位），替换 `ex` 原句字段即可。

## 诚实边界

- 模板/规则的表层措辞带有题库拟合成分（`audit_fitting.py` 分"内容骨架/兜底骨架"两类量化）。
- 语言真实感依赖语料质量；机制的"像人"与语言的"像人"是两件事，测试只覆盖前者。
- `test_phenomena.py` 是行为验收：给输入条件、断言应涌现的现象，不做"教一条再考一条"的同义反复。
