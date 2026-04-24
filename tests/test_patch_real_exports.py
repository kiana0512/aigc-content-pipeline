from __future__ import annotations

from pathlib import Path

from src.generation.comfyui_adapter import WorkflowPatchParams, load_node_mapping, load_workflow_json, patch_workflow


ROOT = Path(__file__).resolve().parents[1]


def test_patch_real_export_z_image_turbo() -> None:
    workflow = load_workflow_json(ROOT / "workflows/comfyui/image_z_image_turbo_api.json")
    mapping = load_node_mapping(ROOT / "configs/node_maps/z_image_turbo_node_map.yaml")

    params = WorkflowPatchParams(
        positive_prompt="test positive z",
        negative_prompt="",
        seed=123456,
        width=960,
        height=640,
        batch_size=2,
        steps=12,
        cfg=1.1,
        sampler="euler",
        scheduler="normal",
        denoise=0.9,
        filename_prefix="z_smoke/item_001",
    )
    patched = patch_workflow(workflow, mapping, params)

    assert patched["57:27"]["inputs"]["text"] == "test positive z"
    assert patched["57:13"]["inputs"]["width"] == 960
    assert patched["57:13"]["inputs"]["height"] == 640
    assert patched["57:13"]["inputs"]["batch_size"] == 2
    assert patched["57:3"]["inputs"]["seed"] == 123456
    assert patched["57:3"]["inputs"]["steps"] == 12
    assert patched["57:3"]["inputs"]["cfg"] == 1.1
    assert patched["57:3"]["inputs"]["sampler_name"] == "euler"
    assert patched["57:3"]["inputs"]["scheduler"] == "normal"
    assert patched["57:3"]["inputs"]["denoise"] == 0.9
    assert patched["9"]["inputs"]["filename_prefix"] == "z_smoke/item_001"


def test_patch_real_export_qwen_lora() -> None:
    workflow = load_workflow_json(ROOT / "workflows/comfyui/qwen_image_illustration_lora_api.json")
    mapping = load_node_mapping(ROOT / "configs/node_maps/qwen_image_illustration_lora_node_map.yaml")

    params = WorkflowPatchParams(
        positive_prompt="test positive qwen",
        negative_prompt="test negative qwen",
        seed=8888,
        width=768,
        height=1024,
        batch_size=1,
        steps=30,
        cfg=5.8,
        sampler="euler",
        scheduler="karras",
        denoise=1.0,
        filename_prefix="qwen_smoke/item_001",
        use_lora=True,
        lora_path="illustration-1.0-qwen-image.safetensors",
        lora_strength=0.85,
    )

    patched = patch_workflow(workflow, mapping, params)
    assert patched["76:6"]["inputs"]["text"] == "test positive qwen"
    assert patched["76:7"]["inputs"]["text"] == "test negative qwen"
    assert patched["76:58"]["inputs"]["width"] == 768
    assert patched["76:58"]["inputs"]["height"] == 1024
    assert patched["76:3"]["inputs"]["seed"] == 8888
    assert patched["76:3"]["inputs"]["steps"] == 30
    assert patched["76:3"]["inputs"]["cfg"] == 5.8
    assert patched["76:3"]["inputs"]["sampler_name"] == "euler"
    assert patched["76:3"]["inputs"]["scheduler"] == "karras"
    assert patched["60"]["inputs"]["filename_prefix"] == "qwen_smoke/item_001"
    assert patched["76:73"]["inputs"]["lora_name"] == "illustration-1.0-qwen-image.safetensors"
    assert patched["76:73"]["inputs"]["strength_model"] == 0.85
