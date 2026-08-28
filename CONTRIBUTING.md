# Contributing to RetreatBench

RetreatBench values reproducibility, task fidelity, and falsifiable behavioral claims more than feature count.

## Contribution classes

1. **Core framework:** schemas, state bundles, candidate detection, continuation materialization, evaluation, and metrics.
2. **Benchmark adapters:** deterministic conversion of non-native datasets into Harbor tasks.
3. **Native overlays:** job-level artifacts, goal contracts, and progress probes that do not modify upstream Harbor tasks.
4. **Validation:** oracle/NOP tests, parity studies, state-restore checks, leakage audits, and annotated behavior fixtures.
5. **Documentation:** construct definitions, protocol details, adjudication guides, and reproducible experiment reports.

## Non-negotiable requirements

- Pin every upstream revision and record file hashes.
- Preserve original instructions, visible inputs, environment semantics, budget, and capability verifier.
- Keep private goal contracts, hidden tests, rubric keys, and judge credentials outside the agent environment.
- Never infer recoverability solely from a model judge or final-answer rhetoric.
- Label small task subsets as CI/parity fixtures, never as the official benchmark.
- Add tests for schema changes and metric denominator changes.
- Document any task exclusion and its effect on the evaluation denominator.

## Development workflow

```bash
python -m pip install -e '.[dev]'
pytest
python scripts/export_schemas.py --check
```

Open an issue before changing the construct definition, evidence tiers, main denominators, or continuation intervention. Such changes require a decision record in `docs/decisions.md`.
