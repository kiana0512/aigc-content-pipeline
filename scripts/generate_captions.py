from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import add_captions_to_metadata_csv


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


def main() -> None:
    args = parse_args()

    input_csv = Path(args.input_csv)
    output_csv = Path(args.output_csv)
    try:
        add_captions_to_metadata_csv(
            input_csv=input_csv,
            output_csv=output_csv,
            task_type=args.task_type,
            style=args.style,
        )
    except ValueError:
        print(f"[WARN] No rows found in: {input_csv}")
        return

    with output_csv.open("r", newline="", encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1

    print(f"[OK] Generated captions for {max(row_count, 0)} samples.")
    print(f"[OK] Saved to: {output_csv}")


if __name__ == "__main__":
    main()
