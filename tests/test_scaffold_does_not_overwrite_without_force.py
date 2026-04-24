from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import scripts.run_batch_generation as batch_script


def _workflow_payload() -> dict:
    return {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "positive"},
            "_meta": {"title": "Positive Prompt"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "negative"},
            "_meta": {"title": "Negative Prompt"},
        },
        "3": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 1,
                "steps": 10,
                "cfg": 2.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["3", 0],
            },
        },
        "5": {"class_type": "SaveImage", "inputs": {"filename_prefix": "overwrite", "images": ["4", 0]}},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _args(workflow_path: Path, force: bool) -> argparse.Namespace:
    return argparse.Namespace(
        workflow_json=str(workflow_path.as_posix()),
        slug="overwrite_case",
        force=force,
        validate=False,
        submit_after_validate=False,
        config="",
        mode="scaffold_workflow",
    )


def test_scaffold_does_not_overwrite_without_force(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / "workflows" / "comfyui" / "overwrite_case_api.json"
    _write_json(workflow_path, _workflow_payload())

    batch_script.run_scaffold_workflow(_args(workflow_path, force=False))

    config_path = tmp_path / "configs" / "overwrite_case_api.yaml"
    original_text = "custom_marker: keep_me\n"
    config_path.write_text(original_text, encoding="utf-8")

    with pytest.raises(FileExistsError, match="File already exists. Use --force to overwrite."):
        batch_script.run_scaffold_workflow(_args(workflow_path, force=False))

    batch_script.run_scaffold_workflow(_args(workflow_path, force=True))
    overwritten = config_path.read_text(encoding="utf-8")
    assert overwritten != original_text
