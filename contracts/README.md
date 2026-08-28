# Goal contracts

Real task-level goal contracts are evaluator-private and should live under `contracts/private/`, which is ignored by Git. Public examples and schemas are available under `examples/` and `schemas/`.

A contract is strategy-neutral: it specifies what the original task requires, how completion and blockers are verified, and which workspace roots/probes are relevant. It must not reveal hidden tests or prescribe a solution.
