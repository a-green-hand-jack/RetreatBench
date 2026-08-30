from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from retreatbench.state import StateError, build_manifest, capture_state, restore_state, verify_manifest


def test_capture_restore_and_verify(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested").mkdir()
    (source / "nested" / "output.txt").write_text("hello\n", encoding="utf-8")
    snapshot = capture_state(source, tmp_path / "snapshot")

    restored = tmp_path / "restored"
    restore_state(snapshot.archive.parent, restored)
    verify_manifest(restored, {**snapshot.manifest, "root": str(restored)})
    assert (restored / "nested" / "output.txt").read_text() == "hello\n"


def test_manifest_detects_mutation(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "output.txt").write_text("before", encoding="utf-8")
    manifest = build_manifest(root)
    (root / "output.txt").write_text("after", encoding="utf-8")

    with pytest.raises(StateError, match="do not match"):
        verify_manifest(root, manifest)


def test_capture_rejects_snapshot_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(StateError, match="outside the state root"):
        capture_state(root, root / "snapshot")


def test_restore_preserves_restrictive_directory_mode(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    nested = source / "nested"
    nested.mkdir(mode=0o755)
    (nested / "output.txt").write_text("hello", encoding="utf-8")
    nested.chmod(0o555)
    snapshot = capture_state(source, tmp_path / "snapshot")

    restored = tmp_path / "restored"
    restore_state(snapshot.archive.parent, restored)
    assert (restored / "nested").stat().st_mode & 0o777 == 0o555


def test_restore_rejects_archive_path_escape(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    archive = snapshot_dir / "state_bundle.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("../escape.txt")
        member.size = 1
        tar.addfile(member, io.BytesIO(b"x"))
    manifest = {
        "schema_version": "retreatbench.state-manifest.v1",
        "root_mode": 0o755,
        "root": str(tmp_path / "source"),
        "excluded": [],
        "entries": [],
        "tree_sha256": "unused",
        "archive": {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
    }
    (snapshot_dir / "state_manifest.json").write_text(json.dumps(manifest))

    with pytest.raises((tarfile.ReadError, StateError)):
        restore_state(snapshot_dir, tmp_path / "restored")


def test_verify_rejects_malformed_manifest(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(StateError, match="excluded"):
        verify_manifest(
            root,
            {
                "schema_version": "retreatbench.state-manifest.v1",
                "excluded": None,
                "entries": [],
                "tree_sha256": "x",
            },
        )
