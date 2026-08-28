# Adapter and overlay contract

## Adapter output

A non-native benchmark adapter must generate or reference:

- deterministic, registry-safe task names;
- `task.toml`, `instruction.md`, environment, solution/oracle, and tests as required by Harbor;
- a source manifest with upstream revision, hashes, protocol, license metadata, and task digest;
- a private goal contract and progress-probe mapping;
- declared workspace roots and state-bundle exclusions;
- oracle, NOP, health, leakage, and state-restore tests;
- benchmark-specific capability aggregation that remains separate from RetreatBench behavior aggregation.

## Parity

Parity experiments use the same agent, model, prompt, tools, network policy, evaluator commit, and sampling configuration in the upstream harness and Harbor adapter. Report repeated-run mean and sampling uncertainty. Do not compare against historical paper scores produced by different evaluator versions.

## Public/private/oracle separation

Only whitelisted public inputs enter the agent environment. Hidden tests, original papers, rubric keys, ground truth, and evaluator credentials remain in independent verifier or sidecar environments. Whole-directory copying is prohibited when source directories mix public and private files.

## Native overlays

For native Harbor datasets, store task digests, contract indexes, job-level artifact hooks, and private probes outside the task package. Any modification to upstream `task.toml`, instruction, or verifier creates a derived dataset and requires a new parity study.
