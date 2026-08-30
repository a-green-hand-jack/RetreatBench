#!/usr/bin/env python3
"""Mechanical verification of one converted Harbor task tree.

Deliberately NOT a semantic parity check against the upstream task -- only:
(1) task.toml parses and carries the fields every Harbor task needs, and
(2) the environment's Dockerfile builds (unless --skip-build, since a real
    docker_image is usually a placeholder immediately after conversion).

Usage:
    python3 infra/adapters/verify_task.py <converted-task-dir> [--skip-build]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

REQUIRED_TOP_FIELDS = ["version"]
REQUIRED_SECTIONS = {
    "metadata": ["author_name", "difficulty", "category"],
    "verifier": ["timeout_sec"],
    "agent": ["timeout_sec"],
    "environment": ["build_timeout_sec", "docker_image"],
}


def verify(task_dir: Path, *, skip_build: bool) -> list[str]:
    problems: list[str] = []

    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        return [f"missing {toml_path}"]

    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"{toml_path} does not parse: {exc}"]

    for field in REQUIRED_TOP_FIELDS:
        if field not in data:
            problems.append(f"task.toml missing top-level field: {field}")

    for section, fields in REQUIRED_SECTIONS.items():
        if section not in data:
            problems.append(f"task.toml missing [{section}]")
            continue
        for field in fields:
            if field not in data[section]:
                problems.append(f"task.toml [{section}] missing field: {field}")

    if not (task_dir / "instruction.md").exists():
        problems.append("missing instruction.md")

    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.exists():
        problems.append("missing environment/Dockerfile")
    elif not skip_build:
        image_tag = f"retreatbench-adapter-verify-{task_dir.name}".lower()
        result = subprocess.run(
            ["docker", "build", "-t", image_tag, "-f", str(dockerfile), str(dockerfile.parent)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            problems.append(
                f"docker build failed (exit {result.returncode}): {result.stderr[-2000:]}"
            )

    tests_dir = task_dir / "tests"
    if not tests_dir.exists() or not any(tests_dir.iterdir()):
        problems.append("tests/ is missing or empty")

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--skip-build", action="store_true", help="skip the docker build check")
    args = parser.parse_args()

    problems = verify(args.task_dir, skip_build=args.skip_build)
    if problems:
        print(f"FAIL {args.task_dir}:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"OK {args.task_dir}")


if __name__ == "__main__":
    main()
