from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.run_batch_generation as batch_script


def _sample_api_workflow() -> dict:
    return {
        "57:27": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "Latina female with thick wavy hair, harbor boats and pastel houses behind."},
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
                "seed": 20260424,
                "steps": 8,
                "cfg": 1.0,
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
            "inputs": {"filename_prefix": "my_new_workflow", "images": ["57:3", 0]},
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_scaffold_workflow_generates_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / "workflows" / "comfyui" / "my_new_workflow_api.json"
    _write_json(workflow_path, _sample_api_workflow())

    args = argparse.Namespace(
        workflow_json=str(workflow_path.as_posix()),
        slug="my_new_workflow",
        force=False,
        validate=False,
        submit_after_validate=False,
        config="",
        mode="scaffold_workflow",
    )
    batch_script.run_scaffold_workflow(args)

    assert (tmp_path / "configs" / "my_new_workflow_api.yaml").exists()
    assert (tmp_path / "configs" / "node_maps" / "my_new_workflow_node_map.yaml").exists()
    assert (
        tmp_path / "examples" / "prompt_packs" / "my_new_workflow_default_from_workflow.csv"
    ).exists()
    assert (tmp_path / "examples" / "prompt_packs" / "my_new_workflow_prompt_pack.csv").exists()
    assert (
        tmp_path / "results" / "runs" / "scaffold_my_new_workflow" / "scaffold_report.json"
    ).exists()
    assert (
        tmp_path / "results" / "runs" / "scaffold_my_new_workflow" / "scaffold_report.md"
    ).exists()
    assert (
        tmp_path / "results" / "runs" / "scaffold_my_new_workflow" / "next_commands.md"
    ).exists()
