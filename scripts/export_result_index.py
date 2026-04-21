from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generation.result_parser import export_image_index_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a CSV index for generated result images."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Directory to scan for result images.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        required=True,
        help="Path to output CSV file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    try:
        export_image_index_csv(input_dir=input_dir, output_csv=output_csv)
    except ValueError:
        print(f"[WARN] No images found in: {input_dir}")
        return

    with output_csv.open("r", encoding="utf-8") as f:
        row_count = max(sum(1 for _ in f) - 1, 0)

    print(f"[OK] Exported result index with {row_count} rows to: {output_csv}")


if __name__ == "__main__":
    main()
