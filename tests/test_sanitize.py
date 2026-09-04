from __future__ import annotations

import json
from pathlib import Path

from retreatbench.sanitize import sanitize_tree


def test_sanitize_tree_removes_private_and_runtime_files(tmp_path: Path) -> None:
    source = tmp_path / "trial"
    source.mkdir()
    (source / "decision.json").write_text(
        json.dumps(
            {
                "goal_contract": {"goals": ["private"]},
                "message": "token=sk-test-secret-value-123456",
                "action": "write /Users/alice/project/output.txt",
                "stdout": "provider output must stay private",
            }
        ),
        encoding="utf-8",
    )
    (source / "opencode.txt").write_text("raw provider session", encoding="utf-8")
    public = tmp_path / "public"
    report = sanitize_tree(source, public)

    payload = json.loads((public / "decision.json").read_text(encoding="utf-8"))
    assert "goal_contract" not in payload
    assert "stdout" not in payload
    assert "[REDACTED]" in payload["message"]
    assert "[LOCAL_PATH]" in payload["action"]
    assert not (public / "opencode.txt").exists()
    assert report.redactions >= 2


def test_sanitize_tree_repairs_bare_harbor_redaction_placeholder(tmp_path: Path) -> None:
    source = tmp_path / "trial"
    source.mkdir()
    (source / "trajectory.json").write_text(
        '{"steps": [{"step_id": [REDACTED], "message": "kept"}]}\n',
        encoding="utf-8",
    )
    public = tmp_path / "public"
    sanitize_tree(source, public)

    payload = json.loads((public / "trajectory.json").read_text(encoding="utf-8"))
    assert payload["steps"][0]["step_id"] == "[REDACTED]"
