from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a simple evaluation summary for output images."
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Directory containing generated images.",
    )
    parser.add_argument(
        "--report-out",
        type=str,
        required=True,
        help="Path to output markdown report.",
    )
    return parser.parse_args()


def iter_images(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    images = iter_images(input_dir)
    if not images:
        print(f"[WARN] No images found in: {input_dir}")
        return

    ext_counter = Counter()
    size_counter = Counter()
    total_bytes = 0

    for image_path in images:
        ext_counter[image_path.suffix.lower()] += 1
        total_bytes += image_path.stat().st_size

        with Image.open(image_path) as img:
            size_counter[f"{img.width}x{img.height}"] += 1

    avg_size_mb = total_bytes / len(images) / 1024 / 1024

    lines = [
        "# Output Evaluation Report",
        "",
        f"- Input directory: `{input_dir.as_posix()}`",
        f"- Number of images: **{len(images)}**",
        f"- Average file size: **{avg_size_mb:.2f} MB**",
        "",
        "## File Extension Distribution",
        "",
    ]

    for ext, count in sorted(ext_counter.items()):
        lines.append(f"- {ext}: {count}")

    lines.extend(["", "## Resolution Distribution", ""])
    for size, count in sorted(size_counter.items()):
        lines.append(f"- {size}: {count}")

    lines.extend(["", "## Sample Files", ""])
    for image_path in images[:10]:
        lines.append(f"- {image_path.as_posix()}")

    report_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[OK] Evaluation report written to: {report_out}")


if __name__ == "__main__":
    main()