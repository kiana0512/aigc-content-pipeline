from __future__ import annotations

from pathlib import Path

from src.generation.workflow_inspector import inspect_workflow_path


ROOT = Path(__file__).resolve().parents[1]
Z_WORKFLOW = ROOT / "workflows/comfyui/image_z_image_turbo_api.json"
QWEN_WORKFLOW = ROOT / "workflows/comfyui/qwen_image_illustration_lora_api.json"


def test_inspect_real_export_z_image_turbo_contains_required_nodes() -> None:
    result = inspect_workflow_path(Z_WORKFLOW)

    assert result["workflow_format"] == "comfyui_api_prompt"
    class_types = set(result["class_types"])
    assert "SaveImage" in class_types
    assert "CLIPTextEncode" in class_types
    assert "EmptySD3LatentImage" in class_types
    assert "KSampler" in class_types
    assert "VAEDecode" in class_types
    assert "UNETLoader" in class_types
    assert "CLIPLoader" in class_types
    assert "VAELoader" in class_types
    assert "ModelSamplingAuraFlow" in class_types
    assert "ConditioningZeroOut" in class_types

    latent = result["detected_latent_nodes"][0]
    assert latent["node_id"] == "57:13"
    assert latent["width"] == 1024
    assert latent["height"] == 1024


def test_inspect_real_export_qwen_lora_contains_required_nodes() -> None:
    result = inspect_workflow_path(QWEN_WORKFLOW)

    assert result["workflow_format"] == "comfyui_api_prompt"
    class_types = set(result["class_types"])
    assert "SaveImage" in class_types
    assert "CLIPTextEncode" in class_types
    assert "EmptySD3LatentImage" in class_types
    assert "KSampler" in class_types
    assert "VAEDecode" in class_types
    assert "UNETLoader" in class_types
    assert "CLIPLoader" in class_types
    assert "VAELoader" in class_types
    assert "LoraLoaderModelOnly" in class_types

    prompt_nodes = result["detected_prompt_nodes"]
    roles = {item["role"] for item in prompt_nodes}
    assert "positive" in roles
    assert "negative" in roles


def test_inspect_real_export_colon_node_ids_do_not_fail() -> None:
    result_z = inspect_workflow_path(Z_WORKFLOW)
    result_qwen = inspect_workflow_path(QWEN_WORKFLOW)

    loader_z = {item["node_id"] for item in result_z["detected_loader_nodes"]}
    loader_qwen = {item["node_id"] for item in result_qwen["detected_loader_nodes"]}

    assert "57:28" in loader_z
    assert "57:30" in loader_z
    assert "57:29" in loader_z

    assert "76:37" in loader_qwen
    assert "76:38" in loader_qwen
    assert "76:39" in loader_qwen
    assert "76:73" in loader_qwen
