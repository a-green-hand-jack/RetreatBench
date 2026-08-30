#!/usr/bin/env python3
"""Mechanical verification of one converted Harbor task tree.

Deliberately NOT a semantic parity check against the upstream task -- only:
(1) task.toml parses and carries the fields every Harbor task needs, with a
    real build path (either docker_image is set, or environment/Dockerfile
    exists -- Harbor builds from the Dockerfile itself when docker_image is
    unset, see harbor.environments.definition.should_use_prebuilt_docker_image),
(2) the environment builds (unless --skip-build),
(3) tests/test.sh actually writes Harbor's expected reward.txt/reward.json
    (a real `harbor run` trial fails with RewardFileNotFoundError otherwise,
    regardless of whether the underlying tests passed -- this class of bug
    is caught here mechanically, cheaply, before spending a real trial on it),
(4) when --private-source is given, no file from that private source
    directory (matched by exact content hash, or by filename as a weaker
    heuristic) appears anywhere under the converted task's environment/ --
    this is a hard fail, not a warning, since private-ground-truth leakage
    silently corrupts an evaluation rather than merely failing it.

Usage:
    python3 infra/adapters/verify_task.py <converted-task-dir> [--skip-build] \
        [--private-source <dir> ...]
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

REQUIRED_TOP_FIELDS = ["version"]
REQUIRED_SECTIONS = {
    "metadata": ["author_name", "difficulty", "category"],
    "verifier": ["timeout_sec"],
    "agent": ["timeout_sec"],
    "environment": ["build_timeout_sec"],
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_no_private_leak(task_dir: Path, private_source_dirs: list[Path]) -> list[str]:
    """Hard-fail if any private-source file's bytes or filename appear under
    the converted task's agent-visible environment/ tree."""

    environment_dir = task_dir / "environment"
    if not environment_dir.exists():
        return []

    visible_files = [p for p in environment_dir.rglob("*") if p.is_file()]
    visible_hashes = {_sha256(p): p for p in visible_files}
    visible_names = {p.name: p for p in visible_files}

    problems: list[str] = []
    for source_dir in private_source_dirs:
        if not source_dir.exists():
            problems.append(f"--private-source {source_dir} does not exist")
            continue
        for private_file in source_dir.rglob("*"):
            if not private_file.is_file():
                continue
            digest = _sha256(private_file)
            if digest in visible_hashes:
                problems.append(
                    f"PRIVATE LEAK: {private_file} content found verbatim at "
                    f"{visible_hashes[digest]} (under environment/)"
                )
            elif private_file.name in visible_names:
                problems.append(
                    f"PRIVATE LEAK (name match, verify by hand): {private_file.name} "
                    f"also present at {visible_names[private_file.name]} (under environment/)"
                )
    return problems


def verify(
    task_dir: Path,
    *,
    skip_build: bool,
    private_source_dirs: list[Path] | None = None,
) -> list[str]:
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
    docker_image = data.get("environment", {}).get("docker_image")
    if not docker_image and not dockerfile.exists():
        problems.append(
            "task.toml has no [environment].docker_image and environment/Dockerfile "
            "is missing -- Harbor has no way to build or pull this environment"
        )
    elif dockerfile.exists() and not skip_build:
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

    test_sh = tests_dir / "test.sh"
    if test_sh.exists():
        test_sh_content = test_sh.read_text(encoding="utf-8", errors="replace")
        if "reward.txt" not in test_sh_content and "reward.json" not in test_sh_content:
            problems.append(
                "tests/test.sh never writes /logs/verifier/reward.txt or reward.json -- "
                "Harbor's verifier reads the trial's score from that file, not from the "
                "script's exit code; a trial will fail with RewardFileNotFoundError "
                "regardless of whether the underlying tests passed"
            )
    elif tests_dir.exists():
        problems.append("missing tests/test.sh (Harbor's verifier entrypoint)")

    if private_source_dirs:
        problems.extend(check_no_private_leak(task_dir, private_source_dirs))

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--skip-build", action="store_true", help="skip the environment build check")
    parser.add_argument(
        "--private-source",
        type=Path,
        action="append",
        default=[],
        help="a directory of private/ground-truth files that must never appear under "
        "environment/ (by content hash or filename); repeatable",
    )
    args = parser.parse_args()

    problems = verify(args.task_dir, skip_build=args.skip_build, private_source_dirs=args.private_source)
    if problems:
        print(f"FAIL {args.task_dir}:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"OK {args.task_dir}")


if __name__ == "__main__":
    main()
