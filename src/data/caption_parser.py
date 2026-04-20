from __future__ import annotations

import csv
from pathlib import Path


def stem_to_subject_phrase(stem: str) -> str:
    parts = stem.replace("-", "_").split("_")
    parts = [p for p in parts if p and not p.isdigit() and p != "img"]
    return " ".join(parts).strip() or "unknown subject"


def build_caption(
    subject: str,
    task_type: str = "generic",
    style: str = "fantasy game art",
    extra_tags: str = "",
) -> str:
    extra = f", {extra_tags}" if extra_tags.strip() else ""

    if task_type == "ui_icon":
        return (
            f"{subject}, game ui icon, centered composition, clean silhouette, "
            f"high readability, {style}{extra}"
        )

    if task_type == "character_concept":
        return (
            f"{subject}, game character concept art, full character focus, "
            f"clear costume design, stylized rendering, {style}{extra}"
        )

    return f"{subject}, game-related visual asset, {style}{extra}"


def fill_prompt_template(
    template: str,
    subject: str,
    style: str,
    attributes: str = "",
) -> str:
    return (
        template.replace("{subject}", subject)
        .replace("{character_subject}", subject)
        .replace("{style}", style)
        .replace("{attributes}", attributes)
    )


def add_captions_to_metadata_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    task_type: str = "generic",
    style: str = "fantasy game art",
    extra_tags: str = "",
) -> None:
    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"No rows found in input CSV: {input_csv}")

    updated_rows = []
    for row in rows:
        stem = row.get("stem", "")
        subject = stem_to_subject_phrase(stem)
        row["caption"] = build_caption(
            subject=subject,
            task_type=task_type,
            style=style,
            extra_tags=extra_tags,
        )
        updated_rows.append(row)

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=updated_rows[0].keys())
        writer.writeheader()
        writer.writerows(updated_rows)