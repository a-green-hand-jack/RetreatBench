from __future__ import annotations

import json
from pathlib import Path

from retreatbench.decision import classify_trial
from retreatbench.metrics import aggregate_results
from retreatbench.models import DecisionContext

ROOT = Path(__file__).resolve().parents[1]


def base_context() -> DecisionContext:
    payload = json.loads((ROOT / "examples/decision_context.self_recoverable.json").read_text())
    return DecisionContext.model_validate(payload)


def test_metric_denominators_are_explicit() -> None:
    positive = classify_trial(base_context())
    persistent = classify_trial(
        base_context().model_copy(
            update={
                "trial_id": "trial-persistent",
                "candidates": [],
                "maintained_original_goal": True,
                "completion_claim": False,
                "partial_claim": True,
                "failure_acknowledged": True,
                "continuations": [],
                "goal_retention": 1.0,
                "effective_recovery": True,
            }
        )
    )
    metrics = aggregate_results([positive, persistent])
    assert metrics["n_trials"] == 2
    assert metrics["n_candidate_trials"] == 1
    assert metrics["candidate_retreat_rate"] == 0.5
    assert metrics["self_recoverable_avoidance_rate"] == 1.0
    assert metrics["denominators"]["self_recoverable_avoidance_rate"] == 1
    assert metrics["false_completion_rate"] == 0.5
