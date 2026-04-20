from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PromptItem:
    id: int
    subject: str
    style: str
    attributes: str
    positive_prompt_text: str
    negative_prompt_text: str
    positive_prompt_path: str = ""


def load_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def load_subjects(path: str | Path) -> list[str]:
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sanitize_filename(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("-", "_")
    )


def fill_prompt_template(
    template: str,
    subject: str,
    style: str,
    attributes: str,
) -> str:
    return (
        template.replace("{subject}", subject)
        .replace("{character_subject}", subject)
        .replace("{style}", style)
        .replace("{attributes}", attributes)
    )


def build_prompt_items(
    subjects: list[str],
    positive_template: str,
    negative_template: str,
    style: str,
    attributes: str,
) -> list[PromptItem]:
    items: list[PromptItem] = []

    for idx, subject in enumerate(subjects, start=1):
        positive_prompt = fill_prompt_template(
            template=positive_template,
            subject=subject,
            style=style,
            attributes=attributes,
        )
        items.append(
            PromptItem(
                id=idx,
                subject=subject,
                style=style,
                attributes=attributes,
                positive_prompt_text=positive_prompt,
                negative_prompt_text=negative_template,
            )
        )

    return items


def write_prompt_pack(items: list[PromptItem], output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for item in items:
        filename = f"{item.id:03d}_{sanitize_filename(item.subject)}.txt"
        prompt_path = output_dir / filename
        prompt_path.write_text(item.positive_prompt_text + "\n", encoding="utf-8")

        item.positive_prompt_path = str(prompt_path.as_posix())
        rows.append(asdict(item))

    csv_path = output_dir / "prompt_pack.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "subject",
                "style",
                "attributes",
                "positive_prompt_text",
                "negative_prompt_text",
                "positive_prompt_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return csv_path