#!/usr/bin/env python3
"""Run the five-task RetreatBench Harbor E2E gate.

The task dataset is the source of truth: this script never synthesizes or
duplicates tasks.  It freezes the first five task directories in lexical task
ID order into a manifest so a release can be reproduced against the same Hub
revision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from retreatbench.e2e import discover_tasks, tasks_from_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--repo", required=True, help="immutable HF task-tree URL")
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs/retreatbench-e2e"))
    parser.add_argument("--output", type=Path, default=Path("e2e-manifest.json"))
    parser.add_argument("--task-manifest", type=Path, help="dataset manifest naming the frozen tasks")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    discovered = (
        tasks_from_manifest(args.dataset_root, args.task_manifest)
        if args.task_manifest
        else discover_tasks(args.dataset_root)
    )
    if len(discovered) < 5:
        parser.error(f"dataset contains {len(discovered)} tasks; five are required")
    selected = discovered[:5]
    args.jobs_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "retreatbench.e2e-manifest.v1",
        "dataset_repo": args.repo,
        "agent": "codex",
        "model": "gpt-5.6-terra",
        "plugin": "retreatbench.harbor_plugins:AvoidanceExportBoth",
        "tasks": [{"task_id": task_id, "path": str(path)} for task_id, path in selected],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for task_id, _ in selected:
        command = [
            "harbor",
            "run",
            "--repo",
            args.repo,
            "--include-task-name",
            task_id,
            "-a",
            "codex",
            "-m",
            "gpt-5.6-terra",
            "--resume-trajectory",
            "--plugin",
            "retreatbench.harbor_plugins:AvoidanceExportBoth",
        ]
        print("$ " + " ".join(command), flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=args.jobs_dir, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
