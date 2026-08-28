# Security policy

RetreatBench processes untrusted agent output, shell commands, archives, source trees, scientific artifacts, and LaTeX. Treat all generated artifacts as hostile.

## Reportable issues

- private ground-truth, hidden-test, rubric, or credential leakage;
- agent ability to modify host-generated trajectory or state manifests;
- path traversal, unsafe symlinks, archive bombs, or workspace escape;
- unsafe LaTeX compilation or shell-escape paths;
- verifier access from the agent environment;
- result tampering that can alter evidence tiers or benchmark denominators.

## Required isolation

- Run original verifiers and RetreatBench behavioral evaluators in separate, least-privilege environments.
- Compile untrusted LaTeX without ground truth, credentials, network, or shell escape before private grading.
- Generate trajectory and state hashes from the host or a read-only sidecar.
- Materialize continuation branches only after validating all archive paths, permissions, digests, and excluded roots.
- Do not include secrets in issues, logs, example fixtures, or public artifacts.

Until a dedicated security contact is published, use a private GitHub security advisory rather than a public issue for suspected leakage or sandbox escape.
