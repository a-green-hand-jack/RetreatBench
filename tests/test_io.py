from __future__ import annotations

import json
from pathlib import Path

import pytest

from retreatbench.io import load_model, read_json, read_jsonl, write_json, write_jsonl
from retreatbench.models import GoalContract

ROOT = Path(__file__).resolve().parents[1]


def test_read_and_write_json(tmp_path: Path) -> None:
    path = tmp_path / "nested/value.json"
    write_json(path, {"value": 3})
    assert read_json(path) == {"value": 3}


def test_read_json_missing_file() -> None:
    with pytest.raises(ValueError, match="file does not exist"):
        read_json(ROOT / "does-not-exist.json")


def test_read_json_invalid(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        read_json(path)


def test_load_model() -> None:
    contract = load_model(ROOT / "examples/goal_contract.example.json", GoalContract)
    assert contract.schema_version == "retreatbench.goal-contract.v1"


def test_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    write_jsonl(path, [{"a": 1}, {"b": 2}])
    assert list(read_jsonl(path)) == [{"a": 1}, {"b": 2}]


def test_jsonl_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        list(read_jsonl(path))


def test_jsonl_rejects_invalid_record(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text("{bad}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSONL"):
        list(read_jsonl(path))


def test_jsonl_missing_file() -> None:
    with pytest.raises(ValueError, match="file does not exist"):
        list(read_jsonl(ROOT / "missing.jsonl"))
