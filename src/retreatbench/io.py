from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def read_json(path: str | Path) -> Any:
    file_path = Path(path)
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"file does not exist: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {file_path}: {exc}") from exc


def load_model(path: str | Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate(read_json(path))


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    file_path = Path(path)
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL at {file_path}:{line_number}: {exc}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"JSONL record at {file_path}:{line_number} must be an object")
                yield value
    except FileNotFoundError as exc:
        raise ValueError(f"file does not exist: {file_path}") from exc


def write_json(path: str | Path, value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, values: Iterable[Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for value in values:
            if isinstance(value, BaseModel):
                value = value.model_dump(mode="json")
            handle.write(json.dumps(value, ensure_ascii=False) + "\n")
