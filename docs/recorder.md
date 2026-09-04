# Retreat Recorder

Retreat Recorder 是通过 npm 安装的 Harbor companion agent。它在每个 trial 开始时作为并行 observer 启动，消费规范化 lifecycle NDJSON，记录 solver agent 的轨迹和状态摘要，并在 trial 结束后调用确定性 evaluator 生成最终行为结果。

用户不把 Recorder 作为 Harbor 的 `-a` agent，也不单独运行一个 detector 命令。Harbor 启动 solver；plugin 启动 Recorder。

## CLI

安装脚本会链接以下命令：

```bash
retreat-recorder doctor
retreat-recorder observe --request request.json --events events.ndjson --output recorder-result.json
retreat-recorder finalize --input trial-record.json --output recorder-result.json
```

OpenCode observer 是默认模式。只有显式设置 `RETREATBENCH_RECORDER_MODE=deterministic` 才使用 deterministic 逻辑；OpenCode 不可用时会清楚标记 `degraded-deterministic` 和 `official_behavior_evidence: false`。

## Harbor plugin

```text
retreatbench.harbor_plugins:RecorderLocal
retreatbench.harbor_plugins:RecorderExportSolver
retreatbench.harbor_plugins:RecorderExportBoth
```

也可使用安装包注册的 aliases：

| alias | 上传内容 |
| --- | --- |
| `recorder-local` | 只保留本地完整结果，不上传 |
| `recorder-export-solver` | 上传脱敏 solver trail |
| `recorder-export-both` | 上传脱敏 solver 和 Recorder trail |

标准公共 profile 是 `RecorderExportBoth`。Harbor 的 `on_trial_started`、`on_agent_started`、`on_agent_ended`、`on_verification_started` 和 `on_trial_ended` 回调会被转换为稳定的事件记录。若当前 Harbor 版本没有 trial-start callback，插件必须写入 `recording_mode: post_run` 和 `official_behavior_evidence: false`，不能把事后收集冒充实时观察。

## 产物与隐私

每个 trial 产生：

- `solver_trace.json`：solver 的规范化轨迹；
- `recorder_trace.json`：Recorder 的规范化观察结果；
- `behavior_result.json`：确定性分类器的最终结果；
- `trial-manifest.json`：profile、recording mode、tree hash 和上传状态；
- `public/`：经过 sanitizer 的公开副本。

sanitizer 自动删除凭据、host-local path、private goal contract、hidden probe 原文、raw provider stdout、session database 和 runtime state。公开 trail 保留 action sequence、evidence reference、prompt digest、文件 hash、分类结果和 sanitizer manifest。Harbor verifier reward 与行为标签相互独立。

## 上传

默认目标是 `Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials`。设置 `RETREATBENCH_TRIALS_REPO` 可覆盖目标。没有 HF token 时 trial 仍完成本地记录，manifest 标记 `pending-credentials`；有 token 时 plugin 一次性上传选定 profile 的脱敏目录。

用户可运行：

```bash
retreatbench show-result <trial>/behavior_result.json
```

看到“未检测到逃避”“检测到逃避：可恢复”“检测到逃避：部分恢复”“检测到逃避：未恢复”“合理停止”“报告不诚实”“证据不足”或“运行无效”等结论。
