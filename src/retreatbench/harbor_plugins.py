"""Harbor lifecycle plugins for the RetreatBench sidecar evaluator.

The Harbor dependency is optional at import time so the core evaluator and its
tests remain usable without installing Harbor.  When Harbor is present these
classes implement the documented ``BaseJobPlugin`` contract and register trial
callbacks for the natural run and final artifact export.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from retreatbench.decision import classify_trial
from retreatbench.io import load_model, write_json
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


def _digest_text(value: bytes | str) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


def _safe_trial_name(value: str) -> str:
    """Keep Harbor-provided names inside the configured artifact directory."""

    return value.replace("..", "_").replace("\\", "_").strip("/") or "unknown"


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
    reason: str = "decision_context.json was not produced by the auditor",
) -> dict[str, Any]:
    """Keep the artifact schema-valid when a detector cannot produce context."""

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
        evidence=["Retreat Auditor did not produce a decision context."],
    ).model_dump(mode="json")


class RetreatAuditorPlugin(BaseJobPlugin):
    """Start and collect a Retreat Auditor sidecar for every Harbor trial."""

    upload_mode = "both"

    def __init__(
        self,
        output_dir: str | None = None,
        trials_repo: str | None = None,
        auditor_command: str = "retreat-auditor",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.output_dir = Path(output_dir or os.environ.get("RETREATBENCH_TRIALS_DIR", "retreatbench-trials"))
        self.trials_repo = (
            trials_repo
            or os.environ.get("RETREATBENCH_TRIALS_REPO")
            or "Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials"
        )
        self.auditor_command = auditor_command
        self._trial_dirs: dict[str, Path] = {}

    async def on_job_start(self, job: Any) -> None:
        """Register lifecycle hooks; Harbor invokes callbacks in order."""

        job.on_agent_ended(self._on_agent_ended)
        job.on_trial_ended(self._on_trial_ended)

    async def _on_agent_ended(self, event: Any) -> None:
        trial_id = str(getattr(event, "trial_id", "unknown"))
        trial_name = _safe_trial_name(str(getattr(event, "trial_name", trial_id)))
        trial_dir = self.output_dir / trial_name
        trial_dir.mkdir(parents=True, exist_ok=True)
        self._trial_dirs[trial_id] = trial_dir

        result = _dump_model(getattr(event, "result", {}))
        write_json(trial_dir / "performer-trial-result.json", result)
        write_json(trial_dir / "performer_trace.json", result)
        if isinstance(result, dict) and isinstance(result.get("decision_context"), dict):
            write_json(trial_dir / "decision_context.json", result["decision_context"])
        request = {
            "schema_version": "retreatbench.auditor-request.v1",
            "role": "retreat-auditor",
            "trial_id": trial_id,
            "task_name": str(getattr(event, "task_name", "unknown")),
            "performer_result": result,
            "output_dir": str(trial_dir),
        }
        request_path = trial_dir / "auditor-request.json"
        write_json(request_path, request)
        sidecar_result = trial_dir / "auditor-result.json"
        command = shutil.which(self.auditor_command)
        if command is None:
            write_json(sidecar_result, {"status": "not-installed", "request": str(request_path)})
            write_json(trial_dir / "auditor_trace.json", {"status": "not-installed"})
            return
        try:
            process = await asyncio.create_subprocess_exec(
                command,
                "sidecar",
                "--input",
                str(request_path),
                "--output",
                str(sidecar_result),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            if process.returncode != 0:
                write_json(
                    sidecar_result,
                    {
                        "status": "failed",
                        "returncode": process.returncode,
                        "stdout_digest": _digest_text(stdout),
                        "stderr_digest": _digest_text(stderr),
                    },
                )
            if sidecar_result.is_file():
                shutil.copy2(sidecar_result, trial_dir / "auditor_trace.json")
        except TimeoutError:
            process.kill()
            await process.wait()
            write_json(sidecar_result, {"status": "failed", "error": "auditor timed out"})
            write_json(trial_dir / "auditor_trace.json", {"status": "failed", "error": "auditor timed out"})
        except OSError as exc:
            error_digest = _digest_text(str(exc))
            write_json(sidecar_result, {"status": "failed", "error_digest": error_digest})
            write_json(
                trial_dir / "auditor_trace.json",
                {"status": "failed", "error_digest": error_digest},
            )

    async def _on_trial_ended(self, event: Any) -> None:
        trial_id = str(getattr(event, "trial_id", "unknown"))
        trial_name = _safe_trial_name(str(getattr(event, "trial_name", trial_id)))
        source = self._trial_dirs.get(trial_id, self.output_dir / trial_name)
        source.mkdir(parents=True, exist_ok=True)
        write_json(source / "harbor-trial-result.json", _dump_model(getattr(event, "result", {})))

        behavior_path = source / "decision_context.json"
        if behavior_path.is_file():
            try:
                behavior = classify_trial(load_model(behavior_path, DecisionContext))
                write_json(source / "behavior_result.json", behavior.model_dump(mode="json"))
                behavior_payload = behavior.model_dump(mode="json")
            except (ValueError, OSError) as exc:
                behavior_payload = _pending_behavior_result(
                    trial_id,
                    trial_name,
                    getattr(event, "result", {}),
                    reason=f"decision_context.json is invalid: {exc}",
                )
                write_json(source / "behavior_result.json", behavior_payload)
        else:
            behavior_payload = _pending_behavior_result(trial_id, trial_name, getattr(event, "result", {}))
            write_json(source / "behavior_result.json", behavior_payload)
        print(
            "[RetreatBench] verdict="
            f"{behavior_payload.get('classification', behavior_payload.get('status', 'unknown'))} "
            f"evidence={behavior_payload.get('evidence_tier', 'none')}"
        )
        public_dir = source / "public"
        if public_dir.exists():
            shutil.rmtree(public_dir)
        report = sanitize_tree(source, public_dir)
        # The public copy must never contain another public copy or the raw
        # sanitizer report generated while traversing the source tree.
        nested_public = public_dir / "public"
        if nested_public.exists():
            shutil.rmtree(nested_public)
        if self.upload_mode == "performer":
            # The performer-only profile must not disclose the detector's
            # private reasoning or its normalized auditor trail.
            for name in (
                "auditor-request.json",
                "auditor-result.json",
                "auditor_trace.json",
                "decision_context.json",
                "behavior_result.json",
            ):
                candidate = public_dir / name
                if candidate.is_file():
                    candidate.unlink()
        write_json(public_dir / "sanitization-report.json", report.as_dict())
        upload_status = await self._upload_public_tree(public_dir, trial_name)
        manifest = {
            "schema_version": "retreatbench.trial-manifest.v1",
            "trial_id": trial_id,
            "trial_name": trial_name,
            "upload_mode": self.upload_mode,
            "public_dir": "public",
            "tree_sha256": report.tree_sha256,
            "upload_status": upload_status,
        }
        write_json(source / "retreatbench-trial-manifest.json", manifest)
        write_json(public_dir / "retreatbench-trial-manifest.json", manifest)

    async def _upload_public_tree(self, public_dir: Path, trial_name: str) -> str:
        if self.upload_mode == "local":
            return "disabled"
        if not self.trials_repo:
            return "not-configured"
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
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
        return None


class AvoidanceLocal(RetreatAuditorPlugin):
    """Run detection and keep all artifacts local."""

    upload_mode = "local"


class AvoidanceExportPerformer(RetreatAuditorPlugin):
    """Publish only the sanitized Task Performer trajectory."""

    upload_mode = "performer"


class AvoidanceExportBoth(RetreatAuditorPlugin):
    """Publish sanitized Task Performer and Retreat Auditor trajectories."""

    upload_mode = "both"


PLUGIN_ALIASES = {
    "avoidance-local": "retreatbench.harbor_plugins:AvoidanceLocal",
    "avoidance-export-performer": "retreatbench.harbor_plugins:AvoidanceExportPerformer",
    "avoidance-export-both": "retreatbench.harbor_plugins:AvoidanceExportBoth",
}
