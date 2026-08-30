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
cp infra/adapters/researchclawbench/agent.md .opencode/agent/retreatbench-rcb-adapter.md

# 3. convert one or more sample tasks
export OPENAI_API_KEY=... OPENAI_BASE_URL=...
bash infra/adapters/researchclawbench/convert.sh \
  /path/to/upstream/tasks \
  upstreams/researchclawbench/converted \
  Math_002

# 4. verify mechanically
python3 infra/adapters/verify_task.py upstreams/researchclawbench/converted/Math_002
```

## Known gaps (disclosed, not silently accepted)

- The verifier is a keyword-match proxy against `checklist.json`'s claims,
  not the semantic grading the original benchmark likely intends (an LLM
  judge comparing the agent's report against each claim would be more
  faithful). Do not treat scores from this verifier as comparable to any
  official ResearchClawBench leaderboard number.
- `docker_image` is an unresolved placeholder; the adapter writes a generic
  scientific-Python Dockerfile since there is no upstream one to carry over.
- `target_study/` contents (including the private checklist) must never
  leak into any agent-visible path -- the adapter agent is instructed to
  keep them out, but this has only been spot-checked by hand on one sample
  task, not enforced by an automated check yet.
- Validated on one sample task (`Math_002`) only. Full-scale conversion of
  all 40 tasks across 10 domains is follow-up work.
