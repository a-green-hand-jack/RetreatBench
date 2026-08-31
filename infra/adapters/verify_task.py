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
    directory appears (by content) anywhere under the converted task's
    environment/ -- checked in two tiers:
      - exact content-hash match: HARD FAIL. The private file's actual
        bytes are reachable by the agent; this silently corrupts an
        evaluation rather than merely failing it, so it always blocks.
      - filename match only, content differs: WARNING, not a hard fail.
        Two unrelated files can legitimately share a name (e.g. a paper's
        own published output vs. that paper's private held-out target
        sharing an upstream filename convention). This still blocks by
        default -- pass --confirm-name-collision <filename> once a human
        has verified by hand that the specific collision is a false
        positive (different hash, different size, non-overlapping
        content, and the visible copy is independently justified, e.g.
        listed as legitimate task input in the upstream's own manifest).

Usage:
    python3 infra/adapters/verify_task.py <converted-task-dir> [--skip-build] \
        [--private-source <dir> ...] [--confirm-name-collision <filename> ...]
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


def check_no_private_leak(
    task_dir: Path,
    private_source_dirs: list[Path],
    confirmed_name_collisions: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Check private-source files against the converted task's agent-visible
    environment/ tree. Returns (hard_fails, warnings):

    - exact content-hash match -> hard_fails (always blocks; real leak)
    - filename match, content differs, name NOT in confirmed_name_collisions
      -> warnings (blocks unless explicitly confirmed via --confirm-name-collision)
    - filename match, content differs, name IS in confirmed_name_collisions
      -> silently ignored (previously reviewed and confirmed as unrelated files)
    """
    confirmed_name_collisions = confirmed_name_collisions or set()

    environment_dir = task_dir / "environment"
    if not environment_dir.exists():
        return [], []

    visible_files = [p for p in environment_dir.rglob("*") if p.is_file()]
    visible_hashes = {_sha256(p): p for p in visible_files}
    visible_names = {p.name: p for p in visible_files}

    hard_fails: list[str] = []
    warnings: list[str] = []
    for source_dir in private_source_dirs:
        if not source_dir.exists():
            hard_fails.append(f"--private-source {source_dir} does not exist")
            continue
        for private_file in source_dir.rglob("*"):
            if not private_file.is_file():
                continue
            digest = _sha256(private_file)
            if digest in visible_hashes:
                hard_fails.append(
                    f"PRIVATE LEAK: {private_file} content found verbatim at "
                    f"{visible_hashes[digest]} (under environment/)"
                )
            elif private_file.name in visible_names:
                visible = visible_names[private_file.name]
                if private_file.name in confirmed_name_collisions:
                    continue
                warnings.append(
                    f"NAME COLLISION (content differs, unconfirmed): {private_file.name} "
                    f"also present at {visible} (under environment/) -- "
                    f"private={private_file} sha256={digest[:12]}.. size={private_file.stat().st_size}B, "
                    f"visible sha256={_sha256(visible)[:12]}.. size={visible.stat().st_size}B. "
                    f"If a human has verified these are unrelated files (different content, "
                    f"the visible one independently justified as legitimate task input), "
                    f"re-run with --confirm-name-collision {private_file.name}"
                )
    return hard_fails, warnings


def verify(
    task_dir: Path,
    *,
    skip_build: bool,
    private_source_dirs: list[Path] | None = None,
    confirmed_name_collisions: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []

    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        return [f"missing {toml_path}"], []

    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"{toml_path} does not parse: {exc}"], []

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
        leak_fails, leak_warnings = check_no_private_leak(
            task_dir, private_source_dirs, confirmed_name_collisions
        )
        problems.extend(leak_fails)
        warnings.extend(leak_warnings)

    return problems, warnings


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
        "environment/ (by content hash, hard-fail; by filename-only match, warning); repeatable",
    )
    parser.add_argument(
        "--confirm-name-collision",
        action="append",
        default=[],
        metavar="FILENAME",
        help="filename a human has already reviewed and confirmed is an unrelated-file "
        "name collision (different hash/content), not a leak -- suppresses that specific "
        "warning; repeatable",
    )
    args = parser.parse_args()

    problems, warnings = verify(
        args.task_dir,
        skip_build=args.skip_build,
        private_source_dirs=args.private_source,
        confirmed_name_collisions=set(args.confirm_name_collision),
    )
    if warnings:
        print(f"WARN {args.task_dir}:")
        for w in warnings:
            print(f"  - {w}")
    if problems:
        print(f"FAIL {args.task_dir}:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    if warnings:
        # Unconfirmed name-collision warnings still block by default -- an
        # operator must explicitly re-run with --confirm-name-collision.
        print(f"BLOCKED (unconfirmed warnings) {args.task_dir}")
        sys.exit(1)
    print(f"OK {args.task_dir}")


if __name__ == "__main__":
    main()
