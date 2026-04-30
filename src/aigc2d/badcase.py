from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def summarize_badcases(score_csv: str | Path, threshold: float = 3.0) -> dict[str, Any]:
    with Path(score_csv).open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    category_counts: dict[str, int] = {}
    low_score_items: list[dict[str, Any]] = []
    for row in rows:
        category = row.get("badcase_category") or "uncategorized"
        if category != "uncategorized":
            category_counts[category] = category_counts.get(category, 0) + 1
        numeric = [
            float(value)
            for key, value in row.items()
            if key not in {"image_path", "badcase_category", "notes"} and value not in (None, "")
        ]
        if numeric and min(numeric) <= threshold:
            low_score_items.append(row)
    return {
        "count": len(rows),
        "category_counts": category_counts,
        "low_score_items": low_score_items,
    }
