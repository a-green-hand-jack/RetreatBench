"""Helpers for the fixed five-task Harbor end-to-end gate."""

from __future__ import annotations

import json
from pathlib import Path


def discover_tasks(dataset_root: str | Path) -> list[tuple[str, Path]]:
    """Return existing Harbor task directories in deterministic task-id order."""

    root = Path(dataset_root)
    tasks = []
    for task_toml in root.rglob("task.toml"):
        task_dir = task_toml.parent
        task_id = "/".join(task_dir.relative_to(root).parts)
        tasks.append((task_id, task_dir))
    return sorted(tasks, key=lambda item: item[0])


def tasks_from_manifest(dataset_root: str | Path, manifest: str | Path) -> list[tuple[str, Path]]:
    """Resolve the published task order against real Harbor task directories."""

    payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    entries = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise TypeError(f"task manifest must contain a tasks list: {manifest}")
    discovered = dict(discover_tasks(dataset_root))
    selected: list[tuple[str, Path]] = []
    for entry in entries:
        task_id = entry.get("task_id") if isinstance(entry, dict) else entry
        if not isinstance(task_id, str) or task_id not in discovered:
            raise ValueError(f"manifest task is missing from dataset: {task_id!r}")
        selected.append((task_id, discovered[task_id]))
    return selected
