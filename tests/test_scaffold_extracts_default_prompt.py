from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import scripts.run_batch_generation as batch_script


DEFAULT_POSITIVE = (
    "Latina female with thick wavy hair, harbor boats and pastel houses behind. "
    "Breezy seaside light, warm tones, cinematic close-up."
)


def _workflow_with_defaults() -> dict:
    return {
        "57:27": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": DEFAULT_POSITIVE},
            "_meta": {"title": "Positive Prompt"},
        },
        "57:28": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "low quality, blurry, watermark"},
            "_meta": {"title": "Negative Prompt"},
        },
        "57:13": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        },
        "57:3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 12,
                "cfg": 1.2,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "positive": ["57:27", 0],
                "negative": ["57:28", 0],
                "latent_image": ["57:13", 0],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "extract_case", "images": ["57:3", 0]},
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_first_csv_row(path: Path) -> dict[str, str]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def test_scaffold_extracts_default_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / "workflows" / "comfyui" / "extract_case_api.json"
    _write_json(workflow_path, _workflow_with_defaults())

    args = argparse.Namespace(
        workflow_json=str(workflow_path.as_posix()),
        slug="extract_case",
        force=False,
        validate=False,
        submit_after_validate=False,
        config="",
        mode="scaffold_workflow",
    )
    batch_script.run_scaffold_workflow(args)

    default_csv = (
        tmp_path / "examples" / "prompt_packs" / "extract_case_default_from_workflow.csv"
    )
    editable_csv = tmp_path / "examples" / "prompt_packs" / "extract_case_prompt_pack.csv"

    assert _read_first_csv_row(default_csv)["positive_prompt"] == DEFAULT_POSITIVE
    assert _read_first_csv_row(editable_csv)["positive_prompt"] == DEFAULT_POSITIVE
