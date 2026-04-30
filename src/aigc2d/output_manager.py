from __future__ import annotations

import csv
import shutil
from pathlib import Path


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def collect_images(source_dir: str | Path, output_dir: str | Path, copy: bool = True) -> list[Path]:
    source = Path(source_dir)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    collected: list[Path] = []
    for image_path in sorted(source.rglob("*")):
        if image_path.suffix.lower() not in IMAGE_EXTS:
            continue
        destination = target / image_path.name
        if copy:
            shutil.copy2(image_path, destination)
        else:
            shutil.move(str(image_path), destination)
        collected.append(destination)
    return collected


def write_image_index(path: str | Path, images: list[Path]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "filename"])
        writer.writeheader()
        for image in images:
            writer.writerow({"image_path": str(image), "filename": image.name})
    return target
