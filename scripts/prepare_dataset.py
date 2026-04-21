from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import copy_and_normalize_images, write_metadata_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a small-scale image dataset for the game AIGC workflow."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Directory containing raw input images.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory to store processed images.",
    )
    parser.add_argument(
        "--metadata-out",
        type=str,
        default="data/metadata/prepared_dataset.csv",
        help="Path to output metadata CSV.",
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default="placeholder_dataset",
        help="Logical dataset name written to metadata.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="img",
        help="Filename prefix for normalized output images.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    metadata_out = Path(args.metadata_out)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    rows = copy_and_normalize_images(
        input_dir=input_dir,
        output_dir=output_dir,
        prefix=args.prefix,
        dataset_name=args.dataset_name,
    )
    if not rows:
        print(f"[WARN] No image files found in: {input_dir}")
        return

    write_metadata_csv(rows, metadata_out)

    print(f"[OK] Copied {len(rows)} images to: {output_dir}")
    print(f"[OK] Metadata written to: {metadata_out}")


if __name__ == "__main__":
    main()
