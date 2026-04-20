from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


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

    rows = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        stat = path.stat()
        with Image.open(path) as img:
            width, height = img.width, img.height

        rows.append(
            {
                "relative_path": str(path.relative_to(input_dir).as_posix()),
                "absolute_path": str(path.as_posix()),
                "extension": path.suffix.lower(),
                "width": width,
                "height": height,
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )

    if not rows:
        print(f"[WARN] No images found in: {input_dir}")
        return

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "relative_path",
                "absolute_path",
                "extension",
                "width",
                "height",
                "size_bytes",
                "modified_time",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Exported result index with {len(rows)} rows to: {output_csv}")


if __name__ == "__main__":
    main()