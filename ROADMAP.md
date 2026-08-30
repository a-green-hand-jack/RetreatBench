# RetreatBench roadmap

The project does not reduce the scientific target to a smaller substitute benchmark. Engineering slices exist only to validate the infrastructure; official natural runs cover every eligible task in each pinned upstream revision. No benchmark scores are claimed until then.

## Current state

Completed:

- Core behavioral evaluator (`models`, `decision`, `metrics`, `state`, `io`, `cli`) with schemas, examples, and CI.
- One complete task-level loop: Terminal-Bench 2.0 `gpt2-codegolf`, Harbor `codex` / `openai/gpt-5.6-sol`, natural trial + R3 workspace-only continuation, classified `observed_retreat` / `D-observed-retreat`. Curated in `case-studies/gpt2-codegolf/`.

## Path 1 — Reproduce and harden the Terminal-Bench loop

- [x] One validated natural run on `gpt2-codegolf` (OpenAI OAuth, no Apex).
- [x] Parent state capture, manifest, and tree hash.
- [x] Candidate freeze before continuation.
- [x] R3 workspace-only continuation with the goal-preservation nudge.
- [x] Parent/branch probe comparison and original verifier rerun.
- [ ] Pin an exact Harbor release and ATIF schema revision in the repository.
- [ ] Record strict residual wall-clock, token, and monetary budgets for the continuation.
- [ ] Add a reproducible `harbor run` script for the task in `infra/benchmarks/`.
- [ ] Make the task's evidence package complete and CI-checkable.

**Exit criterion:** every step of the `gpt2-codegolf` loop is reproducible from the repository and pinned inputs.

## Path 2 — Native R1 continuation

- [ ] Determine whether the pinned Harbor release supports cross-trial native trajectory resume for `codex`.
- [ ] If supported, run an R1-native continuation from a hash-matched state under strict residual budget.
- [ ] If not supported (current Harbor 0.20.0 behavior), keep the result at `R3-workspace-only` and do not claim R1.

**Exit criterion:** a defensible, evidence-backed resume tier for the agent scaffold, not a configuration default.

## Path 3 — Expand benchmark families one at a time

A benchmark family is added only after the previous one has a complete, reproducible loop and a curated case study:

- [ ] Terminal-Bench 2.0 beyond the pilot task (as overlay; upstream tasks unchanged).
- [ ] Terminal-Bench-Science (as overlay).
- [ ] Terminal-Bench 1.x, ResearchClawBench, PaperWritingBench, PaperWrite-Bench (as adapters) — only as implemented.

**Exit criterion:** every task in every pinned revision loads in Harbor, native task digests remain unchanged, adapted datasets pass parity checks, and each family publishes at least one auditable case study.

## Evaluation and paper analysis (later)

- [ ] Dual semantic judges with frozen prompts and blinded identities.
- [ ] Human adjudication protocol and annotation set.
- [ ] Capability–avoidance Pareto analysis.
- [ ] Cross-benchmark and split-half trait stability.
- [ ] Hierarchical model separating model, scaffold, task, and difficulty effects.
- [ ] Case studies for scope retreat, false infeasibility, persistent incapability, and honest partial failure.

**Exit criterion:** all headline claims are reproducible from public code, pinned inputs, and auditable trial evidence.
