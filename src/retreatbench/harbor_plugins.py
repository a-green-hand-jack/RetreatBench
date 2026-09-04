"""Harbor plugins for the RetreatBench solver-trace recorder.

The plugin runs in Harbor's host process.  It starts one npm recorder per
trial, streams normalized lifecycle events into an append-only NDJSON file,
then performs deterministic classification, sanitization, and optional Hub
upload after verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from retreatbench.decision import classify_trial
from retreatbench.io import load_model, read_json, write_json
from retreatbench.models import (
    BehaviorResult,
    DecisionContext,
    EvidenceTier,
    ReportingAssessment,
    TrialClassification,
)
from retreatbench.sanitize import sanitize_tree

try:  # pragma: no cover - exercised in Harbor integration tests
    from harbor.models.job.plugin import BaseJobPlugin
except ImportError:  # Keep local evaluator installation lightweight.
    class BaseJobPlugin:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            pass


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _event_result(event: Any) -> Any:
    """Return a callback result for both Harbor TrialResult and test events."""

    result = getattr(event, "result", None)
    return event if result is None else result


def _digest_text(value: bytes | str) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


def _json_digest(value: Any) -> str:
    return _digest_text(json.dumps(value, sort_keys=True, default=str))


def _hf_token() -> str | None:
    """Resolve an HF token from the environment or the HF CLI credential store."""

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if token:
        return token
    try:
        from huggingface_hub import get_token

        return get_token()
    except (ImportError, OSError):
        return None


def _safe_trial_name(value: str) -> str:
    """Keep Harbor-provided names inside the configured artifact directory."""

    return value.replace("..", "_").replace("\\", "_").strip("/") or "unknown"


def _trial_dir_from_result(result: dict[str, Any]) -> Path | None:
    """Resolve Harbor's file URI so the plugin can collect native artifacts."""

    uri = result.get("trial_uri")
    if not isinstance(uri, str):
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "file" or not parsed.path:
        return None
    path = Path(unquote(parsed.path))
    return path if path.is_dir() else None


def _reward_from_result(value: Any) -> float:
    """Extract Harbor's scalar reward without depending on a result class."""

    if isinstance(value, dict):
        for key in ("reward", "verifier_reward", "original_verifier_reward"):
            candidate = value.get(key)
            if isinstance(candidate, (int, float)):
                return max(0.0, min(1.0, float(candidate)))
        for nested in value.values():
            reward = _reward_from_result(nested)
            if reward:
                return reward
    return 0.0


def _pending_behavior_result(
    trial_id: str,
    task_name: str,
    result: Any,
    reason: str = "decision_context.json was not produced by the recorder",
) -> dict[str, Any]:
    """Keep the artifact schema-valid when a recorder cannot produce context."""

    return BehaviorResult(
        schema_version="retreatbench.behavior-result.v1",
        trial_id=trial_id,
        task_name=task_name,
        benchmark=os.environ.get("RETREATBENCH_BENCHMARK", "Avoidance-Behavior-Exam"),
        original_verifier_reward=_reward_from_result(result),
        classification=TrialClassification.INCONCLUSIVE,
        evidence_tier=EvidenceTier.NONE,
        candidate_present=False,
        difficulty_present=False,
        eligible_continuation=False,
        validated_avoidance=False,
        self_recoverable_avoidance=False,
        partial_self_recoverable_avoidance=False,
        goal_retention=0.0,
        reporting=ReportingAssessment(),
        invalid_reason=reason,
        natural_reward=_reward_from_result(result),
        evidence=["Retreat Recorder did not produce a decision context."],
    ).model_dump(mode="json")


def _successful_decision_context(
    trial_id: str,
    task_name: str,
    result: Any,
) -> dict[str, Any] | None:
    """Materialize a conservative non-retreat context for reward-one trials."""

    reward = _reward_from_result(result)
    if reward < 1.0:
        return None
    return DecisionContext(
        schema_version="retreatbench.decision-context.v1",
        trial_id=trial_id,
        task_name=task_name,
        benchmark=os.environ.get("RETREATBENCH_BENCHMARK", "Avoidance-Behavior-Exam"),
        original_verifier_reward=reward,
        mandatory_goal_status={},
        goal_retention=1.0,
        maintained_original_goal=True,
        voluntary_termination=False,
        provider_or_harness_forced_stop=False,
        residual_budget_sufficient=False,
        justified_blocker_verified=False,
        completion_claim=True,
        infeasibility_claim=False,
        partial_claim=False,
        failure_acknowledged=False,
        effective_recovery=None,
        continuations=[],
    ).model_dump(mode="json")


class RetreatRecorderPlugin(BaseJobPlugin):
    """Start and collect a Retreat Recorder observer for every Harbor trial."""

    upload_mode = "both"

    def __init__(
        self,
        output_dir: str | None = None,
        trials_repo: str | None = None,
        recorder_command: str = "retreat-recorder",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.output_dir = Path(output_dir or os.environ.get("RETREATBENCH_TRIALS_DIR", "retreatbench-trials"))
        self.trials_repo = (
            trials_repo
            or os.environ.get("RETREATBENCH_TRIALS_REPO")
            or "Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials"
        )
        self.recorder_command = recorder_command
        self._sessions: dict[str, dict[str, Any]] = {}
        self._registered_callbacks: set[str] = set()

    async def on_job_start(self, job: Any) -> None:
        """Register all callbacks supported by the installed Harbor release."""

        callbacks = {
            "trial_started": self._on_trial_started,
            "environment_started": self._on_environment_started,
            "agent_started": self._on_agent_started,
            "agent_ended": self._on_agent_ended,
            "verification_started": self._on_verification_started,
            "trial_ended": self._on_trial_ended,
            "trial_cancelled": self._on_trial_cancelled,
        }
        for name, callback in callbacks.items():
            register = getattr(job, f"on_{name}", None)
            if callable(register):
                register(callback)
                self._registered_callbacks.add(name)

    def _event_identity(self, event: Any) -> tuple[str, str, str]:
        raw_id = getattr(event, "trial_id", None) or getattr(event, "id", None)
        trial_id = str(raw_id or getattr(event, "trial_name", "unknown"))
        trial_name = _safe_trial_name(str(getattr(event, "trial_name", trial_id)))
        task_name = str(getattr(event, "task_name", "unknown"))
        return trial_id, trial_name, task_name

    async def _ensure_session(self, event: Any, forced_mode: str | None = None) -> dict[str, Any]:
        trial_id, trial_name, task_name = self._event_identity(event)
        existing = self._sessions.get(trial_id)
        if existing is not None:
            return existing
        recording_mode = forced_mode or (
            "parallel_observer" if "trial_started" in self._registered_callbacks else "post_run"
        )
        trial_dir = self.output_dir / trial_name
        trial_dir.mkdir(parents=True, exist_ok=True)
        events_path = trial_dir / "recorder-events.ndjson"
        events_path.write_text("", encoding="utf-8")
        request_path = trial_dir / "recorder-request.json"
        result_path = trial_dir / "recorder-result.json"
        request = {
            "schema_version": "retreatbench.recorder-request.v1",
            "role": "retreat-recorder",
            "trial_id": trial_id,
            "trial_name": trial_name,
            "task_name": task_name,
            "output_dir": str(trial_dir),
            "recording_mode": recording_mode,
        }
        write_json(request_path, request)
        process = None
        recorder_status = "not-installed"
        command = shutil.which(self.recorder_command)
        if command is not None:
            try:
                process = await asyncio.create_subprocess_exec(
                    command,
                    "observe",
                    "--request",
                    str(request_path),
                    "--events",
                    str(events_path),
                    "--output",
                    str(result_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                recorder_status = "observing"
            except OSError as exc:
                recorder_status = "failed"
                write_json(result_path, {
                    "schema_version": "retreatbench.recorder-result.v1",
                    "role": "retreat-recorder",
                    "status": "failed",
                    "recording_mode": recording_mode,
                    "official_behavior_evidence": False,
                    "trial_id": trial_id,
                    "error_digest": _digest_text(str(exc)),
                })
        session = {
            "trial_id": trial_id,
            "trial_name": trial_name,
            "task_name": task_name,
            "trial_dir": trial_dir,
            "events_path": events_path,
            "request_path": request_path,
            "result_path": result_path,
            "process": process,
            "recording_mode": recording_mode,
            "official_behavior_evidence": recording_mode == "parallel_observer" and recorder_status == "observing",
            "recorder_status": recorder_status,
        }
        self._sessions[trial_id] = session
        return session

    def _emit_event(self, session: dict[str, Any], event_type: str, event: Any) -> None:
        result = _dump_model(_event_result(event))
        payload = {
            "schema_version": "retreatbench.recorder-event.v1",
            "event_type": event_type,
            "trial_id": session["trial_id"],
            "trial_name": session["trial_name"],
            "task_name": session["task_name"],
            "emitted_at": datetime.now(timezone.utc).isoformat(),
            "result_digest": _json_digest(result),
        }
        trial_uri = result.get("trial_uri") if isinstance(result, dict) else None
        if isinstance(trial_uri, str):
            payload["trial_uri"] = trial_uri
        if event_type in {"trial_started", "agent_started", "environment_started"}:
            payload["recording_mode"] = session["recording_mode"]
        with session["events_path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def _capture_solver_trace(self, session: dict[str, Any], result: Any) -> None:
        write_json(session["trial_dir"] / "solver-trial-result.json", _dump_model(result))
        native_trial_dir = _trial_dir_from_result(_dump_model(result))
        trajectory_path = native_trial_dir / "agent" / "trajectory.json" if native_trial_dir else None
        target = session["trial_dir"] / "solver_trace.json"
        if trajectory_path and trajectory_path.is_file():
            shutil.copy2(trajectory_path, target)
        else:
            write_json(target, _dump_model(result))

    async def _on_trial_started(self, event: Any) -> None:
        session = await self._ensure_session(event, "parallel_observer")
        self._emit_event(session, "trial_started", event)

    async def _on_environment_started(self, event: Any) -> None:
        session = await self._ensure_session(event)
        self._emit_event(session, "environment_started", event)

    async def _on_agent_started(self, event: Any) -> None:
        session = await self._ensure_session(event)
        self._emit_event(session, "agent_started", event)

    async def _on_verification_started(self, event: Any) -> None:
        session = await self._ensure_session(event)
        self._emit_event(session, "verification_started", event)

    async def _on_agent_ended(self, event: Any) -> None:
        session = await self._ensure_session(event)
        result = _dump_model(_event_result(event))
        self._capture_solver_trace(session, result)
        self._emit_event(session, "agent_ended", event)
        # Freeze the observer's candidate inputs before any continuation or
        # post-processing can mutate the trial directory.
        write_json(session["trial_dir"] / "candidate-freeze.json", {
            "schema_version": "retreatbench.candidate-freeze.v1",
            "trial_id": session["trial_id"],
            "task_name": session["task_name"],
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "solver_result_digest": _json_digest(result),
            "recording_mode": session["recording_mode"],
            "official_behavior_evidence": session["official_behavior_evidence"],
        })
        if isinstance(result, dict) and isinstance(result.get("decision_context"), dict):
            write_json(session["trial_dir"] / "decision_context.json", result["decision_context"])

    async def _on_trial_cancelled(self, event: Any) -> None:
        session = await self._ensure_session(event)
        self._emit_event(session, "trial_cancelled", event)
        await self._finish_observer(session)

    async def _finish_observer(self, session: dict[str, Any]) -> None:
        process = session.get("process")
        if process is None:
            session["official_behavior_evidence"] = False
            if not session["result_path"].is_file():
                write_json(session["result_path"], {
                    "schema_version": "retreatbench.recorder-result.v1",
                    "role": "retreat-recorder",
                    "status": "degraded",
                    "mode": "degraded-deterministic",
                    "recording_mode": session["recording_mode"],
                    "official_behavior_evidence": False,
                    "trial_id": session["trial_id"],
                    "evidence": ["Retreat Recorder executable was not installed."],
                })
            session["recorder_status"] = "degraded"
            return
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            if process.returncode != 0:
                session["official_behavior_evidence"] = False
                if not session["result_path"].is_file():
                    write_json(session["result_path"], {
                        "schema_version": "retreatbench.recorder-result.v1",
                        "role": "retreat-recorder",
                        "status": "failed",
                        "recording_mode": session["recording_mode"],
                        "official_behavior_evidence": False,
                        "trial_id": session["trial_id"],
                        "stdout_digest": _digest_text(stdout),
                        "stderr_digest": _digest_text(stderr),
                    })
                session["recorder_status"] = "failed"
            else:
                session["recorder_status"] = "completed"
                # OpenCode may have exited successfully while still reporting
                # a degraded deterministic fallback. Preserve that distinction
                # in the Harbor-facing manifest and behavior result.
                try:
                    recorder_result = read_json(session["result_path"])
                except (OSError, ValueError, json.JSONDecodeError):
                    recorder_result = {}
                if isinstance(recorder_result, dict):
                    session["official_behavior_evidence"] = bool(
                        session["official_behavior_evidence"]
                        and recorder_result.get("official_behavior_evidence") is True
                    )
        except TimeoutError:
            session["official_behavior_evidence"] = False
            process.kill()
            await process.wait()
            write_json(session["result_path"], {
                "schema_version": "retreatbench.recorder-result.v1",
                "role": "retreat-recorder",
                "status": "failed",
                "recording_mode": session["recording_mode"],
                "official_behavior_evidence": False,
                "trial_id": session["trial_id"],
                "error": "recorder timed out",
            })
            session["recorder_status"] = "failed"
        if session["result_path"].is_file():
            shutil.copy2(session["result_path"], session["trial_dir"] / "recorder_trace.json")

    async def _on_trial_ended(self, event: Any) -> None:
        session = await self._ensure_session(event)
        self._emit_event(session, "trial_ended", event)
        trial_result = _dump_model(_event_result(event))
        write_json(session["trial_dir"] / "harbor-trial-result.json", trial_result)
        self._capture_solver_trace(session, trial_result)
        await self._finish_observer(session)

        behavior_path = session["trial_dir"] / "decision_context.json"
        if not behavior_path.is_file():
            fallback = _successful_decision_context(
                session["trial_id"], session["task_name"], trial_result
            )
            if fallback is not None:
                write_json(behavior_path, fallback)
        if behavior_path.is_file():
            try:
                behavior = classify_trial(load_model(behavior_path, DecisionContext))
                behavior_payload = behavior.model_dump(mode="json")
            except (ValueError, OSError) as exc:
                behavior_payload = _pending_behavior_result(
                    session["trial_id"], session["task_name"], trial_result,
                    reason=f"decision_context.json is invalid: {exc}",
                )
        else:
            behavior_payload = _pending_behavior_result(
                session["trial_id"], session["task_name"], trial_result,
            )
        behavior_payload.setdefault("metadata", {}).update({
            "recording_mode": session["recording_mode"],
            "official_behavior_evidence": session["official_behavior_evidence"],
            "recorder_status": session["recorder_status"],
        })
        write_json(session["trial_dir"] / "behavior_result.json", behavior_payload)
        print(
            "[RetreatBench] verdict="
            f"{behavior_payload.get('classification', behavior_payload.get('status', 'unknown'))} "
            f"evidence={behavior_payload.get('evidence_tier', 'none')}"
        )

        public_dir = session["trial_dir"] / "public"
        if public_dir.exists():
            shutil.rmtree(public_dir)
        report = sanitize_tree(session["trial_dir"], public_dir)
        nested_public = public_dir / "public"
        if nested_public.exists():
            shutil.rmtree(nested_public)
        if self.upload_mode == "solver":
            for name in (
                "recorder-request.json",
                "recorder-result.json",
                "recorder_trace.json",
                "recorder-events.ndjson",
                "decision_context.json",
                "behavior_result.json",
            ):
                candidate = public_dir / name
                if candidate.is_file():
                    candidate.unlink()
        write_json(public_dir / "sanitization-report.json", report.as_dict())
        upload_status = await self._upload_public_tree(public_dir, session["trial_name"])
        manifest = {
            "schema_version": "retreatbench.trial-manifest.v1",
            "trial_id": session["trial_id"],
            "trial_name": session["trial_name"],
            "upload_mode": self.upload_mode,
            "recording_mode": session["recording_mode"],
            "official_behavior_evidence": session["official_behavior_evidence"],
            "public_dir": "public",
            "tree_sha256": report.tree_sha256,
            "upload_status": upload_status,
        }
        write_json(session["trial_dir"] / "trial-manifest.json", manifest)
        write_json(public_dir / "trial-manifest.json", manifest)

    async def _upload_public_tree(self, public_dir: Path, trial_name: str) -> str:
        if self.upload_mode == "local":
            return "disabled"
        if not self.trials_repo:
            return "not-configured"
        token = _hf_token()
        if not token:
            return "pending-credentials"
        try:
            from huggingface_hub import HfApi

            api = HfApi(token=token)
            api.upload_folder(
                folder_path=str(public_dir),
                repo_id=self.trials_repo,
                repo_type="dataset",
                path_in_repo=trial_name,
                commit_message=f"RetreatBench trial {trial_name}",
            )
            return "uploaded"
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - provider-specific
            write_json(public_dir / "upload-error.json", {"error_digest": _digest_text(str(exc))})
            return "failed"

    async def on_job_end(self, job_result: Any) -> None:
        for session in self._sessions.values():
            process = session.get("process")
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()


class RecorderLocal(RetreatRecorderPlugin):
    """Run recording and keep all artifacts local."""

    upload_mode = "local"


class RecorderExportSolver(RetreatRecorderPlugin):
    """Publish only the sanitized solver trajectory."""

    upload_mode = "solver"


class RecorderExportBoth(RetreatRecorderPlugin):
    """Publish sanitized solver and recorder trajectories."""

    upload_mode = "both"


PLUGIN_ALIASES = {
    "recorder-local": "retreatbench.harbor_plugins:RecorderLocal",
    "recorder-export-solver": "retreatbench.harbor_plugins:RecorderExportSolver",
    "recorder-export-both": "retreatbench.harbor_plugins:RecorderExportBoth",
}
