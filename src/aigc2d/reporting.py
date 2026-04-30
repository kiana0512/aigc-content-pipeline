from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import model_to_dict
from .config import load_json
from .scoring import aggregate_score_records
from .schemas import RunManifest


def build_markdown_report(
    title: str,
    manifest_summary: list[dict[str, Any]] | None = None,
    score_summary: dict[str, Any] | None = None,
    badcase_summary: dict[str, Any] | None = None,
    sample_images: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> str:
    lines = [f"# {title}", ""]
    lines += ["## Run Summary", ""]
    if manifest_summary:
        for item in manifest_summary:
            lines.append(f"- `{item.get('task_name')}`: {item.get('prompt_template', '')} / {item.get('checkpoint_profile', '')}")
    else:
        lines.append("- No manifest summary provided.")
    lines += ["", "## Sample Images", ""]
    if sample_images:
        for image in sample_images:
            lines.append(f"- `{image}`")
    else:
        lines.append("- No sample images attached.")
    lines += ["", "## Score Summary", ""]
    lines.append("```json")
    lines.append(json.dumps(score_summary or {}, ensure_ascii=False, indent=2))
    lines.append("```")
    lines += ["", "## Badcase Summary", ""]
    lines.append("```json")
    lines.append(json.dumps(badcase_summary or {}, ensure_ascii=False, indent=2))
    lines.append("```")
    lines += ["", "## Next Steps", ""]
    for step in next_steps or ["Refine prompts, compare control profiles, and rerun top candidates."]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def write_report(path: str | Path, markdown: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    return target


def summarize_run(manifest: RunManifest) -> dict[str, Any]:
    return {
        "run_id": manifest.run_id,
        "mode": manifest.mode,
        "workflow_name": manifest.workflow_name,
        "model": manifest.model,
        "output_count": len(manifest.output_images),
        "score_summary": aggregate_score_records(manifest.scores),
        "notes": manifest.notes,
    }


def summarize_run_manifest(path: str | Path) -> dict[str, Any]:
    data = load_json(path)
    outputs = data.get("output_images", [])
    return {
        "run_id": data.get("run_id"),
        "task_type": data.get("task_type"),
        "workflow_name": data.get("workflow_name"),
        "model": (data.get("resolved_models") or {}).get("checkpoint") or data.get("model"),
        "output_count": len(outputs),
        "scoring_summary": data.get("scoring_summary", {}),
        "notes": data.get("notes", ""),
    }


def build_run_report(run_manifest_path: str | Path) -> str:
    data = load_json(run_manifest_path)
    return build_markdown_report(
        title=f"Run Report: {data.get('run_id')}",
        manifest_summary=[
            {
                "task_name": data.get("task_type"),
                "prompt_template": data.get("workflow_name"),
                "checkpoint_profile": (data.get("resolved_models") or {}).get("checkpoint", ""),
            }
        ],
        score_summary=data.get("scoring_summary", {}),
        sample_images=[item.get("path", str(item)) if isinstance(item, dict) else str(item) for item in data.get("output_images", [])],
        next_steps=data.get("next_steps") or None,
    )


def write_summary(path: str | Path, manifest: RunManifest) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(model_to_dict(summarize_run(manifest)), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
