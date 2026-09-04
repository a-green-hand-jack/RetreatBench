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


def _load_json_for_sanitization(text: str) -> Any:
    """Load JSON while repairing Harbor's bare redaction placeholders.

    Some Harbor providers redact scalar values before writing ATIF, yielding
    entries such as ``"step_id": [REDACTED]``.  The source is still useful,
    but not technically JSON.  Quoting only standalone placeholders preserves
    the normalized record and keeps the public copy parseable.
    """

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _quote_bare_placeholders(text)
        repaired = _repair_json_escapes(repaired)
        return json.loads(repaired)


def _quote_bare_placeholders(text: str) -> str:
    """Quote redaction markers only when they occur outside JSON strings."""

    markers = ("[REDACTED]", "[PRIVATE_FIELD_REMOVED]")
    out: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue
        marker = next((item for item in markers if text.startswith(item, index)), None)
        if marker is not None:
            end = index + len(marker)
            suffix = text[end:].lstrip()
            if not suffix.startswith(("]", ",", "}")):
                while end < len(text) and text[end] not in ",}\n":
                    end += 1
            token = text[index:end].strip()
            # Redaction may cut through a numeric scalar (for example
            # ``[REDACTED]6[REDACTED]25``).  Keep numeric fields valid with a
            # neutral zero; a standalone marker remains an explicit string.
            if token == marker and out and out[-1].isdigit():
                while out and out[-1].isdigit():
                    out.pop()
                out.append("0")
            else:
                out.append("0" if token != marker else json.dumps(marker))
            index = end
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _repair_json_escapes(text: str) -> str:
    """Escape malformed backslashes while retaining valid JSON escapes."""

    out: list[str] = []
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if not in_string:
            out.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue
        if char == '"':
            out.append(char)
            in_string = False
            index += 1
            continue
        if char != "\\":
            out.append(char)
            index += 1
            continue
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if next_char in '"\\/bfnrt':
            out.extend(("\\", next_char))
            index += 2
        elif next_char == "u" and index + 5 < len(text):
            digits = text[index + 2 : index + 6]
            if re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                out.extend(("\\u", digits))
                index += 6
            else:
                out.extend(("\\\\",))
                index += 1
        else:
            out.extend(("\\\\",))
            index += 1
    return "".join(out)


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
                raw_json = path.read_text(encoding="utf-8")
                try:
                    payload = _load_json_for_sanitization(raw_json)
                except json.JSONDecodeError:
                    # A provider can redact through quotes or delimiters. Do
                    # not publish malformed text or fail the whole trial;
                    # retain an auditable digest and explicit parse status.
                    report.skipped_files.append(f"{relative}:invalid-json")
                    payload = {
                        "schema_version": "retreatbench.sanitized-artifact.v1",
                        "parse_status": "invalid_json",
                        "source_sha256": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
                    }
                target.write_text(
                    json.dumps(sanitize_value(payload, report), indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
            elif path.suffix.lower() in {".jsonl", ".ndjson"}:
                lines = []
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        lines.append(json.dumps(sanitize_value(json.loads(line), report), ensure_ascii=True))
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
