from __future__ import annotations

from pathlib import Path
from typing import Any


def _format_dict_items(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"- **{key}**:")
            for sub_key, sub_value in value.items():
                lines.append(f"  - {sub_key}: {sub_value}")
        elif isinstance(value, list):
            lines.append(f"- **{key}**:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- **{key}**: {value}")
    return lines


def build_markdown_report(
    title: str,
    summary: dict[str, Any],
    aesthetic_summary: dict[str, Any] | None = None,
    consistency_summary: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> str:
    lines: list[str] = [f"# {title}", ""]

    lines.append("## Summary")
    lines.append("")
    lines.extend(_format_dict_items(summary))
    lines.append("")

    if aesthetic_summary is not None:
        lines.append("## Aesthetic Summary")
        lines.append("")
        lines.extend(_format_dict_items(aesthetic_summary))
        lines.append("")

    if consistency_summary is not None:
        lines.append("## Consistency Summary")
        lines.append("")
        lines.extend(_format_dict_items(consistency_summary))
        lines.append("")

    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def save_markdown_report(content: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path