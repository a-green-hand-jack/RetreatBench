from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from retreatbench.harbor_plugins import (
    PLUGIN_ALIASES,
    RecorderExportSolver,
    RecorderLocal,
)


class FakeJob:
    def __init__(self) -> None:
        self.callbacks = {}

    def on_trial_started(self, callback):
        self.callbacks["trial_started"] = callback

    def on_environment_started(self, callback):
        self.callbacks["environment_started"] = callback

    def on_agent_started(self, callback):
        self.callbacks["agent_started"] = callback

    def on_agent_ended(self, callback):
        self.callbacks["agent_ended"] = callback

    def on_verification_started(self, callback):
        self.callbacks["verification_started"] = callback

    def on_trial_ended(self, callback):
        self.callbacks["trial_ended"] = callback

    def on_trial_cancelled(self, callback):
        self.callbacks["trial_cancelled"] = callback


def test_plugin_registers_lifecycle_hooks_and_creates_sanitized_trial(tmp_path: Path) -> None:
    plugin = RecorderLocal(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    assert set(job.callbacks) == {
        "trial_started", "environment_started", "agent_started", "agent_ended",
        "verification_started", "trial_ended", "trial_cancelled",
    }

    event = SimpleNamespace(
        trial_id="t1",
        trial_name="task-1",
        task_name="bench/task-1",
        result={"agent_result": {"message": "done"}},
    )
    asyncio.run(job.callbacks["trial_started"](event))
    asyncio.run(job.callbacks["agent_started"](event))
    asyncio.run(job.callbacks["agent_ended"](event))
    asyncio.run(job.callbacks["trial_ended"](event))

    trial = tmp_path / "task-1"
    manifest = json.loads((trial / "trial-manifest.json").read_text())
    assert manifest["upload_mode"] == "local"
    assert manifest["upload_status"] == "disabled"
    assert manifest["recording_mode"] == "parallel_observer"
    assert manifest["official_behavior_evidence"] is False
    assert (trial / "public" / "behavior_result.json").exists()
    behavior = json.loads((trial / "behavior_result.json").read_text())
    assert behavior["schema_version"] == "retreatbench.behavior-result.v1"
    assert behavior["classification"] == "inconclusive"


def test_plugin_aliases_are_stable() -> None:
    assert set(PLUGIN_ALIASES) == {
        "recorder-local", "recorder-export-solver", "recorder-export-both",
    }
    assert PLUGIN_ALIASES["recorder-export-both"].endswith(":RecorderExportBoth")


def test_successful_trial_materializes_non_retreat_context(tmp_path: Path) -> None:
    plugin = RecorderLocal(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    event = SimpleNamespace(
        trial_id="t-success",
        trial_name="task-success",
        task_name="bench/task-success",
        result={"verifier_result": {"rewards": {"reward": 1.0}}},
    )
    asyncio.run(job.callbacks["trial_ended"](event))

    trial = tmp_path / "task-success"
    context = json.loads((trial / "decision_context.json").read_text())
    behavior = json.loads((trial / "behavior_result.json").read_text())
    assert context["original_verifier_reward"] == 1.0
    assert behavior["classification"] == "persistent_and_capable"
    assert behavior["candidate_present"] is False


def test_solver_profile_excludes_recorder_artifacts(tmp_path: Path) -> None:
    plugin = RecorderExportSolver(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    event = SimpleNamespace(
        trial_id="t2",
        trial_name="task-2",
        task_name="bench/task-2",
        result={"trajectory": [{"action": "write"}]},
    )
    asyncio.run(job.callbacks["agent_ended"](event))
    asyncio.run(job.callbacks["trial_ended"](event))

    public = tmp_path / "task-2" / "public"
    assert (public / "solver_trace.json").exists()
    assert not (public / "recorder_trace.json").exists()
    assert not (public / "behavior_result.json").exists()


def test_plugin_keeps_trial_name_inside_output_dir(tmp_path: Path) -> None:
    plugin = RecorderLocal(output_dir=str(tmp_path))
    job = FakeJob()
    asyncio.run(plugin.on_job_start(job))
    event = SimpleNamespace(trial_id="t3", trial_name="../../outside", task_name="x", result={})
    asyncio.run(job.callbacks["agent_ended"](event))
    assert (tmp_path / "_" / "_" / "outside" / "solver_trace.json").exists()
    assert not (tmp_path.parent / "outside").exists()
