from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .schemas import ExperimentConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (Path(base_dir) if base_dir else PROJECT_ROOT) / candidate


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML must contain a mapping: {path}")
    return data


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON must contain an object: {path}")
    return data


def write_json(path: str | Path, data: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return target


def model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    if isinstance(model, dict):
        return model
    raise TypeError(f"Cannot serialize object of type {type(model)!r}")


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    return ExperimentConfig(**load_yaml(path))
