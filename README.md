# RetreatBench

RetreatBench is a Harbor-native benchmark for judging how an autonomous agent behaves when a task becomes difficult: does it preserve the original goal, recover through effective action, and report honestly?

The repository has two products:

1. **Benchmark Builder**: OpenCode workflows that build or convert Harbor tasks and publish runnable releases to [`Avoidance-Behavior-Exam`](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam).
2. **Retreat Recorder**: an npm-installed Harbor companion that observes the solver during a trial, produces sanitized trails and a deterministic behavior result, and optionally uploads them to [`Avoidance-Behavior-Exam-Trials`](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials).

## Install

Supported v1 environments are Ubuntu/Debian with Python 3.11+, Node.js 20+, npm, Docker, git and curl. The bootstrap installs missing system dependencies, Harbor, OpenCode, the Recorder package and the plugin bridge:

```bash
curl -fsSL https://raw.githubusercontent.com/a-green-hand-jack/RetreatBench/main/scripts/install.sh | bash
```

Read [the installation guide](docs/installation.md) for login, verification, HF credentials and Docker/TeX troubleshooting.

## Run a task

Users run an ordinary Harbor task. Harbor starts the solver; the plugin starts Retreat Recorder automatically:

```bash
harbor run \
  --repo https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam/tree/<revision>/<task-root> \
  --include-task-name <task-id> \
  -a codex -m gpt-5.6-terra \
  --plugin retreatbench.harbor_plugins:RecorderExportBoth
```

The three profiles are `recorder-local` (no upload), `recorder-export-solver` (solver trail only), and `recorder-export-both` (both sanitized trails). Inspect the result with:

```bash
retreatbench show-result <trial>/behavior_result.json
```

The result explains whether retreat was detected, whether continuation recovered the goal, and what evidence supports the decision. Harbor reward remains the original verifier reward; it is not replaced by a behavior score.

## Build tasks

Builder workflows accept a source repository, immutable revision, task id and output directory, then emit a Harbor `task.toml` tree, build manifest and provenance record. Every task must pass parsing, Docker build, verifier, private-source leak, and real Harbor smoke checks before publication. See [Benchmark Builder](docs/benchmark-building.md).

## Evaluation and data

- [Evaluation protocol](docs/evaluation.md): formal retreat definition, same-state continuation, evidence tiers and metrics.
- [Retreat Recorder](docs/recorder.md): lifecycle callbacks, trails, sanitizer and upload profiles.
- [Datasets](docs/datasets.md): Exam, Trials and Source Archive responsibilities.
- [Documentation index](docs/README.md).

The root [`CITATION.cff`](CITATION.cff) is machine-readable citation metadata for GitHub and reference tools. Framework code is Apache-2.0; upstream tasks retain their own licenses.
