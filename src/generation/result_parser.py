from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def scan_image_files(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")

    return sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    )


def export_image_index_csv(input_dir: str | Path, output_csv: str | Path) -> Path:
    input_dir = Path(input_dir)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    image_paths = scan_image_files(input_dir)
    if not image_paths:
        raise ValueError(f"No images found in: {input_dir}")

    rows: list[dict] = []
    for path in image_paths:
        stat = path.stat()
        with Image.open(path) as img:
            rows.append(
                {
                    "relative_path": str(path.relative_to(input_dir).as_posix()),
                    "absolute_path": str(path.as_posix()),
                    "extension": path.suffix.lower(),
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

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

    return output_csv


def build_directory_summary(input_dir: str | Path) -> dict:
    input_dir = Path(input_dir)
    image_paths = scan_image_files(input_dir)

    ext_counter = Counter()
    size_counter = Counter()
    total_bytes = 0

    for path in image_paths:
        ext_counter[path.suffix.lower()] += 1
        total_bytes += path.stat().st_size

        with Image.open(path) as img:
            size_counter[f"{img.width}x{img.height}"] += 1

    avg_size_mb = (total_bytes / len(image_paths) / 1024 / 1024) if image_paths else 0.0

    return {
        "input_dir": str(input_dir.as_posix()),
        "num_images": len(image_paths),
        "avg_size_mb": round(avg_size_mb, 4),
        "extension_distribution": dict(sorted(ext_counter.items())),
        "resolution_distribution": dict(sorted(size_counter.items())),
        "sample_files": [str(path.as_posix()) for path in image_paths[:10]],
    }