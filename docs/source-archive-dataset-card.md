---
pretty_name: Avoidance-Behavior-Exam Source Archive
task_categories:
- other
language:
- en
license: apache-2.0
tags:
- retreatbench
- provenance
- harbor
---

# Avoidance-Behavior-Exam-Source-Archive

This dataset is the provenance ledger for the RetreatBench task release. It
records where each runnable Harbor task came from and how it was converted or
reviewed. It is intentionally small: the runnable task tree belongs to
`Avoidance-Behavior-Exam`, while sanitized observations belong to
`Avoidance-Behavior-Exam-Trials`.

Each release uses an immutable Hub revision and may contain one or more JSON
records with the following fields:

- `source_record_id`: stable identifier for the upstream source record.
- `exam_revision`: exact revision of `Avoidance-Behavior-Exam` evaluated.
- `upstream_revision`: source benchmark or corpus revision.
- `converter_revision`: converter or review commit that produced the task.
- `license`: applicable upstream licensing note.
- `contract_digest`: digest of the private goal-contract description.
- `probe_digest`: digest of the private progress-probe description.

Private goal contracts and hidden probe text are never stored in this public
archive. The archive is a compact reproducibility document, not another copy
of task files or agent trajectories.
