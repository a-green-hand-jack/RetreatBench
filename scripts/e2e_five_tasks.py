#!/usr/bin/env python3
"""Run the five-task RetreatBench Harbor E2E gate.

The task dataset is the source of truth: this script never synthesizes or
duplicates tasks. It freezes the five published ``pwb-0001`` through
``pwb-0005`` task directories into a manifest so a release can be reproduced
against the same Hub revision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from retreatbench.e2e import discover_tasks, tasks_from_manifest

E2E_TASK_IDS = tuple(f"pwb-{index:04d}" for index in range(1, 6))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--repo", required=True, help="immutable HF task-tree URL")
    parser.add_argument(
        "--repo-path",
        help="path inside the repository that contains Harbor task directories",
    )
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
    by_basename = {Path(task_id).name: (task_id, path) for task_id, path in discovered}
    missing = [task_id for task_id in E2E_TASK_IDS if task_id not in by_basename]
    if missing:
        parser.error("dataset is missing fixed E2E tasks: " + ", ".join(missing))
    selected = [by_basename[task_id] for task_id in E2E_TASK_IDS]
    repo_path = args.repo_path or str(selected[0][1].relative_to(args.dataset_root).parts[0])
    harbor_task_ids = [Path(task_id).name for task_id, _ in selected]
    args.jobs_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "retreatbench.e2e-manifest.v1",
        "dataset_repo": args.repo,
        "agent": "codex",
        "model": "gpt-5.6-terra",
        "plugin": "retreatbench.harbor_plugins:RecorderExportBoth",
        "tasks": [
            {"task_id": harbor_id, "path": str(path), "dataset_path": task_id}
            for (task_id, path), harbor_id in zip(selected, harbor_task_ids, strict=True)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for harbor_task_id in harbor_task_ids:
        command = [
            "harbor",
            "run",
            "--repo",
            args.repo,
            "--include-task-name",
            harbor_task_id,
            "--path",
            repo_path,
            "-a",
            "codex",
            "-m",
            "gpt-5.6-terra",
            "--resume-trajectory",
            "--plugin",
            "retreatbench.harbor_plugins:RecorderExportBoth",
            "--yes",
            "--n-concurrent",
            "1",
        ]
        if (Path.home() / ".codex" / "auth.json").is_file():
            command.extend(["--agent-env", "CODEX_FORCE_AUTH_JSON=1"])
        print("$ " + " ".join(command), flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=args.jobs_dir, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
