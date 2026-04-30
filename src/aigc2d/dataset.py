from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .config import PROJECT_ROOT
from .schemas import BenchmarkItem


def _split_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [tag.strip() for tag in value.replace(",", "|").split("|") if tag.strip()]


def load_benchmark(path: str | Path) -> list[BenchmarkItem]:
    source = Path(path)
    if source.is_dir():
        jsonl = source / "items.jsonl"
        csv_path = source / "items.csv"
        source = jsonl if jsonl.exists() else csv_path

    if source.suffix.lower() == ".jsonl":
        return [
            BenchmarkItem(**json.loads(line))
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        rows = data.get("items", data) if isinstance(data, dict) else data
        return [BenchmarkItem(**row) for row in rows]
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        return [
            BenchmarkItem(
                id=row["id"],
                character_name=row["character_name"],
                image_path=row["image_path"],
                source=row["source"],
                tags=_split_tags(row.get("tags")),
                notes=row.get("notes") or "",
            )
            for row in rows
        ]
    raise ValueError(f"Unsupported benchmark format: {source}")


def load_hsr_benchmark(
    benchmark_dir: str | Path = PROJECT_ROOT / "data" / "benchmarks" / "hsr",
) -> list[BenchmarkItem]:
    """Load Honkai: Star Rail character reference items."""
    return load_benchmark(benchmark_dir)


def iter_benchmark_items(items: Iterable[BenchmarkItem], limit: int | None = None) -> list[BenchmarkItem]:
    selected = list(items)
    return selected if limit is None else selected[:limit]
