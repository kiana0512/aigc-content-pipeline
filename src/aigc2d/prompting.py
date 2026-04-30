from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .prompt_builder import MissingPromptVariable, PromptBuilder, render_template


def load_prompt_sheet(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_prompt_sheet(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["id", "positive_prompt", "negative_prompt", "reference_image"]
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return target


__all__ = [
    "MissingPromptVariable",
    "PromptBuilder",
    "render_template",
    "load_prompt_sheet",
    "write_prompt_sheet",
]
