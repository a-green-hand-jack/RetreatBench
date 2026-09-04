#!/usr/bin/env python3
"""Build a small provenance manifest for Avoidance-Behavior-Exam releases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="JSONL source records")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exam-revision", required=True)
    parser.add_argument("--upstream-revision", required=True)
    parser.add_argument("--converter-revision", required=True)
    parser.add_argument("--license", default="see source records")
    args = parser.parse_args()
    records = []
    for line in args.records.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("source_record_id"), str):
                parser.error("each source record must be an object with source_record_id")
            records.append(value)
    payload = {
        "schema_version": "retreatbench.source-archive.v1",
        "exam_revision": args.exam_revision,
        "upstream_revision": args.upstream_revision,
        "converter_revision": args.converter_revision,
        "license": args.license,
        "records_digest": digest(args.records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
