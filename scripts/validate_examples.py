#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retreatbench.decision import classify_trial  # noqa: E402
from retreatbench.io import read_json, read_jsonl  # noqa: E402
from retreatbench.metrics import aggregate_results  # noqa: E402
from retreatbench.models import BehaviorResult, DecisionContext, GoalContract  # noqa: E402


def main() -> int:
    GoalContract.model_validate(read_json(ROOT / "examples/goal_contract.example.json"))
    context = DecisionContext.model_validate(
        read_json(ROOT / "examples/decision_context.self_recoverable.json")
    )
    result = classify_trial(context)
    expected = BehaviorResult.model_validate(
        read_json(ROOT / "examples/behavior_result.self_recoverable.json")
    )
    if result.model_dump(mode="json") != expected.model_dump(mode="json"):
        print("classified result differs from checked-in example", file=sys.stderr)
        print(json.dumps(result.model_dump(mode="json"), indent=2), file=sys.stderr)
        return 1
    records = [BehaviorResult.model_validate(row) for row in read_jsonl(ROOT / "examples/behavior_results.example.jsonl")]
    aggregate_results(records)
    print("all examples valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
