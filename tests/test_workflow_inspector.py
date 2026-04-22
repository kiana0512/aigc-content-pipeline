from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.generation.workflow_inspector import (
    PLACEHOLDER_WORKFLOW_ERROR,
    detect_workflow_format,
    inspect_workflow,
    inspect_workflow_path,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
QWEN_FIXTURE = FIXTURES_DIR / "qwen_api_workflow.json"


def _load_qwen_fixture() -> dict:
    return json.loads(QWEN_FIXTURE.read_text(encoding="utf-8"))


def test_detect_workflow_format_api_graph_from_fixture() -> None:
    workflow = _load_qwen_fixture()
    assert detect_workflow_format(workflow) == "comfyui_api_prompt"


def test_inspect_workflow_qwen_fixture_core_detection() -> None:
    result = inspect_workflow(_load_qwen_fixture())

    assert result["workflow_format"] == "comfyui_api_prompt"
    assert result["suggested_model_family"] == "split_model"
    assert "split_model" in result["detected_model_families"]

    loader_classes = {item["class_type"] for item in result["detected_loader_nodes"]}
    assert "UNETLoader" in loader_classes
    assert "CLIPLoader" in loader_classes
    assert "VAELoader" in loader_classes
    assert "LoraLoaderModelOnly" in loader_classes

    sampler_nodes = result["detected_sampler_nodes"]
    assert len(sampler_nodes) == 1
    assert sampler_nodes[0]["class_type"] == "KSampler"

    output_nodes = result["detected_output_nodes"]
    assert len(output_nodes) == 1
    assert output_nodes[0]["class_type"] == "SaveImage"

    prompt_nodes = result["detected_prompt_nodes"]
    roles = {item["role"] for item in prompt_nodes}
    assert "positive" in roles
    assert "negative" in roles

    params = result["detected_parameters"]
    assert params["width"] == 1024
    assert params["height"] == 1024
    assert params["seed"] == 20260422
    assert params["steps"] == 28
    assert params["cfg"] == 5.5
    assert params["sampler"] == "euler"
    assert params["scheduler"] == "karras"
    assert params["filename_prefix"] == "qwen_image_example"
    assert "game icon style" in params["positive_prompt"]
    assert "low quality" in params["negative_prompt"]


def test_inspect_workflow_path_supports_prompt_wrapped_payload(tmp_path: Path) -> None:
    payload = {"prompt": _load_qwen_fixture()}
    path = tmp_path / "qwen_api_wrapped.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = inspect_workflow_path(path)
    assert result["workflow_format"] == "comfyui_api_prompt_wrapped"
    assert result["source_path"].endswith("qwen_api_wrapped.json")


def test_inspect_workflow_unknown_custom_node_does_not_crash() -> None:
    workflow = _load_qwen_fixture()
    workflow["11"] = {"class_type": "CustomFooNode", "inputs": {"foo": 1}}
    result = inspect_workflow(workflow)
    assert any(item["class_type"] == "CustomFooNode" for item in result["detected_custom_nodes"])
    assert any(item["class_type"] == "CustomFooNode" for item in result["unresolved_nodes"])


def test_inspect_workflow_rejects_placeholder() -> None:
    placeholder = {"workflow_name": "x", "status": {"is_placeholder": True}}
    with pytest.raises(ValueError) as exc:
        inspect_workflow(placeholder)
    assert PLACEHOLDER_WORKFLOW_ERROR in str(exc.value)


def test_inspect_workflow_rejects_ui_json() -> None:
    ui_payload = {"nodes": [{"id": 1, "type": "KSampler"}]}
    with pytest.raises(ValueError) as exc:
        inspect_workflow(ui_payload)
    assert "UI format" in str(exc.value)
