#!/usr/bin/env bash
# Thin orchestration loop for the Terminal-Bench 1.x adapter. No conversion
# logic here -- see agent.md; this just invokes the opencode agent once per
# task id and leaves verification to verify_task.py.
set -euo pipefail

UPSTREAM_ARG="${1:?usage: convert.sh <upstream-original-tasks-dir> <output-root> <task-id> [task-id ...]}"
OUTPUT_ARG="${2:?usage: convert.sh <upstream-original-tasks-dir> <output-root> <task-id> [task-id ...]}"
shift 2
TASK_IDS=("$@")

UPSTREAM_ROOT="$(cd "$UPSTREAM_ARG" && pwd)"
mkdir -p "$OUTPUT_ARG"
OUTPUT_ROOT="$(cd "$OUTPUT_ARG" && pwd)"

MODEL="${RETREATBENCH_ADAPTER_MODEL:-openai/gpt-5.6-sol}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ${#TASK_IDS[@]} -eq 0 ]; then
  echo "no task ids given; refusing to convert the whole benchmark in one pass" >&2
  exit 1
fi

for task_id in "${TASK_IDS[@]}"; do
  upstream_dir="${UPSTREAM_ROOT}/${task_id}"
  out_dir="${OUTPUT_ROOT}/${task_id}"
  if [ ! -d "$upstream_dir" ]; then
    echo "skip ${task_id}: not found at ${upstream_dir}" >&2
    continue
  fi
  mkdir -p "$out_dir"
  prompt="$(sed "s#{upstream_task_dir}#${upstream_dir}#; s#{output_dir}#${out_dir}#" "${SCRIPT_DIR}/prompt.template.txt")"
  echo "=== converting ${task_id} ==="
  opencode run --agent stevedore-tb1x -m "$MODEL" --format json "$prompt"
done
