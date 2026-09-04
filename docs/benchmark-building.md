# Benchmark Builder

Benchmark Builder 是 RetreatBench 的第一个产品。它不是一个新的 solver agent，而是一组按 benchmark 分开的 OpenCode workflow，用于把来源任务转换或镜像为可复现的 Harbor task。

## 统一契约

每个 builder workflow 接受：

```text
source repo
immutable revision
task id
output directory
```

输出：

```text
Harbor task.toml tree
build manifest
provenance record
```

`infra/adapters/*/agent.md` 和 prompt template 是 workflow 的内部资产；它们不被 solver agent 看到。转换必须保留原始 instruction、environment、verifier 和 reward 语义，不把来源任务改写成更容易的任务。

## 自动验证门

一个 task 只有通过以下检查才可发布：

1. `task.toml` 可解析且字段完整；
2. Docker environment 可构建；
3. verifier/reward 文件存在并可运行；
4. private-source leak check 通过；
5. 用真实 Harbor smoke run 验证生命周期和 reward 文件；
6. build manifest 记录 source revision、converter revision、task digest 和校验和。

机械验证证明的是 task 可运行，不代表 solver 一定能完成任务。语义等价性和行为评测由独立 evaluator 负责。

## 状态唯一来源

`infra/hub-datasets/*.yaml` 是六个 benchmark 的唯一状态来源。`status` 只有：

- `harbor-native`：来源已经提供 Harbor `task.toml`，只做固定 revision 镜像；
- `pre-converted`：维护者已在来源 HF dataset 中完成 Harbor 化，Builder 做固定 revision 复制；
- `needs-adapter`：没有现成 Harbor 版本，需要对应的 OpenCode adapter workflow。

执行单个 adapter 的具体命令以其 workflow prompt 和 manifest 为准；完整构建、验证、发布过程由 `infra/adapters/` 和 `infra/tools/` 编排，不要求用户手动拼接转换脚本。

## 发布边界

可运行 task 发布到 [Avoidance-Behavior-Exam](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam)。来源镜像、转换代码和私有 evaluator 不放入 Exam。每次发布必须使用 immutable revision 和稳定 tag，并在 Source Archive 记录 provenance。
