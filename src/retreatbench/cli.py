from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from retreatbench import __version__
from retreatbench.decision import classify_trial
from retreatbench.detect import (
    DEFAULT_ARBITER_MODEL,
    DEFAULT_JUDGE_A_MODEL,
    DEFAULT_JUDGE_B_MODEL,
    DEFAULT_TIMEOUT_SEC,
    DetectError,
    assemble_decision_context,
    run_diagnose_team,
)
from retreatbench.io import load_model, read_json, read_jsonl, write_json
from retreatbench.metrics import aggregate_results
from retreatbench.models import BehaviorResult, DecisionContext, GoalContract
from retreatbench.state import StateError, capture_state, restore_state, verify_manifest

app = typer.Typer(
    name="retreatbench",
    no_args_is_help=True,
    help="Validate, classify, and aggregate RetreatBench behavioral evidence.",
)


def _detect_model(data: dict[str, object]) -> type[GoalContract] | type[DecisionContext] | type[BehaviorResult]:
    schema_version = data.get("schema_version")
    mapping = {
        "retreatbench.goal-contract.v1": GoalContract,
        "retreatbench.decision-context.v1": DecisionContext,
        "retreatbench.behavior-result.v1": BehaviorResult,
    }
    try:
        return mapping[str(schema_version)]
    except KeyError as exc:
        raise ValueError(f"unsupported or missing schema_version: {schema_version!r}") from exc


@app.command()
def version() -> None:
    """Print the RetreatBench package version."""

    typer.echo(__version__)


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a goal contract, decision context, or behavior result JSON file."""

    try:
        data = read_json(path)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value must be an object")
        model = _detect_model(data)
        model.model_validate(data)
    except (ValueError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"valid: {path} ({data['schema_version']})")


@app.command()
def classify(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    partial_progress_threshold: Annotated[
        float, typer.Option(min=0.0, max=1.0)
    ] = 0.10,
) -> None:
    """Apply deterministic counterfactual classification to a decision context."""

    try:
        context = load_model(path, DecisionContext)
        result = classify_trial(context, partial_progress_threshold=partial_progress_threshold)
    except (ValueError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    payload = result.model_dump(mode="json")
    if output is not None:
        write_json(output, payload)
        typer.echo(f"wrote: {output}")
    else:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@app.command()
def aggregate(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Aggregate behavior-result JSONL with explicit metric denominators."""

    try:
        results = [BehaviorResult.model_validate(record) for record in read_jsonl(path)]
        metrics = aggregate_results(results)
    except (ValueError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if output is not None:
        write_json(output, metrics)
        typer.echo(f"wrote: {output}")
    else:
        typer.echo(json.dumps(metrics, indent=2, ensure_ascii=False))


@app.command("snapshot-state")
def snapshot_state(
    root: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    output_dir: Annotated[Path, typer.Argument(file_okay=False)],
    exclude: Annotated[list[str] | None, typer.Option("--exclude")] = None,
) -> None:
    """Capture a workspace tree and write a hash-verified state snapshot."""

    try:
        snapshot = capture_state(root, output_dir, excluded=exclude or [])
    except StateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote: {snapshot.archive}")
    typer.echo(f"manifest: {output_dir / 'state_manifest.json'}")


@app.command("verify-state")
def verify_state(
    root: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Verify a workspace tree against a captured state manifest."""

    try:
        payload = read_json(manifest)
        if not isinstance(payload, dict):
            raise StateError("state manifest must be a JSON object")
        verify_manifest(root, payload)
    except (StateError, ValueError, tarfile.TarError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"verified: {root} ({payload['tree_sha256']})")


@app.command()
def detect(
    evidence_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    goal_contract: Annotated[Path, typer.Option("--goal-contract", exists=True, dir_okay=False, readable=True)],
    out_dir: Annotated[Path, typer.Option("--out-dir")],
    trial_id: Annotated[str, typer.Option("--trial-id")],
    task_name: Annotated[str, typer.Option("--task-name")],
    benchmark: Annotated[str, typer.Option("--benchmark")],
    original_verifier_reward: Annotated[float, typer.Option("--original-verifier-reward", min=0.0, max=1.0)],
    judge_a_model: Annotated[str, typer.Option("--judge-a-model")] = DEFAULT_JUDGE_A_MODEL,
    judge_b_model: Annotated[str, typer.Option("--judge-b-model")] = DEFAULT_JUDGE_B_MODEL,
    arbiter_model: Annotated[str, typer.Option("--arbiter-model")] = DEFAULT_ARBITER_MODEL,
    env_file: Annotated[Path | None, typer.Option("--env-file", exists=True, dir_okay=False, readable=True)] = None,
    timeout_sec: Annotated[float, typer.Option("--timeout-sec", min=1.0)] = DEFAULT_TIMEOUT_SEC,
    detector_label: Annotated[str, typer.Option("--detector-label")] = "retreatbench-detect-v1",
) -> None:
    """Run the double-blind judge + arbiter detector and write a validated decision_context.json.

    One command, analogous to `harbor run`: independently prompts two judges against the
    evidence directory and the private goal contract, arbitrates on disagreement with a
    de-identified stronger model, and assembles the frozen verdict into a schema-valid
    decision_context.json under --out-dir. Credentials for the judge/arbiter calls come from
    --env-file (KEY=VALUE lines loaded into the judge subprocess environment only, never
    printed or merged into this process's own environment) -- point it at any local secrets
    file with OPENAI_API_KEY/OPENAI_BASE_URL and ANTHROPIC_API_KEY/ANTHROPIC_BASE_URL.
    """

    try:
        verdict = run_diagnose_team(
            evidence_dir=evidence_dir,
            goal_contract_path=goal_contract,
            out_dir=out_dir,
            judge_a_model=judge_a_model,
            judge_b_model=judge_b_model,
            arbiter_model=arbiter_model,
            env_file=env_file,
            timeout_sec=timeout_sec,
        )
        context = assemble_decision_context(
            verdict,
            trial_id=trial_id,
            task_name=task_name,
            benchmark=benchmark,
            original_verifier_reward=original_verifier_reward,
            detector_label=detector_label,
        )
    except (DetectError, ValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    context_path = out_dir / "decision_context.json"
    write_json(context_path, context.model_dump(mode="json"))
    typer.echo(f"wrote: {context_path}")


@app.command("restore-state")
def restore_state_command(
    snapshot_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    destination: Annotated[Path, typer.Argument(file_okay=False)],
) -> None:
    """Restore a verified state snapshot into an empty directory."""

    try:
        restore_state(snapshot_dir, destination)
    except (StateError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"restored: {destination}")


if __name__ == "__main__":
    app()
