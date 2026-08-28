# RetreatBench implementation roadmap

The project does not reduce the scientific target to a smaller substitute benchmark. Engineering slices exist only to validate adapters and infrastructure; official natural runs cover every eligible task in each pinned upstream revision.

## Phase A — Frozen interfaces and core schemas

- [x] Select the project name and repository structure.
- [x] Define goal contract, decision context, continuation evidence, behavior result, and aggregate metrics.
- [x] Add executable validation, classification, aggregation, examples, and CI.
- [ ] Pin an exact Harbor release and ATIF schema revision.
- [ ] Freeze all six upstream revisions in `configs/upstreams.lock.json`.

**Exit criterion:** all schemas validate; exported schemas are deterministic; core tests pass.

## Phase B — Full benchmark integration

- [ ] Terminal-Bench 1.x adapter and upstream parity audit.
- [ ] Terminal-Bench 2.0 non-invasive overlay.
- [ ] Terminal-Bench-Science non-invasive overlay.
- [ ] ResearchClawBench adapter.
- [ ] PaperWritingBench sparse/PlotOff adapter.
- [ ] PaperWrite-Bench short-overview adapter.
- [ ] Deterministic task IDs, source manifests, license records, and contract indexes.

**Exit criterion:** every task in every pinned revision loads in Harbor; native task digests remain unchanged; adapted datasets pass parity checks.

## Phase C — Oracle, NOP, health, and state restoration

- [ ] Original verifier oracle pass and flake audit.
- [ ] NOP pass rate of zero.
- [ ] Environment and blocker probes.
- [ ] Host-generated state bundles, manifests, and restore hooks.
- [ ] Hash-equality validation for all tracked workspace roots and sidecar state.
- [ ] Private leakage and adversarial artifact tests.

**Exit criterion:** state restoration is exact for every supported task class and no private evidence enters the agent environment.

## Phase D — Full natural runs

- [ ] Register the agent/model/scaffold matrix.
- [ ] Run all tasks with pre-registered budgets and seeds.
- [ ] Collect ATIF, final answers, rewards, progress probes, budgets, and state bundles.
- [ ] Freeze the candidate detector before any continuation outcomes are visible.

**Exit criterion:** every valid natural trial has a complete evidence package or an explicit invalid reason.

## Phase E — Same-state continuations

- [ ] Neutral Continue branch.
- [ ] Goal-Preservation Nudge branch.
- [ ] Diagnostic Nudge ablation.
- [ ] Native resume support matrix by agent scaffold.
- [ ] Strict residual-budget accounting.
- [ ] Random non-candidate continuations for detector-recall estimation.

**Exit criterion:** every eligible candidate has a valid branch result or a documented infrastructure exclusion.

## Phase F — Evaluation and paper analysis

- [ ] Dual semantic judges with frozen prompts and blinded identities.
- [ ] Human adjudication protocol and annotation set.
- [ ] Capability–avoidance Pareto analysis.
- [ ] Cross-benchmark and split-half trait stability.
- [ ] Hierarchical model separating model, scaffold, task, and difficulty effects.
- [ ] Case studies for scope retreat, false infeasibility, persistent incapability, and honest partial failure.

**Exit criterion:** all headline claims are reproducible from public code, pinned inputs, and auditable trial evidence.
