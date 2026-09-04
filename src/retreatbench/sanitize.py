"""Deterministic sanitization for public RetreatBench trial artifacts.

The sanitizer deliberately works on normalized JSON/text artifacts rather than
provider-specific session databases.  It is safe to run before an upload and
produces a machine-readable report that becomes part of the trial manifest.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9_]{16,})\b"),
    re.compile(r"(?i)\b(xox[baprs]-[A-Za-z0-9-]{16,})\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,}]+"),
)
_PRIVATE_KEYS = {
    "goal_contract",
    "private_goal_contract",
    "hidden_probe",
    "hidden_probes",
    "provider_session",
    "session_state",
    "raw_session",
    "raw_provider_output",
    "raw",
    "raw_output",
    "stdout",
    "stderr",
    "session_database",
    "credentials",
    "env",
}


@dataclass
class SanitizationReport:
    """Summary of transformations applied to one artifact tree."""

    input_files: int = 0
    output_files: int = 0
    redactions: int = 0
    skipped_files: list[str] = field(default_factory=list)
    tree_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "retreatbench.sanitization-report.v1",
            "input_files": self.input_files,
            "output_files": self.output_files,
            "redactions": self.redactions,
            "skipped_files": sorted(self.skipped_files),
            "tree_sha256": self.tree_sha256,
        }


def _redact_text(value: str, report: SanitizationReport) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result, count = pattern.subn("[REDACTED]", result)
        report.redactions += count
    # Host-local paths make public trails unnecessarily identifying.
    result, count = re.subn(r"/(?:Users|home|private|var)/[^\s\"']+", "[LOCAL_PATH]", result)
    report.redactions += count
    return result


def sanitize_value(value: Any, report: SanitizationReport, key: str | None = None) -> Any:
    """Recursively remove private fields and redact secrets in JSON values."""

    if key and key.lower() in _PRIVATE_KEYS:
        report.redactions += 1
        return "[PRIVATE_FIELD_REMOVED]"
    if isinstance(value, str):
        return _redact_text(value, report)
    if isinstance(value, list):
        return [sanitize_value(item, report) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_value(item_value, report, str(item_key))
            for item_key, item_value in value.items()
            if str(item_key).lower() not in _PRIVATE_KEYS
        }
    return value


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sanitize_tree(source: str | Path, destination: str | Path) -> SanitizationReport:
    """Copy *source* to *destination*, sanitizing public-safe artifacts."""

    src = Path(source)
    dst = Path(destination)
    if not src.is_dir():
        raise ValueError(f"source is not a directory: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    dst_resolved = dst.resolve()
    report = SanitizationReport()
    for path in sorted(item for item in src.rglob("*") if item.is_file()):
        # When the destination is inside the source trial directory, do not
        # recursively sanitize the copy we are creating.
        try:
            path.resolve().relative_to(dst_resolved)
            continue
        except ValueError:
            pass
        relative = path.relative_to(src)
        report.input_files += 1
        if (
            path.name in {"codex.txt", "opencode.txt", "session.jsonl", "provider.log"}
            or path.suffix.lower() in {".sqlite", ".db"}
            or "sessions" in path.parts
        ):
            report.skipped_files.append(str(relative))
            continue
        target = dst / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                target.write_text(
                    json.dumps(sanitize_value(payload, report), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            elif path.suffix.lower() in {".jsonl", ".ndjson"}:
                lines = []
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        lines.append(json.dumps(sanitize_value(json.loads(line), report), ensure_ascii=False))
                    except json.JSONDecodeError:
                        lines.append(_redact_text(line, report))
                target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            else:
                target.write_bytes(path.read_bytes())
                if target.suffix.lower() in {".md", ".txt", ".log", ".yaml", ".yml", ".toml"}:
                    target.write_text(_redact_text(target.read_text(encoding="utf-8"), report), encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            target.write_bytes(path.read_bytes())
        report.output_files += 1
    report.tree_sha256 = _tree_digest(dst)
    (dst / "sanitization-report.json").write_text(
        json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
