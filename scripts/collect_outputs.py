from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aigc2d.output_manager import collect_images, write_image_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect generated images into a run folder.")
    parser.add_argument("source_dir")
    parser.add_argument("--output-dir", default="outputs/collected")
    parser.add_argument("--move", action="store_true")
    args = parser.parse_args()
    images = collect_images(args.source_dir, args.output_dir, copy=not args.move)
    index = write_image_index(Path(args.output_dir) / "images.csv", images)
    print(f"collected: {len(images)}")
    print(f"index: {index}")


if __name__ == "__main__":
    main()
