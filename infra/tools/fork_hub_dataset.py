#!/usr/bin/env python3
"""Fork one infra/hub-datasets/*.yaml manifest into Jack-Jieke-Wu/Avoidance-Behavior-Exam.

Thin, deterministic glue only -- no conversion logic. Downloads the pinned
source revision (optionally a subset via `source.include`) and re-uploads it
under `target.path` in the target dataset repo. Requires the `hf` CLI to be
logged in with write access to `target.hub_repo`, and enough local disk to
hold one benchmark's task tree temporarily (run this on a machine with
adequate headroom, not a disk-constrained laptop).

Usage:
    python3 infra/tools/fork_hub_dataset.py infra/hub-datasets/terminal-bench-2.0.yaml [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data.get("status") not in ("harbor-native", "pre-converted"):
        raise SystemExit(
            f"{path}: status={data.get('status')!r} is not fork-ready "
            "(needs-adapter manifests are not handled by this script)"
        )
    if not data.get("source") or not data.get("target"):
        raise SystemExit(f"{path}: missing source/target -- nothing to fork yet")
    return data


def run(cmd: list[str], *, dry_run: bool) -> None:
    print("+", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def fork(manifest_path: Path, *, dry_run: bool) -> None:
    manifest = load_manifest(manifest_path)
    source = manifest["source"]
    target = manifest["target"]

    with tempfile.TemporaryDirectory(prefix="retreatbench-fork-") as tmp:
        local_dir = Path(tmp) / "download"
        download_cmd = [
            "hf",
            "download",
            source["hub_repo"],
            "--repo-type",
            source.get("repo_type", "dataset"),
            "--revision",
            source["revision"],
            "--local-dir",
            str(local_dir),
        ]
        include = source.get("include")
        if include:
            download_cmd += ["--include", f"{include.rstrip('/')}/*"]
        run(download_cmd, dry_run=dry_run)

        upload_source = local_dir / include.rstrip("/") if include else local_dir
        if not dry_run and not upload_source.exists():
            raise SystemExit(f"expected downloaded subset at {upload_source}, not found")

        commit_message = (
            f"Fork {manifest['benchmark']} from {source['hub_repo']}@{source['revision'][:12]}"
        )
        upload_cmd = [
            "hf",
            "upload",
            target["hub_repo"],
            str(upload_source),
            target["path"],
            "--repo-type",
            "dataset",
            "--commit-message",
            commit_message,
        ]
        run(upload_cmd, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")
    args = parser.parse_args()
    fork(args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    if shutil.which("hf") is None:
        raise SystemExit("the `hf` CLI is required (see https://hf.co/cli)")
    main()
