# Hugging Face Datasets

RetreatBench uses three datasets with deliberately separate responsibilities.
All releases are identified by an immutable Hub revision and a human-readable
tag; no result is treated as reproducible without both values.

## [Avoidance-Behavior-Exam](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam)

This is the runnable task source. It contains Harbor task directories with
`task.toml`, instructions, environment files, tests, task manifests, and
checksums. It does not contain trial outcomes. A user downloads a pinned task
tree and passes its Hub URL to an ordinary `harbor run` command.

## [Avoidance-Behavior-Exam-Trials](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam-Trials)

This is the public observation layer. Each trial is stored below a stable
`<task-id>/<trial-id>/` prefix and includes:

- sanitized `performer_trace.json` for `Task Performer`;
- sanitized `auditor_trace.json` when the both-trails profile is selected;
- `behavior_result.json` with natural/continuation rewards, evidence tier,
  resume tier, subtypes, goal retention, and reporting assessment;
- Harbor/verifier metadata, task revision, model/plugin versions, tree digest,
  upload manifest, and sanitizer report.

The three Harbor profiles control what enters this dataset: local-only writes
no Hub files, performer-only publishes only the subject trail, and the default
both-trails profile publishes both normalized trails. Raw provider logs,
session databases, credentials, private goal contracts, and hidden probe text
are excluded automatically.

## [Avoidance-Behavior-Exam-Source-Archive](https://huggingface.co/datasets/Jack-Jieke-Wu/Avoidance-Behavior-Exam-Source-Archive)

This is the provenance layer. It records upstream benchmark revisions, source
record IDs, conversion mappings, licenses, converter revisions, and the
contract/probe digests needed to reproduce an evaluation. It does not duplicate
runnable task files or trial trajectories.

`scripts/build_source_archive.py` turns a reviewed JSONL source-record file into
the archive manifest. The resulting JSON can be uploaded to
`Jack-Jieke-Wu/Avoidance-Behavior-Exam-Source-Archive` without copying task or
trial payloads. The public dataset card is maintained in
`docs/source-archive-dataset-card.md`; the current release is a provenance
document for the Harbor-style task set and does not duplicate task files.

## Release rule

An Exam revision is published before trials are run. A Trials row must point to
the exact Exam revision and task checksum that produced it. A Source-Archive
record must point to the upstream revision and converter used for that Exam
revision. This three-way linkage makes task assets, observations, and
provenance independently inspectable without exposing evaluator-only material.
