# ResearchClawBench adapter

Converts one upstream ResearchClawBench task (`task_info.json` +
`related_work/` + `target_study/checklist.json`) into a Harbor `task.toml`
tree via an opencode custom agent -- see `docs/benchmark-hub.md` for why a
hand-written parser was rejected.

This benchmark is structurally harder than Terminal-Bench: there is no
upstream Dockerfile or pytest verifier to carry over, and grading is against
a weighted, semantic claim checklist rather than a pass/fail script. The
adapter's verifier is a **rough keyword-based proxy** for that checklist, not
a faithful reproduction of the original scoring -- see the "Known gaps"
section below.

## Usage

```bash
# 1. shallow-clone the upstream repo somewhere with disk headroom
git clone --depth 1 https://github.com/InternScience/ResearchClawBench.git /path/to/upstream

# 2. make the agent discoverable to opencode
mkdir -p .opencode/agent
cp infra/adapters/researchclawbench/agent.md .opencode/agent/stevedore-rcb.md

# 3. convert one or more sample tasks -- convert.sh now ALWAYS runs the
#    mandatory private-ground-truth-leak check after each conversion (see
#    verify_task.py's check_no_private_leak) and appends pass/fail to
#    <output-root>/conversion_log.txt; it does not rely on a human
#    remembering to run this separately.
export OPENAI_API_KEY=... OPENAI_BASE_URL=...
bash infra/adapters/researchclawbench/convert.sh \
  /path/to/upstream/tasks \
  upstreams/researchclawbench/converted \
  Math_002

# 4. verify mechanically + confirm no private-data leak
python3 infra/adapters/verify_task.py upstreams/researchclawbench/converted/Math_002 \
  --private-source /path/to/upstream/tasks/Math_002/target_study

# 5. real harbor run smoke test
harbor run --path upstreams/researchclawbench/converted/Math_002 \
  --agent opencode --model openai/gpt-5.6-sol-fast \
  --n-attempts 1 --n-concurrent 1 --agent-timeout-multiplier 0.1 \
  --env-file <path-to-openai-credentials> --yes
```

## Known gaps (disclosed, not silently accepted)

- The verifier is a keyword-match proxy against `checklist.json`'s claims,
  not the semantic grading the original benchmark likely intends (an LLM
  judge comparing the agent's report against each claim would be more
  faithful). Do not treat scores from this verifier as comparable to any
  official ResearchClawBench leaderboard number.
- `docker_image` is intentionally left unset; the adapter writes a generic
  scientific-Python Dockerfile since there is no upstream one to carry over,
  and Harbor builds it directly at run time (see
  `harbor.environments.definition.should_use_prebuilt_docker_image` --
  `docker_image` is an opt-in override for a pre-published image, not a
  required field).
- `target_study/` contents (including the private checklist) must never
  leak into any agent-visible path. This is now an automated hard-fail
  check (`verify_task.py --private-source`, wired into `convert.sh` so it
  runs on every conversion, not a manual-only spot-check) -- but the check
  itself has only been exercised on one sample task so far.
- Validated on one sample task (`Math_002`) only. Full-scale conversion of
  all 40 tasks across 10 domains is follow-up work.
