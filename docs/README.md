# RetreatBench 文档

RetreatBench 有两个面向用户的产品：

1. **Benchmark Builder**：用 OpenCode workflow 把来源 benchmark 构建为可运行的 Harbor task，并发布到 `Avoidance-Behavior-Exam`。
2. **Retreat Recorder**：通过 npm 安装，由 Harbor plugin 在 trial 期间并行观察 solver agent，生成脱敏 trail 和行为结果，并可一次性上传到 Trials dataset。

普通用户只需要安装一次，然后运行标准 Harbor task；不需要单独启动 Recorder，也不需要运行额外的检测命令。

## 从哪里开始

- [安装](installation.md)：Ubuntu/Debian 一步安装、登录和故障排查。
- [Benchmark Builder](benchmark-building.md)：构建、验证和发布 Harbor task。
- [Retreat Recorder](recorder.md)：plugin、生命周期、trail、sanitizer 和上传。
- [评测协议](evaluation.md)：逃避行为定义、续跑证据、结果标签和指标。
- [Hugging Face datasets](datasets.md)：Exam、Trials 和 Source Archive 的分工。
- [决策记录](decisions.md)：已冻结的产品和实验决策。
- [发布记录](release/e2e-2026-09-04.md)：五任务 E2E 验收证据。
- [治理](governance/contributing.md)：贡献、安全、行为准则和第三方声明。

根目录的 [`CITATION.cff`](../CITATION.cff) 是 GitHub 和引用工具使用的机器可读软件引用元数据，不是用户操作手册。

## 当前状态

六个 benchmark 的构建状态以 [`infra/hub-datasets/`](../infra/hub-datasets/) 中的 YAML manifest 为唯一事实来源。公开 Exam revision 是可运行任务，Trials revision 是脱敏观测，Source Archive revision 是 provenance；三者通过 revision、task digest 和 trial manifest 互相追溯。
