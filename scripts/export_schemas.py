#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from retreatbench.models import BehaviorResult, DecisionContext, GoalContract  # noqa: E402

SCHEMAS = {
    "goal_contract.schema.json": GoalContract.model_json_schema(),
    "decision_context.schema.json": DecisionContext.model_json_schema(),
    "behavior_result.schema.json": BehaviorResult.model_json_schema(),
}


def render(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if exported schemas are stale")
    args = parser.parse_args()

    schema_dir = ROOT / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []

    for name, schema in SCHEMAS.items():
        path = schema_dir / name
        expected = render(schema)
        if args.check:
            actual = path.read_text(encoding="utf-8") if path.exists() else ""
            if actual != expected:
                stale.append(name)
        else:
            path.write_text(expected, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")

    if stale:
        print("stale schemas: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
