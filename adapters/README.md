# Benchmark adapters

Adapters convert non-native upstream harnesses into faithful Harbor datasets. They are not permitted to simplify task instructions, visible inputs, resources, budgets, or verifier semantics.

Planned adapters:

- `terminal_bench_1/`
- `researchclawbench/`
- `paperwritingbench/`
- `paperwrite_bench/`

Shared utilities belong in `common/`. Each adapter must expose deterministic `prepare`, `validate`, `oracle`, `nop`, `parity`, and `summarize` operations and produce a source manifest plus private goal-contract index.
