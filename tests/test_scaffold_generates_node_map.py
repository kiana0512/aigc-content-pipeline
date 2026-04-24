from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.run_batch_generation as batch_script


def _workflow_for_node_map() -> dict:
    return {
        "57:27": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "positive prompt"},
            "_meta": {"title": "Positive Prompt"},
        },
        "57:7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "negative prompt"},
            "_meta": {"title": "Negative Prompt"},
        },
        "57:13": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": 960, "height": 640, "batch_size": 2},
        },
        "57:3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "positive": ["57:27", 0],
                "negative": ["57:7", 0],
                "latent_image": ["57:13", 0],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "node_map_case", "images": ["57:3", 0]},
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_scaffold_generates_node_map(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / "workflows" / "comfyui" / "node_map_case_api.json"
    _write_json(workflow_path, _workflow_for_node_map())

    args = argparse.Namespace(
        workflow_json=str(workflow_path.as_posix()),
        slug="node_map_case",
        force=False,
        validate=False,
        submit_after_validate=False,
        config="",
        mode="scaffold_workflow",
    )
    batch_script.run_scaffold_workflow(args)

    node_map_path = tmp_path / "configs" / "node_maps" / "node_map_case_node_map.yaml"
    node_map = batch_script.load_node_mapping(node_map_path)
    required = node_map["required"]
    optional = node_map["optional"]

    assert required["positive_prompt"]["node_id"] == "57:27"
    assert required["latent_size"]["node_id"] == "57:13"
    assert required["latent_size"]["width_key"] == "width"
    assert required["latent_size"]["height_key"] == "height"
    assert required["latent_size"]["batch_size_key"] == "batch_size"
    assert required["sampler"]["node_id"] == "57:3"
    assert required["sampler"]["seed_key"] == "seed"
    assert required["sampler"]["steps_key"] == "steps"
    assert required["sampler"]["cfg_key"] == "cfg"
    assert required["sampler"]["sampler_key"] == "sampler_name"
    assert required["sampler"]["scheduler_key"] == "scheduler"
    assert required["sampler"]["denoise_key"] == "denoise"
    assert optional["save_image"]["node_id"] == "9"
    assert optional["save_image"]["filename_prefix_key"] == "filename_prefix"
