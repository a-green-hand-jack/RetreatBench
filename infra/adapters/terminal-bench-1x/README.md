# Terminal-Bench 1.x adapter

Converts one upstream Terminal-Bench 1.x task (`task.yaml` + `Dockerfile` +
`tests/`) into a Harbor `task.toml` tree via an opencode custom agent, not a
hand-written parser -- see `docs/benchmark-hub.md` for why.

## Usage

```bash
# 1. shallow-clone the upstream repo somewhere with disk headroom
git clone --depth 1 https://github.com/laude-institute/terminal-bench.git /path/to/upstream

# 2. make the agent discoverable to opencode (project-local agent file)
mkdir -p .opencode/agent
cp infra/adapters/terminal-bench-1x/agent.md .opencode/agent/retreatbench-tb1x-adapter.md

# 3. convert one or more sample tasks
export OPENAI_API_KEY=... OPENAI_BASE_URL=...
bash infra/adapters/terminal-bench-1x/convert.sh \
  /path/to/upstream/original-tasks \
  upstreams/terminal-bench-1x/converted \
  git-workflow-hack

# 4. verify mechanically (task.toml parses + required fields + Dockerfile builds)
python3 infra/adapters/verify_task.py upstreams/terminal-bench-1x/converted/git-workflow-hack
```

## Known gaps (disclosed, not silently accepted)

- `docker_image` is left as an unresolved placeholder -- the adapter carries
  the upstream `Dockerfile` over but does not build/publish an image.
- No semantic parity checking against the upstream task -- only mechanical
  checks (parses, required fields, Dockerfile builds). See `ROADMAP.md`.
- Multi-container tasks (`docker-compose.yaml` present upstream) are flagged
  in a `task.toml` comment, not silently collapsed into a single Dockerfile.
- Validated on one sample task (`git-workflow-hack`) only, per the project's
  pilot-before-full-run discipline. Full-scale conversion of all ~80-100
  tasks is follow-up work.
