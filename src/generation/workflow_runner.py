from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt_pack_csv(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_run_manifest(
    config: dict[str, Any],
    prompt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    project_cfg = config.get("project", {})
    task_cfg = config.get("task", {})
    model_cfg = config.get("model", {})
    runtime_cfg = config.get("runtime", {})
    generation_cfg = config.get("generation", {})

    manifest: dict[str, Any] = {
        "project_name": project_cfg.get("name", "unknown_project"),
        "task_type": task_cfg.get("type", "unknown_task"),
        "asset_type": task_cfg.get("asset_type", "unknown_asset"),
        "scenario": task_cfg.get("scenario", "unknown_scenario"),
        "model_family": model_cfg.get("family", "unknown_family"),
        "base_model_name": model_cfg.get("base_model_name", "unknown_model"),
        "seed": runtime_cfg.get("seed", 42),
        "width": generation_cfg.get("width", 1024),
        "height": generation_cfg.get("height", 1024),
        "num_inference_steps": generation_cfg.get("num_inference_steps", 30),
        "guidance_scale": generation_cfg.get("guidance_scale", 7.0),
        "sampler": generation_cfg.get("sampler", "unknown_sampler"),
        "scheduler": generation_cfg.get("scheduler", "unknown_scheduler"),
        "output_subdir": generation_cfg.get("output_subdir", "outputs/placeholder"),
        "items": [],
    }

    for row in prompt_rows:
        positive_prompt = row.get("positive_prompt_text", "").strip()

        if not positive_prompt and row.get("positive_prompt_path"):
            prompt_path = Path(row["positive_prompt_path"])
            if prompt_path.exists():
                positive_prompt = prompt_path.read_text(encoding="utf-8").strip()

        manifest["items"].append(
            {
                "id": row.get("id", ""),
                "subject": row.get("subject", ""),
                "style": row.get("style", ""),
                "attributes": row.get("attributes", ""),
                "positive_prompt": positive_prompt,
                "negative_prompt": row.get("negative_prompt_text", ""),
            }
        )

    return manifest


def save_manifest_json(manifest: dict[str, Any], output_json: str | Path) -> Path:
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return output_json