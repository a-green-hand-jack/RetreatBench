from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from retreatbench import __version__
from retreatbench.decision import classify_trial
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
