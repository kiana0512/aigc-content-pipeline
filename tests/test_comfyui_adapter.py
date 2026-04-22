from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.generation.comfyui_adapter import (
    PLACEHOLDER_WORKFLOW_ERROR,
    ComfyUIAdapterError,
    NodeMappingError,
    PlaceholderWorkflowError,
    WorkflowPatchParams,
    load_node_mapping,
    load_workflow_json,
    patch_workflow,
    patch_workflow_with_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _sample_workflow() -> dict:
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old positive"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "old negative"}},
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
            },
        },
        "5": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "old_prefix"},
        },
    }


def _sample_mapping() -> dict:
    return {
        "required": {
            "positive_prompt": {"node_id": "1", "input_key": "text"},
            "negative_prompt": {"node_id": "2", "input_key": "text"},
            "latent_size": {
                "node_id": "3",
                "width_key": "width",
                "height_key": "height",
            },
            "sampler": {
                "node_id": "4",
                "seed_key": "seed",
                "steps_key": "steps",
                "cfg_key": "cfg",
                "sampler_key": "sampler_name",
                "scheduler_key": "scheduler",
            },
        },
        "optional": {
            "save_image": {
                "node_id": "5",
                "filename_prefix_key": "filename_prefix",
                "output_dir_key": "",
            }
        },
    }


def test_patch_workflow_injects_required_fields() -> None:
    workflow = _sample_workflow()
    mapping = _sample_mapping()
    params = WorkflowPatchParams(
        positive_prompt="new positive",
        negative_prompt="new negative",
        seed=12345,
        width=1024,
        height=768,
        steps=32,
        cfg=6.5,
        sampler="dpmpp_2m",
        scheduler="karras",
        filename_prefix="run/item_001",
    )

    patched = patch_workflow(workflow, mapping, params)

    assert patched["1"]["inputs"]["text"] == "new positive"
    assert patched["2"]["inputs"]["text"] == "new negative"
    assert patched["3"]["inputs"]["width"] == 1024
    assert patched["3"]["inputs"]["height"] == 768
    assert patched["4"]["inputs"]["seed"] == 12345
    assert patched["4"]["inputs"]["steps"] == 32
    assert patched["4"]["inputs"]["cfg"] == 6.5
    assert patched["4"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert patched["4"]["inputs"]["scheduler"] == "karras"
    assert patched["5"]["inputs"]["filename_prefix"] == "run/item_001"


def test_patch_workflow_supports_prompt_wrapped_api_payload() -> None:
    workflow = {"prompt": _sample_workflow()}
    mapping = _sample_mapping()
    params = WorkflowPatchParams(
        positive_prompt="wrapped positive",
        negative_prompt="wrapped negative",
        seed=99,
        width=768,
        height=1024,
        steps=28,
        cfg=5.5,
        sampler="euler_a",
        scheduler="karras",
    )

    patched = patch_workflow(workflow, mapping, params)
    assert patched["prompt"]["1"]["inputs"]["text"] == "wrapped positive"
    assert patched["prompt"]["2"]["inputs"]["text"] == "wrapped negative"
    assert patched["prompt"]["3"]["inputs"]["width"] == 768
    assert patched["prompt"]["3"]["inputs"]["height"] == 1024


def test_placeholder_workflow_raises_clear_error(tmp_path: Path) -> None:
    workflow_path = tmp_path / "placeholder_workflow.json"
    _write_json(
        workflow_path,
        {
            "workflow_name": "placeholder",
            "status": {"is_placeholder": True},
        },
    )

    with pytest.raises(PlaceholderWorkflowError) as exc:
        load_workflow_json(workflow_path)

    assert PLACEHOLDER_WORKFLOW_ERROR in str(exc.value)


def test_ui_workflow_json_is_rejected(tmp_path: Path) -> None:
    workflow_path = tmp_path / "ui_format_workflow.json"
    _write_json(
        workflow_path,
        {
            "last_node_id": 10,
            "nodes": [{"id": 1, "type": "KSampler"}],
        },
    )

    with pytest.raises(ComfyUIAdapterError) as exc:
        load_workflow_json(workflow_path)

    assert "UI format" in str(exc.value)
    assert "API Format" in str(exc.value)


def test_node_mapping_missing_fields_raises_clear_error(tmp_path: Path) -> None:
    mapping_path = tmp_path / "invalid_map.yaml"
    _write_yaml(
        mapping_path,
        {
            "required": {
                "positive_prompt": {"node_id": "1"},
            }
        },
    )

    with pytest.raises(NodeMappingError) as exc:
        load_node_mapping(mapping_path)

    message = str(exc.value)
    assert "missing required fields" in message.lower()
    assert "required.positive_prompt.input_key" in message


def test_lora_enabled_without_mapping_node_raises_error() -> None:
    workflow = _sample_workflow()
    mapping = _sample_mapping()
    params = WorkflowPatchParams(
        positive_prompt="p",
        negative_prompt="n",
        seed=1,
        width=512,
        height=512,
        steps=20,
        cfg=7.0,
        sampler="euler",
        scheduler="normal",
        use_lora=True,
        lora_path="my_lora.safetensors",
        lora_strength=0.8,
    )

    with pytest.raises(ComfyUIAdapterError) as exc:
        patch_workflow(workflow, mapping, params)

    assert "optional.lora.node_id" in str(exc.value)


def test_controlnet_enabled_with_incomplete_mapping_raises_error() -> None:
    workflow = _sample_workflow()
    mapping = _sample_mapping()
    mapping["optional"] = mapping.get("optional", {})
    mapping["optional"]["controlnet"] = {
        "model_node_id": "",
        "model_key": "control_net_name",
        "strength_node_id": "",
        "strength_key": "strength",
        "image_node_id": "",
        "image_key": "image",
    }
    params = WorkflowPatchParams(
        positive_prompt="p",
        negative_prompt="n",
        seed=1,
        width=512,
        height=512,
        steps=20,
        cfg=7.0,
        sampler="euler",
        scheduler="normal",
        use_controlnet=True,
        controlnet_model_name="controlnet-xl.safetensors",
        controlnet_strength=0.8,
        control_image_path="control.png",
    )

    with pytest.raises(ComfyUIAdapterError) as exc:
        patch_workflow(workflow, mapping, params)

    assert "mapping is incomplete" in str(exc.value)
    assert "optional.controlnet.model_node_id" in str(exc.value)


def test_controlnet_enabled_but_node_missing_in_workflow_raises_error() -> None:
    workflow = _sample_workflow()
    mapping = _sample_mapping()
    mapping["optional"] = mapping.get("optional", {})
    mapping["optional"]["controlnet"] = {
        "enabled_node_id": "",
        "enabled_key": "",
        "model_node_id": "10",
        "model_key": "control_net_name",
        "strength_node_id": "11",
        "strength_key": "strength",
        "image_node_id": "12",
        "image_key": "image",
    }
    params = WorkflowPatchParams(
        positive_prompt="p",
        negative_prompt="n",
        seed=1,
        width=512,
        height=512,
        steps=20,
        cfg=7.0,
        sampler="euler",
        scheduler="normal",
        use_controlnet=True,
        controlnet_model_name="controlnet-xl.safetensors",
        controlnet_strength=0.8,
        control_image_path="control.png",
    )

    with pytest.raises(ComfyUIAdapterError) as exc:
        patch_workflow(workflow, mapping, params)

    assert "node id `10` not found" in str(exc.value)


def test_auto_detect_mode_patches_high_confidence_fields() -> None:
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_unet.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_clip.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_vae.safetensors"}},
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old positive", "clip": ["2", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old negative", "clip": ["2", 0]},
        },
        "6": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
                "seed": 1,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "old_prefix"},
        },
    }
    params = WorkflowPatchParams(
        positive_prompt="new positive",
        negative_prompt="new negative",
        seed=2026,
        width=1024,
        height=1024,
        steps=30,
        cfg=6.5,
        sampler="dpmpp_2m",
        scheduler="karras",
        filename_prefix="auto/item_001",
    )
    patched, report = patch_workflow_with_report(
        workflow=workflow,
        mapping=None,
        params=params,
        mapping_mode="auto_detect",
    )
    assert patched["4"]["inputs"]["text"] == "new positive"
    assert patched["5"]["inputs"]["text"] == "new negative"
    assert patched["6"]["inputs"]["width"] == 1024
    assert patched["6"]["inputs"]["height"] == 1024
    assert patched["7"]["inputs"]["seed"] == 2026
    assert patched["7"]["inputs"]["steps"] == 30
    assert patched["7"]["inputs"]["cfg"] == 6.5
    assert patched["7"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert patched["7"]["inputs"]["scheduler"] == "karras"
    assert report["mapping_mode"] == "auto_detect"
    assert "positive_prompt" in report["patched_fields"]
