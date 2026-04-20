from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


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


def iter_image_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_\-]+", "", text)
    return text or "sample"


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    metadata_out = Path(args.metadata_out)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_out.parent.mkdir(parents=True, exist_ok=True)

    image_files = list(iter_image_files(input_dir))
    if not image_files:
        print(f"[WARN] No image files found in: {input_dir}")
        return

    rows = []
    for index, src_path in enumerate(image_files, start=1):
        stem = normalize_text(src_path.stem)
        ext = src_path.suffix.lower()
        new_name = f"{args.prefix}_{index:05d}_{stem}{ext}"
        dst_path = output_dir / new_name

        shutil.copy2(src_path, dst_path)

        rows.append(
            {
                "dataset_name": args.dataset_name,
                "original_path": str(src_path.as_posix()),
                "processed_path": str(dst_path.as_posix()),
                "original_name": src_path.name,
                "processed_name": new_name,
                "stem": stem,
                "caption": "",
                "split": "",
            }
        )

    with metadata_out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "dataset_name",
                "original_path",
                "processed_path",
                "original_name",
                "processed_name",
                "stem",
                "caption",
                "split",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Copied {len(rows)} images to: {output_dir}")
    print(f"[OK] Metadata written to: {metadata_out}")


if __name__ == "__main__":
    main()