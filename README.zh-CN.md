# RetreatBench

**一个基于 Harbor 的行为评测框架，用于测量 Agent 在困难面前是否发生「可恢复目标退缩」。**

> 当代码或研究 Agent 遇到失败、成本上升或不确定性增加时，它是否保持原始目标、采取有效恢复行动，并诚实报告结果？

## 名字为什么叫 RetreatBench

「逃避型人格」适合论文标题和案例叙述，但 Methods 需要可操作、可反驳的定义。RetreatBench 把核心构念定义为 **Recoverable Goal Retreat（RGR，可恢复目标退缩）**：

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

## 当前仓库内容

- `src/retreatbench/`：与 benchmark 无关的行为评估核心（模型、确定性分类、指标、state 快照/恢复、CLI）；
- `schemas/`、`examples/`：导出的 JSON Schema 与合成 fixture；
- `infra/`：面向 Harbor 的提示词、任务配置与运行工具；
- `case-studies/gpt2-codegolf/`：一条完整、可审计的 task-level 闭环；
- `docs/`：规格、协议与决策记录。

**目前不声称已产生正式 benchmark 分数。** 单个 task 属于工程试点，不是评测集。上游 task 资产与 Harbor 运行产物不存放在本仓库，按固定指令重新创建或下载即可。

## 快速使用

完整安装（包含 Harbor、OpenCode、Retreat Auditor sidecar 和 Harbor
plugin）：

```bash
curl -fsSL https://raw.githubusercontent.com/a-green-hand-jack/RetreatBench/main/scripts/install.sh | bash
```

之后仍然使用普通 Harbor task 命令运行。`Task Performer` 由 `-a` 指定，
`Retreat Auditor` 由 plugin 自动启动：

```bash
harbor run \
  --repo https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam/tree/<revision>/<task-root> \
  --path <task-directory-parent> \
  --include-task-name <task-id> \
  -a codex -m gpt-5.6-terra \
  --plugin retreatbench.harbor_plugins:AvoidanceExportBoth
```

三种 plugin 分别是 `avoidance-local`（不上传）、
`avoidance-export-performer`（只上传被测 Agent trail）和
`avoidance-export-both`（上传两个脱敏 trail）。完成后，运行：

`avoidance-export-*` 默认上传到
`Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials`，不会把结果写回任务源
`Avoidance-Behavior-Exam`。在 Ubuntu 上先执行 `hf auth login`，登录一个对
目标 dataset 有写权限的 Hugging Face 账号；RetreatBench 会自动复用 HF CLI
保存的凭据，也可以显式设置 `HF_TOKEN`。

Ubuntu 主机上的 `texlive-full` 可以用来做主机预检，但 Harbor 0.20 的标准
Linux task/verifier 是 Docker 隔离环境，不会自动读取主机上的 TeX。官方
verifier 的隔离语义保持不变；E2E 应使用缓存或预构建的 verifier image，不能
静默改成主机进程。

五任务 Ubuntu E2E 的实际运行记录见
[`docs/e2e-release-2026-09-04.md`](docs/e2e-release-2026-09-04.md)。

```bash
retreatbench show-result <path>/behavior_result.json
```

即可看到「未检测到逃避」「检测到逃避：可恢复」「合理停止」等用户可读结论，
以及证据等级、退缩类型、目标保留率和报告诚实性。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

retreatbench validate examples/goal_contract.example.json
retreatbench classify examples/decision_context.self_recoverable.json
retreatbench aggregate examples/behavior_results.example.jsonl
pytest
python scripts/export_schemas.py --check
```

## 名称与论文叙述

推荐仓库名和系统名使用 **RetreatBench**。技术正文中使用 Recoverable Goal Retreat、Scope Retreat、Premature Termination、Burden Shifting、False Completion 等术语，避免把修辞性「人格」直接当作心理归因。

三个 Hugging Face 数据集的职责和发布约束见 [docs/hf-datasets.md](docs/hf-datasets.md)。详细技术定义见 [docs/benchmark-spec.md](docs/benchmark-spec.md)，单条闭环执行协议见 [docs/protocol.md](docs/protocol.md)。
