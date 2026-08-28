from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from retreatbench.models import GoalContract

ROOT = Path(__file__).resolve().parents[1]


def test_example_goal_contract_validates() -> None:
    payload = json.loads((ROOT / "examples/goal_contract.example.json").read_text())
    contract = GoalContract.model_validate(payload)
    assert contract.task_name == "terminal-bench/example-task"
    assert len(contract.goals) == 2


def test_duplicate_goal_ids_are_rejected() -> None:
    payload = json.loads((ROOT / "examples/goal_contract.example.json").read_text())
    payload["goals"][1]["id"] = payload["goals"][0]["id"]
    with pytest.raises(ValidationError, match="goal IDs must be unique"):
        GoalContract.model_validate(payload)


def test_relative_workspace_root_is_rejected() -> None:
    payload = json.loads((ROOT / "examples/goal_contract.example.json").read_text())
    payload["workspace_roots"] = ["workspace"]
    with pytest.raises(ValidationError, match="absolute paths"):
        GoalContract.model_validate(payload)
