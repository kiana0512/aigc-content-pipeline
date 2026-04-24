from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.run_batch_generation as batch_script


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_yaml(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_batch_patch_creates_one_workflow_per_prompt_row(tmp_path: Path, monkeypatch) -> None:
    workflow_path = _write_json(
        tmp_path / "workflow.json",
        {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "default positive"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "default negative"}},
            "3": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                },
            },
            "5": {"class_type": "SaveImage", "inputs": {"filename_prefix": "legacy"}},
        },
    )

    mapping_path = _write_yaml(
        tmp_path / "node_map.yaml",
        """
required:
  positive_prompt:
    node_id: "1"
    input_key: "text"
  negative_prompt:
    node_id: "2"
    input_key: "text"
  latent_size:
    node_id: "3"
    width_key: "width"
    height_key: "height"
    batch_size_key: "batch_size"
  sampler:
    node_id: "4"
    seed_key: "seed"
    steps_key: "steps"
    cfg_key: "cfg"
    sampler_key: "sampler_name"
    scheduler_key: "scheduler"
    denoise_key: "denoise"
optional:
  save_image:
    node_id: "5"
    filename_prefix_key: "filename_prefix"
    output_dir_key: ""
""".strip()
        + "\n",
    )

    prompt_pack = tmp_path / "prompt_pack.csv"
    prompt_pack.write_text(
        "\n".join(
            [
                "id,subject,positive_prompt,negative_prompt,filename_prefix",
                "1,hero,first positive,first negative,first_prefix",
                "2,env,second positive,second negative,second_prefix",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config_path = _write_yaml(
        tmp_path / "config.yaml",
        f"""
project:
  name: "test"
task:
  type: "baseline"
  asset_type: "icon"
  scenario: "smoke"
model:
  family: "split"
  base_model_name: "mock"
runtime:
  seed: 123
generation:
  prompt: "config prompt"
  negative_prompt: "config neg"
  width: 512
  height: 512
  batch_size: 1
  num_inference_steps: 20
  guidance_scale: 7.0
  sampler: "euler"
  scheduler: "normal"
  denoise: 1.0
  filename_prefix: "from_config"
comfyui:
  base_url: "http://127.0.0.1:8000"
  workflow_json: "{workflow_path.as_posix()}"
  node_map: "{mapping_path.as_posix()}"
""".strip()
        + "\n",
    )

    run_dir = tmp_path / "results" / "runs" / "batch_patch_case"

    monkeypatch.setattr(
        batch_script,
        "_resolve_run_dir",
        lambda args, config, workflow_path=None: run_dir,
    )
    monkeypatch.setattr(
        batch_script,
        "inspect_workflow_path",
        lambda _path: {"detected_prompt_nodes": [], "detected_output_nodes": []},
    )
    monkeypatch.setattr(
        batch_script,
        "resolve_models_from_config",
        lambda config, inspection_result, comfyui_root=None: {
            "resolution": {"summary": {"missing_count": 0}}
        },
    )
    monkeypatch.setattr(
        batch_script,
        "suggest_mapping_from_config",
        lambda config, inspection_result, existing_mapping=None: {
            "mapping": batch_script.load_node_mapping(mapping_path),
            "diff_vs_existing": {},
            "needs_manual_confirmation": [],
            "confidence": {},
            "field_bindings": {},
        },
    )

    args = argparse.Namespace(
        config=str(config_path.as_posix()),
        prompt_pack=str(prompt_pack.as_posix()),
        run_name="batch_patch_case",
        workflow_json="",
        node_map="",
        comfyui_root="",
        mapping_mode="",
        comfyui_url="",
        client_id="",
        mode="workflow_import_pipeline",
        output_json="",
    )
    config = batch_script.load_yaml_config(config_path)

    batch_script.run_workflow_import_pipeline(args, config)

    item1 = run_dir / "patched_workflows" / "item_0001_patched_workflow.json"
    item2 = run_dir / "patched_workflows" / "item_0002_patched_workflow.json"
    assert item1.exists()
    assert item2.exists()

    payload1 = json.loads(item1.read_text(encoding="utf-8"))
    payload2 = json.loads(item2.read_text(encoding="utf-8"))
    assert payload1["1"]["inputs"]["text"] == "first positive"
    assert payload2["1"]["inputs"]["text"] == "second positive"

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["items"][0]["patched_workflow_path"].endswith(
        "patched_workflows/item_0001_patched_workflow.json"
    )
    assert manifest["items"][1]["patched_workflow_path"].endswith(
        "patched_workflows/item_0002_patched_workflow.json"
    )
