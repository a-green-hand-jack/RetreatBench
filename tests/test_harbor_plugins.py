from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from retreatbench.harbor_plugins import PLUGIN_ALIASES, AvoidanceLocal


class FakeJob:
    def __init__(self) -> None:
        self.callbacks = {}

    def on_agent_ended(self, callback):
        self.callbacks["agent_end"] = callback

    def on_trial_ended(self, callback):
        self.callbacks["trial_end"] = callback


def test_plugin_registers_hooks_and_creates_sanitized_trial(tmp_path: Path, monkeypatch) -> None:
    plugin = AvoidanceLocal(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    assert set(job.callbacks) == {"agent_end", "trial_end"}

    event = SimpleNamespace(
        trial_id="t1",
        trial_name="task-1",
        task_name="bench/task-1",
        result={"agent_result": {"message": "done"}},
    )
    asyncio.run(job.callbacks["agent_end"](event))
    asyncio.run(job.callbacks["trial_end"](event))

    manifest = json.loads((tmp_path / "task-1" / "retreatbench-trial-manifest.json").read_text())
    assert manifest["upload_mode"] == "local"
    assert manifest["upload_status"] == "disabled"
    assert (tmp_path / "task-1" / "public" / "behavior_result.json").exists()
    behavior = json.loads((tmp_path / "task-1" / "behavior_result.json").read_text())
    assert behavior["schema_version"] == "retreatbench.behavior-result.v1"
    assert behavior["classification"] == "inconclusive"


def test_plugin_aliases_are_stable() -> None:
    assert PLUGIN_ALIASES["avoidance-export-both"].endswith(":AvoidanceExportBoth")


def test_performer_profile_excludes_auditor_artifacts(tmp_path: Path) -> None:
    from retreatbench.harbor_plugins import AvoidanceExportPerformer

    plugin = AvoidanceExportPerformer(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    event = SimpleNamespace(
        trial_id="t2",
        trial_name="task-2",
        task_name="bench/task-2",
        result={"trajectory": [{"action": "write"}]},
    )
    asyncio.run(job.callbacks["agent_end"](event))
    asyncio.run(job.callbacks["trial_end"](event))

    public = tmp_path / "task-2" / "public"
    assert (public / "performer_trace.json").exists()
    assert not (public / "auditor_trace.json").exists()
    assert not (public / "behavior_result.json").exists()


def test_plugin_keeps_trial_name_inside_output_dir(tmp_path: Path) -> None:
    plugin = AvoidanceLocal(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    event = SimpleNamespace(trial_id="t3", trial_name="../../outside", task_name="x", result={})
    asyncio.run(job.callbacks["agent_end"](event))
    assert (tmp_path / "_" / "_" / "outside" / "performer_trace.json").exists()
    assert not (tmp_path.parent / "outside").exists()
