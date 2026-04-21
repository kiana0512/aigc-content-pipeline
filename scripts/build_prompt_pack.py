from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generation.prompt_builder import (
    build_prompt_items,
    load_subjects,
    load_text,
    write_prompt_pack,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build prompt pack files from a base prompt and subject list."
    )
    parser.add_argument(
        "--base-positive",
        type=str,
        required=True,
        help="Path to base positive prompt txt file.",
    )
    parser.add_argument(
        "--base-negative",
        type=str,
        required=True,
        help="Path to base negative prompt txt file.",
    )
    parser.add_argument(
        "--subjects-file",
        type=str,
        required=True,
        help="Text file containing one subject per line.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Directory to store generated prompt pack files.",
    )
    parser.add_argument(
        "--style",
        type=str,
        default="fantasy game art",
        help="Style replacement string.",
    )
    parser.add_argument(
        "--attributes",
        type=str,
        default="clear silhouette, production-ready design",
        help="Attribute replacement string.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    base_positive = load_text(args.base_positive)
    base_negative = load_text(args.base_negative)
    subjects = load_subjects(args.subjects_file)
    items = build_prompt_items(
        subjects=subjects,
        positive_template=base_positive,
        negative_template=base_negative,
        style=args.style,
        attributes=args.attributes,
    )
    csv_path = write_prompt_pack(items=items, output_dir=Path(args.output_dir))

    print(f"[OK] Generated {len(items)} prompt files in: {Path(args.output_dir)}")
    print(f"[OK] Prompt pack CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
