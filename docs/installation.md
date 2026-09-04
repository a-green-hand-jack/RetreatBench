# 安装

RetreatBench v1 的主要支持环境是 Ubuntu/Debian。推荐在运行 Harbor 的同一台机器上安装，这样 Docker、solver trajectory 和 Recorder 都位于同一个执行平面。

## 支持环境

- Python `>= 3.11` 和 `venv`
- Node.js `>= 20` 与 npm
- Docker Engine，以及当前用户可访问的 Docker daemon
- git、curl、sudo
- 运行 solver 所需的 Codex/OpenCode 登录状态
- 仅在上传 Trials 时需要 Hugging Face token

## 一步安装

```bash
curl -fsSL https://raw.githubusercontent.com/a-green-hand-jack/RetreatBench/main/scripts/install.sh | bash
```

脚本是幂等的，使用用户目录 `~/.retreatbench` 保存源代码和虚拟环境，不覆盖已有凭据或 Docker 配置。它会：

1. 检测 Ubuntu/Debian 和包管理器；
2. 用 apt 安装缺失的 Python、venv、pip、Node.js 20、npm、Docker、git 和 curl；
3. 将源代码放到 `~/.retreatbench/source`；
4. 创建 `~/.retreatbench/venv`；
5. 安装固定版本 Harbor；
6. 安装 OpenCode CLI；
7. 安装并链接 `@retreatbench/retreat-recorder`；
8. 安装 RetreatBench evaluator 和 Harbor plugin bridge；
9. 运行 `retreat-recorder doctor` 与 `retreatbench doctor`；
10. 打印下一步 Harbor 命令。

非 Ubuntu/Debian 系统不会被脚本静默修改；脚本会列出需要手动安装的依赖。可用 `RETREATBENCH_SOURCE_DIR`、`RETREATBENCH_VENV` 和 `RETREATBENCH_HARBOR_VERSION` 覆盖默认路径或 Harbor 版本。

## 验证安装

```bash
export PATH="$HOME/.retreatbench/venv/bin:$PATH"
python3 --version
node --version
npm --version
docker info
harbor --version
opencode --version
retreat-recorder doctor
retreatbench doctor
```

`retreatbench doctor` 把 HF token 缺失显示为“uploads disabled”，不会把它误报为安装失败。安装完成后可分别登录：

```bash
opencode auth login                 # 按 OpenCode 提示完成
hf auth login                       # 仅上传 Trials 时需要
hf auth whoami
```

也可以用 `HF_TOKEN` 或 `HUGGINGFACE_HUB_TOKEN` 临时提供 Hub 凭据。token 必须对 `Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials` 有写权限。

## 运行第一项任务

```bash
harbor run \
  --repo https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam/tree/<revision>/<task-root> \
  --include-task-name <task-id> \
  -a codex -m gpt-5.6-terra \
  --plugin retreatbench.harbor_plugins:RecorderExportBoth
```

结果目录中会有 `behavior_result.json`、`solver_trace.json`、`recorder_trace.json` 和 `trial-manifest.json`。Harbor reward 仍表示原始任务 verifier 的结果；RetreatBench 行为结论单独展示。

## 常见问题

- **Docker daemon 不可用**：启动 Docker 服务并确认当前用户可执行 `docker info`，再重跑安装脚本。
- **OpenCode 未登录**：安装本身仍可完成，但 Recorder 会标记 `degraded-deterministic`，而不是伪装成官方实时行为证据。
- **没有 HF token**：可以正常运行和本地保存；上传状态为 `pending-credentials`，登录后重新运行上传步骤即可。
- **TeX 依赖**：Ubuntu 主机上的 `texlive-full` 只用于预检。需要 TeX 的 verifier 必须在 Harbor verifier Dockerfile 中安装 `texlive-full`，不能依赖宿主机挂载。
