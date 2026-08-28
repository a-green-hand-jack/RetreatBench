from __future__ import annotations

import json
from pathlib import Path

from retreatbench.decision import classify_trial
from retreatbench.models import BehaviorResult, DecisionContext

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_behavior_result_matches_classifier() -> None:
    context = DecisionContext.model_validate_json(
        (ROOT / "examples/decision_context.self_recoverable.json").read_text()
    )
    expected = BehaviorResult.model_validate_json(
        (ROOT / "examples/behavior_result.self_recoverable.json").read_text()
    )
    assert classify_trial(context) == expected
