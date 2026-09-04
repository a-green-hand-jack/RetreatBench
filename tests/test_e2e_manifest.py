from __future__ import annotations

import json
from pathlib import Path

from retreatbench.e2e import discover_tasks, tasks_from_manifest


def test_discover_tasks_is_sorted_and_uses_existing_task_dirs(tmp_path: Path) -> None:
    for task_id in ("zeta", "alpha", "middle"):
        task_dir = tmp_path / task_id
        task_dir.mkdir()
        (task_dir / "task.toml").write_text("[task]\nname='x/y'\n", encoding="utf-8")
    assert [task_id for task_id, _ in discover_tasks(tmp_path)] == ["alpha", "middle", "zeta"]


def test_tasks_from_manifest_preserves_published_order(tmp_path: Path) -> None:
    for task_id in ("first", "second"):
        task_dir = tmp_path / task_id
        task_dir.mkdir()
        (task_dir / "task.toml").write_text("[task]\nname='x/y'\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"tasks": [{"task_id": "second"}, {"task_id": "first"}]}), encoding="utf-8")
    assert [task_id for task_id, _ in tasks_from_manifest(tmp_path, manifest)] == ["second", "first"]
