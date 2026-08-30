#!/usr/bin/env bash
# Thin orchestration loop for the ResearchClawBench adapter. No conversion
# logic here -- see agent.md; this just invokes the opencode agent once per
# task id, then always runs the mandatory private-ground-truth-leak check
# (not an optional step -- see verify_task.py's --private-source) before
# logging pass/fail. Does not halt on a single task's failure; every result
# is appended to <output-root>/conversion_log.txt so failures are recorded,
# not silently dropped or silently retried.
set -euo pipefail

UPSTREAM_ARG="${1:?usage: convert.sh <upstream-tasks-dir> <output-root> <task-id> [task-id ...]}"
OUTPUT_ARG="${2:?usage: convert.sh <upstream-tasks-dir> <output-root> <task-id> [task-id ...]}"
shift 2
TASK_IDS=("$@")

UPSTREAM_ROOT="$(cd "$UPSTREAM_ARG" && pwd)"
mkdir -p "$OUTPUT_ARG"
OUTPUT_ROOT="$(cd "$OUTPUT_ARG" && pwd)"

MODEL="${RETREATBENCH_ADAPTER_MODEL:-openai/gpt-5.6-sol}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${OUTPUT_ROOT}/conversion_log.txt"

if [ ${#TASK_IDS[@]} -eq 0 ]; then
  echo "no task ids given; refusing to convert the whole benchmark in one pass" >&2
  exit 1
fi

for task_id in "${TASK_IDS[@]}"; do
  upstream_dir="${UPSTREAM_ROOT}/${task_id}"
  out_dir="${OUTPUT_ROOT}/${task_id}"
  if [ ! -d "$upstream_dir" ]; then
    echo "skip ${task_id}: not found at ${upstream_dir}" >&2
    printf "%s\tSKIP\tupstream dir not found\n" "${task_id}" >> "$LOG_FILE"
    continue
  fi
  mkdir -p "$out_dir"
  prompt="$(sed "s#{upstream_task_dir}#${upstream_dir}#; s#{output_dir}#${out_dir}#" "${SCRIPT_DIR}/prompt.template.txt")"
  echo "=== converting ${task_id} ==="
  opencode run --agent stevedore-rcb -m "$MODEL" --format json "$prompt"

  echo "=== mandatory private-leak check for ${task_id} ==="
  if python3 "${SCRIPT_DIR}/../verify_task.py" "$out_dir" --skip-build \
      --private-source "${upstream_dir}/target_study"; then
    printf "%s\tCONVERTED_AND_LEAK_CHECKED_OK\t-\n" "${task_id}" >> "$LOG_FILE"
  else
    printf "%s\tFAIL_LEAK_CHECK_OR_SCHEMA\tsee output above\n" "${task_id}" >> "$LOG_FILE"
  fi
done
