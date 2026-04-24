from __future__ import annotations

from pathlib import Path

from src.generation.mapping_suggester import suggest_node_mapping
from src.generation.workflow_inspector import inspect_workflow_path


ROOT = Path(__file__).resolve().parents[1]
Z_WORKFLOW = ROOT / "workflows/comfyui/image_z_image_turbo_api.json"
QWEN_WORKFLOW = ROOT / "workflows/comfyui/qwen_image_illustration_lora_api.json"


def test_suggest_mapping_real_export_z_image_turbo() -> None:
    inspection = inspect_workflow_path(Z_WORKFLOW)
    suggestion = suggest_node_mapping(inspection)
    bindings = suggestion["field_bindings"]

    assert bindings["positive_prompt"] == {"node_id": "57:27", "input": "text"}
    assert bindings["width"] == {"node_id": "57:13", "input": "width"}
    assert bindings["height"] == {"node_id": "57:13", "input": "height"}
    assert bindings["batch_size"] == {"node_id": "57:13", "input": "batch_size"}
    assert bindings["seed"] == {"node_id": "57:3", "input": "seed"}
    assert bindings["steps"] == {"node_id": "57:3", "input": "steps"}
    assert bindings["cfg"] == {"node_id": "57:3", "input": "cfg"}
    assert bindings["sampler_name"] == {"node_id": "57:3", "input": "sampler_name"}
    assert bindings["scheduler"] == {"node_id": "57:3", "input": "scheduler"}
    assert bindings["denoise"] == {"node_id": "57:3", "input": "denoise"}
    assert bindings["filename_prefix"] == {"node_id": "9", "input": "filename_prefix"}


def test_suggest_mapping_real_export_qwen_lora() -> None:
    inspection = inspect_workflow_path(QWEN_WORKFLOW)
    suggestion = suggest_node_mapping(inspection)
    bindings = suggestion["field_bindings"]

    assert bindings["positive_prompt"] == {"node_id": "76:6", "input": "text"}
    assert bindings["negative_prompt"] == {"node_id": "76:7", "input": "text"}
    assert bindings["width"] == {"node_id": "76:58", "input": "width"}
    assert bindings["height"] == {"node_id": "76:58", "input": "height"}
    assert bindings["batch_size"] == {"node_id": "76:58", "input": "batch_size"}
    assert bindings["seed"] == {"node_id": "76:3", "input": "seed"}
    assert bindings["steps"] == {"node_id": "76:3", "input": "steps"}
    assert bindings["cfg"] == {"node_id": "76:3", "input": "cfg"}
    assert bindings["sampler_name"] == {"node_id": "76:3", "input": "sampler_name"}
    assert bindings["scheduler"] == {"node_id": "76:3", "input": "scheduler"}
    assert bindings["denoise"] == {"node_id": "76:3", "input": "denoise"}
    assert bindings["lora_name"] == {"node_id": "76:73", "input": "lora_name"}
    assert bindings["lora_strength_model"] == {
        "node_id": "76:73",
        "input": "strength_model",
    }
    assert bindings["filename_prefix"] == {"node_id": "60", "input": "filename_prefix"}
