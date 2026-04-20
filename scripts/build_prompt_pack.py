from __future__ import annotations

import argparse
import csv
from pathlib import Path


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


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def sanitize_filename(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("-", "_")
    )


def fill_prompt(template: str, subject: str, style: str, attributes: str) -> str:
    return (
        template.replace("{subject}", subject)
        .replace("{style}", style)
        .replace("{attributes}", attributes)
        .replace("{character_subject}", subject)
    )


def main() -> None:
    args = parse_args()

    base_positive = load_text(Path(args.base_positive))
    base_negative = load_text(Path(args.base_negative))
    subjects = [
        line.strip()
        for line in Path(args.subjects_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pack_rows = []
    for index, subject in enumerate(subjects, start=1):
        prompt_text = fill_prompt(
            template=base_positive,
            subject=subject,
            style=args.style,
            attributes=args.attributes,
        )

        filename = f"{index:03d}_{sanitize_filename(subject)}.txt"
        prompt_path = output_dir / filename
        prompt_path.write_text(prompt_text + "\n", encoding="utf-8")

        pack_rows.append(
            {
                "id": index,
                "subject": subject,
                "style": args.style,
                "attributes": args.attributes,
                "positive_prompt_path": str(prompt_path.as_posix()),
                "negative_prompt": base_negative,
            }
        )

    csv_path = output_dir / "prompt_pack.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "subject",
                "style",
                "attributes",
                "positive_prompt_path",
                "negative_prompt",
            ],
        )
        writer.writeheader()
        writer.writerows(pack_rows)

    print(f"[OK] Generated {len(pack_rows)} prompt files in: {output_dir}")
    print(f"[OK] Prompt pack CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()