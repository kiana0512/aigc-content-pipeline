from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate simple draft captions from metadata."
    )
    parser.add_argument(
        "--input-csv",
        type=str,
        required=True,
        help="Prepared metadata CSV produced by prepare_dataset.py",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        required=True,
        help="Output CSV with generated captions.",
    )
    parser.add_argument(
        "--task-type",
        type=str,
        choices=["ui_icon", "character_concept", "generic"],
        default="generic",
        help="Caption generation mode.",
    )
    parser.add_argument(
        "--style",
        type=str,
        default="fantasy game art",
        help="Style phrase appended into generated captions.",
    )
    return parser.parse_args()


def stem_to_phrase(stem: str) -> str:
    parts = stem.replace("-", "_").split("_")
    parts = [p for p in parts if p and not p.isdigit() and p != "img"]
    return " ".join(parts).strip() or "unknown subject"


def build_caption(subject: str, task_type: str, style: str) -> str:
    if task_type == "ui_icon":
        return (
            f"{subject}, game ui icon, centered composition, clean silhouette, "
            f"high readability, {style}"
        )
    if task_type == "character_concept":
        return (
            f"{subject}, game character concept art, full character focus, "
            f"clear costume design, stylized rendering, {style}"
        )
    return f"{subject}, game-related visual asset, {style}"


def main() -> None:
    args = parse_args()

    input_csv = Path(args.input_csv)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"[WARN] No rows found in: {input_csv}")
        return

    output_rows = []
    for row in rows:
        stem = row.get("stem", "")
        subject = stem_to_phrase(stem)
        caption = build_caption(subject, args.task_type, args.style)

        row["caption"] = caption
        output_rows.append(row)

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_rows[0].keys())
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"[OK] Generated captions for {len(output_rows)} samples.")
    print(f"[OK] Saved to: {output_csv}")


if __name__ == "__main__":
    main()