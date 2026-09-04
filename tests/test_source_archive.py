from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_build_source_archive_writes_reproducible_manifest(tmp_path: Path) -> None:
    records = tmp_path / "records.jsonl"
    records.write_text(json.dumps({"source_record_id": "r1", "license": "MIT"}) + "\n", encoding="utf-8")
    output = tmp_path / "archive.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_source_archive.py",
            str(records),
            "--output",
            str(output),
            "--exam-revision",
            "exam-sha",
            "--upstream-revision",
            "upstream-sha",
            "--converter-revision",
            "converter-sha",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.exists()
    assert json.loads(output.read_text())["records"][0]["source_record_id"] == "r1"
    assert str(output) in result.stdout
