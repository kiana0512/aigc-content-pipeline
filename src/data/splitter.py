from __future__ import annotations

import csv
import random
from pathlib import Path


def validate_split_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Train/val/test ratios must sum to 1.0, got {total:.6f}"
        )


def assign_splits(
    rows: list[dict],
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
) -> list[dict]:
    validate_split_ratios(train_ratio, val_ratio, test_ratio)

    items = rows.copy()
    rng = random.Random(seed)
    rng.shuffle(items)

    n = len(items)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)

    assigned = []
    for idx, row in enumerate(items):
        row = dict(row)
        if idx < train_end:
            row["split"] = "train"
        elif idx < val_end:
            row["split"] = "val"
        else:
            row["split"] = "test"
        assigned.append(row)

    return assigned


def write_split_csv(rows: list[dict], output_csv: str | Path) -> None:
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError("No rows provided for split CSV writing.")

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def split_metadata_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
) -> None:
    input_csv = Path(input_csv)
    with input_csv.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"No rows found in input CSV: {input_csv}")

    split_rows = assign_splits(
        rows=rows,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
    )
    write_split_csv(split_rows, output_csv)