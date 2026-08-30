# Benchmark hub: managing the 6 target benchmarks via HuggingFace

RetreatBench's target set (Issue #1) is 6 benchmarks: Terminal-Bench 1.x / 2.0 /
Science, ResearchClawBench, PaperWritingBench, PaperWrite-Bench. Every one of
them is managed the same way: a small declarative manifest in
`infra/hub-datasets/*.yaml` records where its Harbor-ready task tree comes
from and where it lands, pinned at an exact revision -- the same reproducibility
discipline `infra/benchmarks/*/*.yaml`'s `dataset.revision` field already gives
individual task runs.

**Ready-to-run converted task trees live in the HuggingFace dataset
`Jack-Jieke-Wu/Avoidance-Behavior-Exam`. Raw upstream mirrors and conversion
code never go there** -- conversion code and agents stay in this git repo
(`infra/adapters/`); the HF dataset only holds output someone can `hf
download` and hand straight to `harbor run`.

## Fork vs. adapt

Each manifest's `status` field is one of:

- **`harbor-native`** -- the upstream benchmark already ships real Harbor
  `task.toml` trees (confirmed by inspecting its HF Hub file listing, not
  assumed from the benchmark's name). No conversion: just mirror it, pinned,
  into `Avoidance-Behavior-Exam`.
- **`pre-converted`** -- not Harbor-native upstream, but already converted to
  Harbor style by the RetreatBench maintainer in a separate HF dataset. Also
  just a fork, from that dataset instead of the original upstream.
- **`needs-adapter`** -- no Harbor-style version exists anywhere (checked via
  HF Hub search before assuming this, e.g. Terminal-Bench 1.x: only
  `harborframework`'s 2.0/2.1/3.0 and an unrelated `harbor-datasets` mix
  exist; the only other Hub hits are plain parquet mirrors of raw data, not
  `task.toml` trees). These get an `infra/adapters/<slug>/` conversion
  workflow instead of a `source`.

## Fork mechanics

`infra/tools/fork_hub_dataset.py <manifest.yaml>` is the only code involved in
forking: it downloads the manifest's pinned `source.revision` (optionally
just `source.include` when the source repo bundles more than one benchmark,
as `Jack-Jieke-Wu/Paper-Writing-Exam` does) and re-uploads it under
`target.path` in `target.hub_repo`. No parsing or transformation happens here
-- it is a copy operation, run on a machine with enough disk headroom for one
benchmark's task tree (not necessarily the machine running Harbor trials).

## Adapter mechanics (`needs-adapter` benchmarks)

Terminal-Bench 1.x's own conversion story (Harbor's `harbor task migrate` is
explicitly documented as imperfect: "some tasks may require manual
migration") and ResearchClawBench's total absence of Harbor integration both
argue against a hand-written, deterministic Python parser -- upstream task
formats here are heterogeneous enough that a rigid converter would need
constant per-task exceptions. Instead, `infra/adapters/<slug>/` holds a member
of **Stevedore** -- the opencode agent family that loads upstream benchmark
tasks into Harbor, the way a stevedore loads cargo onto a ship
(`stevedore-tb1x`, `stevedore-rcb`, one per benchmark since each has a
genuinely different source format and prompt, discoverable to opencode under
`.opencode/agent/stevedore-<slug>.md`):

- `agent.md` -- Stevedore's system prompt, carrying Harbor's
  `task.toml` schema/fields, worked examples from
  `infra/benchmarks/terminal-bench-2/gpt2-codegolf.yaml` and
  `case-studies/gpt2-codegolf/`, and the upstream benchmark's raw task
  format, with an explicit instruction to preserve the original
  instruction/environment/verifier semantics rather than paraphrase them
  (Design invariant #1 in `README.md`).
- `prompt.template.txt` -- the per-task invocation template.
- A thin bash orchestration loop that calls Stevedore once per upstream task,
  then always runs the mandatory verification below (not an optional
  separate step a human might forget).
- `infra/adapters/verify_task.py` -- mechanical verification: does the
  produced `task.toml` parse and carry the required fields, does the
  environment build (Harbor builds directly from `environment/Dockerfile`
  when `[environment].docker_image` is left unset -- see
  `harbor.environments.definition.should_use_prebuilt_docker_image`;
  `docker_image` is an opt-in override for a pre-published image, never a
  required placeholder), and -- for benchmarks with private ground truth
  like ResearchClawBench -- a hard-fail check (`--private-source`) that no
  private file's content or filename leaked into any agent-visible path.
  This is **not** semantic parity checking against the upstream task, and
  not a real capability signal -- both remain open items (see `ROADMAP.md`
  Path 3). A real `harbor run --path <converted-task-dir>` smoke test with a
  cheap subject agent and a short timeout is the second, independent
  validation layer before any converted task is published to the HF dataset.

Adapter work is validated on 1-2 sample tasks before any full-scale run, the
same pilot-first discipline used for the single `gpt2-codegolf` task before
any Terminal-Bench-2.0-wide run.

## Manifest schema

```yaml
benchmark: <slug>
status: harbor-native | pre-converted | needs-adapter

source:                       # omitted (null) for needs-adapter until an adapter exists
  hub_repo: <owner>/<repo>
  repo_type: dataset
  revision: <pinned commit sha>
  include: <subset-path>/     # optional, when source_repo bundles multiple benchmarks

target:
  hub_repo: Jack-Jieke-Wu/Avoidance-Behavior-Exam
  path: <slug>/

upstream:                     # needs-adapter only: where the real upstream benchmark lives
  repo: <owner>/<repo>
  task_count_hint: "..."

task_count_hint: "..."
notes: |
  ...
```
