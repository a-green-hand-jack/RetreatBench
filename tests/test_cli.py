from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from retreatbench.cli import app

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_validate_command() -> None:
    result = runner.invoke(app, ["validate", str(ROOT / "examples/goal_contract.example.json")])
    assert result.exit_code == 0
    assert "retreatbench.goal-contract.v1" in result.stdout


def test_validate_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps({"schema_version": "unknown"}), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert "unsupported or missing schema_version" in result.stderr


def test_classify_to_stdout() -> None:
    result = runner.invoke(
        app,
        ["classify", str(ROOT / "examples/decision_context.self_recoverable.json")],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["classification"] == "self_recoverable_avoidance"


def test_classify_to_file(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "classify",
            str(ROOT / "examples/decision_context.self_recoverable.json"),
            "--output",
            str(output),
            "--partial-progress-threshold",
            "0.2",
        ],
    )
    assert result.exit_code == 0
    assert output.exists()
    assert json.loads(output.read_text())["evidence_tier"] == "A-self-recoverable"


def test_aggregate_to_stdout() -> None:
    result = runner.invoke(
        app,
        ["aggregate", str(ROOT / "examples/behavior_results.example.jsonl")],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["n_trials"] == 4
    assert payload["n_invalid_trials"] == 1


def test_aggregate_to_file(tmp_path: Path) -> None:
    output = tmp_path / "metrics.json"
    result = runner.invoke(
        app,
        [
            "aggregate",
            str(ROOT / "examples/behavior_results.example.jsonl"),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert output.exists()


def test_snapshot_and_verify_state_commands(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "output.txt").write_text("ok", encoding="utf-8")
    snapshot = tmp_path / "snapshot"
    result = runner.invoke(app, ["snapshot-state", str(root), str(snapshot)])
    assert result.exit_code == 0
    result = runner.invoke(app, ["verify-state", str(root), str(snapshot / "state_manifest.json")])
    assert result.exit_code == 0
    restored = tmp_path / "restored"
    result = runner.invoke(app, ["restore-state", str(snapshot), str(restored)])
    assert result.exit_code == 0
