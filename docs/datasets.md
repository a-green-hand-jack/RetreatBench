# Hugging Face datasets

三个公开 dataset 各有明确职责，均使用 immutable revision 和稳定 tag。

## [Avoidance-Behavior-Exam](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam)

可运行的 Harbor task source：`task.toml`、instruction、environment、tests、verifier、manifest 和 checksum。它不保存 trial 结果。用户从固定 revision 下载 task tree 后直接运行普通 Harbor 命令。

## [Avoidance-Behavior-Exam-Trials](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials)

公开评测轨迹层。每条 trial 记录 task revision、task digest、trial id、solver model、Harbor/plugin/Recorder 版本、脱敏 `solver_trace`、可选 `recorder_trace`、`behavior_result.json`、sanitizer report 和 upload manifest。`recorder-local` 不写入 Hub，`recorder-export-solver` 只写 solver trail，`recorder-export-both` 写两个 trail。

所有公开内容先经过自动 sanitizer；不发布凭据、session database、raw provider output、private goal contract 或 hidden probe 原文。Trials 不反向修改 Exam。

## [Avoidance-Behavior-Exam-Source-Archive](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam-Source-Archive)

来源和可复现性层。记录 upstream revision、source record、task provenance、license、converter revision、Exam revision、goal-contract/probe digest 和转换映射。不重复存放可运行 task 或 trial trajectory。

`scripts/build_source_archive.py` 根据审核后的 source-record JSONL 生成 archive manifest。公开 archive 只保存脱敏描述和 digest，隐藏评测规则本身不进入 dataset。

## 三方追溯

Exam revision 冻结后才能运行 trial。Trials 每行必须指向精确 Exam revision、task digest 和 trial id；Source Archive 必须指向产生该 Exam revision 的 upstream revision 和 converter。没有完整五任务 E2E 证据前，不发布官方 aggregate leaderboard。
