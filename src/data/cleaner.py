from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def list_image_files(root: str | Path, recursive: bool = True) -> list[Path]:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")

    iterator: Iterable[Path]
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted([path for path in iterator if is_image_file(path)])


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_\-]+", "", text)
    return text or "sample"


def build_normalized_filename(
    src_path: str | Path,
    index: int,
    prefix: str = "img",
) -> str:
    src_path = Path(src_path)
    stem = normalize_text(src_path.stem)
    ext = src_path.suffix.lower()
    return f"{prefix}_{index:05d}_{stem}{ext}"


def ensure_directory(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_and_normalize_images(
    input_dir: str | Path,
    output_dir: str | Path,
    prefix: str = "img",
    dataset_name: str = "placeholder_dataset",
) -> list[dict]:
    input_dir = Path(input_dir)
    output_dir = ensure_directory(output_dir)

    image_files = list_image_files(input_dir)
    rows: list[dict] = []

    for index, src_path in enumerate(image_files, start=1):
        new_name = build_normalized_filename(src_path, index=index, prefix=prefix)
        dst_path = output_dir / new_name
        shutil.copy2(src_path, dst_path)

        rows.append(
            {
                "dataset_name": dataset_name,
                "original_path": str(src_path.as_posix()),
                "processed_path": str(dst_path.as_posix()),
                "original_name": src_path.name,
                "processed_name": new_name,
                "stem": normalize_text(src_path.stem),
                "caption": "",
                "split": "",
            }
        )

    return rows


def write_metadata_csv(rows: list[dict], output_csv: str | Path) -> None:
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError("No rows provided for metadata CSV writing.")

    fieldnames = [
        "dataset_name",
        "original_path",
        "processed_path",
        "original_name",
        "processed_name",
        "stem",
        "caption",
        "split",
    ]

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)