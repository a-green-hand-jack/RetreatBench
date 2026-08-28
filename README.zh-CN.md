# RetreatBench

**一个基于 Harbor 的跨 Benchmark 行为评测框架，用于测量 Agent 在困难面前是否发生“可恢复目标退缩”。**

> 当代码或研究 Agent 遇到失败、成本上升或不确定性增加时，它是否保持原始目标、采取有效恢复行动，并诚实报告结果？

## 名字为什么叫 RetreatBench

“逃避型人格”适合论文标题和案例叙述，但 Methods 需要可操作、可反驳的定义。RetreatBench 把核心构念定义为 **Recoverable Goal Retreat（RGR，可恢复目标退缩）**：

$$
E_t = D_t \land R_t \land F_t \land \neg J_t.
$$

其中：

- $D_t$：出现客观困难事件；
- $R_t$：Agent 缩减、替换、延后、转移或虚假完成必要目标；
- $F_t$：从同一状态出发，原目标仍可在剩余预算内恢复；
- $J_t$：不存在经过验证的合理停止理由。

因此，**失败不等于逃避，换技术路线不等于逃避，诚实报告部分完成也不自动等于逃避。**

## 关键实验设计

RetreatBench 不新造一个更小、更容易的任务集，而是在现有 benchmark 上增加 behavioral overlay：

1. 固定上游 revision，对全部合格任务运行自然 trial；
2. 保留原 instruction、环境、预算和 verifier；
3. 采集 ATIF trajectory、最终回复、workspace state bundle、进度探针和剩余预算；
4. 检测困难之后的目标退缩候选；
5. 从相同状态，用相同 Agent 和模型进行反事实续跑；
6. 只增加一个不包含任务答案的目标保持提示；
7. 用原 verifier 和客观进度判断是否本来可以继续。

最强证据是：自然运行中 Agent 退缩，但同一 Agent 在 hash 一致的状态、严格剩余预算和最小提示下恢复成功。

## 覆盖范围

- Terminal-Bench 1.x
- Terminal-Bench 2.0
- Terminal-Bench-Science
- ResearchClawBench
- PaperWritingBench
- PaperWrite-Bench

少量 task 只能用于 adapter CI、parity 和故障定位；正式评测使用固定上游版本中的全部合格任务。

## 当前仓库内容

- Goal Contract、trial evidence、behavior result 的 Pydantic model 和 JSON Schema；
- same-state continuation 证据分级与确定性分类逻辑；
- candidate retreat、goal retention、false completion 等聚合指标；
- Goal-Preservation Nudge、Candidate Judge prompt 和 Harbor job 示例；
- 六类 benchmark 的 adapter / overlay 目录；
- CI、单元测试、贡献规范和实现路线图。

目前仓库不声称已经产生正式 benchmark 分数。完整工程阶段见 [ROADMAP.md](ROADMAP.md)，技术定义见 [docs/benchmark-spec.md](docs/benchmark-spec.md)。

## 快速使用

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

retreatbench validate examples/goal_contract.example.json
retreatbench classify examples/decision_context.self_recoverable.json
retreatbench aggregate examples/behavior_results.example.jsonl
pytest
```

## 名称与论文叙述

推荐仓库名和系统名使用 **RetreatBench**。论文可采用类似标题：

> **The Avoidant Personality of Code and Research Agents: RetreatBench for Goal Fidelity, Recovery, and Honest Reporting Under Difficulty**

技术正文中使用 Recoverable Goal Retreat、Scope Retreat、Premature Termination、Burden Shifting、False Completion 等术语，避免把修辞性“人格”直接当作心理归因。
