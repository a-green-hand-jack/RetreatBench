#!/usr/bin/env python3
"""Assemble a retreatbench.decision-context.v1 JSON from a diagnose-team verdict
plus the natural-run outcome (reward). Pilot script, mirrors examples/decision_context.*.json.

Usage:
  python pilot/assemble_decision_context.py \
      --verdict pilot/gpt2-codegolf/diagnose/final_verdict.json \
      --trial-id gpt2-codegolf-seed1 \
      --task-name terminal-bench-2.0/gpt2-codegolf \
      --benchmark "Terminal-Bench 2.0" \
      --original-verifier-reward 0.0 \
      --detector-label opencode-diagnose-team-v0 \
      --out pilot/gpt2-codegolf/decision_context.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", type=Path, required=True)
    ap.add_argument("--trial-id", required=True)
    ap.add_argument("--task-name", required=True)
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--original-verifier-reward", type=float, required=True)
    ap.add_argument("--detector-label", default="opencode-diagnose-team-v0")
    ap.add_argument("--voluntary-termination", action="store_true", default=None)
    ap.add_argument("--provider-or-harness-forced-stop", action="store_true", default=False)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    verdict = json.loads(args.verdict.read_text(encoding="utf-8"))
    resolved_by = verdict.get("_resolved_by", "unknown")
    detector = f"{args.detector_label}:{resolved_by}"

    candidates = []
    for c in verdict.get("candidates", []):
        candidates.append(
            {
                "candidate_id": c["candidate_id"],
                "subtype": c["subtype"],
                "goal_ids": c.get("goal_ids", []),
                "difficulty_event_ids": c.get("difficulty_event_ids", []),
                "step_ids": c["step_ids"],
                "evidence": c["evidence"],
                "detector": detector,
                "confidence": c.get("confidence"),
            }
        )

    goal_retention = None
    statuses = verdict.get("mandatory_goal_status", {})
    if statuses:
        satisfied_like = {"satisfied", "active"}
        goal_retention = sum(1 for s in statuses.values() if s in satisfied_like) / len(statuses)
    else:
        goal_retention = 1.0 if args.original_verifier_reward >= 1.0 else 0.0

    decision_context = {
        "schema_version": "retreatbench.decision-context.v1",
        "trial_id": args.trial_id,
        "task_name": args.task_name,
        "benchmark": args.benchmark,
        "original_verifier_reward": args.original_verifier_reward,
        "difficulty_events": verdict.get("difficulty_events", []),
        "candidates": candidates,
        "mandatory_goal_status": statuses,
        "goal_retention": goal_retention,
        "maintained_original_goal": verdict.get("maintained_original_goal", True),
        "voluntary_termination": verdict.get("voluntary_termination", True),
        "provider_or_harness_forced_stop": args.provider_or_harness_forced_stop,
        "residual_budget_sufficient": verdict.get("residual_budget_sufficient", True),
        "justified_blocker_verified": verdict.get("justified_blocker_verified", False),
        "completion_claim": verdict.get("completion_claim", False),
        "infeasibility_claim": verdict.get("infeasibility_claim", False),
        "partial_claim": verdict.get("partial_claim", False),
        "failure_acknowledged": verdict.get("failure_acknowledged", False),
        "effective_recovery": None,
        "continuations": [],
        "invalid_reason": None,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decision_context, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
