from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def suggest_node_mapping(
    inspection_result: dict[str, Any],
    existing_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    suggestion = _build_base_mapping_template()
    confidence: dict[str, str] = {}
    manual_confirmation: list[str] = []

    positive = _pick_prompt_node(inspection_result, role="positive")
    negative = _pick_prompt_node(inspection_result, role="negative")
    latent = _pick_first(inspection_result.get("detected_latent_nodes", []))
    sampler = _pick_first(inspection_result.get("detected_sampler_nodes", []))
    save_image = _pick_first(inspection_result.get("detected_output_nodes", []))
    lora = _pick_lora_node(inspection_result)
    controlnet = _pick_controlnet_node(inspection_result)

    if positive:
        suggestion["required"]["positive_prompt"]["node_id"] = positive["node_id"]
        suggestion["required"]["positive_prompt"]["input_key"] = positive["input_key"]
        confidence["required.positive_prompt"] = "high"
    else:
        confidence["required.positive_prompt"] = "low"
        manual_confirmation.append("required.positive_prompt")

    if negative:
        suggestion["required"]["negative_prompt"]["node_id"] = negative["node_id"]
        suggestion["required"]["negative_prompt"]["input_key"] = negative["input_key"]
        confidence["required.negative_prompt"] = "high"
    else:
        confidence["required.negative_prompt"] = "low"
        manual_confirmation.append("required.negative_prompt")

    if latent:
        latent_map = suggestion["required"]["latent_size"]
        latent_map["node_id"] = str(latent.get("node_id", ""))
        latent_map["width_key"] = str(latent.get("width_key", "width"))
        latent_map["height_key"] = str(latent.get("height_key", "height"))
        latent_map["batch_size_key"] = str(
            latent.get("batch_size_key", "batch_size")
        )
        confidence["required.latent_size"] = "high"
    else:
        confidence["required.latent_size"] = "low"
        manual_confirmation.append("required.latent_size")

    if sampler:
        sampler_map = suggestion["required"]["sampler"]
        sampler_map["node_id"] = str(sampler.get("node_id", ""))
        sampler_map["seed_key"] = str(sampler.get("seed_key", "seed"))
        sampler_map["steps_key"] = str(sampler.get("steps_key", "steps"))
        sampler_map["cfg_key"] = str(sampler.get("cfg_key", "cfg"))
        sampler_map["sampler_key"] = str(sampler.get("sampler_key", "sampler_name"))
        sampler_map["scheduler_key"] = str(sampler.get("scheduler_key", "scheduler"))
        sampler_map["denoise_key"] = str(sampler.get("denoise_key", "denoise"))
        confidence["required.sampler"] = "high"
    else:
        confidence["required.sampler"] = "low"
        manual_confirmation.append("required.sampler")

    if save_image:
        suggestion["optional"]["save_image"]["node_id"] = str(save_image.get("node_id", ""))
        suggestion["optional"]["save_image"]["filename_prefix_key"] = str(
            save_image.get("filename_prefix_key", "filename_prefix")
        )
        confidence["optional.save_image"] = "high"
    else:
        confidence["optional.save_image"] = "medium"
        manual_confirmation.append("optional.save_image.node_id")

    if lora:
        suggestion["optional"]["lora"]["node_id"] = str(lora.get("node_id", ""))
        suggestion["optional"]["lora"]["path_key"] = str(lora.get("path_key", "lora_name"))
        suggestion["optional"]["lora"]["strength_key"] = str(
            lora.get("strength_key", "strength_model")
        )
        confidence["optional.lora"] = "high"
    else:
        confidence["optional.lora"] = "low"

    if controlnet:
        ctrl_map = suggestion["optional"]["controlnet"]
        ctrl_map["model_node_id"] = str(controlnet.get("node_id", ""))
        ctrl_map["model_key"] = str(controlnet.get("model_key", "control_net_name"))
        confidence["optional.controlnet"] = "medium"
        manual_confirmation.extend(
            [
                "optional.controlnet.strength_node_id",
                "optional.controlnet.image_node_id",
            ]
        )
    else:
        confidence["optional.controlnet"] = "low"

    merged_mapping = merge_mapping_override(suggestion, existing_mapping)
    diff_report = (
        compare_mappings(existing_mapping, merged_mapping) if existing_mapping else {}
    )
    field_bindings = build_flat_field_bindings(merged_mapping)
    low_confidence_fields = [
        path for path, level in confidence.items() if str(level).lower() != "high"
    ]
    manual_confirmation.extend(low_confidence_fields)

    return {
        "mapping": merged_mapping,
        "field_bindings": field_bindings,
        "confidence": confidence,
        "needs_manual_confirmation": sorted(set(manual_confirmation)),
        "diff_vs_existing": diff_report,
    }


def build_flat_field_bindings(mapping: dict[str, Any]) -> dict[str, dict[str, str]]:
    required = mapping.get("required", {}) if isinstance(mapping, dict) else {}
    optional = mapping.get("optional", {}) if isinstance(mapping, dict) else {}

    positive = required.get("positive_prompt", {}) if isinstance(required, dict) else {}
    negative = required.get("negative_prompt", {}) if isinstance(required, dict) else {}
    latent = required.get("latent_size", {}) if isinstance(required, dict) else {}
    sampler = required.get("sampler", {}) if isinstance(required, dict) else {}
    save_image = optional.get("save_image", {}) if isinstance(optional, dict) else {}
    lora = optional.get("lora", {}) if isinstance(optional, dict) else {}

    return {
        "positive_prompt": _binding(positive.get("node_id"), positive.get("input_key")),
        "negative_prompt": _binding(negative.get("node_id"), negative.get("input_key")),
        "width": _binding(latent.get("node_id"), latent.get("width_key")),
        "height": _binding(latent.get("node_id"), latent.get("height_key")),
        "batch_size": _binding(latent.get("node_id"), latent.get("batch_size_key")),
        "seed": _binding(sampler.get("node_id"), sampler.get("seed_key")),
        "steps": _binding(sampler.get("node_id"), sampler.get("steps_key")),
        "cfg": _binding(sampler.get("node_id"), sampler.get("cfg_key")),
        "sampler_name": _binding(sampler.get("node_id"), sampler.get("sampler_key")),
        "scheduler": _binding(sampler.get("node_id"), sampler.get("scheduler_key")),
        "denoise": _binding(sampler.get("node_id"), sampler.get("denoise_key")),
        "filename_prefix": _binding(
            save_image.get("node_id"), save_image.get("filename_prefix_key")
        ),
        "lora_name": _binding(lora.get("node_id"), lora.get("path_key")),
        "lora_strength_model": _binding(
            lora.get("node_id"), lora.get("strength_key")
        ),
    }


def merge_mapping_override(
    auto_mapping: dict[str, Any],
    manual_override: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(manual_override, dict):
        return auto_mapping
    merged = deepcopy(auto_mapping)
    _deep_merge_keep_non_empty(merged, manual_override)
    return merged


def compare_mappings(
    old_mapping: dict[str, Any] | None, new_mapping: dict[str, Any] | None
) -> dict[str, Any]:
    old = old_mapping if isinstance(old_mapping, dict) else {}
    new = new_mapping if isinstance(new_mapping, dict) else {}
    changes: list[dict[str, Any]] = []
    _diff_dict("", old, new, changes)
    return {"change_count": len(changes), "changes": changes}


def save_mapping_yaml(mapping: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return output


def build_mapping_manual_review_payload(suggestion: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "needs_manual_confirmation",
        "items": list(suggestion.get("needs_manual_confirmation", [])),
        "confidence": suggestion.get("confidence", {}),
        "field_bindings": suggestion.get("field_bindings", {}),
        "note": (
            "The listed items are low-confidence or unresolved fields. "
            "Please confirm manually before production use."
        ),
    }


def save_mapping_manual_review_yaml(
    suggestion: dict[str, Any], output_path: str | Path
) -> Path:
    payload = build_mapping_manual_review_payload(suggestion)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return output


def build_mapping_diff_markdown(diff_report: dict[str, Any]) -> str:
    changes = diff_report.get("changes", []) if isinstance(diff_report, dict) else []
    lines = [
        "# Mapping Diff",
        "",
        f"- change_count: `{len(changes)}`",
        "",
    ]
    if not changes:
        lines.append("No changes.")
        return "\n".join(lines) + "\n"

    lines.append("| Path | Old | New |")
    lines.append("| --- | --- | --- |")
    for item in changes:
        old = str(item.get("old", "")).replace("\n", "\\n")
        new = str(item.get("new", "")).replace("\n", "\\n")
        lines.append(f"| `{item.get('path','')}` | `{old}` | `{new}` |")
    return "\n".join(lines) + "\n"


def save_mapping_diff_markdown(diff_report: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_mapping_diff_markdown(diff_report), encoding="utf-8")
    return output


def _build_base_mapping_template() -> dict[str, Any]:
    return {
        "meta": {
            "name": "auto_suggested_node_map",
            "workflow_format": "comfyui_api_prompt",
            "notes": (
                "Auto-generated suggestion. Please manually confirm low-confidence "
                "and custom-node related fields before production use."
            ),
        },
        "required": {
            "positive_prompt": {"node_id": "", "input_key": "text"},
            "negative_prompt": {"node_id": "", "input_key": "text"},
            "latent_size": {
                "node_id": "",
                "width_key": "width",
                "height_key": "height",
                "batch_size_key": "batch_size",
            },
            "sampler": {
                "node_id": "",
                "seed_key": "seed",
                "steps_key": "steps",
                "cfg_key": "cfg",
                "sampler_key": "sampler_name",
                "scheduler_key": "scheduler",
                "denoise_key": "denoise",
            },
        },
        "optional": {
            "save_image": {
                "node_id": "",
                "filename_prefix_key": "filename_prefix",
                "output_dir_key": "",
            },
            "lora": {
                "node_id": "",
                "enabled_key": "",
                "path_key": "lora_name",
                "strength_key": "strength_model",
            },
            "controlnet": {
                "enabled_node_id": "",
                "enabled_key": "",
                "model_node_id": "",
                "model_key": "control_net_name",
                "strength_node_id": "",
                "strength_key": "strength",
                "image_node_id": "",
                "image_key": "image",
            },
        },
    }


def _binding(node_id: Any, input_key: Any) -> dict[str, str]:
    return {
        "node_id": str(node_id or ""),
        "input": str(input_key or ""),
    }


def _pick_first(items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if isinstance(items, list) and items:
        return items[0]
    return None


def _pick_prompt_node(
    inspection_result: dict[str, Any], role: str
) -> dict[str, Any] | None:
    prompt_nodes = inspection_result.get("detected_prompt_nodes", [])
    exact = [node for node in prompt_nodes if str(node.get("role")) == role]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact[0]
    unknown = [node for node in prompt_nodes if str(node.get("role")) == "unknown"]
    if len(unknown) == 1:
        return unknown[0]
    return None


def _pick_lora_node(inspection_result: dict[str, Any]) -> dict[str, Any] | None:
    for node in inspection_result.get("detected_loader_nodes", []):
        class_type = str(node.get("class_type", ""))
        if class_type in {"LoraLoader", "LoraLoaderModelOnly"}:
            keys = {str(key) for key in node.get("input_keys", [])}
            strength_key = (
                "strength_model"
                if "strength_model" in keys
                else ("strength" if "strength" in keys else "strength_model")
            )
            return {
                "node_id": str(node.get("node_id", "")),
                "path_key": "lora_name" if "lora_name" in keys else "",
                "strength_key": strength_key,
            }
    return None


def _pick_controlnet_node(inspection_result: dict[str, Any]) -> dict[str, Any] | None:
    for node in inspection_result.get("detected_loader_nodes", []):
        class_type = str(node.get("class_type", ""))
        if class_type == "ControlNetLoader":
            keys = {str(key) for key in node.get("input_keys", [])}
            return {
                "node_id": str(node.get("node_id", "")),
                "model_key": "control_net_name"
                if "control_net_name" in keys
                else "control_net_name",
            }
    return None


def _deep_merge_keep_non_empty(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            if key not in target or not isinstance(target.get(key), dict):
                target[key] = {}
            _deep_merge_keep_non_empty(target[key], value)
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        target[key] = value


def _diff_dict(
    prefix: str,
    old: dict[str, Any],
    new: dict[str, Any],
    changes: list[dict[str, Any]],
) -> None:
    keys = sorted(set(old.keys()) | set(new.keys()))
    for key in keys:
        path = f"{prefix}.{key}" if prefix else key
        old_val = old.get(key)
        new_val = new.get(key)
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            _diff_dict(path, old_val, new_val, changes)
            continue
        if old_val != new_val:
            changes.append({"path": path, "old": old_val, "new": new_val})
