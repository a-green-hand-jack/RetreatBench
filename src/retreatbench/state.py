from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class StateError(ValueError):
    """Raised when a workspace snapshot cannot be trusted or restored."""


@dataclass(frozen=True)
class StateSnapshot:
    root: Path
    manifest: dict[str, Any]
    archive: Path


MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_EXPANDED_BYTES = 10 * 1024 * 1024 * 1024


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _tree_hash(payload: dict[str, Any]) -> str:
    identity = {
        "schema_version": payload["schema_version"],
        "root_mode": payload["root_mode"],
        "excluded": payload["excluded"],
        "entries": payload["entries"],
    }
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canonical.encode("utf-8"))


def _iter_entries(root: Path, excluded: set[str]) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        relative = _relative(path, root)
        if any(relative == item or relative.startswith(f"{item}/") for item in excluded):
            continue
        yield path


def build_manifest(root: str | Path, *, excluded: Iterable[str] = ()) -> dict[str, Any]:
    """Build a deterministic manifest for a workspace tree.

    Paths in the manifest are relative to *root*. Symlinks are recorded but never
    followed, which keeps a snapshot from escaping the declared workspace.
    """

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise StateError(f"state root is not a directory: {root_path}")
    excluded_set = {Path(item).as_posix().strip("/") for item in excluded if item}
    for item in excluded_set:
        excluded_path = root_path / item
        if excluded_path.exists() or excluded_path.is_symlink():
            raise StateError(f"excluded path must be absent from state root: {item}")
    entries: list[dict[str, Any]] = []
    for path in _iter_entries(root_path, excluded_set):
        info = path.lstat()
        relative = _relative(path, root_path)
        entry: dict[str, Any] = {
            "path": relative,
            "mode": stat.S_IMODE(info.st_mode),
        }
        if stat.S_ISLNK(info.st_mode):
            target = (path.parent / os.readlink(path)).resolve()
            try:
                target.relative_to(root_path)
            except ValueError as exc:
                raise StateError(f"symlink target escapes state root: {relative}") from exc
            entry.update({"type": "symlink", "target": os.readlink(path)})
        elif stat.S_ISREG(info.st_mode):
            entry.update(
                {
                    "type": "file",
                    "size": info.st_size,
                    "sha256": _sha256_file(path),
                }
            )
        elif stat.S_ISDIR(info.st_mode):
            entry["type"] = "directory"
        else:
            raise StateError(f"unsupported filesystem entry: {path}")
        entries.append(entry)

    payload = {
        "schema_version": "retreatbench.state-manifest.v1",
        "root": str(root_path),
        "root_mode": stat.S_IMODE(root_path.stat().st_mode),
        "excluded": sorted(excluded_set),
        "entries": entries,
    }
    payload["tree_sha256"] = _tree_hash(payload)
    return payload


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_manifest(root: str | Path, manifest: dict[str, Any], *, check_modes: bool = True) -> None:
    """Verify a workspace against a previously captured manifest."""

    _validate_manifest(manifest)
    actual = build_manifest(root, excluded=manifest["excluded"])
    expected_entries = manifest.get("entries")
    if not isinstance(expected_entries, list):
        raise StateError("manifest entries must be a list")
    if not check_modes:
        expected_modes = {entry["path"]: entry["mode"] for entry in expected_entries}
        for entry in actual["entries"]:
            entry["mode"] = expected_modes[entry["path"]]
        actual["root_mode"] = manifest["root_mode"]
        actual["tree_sha256"] = _tree_hash(actual)
    if actual["entries"] != expected_entries:
        raise StateError("workspace entries do not match the state manifest")
    if actual["tree_sha256"] != manifest.get("tree_sha256"):
        raise StateError("workspace tree hash does not match the state manifest")


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "retreatbench.state-manifest.v1":
        raise StateError("unsupported or missing state manifest schema_version")
    if not isinstance(manifest.get("excluded"), list) or not all(
        isinstance(item, str) for item in manifest["excluded"]
    ):
        raise StateError("manifest excluded must be a list of strings")
    if not isinstance(manifest.get("entries"), list):
        raise StateError("manifest entries must be a list")
    if not isinstance(manifest.get("tree_sha256"), str):
        raise StateError("manifest tree_sha256 must be a string")
    if not isinstance(manifest.get("root_mode"), int):
        raise StateError("manifest root_mode must be an integer")
    for entry in manifest["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise StateError("manifest entries must contain path objects")
        path = Path(entry["path"])
        if path.is_absolute() or ".." in path.parts or entry["path"] != path.as_posix():
            raise StateError(f"manifest path must be relative and canonical: {entry['path']!r}")
        if entry.get("type") not in {"file", "directory", "symlink"}:
            raise StateError(f"unsupported manifest entry type: {entry.get('type')!r}")
        if not isinstance(entry.get("mode"), int):
            raise StateError("manifest entry mode must be an integer")
        if entry["type"] == "file" and not all(
            isinstance(entry.get(field), expected)
            for field, expected in (("size", int), ("sha256", str))
        ):
            raise StateError("file manifest entries require size and sha256")
        if entry["type"] == "symlink" and not isinstance(entry.get("target"), str):
            raise StateError("symlink manifest entries require target")


def _apply_modes(root: Path, entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        if entry["type"] == "file":
            os.chmod(root / entry["path"], entry["mode"])
    directories = [entry for entry in entries if entry["type"] == "directory"]
    for entry in sorted(directories, key=lambda item: item["path"].count("/"), reverse=True):
        os.chmod(root / entry["path"], entry["mode"])


def create_archive(root: str | Path, archive: str | Path, *, excluded: Iterable[str] = ()) -> dict[str, Any]:
    """Create a gzip tar archive and return its manifest plus archive digest."""

    root_path = Path(root).resolve()
    archive_path = Path(archive).resolve()
    try:
        archive_path.relative_to(root_path)
    except ValueError:
        pass
    else:
        raise StateError("state archive must be outside the state root")
    manifest = build_manifest(root_path, excluded=excluded)
    output = archive_path
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, mode="w:gz") as tar:
        for path in _iter_entries(root_path, set(manifest["excluded"])):
            tar.add(path, arcname=_relative(path, root_path), recursive=False)
    manifest["archive"] = {
        "path": str(output),
        "size": output.stat().st_size,
        "sha256": _sha256_file(output),
        "format": "tar.gz",
    }
    return manifest


def restore_archive(archive: str | Path, destination: str | Path, manifest: dict[str, Any]) -> None:
    """Safely restore an archive and verify the resulting tree."""

    archive_path = Path(archive).resolve()
    destination_input = Path(destination)
    if destination_input.is_symlink():
        raise StateError(f"restore destination must not be a symlink: {destination_input}")
    destination_path = destination_input.resolve()
    _validate_manifest(manifest)
    archive = manifest.get("archive")
    if not isinstance(archive, dict) or not isinstance(archive.get("sha256"), str):
        raise StateError("manifest archive must contain sha256")
    if not archive_path.is_file():
        raise StateError(f"state archive does not exist: {archive_path}")
    expected_archive = manifest.get("archive", {})
    if expected_archive.get("sha256") != _sha256_file(archive_path):
        raise StateError("state archive hash does not match the manifest")
    if destination_path.exists():
        if not destination_path.is_dir():
            raise StateError(f"restore destination must be a directory: {destination_path}")
        if any(destination_path.iterdir()):
            raise StateError(f"restore destination must be empty: {destination_path}")
    if destination_path.is_symlink():
        raise StateError(f"restore destination must not be a symlink: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_destination = Path(tempfile.mkdtemp(prefix="retreatbench-restore-", dir=destination_path.parent))
    try:
        with tarfile.open(archive_path, mode="r:gz") as tar:
            members = tar.getmembers()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise StateError("state archive contains too many members")
            expanded_bytes = sum(member.size for member in members if member.isreg())
            if expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
                raise StateError("state archive expands beyond the configured size limit")
            for member in members:
                target = (temporary_destination / member.name).resolve()
                try:
                    target.relative_to(temporary_destination)
                except ValueError as exc:
                    raise StateError(f"archive contains path outside destination: {member.name}") from exc
                if member.issym():
                    link_target = (target.parent / member.linkname).resolve()
                    try:
                        link_target.relative_to(temporary_destination)
                    except ValueError as exc:
                        raise StateError(f"archive symlink escapes destination: {member.name}") from exc
                elif member.islnk() or not (member.isdir() or member.isreg()):
                    raise StateError(f"unsupported archive member: {member.name}")
            for member in members:
                target = temporary_destination / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isreg():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = tar.extractfile(member)
                    if source is None:
                        raise StateError(f"cannot read archive member: {member.name}")
                    with target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    os.chmod(target, member.mode)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(member.linkname)
        verify_manifest(
            temporary_destination,
            {**manifest, "root": str(temporary_destination)},
            check_modes=False,
        )
        _apply_modes(temporary_destination, manifest["entries"])
        os.chmod(temporary_destination, manifest["root_mode"])
        if destination_path.exists():
            destination_path.rmdir()
        os.replace(temporary_destination, destination_path)
    except Exception:
        shutil.rmtree(temporary_destination, ignore_errors=True)
        raise


def capture_state(root: str | Path, output_dir: str | Path, *, excluded: Iterable[str] = ()) -> StateSnapshot:
    """Capture a workspace and its manifest into an output directory."""

    root_path = Path(root).resolve()
    output = Path(output_dir).resolve()
    try:
        output.relative_to(root_path)
    except ValueError:
        pass
    else:
        raise StateError("snapshot output directory must be outside the state root")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "state_bundle.tar.gz"
    manifest = create_archive(root_path, archive, excluded=excluded)
    write_manifest(output / "state_manifest.json", manifest)
    return StateSnapshot(root=Path(root).resolve(), manifest=manifest, archive=archive)


def restore_state(snapshot_dir: str | Path, destination: str | Path) -> None:
    snapshot = Path(snapshot_dir).resolve()
    manifest_path = snapshot / "state_manifest.json"
    archive_path = snapshot / "state_bundle.tar.gz"
    if not manifest_path.is_file() or not archive_path.is_file():
        raise StateError("snapshot must contain state_manifest.json and state_bundle.tar.gz")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError(f"invalid state manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise StateError("state manifest must be a JSON object")
    restore_archive(archive_path, destination, manifest)
