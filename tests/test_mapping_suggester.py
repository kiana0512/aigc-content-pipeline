from __future__ import annotations

from src.generation.mapping_suggester import (
    build_mapping_diff_markdown,
    build_mapping_manual_review_payload,
    compare_mappings,
    suggest_node_mapping,
)


def _inspection_result() -> dict:
    return {
        "workflow_format": "comfyui_api_prompt",
        "detected_prompt_nodes": [
            {
                "node_id": "4",
                "class_type": "CLIPTextEncode",
                "role": "positive",
                "input_key": "text",
            },
            {
                "node_id": "5",
                "class_type": "CLIPTextEncode",
                "role": "negative",
                "input_key": "text",
            },
        ],
        "detected_latent_nodes": [
            {
                "node_id": "6",
                "class_type": "EmptySD3LatentImage",
                "width_key": "width",
                "height_key": "height",
            }
        ],
        "detected_sampler_nodes": [
            {
                "node_id": "8",
                "class_type": "KSampler",
                "seed_key": "seed",
                "steps_key": "steps",
                "cfg_key": "cfg",
                "sampler_key": "sampler_name",
                "scheduler_key": "scheduler",
            }
        ],
        "detected_output_nodes": [
            {
                "node_id": "10",
                "class_type": "SaveImage",
                "filename_prefix_key": "filename_prefix",
            }
        ],
        "detected_loader_nodes": [
            {
                "node_id": "7",
                "class_type": "LoraLoaderModelOnly",
                "input_keys": ["model", "lora_name", "strength_model"],
            }
        ],
    }


def test_suggest_node_mapping_generates_required_fields() -> None:
    suggestion = suggest_node_mapping(_inspection_result())
    mapping = suggestion["mapping"]
    assert mapping["required"]["positive_prompt"]["node_id"] == "4"
    assert mapping["required"]["negative_prompt"]["node_id"] == "5"
    assert mapping["required"]["latent_size"]["node_id"] == "6"
    assert mapping["required"]["sampler"]["node_id"] == "8"
    assert mapping["optional"]["save_image"]["node_id"] == "10"

    confidence = suggestion["confidence"]
    assert confidence["required.positive_prompt"] == "high"
    assert confidence["required.sampler"] == "high"


def test_suggest_node_mapping_respects_manual_override() -> None:
    existing = {
        "required": {
            "positive_prompt": {"node_id": "99", "input_key": "text"},
            "negative_prompt": {"node_id": "5", "input_key": "text"},
            "latent_size": {"node_id": "6", "width_key": "width", "height_key": "height"},
            "sampler": {
                "node_id": "8",
                "seed_key": "seed",
                "steps_key": "steps",
                "cfg_key": "cfg",
                "sampler_key": "sampler_name",
                "scheduler_key": "scheduler",
            },
        }
    }
    suggestion = suggest_node_mapping(_inspection_result(), existing_mapping=existing)
    assert suggestion["mapping"]["required"]["positive_prompt"]["node_id"] == "99"
    diff = suggestion["diff_vs_existing"]
    assert diff["change_count"] >= 1


def test_compare_mappings_reports_changes() -> None:
    old = {"required": {"positive_prompt": {"node_id": "1"}}}
    new = {"required": {"positive_prompt": {"node_id": "2"}}}
    diff = compare_mappings(old, new)
    assert diff["change_count"] == 1
    assert diff["changes"][0]["path"] == "required.positive_prompt.node_id"


def test_manual_review_payload_and_diff_markdown() -> None:
    suggestion = suggest_node_mapping(_inspection_result())
    payload = build_mapping_manual_review_payload(suggestion)
    assert payload["status"] == "needs_manual_confirmation"
    assert isinstance(payload["items"], list)

    md = build_mapping_diff_markdown({"changes": [{"path": "a.b", "old": "1", "new": "2"}]})
    assert "| `a.b` | `1` | `2` |" in md
