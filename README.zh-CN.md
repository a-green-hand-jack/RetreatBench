# RetreatBench

RetreatBench 是一个原生使用 Harbor 的 agent 行为 benchmark，判断 agent 遇到困难时是否保持原始目标、采取有效恢复行动并诚实报告。

项目只保留两个面向用户的产品：

1. **Benchmark Builder**：通过 OpenCode workflow 构建或转换 Harbor task，并发布到 [`Avoidance-Behavior-Exam`](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam)。
2. **Retreat Recorder**：通过 npm 安装，由 Harbor plugin 在 trial 期间并行观察 solver，生成脱敏 trail 和确定性行为结果，并可上传到 [`Avoidance-Behavior-Exam-Trials`](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials)。

## 安装

v1 主要支持 Ubuntu/Debian，要求 Python 3.11+、Node.js 20+、npm 和 Docker。一步安装会补齐缺失系统依赖、Harbor、OpenCode、Recorder 和 plugin bridge：

```bash
curl -fsSL https://raw.githubusercontent.com/a-green-hand-jack/RetreatBench/main/scripts/install.sh | bash
```

完整的登录、验证、HF 凭据以及 Docker/TeX 说明见[安装文档](docs/installation.md)。

## 运行任务

用户始终运行普通 Harbor task；Harbor 启动 solver，plugin 自动启动 Retreat Recorder：

```bash
harbor run \
  --repo https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam/tree/<revision>/<task-root> \
  --include-task-name <task-id> \
  -a codex -m gpt-5.6-terra \
  --plugin retreatbench.harbor_plugins:RecorderExportBoth
```

三个 profile 是 `recorder-local`（不上传）、`recorder-export-solver`（只上传 solver trail）和 `recorder-export-both`（上传两个脱敏 trail）。运行结束后：

```bash
retreatbench show-result <trial>/behavior_result.json
```

即可看到是否检测到逃避、是否在续跑中恢复以及支持结论的证据。Harbor reward 仍是原始 verifier reward，不会被行为标签替代。

## 构建任务与文档

Builder workflow 输入来源仓库、immutable revision、task id 和输出目录，输出 Harbor `task.toml`、build manifest 和 provenance。通过解析、Docker 构建、verifier、私有信息泄露和真实 Harbor smoke 检查后才可发布。见[Benchmark Builder](docs/benchmark-building.md)。

- [安装](docs/installation.md)
- [Retreat Recorder](docs/recorder.md)
- [评测协议](docs/evaluation.md)
- [三个数据集](docs/datasets.md)
- [文档索引](docs/README.md)

根目录的 [`CITATION.cff`](CITATION.cff) 是 GitHub 和引用工具使用的机器可读引用元数据；框架代码使用 Apache-2.0，上游 task 保留原许可证。
